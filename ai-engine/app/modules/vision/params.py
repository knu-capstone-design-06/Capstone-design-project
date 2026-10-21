"""Parameters of the runtime chain (perception -> optional columns -> windows -> rule table v0), each with a source.

Two kinds live here:
- PilotParams: the values the chain added on 2026-10-22 (head boxes, the optional columns, the runners' segment, the
  rule table v0). Every field has a default and a `source` text in its metadata. A value with no standard and no
  measured data behind it is tagged [파일럿] in its source: it is a start value to be replaced from sources or public
  data before the 2026-10-28 recording, or reported per value bundle (decision list 2026-10-13, items 3 and 19).
- events.PilotParams (re-exported here as SituationParams): the 13 values of the events and situation rules. They keep
  NO defaults on purpose (vision README '상황 층'; tests/test_situation.py checks it), so they only come from a value
  bundle file (load_bundle). Without one the runners still run and the situation output is 'unknown'.

Value bundle file (JSON; one per replay run, fixed before the run - D13 3 and 19):
    {"bundle_id": "...", "note": "...",
     "situation": {<each of the 13 events.PilotParams fields>: {"value": v, "source": "..."}},   # optional section;
                                                                                                 # all 13 when present
     "chain": {<PilotParams field>: {"value": v, "source": "..."}, ...}}   # optional overrides of the defaults below
Every value in the file carries its own non-empty source: the bundle is the one place where values are fixed before a
recording, and every constant names where it comes from. A bare value or an empty source is an error (ValueError naming
the field). Bundle.to_dict() records each value with its source and origin: 'bundle' (the file's source text),
'default' (a chain default with the source written below) or 'code' (set in code without a source, e.g. in tests).

Plain Python (dataclasses, json): no numpy, OpenCV or ONNX Runtime.
"""
from __future__ import annotations

import json
import math
import numbers
from dataclasses import dataclass, field, fields

from .events import PilotParams as SituationParams

PILOT = "[파일럿]"

# Mouth and jaw dials of the 52 MediaPipe blendshapes: the names of Apple ARKit's "Mouth and Jaw" group of
# ARFaceAnchor.BlendShapeLocation (MediaPipe's 52 names follow ARKit's), i.e. every name that starts with jaw or mouth.
MOUTH_AND_JAW_DIALS = (
    "jawForward", "jawLeft", "jawOpen", "jawRight", "mouthClose", "mouthDimpleLeft", "mouthDimpleRight",
    "mouthFrownLeft", "mouthFrownRight", "mouthFunnel", "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthPressLeft", "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower", "mouthRollUpper",
    "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft",
    "mouthStretchRight", "mouthUpperUpLeft", "mouthUpperUpRight",
)
PRIMARY_RULES = ("face_then_largest", "largest")


def _p(default, source: str, unit: str = ""):
    return field(default=default, metadata={"source": source, "unit": unit})


