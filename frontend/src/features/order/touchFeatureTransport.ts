import { ApiError } from '../../shared/api/client.ts';
import type { FeatureWindowRequest, FeatureWindowResponse } from '../../shared/api/types.ts';
import type { FeatureLog } from './touchLog.ts';
import { buildTouchFeatureWindow, FEATURE_WINDOW_MS, featureInputLookbackStart, hasFeatureHistory } from './interactionFeatures.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';

type Send = (session: string, window: FeatureWindowRequest, signal: AbortSignal) => Promise<FeatureWindowResponse>;
type FeatureOfferContext = {
  key: string;
  canOffer: boolean;
  includeInteraction: boolean;
  receive: (response: FeatureWindowResponse) => void;
};
export type TransmissionState = { state: 'idle' | 'skipped' | 'sending' | 'sent' | 'error' | 'stopped'; sent: number; lastWindowEnd: string | null };

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

/** One request at a time. Keep the window boundary while waiting for touches to end. */
export function createTouchFeatureTransport(send: Send, read: () => FeatureLog | null, now = Date.now) {
  let session: string | null = null, allowed = false, sequence = 0, generation = 0;
  let active: AbortController | null = null;
  let stoppedSession: string | null = null;
  let nextWindowEnd: number | null = null;
  let lastAttemptedEnd: number | null = null;
  let offer: FeatureOfferContext | undefined;
  let offerRevision = 0;
  let offerSince = 0;
  let status: TransmissionState = { state: 'idle', sent: 0, lastWindowEnd: null };
  function cancel() { generation++; active?.abort(); active = null; }
  return {
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
      if (!allowed || !session || active || stoppedSession === session) return;
      const observedAt = now();
      const end = nextWindowEnd ?? observedAt - 1;
      // A later event can still receive the current millisecond's timestamp.
      if (end >= observedAt || (lastAttemptedEnd !== null && end - FEATURE_WINDOW_MS < lastAttemptedEnd)) return;
      const saved = read();
      if (saved?.serverSessionId !== session) return;
      const window = buildTouchFeatureWindow(saved, end, sequence + 1, observedAt);
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
      const { interaction, ...baseTouch } = window.touch;
      const visitId = interaction?.visit_id;
      const body = offer?.includeInteraction === false ? { ...window, touch: baseTouch } : window;
      active = controller; status = { ...status, state: 'sending' };
      const timer = setTimeout(() => controller.abort(), 5000);
      try {
        const response = await send(requestSession, body, controller.signal);
        if (generation !== token) return;
        if (controller.signal.aborted || response.session_id !== requestSession) throw new Error('Invalid feature response');
        status = { state: 'sent', sent: status.sent + 1, lastWindowEnd: window.window_end };
        // Backlogged windows still count for telemetry. Their old context cannot open an offer.
        if (offer?.canOffer && requestOfferRevision === offerRevision && end >= offerSince - 1 && visitId) {
          const current = read();
          if (current?.sessionId === saved.sessionId && current.serverSessionId === requestSession
            && currentVisit(current) === visitId) offer.receive(response);
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
}
