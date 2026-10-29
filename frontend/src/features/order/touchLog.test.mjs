import assert from 'node:assert/strict';
import test from 'node:test';
import { createTouchLog, distanceToRect, logLimit, touchLogKey } from './touchLog.ts';
import { summarizeTouchLog } from './touchLogSummary.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';
import { captureTouchLogObservation } from './touchLogObservation.ts';

test('주문·옵션·음성 관측은 필요한 필드만 복사하고 인식문·서버 오류 상세를 보관하지 않는다', () => {
  const order = { status: 'ready', order: null, message: '서버 오류 상세', cart: {
    version: 2, total_quantity: 3, items: [{ item_id: 'item', product_id: 'coffee', temperature: 'hot', quantity: 3, name: '상품명', unit_price: 3500 }],
  } };
  const selection = { productId: 'coffee', temperature: 'iced', quantity: 2 };
  const voice = { enabled: true, microphoneActive: true, phase: 'listening', partialText: '개인적인 발화', lastTranscript: '마지막 인식문', lastResult: { reply_text: '서버 응답' } };
  const observed = captureTouchLogObservation(order, selection, voice);
  assert.deepEqual(observed, {
    order: { status: 'ready', completed: false, feedbackVisible: true,
      cart: { version: 2, totalQuantity: 3, items: [{ itemId: 'item', productId: 'coffee', temperature: 'hot', quantity: 3 }] } },
    selection, voice: { enabled: true, microphoneActive: true, phase: 'listening' },
  });
  observed.order.cart.items[0].quantity = 9;
  observed.selection.quantity = 9;
  observed.voice.enabled = false;
  assert.equal(order.cart.items[0].quantity, 3);
  assert.equal(selection.quantity, 2);
  assert.equal(voice.enabled, true);
  assert.equal(captureTouchLogObservation({ ...order, order: {}, cart: null, message: '' }, null, voice).order.completed, true);
});

function pilotLog() {
  const saved = { version: 1, sessionId: 'current', serverSessionId: 'server', startedAt: 0, events: [] };
  const emit = (ms, kind, data = null, visitId = 'visit-1', screen = 'menu', sessionId = 'current') => {
    const id = `pilot-${saved.events.length}`;
    saved.events.push({ ...context(), id, sessionId, serverSessionId: 'server', occurredAt: new Date(ms).toISOString(), elapsedMs: ms, visitId, screen, kind, data });
    return id;
  };
  return { saved, emit };
}

test('로컬 최근 구간은 관측한 0과 미측정 null을 구별하고 이전 세션 입력을 제외한다', () => {
  const { saved, emit } = pilotLog();
  emit(0, 'pointer_start', { target: null }, 'old', 'menu', 'previous');
  emit(1000, 'screen_enter', { visibility: 'visible' });
  assert.equal(measureTouchPilot(saved, 1500).features.tap_count, null);
  assert.deepEqual(measureTouchPilot(saved, 4000).features, { tap_count: 0, miss_tap_count: 0, repeat_tap_count: 0, back_count: 0, dwell_ms: 3000 });
  emit(4100, 'pointer_start', { target: null });
  emit(4200, 'pointer_start', {});
  const measured = measureTouchPilot(saved, 5000).features;
  assert.equal(measured.tap_count, 2);
  assert.equal(measured.miss_tap_count, null);
});

test('전경 화면 이동은 최근 구간의 뒤로가기를 보존하고 방문 체류는 새로 계산한다', () => {
  const { saved, emit } = pilotLog();
  emit(0, 'screen_enter', { visibility: 'visible' }, 'review', 'review');
  emit(4500, 'screen_leave', { to: 'menu' }, 'review', 'review');
  emit(4500, 'screen_enter', { from: 'review', visibility: 'visible' }, 'menu', 'menu');
  const result = measureTouchPilot(saved, 6000, 2000, { repeatMs: null, repeatPx: null, dwellMode: 'foreground_visit' });
  assert.equal(result.features.back_count, 1);
  assert.equal(result.features.dwell_ms, 1500);
  assert.equal(result.sinceLastInputMs, null);
});

