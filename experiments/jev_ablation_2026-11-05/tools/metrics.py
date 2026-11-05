"""E5 metrics over one run folder of run_jev_ablation.py (rule_windows.jsonl, jev_calls.jsonl, repeats.jsonl,
run_settings.json). Writes metrics.json and metrics.md next to the run. The formulas, with their denominators, are
in README.md §5 and results/settings.json ("metrics").

Design (supervisor review, Codex 200; survey guide 6_records/reviews/2026-11-04/experiment_changes_from_survey.md P2):
each kind of output is scored on its own, never in one accuracy column.
  selection      PRIMARY. A against C / C0 / E inside the rule filter (options = the question actually sent), against
                 the admissible actions of the window (E3 admissible_v<N> with the add-on onset, or the judgment
                 labels), with a chance column, clip-bootstrap intervals, the option-order swap (a choice counts
                 only when both orders agree), next-window application beside an equally delayed A, segment 2x2
                 (false alarm, missed help, offer precision) with Wilson intervals, and the error attribution
                 (perception: the window's tag differs from the ground-truth tag; judgment: tag right, choice wrong).
  state          B (every arm with state_scores): the five scores described; where a label maps to states, Brier,
                 ECE (10 equal-width bins) and AUROC per binary question with sample counts.
  forecast       D / E next_difficulty against the next NEXT_HORIZON_S seconds' labels, with majority and
                 persistence baselines.
  execution      windows, eligible, attempted, answered, failed by kind, skipped by reason; API calls, answers from
                 the identical-request cache, calls per attempted window, escalation rate; latency p50 / p95 / max of
                 API calls only (wall clock around the client call).
  controls       paired comparisons, repeat consistency (Fleiss kappa, share of requests with one choice), the
                 permuted-values arms (B:perm_vision, B:perm_touch) scored like any arm, label- and answer-shuffled
                 null checks (by session and globally).
No threshold is applied to a Jev probability. In a stub run the Jev-derived sections are computed only to check the
code paths: metrics.md prints them as 'not evaluated: API unavailable'.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

SUPPORTS = {"wait_hold_timer", "remaining_steps_notice", "delay_responsibility_notice", "large_button",
            "highlight_next_action", "defer_big_button_question", "call_staff", "general_help_ask", "none"}
RULE_SUPPORTS = ("wait_hold_timer", "remaining_steps_notice", "delay_responsibility_notice", "large_button",
                 "highlight_next_action", "defer_big_button_question")
ACTIONS = {"wait", "propose", "apply", "call_staff", "none"}
KOREAN_ACTIONS = {"기다림": "wait", "묻기": "propose", "바로 적용": "apply", "바로적용": "apply", "직원 호출": "call_staff",
                  "직원호출": "call_staff", "없음": "none"}   # rule_table.py INTERVENTION, read backwards
ACTION_OF = {"wait_hold_timer": "wait", "remaining_steps_notice": "apply", "delay_responsibility_notice": "apply",
             "large_button": "propose", "highlight_next_action": "apply", "defer_big_button_question": "wait",
             "call_staff": "call_staff", "general_help_ask": "propose",
             "none": "wait"}   # rule_table.py candidate_rows actions and the 3-1 choice_actions; showing nothing = 기다림
VISIBLE = {"apply", "propose", "call_staff"}   # 평가 설계 v1.4 §2-2 '보이는 허용 행동' (기다림 is not visible)
TAGS = ("looking_back_with_people_behind", "consulting_companion", "looking_around")
STATE_NAMES = ("normal", "touch_difficulty", "navigation_difficulty", "visual_difficulty", "hesitation")
DIFF_ORDER = ("touch_difficulty", "navigation_difficulty", "visual_difficulty", "hesitation", "none")  # jev_questions
NEXT_HORIZON_S = 10.0   # the next_difficulty question's own horizon ("within the next ten seconds", jev_questions.py)
# Label -> states: the contract StateScores names against the scenes (조사 47 §2-4 '상태 어휘':
# touch_difficulty = 4-1, navigation_difficulty = 4-2, visual_difficulty = 2-1, hesitation = 4-2, normal = 정상 사용).
# A label maps through the scene numbers of its designated support (from its onset) or its plan; plan S0 (촬영 계획
# 2판 §2-2 '보통 주문') is read as normal (Claude's reading of 정상 사용). Labels of other scenes: no mapping, excluded.
STATE_PROXY = {"4-1": {"touch_difficulty"}, "4-2": {"navigation_difficulty", "hesitation"}, "2-1": {"visual_difficulty"}}
NORMAL_PLANS = {"S0"}
STATE_PROXY_SOURCE = ("조사 47 §2-4 (2_requirements/research/7_rules_review_2026-10-29/"
                      "47_current_rules_bias_audit_2026-10-29.md); S0 = normal is Claude's reading")
DEFAULT_PERMS = 1000
BOOT_RESAMPLES, BOOT_SEED = 9999, 20261104   # survey guide standing rule (clip bootstrap, percentile; PROTOCOL §4-4)
SEG_CLASSES_2X2 = ("wait_only", "designated")
# segments no policy score uses: excluded (ambiguous), and since labels v3 the contradictory cells (a planned behaviour
# without presses crossed with a touch condition that presses) are not evaluable for policy metrics
SCORING_VERSION = ("2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)")
INPUTS = Path(__file__).resolve().parents[1] / "inputs"      # the package's inputs/ (E3 bundles, labels)
NOT_EVALUABLE = {"excluded", "contradictory"}  # survey guide P1 #2; no_user, time_stop, excluded, other: counted apart

# The formulas, with their denominators (frozen into results/settings.json; README §3 says the same in Korean).
FORMULAS = {
    "options": "O_w = allowed candidates of window w (rule_table.allowed_supports on the state the table decided on) "
               "+ none; K_w = |O_w|",
    "admissible": "admissible mode (E3 admissible_v<N>, joined on segment_id x condition x variant): a selection is "
                  "admissible when it is none (no new support) or its form is in base_admissible, plus "
                  "addon_admissible for windows ending at or after addon_onset_s; time mode (judgment labels): its "
                  "action is in the allowed set, nothing shown = wait",
    "selection_agreement": "k / n, n = labelled windows of the scope (all; windows with candidates; windows where the "
                           "arm answered), k = windows whose selection is admissible; 95% interval = clip bootstrap",
    "with_rule_fallback": "k / n over all labelled windows; where support_choice gave no answer, was skipped or the "
                          "window was not asked, A's selection is used",
    "order_agreed": "a support_choice answer counts only when the reversed-order call (criteria and state.candidates "
                    "reversed) answered the same choice; otherwise the window abstains (status order_disagree / "
                    "order_unanswered); the reversed request is cached under an order-aware key (its JSON in sent "
                    "order) -- runs made before 2026-11-05 used an order-blind key and their order figures are invalid "
                    "(Codex 205 #1)",
    "order_consistency": "windows with both orders answered and the same choice / windows with both orders answered",
    "chance_selection": "mean over the scored windows of a_w / K_w (a_w = admissible options), on the same windows "
                        "and with the same abstention as the figure beside it; under the two-order protocol a uniform "
                        "chooser agrees with probability 1 / K_w and gives an agreed admissible choice with a_w / K_w^2",
    "chance_designated": "mean over windows with a designated support of 1 / K_w when the designated support is an "
                         "option, else 0",
    "segment_2x2": "per segment (take x label row; a take is clip x touch condition; only designations with a "
                   "rule-table v0 row; contradictory and excluded segments are not evaluable): TP = designated with "
                   "admissible help after onset (HELP_RULE), FN = designated without, FP = wait-only with a new visible "
                   "selection, TN = wait-only without; false alarm FP / (FP + TN), missed help FN / (TP + FN), offer "
                   "precision TP / (TP + FP); designated delivery = the designated support itself under HELP_RULE; "
                   "designations without a v0 row apart, by designated delivery only; split by origin (camera / touch "
                   "S3 add-on); 95% Wilson; no_user, time_stop, excluded and other segments counted apart",
    "next_window": "pairs (N, N+1) in one session with N+1 labelled and the arm answered at N: C's selection of N, A's "
                   "selection of N (delayed one window) and A's of N+1, each scored against N+1's label",
    "decision_error_split": "descriptive, no causal claim: windows whose selection is not admissible, split into "
                            "decision errors with an incorrect observed tag (the window's situation tag, none when "
                            "no tag, differs from truth_tag) and with a correct observed tag; apart: observed tag "
                            "unknown, truth_tag missing or ambiguous",
    "state_target": "y_q = 1 when the window's label maps to state q (STATE_PROXY), 0 when it maps to other states; "
                    "windows without a mapping are excluded",
    "brier": "mean over n of (p - y)^2",
    "ece": "sum over the 10 equal-width bins b of (n_b / n) |observed_b - mean_p_b|, observed_b = share of y = 1 in b",
    "auroc": "probability that a window with y = 1 has a higher p than one with y = 0, ties counted half "
             "(Mann-Whitney); undefined when only one class is present",
    "forecast": "k / n, n = windows where next_difficulty answered and a mapped label lies in (t, t + 10 s] of the "
                "session; hit = the forecast is one of the mapped classes there (normal = none); majority = the class "
                "present in most targets; persistence = the window's own first mapped class; chance = mean |target| / 5; the "
                "forecast is also scored on exactly the windows where persistence applies",
    "repeats": "per distinct request sent R = --repeats times (bypassing the cache): one-choice share = requests whose "
               "R choices are equal / requests with all R answered (95% Wilson), flip share = 1 - that, Fleiss kappa "
               "over requests x R, pairwise agreement P_i = (sum_j n_ij^2 - R) / (R (R - 1)); noul: range and SD of p",
    "null": "labels shuffled, or answers shuffled, within each session and, separately, over all windows (seed 0), on "
            "the same scored windows as the primary figures; mean and min-max of the agreement count or Brier; the "
            "min-max range is the spread of the shuffled values, not a significance test; no p-values",
    "scored_population": "labelled windows outside excluded segments; one set for selection, state estimation, rule "
                         "question, forecast and the null controls",
    "cost": "API calls (cached answers excluded) / attempted windows; escalation = windows whose support_choice stage "
            "was attempted / measurable windows",
    "latency": "wall clock (time.perf_counter) around each API call; cached answers excluded; p50, p95 (linear "
               "interpolation, Hyndman & Fan type 7) and max per stage and for the whole chain",
    "intervals": "window-level k / n: 95% percentile interval of a clip bootstrap (9,999 resamples, seed 20261104); "
                 "segment and request level: 95% Wilson",
}

COLS = {
    "take": ("take", "take_id", "video", "clip"),
    "t_start": ("t_start", "start_s", "seg_start_s", "segment_start", "t0", "start"),
    "t_end": ("t_end", "end_s", "seg_end_s", "segment_end", "t1", "end"),
    "allowed": ("allowed", "allowed_actions", "allowed_supports", "allowed_set", "admissible"),
    "designated": ("designated", "designated_action", "designated_support", "required"),
    "states": ("state", "states", "difficulty", "difficulties", "state_label"),
    "segment": ("segment_id", "segment", "seg_id", "row_id", "id"),
    "plan": ("scene_plan", "scene"),
    "truth": ("truth_tag",),
    "made_by": ("made_by",),
    "onset": ("onset_s",),
    "eff_class": ("segment_class", "eff_class"),
    "v0_row": ("v0_row", "designated_v0_row"),
    "truth_seconds": ("truth_seconds",),
}


def tokens(cell: str | None) -> list[str]:
    if cell is None:
        return []
    return [KOREAN_ACTIONS.get(t.strip(), t.strip()) for t in re.split(r"[;|,/]+", cell.strip()) if t.strip()]


def designated_names(text: str) -> list[str]:
    return [s for s in RULE_SUPPORTS if re.search(rf"\b{s}\b", text or "")]


def scenes_of(text: str) -> list[str]:
    return sorted(set(re.findall(r"\b\d-\d\b", text or "")))


class Labels:
    """The judgment label table matched by time: rows (take, segment start / end, allowed set, designated support,
    plan, truth tag, optional states)."""

    mode = "time"

    def __init__(self, rows: list[dict], path: str, columns: dict):
        self.rows, self.path, self.columns = rows, path, columns
        self.by_take = defaultdict(list)
        for r in rows:
            self.by_take[r["take"]].append(r)
        notes = {r["made_by"] for r in rows if r.get("made_by")}
        self.status = "; ".join(sorted(notes)) if notes else None

    @classmethod
    def load(cls, path) -> "Labels":
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            header = {h.strip().lower(): h for h in (reader.fieldnames or [])}
            columns = {k: next((header[a] for a in names if a in header), None) for k, names in COLS.items()}
            if columns["take"] is None or columns["allowed"] is None:
                raise SystemExit(f"{path}: need a take column {COLS['take']} and an allowed column {COLS['allowed']}; "
                                 f"found {reader.fieldnames}")
            rows = []
            for n, r in enumerate(reader):
                get = lambda key: (r.get(columns[key]) or "").strip() if columns[key] else ""
                allowed = tokens(get("allowed"))
                level = "support" if all(a in SUPPORTS for a in allowed) else (
                    "action" if all(a in ACTIONS for a in allowed) else "mixed")
                designated_text = get("designated")
                rows.append({
                    "mode": "time", "row": n, "take": get("take"),
                    "t_start": float(get("t_start")) if get("t_start") else None,
                    "t_end": float(get("t_end")) if get("t_end") else None,
                    "allowed": allowed, "level": level, "designated_text": designated_text,
                    "designated": designated_names(designated_text), "designated_all": designated_names(designated_text),
                    "scenes": scenes_of(designated_text + " " + get("plan")), "plan": get("plan"),
                    "states": tokens(get("states")), "segment": get("segment") or None, "truth_tag": get("truth") or None,
                    "made_by": get("made_by") or None,
                    # labels v3 (Codex 209 #2): the onset of the designated support, the segment class and whether rule
                    # table v0 has a row for the designation, as in the admissible table; None when the file lacks them
                    "onset": float(get("onset")) if get("onset") else None,
                    "eff_class": get("eff_class") or None,
                    "v0_row": get("v0_row") if columns["v0_row"] else None,
                    "truth_secs": [float(x) for x in get("truth_seconds").split(";") if x] if columns["truth_seconds"]
                    else None,
                    # for help_rule: the judgment row as an admissible row without touch add-on (vision windows)
                    "e3_row": {"segment_id": get("segment"), "base_set": set(x.strip() for x in get("allowed").split(";")
                                                                            if x.strip()),
                               "addon_set": set(), "addon_onset": None,
                               "onset": float(get("onset")) if get("onset") else None,
                               "designated": designated_text, "designated_v0_row": get("v0_row") if columns["v0_row"]
                               else "", "rules": ""},
                })
        return cls(rows, str(path), columns)

    def match(self, take: str, t: float, segment=None) -> dict | None:
        """The label row of the window ending at t, by the rule of E3 / E4 (eval_ab_2026-11-04/tools/harness.py
        segment_at) so the three experiments count the same windows: the row with t_start <= t < t_end, the last
        row closed at its end; a t after the last row takes the last row and a t before the first row the first
        ('fallback'). A row without times covers the whole take."""
        rows = sorted(self.by_take.get(take, []), key=lambda r: (r["t_start"] is not None, r["t_start"] or 0.0))
        if not rows:
            return None
        if all(r["t_start"] is None for r in rows):
            return {**rows[0], "match": "take", "multiple": len(rows) > 1}
        timed = [r for r in rows if r["t_start"] is not None and r["t_end"] is not None]
        for k, r in enumerate(timed):
            last = k == len(timed) - 1
            if r["t_start"] <= t < r["t_end"] or (last and r["t_start"] <= t <= r["t_end"] + 1e-6):
                return self._at_onset({**r, "match": "inside", "multiple": False}, t)
        r = timed[-1] if t > timed[-1]["t_end"] else timed[0]
        return self._at_onset({**r, "match": "fallback", "multiple": False}, t)

    @staticmethod
    def _at_onset(r: dict, t: float) -> dict:
        """Before the designated support's onset the window has no designation and no designated scene (so no
        state target from it), as AdmissibleLabels.match_record does (Codex 209 #2)."""
        if r.get("onset") is not None and t < r["onset"] - 1e-9:
            r["designated"], r["scenes"] = [], scenes_of(r.get("plan") or "")
        return r

    def match_record(self, r: dict) -> dict | None:
        return self.match(r.get("clip") or r["take"], r["t"])


def e3_row(r: dict) -> dict:
    """An admissible-table row in the form E3's make_admissible.load() gives help_rule (sets of Korean forms, floats)."""
    sets = lambda k: set(x for x in (r.get(k) or "").split(";") if x)
    f = lambda k: float(r[k]) if r.get(k) else None
    return {"segment_id": r["segment_id"], "base_set": sets("base_admissible"), "addon_set": sets("addon_admissible"),
            "addon_onset": f("addon_onset_s"), "onset": f("onset_s"), "designated": r.get("designated") or "",
            "designated_v0_row": r.get("designated_v0_row") or "", "rules": r.get("rules") or ""}


class AdmissibleLabels:
    """E3's admissible table (admissible_v<N>.csv; v3 current): one row per segment x touch condition x variant, joined to a window by its
    segment_id, condition and variant. A window ending at t takes the base set, plus the add-on forms from
    addon_onset_s on; the designated support counts from onset_s on (E3 run_eval.py annotate / seg_summaries)."""

    mode = "admissible"

    def __init__(self, rows: dict, path: str, kinds: set, segments: "Labels | None" = None):
        self.rows, self.path = rows, path
        self.status = "; ".join(sorted(kinds)) + f" ({Path(path).name})" if kinds else None
        self.columns = Path(path).stem
        # with a judgment-label file (v2 changed boundaries and added segments), the window's segment comes from it by
        # the window end (E3 segment_at), not from the segment_id the aligned record carries (v1)
        self.segments = segments

    @classmethod
    def load(cls, path, segments_path=None) -> "AdmissibleLabels":
        rows, kinds = {}, set()
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                f = lambda k: float(r[k]) if r.get(k) else None
                rows[(r["segment_id"], r["condition"], r["variant"])] = {
                    "segment_id": r["segment_id"], "take": r["take"], "condition": r["condition"],
                    "variant": r["variant"], "plan": r["scene_plan"], "eff_class": r["eff_class"],
                    "contradictory": r["contradictory"] == "True", "truth_tag": r["truth_tag"] or None,
                    "base": tokens(r["base_admissible"]), "addon": tokens(r["addon_admissible"]),
                    "addon_onset": f("addon_onset_s"), "onset": f("onset_s"), "designated_text": r["designated"],
                    "designated_all": [d.split("(")[0] for d in r["designated"].split(";") if d],
                    "v0_row": r["designated_v0_row"], "rules": r.get("rules") or "", "base_class": r.get("base_class"),
                    "e3_row": e3_row(r),
                    "truth_secs": [float(x) for x in (r.get("truth_seconds") or "").split(";") if x]
                    if "truth_seconds" in r else None}
                kinds.add(r.get("label_kind") or "")
        segs = Labels.load(segments_path) if segments_path else None
        return cls(rows, str(path), {k for k in kinds if k}, segs)

    def match_record(self, r: dict) -> dict | None:
        sid, seg = r.get("segment_id"), None
        if self.segments is not None:
            seg = self.segments.match(r.get("clip") or r["take"], r["t"])
            sid = None if seg is None else seg["segment"]
        a = self.rows.get((sid, r.get("condition"), r.get("variant")))
        if a is None:
            return None
        t = r["t"]
        allowed = set(a["base"])
        if a["addon_onset"] is not None and t >= a["addon_onset"] - 1e-9:
            allowed |= set(a["addon"])
        started = a["onset"] is None or t >= a["onset"] - 1e-9
        return {"mode": "admissible", "row": f"{a['segment_id']}|{a['condition']}|{a['variant']}", "take": a["take"],
                "allowed": sorted(allowed), "level": "action", "designated_text": a["designated_text"],
                "designated": a["designated_all"] if started else [], "designated_all": a["designated_all"],
                "scenes": scenes_of(a["designated_text"]) if started and a["designated_all"] else [],
                "plan": a["plan"], "states": [], "segment": a["segment_id"], "truth_tag": a["truth_tag"],
                "eff_class": a["eff_class"], "contradictory": a["contradictory"], "onset": a["onset"],
                "v0_row": a["v0_row"], "rules": a["rules"], "base_class": a["base_class"], "truth_secs": a["truth_secs"],
                "e3_row": a["e3_row"],
                "t_start": None if seg is None else seg["t_start"], "made_by": None, "match": "segment_id",
                "multiple": False}


# ---------------------------------------------------------------------------------------------------- helpers


def percentile(values: list[float], q: float) -> float | None:
    """Linear interpolation between order statistics (Hyndman & Fan 1996 type 7, NumPy's default)."""
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": statistics.fmean(values), "min": min(values), "max": max(values),
            "p50": percentile(values, 0.5), "p95": percentile(values, 0.95)}


