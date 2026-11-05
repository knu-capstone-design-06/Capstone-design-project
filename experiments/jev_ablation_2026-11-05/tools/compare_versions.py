"""Compare two E5 result sets run on different PR #77 commits (no API call): results/real_2026-11-04 (0114ed1, superseded)
and results/real_2026-11-05_3c936ae.

Per run present in both: windows whose rule inputs are identical (rescore_labels.py FIELDS and the situation used),
rule decisions and allowed candidates on those windows, and per arm x stage on those windows: requests asked in both,
identical requests (same state and questions), changed requests and among them changed answers (choice questions:
the choice; noul: p), identical requests with another answer (duplicate cache entries), and stages asked in only one
set. Writes <new set>/version_comparison.json and prints one line per run and arm.

  python -B compare_versions.py --old <0114ed1 set> --new <3c936ae set>

Record: this script made results/version_comparison.json from the two sets' run files in the author's workspace
(4_vision/eval_jev_2026-11-04/results/real_2026-11-04 and real_2026-11-05_3c936ae). The package ships neither set's
run files (the 0114ed1 set is superseded; the 3c936ae run files are re-made by tools/run_set.py --jev cache), so it
runs here only with --new runs/cache and an --old set obtained from the author.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

E5 = Path(__file__).resolve().parent.parent
FIELDS = ("t", "measurable", "screen", "steps_left", "gaze", "misses_recent", "fixes_recent", "backs_recent", "pause_s",
          "taps_segment", "progress_segment", "options_open")


def read_jsonl(p: Path) -> list:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def same_input(a: dict, b: dict) -> bool:
    return all(a["input"].get(f) == b["input"].get(f) for f in FIELDS) and a.get("situation_used") == b.get("situation_used")


def compact(c: dict) -> dict:
    """{stage: (state_hash, questions_hash, {question: p or choice})} of the answered stages (streamed, low memory)."""
    return {e["stage"]: (e["state_hash"], e["questions_hash"],
                         {q: (a["p"] if a["type"] == "noul" else a.get("choice")) for q, a in e["answers"].items()})
            for e in c["stages"] if e["outcome"] == "answered"}


def stream(p: Path):
    with open(p, encoding="utf-8") as fh:
        for x in fh:
            if x.strip():
                yield json.loads(x)


def compare(old: Path, new: Path) -> dict:
    ro = {(r["take"], r["i"]): r for r in read_jsonl(old / "rule_windows.jsonl")}
    rn = {(r["take"], r["i"]): r for r in read_jsonl(new / "rule_windows.jsonl")}
    keys = [k for k in rn if k in ro and same_input(ro[k], rn[k])]
    ks = set(keys)
    dec = sum((ro[k]["rule"]["transition"], ro[k]["rule"]["support"]) != (rn[k]["rule"]["transition"], rn[k]["rule"]["support"])
              for k in keys)
    cand = sum(ro[k]["allowed_candidates"] != rn[k]["allowed_candidates"] for k in keys)
    co = {(c["arm"], c["take"], c["i"]): compact(c) for c in stream(old / "jev_calls.jsonl")
          if (c["take"], c["i"]) in ks}
    per = defaultdict(Counter)
    for c in stream(new / "jev_calls.jsonl"):
        if (c["take"], c["i"]) not in ks:
            continue
        so = co.get((c["arm"], c["take"], c["i"])) or {}
        sn = compact(c)
        for st in set(so) | set(sn):
            d = per[f"{c['arm']} / {st}"]
            if st not in so or st not in sn:
                d["only_old" if st in so else "only_new"] += 1
                continue
            x, y = so[st], sn[st]
            d["both"] += 1
            same_req = x[0] == y[0] and x[1] == y[1]
            d["identical_request"] += same_req
            ch = bool([q for q in y[2] if q in x[2] and x[2][q] != y[2][q]])
            if same_req:
                # the same request with another answer: the cache file holds two answers for it (two identical calls
                # in flight at once in the 0114ed1 run; the cache now serves the last one), not a code effect
                d["identical_request_other_answer"] += ch
            else:
                d["request_changed"] += 1
                d["answer_changed"] += ch
    return {"windows_new": len(rn), "windows_compared": len(keys), "inputs_differ": sum(1 for k in rn if k in ro) - len(keys),
            "decisions_differ": dec, "candidate_lists_differ": cand, "arms": {k: dict(v) for k, v in sorted(per.items())},
            "commits": [json.loads((old / "run_settings.json").read_text(encoding="utf-8")).get("pr_commit"),
                        json.loads((new / "run_settings.json").read_text(encoding="utf-8")).get("pr_commit")]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--old", required=True, help="the superseded set's folder (PR #77 0114ed1)")
    ap.add_argument("--new", required=True, help="the set's folder at 3c936ae (e.g. runs/cache)")
    args = ap.parse_args()
    old, new = Path(args.old), Path(args.new)
    out = {}
    for d in sorted(new.iterdir()):
        if (d / "jev_calls.jsonl").is_file() and (old / d.name / "jev_calls.jsonl").is_file():
            out[d.name] = compare(old / d.name, d)
            r = out[d.name]
            print(f"== {d.name}: windows compared {r['windows_compared']} (inputs differ {r['inputs_differ']}), decisions "
                  f"differ {r['decisions_differ']}, candidate lists differ {r['candidate_lists_differ']}")
            for arm, v in r["arms"].items():
                print(f"   {arm}: {v}")
    (new / "version_comparison.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
