import hashlib
import logging
import re
from collections import Counter
from collections.abc import Callable, Iterable
from uuid import UUID

from app.modules.ordering.repository import OrderingRepository
from app.modules.voice.exceptions import VoiceRequestNotFound, VoiceSessionNotFound
from app.modules.voice.executor import (
    FALLBACK_EXECUTION_REPLY, CartChanged, CartExecutor, ToolExecutionFailed,
)
from app.modules.voice.interpreter import VoiceInterpreter
from app.modules.voice.repository import VoiceRepository
from app.modules.voice.schemas import (
    AddCartItemCall, CartItemQuantity, CartItemTarget, CartLine, MenuItem, RemoveCartItemCall,
    UpdateCartItemCall, VoiceErrorResponse, VoiceInterpretation, VoiceRequestAccepted,
    VoiceRequestCreate, VoiceRequestStatus, VoiceTurn,
)

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "지금은 음성 주문이 어려워요. 화면을 눌러 주문해 주세요."
# Plain acceptances: they take a proposal as it stands and cannot pick an option such
# as a temperature. "어" is left out because "어?" is a question, not a yes.
BARE_YES = {"네", "넵", "예", "응", "그래", "그래요", "좋아요", "맞아요"}
TEMPERATURE_WORDS = {"iced": "아이스", "hot": "따뜻한"}
REPLY_MAX = 60


def is_bare_yes(text: str) -> bool:
    return "".join(ch for ch in text if ch.isalnum()) in BARE_YES


SPLIT_ORDER_REPLY = "주문이 길어요. 두 가지씩 나눠서 말씀해 주세요."


def confirmation_text(tool_calls: list, menu: list[MenuItem]) -> str | None:
    """Word the confirmation from the validated tool inputs, never from the model.

    The model's reply_text and tool_calls are separate outputs and may disagree
    ("2잔 담을까요?" beside quantity 20); what the customer confirms must be what runs.
    Every product, option and quantity is spelled out; None when that does not fit the
    reply limit, so a long proposal is never accepted with items the customer never saw.
    """
    products = {item.product_id: item for item in menu}
    clauses = []
    for call in tool_calls:
        arguments = call.arguments
        item = products[arguments.product_id]
        unit = "잔" if item.temperatures else "개"
        name = " ".join(filter(None, [TEMPERATURE_WORDS.get(arguments.temperature or ""), item.name]))
        if isinstance(call, AddCartItemCall):
            clauses.append((f"{name} {arguments.quantity}{unit}", "담을까요?", "담기"))
        elif isinstance(call, UpdateCartItemCall):
            clauses.append((f"{name} {arguments.quantity}{unit}으로", "바꿀까요?", "바꾸기"))
        else:
            clauses.append((name, "뺄까요?", "빼기"))
    if len(clauses) == 1:
        subject, verb, _ = clauses[0]
        return f"{subject} {verb}"
    text = ", ".join(f"{subject} {short}" for subject, _, short in clauses) + ", 이대로 할까요?"
    return text if len(text) <= REPLY_MAX else None


def menu_from_products(products: Iterable[object]) -> list[MenuItem]:
    """Keep only the product fields the interpreter needs (e.g. the ordering catalog)."""
    fields = MenuItem.model_fields.keys()
    return [
        MenuItem.model_validate({name: getattr(product, name) for name in fields})
        for product in products
    ]


def cart_from_items(items: Iterable[object]) -> list[CartLine]:
    """Keep only the cart fields the interpreter needs (e.g. the ordering Cart's items)."""
    fields = CartLine.model_fields.keys()
    return [CartLine.model_validate({name: getattr(item, name) for name in fields}) for item in items]


def _with_temperature(call, temperature):
    return call.model_copy(update={"arguments": call.arguments.model_copy(update={"temperature": temperature})})


