"""Placeholder for the discomfort-state model.

The real model (PyTorch -> ONNX in the project plan) does not exist yet. This
module computes nothing: it returns the example scores written in
contract/backend-ai.openapi.yaml so the services can be wired and tested.
Do not use its output for a real UI decision.
"""

from app.modules.analyze.schemas import AnalyzeRequest, StateScores

# Both values are the contract's "dummy-0.1" example.
MODEL_VERSION = "dummy-0.1"
EXAMPLE_SCORES = StateScores(
    normal=0.167,
    touch_difficulty=0.833,
    navigation_difficulty=0,
    visual_difficulty=0.056,
    hesitation=0.1,
)


def judge(request: AnalyzeRequest) -> StateScores | None:
    """Return None when the window holds nothing to judge (measurable=false)."""
    touch = request.touch
    has_touch = touch.tap_count > 0 or touch.back_count > 0
    has_face = request.vision is not None and request.vision.face_detected
    if not has_touch and not has_face:
        return None
    return EXAMPLE_SCORES
