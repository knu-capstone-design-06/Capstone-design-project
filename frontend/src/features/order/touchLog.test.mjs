import assert from 'node:assert/strict';
import test from 'node:test';
import { createTouchLog, distanceToRect, logLimit, touchLogKey } from './touchLog.ts';
import { summarizeTouchLog } from './touchLogSummary.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';
import { captureTouchLogObservation } from './touchLogObservation.ts';
import { createTouchFeatureTransport, FEATURE_TICK_MS } from './touchFeatureTransport.ts';
import { createEngineTouchSender } from './engineTouchSender.ts';
import { answersStoppedStates, cardAfterAnswer, cardHoldsRestart, createDecisionReader, offeredCard, readOfferedSupport, restartForDecision } from './backendSupport.ts';
import { initialSettings } from './model.ts';
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
  let now = 1501;
  const transport = supportTransport(async (session, body) => { sent.push(body); return { session_id: session }; }, () => saved, () => {}, () => now);
  transport.setContext('server', 'menu', true, false);
  await transport.tick();
  assert.deepEqual(sent, []);
  now = 4001;
  await transport.tick();
  assert.deepEqual(sent[0], {
    screen_id: 'menu', window_start: new Date(3000).toISOString(), window_end: new Date(4000).toISOString(),
    touch: { tap_count: 0, miss_tap_count: 0, repeat_tap_count: 0, back_count: 0, dwell_ms: 3000 }, vision: null,
  });
  transport.setContext('server', 'menu', true, false, true);
  now = 5001;
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
  now = 5000; const second = transport.tick();
  // 같은 화면으로 돌아와도 다른 방문이면 이전 요청을 재사용하지 않습니다.
  emit(5000, 'screen_enter', { visibility: 'visible', from: 'review' }, 'visit-2');
  calls[1].resolve({ session_id: 'server' }); await second;
  assert.equal(received.length, 0);
  transport.setContext('new-server', 'menu', true, true); await transport.tick(); assert.equal(calls.length, 2);
  transport.setContext('server', 'menu', true, true);
  now = 6000; const third = transport.tick(); transport.dispose();
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
  const inputId = emit(2999, 'pointer_start', { target: null, start: { x: 3, y: 4 }, pointerType: 'mouse', isPrimary: true });
  transport.setContext('server', 'option', true, false);
  now = 3000; await transport.tick(); assert.equal(sent.length, 1);
  emit(3050, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
  now = 3250; await transport.tick();
  assert.equal(sent[1].window_start, sent[0].window_end);
  assert.equal(sent[1].touch.tap_count, 1);
  assert.equal(received.length, 1, '조작 중 수집하지만 그 응답으로는 제안하지 않음');
  transport.setContext('server', 'menu', true, true);
  now = 4250; await transport.tick();
  assert.equal(sent[2].window_start, sent[1].window_end);
  assert.equal(sent[2].touch.tap_count, 0);
  transport.dispose();
});

test('지연된 요청 뒤에도 구간을 이어 보내고 화면 상태 변경 전의 응답은 제안에 사용하지 않는다', async () => {
  const { saved, emit } = pilotLog(true);
  emit(0, 'screen_enter', { visibility: 'visible' });
  const inputId = emit(4500, 'pointer_start', { target: null, start: { x: 3, y: 4 }, pointerType: 'mouse', isPrimary: true });
  emit(4510, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
  let now = 4001;
  const requests = [], received = [];
  const transport = supportTransport((session, body) => new Promise(resolve => requests.push({ body, resolve })),
    () => ({ ...saved, events: saved.events.filter(event => Date.parse(event.occurredAt) <= now) }),
    response => received.push(response), () => now);
  transport.setContext('server', 'menu:coffee', true, true, true);
  const first = transport.tick();
  now = 5200;
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
  now = 6001;
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
  now = 5000; await transport.tick();
  now = 6000; await transport.tick();
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
  assert.equal(sent.length, 1, '1초가 차기 전에는 겹치는 최근 구간을 보내지 않음');
  if (pending) { sent[0].resolve({ session_id: 'server' }); await first; assert.equal(received.length, 0); }
  now = 5000; const second = transport.tick();
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
  now = 5000; await transport.tick();
  assert.equal(sent[1].window_start, sent[0].window_end);
  assert.deepEqual(sent.map(body => body.touch.tap_count), [0, 1]);
  now = 6000; await transport.tick();
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
  now = 5000; await transport.tick();
  assert.equal(sent[1].screen_id, 'review');
  assert.equal(received.length, 1);
  now = 6000; emit(6100, 'scroll', {}); await transport.tick();
  assert.equal(sent.length, 2, '실제 시계 역행·미래 기록을 현재 밀리초 기록처럼 제외하지 않음');
  transport.dispose();
});

test('AI 엔진 주소가 없으면 엔진 전송기를 만들지 않고, 주소가 있으면 같은 창과 세션 ID를 /touch-windows로 보낸다', async () => {
  const calls = [];
  const spy = (url, init) => { calls.push({ url, init }); return Promise.resolve(new Response('{}', { status: 202 })); };
  for (const unset of [undefined, '', '   ']) assert.equal(createEngineTouchSender(unset, spy), undefined);
  assert.equal(calls.length, 0);
  const send = createEngineTouchSender('http://127.0.0.1:9000/', spy);
  const window = { screen_id: 'menu', window_start: new Date(0).toISOString(), window_end: new Date(2000).toISOString(),
    touch: { tap_count: 1, miss_tap_count: 0, repeat_tap_count: 0, back_count: 0, dwell_ms: 2000 }, vision: null };
  const done = send('server', window);
  assert(done instanceof Promise, '끝난 때를 Promise로 알림');
  assert.equal(await done, undefined, '엔진의 답을 돌려주지 않음');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'http://127.0.0.1:9000/touch-windows');
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(calls[0].init.body), { ...window, session_id: 'server' });
  assert.equal(calls[0].init.signal instanceof AbortSignal, true);
});

