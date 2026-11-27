import { ApiError } from '../../shared/api/client.ts';
import type { FeatureWindowRequest, FeatureWindowResponse } from '../../shared/api/types.ts';
import type { FeatureLog } from './touchLog.ts';
import { buildTouchFeatureWindow, FEATURE_WINDOW_MS, featureInputLookbackStart, hasFeatureHistory } from './interactionFeatures.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';
import type { EngineTouchSend } from './engineTouchSender.ts';

type Send = (session: string, window: FeatureWindowRequest, signal: AbortSignal) => Promise<FeatureWindowResponse>;
type FeatureOfferContext = {
  key: string;
  canOffer: boolean;
  includeInteraction: boolean;
  receive: (response: FeatureWindowResponse) => void;
  /** Decisions the screen carries out without asking (highlight, notice); called with every current response, also while no offer can open. */
  act?: (response: FeatureWindowResponse) => void;
  /** The transmission state at every tick, so a held notice can end when answers stop (stopped, error, idle). */
  onState?: (state: TransmissionState['state']) => void;
  /** The screen's own gate for showing an ask (OrderPage canOfferSupport) when a window is built: its touch.scene_signals.can_offer (null without it). */
  askGate?: boolean;
};
export type TransmissionState = { state: 'idle' | 'skipped' | 'sending' | 'sent' | 'error' | 'stopped'; sent: number; lastWindowEnd: string | null };
/**
 * How often the screen calls tick() to see whether a window is due (the screen's existing 250 ms check, useBackendSupport).
 * Also the longest /features waits for the AI engine's answer to the same window.
 */
export const FEATURE_TICK_MS = 250;

/** Settles when the engine copy's request settled or after one tick, whichever comes first; never rejects. A sender that throws ends the wait at once. */
function engineAnswerOrTick(notifyEngine: EngineTouchSend, session: string, body: FeatureWindowRequest) {
  let answered: Promise<unknown>;
  try { answered = Promise.resolve(notifyEngine(session, body)); } catch { return Promise.resolve(); }
  return new Promise<void>(resolve => {
    const timer = setTimeout(resolve, FEATURE_TICK_MS);
    const done = () => { clearTimeout(timer); resolve(); };
    answered.then(done, done);
  });
}

function currentVisit(log: FeatureLog) {
  return [...log.events].reverse().find(event => event.sessionId === log.sessionId && event.kind === 'screen_enter')?.visitId;
}

function waitsForInputEnd(saved: FeatureLog, end: number, observedAt: number) {
  if (!hasFeatureHistory(saved, end)) return false;
  const earliest = featureInputLookbackStart(end);
  const pending = new Set<string>();
  for (const event of saved.events) {
    if (event.sessionId !== saved.sessionId) continue;
    const time = Date.parse(event.occurredAt);
    if (event.kind === 'pointer_start' && time > earliest && time <= end) pending.add(event.id);
    if ((event.kind === 'pointer_end' || event.kind === 'pointer_interrupted') && time <= observedAt) {
      const data = event.data as { inputId?: string } | null;
      if (data?.inputId) pending.delete(data.inputId);
    }
  }
  return pending.size > 0 && measureTouchPilot(saved, end, FEATURE_WINDOW_MS, undefined, observedAt).observed;
}

/**
 * One request at a time. Keep the window boundary while waiting for touches to end.
 * notifyEngine (optional) gets each window first, for the local AI engine; /features waits for the engine's answer at most one tick
 * (FEATURE_TICK_MS) and then goes with the same body. The engine copy can delay /features by one tick at most and never changes or
 * blocks it; the engine gets each window once, also when /features then fails. Without notifyEngine nothing waits.
 * A window that falls due before the next tick gets one extra check at its due moment, so it does not wait for the interval.
 */