def brier(pairs) -> float | None:
    return statistics.fmean((p - y) ** 2 for p, y in pairs) if pairs else None


def auroc(pairs) -> float | None:
    """P(p of a positive > p of a negative) + 0.5 P(tie) (Mann-Whitney); None without both classes."""
    pos = [p for p, y in pairs if y]
    neg = [p for p, y in pairs if not y]
    if not pos or not neg:
        return None
    ranked = sorted(pairs, key=lambda x: x[0])
    ranks, i = {}, 0
    rank_sum = 0.0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        rank_sum += sum(avg for k in range(i, j + 1) if ranked[k][1])
        i = j + 1
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def reliability(pairs: list[tuple[float, int]], bins: int) -> dict:
    """Brier, ECE = sum_b (n_b / N) |observed_b - mean_p_b| over equal-width bins, AUROC, and the table."""
    if not pairs:
        return {"n": 0}
    table = []
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        inside = [(p, y) for p, y in pairs if (lo <= p < hi) or (b == bins - 1 and p == 1.0)]
        row = {"bin": [round(lo, 4), round(hi, 4)], "n": len(inside), "positives": sum(y for _, y in inside),
               "mean_p": statistics.fmean(p for p, _ in inside) if inside else None,
               "observed": statistics.fmean(y for _, y in inside) if inside else None}
        if inside:
            ece += len(inside) / len(pairs) * abs(row["observed"] - row["mean_p"])
        table.append(row)
    return {"n": len(pairs), "positives": sum(y for _, y in pairs), "brier": brier(pairs), "ece": ece, "bins": bins,
            "auroc": auroc(pairs), "table": table}


def wilson(k: int, n: int, z: float = 1.959964) -> list | None:
    """95% Wilson score interval."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def clip_boot(items: list[tuple[str, int]]) -> list | None:
    """95% percentile interval of sum(k) / sum(n) over clips resampled with replacement (9,999, seed 20261104)."""
    if not items:
        return None
    per = defaultdict(lambda: [0, 0])
    for clip, hit in items:
        per[clip][0] += hit
        per[clip][1] += 1
    clips = list(per.values())
    rng = random.Random(BOOT_SEED)
    vals = []
    for _ in range(BOOT_RESAMPLES):
        k = n = 0
        for _ in clips:
            a = clips[rng.randrange(len(clips))]
            k += a[0]
            n += a[1]
        if n:
            vals.append(k / n)
    return [percentile(vals, 0.025), percentile(vals, 0.975)] if vals else None


def kn(k: int, n: int, ci=None) -> dict:
    out = {"k": k, "n": n}
    if ci is not None:
        out["ci95"] = ci
    return out


def kn_boot(items: list[tuple[str, int]]) -> dict:
    return kn(sum(h for _, h in items), len(items), clip_boot(items))


def kn_wilson(k: int, n: int) -> dict:
    return kn(k, n, wilson(k, n))


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def fleiss_kappa(table: list[Counter], raters: int) -> float | None:
    """Fleiss' kappa over subjects (requests) x categories (choices), each subject rated `raters` times."""
    if not table or raters < 2:
        return None
    cats = sorted({c for row in table for c in row})
    N = len(table)
    P_i = [(sum(v * v for v in row.values()) - raters) / (raters * (raters - 1)) for row in table]
    p_j = [sum(row.get(c, 0) for row in table) / (N * raters) for c in cats]
    P_bar, P_e = statistics.fmean(P_i), sum(p * p for p in p_j)
    return None if P_e == 1 else (P_bar - P_e) / (1 - P_e)


# ---------------------------------------------------------------------------------------------------- label logic


def token_of(support: str | None, level: str) -> str:
    s = support or "none"
    return ACTION_OF.get(s, s) if level == "action" else s


def allowed_hit(support: str | None, label: dict) -> bool:
    """Admissible mode (E3): a window without a new support is admissible; a new one when its form is allowed.
    Time mode: the support (or its action) is in the allowed set; nothing shown = wait."""
    if label.get("mode") == "admissible" and (support in (None, "none")):
        return True
    tok = token_of(support, label["level"])
    allowed = set(label["allowed"])
    return tok in allowed or (label["level"] == "action" and tok == "wait" and "none" in allowed)


def visible(support: str | None) -> bool:
    return ACTION_OF.get(support or "none", "wait") in VISIBLE