test('동시 입력이 관측된 주 포인터를 단일 반복 누름 후보로 세지 않는다', () => {
  const { saved, emit } = pilotLog();
  emit(0, 'screen_enter', { visibility: 'visible' });
  const data = { start: { x: 20, y: 20 }, target: { id: 'same', kind: 'button', disabled: false }, pointerType: 'touch', isPrimary: true };
  const first = emit(2200, 'pointer_start', data);
  emit(2250, 'pointer_end', { inputId: first, cancelled: false, maxObservedDistance: 0, overlappingInputIds: [] });
  const second = emit(2400, 'pointer_start', data);
  emit(2600, 'pointer_end', { inputId: second, cancelled: false, maxObservedDistance: 0, overlappingInputIds: ['secondary-contact'] });
  assert.equal(measureTouchPilot(saved, 3000).features.repeat_tap_count, 0);
  saved.events.at(-1).data.overlappingInputIds = [];
  assert.equal(measureTouchPilot(saved, 3000).features.repeat_tap_count, 1);
});

test('전경 체류는 백그라운드·페이지 중단을 제외하고 관측이 끊긴 최근 구간은 미산출이다', () => {
  const { saved, emit } = pilotLog();
  const policy = { repeatMs: null, repeatPx: null, dwellMode: 'foreground_visit' };
  emit(0, 'screen_enter', { visibility: 'visible' });
  emit(2000, 'visibility_change', { visibility: 'hidden' });
  emit(4000, 'visibility_change', { visibility: 'visible' });
  const early = measureTouchPilot(saved, 4500, 2000, policy);
  assert.equal(early.features.tap_count, null);
  assert.equal(early.features.dwell_ms, 2500);
  emit(5000, 'pointer_start', { target: null });
  assert.equal(measureTouchPilot(saved, 7000, 2000, policy).features.dwell_ms, 5000);
  assert.equal(measureTouchPilot(saved, 7000, 2000, { ...policy, dwellMode: 'since_last_input' }).features.dwell_ms, 2000);
  emit(7500, 'screen_leave', { reason: 'pagehide' });
  emit(7500, 'session_suspend', { reason: 'pagehide' });
  assert.equal(measureTouchPilot(saved, 9000, 2000, policy).features.dwell_ms, 5500);
  assert.equal(measureTouchPilot(saved, 9000, 2000, policy).features.tap_count, null);
});

test('이전 로그의 전경 정보 누락과 시계 역행을 체류 0으로 채우지 않는다', () => {
  const { saved, emit } = pilotLog();
  const policy = { repeatMs: null, repeatPx: null, dwellMode: 'foreground_visit' };
  emit(0, 'screen_enter');
  assert.equal(measureTouchPilot(saved, 5000, 2000, policy).features.dwell_ms, null);
  emit(6000, 'pointer_start', { target: null });
  assert.equal(measureTouchPilot(saved, 5000).observed, false);
  emit(4000, 'pointer_start', { target: null });
  assert.equal(measureTouchPilot(saved, 7000).features.tap_count, null);
});

test('명시한 파일럿 기준으로 추가 반복 누름만 세고 취소·스크롤·다른 대상·방문은 이어 붙이지 않는다', () => {
  const { saved, emit } = pilotLog();
  const policy = { repeatMs: 800, repeatPx: 24, dwellMode: null };
  emit(0, 'screen_enter', { visibility: 'visible' });
  function press(ms, x, targetId = 'options-increase', cancelled = false) {
    const id = emit(ms, 'pointer_start', { start: { x, y: 10 }, pointerType: 'touch', isPrimary: true,
      target: { id: targetId, kind: 'button', disabled: false } });
    emit(ms + 10, 'pointer_end', { inputId: id, cancelled, maxObservedDistance: 0 });
    return id;
  }
  press(3000, 0); press(3800, 24);
  assert.equal(measureTouchPilot(saved, 4000, 2000, policy).features.repeat_tap_count, 1);
  press(4000, 24, 'options-decrease');
  press(4100, 24, 'options-decrease', true);
  press(4200, 24, 'options-decrease');
  const last = press(4300, 24, 'options-decrease');
  emit(4400, 'scroll', { inputCandidates: [last] });
  assert.equal(measureTouchPilot(saved, 4500, 2000, policy).features.repeat_tap_count, 1);
  assert.equal(measureTouchPilot(saved, 4500, 2000, { ...policy, repeatPx: 16 }).features.repeat_tap_count, 0);
  assert.equal(measureTouchPilot(saved, 4500, 2000, { ...policy, repeatMs: 500 }).features.repeat_tap_count, 0);
});

