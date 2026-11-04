"""External Jev (TypeSafe AI) transport. Questions and what answers mean belong to the caller.

Only the backend calls external AI APIs (AGENTS.md 4): ai-engine builds the question,
the backend sends it. Same shape as openai_client.py: application-owned HTTP client,
one total deadline, no retries, None on any failure.
"""

import asyncio
import logging

import httpx
from pydantic import ValidationError

from app.infrastructure.external.jev_schemas import JevRequest, JevResponse

logger = logging.getLogger(__name__)

JEV_BASE_URL = "https://api.typesafe.ai"


class JevClient:
    """None means transport, HTTP (4xx, 5xx, 429, 529), timeout or response-format failure.

    The configured model replaces the request's: experiments pin one version in the
    backend settings, so a question built elsewhere never picks a moving alias.
    """

    def __init__(self, http: httpx.AsyncClient, model: str, timeout_seconds: float = 3.0):
        # model comes from Settings.jev_model: the one place the pinned version lives.
        self._http = http
        self._model = model
        self._timeout_seconds = timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def ask(self, request: JevRequest) -> JevResponse | None:
        body = request.model_dump(mode="json")
        body["model"] = self._model
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._http.post(
                    "/v1/systemone", json=body, timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                return JevResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            # Do not log the state, the answers or the key.
            logger.warning("Jev answer unavailable (HTTP %s)", exc.response.status_code)
            return None
        except (TimeoutError, httpx.HTTPError, ValidationError, ValueError, TypeError) as exc:
            logger.warning("Jev answer unavailable (%s)", type(exc).__name__)
            return None


def create_jev_http(api_key: str, base_url: str, timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout_seconds,
        trust_env=False,
        follow_redirects=False,
    )