def proxy_states(label: dict | None) -> set | None:
    """The states a label stands for: its own state column, else STATE_PROXY by scene; None = no mapping."""
    if not label:
        return None
    if label.get("states"):
        return set(label["states"])
    found = set()
    for sc in label.get("scenes") or []:
        found |= STATE_PROXY.get(sc, set())
    if found:
        return found
    if label.get("plan") in NORMAL_PLANS and not label.get("contradictory"):
        return {"normal"}
    return None


def as_forecast_classes(states: set) -> set:
    return {"none" if s == "normal" else s for s in states}


def seg_class(label: dict) -> str:
    if label.get("eff_class"):
        return label["eff_class"]
    acts = {ACTION_OF.get(a, a) if label["level"] == "support" else a for a in label["allowed"]}
    if acts <= {"wait", "none"}:
        return "wait_only"
    return "designated" if label.get("designated_text") and acts & VISIBLE else "other"


def obs_tag(rule: dict) -> str:
    name = rule.get("situation_used")
    return name if name in TAGS else "none"


def a_selection(rule: dict) -> str:
    r = rule["rule"]
    return r["support"] if r["transition"] in ("open", "replace") else "none"


def stage_of(line: dict | None, name: str) -> dict | None:
    for s in (line or {}).get("stages", []):
        if s["stage"] == name:
            return s
    return None


def c_selection(line: dict | None, order_agreed: bool = False) -> tuple[str, str | None, float | None]:
    """(status, selection, probability of the selection): answered | failed | skipped | not asked | order_disagree.
    order_agreed: the choice counts only when the reversed-order call answered the same."""
    if line is None or not line.get("asked"):
        return ("not asked", None, None)
    s = stage_of(line, "support_choice")
    if s is None or s["outcome"] == "skipped":
        return ("skipped", None, None)
    if s["outcome"] != "answered":
        return ("failed", None, None)
    ans = s["answers"]["support_choice"]
    if order_agreed:
        sw = s.get("order_swap") or {}
        if sw.get("outcome") != "answered":
            return ("order_unanswered", None, None)
        if sw["answers"]["support_choice"]["choice"] != ans["choice"]:
            return ("order_disagree", None, None)
    return ("answered", ans["choice"], ans["probabilities"].get(ans["choice"]))


ALL_OPTIONS = list(RULE_SUPPORTS) + ["none"]    # arm J (Jev alone): every support of the rule table + none


_QUESTIONS: dict = {}


def sent_options(line: dict | None) -> list[str] | None:
    """The options (criteria keys) of the support_choice question this call actually sent; None when not sent."""
    s = stage_of(line, "support_choice")
    if not s or s["outcome"] == "skipped" or not s.get("questions_hash"):
        return None
    q = _QUESTIONS.get(s["questions_hash"]) or {}
    return list(q["support_choice"]["criteria"]) if "support_choice" in q else None


def options_of(rule: dict, alone: bool = False) -> list[str]:
    """The options of the window: J all supports + none; otherwise the rule-filtered question actually sent at the
    window (Codex 209 #7: PR 0114ed1 leaves a candidate without a WHAT line, wait_hold_timer, out of the question),
    else the allowed candidates + none (no rule-filtered support_choice arm in the run)."""
    if alone:
        return list(ALL_OPTIONS)
    if rule.get("q_options") is not None:
        return list(rule["q_options"])
    return list(rule["allowed_candidates"]) + ["none"]


def has_options(rule: dict) -> bool:
    """A real choice: at least one support besides none among the window's options."""
    return len(options_of(rule)) >= 2


def singleton_none(rule: dict) -> bool:
    """Allowed candidates exist, but the question sent offers none alone (wait-only candidates, Codex 209 #7)."""
    return bool(rule["allowed_candidates"]) and not has_options(rule)


def cand_of(rule: dict) -> str | None:
    """The first support offered at the window (the sent question's, else the first allowed candidate)."""
    return next((o for o in options_of(rule) if o != "none"), None)


def window_truth(label: dict, t: float, window_s: float | None) -> str | None:
    """E3 run_eval.py window_truth (Codex 209 #4): the segment's truth tag holds in the window ending at t only when a
    GT behaviour second s lies in (t - window_s, t]; otherwise none. Labels without truth seconds keep the segment's
    tag."""
    if label.get("truth_secs") is None or window_s is None:
        return label.get("truth_tag")
    if label.get("truth_tag") in TAGS and any(t - window_s < x <= t + 1e-6 for x in label["truth_secs"]):
        return label["truth_tag"]
    return "none"


_WINDOW_S: dict = {}


def window_s_of(rule: dict, settings: dict) -> float | None:
    """The situation window length of the E3 bundle the window's tags came from (bundles/<bundle>.json); for a replay
    file windows_<b>.jsonl the shared value of the bundles <b>_*.json. None when no bundle is known."""
    b = rule.get("bundle") or (settings.get("aligned") or {}).get("bundle")
    if not b:
        argv = settings.get("command") or []
        name = argv[argv.index("--windows-name") + 1] if "--windows-name" in argv else ""
        m = re.match(r"windows_(b\d+)\.jsonl$", name)
        b = m.group(1) if m else None
    if not b:
        return None
    if b not in _WINDOW_S:
        one = INPUTS / "bundles" / f"{b}.json"
        files = [one] if one.is_file() else sorted((INPUTS / "bundles").glob(f"{b}_*.json"))
        vals = {json.loads(f.read_text(encoding="utf-8"))["situation"]["window_s"]["value"] for f in files}
        _WINDOW_S[b] = vals.pop() if len(vals) == 1 else None
    return _WINDOW_S[b]


# ---------------------------------------------------------------------------------------------------- compute


