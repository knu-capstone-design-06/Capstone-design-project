"""Which recorded E5 requests would change under another PR #77 commit (no API call, no stub run).

For every recorded real run it rebuilds the rule table's pass with the other commit's code on the recorded window
inputs (decisions, allowed candidates), rewrites each recorded request the way the other commit would build it
(jev_state, support_choice candidates and criteria, next_difficulty wording), and checks the result against the real
cache keys. Counts: windows with an unknown or missing situation among the asked windows, windows whose candidate
list differs, decisions that differ, and the distinct new requests per run and stage (a request already in the cache,
or already new earlier in the sequence, costs nothing). Swapped-order and repeat calls are added per new request.

  python -B payload_diff.py --backend <other commit's backend/> --set <recorded set>

Record: this script counted, before the 3c936ae re-run, which 0114ed1 requests that commit would change
(real_2026-11-04/payload_diff.json in the author's workspace, not shipped). count_requests.py imports its helpers.
"""

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
E5 = Path(__file__).resolve().parent.parent
MODEL = "jev-1.13.0"


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(o):
    return hashlib.sha256(canon(o).encode("utf-8")).hexdigest()[:16]


def read_jsonl(p):
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


NONE_TEXT = "Show nothing new in this window; the user is doing fine or already has the help they need"


def rule_pass(rules, R, S):
    """The other commit's rule pass on the recorded window inputs: {(take, i): allowed candidates}, the number of
    windows whose candidate list or decision differs, and the asked windows with an unknown situation."""
    new_allowed, cand_diff, dec_diff, unknown_asked = {}, 0, 0, 0
    by_take = defaultdict(list)
    for r in rules:
        by_take[r["take"]].append(r)
    for take, rs in by_take.items():
        rs.sort(key=lambda x: x["i"])
        state, k = S.SessionState(), None
        for r in rs:
            if r["session_k"] != k:
                state, k = S.SessionState(), r["session_k"]
            inp = S.WindowInput(**{**r["input"], "situation": r.get("situation_input")})
            state, _ = R.tick(state, inp.t, S.PILOT_PARAMS)
            before = copy.deepcopy(state)
            al = R.allowed_supports(inp, before, S.PILOT_PARAMS)
            d = R.decide(inp, before, S.PILOT_PARAMS)
            state, d = R.apply(state, d)
            new_allowed[(take, r["i"])] = al
            cand_diff += al != r["allowed_candidates"]
            dec_diff += (d.transition, d.support) != (r["rule"]["transition"], r["rule"]["support"])
            unknown_asked += r["measurable"] and not R.situation_known(r.get("situation_input"))
    return new_allowed, cand_diff, dec_diff, unknown_asked


def rewrite(stage, state, questions, cond, allowed, R, S):
    """The request the other commit (3c936ae) would send for a recorded one: unknown situation -> tag None and
    evidence {} (looking_around False -> None beside it); support_choice candidates and criteria from its rule pass
    (J: every support with its WHAT line); next_difficulty horizon wording. None: the stage is now skipped."""
    s2, q2 = copy.deepcopy(state), copy.deepcopy(questions)
    sit, vis = s2.get("situation"), s2.get("vision")
    if isinstance(sit, dict) and sit.get("tag") in (None, "unknown"):
        sit["tag"], sit["evidence"] = None, {}
        if isinstance(vis, dict) and vis.get("looking_around") is False:
            vis["looking_around"] = None
    if stage == "support_choice":
        if cond == "J":
            q2["support_choice"]["criteria"] = {**{x: R.WHAT.get(x) for x in s2["candidates"]}, "none": NONE_TEXT}
        else:
            if not allowed:
                return None
            s2["candidates"] = allowed
            q2["support_choice"]["criteria"] = {**{x: R.WHAT[x] for x in allowed if x in R.WHAT}, "none": NONE_TEXT}
    if stage == "next_difficulty":
        ins = q2["next_difficulty"]["instructions"]
        q2["next_difficulty"]["instructions"] = ins.replace("ten seconds", f"{S.FORECAST_HORIZON_S} seconds")
    return s2, q2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", required=True)
    ap.add_argument("--set", required=True, help="a set folder with run folders (rule_windows, jev_calls, states)")
    args = ap.parse_args()
    sys.path.insert(0, args.backend)
    from app.modules.decision import jev_questions as Q, rule_table as R, schemas as S
    root = Path(args.set)
    cache = {json.loads(x)["key"] for x in open(root / "jev_cache.jsonl", encoding="utf-8") if '"response"' in x}
    seen = set(cache)
    totals = Counter()
    out = {}
    for run in sorted(d for d in root.iterdir() if (d / "jev_calls.jsonl").is_file()):
        st = json.loads((run / "run_settings.json").read_text(encoding="utf-8"))
        if st.get("jev") != "real":
            continue
        rules = read_jsonl(run / "rule_windows.jsonl")
        states = {x["state_hash"]: x["state"] for x in read_jsonl(run / "states.jsonl")}
        qs = json.loads((run / "questions.json").read_text(encoding="utf-8"))
        new_allowed, cand_diff, dec_diff, unknown_asked = rule_pass(rules, R, S)
        arms = {a["arm"]: a for a in st["arms"]}
        new_by_stage = Counter()
        new_windows = Counter()
        for c in read_jsonl(run / "jev_calls.jsonl"):
            if not c["asked"]:
                continue
            cond = arms[c["arm"]]["condition"]
            stage1_new = False
            for e in c["stages"]:
                if e["outcome"] == "skipped" or not e.get("state_hash"):
                    continue
                rw = rewrite(e["stage"], states[e["state_hash"]], qs[e["questions_hash"]], cond,
                             new_allowed.get((c["take"], c["i"])), R, S)
                if rw is None:
                    new_by_stage["support_choice_now_skipped"] += 1
                    continue
                s2, q2 = rw
                key = digest({"model": MODEL, "state": s2, "questions": q2})
                dependent = e["stage"] != "state_scores" and stage1_new and "jev" in s2
                if key not in seen or dependent:
                    if key not in seen:
                        seen.add(key)
                        new_by_stage[e["stage"]] += 1
                        if e["stage"] == "support_choice":
                            new_by_stage["swap"] += 1
                    elif dependent:
                        new_by_stage[e["stage"] + "_after_new_stage1"] += 1
                    new_windows[c["arm"]] += 1
                    if e["stage"] == "state_scores":
                        stage1_new = True
        reps = st.get("repeats") or 1
        calls = sum(v for k, v in new_by_stage.items() if k in ("state_scores", "support_choice", "next_difficulty",
                                                                "swap")) + sum(
            v for k, v in new_by_stage.items() if k.endswith("_after_new_stage1"))
        calls_rep = calls + (reps - 1) * sum(v for k, v in new_by_stage.items() if k != "swap"
                                            and not k.endswith("now_skipped"))
        out[run.name] = {"windows": len(rules), "asked_unknown_situation": unknown_asked,
                         "candidate_lists_differ": cand_diff, "decisions_differ": dec_diff,
                         "new_requests_by_stage": dict(new_by_stage), "arms_with_changed_requests": dict(new_windows),
                         "new_calls": calls, "new_calls_with_repeats": calls_rep, "recorded_calls": st["calls_total"]}
        totals["new_calls"] += calls_rep
        totals["recorded_calls"] += st["calls_total"]
        print(run.name, json.dumps(out[run.name], ensure_ascii=False))
    print("TOTAL", dict(totals))
    (root / "payload_diff.json").write_text(json.dumps({"backend": args.backend, "runs": out, "totals": dict(totals)},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
