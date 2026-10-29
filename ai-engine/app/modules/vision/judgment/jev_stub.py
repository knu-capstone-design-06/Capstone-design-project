"""Jev stub in shadow mode (JP v2.2 section 0-9: 그림자 모드로 시작).

The rule table builds the Jev question of a decision (`jev_request`, JP section 2-2: model, state, questions); this
stub only records it. Nothing is sent anywhere: external AI APIs (STT, LLM, Jev) are called by the backend, never by
ai-engine (AGENTS.md section 4), and the screen follows the rule result while no threshold (T_LOWER, T_AID, T_CHOICE)
has a value (JP section 0-5: 기준 없음). A later backend adapter answers the same request; `answer` stays None here.
"""
from __future__ import annotations

from typing import Protocol

JEV_MODEL = "jev-1.13.0"   # JP section 1: the version is pinned (`/models`); used in the request only


class JevAdapter(Protocol):
    """What a backend adapter would offer: one call per decision opening (JP section 0-7)."""

    def ask(self, kind: str, request: dict) -> dict: ...


class ShadowJev:
    """Records each question with its kind ('fit' | 'choice' | 'aid'); answer None, applied False, shadow True."""

    def __init__(self):
        self.log: list = []

    def ask(self, kind: str, request: dict) -> dict:
        entry = {"kind": kind, "request": request, "answer": None, "shadow": True, "applied": False,
                 "decided_by": "rule_placeholder"}
        self.log.append(entry)
        return entry
