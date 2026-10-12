from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=20)]
Temperature = Literal["iced", "hot"] | None
VoiceStatus = Literal[
    "accepted", "processing", "completed", "needs_confirmation", "needs_clarification", "failed",
]
VoiceAction = Literal["cart_updated", "ui_changed", "confirmation_required"]
VoiceErrorCode = Literal[
    "invalid_request", "session_not_found", "voice_request_not_found",
    "request_in_progress", "idempotency_key_reused", "ai_unavailable",
]


class RecognitionAlternative(BaseModel):
    text: str = Field(max_length=500)
    confidence: Confidence | None


class VoiceRequestCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    alternatives: list[RecognitionAlternative] = Field(max_length=5)
    screen_id: str

    @field_validator("text")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class MenuItem(BaseModel):
    """Product fields the interpreter needs, as in the product-cart-order draft."""

    product_id: str
    name: str
    available: bool
    temperatures: list[Literal["iced", "hot"]]


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CartItemTarget(_Arguments):
    # MCP tools resolve item_id, expected_version and Idempotency-Key from the cart.
    product_id: str
    temperature: Temperature


class CartItemQuantity(CartItemTarget):
    quantity: Quantity


class AddCartItemCall(_Arguments):
    tool: Literal["add_cart_item"]
    arguments: CartItemQuantity


class UpdateCartItemCall(_Arguments):
    """quantity is the absolute value after the change."""

    tool: Literal["update_cart_item"]
    arguments: CartItemQuantity


class RemoveCartItemCall(_Arguments):
    tool: Literal["remove_cart_item"]
    arguments: CartItemTarget


ToolCall = Annotated[
    AddCartItemCall | UpdateCartItemCall | RemoveCartItemCall, Field(discriminator="tool")
]


class VoiceInterpretation(BaseModel):
    """Interpreter output.

    completed: tool_calls are ready for MCP. needs_confirmation: tool_calls are a
    proposal awaiting the user's answer. needs_clarification: question only.
    """

    status: Literal["completed", "needs_confirmation", "needs_clarification"]
    tool_calls: list[ToolCall] = Field(max_length=10)
    # Short enough to read at a glance on the kiosk.
    reply_text: str | None = Field(max_length=60)

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        needs_calls = self.status != "needs_clarification"
        needs_reply = self.status != "completed"
        if bool(self.tool_calls) != needs_calls:
            raise ValueError(f"{self.status} tool_calls mismatch")
        if bool(self.reply_text and self.reply_text.strip()) != needs_reply:
            raise ValueError(f"{self.status} reply_text mismatch")
        return self


class VoiceTurn(BaseModel):
    """One exchange kept as per-session context: what the user said and how it was read."""

    request: VoiceRequestCreate
    result: VoiceInterpretation


class VoiceRequestAccepted(BaseModel):
    request_id: str
    status: Literal["accepted"] = "accepted"
    accepted_at: AwareDatetime


class VoiceErrorResponse(BaseModel):
    code: VoiceErrorCode
    detail: str


class VoiceRequestStatus(BaseModel):
    request_id: str
    status: VoiceStatus
    reply_text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    actions: list[VoiceAction] = Field(default_factory=list)
    error: VoiceErrorResponse | None = None
