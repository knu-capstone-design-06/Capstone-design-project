"""One window record -> the existing contract shapes plus an `extension` dict (a proposal, not a contract change).

contract/backend-ai.openapi.yaml 0.2.0 (AnalyzeResponse) and contract/frontend-backend.openapi.yaml
(FeatureWindowResponse.support = SupportDecision) stay as they are (AGENTS.md section 2). What they cannot carry yet -
the situation tag, its evidence, why it is unknown, the alternatives, and the rule table's decision meta - goes into
`extension`, which the vision README proposes as an additive optional field (JP 2-5 `decision_meta`; the 2026-10-14
agenda V04 '상황 태그를 실을 명세 칸').

  analyze_response  {session_id, measurable, states, model_version}: measurable as the team placeholder defines it
                    (app/inference/placeholder.py: a tap or back in the segment, or a face); states = None because
                    no discomfort-state model exists in this chain
  support           {preset, requires_confirmation, decided_by}: UIPreset and the confirmation flag of the rule table's
                    support (JP 2-5 table); decided_by 'rule_placeholder' (shadow mode: Jev never changes the screen)
  extension         {situation: {...}, decision_meta: {...}}; decision_meta also carries the execution fields of
                    JP 2-5 (steps_left, target_id, message_id) and session_signal ({name: hold_timer} on the 3-2 wait)
"""
from __future__ import annotations

MODEL_VERSION = "vision-situation-rules_v1+rule_table_v0-shadow"
DECIDED_BY = "rule_placeholder"     # contract SupportDecision.decided_by enum: rule_placeholder | jev


def to_contract(record: dict, session_id: str) -> dict:
    d = record["decision"]
    sit = record["situation"]
    return {
        "analyze_response": {"session_id": session_id, "measurable": bool(record["measurable"]), "states": None,
                             "model_version": MODEL_VERSION},
        "support": {"preset": d["preset"], "requires_confirmation": bool(d["requires_confirmation"]),
                    "decided_by": DECIDED_BY},
        "extension": {
            "situation": {"tag": sit["name"], "display_text": sit["display_text"], "evidence_ids": sit["evidence_ids"],
                          "confidence": sit["confidence"], "alternatives": sit["alternatives"],
                          "unknown_reason": sit["unknown_reason"], "quality": sit["quality"], "source": sit["source"]},
            "decision_meta": {k: d[k] for k in ("decision_id", "withdrawn_id", "support", "scene", "action",
                                                "intervention", "transition", "scope", "rank", "withdraw_on",
                                                "policy", "meta", "steps_left", "target_id", "message_id",
                                                "session_signal")}
                             | {"jev_kind": (record.get("jev") or {}).get("kind"),
                                "jev": None if not record.get("jev") else {"shadow": True, "applied": False,
                                                                           "answer": None}},
        },
    }