test('엔진 전송기의 예외·실패·응답 없음은 호출한 쪽에 오류를 넘기지 않는다', async () => {
  const window = { screen_id: 'menu', window_start: new Date(0).toISOString(), window_end: new Date(2000).toISOString(),
    touch: { tap_count: 0, miss_tap_count: 0, repeat_tap_count: 0, back_count: 0, dwell_ms: 2000 }, vision: null };
  for (const fetcher of [() => { throw new TypeError('sync'); }, () => Promise.reject(new TypeError('offline')), () => new Promise(() => {}), () => undefined]) {
    assert.doesNotThrow(() => createEngineTouchSender('http://127.0.0.1:9000', fetcher)('server', window));
  }
  // 응답 없음 말고는 Promise가 거부 없이 끝납니다. 제한 시간에 끊긴 요청은 fetch가 TimeoutError로 거부한 경우입니다.
  for (const fetcher of [() => { throw new TypeError('sync'); }, () => Promise.reject(new TypeError('offline')), () => undefined,
    () => Promise.reject(new DOMException('signal timed out', 'TimeoutError'))]) {
    assert.equal(await createEngineTouchSender('http://127.0.0.1:9000', fetcher)('server', window), undefined);
  }
  await new Promise(resolve => setTimeout(resolve, 0));
});

test('엔진 전송기의 Promise는 엔진이 답하면 상태와 관계없이 본문을 끝까지 읽은 뒤 끝나고, 본문 읽기가 실패해도 거부하지 않는다', async () => {
  const window = { screen_id: 'menu', window_start: new Date(0).toISOString(), window_end: new Date(1000).toISOString(),
    touch: { tap_count: 0, miss_tap_count: 0, repeat_tap_count: 0, back_count: 0, dwell_ms: 1000 }, vision: null };
  for (const status of [202, 400, 503]) {
    const answer = new Response('{"status":"refused"}', { status });
    assert.equal(await createEngineTouchSender('http://127.0.0.1:9000', () => Promise.resolve(answer))('server', window), undefined);
    assert.equal(answer.bodyUsed, true, `${status}: 본문을 읽은 뒤에 끝남`);
  }
  const broken = new Response(new ReadableStream({ start(controller) { controller.error(new TypeError('connection reset')); } }), { status: 202 });
  assert.equal(await createEngineTouchSender('http://127.0.0.1:9000', () => Promise.resolve(broken))('server', window), undefined);
});

test('엔진 전송기는 엔진의 답을 쓰지 않아도 본문을 끝까지 읽어 요청을 끝내고, 본문을 취소하지 않는다', async () => {
  const window = { screen_id: 'menu', window_start: new Date(0).toISOString(), window_end: new Date(2000).toISOString(),
    touch: { tap_count: 0, miss_tap_count: 0, repeat_tap_count: 0, back_count: 0, dwell_ms: 2000 }, vision: null };
  let cancelled = false;
  const answer = new Response(new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('{"status":"accepted"}')); controller.close(); },
    cancel() { cancelled = true; },
  }), { status: 202 });
  createEngineTouchSender('http://127.0.0.1:9000', () => Promise.resolve(answer))('server', window);
  // 본문은 이미 다 들어와 있어 읽기는 마이크로태스크 안에서 끝나므로, 타이머 한 번이면 충분합니다.
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(answer.bodyUsed, true, '답의 본문을 읽음');
  assert.equal(cancelled, false, '답의 본문을 취소하지 않음');
});

