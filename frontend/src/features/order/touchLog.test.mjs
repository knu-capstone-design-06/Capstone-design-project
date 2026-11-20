import assert from 'node:assert/strict';
import test from 'node:test';
import { createTouchLog, distanceToRect, logLimit, touchLogKey } from './touchLog.ts';
import { summarizeTouchLog } from './touchLogSummary.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';
import { captureTouchLogObservation } from './touchLogObservation.ts';
import { createTouchFeatureTransport } from './touchFeatureTransport.ts';
import { ApiError } from '../../shared/api/client.ts';

function supportTransport(send, read, receive, now) {
  const transport = createTouchFeatureTransport(send, read, now);
  return {
    ...transport,
    setContext(session, key, enabled, canOffer, includeInteraction = false) {
      transport.setContext(session, enabled, { key, canOffer, includeInteraction, receive });
    },
  };
}

test('같은 전송기가 기본 통계와 선택적 확장 통계를 보내며 미관측 구간은 건너뛴다', async () => {
  const { saved, emit } = pilotLog(true);
  emit(1000, 'screen_enter', { visibility: 'visible' });
  const sent = [];
  let now = 2001;
  const transport = supportTransport(async (session, body) => { sent.push(body); return { session_id: session }; }, () => saved, () => {}, () => now);
  transport.setContext('server', 'menu', true, false);
  await transport.tick();
  assert.deepEqual(sent, []);
  now = 4001;
  await transport.tick();
  assert.deepEqual(sent[0], {
    screen_id: 'menu', window_start: new Date(2000).toISOString(), window_end: new Date(4000).toISOString(),
    touch: { tap_count: 0, miss_tap_count: 0, repeat_tap_count: 0, back_count: 0, dwell_ms: 3000 }, vision: null,
  });
  transport.setContext('server', 'menu', true, false, true);
  now = 6001;
  await transport.tick();
  assert.equal(sent.length, 2);
  assert.equal(sent[1].window_start, sent[0].window_end);
  assert.equal(sent[1].touch.interaction.schema_version, 'touch-interaction-pilot-v1');
  assert.equal(sent[1].touch.interaction.window_sequence, 2);
  transport.dispose();
});

test('전송은 중복 요청을 막고 화면·세션 변경 및 중단 뒤의 늦은 응답을 버린다', async () => {
  const { saved, emit } = pilotLog(true); emit(1000, 'screen_enter', { visibility: 'visible' });
  const calls = [], received = [];
  let now = 4000;
  const transport = supportTransport((session, body, signal) => new Promise(resolve => calls.push({ session, body, signal, resolve })), () => saved, response => received.push(response), () => now);
  transport.setContext('server', 'menu', true, true);
  const first = transport.tick(); await transport.tick();
  assert.equal(calls.length, 1);
  transport.setContext('server', 'review', true, false);
  transport.setContext('server', 'menu', true, true);
  assert.equal(calls[0].signal.aborted, false);
  calls[0].resolve({ session_id: 'server' }); await first;
  assert.equal(received.length, 0);
  now = 6000; const second = transport.tick();
  // 같은 화면으로 돌아와도 다른 방문이면 이전 요청을 재사용하지 않습니다.
  emit(6000, 'screen_enter', { visibility: 'visible', from: 'review' }, 'visit-2');
  calls[1].resolve({ session_id: 'server' }); await second;
  assert.equal(received.length, 0);
  transport.setContext('new-server', 'menu', true, true); await transport.tick(); assert.equal(calls.length, 2);
  transport.setContext('server', 'menu', true, true);
  now = 8000; const third = transport.tick(); transport.dispose();
  assert.equal(calls[2].signal.aborted, true);
  calls[2].resolve({ session_id: 'server' }); await third;
  assert.equal(received.length, 0);
});