def compute(run: Path, labels, bins: int, perms: int, seed: int, skip: set | None = None) -> dict:
    rules = read_jsonl(run / "rule_windows.jsonl")
    states_map = {x["state_hash"]: x["state"] for x in read_jsonl(run / "states.jsonl")}
    global _QUESTIONS
    qfile = run / "questions.json"
    _QUESTIONS = json.loads(qfile.read_text(encoding="utf-8")) if qfile.is_file() else {}
    if skip:                                   # windows whose inputs changed since the run (rescoring only)
        rules = [r for r in rules if (r["take"], r["i"]) not in skip]
    calls = read_jsonl(run / "jev_calls.jsonl")
    repeats = read_jsonl(run / "repeats.jsonl")
    settings = json.loads((run / "run_settings.json").read_text(encoding="utf-8"))
    arms_cfg = settings["arms"]
    for r in rules:
        r["session"] = f"{r['take']}#{r['session_k']}"
        r.setdefault("clip", r["take"])
        if labels is not None:
            r["label"] = labels.match_record(r)
    by_arm = defaultdict(list)
    for c in calls:
        by_arm[c["arm"]].append(c)
    index = {(c["arm"], c["take"], c["i"]): c for c in calls}
    filtered = [c["arm"] for c in arms_cfg if "support_choice" in c["JEV_STAGES"] and c["condition"] != "J"]
    for r in rules:
        r["q_options"] = next((o for o in (sent_options(index.get((a, r["take"], r["i"]))) for a in filtered)
                               if o is not None), None)
        if r.get("label"):
            r["label"]["truth_window"] = window_truth(r["label"], r["t"], window_s_of(r, settings))
    swaps = [st for c in calls for st in c["stages"] if st.get("order_swap")]
    swap_valid = not swaps or settings.get("order_swap_cache") == "ordered-key"
    out_swap = {"valid": swap_valid, "reversed_requests": len(swaps),
                "reversed_from_cache": sum(1 for st in swaps if st["order_swap"].get("cached")),
                "note": None if swap_valid else (
                    "invalid: the run's cache identity sorted dict keys, so a reversed criteria order (and a reversed "
                    "singleton candidate list) was the same request; reversed-order answers came from the cache "
                    "(Codex 205 #1). Order consistency and the order-agreed figures of this run are not evidence.")}
    out: dict = {"run": str(run), "jev": settings.get("jev"), "model": settings.get("model"), "order_swap": out_swap,
                 "jev_numbers": "none: stub run, execution behaviour only" if settings.get("jev") == "stub" else "real",
                 "labels": None if labels is None else labels.path, "label_mode": None if labels is None else labels.mode,
                 "label_status": None if labels is None else labels.status, "aligned": settings.get("aligned"),
                 "scoring_version": SCORING_VERSION}

    # ---- rule (A)
    expect = [(r["take"], r["i"], r["expect"], {"transition": r["rule"]["transition"], "support": r["rule"]["support"]})
              for r in rules if r.get("expect")]
    out["rule"] = {
        "windows": len(rules), "takes": len({r["take"] for r in rules}), "clips": len({r["clip"] for r in rules}),
        "sessions": len({r["session"] for r in rules}), "measurable": sum(r["measurable"] for r in rules),
        "situation_record": dict(Counter(str(r["situation_record"]) for r in rules)),
        "transitions": dict(Counter(r["rule"]["transition"] for r in rules)),
        "opened": dict(Counter(r["rule"]["support"] for r in rules if r["rule"]["transition"] in ("open", "replace"))),
        "rule_question_kinds": dict(Counter(r["rule"]["jev_kind"] for r in rules if r["rule"]["rule_question"])),
        "rule_question_windows": sum(1 for r in rules if r["rule"]["rule_question"]),
        "expired_by_tick": sum(1 for r in rules if r["expired_by_tick"]),
        "candidate_set_sizes": dict(sorted(Counter(len(r["allowed_candidates"]) for r in rules).items())),
        "vision_record_match": dict(Counter(str(r["vision_record_match"]) for r in rules)),
        "touch_features": dict(Counter(r["sources"].get("touch_features") for r in rules)),
        "recent_source": dict(Counter(re.sub(r"\(\d+ windows\)", "(n windows)", r["sources"].get("recent", ""))
                                      for r in rules)),
        "expect": {"checked": len(expect), "failed": [list(e) for e in expect
                                                      if any(e[2].get(k) != e[3].get(k) for k in e[2])]},
    }

    # ---- execution
    execution = {}
    measurable = sum(r["measurable"] for r in rules)
    for cfg in arms_cfg:
        lines = by_arm.get(cfg["arm"], [])
        a = {"condition": cfg["condition"], "variant": cfg["variant"], "JEV_STAGES": cfg["JEV_STAGES"],
             "windows": len(rules), "eligible": measurable}
        if cfg["condition"] == "A":
            execution[cfg["arm"]] = a
            continue
        attempted = sum(c["asked"] for c in lines)
        a.update(attempted=attempted, skipped=dict(Counter(c["skip_reason"] for c in lines if c["skip_reason"])),
                 would_skip_in_flight=sum(c["would_skip_in_flight"] for c in lines))
        stages = defaultdict(list)
        for c in lines:
            for s in c["stages"]:
                stages[s["stage"]].append(s)
        st = {}
        api_total = cached_total = 0
        for name, items in stages.items():
            done = [s for s in items if s["outcome"] != "skipped"]
            ok = [s for s in done if s["outcome"] == "answered"]
            live = [s for s in done if not s.get("cached")]
            swaps = [s["order_swap"] for s in done if s.get("order_swap")]
            live_sw = [x for x in swaps if not x.get("cached")]
            uin = [s["usage"]["input_tokens"] for s in ok if s.get("usage") and not s.get("cached")]
            uout = [s["usage"]["output_tokens"] for s in ok if s.get("usage") and not s.get("cached")]
            api_total += len(live) + len(live_sw)
            cached_total += len(done) - len(live) + len(swaps) - len(live_sw)
            st[name] = {"eligible": len(items), "skipped_build_none": len(items) - len(done), "attempted": len(done),
                        "answered": len(ok), "failed": dict(Counter(s.get("failure") for s in done
                                                                    if s["outcome"] != "answered")),
                        "api_calls": len(live), "answers_from_cache": len(done) - len(live),
                        "order_swap_calls": len(live_sw), "order_swap_answered": sum(x["outcome"] == "answered"
                                                                                     for x in swaps),
                        "latency_ms_api": summary([s["latency_ms"] for s in live if s["outcome"] == "answered"]),
                        "latency_ms_api_all": summary([s["latency_ms"] for s in live]),
                        "request_bytes": summary([s["request_bytes"] for s in done]),
                        "input_tokens": {"sum": sum(uin), **summary(uin)},
                        "output_tokens": {"sum": sum(uout), **summary(uout)},
                        "response_models": dict(Counter(s["response_model"] for s in ok))}
        a["stages"] = st
        a["api_calls"], a["answers_from_cache"] = api_total, cached_total
        a["calls_per_attempted_window"] = api_total / attempted if attempted else None
        if "support_choice" in stages:
            reach = sum(1 for s in stages["support_choice"] if s["outcome"] != "skipped")
            a["escalation"] = kn(reach, measurable)
        a["chain_latency_ms"] = summary([sum(s["latency_ms"] for s in c["stages"]
                                             if s["outcome"] != "skipped" and not s.get("cached"))
                                         for c in lines if c["asked"] and all(not s.get("cached") for s in c["stages"]
                                                                               if s["outcome"] != "skipped")])
        execution[cfg["arm"]] = a
    out["execution"] = execution
    out["latency_method"] = ("wall clock (time.perf_counter) around the client call of each API request; answers from "
                             "the identical-request cache are excluded; machine and network of the run")

    # ---- answers (descriptive)
    answers = {}
    for cfg in arms_cfg:
        per = defaultdict(lambda: {"noul": defaultdict(list), "choice": defaultdict(Counter), "conf": defaultdict(list)})
        for c in by_arm.get(cfg["arm"], []):
            for s in c["stages"]:
                if s["outcome"] != "answered":
                    continue
                for q, ans in s["answers"].items():
                    if ans["type"] == "noul":
                        per[s["stage"]]["noul"][q].append(ans["p"])
                    else:
                        per[s["stage"]]["choice"][q][ans["choice"]] += 1
                        per[s["stage"]]["conf"][q].append(ans["confidence"])
        if per:
            answers[cfg["arm"]] = {st: {"noul": {q: summary(v) for q, v in sorted(d["noul"].items())},
                                        "choice": {q: {"counts": dict(v), "confidence": summary(d["conf"][q])}
                                                   for q, v in sorted(d["choice"].items())}}
                                   for st, d in per.items()}
    out["answers"] = answers

    # ---- paired controls
    def answered(c, stage):
        s = stage_of(c, stage)
        return s if s and s["outcome"] == "answered" else None

    def pair(arm_x, arm_ref, stages=None):
        res = {}
        names = stages or sorted({s["stage"] for c in by_arm.get(arm_x, []) for s in c["stages"]})
        for stage in names:
            diffs, top, top_n, ch, ch_n, same_req, n = defaultdict(list), 0, 0, Counter(), Counter(), 0, 0
            for c in by_arm.get(arm_x, []):
                sv, sb = answered(c, stage), answered(index.get((arm_ref, c["take"], c["i"])), stage)
                if sv is None or sb is None:
                    continue
                n += 1
                same_req += sv["state_hash"] == sb["state_hash"] and sv["questions_hash"] == sb["questions_hash"]
                for q, av in sv["answers"].items():
                    ab = sb["answers"].get(q)
                    if ab is None:
                        continue
                    if av["type"] == "noul" and ab["type"] == "noul":
                        diffs[q].append(av["p"] - ab["p"])
                    elif av.get("choice") is not None and ab.get("choice") is not None:
                        ch_n[q] += 1
                        ch[q] += av["choice"] != ab["choice"]
                if all(q in sv["answers"] and q in sb["answers"] for q in STATE_NAMES):
                    top_n += 1
                    top += max(STATE_NAMES, key=lambda q: sv["answers"][q]["p"]) != max(
                        STATE_NAMES, key=lambda q: sb["answers"][q]["p"])
            res[stage] = {"windows": n, "identical_requests": same_req,
                          "noul": {q: {"n": len(d), "mean_diff": statistics.fmean(d),
                                       "mean_abs_diff": statistics.fmean(map(abs, d)), "max_abs_diff": max(map(abs, d))}
                                   for q, d in sorted(diffs.items()) if d},
                          "largest_state_changed": kn(top, top_n),
                          "choice_changed": {q: kn(ch[q], ch_n[q]) for q in sorted(ch_n)}}
        return res

    paired = {}
    specs = {c["arm"]: c for c in arms_cfg}
    for cfg in arms_cfg:
        if cfg["variant"] != "base" and cfg["condition"] != "A":
            base = next((x["arm"] for x in arms_cfg if x["condition"] == cfg["condition"] and x["variant"] == "base"), None)
            if base:
                paired[f"{cfg['arm']} vs {base}"] = pair(cfg["arm"], base)
    if "C0" in specs and "C" in specs:
        paired["C0 vs C"] = pair("C0", "C", ["support_choice"])
    base_arms = [x["arm"] for x in arms_cfg if x["variant"] == "base" and "state_scores" in x["JEV_STAGES"]]
    for x in base_arms[1:]:
        paired[f"{x} vs {base_arms[0]} (state_scores)"] = pair(x, base_arms[0], ["state_scores"])
    out["paired"] = paired

    # ---- repeated fixed inputs
    rep = defaultdict(lambda: {"requests": 0, "all_answered": 0, "range": defaultdict(list), "sd": defaultdict(list),
                               "tables": defaultdict(list), "agree": defaultdict(list)})
    raters = settings.get("repeats") or 1
    for r in repeats:
        runs = [r["first"]] + r["again"]
        d = rep[(r["arm"], r["stage"])]
        d["requests"] += 1
        if not all(x["outcome"] == "answered" for x in runs):
            continue
        d["all_answered"] += 1
        for q, a0 in r["first"]["answers"].items():
            vals = [x["answers"].get(q) for x in runs]
            if a0["type"] == "noul":
                ps = [v["p"] for v in vals]
                d["range"][q].append(max(ps) - min(ps))
                d["sd"][q].append(statistics.pstdev(ps))
            else:
                cnt = Counter(v["choice"] for v in vals)
                d["tables"][q].append(cnt)
                d["agree"][q].append((sum(v * v for v in cnt.values()) - len(vals)) / (len(vals) * (len(vals) - 1)))
                pmax = [v["probabilities"].get(a0["choice"], 0.0) for v in vals]
                d["range"][q].append(max(pmax) - min(pmax))
    out["repeats"] = {"calls_per_request": raters, "by_arm_stage": {
        f"{arm} / {st}": {
            "requests": d["requests"], "all_answered": d["all_answered"],
            "probability_range": {q: summary(v) for q, v in d["range"].items()},
            "probability_sd": {q: summary(v) for q, v in d["sd"].items()},
            "choice": {q: {"one_choice": kn_wilson(sum(len(c) == 1 for c in t), len(t)),
                           "flip_share": (sum(len(c) > 1 for c in t) / len(t)) if t else None,
                           "fleiss_kappa": fleiss_kappa(t, raters),
                           "pairwise_agreement": summary(d["agree"][q])} for q, t in d["tables"].items()}}
        for (arm, st), d in rep.items()}}

    # ---- labels
    labelled = [r for r in rules if r.get("label")]
    if labelled:
        sessions = defaultdict(list)
        for r in labelled:
            sessions[r["session"]].append(r)
        out["label_windows"] = {
            "labelled": len(labelled), "unlabelled": len(rules) - len(labelled),
            "levels": dict(Counter(r["label"]["level"] for r in labelled)),
            "match": dict(Counter(r["label"].get("match") for r in labelled)),
            "segment_classes": dict(Counter(seg_class(r["label"]) for r in labelled)),
            "sessions": len(sessions),
            "sessions_with_more_than_one_label_row": sum(1 for v in sessions.values()
                                                         if len({x["label"]["row"] for x in v}) > 1),
            "state_proxy_defined": sum(1 for r in labelled if proxy_states(r["label"]) is not None),
            "state_proxy_by_states": dict(Counter(",".join(sorted(proxy_states(r["label"]))) for r in labelled
                                                  if proxy_states(r["label"]) is not None)),
            "tag_vs_truth": dict(Counter(f"{obs_tag(r)} | {r['label'].get('truth_window')}" for r in labelled)),
            "truth_basis": ("window truth: the segment's truth tag when a GT behaviour second lies in (t - window_s, t], "
                            "else none (E3 run_eval.py window_truth)") if any(r["label"].get("truth_secs") is not None
                                                                           for r in labelled) else "segment truth_tag",
            "singleton_none_windows": sum(1 for r in labelled if singleton_none(r)),
        }
        out["coverage"] = coverage(labelled)
        scored = [r for r in labelled if seg_class(r["label"]) not in NOT_EVALUABLE]
        out["scored_population"] = {"windows": len(scored), "excluded_windows": len(labelled) - len(scored),
                                    "rule": "labelled windows outside excluded and contradictory segments; the same set for selection, "
                                            "state estimation, rule question, forecast and the null controls"}
        global _STATES
        _STATES = states_map
        out["selection"] = selection(scored, rules, arms_cfg, index, bins)
        out["baselines"] = baselines(scored, index, arms_cfg, states_map)
        out["state_estimation"] = state_estimation(scored, arms_cfg, index, bins)
        out["rule_question"] = rule_question(scored, arms_cfg, index, bins)
        excluded_keys = {(r["take"], r["i"]) for r in labelled if seg_class(r["label"]) in NOT_EVALUABLE}
        out["forecast"] = forecast([r for r in rules if (r["take"], r["i"]) not in excluded_keys], arms_cfg, index)
        out["null"] = null_checks(scored, arms_cfg, index, perms, seed)
    return out


def coverage(labelled: list[dict]) -> dict:
    """How often the reference is out of reach of the options (allowed candidates + none)."""
    def absent(r):
        return not any(allowed_hit(o, r["label"]) for o in options_of(r))
    with_c = [r for r in labelled if has_options(r)]
    desig = [r for r in labelled if r["label"]["designated"]]
    named_other = [r for r in labelled if r["label"]["designated_text"] and not r["label"]["designated_all"]]
    return {
        "allowed_action_absent": {"all": kn(sum(map(absent, labelled)), len(labelled)),
                                  "with_candidates": kn(sum(map(absent, with_c)), len(with_c))},
        "designated_support_absent": kn(sum(1 for r in desig if not set(r["label"]["designated"])
                                            & set(options_of(r))), len(desig)),
        "designated_outside_rule_table": kn(len(named_other), len(labelled)),
        "designated_outside_examples": sorted({r["label"]["designated_text"] for r in named_other})[:5],
    }


def chance_allowed(rows: list[dict], alone: bool = False) -> float | None:
    """Expected agreement of a uniform choice over the options: mean_w (#options admissible in w) / |options_w|."""
    if not rows:
        return None
    return statistics.fmean(sum(allowed_hit(o, r["label"]) for o in options_of(r, alone)) / len(options_of(r, alone))
                            for r in rows)


def chance_designated(rows: list[dict], alone: bool = False) -> float | None:
    """mean_w 1 / |options_w| over windows whose designated support is among the options (0 otherwise)."""
    rows = [r for r in rows if r["label"]["designated"]]
    if not rows:
        return None
    return statistics.fmean((1 / len(options_of(r, alone))) if set(r["label"]["designated"]) & set(options_of(r, alone))
                            else 0.0
                            for r in rows)


HELP_RULE = ("admissible help after onset (E3 tools/help_rule.py, imported, one implementation for E3 / E5; main "
             "2026-11-05 from labels red team round 3 #1): a display = a visible support opened inside the segment (not "
             "at the window ending at the turn start) and kept by the following windows; help = a display shown at "
             "some time at or after the onset whose form is admissible then; designated delivery = the same for the "
             "designated supports themselves; latency = max(0, open - onset)")
OLD_HELP_RULE = "before 2026-11-05: a new visible admissible offer at or after the onset (a support held at the onset not credited)"
_HR = None


def help_rule():
    """E3's help_rule module, shipped byte for byte in tools/e3/help_rule.py (E3: 4_vision/eval_ab_2026-11-04/tools/).
    It imports E3's harness; tools/e3/harness.py holds the four names it reads (no numpy). The turn starts come from
    harness.LABELS, set to the scoring's judgment labels by main()."""
    global _HR
    if _HR is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "e3"))
        import help_rule as hr   # noqa: E402
        _HR = hr
    return _HR


def policy_records(rs: list[dict], select) -> list[dict]:
    """A policy's windows of one segment as E3 window records (t, transition, support, action, segment_id) for
    help_rule: the policy's own new selection is an open; otherwise the rule-table trajectory's keep of a support
    (so a selection stays on screen while the rule table keeps that same support; Jev's choices do not update the
    state, so one the rule table does not hold lasts one window); else nothing."""
    out = []
    for r in rs:
        x = select(r)
        seg = r["label"].get("segment")
        if x not in (None, "none"):
            out.append({"t": r["t"], "transition": "open", "support": x, "action": ACTION_OF.get(x, "wait"),
                        "segment_id": seg})
        elif r["rule"]["transition"] == "keep":
            sp = r["rule"]["support"]
            out.append({"t": r["t"], "transition": "keep", "support": sp, "action": ACTION_OF.get(sp or "none", "wait"),
                        "segment_id": seg})
        else:
            out.append({"t": r["t"], "transition": "none", "support": None, "action": None, "segment_id": seg})
    return out


