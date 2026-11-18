import { ApiError } from '../../shared/api/client.ts';
import type { FeatureWindowRequest, FeatureWindowResponse } from '../../shared/api/types.ts';
import type { FeatureLog } from './touchLog.ts';
import { buildTouchFeatureWindow, FEATURE_WINDOW_MS, featureInputLookbackStart, hasFeatureHistory } from './interactionFeatures.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';

type Send = (session: string, window: FeatureWindowRequest, signal: AbortSignal) => Promise<FeatureWindowResponse>;
export type TransmissionState = { state: 'idle' | 'skipped' | 'sending' | 'sent' | 'error' | 'stopped'; sent: number; lastWindowEnd: string | null };

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
export function createTouchFeatureTransport(send: Send, read: () => FeatureLog, now = Date.now) {
  let session: string | null = null, allowed = false, sequence = 0, generation = 0;
  let active: AbortController | null = null;
  let stoppedSession: string | null = null;
  let nextWindowEnd: number | null = null;
  let status: TransmissionState = { state: 'idle', sent: 0, lastWindowEnd: null };
  function cancel() { generation++; active?.abort(); active = null; nextWindowEnd = null; }
  return {
    status: () => ({ ...status }),
    setContext(nextSession: string | null, enabled: boolean) {
      if (session !== nextSession) {
        cancel(); session = nextSession; sequence = 0; stoppedSession = null;
        status = { state: 'idle', sent: 0, lastWindowEnd: null };
      }
      allowed = enabled;
      if (!enabled) { cancel(); status = { ...status, state: 'idle' }; }
    },
    async tick() {
      if (!allowed || !session || active || stoppedSession === session) return;
      const observedAt = now();
      const end = nextWindowEnd ?? observedAt - 1;
      // A later event can still receive the current millisecond's timestamp.
      if (end >= observedAt) return;
      const saved = read();
      if (saved.serverSessionId !== session) return;
      const window = buildTouchFeatureWindow(saved, end, sequence + 1, observedAt);
      if (!window) {
        nextWindowEnd = waitsForInputEnd(saved, end, observedAt) ? end : null;
        status = { ...status, state: 'skipped' };
        return;
      }
      nextWindowEnd = end + FEATURE_WINDOW_MS;
      sequence++;
      const controller = new AbortController(), token = generation, requestSession = session;
      active = controller; status = { ...status, state: 'sending' };
      const timer = setTimeout(() => controller.abort(), 5000);
      try {
        const response = await send(requestSession, window, controller.signal);
        if (generation !== token) return;
        if (controller.signal.aborted || response.session_id !== requestSession) throw new Error('Invalid feature response');
        status = { state: 'sent', sent: status.sent + 1, lastWindowEnd: window.window_end };
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