test('구간 직전 반복 후보의 주 포인터·종료 정보가 없으면 반복이나 0으로 추정하지 않는다', () => {
  for (const missing of ['isPrimary', 'end']) {
    const { saved, emit } = pilotLog();
    emit(0, 'screen_enter', { visibility: 'visible' });
    const input = { start: { x: 10, y: 10 }, pointerType: 'touch', isPrimary: true, target: null };
    const prior = emit(2900, 'pointer_start', missing === 'isPrimary' ? { ...input, isPrimary: undefined } : input);
    if (missing !== 'end') emit(2910, 'pointer_end', { inputId: prior, cancelled: false, maxObservedDistance: 0 });
    const next = emit(3100, 'pointer_start', input);
    emit(3110, 'pointer_end', { inputId: next, cancelled: false, maxObservedDistance: 0 });
    const result = measureTouchPilot(saved, 5000).features;
    assert.equal(result.tap_count, 1);
    assert.equal(result.repeat_tap_count, null, missing);
    // 선행 기록이 반복 시간 범위 밖이면 현재 구간의 관측한 0을 유지합니다.
    assert.equal(measureTouchPilot(saved, 5000, 2000, { repeatMs: 100, repeatPx: 24, dwellMode: null }).features.repeat_tap_count, 0);
  }
});

test('잘못된 이동 거리나 종료 후 중단 기록을 정상 반복 후보로 세지 않는다', () => {
  for (const distance of [-1, NaN, Infinity]) {
    const { saved, emit } = pilotLog();
    emit(0, 'screen_enter', { visibility: 'visible' });
    const input = { start: { x: 10, y: 10 }, pointerType: 'touch', isPrimary: true, target: null };
    const first = emit(3100, 'pointer_start', input);
    emit(3110, 'pointer_end', { inputId: first, cancelled: false, maxObservedDistance: distance });
    const second = emit(3200, 'pointer_start', input);
    emit(3210, 'pointer_end', { inputId: second, cancelled: false, maxObservedDistance: 0 });
    assert.equal(measureTouchPilot(saved, 5000).features.repeat_tap_count, null);
  }
  const { saved, emit } = pilotLog();
  emit(0, 'screen_enter', { visibility: 'visible' });
  const input = { start: { x: 10, y: 10 }, pointerType: 'touch', isPrimary: true, target: null };
  const first = emit(3100, 'pointer_start', input);
  emit(3110, 'pointer_end', { inputId: first, cancelled: false, maxObservedDistance: 0 });
  emit(3120, 'pointer_interrupted', { inputId: first });
  const second = emit(3200, 'pointer_start', input);
  emit(3210, 'pointer_end', { inputId: second, cancelled: false, maxObservedDistance: 0 });
  assert.equal(measureTouchPilot(saved, 5000).features.repeat_tap_count, 0);
});

const context = () => ({ screen: 'menu', visitId: 'visit-1', settings: { largeButton: false } });
function memoryStorage() {
  const values = new Map();
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
}

test('버튼 내부·변·모서리까지 실제 거리만 계산하며 임계값을 사용하지 않는다', () => {
  const rect = { x: 10, y: 20, width: 100, height: 40 };
  assert.equal(distanceToRect({ x: 50, y: 30 }, rect), 0);
  assert.equal(distanceToRect({ x: 110, y: 60 }, rect), 0);
  assert.equal(distanceToRect({ x: 116, y: 30 }, rect), 6);
  assert.equal(distanceToRect({ x: 113, y: 64 }, rect), 5);
});

test('보관 버퍼를 복원하고 새 서버 세션의 ID를 분리하며 이전 로그를 유지한다', () => {
  const storage = memoryStorage();
  let nextId = 0;
  let timestamp = 1000;
  const id = () => `id-${++nextId}`;
  const now = () => timestamp;
  const first = createTouchLog(storage, id, now);
  first.newSession('server-1');
  assert.equal(first.getServerSessionId(), 'server-1');
  const firstSession = first.read().sessionId;
  timestamp = 1100;
  first.record(context(), 'pointer_start', { start: { x: 1, y: 2 } });
  const restored = createTouchLog(storage, id, now);
  assert.equal(restored.resumed, true);
  assert.equal(restored.read().sessionId, firstSession);
  assert.equal(restored.read().events[0].elapsedMs, 100);
  restored.newSession('server-2');
  assert.equal(restored.getServerSessionId(), 'server-2');
  restored.record(context(), 'session_start', { server_session_id: 'server-2' });
  const result = restored.read();
  assert.notEqual(result.sessionId, firstSession);
  assert.equal(result.events[0].sessionId, firstSession);
  assert.equal(result.events[1].sessionId, result.sessionId);
  assert.equal(result.events[0].serverSessionId, 'server-1');
  assert.equal(result.events[1].serverSessionId, 'server-2');
  assert.equal(result.serverSessionId, 'server-2');
  const again = createTouchLog(storage, id, now).read();
  assert.equal(again.serverSessionId, 'server-2');
});