def ask_for_missing_temperature(
    result: VoiceInterpretation, menu: list[MenuItem], cart: Iterable[CartLine] = (),
) -> VoiceInterpretation:
    """Turn a drink without a temperature into a question instead of a failure.

    The model sometimes sends temperature null for products sold iced and hot even
    though the prompt says to ask. A single allowed temperature is filled in. For a
    change or removal, the cart decides: one line of that product fills its temperature,
    two lines ask which one.
    """
    products = {item.product_id: item for item in menu}
    calls = []
    for call in result.tool_calls:
        item = products.get(call.arguments.product_id)
        if (item is None or call.arguments.temperature is not None or not item.temperatures
                or (isinstance(call, AddCartItemCall) and not item.available)):
            calls.append(call)  # left for matches_menu, which rejects unsold additions
            continue
        in_cart = [line for line in cart if line.product_id == item.product_id]
        if not isinstance(call, AddCartItemCall) and len(in_cart) == 1:
            calls.append(_with_temperature(call, in_cart[0].temperature))
            continue
        if len(item.temperatures) > 1:
            return VoiceInterpretation(
                status="needs_clarification", tool_calls=[],
                reply_text=f"{item.name}, 따뜻한 것과 아이스 중 무엇으로 할까요?",
            )
        calls.append(_with_temperature(call, item.temperatures[0]))
    return result.model_copy(update={"tool_calls": calls})


def drop_repeated_calls(result: VoiceInterpretation) -> VoiceInterpretation:
    """Keep one of several identical tool inputs.

    The model sometimes repeats the very same call (two "add 1 iced latte" for one
    "카페라떼 하나요"); nobody orders the same thing twice in one breath, they say a number.
    """
    seen, calls = set(), []
    for call in result.tool_calls:
        key = (call.tool, call.arguments.model_dump_json())
        if key in seen:
            logger.warning("voice interpretation repeated a tool input; kept one")
            continue
        seen.add(key)
        calls.append(call)
    return result.model_copy(update={"tool_calls": calls}) if len(calls) != len(result.tool_calls) else result


def require_cart_items(
    result: VoiceInterpretation, cart: Iterable[CartLine], menu: list[MenuItem],
) -> VoiceInterpretation:
    """A change or removal of something not in the cart becomes a question, not a failure."""
    lines = {(line.product_id, line.temperature) for line in cart}
    names = {item.product_id: item.name for item in menu}
    for call in result.tool_calls:
        if isinstance(call, AddCartItemCall):
            continue
        if (call.arguments.product_id, call.arguments.temperature) not in lines:
            name = names.get(call.arguments.product_id, call.arguments.product_id)
            return VoiceInterpretation(
                status="needs_clarification", tool_calls=[], reply_text=f"{name}, 지금 장바구니에 없어요.",
            )
    return result


ONES = {
    "하나": 1, "한": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "넷": 4, "네": 4, "다섯": 5,
    "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9,
}
TENS = {"열": 10, "스물": 20, "스무": 20}
# "하나", "두 잔", "열아홉 잔", "3개", "한 잔만": a count and an optional unit. The one-syllable
# counts (한, 두, 세, 네) need the unit, so "네" the yes is never four and "따뜻한" never one.
_COUNT = re.compile(
    r"(?:(?P<tens>열|스물|스무)?(?P<ones>하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉)(?:잔|개|컵|병)?"
    r"|(?P<tens_only>열|스물|스무)(?:잔|개|컵|병)?"
    r"|(?P<digits>\d+)(?:잔|개|컵|병)?"
    r"|(?P<short_tens>열|스물|스무)?(?P<short>한|두|세|네)(?:잔|개|컵|병))(?:만|씩)?"
)
# Right after a count (or its 더): "하나 빼 주세요", "하나 더 빼 주세요", "하나 줄여요" take away.
DECREASE_AFTER = ("빼", "취소", "줄", "덜", "없")
SPOKEN_TEMPERATURES = {
    "아이스": "iced", "차가운": "iced", "차갑게": "iced", "시원한": "iced", "시원하게": "iced",
    "따뜻한": "hot", "따뜻하게": "hot", "뜨거운": "hot", "뜨겁게": "hot",
}
_TEMPERATURE = re.compile("|".join(sorted(SPOKEN_TEMPERATURES, key=len, reverse=True)))
# What may stand between a temperature word and the product it describes: nothing or 로/으로.
TEMPERATURE_LINKS = ("", "로", "으로")
QUANTITY_MAX = 20  # as Quantity in schemas.py and the ordering API
QUANTITY_LIMIT_REPLY = f"한 상품은 {QUANTITY_MAX}개까지 담을 수 있어요."


def _count(found: re.Match) -> int:
    if found.group("digits"):
        return int(found.group("digits"))
    tens = TENS.get(found.group("tens") or found.group("tens_only") or found.group("short_tens") or "", 0)
    ones = ONES.get(found.group("ones") or found.group("short") or "", 0)
    return tens + ones


