"""The cells of the paper's 표 4 under bundle b0_rA, from answer files. No model call.

Counts: the kit's scorer (5_deliverables/llm_eval_kit_2026-11-08/score.py, imported unchanged through tools/kit_rA.py,
so the rule table's fallback decisions are this folder's b0_rA labels/window_cells.csv). Metrics: cm_metrics of
4_vision/eval_llm_2026-11-09/tools/score_scen_f1_macro.py, the definitions 4_vision/eval_ab_2026-11-04/tools/
rescore_macro_f1.py uses for the b0_r0 표 4: help F1 = 2TP/(2TP+FP+FN), wait F1 = 2TN/(2TN+FN+FP),
Macro-F1 = their mean.

Rows (as rescore_macro_f1.py T4): rule table = its own decisions; Jev = reference_answers/<arm>.jsonl (the recorded
jev-1.13.0 answers of the 2026-11-05 b0_rA run); models = <runs>/<model id>_E5_C0/answers.jsonl and
<runs>/<model id>_E5_J_cells/answers.jsonl (default <runs> = this folder's runs/), a row is 'not run' while its file
is missing. Checks printed: answers all null (every asked window falls back to the rule table) give the rule row in
both arms; Jev restricted to the J cell windows (prep/E5_J_jev_restricted.jsonl) gives the unrestricted Jev J row.

  python table4_rA.py [--runs <folder>] [--json-out <file>]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RA = HERE.parent
WS = RA.parents[1]
sys.path.insert(0, str(HERE))
import kit_rA  # noqa: E402

S = kit_rA.load_score()
spec = importlib.util.spec_from_file_location(
    "score_scen_f1_macro", WS / "4_vision" / "eval_llm_2026-11-09" / "tools" / "score_scen_f1_macro.py")
SM = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SM)

ROWS = [("규칙 기반 판단", None), ("Jev", "jev"), ("gpt-4o-mini", "gpt-4o-mini-2024-07-18"),
        ("gpt-5.4-mini", "gpt-5.4-mini-2026-03-17"), ("gpt-6.1-sol", "gpt-6.1-sol"),
        ("Haiku 5.5", "claude-haiku-5-5"), ("Sonnet 5.5", "claude-sonnet-5-5")]
ARMS = (("후보 내", "E5_C0", "E5_C0"), ("후보 제한 없음", "E5_J", "E5_J_cells"))


def counts(wins, cells, tstart, data_arm: str | None, answers: dict | None) -> dict:
    if data_arm is None:
        sel = {w["window_id"]: S.rule_choice(w) for w in wins}
    else:
        asked = {x["window_id"]: x["stages"][-1]["options"] for x in S.read_jsonl(RA / "data" / f"{data_arm}.jsonl")}
        sel, _ = S.selections(wins, asked, answers or {})
    return S.score(wins, cells, tstart, sel)


def read_answers(p: Path) -> dict:
    return {x["window_id"]: x.get("choice") for x in S.read_jsonl(p)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=RA / "runs")
    ap.add_argument("--json-out", type=Path)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    wins, cells, tstart = S.load_labels()
    rule = counts(wins, cells, tstart, None, None)
    key = lambda s: (s["TP"], s["FP"], s["FN"], s["TN"])
    checks = []
    for _, data_arm, _ in ARMS:
        s = counts(wins, cells, tstart, data_arm, {})
        checks.append((f"{data_arm}: all-null answers give the rule row {key(rule)}: {key(s)}", key(s) == key(rule)))
    jev_j = counts(wins, cells, tstart, "E5_J", read_answers(RA / "reference_answers" / "E5_J.jsonl"))
    jev_jr = counts(wins, cells, tstart, "E5_J", read_answers(RA / "prep" / "E5_J_jev_restricted.jsonl"))
    checks.append((f"E5_J: Jev restricted to the cell windows {key(jev_jr)} = Jev on every window {key(jev_j)}",
                   key(jev_jr) == key(jev_j)))
    out = {}
    lines = ["| 판단 모델 | 후보 내 TP/FP/FN/TN | 도움 F1 | 대기 F1 | Macro-F1 | 후보 제한 없음 TP/FP/FN/TN | 도움 F1 | 대기 F1 | "
             "Macro-F1 | source |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, mid in ROWS:
        cols, srcs = [], []
        out[name] = {}
        for arm_ko, data_arm, suffix in ARMS:
            if mid is None:
                s, src = rule, "rule table's own decisions"
            elif mid == "jev":
                p = RA / "reference_answers" / f"{data_arm}.jsonl"
                s, src = counts(wins, cells, tstart, data_arm, read_answers(p)), f"reference_answers/{data_arm}.jsonl"
            else:
                p = a.runs / f"{mid}_{suffix}" / "answers.jsonl"
                if not p.is_file():
                    cols += ["not run", "", "", ""]
                    srcs.append(f"{p.parent.name}: missing")
                    out[name][arm_ko] = None
                    continue
                s, src = counts(wins, cells, tstart, data_arm, read_answers(p)), str(p.relative_to(a.runs.parent))
            m = SM.cm_metrics(s["TP"], s["FP"], s["FN"], s["TN"])
            cols += ["/".join(map(str, key(s))), SM.f3(m["f1_help"]), SM.f3(m["f1_wait"]), SM.f3(m["macro_f1"])]
            srcs.append(src)
            out[name][arm_ko] = {"counts": key(s), "dsr": s["dsr"], "c4": s["c4"], "source": src, **m}
        lines.append(f"| {name} | " + " | ".join(cols) + " | " + "; ".join(srcs) + " |")
    for c, ok in checks:
        print(f"{'OK  ' if ok else 'FAIL'} {c}")
    print()
    print("\n".join(lines))
    if a.json_out:
        a.json_out.write_text(json.dumps({"rows": out, "checks": [{"check": c, "ok": ok} for c, ok in checks]},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