def segment_outcomes(labelled: list[dict], select) -> dict:
    """Per label segment (take x label row), the 2x2 of the survey guide P1 #2 / 평가 설계 v1.4 §2-2 (labels v3 rule:
    only designations that rule table v0 has a row for enter the 2x2; the others are scored apart by designated
    delivery; an admissible visible form there is not help). Help: HELP_RULE (help_rule.help_after_onset on the
    segment's admissible row). TP = designated (v0 row) segment with help; FN = without; FP = wait-only segment with
    a new visible selection; TN = wait-only without (unchanged). False-alarm rate FP / (FP + TN), missed-help rate
    FN / (TP + FN), offer precision TP / (TP + FP); designated delivery = help by the designated supports themselves;
    split by origin (help_rule.help_source); the old rule's TP / FN / delivery once beside them; other classes apart."""
    HR = help_rule()
    segs = defaultdict(list)
    for r in labelled:                      # a segment = take x label row (E3 keys by segment_id per condition)
        segs[(r["take"], r["label"]["row"])].append(r)
    tp = fn = fp = tn = n_v0 = deliv = n_norow = cov_norow = vis_norow = 0
    old_tp = old_deliv = 0
    held, lat = [], []
    by_origin = defaultdict(Counter)
    other = Counter()
    for rs in segs.values():
        lab = rs[0]["label"]
        cls = seg_class(lab)
        rs = sorted(rs, key=lambda x: x["i"])
        sels = [(r, select(r)) for r in rs]
        vis = [(r, x) for r, x in sels if visible(x)]
        if cls == "wait_only":
            fp += bool(vis)
            tn += not vis
        elif cls == "designated":
            a = lab["e3_row"]
            onset = a.get("onset")
            recs = policy_records(rs, select)
            ds = HR.displays(recs)
            des = HR.designated_names(a)
            h = HR.help_after_onset(recs, a, ds=ds)
            hd = HR.help_after_onset(recs, a, supports=des, ds=ds)
            v0 = "true" in str(lab.get("v0_row") or "").split(";") if lab.get("v0_row") is not None \
                else bool(lab.get("designated_all"))
            if v0:
                n_v0 += 1
                tp += h is not None
                fn += h is None
                deliv += hd is not None
                if h is not None and h["latency_s"] is not None:
                    lat.append(h["latency_s"])
                if h is not None and h["opened_before_onset"]:
                    held.append(h["lead_s"])
                o = by_origin[HR.help_source(a)]
                o["n"] += 1
                o["TP"] += h is not None
                o["delivery"] += hd is not None
                old_tp += HR.old_rule_t(recs, a) is not None
                old_deliv += any(x in des and (onset is None or r["t"] >= onset - 1e-9) for r, x in sels)
            else:                           # no rule-table row: outside the 2x2; help only by the designated support
                n_norow += 1                # itself (Codex 209 #1; E3 JUDGMENT_PROTOCOL.md:95, run_eval.py missed_norow)
                cov_norow += hd is not None
                vis_norow += h is not None
        else:
            other[cls] += 1
    return {"help_rule": HELP_RULE, "help_rule_name": HR.RULE_NAME,
            "false_alarm": kn_wilson(fp, fp + tn), "missed_help": kn_wilson(fn, tp + fn),
            "missed_help_v0_row": kn_wilson(fn, n_v0), "offer_precision": kn_wilson(tp, tp + fp),
            "designated_delivery_v0_row": kn_wilson(deliv, n_v0),
            "designated_delivery_no_row": kn_wilson(cov_norow, n_norow),
            "admissible_visible_no_row": kn(vis_norow, n_norow),
            "help_opened_before_onset": {"segments": len(held), "lead_s": sorted(held)},
            "latency_s": {"n": len(lat), "median": statistics.median(lat) if lat else None},
            "by_origin": {k: {"designated_v0_row": v["n"], "TP": v["TP"], "FN": v["n"] - v["TP"],
                              "designated_delivery": kn(v["delivery"], v["n"])} for k, v in sorted(by_origin.items())},
            "old_definition": {"rule": OLD_HELP_RULE, "TP": old_tp, "FN": n_v0 - old_tp,
                               "designated_delivery_v0_row": kn(old_deliv, n_v0)},
            "TP": tp, "FN": fn, "FP": fp, "TN": tn, "other_segments": dict(other)}


_STATES: dict = {}
ATTRIBUTION = ("with_incorrect_observed_tag", "with_correct_observed_tag", "observed_tag_unknown", "reference_missing")


def attribution(rows: list[dict], select) -> dict:
    """Descriptive split of the windows whose selection is not admissible (no causal claim): decision errors with
    an incorrect observed tag (the window's tag differs from the ground-truth tag), with a correct observed tag;
    apart: the window's tag unknown, the ground-truth tag missing or ambiguous."""
    wrong = [r for r in rows if not allowed_hit(select(r), r["label"])]
    res = Counter()
    for r in wrong:
        gt = r["label"].get("truth_window", r["label"].get("truth_tag"))
        if gt in (None, "", "ambiguous"):
            res["reference_missing"] += 1
        elif r.get("situation_used") in (None, "", "unknown"):
            res["observed_tag_unknown"] += 1
        else:
            res["with_incorrect_observed_tag" if obs_tag(r) != gt else "with_correct_observed_tag"] += 1
    return {"decision_errors": len(wrong), "of_windows": len(rows), **{k: res.get(k, 0) for k in ATTRIBUTION}}


def withdrawn_of(r: dict, index: dict, arms_cfg: list, states: dict) -> list | None:
    """The supports withdrawn earlier in the session at this window: rule_windows' withdrawn_before, else the
    session.withdrawn of any support_choice request of the window (runs made before the field existed)."""
    if "withdrawn_before" in r:
        return r["withdrawn_before"]
    for cfg in arms_cfg:
        st = stage_of(index.get((cfg["arm"], r["take"], r["i"])), "support_choice")
        if st and st.get("state_hash") in states:
            ses = (states[st["state_hash"]] or {}).get("session") or {}
            if "withdrawn" in ses:
                return list(ses["withdrawn"])
    return None


def baselines(scored: list[dict], index: dict, arms_cfg: list, states: dict) -> dict:
    """Offline selection baselines on the windows with candidates (0 calls; red team E5 stage 1 #2-#3):
    always none, always the first candidate, decline-if-withdrawn (none when the candidate was withdrawn earlier in
    the session, else the candidate)."""
    rows = [r for r in scored if has_options(r)]
    out = {"windows": len(rows), "population": "windows whose sent question offers a support besides none"}

    def score(select):
        return kn_boot([(r["clip"], int(allowed_hit(select(r), r["label"]))) for r in rows])
    out["always_none"] = score(lambda r: "none")
    out["always_candidate"] = score(cand_of)

    def diw(r):
        wd = withdrawn_of(r, index, arms_cfg, states)
        return "none" if wd and cand_of(r) in wd else cand_of(r)
    out["decline_if_withdrawn"] = score(diw)
    out["withdrawn_known"] = sum(1 for r in rows if withdrawn_of(r, index, arms_cfg, states) is not None)
    out["segments_decline_if_withdrawn"] = segment_outcomes(scored, lambda r: diw(r) if has_options(r)
                                                            else a_selection(r))
    return out


def decline_profile(scored, arm, index, arms_cfg, states) -> dict:
    """For one support_choice arm on windows with candidates where it answered: the window 2x2 (declined /
    kept x admissible candidate or not), the random-decline expectation at the arm's own decline count, and the
    withdrawn-rule reproduction (declines exactly when the candidate is in session.withdrawn)."""
    rows = []
    for r in scored:
        if not has_options(r):
            continue
        st, sel, _ = c_selection(index.get((arm, r["take"], r["i"])))
        if st == "answered":
            rows.append((r, sel))
    if not rows:
        return {"windows": 0}
    cand_ok = [int(allowed_hit(cand_of(r), r["label"])) for r, _ in rows]
    none_ok = [int(allowed_hit("none", r["label"])) for r, _ in rows]
    declined = [sel in (None, "none") for _, sel in rows]
    d, n = sum(declined), len(rows)
    tab = Counter((("declined" if dc else "kept") + "_" + ("admissible_candidate" if ok else "inadmissible_candidate"))
                  for dc, ok in zip(declined, cand_ok))
    expected = sum((d / n) * no + ((n - d) / n) * co for no, co in zip(none_ok, cand_ok))
    actual = sum(no if dc else co for dc, no, co in zip(declined, none_ok, cand_ok))
    rep_k = rep_n = dec_w = n_w = dec_f = n_f = 0
    for (r, sel), dc in zip(rows, declined):
        wd = withdrawn_of(r, index, arms_cfg, states)
        if wd is None:
            continue
        inw = cand_of(r) in wd
        rep_n += 1
        rep_k += dc == inw
        if inw:
            n_w += 1
            dec_w += dc
        else:
            n_f += 1
            dec_f += dc
    return {"windows": n, "declines": d, "window_2x2": dict(tab), "admissible_actual": actual,
            "admissible_expected_random_decline": expected,
            "withdrawn_rule_reproduction": kn_wilson(rep_k, rep_n),
            "declined_when_withdrawn": kn(dec_w, n_w), "declined_when_fresh": kn(dec_f, n_f)}


def selection(labelled, rules, arms_cfg, index, bins: int) -> dict:
    """Window-level scores leave out segments the labels exclude (eff_class excluded, as E3 policy_row does)."""
    labelled = [r for r in labelled if seg_class(r["label"]) not in NOT_EVALUABLE]
    res = {"windows_scored": len(labelled)}
    with_c = [r for r in labelled if has_options(r)]
    single = [r for r in labelled if singleton_none(r)]
    res["singleton_none_windows"] = len(single)
    hit_a = lambda r: int(allowed_hit(a_selection(r), r["label"]))
    des_rows = [r for r in labelled if r["label"]["designated"]]
    res["A"] = {"allowed": {"all": kn_boot([(r["clip"], hit_a(r)) for r in labelled]),
                            "with_candidates": kn_boot([(r["clip"], hit_a(r)) for r in with_c])},
                "chance_allowed": {"all": chance_allowed(labelled), "with_candidates": chance_allowed(with_c)},
                "designated": kn_boot([(r["clip"], int(a_selection(r) in r["label"]["designated"])) for r in des_rows]),
                "chance_designated": chance_designated(labelled),
                "selected": dict(Counter(a_selection(r) for r in labelled)),
                "segments": segment_outcomes(labelled, a_selection),
                "attribution": attribution([r for r in labelled if seg_class(r["label"]) not in NOT_EVALUABLE],
                                           a_selection)}
    by_session = defaultdict(list)
    for r in rules:
        by_session[r["session"]].append(r)
    nxt = {}
    for rs in by_session.values():
        rs.sort(key=lambda x: x["i"])
        for x, y in zip(rs, rs[1:]):
            nxt[(x["take"], x["i"])] = y
    for cfg in arms_cfg:
        if "support_choice" not in cfg["JEV_STAGES"]:
            continue
        arm = cfg["arm"]
        alone = cfg["condition"] == "J"
        scope = labelled if alone else with_c          # J has options in every window
        out = {"options_windows": len(scope),
               "options": "all supports + none" if alone else "the sent question's options (a support besides none)"}
        if not alone:
            out["singleton_none"] = {"windows": len(single), "status_and_choice": dict(Counter(
                "/".join(str(x) for x in c_selection(index.get((arm, r["take"], r["i"])))[:2]) for r in single))}
        for mode, agreed in (("first_order", False), ("order_agreed", True)):
            status = Counter()
            ans_rows, items, items_a, fb, pairs, des = [], [], [], [], [], []
            for r in labelled:
                st, sel, p = c_selection(index.get((arm, r["take"], r["i"])), agreed)
                if alone or has_options(r):
                    status[st] += 1
                if st == "answered" and (alone or has_options(r)):
                    h = int(allowed_hit(sel, r["label"]))
                    ans_rows.append(r)
                    items.append((r["clip"], h))
                    items_a.append((r["clip"], hit_a(r)))
                    fb.append((r["clip"], h))
                    pairs.append((p, h))
                    if r["label"]["designated"]:
                        des.append((r["clip"], int(sel in r["label"]["designated"])))
                else:
                    fb.append((r["clip"], hit_a(r)))
            out[mode] = {"status_on_options_windows": dict(status), "allowed_answered": kn_boot(items),
                         "chance_on_answered": chance_allowed(ans_rows, alone), "a_on_same_windows": kn_boot(items_a),
                         "allowed_with_rule_fallback": kn_boot(fb), "designated_answered": kn_boot(des),
                         "chance_designated_on_answered": chance_designated(ans_rows, alone),
                         "calibration_p_selected": reliability(pairs, bins)}
        # order consistency
        both = agree = 0
        oc_items = []
        for r in (labelled if alone else with_c):
            s = stage_of(index.get((arm, r["take"], r["i"])), "support_choice")
            if s and s["outcome"] == "answered" and (s.get("order_swap") or {}).get("outcome") == "answered":
                both += 1
                same = int(s["answers"]["support_choice"]["choice"] == s["order_swap"]["answers"]["support_choice"]["choice"])
                agree += same
                oc_items.append((r["clip"], same))
        out["order_consistency"] = kn_boot(oc_items)
        # a uniform chooser asked in both orders agrees with probability 1 / K and gives an agreed admissible
        # choice with probability a / K^2 (K options, a of them admissible), on the same windows
        sw_rows = [r for r in (labelled if alone else with_c) if (stage_of(index.get((arm, r["take"], r["i"])), "support_choice") or {})
                   .get("outcome") == "answered" and ((stage_of(index.get((arm, r["take"], r["i"])), "support_choice")
                                                        or {}).get("order_swap") or {}).get("outcome") == "answered"]
        out["chance_order_protocol"] = None if not sw_rows else {
            "agree": statistics.fmean(1 / len(options_of(r, alone)) for r in sw_rows),
            "agreed_admissible": statistics.fmean(sum(allowed_hit(o, r["label"]) for o in options_of(r, alone))
                                                  / len(options_of(r, alone)) ** 2 for r in sw_rows)}
        if alone:   # without the rule filter: the reference is always among the options; how often J leaves the filter
            sel = [(r, c_selection(index.get((arm, r["take"], r["i"])))) for r in labelled]
            ans = [(r, x[1]) for r, x in sel if x[0] == "answered"]
            out["reference_absent"] = kn(sum(1 for r in labelled if not any(allowed_hit(o, r["label"])
                                                                            for o in ALL_OPTIONS)), len(labelled))
            out["out_of_filter_choice"] = kn_boot([(r["clip"], int(c not in options_of(r))) for r, c in ans])

        def c_as_run(r, arm=arm):
            st, sel, _ = c_selection(index.get((arm, r["take"], r["i"])))
            return sel if st == "answered" else ("none" if st == "skipped" else a_selection(r))
        out["segments_with_rule_fallback"] = segment_outcomes(labelled, c_as_run)
        if not alone:
            out["decline_profile"] = decline_profile(labelled, arm, index, arms_cfg, _STATES)
        out["attribution_with_rule_fallback"] = attribution(
            [r for r in labelled if seg_class(r["label"]) not in NOT_EVALUABLE], c_as_run)
        # next-window application: C's selection of window N shown at N+1, A delayed by one window, A at N+1
        nw = {"pairs": 0, "c": 0, "a_delayed": 0, "a_same": 0}
        k_all = n_all = 0
        for r in rules:
            y = nxt.get((r["take"], r["i"]))
            if y is None or not y.get("label") or seg_class(y["label"]) in NOT_EVALUABLE:
                continue
            n_all += 1
            k_all += allowed_hit(a_selection(r), y["label"])
            st, sel, _ = c_selection(index.get((arm, r["take"], r["i"])))
            if st != "answered":
                continue
            nw["pairs"] += 1
            nw["c"] += allowed_hit(sel, y["label"])
            nw["a_delayed"] += allowed_hit(a_selection(r), y["label"])
            nw["a_same"] += allowed_hit(a_selection(y), y["label"])
        nw["a_delayed_all"] = kn(k_all, n_all)
        out["next_window"] = nw
        res[arm] = out
    return res