test('/features 창을 엔진에도 같은 본문과 세션 ID로 보내고, 엔진 실패·응답 없음은 /features의 본문과 응답 처리를 바꾸지 않는다', async () => {
  async function run(notifyEngine) {
    const { saved, emit } = pilotLog(true);
    emit(1000, 'screen_enter', { visibility: 'visible' });
    const inputId = emit(4500, 'pointer_start', { target: null, start: { x: 3, y: 4 }, pointerType: 'mouse', isPrimary: true });
    emit(4510, 'pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
    const sent = [], received = [], states = [];
    let now = 4001;
    const transport = createTouchFeatureTransport(async (session, body) => { sent.push({ session, body }); return { session_id: session }; },
      () => ({ ...saved, events: saved.events.filter(event => Date.parse(event.occurredAt) <= now) }), () => now, notifyEngine);
    transport.setContext('server', true, { key: 'menu', canOffer: true, includeInteraction: false, receive: response => received.push(response) });
    for (const at of [4001, 5001, 6001]) { now = at; await transport.tick(); states.push(transport.status()); }
    transport.dispose();
    return { sent, received, states };
  }
  const plain = await run(undefined);
  assert.deepEqual(plain.sent.map(({ body }) => body.touch.tap_count), [0, 1, 0]);
  assert.equal(plain.received.length, 3);

  const engine = [];
  const recorded = await run((session, body) => engine.push({ session, body }));
  assert.deepEqual(recorded, plain);
  assert.equal(engine.length, 3);
  for (const [index, { session, body }] of engine.entries()) {
    assert.equal(session, 'server');
    assert.equal(body, recorded.sent[index].body, '/features와 같은 창');
  }

  const fetched = [];
  const viaFetch = await run(createEngineTouchSender('http://127.0.0.1:9000', (url, init) => { fetched.push(JSON.parse(init.body)); return Promise.resolve(new Response(null, { status: 202 })); }));
  assert.deepEqual(viaFetch, plain);
  assert.deepEqual(fetched, plain.sent.map(({ session, body }) => ({ ...body, session_id: session })));

  const failing = [
    () => { throw new Error('engine down'); },
    createEngineTouchSender('http://127.0.0.1:9000', () => { throw new TypeError('sync'); }),
    createEngineTouchSender('http://127.0.0.1:9000', () => Promise.reject(new TypeError('offline'))),
    createEngineTouchSender('http://127.0.0.1:9000', () => new Promise(() => {})),
  ];
  for (const notifyEngine of failing) assert.deepEqual(await run(notifyEngine), plain);
});

// 엔진에 먼저 보내고 /features는 그 뒤에 보내는 순서: 확인 주기(FEATURE_TICK_MS)의 타이머는 node:test의 가짜 타이머로 돌립니다.
const flushAnswers = () => new Promise(resolve => setImmediate(resolve));
function engineFirst(notifyEngine, sendFeatures) {
  const { saved, emit } = pilotLog(true);
  emit(1000, 'screen_enter', { visibility: 'visible' });
  const clock = { now: 4001 }, sent = [];
  const transport = createTouchFeatureTransport((session, body, signal) => {
    sent.push({ session, body, signal });
    return sendFeatures ? sendFeatures(session, sent.length, signal) : Promise.resolve({ session_id: session });
  }, () => saved, () => clock.now, notifyEngine);
  const context = { key: 'menu', canOffer: false, includeInteraction: false, receive: () => {} };
  transport.setContext('server', true, context);
  return { saved, clock, sent, transport, context };
}

test('엔진에 먼저 보내고 /features는 엔진이 답한 뒤에 같은 본문으로 보낸다', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const order = [], answers = [];
  const { sent, transport } = engineFirst((session, body) => {
    order.push(['engine', body.window_end]);
    return new Promise(resolve => answers.push(resolve));
  });
  const pending = transport.tick();
  await flushAnswers();
  const end = new Date(4000).toISOString();
  assert.deepEqual(order, [['engine', end]]);
  assert.equal(sent.length, 0, '엔진의 답을 기다리는 동안 /features는 아직 보내지 않음');
  assert.equal(transport.status().state, 'sending');
  t.mock.timers.tick(FEATURE_TICK_MS - 1);
  await flushAnswers();
  assert.equal(sent.length, 0, '확인 주기 한 번이 차기 전에 엔진이 답하지 않았으면 계속 기다림');
  answers[0]();
  await pending;
  assert.equal(sent.length, 1, '엔진이 답하자 보냄');
  assert.equal(sent[0].body.window_end, end);
  assert.equal(transport.status().state, 'sent');
  // 실제 엔진 전송기: 202 답의 본문을 다 읽으면 바로 보냅니다.
  const viaFetch = engineFirst(createEngineTouchSender('http://127.0.0.1:9000', () => Promise.resolve(new Response('{"status":"accepted"}', { status: 202 }))));
  const second = viaFetch.transport.tick();
  await flushAnswers();
  assert.equal(viaFetch.sent.length, 1, '엔진이 답하면 확인 주기를 기다리지 않음');
  await second;
  transport.dispose(); viaFetch.transport.dispose();
});

test('엔진이 답하지 않으면 /features는 확인 주기 한 번(FEATURE_TICK_MS) 뒤에 보내고, 5초 중단 타이머는 그때 시작한다', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const engine = [];
  // 응답하지 않는 /features: 중단 신호에 fetch처럼 AbortError로 거부합니다.
  const { sent, transport } = engineFirst((session, body) => { engine.push(body); return new Promise(() => {}); },
    (session, count, signal) => new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))));
  const pending = transport.tick();
  await flushAnswers();
  t.mock.timers.tick(FEATURE_TICK_MS - 1);
  await flushAnswers();
  assert.equal(sent.length, 0);
  t.mock.timers.tick(1);
  await flushAnswers();
  assert.equal(sent.length, 1, '확인 주기 한 번 뒤에 보냄');
  assert.equal(sent[0].body, engine[0], '엔진에 보낸 것과 같은 본문');
  // 중단 타이머는 /features 요청에만 걸립니다: 요청이 시작된 때부터 5초입니다.
  t.mock.timers.tick(5000 - 1);
  assert.equal(sent[0].signal.aborted, false);
  t.mock.timers.tick(1);
  assert.equal(sent[0].signal.aborted, true, '/features 요청이 시작되고 5초 뒤에 끊음');
  await pending;
  assert.equal(transport.status().state, 'error');
  transport.dispose();
});

