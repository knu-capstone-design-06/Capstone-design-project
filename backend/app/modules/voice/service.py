import hashlib
import logging
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
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


# The whole utterances that take an offer, optionally after a yes ("네 그걸로 주세요").
# Anything else is not an acceptance: no word list can catch every "하지 마세요", so the
# offer runs only on these, and any other utterance makes the kiosk ask again.
ACCEPT_UTTERANCES = {
    "그걸로", "그걸로요", "그걸로주세요", "그걸로해주세요", "그걸로할게요", "그걸로부탁해요",
    "그렇게", "그렇게요", "그렇게주세요", "그렇게해주세요", "그렇게할게요", "그렇게해줘",
    "그대로", "그대로요", "그대로주세요", "그대로해주세요", "그대로할게요",
    "맞아요", "맞아", "맞습니다", "좋아요", "좋아", "좋습니다", "그래요", "그래", "응", "예", "네", "넵",
    "담아주세요", "담아줘", "주세요", "해주세요", "할게요", "부탁해요", "부탁합니다",
}
# Words that turn an offer down; they only pick the reply (ask for the menu instead of
# reading the offer back), never whether it runs.
REJECT_MARKS = ("아니", "아뇨", "말고", "싫", "취소", "다시", "빼", "안돼", "안되", "안해", "안할", "않", "못",
                "됐어", "괜찮", "그만", "하지마", "마세요", "말아")


def is_rejection(text: str) -> bool:
    compact = "".join(ch for ch in text if ch.isalnum())
    return any(mark in compact for mark in REJECT_MARKS)


def is_acceptance(text: str) -> bool:
    """Only a whole utterance from the acceptance list, optionally led by a yes, accepts an offer."""
    compact = "".join(ch for ch in text if ch.isalnum())
    if compact in BARE_YES:
        return True
    for yes in sorted(BARE_YES, key=len, reverse=True):
        if compact.startswith(yes):
            compact = compact[len(yes):]
            break
    return compact in ACCEPT_UTTERANCES


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
# Right after a count: "하나 추가해 주세요", "두 개 넣어 주세요" add that many, like "하나 더".
INCREASE_AFTER = ("추가", "넣어")
# "하나도 안 보여요", "하나도 모르겠어요", "한 개도 없어요": 하나도 before a negation means "at all", not one.
_NOT_AT_ALL = ("안", "않", "없", "못", "모르")
SPOKEN_TEMPERATURES = {
    "아이스": "iced", "차가운": "iced", "차갑게": "iced", "시원한": "iced", "시원하게": "iced",
    "따뜻한": "hot", "따뜻하게": "hot", "따듯한": "hot", "따듯하게": "hot", "뜨거운": "hot", "뜨겁게": "hot", "핫": "hot",
}
# Particles that may sit between a count and the word that gives it its meaning ("한 잔을 빼").
_PARTICLES = re.compile(r"^(?:을|를|은|는|이|가|만|씩|도|이나|나|좀)+")
_TEMPERATURE = re.compile("|".join(sorted(SPOKEN_TEMPERATURES, key=len, reverse=True)))
# What may stand between a temperature word and the product it describes: nothing or 로/으로.
TEMPERATURE_LINKS = ("", "로", "으로")
QUANTITY_MAX = 20  # as Quantity in schemas.py and the ordering API
QUANTITY_LIMIT_REPLY = f"한 상품은 {QUANTITY_MAX}개까지 담을 수 있어요."
# Words that ask to take something out of the cart, and what right after one turns it
# into the opposite ("빼지 말아 주세요", "빼면 안 돼요").
REMOVAL_MARKS = ("빼", "취소", "삭제", "없애", "지워", "지우", "제거", "말고", "줄여", "줄이", "덜")
# A removal word counts as a request only with a requesting ending right after it ("빼
# 주세요", "빼 줘", "취소해 주세요", "빼고"); "빼지 마세요", "빼시면 안 돼요", "삭제 안 해도
# 돼요" and every other continuation are not requests, whatever negation they use.
REQUEST_AFTER = tuple(sorted(
    ("주세요", "주시", "주실", "주십", "줘", "줄래", "달라", "해주세요", "해줘", "해주", "해요", "할게", "할래", "해", "고", "요"),
    key=len, reverse=True))