def _name_positions(compact: str, menu: list[MenuItem]) -> list[tuple[int, str]]:
    """Where each product is named in the utterance, as (position, product_id), in order."""
    positions = []
    for product_id, keys in _name_keys(menu).items():
        for key in keys:
            positions.extend((found.start(), product_id) for found in re.finditer(re.escape(key), compact))
    return sorted(set(positions))


def spoken_mentions(
    text: str, menu: list[MenuItem],
) -> tuple[list[tuple[str | None, str, int]], list[tuple[str | None, str]]]:
    """The counts and temperatures the customer said, each tied to a product.

    Counts: (product_id, kind, n) with kind "more" ("하나 더"), "less" ("하나 빼", "하나 더
    빼") or "abs" ("두 잔", "세 잔으로"). A count belongs to the product named last before
    it since the previous count, so "아메리카노 하나 더, 샌드위치 두 개 더" gives
    [(americano, more, 1), (sandwich, more, 2)] and a bare "하나 더요" gives [(None, more, 1)].
    Temperatures: (product_id, temperature) tied to the product named right after the word
    with nothing or 로/으로 in between ("아이스 아메리카노", "아이스로 아메리카노"), else to
    the last product named before it ("아메리카노 아이스로 하고 샌드위치 하나": the americano,
    not the sandwich), else None ("아이스로요").
    """
    compact = _compact(text)
    names = _name_positions(compact, menu)
    counts, start = [], 0
    for found in _COUNT.finditer(compact):
        after = compact[found.end():]
        if after.startswith("더"):
            kind = "less" if after[1:].startswith(DECREASE_AFTER) else "more"
        else:
            kind = "less" if after.startswith(DECREASE_AFTER) else "abs"
        before = [product_id for position, product_id in names if start <= position < found.start()]
        counts.append((before[-1] if before else None, kind, _count(found)))
        start = found.end()
    temperatures = []
    for found in _TEMPERATURE.finditer(compact):
        after = [(position, product_id) for position, product_id in names if position >= found.end()]
        before = [product_id for position, product_id in names if position < found.start()]
        if after and compact[found.end():after[0][0]] in TEMPERATURE_LINKS:
            product_id = after[0][1]  # "아이스 아메리카노", "아이스로 아메리카노"
        else:
            product_id = before[-1] if before else None  # "아메리카노 아이스로 하고 샌드위치"
        temperatures.append((product_id, SPOKEN_TEMPERATURES[found.group()]))
    return counts, temperatures


def spoken_increments(text: str, menu: list[MenuItem]) -> list[tuple[str | None, int]]:
    """Every "N 더" in the utterance with the product named just before it, in order."""
    counts, _ = spoken_mentions(text, menu)
    return [(product_id, n) for product_id, kind, n in counts if kind == "more"]


def spoken_increment(text: str) -> int | None:
    """The count in a bare "하나 더요", "두 잔 더 주세요"; None when the utterance is not that."""
    increments = spoken_increments(text, [])
    return increments[0][1] if len(increments) == 1 else None


def _removal(call) -> RemoveCartItemCall:
    return RemoveCartItemCall(
        tool="remove_cart_item",
        arguments=CartItemTarget(product_id=call.arguments.product_id, temperature=call.arguments.temperature),
    )


def _with_quantity(call, quantity: int):
    return call.model_copy(update={"arguments": call.arguments.model_copy(update={"quantity": quantity})})