test('변경 중에도 전송 구간의 경계가 이어지고 종료를 기다린 누름을 한 번만 센다', async () => {
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 2001;
  const sent = [], received = [];
  const transport = supportTransport(async (session, body) => {
    sent.push(body);
    return { session_id: session };
  }, () => saved, response => received.push(response), () => now);
  transport.setContext('server', 'menu', true, true);
  await transport.tick();
  const inputId = emit(3999, 'pointer_start', { target: null, start: { x: 3, y: 4 }, pointerType: 'mouse', isPrimary: true });
  transport.setContext('server', 'option', true, false);
  now = 4000; await transport.tick(); assert.equal(sent.length, 1);
  emit(4050, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
  now = 4250; await transport.tick();
  assert.equal(sent[1].window_start, sent[0].window_end);
  assert.equal(sent[1].touch.tap_count, 1);
  assert.equal(received.length, 1, '조작 중 수집하지만 그 응답으로는 제안하지 않음');
  transport.setContext('server', 'menu', true, true);
  now = 6250; await transport.tick();
  assert.equal(sent[2].window_start, sent[1].window_end);
  assert.equal(sent[2].touch.tap_count, 0);
  transport.dispose();
});

test('지연된 요청 뒤에도 구간을 이어 보내고 화면 상태 변경 전의 응답은 제안에 사용하지 않는다', async () => {
  const { saved, emit } = pilotLog(true);
  emit(0, 'screen_enter', { visibility: 'visible' });
  const inputId = emit(5000, 'pointer_start', { target: null, start: { x: 3, y: 4 }, pointerType: 'mouse', isPrimary: true });
  emit(5010, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
  let now = 4001;
  const requests = [], received = [];
  const transport = supportTransport((session, body) => new Promise(resolve => requests.push({ body, resolve })),
    () => ({ ...saved, events: saved.events.filter(event => Date.parse(event.occurredAt) <= now) }),
    response => received.push(response), () => now);
  transport.setContext('server', 'menu:coffee', true, true, true);
  const first = transport.tick();
  now = 7200;
  transport.setContext('server', 'menu:dessert', true, true, true);
  await transport.tick();
  assert.equal(requests.length, 1);
  requests[0].resolve({ session_id: 'server' });
  await first;
  const second = transport.tick();
  requests[1].resolve({ session_id: 'server' });
  await second;
  assert.equal(requests[1].body.window_start, requests[0].body.window_end);
  assert.equal(requests[1].body.touch.tap_count, 1);
  assert.equal(requests[1].body.touch.interaction.window_sequence, 2);
  assert.deepEqual(received, []);
  now = 8001;
  const third = transport.tick();
  requests[2].resolve({ session_id: 'server' });
  await third;
  assert.equal(requests[2].body.window_start, requests[1].body.window_end);
  assert.equal(received.length, 1);
  transport.dispose();
});

test('네트워크 실패 뒤에는 새 구간을 보내고 종료된 세션은 다음 세션까지 중단한다', async () => {
  const { saved, emit } = pilotLog(true); emit(1000, 'screen_enter', { visibility: 'visible' });
  let count = 0, now = 4000;
  const received = [];
  const transport = supportTransport(async session => {
    count++;
    if (count === 1) throw new TypeError('offline');
    if (count === 2) throw new ApiError(410, {});
    return { session_id: session };
  }, () => saved, response => received.push(response), () => now);
  transport.setContext('server', 'menu', true, true);
  await transport.tick();
  now = 6000; await transport.tick();
  now = 8000; await transport.tick();
  assert.equal(count, 2);
  saved.serverSessionId = 'next';
  for (const event of saved.events) event.serverSessionId = 'next';
  transport.setContext('next', 'menu', true, true); await transport.tick();
  assert.equal(count, 3); assert.equal(received.length, 1); transport.dispose();
});

for (const pending of [false, true]) test(`같은 세션의 전송 재개는 직전 경계를 유지한다 (${pending ? '요청 처리 중 취소' : '응답 완료'})`, async () => {
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  const inputId = emit(3500, 'pointer_start', { target: null, start: { x: 3, y: 4 }, pointerType: 'mouse', isPrimary: true });
  emit(3510, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
  let now = 4000;
  const sent = [], received = [];
  const transport = supportTransport((session, body, signal) => {
    const request = { body, signal };
    sent.push(request);
    if (sent.length === 1) return new Promise(resolve => { request.resolve = resolve; });
    return Promise.resolve({ session_id: session });
  }, () => saved, response => received.push(response), () => now);
  transport.setContext('server', 'menu', true, true);
  const first = transport.tick();
  if (!pending) { sent[0].resolve({ session_id: 'server' }); await first; }
  transport.setContext('server', 'menu', false, false);
  assert.equal(sent[0].signal.aborted, pending);
  now = 4500; transport.setContext('server', 'menu', true, true);
  await transport.tick();
  assert.equal(sent.length, 1, '2초가 차기 전에는 겹치는 최근 구간을 보내지 않음');
  if (pending) { sent[0].resolve({ session_id: 'server' }); await first; assert.equal(received.length, 0); }
  now = 6000; const second = transport.tick();
  assert.equal(sent[1].body.window_start, sent[0].body.window_end);
  assert.equal(sent.reduce((sum, request) => sum + request.body.touch.tap_count, 0), 1, '3500ms 누름을 한 번만 전송');
  await second;
  transport.dispose();
});

for (const beforeRead of [false, true]) test(`읽기와 같은 밀리초의 누름을 다음 구간에서 한 번 센다 (${beforeRead ? '읽기 직전 기록' : '읽기 직후 기록'})`, async () => {
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 4000;
  const sent = [];
  const transport = supportTransport(async (session, body) => { sent.push(body); return { session_id: session }; }, () => saved, () => {}, () => now);
  const press = () => emit(4000, 'pointer_start', { target: null, start: { x: 3, y: 4 }, pointerType: 'mouse', isPrimary: true });
  let inputId;
  if (beforeRead) inputId = press();
  transport.setContext('server', 'menu', true, true);
  await transport.tick();
  assert.equal(sent.length, 1, '현재 밀리초의 시작 기록 때문에 앞선 완전 관측 구간을 버리지 않음');
  assert.equal(sent[0].window_end, new Date(3999).toISOString());
  if (!beforeRead) inputId = press();
  emit(4010, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
  now = 6000; await transport.tick();
  assert.equal(sent[1].window_start, sent[0].window_end);
  assert.deepEqual(sent.map(body => body.touch.tap_count), [0, 1]);
  now = 8000; await transport.tick();
  assert.deepEqual(sent.map(body => body.touch.tap_count), [0, 1, 0]);
  transport.dispose();
});

test('종료 경계를 지난 새 방문의 응답을 현재 화면 제안으로 사용하지 않고 실제 미래 시각은 미산출로 둔다', async () => {
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 4000;
  const sent = [], received = [];
  const transport = supportTransport(async (session, body) => { sent.push(body); return { session_id: session }; }, () => saved, response => received.push(response), () => now);
  emit(4000, 'screen_enter', { visibility: 'visible', from: 'menu' }, 'review-visit', 'review');
  transport.setContext('server', 'review', true, true); await transport.tick();
  assert.equal(sent[0].screen_id, 'menu', '종료 경계 시점의 화면을 사용');
  assert.equal(received.length, 0, '새 방문에서 이전 화면 구간의 제안을 쓰지 않음');
  now = 6000; await transport.tick();
  assert.equal(sent[1].screen_id, 'review');
  assert.equal(received.length, 1);
  now = 8000; emit(8100, 'scroll', {}); await transport.tick();
  assert.equal(sent.length, 2, '실제 시계 역행·미래 기록을 현재 밀리초 기록처럼 제외하지 않음');
  transport.dispose();
});

test('주문·옵션·음성 관측은 필요한 필드만 복사하고 인식문·서버 오류 상세를 보관하지 않는다', () => {
  const order = { status: 'ready', order: null, message: '서버 오류 상세', cart: {
    version: 2, total_quantity: 3, items: [{ item_id: 'item', product_id: 'coffee', temperature: 'hot', quantity: 3, name: '상품명', unit_price: 3500 }],
  } };
  const selection = { productId: 'coffee', temperature: 'iced', quantity: 2 };
  const voice = { enabled: true, microphoneActive: true, phase: 'listening', autoOff: null, partialText: '개인적인 발화', lastTranscript: '마지막 인식문', lastResult: { reply_text: '서버 응답' } };
  const observed = captureTouchLogObservation(order, selection, voice);
  assert.deepEqual(observed, {
    order: { status: 'ready', completed: false, feedbackVisible: true,
      cart: { version: 2, totalQuantity: 3, items: [{ itemId: 'item', productId: 'coffee', temperature: 'hot', quantity: 3 }] } },
    selection, voice: { enabled: true, microphoneActive: true, phase: 'listening', autoOff: null },
  });
  observed.order.cart.items[0].quantity = 9;
  observed.selection.quantity = 9;
  observed.voice.enabled = false;
  assert.equal(order.cart.items[0].quantity, 3);
  assert.equal(selection.quantity, 2);
  assert.equal(voice.enabled, true);
  assert.equal(captureTouchLogObservation({ ...order, order: {}, cart: null, message: '' }, null, voice).order.completed, true);
  assert.deepEqual(captureTouchLogObservation(order, null, { ...voice, enabled: false, autoOff: 'silence' }).voice,
    { enabled: false, microphoneActive: true, phase: 'listening', autoOff: 'silence' });
});

function pilotLog(withOrder = false) {
  const saved = { version: 1, sessionId: 'current', serverSessionId: 'server', startedAt: 0, events: [] };
  const emit = (ms, kind, data = null, visitId = 'visit-1', screen = 'menu', sessionId = 'current') => {
    const id = `pilot-${saved.events.length}`;
    saved.events.push({ ...context(), id, sessionId, serverSessionId: 'server', occurredAt: new Date(ms).toISOString(), elapsedMs: ms, visitId, screen, kind, data });
    return id;
  };
  if (withOrder) emit(0, 'order_state_change', { before: null, after: { status: 'ready', completed: false } });
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