RAW_FEATURES = {   # the window's own inputs, as single-feature scores on the same windows (red team E5 stage 1 #4)
    "misses_recent": lambda r: r["input"].get("misses_recent"),
    "backs_recent": lambda r: r["input"].get("backs_recent"),
    "fixes_recent": lambda r: r["input"].get("fixes_recent"),
    "condition_C2": lambda r: None if not r.get("condition") else int(r["condition"] == "C2"),
}


def state_estimation(labelled, arms_cfg, index, bins) -> dict:
    res = {}
    for cfg in arms_cfg:
        if "state_scores" not in cfg["JEV_STAGES"]:
            continue
        pairs = defaultdict(list)
        feats = defaultdict(list)
        for r in labelled:
            P = proxy_states(r["label"])
            if P is None:
                continue
            s = stage_of(index.get((cfg["arm"], r["take"], r["i"])), "state_scores")
            if not s or s["outcome"] != "answered":
                continue
            for q in STATE_NAMES:
                if q in s["answers"]:
                    pairs[q].append((s["answers"][q]["p"], int(q in P)))
                    feats[q].append(r)
        per = {}
        for q in STATE_NAMES:
            rel = reliability(pairs[q], bins)
            if rel.get("n"):
                prev = rel["positives"] / rel["n"]
                rel["brier_base_rate"] = prev * (1 - prev)
                rel["brier_skill"] = None if prev in (0, 1) else 1 - rel["brier"] / (prev * (1 - prev))
                ys = [y for _, y in pairs[q]]
                raw = {}
                for name, f in RAW_FEATURES.items():
                    keep = [k for k, r in enumerate(feats[q]) if f(r) is not None]
                    fx = [(float(f(feats[q][k])), ys[k]) for k in keep]
                    # paired (Codex 209 #3): Jev's AUROC on exactly the windows where the comparator has a value
                    raw[name] = {"n": len(fx), "auroc": auroc(fx), "positives": sum(y for _, y in fx),
                                 "jev_auroc_same_windows": auroc([pairs[q][k] for k in keep])}
                rel["raw_feature_auroc"] = raw
            per[q] = rel
        res[cfg["arm"]] = per
    return res


def rule_question(labelled, arms_cfg, index, bins) -> dict:
    """Secondary: the rule table's own fit question (y = the proposed support is admissible)."""
    res = {}
    for cfg in arms_cfg:
        if "state_scores" not in cfg["JEV_STAGES"]:
            continue
        fit = []
        for r in labelled:
            s = stage_of(index.get((cfg["arm"], r["take"], r["i"])), "state_scores")
            if s and s["outcome"] == "answered" and "proposal_fits" in s["answers"]:
                fit.append((s["answers"]["proposal_fits"]["p"], int(allowed_hit(r["rule"]["support"], r["label"]))))
        res[cfg["arm"]] = reliability(fit, bins)
    return res


def forecast(rules, arms_cfg, index) -> dict:
    by_session = defaultdict(list)
    for r in rules:
        by_session[r["session"]].append(r)
    res = {}
    for cfg in arms_cfg:
        if "next_difficulty" not in cfg["JEV_STAGES"]:
            continue
        items = []
        for rs in by_session.values():
            for r in rs:
                s = stage_of(index.get((cfg["arm"], r["take"], r["i"])), "next_difficulty")
                if not s or s["outcome"] != "answered":
                    continue
                ahead = [x for x in rs if r["t"] < x["t"] <= r["t"] + NEXT_HORIZON_S
                         and proxy_states(x.get("label")) is not None]
                if not ahead:
                    continue
                target = set().union(*[as_forecast_classes(proxy_states(x["label"])) for x in ahead])
                now = proxy_states(r.get("label"))
                persist = None if now is None else next(c for c in DIFF_ORDER if c in as_forecast_classes(now))
                st1 = stage_of(index.get((cfg["arm"], r["take"], r["i"])), "state_scores")
                top = None
                if st1 and st1["outcome"] == "answered" and all(q in st1["answers"] for q in STATE_NAMES):
                    top = max(STATE_NAMES, key=lambda q: st1["answers"][q]["p"])
                    top = "none" if top == "normal" else top
                items.append((r["clip"], s["answers"]["next_difficulty"]["choice"], target, persist, top))
        if not items:
            res[cfg["arm"]] = {"scored": 0}
            continue
        counts = Counter(c for _, _, t, _, _ in items for c in t)
        majority = max(DIFF_ORDER, key=lambda c: (counts[c], -DIFF_ORDER.index(c)))
        b_carry = [(cl, int(tp in t)) for cl, _, t, _, tp in items if tp is not None]
        res[cfg["arm"]] = {"scored": len(items),
                           "forecast": kn_boot([(cl, int(g in t)) for cl, g, t, _, _ in items]),
                           "forecast_on_persistence_windows": kn_boot([(cl, int(g in t)) for cl, g, t, p, _ in items
                                                                       if p is not None]),
                           "majority_class": majority,
                           "majority": kn_boot([(cl, int(majority in t)) for cl, _, t, _, _ in items]),
                           "persistence_oracle": kn_boot([(cl, int(p in t)) for cl, _, t, p, _ in items
                                                          if p is not None]),
                           "b_top_carry_forward": kn_boot(b_carry),
                           "constant": {c: kn(sum(c in t for _, _, t, _, _ in items), len(items)) for c in DIFF_ORDER},
                           "chance": statistics.fmean(len(t & set(DIFF_ORDER)) / len(DIFF_ORDER)
                                                      for _, _, t, _, _ in items),
                           "forecasts": dict(Counter(g for _, g, _, _, _ in items))}
    return res


def null_checks(labelled, arms_cfg, index, perms: int, seed: int) -> dict:
    """Selection agreement and state Brier scores with labels shuffled and with answers shuffled, within sessions
    and globally (seeded; mean and min-max over the permutations)."""
    rng = random.Random(seed)
    n_all = len(labelled)
    groups = {"session": defaultdict(list), "global": {"all": list(range(n_all))}}
    for n, r in enumerate(labelled):
        groups["session"][r["session"]].append(n)
    labs = [r["label"] for r in labelled]
    rid0 = list(range(n_all))                      # a label is the n-th window's label (labels are per window)
    prox = [proxy_states(l) for l in labs]
    memo = {}

    def hit(sel, rid):
        k = (sel, rid)
        if k not in memo:
            memo[k] = allowed_hit(sel, labs[rid])
        return memo[k]

    a_sel = [a_selection(r) for r in labelled]
    c_arms = {}
    for cfg in arms_cfg:
        if "support_choice" in cfg["JEV_STAGES"]:
            sel = [c_selection(index.get((cfg["arm"], r["take"], r["i"]))) for r in labelled]
            c_arms[cfg["arm"]] = [(n, x[1]) for n, x in enumerate(sel) if x[0] == "answered"]
    b_arms = {}
    for cfg in arms_cfg:
        if "state_scores" not in cfg["JEV_STAGES"]:
            continue
        per_q = defaultdict(list)
        for n, r in enumerate(labelled):
            s = stage_of(index.get((cfg["arm"], r["take"], r["i"])), "state_scores")
            if s and s["outcome"] == "answered":
                for q in STATE_NAMES:
                    if q in s["answers"]:
                        per_q[q].append((n, s["answers"][q]["p"]))
        b_arms[cfg["arm"]] = per_q

    def scores(rid, c_s, b_s):
        out = {"A selection": sum(hit(a, rid[n]) for n, a in enumerate(a_sel))}
        for arm, items in c_s.items():
            out[f"{arm} selection (answered)"] = sum(hit(sel, rid[n]) for n, sel in items)
        for arm, per_q in b_s.items():
            for q, items in per_q.items():
                pairs = [(p, int(q in prox_of[n])) for n, p in items if prox[rid0[n]] is not None]
                if pairs:
                    out[f"{arm} {q} Brier"] = brier(pairs)
        return out

    # Brier population is fixed: only windows whose own label maps to a state; the label shuffle permutes the mapped
    # states among those windows (within session or over all), never brings unmapped windows in
    mapped = [n for n in range(n_all) if prox[n] is not None]

    def shuffle_within(items, mode, by_options=False):
        """values shuffled among items of the same group (session or all; with by_options also the same option set,
        so a choice never lands on a window where it is not an option)."""
        grp = defaultdict(list)
        for k, (n, _) in enumerate(items):
            key = labelled[n]["session"] if mode == "session" else "all"
            if by_options:
                key = (key, tuple(labelled[n]["allowed_candidates"]))
            grp[key].append(k)
        out = list(items)
        for ks in grp.values():
            vals = [items[k][1] for k in ks]
            rng.shuffle(vals)
            for k, v in zip(ks, vals):
                out[k] = (items[k][0], v)
        return out

    prox_of = list(prox)
    actual = scores(rid0, c_arms, b_arms)
    res = {"permutations": perms, "seed": seed, "actual": actual}
    for mode in ("session", "global"):
        acc_l, acc_a = defaultdict(list), defaultdict(list)
        for _ in range(perms):
            rid = list(rid0)
            for idx in groups[mode].values():
                vals = [rid0[n] for n in idx]
                rng.shuffle(vals)
                for n, v in zip(idx, vals):
                    rid[n] = v
            perm_prox = list(prox)
            grp = defaultdict(list)
            for n in mapped:
                grp[labelled[n]["session"] if mode == "session" else "all"].append(n)
            for idx in grp.values():
                vals = [prox[n] for n in idx]
                rng.shuffle(vals)
                for n, v in zip(idx, vals):
                    perm_prox[n] = v
            prox_of[:] = perm_prox
            for k, v in scores(rid, c_arms, b_arms).items():
                acc_l[k].append(v)
            prox_of[:] = prox
            c_perm = {arm: shuffle_within(items, mode, by_options=True) for arm, items in c_arms.items()}
            b_perm = {arm: {q: shuffle_within(items, mode) for q, items in per_q.items()} for arm, per_q in b_arms.items()}
            for k, v in scores(rid0, c_perm, b_perm).items():
                if not k.startswith("A "):
                    acc_a[k].append(v)
        res[mode] = {"labels_shuffled": {k: {"mean": statistics.fmean(v), "min": min(v), "max": max(v)}
                                         for k, v in acc_l.items()},
                     "answers_shuffled": {k: {"mean": statistics.fmean(v), "min": min(v), "max": max(v)}
                                          for k, v in acc_a.items()}}
    return res


