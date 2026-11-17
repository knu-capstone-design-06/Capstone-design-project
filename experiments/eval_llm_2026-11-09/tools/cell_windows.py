"""List the windows of an arm's data file that fall in the 137 table cells (wait_only 70 + designated with a
rule-table v0 row 67), using score.py's own label loader. Writes the window list and a restricted copy of the Jev
reference answers (every other window -> null) so score.py can check that the restriction leaves the row unchanged.
"""
import json, sys
from pathlib import Path

kit, arm, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, str(kit))
import score  # noqa: E402  (kit scorer, read-only use of load_labels)

wins, cells, _ = score.load_labels()
table_cells = {cid for cid, a in cells.items()
               if a["cls"] == "wait_only" or (a["cls"] == "designated" and "true" in a["v0_row"].split(";"))}
in_cell = {w["window_id"] for w in wins if w["scored"] and w["cell_id"] in table_cells}
rows = [json.loads(l) for l in (kit / f"data/{arm}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
keep = [r["window_id"] for r in rows if r["window_id"] in in_cell]
out.mkdir(parents=True, exist_ok=True)
(out / f"{arm}_cell_windows.txt").write_text("\n".join(keep) + "\n", encoding="utf-8")
ref = [json.loads(l) for l in (kit / f"reference_answers/{arm}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
with open(out / f"{arm}_jev_restricted.jsonl", "w", encoding="utf-8") as f:
    for r in ref:
        f.write(json.dumps({"window_id": r["window_id"], "choice": r["choice"] if r["window_id"] in in_cell else None}) + "\n")
cls = {}
for cid in table_cells:
    cls[cells[cid]["cls"]] = cls.get(cells[cid]["cls"], 0) + 1
print(json.dumps({"table_cells": len(table_cells), "by_class": cls, "data_windows": len(rows),
                  "data_windows_in_table_cells": len(keep)}))
