import assert from 'node:assert/strict';
import test from 'node:test';
import { createTouchLog, logLimit } from './touchLog.ts';
import { buildTouchFeatureWindow, FEATURE_WINDOW_MS, measureSceneSignals } from './interactionFeatures.ts';
import { createTouchFeatureTransport } from './touchFeatureTransport.ts';
import { ApiError } from '../../shared/api/client.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';

function fixture(session = 'server-1', collectFeatures = false) {
  let clock = 0, id = 0;
  const recorder = createTouchLog(null, () => `e-${++id}`, () => clock, collectFeatures);
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

function voiceAt(f, time, phase) {
  f.record(time, 'voice_state_change', { before: {}, after: { enabled: true, microphoneActive: phase === 'listening', phase } });
}

test('scrolls can roll out the raw log while feature uploads retain current session state', async () => {
  const f = fixture('server-1', true);
  f.record(100, 'selection_state_change', { before: null, after: { productId: 'drink' } });
  f.press(500);
  let now = 2001;
  const sent = [];
  const transport = createTouchFeatureTransport(async (session, window) => {
    sent.push(window);
    return { session_id: session };
  }, () => f.recorder.readForFeatures(), () => now);
  transport.setContext('server-1', true);

  await transport.tick();
  for (let i = 1; i <= logLimit + 200; i++) {
    f.record(2000 + i * 10, 'scroll');
    now = 2001 + i * 10;
    await transport.tick();
  }
  const raw = f.recorder.read();
  assert.equal(raw.events.length, logLimit);
  assert(raw.events.every(event => event.kind === 'scroll'));
  assert.equal(sent.length, 13);
  assert.deepEqual(sent.slice(1).map(w => w.touch.interaction.scroll_event_count), Array(12).fill(100));
  const latest = sent.at(-1);
  assert.equal(latest.screen_id, 'menu');
  assert.equal(latest.touch.interaction.visit_id, 'visit-1');
  assert.equal(latest.touch.interaction.options_open, true);
  assert.equal(latest.touch.interaction.order_busy, false);
  assert.equal(latest.touch.interaction.screen_revisit_count, 0);
  assert.equal(latest.touch.interaction.since_last_input_ms, 13500);
  assert.equal(latest.touch.dwell_ms, 14000);
  transport.dispose();
});

test('a window with lost scroll evidence is skipped and a later full window can be sent', () => {
  const f = fixture('server-1', true);
  for (let i = 0; i < logLimit + 1; i++) f.record(2500, 'scroll');
  assert.equal(buildTouchFeatureWindow(f.recorder.readForFeatures(), 4000, 1), null);
  const window = buildTouchFeatureWindow(f.recorder.readForFeatures(), 5500, 1);
  assert.equal(window.touch.interaction.scroll_event_count, 0);
  f.recorder.newSession('server-2');
  const next = f.recorder.readForFeatures();
  assert.deepEqual(next.events, []);
  assert.equal(next.discardedThrough, undefined);
});

test('processing → speaking → listening preserves legacy metrics and excludes both waits', () => {
  const f = fixture(); f.press(1000);
  voiceAt(f, 2200, 'processing'); voiceAt(f, 2600, 'speaking');
  let extra = buildTouchFeatureWindow(f.recorder.read(), 3000, 1).touch.interaction;
  assert.equal(extra.voice_processing, false);
  assert.equal(extra.voice_speaking, true); assert.equal(extra.voice_busy, true);
  assert.equal(extra.voice_phase, 'speaking'); assert.equal(extra.voice_busy_ms, 800);
  assert.equal(extra.since_last_input_ms, 2000);
  assert.equal(extra.since_last_input_excluding_system_busy_ms, 1200);
  voiceAt(f, 4500, 'listening');
  const result = buildTouchFeatureWindow(f.recorder.read(), 5000, 2);
  extra = result.touch.interaction;
  assert.equal(extra.voice_busy, false); assert.equal(extra.voice_busy_ms, 500);
  assert.equal(extra.since_last_input_excluding_system_busy_ms, 1700);
  // 파일럿 블록 둘(interaction, scene_signals)을 뺀 나머지가 기존 다섯 수입니다.
  const { interaction, scene_signals, ...legacy } = result.touch;
  assert.deepEqual(legacy, measureTouchPilot(f.recorder.read(), 5000, FEATURE_WINDOW_MS).features);
  assert.equal(legacy.dwell_ms, 5000);
});

test('overlapping order and voice waits are subtracted once, including history before window', () => {
  const f = fixture(); f.press(500);
  voiceAt(f, 1000, 'processing');
  f.record(1500, 'order_state_change', { before: f.ready, after: { ...f.ready, status: 'saving' } });
  voiceAt(f, 2000, 'speaking'); voiceAt(f, 4000, 'idle');
  f.record(4500, 'order_state_change', { before: {}, after: f.ready });
  const extra = buildTouchFeatureWindow(f.recorder.read(), 5000, 1).touch.interaction;
  assert.equal(extra.voice_busy_ms, 0);
  assert.equal(extra.order_busy_ms, 500);
  assert.equal(extra.since_last_input_ms, 4500);
  assert.equal(extra.since_last_input_excluding_system_busy_ms, 1000);
});

test('new touch during speaking resets only the input baseline', () => {
  const f = fixture(); voiceAt(f, 500, 'speaking'); f.press(3000);
  voiceAt(f, 3500, 'idle');
  const extra = buildTouchFeatureWindow(f.recorder.read(), 4000, 1).touch.interaction;
  assert.equal(extra.voice_busy_ms, 500);
  assert.equal(extra.since_last_input_ms, 1000);
  assert.equal(extra.since_last_input_excluding_system_busy_ms, 500);
});

test('missing or unknown voice history is null rather than an invented zero', () => {
  const f = fixture(); f.press(500); voiceAt(f, 2500, 'idle');
  const saved = f.recorder.read();
  saved.events = saved.events.filter(e => e.kind !== 'voice_state_change' || Date.parse(e.occurredAt) > 1000);
  let extra = buildTouchFeatureWindow(saved, 3000, 1).touch.interaction;
  assert.equal(extra.voice_busy_ms, null);
  assert.equal(extra.since_last_input_excluding_system_busy_ms, null);
  voiceAt(f, 2600, 'future-phase');
  extra = buildTouchFeatureWindow(f.recorder.read(), 3000, 1).touch.interaction;
  assert.equal(extra.voice_phase, null); assert.equal(extra.voice_busy, null);
  assert.equal(extra.voice_busy_ms, null);
});

test('foreground gaps, visit and session boundaries do not create a waiting estimate', () => {
  const f = fixture(); f.press(500); voiceAt(f, 700, 'speaking');
  f.record(1000, 'visibility_change', { visibility: 'hidden' });
  f.record(2000, 'visibility_change', { visibility: 'visible' });
  voiceAt(f, 2200, 'idle');
  let extra = buildTouchFeatureWindow(f.recorder.read(), 5000, 1).touch.interaction;
  assert.equal(extra.since_last_input_ms, 4500);
  assert.equal(extra.since_last_input_excluding_system_busy_ms, null);
  f.context.visitId = 'visit-2';
  f.record(5100, 'screen_enter', { from: 'menu', visibility: 'visible' });
  extra = buildTouchFeatureWindow(f.recorder.read(), 7200, 2).touch.interaction;
  assert.equal(extra.since_last_input_excluding_system_busy_ms, null);
  const next = fixture('server-2');
  assert.equal(buildTouchFeatureWindow(next.recorder.read(), 3000, 1).touch.interaction.voice_busy_ms, 0);
});

test('window boundaries clip waits and speaking cancellation/failure stop the timer', () => {
  for (const end of ['idle', 'listening']) {
    const f = fixture(); f.press(500);
    voiceAt(f, 1000, 'speaking'); voiceAt(f, 3000, end);
    let extra = buildTouchFeatureWindow(f.recorder.read(), 3000, 1).touch.interaction;
    assert.equal(extra.voice_busy_ms, 1000); assert.equal(extra.voice_busy, false);
    extra = buildTouchFeatureWindow(f.recorder.read(), 5000, 2).touch.interaction;
    assert.equal(extra.voice_busy_ms, 0);
    assert.equal(extra.since_last_input_excluding_system_busy_ms, 2500);
  }
});

test('same feature window carries five pilot metrics and contextual interaction observations', () => {
  const f = fixture();
  f.press(2050); f.press(2100, { id: 'increase', kind: 'button', disabled: false });
  f.record(2150, 'category_change', { from: '전체', to: '커피' });
  f.record(2200, 'options_open', { productId: 'americano' });
  f.record(2200, 'selection_state_change', { before: null, after: { productId: 'americano' } });
  f.record(2225, 'selection_state_change', { before: { quantity: 1 }, after: { quantity: 2 } });
  const pending = { ...f.ready, status: 'saving' };
  f.record(2250, 'order_state_change', { before: f.ready, after: pending });
  f.record(2600, 'order_state_change', { before: pending, after: { ...f.ready, cart: { version: 1 } } });
  f.record(2650, 'scroll'); f.record(2700, 'scroll');
  f.record(2750, 'ui_settings_change', { before: {}, after: { largeText: true } });
  const result = buildTouchFeatureWindow(f.recorder.read(), 3000, 2);
  assert.equal(result.window_start, new Date(2000).toISOString());
  assert.equal(result.touch.tap_count, 2); assert.equal(result.touch.miss_tap_count, 1);
  assert.equal(result.touch.dwell_ms, 3000);
  const extra = result.touch.interaction;
  assert.equal(extra.outside_tap_ratio, 0.5); assert.equal(extra.order_busy_ms, 350);
  assert.equal(extra.cart_change_count, 1); assert.equal(extra.options_open_count, 1);
  assert.equal(extra.category_change_count, 1); assert.equal(extra.selection_change_count, 2);
  assert.equal(extra.scroll_event_count, 2); assert.equal(extra.since_last_input_ms, 900);
  assert.equal(extra.ui_settings.large_text, true); assert.equal(extra.options_open, true);
  assert.equal(extra.window_sequence, 2);
  assert(!JSON.stringify(result).includes('americano'), 'raw cart/menu selection details are not uploaded');
  assert(!JSON.stringify(result).includes('"x":'), 'raw pointer coordinates are not uploaded');
});

test('ui settings use the change after-value without waiting for a new input event', () => {
  const f = fixture();
  f.record(2200, 'ui_settings_change', {
    before: { largeText: true },
    after: { largeText: true, largeButton: true, highContrast: true },
  });
  const saved = f.recorder.read();
  assert.equal(saved.events.at(-1).settings.largeButton, undefined);
  for (const end of [3000, 5000]) {
    const extra = buildTouchFeatureWindow(saved, end, 1).touch.interaction;
    assert.equal(extra.ui_settings.large_button, true);
    assert.equal(extra.ui_settings.high_contrast, true);
    assert.equal(extra.ui_settings_change_count, end === 3000 ? 1 : 0);
  }
});

test('no input is distinct from unobserved windows and unobserved historical context', () => {
  const f = fixture();
  const saved = f.recorder.read();
  const result = buildTouchFeatureWindow(saved, 3000, 1);
  assert.equal(result.touch.tap_count, 0); assert.equal(result.touch.interaction.outside_tap_ratio, null);
  assert.equal(result.touch.interaction.since_last_input_ms, null);
  assert.equal(buildTouchFeatureWindow(saved, 999, 1), null, 'startup window is not fully observed');
  assert.equal(buildTouchFeatureWindow({ ...saved, serverSessionId: null }, 3000, 1), null);
  saved.events = saved.events.filter(e => e.kind !== 'session_start');
  assert.equal(buildTouchFeatureWindow(saved, 3000, 1).touch.interaction.screen_revisit_count, null);
  f.record(2000, 'visibility_change', { visibility: 'hidden' });
  assert.equal(buildTouchFeatureWindow(f.recorder.read(), 3000, 1), null);
});

test('screen revisits and cancellations are observed without diagnosing confusion or failure', () => {
  const f = fixture();
  f.press(2100, null, true);
  f.record(2300, 'screen_leave', { to: 'review' });
  f.context.screen = 'review'; f.context.visitId = 'visit-2';
  f.record(2300, 'screen_enter', { from: 'menu', visibility: 'visible' });
  f.record(2600, 'screen_leave', { to: 'menu' });
  f.context.screen = 'menu'; f.context.visitId = 'visit-3';
  f.record(2600, 'screen_enter', { from: 'review', visibility: 'visible' });
  const result = buildTouchFeatureWindow(f.recorder.read(), 3000, 1);
  assert.equal(result.touch.back_count, 1); assert.equal(result.touch.dwell_ms, 400);
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

test('a pointer that ends in an older visit cannot replace the screen and visit at window end', () => {
  const f = fixture();
  const inputId = f.record(2150, 'pointer_start', { start: { x: 0, y: 0 }, target: null, pointerType: 'touch', isPrimary: true });
  f.record(2200, 'screen_leave', { to: 'review' });
  f.context.screen = 'review'; f.context.visitId = 'visit-2';
  f.record(2200, 'screen_enter', { from: 'menu', visibility: 'visible' });
  f.context.screen = 'menu'; f.context.visitId = 'visit-1';
  f.record(2600, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
  const result = buildTouchFeatureWindow(f.recorder.read(), 3000, 1);
  assert.equal(result.screen_id, 'review');
  assert.equal(result.touch.interaction.visit_id, 'visit-2');
  assert.equal(result.touch.interaction.since_last_input_ms, null);
  assert.equal(result.touch.tap_count, 1);
});

test('2.6-second press remains in its original window and late ticks neither miss nor duplicate presses', async () => {
  const f = fixture();
  let now = 3001;
  const sent = [];
  const sender = createTouchFeatureTransport(async (session, body) => { sent.push(body); return { session_id: session }; },
    () => f.recorder.read(), () => now);
  sender.setContext('server-1', true);
  await sender.tick();
  f.press(3250);
  const inputId = f.record(3500, 'pointer_start', { start: { x: 0, y: 0 }, target: null, pointerType: 'touch', isPrimary: true });
  for (now = 4250; now <= 6000; now += 250) await sender.tick();
  assert.equal(sent.length, 1, 'do not report a newer zero while the held input is still unresolved');
  f.press(5500);
  f.record(6100, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
  now = 6250; await sender.tick();
  now = 6500; await sender.tick();
  now = 6750; await sender.tick();
  now = 7300; await sender.tick();
  assert.deepEqual(sent.map(w => [Date.parse(w.window_start), Date.parse(w.window_end), w.touch.tap_count]), [
    [2000, 3000, 0], [3000, 4000, 2], [4000, 5000, 0], [5000, 6000, 1], [6000, 7000, 0],
  ]);
  assert.deepEqual(sent.map(w => w.touch.interaction.window_sequence), [1, 2, 3, 4, 5]);
  sender.dispose();
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
  error = null; now = 4000; await sender.tick(); assert.equal(sender.status().sent, 1);
  assert.notEqual(calls[0].window_end, calls[1].window_end);
  error = new ApiError(410, {}); now = 5000; await sender.tick();
  now = 6000; await sender.tick(); assert.equal(attempts, 3);
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
  const f = fixture(); f.press(2100); f.press(2400); f.press(2700);
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
  assert.equal(buildTouchFeatureWindow(f.recorder.read(), 3000, 1).touch.interaction.order_busy_ms, 500);
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


test('selection count is unknown after its session baseline is truncated', () => {
  const f = fixture();
  f.record(2400, 'selection_state_change', { before: null, after: { productId: 'americano' } });
  const saved = f.recorder.read();
  assert.equal(buildTouchFeatureWindow(saved, 3000, 1).touch.interaction.selection_change_count, 1);
  saved.events = saved.events.filter(e => e.kind !== 'session_start' &&
    !(e.kind === 'selection_state_change' && e.data.after === null));
  assert.equal(buildTouchFeatureWindow(saved, 3000, 1).touch.interaction.selection_change_count, null);
});

// touch.scene_signals: 4-1 빗나간 뒤 바로 고침, 2-1 확대 시도(글자 두 번 누르기). 시각은 ms, 좌표는 CSS px입니다.
const button = id => ({ id, kind: 'button', disabled: false, rect: { x: 0, y: 0, width: 100, height: 100 } });
function tap(f, time, { target = null, x = 10, y = 20, candidates = null } = {}) {
  const value = { start: { x, y }, target, pointerType: 'touch', isPrimary: true };
  if (candidates) value.nearestCandidates = candidates.map(id => ({ ...button(id), visibleRect: button(id).rect, distance: 12 }));
  const inputId = f.record(time, 'pointer_start', value);
  f.record(time + 10, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0, overlappingInputIds: [] });
}
const signals = (f, end, saved = f.recorder.read()) => buildTouchFeatureWindow(saved, end, 1, 20000).touch.scene_signals;

test('빗나간 누름을 다음 누름이 가장 가까운 후보로 고치면 고친 누름의 구간에서 하나로 세고, 시간 한계는 없다', () => {
  const f = fixture();
  tap(f, 3500, { candidates: ['product:americano', 'product:latte'] });
  tap(f, 4500, { target: button('product:americano'), x: 60 });
  assert.deepEqual(signals(f, 4000), { schema_version: 'touch-scene-signals-pilot-v1', near_miss_fix_count: 0, zoom_attempt_count: 0, can_offer: null }, '빗나간 구간');
  assert.equal(signals(f, 5000).near_miss_fix_count, 1, '고친 누름의 구간');
  // 시간 한계 없음: 오래 뒤의 다음 누름도 고침입니다.
  const g = fixture();
  tap(g, 1000, { candidates: ['product:latte'] });
  tap(g, 9500, { target: button('product:latte') });
  assert.equal(signals(g, 10000).near_miss_fix_count, 1);
});

test('고침은 바로 다음 누름만 보고, 후보 밖의 버튼이나 후보가 없는 빗나감은 세지 않는다', () => {
  const f = fixture();
  tap(f, 3100, { candidates: ['product:americano'] });
  tap(f, 3300, { target: button('category:coffee'), x: 300 }); // 다음 누름이 후보 밖
  tap(f, 3500, { target: button('product:americano') }); // 그다음 누름은 앞 누름(버튼에 닿음)을 고친 것이 아님
  tap(f, 3700); // 후보가 없는 빗나감
  tap(f, 3900, { target: button('product:americano'), x: 400 });
  assert.equal(signals(f, 4000).near_miss_fix_count, 0);
});

test('구간 안 누름에 대상 정보가 없거나 앞 누름이 빠진 기록에 있었을 수 있으면 고친 수는 null이다', () => {
  const at = time => new Date(time).toISOString();
  const press = (time, value) => ({ id: `p${time}`, sessionId: 's', serverSessionId: 'server-1', screen: 'menu', visitId: 'v', settings: {},
    occurredAt: at(time), elapsedMs: time, kind: 'pointer_start', data: value });
  const miss = press(1500, { start: { x: 10, y: 20 }, target: null, nearestCandidates: [button('cart-add')] });
  // target 필드가 없는 누름: 두 수 모두 null
  assert.deepEqual(measureSceneSignals([miss, press(3000, { start: { x: 10, y: 20 } })], 2000, false),
    { schema_version: 'touch-scene-signals-pilot-v1', near_miss_fix_count: null, zoom_attempt_count: null, can_offer: null });
  // 구간 밖의 앞 누름이 target 필드 없이 남은 경우는 빗나감이 아니라서 고침도 아닙니다(0).
  assert.equal(measureSceneSignals([press(1500, { start: { x: 10, y: 20 } }), press(3000, { start: { x: 10, y: 20 }, target: button('cart-add') })], 2000, false).near_miss_fix_count, 0);
  assert.equal(measureSceneSignals([miss, press(3000, { start: { x: 10, y: 20 }, target: button('cart-add') })], 2000, false).near_miss_fix_count, 1);
  // 보관 기록의 앞부분이 빠졌고 구간 안 누름의 앞 누름이 기록에 없으면 셀 수 없습니다(확대 시도는 두 번 클릭 간격 안의 기록이 늘 남음).
  const f = fixture('server-1', true);
  tap(f, 3500, { target: button('cart-add') });
  assert.equal(signals(f, 4000, { ...f.recorder.readForFeatures(), discardedThrough: 1 }).near_miss_fix_count, null);
  assert.equal(signals(f, 4000, { ...f.recorder.readForFeatures(), discardedThrough: 1 }).zoom_attempt_count, 0);
  assert.equal(signals(f, 4000, f.recorder.readForFeatures()).near_miss_fix_count, 0);
});

test('확대 시도는 버튼에 닿지 않은 연달은 두 누름이 두 번 클릭 간격·같은 자리 거리 안일 때이며, 버튼을 두 번 누른 것은 아니다', () => {
  // 화면의 기존 값만 씁니다: doubleClickMs 500ms(utils/timing.ts), touchPilotPolicy.repeatPx 24px(touchLogFeatures.ts)
  const count = (presses, end = 4000) => {
    const f = fixture();
    for (const [time, options] of presses) tap(f, time, options);
    return signals(f, end).zoom_attempt_count;
  };
  assert.equal(count([[3100, {}], [3400, { x: 20 }]]), 1, '제목·빈 곳의 글자를 두 번 누름');
  assert.equal(count([[3100, {}], [3600, { x: 34 }]]), 1, '간격 500ms, 거리 24px까지');
  assert.equal(count([[3100, {}], [3601, {}]]), 0, '두 번 클릭 간격 밖');
  assert.equal(count([[3100, {}], [3400, { x: 35 }]]), 0, '같은 자리 거리 밖');
  assert.equal(count([[3100, { target: button('product:americano') }], [3400, { target: button('product:americano') }]]), 0, '버튼을 두 번 누름');
  assert.equal(count([[3100, { target: button('product:americano') }], [3400, {}]]), 0, '한쪽만 버튼 밖');
  assert.equal(count([[3100, {}], [3400, {}], [3700, {}]]), 2, '세 번 누르면 연달은 두 쌍');
  assert.equal(count([[3800, {}], [4100, {}]]), 0, '둘째 누름이 다음 구간');
  assert.equal(count([[3800, {}], [4100, {}]], 5000), 1, '둘째 누름의 구간에서 셈');
});

test('scene_signals.can_offer는 전송기가 그 창을 만든 때 화면의 묻기 조건(askGate)이고, 조건을 받지 않았으면 null이다', async () => {
  const f = fixture();
  const sent = [];
  let now = 4001;
  const transport = createTouchFeatureTransport(async (session, body) => { sent.push(body); return { session_id: session }; },
    () => f.recorder.read(), () => now);
  for (const [at, gate] of [[4001, { askGate: true }], [5001, { askGate: false }], [6001, {}]]) {
    tap(f, at - 500); // 구간마다 누름 하나
    now = at;
    transport.setContext('server-1', true, { key: 'menu', canOffer: false, includeInteraction: true, receive: () => {}, ...gate });
    await transport.tick();
  }
  assert.deepEqual(sent.map(body => body.touch.scene_signals.can_offer), [true, false, null]);
  transport.dispose();
});

test('scene_signals는 파일럿 설정에서만 /features 본문과 AI 엔진 사본에 실린다', async () => {
  const f = fixture();
  tap(f, 3500); tap(f, 3700, { x: 15 });
  for (const includeInteraction of [false, true]) {
    const sent = [], engine = [];
    const transport = createTouchFeatureTransport(async (session, body) => { sent.push(body); return { session_id: session }; },
      () => f.recorder.read(), () => 4001, (session, body) => engine.push(body));
    transport.setContext('server-1', true, { key: 'menu', canOffer: false, includeInteraction, receive: () => {} });
    await transport.tick();
    assert.equal(sent.length, 1);
    assert.equal(engine[0], sent[0], 'AI 엔진에는 같은 본문');
    if (includeInteraction) assert.deepEqual(sent[0].touch.scene_signals, { schema_version: 'touch-scene-signals-pilot-v1', near_miss_fix_count: 0, zoom_attempt_count: 1, can_offer: null });
    else assert.deepEqual(Object.keys(sent[0].touch).sort(), ['back_count', 'dwell_ms', 'miss_tap_count', 'repeat_tap_count', 'tap_count']);
    transport.dispose();
  }
});
