import assert from 'node:assert/strict';
import test from 'node:test';
import { createTouchLog } from './touchLog.ts';
import { buildTouchFeatureWindow } from './interactionFeatures.ts';
import { createTouchFeatureTransport } from './touchFeatureTransport.ts';
import { ApiError } from '../../shared/api/client.ts';

function fixture(session = 'server-1') {
  let clock = 0, id = 0;
  const recorder = createTouchLog(null, () => `e-${++id}`, () => clock);
  recorder.newSession(session);
  const context = { screen: 'menu', visitId: 'visit-1', settings: { largeText: true } };
  const ready = { status: 'ready', completed: false, cart: { version: 0, items: [] } };
  const record = (time, kind, data = null) => { clock = time; return recorder.record(context, kind, data); };
  record(0, 'session_start'); record(0, 'screen_enter', { visibility: 'visible' });
  record(0, 'order_state_change', { before: null, after: ready });
  record(0, 'selection_state_change', { before: null, after: null });
  record(0, 'voice_state_change', { before: null, after: { enabled: false, microphoneActive: false, phase: 'idle' } });
  const press = (time, target = null, cancelled = false) => {
    const inputId = record(time, 'pointer_start', { start: { x: 10, y: 20 }, target, pointerType: 'touch', isPrimary: true });
    record(time + 10, 'pointer_end', { inputId, cancelled, maxObservedDistance: 0, overlappingInputIds: [] });
  };
  return { recorder, record, context, ready, press };
}

test('same feature window carries five pilot metrics and contextual interaction observations', () => {
  const f = fixture();
  f.press(1100); f.press(1200, { id: 'increase', kind: 'button', disabled: false });
  f.record(1300, 'category_change', { from: '전체', to: '커피' });
  f.record(1400, 'options_open', { productId: 'americano' });
  f.record(1400, 'selection_state_change', { before: null, after: { productId: 'americano' } });
  f.record(1450, 'selection_state_change', { before: { quantity: 1 }, after: { quantity: 2 } });
  const pending = { ...f.ready, status: 'saving' };
  f.record(1500, 'order_state_change', { before: f.ready, after: pending });
  f.record(2200, 'order_state_change', { before: pending, after: { ...f.ready, cart: { version: 1 } } });
  f.record(2300, 'scroll'); f.record(2400, 'scroll');
  f.record(2500, 'ui_settings_change', { before: {}, after: { largeText: true } });
  const result = buildTouchFeatureWindow(f.recorder.read(), 3000, 2);
  assert.equal(result.window_start, new Date(1000).toISOString());
  assert.equal(result.touch.tap_count, 2); assert.equal(result.touch.miss_tap_count, 1);
  assert.equal(result.touch.dwell_ms, 3000);
  const extra = result.touch.interaction;
  assert.equal(extra.outside_tap_ratio, 0.5); assert.equal(extra.order_busy_ms, 700);
  assert.equal(extra.cart_change_count, 1); assert.equal(extra.options_open_count, 1);
  assert.equal(extra.category_change_count, 1); assert.equal(extra.selection_change_count, 2);
  assert.equal(extra.scroll_event_count, 2); assert.equal(extra.since_last_input_ms, 1800);
  assert.equal(extra.ui_settings.large_text, true); assert.equal(extra.options_open, true);
  assert.equal(extra.window_sequence, 2);
  assert(!JSON.stringify(result).includes('americano'), 'raw cart/menu selection details are not uploaded');
  assert(!JSON.stringify(result).includes('"x":'), 'raw pointer coordinates are not uploaded');
});

test('no input is distinct from unobserved windows and unobserved historical context', () => {
  const f = fixture();
  const saved = f.recorder.read();
  const result = buildTouchFeatureWindow(saved, 3000, 1);
  assert.equal(result.touch.tap_count, 0); assert.equal(result.touch.interaction.outside_tap_ratio, null);
  assert.equal(result.touch.interaction.since_last_input_ms, null);
  assert.equal(buildTouchFeatureWindow(saved, 1000, 1), null, 'startup window is not fully observed');
  assert.equal(buildTouchFeatureWindow({ ...saved, serverSessionId: null }, 3000, 1), null);
  saved.events = saved.events.filter(e => e.kind !== 'session_start');
  assert.equal(buildTouchFeatureWindow(saved, 3000, 1).touch.interaction.screen_revisit_count, null);
  f.record(2000, 'visibility_change', { visibility: 'hidden' });
  assert.equal(buildTouchFeatureWindow(f.recorder.read(), 3000, 1), null);
});

test('screen revisits and cancellations are observed without diagnosing confusion or failure', () => {
  const f = fixture();
  f.press(1100, null, true);
  f.record(1300, 'screen_leave', { to: 'review' });
  f.context.screen = 'review'; f.context.visitId = 'visit-2';
  f.record(1300, 'screen_enter', { from: 'menu', visibility: 'visible' });
  f.record(1600, 'screen_leave', { to: 'menu' });
  f.context.screen = 'menu'; f.context.visitId = 'visit-3';
  f.record(1600, 'screen_enter', { from: 'review', visibility: 'visible' });
  const result = buildTouchFeatureWindow(f.recorder.read(), 3000, 1);
  assert.equal(result.touch.back_count, 1); assert.equal(result.touch.dwell_ms, 1400);
  assert.equal(result.touch.interaction.pointer_cancel_count, 1);
  assert.equal(result.touch.interaction.screen_transition_count, 2);
  assert.equal(result.touch.interaction.screen_revisit_count, 1);
  assert.equal(result.touch.interaction.since_last_input_ms, null, 'last input does not cross visits');
});

