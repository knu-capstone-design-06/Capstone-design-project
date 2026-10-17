from typing import Literal

from app.infrastructure.external.ai_client import AiEngineClient


async def check_connectivity(ai: AiEngineClient) -> Literal["ok", "unreachable"]:
    return "ok" if await ai.health() is not None else "unreachable"
