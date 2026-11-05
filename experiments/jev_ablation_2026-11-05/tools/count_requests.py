"""Exact API-call count of a planned E5 stage against the frozen cache, for PR #77 at 0114ed1 and at another commit
(no API call; Codex 209 #9: recount unique requests against the current cache before each stage).

Input: a run folder that holds the stage's requests: a recorded real run, or a stub run of the planned arms (the
state of state_scores and support_choice does not depend on Jev's answers, since Jev does not update the state).
For the selected arms and stages it collects the distinct first-order requests (the runner's cache identity) and
counts: requests already answered in the cache, new first calls, new reversed-order calls (support_choice, one per
new request), and the repeat calls for --repeats R (R - 1 per distinct request, minus repeats the cache file already
holds; the runner extends stored repeats). With --backend-new the same is done after rewriting every request the way
that commit builds it (payload_diff.py rewrite; its rule pass gives the support_choice candidates).

  <backend venv python> -B count_requests.py --run <folder> [--arms C C0] [--stages support_choice] [--repeats 5]
      [--repeat-fraction 0.1 --repeat-seed 0] [--cache results/jev_cache.jsonl.gz] [--backend-new <dir>]

In this package: --run is a run folder made by tools/run_set.py (runs/<name>/<run>/); the default cache is the
package's results/jev_cache.jsonl.gz (read as is, gzipped or not).
"""

import argparse
import gzip
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import payload_diff as PD  # noqa: E402

E5 = HERE.parent


def count(calls, states, qs, arms, stages, cache, reps, windows, conds, rewrite=None):
    keys, by_stage = {}, Counter()
    skipped = 0
    for c in calls:
        if not c["asked"] or (arms and c["arm"] not in arms) or (windows is not None and (c["take"], c["i"]) not in windows):
            continue
        for e in c["stages"]:
            if e["outcome"] == "skipped" or not e.get("state_hash") or (stages and e["stage"] not in stages):
                continue
            st, q = states[e["state_hash"]], qs[e["questions_hash"]]
            if rewrite is not None:
                rw = rewrite(e["stage"], st, q, conds[c["arm"]], c)
                if rw is None:
                    skipped += 1
                    continue
                st, q = rw
            k = PD.digest({"model": PD.MODEL, "state": st, "questions": q})
            keys.setdefault(k, e["stage"])
    new = [k for k in keys if k not in cache["answers"]]
    stored = sum(min(len(cache["repeats"].get(k) or []), reps - 1) for k in keys)
    for k, stg in keys.items():
        by_stage[stg] += 1
    first = len(new)
    swaps = sum(1 for k in new if keys[k] == "support_choice")
    repeat = (reps - 1) * len(keys) - stored
    return {"distinct_requests": len(keys), "by_stage": dict(by_stage), "in_cache": len(keys) - first,
            "new_first_calls": first, "new_reversed_calls": swaps, "repeat_calls": repeat,
            "repeats_already_stored": stored, "now_skipped": skipped, "total_calls": first + swaps + repeat}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--arms", nargs="*")
    ap.add_argument("--stages", nargs="*")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--repeat-fraction", type=float, default=1.0)
    ap.add_argument("--repeat-seed", type=int, default=0)
    ap.add_argument("--cache", default=str(E5 / "results" / "jev_cache.jsonl.gz"))
    ap.add_argument("--backend-new", help="backend/ of the other commit (e.g. 3c936ae)")
    args = ap.parse_args()
    run = Path(args.run)
    st = json.loads((run / "run_settings.json").read_text(encoding="utf-8"))
    rules = PD.read_jsonl(run / "rule_windows.jsonl")
    states = {x["state_hash"]: x["state"] for x in PD.read_jsonl(run / "states.jsonl")}
    qs = json.loads((run / "questions.json").read_text(encoding="utf-8"))
    calls = PD.read_jsonl(run / "jev_calls.jsonl")
    conds = {a["arm"]: a["condition"] for a in st["arms"]}
    cache = {"answers": set(), "repeats": {}}
    with (gzip.open(args.cache, "rt", encoding="utf-8") if args.cache.endswith(".gz")
          else open(args.cache, encoding="utf-8")) as fh:
        for x in fh:
            e = json.loads(x)
            if "response" in e:
                cache["answers"].add(e["key"])
            if "repeats" in e:
                cache["repeats"][e["key"]] = e["repeats"]
    windows = None
    if args.repeat_fraction < 1.0:      # the runner's seeded subset (run_jev_ablation.py repeat_windows)
        keys = sorted((r["take"], r["i"]) for r in rules)
        windows = set(random.Random(args.repeat_seed).sample(keys, round(args.repeat_fraction * len(keys))))
    out = {"run": str(run), "arms": args.arms, "stages": args.stages, "repeats": args.repeats,
           "repeat_fraction": args.repeat_fraction, "windows_in_subset": None if windows is None else len(windows),
           "pr_commit_of_run": st.get("pr_commit"),
           "at_run_commit": count(calls, states, qs, args.arms, args.stages, cache, args.repeats, windows, conds)}
    if args.backend_new:
        sys.path.insert(0, args.backend_new)
        from app.modules.decision import rule_table as R, schemas as S
        allowed, *_ = PD.rule_pass(rules, R, S)
        out["backend_new"] = args.backend_new
        out["at_backend_new"] = count(calls, states, qs, args.arms, args.stages, cache, args.repeats, windows, conds,
                                      lambda stage, s_, q_, cond, c: PD.rewrite(stage, s_, q_, cond,
                                                                                allowed.get((c["take"], c["i"])), R, S))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