test('엔진 전송기가 없으면 기다리지 않고, 엔진 요청이 실패하면 확인 주기를 기다리지 않고 /features를 보낸다', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const plain = engineFirst(undefined);
  const first = plain.transport.tick();
  assert.equal(plain.sent.length, 1, '엔진 전송기가 없으면 같은 호출 안에서 바로 보냄(지금과 같음)');
  await first;
  for (const notifyEngine of [
    createEngineTouchSender('http://127.0.0.1:9000', () => Promise.reject(new TypeError('offline'))),
    createEngineTouchSender('http://127.0.0.1:9000', () => { throw new TypeError('sync'); }),
    () => { throw new Error('engine down'); },
  ]) {
    const failing = engineFirst(notifyEngine);
    const pending = failing.transport.tick();
    await flushAnswers();
    assert.equal(failing.sent.length, 1, '실패한 엔진 요청은 확인 주기를 기다리게 하지 않음');
    await pending;
    assert.deepEqual(failing.sent[0].body, plain.sent[0].body, '엔진 실패는 /features 본문을 바꾸지 않음');
    failing.transport.dispose();
  }
  plain.transport.dispose();
});

for (const change of ['session', 'disabled', 'dispose']) test(`엔진의 답을 기다리는 동안 ${change === 'session' ? '세션이 바뀌면' : change === 'disabled' ? '전송을 끄면' : '전송기를 버리면'} 그 창의 /features는 보내지 않는다`, async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const engine = [];
  const { saved, sent, transport, context } = engineFirst((session, body) => { engine.push({ session, body }); return new Promise(() => {}); });
  const pending = transport.tick();
  await flushAnswers();
  if (change === 'session') transport.setContext('next', true, context);
  else if (change === 'disabled') transport.setContext('server', false, context);
  else transport.dispose();
  t.mock.timers.tick(FEATURE_TICK_MS);
  await pending;
  assert.equal(sent.length, 0, '버린 창은 /features로 보내지 않음');
  if (change !== 'session') return;
  // 새 세션의 창은 새 세션으로 엔진에 먼저 보내고, 그 뒤에 /features로 보냅니다.
  saved.serverSessionId = 'next';
  for (const event of saved.events) event.serverSessionId = 'next';
  const next = transport.tick();
  await flushAnswers();
  t.mock.timers.tick(FEATURE_TICK_MS);
  await next;
  assert.deepEqual(engine.map(({ session }) => session), ['server', 'next']);
  assert.deepEqual(sent.map(({ session }) => session), ['next']);
  transport.dispose();
});

test('엔진의 답을 기다리는 동안에도 창은 한 번에 하나이고, 엔진은 창마다 한 번만 받으며 /features가 실패해도 다시 받지 않는다', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const engine = [], answers = [];
  const { clock, sent, transport } = engineFirst((session, body) => { engine.push(body.window_end); return new Promise(resolve => answers.push(resolve)); },
    (session, count) => count === 1 ? Promise.reject(new TypeError('offline')) : Promise.resolve({ session_id: session }));
  const first = transport.tick();
  await flushAnswers();
  // 다음 창의 끝이 지난 확인도 기다리는 창이 있으면 아무것도 하지 않습니다.
  clock.now = 5001;
  await transport.tick();
  assert.deepEqual([engine.length, sent.length, transport.status().state], [1, 0, 'sending']);
  answers[0]();
  await first;
  assert.equal(transport.status().state, 'error', '첫 /features는 실패');
  for (const at of [5001, 6001]) {
    clock.now = at;
    const pending = transport.tick();
    await flushAnswers();
    answers.at(-1)();
    await pending;
  }
  const ends = [4000, 5000, 6000].map(ms => new Date(ms).toISOString());
  assert.deepEqual(engine, ends, '엔진은 창마다 한 번, 실패한 창도 다시 받지 않음');
  assert.deepEqual(sent.map(({ body }) => body.window_end), ends);
  assert.equal(transport.status().state, 'sent');
  transport.dispose();
});

// 다음 창이 다음 확인 전에 차면, 전송기는 그 창이 차는 때(창 끝 + 1ms)에 한 번 더 확인합니다. 시계와 가짜 타이머를 함께 움직입니다.
test('확인이 창이 차기 1ms 전에 오면 창이 차는 때에 한 번 더 확인해 바로 보내고, 같은 창을 두 번 보내지 않는다', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const times = [];
  const setup = engineFirst(undefined, session => { times.push(setup.clock.now); return Promise.resolve({ session_id: session }); });
  const { clock, sent, transport } = setup;
  const advance = ms => { clock.now += ms; t.mock.timers.tick(ms); };
  await transport.tick();
  assert.deepEqual(times, [4001]);
  // 다음 창(끝 5000)은 5001에 찹니다. 4750의 확인에서는 다음 확인(5000)보다 늦게 차므로 추가 확인을 잡지 않고 확인 주기가 맡습니다.
  clock.now = 4750; await transport.tick();
  advance(FEATURE_TICK_MS + 1);
  await flushAnswers();
  assert.equal(sent.length, 1, '다음 확인보다 늦게 차는 창에는 추가 확인이 없음');
  await transport.tick();
  assert.deepEqual(times, [4001, 5001]);
  // 6000의 확인은 창(끝 6000)이 차기 1ms 전이라 보내지 않습니다. 같은 밀리초에 다시 확인해도 추가 확인은 하나입니다.
  clock.now = 6000;
  await transport.tick();
  await transport.tick();
  assert.equal(sent.length, 2, '창이 차기 전에는 보내지 않음');
  advance(1);
  await flushAnswers();
  assert.deepEqual(times, [4001, 5001, 6001], '창이 차는 밀리초에 보냄(다음 확인 6250을 기다리지 않음)');
  assert.equal(sent[2].body.window_start, sent[1].body.window_end);
  assert.equal(sent[2].body.window_end, new Date(6000).toISOString());
  // 같은 때와 다음 확인 주기의 확인은 이미 보낸 창을 다시 보내지 않습니다.
  await transport.tick();
  advance(FEATURE_TICK_MS - 1);
  await transport.tick();
  await flushAnswers();
  assert.equal(sent.length, 3, '두 번째 요청 없음');
  transport.dispose();
});

