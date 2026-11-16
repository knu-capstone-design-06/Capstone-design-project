"""The LLM evaluation kit's scorer on this folder's bundle-b0_rA labels.

The kit's score.py (5_deliverables/llm_eval_kit_2026-11-08/score.py) is imported unchanged; only its module globals
HERE and LABELS are pointed at this folder, so the rule table's own decisions (used for every window that is not
answered) come from labels/window_cells.csv of bundle b0_rA instead of the kit's b0_r0 file. The module is also
registered as `score`, so an existing tool that does `import score` (eval_llm_2026-11-09/tools/cell_windows.py) runs
on the same labels.

  python kit_rA.py score --rule-table
  python kit_rA.py score --data ../data/E5_J.jsonl --answers <answers.jsonl> [--name ...] [--cells-out cells.csv]
  python kit_rA.py run <script.py> [args ...]          # e.g. cell_windows.py <this folder> E5_J <out folder>

score.py --check is refused here: its recorded rows are the b0_r0 rows of the kit.
Standard library only.
"""
from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

sys.dont_write_bytecode = True
RA = Path(__file__).resolve().parents[1]                          # 4_vision/eval_llm_2026-11-12_rA
KIT = RA.parents[1] / "5_deliverables" / "llm_eval_kit_2026-11-08"


def load_score():
    spec = importlib.util.spec_from_file_location("score", KIT / "score.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["score"] = mod
    spec.loader.exec_module(mod)
    mod.HERE, mod.LABELS = RA, RA / "labels"
    return mod


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("score", "run"):
        print(__doc__)
        return 2
    mode, rest = sys.argv[1], sys.argv[2:]
    S = load_score()
    if mode == "score":
        if "--check" in rest:
            sys.exit("--check compares with the kit's b0_r0 rows; it does not apply to the b0_rA labels")
        sys.argv = [str(KIT / "score.py"), *rest]
        return S.main()
    script = Path(rest[0]).resolve()
    sys.argv = [str(script), *rest[1:]]
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
