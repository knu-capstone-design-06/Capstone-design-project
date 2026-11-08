import type { LogEvent } from './touchLog.ts';

const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {};
const at = (event: LogEvent) => Date.parse(event.occurredAt);
export function voicePhase(value: unknown): 'idle' | 'listening' | 'processing' | 'speaking' | null {
  return value === 'idle' || value === 'listening' || value === 'processing' || value === 'speaking' ? value : null;
}
export const voiceBusy = (phase: ReturnType<typeof voicePhase>) => phase === null ? null : phase === 'processing' || phase === 'speaking';

/** Integrate observed state intervals. Missing history stays unknown, never zero. */
export function observedWaitMs(events: LogEvent[], from: number, to: number, includeOrder: boolean): number | null {
  let phase: ReturnType<typeof voicePhase> = null;
  let order: boolean | null = null;
  const update = (event: LogEvent) => {
    const state = object(object(event.data).after);
    if (event.kind === 'voice_state_change') phase = voicePhase(state.phase);
    if (event.kind === 'order_state_change') order = ['loading', 'saving'].includes(String(state.status)) ? true
      : ['ready', 'idle', 'uncertain', 'disconnected', 'ended'].includes(String(state.status)) ? false : null;
  };
  for (const event of events) if (at(event) <= from) update(event);
  let cursor = from, total = 0;
  const add = (end: number) => {
    if (end === cursor) return true;
    const voice = voiceBusy(phase);
    if (voice === null || (includeOrder && order === null)) return false;
    if (voice || (includeOrder && order)) total += end - cursor;
    return true;
  };
  for (const event of events) {
    if (at(event) <= from || at(event) > to) continue;
    // A foreground gap cannot be reconstructed as user waiting.
    if (event.kind === 'session_suspend' || event.kind === 'session_end'
      || (event.kind === 'visibility_change' && object(event.data).visibility !== 'visible')) return null;
    if (!add(at(event))) return null;
    cursor = at(event); update(event);
  }
  return add(to) ? Math.round(total) : null;
}