test('completed sessions and currently unresolved pointer samples are not transmitted', () => {
  const f = fixture();
  f.record(2500, 'pointer_start', { start: { x: 0, y: 0 }, target: null, pointerType: 'touch', isPrimary: true });
  assert.equal(buildTouchFeatureWindow(f.recorder.read(), 3000, 1), null);
  const completed = fixture();
  completed.record(1000, 'order_state_change', { before: completed.ready, after: { ...completed.ready, completed: true } });
  assert.equal(buildTouchFeatureWindow(completed.recorder.read(), 3000, 1), null);
});

test('transport serializes requests, cancels an old session and ignores its late response', async () => {
  let f = fixture(), resolve;
  const calls = [];
  const sender = createTouchFeatureTransport((session, window, signal) => {
    calls.push({ session, window, signal }); return new Promise(r => { resolve = r; });
  }, () => f.recorder.read(), () => 3000);
  sender.setContext('server-1', true);
  const first = sender.tick(); await sender.tick(); assert.equal(calls.length, 1);
  sender.setContext('server-2', true); assert.equal(calls[0].signal.aborted, true);
  resolve({ session_id: 'server-1' }); await first; assert.equal(sender.status().sent, 0);
  f = fixture('server-2');
  const second = sender.tick(); assert.equal(calls[1].window.touch.interaction.window_sequence, 1);
  resolve({ session_id: 'server-2' }); await second;
  assert.equal(sender.status().sent, 1); sender.dispose();
});

test('failed transport sends a fresh sample later, while 410 stops this session', async () => {
  const f = fixture(); let now = 3000, attempts = 0, error = new TypeError('offline');
  const calls = [];
  const sender = createTouchFeatureTransport(async (session, window) => {
    attempts++; calls.push(window); if (error) throw error; return { session_id: session };
  }, () => f.recorder.read(), () => now);
  sender.setContext('server-1', true); await sender.tick(); assert.equal(sender.status().state, 'error');
  error = null; now = 5000; await sender.tick(); assert.equal(sender.status().sent, 1);
  assert.notEqual(calls[0].window_end, calls[1].window_end);
  error = new ApiError(410, {}); await sender.tick(); await sender.tick(); assert.equal(attempts, 3);
  assert.equal(sender.status().state, 'stopped'); sender.dispose();
});

test('disabled upload never sends and suspension aborts in-flight work', async () => {
  const f = fixture(); let signal, reject;
  const sender = createTouchFeatureTransport(async (_session, _window, s) => {
    signal = s; return new Promise((_resolve, fail) => { reject = fail; });
  }, () => f.recorder.read(), () => 3000);
  sender.setContext('server-1', false); await sender.tick(); assert.equal(signal, undefined);
  sender.setContext('server-1', true); const pending = sender.tick();
  sender.setContext('server-1', false); assert(signal.aborted);
  reject(new Error('aborted')); await pending; assert.equal(sender.status().sent, 0); sender.dispose();
});

test('nearest distance uses one sample per outside press and never invents a proximity threshold', () => {
  const f = fixture(); f.press(1100); f.press(1400); f.press(1700);
  const saved = f.recorder.read();
  const presses = saved.events.filter(e => e.kind === 'pointer_start');
  presses[0].data.nearestCandidates = [{ distance: 4 }, { distance: 4 }];
  presses[1].data.nearestCandidates = [{ distance: 100 }];
  presses[2].data.nearestCandidates = [];
  const extra = buildTouchFeatureWindow(saved, 3000, 1).touch.interaction;
  assert.equal(extra.outside_nearest_distance_mean_px, 52);
  assert.equal(extra.outside_nearest_distance_sample_count, 2);
});

test('busy state spanning the window is integrated and an absent baseline remains unknown', () => {
  const f = fixture();
  const pending = { ...f.ready, status: 'saving' };
  f.record(500, 'order_state_change', { before: f.ready, after: pending });
  f.record(2500, 'order_state_change', { before: pending, after: f.ready });
  assert.equal(buildTouchFeatureWindow(f.recorder.read(), 3000, 1).touch.interaction.order_busy_ms, 1500);
  const saved = f.recorder.read();
  saved.events = saved.events.filter(e => e.kind !== 'order_state_change' || Date.parse(e.occurredAt) > 1000);
  assert.equal(buildTouchFeatureWindow(saved, 3000, 1).touch.interaction.order_busy_ms, null);
});

test('voice processing and automatic shutdown are context, not touch inactivity', () => {
  const f = fixture();
  f.record(1500, 'voice_state_change', {
    before: { enabled: false, microphoneActive: false, phase: 'idle', autoOff: null },
    after: { enabled: true, microphoneActive: false, phase: 'processing', autoOff: null },
  });
  let extra = buildTouchFeatureWindow(f.recorder.read(), 3000, 1).touch.interaction;
  assert.equal(extra.voice_processing, true);
  assert.equal(extra.voice_auto_off, null);
  f.record(3200, 'voice_state_change', {
    before: { enabled: true, microphoneActive: false, phase: 'processing', autoOff: null },
    after: { enabled: false, microphoneActive: false, phase: 'idle', autoOff: 'silence' },
  });
  extra = buildTouchFeatureWindow(f.recorder.read(), 4000, 2).touch.interaction;
  assert.equal(extra.voice_processing, false);
  assert.equal(extra.voice_auto_off, 'silence');
  assert.equal(extra.voice_enabled, false);
});