for (const change of ['session', 'disabled', 'dispose']) test(`창이 차는 때의 추가 확인은 ${change === 'session' ? '세션이 바뀌면' : change === 'disabled' ? '전송을 끄면' : '전송기를 버리면'} 지운다`, async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const sends = [];
  const setup = engineFirst(undefined, session => { sends.push([session, setup.clock.now]); return Promise.resolve({ session_id: session }); });
  const { saved, clock, transport, context } = setup;
  await transport.tick();
  // 5000의 확인이 5001의 추가 확인을 잡습니다.
  clock.now = 5000; await transport.tick();
  if (change === 'session') {
    transport.setContext('next', true, context);
    saved.serverSessionId = 'next';
    for (const event of saved.events) event.serverSessionId = 'next';
  } else if (change === 'disabled') {
    transport.setContext('server', false, context);
    transport.setContext('server', true, context);
  } else {
    transport.dispose();
    transport.setContext('server', true, context);
  }
  clock.now = 5001; t.mock.timers.tick(1);
  await flushAnswers();
  assert.equal(sends.length, 1, '지운 추가 확인은 돌지 않음');
  // 다음 확인은 보낼 창이 있어 보냅니다. 위에서 보내지 않은 것은 추가 확인이 지워졌기 때문입니다.
  await transport.tick();
  assert.deepEqual(sends, [['server', 4001], [change === 'session' ? 'next' : 'server', 5001]]);
  transport.dispose();
});

test('묻지 않고 실행하는 결정은 제안을 띄울 수 없는 동안에도 받고, 다른 방문·바뀐 화면 상태의 응답은 받지 않는다', async () => {
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 4000;
  const calls = [], received = [], acted = [];
  const transport = createTouchFeatureTransport((session, body) => new Promise(resolve => calls.push({ session, body, resolve })), () => saved, () => now);
  const context = (key, canOffer) => transport.setContext('server', true, { key, canOffer, includeInteraction: false,
    receive: response => received.push(response), act: response => acted.push(response) });
  // 옵션 창이 열려 제안을 띄울 수 없는 동안에도 결정은 받습니다.
  context('menu:option', false);
  let pending = transport.tick();
  calls[0].resolve({ session_id: 'server', n: 1 }); await pending;
  assert.deepEqual(acted.map(response => response.n), [1]);
  assert.deepEqual(received, []);
  // 제안을 띄울 수 있으면 같은 응답을 결정과 제안 양쪽에 넘깁니다.
  context('menu', true);
  now = 5000; pending = transport.tick();
  calls[1].resolve({ session_id: 'server', n: 2 }); await pending;
  assert.deepEqual(acted.map(response => response.n), [1, 2]);
  assert.deepEqual(received.map(response => response.n), [2]);
  // 요청 중에 화면 상태가 바뀌면 받지 않습니다.
  now = 6000; pending = transport.tick();
  context('menu:page-2', true);
  calls[2].resolve({ session_id: 'server', n: 3 }); await pending;
  // 요청 중에 새 방문이 시작되면 받지 않습니다.
  now = 7000; pending = transport.tick();
  emit(6500, 'screen_enter', { visibility: 'visible', from: 'menu' }, 'visit-2', 'review');
  calls[3].resolve({ session_id: 'server', n: 4 }); await pending;
  assert.deepEqual(acted.map(response => response.n), [1, 2]);
  assert.deepEqual(received.map(response => response.n), [2]);
  transport.dispose();
});

test('유지되어 반복된 3-1 안내는 화면 상태가 바뀌어도 안내 바를 다시 열지 않고, 4-1 크게 보기는 다시 묻는다', async () => {
  const notice = { session_id: 'server', ai_available: true, support: { preset: 'step_guide', requires_confirmation: false, decided_by: 'rule_placeholder',
    name: 'remaining_steps_notice', decision_id: 'd0001', steps_left: 2, target_id: 'cart_progress', message_id: 'steps_left_notice' } };
  const bigButton = { session_id: 'server', ai_available: true, support: { preset: 'large_button', requires_confirmation: true, decided_by: 'rule_placeholder',
    name: 'large_button', decision_id: 'd0002' } };
  for (const [answer, expected] of [[notice, null], [bigButton, 'enlarge']]) {
    const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
    let now = 4000;
    const offered = [], acted = [];
    const transport = createTouchFeatureTransport(async () => answer, () => saved, () => now);
    // useBackendSupport의 receive처럼 안내 바에 올릴 프리셋을 읽고, 화면 상태(분류·쪽)를 바꿔 가며 같은 결정의 반복 응답을 받습니다.
    for (const [index, key] of ['menu', 'menu:coffee', 'menu:page-2'].entries()) {
      transport.setContext('server', true, { key, canOffer: true, includeInteraction: false,
        receive: response => offered.push(readOfferedSupport(response, 'server', initialSettings)), act: response => acted.push(response.support.decision_id) });
      now = 4000 + index * 1000; await transport.tick();
    }
    assert.equal(acted.length, 3, '같은 결정이 세 번 반복');
    assert.deepEqual(offered, [expected, expected, expected]);
    transport.dispose();
  }
});

