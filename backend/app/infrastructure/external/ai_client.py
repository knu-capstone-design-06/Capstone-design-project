"""Internal AI transport. Callers retain their current UI on unavailable results."""

import asyncio
import logging

import httpx
from fastapi import Request

from app.infrastructure.external.ai_schemas import (
    AiHealthResponse,
    AnalyzeRequest,
    AnalyzeResponse,
)


logger = logging.getLogger(__name__)


class AiServerClient:
    """Uses an application-owned HTTP client; no automatic retries.

    None means transport/response failure, while measurable=False is a valid
    AI response. Neither case authorizes a new assistance decision.
    """

    def __init__(self, http: httpx.AsyncClient, timeout_seconds: float = 2.0):
        self._http = http
        self._timeout_seconds = timeout_seconds

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse | None:
        try:
            # HTTPX timeouts apply per I/O phase. This also caps the full call.
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._http.post(
                    "/v1/analyze",
                    json=request.model_dump(mode="json", exclude_unset=True),
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                result = AnalyzeResponse.model_validate(response.json())
                if result.session_id != request.session_id:
                    raise ValueError("AI response session mismatch")
                return result
        except (TimeoutError, httpx.HTTPError, ValueError) as exc:
            # Do not log camera/touch features, transcripts or response bodies.
            logger.warning("AI analysis unavailable (%s)", type(exc).__name__)
            return None

    async def health(self) -> AiHealthResponse | None:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._http.get(
                    "/health", timeout=self._timeout_seconds
                )
                response.raise_for_status()
                return AiHealthResponse.model_validate(response.json())
        except (TimeoutError, httpx.HTTPError, ValueError) as exc:
            logger.warning("AI health unavailable (%s)", type(exc).__name__)
            return None


def get_ai_server_client(request: Request) -> AiServerClient:
    """Inject with Depends(get_ai_server_client) in a future backend router."""
    return request.app.state.ai_server_client
