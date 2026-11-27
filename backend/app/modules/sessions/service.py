import logging
from datetime import datetime, timezone

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.infrastructure.external.ai_client import AiEngineClient
from app.infrastructure.external.ai_schemas import AnalyzeRequest
from app.modules.decision.rule_table import execution
from app.modules.decision.schemas import BIG, LARGE_TEXT, LOWER, VOICE, Decision, WindowInput
from app.modules.decision.service import DecisionService, window_input
from app.modules.ordering.repository import OrderingRepository
from app.modules.sessions.exceptions import SessionCompleted, SessionNotFound
from app.modules.sessions.repository import SessionRepository
from app.modules.sessions.schemas import (
    FeatureWindowRequest, FeatureWindowResponse, InteractionPilot, PilotSettings, SceneSignalsPilot,
    SessionCreateResponse, StateScores, SupportDecision, TouchFeatures, VisionWindowAccepted, VisionWindowRequest,
)


logger = logging.getLogger(__name__)

# The transitions after which the decision's support is on the screen (the set Decision.form() reads).
SHOWN = ("open", "replace", "keep")


def support_answer(decision: Decision, now: WindowInput | None = None) -> SupportDecision:
    """The /features answer's support for a rule-table decision (DECISION_SEND_SUPPORT on): Decision.form() and, while
    the decision shows a support, its name, its id and its execution fields. Anything else (none, withdraw, a window
    recorded only) answers the placeholder's preset none.

    The execution fields (steps_left, target_id, message_id) describe the window being answered: a kept decision
    repeats those fixed when it opened, so for keep they come from the rule table's own execution() on `now`, this
    window's input line (a 4-2 opened on the plain menu points at cart-add once the options sheet is open). An
    opened or replacing decision already holds this window's. decision_id stays the held decision's.
    """
    if decision.transition not in SHOWN or decision.support is None:
        return SupportDecision()
    preset, confirm = decision.form()
    fields = execution(decision.support, now) if decision.transition == "keep" and now is not None \
        else decision.execution
    return SupportDecision(preset=preset, requires_confirmation=confirm, name=decision.support,
                           decision_id=decision.decision_id, steps_left=fields.get("steps_left"),
                           target_id=fields.get("target_id"), message_id=fields.get("message_id"))


def seen_without_touch(window: FeatureWindowRequest, paired) -> bool:
    """A touch window without taps or backs whose paired AI engine window saw a face: measurable by the team
    placeholder's other basis (ai-engine app/inference/placeholder.py: a tap or back, or vision.face_detected),
    which ai-engine cannot apply to /features windows because they carry no vision value."""
    touch = window.touch
    return paired is not None and paired.face_seen and touch.tap_count == 0 and touch.back_count == 0


def measurable_here(window: FeatureWindowRequest, paired, pressed_before: bool) -> bool:
    """The team placeholder's rule of measurable (ai-engine app/inference/placeholder.py), read in the backend over
    the window's pairing span: a tap or a back in the window, or in an earlier touch window of the session that ended
    inside that span (pressed_before: DecisionService.pressed_before), or a face seen by its paired AI engine windows:
    the latest one or the one the situation came from (both in the bound and read by this window; a tag held in the
    earlier segment while the face was lost in the later one, a full turn toward the companion or the people behind,
    still counts). Press evidence and camera evidence are read over the same span, the one whose engine windows the
    decision reads: a cue that first reaches the touch window after the press's own still meets the press. Used under
    DECISION_SEND_SUPPORT, so the chain does not ride on the /v1/analyze answer (the team paper's figure 1 has no
    backend -> AI engine arrow)."""
    touch = window.touch
    seen = paired is not None and (paired.face_seen or paired.named.face_seen)
    return touch.tap_count > 0 or touch.back_count > 0 or pressed_before or seen


def interaction_inputs(touch: TouchFeatures) -> dict:
    """options_open and pause_s for the rule table from the order screen's pilot block touch.interaction.

    The demonstration mapping, read with DECISION_SEND_SUPPORT only; the team's touch contract decides the final
    definition. options_open as sent. pause_s as docs/Touch-Interaction-Contract-Proposal.md 4.3 proposes (the
    paragraph after its table): since_last_input_excluding_system_busy_ms / 1000 only, which already leaves out the
    order's loading/saving and voice processing/speaking time; None when it is missing (no fallback to the raw
    since_last_input_ms or to dwell_ms); None while voice_phase is listening or microphone_active is true (the user is
    speaking, which the corrected value does not leave out). {} when the block is absent or malformed: both inputs
    stay None.
    """
    if touch.interaction is None:
        return {}
    try:
        block = InteractionPilot.model_validate(touch.interaction)
    except ValidationError:
        return {}
    since_ms = block.since_last_input_excluding_system_busy_ms
    speaking = block.voice_phase == "listening" or block.microphone_active is True
    pause_s = None if speaking or since_ms is None else since_ms / 1000
    return {"options_open": block.options_open, "pause_s": pause_s}