export function createTouchFeatureTransport(send: Send, read: () => FeatureLog | null, now = Date.now, notifyEngine?: EngineTouchSend) {
  let session: string | null = null, allowed = false, sequence = 0, generation = 0;
  let active: AbortController | null = null;
  let stoppedSession: string | null = null;
  let nextWindowEnd: number | null = null;
  let lastAttemptedEnd: number | null = null;
  let offer: FeatureOfferContext | undefined;
  let offerRevision = 0;
  let offerSince = 0;
  let status: TransmissionState = { state: 'idle', sent: 0, lastWindowEnd: null };
  // The extra check at a window's due moment (tick()): its timer while pending, and the window end it was made for (one per window).
  let dueCheck: ReturnType<typeof setTimeout> | null = null, dueCheckEnd: number | null = null;
  function cancel() {
    generation++; active?.abort(); active = null;
    if (dueCheck !== null) clearTimeout(dueCheck);
    dueCheck = null; dueCheckEnd = null;
  }
  const transport = {
    status: () => ({ ...status }),
    setContext(nextSession: string | null, enabled: boolean, nextOffer?: FeatureOfferContext) {
      if (offer?.key !== nextOffer?.key || offer?.canOffer !== nextOffer?.canOffer) {
        offerRevision++;
        offerSince = now();
      }
      offer = nextOffer;
      if (session !== nextSession) {
        cancel(); session = nextSession; sequence = 0; stoppedSession = null;
        nextWindowEnd = null; lastAttemptedEnd = null;
        status = { state: 'idle', sent: 0, lastWindowEnd: null };
      }
      if (!enabled) { cancel(); status = { ...status, state: 'idle' }; }
      allowed = enabled;
    },
    async tick() {
      offer?.onState?.(status.state);
      if (!allowed || !session || active || stoppedSession === session) return;
      const observedAt = now();
      const end = nextWindowEnd ?? observedAt - 1;
      // A later event can still receive the current millisecond's timestamp.
      if (end >= observedAt) {
        // The window is due at end + 1, the first millisecond with end < now. When that comes before the next tick, check once
        // more at that moment; the guards above and below still keep one request at a time and each window sent once.
        const dueIn = end + 1 - observedAt;
        if (dueCheck === null && dueCheckEnd !== end && dueIn < FEATURE_TICK_MS) {
          dueCheckEnd = end;
          dueCheck = setTimeout(() => { dueCheck = null; void transport.tick(); }, dueIn);
        }
        return;
      }
      if (lastAttemptedEnd !== null && end - FEATURE_WINDOW_MS < lastAttemptedEnd) return;
      const saved = read();
      if (saved?.serverSessionId !== session) return;
      const window = buildTouchFeatureWindow(saved, end, sequence + 1, observedAt, offer?.askGate ?? null);
      if (!window) {
        nextWindowEnd = waitsForInputEnd(saved, end, observedAt) ? end : null;
        status = { ...status, state: 'skipped' };
        return;
      }
      nextWindowEnd = end + FEATURE_WINDOW_MS;
      lastAttemptedEnd = end;
      sequence++;
      const controller = new AbortController(), token = generation, requestSession = session;
      const requestOfferRevision = offerRevision;
      // The two pilot blocks (interaction, scene_signals) go only with the pilot flag; the base request keeps the five counts.
      const { interaction, scene_signals: _sceneSignals, ...baseTouch } = window.touch;
      const visitId = interaction?.visit_id;
      const body = offer?.includeInteraction === false ? { ...window, touch: baseTouch } : window;
      active = controller; status = { ...status, state: 'sending' };
      if (notifyEngine) {
        // The engine answers after handing on the windows this touch window releases when it can within its window interval,
        // so the /features request that follows usually reads them. Handing on and reading are best effort: a window whose
        // send ended in a failure may or may not have reached the backend, and a window replaced before it was sent or one
        // that arrives after the pairing span is read by no request. Its failure or delay never reaches this request or its
        // handling. The window stays busy while waiting.
        await engineAnswerOrTick(notifyEngine, requestSession, body);
        // A session change, setContext(..., false) or dispose() during the wait abandons the window (cancel() cleared active).
        if (generation !== token) return;
      }
      // The 5 s abort covers the /features request only.
      const timer = setTimeout(() => controller.abort(), 5000);
      try {
        const response = await send(requestSession, body, controller.signal);
        if (generation !== token) return;
        if (controller.signal.aborted || response.session_id !== requestSession) throw new Error('Invalid feature response');
        status = { state: 'sent', sent: status.sent + 1, lastWindowEnd: window.window_end };
        // Backlogged windows still count for telemetry. Their old context cannot open an offer.
        if ((offer?.canOffer || offer?.act) && requestOfferRevision === offerRevision && end >= offerSince - 1 && visitId) {
          const current = read();
          if (current?.sessionId === saved.sessionId && current.serverSessionId === requestSession
            && currentVisit(current) === visitId) {
            offer.act?.(response);
            if (offer.canOffer) offer.receive(response);
          }
        }
      } catch (error) {
        if (generation !== token) return;
        // Missing/finished sessions and incompatible contracts require a new session or reload.
        const terminal = error instanceof ApiError && [400, 401, 403, 404, 410, 422].includes(error.status);
        if (terminal) stoppedSession = requestSession;
        status = { ...status, state: terminal ? 'stopped' : 'error' };
      } finally {
        clearTimeout(timer);
        if (active === controller) active = null;
      }
    },
    dispose() { allowed = false; cancel(); },
  };
  return transport;
}
