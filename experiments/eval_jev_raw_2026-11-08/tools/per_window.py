"""Per-window answers of an E12 run beside E5's arm J on the same windows (no API call), and their agreement.

Writes <out>/per_window_answers.csv (one row per window: rule-table decision, J's choice, RAW-1 / RAW-2 choices with
confidence, RAW-2's five state scores) and <out>/answer_summary.json (choice counts per arm, pairwise agreement on the
windows both answered). Windows of the excluded clip 20261028_165108 are kept in the CSV and flagged; the summary
counts the scored clips only.

  python -B per_window.py --run <E12 run folder> --out <dir>
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[2]
J_RUN = WS / "4_vision" / "eval_jev_2026-11-04" / "results" / "real_2026-11-05_3c936ae" / "stage2_3_J_b0_r0"
EXCLUDED = ("20261028_165108",)
STATES = ("touch_difficulty", "navigation_difficulty", "visual_difficulty", "hesitation", "normal")


def read_jsonl(p: Path) -> list:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def stage(c: dict | None, name: str) -> dict | None:
    for s in (c or {}).get("stages", []):
        if s["stage"] == name and s["outcome"] == "answered":
            return s
    return None


def choice(c):
    s = stage(c, "support_choice")
    return (None, None) if s is None else (s["answers"]["support_choice"]["choice"],
                                           s["answers"]["support_choice"]["confidence"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    run, out = Path(args.run), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rules = read_jsonl(run / "rule_windows.jsonl")
    calls = {(c["arm"], c["take"], c["i"]): c for c in read_jsonl(run / "jev_calls.jsonl")}
    jcalls = {(c["take"], c["i"]): c for c in read_jsonl(J_RUN / "jev_calls.jsonl")}
    rows, counts, agree = [], {a: Counter() for a in ("J", "RAW-1", "RAW-2")}, Counter()
    for r in rules:
        k = (r["take"], r["i"])
        j, c1, c2 = jcalls.get(k), calls.get(("RAW-1", *k)), calls.get(("RAW-2", *k))
        jc, _ = choice(j)
        r1, r1c = choice(c1)
        r2, r2c = choice(c2)
        sc = stage(c2, "state_scores")
        excluded = r["clip"] in EXCLUDED
        rows.append({"take": r["take"], "clip": r["clip"], "condition": r["condition"], "t": r["t"],
                     "segment_id": r["segment_id"], "excluded_clip": excluded, "measurable": r["measurable"],
                     "rule_transition": r["rule"]["transition"], "rule_support": r["rule"]["support"] or "",
                     "J_choice": jc or "", "RAW1_choice": r1 or "",
                     "RAW1_confidence": "" if r1c is None else round(r1c, 4), "RAW2_choice": r2 or "",
                     "RAW2_confidence": "" if r2c is None else round(r2c, 4),
                     **{f"RAW2_{q}": "" if sc is None else round(sc["answers"][q]["p"], 4) for q in STATES}})
        if excluded:
            continue
        for a, x in (("J", jc), ("RAW-1", r1), ("RAW-2", r2)):
            if x is not None:
                counts[a][x] += 1
        for (a, x), (b, y) in ((("J", jc), ("RAW-1", r1)), (("J", jc), ("RAW-2", r2)), (("RAW-1", r1), ("RAW-2", r2))):
            if x is not None and y is not None:
                agree[f"{a} vs {b} windows"] += 1
                agree[f"{a} vs {b} same choice"] += x == y
    with open(out / "per_window_answers.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {"windows": len(rows), "scored_clip_windows": sum(not x["excluded_clip"] for x in rows),
               "choice_counts_scored_clips": {a: dict(c.most_common()) for a, c in counts.items()},
               "agreement_scored_clips": dict(agree)}
    (out / "answer_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