# ---------------------------------------------------------------------------------------------------- report

NOT_EVALUATED = "평가하지 않음: API를 쓸 수 없음(stub 실행은 실행 동작만 확인한다)"


def fmt(x, nd=3):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def fmt_auc(v: dict) -> str:
    if not v.get("n"):
        return "-"
    return "undefined(한 부류뿐)" if v.get("auroc") is None else f"{v['auroc']:.3f}"


def k_of(d: dict) -> str:
    if not d:
        return "-"
    ci = d.get("ci95")
    tail = f", 95% {ci[0]:.3f}~{ci[1]:.3f}" if ci else ""
    return f"{d['k']}(전체 {d['n']}{tail})"


def render_md(m: dict) -> str:
    stub = m["jev"] == "stub"
    L = [f"# E5 지표: `{Path(m['run']).name}`", "",
         f"- 매니페스트 `{m.get('manifest_id') or '없음'}` · 라벨 판 `{m.get('label_version') or '-'}` · 채점 판 "
         f"`{m.get('scoring_version') or '-'}`",
         f"- Jev: `{m['jev']}` · 모델 `{m['model']}` · 라벨 `{m['labels'] or '없음'}`({m.get('label_mode') or '-'})"]
    if m.get("aligned"):
        L.append(f"- 합성 터치 창: 값 묶음 `{m['aligned']['bundle']}`, 배치 `{m['aligned']['variant']}`, 조건 "
                 f"{', '.join(m['aligned']['conditions'])}")
    if stub:
        L.append(f"- Jev 숫자: {NOT_EVALUATED}")
    if m.get("label_status"):
        L.append(f"- 라벨 상태: {m['label_status']}")
    if not m["order_swap"]["valid"]:
        L.append(f"- **순서 바꾼 확인은 무효다.** 이 실행의 캐시는 사전 키를 정렬해서 선택지 순서가 달라도 같은 요청으로 봤다. 순서를 "
                 f"뒤집은 요청 {m['order_swap']['reversed_requests']}개 가운데 {m['order_swap']['reversed_from_cache']}개가 캐시에서 "
                 f"나왔다(Codex 205 #1). 이 실행의 순서 일관성과 '두 순서가 같을 때만' 수는 근거가 아니다. 캐시 없이 다시 묻는 일은 "
                 f"2단계에서 한다.")
    r = m["rule"]
    L += ["", "## 규칙표(조건 A)", "",
          f"- 창 {r['windows']}개(영상 {r['clips']}개, 테이크 {r['takes']}개, 세션 {r['sessions']}개), 측정 가능 {r['measurable']}개",
          f"- 기록의 상황 태그: {r['situation_record']}",
          f"- 전이: {r['transitions']}; 연 지원(open · replace): {r['opened'] or '없음'}",
          f"- 규칙표 자체 질문이 붙은 창: {r['rule_question_windows']}개 {r['rule_question_kinds'] or ''}; tick으로 거둔 묻기 "
          f"{r['expired_by_tick']}개",
          f"- 허용 후보 수별 창: {r['candidate_set_sizes']}",
          f"- 입력 기록의 결정(비전 기록 또는 E3 AB0)과 같음: {r['vision_record_match']}",
          f"- 계약 터치 5칸: {r['touch_features']}; 최근 구간 터치 수의 출처: {r['recent_source']}",
          f"- fixture 기대값: {r['expect']['checked']}개 확인, 어긋남 {len(r['expect']['failed'])}개"]
    L += ["", "## 실행(조건 · 변형 · 단계별)", "",
          "| arm | 창 | 대상 창 | 시도한 창 | 건너뜀(이유) | 단계 | 단계 대상 | build 없음 | 시도 | 답 | 실패(종류) | API 호출 | 캐시 답 | 순서 바꾼 호출 | 지연 p50 · p95 · 최대 ms | 입력 토큰 합 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm, a in m["execution"].items():
        if a["condition"] == "A":
            L.append(f"| {arm} | {a['windows']} | {a['eligible']} | 0 | 조건 A(묻지 않음) | - | - | - | - | - | - | - | - | - | - | - |")
            continue
        first = True
        for st, s in a["stages"].items():
            lat = s["latency_ms_api"]
            head = (f"| {arm} | {a['windows']} | {a['eligible']} | {a['attempted']} | {a['skipped'] or '-'} |"
                    if first else "| | | | | |")
            lat_txt = "-" if stub else f"{fmt(lat.get('p50'), 1)} · {fmt(lat.get('p95'), 1)} · {fmt(lat.get('max'), 1)}"
            L.append(f"{head} {st} | {s['eligible']} | {s['skipped_build_none']} | {s['attempted']} | {s['answered']} | "
                     f"{s['failed'] or 0} | {s['api_calls']} | {s['answers_from_cache']} | {s['order_swap_calls']} | "
                     f"{lat_txt} | {'-' if stub else s['input_tokens']['sum']} |")
            first = False
    L += ["", f"- 지연 측정: {m['latency_method']}"]
    for arm, a in m["execution"].items():
        if a["condition"] == "A":
            continue
        esc = f", 2단계까지 간 창 {k_of(a['escalation'])}" if a.get("escalation") else ""
        L.append(f"- {arm}: API 호출 {a['api_calls']}번, 캐시 답 {a['answers_from_cache']}개, 시도한 창마다 호출 "
                 f"{fmt(a['calls_per_attempted_window'], 2)}번{esc}; 사슬 전체 지연 "
                 + (NOT_EVALUATED if stub else f"p50 {fmt(a['chain_latency_ms'].get('p50'), 1)} · p95 "
                                               f"{fmt(a['chain_latency_ms'].get('p95'), 1)} ms"))
    L += ["", "## 같은 요청 점검(실행 동작)", ""]
    for name, per in m["paired"].items():
        for st, s in per.items():
            L.append(f"- {name}, 단계 {st}: 짝 창 {s['windows']}개, 요청이 같은 창 {s['identical_requests']}개")
    rp = m["repeats"]
    L += ["", f"## 같은 입력 반복(요청마다 {rp['calls_per_request']}번)", ""]
    for name, d in rp["by_arm_stage"].items():
        if stub:
            L.append(f"- {name}: 요청 {d['requests']}개(모두 답 {d['all_answered']}개); 일치도: {NOT_EVALUATED}")
            continue
        ch = "; ".join(f"{q}: 한 가지로 같음 {k_of(v['one_choice'])}, 바뀐 몫 {fmt(v['flip_share'])}, Fleiss κ "
                       f"{fmt(v['fleiss_kappa'])}, 짝 일치 평균 {fmt(v['pairwise_agreement'].get('mean'))}"
                       f"(최소 {fmt(v['pairwise_agreement'].get('min'))})" for q, v in d["choice"].items())
        L.append(f"- {name}: 요청 {d['requests']}개(모두 답 {d['all_answered']}개); {ch or '선택 질문 없음'}; 확률 폭 평균 "
                 f"{({q: fmt(v.get('mean')) for q, v in d['probability_range'].items()})}")
    if not stub:
        L += ["", "## 답 요약", "", "| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |", "|---|---|---|---|---|---|---|"]
        for arm, per in m["answers"].items():
            for st, d in per.items():
                for q, v in d["noul"].items():
                    L.append(f"| {arm} | {st} | {q} | {v['n']} | {fmt(v.get('mean'))} | {fmt(v.get('min'))} | {fmt(v.get('max'))} |")
                for q, v in d["choice"].items():
                    L.append(f"| {arm} | {st} | {q}(choice) | {sum(v['counts'].values())} | {v['counts']} | "
                             f"conf 평균 {fmt(v['confidence'].get('mean'))} | |")
        L += ["", "## 짝 비교(같은 창)", ""]
        for name, per in m["paired"].items():
            for st, s in per.items():
                L.append(f"- {name}, {st}: 가장 큰 상태 점수가 바뀐 창 {k_of(s['largest_state_changed'])}; "
                         f"고른 답이 바뀐 창 {({q: k_of(v) for q, v in s['choice_changed'].items()}) or '없음'}")
                for q, v in s["noul"].items():
                    L.append(f"  - {q}: n {v['n']}, 평균 차 {fmt(v['mean_diff'])}, 평균 |차| {fmt(v['mean_abs_diff'])}, "
                             f"최대 |차| {fmt(v['max_abs_diff'])}")
    if m.get("label_windows"):
        lw = m["label_windows"]
        L += ["", "## 라벨", "",
              f"- 라벨이 붙은 창 {lw['labelled']}개(안 붙은 창 {lw['unlabelled']}개), 수준 {lw['levels']}, 맞춘 방법 {lw['match']}",
              f"- 구간 분류별 창: {lw['segment_classes']}",
              f"- 세션 {lw['sessions']}개 가운데 라벨 행이 둘 이상인 세션 {lw['sessions_with_more_than_one_label_row']}개",
              f"- 상태 대응(STATE_PROXY)이 있는 창 {lw['state_proxy_defined']}개: {lw['state_proxy_by_states']}",
              f"- 창의 태그 | 정답 태그({lw.get('truth_basis')}): {lw['tag_vs_truth']}",
              f"- 보낸 질문의 선택지가 none 하나뿐인 창: {lw.get('singleton_none_windows')}개"]
        cv = m["coverage"]
        L += ["", "### 기준이 선택지 밖인 창", "",
              f"- 허용 행동이 선택지(허용 후보 + none)에 없음: 전체 {k_of(cv['allowed_action_absent']['all'])}, 후보가 있는 창 "
              f"{k_of(cv['allowed_action_absent']['with_candidates'])}",
              f"- 지정 지원이 허용 후보에 없음: {k_of(cv['designated_support_absent'])}",
              f"- 지정 지원이 규칙표 v0 밖(행 없음): {k_of(cv['designated_outside_rule_table'])} {cv['designated_outside_examples']}"]
        se = m["selection"]
        A = se["A"]
        sg = A["segments"]
        sp = m.get("scored_population") or {}
        L.append(f"- 점수 대상: 제외 · 모순 구간 밖의 라벨 창 {sp.get('windows')}개(뺀 창 {sp.get('excluded_windows')}개). 선택 · 상태 추정 · "
                 f"규칙표 질문 · 예측 · 섞은 대조가 모두 이 창을 쓴다.")
        L += ["", f"### 지원 선택(주 비교: A 대 C · C0 · E, 같은 창; 제외 구간을 뺀 창 {se['windows_scored']}개)", "",
              f"- A: 허용 안 {k_of(A['allowed']['all'])}(우연 {fmt(A['chance_allowed']['all'])}), 후보가 있는 창 "
              f"{k_of(A['allowed']['with_candidates'])}(우연 {fmt(A['chance_allowed']['with_candidates'])}); 지정 지원과 같음 "
              f"{k_of(A['designated'])}(우연 {fmt(A['chance_designated'])}); 고른 것 {A['selected']}",
              f"  - 구간 2×2: TP/FN/FP/TN = {sg['TP']}/{sg['FN']}/{sg['FP']}/{sg['TN']}; 거짓 경보 {k_of(sg['false_alarm'])}, "
              f"놓친 도움 {k_of(sg['missed_help'])}(v0 행 있음 {k_of(sg['missed_help_v0_row'])}), 제안 정밀도 "
              f"{k_of(sg['offer_precision'])}; 2×2 밖 {sg['other_segments']}",
              f"  - 지정 지원 자체를 시작 시각 이후 낸 구간(v0 행 있음): {k_of(sg['designated_delivery_v0_row'])}; 규칙표 행이 없는 "
              f"지정 구간(2×2 밖)에서 지정 지원 자체를 낸 구간: {k_of(sg.get('designated_delivery_no_row'))}(보이는 허용 형태만 낸 "
              f"구간 {k_of(sg.get('admissible_visible_no_row'))}은 도움으로 세지 않음)",
              f"  - 도움 규칙: 시작 시각 이후 허용 도움(admissible help after onset; 같은 turn에서 연 지원이 시작 시각 이후 "
              f"보이면 도움, 시작 시각 전에 열어 그때까지 보이면 지연 0). 시작 시각 전에 연 도움 "
              f"{sg['help_opened_before_onset']['segments']}구간(앞선 초 {sg['help_opened_before_onset']['lead_s']}), 지연 중앙값 "
              f"{fmt(sg['latency_s']['median'])}초(n {sg['latency_s']['n']}); 출처별 {sg['by_origin']}; 옛 규칙(시작 시각 이후 새 "
              f"제안만) TP/FN {sg['old_definition']['TP']}/{sg['old_definition']['FN']}, 지정 지원 "
              f"{sg['old_definition']['designated_delivery_v0_row']}",
              f"  - 허용 밖 결정의 분류(창 정답 태그 기준, 기술만, 인과 주장 아님): {A['attribution']}"]
        bl = m.get("baselines") or {}
        if bl.get("windows"):
            L += [f"- 오프라인 기준(호출 없음, 후보가 있는 창 {bl['windows']}개): 늘 none {k_of(bl['always_none'])}, 늘 후보 "
                  f"{k_of(bl['always_candidate'])}, 철회된 지원이면 none {k_of(bl['decline_if_withdrawn'])}(철회 목록을 아는 창 "
                  f"{bl['withdrawn_known']}개); 철회 규칙의 구간 2×2 TP/FN/FP/TN = "
                  f"{bl['segments_decline_if_withdrawn']['TP']}/{bl['segments_decline_if_withdrawn']['FN']}/"
                  f"{bl['segments_decline_if_withdrawn']['FP']}/{bl['segments_decline_if_withdrawn']['TN']}"]
        for arm, s in se.items():
            if arm in ("A", "windows_scored", "singleton_none_windows"):
                continue
            fo = s["first_order"]
            if stub:
                L.append(f"- {arm}: 후보가 있는 창 {s['options_windows']}개, 상태 {fo['status_on_options_windows']}, 순서를 바꾼 "
                         f"뒤 상태 {s['order_agreed']['status_on_options_windows']}; 일치 · 보정 · 순서 일관성 · 구간 · 원인 · 다음 창: "
                         f"{NOT_EVALUATED}")
                continue
            oa = s["order_agreed"]
            nw = s["next_window"]
            sgc = s["segments_with_rule_fallback"]
            j_line = (f"; 기준이 선택지 밖 {k_of(s['reference_absent'])}, 규칙표 거름 밖을 고른 답 {k_of(s['out_of_filter_choice'])}"
                      if "reference_absent" in s else "")
            dp = s.get("decline_profile") or {}
            dp_line = ("" if not dp.get("windows") else
                       f"  - 고르지 않은 창 {dp['declines']}개(전체 {dp['windows']}): {dp['window_2x2']}; 같은 수를 무작위로 고르지 않았을 때 "
                       f"허용 기대 {fmt(dp['admissible_expected_random_decline'], 1)} 대 실제 {dp['admissible_actual']}; 철회 규칙 재현 "
                       f"{k_of(dp['withdrawn_rule_reproduction'])}(철회된 후보에서 고르지 않음 {k_of(dp['declined_when_withdrawn'])}, "
                       f"처음 후보에서 {k_of(dp['declined_when_fresh'])})")
            cal = fo['calibration_p_selected']
            L += [f"- {arm}: 선택지({s['options']})가 있는 창 {s['options_windows']}개, 상태 {fo['status_on_options_windows']}{j_line}",
                  f"  - 첫 순서: 답한 창에서 허용 안 {k_of(fo['allowed_answered'])}(우연 {fmt(fo['chance_on_answered'])}; 같은 창의 "
                  f"A {k_of(fo['a_on_same_windows'])}); 규칙표로 채운 전체 {k_of(fo['allowed_with_rule_fallback'])}; 지정 지원과 같음 "
                  f"{k_of(fo['designated_answered'])}(우연 {fmt(fo['chance_designated_on_answered'])}); 고른 지원 확률 Brier "
                  f"{fmt(cal.get('brier'))} · ECE {fmt(cal.get('ece'))} · AUROC {fmt_auc(cal)}(고른 확률 대 허용; 게이트로 쓰지 않음)",
                  (f"  - 두 순서가 같을 때만: 상태 {oa['status_on_options_windows']}; 허용 안 {k_of(oa['allowed_answered'])}(우연 "
                   f"{fmt(oa['chance_on_answered'])}); 같은 창의 A {k_of(oa['a_on_same_windows'])}; 순서 일관성 "
                   f"{k_of(s['order_consistency'])}(무작위 선택자 {fmt((s['chance_order_protocol'] or {}).get('agree'))}, "
                   f"합의 · 허용 {fmt((s['chance_order_protocol'] or {}).get('agreed_admissible'))})"
                   if m["order_swap"]["valid"] else
                   "  - 두 순서가 같을 때만 · 순서 일관성: 무효(위 머리말의 캐시 산물, Codex 205 #1)"),
                  f"  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = {sgc['TP']}/{sgc['FN']}/{sgc['FP']}/{sgc['TN']}(A는 "
                  f"{sg['TP']}/{sg['FN']}/{sg['FP']}/{sg['TN']}); 거짓 경보 {k_of(sgc['false_alarm'])}, 놓친 도움 "
                  f"{k_of(sgc['missed_help'])}, 제안 정밀도 {k_of(sgc['offer_precision'])}; 허용 밖 결정의 분류 "
                  f"{s['attribution_with_rule_fallback']}",
                  f"  - 다음 창 적용: 짝 {nw['pairs']}개에서 C {nw['c']}, 한 창 늦춘 A {nw['a_delayed']}, 같은 창 A {nw['a_same']}; "
                  f"한 창 늦춘 A 전체 {k_of(nw['a_delayed_all'])}",
                  f"  - 지정 지원 자체를 낸 구간(v0 행 있음): {k_of(sgc['designated_delivery_v0_row'])}; 행이 없는 지정 구간에서 "
                  f"지정 지원 자체 {k_of(sgc.get('designated_delivery_no_row'))}(보이는 허용 형태만 "
                  f"{k_of(sgc.get('admissible_visible_no_row'))}, 도움 아님)",
                  f"  - 출처별 {sgc['by_origin']}; 시작 시각 전에 연 도움 {sgc['help_opened_before_onset']['segments']}구간; 옛 규칙 "
                  f"TP/FN {sgc['old_definition']['TP']}/{sgc['old_definition']['FN']}, 지정 지원 "
                  f"{sgc['old_definition']['designated_delivery_v0_row']}"] + ([dp_line] if dp_line else [])
            if s.get("singleton_none", {}).get("windows"):
                L.append(f"  - 보낸 질문의 선택지가 none 하나뿐인 창(대기 후보만, 위 점수 밖) {s['singleton_none']['windows']}개: "
                         f"{s['singleton_none']['status_and_choice']}")
        L += ["", "### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)", ""]
        if stub:
            L.append(f"- {NOT_EVALUATED}")
        else:
            for arm, per in m["state_estimation"].items():
                L.append(f"- {arm}: " + "; ".join(
                    f"{q} Brier {fmt(v.get('brier'))}(기준율 {fmt(v.get('brier_base_rate'))}, skill {fmt(v.get('brier_skill'))}) · "
                    f"ECE {fmt(v.get('ece'))} · AUROC {fmt_auc(v)}(n {v['n']}, 양성 {v.get('positives', 0)})"
                    for q, v in per.items()))
                for q, v in per.items():
                    raw = v.get("raw_feature_auroc") or {}
                    if raw:
                        L.append(f"  - {q} 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): " + ", ".join(
                            f"{name} {fmt(x['auroc'])} 대 {fmt(x.get('jev_auroc_same_windows'))}(n {x['n']})"
                            for name, x in raw.items()))
            L += ["", "### 규칙표 자체 질문(proposal_fits, 보조)", ""]
            for arm, v in m["rule_question"].items():
                L.append(f"- {arm}: Brier {fmt(v.get('brier'))} · ECE {fmt(v.get('ece'))} · AUROC {fmt_auc(v)}"
                         f"(n {v['n']}, 양성 {v.get('positives', 0)})")
        L += ["", "### 다음 어려움 예측(D · E, 따로 셈)", ""]
        for arm, f in m["forecast"].items():
            if not f.get("scored"):
                L.append(f"- {arm}: 점수를 낼 창 없음(앞 {NEXT_HORIZON_S:.0f}초 안에 상태 대응이 있는 라벨 창이 없거나 답이 없음)")
            elif stub:
                L.append(f"- {arm}: 점수를 낸 창 {f['scored']}개; 예측: {NOT_EVALUATED}; 다수 범주({f['majority_class']}) "
                         f"{k_of(f['majority'])}, 지속(오라클) {k_of(f['persistence_oracle'])}, 우연 {fmt(f['chance'])}")
            else:
                L.append(f"- {arm}: 예측 {k_of(f['forecast'])}; 관측 가능한 기준: B의 지금 최고 상태를 그대로 씀 "
                         f"{k_of(f['b_top_carry_forward'])}, 상수 {({c: v['k'] for c, v in f['constant'].items()})}(전체 "
                         f"{f['scored']}), 다수 범주({f['majority_class']}) {k_of(f['majority'])}, 우연 {fmt(f['chance'])}; "
                         f"지금 창의 라벨을 쓰는 지속(오라클)과 같은 창에서 예측 {k_of(f['forecast_on_persistence_windows'])} 대 "
                         f"{k_of(f['persistence_oracle'])}; 예측 분포 {f['forecasts']}")
        nl = m["null"]
        L += ["", f"### 섞은 대조(순열 {nl['permutations']}번, seed {nl['seed']}; 위와 같은 점수 대상 창)", "",
              "최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다."]
        for mode, title in (("session", "세션 안에서 섞음"), ("global", "전체에서 섞음")):
            L += ["", f"#### {title}", ""]
            for kind, kname in (("labels_shuffled", "라벨을 섞음"), ("answers_shuffled", "답을 섞음")):
                for name, v in nl[mode][kind].items():
                    if stub and not name.startswith("A "):
                        continue
                    L.append(f"- {kname} · {name}: 실제 {fmt(nl['actual'].get(name))}, 섞은 평균 {fmt(v['mean'])}, "
                             f"범위 {fmt(v['min'])}~{fmt(v['max'])}")
        if stub:
            L.append(f"- Jev 쪽 섞은 대조: {NOT_EVALUATED}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True, help="a run folder of run_jev_ablation.py")
    ap.add_argument("--labels", help="label CSV (default: the labels the runner used, if any)")
    ap.add_argument("--bins", type=int, default=10)
    ap.add_argument("--null-perms", type=int, default=DEFAULT_PERMS)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--segments", help="judgment-label CSV giving each window's segment by time (v2 joins)")
    ap.add_argument("--out-dir", help="write metrics.* here instead of the run folder")
    ap.add_argument("--exclude-windows", help="JSON list of [take, i] windows to leave out (inputs changed)")
    ap.add_argument("--manifest", help="manifest.json whose id goes into the header (default: next to the run folder)")
    args = ap.parse_args()
    run = Path(args.run)
    s = json.loads((run / "run_settings.json").read_text(encoding="utf-8"))
    path = args.labels or s.get("labels")
    import os
    jl = args.segments if s.get("aligned") else path
    if jl:
        os.environ["EVAL_LABELS"] = str(jl)   # harness.LABELS, read by help_rule.seg_start (import after this line)
    labels = None
    if path:
        labels = AdmissibleLabels.load(path, args.segments) if s.get("aligned") else Labels.load(path)
    skip = {tuple(x) for x in json.loads(Path(args.exclude_windows).read_text(encoding="utf-8"))} \
        if args.exclude_windows else None
    m = compute(run, labels, args.bins, args.null_perms, args.seed, skip)
    out = Path(args.out_dir) if args.out_dir else run
    out.mkdir(parents=True, exist_ok=True)
    m["labels_segments"] = args.segments
    if _HR is not None:
        m["help_rule_module"] = {"path": _HR.__file__, "labels_for_turn_starts": _HR.H.LABELS}
    lv = re.search(r"_v(\d+)\.csv$", str(path or ""))
    m["label_version"] = f"v{lv.group(1)}" if lv else None
    man = Path(args.manifest) if args.manifest else run.parent / "manifest.json"
    m["manifest_id"] = json.loads(man.read_text(encoding="utf-8")).get("manifest_id") if man.is_file() else None
    (out / "metrics.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "metrics.md").write_text(render_md(m), encoding="utf-8")
    print(f"metrics -> {out / 'metrics.json'}, {out / 'metrics.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
