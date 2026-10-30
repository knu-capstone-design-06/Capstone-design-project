"""Reads an utterance in its session context into MCP cart tool inputs. Tools are not executed here."""

import json
import logging
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.infrastructure.external.openai_client import OpenAiClient
from app.modules.voice.schemas import (
    MenuItem, VoiceInterpretation, VoiceRequestCreate, VoiceTurn,
)

logger = logging.getLogger(__name__)

# Record this version with experiment results; add a new file for a new prompt.
PROMPT_VERSION = "interpret_v3"
_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"

_TEMPERATURE = {"type": ["string", "null"], "enum": ["iced", "hot", None]}
_QUANTITY = {"type": "integer", "minimum": 1, "maximum": 20}


def _tool_schema(tool: str, with_quantity: bool) -> dict:
    properties = {"product_id": {"type": "string"}, "temperature": _TEMPERATURE}
    if with_quantity:
        properties["quantity"] = _QUANTITY
    return {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "enum": [tool]},
            "arguments": {
                "type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False,
            },
        },
        "required": ["tool", "arguments"],
        "additionalProperties": False,
    }


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["completed", "needs_confirmation", "needs_clarification", "ignored"],
        },
        "tool_calls": {
            "type": "array",
            "items": {"anyOf": [
                _tool_schema("add_cart_item", True),
                _tool_schema("update_cart_item", True),
                _tool_schema("remove_cart_item", False),
            ]},
        },
        "reply_text": {"type": ["string", "null"]},
    },
    "required": ["status", "tool_calls", "reply_text"],
    "additionalProperties": False,
}

_UTTERANCE_FIELDS = {"text", "alternatives", "screen_id"}


def build_messages(
    system: str, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn]
) -> list[dict[str, str]]:
    """Earlier exchanges become user/assistant messages; the menu goes with the latest one."""
    messages = [{"role": "system", "content": system}]
    for turn in history:
        messages.append({"role": "user", "content": json.dumps(
            turn.request.model_dump(include=_UTTERANCE_FIELDS), ensure_ascii=False
        )})
        messages.append({"role": "assistant", "content": turn.result.model_dump_json()})
    messages.append({"role": "user", "content": json.dumps(
        {
            **request.model_dump(include=_UTTERANCE_FIELDS),
            "menu": [item.model_dump() for item in menu],
        },
        ensure_ascii=False,
    )})
    return messages


class VoiceInterpreter(Protocol):
    async def interpret(
        self, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn]
    ) -> VoiceInterpretation | None:
        """None means the AI is unavailable or returned an unusable result."""


class StubVoiceInterpreter:
    """Development result used while OPENAI_API_KEY is unset. Never calls OpenAI."""

    async def interpret(
        self, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn]
    ) -> VoiceInterpretation | None:
        return VoiceInterpretation(
            status="needs_clarification", tool_calls=[],
            reply_text="개발용 응답이에요. 음성 해석이 연결되지 않았어요.",
        )


class OpenAiVoiceInterpreter:
    def __init__(self, client: OpenAiClient):
        self._client = client
        self._system = _PROMPT_PATH.read_text(encoding="utf-8")

    async def interpret(
        self, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn]
    ) -> VoiceInterpretation | None:
        result = await self._client.complete_json(
            build_messages(self._system, request, menu, history),
            "voice_interpretation", _OUTPUT_SCHEMA,
        )
        if result is None:
            return None
        try:
            return VoiceInterpretation.model_validate(result)
        except ValidationError:
            logger.warning("OpenAI voice interpretation rejected (invalid output)")
            return None


def build_voice_interpreter(client: OpenAiClient | None) -> VoiceInterpreter:
    if client is None:
        logger.warning("OPENAI_API_KEY is not set; voice requests use development stub results")
        return StubVoiceInterpreter()
    return OpenAiVoiceInterpreter(client)
