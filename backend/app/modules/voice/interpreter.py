"""Reads an utterance in its session context into MCP cart tool inputs. Tools are not executed here."""

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.infrastructure.external.openai_client import OpenAiClient
from app.modules.voice.schemas import (
    CartLine, MenuItem, VoiceInterpretation, VoiceRequestCreate, VoiceTurn,
)

logger = logging.getLogger(__name__)

# Record this version with experiment results; add a new file for a new prompt.
PROMPT_VERSION = "interpret_v4"
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
    system: str, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn],
    cart: Sequence[CartLine] = (),
) -> list[dict[str, str]]:
    """Earlier exchanges become user/assistant messages; the menu and the current cart go
    with the latest one, so "하나 더" is read against what is actually in the cart."""
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
            "cart": [line.model_dump() for line in cart],
        },
        ensure_ascii=False,
    )})
    return messages


# What the kiosk asks when the model's own question cannot be shown (service.py asks the same).
ASK_MENU_REPLY = "어떤 메뉴를 주문할까요?"
_REPLY_MAX = VoiceInterpretation.model_fields["reply_text"].metadata[0].max_length


def tidy_output(result: dict) -> dict:
    """Mend reply_text slips that do not touch what would run, so a good order is not failed for them.

    The tool inputs are left as they are and still validated, and nothing here makes an order run
    without the customer's yes that would not have run before. A proposal's sentence is always
    rebuilt by the service from the tool inputs, so a missing or long one only needs a stand-in. A completed result that also carries a
    sentence ("담았어요", or a question) contradicts itself: it is read back as a proposal instead of
    run or failed. A question that is missing or too long to show becomes the plain menu question.
    """
    status, reply = result.get("status"), result.get("reply_text")
    said = isinstance(reply, str) and bool(reply.strip())
    usable = said and len(reply) <= _REPLY_MAX
    if status == "completed" and said and result.get("tool_calls"):
        return {**result, "status": "needs_confirmation", "reply_text": "?"}
    if status == "needs_confirmation" and not usable:
        return {**result, "reply_text": "?"}
    if status == "needs_clarification" and not usable:
        return {**result, "reply_text": ASK_MENU_REPLY}
    return result


class VoiceInterpreter(Protocol):
    async def interpret(
        self, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn],
        cart: Sequence[CartLine] = (),
    ) -> VoiceInterpretation | None:
        """None means the AI is unavailable or returned an unusable result."""


class StubVoiceInterpreter:
    """Development result used while OPENAI_API_KEY is unset. Never calls OpenAI."""

    async def interpret(
        self, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn],
        cart: Sequence[CartLine] = (),
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
        self, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn],
        cart: Sequence[CartLine] = (),
    ) -> VoiceInterpretation | None:
        result = await self._client.complete_json(
            build_messages(self._system, request, menu, history, cart),
            "voice_interpretation", _OUTPUT_SCHEMA,
        )
        if result is None:
            return None
        try:
            return VoiceInterpretation.model_validate(tidy_output(result))
        except ValidationError:
            logger.warning("OpenAI voice interpretation rejected (invalid output)")
            return None


class UnavailableVoiceInterpreter:
    """No key on a server set up for real use: every request fails as AI unavailable. Never calls OpenAI."""

    async def interpret(
        self, request: VoiceRequestCreate, menu: list[MenuItem], history: list[VoiceTurn],
        cart: Sequence[CartLine] = (),
    ) -> VoiceInterpretation | None:
        return None


def build_voice_interpreter(client: OpenAiClient | None, development: bool = True) -> VoiceInterpreter:
    """development=False (the cart is changed by voice, or orders are stored in the database): without a
    key the customer gets the outage reply, not the development sentence."""
    if client is None and not development:
        logger.error("OPENAI_API_KEY is not set; voice requests fail as AI unavailable")
        return UnavailableVoiceInterpreter()
    if client is None:
        logger.warning("OPENAI_API_KEY is not set; voice requests use development stub results")
        return StubVoiceInterpreter()
    return OpenAiVoiceInterpreter(client)
