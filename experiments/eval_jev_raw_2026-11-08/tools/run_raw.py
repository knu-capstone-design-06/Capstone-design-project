"""E12 runner: Jev chooses end to end from processed camera numbers (MediaPipe + H1) plus the touch values.

Same windows, rule pass and shadow flow as E5's arm J (b0_r0, 35 team clips x C0-C6, aligned as in E5): E5's
run_jev_ablation.py is imported for the PR modules, the window inputs (load_aligned, build_windows), the rule pass,
the clients (stub, cache, backoff, recorder) and the output lines; nothing in E5 is changed. Only the request
differs from J's: the situation and vision parts of J's state (rule-made tags, gaze) are replaced by the camera block
of camera_features.py, and the question carries the camera field definitions (instructions.camera_fields).

Arms (both choose among all six supports plus none, J's option set and the PR's wording):
  RAW-1  one stage: support_choice from the raw state
  RAW-2  stage 1: the five state scores (STATE_QUESTIONS of the PR) from the raw state; stage 2: support_choice with
         the stage-1 answers under state.jev (the PR's with_previous, as in E5's score-then-choose)
In the run files both carry condition "J": E5's metrics.py scores a condition-J arm as a choice among all supports
plus none; the arm names and JEV_STAGES ("raw:...") tell them apart.

Not sent: images, situation tags, gaze, the rule table's candidate filter or its own questions, P1 head direction,
people_behind_count / companion_box. Sent besides the camera block (as J): screen {name, steps_left}, touch
{misses_recent, fixes_recent, backs_recent, pause_s}, session {active, held, refused, withdrawn} of the rule table's
shadow flow, candidates = the fixed list of all six supports.

  <backend venv python> -B run_raw.py --jev stub|real --out <dir> [--takes ...] [--max-calls N] [--concurrency N]
The key is read as E5 reads it (environment JEV_API_KEY, else Capstone-design-project/backend/.env); never printed.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import asyncio
import contextvars
import copy
import json
import logging
import platform
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
WS = HERE.parents[2]
E5_TOOLS = WS / "4_vision" / "eval_jev_2026-11-04" / "tools"
EVAL_AB = WS / "4_vision" / "eval_ab_2026-11-04"
sys.path.insert(0, str(E5_TOOLS))
sys.path.insert(0, str(HERE))
import run_jev_ablation as R      # noqa: E402  (E5, imported only)
import camera_features as F       # noqa: E402

ENV_FILE = WS / "Capstone-design-project" / "backend" / ".env"
# E5's arm J input (results/real_2026-11-05_3c936ae/stage2_3_J_b0_r0/run_settings.json command)
J_INPUT = {"aligned": [EVAL_AB / "aligned", EVAL_AB / "aligned_touch_none"], "windows_dir": EVAL_AB / "results" / "labels_v2",
           "bundle": "b0_r0", "variant": "fit-medium", "conditions": ["C0", "C1", "C2", "C3", "C4", "C5", "C6"]}
CAMERA = contextvars.ContextVar("e12_camera", default=None)   # the camera block of the window being asked


def raw_state(state: dict, camera: dict) -> dict:
    """J's state with situation and vision replaced by the camera block (first); other parts in J's order."""
    out = {"camera": camera}
    out.update({k: v for k, v in state.items() if k not in ("situation", "vision")})
    return out


class RawChoiceStage:
    """support_choice over all six supports + none: J's stage (E5 JevAloneStage, the PR's wording), raw state."""

    name = "support_choice"

    def __init__(self, pr, defs: dict):
        self._j, self._defs = R.JevAloneStage(pr), defs

    def build(self, ctx):
        state, questions = self._j.build(ctx)
        q = questions["support_choice"]
        q["instructions"] = {"question": q["instructions"], "camera_fields": self._defs}
        return raw_state(state, CAMERA.get()), questions


class RawScoreStage:
    """The five state scores (the PR's STATE_QUESTIONS, criteria unchanged) from the raw state; the rule table's own
    question (proposal_fits / queue_support) is not added (a rule output)."""

    name = "state_scores"

    def __init__(self, pr, defs: dict):
        self._pr, self._defs = pr, defs

    def build(self, ctx):
        Q = self._pr.Q
        state = Q.with_previous(Q.shadow_state(ctx.inp, ctx.state, ctx.touch), ctx.previous)
        questions = {name: {"type": body["type"],
                            "instructions": {"question": body["instructions"], "camera_fields": self._defs},
                            "criteria": copy.deepcopy(body["criteria"])}
                     for name, body in Q.STATE_QUESTIONS.items()}
        return raw_state(state, CAMERA.get()), questions


@dataclass
class RawArm:
    spec: str
    stage_classes: tuple
    jev_stages: str
    meaning: str
    condition: str = "J"          # metrics.py: a choice among all supports + none (J's option set)
    variant: str = "raw"


ARMS = {
    "RAW-1": RawArm("RAW-1", (RawChoiceStage,), "raw:support_choice",
                    "one stage: support_choice over all six supports + none from the raw state"),
    "RAW-2": RawArm("RAW-2", (RawScoreStage, RawChoiceStage), "raw:state_scores,raw:support_choice",
                    "stage 1 the five state scores from the raw state, stage 2 support_choice over all six supports "
                    "+ none with the stage-1 answers under state.jev"),
}


def camera_blocks(takes: dict, span: float) -> tuple[dict, dict]:
    """{(take, i): camera block} and the session starts used. A rule-table session after the first starts at the end
    time of its first window (= E3 TouchTimeline.session_since in all 12 session changes, camera_features docstring)."""
    rows_of, out, starts = {}, {}, {}
    for take, windows in takes.items():
        clip = take.split("@")[0]
        if clip not in rows_of:
            rows_of[clip] = F.load_rows(clip)
            R.INPUT_FILES.add(str(F.REPLAY / clip / "rows.csv"))
        rows = rows_of[clip]
        first = {}
        for w in windows:
            first.setdefault(w.session_k, w.t)
        refs = {k: (None if k == 0 else F.session_ref(rows, t0)) for k, t0 in first.items()}
        for k, t0 in first.items():
            if k > 0:
                starts[f"{take}#{k}"] = {"start_s": t0, "start_pose_found": refs[k] is not None}
        for w in windows:
            k = w.session_k
            out[(take, w.i)] = F.camera_block(rows, w.t, span, None if k == 0 else first[k], refs[k])
    return out, starts


async def run_arm(pr, arm: RawArm, takes: dict, cameras: dict, cache, args, states: dict, questions_cat: dict,
                  out_fh, budget: dict, defs: dict) -> dict:
    """E5 run_arm (run_jev_ablation.py) for one RAW arm: the same skip rules, history, add_window and line format;
    no variants, no order swap, no repeats."""
    stages = tuple(cls(pr, defs) for cls in arm.stage_classes)
    counts = {"windows": 0, "asked": 0, "requests": 0, "answered": 0, "no_answer": 0, "skipped_stage": 0}
    gate = asyncio.Semaphore(max(1, args.concurrency))

    async def run_take(take, windows):
        recorder = R.Recorder(cache)
        repo = pr.repo.DecisionRepository()
        service = pr.svc.DecisionService(repo, pr.params, jev=recorder, stages=stages)
        busy_until: dict = {}
        t0 = R.take_start(take)
        for w in windows:
            sid = f"{take}#{w.session_k}"
            history = repo.history(sid)
            d = w.decision
            counts["windows"] += 1
            line = {"arm": arm.spec, "condition": arm.condition, "variant": arm.variant, "jev_stages": arm.jev_stages,
                    "take": take, "i": w.i, "t": w.t, "session": sid, "asked": False, "skip_reason": None,
                    "would_skip_in_flight": bool(w.t < busy_until.get(sid, float("-inf"))), "stages": []}
            if not w.inp.measurable:
                line["skip_reason"], why = "not measurable", "not_measurable"
            elif args.max_calls is not None and budget["calls"] >= args.max_calls:
                line["skip_reason"], why = "max_calls", "skipped_max_calls"
            elif (args.max_failure_rate is not None and budget["calls"] >= R.FAILURE_GUARD_MIN_CALLS
                  and budget["failed"] > args.max_failure_rate * budget["calls"]):
                line["skip_reason"], why = "failure_rate", "skipped_failure_rate"
            else:
                why = "asked"
            R.add_window(pr, repo, service, sid, w, t0 + timedelta(seconds=w.t), why)
            if why == "asked":
                recorder.calls.clear()
                window_ns = SimpleNamespace(touch=w.touch, window_end=t0 + timedelta(seconds=w.t))
                R.CURRENT.set((arm.spec, take, w.i))
                CAMERA.set(cameras[(take, w.i)])
                records = await service.ask_shadow(sid, window_ns, w.inp, d, w.before, history)
                line["asked"] = True
                counts["asked"] += 1
                done = {r.stage for r in records}
                total_ms = 0.0
                for rec, call in zip(records, recorder.calls):
                    st_hash, q_hash = R.digest(call["request"]["state"]), R.digest(call["request"]["questions"])
                    states.setdefault(st_hash, call["request"]["state"])
                    questions_cat.setdefault(q_hash, call["request"]["questions"])
                    resp = call["response"]
                    line["stages"].append({
                        "stage": rec.stage, "outcome": rec.outcome, "failure": call["failure"],
                        "latency_ms": round(call["latency_ms"], 3), "cached": call["cached"],
                        "latency_ms_service": rec.latency_ms, "request_bytes": call["bytes"], "state_hash": st_hash,
                        "questions_hash": q_hash, "questions": list(rec.questions), "request_model": rec.request_model,
                        "response_model": rec.response_model, "usage": rec.usage,
                        "answers": {k: R.answer_view(v) for k, v in (resp or {}).get("answers", {}).items()}})
                    total_ms += call["latency_ms"]
                    counts["requests"] += 1
                    counts["answered" if rec.outcome == "answered" else "no_answer"] += 1
                for s in stages:
                    if s.name not in done:
                        line["stages"].append({"stage": s.name, "outcome": "skipped", "reason": "build returned None"})
                        counts["skipped_stage"] += 1
                order = {s.name: k for k, s in enumerate(stages)}
                line["stages"].sort(key=lambda e: order.get(e["stage"], 99))
                busy_until[sid] = w.t + total_ms / 1000.0
            out_fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    async def guarded(take, windows):
        async with gate:
            await run_take(take, windows)

    await asyncio.gather(*(guarded(take, ws) for take, ws in takes.items()))
    return counts


async def main_async(args) -> int:
    pr = R.PR(Path(args.backend))
    arms = [ARMS[a] for a in args.arms]
    only = set(args.takes) if args.takes else None
    takes_raw = R.load_aligned(J_INPUT["aligned"], J_INPUT["bundle"], set(J_INPUT["conditions"]), J_INPUT["variant"],
                               only, J_INPUT["windows_dir"], "replay")
    if not takes_raw:
        raise SystemExit("no takes")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    takes = {}
    for take, records in takes_raw.items():
        windows = R.build_windows(pr, take, records)
        R.rule_pass(pr, windows)
        takes[take] = windows
    span = F.span_s()
    R.INPUT_FILES.add(str(F.BUNDLE))
    defs = F.field_defs(span)
    cameras, starts = camera_blocks(takes, span)

    failures = R.FailureLog()
    logging.getLogger(pr.client.__name__).addHandler(failures)
    logging.getLogger(pr.client.__name__).propagate = False
    http, key_source = None, None
    if args.jev == "stub":
        inner = R.StubJev(pr, args.stub_seed, 0)
        if args.stub_model:
            inner.model = args.stub_model
        model, base_url, timeout = inner.model, None, None
    else:
        settings, key_source = R.load_settings(pr, [ENV_FILE])
        if settings.jev_api_key is None:
            print("key absent: JEV_API_KEY is not set in the environment or in", ENV_FILE, "- real run skipped")
            return 2
        model = args.model
        base_url, timeout = settings.jev_api_url, settings.jev_timeout_seconds
        http = pr.client.create_jev_http(settings.jev_api_key.get_secret_value(), base_url, timeout)
        inner = pr.client.JevClient(http, model, timeout)
        print(f"real Jev: model {model}, {base_url}, timeout {timeout} s, key from {key_source}")
    budget = {"calls": 0, "cached": 0, "failed": 0, "repeat_calls": 0, "backoff_retries": 0, "cache_misses": 0,
              "pinned": 0}
    inner = R.BackoffClient(inner, failures, budget, args.backoff_base_s, args.backoff_tries)
    cache = R.CachingClient(inner, failures, budget, enabled=True,
                            cache_file=Path(args.cache_file) if args.cache_file else None, js=pr.js)
    if cache.loaded:
        print(f"cache file: {cache.loaded} answers loaded")
    states, questions_cat, arm_counts = {}, {}, {}
    started = time.perf_counter()
    try:
        with open(out / "jev_calls.jsonl", "w", encoding="utf-8") as fh:
            for arm in arms:
                arm_counts[arm.spec] = await run_arm(pr, arm, takes, cameras, cache, args, states, questions_cat, fh,
                                                     budget, defs)
                print(f"arm {arm.spec}: {arm_counts[arm.spec]}; budget {budget}")
    finally:
        cache.close()
        if http is not None:
            await http.aclose()
    wall = time.perf_counter() - started
    (out / "repeats.jsonl").write_text("", encoding="utf-8")      # metrics.py reads it; no repeats in E12
    with open(out / "rule_windows.jsonl", "w", encoding="utf-8") as fh:
        for windows in takes.values():
            for w in windows:
                fh.write(json.dumps(R.rule_line(pr, w, None), ensure_ascii=False,
                                    default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else str(o)) + "\n")
    with open(out / "camera_blocks.jsonl", "w", encoding="utf-8") as fh:
        for (take, i), cam in cameras.items():
            fh.write(json.dumps({"take": take, "i": i, "camera": cam}, ensure_ascii=False) + "\n")
    with open(out / "states.jsonl", "w", encoding="utf-8") as fh:
        for h, s in states.items():
            fh.write(json.dumps({"state_hash": h, "state": s}, ensure_ascii=False) + "\n")
    (out / "questions.json").write_text(json.dumps(questions_cat, ensure_ascii=False, indent=1), encoding="utf-8")
    import httpx
    import pydantic
    run_settings = {
        "created": datetime.now(R.KST).isoformat(timespec="seconds"), "command": [Path(sys.executable).name, *sys.argv],
        "experiment": "E12: Jev end to end from processed camera numbers + touch values",
        "jev": args.jev, "model": model, "base_url": base_url, "timeout_s": timeout, "key": key_source,
        "pr_backend": str(pr.backend), "pr_commit": pr.commit,
        "arms": [{"arm": a.spec, "condition": a.condition, "JEV_STAGES": a.jev_stages, "variant": a.variant,
                  "variant_meaning": [a.meaning], "wording_file": None,
                  "condition_note": "J = scored by E5 metrics.py as a choice among all six supports + none"}
                 for a in arms],
        "inputs": [str(d) for d in J_INPUT["aligned"]],
        "aligned": {"bundle": J_INPUT["bundle"], "variant": J_INPUT["variant"], "conditions": J_INPUT["conditions"],
                    "windows_rows": str(J_INPUT["windows_dir"] / f"windows_{J_INPUT['bundle']}.csv")},
        "camera": {"replay": str(F.REPLAY), "span_s": span, "span_source": f"{F.BUNDLE} situation.window_s",
                   "later_session_starts": starts},
        "cache_identical": True, "order_swap": False, "order_swap_cache": None, "tag_source": "none (no tags sent)",
        "input_sha256": {f: R.sha_file(f) for f in sorted(R.INPUT_FILES)},
        "takes": {t: len(w) for t, w in takes.items()}, "labels": None, "in_flight": "record", "repeats": 1,
        "max_calls": args.max_calls, "max_failure_rate": args.max_failure_rate, "concurrency": args.concurrency,
        "calls_total": budget["calls"], "calls_failed": budget["failed"], "answers_from_cache": budget["cached"],
        "backoff_retries": budget["backoff_retries"], "cache_file": args.cache_file, "cache_loaded": cache.loaded,
        "backoff": {"base_s": args.backoff_base_s, "tries": args.backoff_tries}, "wall_s": round(wall, 3),
        "arm_counts": arm_counts, "questions_catalog": sorted(questions_cat), "distinct_states": len(states),
        "python": platform.python_version(), "httpx": httpx.__version__, "pydantic": pydantic.__version__,
    }
    (out / "run_settings.json").write_text(json.dumps(run_settings, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {sum(len(w) for w in takes.values())} windows in {len(takes)} takes, {budget['calls']} API calls "
          f"({budget['cached']} answers from cache, {budget['failed']} failed), {wall:.1f} s -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--jev", choices=("stub", "real"), default="stub")
    ap.add_argument("--arms", nargs="*", default=list(ARMS), choices=list(ARMS))
    ap.add_argument("--takes", nargs="*", help="only these clips (aligned file stems)")
    ap.add_argument("--backend", default=str(R.DEFAULT_BACKEND), help="PR #77 backend/ at 3c936ae (E5's)")
    ap.add_argument("--cache-file", help="append-only answer cache (JSONL) of this experiment")
    ap.add_argument("--max-calls", type=int)
    ap.add_argument("--max-failure-rate", type=float, default=0.01, help="E5's stop rule (0.01)")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--model", default="jev-1.13.0", help="E5 arm J's model (stage2_3_J_b0_r0 run_settings.json)")
    ap.add_argument("--stub-seed", type=int, default=0)
    ap.add_argument("--stub-model", help="model name the stub reports")
    ap.add_argument("--backoff-base-s", type=float, default=1.0)
    ap.add_argument("--backoff-tries", type=int, default=5)
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