def match_spoken_details(
    result: VoiceInterpretation, request: VoiceRequestCreate, cart: Iterable[CartLine],
    menu: list[MenuItem] = (),
) -> VoiceInterpretation:
    """The counts and temperatures the customer said must be what the tool inputs do.

    The prompt tells the model to copy them, but it may still answer "아이스 아메리카노
    한 잔 주세요" with three cups or a hot one, or "하나 더요" over two cups with add 3,
    and the earlier checks only look at the product. What the customer said is their own
    order, so a tool input that disagrees is set to it and read back for confirmation
    instead of running: an addition gets the spoken count ("두 잔"), "N 더" adds N to the
    cart line, "N 빼" takes N off it (down to removing the line), and a spoken temperature
    replaces the model's. A count or temperature with no product goes with the one tool
    input that has none of its own. Anything that cannot be matched (two unnamed counts,
    a count for a product the model left out, two different counts for one product) turns
    the whole result into a confirmation, so nothing the customer did not hear runs. A
    count past the cart limit is refused with the limit and never stored as a proposal.
    """
    menu = list(menu)
    counts, temperatures = spoken_mentions(request.text, menu)
    if not result.tool_calls or not (counts or temperatures):
        return result
    products = {item.product_id: item for item in menu}
    in_cart = {(line.product_id, line.temperature): line.quantity for line in cart}
    said = {call.arguments.product_id for call in result.tool_calls}
    quantified = [call for call in result.tool_calls if not isinstance(call, RemoveCartItemCall)]
    ambiguous = False

    bound_counts: dict[str, tuple[str, int]] = {}
    unbound_counts: list[tuple[str, int]] = []
    for product_id, kind, n in counts:
        if product_id is None:
            unbound_counts.append((kind, n))
        elif product_id in bound_counts or product_id not in said:
            ambiguous = True  # two counts for one product, or a count for a product the model left out
        else:
            bound_counts[product_id] = (kind, n)
    uncounted = [call for call in quantified if call.arguments.product_id not in bound_counts]
    if len(unbound_counts) > 1 or (unbound_counts and len(uncounted) != 1):
        ambiguous = True

    bound_temperatures: dict[str, str] = {}
    unbound_temperatures: set[str] = set()
    for product_id, temperature in temperatures:
        if product_id is None:
            unbound_temperatures.add(temperature)
        elif product_id in products and not products[product_id].temperatures:
            ambiguous = True  # "아이스 샌드위치": the word must have meant something else
        elif bound_temperatures.get(product_id, temperature) != temperature:
            ambiguous = True  # two temperatures for one product: which cup is which?
        else:
            bound_temperatures[product_id] = temperature
    if len(unbound_temperatures) > 1 or (unbound_temperatures and len(result.tool_calls) != 1):
        ambiguous = True

    if ambiguous:
        logger.warning("voice interpretation: spoken counts or temperatures could not be matched; confirming")
        return VoiceInterpretation(status="needs_confirmation", tool_calls=result.tool_calls, reply_text="?")

    calls, changed = [], False
    for call in result.tool_calls:
        product_id = call.arguments.product_id
        item = products.get(product_id)
        temperature = bound_temperatures.get(product_id) or next(iter(unbound_temperatures), None)
        if temperature is not None and call.arguments.temperature not in (None, temperature):
            if item is not None and temperature not in item.temperatures:
                return VoiceInterpretation(
                    status="needs_clarification", tool_calls=[],
                    reply_text=f"{item.name}, 따뜻한 것과 아이스 중 무엇으로 할까요?",
                )
            logger.warning("voice interpretation temperature disagrees with the spoken one; confirming")
            call, changed = _with_temperature(call, temperature), True
        count = bound_counts.get(product_id) or (unbound_counts[0] if unbound_counts and call in uncounted else None)
        if count is not None:
            kind, n = count
            current = in_cart.get((product_id, call.arguments.temperature), 0)
            if isinstance(call, RemoveCartItemCall):
                if kind != "less":
                    return VoiceInterpretation(status="needs_confirmation", tool_calls=result.tool_calls, reply_text="?")
                expected = current - n  # "하나 빼 주세요" over three cups leaves two, not none
            elif isinstance(call, UpdateCartItemCall):
                expected = {"more": current + n, "less": current - n, "abs": n}[kind]
            elif kind == "less":
                return VoiceInterpretation(status="needs_confirmation", tool_calls=result.tool_calls, reply_text="?")
            else:
                expected = n
            if expected > QUANTITY_MAX:
                return VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=QUANTITY_LIMIT_REPLY)
            if expected <= 0:
                if not isinstance(call, RemoveCartItemCall):
                    call, changed = _removal(call), True
            elif isinstance(call, RemoveCartItemCall):
                call, changed = UpdateCartItemCall(tool="update_cart_item", arguments=CartItemQuantity(
                    product_id=product_id, temperature=call.arguments.temperature, quantity=expected)), True
            elif call.arguments.quantity != expected:
                logger.warning("voice interpretation quantity disagrees with the spoken count; confirming")
                call, changed = _with_quantity(call, expected), True
        calls.append(call)
    if not changed:
        return result
    return VoiceInterpretation(status="needs_confirmation", tool_calls=calls, reply_text="?")


ASK_MENU_REPLY = "어떤 메뉴를 주문할까요?"
PENDING = {"needs_confirmation", "needs_clarification"}


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _name_words(menu: list[MenuItem]) -> dict[str, list[str]]:
    return {item.product_id: [w for w in map(_compact, item.name.split()) if len(w) >= 2] for item in menu}


