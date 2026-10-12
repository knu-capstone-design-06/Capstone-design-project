"""External OpenAI transport. Prompts and output meaning belong to the caller."""

import asyncio
import json
import logging

import httpx

from app.infrastructure.external.ai_schemas import JsonObject


logger = logging.getLogger(__name__)

OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAiClient:
    """Uses an application-owned HTTP client; no automatic retries.

    None means transport, HTTP or response-format failure. Callers decide the
    user-facing fallback and must validate the returned object themselves.
    """

    def __init__(self, http: httpx.AsyncClient, model: str, timeout_seconds: float = 10.0):
        self._http = http
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def complete_json(
        self, messages: list[dict[str, str]], schema_name: str, schema: JsonObject
    ) -> JsonObject | None:
        """messages are chat messages ({role, content}) in order, system first."""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._http.post(
                    "/chat/completions",
                    json={
                        "model": self._model,
                        "messages": messages,
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": schema_name, "strict": True, "schema": schema,
                            },
                        },
                    },
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                result = json.loads(content)
                if not isinstance(result, dict):
                    raise ValueError("OpenAI response is not a JSON object")
                return result
        except (TimeoutError, httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            # Do not log transcripts, prompts, keys or response bodies.
            logger.warning("OpenAI completion unavailable (%s)", type(exc).__name__)
            return None


def create_openai_http(api_key: str, timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=OPENAI_BASE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout_seconds,
        trust_env=False,
        follow_redirects=False,
    )