# Right after a removal word: these say "do not" outright.
NEGATED_TAIL = ("지마", "지말", "지않", "진마", "진않", "지는마", "지는않", "시지마", "시지말", "면안", "시면안", "는안", "안", "않", "말아", "말고")
# Inside what follows a requesting ending: a negation anywhere turns the request around
# ("빼 달라고 안 했어요", "빼고 싶다고 한 적 없어요", "취소해 주시면 안 돼요").
NEGATION_WORDS = ("안", "않", "마세", "말아", "말라", "아니", "없", "싶지", "싶진")
# Polite requests that contain a negation word but ask for the removal: "빼 주시면 안 될까요?"
POLITE_REQUESTS = ("안될까", "안되나", "안될지", "안되겠냐", "안되겠니")
# What may close a request: nothing more, or exactly one of these tails. "빼 줄래요? 아
# 됐어요" goes on past the tail, so the clause is not closed and the request is not certain.
POLITE_TAILS = (
    "요", "세요", "셔요", "습니다", "ㅂ니다", "습니까", "시오", "래요", "라요", "게요", "겠어요", "겠습니다", "겠습니까",
    "싶어", "싶어요", "싶습니다", "싶네요",
)
_REMOVAL = re.compile("|".join(map(re.escape, sorted(REMOVAL_MARKS, key=len, reverse=True))))


def removal_intents(text: str, menu: list[MenuItem]) -> dict[str | None, str]:
    """Per product, "yes" when the utterance asks to take it out and "no" when it says not to.

    Each removal word goes with the product named last before it since the previous one,
    so "아메리카노 빼지 말고 샌드위치 빼 주세요" is {americano: no, sandwich: yes}; a word with
    no product before it ("그거 빼 줘") is keyed None. "안" right before the word ("안 빼요",
    "한 잔 안 빼도 돼요") is a no. "말고" ("아메리카노 말고 라떼") is a request by itself, unless
    what follows takes another product out ("아메리카노 말고 샌드위치 빼 주세요": the americano
    stays). Any "no" for a product wins.
    """
    compact = _compact(text)
    names = _name_positions(compact, menu)
    boundaries = _clause_boundaries(compact, names)
    intents: dict[str | None, str] = {}
    position = start = 0
    while (found := _REMOVAL.search(compact, position)) is not None:
        after = compact[found.end():]
        if found.group() == "말고" and compact[:found.start()].endswith("지"):
            position = found.end()  # the 말고 of "빼지 말고": part of a negation, not a request
            continue
        if compact[:found.start()].endswith("안"):
            verdict = "no"  # "안 빼요", "안 취소해요": the removal word itself is negated
        elif found.group() == "말고" and _removes_another(compact, found.end(), names):
            verdict = "no"  # "아메리카노 말고 샌드위치 빼 주세요": the sandwich goes, not the americano
        else:
            verdict = _removal_verdict(found.group(), after, [b - found.end() for b in boundaries if b >= found.end()])
        before = [product_id for p, product_id in names if start <= p < found.start()]
        key = before[-1] if before else None
        previous = intents.get(key)
        intents[key] = "no" if "no" in (previous, verdict) else "unclear" if "unclear" in (previous, verdict) else "yes"
        position = start = found.end()
    return intents


def _clause_boundaries(compact: str, names: list[tuple[int, str]]) -> list[int]:
    """Where another product's words begin: its name, or a temperature word tied to it.

    In "샌드위치 빼고 아이스 아메리카노 주세요" the americano's clause starts at "아이스".
    """
    boundaries = [position for position, _ in names]
    for found in _TEMPERATURE.finditer(compact):
        following = [position for position in boundaries if position >= found.end()]
        if following and compact[found.end():following[0]] in TEMPERATURE_LINKS:
            boundaries.append(found.start())
    return sorted(set(boundaries))


def _removes_another(compact: str, start: int, names: list[tuple[int, str]]) -> bool:
    """Whether a product named after start is followed by a removal word of its own."""
    following = [position for position, _ in names if position >= start]
    if not following:
        return False
    later = _REMOVAL.search(compact, following[0])
    return later is not None and later.group() != "말고"


