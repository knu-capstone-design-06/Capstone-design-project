import { ApiError } from '../../shared/api/client.ts';
import type { FeatureWindowRequest, FeatureWindowResponse } from '../../shared/api/types.ts';
import type { SavedLog } from './touchLog.ts';
import { buildTouchFeatureWindow } from './interactionFeatures.ts';

type Send = (session: string, window: FeatureWindowRequest, signal: AbortSignal) => Promise<FeatureWindowResponse>;
export type TransmissionState = { state: 'idle' | 'skipped' | 'sending' | 'sent' | 'error' | 'stopped'; sent: number; lastWindowEnd: string | null };

/** Best-effort live samples: no replay of stale windows and no UI decisions from responses. */
export function createTouchFeatureTransport(send: Send, read: () => SavedLog, now = Date.now) {
  let session: string | null = null, allowed = false, sequence = 0, generation = 0;
  let active: AbortController | null = null;
  let stoppedSession: string | null = null;
  let status: TransmissionState = { state: 'idle', sent: 0, lastWindowEnd: null };
  function cancel() { generation++; active?.abort(); active = null; }
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
      const saved = read();
      if (saved.serverSessionId !== session) return;
      const window = buildTouchFeatureWindow(saved, now(), sequence + 1);
      if (!window) { status = { ...status, state: 'skipped' }; return; }
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