def _name_keys(menu: list[MenuItem]) -> dict[str, list[str]]:
    """What names each product in an utterance: its full name, or a word only its name has."""
    words = _name_words(menu)
    uses = Counter(word for item_words in words.values() for word in set(item_words))
    return {
        item.product_id: [k for k in [_compact(item.name), *(w for w in words[item.product_id] if uses[w] == 1)] if k]
        for item in menu
    }


def which_in_cart_reply(lines: list[CartLine], menu: list[MenuItem]) -> str:
    """Ask which cart line an unnamed "하나 더", "그거" means, naming them when that fits."""
    names = {item.product_id: item.name for item in menu}
    labels = []
    for line in lines:
        label = " ".join(filter(None, [TEMPERATURE_WORDS.get(line.temperature or ""), names.get(line.product_id, line.product_id)]))
        if label not in labels:
            labels.append(label)
    text = ", ".join(labels) + " 중 어느 것을 말씀하시나요?"
    return text if len(text) <= REPLY_MAX else "장바구니의 어느 상품을 말씀하시나요?"


def require_named_products(
    result: VoiceInterpretation, request: VoiceRequestCreate, history: list[VoiceTurn],
    menu: list[MenuItem], cart: Iterable[CartLine] = (),
) -> VoiceInterpretation:
    """Send tool inputs only for products this utterance points at.

    A short answer such as "네" or "따뜻한 걸로요" must not become an order the
    model made up, nor swap in another product. What counts, in this order:

    1. Products named in this utterance (or its recognition alternatives) by their full
       name or a word only their name has. Then every tool input must be one of them;
       a product the customer said earlier but not now is not enough ("샌드위치 하나
       더요" must not add the americano from two turns ago).
    2. Otherwise the product the kiosk's last reply asked about ("카페 라떼는 아이스,
       따뜻한 것 중 무엇으로 할까요?" → "아이스로요"). A general "어떤 메뉴를
       주문할까요?" names nothing.
    3. Otherwise ("하나 더요", "그거 빼 줘") the cart decides: only while it holds exactly
       one line, and the tool input means that line. Two products, or one product in two
       temperatures, make the kiosk ask which; an empty cart makes it ask for the menu.

    A word several names share ("라떼") is not enough; the kiosk asks which one.
    """
    if not result.tool_calls:
        return result
    words = _name_words(menu)
    uses = Counter(word for item_words in words.values() for word in set(item_words))
    keys = _name_keys(menu)

    def named_in(texts: list[str]) -> set[str]:
        return {product_id for product_id in keys if any(key in text for key in keys[product_id] for text in texts)}

    now = [_compact(request.text), *(_compact(item.text) for item in request.alternatives)]
    asked = [_compact(history[-1].result.reply_text)] if history and history[-1].result.reply_text else []
    allowed = named_in(now) or named_in(asked)
    lines = list(cart)
    sole = lines[0] if len(lines) == 1 else None
    in_cart = {line.product_id for line in lines}
    for call in result.tool_calls:
        product_id = call.arguments.product_id
        if allowed:
            if product_id in allowed:
                continue
        elif product_id in in_cart:
            if sole is not None and call.arguments.temperature in (None, sole.temperature):
                continue  # the one thing in the cart is the only thing "그거" can mean
            return VoiceInterpretation(
                status="needs_clarification", tool_calls=[], reply_text=which_in_cart_reply(lines, menu),
            )
        shared = [w for w in words.get(product_id, []) if uses[w] > 1 and any(w in text for text in now)]
        reply = f"{max(shared, key=len)} 중 어떤 메뉴로 할까요?" if shared else ASK_MENU_REPLY
        return VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=reply)
    return result


def matches_menu(
    result: VoiceInterpretation, menu: list[MenuItem], allow_missing_temperature: bool = False,
) -> bool:
    """Reject tool inputs naming unknown products, unavailable additions or invalid temperatures.

    allow_missing_temperature lets a drink without a temperature through, to be asked later.
    """
    products = {item.product_id: item for item in menu}
    for call in result.tool_calls:
        item = products.get(call.arguments.product_id)
        if item is None:
            return False
        if isinstance(call, AddCartItemCall) and not item.available:
            return False
        temperature = call.arguments.temperature
        if temperature is None and item.temperatures and allow_missing_temperature:
            continue
        if (temperature is None) != (not item.temperatures):
            return False
        if temperature is not None and temperature not in item.temperatures:
            return False
    return True


