from fastapi import APIRouter, Depends

from app.infrastructure.external.ai_client import AiEngineClient, get_ai_engine_client
from app.modules.connectivity.service import check_connectivity
from app.modules.connectivity.schemas import ConnectivityResponse

router = APIRouter(prefix="/api/v1", tags=["connectivity"])


@router.get("/connectivity", response_model=ConnectivityResponse)
async def connectivity(ai: AiEngineClient = Depends(get_ai_engine_client)):
    return ConnectivityResponse(ai_engine=await check_connectivity(ai))
