"""E12 checks of a run folder (no API call): alignment with E5's arm J, what the requests contain, their size.

1. Windows: rule_windows.jsonl against E5 J's (stage2_3_J_b0_r0): same windows, inputs, rule decisions, candidates.
2. Asked windows: the (take, i) each RAW arm asked against the windows J asked.
3. Content: every sent state and question is scanned for keys that must not be sent (tags, gaze, rule outputs, P1,
   role decisions, the rule table's own questions); candidates must be the fixed six-support list; every leaf must be
   a number, null, a boolean or a short name (no image, no long string in the state).
4. Size: request bytes per arm and stage over the distinct requests (the ones the API is called for).
5. Example requests: one window's requests written as JSON (numbers only besides names and the question texts).

  python -B check_run.py --run <run folder> [--example-take 20261028_171348@C2 --example-t 6.0] [--write-examples]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[2]
J_RUN = WS / "4_vision" / "eval_jev_2026-11-04" / "results" / "real_2026-11-05_3c936ae" / "stage2_3_J_b0_r0"
ALL_SUPPORTS = ["wait_hold_timer", "remaining_steps_notice", "delay_responsibility_notice", "large_button",
                "highlight_next_action", "defer_big_button_question"]
FORBIDDEN = ("situation", "vision", "tag", "evidence", "dropped_cues", "facing_screen", "looking_around", "gaze",
             "people_behind", "people_behind_count", "companion", "companion_box", "head_dir", "proposal_fits",
             "queue_support", "role", "image", "frame", "pixels")
NAME_MAX = 40   # a leaf string longer than this in a state is reported (support / screen names are shorter)


def read_jsonl(p: Path) -> list:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--example-take", default="20261028_171348@C2")
    ap.add_argument("--example-t", type=float, default=6.0)
    ap.add_argument("--write-examples", action="store_true")
    args = ap.parse_args()
    run = Path(args.run)
    out = {"run": str(run)}

    # 1. windows
    mine = read_jsonl(run / "rule_windows.jsonl")
    theirs = {(r["take"], r["i"]): r for r in read_jsonl(J_RUN / "rule_windows.jsonl")}
    keys = ("t", "segment_id", "condition", "session_k", "measurable", "input", "situation_used", "rule",
            "allowed_candidates", "held_before", "withdrawn_before")
    diff = [(r["take"], r["i"]) for r in mine if (r["take"], r["i"]) not in theirs
            or any(r.get(k) != theirs[(r["take"], r["i"])].get(k) for k in keys)]
    out["windows"] = {"this_run": len(mine), "e5_J": len(theirs), "differing_or_missing": len(diff),
                      "file_sha256_equal": sha(run / "rule_windows.jsonl") == sha(J_RUN / "rule_windows.jsonl"),
                      "compared_fields": list(keys), "examples": diff[:5]}

    # 2. asked windows
    j_asked = {(c["take"], c["i"]) for c in read_jsonl(J_RUN / "jev_calls.jsonl") if c["asked"]}
    calls = read_jsonl(run / "jev_calls.jsonl")
    by_arm = defaultdict(list)
    for c in calls:
        by_arm[c["arm"]].append(c)
    out["asked"] = {}
    for arm, cs in by_arm.items():
        asked = {(c["take"], c["i"]) for c in cs if c["asked"]}
        out["asked"][arm] = {"asked": len(asked), "same_as_J": asked == j_asked, "J_asked": len(j_asked),
                             "skips": dict(Counter(c["skip_reason"] for c in cs if c["skip_reason"]))}

    # 3. content
    states = {x["state_hash"]: x["state"] for x in read_jsonl(run / "states.jsonl")}
    questions = json.loads((run / "questions.json").read_text(encoding="utf-8"))
    bad, long_str, cand_bad, kinds = [], [], 0, Counter()
    for h, st in states.items():
        for path, v in walk(st):
            parts = [p.split("[")[0] for p in path.split(".")]
            if any(p in FORBIDDEN for p in parts):
                bad.append((h, path))
            kinds[type(v).__name__] += 1
            if isinstance(v, str) and len(v) > NAME_MAX:
                long_str.append((h, path, len(v)))
        if "candidates" in st and st["candidates"] != ALL_SUPPORTS:
            cand_bad += 1
    qbad = [(h, q) for h, qs in questions.items() for q in qs if q in FORBIDDEN]
    top = Counter(tuple(st) for st in states.values())
    out["content"] = {"distinct_states": len(states), "forbidden_keys_in_states": len(bad), "examples": bad[:5],
                      "forbidden_question_names": qbad, "candidates_not_the_fixed_six": cand_bad,
                      "long_strings_in_states": long_str[:5], "leaf_types": dict(kinds),
                      "top_level_keys": {"|".join(k): n for k, n in top.items()},
                      "question_sets": {h: sorted(qs) for h, qs in questions.items()}}

    # 4. size over the distinct requests (not cached)
    size = defaultdict(list)
    tokens = defaultdict(list)
    for c in calls:
        for s in c["stages"]:
            if s["outcome"] == "skipped":
                continue
            if not s.get("cached"):
                size[(c["arm"], s["stage"])].append(s["request_bytes"])
                if s.get("usage"):
                    tokens[(c["arm"], s["stage"])].append(s["usage"]["input_tokens"])
    out["size"] = {f"{a} / {st}": {"distinct_requests": len(v), "bytes_median": statistics.median(v),
                                   "bytes_max": max(v), "bytes_sum": sum(v),
                                   "input_tokens_sum": sum(tokens[(a, st)]) if tokens[(a, st)] else None}
                   for (a, st), v in sorted(size.items())}
    out["size_total_bytes"] = sum(sum(v) for v in size.values())

    # 5. example requests of one window
    ex = {}
    for c in calls:
        if c["take"] == args.example_take and abs(c["t"] - args.example_t) < 1e-6 and c["asked"]:
            for s in c["stages"]:
                ex[f"{c['arm']}__{s['stage']}"] = {"model": s.get("request_model"), "state": states[s["state_hash"]],
                                                    "questions": questions[s["questions_hash"]]}
    out["example_requests"] = sorted(ex)
    if args.write_examples:
        for k, body in ex.items():
            (run / f"request_example_{k}.json").write_text(json.dumps(body, ensure_ascii=False, indent=1),
                                                           encoding="utf-8")
    (run / "check_run.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("windows", "asked")}, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in out["content"].items() if k != "question_sets"}, ensure_ascii=False))
    print(json.dumps(out["size"], ensure_ascii=False, indent=1), out["size_total_bytes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