# The pilot block's settings as the rule-table supports they are (ui_settings key -> support; voice_enabled -> VOICE).
SETTING_SUPPORTS = {"large_text": LARGE_TEXT, "large_button": BIG, "low_screen": LOWER}


def settings_on(touch: TouchFeatures) -> tuple | None:
    """The supports the customer already has on at the window end, from touch.interaction (PilotSettings), read with
    DECISION_SEND_SUPPORT only: each ui_settings value that is true, and voice ordering when voice_enabled is true.
    The rule table counts them as active (no ask for what the customer has). None when the block is absent or its
    settings are malformed: not known, and the rows behave as without the block."""
    if touch.interaction is None:
        return None
    try:
        block = PilotSettings.model_validate(touch.interaction)
    except ValidationError:
        return None
    ui = block.ui_settings
    on = [support for key, support in SETTING_SUPPORTS.items() if ui is not None and getattr(ui, key) is True]
    return (*on, VOICE) if block.voice_enabled is True else tuple(on)


def scene_signal_inputs(touch: TouchFeatures) -> dict:
    """fixes_segment, zoom_attempts_segment and can_offer for the rule table from the order screen's block
    touch.scene_signals (SceneSignalsPilot), read with DECISION_SEND_SUPPORT only: this window's two counts and the
    screen's ask gate as sent, null as None. All None when the block is absent, malformed or of another version. The
    decision service sums the counts over the recent span (fixes_recent for 4-1, zoom_attempt for 2-1); the rows 1-1
    and 1-2 read can_offer."""
    block = None
    if touch.scene_signals is not None:
        try:
            block = SceneSignalsPilot.model_validate(touch.scene_signals)
        except ValidationError:
            block = None
    return {"fixes_segment": block.near_miss_fix_count if block else None,
            "zoom_attempts_segment": block.zoom_attempt_count if block else None,
            "can_offer": block.can_offer if block else None}


