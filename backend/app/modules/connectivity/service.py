from typing import Literal

from app.infrastructure.external.ai_client import AiServerClient


async def check_connectivity(ai: AiServerClient) -> Literal["ok", "unreachable"]:
    return "ok" if await ai.health() is not None else "unreachable"