test('서버 ID가 없는 이전 초안 로그는 서버 세션을 추측하지 않고 null로 복원한다', () => {
  const storage = memoryStorage();
  storage.setItem(touchLogKey, JSON.stringify({ version: 1, sessionId: 'old-local', startedAt: 0,
    events: [{ id: 'old-event', sessionId: 'old-local', kind: 'pointer_start' }] }));
  const recorder = createTouchLog(storage);
  assert.equal(recorder.resumed, true);
  assert.equal(recorder.read().serverSessionId, null);
  assert.equal(recorder.getServerSessionId(), null);
  assert.equal(recorder.read().events[0].serverSessionId, null);
});

test('설정과 읽기 결과 변경이 저장된 과거 로그를 바꾸지 않는다', () => {
  const recorder = createTouchLog(memoryStorage());
  const original = context();
  recorder.record(original, 'pointer_start');
  original.settings.largeButton = true;
  const snapshot = recorder.read();
  snapshot.events[0].settings.largeButton = true;
  assert.equal(recorder.read().events[0].settings.largeButton, false);
});

test('저장 불가·손상 데이터에서도 기록을 계속하고 상태로 알린다', () => {
  const broken = { getItem: () => '{broken', setItem: () => { throw new Error('quota'); } };
  const recorder = createTouchLog(broken);
  assert.equal(recorder.resumed, false);
  recorder.record(context(), 'pointer_start');
  assert.equal(recorder.read().events.length, 1);
  assert.match(recorder.getWarning(), /저장 실패/);
  const malformed = memoryStorage();
  malformed.setItem(touchLogKey, JSON.stringify({ version: 1, sessionId: 'x', startedAt: 0, events: [null] }));
  assert.equal(createTouchLog(malformed).resumed, false);
});

test('로컬 버퍼는 최신 기록만 제한된 개수로 유지한다', () => {
  const recorder = createTouchLog(null);
  for (let i = 0; i <= logLimit; i++) recorder.record(context(), 'scroll', { i });
  const events = recorder.read().events;
  assert.equal(events.length, logLimit);
  assert.equal(events[0].data.i, 1);
  assert.equal(events.at(-1).data.i, logLimit);
});

function summaryFixture(items) {
  return {
    version: 1, sessionId: 'current', serverSessionId: 'server-current', startedAt: 0,
    events: items.map((item, index) => ({
      id: `event-${index}`, sessionId: 'current', serverSessionId: 'server-current',
      occurredAt: new Date(index).toISOString(), elapsedMs: index,
      screen: 'menu', visitId: 'visit-1', settings: {}, data: null, ...item,
    })),
  };
}
const press = target => ({ kind: 'pointer_start', data: { target } });

test('원시 요약은 현재 로컬 세션만 계산하고 입력과 반환값을 서로 분리한다', () => {
  const saved = summaryFixture([
    { kind: 'session_start' },
    { ...press(null), sessionId: 'old', serverSessionId: 'server-old' },
    press({ kind: 'button', disabled: false }),
    { kind: 'screen_enter' }, { kind: 'category_change' },
    { kind: 'options_open' }, { kind: 'options_close' }, { kind: 'ui_settings_change' },
  ]);
  const before = structuredClone(saved);
  const result = summarizeTouchLog(saved);
  assert.equal(result.sessionId, 'current');
  assert.equal(result.serverSessionId, 'server-current');
  assert.equal(result.hasSessionStart, true);
  assert.equal(result.counts.events, 7);
  assert.equal(result.counts.presses, 1);
  assert.equal(result.counts.outsideTargetPresses, 0);
  for (const key of ['screenEntries', 'categoryChanges', 'optionsOpened', 'optionsClosed', 'settingsChanges']) assert.equal(result.counts[key], 1);
  result.visits[0].counts.presses = 99;
  assert.equal(result.counts.presses, 1);
  assert.equal(summarizeTouchLog(saved).visits[0].counts.presses, 1);
  assert.deepEqual(saved, before);
});

