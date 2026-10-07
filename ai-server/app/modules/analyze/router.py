from fastapi import APIRouter

from app.inference import placeholder
from app.modules.analyze.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter(prefix="/v1", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse, operation_id="analyzeWindow")
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Judge one time window. Stateless: nothing is kept between calls."""
    states = placeholder.judge(request)
    return AnalyzeResponse(
        session_id=request.session_id,
        measurable=states is not None,
        states=states,
        model_version=placeholder.MODEL_VERSION,
    )