test('전송기에서 화면까지: 결정은 결정 ID마다 세션에서 한 번만 실행하고, 그 응답은 안내 바에 올리지 않는다', async () => {
  const support = (extra) => ({ preset: 'none', requires_confirmation: false, decided_by: 'rule_placeholder', ...extra });
  const notice = support({ preset: 'step_guide', name: 'remaining_steps_notice', decision_id: 'd0001', steps_left: 2, target_id: 'cart_progress', message_id: 'steps_left_notice' });
  const highlight = support({ name: 'highlight_next_action', decision_id: 'd0002', steps_left: 2, target_id: 'cart-add' });
  // 창마다의 답: [ai_available, support, 이 창의 화면 상태 키]
  const answers = [[true, notice, 'menu'], [true, notice, 'menu:coffee'], [false, notice, 'menu:coffee'],
    [false, highlight, 'menu:option'], [true, support({}), 'menu'], [true, notice, 'menu']];
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 4000, index = 0, session = 'server';
  const read = createDecisionReader(), seen = [];
  const transport = createTouchFeatureTransport(async requested => ({ session_id: requested, ai_available: answers[index][0], states: null, model_version: null, support: answers[index][1] }),
    () => saved, () => now);
  for (; index < answers.length; index++) {
    if (index === answers.length - 1) {
      // 새 세션에서는 같은 결정 ID도 처음부터 셉니다.
      session = 'next'; saved.serverSessionId = 'next';
      for (const event of saved.events) event.serverSessionId = 'next';
    }
    const entry = { offered: [], status: null, action: null };
    transport.setContext(session, true, { key: answers[index][2], canOffer: true, includeInteraction: false,
      receive: response => entry.offered.push(readOfferedSupport(response, session, initialSettings)),
      act: response => Object.assign(entry, read(response, session)) });
    now = 4000 + index * 1000; await transport.tick();
    seen.push({ ...entry, status: entry.status?.decisionId ?? null, action: entry.action?.kind ?? null });
  }
  assert.deepEqual(seen.map(entry => entry.action), ['steps_left', null, null, 'highlight', null, 'steps_left']);
  assert.deepEqual(seen.map(entry => entry.status), ['d0001', 'd0001', 'd0001', 'd0002', null, 'd0001'], '개발용 상태 줄은 매 응답');
  assert.deepEqual(seen.map(entry => entry.offered), [[null], [null], [null], [null], [null], [null]], '안내 바는 한 번도 열리지 않음');
  transport.dispose();
});

test('3-1 안내는 받아들인 응답을 따라 남고, 버린 응답은 아무것도 바꾸지 않으며, 전송이 멈추면(실패·중단·꺼짐) 내렸다가 같은 결정 ID에 되살아난다', async () => {
  const support = extra => ({ preset: 'none', requires_confirmation: false, decided_by: 'rule_placeholder', ...extra });
  const notice = steps_left => support({ preset: 'step_guide', name: 'remaining_steps_notice', decision_id: 'd0001', steps_left, target_id: 'cart_progress', message_id: 'steps_left_notice' });
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 4000, reply = null;
  const read = createDecisionReader(), states = [];
  let shown = null; // useSupportDecision의 안내 상태처럼
  const transport = createTouchFeatureTransport(async session => {
    if (reply instanceof Error) throw reply;
    return { session_id: session, ai_available: true, states: null, model_version: null, support: reply };
  }, () => saved, () => now);
  const context = (key, enabled = true) => transport.setContext('server', enabled, { key, canOffer: true, includeInteraction: false, receive: () => {},
    act: response => { shown = read(response, 'server').notice; },
    onState: state => { states.push(state); if (answersStoppedStates.includes(state)) { read.pauseNotice(); shown = null; } } });
  const tick = async (at, answer, during) => { now = at; reply = answer; const pending = transport.tick(); during?.(); await pending; };

  context('menu');
  await tick(4000, notice(2));
  assert.deepEqual(shown, { sessionId: 'server', decisionId: 'd0001', stepsLeft: 2 });
  // 요청 중에 화면 상태가 바뀐 응답은 전송기가 버립니다: 결정이 없는 응답이어도 안내는 그대로입니다.
  await tick(5000, support({}), () => context('menu:coffee'));
  assert.equal(shown?.stepsLeft, 2, '버린 응답은 안내를 바꾸지 않음');
  await tick(6000, notice(1));
  assert.equal(shown?.stepsLeft, 1, '받아들인 응답의 남은 단계 수를 따라감');
  // 요청이 실패하면 다음 확인에서 전송기의 상태(error)를 보고 내립니다.
  await tick(7000, new TypeError('offline'));
  assert.equal(shown?.stepsLeft, 1, '실패한 요청의 답은 없음');
  await tick(7250, notice(1)); // 구간이 끝나기 전의 확인: 상태만 넘김
  assert.equal(shown, null, 'error 상태를 보면 내림');
  // backend가 지원을 유지하는 동안 다음 응답이 같은 결정 ID를 다시 실으면 되살아납니다.
  await tick(8000, notice(1));
  assert.deepEqual(shown, { sessionId: 'server', decisionId: 'd0001', stepsLeft: 1 }, '한 번의 실패로 잃지 않음');
  assert.deepEqual(states, ['idle', 'sent', 'sent', 'sent', 'error', 'error'], '확인할 때마다 그때의 상태를 넘김');
  // 그 결정이 없는 응답으로 끝난 안내는 같은 결정 ID로 되살아나지 않습니다.
  await tick(9000, support({}));
  assert.equal(shown, null);
  await tick(10000, notice(1));
  assert.equal(shown, null, '상태가 끝난 결정 ID로는 다시 띄우지 않음');
  // 세션을 멈추는 응답(410)과 전송 꺼짐도 상태로 보입니다.
  await tick(11000, new ApiError(410, {}));
  await tick(12000, notice(1));
  context('menu:coffee', false);
  await tick(13000, notice(1));
  assert.deepEqual(states.slice(-2), ['stopped', 'idle']);
  transport.dispose();
});