def _removal_verdict(word: str, after: str, boundary_offsets: list[int]) -> str:
    """Three ways to read what follows a removal word.

    "yes" when the request is certain: nothing follows, a requesting ending with at most a
    polite tail closes the clause ("빼 주세요", "빼 줘", "빼 줄래요?"), or the ending leads into
    another request ("빼고 샌드위치 주세요", "빼고 싶어요", "빼 주시면 안 될까요?"). "no" when a
    negation is certain: "빼지 마세요", "빼 달라고 안 했어요", "빼고 싶은 것은 아니에요", "취소해
    주시면 안 돼요". "unclear" for everything else ("빼면 어때요", "빼 줄래요? 아 됐어요"), which
    the caller reads back.
    """
    # Only the words up to the next product belong to this removal: in "아메리카노 빼 주세요
    # 샌드위치는 빼지 마세요" the sandwich's negation is not the americano's.
    cut = min((offset for offset in boundary_offsets if offset > 0), default=None)
    if cut is not None:
        after = after[:cut]
    if word == "말고" or after == "":
        return "yes"  # "빼고 샌드위치 주세요" ends the americano's part at "빼고"
    if after.startswith(NEGATED_TAIL):
        return "no"
    ending = next((e for e in REQUEST_AFTER if after.startswith(e)), None)
    if ending is None:
        return "no" if any(n in after for n in NEGATION_WORDS) else "unclear"
    rest = after[len(ending):]
    polite = next((p for p in POLITE_REQUESTS if p in rest), None)
    if polite is not None:
        # "빼 주시면 안 될까요?" asks; "빼 주시면 안 될까요? 아니요 그대로 해 주세요" takes it back.
        later = rest[rest.find(polite) + len(polite):]
        return "no" if any(n in later for n in NEGATION_WORDS) else "yes"
    if any(n in rest for n in NEGATION_WORDS):
        return "no"
    if rest == "" or rest in POLITE_TAILS:
        return "yes"  # the clause ends with the request; "빼 줄래요? 아 됐어요" goes on, so it is unclear
    if ending == "고" and _COUNT.match(rest):
        return "yes"  # "빼고 하나 더요": what follows is another request
    return "unclear"