class SessionService:
    def __init__(self, repository: SessionRepository, ordering: OrderingRepository,
                 decision: DecisionService | None = None, send_support: bool = False):
        self._repository = repository
        self._ordering = ordering
        # Shadow judgment layer: runs beside the response and never changes it (docs/Jev-Integration.md), unless
        # send_support (DECISION_SEND_SUPPORT, the demonstration switch) puts the rule table's decision in support.
        self._decision = decision
        self._send_support = send_support

    def exists(self, session_id: str) -> bool:
        return self._repository.exists(session_id)

    def _cart_items(self, session_id: str) -> int:
        """Items in the session's cart (its total quantity), read the way the ordering service reads the cart (under
        the repository's lock). Synchronous: called through run_in_threadpool, like is_completed."""
        with self._ordering.lock:
            return self._ordering.state(session_id).cart.total_quantity

    def create(self) -> SessionCreateResponse:
        return self._repository.create()

    async def receive_vision(self, session_id: str, window: VisionWindowRequest) -> VisionWindowAccepted:
        """Keep a window the AI engine posted (situation tags, gaze, face) for the /features windows of the session.

        The same refusals as /features: an unknown session, a session whose order is complete. Without a judgment
        layer nothing reads the window, so it is acknowledged and not kept.
        """
        received_at = datetime.now(timezone.utc)
        if not await run_in_threadpool(self._repository.exists, session_id):
            raise SessionNotFound()
        if await run_in_threadpool(self._ordering.is_completed, session_id):
            raise SessionCompleted()
        if self._decision is not None:
            noted = self._decision.add_vision(session_id, window, received_at=received_at)
            if self._send_support and noted is not None:
                # One line per engine window that brought new 2-2 event ids, so a demonstration run shows why 2-2 did or
                # did not open (DecisionRepository.note_user_changed).
                if noted.reason is None:
                    logger.info("new customer event session=%s engine_window_end=%s ids=%s pending", session_id,
                                window.window_end.isoformat(), ",".join(noted.ids))
                else:
                    logger.info("new customer event session=%s engine_window_end=%s ids=%s remembered only: %s",
                                session_id, window.window_end.isoformat(), ",".join(noted.ids), noted.reason)
        return VisionWindowAccepted()

    async def analyze(
        self, session_id: str, window: FeatureWindowRequest, ai: AiEngineClient
    ) -> FeatureWindowResponse:
        received_at = datetime.now(timezone.utc)   # kept with the window record: before the ai-engine round trip
        if not await run_in_threadpool(self._repository.exists, session_id):
            raise SessionNotFound()
        if await run_in_threadpool(self._ordering.is_completed, session_id):
            raise SessionCompleted()
        request = AnalyzeRequest(
            session_id=session_id, **window.model_dump(exclude_unset=True)
        )
        result = await ai.analyze(request)
        # An order may complete while the AI request is in flight.
        if await run_in_threadpool(self._ordering.is_completed, session_id):
            raise SessionCompleted()
        # The scores are checked before the judgment layer sees the window, so both read it the same way: scores
        # the response rejects (ai_available=false) make the table record a window that was not measurable.
        valid, states = result is not None, None
        if result is not None and result.measurable:
            try:
                states = StateScores.model_validate(result.states)
            except ValidationError:
                valid = False
        decision = now = None
        if self._decision is not None:
            ai = ("unavailable" if result is None else "invalid_scores" if not valid
                  else "ok" if result.measurable else "unmeasurable")
            try:
                # The pilot block's two values only under the demonstration switch: the default mode's records
                # stay as they are.
                pilot = {**interaction_inputs(window.touch), **scene_signal_inputs(window.touch),
                         "supports_on": settings_on(window.touch)} if self._send_support else {}
                if self._send_support and window.touch.tap_count > 0:
                    # 2-2 reads the session's own cart on a window with a press (no new field in the window).
                    pilot["cart_items"] = await run_in_threadpool(self._cart_items, session_id)
                # Placed first, with no await before observe(), so the engine windows and the earlier presses are read
                # on the timeline this window is placed on (a window that confirms a clock move has started the new
                # epoch). A window recorded only (late, or off the timeline) pairs nothing and moves no pairing bound.
                placed = self._decision.place(session_id, window)
                # The AI engine's window for this stretch or the one before: its situation and gaze go to the table.
                paired = self._decision.paired_vision(session_id, window) if placed else None
                if self._send_support:
                    # Whatever /v1/analyze returned (down, slow, invalid): a tap or a back in this window or in an
                    # earlier one inside its pairing span, or the face.
                    measurable = measurable_here(window, paired, self._decision.pressed_before(session_id, window))
                else:
                    measurable = valid and (result.measurable or seen_without_touch(window, paired))
                situation = paired.situation if paired is not None else None
                if self._send_support and paired is not None:
                    # The scene tags of every engine window in the bound, for the scene rows (true when any says true).
                    situation = {**situation, "tags": paired.scene_tag_states()}
                decision = self._decision.observe(
                    session_id, window, measurable=measurable, ai=ai, situation=situation,
                    gaze=paired.gaze if paired is not None else None,
                    ai_model_version=result.model_version if result is not None else None,
                    received_at=received_at, vision=paired, placed=placed, **pilot)
                if self._send_support:
                    # This window's input line for the answer's execution fields (what execution() reads: the
                    # screen, its steps left and the options dialog).
                    now = window_input(window, measurable, **pilot)
                    # One line per window, so a demonstration run can be read afterwards (review row 9).
                    # The situation's own engine window is named too when it is not the latest one (the gaze's).
                    situation_from = "" if paired is None or paired.situation_window_end == paired.window_end \
                        else f" situation_window_end={paired.situation_window_end.isoformat()}"
                    logger.info("decision window session=%s window_end=%s transition=%s support=%s scene=%s "
                                "measurable=%s engine_window_end=%s situation=%s%s", session_id,
                                window.window_end.isoformat(), decision.transition, decision.support, decision.scene,
                                measurable, paired.window_end.isoformat() if paired is not None else None,
                                paired.situation.get("name") if paired is not None else None, situation_from)
            except Exception:
                # The judgment layer is in shadow mode: a failure there must not touch the response.
                logger.exception("decision layer failed; response unchanged")
        # The rule table's result as it stands: the answer never waits for Jev, whose answers stay records only. Under
        # the switch it is answered whenever the decision layer ran, ai_available false included (ai_available keeps
        # its meaning: whether the /v1/analyze analysis answered); with the switch off, preset none as before.
        support = support_answer(decision, now) if self._send_support and decision is not None else SupportDecision()
        if not valid:
            return FeatureWindowResponse(session_id=session_id, ai_available=False, support=support)
        return FeatureWindowResponse(
            session_id=session_id, ai_available=True,
            states=states, model_version=result.model_version, support=support,
        )
