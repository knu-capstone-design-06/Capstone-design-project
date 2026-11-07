import type { FeatureWindowRequest, TouchFeatures } from '../../shared/api/types.ts';
import type { LogEvent, SavedLog } from './touchLog.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';

const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {};
const at = (event: LogEvent) => Date.parse(event.occurredAt);
const data = (event: LogEvent) => object(event.data);
const busy = (state: Record<string, unknown>) => state.status === 'loading' || state.status === 'saving';
const last = (events: LogEvent[], predicate: (event: LogEvent) => boolean) => [...events].reverse().find(predicate);

/** Existing local pilot policy, with observable interaction counts. No discomfort labels. */
export function buildTouchFeatureWindow(saved: SavedLog, now: number, sequence: number): FeatureWindowRequest | null {
  if (!saved.serverSessionId) return null;
  const pilot = measureTouchPilot(saved, now);
  // The existing five required integer fields cannot represent unobserved values.
  if (!pilot.observed || Object.values(pilot.features).some(value => value === null)) return null;
  const events = saved.events.filter(e => e.sessionId === saved.sessionId && e.serverSessionId === saved.serverSessionId && at(e) <= now);
  const current = events.at(-1);
  if (!current || current.screen === 'complete') return null;
  const window = events.filter(e => at(e) > pilot.from);
  const count = (kind: string) => window.filter(e => e.kind === kind).length;
  const changed = (kind: string) => {
    const baseline = events.find(e => e.kind === kind);
    return window.filter(e => e.kind === kind && (data(e).before !== null || e !== baseline));
  };
  const lastState = (kind: string) => {
    const event = last(events, e => e.kind === kind);
    return event ? object(data(event).after) : null;
  };
  const order = lastState('order_state_change');
  if (!order || order.completed !== false || !['ready', 'saving'].includes(String(order.status))) return null;
  const voice = lastState('voice_state_change');
  const selectionEvent = last(events, e => e.kind === 'selection_state_change');
  const settings = object(current.settings);

  // Integrate the observed UI busy state, including a request already pending at window start.
  const baseline = last(events, e => e.kind === 'order_state_change' && at(e) <= pilot.from);
  let orderBusyMs: number | null = baseline ? 0 : null;
  if (baseline) {
    let previous = object(data(baseline).after), cursor = pilot.from;
    for (const event of window.filter(e => e.kind === 'order_state_change')) {
      if (busy(previous)) orderBusyMs! += at(event) - cursor;
      previous = object(data(event).after); cursor = at(event);
    }
    if (busy(previous)) orderBusyMs! += now - cursor;
  }
  let revisits: number | null = events.some(e => e.kind === 'session_start') ? 0 : null;
  const seen = new Set<string>();
  for (const event of events.filter(e => e.kind === 'screen_enter')) {
    if (revisits !== null && at(event) > pilot.from && seen.has(event.screen)) revisits++;
    seen.add(event.screen);
  }
  const cartChanges = changed('order_state_change').filter(e => {
    const before = object(object(data(e).before).cart), after = object(object(data(e).after).cart);
    return typeof before.version === 'number' && typeof after.version === 'number' && after.version > before.version;
  }).length;
  // Continuous distance evidence avoids inventing a near-button threshold or intended target.
  const outsideDistances = window.filter(e => e.kind === 'pointer_start' && data(e).target === null).flatMap(e => {
    const candidates = data(e).nearestCandidates;
    if (!Array.isArray(candidates)) return [];
    const distances = candidates.map(candidate => object(candidate).distance)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0);
    return distances.length ? [Math.min(...distances)] : [];
  });
  const touch = pilot.features as TouchFeatures;
  return {
    screen_id: current.screen,
    window_start: new Date(pilot.from).toISOString(), window_end: new Date(now).toISOString(),
    vision: null,
    touch: {
      ...touch,
      interaction: {
        schema_version: 'touch-interaction-pilot-v1', visit_id: current.visitId, window_sequence: sequence,
        outside_tap_ratio: touch.tap_count ? touch.miss_tap_count / touch.tap_count : null,
        outside_nearest_distance_mean_px: outsideDistances.length
          ? outsideDistances.reduce((sum, value) => sum + value, 0) / outsideDistances.length : null,
        outside_nearest_distance_sample_count: outsideDistances.length,
        pointer_cancel_count: window.filter(e => e.kind === 'pointer_end' && data(e).cancelled === true).length,
        pointer_interrupted_count: count('pointer_interrupted'), scroll_event_count: count('scroll'),
        category_change_count: count('category_change'), options_open_count: count('options_open'), options_close_count: count('options_close'),
        screen_transition_count: window.filter(e => e.kind === 'screen_enter' && typeof data(e).from === 'string').length,
        screen_revisit_count: revisits, cart_change_count: cartChanges,
        selection_change_count: events.some(e => e.kind === 'session_start')
          && events.some(e => e.kind === 'selection_state_change' && data(e).before === null)
          ? changed('selection_state_change').length : null,
        ui_settings_change_count: count('ui_settings_change'), voice_state_change_count: changed('voice_state_change').length,
        since_last_input_ms: pilot.sinceLastInputMs, order_busy_ms: orderBusyMs === null ? null : Math.round(orderBusyMs),
        options_open: selectionEvent ? data(selectionEvent).after !== null : null,
        order_busy: busy(order), voice_enabled: typeof voice?.enabled === 'boolean' ? voice.enabled : null,
        microphone_active: typeof voice?.microphoneActive === 'boolean' ? voice.microphoneActive : null,
        voice_processing: typeof voice?.phase === 'string' ? voice.phase === 'processing' : null,
        voice_auto_off: voice?.autoOff === 'silence' || voice?.autoOff === 'idle' ? voice.autoOff : null,
        ui_settings: {
          large_text: settings.largeText === true, large_button: settings.largeButton === true,
          simple_screen: settings.simpleScreen === true, step_guide: settings.stepGuide === true,
          low_screen: settings.lowScreen === true, high_contrast: settings.highContrast === true,
        },
      },
    },
  };
}