def removal_intent(text: str) -> str:
    """The removal intent of an utterance naming no product: "yes", "no" or "unclear"."""
    return removal_intents(text, []).get(None, "unclear")


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
        tail = compact[found.end():]
        if tail.startswith("도") and tail[1:].startswith(_NOT_AT_ALL):
            continue  # "화면이 하나도 안 보여요": no count was said
        after = _PARTICLES.sub("", tail)  # "한 잔을 빼" reads like "한 잔 빼"
        if after.startswith("더"):
            kind = "less" if after[1:].startswith(DECREASE_AFTER) else "more"
        elif after.startswith(DECREASE_AFTER):
            kind = "less"
        elif after.startswith(INCREASE_AFTER):
            kind = "more"  # "하나 추가해 주세요": one more, not one in all
        elif after.startswith("안") and after[1:].startswith(DECREASE_AFTER):
            kind = "less"  # "한 잔 안 빼도 돼요": a removal, negated; removal_intents says so
        elif after.startswith(("으로", "로")):
            kind = "to"  # "세 잔으로": the line becomes three, whatever it holds now
        else:
            kind = "abs"
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
    menu: list[MenuItem] = (), history: Sequence[VoiceTurn] = (), confirmed: list | None = None,
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

    An addition with no spoken count is one ("아이스 아메리카노 주세요"); any other model
    quantity, and any quantity change with no count, is read back first. When this
    utterance answers the kiosk's question ("카페라떼 두 잔이요" → "아이스로요"), the counts
    of the utterance that was asked about still hold. Tool inputs equal to what the kiosk
    already read back (confirmed) run as they are.
    """
    menu = list(menu)
    if not result.tool_calls:
        return result
    counts, temperatures = spoken_mentions(request.text, menu)
    if confirmed is not None and result.tool_calls == confirmed and not (counts or temperatures):
        # "네 그걸로 주세요": the offer as read back, taken as it stands. An utterance with
        # a count or temperature of its own ("한 잔만 주세요") is a correction, checked below.
        return result
    last = history[-1] if history else None
    if (not counts and last is not None and last.result.status == "needs_clarification"
            and (last.result.reply_text or "").endswith("?")
            and answers_question(request.text, last.result.reply_text)
            and _name_positions(_compact(last.result.reply_text), menu)):
        # An answer to the kiosk's question about a product ("아메리카노, 따뜻한 것과 아이스 중?")
        # keeps the counts of the utterance asked about, also when the question had to be
        # repeated in between. A general "어떤 메뉴를 주문할까요?" carries nothing over.
        counts = spoken_mentions(_asked_utterance(history, menu), menu)[0]
    products = {item.product_id: item for item in menu}
    in_cart = {(line.product_id, line.temperature): line.quantity for line in cart}
    removals = removal_intents(request.text, menu)
    said = {call.arguments.product_id for call in result.tool_calls}
    quantified = [call for call in result.tool_calls if not isinstance(call, RemoveCartItemCall)]
    ambiguous = False
    touched = [(call.arguments.product_id, call.arguments.temperature) for call in result.tool_calls]
    if len(touched) != len(set(touched)):
        ambiguous = True  # "하나 더요" answered with update(3) and add(1) on the same line: which one?

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
    for product_id in bound_counts:
        if sum(call.arguments.product_id == product_id for call in result.tool_calls) > 1:
            ambiguous = True  # one spoken count, two tool inputs: "아메리카노 하나 더요" on both temperatures

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

    calls, changed, unspoken = [], False, False
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
            if kind == "less":
                intent = removals.get(product_id) or removals.get(None) or "unclear"
                if intent == "no":
                    # "한 잔 빼지 마세요": the count sits next to a removal word, but the word is negated.
                    logger.warning("voice interpretation reduced what the customer said to keep; asking")
                    return VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=ASK_MENU_REPLY)
                if intent == "unclear":
                    unspoken = True  # "한 잔 빼면 어때요": read the change back first
            if isinstance(call, RemoveCartItemCall):
                if kind != "less":
                    return VoiceInterpretation(status="needs_confirmation", tool_calls=result.tool_calls, reply_text="?")
                expected = current - n  # "하나 빼 주세요" over three cups leaves two, not none
            elif isinstance(call, UpdateCartItemCall):
                expected = {"more": current + n, "less": current - n, "abs": n, "to": n}[kind]
            elif kind == "less":
                return VoiceInterpretation(status="needs_confirmation", tool_calls=result.tool_calls, reply_text="?")
            elif kind == "to" and (product_id, call.arguments.temperature) in in_cart:
                # "세 잔으로" over two cups is a change to three, not three more: the model's
                # addition becomes that change and is read back.
                logger.warning("voice interpretation added where the spoken count set a total; confirming")
                call, changed = UpdateCartItemCall(tool="update_cart_item", arguments=CartItemQuantity(
                    product_id=product_id, temperature=call.arguments.temperature, quantity=n)), True
                expected = n
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
        elif isinstance(call, UpdateCartItemCall) or (
                isinstance(call, AddCartItemCall) and call.arguments.quantity != 1):
            # No count was said; the model's number is its own, so the customer hears it first.
            unspoken = True
        elif isinstance(call, AddCartItemCall) and (removals.get(product_id) or removals.get(None)) == "yes":
            # "아이스 아메리카노 빼 주세요" answered with an addition: the action disagrees
            # with the words, so it is read back, never run.
            logger.warning("voice interpretation added what the customer asked to remove; confirming")
            unspoken = True
        elif isinstance(call, RemoveCartItemCall):
            # A removal runs only on words that ask for one: "빼지 말아 주세요" says the
            # opposite and "아메리카노요" says nothing, whatever the model made of them.
            intent = removals.get(product_id) or removals.get(None) or "unclear"
            if intent == "no":
                logger.warning("voice interpretation removed what the customer said to keep; asking")
                return VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=ASK_MENU_REPLY)
            if intent == "unclear":
                unspoken = True
        calls.append(call)
    if not (changed or unspoken):
        return result
    if unspoken:
        logger.warning("voice interpretation quantity was not spoken; confirming")
    return VoiceInterpretation(status="needs_confirmation", tool_calls=calls, reply_text="?")


def _asked_utterance(history: Sequence[VoiceTurn], menu: list[MenuItem]) -> str:
    """The utterance the kiosk's last question was first asked about.

    When the same question was repeated over words that neither answered it, named a
    product nor said a count ("네", "잠깐만요", "화면이 하나도 안 보여요"), the order that drew it
    is the earlier one: "아메리카노 두 잔 주세요" → question → "네" → same question → "아이스로요"
    is two cups. A count said on its own in between ("한 잔만요") is a correction, so the walk
    stops there; a count inside other words ("하나만 물어볼게요") is not one.
    """
    question = history[-1].result.reply_text
    index = len(history) - 1
    while (index > 0 and history[index - 1].result.status == "needs_clarification"
           and history[index - 1].result.reply_text == question
           and not answers_question(history[index].request.text, question)
           and not _name_positions(_compact(history[index].request.text), menu)
           and not (spoken_mentions(history[index].request.text, menu)[0]
                    and _cart_words_only(history[index].request.text))):
        index -= 1
    return history[index].request.text


ASK_MENU_REPLY = "어떤 메뉴를 주문할까요?"
PENDING = {"needs_confirmation", "needs_clarification"}
# Everything a bare instruction about the one thing in the cart may be made of: a count,
# the words for more/less/change, a pointer such as "그거", particles and a polite ending.
# "하나 더요", "한 잔 더 주세요", "두 잔으로 해 주세요", "그거 빼 줘", "같은 걸로 하나 더요" reduce to
# nothing; "샷 하나 추가해 주세요", "얼음 빼고 주세요", "화면이 하나도 안 보여요" leave words behind.
_ACTION_TOKENS = ("더", "빼", "취소", "삭제", "없애", "지워", "제거", "바꿔", "바꾸", "변경", "줄여", "늘려", "추가", "넣어")
_INSTRUCTION_TOKENS = tuple(sorted((
    "더", "빼", "취소", "삭제", "없애", "지워", "제거", "그거", "그것", "그걸", "이거", "이것", "이걸", "저거", "저것",
    "바꿔", "바꾸", "변경", "줄여", "늘려", "추가", "넣어", "부탁", "같은", "걸로", "아까", "으로", "로", "만", "씩", "은",
    "는", "이", "가", "을", "를", "도", "요", "주세요", "주시겠어요", "주실래요", "주십시오", "줘", "줄래", "해주세요",
    "해줘", "해주", "해", "고", "좀", "다", "하", "것",
), key=len, reverse=True))


def _cart_tokens(text: str) -> list[str] | None:
    """The instruction tokens the utterance is made of besides counts, or None when other words remain."""
    rest = _COUNT.sub("", _compact(text))
    tokens = []
    while rest:
        for token in _INSTRUCTION_TOKENS:
            if rest.startswith(token):
                tokens.append(token)
                rest = rest[len(token):]
                break
        else:
            return None
    return tokens


def _cart_words_only(text: str) -> bool:
    """Whether the utterance is nothing but counts, pointers, particles and endings ("한 잔만요")."""
    return bool(_compact(text)) and _cart_tokens(text) is not None


def is_cart_instruction(text: str) -> bool:
    """Whether the whole utterance is an instruction about what is already in the cart."""
    if not _compact(text):
        return False
    tokens = _cart_tokens(text)
    if tokens is None:
        return False
    # A pointer alone ("그걸로요") or a bare count ("하나만요", "두 잔이요": more, or that many?)
    # instructs nothing: an action word ("더", "빼", "(으)로", "추가") is needed.
    return (any(kind != "abs" for _, kind, _ in spoken_mentions(text, [])[0])
            or any(token in _ACTION_TOKENS for token in tokens))


def answers_question(text: str, question: str = "") -> bool:
    """Whether the utterance answers what the kiosk asked.

    A temperature question ("따뜻한 것과 아이스 중?") is answered only by a temperature word:
    "화면 아래로 내려주세요", "네네" and "하나도 모르겠어요" answer nothing, so the question's
    product and count must not become their order. Any other question is answered by a
    temperature, a count, "그거" or an acceptance.
    """
    compact = _compact(text)
    if _TEMPERATURE.search(_compact(question)):
        return bool(_TEMPERATURE.search(compact))
    return bool(is_acceptance(text) or _TEMPERATURE.search(compact) or _COUNT.search(compact)
                or any(mark in compact for mark in ("그거", "그것", "그걸로", "이거", "저거")))


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

    now = [_compact(request.text)]
    # A recognition alternative counts only when the chosen text names nothing and the
    # recognizer was at least half sure of it: a 1% alternative must not pick the product.
    alternatives = [_compact(item.text) for item in request.alternatives if (item.confidence or 0) >= 0.5]
    # The last reply's product applies to an answer to its question, or to any reply to an
    # open offer (which is only ever read back again, never run, unless accepted).
    asked = ([_compact(history[-1].result.reply_text)]
             if history and history[-1].result.reply_text
             and (answers_question(request.text, history[-1].result.reply_text)
                  or history[-1].result.status == "needs_confirmation") else [])
    asked_products = named_in(asked)
    lines = list(cart)
    if (history and history[-1].result.status == "needs_clarification" and len(asked_products) > 1):
        # "아이스 아메리카노, 따뜻한 카페 라떼 중 어느 것?" answered by "아이스요" picks the one line
        # with that temperature; answered by "그거요", neither is chosen, so neither counts.
        spoken = {SPOKEN_TEMPERATURES[found.group()] for found in _TEMPERATURE.finditer(now[0])}
        fitting = {line.product_id for line in lines if line.product_id in asked_products and line.temperature in spoken}
        asked_products = fitting if len(spoken) == 1 and len(fitting) == 1 else set()
    allowed = named_in(now) or named_in(alternatives) or asked_products
    sole = lines[0] if len(lines) == 1 else None
    in_cart = {line.product_id for line in lines}
    # The one cart line stands in for a product only when the whole utterance is an
    # instruction about the cart ("하나 더요", "한 잔 더 주세요", "두 잔으로 해 주세요", "그거 빼
    # 줘") and names no product. "샷 하나 추가해 주세요", "얼음 빼고 주세요", "이거 얼마예요?"
    # and a stray "네네" with no offer open all leave other words behind and name nothing.
    mentions_product = any(w in text for item_words in words.values() for w in item_words for text in now)
    instruction = not mentions_product and is_cart_instruction(request.text)
    removing = any(_REMOVAL.search(text) for text in now)
    question = (history[-1].result.reply_text if history and history[-1].result.status == "needs_clarification"
                and (history[-1].result.reply_text or "").endswith("?") else None)
    for call in result.tool_calls:
        product_id = call.arguments.product_id
        if allowed:
            if product_id in allowed:
                continue
        elif product_id in in_cart and instruction and (removing or not isinstance(call, RemoveCartItemCall)):
            if sole is not None and call.arguments.temperature in (None, sole.temperature):
                continue  # the one thing in the cart is the only thing "그거" can mean
            return VoiceInterpretation(
                status="needs_clarification", tool_calls=[], reply_text=which_in_cart_reply(lines, menu),
            )
        shared = [w for w in words.get(product_id, []) if uses[w] > 1 and any(w in text for text in now)]
        if shared:
            reply = f"{max(shared, key=len)} 중 어떤 메뉴로 할까요?"
        elif question is not None and not mentions_product:
            # An unanswered question ("따뜻한 것과 아이스 중?", "A, B 중 어느 것?") is asked again,
            # so "핫으로요" or "그거요" does not throw the order away.
            reply = question
        else:
            reply = ASK_MENU_REPLY
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
                result = match_spoken_details(
                    result, request, cart, menu, history,
                    proposal.tool_calls if proposal is not None and is_acceptance(request.text) else None)
                result = require_cart_items(result, cart, menu)
            if result is not None and not matches_menu(result, menu):
                logger.warning("voice interpretation rejected (not on menu)")
                result = None
            if (result is not None and result.status in ("completed", "needs_confirmation") and proposal is not None
                    and result.tool_calls == proposal.tool_calls and not is_acceptance(request.text)):
                # The model repeated the offer, but the customer did not take it: "아니요 그거
                # 말고요" turns it down, so ask what to order; "음 잠깐만요" is unclear, so
                # read the offer back again. Only a yes runs it.
                if is_rejection(request.text):
                    result = VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=ASK_MENU_REPLY)
                else:
                    result = VoiceInterpretation(status="needs_confirmation", tool_calls=result.tool_calls, reply_text="?")
            if (result is not None and result.status == "completed" and proposal is not None
                    and result.tool_calls == proposal.tool_calls and is_acceptance(request.text)):
                # "네 그걸로 주세요" takes the offer as read back, like a bare "네": it runs on
                # the cart the offer was checked against, so a touch in between is caught.
                expected = proposal.cart
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