test('전송기에서 2-2 처리까지(OrderPage의 화면 상태와 두 처리는 흉내 냄): 결정은 다른 창 뒤에서 기다렸다가 옵션 창을 담지 않고 닫은 뒤 처음부터 주문 창을 결정 ID마다 한 번 열고, 이미 열린 창은 연 것으로 친다', async () => {
  const swap = decision_id => ({ preset: 'none', requires_confirmation: true, decided_by: 'rule_placeholder', name: 'continue_or_new_order', decision_id, steps_left: 2 });
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 4000, reply = swap('d0001');
  const read = createDecisionReader();
  // restartForDecision에 넘기는 OrderPage의 화면 상태와, 옵션 창을 담지 않고 닫는 처리·[처음으로]의 처리만 흉내 냅니다.
  const screen = { options: false, help: true, cart: false, restart: false, ask: false, restartDisabled: false };
  const done = [];
  const handlers = { closeOptions: () => { done.push('close_options'); screen.options = false; }, openRestart: () => { done.push('open'); screen.restart = true; } };
  const transport = createTouchFeatureTransport(async session => ({ session_id: session, ai_available: true, states: null, model_version: null, support: reply }),
    () => saved, () => now);
  const context = key => transport.setContext('server', true, { key, canOffer: false, includeInteraction: false, receive: () => {},
    act: response => { const { restart } = read(response, 'server'); if (restart && restartForDecision(screen, handlers)) read.restartOpened(restart.sessionId, restart.decisionId); } });
  // 1) 화면 도움 창이 열린 동안에 온 결정: 기다림
  context('menu:help'); await transport.tick();
  assert.deepEqual(done, []);
  // 2) 화면 도움을 닫고, 그 결정을 부른 누름이 옵션 창을 연 뒤의 응답(같은 결정 ID): 옵션 창을 닫고 엶
  screen.help = false; screen.options = true;
  context('menu:option'); now = 5000; await transport.tick();
  assert.deepEqual([done, screen.options, screen.restart], [['close_options', 'open'], false, true]);
  // 3) [계속 주문하기]로 닫은 뒤에도 backend가 같은 결정을 유지해 보내면 다시 열지 않음
  screen.restart = false;
  context('menu'); now = 6000; await transport.tick();
  assert.equal(screen.restart, false, '같은 결정 ID로는 한 번만 엶');
  // 4) 고객이 [처음으로]로 연 창이 떠 있을 때 온 새 결정: 연 것으로 쳐서, [계속 주문하기]로 닫은 뒤 그 결정으로 다시 열지 않음
  screen.restart = true; reply = swap('d0002');
  context('menu:restart'); now = 7000; await transport.tick();
  screen.restart = false;
  context('menu'); now = 8000; await transport.tick();
  assert.deepEqual([done, screen.restart], [['close_options', 'open'], false], '이미 열린 창은 보인 것으로 침');
  transport.dispose();
});

test('4-2 강조는 버린 응답이나 실패한 요청으로는 바뀌지 않고, 받아들인 기다림 응답에 내린다', async () => {
  const support = extra => ({ preset: 'none', requires_confirmation: false, decided_by: 'rule_placeholder', ...extra });
  const ring = support({ name: 'highlight_next_action', decision_id: 'd0001', steps_left: 2, target_id: 'cart-add' });
  const wait = support({ name: 'wait_hold_timer', decision_id: 'd0002' });
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 4000, reply = null, shown = null;
  const read = createDecisionReader();
  const transport = createTouchFeatureTransport(async session => {
    if (reply instanceof Error) throw reply;
    return { session_id: session, ai_available: true, states: null, model_version: null, support: reply };
  }, () => saved, () => now);
  const context = key => transport.setContext('server', true, { key, canOffer: false, includeInteraction: false, receive: () => {},
    act: response => { shown = read(response, 'server').highlight; } });
  const tick = async (at, answer, during) => { now = at; reply = answer; const pending = transport.tick(); during?.(); await pending; };
  context('menu:option');
  await tick(4000, ring);
  assert.equal(shown?.decisionId, 'd0001');
  await tick(5000, wait, () => context('menu:option:2')); // 요청 중에 화면 상태가 바뀌어 버린 응답
  assert.equal(shown?.decisionId, 'd0001', '버린 응답은 바꾸지 않음');
  await tick(6000, new TypeError('offline'));
  assert.equal(shown?.decisionId, 'd0001', '실패한 요청은 바꾸지 않음');
  await tick(7000, ring);
  assert.equal(shown?.decisionId, 'd0001', '같은 결정이면 남음');
  await tick(8000, wait);
  assert.equal(shown, null, '받아들인 기다림 응답에 내림');
  transport.dispose();
});