@dataclass(frozen=True)
class PilotParams:
    """Chain values with their sources (the `source` metadata of each field; PilotParams.sources())."""

    # --- head detector (perception/head.py) -------------------------------------------------------------------
    head_score_min: float = _p(
        0.65, "데이터(E3b): H1 README 결과 절, Open Images 검증 전부(h1_val_all) 입력 416에서 F1이 가장 큰 점수 기준 "
              "0.65(정밀도 0.682 · 재현율 0.676). 키오스크 시점 값 아님", "score 0~1")
    head_nms_iou: float = _p(
        0.65, "관행값: YOLOX 6ddff48 yolox/exp/yolox_base.py nmsthre 기본값(H1 평가 설정과 같음)", "IoU 0~1")

    # --- optional columns (columns.py) ------------------------------------------------------------------------
    primary_rule: str = _p(
        "face_then_largest", f"{PILOT} 규칙: Face Landmarker 얼굴 중심을 품은 머리 상자 가운데 가장 큰 것, 없으면 가장 "
                             "큰 머리 상자(같으면 화면 가운데에 가까운 것). 'largest' = 늘 가장 큰 상자")
    companion_min_area_ratio: float = _p(
        0.5, f"{PILOT} 시작값: 동행자 = 주 사용자 머리 넓이의 이 비율 이상(넓이 비 0.5 = 길이 비 약 0.71, 대략 1.4배 "
             "먼 머리까지 '비슷한 크기'). 결정 §3 '비슷한 크기의 두 번째 상자', 대본 §1-1 C는 A와 같은 거리",
        "area ratio")
    companion_max_dist_widths: float = _p(
        3.0, f"{PILOT} 시작값: 동행자 = 머리 중심 사이 거리가 주 사용자 머리 폭의 이 배수 이하. 결정 §3 '옆'",
        "primary head widths")
    behind_max_area_ratio: float = _p(
        1.0, "결정 §3 '주 사용자보다 작은 상자': 머리 넓이가 주 사용자의 이 비율 미만이면 뒤에 선 사람으로 셈(1.0 = 더 "
             "작기만 하면)", "area ratio")
    mouth_dials: tuple = _p(
        MOUTH_AND_JAW_DIALS, "Apple ARKit ARFaceAnchor.BlendShapeLocation의 'Mouth and Jaw' 묶음(jaw · mouth로 "
                             "시작하는 이름 27개); 결정 §3 '입 움직임(jawOpen 등 입 다이얼)'")
    mouth_baseline_s: float = _p(
        2.0, f"{PILOT} 시작값: 입 다이얼의 사람별 기준선 = 직전 이만큼(초)의 얼굴 프레임 중앙값(결정 목록 2026-10-10 "
             "§16: 기준선을 뺀 창 안 변동)", "s")

    # --- runners (replay.py, live.py) -------------------------------------------------------------------------
    segment_s: float = _p(
        1.0, f"계약 sendFeatureWindow의 '1~3초 구간' 안에서 고른 {PILOT} 값: 창 결과 한 줄의 간격이자 터치 횟수 · "
             "measurable을 세는 구간", "s")

    # --- rule table v0 (judgment/rule_table_v0.py) -------------------------------------------------------------
    touch_span_s: float = _p(
        5.0, f"{PILOT} 시작값: 터치 단서(4-1 빗나감, 4-2 되돌아감)를 세는 최근 구간 길이", "s")
    tremor_miss_min: int = _p(
        2, "정의: 트리 표 3-가 4-1 '빗나감 · 바로 고침 반복'의 반복 = 2번 이상(최근 구간 안의 버튼 밖 터치)", "count")
    tremor_miss_min_no_gaze: int = _p(
        3, f"{PILOT} 시작값: 고개 방향을 못 재는 창의 올린 기준(JP §0-2 '기준을 올린 확인 팝업', 트리 §4 ⑦) = "
           "tremor_miss_min보다 한 번 더", "count")
    lost_back_min: int = _p(
        1, "정의: 트리 표 3-가 4-2 '되돌아감'이 한 번이라도 있음(최근 구간 안)", "count")
    lost_pause_s: float = _p(
        8.0, f"{PILOT} 시작값: 4-2 '고른 뒤 멈춤' = 마지막 터치 뒤 이만큼 지남(남은 단계가 있는 화면)", "s")
    lost_pause_s_vision: float = _p(
        4.0, f"{PILOT} 시작값: 두리번(looking_around) 태그나 화면을 보는 고개가 있을 때 낮춘 멈춤 기준(JP §0-2 "
             "'확신을 올림' = 터치 근거 기준을 낮춤; 조정량은 기준 없음 → 값 묶음)", "s")
    no_response_s: float = _p(
        10.0, f"{PILOT} 시작값: 띄운 묻기에 반응이 없으면 무응답으로 거둠(JP §0-6 '무응답은 policy의 시간 [파일럿]')",
        "s")
    delay_notice_on: bool = _p(
        False, "평가 조건표 스위치(결정 목록 2026-10-10 §14, JP §0-2): 켜면 3-1의 허용 후보는 지연 책임 안내 하나")
    defer_option_on: bool = _p(
        True, "평가 조건표 스위치(JP §0-2): 3-1의 허용 후보에 '큰 버튼 질문 미룸'을 넣음(안내가 꺼진 조건)")

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "primary_rule":
                if value not in PRIMARY_RULES:
                    raise ValueError(f"PilotParams.primary_rule must be one of {PRIMARY_RULES}, got {value!r}")
            elif f.name == "mouth_dials":
                if not value or not all(isinstance(v, str) and v for v in value):
                    raise ValueError(f"PilotParams.mouth_dials must be a non-empty list of blendshape names, got {value!r}")
            elif isinstance(f.default, bool):
                if not isinstance(value, bool):
                    raise ValueError(f"PilotParams.{f.name} must be true or false, got {value!r}")
            elif isinstance(f.default, int):
                if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < 1:
                    raise ValueError(f"PilotParams.{f.name} is a count and must be a whole number >= 1, got {value!r}")
            else:
                if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value) \
                        or value <= 0:
                    raise ValueError(f"PilotParams.{f.name} must be a finite number > 0, got {value!r}")
                if f.name in ("head_score_min", "head_nms_iou") and value > 1:
                    raise ValueError(f"PilotParams.{f.name} is a score / IoU and must be at most 1, got {value!r}")

    @staticmethod
    def sources() -> dict:
        """{field: source text} of every field."""
        return {f.name: f.metadata["source"] for f in fields(PilotParams)}

    @staticmethod
    def pilot_fields() -> list:
        """The fields whose default value has no standard and no measured data ([파일럿] in the source)."""
        return [f.name for f in fields(PilotParams) if _is_pilot(f.metadata["source"])]

    def to_dict(self) -> dict:
        """{field: {"value", "source", "unit"}} with each field's default source (the code's view; the runners record
        Bundle.to_dict(), which names where each value came from)."""
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            out[f.name] = {"value": list(value) if isinstance(value, tuple) else value,
                           "source": f.metadata["source"], "unit": f.metadata["unit"]}
        return out

    @classmethod
    def from_dict(cls, values: dict) -> "PilotParams":
        """Defaults overridden by plain values {field: value}; unknown names are errors. A bundle file goes through
        load_bundle, which also requires a source for every value."""
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(values) - names)
        if unknown:
            raise ValueError(f"unknown chain parameter(s) {unknown}; known: {sorted(names)}")
        clean = dict(values)
        if "mouth_dials" in clean:
            clean["mouth_dials"] = tuple(clean["mouth_dials"])
        return cls(**clean)