test('활성·비활성 버튼과 링크·대상 밖 기록을 나누고 비율의 분모는 모든 누름 시작이다', () => {
  const result = summarizeTouchLog(summaryFixture([
    press({ kind: 'button', disabled: false }), press({ kind: 'a', disabled: false }),
    press({ kind: 'button', disabled: true }), press(null),
    { kind: 'pointer_end', data: { cancelled: true } }, { kind: 'scroll' },
  ]));
  assert.equal(result.counts.presses, 4);
  assert.equal(result.counts.activeTargetPresses, 2);
  assert.equal(result.counts.disabledTargetPresses, 1);
  assert.equal(result.counts.outsideTargetPresses, 1);
  assert.equal(result.counts.unknownTargetPresses, 0);
  assert.equal(result.outsidePressRatio, 0.25);
  assert.equal(result.counts.cancellations, 1);
  assert.equal(result.counts.scrolls, 1);
});

test('옛 로그의 대상 정보 누락을 영역 밖으로 계산하거나 0%로 채우지 않는다', () => {
  const result = summarizeTouchLog(summaryFixture([
    press(null), { kind: 'pointer_start', data: { start: { x: 1, y: 2 } } },
    { kind: 'pointer_start', data: null }, press({ kind: 'button' }), press({ kind: 'other', disabled: false }),
  ]));
  assert.equal(result.counts.presses, 5);
  assert.equal(result.counts.outsideTargetPresses, 1);
  assert.equal(result.counts.unknownTargetPresses, 4);
  assert.equal(result.outsidePressRatio, null);
});

test('손 뗌·취소·중단은 원시 기록 수이며 시작 기록이 없어도 성공이나 완료 탭으로 추정하지 않는다', () => {
  const result = summarizeTouchLog(summaryFixture([
    { kind: 'pointer_end', data: { cancelled: false, inputId: 'evicted-start' } },
    { kind: 'pointer_end', data: { cancelled: true } },
    { kind: 'pointer_end', data: {} }, { kind: 'pointer_interrupted' }, { kind: 'scroll' },
  ]));
  assert.equal(result.counts.presses, 0);
  assert.equal(result.counts.releases, 1);
  assert.equal(result.counts.cancellations, 1);
  assert.equal(result.counts.unknownEnds, 1);
  assert.equal(result.counts.interruptions, 1);
  assert.equal(result.counts.scrolls, 1);
  assert.equal(result.outsidePressRatio, null);
  assert.equal(result.hasSessionStart, false);
  assert(!('tap_count' in result.counts));
  assert(!('dwell_ms' in result.counts));
});

test('같은 화면 재방문을 분리하고 없는 화면·방문 정보를 만들어 넣지 않는다', () => {
  const saved = summaryFixture([
    { kind: 'screen_enter' }, press(null),
    { kind: 'screen_enter', visitId: 'visit-2', screen: 'review' },
    { ...press({ kind: 'button', disabled: false }), visitId: 'visit-2', screen: 'review' },
    { kind: 'screen_enter', visitId: 'visit-3' }, { ...press(null), visitId: 'visit-3' },
    { kind: 'scroll', visitId: undefined, screen: undefined },
  ]);
  const result = summarizeTouchLog(saved);
  assert.deepEqual(result.visits.map(visit => [visit.visitId, visit.screen]), [
    ['visit-1', 'menu'], ['visit-2', 'review'], ['visit-3', 'menu'], [null, null],
  ]);
  assert.deepEqual(result.visits.map(visit => visit.counts.presses), [1, 1, 1, 0]);
  assert.equal(result.counts.screenEntries, 3);
  assert.equal(result.visits.reduce((total, visit) => total + visit.counts.events, 0), result.counts.events);
});

test('버퍼 제한으로 시작 기록이 사라지면 보관된 기록만 요약한다', () => {
  let sequence = 0;
  const recorder = createTouchLog(null, () => `id-${++sequence}`, () => 0);
  recorder.newSession('bounded');
  recorder.record(context(), 'session_start');
  recorder.record(context(), 'pointer_start', { target: null });
  for (let index = 0; index < logLimit; index++) recorder.record(context(), 'scroll');
  const result = summarizeTouchLog(recorder.read());
  assert.equal(result.hasSessionStart, false);
  assert.equal(result.counts.events, logLimit);
  assert.equal(result.counts.presses, 0);
  assert.equal(result.counts.scrolls, logLimit);
  assert.equal(result.outsidePressRatio, null);
});
