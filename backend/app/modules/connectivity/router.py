from fastapi import APIRouter, Depends

from app.infrastructure.external.ai_client import AiServerClient, get_ai_server_client
from app.modules.connectivity.service import check_connectivity
from app.modules.connectivity.schemas import ConnectivityResponse

router = APIRouter(prefix="/api/v1", tags=["connectivity"])


@router.get("/connectivity", response_model=ConnectivityResponse)
async def connectivity(ai: AiServerClient = Depends(get_ai_server_client)):
    return ConnectivityResponse(ai_server=await check_connectivity(ai))
