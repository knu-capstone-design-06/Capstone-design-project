"""The part of E3's harness (4_vision/eval_ab_2026-11-04/tools/harness.py in the author's workspace) that help_rule.py
reads: LABELS, FORM, VISIBLE and load_labels(), copied unchanged. The full harness imports the vision module
(ai-engine/app/modules/vision, numpy); help_rule needs none of that, so this package ships only these lines and
help_rule.py byte for byte (sha256 0e3584a7..., the hash in results/manifest.json scoring.help_rule_module).

LABELS: the judgment labels whose segment starts (t_start) the help rule reads; metrics.py sets EVAL_LABELS to the
scoring's judgment-label file before help_rule is imported.
"""
from __future__ import annotations

import csv
import os

LABELS = os.environ.get("EVAL_LABELS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "inputs",
                                                    "labels", "judgment_labels_v4.csv"))
FORM = {"wait": "기다림", "propose": "묻기", "apply": "바로 적용", "call_staff": "직원 호출"}   # rule_table_v0.INTERVENTION
VISIBLE = {"propose", "apply", "call_staff"}     # 평가 설계 v1.4 §2-2: 보이는 행동 = 묻기 · 바로 적용 · 직원 호출


def load_labels() -> dict:
    """take -> list of segments (dicts) sorted by t_start."""
    out = {}
    with open(LABELS, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r["t_start"], r["t_end"] = float(r["t_start"]), float(r["t_end"])
            r["allowed_set"] = set(a.strip() for a in r["allowed"].split(";") if a.strip())
            out.setdefault(r["take"], []).append(r)
    for v in out.values():
        v.sort(key=lambda s: s["t_start"])
    return out
