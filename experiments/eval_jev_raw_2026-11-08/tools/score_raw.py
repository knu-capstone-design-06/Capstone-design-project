"""Score an E12 (or E5) run folder at labels v5 with E5's metrics.py, unchanged, and write the judgment-table rows.

1. Windows of clip 20261028_165108 are left out (E5 rescore_labels.py EXCLUDED_TAKES), as E5's v5 rescoring
   did; the labels are E3's admissible_v5.csv joined by segment (judgment_labels_v5.csv), E5's v5 call.
2. metrics.py --run <run> --labels admissible_v5.csv --segments judgment_labels_v5.csv --exclude-windows ... writes
   <out>/metrics.{json,md}. The 2x2 of a support_choice arm is selection[arm].segments_with_rule_fallback (the field
   E5's stage2_summary.py reports for J); the rule table's is selection.A.segments.
3. C4 false alarms: the same metrics.py on a copy of the run holding only the C4 takes; FP / (FP + TN) of that 2x2 =
   wait-only C4 cells with an intervention (results_tables_v5/definitions.md 'False alarms under long no-input (C4)').
4. Derived as results_tables_v5/definitions.md: accuracy = (TP + TN) / (P + N), precision = TP / (TP + FP), recall =
   TP / (TP + FN), F1 = 2TP / (2TP + FP + FN), designated-support recall = designated_delivery_v0_row k / P.

  <ai-engine venv python> -B score_raw.py --run <run folder> --out <dir> [--arms RAW-1 RAW-2] [--null-perms 0]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[2]
E5_TOOLS = WS / "4_vision" / "eval_jev_2026-11-04" / "tools"
EVAL_AB = WS / "4_vision" / "eval_ab_2026-11-04"
ADMISSIBLE = EVAL_AB / "admissible_v5.csv"
JUDGMENT = EVAL_AB / "judgment_labels_v5.csv"
EXCLUDED_TAKES = ("20261028_165108",)     # E5 rescore_labels.py, E3 harness.EXCLUDED_TAKES
COPY = ("states.jsonl", "questions.json", "run_settings.json", "repeats.jsonl")


def read_jsonl(p: Path) -> list:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def run_metrics(run: Path, out: Path, perms: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    excl = out / "_exclude.json"
    rules = read_jsonl(run / "rule_windows.jsonl")
    excl.write_text(json.dumps([[r["take"], r["i"]] for r in rules if r["take"].split("@")[0] in EXCLUDED_TAKES]),
                    encoding="utf-8")
    cmd = [sys.executable, "-B", str(E5_TOOLS / "metrics.py"), "--run", str(run), "--labels", str(ADMISSIBLE),
           "--segments", str(JUDGMENT), "--exclude-windows", str(excl), "--out-dir", str(out), "--null-perms", str(perms)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    excl.unlink()
    return json.loads((out / "metrics.json").read_text(encoding="utf-8"))


def c4_copy(run: Path, dest: Path) -> Path:
    """A run folder holding only the C4 takes (rule windows and calls), other files copied."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("rule_windows.jsonl", "jev_calls.jsonl"):
        with open(run / name, encoding="utf-8") as src, open(dest / name, "w", encoding="utf-8") as dst:
            for line in src:
                if line.strip() and json.loads(line)["take"].endswith("@C4"):
                    dst.write(line)
    for name in COPY:
        if (run / name).is_file():
            shutil.copyfile(run / name, dest / name)
    return dest


def segs(m: dict, arm: str) -> dict:
    se = m["selection"]
    return se["A"]["segments"] if arm == "A" else se[arm]["segments_with_rule_fallback"]


def row(s: dict, c4: dict | None) -> dict:
    tp, fn, fp, tn = s["TP"], s["FN"], s["FP"], s["TN"]
    p, n = tp + fn, fp + tn
    dd = s["designated_delivery_v0_row"]
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn, "positives": p, "negatives": n,
            "accuracy": (tp + tn) / (p + n), "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / p if p else None, "f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0,
            "designated_support_recall": dd["k"] / p if p else None, "designated_delivery": f"{dd['k']}/{dd['n']}",
            "c4_false_alarms": None if c4 is None else f"{c4['FP']}/{c4['FP'] + c4['TN']}",
            "by_origin": s.get("by_origin")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--arms", nargs="*", default=["RAW-1", "RAW-2"])
    ap.add_argument("--null-perms", type=int, default=0, help="E5's permutation controls (not part of the 2x2)")
    args = ap.parse_args()
    run, out = Path(args.run), Path(args.out)
    m = run_metrics(run, out, args.null_perms)
    tmp = c4_copy(run, out / "_c4_run")
    try:
        m4 = run_metrics(tmp, out / "C4", args.null_perms)
    finally:
        shutil.rmtree(tmp)
    rows = {"A (rule table)": row(segs(m, "A"), segs(m4, "A"))}
    for arm in args.arms:
        rows[arm] = row(segs(m, arm), segs(m4, arm))
    res = {"run": str(run), "labels": str(ADMISSIBLE), "segments": str(JUDGMENT), "excluded_takes": list(EXCLUDED_TAKES),
           "scored_windows": m["scored_population"]["windows"], "help_rule": segs(m, "A")["help_rule_name"],
           "rows": rows}
    (out / "judgment_rows.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, r in rows.items():
        f = lambda x: "-" if x is None else f"{x:.3f}"
        print(f"{k}: TP {r['TP']} FP {r['FP']} FN {r['FN']} TN {r['TN']} acc {f(r['accuracy'])} P {f(r['precision'])} "
              f"R {f(r['recall'])} F1 {f(r['f1'])} DSR {f(r['designated_support_recall'])} ({r['designated_delivery']}) "
              f"C4 FA {r['c4_false_alarms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
