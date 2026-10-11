"""상황 (situation) layer - a documented placeholder: the situation-tag interface and an empty rule table.

Layers of the vision path, as in the vision owner's plan (research/26 section 4 step 2: (a) skeleton, (b) rules after
the cases are settled; before-after table 27 v3.1):

  입력 sources.py -> 추론 inference.py -> 관측값 features.py -> 상황 this file -> 전달 (contract/, not built yet)

A situation tag names what a window of observations suggests, like the 'judgment' column of table A in doc 27
(e.g. a person approaching the screen). No tag is defined and RULES is empty on purpose: which situations the
camera has to supply waits for the open decisions D2-D4 of doc 27 (section 4) and for the analysis of the AI Hub
dataset 71827. Each rule added later names its source - a standard, measured data, or a start value marked
[파일럿] for the pilot to calibrate. Nothing in this file sets a threshold, and run.py does not call it yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class SituationTag:
    name: str                          # tag name as the team's documents will name it
    window: tuple[float, float]        # (start, end) of the observation window in seconds of frame time (t_s)
    evidence: dict = field(default_factory=dict)   # the observation values the rule used
    source: str = ""                   # where the rule comes from: standard, data analysis, or [파일럿]


# tag name -> (rule, source); a rule reads the observation rows (features.COLUMNS) of one window and returns the
# evidence it used, or None when the situation does not apply. Empty until decisions D2-D4 and the 71827 analysis.
RULES: dict[str, tuple[Callable[[list], dict | None], str]] = {}


def tags_for(rows: list, window: tuple[float, float]) -> list[SituationTag]:
    """Situation tags for the observation rows of one window; [] while RULES is empty. The window length is not
    fixed here: the 1-second window in the design notes is marked [파일럿] with "길이의 출처는 없음" (research/25)."""
    tags = []
    for name, (rule, source) in RULES.items():
        evidence = rule(rows)
        if evidence is not None:
            tags.append(SituationTag(name, window, evidence, source))
    return tags