class VoiceService:
    def __init__(
        self, session_exists: Callable[[str], bool], repository: VoiceRepository,
        interpreter: VoiceInterpreter, menu_provider: Callable[[], list[MenuItem]],
        ordering: OrderingRepository, executor: CartExecutor | None = None,
        cart_provider: Callable[[str], Iterable[CartLine]] | None = None,
    ):
        self._session_exists = session_exists
        self._repository = repository
        self._interpreter = interpreter
        self._menu_provider = menu_provider
        self._ordering = ordering
        # None: tool_calls are returned as MCP inputs only and the cart is not changed.
        self._executor = executor
        # What the session has in its cart now, for "하나 더" and "빼 줘"; None reads as empty.
        self._cart_provider = cart_provider

    def _cart(self, session_id: str) -> list[CartLine]:
        if self._cart_provider is None:
            return []
        try:
            return list(self._cart_provider(session_id))
        except Exception:
            # A cart that cannot be read (completed session, store error) is read as empty;
            # the ordering service still has the last word when tools run.
            logger.warning("voice could not read the cart; interpreting without it")
            return []

    def accept(
        self, session_id: str, key: UUID, request: VoiceRequestCreate
    ) -> tuple[VoiceRequestAccepted, bool]:
        """Return (accepted, created). Only a newly created request is processed."""
        if not self._session_exists(session_id):
            raise VoiceSessionNotFound()
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        # Keep completion stable through insertion; existing keys replay first.
        with self._ordering.completion_guard(session_id) as completed:
            record, created = self._repository.accept(
                session_id, key, fingerprint,
                is_completed=lambda: completed,
            )
        accepted = VoiceRequestAccepted(
            request_id=record.request_id, accepted_at=record.accepted_at
        )
        return accepted, created

    async def process(
        self, session_id: str, request_id: str, request: VoiceRequestCreate
    ) -> None:
        self._repository.update(request_id, "processing")
        try:
            menu = self._menu_provider()
            if not menu:
                # Nothing can be ordered, so do not spend an OpenAI call on it.
                self._repository.update(
                    request_id, "failed", FALLBACK_REPLY,
                    error=VoiceErrorResponse(
                        code="ai_unavailable", detail="판매 메뉴가 연결되지 않아 음성 해석을 하지 않았습니다.",
                    ),
                )
                return
            history = self._repository.history(session_id)
            last = history[-1].result if history else None
            # A proposal answers this one utterance, whatever it turns out to be: an
            # ignored or failed exchange in between must not leave it waiting for a later "네".
            proposal = self._repository.take_proposal(session_id)
            # The cart the tool inputs are checked against; execution runs only on that cart.
            expected: list[CartLine] | None = None
            if proposal is not None and is_bare_yes(request.text):
                # The customer accepted what the kiosk proposed, so run exactly that proposal.
                # A fresh model reading of "네" could differ from it (another quantity) and
                # would otherwise pass the menu checks and change the cart.
                result = VoiceInterpretation(status="completed", tool_calls=proposal.tool_calls, reply_text=None)
                expected = proposal.cart
            elif last is not None and last.status == "needs_clarification" and is_bare_yes(request.text):
                # "네" cannot answer "아이스, 따뜻한 것 중 무엇으로?"; ask again instead of guessing.
                result = last
            elif is_bare_yes(request.text):
                # Nothing is proposed (or the proposal has lapsed), so "네" must not invent an order.
                result = VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=ASK_MENU_REPLY)
            else:
                cart = self._cart(session_id)
                result = await self._interpreter.interpret(request, menu, history, cart)
            if result is not None and not matches_menu(result, menu, allow_missing_temperature=True):
                logger.warning("voice interpretation rejected (not on menu)")
                result = None
            if result is not None:
                cart = list(self._cart(session_id))
                if expected is None:
                    expected = cart
                # Check named products before asking about a temperature, so the kiosk
                # never asks about a drink the customer did not mention.
                result = drop_repeated_calls(result)
                result = require_named_products(result, request, history, menu, cart)
                result = ask_for_missing_temperature(result, menu, cart)
                result = match_spoken_details(result, request, cart, menu)
                result = require_cart_items(result, cart, menu)
            if result is not None and not matches_menu(result, menu):
                logger.warning("voice interpretation rejected (not on menu)")
                result = None
            if (result is not None and result.status == "completed"
                    and self._repository.needs_reconfirm(session_id)
                    and (proposal is None or result.tool_calls != proposal.tool_calls)):
                # An answer to a confirmation went to the model ("네 그걸로 주세요"), which
                # may answer with other tool inputs than the customer confirmed, or the
                # proposal has lapsed and the model read the answer against older turns;
                # either way it is a new proposal, not an order. The mark lives apart from
                # the history, so earlier completed orders cannot stand in for the offer.
                result = VoiceInterpretation(status="needs_confirmation", tool_calls=result.tool_calls, reply_text="?")
            if result is not None and result.status == "needs_confirmation":
                text = confirmation_text(result.tool_calls, menu)
                if text is None:
                    # Too much to read back in one line: never confirm items the customer
                    # cannot see. The utterance stays in the context, so a later "그걸로
                    # 주세요" read against it must come back here, not run.
                    result = VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=SPLIT_ORDER_REPLY)
                    self._repository.mark_reconfirm(session_id)
                else:
                    result = result.model_copy(update={"reply_text": text})
                    self._repository.set_proposal(session_id, result.tool_calls, cart)
        except Exception:
            # A voice failure must not affect touch ordering; record it as unavailable.
            logger.exception("voice interpretation crashed")
            result = None
        if proposal is not None and (result is None or result.status != "completed"):
            # The proposal was not accepted (declined, ignored, failed, or replaced by a new
            # one), so its question leaves the context: a later "그걸로 주세요" must not be
            # read against an offer that is no longer open. The reconfirm mark stays until
            # an order actually goes through.
            self._repository.discard_proposal_turn(session_id)
        if result is None:
            # Failed exchanges stay out of the context so later turns read cleanly.
            self._repository.update(
                request_id, "failed", FALLBACK_REPLY,
                error=VoiceErrorResponse(code="ai_unavailable", detail="외부 AI를 사용할 수 없습니다."),
            )
            return
        actions = []
        if result.status == "completed" and self._executor is not None:
            # A proposal (needs_confirmation) is not run; the customer's "네" comes back
            # as a completed result and is run then.
            try:
                self._executor.execute(session_id, request_id, result.tool_calls, expected)
            except CartChanged as changed:
                # A touch changed the cart after the inputs were checked ("3잔으로" was
                # "하나 더" over two cups; now there are five). Nothing ran: read the same
                # inputs back against the cart as it is now, and "네" runs them on that.
                logger.warning("voice tool execution skipped: cart changed since the checks; confirming")
                if proposal is not None:
                    self._repository.discard_proposal_turn(session_id)
                text = confirmation_text(result.tool_calls, menu)
                if text is None:
                    result = VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=SPLIT_ORDER_REPLY)
                    self._repository.mark_reconfirm(session_id)
                else:
                    result = VoiceInterpretation(status="needs_confirmation", tool_calls=result.tool_calls, reply_text=text)
                    self._repository.set_proposal(session_id, result.tool_calls, changed.cart)
            except ToolExecutionFailed as failed:
                self._repository.update(request_id, "failed", failed.reply_text, error=failed.error)
                return
            except Exception:
                # The interpretation succeeded; only the cart change failed, so the code
                # must not blame the AI (the transaction already rolled the cart back).
                logger.exception("voice tool execution crashed")
                self._repository.update(
                    request_id, "failed", FALLBACK_EXECUTION_REPLY,
                    error=VoiceErrorResponse(code="cart_update_failed", detail="장바구니에 반영하지 못했습니다."),
                )
                return
            if result.status == "completed":
                actions = ["cart_updated"]
        if result.status == "completed":
            # An order went through (accepted or read with no open offer): later readings
            # are orders again.
            self._repository.clear_reconfirm(session_id)
        if result.status != "ignored":
            # Speech not meant for the kiosk would only confuse later turns.
            self._repository.append_turn(session_id, VoiceTurn(request=request, result=result))
        # Without an executor, tool_calls are MCP inputs only (a proposal when
        # needs_confirmation) and actions stay empty.
        self._repository.update(
            request_id, result.status, result.reply_text, result.tool_calls, actions=actions,
        )

    def get(self, session_id: str, request_id: str) -> VoiceRequestStatus:
        if not self._session_exists(session_id):
            raise VoiceSessionNotFound()
        status = self._repository.get(session_id, request_id)
        if status is None:
            raise VoiceRequestNotFound()
        return status
