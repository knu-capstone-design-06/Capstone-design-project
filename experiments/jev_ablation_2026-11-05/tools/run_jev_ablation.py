"""E5 offline Jev-ablation harness: replay vision window records through PR #77's decision module.

Per take and window: build the rule table's WindowInput from the window record, run tick -> decide -> apply
(the vision replay's order, ai-engine/app/modules/vision/chain.py WindowJudge.evaluate), then for every arm
(condition x variant) run the PR's own DecisionService.ask_shadow with that arm's stages against a stub or the
real Jev client, the way DecisionService.observe does (backend/app/modules/decision/service.py:75-98), but
synchronously and with this script's WindowInput (the PR's window_input() fills neither the vision fields nor
steps_left / progress_segment, and the service never calls tick / react).

Timing semantics (as implemented in the PR): the stages of one window run in that window's background task, one
after another, so stage 2 (support_choice) sees stage 1's answers of the SAME window. The docs' diagram variant
(docs/Jev-Integration.md 9.5: stage 2 at window N+1 with window N's scores) is not evaluated. Offline, every
measurable window's chain is awaited before the next window (--in-flight record, the default): no window is
skipped for a call still in flight; the windows the live service would have skipped are only flagged.

The PR code is imported, never edited: --backend (or the environment variable E5_BACKEND) points at a checkout's
backend/ folder with PR #77 (branch feat/jev at 3c936ae, or main after the merge). Outputs (--out): rule_windows.jsonl
(one line per window: input, rule decision, candidates, label),
jev_calls.jsonl (one line per arm and window: each stage's answer, confidence, latency, tokens, skip flags),
repeats.jsonl (each distinct request sent repeats - 1 more times), states.jsonl and questions.json (each
distinct state / question set once, by hash), run_settings.json; --write-settings also writes the frozen
settings (parameters, model, question texts, mappings, fallbacks, file hashes).

Answer sources (--jev): stub = the fake answers below; real = the Jev API with the key from the environment
(JEV_API_KEY) or <backend>/.env, never printed; cache = recorded answers only (--cache-file, read-only, .jsonl or
.jsonl.gz): no key, no network, no API call; a request missing from the cache gets no answer ('cache miss', counted
apart from API calls). --answer-pins / --pin-run (cache mode) give back, window by window, the answer a recorded run
used where the cache holds two answers for one request (the same request sent twice at the same moment).
Inputs may be gzipped (<take>.jsonl.gz, <take>/windows.jsonl.gz, windows_<bundle>.csv.gz).

Stub answers (--jev stub) are deterministic fakes for checking the mechanics and are never Jev results:
  noul    p = U(seed | question name | question JSON | state JSON)
  choice  w_o = U(seed | question name | option | question JSON | state JSON) for every option o in criteria
          order; probabilities = w_o / sum(w); choice = the first option with the largest probability;
          confidence = (p_max - 1/n) / (1 - 1/n), n = number of options (1.0 when n = 1)
  U(x) = the first 13 hex digits of sha256(x) / 16**13 (uniform in [0, 1)); usage tokens 0; model "stub".
  --stub-fail-every N (0 = never): every N-th call of the run returns no answer, only to exercise that path.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True   # never write __pycache__ into the PR worktree

import argparse
import asyncio
import contextvars
import copy
import gzip
import hashlib
import json
import logging
import os
import platform
import subprocess
import time
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
PKG = HERE.parent                                   # experiments/jev_ablation_2026-11-05
INPUTS = PKG / "inputs"
# the recorded set ran on PR #77 commit 3c936ae (approved 2026-11-05); rescore_labels.py checks the run's commit
DEFAULT_BACKEND = os.environ.get("E5_BACKEND")
DEFAULT_LABELS = INPUTS / "labels" / "judgment_labels_v4.csv"     # time-mode labels (vision windows), labels v4
DEFAULT_ADMISSIBLE = INPUTS / "labels" / "admissible_v4.csv"      # per segment x touch condition x variant, labels v4
BUNDLES = INPUTS / "bundles"                                      # E3 value bundles (the situation window_s)
DEFAULT_WINDOWS_DIR = INPUTS / "e3_windows"                       # E3 AB0 window rows windows_<bundle>.csv.gz
KST = timezone(timedelta(hours=9))
CURRENT = contextvars.ContextVar("e5_window", default=None)       # (arm, take, window index) being asked (answer pins)
FAILURE_GUARD_MIN_CALLS = 100   # Claude's choice: the failure-rate stop is checked once this many calls were made

# The rule table's screen order (ai-engine/app/modules/vision/touch.py:59, OrderPage.tsx: menu -> review -> complete).
SCREEN_FLOW = ("menu", "review", "complete")
TOUCH_FIVE = ("tap_count", "miss_tap_count", "repeat_tap_count", "back_count", "dwell_ms")   # contract TouchFeatures

# Conditions: backend setting JEV_STAGES (docs/Jev-Integration.md 7.1). E is that table's 'n stages' row with all
# three registered stages.
CONDITIONS = {
    "A": "off",
    "B": "state_scores",
    "C": "state_scores,support_choice",
    "D": "state_scores,next_difficulty",
    "E": "state_scores,support_choice,next_difficulty",
    "C0": "support_choice",          # control: C without the stage-1 scores (same raw state, candidates, question)
    # Jev alone: the PR's support_choice question with every support of the rule table + none as options, no rule
    # filter (a harness stage around the PR's SupportChoiceStage; not a JEV_STAGES value)
    "J": "support_choice_all",
}
ALL_SUPPORTS = ("wait_hold_timer", "remaining_steps_notice", "delay_responsibility_notice", "large_button",
                "highlight_next_action", "defer_big_button_question")   # rule_table.py rows in rank order
# rule_table.WHAT has no line for the 3-2 wait (it is a session action, never a Jev option in the PR); the Jev-alone
# arm needs one. Claude's text, from the rule table's own description of 3-2 (wait, hold timer, companion talk):
WAIT_WHAT = "Pause the session timer and show nothing while the user talks with a companion"
WORDING_DIR = HERE / "wording"
VARIANTS = {
    "novision": "state.situation and state.vision set to null (also history[*].tag in trajectory stages)",
    "notouch": "state.touch set to null (also history[*].touch in trajectory stages)",
    "la_null": "state.vision.looking_around null when the window's situation is missing or unknown "
               "(PR rule_table.py:160 sends false)",
    "sit_dict": "the window's situation record passed even when its tag is unknown, so state.situation.tag is "
                "'unknown' instead of null (the vision chain's form when a value bundle exists)",
    "vision_summary": "the window record's vision summary (frames, face_seen_ratio, body_seen_ratio, head_count_max, "
                      "people_behind_max, companion_frames, mouth_motion_max) added to state.vision, as in the "
                      "multimodal proposal (docs/Jev-Integration.md 9.2) and the vision README's window summary",
    "wording_nocrit": "the five state_scores questions sent without their criteria (instructions only; noul "
                      "criteria are optional in the API, docs/Jev-Integration.md 3)",
    "wording": "wording=<file>: question texts merged by name from a JSON file {stage: {question: {instructions, "
               "criteria}}} (instructions replaced; criteria texts replaced only for options the question has)",
    "wording_formal": "the state questions and the support_choice question in a more formal register "
                      "(tools/wording/formal_v1.json, Claude's text)",
    "wording_short": "the state questions and the support_choice question shortened (tools/wording/short_v1.json, "
                     "Claude's text)",
    "nohistory": "support_choice stage only: state.session.withdrawn and state.session.held left out (the probe of "
                 "whether Jev's declines follow the session history; red team E5 stage 1 #3)",
    "perm_vision": "permuted-values control: state.situation and state.vision taken from another measurable window of "
                   "the same session (seeded permutation, --perm-seed)",
    "perm_touch": "permuted-values control: state.touch taken from another measurable window of the same session "
                  "(seeded permutation, --perm-seed)",
}
DEFAULT_ARMS = ("A", "B", "C", "C0", "D", "E", "B:novision", "B:notouch", "B:la_null", "B:sit_dict", "B:vision_summary",
                "B:wording_nocrit", "B:perm_vision", "B:perm_touch")


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj) -> str:
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()[:16]


INPUT_FILES: set = set()      # every input file a run reads; their sha256 go into run_settings.json


def sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha_content(path) -> str:
    """sha256 of the uncompressed bytes of a .gz file (= the hash of the file it was made from)."""
    h = hashlib.sha256()
    with gzip.open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def open_text(path):
    """A UTF-8 text file, gzipped (.gz) or not."""
    path = Path(path)
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else open(path, encoding="utf-8")


def take_name(path: Path) -> str:
    """<take>.jsonl or <take>.jsonl.gz -> <take>."""
    for ext in (".jsonl.gz", ".jsonl"):
        if path.name.endswith(ext):
            return path.name[: -len(ext)]
    return path.stem


def unit(*parts) -> float:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:13], 16) / 16 ** 13


# ---------------------------------------------------------------------------------------------------- PR imports


class PR:
    """The PR's modules, imported from --backend (sys.path tweak here, nothing vendored)."""

    def __init__(self, backend: Path):
        if not (backend / "app" / "modules" / "decision" / "rule_table.py").is_file():
            raise SystemExit(f"no decision module under {backend}")
        sys.path.insert(0, str(backend))
        from app.common.config import settings as settings_mod
        from app.infrastructure.external import jev_client, jev_schemas
        from app.modules.decision import jev_questions, repository, rule_table, schemas, service
        from app.modules.sessions import schemas as session_schemas
        self.backend = backend
        self.R = rule_table
        self.S = schemas
        self.Q = jev_questions
        self.repo = repository
        self.svc = service
        self.client = jev_client
        self.js = jev_schemas
        self.settings = settings_mod
        self.TouchFeatures = session_schemas.TouchFeatures
        self.params = schemas.PILOT_PARAMS
        # 3c936ae: DecisionRepository.add_window(WindowRecord) and HISTORY_WINDOWS in schemas; 0114ed1: add_window(
        # session_id, summary dict) and HISTORY_WINDOWS in repository. window_record() below builds either form.
        self.window_records = hasattr(schemas, "WindowRecord")
        self.history_windows = getattr(schemas, "HISTORY_WINDOWS", getattr(repository, "HISTORY_WINDOWS", None))
        try:
            self.commit = subprocess.run(["git", "-C", str(backend), "rev-parse", "HEAD"], capture_output=True,
                                         text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            self.commit = None
        # the support -> action map of the rule rows (rule_table.py candidate_rows) and the 3-1 choice_actions
        self.action_of = {schemas.WAIT: "wait", schemas.NOTICE: "apply", schemas.DELAY: "apply",
                          schemas.BIG: "propose", schemas.HIGHLIGHT: "apply", schemas.DEFER: "wait"}


def add_window(pr: "PR", repo, service, sid: str, w, window_end: datetime, why: str) -> None:
    """Shim for the PR's DecisionRepository.add_window, as DecisionService.observe calls it (no change to the PR copy).
    3c936ae (service.py observe): a WindowRecord of the window's input line, the rule decision, the arm's stages and
    why Jev was or was not asked; the trajectory history is read back from it. 0114ed1 (service.py:87-91): the summary
    dict. Both give repository.history() the same fields (t, tag, screen, measurable, decision, support, touch)."""
    d = w.decision
    if pr.window_records:
        repo.add_window(pr.S.WindowRecord(
            sid, window_end, w.inp.t, asdict(w.inp),
            {"transition": d.transition, "support": d.support, "scene": d.scene, "action": d.action,
             "decision_id": d.decision_id, "reason": d.reason, "tag": d.meta.get("tag"), "policy": d.policy},
            tuple(getattr(service, "stage_names", ())), why,
            service._jev.model if getattr(service, "_jev", None) else None, w.expired_id))
    else:
        repo.add_window(sid, {
            "t": w.inp.t, "tag": d.meta.get("tag"), "screen": w.inp.screen, "measurable": w.inp.measurable,
            "decision": d.transition, "support": d.support,
            "touch": {"taps": w.inp.taps_segment, "misses": w.inp.misses_recent, "backs": w.inp.backs_recent},
        })


# ---------------------------------------------------------------------------------------------------- inputs


def load_takes(paths: list[Path], only: set[str] | None, windows_name: str = "windows.jsonl") -> dict[str, list[dict]]:
    """{take: window records}. A path is a replay folder (<take>/windows.jsonl), a folder of <take>.jsonl files
    (aligned layout, fixtures) or one .jsonl file (take = its stem)."""
    files: list[tuple[str, Path]] = []
    for p in paths:
        if p.is_file():
            files.append((take_name(p), p))
        elif p.is_dir():
            nested = sorted(p.glob(f"*/{windows_name}")) + sorted(p.glob(f"*/{windows_name}.gz"))
            flat = sorted(p.glob("*.jsonl")) + sorted(p.glob("*.jsonl.gz"))
            files += [(f.parent.name, f) for f in nested] + [(take_name(f), f) for f in flat]
        else:
            raise SystemExit(f"input not found: {p}")
    takes: dict[str, list[dict]] = {}
    for take, f in files:
        if only and take not in only:
            continue
        if take in takes:
            raise SystemExit(f"take {take} appears twice in the inputs")
        INPUT_FILES.add(str(f))
        with open_text(f) as fh:
            takes[take] = [json.loads(line) for line in fh if line.strip()]
    return takes


# E2's verified window labels of the 2026-10-28 team recording (datasets/team_recording_2026-10-28/labels/)
VERIFIED_LABELS = INPUTS / "labels" / "window_labels_v1_verified.csv"
TAG_ORDER = ("looking_back_with_people_behind", "consulting_companion", "looking_around")   # decision 2026-10-10 §3


def verified_tags(bundle: str) -> tuple:
    """The tag of a window from the verified window labels, by E3's AB0-GT rule (eval_ab_2026-11-04/tools/
    followups_204.py gt_tag, E2's TAG_REFERENCE): label seconds s with t - window_s < s <= t; behind = someone behind
    and the user looking back; companion = consulting a companion with a companion present; looking around = looking
    around with nobody behind; several -> the first in TAG_ORDER; none of them -> 'none'. window_s from the bundle file.
    Returns (function (clip, t) -> (tag, number of tags that hold), window_s)."""
    import csv as _csv
    INPUT_FILES.update({str(BUNDLES / f"{bundle}.json"), str(VERIFIED_LABELS)})
    wsec = float(json.loads((BUNDLES / f"{bundle}.json").read_text(encoding="utf-8"))
                 ["situation"]["window_s"]["value"])
    num = lambda v: int(v) if str(v).isdigit() else 0
    labs: dict = {}
    with open(VERIFIED_LABELS, encoding="utf-8-sig", newline="") as fh:
        for r in _csv.DictReader(fh):
            labs.setdefault(r["clip"], []).append({
                "sec": int(r["sec"]), "behind_n": num(r["behind_n"]), "companions_n": num(r["companions_n"]),
                "back": r["user_looking_back"] == "true", "companion": r["consulting_companion"] == "true",
                "around": r["looking_around"] == "true"})

    def tag(clip: str, t: float):
        xs = [x for x in labs.get(clip, []) if t - wsec < x["sec"] <= t + 1e-6]
        held = []
        if any(x["behind_n"] > 0 for x in xs) and any(x["back"] for x in xs):
            held.append(TAG_ORDER[0])
        if any(x["companion"] and x["companions_n"] > 0 for x in xs):
            held.append(TAG_ORDER[1])
        if xs and any(x["around"] for x in xs) and all(x["behind_n"] == 0 for x in xs):
            held.append(TAG_ORDER[2])
        return (held[0] if held else "none"), len(held)
    return tag, wsec


def load_aligned(dirs: list[Path], bundle: str, conditions: set | None, variant: str, only: set | None,
                 windows_dir: Path, tag_source: str = "replay") -> dict[str, list[dict]]:
    """E3's aligned windows (one line per window x touch condition; synthetic touch fields, the replay's vision
    summary, segment_id) joined to E3's AB0 window rows of one value bundle (results/windows_<bundle>.csv: the
    situation name, gaze, measurable and session reset the bundle gives, and AB0's decision for the parity check).
    Each take x condition becomes its own take '<take>@<condition>'."""
    import csv as _csv
    ab0 = {}
    import gzip as _gzip
    path = windows_dir / f"windows_{bundle}.csv"
    if not path.is_file() and (windows_dir / f"windows_{bundle}.csv.gz").is_file():
        path = windows_dir / f"windows_{bundle}.csv.gz"          # E3 may keep the rows gzipped
    if not path.is_file():
        raise SystemExit(f"no E3 window rows for bundle {bundle}: {path}")
    opener = _gzip.open if path.suffix == ".gz" else open
    INPUT_FILES.add(str(path))
    with opener(path, "rt", encoding="utf-8-sig", newline="") as fh:
        for r in _csv.DictReader(fh):
            if r["line"] == "AB0" and r["variant"] == variant:
                ab0[(r["take"], r["condition"], round(float(r["t"]), 4))] = r
    tri = {"True": True, "False": False, "": None}
    gt = verified_tags(bundle)[0] if tag_source == "verified" else None
    out: dict[str, list[dict]] = {}
    for d in dirs:
        for f in sorted(list(d.glob("*.jsonl")) + list(d.glob("*.jsonl.gz"))):
            if only and take_name(f) not in only:
                continue
            INPUT_FILES.add(str(f))
            with open_text(f) as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    a = json.loads(line)
                    cond = a["condition"]
                    if conditions and cond not in conditions:
                        continue
                    if a.get("variant") not in (None, variant):
                        continue
                    row = ab0.get((a["take"], cond, round(float(a["t"]), 4)))
                    if row is None:
                        raise SystemExit(f"no AB0 row for {a['take']} {cond} t={a['t']} in {path}")
                    tch = a.get("touch") or {}
                    out.setdefault(f"{a['take']}@{cond}", []).append({
                        "t": float(a["t"]), "segment_s": a.get("segment_s"), "segment_id": a.get("segment_id"),
                        "clip": a["take"], "condition": cond, "variant": variant, "bundle": bundle,
                        "touch_source": a.get("touch_source"),
                        "situation": (row["situation"] or "unknown") if gt is None else gt(a["take"], float(a["t"]))[0],
                        "situation_replay": row["situation"] or "unknown", "tag_source": tag_source,
                        "vision": {**(a.get("vision") or {}), "facing_screen": tri.get(row["gaze"])},
                        "measurable": row["measurable"] == "True", "session_reset": row["session_reset"] == "True",
                        "screen": {"name": tch.get("screen"), "steps_left": tch.get("steps_left"),
                                   "pause_s": tch.get("pause_s"), "options_open": tch.get("options_open")},
                        "progress_segment": tch.get("progress_segment"),
                        "touch": None if tch.get("taps_segment") is None else {"tap_count": tch["taps_segment"]},
                        "window_input": {k: tch.get(k) for k in ("taps_segment", "misses_recent", "fixes_recent",
                                                                 "backs_recent", "pause_s", "options_open", "screen",
                                                                 "steps_left", "progress_segment")},
                        "decision": None if gt is not None else {"transition": row["transition"],
                                                                 "support": row["support"] or None},
                    })
    for recs in out.values():
        recs.sort(key=lambda r: r["t"])
    return out


def take_start(take: str) -> datetime:
    """Wall time of a take's t = 0 from its name (YYYYMMDD_HHMMSS, KST), else the epoch: only window_end uses it."""
    try:
        return datetime.strptime(take[:15], "%Y%m%d_%H%M%S").replace(tzinfo=KST)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass
class Window:
    take: str
    i: int
    t: float
    session_k: int
    record: dict
    inp: object                       # WindowInput
    situation_raw: dict | None        # the record's situation view (for the sit_dict variant)
    touch: object | None              # TouchFeatures or None
    sources: dict = field(default_factory=dict)
    before: object = None             # SessionState the rule table decided on (after tick, before apply)
    decision: object = None           # the applied Decision (with its id)
    expired_id: str | None = None
    allowed: list = field(default_factory=list)


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def recent_counts(records: list[dict], j: int, start_j: int, span_s: float) -> tuple[dict | None, str]:
    """Touch counts over the recent span ending at window j: the record's own touch_recent when it has one, else the
    sum of the segment counts of this session's windows whose segment lies inside (t - span, t]. None when one of
    them has no touch counts (the vision timeline's counts() is None outside an observed span)."""
    rec = records[j]
    if isinstance(rec.get("touch_recent"), dict):
        return rec["touch_recent"], "record touch_recent"
    t = float(rec["t"])
    keys = ("miss_tap_count", "near_miss_fix_count", "back_count", "tap_count")
    total = {k: 0 for k in keys}
    used = 0
    for k in range(start_j, j + 1):
        r = records[k]
        seg = r.get("segment_s") or [float(r["t"]) - 1.0, float(r["t"])]
        if float(seg[0]) < t - span_s - 1e-9 or float(seg[1]) > t + 1e-9:
            continue
        touch = r.get("touch")
        if not isinstance(touch, dict):
            return None, "segment sum (a window without touch)"
        used += 1
        for key in keys:
            v = touch.get(key)
            total[key] = None if (total[key] is None or _int(v) is None) else total[key] + v
    if used == 0:
        return None, "segment sum (no window)"
    return total, f"segment sum ({used} windows)"


def build_windows(pr: PR, take: str, records: list[dict]) -> list[Window]:
    """WindowInput per record (JP 0-2 input line), the same field sources as chain.py WindowJudge.evaluate."""
    S, p = pr.S, pr.params
    out: list[Window] = []
    session_k, start_j, prev_screen = 0, 0, None
    for j, rec in enumerate(records):
        if rec.get("session_reset"):
            session_k, start_j, prev_screen = session_k + 1, j, None
        sources = {}
        wi = rec.get("window_input") if isinstance(rec.get("window_input"), dict) else None
        sit = rec.get("situation")
        if isinstance(sit, str):                      # flat records: the tag name only
            sit = {"name": sit, "evidence": [], "confidence": "unknown" if sit == S.UNKNOWN else None}
        sit = sit if isinstance(sit, dict) else None
        known = sit is not None and sit.get("name") not in (None, S.UNKNOWN)
        situation = sit if known else None            # missing or unknown -> None (brief; variant sit_dict keeps it)
        screen = rec.get("screen") or {}
        if not isinstance(screen, dict):              # flat records: screen name and steps_left at the top
            screen = {"name": screen, "steps_left": rec.get("steps_left"), "pause_s": rec.get("pause_s"),
                      "options_open": rec.get("options_open")}
        vision = rec.get("vision") if isinstance(rec.get("vision"), dict) else {"facing_screen": rec.get("gaze")}
        touch = rec.get("touch") if isinstance(rec.get("touch"), dict) else None
        name = screen.get("name")
        steps_left = screen.get("steps_left")
        sources["steps_left"] = "record"
        if steps_left is None and name in SCREEN_FLOW:
            steps_left = len(SCREEN_FLOW) - 1 - SCREEN_FLOW.index(name)
            sources["steps_left"] = "derived from SCREEN_FLOW"
        if "progress_segment" in rec:
            progress = rec["progress_segment"]
            sources["progress"] = "record"
        elif prev_screen in SCREEN_FLOW and name in SCREEN_FLOW and SCREEN_FLOW.index(name) > SCREEN_FLOW.index(prev_screen):
            progress, sources["progress"] = True, "derived: screen forward"
        else:
            progress = None if touch is None else False
            sources["progress"] = "derived: no screen forward"
        recent, sources["recent"] = recent_counts(records, j, start_j, p.touch_span_s)
        kw = dict(
            t=float(rec["t"]), measurable=bool(rec.get("measurable")), situation=situation, screen=name,
            steps_left=steps_left, gaze=vision.get("facing_screen"),
            misses_recent=None if recent is None else recent.get("miss_tap_count"),
            fixes_recent=None if recent is None else recent.get("near_miss_fix_count"),
            backs_recent=None if recent is None else recent.get("back_count"),
            pause_s=screen.get("pause_s"), taps_segment=None if touch is None else touch.get("tap_count"),
            progress_segment=progress, options_open=screen.get("options_open"),
        )
        if wi:                                        # explicit fields win (aligned files may carry them)
            kw.update({k: v for k, v in wi.items() if k in kw})
            sources["window_input"] = sorted(k for k in wi if k in kw)
        inp = S.WindowInput(**kw)
        tf_src = rec.get("touch_features") if isinstance(rec.get("touch_features"), dict) else touch
        tf = None
        if tf_src is not None and all(_int(tf_src.get(k)) is not None for k in TOUCH_FIVE):
            tf = pr.TouchFeatures(**{k: tf_src[k] for k in TOUCH_FIVE})
        sources["touch_features"] = "present" if tf is not None else "absent (contract five not all known)"
        sources["touch_source"] = rec.get("touch_source")
        out.append(Window(take, j, inp.t, session_k, rec, inp, sit, tf, sources))
        prev_screen = name if name is not None else prev_screen
    return out


def rule_pass(pr: PR, windows: list[Window]) -> None:
    """tick -> decide -> apply per window with the session state carried (a session_reset starts it again)."""
    R, p = pr.R, pr.params
    state, k = pr.S.SessionState(), None
    for w in windows:
        if w.session_k != k:
            state, k = pr.S.SessionState(), w.session_k
        state, w.expired_id = R.tick(state, w.t, p)
        w.before = copy.deepcopy(state)
        w.allowed = R.allowed_supports(w.inp, w.before, p)
        decision = R.decide(w.inp, w.before, p)
        state, w.decision = R.apply(state, decision)


# ---------------------------------------------------------------------------------------------------- arms


@dataclass
class Arm:
    spec: str
    condition: str
    jev_stages: str
    variants: tuple
    wording_file: str | None = None

    @property
    def variant(self) -> str:
        return "+".join(self.variants) if self.variants else "base"


def parse_arm(spec: str) -> Arm:
    cond, _, rest = spec.partition(":")
    if cond not in CONDITIONS:
        raise SystemExit(f"unknown condition {cond!r} in arm {spec!r}; known {sorted(CONDITIONS)}")
    variants, wording = [], None
    for v in [x for x in rest.split("+") if x]:
        if v.startswith("wording="):
            wording = v.split("=", 1)[1]
            variants.append("wording")
        elif v in ("wording_formal", "wording_short"):
            wording = str(WORDING_DIR / f"{v.split('_', 1)[1]}_v1.json")
            variants.append(v)
        elif v in VARIANTS and v != "wording":
            variants.append(v)
        else:
            raise SystemExit(f"unknown variant {v!r} in arm {spec!r}; known {sorted(VARIANTS)}")
    if cond == "A" and variants:
        raise SystemExit("condition A asks nothing; it takes no variant")
    return Arm(spec, cond, CONDITIONS[cond], tuple(variants), wording)


class VariantStage:
    """A PR stage with this arm's state / question changes applied to what its build() returns (PR code untouched)."""

    def __init__(self, inner, arm: Arm, pr: PR, records: dict, wording: dict | None, donors: dict | None = None):
        self._inner, self._arm, self._pr, self._rec, self._wording = inner, arm, pr, records, wording
        self._donors = donors or {}      # t -> {"situation", "vision", "touch"} of the permuted donor window
        self.name = inner.name

    def build(self, ctx):
        built = self._inner.build(ctx)
        if built is None:
            return None
        state, questions = copy.deepcopy(built[0]), copy.deepcopy(built[1])
        S, R = self._pr.S, self._pr.R
        sit = ctx.inp.situation
        unknown = sit is None or sit.get("name") == S.UNKNOWN
        for v in self._arm.variants:
            if v == "novision":
                state["situation"], state["vision"] = None, None
                for h in state.get("history") or []:
                    if "tag" in h:
                        h["tag"] = None
            elif v == "notouch":
                state["touch"] = None
                for h in state.get("history") or []:
                    if "touch" in h:
                        h["touch"] = None
            elif v == "la_null":
                if unknown and isinstance(state.get("vision"), dict):
                    state["vision"]["looking_around"] = None
            elif v == "sit_dict":
                raw = (self._rec.get(ctx.inp.t) or {}).get("situation_raw")
                if sit is None and raw is not None:
                    state["situation"] = R.jev_state(replace(ctx.inp, situation=raw), ctx.state)["situation"]
            elif v == "vision_summary":
                summ = (self._rec.get(ctx.inp.t) or {}).get("vision") or {}
                if isinstance(state.get("vision"), dict):
                    state["vision"].update({k: val for k, val in summ.items() if k != "facing_screen"})
            elif v == "wording_nocrit":
                if self.name == "state_scores":
                    for q in self._pr.Q.STATE_QUESTIONS:
                        if q in questions:
                            questions[q] = {k: val for k, val in questions[q].items() if k != "criteria"}
            elif v in ("wording", "wording_formal", "wording_short"):
                for q, body in (self._wording or {}).get(self.name, {}).items():
                    if q in questions and isinstance(body, dict):
                        if "instructions" in body:
                            questions[q]["instructions"] = body["instructions"]
                        crit = questions[q].get("criteria")
                        for k, txt in (body.get("criteria") or {}).items():
                            if isinstance(crit, dict) and k in crit:
                                crit[k] = txt
            elif v == "nohistory":
                if self.name == "support_choice" and isinstance(state.get("session"), dict):
                    state["session"] = {k: val for k, val in state["session"].items() if k not in ("withdrawn", "held")}
            elif v in ("perm_vision", "perm_touch"):
                donor = self._donors.get(ctx.inp.t)
                if donor is not None:
                    keys = ("situation", "vision") if v == "perm_vision" else ("touch",)
                    for k in keys:
                        state[k] = copy.deepcopy(donor[k])
        return state, questions


class JevAloneStage:
    """Arm J: the PR's SupportChoiceStage built with every support of the rule table as candidates (no rule filter),
    so its instructions and the none text stay the PR's; the 3-2 wait gets WAIT_WHAT, which rule_table.WHAT lacks
    (the PR's own stage leaves the wait out of the options even when it is an allowed candidate)."""

    name = "support_choice"

    def __init__(self, pr: PR):
        self._pr = pr

    def build(self, ctx):
        Q = self._pr.Q
        original = Q.allowed_supports
        Q.allowed_supports = lambda *a, **k: list(ALL_SUPPORTS)   # in-memory only, restored at once (sync code)
        try:
            built = Q.SupportChoiceStage(self._pr.params).build(ctx)
        finally:
            Q.allowed_supports = original
        state, questions = built
        q = questions["support_choice"]
        none_text = q["criteria"][Q.NO_SUPPORT]
        q["criteria"] = {**{s: self._pr.R.WHAT.get(s, WAIT_WHAT) for s in ALL_SUPPORTS}, Q.NO_SUPPORT: none_text}
        return state, questions


# ---------------------------------------------------------------------------------------------------- clients


class FailureLog(logging.Handler):
    """Keeps the last warning of the PR's JevClient ('Jev answer unavailable (HTTP 429)'): the failure kind."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.last = None

    def emit(self, record):
        self.last = record.getMessage()


class StubJev:
    """Deterministic fake answers (module docstring). Never reported as Jev results."""

    def __init__(self, pr: PR, seed: int, fail_every: int):
        self._pr, self._seed, self._fail_every = pr, seed, fail_every
        self.model = f"stub-seed{seed}"
        self.failure = None
        self._n = 0                      # calls so far (the fail-every counter)

    async def ask(self, request):
        state = canon(request.state)
        self.failure = None
        self._n += 1
        if self._fail_every and self._n % self._fail_every == 0:
            self.failure = "stub_injected"
            return None
        answers = {}
        for name, q in request.questions.items():
            qtext = canon(q)
            if q.get("type") == "noul":
                answers[name] = {"type": "noul", "noul": unit(self._seed, name, qtext, state)}
            elif q.get("type") == "choice":
                options = list(q.get("criteria") or {})
                w = [unit(self._seed, name, o, qtext, state) + 1e-12 for o in options]
                probs = [x / sum(w) for x in w]
                k = max(range(len(options)), key=lambda i: (probs[i], -i))
                n = len(options)
                conf = 1.0 if n == 1 else min(1.0, max(0.0, (probs[k] - 1 / n) / (1 - 1 / n)))
                answers[name] = {"type": "choice", "choice": options[k], "confidence": conf,
                                 "probabilities": dict(zip(options, [min(1.0, x) for x in probs]))}
            else:
                raise ValueError(f"stub has no rule for question type {q.get('type')!r}")
        return self._pr.js.JevResponse.model_validate(
            {"model": "stub", "answers": answers, "usage": {"input_tokens": 0, "output_tokens": 0}})


class CacheOnly:
    """--jev cache: never calls anything. A request the answer cache does not hold gets no answer ('cache miss');
    CachingClient counts these apart from API calls (budget cache_misses). The model name (the cache key's first part)
    is --model, else the one model the cache file's answers carry."""

    offline = True

    def __init__(self, model: str | None):
        self.model = model
        self.failure = None
        self.latency_ms = 0.0

    async def ask(self, request):
        self.failure = "cache miss"
        return None


class BackoffClient:
    """Retries a call that failed with HTTP 429 or 529 after a pause that doubles (--backoff-base-s, then 2x, 4x,
    ...), at most --backoff-tries more times; while a pause runs no other call starts (one shared pause). TypeSafe
    advises exponential backoff on 429 (docs/Jev-Integration.md 3); the base and the number of tries are this
    harness's run settings. The PR's JevClient itself never retries (a failed window in operation stays 'no answer');
    the retries are counted (backoff_retries) and the latency is that of the final attempt."""

    def __init__(self, inner, failures: FailureLog, budget: dict, base_s: float, tries: int):
        self._inner, self._failures, self._budget, self._base, self._tries = inner, failures, budget, base_s, tries
        self._pause_until = 0.0
        self.failure = None
        self.latency_ms = None

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def offline(self) -> bool:
        return getattr(self._inner, "offline", False)

    async def ask(self, request):
        for attempt in range(self._tries + 1):
            wait = self._pause_until - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._failures.last = None
            started = time.perf_counter()
            response = await self._inner.ask(request)
            self.latency_ms = (time.perf_counter() - started) * 1000.0
            if response is not None:
                self.failure = None
                return response
            self.failure = getattr(self._inner, "failure", None) or self._failures.last or "no_answer"
            if attempt < self._tries and ("HTTP 429" in self.failure or "HTTP 529" in self.failure):
                self._pause_until = max(self._pause_until, time.monotonic() + self._base * 2 ** attempt)
                self._budget["backoff_retries"] += 1
                continue
            return None
        return None


class CachingClient:
    """Identical requests (same model, state and questions) get the first answer again without a new API call, so a
    run costs one call per distinct request; failures are not cached (the next identical request calls again).
    --cache-file keeps the answers (and the repeats) in an append-only JSONL file, so later runs, other bundles
    and an interrupted run reuse them. --no-cache turns both off. Repeats always bypass the answer cache.
    read_only (--jev cache): the file (.jsonl or .jsonl.gz) is only read; a key with two answers in the file gives
    the later one. pins: (arm, take, window index, key) -> the answer a recorded run used there (answer_pins.json)."""

    def __init__(self, inner, failures: FailureLog, budget: dict, enabled: bool, cache_file: Path | None = None,
                 js=None, read_only: bool = False, pins: dict | None = None):
        self._inner, self._failures, self._budget, self._enabled = inner, failures, budget, enabled
        self._seen: dict = {}
        self.repeats: dict = {}
        self.last = None                 # {"cached", "latency_ms", "failure"} of the last ask
        self._file = None
        self.loaded = 0
        self.models: Counter = Counter()  # model names of the loaded answers
        self.pins = pins or {}
        if enabled and cache_file is not None:
            if cache_file.is_file():
                with open_text(cache_file) as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        e = json.loads(line)
                        if "response" in e:
                            self._seen[e["key"]] = (js.JevResponse.model_validate(e["response"]), e["latency_ms"])
                            self.models[e.get("model")] += 1
                        if "repeats" in e:
                            self.repeats[e["key"]] = e["repeats"]
            elif read_only:
                raise SystemExit(f"cache file not found: {cache_file}")
            self.loaded = len(self._seen)
            if not read_only:
                if cache_file.suffix == ".gz":
                    raise SystemExit(f"{cache_file}: a gzipped cache is read-only (--jev cache); give a .jsonl file")
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                self._file = open(cache_file, "a", encoding="utf-8")

    @property
    def model(self) -> str:
        return self._inner.model

    def key_of(self, request, ordered: bool = False) -> str:
        """The cache identity. digest() sorts dict keys, so it cannot tell two option orders apart; the
        reversed-order request (ordered=True) is keyed on its JSON in sent order instead ('o:' prefix; Codex 205 #1)."""
        if ordered:
            body = json.dumps({"model": self.model, "state": request.state, "questions": request.questions},
                              ensure_ascii=False, separators=(",", ":"))
            return "o:" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        return digest({"model": self.model, "state": request.state, "questions": request.questions})

    def save_repeats(self, key: str, again: list) -> None:
        self.repeats[key] = again
        if self._file is not None:
            self._file.write(json.dumps({"key": key, "repeats": again}, ensure_ascii=False) + "\n")
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()

    async def ask(self, request, ordered: bool = False):
        key = self.key_of(request, ordered)
        where = CURRENT.get()
        pin = self.pins.get((*where, key)) if (self.pins and where is not None) else None
        if pin is not None:                               # cache mode: the answer the recorded run used here
            response, latency_ms = pin
            self.last = {"cached": True, "latency_ms": latency_ms, "failure": None}
            self._budget["cached"] += 1
            self._budget["pinned"] += 1
            return response
        if self._enabled and key in self._seen:
            response, latency_ms = self._seen[key]
            self.last = {"cached": True, "latency_ms": latency_ms, "failure": None}
            self._budget["cached"] += 1
            return response
        self._failures.last = None
        started = time.perf_counter()
        response = await self._inner.ask(request)
        latency_ms = getattr(self._inner, "latency_ms", None) or (time.perf_counter() - started) * 1000.0
        offline = getattr(self._inner, "offline", False)
        self._budget["cache_misses" if offline else "calls"] += 1
        failure = None
        if response is None:
            failure = getattr(self._inner, "failure", None) or self._failures.last or "no_answer"
            if not offline:
                self._budget["failed"] += 1
        elif self._enabled:
            self._seen[key] = (response, latency_ms)
            if self._file is not None:
                self._file.write(json.dumps({"key": key, "model": self.model, "latency_ms": latency_ms,
                                             "response": response.model_dump(mode="json")}, ensure_ascii=False) + "\n")
                self._file.flush()
        self.last = {"cached": False, "latency_ms": latency_ms, "failure": failure}
        return response


class Recorder:
    """The client the PR service calls: forwards to the caching client and keeps every request (compact body
    bytes, latency of the API call that produced the answer, cached flag, full answer with probabilities,
    failure kind)."""

    def __init__(self, inner: CachingClient):
        self._inner = inner
        self.calls: list[dict] = []

    @property
    def model(self) -> str:
        return self._inner.model

    async def ask(self, request):
        body = request.model_dump(mode="json")
        body["model"] = self.model
        response = await self._inner.ask(request)
        last = self._inner.last
        self.calls.append({"request": body, "bytes": len(canon(body).encode("utf-8")), "latency_ms": last["latency_ms"],
                           "cached": last["cached"],
                           "response": None if response is None else response.model_dump(mode="json"),
                           "failure": last["failure"]})
        return response


def load_settings(pr: PR, env_files: list[Path]):
    """The PR's Settings (JEV_* from the environment, else the first env file that sets JEV_API_KEY); the key is
    never printed. Returns (settings, key source)."""
    if os.environ.get("JEV_API_KEY"):
        return pr.settings.Settings(_env_file=None), "environment JEV_API_KEY"
    for f in env_files:
        if f.is_file():
            s = pr.settings.Settings(_env_file=f)
            if s.jev_api_key is not None and s.jev_api_key.get_secret_value():
                return s, f"file {f}"
    return pr.settings.Settings(_env_file=None), "key absent"


# ---------------------------------------------------------------------------------------------------- run


def answer_view(resp_answer: dict) -> dict:
    if resp_answer.get("type") == "noul":
        return {"type": "noul", "p": resp_answer["noul"]}
    out = {"type": resp_answer.get("type"), "choice": resp_answer.get("choice"),
           "confidence": resp_answer.get("confidence"), "probabilities": resp_answer.get("probabilities")}
    if resp_answer.get("type") == "score":
        out["score"] = resp_answer.get("score")
    return out


def donors_for(pr: PR, arm: Arm, windows: list, rng) -> dict:
    """t -> the state parts of another measurable window of the same session (seeded permutation) for the
    permuted-values controls; built with the PR's own jev_state / shadow_state."""
    if not any(v in ("perm_vision", "perm_touch") for v in arm.variants):
        return {}
    out = {}
    sessions: dict = {}
    for w in windows:
        if w.inp.measurable:
            sessions.setdefault(w.session_k, []).append(w)
    for ws in sessions.values():
        order = list(range(len(ws)))
        rng.shuffle(order)
        for w, k in zip(ws, order):
            d = ws[k]
            st = pr.Q.shadow_state(d.inp, d.before, d.touch)
            out[w.t] = {"situation": st["situation"], "vision": st["vision"], "touch": st["touch"], "donor_i": d.i}
    return out


def swapped(body: dict) -> dict:
    """The support_choice request with its options in reverse order (criteria and state.candidates)."""
    b = copy.deepcopy(body)
    q = b["questions"]["support_choice"]
    q["criteria"] = dict(reversed(list(q["criteria"].items())))
    if isinstance(b.get("state"), dict) and isinstance(b["state"].get("candidates"), list):
        b["state"]["candidates"] = list(reversed(b["state"]["candidates"]))
    return b


async def run_arm(pr: PR, arm: Arm, takes: dict[str, list[Window]], cache: CachingClient, raw_inner,
                  failures: FailureLog, args, states: dict, questions_cat: dict, out_fh, budget: dict, repeat_fh,
                  repeat_seen: set, repeat_windows: set | None = None) -> dict:
    stages_base = (JevAloneStage(pr),) if arm.condition == "J" else pr.Q.build_stages(arm.jev_stages)
    wording = None
    if arm.wording_file:
        with open(arm.wording_file, encoding="utf-8") as fh:
            wording = json.load(fh)
    counts = {"windows": 0, "asked": 0, "requests": 0, "answered": 0, "no_answer": 0, "skipped_stage": 0}
    import random as _random
    gate = asyncio.Semaphore(max(1, args.concurrency))

    async def guarded(take, windows):
        async with gate:
            await run_take(take, windows)

    async def run_take(take, windows):
        recs = {w.t: {"situation_raw": w.situation_raw, "vision": w.record.get("vision")
                      if isinstance(w.record.get("vision"), dict) else None} for w in windows}
        # one seeded permutation per take, so the donors do not depend on the order takes run in
        donors = donors_for(pr, arm, windows, _random.Random(f"{args.perm_seed}|{arm.spec}|{take}"))
        stages = tuple(VariantStage(s, arm, pr, recs, wording, donors) for s in stages_base) if arm.variants \
            else stages_base
        recorder = Recorder(cache)
        repo = pr.repo.DecisionRepository()
        service = pr.svc.DecisionService(repo, pr.params, jev=recorder, stages=stages)
        busy_until: dict[str, float] = {}
        t0 = take_start(take)
        for w in windows:
            sid = f"{take}#{w.session_k}"
            history = repo.history(sid)                      # observe(): the windows before this one
            d = w.decision
            counts["windows"] += 1
            line = {"arm": arm.spec, "condition": arm.condition, "variant": arm.variant, "jev_stages": arm.jev_stages,
                    "take": take, "i": w.i, "t": w.t, "session": sid, "asked": False, "skip_reason": None,
                    "would_skip_in_flight": bool(w.t < busy_until.get(sid, float("-inf"))), "stages": []}
            if not service.shadow:
                line["skip_reason"], why = "condition A (no stages)", "off"
            elif not w.inp.measurable:
                line["skip_reason"], why = "not measurable", "not_measurable"
            elif args.in_flight == "simulate" and line["would_skip_in_flight"]:
                line["skip_reason"], why = "in flight", "skipped_in_flight"
            elif args.max_calls is not None and budget["calls"] >= args.max_calls:
                line["skip_reason"], why = "max_calls", "skipped_max_calls"
            elif (args.max_failure_rate is not None and budget["calls"] >= FAILURE_GUARD_MIN_CALLS
                  and budget["failed"] > args.max_failure_rate * budget["calls"]):
                line["skip_reason"], why = "failure_rate", "skipped_failure_rate"
            else:
                why = "asked"
            add_window(pr, repo, service, sid, w, t0 + timedelta(seconds=w.t), why)   # observe(): after the judgment
            if why == "asked":
                recorder.calls.clear()
                window_ns = SimpleNamespace(touch=w.touch, window_end=t0 + timedelta(seconds=w.t))
                CURRENT.set((arm.spec, take, w.i))           # read by CachingClient for answer pins
                records = await service.ask_shadow(sid, window_ns, w.inp, d, w.before, history)
                line["asked"] = True
                counts["asked"] += 1
                done = {r.stage for r in records}
                total_ms = 0.0
                for rec, call in zip(records, recorder.calls):
                    st_hash, q_hash = digest(call["request"]["state"]), digest(call["request"]["questions"])
                    states.setdefault(st_hash, call["request"]["state"])
                    questions_cat.setdefault(q_hash, call["request"]["questions"])
                    resp = call["response"]
                    entry = {"stage": rec.stage, "outcome": rec.outcome, "failure": call["failure"],
                             "latency_ms": round(call["latency_ms"], 3), "cached": call["cached"],
                             "latency_ms_service": rec.latency_ms,
                             "request_bytes": call["bytes"], "state_hash": st_hash, "questions_hash": q_hash,
                             "questions": list(rec.questions), "request_model": rec.request_model,
                             "response_model": rec.response_model, "usage": rec.usage,
                             "answers": {k: answer_view(v) for k, v in (resp or {}).get("answers", {}).items()}}
                    if donors.get(w.t):
                        entry["perm_donor_i"] = donors[w.t]["donor_i"]
                    if rec.stage == "support_choice" and args.order_swap:     # option-order swap, same window
                        body2 = swapped(call["request"])
                        resp2 = await cache.ask(pr.js.JevRequest.model_validate(body2), ordered=True)
                        states.setdefault(digest(body2["state"]), body2["state"])
                        questions_cat.setdefault(digest(body2["questions"]), body2["questions"])
                        entry["order_swap"] = {
                            "outcome": "answered" if resp2 is not None else "no_answer", "failure": cache.last["failure"],
                            "cached": cache.last["cached"], "latency_ms": round(cache.last["latency_ms"], 3),
                            "answers": {} if resp2 is None else {
                                k: answer_view(v) for k, v in resp2.model_dump(mode="json")["answers"].items()}}
                    total_ms += call["latency_ms"]
                    counts["requests"] += 1
                    counts["answered" if rec.outcome == "answered" else "no_answer"] += 1
                    line["stages"].append(entry)
                for s in stages:
                    if s.name not in done:
                        line["stages"].append({"stage": s.name, "outcome": "skipped", "reason": "build returned None"})
                        counts["skipped_stage"] += 1
                order = {s.name: k for k, s in enumerate(stages)}
                line["stages"].sort(key=lambda e: order.get(e["stage"], 99))
                busy_until[sid] = w.t + total_ms / 1000.0
                # repeated fixed inputs: every distinct request of the run once more, repeats - 1 times; the
                # extra answers go to repeats.jsonl only (they feed no chain and no history)
                for rec, call in zip(records, recorder.calls):
                    req = pr.js.JevRequest.model_validate(call["request"])
                    key = cache.key_of(req)
                    if args.repeats < 2 or key in repeat_seen:
                        continue
                    if args.repeat_stages and rec.stage not in args.repeat_stages:
                        continue
                    if repeat_windows is not None and (take, w.i) not in repeat_windows:
                        continue
                    repeat_seen.add(key)
                    have = list(cache.repeats.get(key) or [])
                    reused = len(have) >= args.repeats - 1
                    again = have[:args.repeats - 1]          # earlier repeats of this request are kept and extended
                    for _ in range(args.repeats - 1 - len(again)):
                        resp = await raw_inner.ask(req)
                        if getattr(raw_inner, "offline", False):
                            budget["cache_misses"] += 1     # cache mode: a repeat the cache lacks; nothing was sent
                        else:
                            budget["calls"] += 1
                            budget["repeat_calls"] += 1
                        again.append({"latency_ms": round(raw_inner.latency_ms or 0.0, 3),
                                      "outcome": "answered" if resp is not None else "no_answer",
                                      "failure": None if resp is not None else raw_inner.failure,
                                      "answers": {} if resp is None else {
                                          k: answer_view(v) for k, v in resp.model_dump(mode="json")["answers"].items()}})
                    if len(again) > len(have):
                        cache.save_repeats(key, again)
                    repeat_fh.write(json.dumps({
                        "arm": arm.spec, "stage": rec.stage, "take": take, "i": w.i,
                        "state_hash": digest(call["request"]["state"]),
                        "questions_hash": digest(call["request"]["questions"]), "request_key": key,
                        "reused_from_cache_file": reused, "first": {"outcome": rec.outcome, "answers": {
                            k: answer_view(v) for k, v in (call["response"] or {}).get("answers", {}).items()}},
                        "again": again}, ensure_ascii=False) + "\n")
            out_fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    await asyncio.gather(*(guarded(take, windows) for take, windows in takes.items()))
    return counts


PR_FILES = ("app/modules/decision/schemas.py", "app/modules/decision/rule_table.py", "app/modules/decision/jev_questions.py",
            "app/modules/decision/service.py", "app/modules/decision/repository.py",
            "app/infrastructure/external/jev_client.py", "app/infrastructure/external/jev_schemas.py",
            "app/common/config/settings.py")


def frozen_settings(pr: PR, arms: list, questions_cat: dict, run_model: str, args) -> dict:
    """Everything a result depends on, frozen in one file: parameters, model, question texts, output mappings,
    fallback handling, label matching, metric settings, the PR's commit and file hashes."""
    sys.path.insert(0, str(HERE))
    import metrics as M
    S, R, Q = pr.S, pr.R, pr.Q
    fields = pr.settings.Settings.model_fields
    return {
        "frozen": datetime.now(KST).isoformat(timespec="seconds"),
        "pr": {"backend": str(pr.backend), "commit": pr.commit,
               "sha256": {f: hashlib.sha256((pr.backend / f).read_bytes()).hexdigest() for f in PR_FILES}},
        "params": {"values": asdict(pr.params), "source": "PILOT_PARAMS, backend/app/modules/decision/schemas.py "
                                                          "([파일럿], the same values as ai-engine vision params.py)"},
        "model": {"setting_default": fields["jev_model"].default, "this_run": run_model,
                  "api_url_default": fields["jev_api_url"].default,
                  "timeout_s_default": fields["jev_timeout_seconds"].default,
                  "note": "a real run uses JEV_MODEL from the environment / backend/.env, else the default; the "
                          "response's own model field is recorded per call"},
        "conditions": CONDITIONS, "variants": VARIANTS, "arms": [a.spec for a in arms],
        "semantics": {
            "stages": "stages of one window run in order in that window's task; stage 2 sees stage 1's answers of the "
                      "same window (service.py ask_shadow); the docs 9.5 N+1 variant is not evaluated",
            "eligible": "a window is asked when it is measurable (service.py observe); a stage is skipped when its "
                        "build() returns None (support_choice: no allowed candidate; next_difficulty: no history)",
            "in_flight": "offline every eligible window is awaited (--in-flight record); would-skip windows are flagged",
            "tick": "tick() before decide() per window, as the vision replay does; react() is never called "
                    "(no front-end reactions offline)",
            "history": "DecisionRepository.add_window / attach as in observe() (WindowRecord at 3c936ae, summary dict at "
                       "0114ed1; run_jev_ablation.add_window); HISTORY_WINDOWS = %s" % pr.history_windows,
        },
        "questions": {
            "state_scores": Q.STATE_QUESTIONS, "rule_what": R.WHAT, "rule_fit_criteria": R.FIT_CRITERIA,
            "rule_choice_criteria": R.CHOICE_CRITERIA, "next_difficulty_options": Q.DIFFICULTIES,
            "no_support_name": Q.NO_SUPPORT,
            "jev_alone_options": list(ALL_SUPPORTS), "jev_alone_wait_text": WAIT_WHAT,
            "wording_variants": {f.stem: json.loads(f.read_text(encoding="utf-8"))
                                 for f in sorted(WORDING_DIR.glob("*.json"))},
            "sent_in_run": questions_cat,
        },
        "output_mappings": {
            "support_to_action": M.ACTION_OF, "label_vocabulary": M.KOREAN_ACTIONS,
            "a_selection": "the support A opens or replaces in the window (rule transition open / replace), else none",
            "c_selection": "the support_choice answer; none = nothing new (the support held before the window stays)",
            "shown": "the support held after the window's decision (open / replace / keep), else none",
            "nothing_shown": "wait (기다림), 평가 설계 v1.4 §2-2",
            "segment_counts": " ".join(M.segment_outcomes.__doc__.split()),
            "c_as_run": "per window: the support_choice answer; none when the stage was skipped (no candidate); the "
                        "rule table's selection when the call failed or the window was not asked",
            "shadow_trajectory": "C is scored on the rule table's session-state trajectory: its selections do not feed "
                                 "back into the state (shadow); a C-applied trajectory is not simulated",
            "state_proxy": {"by_scene": {k: sorted(v) for k, v in M.STATE_PROXY.items()},
                            "normal_plans": sorted(M.NORMAL_PLANS), "source": M.STATE_PROXY_SOURCE},
        },
        "fallbacks": {
            "client": "JevClient: no retries; HTTP 4xx / 5xx / 429 / 529, timeout or a malformed answer -> no answer",
            "chain": "a stage without an answer leaves nothing for the next stage, which still runs (ask_shadow)",
            "decision": "shadow mode: Jev never changes the rule table's decision; the C figure 'with rule fallback' "
                        "uses A's selection where support_choice gave no answer or did not run",
        },
        "labels": {"default": str(DEFAULT_LABELS), "match": M.Labels.match.__doc__.strip()},
        "metrics": {"bins": "10 equal-width ([관행값] Niculescu-Mizil & Caruana 2005 ten-bin reliability diagrams)",
                    "percentile": "linear interpolation, Hyndman & Fan 1996 type 7 (NumPy default)",
                    "null_permutations": M.DEFAULT_PERMS, "null_seed": 0,
                    "next_difficulty_horizon_s": M.NEXT_HORIZON_S, "repeats": args.repeats,
                    "bootstrap": {"resamples": M.BOOT_RESAMPLES, "seed": M.BOOT_SEED, "unit": "clip"},
                    "formulas": M.FORMULAS},
        "input_adapter": {"aligned": " ".join(load_aligned.__doc__.split()),
                          "cache_identical": " ".join(CachingClient.__doc__.split()),
                          "backoff": " ".join(BackoffClient.__doc__.split())
                                     + f" Defaults: base {args.backoff_base_s} s, {args.backoff_tries} retries.",
                          "concurrency": "--concurrency N runs up to N takes of an arm at once (arms stay in order); "
                                         "1 = sequential; outputs equal the sequential run as sets of lines",
                          "order_swap": " ".join(swapped.__doc__.split()),
                          "perm_controls": " ".join(donors_for.__doc__.split())},
        "stub_rule": __doc__.split("Stub answers")[1].strip(),
    }


def rule_line(pr: PR, w: Window, labels) -> dict:
    d = w.decision
    rec = w.record.get("decision") or {}
    vd = {"transition": rec.get("transition"), "support": rec.get("support")} if rec else None
    held = w.decision.support if d.transition in ("open", "replace", "keep") else None
    line = {
        "take": w.take, "clip": w.record.get("clip") or w.take, "i": w.i, "t": w.t,
        "segment_s": w.record.get("segment_s") or [w.t - 1.0, w.t], "segment_id": w.record.get("segment_id"),
        "condition": w.record.get("condition"), "variant": w.record.get("variant"), "bundle": w.record.get("bundle"),
        "touch_source": w.record.get("touch_source"), "tag_source": w.record.get("tag_source"),
        "situation_replay": w.record.get("situation_replay"),
        "session_k": w.session_k, "measurable": w.inp.measurable,
        "situation_record": (w.situation_raw or {}).get("name"), "situation_used": (w.inp.situation or {}).get("name"),
        "input": {k: v for k, v in asdict(w.inp).items() if k not in ("situation",)},
        "situation_input": w.inp.situation,
        "sources": w.sources,
        "touch_features": None if w.touch is None else w.touch.model_dump(),
        "expired_by_tick": w.expired_id,
        "held_before": w.before.held.support if w.before.held else None,
        "withdrawn_before": [x["support"] for x in w.before.withdrawn],
        "allowed_candidates": list(w.allowed),
        "rule": {"transition": d.transition, "support": d.support, "scene": d.scene, "action": d.action,
                 "rank": d.rank, "decision_id": d.decision_id, "reason": d.reason,
                 "jev_kind": (d.policy or {}).get("kind"), "ask_jev": (d.policy or {}).get("ask_jev"),
                 "rule_question": None if d.jev_request is None else sorted(d.jev_request["questions"]),
                 "shown": held, "shown_action": pr.action_of.get(held) if held else None},
        "vision_record_decision": vd,
        "vision_record_match": None if vd is None else (vd["transition"] == d.transition and vd["support"] == d.support),
        "expect": w.record.get("expect"),
    }
    if labels is not None:
        line["label"] = labels.match_record({"take": w.take, "clip": w.record.get("clip") or w.take, "t": w.t,
                                             "segment_id": w.record.get("segment_id"),
                                             "condition": w.record.get("condition"),
                                             "variant": w.record.get("variant")})
    return line


async def main_async(args) -> int:
    if not args.backend:
        raise SystemExit("pass --backend <checkout>/backend (PR #77: branch feat/jev at 3c936ae, or main after the "
                         "merge) or set the environment variable E5_BACKEND")
    pr = PR(Path(args.backend))
    arms = [parse_arm(s) for s in (args.arms or DEFAULT_ARMS)]
    only = set(args.takes) if args.takes else None
    sys.path.insert(0, str(HERE))
    import metrics
    labels = None
    if args.aligned:
        takes_raw = load_aligned([Path(d) for d in args.aligned], args.bundle, set(args.conditions or []) or None,
                                 args.variant, only, Path(args.windows_dir), args.tag_source)
        label_path = Path(args.labels) if args.labels else DEFAULT_ADMISSIBLE
        if not args.no_labels:
            labels = metrics.AdmissibleLabels.load(label_path)
    else:
        if not args.input:
            raise SystemExit("give --input (window records) or --aligned (E3 aligned windows)")
        takes_raw = load_takes([Path(p) for p in args.input], only, args.windows_name)
        label_path = Path(args.labels) if args.labels else (DEFAULT_LABELS if DEFAULT_LABELS.is_file() else None)
        if label_path is not None and not args.no_labels:
            labels = metrics.Labels.load(label_path)
    if not takes_raw:
        raise SystemExit("no takes")
    if label_path is not None and labels is not None:
        INPUT_FILES.add(str(label_path))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    takes: dict[str, list[Window]] = {}
    for take, records in takes_raw.items():
        windows = build_windows(pr, take, records)
        rule_pass(pr, windows)
        takes[take] = windows

    failures = FailureLog()
    logging.getLogger(pr.client.__name__).addHandler(failures)
    logging.getLogger(pr.client.__name__).propagate = False
    http, key_source, settings = None, None, None
    if args.jev == "stub":
        inner = StubJev(pr, args.stub_seed, args.stub_fail_every)
        if args.stub_model:     # count against a real cache: the stub carries the real model name in the cache key
            inner.model = args.stub_model
        model, base_url, timeout = inner.model, None, None
    elif args.jev == "cache":
        if not args.cache_file or args.no_cache:
            raise SystemExit("--jev cache needs --cache-file (e.g. results/jev_cache.jsonl.gz) and no --no-cache")
        inner = CacheOnly(args.model)
        model, base_url, timeout, key_source = None, None, None, "none (cache mode: no key read, nothing sent)"
    else:
        env_files = [Path(args.backend) / ".env"] + [Path(f) for f in (args.env_file or [])]
        settings, key_source = load_settings(pr, env_files)
        if settings.jev_api_key is None:
            print("key absent: JEV_API_KEY is not set in the environment or in", ", ".join(map(str, env_files)),
                  "- real run skipped")
            (out / "run_settings.json").write_text(json.dumps(
                {"created": datetime.now(KST).isoformat(timespec="seconds"), "jev": "real", "key": "key absent",
                 "skipped": True, "env_files_checked": [str(f) for f in env_files]}, ensure_ascii=False, indent=1),
                encoding="utf-8")
            return 2
        model = args.model or settings.jev_model
        base_url, timeout = settings.jev_api_url, args.timeout or settings.jev_timeout_seconds
        http = pr.client.create_jev_http(settings.jev_api_key.get_secret_value(), base_url, timeout)
        inner = pr.client.JevClient(http, model, timeout)
        print(f"real Jev: model {model}, {base_url}, timeout {timeout} s, key from {key_source}")

    repeat_windows = None
    if args.repeat_fraction < 1.0:   # seeded subset of the windows whose requests are repeated
        import random as _random
        keys = sorted((t, w.i) for t, ws in takes.items() for w in ws)
        repeat_windows = set(_random.Random(args.repeat_seed).sample(keys, round(args.repeat_fraction * len(keys))))
        print(f"repeat subset: {len(repeat_windows)} of {len(keys)} windows (seed {args.repeat_seed})")
    states: dict = {}
    questions_cat: dict = {}
    budget = {"calls": 0, "cached": 0, "failed": 0, "repeat_calls": 0, "backoff_retries": 0, "cache_misses": 0,
              "pinned": 0}
    pins, pin_info = {}, None
    if args.answer_pins:
        if args.jev != "cache" or not args.pin_run:
            raise SystemExit("--answer-pins applies to --jev cache and needs --pin-run <recorded run name>")
        allp = json.loads(Path(args.answer_pins).read_text(encoding="utf-8"))
        for p in (allp.get("runs") or {}).get(args.pin_run, []):
            pins[(p["arm"], p["take"], p["i"], p["key"])] = (pr.js.JevResponse.model_validate(p["response"]),
                                                             p["latency_ms"])
        pin_info = {"file": str(args.answer_pins), "run": args.pin_run, "pins": len(pins)}
    base_client = inner
    inner = BackoffClient(inner, failures, budget, args.backoff_base_s, args.backoff_tries)
    cache = CachingClient(inner, failures, budget, enabled=not args.no_cache,
                          cache_file=Path(args.cache_file) if args.cache_file else None, js=pr.js,
                          read_only=args.jev == "cache", pins=pins)
    if args.jev == "cache":
        if base_client.model is None:
            names = sorted(m for m in cache.models if m)
            if len(names) != 1:
                raise SystemExit(f"the cache holds answers of models {names}; pass --model")
            base_client.model = names[0]
        model = base_client.model
        print(f"cache mode: model {model}, answers only from {args.cache_file} (read-only), nothing is sent")
    if cache.loaded:
        print(f"cache file: {cache.loaded} answers and {len(cache.repeats)} repeat sets loaded"
              + (f"; {len(pins)} answer pins for {args.pin_run}" if pin_info else ""))
    arm_counts = {}
    started = time.perf_counter()
    try:
        repeat_seen: set = set()
        with open(out / "jev_calls.jsonl", "w", encoding="utf-8") as fh, \
                open(out / "repeats.jsonl", "w", encoding="utf-8") as repeat_fh:
            for arm in arms:
                if arm.condition == "A":
                    arm_counts[arm.spec] = {"windows": sum(len(w) for w in takes.values()), "asked": 0, "requests": 0}
                    continue
                arm_counts[arm.spec] = await run_arm(pr, arm, takes, cache, inner, failures, args, states,
                                                     questions_cat, fh, budget, repeat_fh, repeat_seen, repeat_windows)
                print(f"arm {arm.spec:>18}: {arm_counts[arm.spec]}")
    finally:
        cache.close()
        if http is not None:
            await http.aclose()
    wall = time.perf_counter() - started

    with open(out / "rule_windows.jsonl", "w", encoding="utf-8") as fh:
        for windows in takes.values():
            for w in windows:
                # sets (a time-mode label row's e3_row) as sorted lists: the recorded runs ran with --no-labels and
                # never wrote one; with --labels this line failed before (package fix)
                fh.write(json.dumps(rule_line(pr, w, labels), ensure_ascii=False,
                                    default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else str(o)) + "\n")
    with open(out / "states.jsonl", "w", encoding="utf-8") as fh:
        for h, s in states.items():
            fh.write(json.dumps({"state_hash": h, "state": s}, ensure_ascii=False) + "\n")
    (out / "questions.json").write_text(json.dumps(questions_cat, ensure_ascii=False, indent=1), encoding="utf-8")

    import httpx
    import pydantic
    settings_out = {
        "created": datetime.now(KST).isoformat(timespec="seconds"),
        "command": [Path(sys.executable).name, *sys.argv],
        "jev": args.jev, "model": model, "base_url": base_url, "timeout_s": timeout, "key": key_source,
        "stub_rule": __doc__.split("Stub answers")[1].split('"""')[0].strip() if args.jev == "stub" else None,
        "stub_seed": args.stub_seed if args.jev == "stub" else None,
        "stub_fail_every": args.stub_fail_every if args.jev == "stub" else None,
        "pr_backend": str(pr.backend), "pr_commit": pr.commit,
        "params": asdict(pr.params), "params_note": "PILOT_PARAMS of backend/app/modules/decision/schemas.py ([파일럿])",
        "arms": [{"arm": a.spec, "condition": a.condition, "JEV_STAGES": a.jev_stages, "variant": a.variant,
                  "variant_meaning": [VARIANTS[v] for v in a.variants], "wording_file": a.wording_file} for a in arms],
        "inputs": ([str(d) for d in args.aligned] if args.aligned else [str(p) for p in args.input]),
        "aligned": None if not args.aligned else {"bundle": args.bundle, "variant": args.variant,
                                                  "conditions": sorted({w.record.get("condition") for ws in takes.values()
                                                                        for w in ws}),
                                                  "windows_rows": str(Path(args.windows_dir) / f"windows_{args.bundle}.csv")},
        "cache_identical": not args.no_cache, "order_swap": args.order_swap, "perm_seed": args.perm_seed,
        "order_swap_cache": "ordered-key" if args.order_swap else None, "tag_source": args.tag_source,
        "input_sha256": {f: sha_file(f) for f in sorted(INPUT_FILES)},
        "input_sha256_uncompressed": {f: sha_content(f) for f in sorted(INPUT_FILES) if f.endswith(".gz")},
        "takes": {t: len(w) for t, w in takes.items()},
        "labels": None if labels is None else str(label_path),
        "in_flight": args.in_flight, "repeats": args.repeats, "max_calls": args.max_calls,
        "calls_total": budget["calls"], "calls_failed": budget["failed"], "answers_from_cache": budget["cached"],
        "repeat_calls": budget["repeat_calls"], "backoff_retries": budget["backoff_retries"],
        "cache_misses": budget["cache_misses"], "answers_pinned": budget["pinned"], "answer_pins": pin_info,
        "cache_file": args.cache_file, "cache_read_only": args.jev == "cache", "cache_loaded": cache.loaded,
        "concurrency": args.concurrency,
        "repeat_fraction": args.repeat_fraction, "repeat_seed": args.repeat_seed, "repeat_stages": args.repeat_stages,
        "max_failure_rate": args.max_failure_rate,
        "repeat_windows": None if repeat_windows is None else len(repeat_windows),
        "backoff": {"base_s": args.backoff_base_s, "tries": args.backoff_tries},
        "wall_s": round(wall, 3), "arm_counts": arm_counts,
        "questions_catalog": sorted(questions_cat), "distinct_states": len(states),
        "python": platform.python_version(), "httpx": httpx.__version__, "pydantic": pydantic.__version__,
    }
    (out / "run_settings.json").write_text(json.dumps(settings_out, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.write_settings:
        Path(args.write_settings).write_text(json.dumps(frozen_settings(pr, arms, questions_cat, model, args),
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"frozen settings -> {args.write_settings}")
    calls = "stub calls (fake answers, nothing sent)" if args.jev == "stub" else "API calls"
    print(f"done: {sum(len(w) for w in takes.values())} windows in {len(takes)} takes, {budget['calls']} {calls} "
          f"({budget['cached']} answers from cache, {budget['cache_misses']} cache misses), "
          f"{wall:.1f} s -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--input", action="append", help="window records: a replay folder (<take>/windows.jsonl[.gz]), a "
                                                    "folder of <take>.jsonl[.gz] or one file (repeatable)")
    ap.add_argument("--takes", nargs="*", help="only these takes")
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", default=DEFAULT_BACKEND, help="a checkout's backend/ folder with PR #77 (default: the "
                                                               "environment variable E5_BACKEND)")
    ap.add_argument("--jev", choices=("stub", "cache", "real"), default="stub",
                    help="stub = fake answers; cache = recorded answers only (--cache-file, nothing sent); real = API")
    ap.add_argument("--answer-pins", help="cache mode: results/answer_pins.json (the recorded run's answer where the "
                                          "cache holds two answers for one request)")
    ap.add_argument("--pin-run", help="cache mode: the recorded run whose pins apply (e.g. stage2_1_swap_C_C0)")
    ap.add_argument("--arms", nargs="*", help=f"condition[:variant[+variant]] (default {' '.join(DEFAULT_ARMS)})")
    ap.add_argument("--labels", help="judgment label CSV (default inputs/labels/judgment_labels_v4.csv; aligned input: "
                                     "inputs/labels/admissible_v4.csv)")
    ap.add_argument("--no-labels", action="store_true")
    ap.add_argument("--in-flight", choices=("record", "simulate"), default="record",
                    help="record = ask every measurable window and flag the ones the service would skip; "
                         "simulate = skip them like DecisionService.observe")
    ap.add_argument("--repeats", type=int, default=3,
                    help="calls per distinct request (the first one feeds the chain; the others go to repeats.jsonl)")
    ap.add_argument("--max-calls", type=int, help="stop asking after this many calls")
    ap.add_argument("--max-failure-rate", type=float, help="stop asking once failed calls exceed this share of the calls "
                    f"made (checked from {FAILURE_GUARD_MIN_CALLS} calls on; main 2026-11-05: 0.01)")
    ap.add_argument("--repeat-stages", nargs="*", help="repeat only the requests of these stages (e.g. support_choice)")
    ap.add_argument("--stub-seed", type=int, default=0)
    ap.add_argument("--stub-fail-every", type=int, default=0)
    ap.add_argument("--stub-model", help="model name the stub reports (e.g. jev-1.13.0) to count new calls against a "
                                         "copy of a real cache; never point --cache-file at the real cache itself")
    ap.add_argument("--env-file", action="append", help="extra .env file to look for JEV_API_KEY in (after "
                                                         "<backend>/.env)")
    ap.add_argument("--model", help="override JEV_MODEL (default: the PR setting jev_model)")
    ap.add_argument("--timeout", type=float, help="override JEV_TIMEOUT_SECONDS")
    ap.add_argument("--write-settings", help="also write the frozen settings file (e.g. results/settings.json)")
    ap.add_argument("--aligned", action="append", help="E3 aligned folder(s) (inputs/aligned and "
                                                      "inputs/aligned_touch_none); replaces --input")
    ap.add_argument("--bundle", default="b0_r0", help="value bundle whose E3 AB0 rows give situation, gaze, measurable")
    ap.add_argument("--conditions", nargs="*", help="touch conditions to read from the aligned files (default all)")
    ap.add_argument("--variant", default="fit-medium", help="E3 placement variant (the aligned files hold fit-medium)")
    ap.add_argument("--windows-dir", default=str(DEFAULT_WINDOWS_DIR),
                    help="folder of E3's windows_<bundle>.csv(.gz) (default inputs/e3_windows)")
    ap.add_argument("--no-cache", action="store_true", help="call the API again for identical requests")
    ap.add_argument("--no-order-swap", dest="order_swap", action="store_false",
                    help="skip the reversed-order second support_choice call")
    ap.add_argument("--perm-seed", type=int, default=0, help="seed of the permuted-values controls")
    ap.add_argument("--cache-file", help="append-only JSONL of answers and repeats, reused across runs and bundles "
                                         "(cache mode: read-only, .jsonl or .jsonl.gz)")
    ap.add_argument("--repeat-fraction", type=float, default=1.0,
                    help="repeat only the requests of this seeded share of the windows (e.g. 0.1)")
    ap.add_argument("--repeat-seed", type=int, default=0)
    ap.add_argument("--windows-name", default="windows.jsonl",
                    help="window file name inside each take folder of --input (e.g. windows_b0.jsonl in round3_replay)")
    ap.add_argument("--tag-source", choices=("replay", "verified"), default="replay",
                    help="aligned input: situation tags from E3's AB0 rows (replay) or from the verified window labels "
                         "(verified: the A_GT / C_GT diagnostic, E3's AB0-GT rule)")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="takes in flight at once within an arm (1 = sequential); the API's rate limit is unknown")
    ap.add_argument("--backoff-base-s", type=float, default=1.0, help="first pause after HTTP 429 / 529 (doubles)")
    ap.add_argument("--backoff-tries", type=int, default=5, help="retries after HTTP 429 / 529 per call")
    args = ap.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