def _is_pilot(source: str | None) -> bool:
    return isinstance(source, str) and (source.startswith(PILOT) or f" {PILOT}" in source)


SOURCED_FORM = '{"value": <value>, "source": "<where the value comes from>"}'


def _split(section: str, entries: dict, names: list) -> tuple:
    """({field: value}, {field: source}) of one bundle section. Every entry must be {"value": v, "source": text}
    with a non-empty text; anything else raises ValueError naming the field and the required form."""
    if not isinstance(entries, dict):
        raise ValueError(f"value bundle section {section!r} must be an object {{field: {SOURCED_FORM}}}")
    unknown = sorted(set(entries) - set(names))
    if unknown:
        raise ValueError(f"value bundle section {section!r}: unknown name(s) {unknown}; known: {sorted(names)}")
    values, sources = {}, {}
    for name, entry in entries.items():
        if not isinstance(entry, dict) or "value" not in entry:
            raise ValueError(f"value bundle {section}.{name}: write it as {SOURCED_FORM}, got {entry!r}")
        extra = sorted(set(entry) - {"value", "source"})
        if extra:
            raise ValueError(f"value bundle {section}.{name}: unknown key(s) {extra}; write it as {SOURCED_FORM}")
        source = entry.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"value bundle {section}.{name}: the source is missing or empty; write it as "
                             f"{SOURCED_FORM}")
        values[name], sources[name] = entry["value"], source
    return values, sources


@dataclass(frozen=True)
class Bundle:
    """One value bundle: the chain values and, when the file has them, the 13 situation values. sources = {field:
    source text given in the bundle file} (empty for a Bundle built in code); the chain and situation fields share no
    name, so one dict holds both."""
    chain: PilotParams
    situation: SituationParams | None
    bundle_id: str = ""
    note: str = ""
    path: str = ""
    sources: dict = field(default_factory=dict)

    def _chain_entry(self, f) -> tuple:
        """(source, origin) of one chain field: the file's text, else the default's source when the value is the
        default, else None (set in code without a source)."""
        if f.name in self.sources:
            return self.sources[f.name], "bundle"
        if getattr(self.chain, f.name) == f.default:
            return f.metadata["source"], "default"
        return None, "code"

    def pilot_fields(self) -> list:
        """The chain fields whose recorded source carries [파일럿] (an override keeps its own source)."""
        return [f.name for f in fields(self.chain) if _is_pilot(self._chain_entry(f)[0])]

    def to_dict(self) -> dict:
        """The bundle as the runners record it: chain {field: {"value", "unit", "source", "origin"}} with origin
        'bundle' | 'default' | 'code', situation {field: {"value", "source", "origin"}} with origin 'bundle' | 'code'
        (source None when the Bundle was built in code), or None without situation values."""
        chain = {}
        for f in fields(self.chain):
            value = getattr(self.chain, f.name)
            source, origin = self._chain_entry(f)
            chain[f.name] = {"value": list(value) if isinstance(value, tuple) else value, "unit": f.metadata["unit"],
                             "source": source, "origin": origin}
        situation = None
        if self.situation is not None:
            situation = {f.name: {"value": getattr(self.situation, f.name), "source": self.sources.get(f.name),
                                  "origin": "bundle" if f.name in self.sources else "code"}
                         for f in fields(self.situation)}
        return {"bundle_id": self.bundle_id, "note": self.note, "path": self.path, "chain": chain,
                "situation": situation}


def situation_from_dict(values: dict) -> SituationParams:
    """All 13 situation values as plain values, no defaults (events.PilotParams checks the ranges)."""
    names = [f.name for f in fields(SituationParams)]
    missing = [n for n in names if n not in values]
    unknown = sorted(set(values) - set(names))
    if missing or unknown:
        raise ValueError(f"situation section: missing {missing}, unknown {unknown} (all 13 events.PilotParams "
                         f"fields are needed, none has a default)")
    return SituationParams(**{n: values[n] for n in names})


def load_bundle(path: str | None) -> Bundle:
    """The value bundle at path, or the chain defaults and no situation values when path is None. Every value in the
    file must be {"value": v, "source": "..."} (module docstring)."""
    if path is None:
        return Bundle(PilotParams(), None)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    unknown = sorted(set(data) - {"bundle_id", "note", "situation", "chain"})
    if unknown:
        raise ValueError(f"{path}: unknown top-level key(s) {unknown}")
    chain_values, sources = _split("chain", data.get("chain") or {}, [f.name for f in fields(PilotParams)])
    situation = None
    if data.get("situation") is not None:
        situation_values, situation_sources = _split("situation", data["situation"],
                                                     [f.name for f in fields(SituationParams)])
        situation = situation_from_dict(situation_values)
        sources = {**sources, **situation_sources}
    return Bundle(PilotParams.from_dict(chain_values), situation, str(data.get("bundle_id", "")),
                  str(data.get("note", "")), path, sources)
