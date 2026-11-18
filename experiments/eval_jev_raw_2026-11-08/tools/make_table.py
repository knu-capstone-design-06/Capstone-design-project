"""The E12 judgment table: the rule table, score-then-choose and J beside RAW-1 and RAW-2, in the columns of
5_deliverables/ucwit2026/results_tables_v5/judgment.md, from the judgment_rows.json files score_raw.py wrote (E5's
recorded runs rescored by the same scorer: their rows equal judgment.md's). The C4 column of the Jev rows is E12's
(judgment.md leaves it empty).

  python -B make_table.py   # writes results/judgment_E12.csv and results/judgment_E12.md
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"
SOURCES = [   # (group, condition name, judgment_rows.json, row key)
    ("Evaluated implementation", "Rule table (evaluated implementation)", RES / "c_full" / "labels_v5", "A (rule table)"),
    ("Jev selection (shadow flow)", "Jev: score, then choose", RES / "scoring_check" / "E5_C_C0", "C"),
    ("Jev selection (shadow flow)", "Jev: unconstrained choice", RES / "scoring_check" / "E5_J", "J"),
    ("Jev from camera numbers (shadow flow)", "Jev raw: choose only (RAW-1)", RES / "c_full" / "labels_v5", "RAW-1"),
    ("Jev from camera numbers (shadow flow)", "Jev raw: score, then choose (RAW-2)", RES / "c_full" / "labels_v5", "RAW-2"),
]
COLS = ["Group", "Condition", "TP", "FP", "FN", "TN", "Accuracy", "Precision", "Recall", "F1",
        "Designated-support recall", "False alarms under long no-input (C4)"]


def f3(x):
    return "—" if x is None else f"{x:.3f}"


def main() -> int:
    rows = []
    for group, name, folder, key in SOURCES:
        r = json.loads((folder / "judgment_rows.json").read_text(encoding="utf-8"))["rows"][key]
        rows.append([group, name, r["TP"], r["FP"], r["FN"], r["TN"], f3(r["accuracy"]), f3(r["precision"]),
                     f3(r["recall"]), f3(r["f1"]), f3(r["designated_support_recall"]), r["c4_false_alarms"]])
    with open(RES / "judgment_E12.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        w.writerows(rows)
    md = ["| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
    md += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    (RES / "judgment_E12.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