test('전송기에서 안내 바까지(useBackendSupport의 상태와 호출 순서는 흉내 냄): 1-2 카드를 내린 응답이 실은 말로 주문 묻기는 그 응답에 뜨고, 남은 묻기와 결정 ID 없는 카드는 그대로다', async () => {
  const ask = (name, decision_id) => ({ preset: 'none', requires_confirmation: true, decided_by: 'rule_placeholder', name, decision_id, steps_left: 2 });
  const lower = ask('lower_screen', 'd0001'), voice = ask('voice_order', 'd0002');
  const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
  let now = 4000, reply = null, card = null;
  const transport = createTouchFeatureTransport(async session => {
    if (reply instanceof Error) throw reply;
    return { session_id: session, ai_available: true, states: null, model_version: null, support: reply };
  }, () => saved, () => now);
  // 카드가 없을 때만 새 카드를 띄우고(receive), 받아들인 응답마다 카드가 남는지 보며 내린 카드 자리에는 같은 응답의 묻기를 띄웁니다
  // (act). 두 곳 모두 같은 확인(offeredCard)을 거치고, act의 화면 조건은 내린 카드를 뺀 것입니다.
  const place = (key, gate) => ({ sessionId: 'server', settings: initialSettings, voiceOrder: true, context: key, gate });
  const remembered = () => false;
  const context = (key = 'menu') => transport.setContext('server', true, { key, canOffer: card === null, includeInteraction: false,
    receive: response => { const next = offeredCard(response, place(key, card === null), remembered); if (next && !card) card = next; },
    act: response => { const next = offeredCard(response, place(key, true), remembered); card = cardAfterAnswer(card, response, 'server', () => next); } });
  const tick = async (at, answer, during) => { context(); now = at; reply = answer; const pending = transport.tick(); during?.(); await pending; };
  await tick(4000, lower);
  assert.deepEqual(card, { ask: 'lower_screen', context: 'menu', decisionId: 'd0001' });
  await tick(5000, lower);
  assert.equal(card?.decisionId, 'd0001', 'backend가 붙잡은 묻기는 카드가 남음');
  await tick(6000, voice, () => context('menu:coffee'));
  assert.equal(card?.decisionId, 'd0001', '버린 응답은 바꾸지 않음');
  await tick(7000, new TypeError('offline'));
  assert.equal(card?.decisionId, 'd0001', '실패한 요청은 바꾸지 않음');
  await tick(8000, voice);
  assert.deepEqual(card, { ask: 'voice_order', context: 'menu', decisionId: 'd0002' }, '1-2를 거두고 1-1을 연 응답: 1-2 카드를 내리고 그 응답에 말로 주문을 물음');
  await tick(9000, voice);
  assert.equal(card?.decisionId, 'd0002', '붙잡힌 말로 주문 묻기는 그대로');
  // 결정 ID 없는 응답으로 연 카드(팀의 프리셋 제안)는 지금처럼 다음 응답에 내려가지 않습니다.
  card = null;
  await tick(10000, { preset: 'large_text', requires_confirmation: true, decided_by: 'jev' });
  await tick(11000, { preset: 'none', requires_confirmation: false, decided_by: 'rule_placeholder' });
  assert.deepEqual(card, { ask: 'large_text', context: 'menu', decisionId: null });
  transport.dispose();
});

test('전송기에서 2-2 처리까지(OrderPage의 상태와 호출 순서는 흉내 냄): 결정 ID로 연 카드는 2-2 결정을 실은 같은 응답에 내려가고 창은 그 응답에 열리며, 결정 ID 없는 카드는 창을 기다리게 한다', async () => {
  const swap = { preset: 'none', requires_confirmation: true, decided_by: 'rule_placeholder', name: 'continue_or_new_order', decision_id: 'd0002', steps_left: 2 };
  const cases = [
    [{ ask: 'lower_screen', context: 'menu', decisionId: 'd0001' }, ['open'], null],
    [{ ask: 'large_text', context: 'menu', decisionId: null }, [], { ask: 'large_text', context: 'menu', decisionId: null }],
  ];
  for (const [shown, opened, left] of cases) {
    const { saved, emit } = pilotLog(true); emit(0, 'screen_enter', { visibility: 'visible' });
    let card = shown;
    const read = createDecisionReader(), done = [];
    const screen = { options: false, help: false, cart: false, restart: false, ask: false, restartDisabled: false };
    const handlers = { closeOptions: () => done.push('close_options'), openRestart: () => done.push('open') };
    const place = { sessionId: 'server', settings: initialSettings, voiceOrder: true, context: 'menu', gate: true };
    const transport = createTouchFeatureTransport(async session => ({ session_id: session, ai_available: true, states: null, model_version: null, support: swap }),
      () => saved, () => 4000);
    // useBackendSupport의 act: 카드 갱신을 맡긴 뒤 onDecision을 부르므로, 2-2 처리는 이 응답 전 그림의 카드(before)를 봅니다.
    transport.setContext('server', true, { key: 'menu', canOffer: false, includeInteraction: false, receive: () => {},
      act: response => {
        const before = card;
        card = cardAfterAnswer(card, response, 'server', () => offeredCard(response, place, () => false));
        const { restart } = read(response, 'server');
        if (restart && restartForDecision({ ...screen, ask: cardHoldsRestart(before, false) }, handlers)) read.restartOpened(restart.sessionId, restart.decisionId);
      } });
    await transport.tick();
    assert.deepEqual([done, card], [opened, left], shown.decisionId ?? 'nameless');
    transport.dispose();
  }
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
