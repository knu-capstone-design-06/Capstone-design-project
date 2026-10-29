import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError } from '../../shared/api/client.ts';
import { createVoiceApi } from './voiceApi.ts';
import { VoiceController } from './voiceController.ts';
import { FakeRecognition, factory, tick } from './voiceFakes.mjs';

const addAmericano = { tool: 'add_cart_item', arguments: { product_id: 'americano', temperature: 'iced', quantity: 2 } };
const status = (value, extra = {}) => ({ request_id: 'vr_1', status: value, reply_text: null, tool_calls: [], actions: [], error: null, ...extra });

function setup(results, options = {}) {
  FakeRecognition.reset();
  const calls = [];
  const delivered = [];
  const queue = [...results];
  const api = {
    async submit(sessionId, body, key) { calls.push({ sessionId, body, key }); return { request_id: 'vr_1', status: 'accepted', accepted_at: '2026-10-13T00:00:00Z' }; },
    async get() { const next = queue.length > 1 ? queue.shift() : queue[0]; if (next instanceof Error) throw next; return next; },
  };
  const controller = new VoiceController({
    api, recognition: factory, pollIntervalMs: 1, pollTimeoutMs: 200,
    createKey: () => `key-${calls.length + 1}`, onResult: result => delivered.push(result), ...options,
  });
  controller.setContext({ sessionId: 'session-1', screenId: 'menu' });
  return { api, calls, controller, delivered };
}

test('음성 모드를 켜면 바로 듣고, 확실한 결과는 넘긴 뒤 마이크를 닫는다', async () => {
  const { calls, controller, delivered } = setup([status('processing'), status('completed', { tool_calls: [addAmericano] })]);
  assert.equal(controller.setEnabled(true), true);
  assert.deepEqual([controller.getSnapshot().enabled, controller.getSnapshot().phase], [true, 'listening']);
  FakeRecognition.last().final(['아이스 아메리카노 두 잔', 0.9], ['아이스 아메리카노 두 개', 0.4]);
  assert.equal(controller.getSnapshot().phase, 'processing');
  await tick(20);
  assert.deepEqual(calls, [{ sessionId: 'session-1', key: 'key-1', body: {
    text: '아이스 아메리카노 두 잔', screen_id: 'menu',
    alternatives: [{ text: '아이스 아메리카노 두 잔', confidence: 0.9 }, { text: '아이스 아메리카노 두 개', confidence: 0.4 }],
  } }]);
  const snapshot = controller.getSnapshot();
  assert.deepEqual([snapshot.phase, snapshot.lastResult.status, snapshot.error], ['idle', 'completed', null]);
  assert.equal(snapshot.lastTranscript, '아이스 아메리카노 두 잔', '처리 결과가 나온 뒤에도 인식 문장을 표시할 수 있음');
  assert.deepEqual(delivered.map(result => result.tool_calls), [[addAmericano]]);
  assert.equal(FakeRecognition.instances.length, 1);
});

test('확인·질문 결과에는 대답을 듣기 위해 마이크를 다시 연다', async () => {
  const { controller } = setup([status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' })]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
  await tick(20);
  assert.equal(controller.getSnapshot().lastResult.reply_text, '아이스 아메리카노 2잔 담을까요?');
  assert.equal(controller.getSnapshot().lastTranscript, '아메리카노 두 잔', '대답을 다시 듣는 동안 첫 인식 문장 유지');
  assert.equal(controller.getSnapshot().phase, 'listening');
  assert.equal(FakeRecognition.instances.length, 2);
});

test('확인 질문 뒤의 "네"는 같은 세션의 다음 요청으로 보낸다', async () => {
  const { calls, controller, delivered } = setup([
    status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' }),
    status('completed', { tool_calls: [addAmericano] }),
  ]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
  await tick(20);
  assert.equal(controller.getSnapshot().phase, 'listening');
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  assert.deepEqual(calls.map(call => [call.sessionId, call.body.text, call.key]), [
    ['session-1', '아메리카노 두 잔', 'key-1'], ['session-1', '네', 'key-2'],
  ]);
  assert.deepEqual(delivered.map(result => result.status), ['needs_confirmation', 'completed']);
});

test('확인 질문 뒤 무음으로 닫혀도 다시 들으면 "네"를 다음 요청으로 보낸다', async () => {
  const { calls, controller } = setup([status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' }), status('completed', { tool_calls: [addAmericano] })]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
  await tick(20);
  FakeRecognition.last().fail('no-speech');
  assert.equal(controller.getSnapshot().phase, 'idle');
  assert.equal(controller.listen(), true);
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  assert.deepEqual(calls.map(call => call.body.text), ['아메리카노 두 잔', '네']);
});

test('확인 흐름이 끝나면 다시 들을 때 한 글자를 다시 거른다', async () => {
  const { calls, controller } = setup([status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' }), status('completed', { tool_calls: [addAmericano] })]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
  await tick(20);
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  controller.listen();
  FakeRecognition.last().final(['응', 0.9]);
  await tick(20);
  assert.deepEqual(calls.map(call => call.body.text), ['아메리카노 두 잔', '네']);
});

test('세션이 바뀌거나 음성 모드를 끄면 대답 대기 상태를 지운다', async () => {
  for (const reset of [
    controller => controller.setContext({ sessionId: 'session-2', screenId: 'menu' }),
    controller => { controller.setEnabled(false); controller.setEnabled(true); },
  ]) {
    const { calls, controller } = setup([status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' })]);
    controller.setEnabled(true);
    FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
    await tick(20);
    reset(controller);
    controller.listen();
    FakeRecognition.last().final(['네', 0.9]);
    await tick(20);
    assert.equal(calls.length, 1);
  }
});

test('결과 콜백에서 세션을 바꾸면 이전 확인 질문 때문에 마이크를 열거나 "네"를 보내지 않는다', async () => {
  let controller;
  const setupResult = setup([status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' })], {
    onResult: () => controller.setContext({ sessionId: 'session-2', screenId: 'menu' }),
  });
  controller = setupResult.controller;
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
  await tick(20);
  assert.deepEqual([controller.getSnapshot().phase, FakeRecognition.instances.length], ['idle', 1]);
  controller.listen();
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  assert.deepEqual(setupResult.calls.map(call => call.sessionId), ['session-1']);
});

test('결과 콜백에서 음성 모드를 끄면 다시 켜도 이전 대답 대기 상태가 이어지지 않는다', async () => {
  let controller;
  const setupResult = setup([status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' })], { onResult: () => controller.setEnabled(false) });
  controller = setupResult.controller;
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
  await tick(20);
  assert.deepEqual([controller.getSnapshot().enabled, controller.getSnapshot().phase, FakeRecognition.instances.length], [false, 'idle', 1]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  assert.equal(setupResult.calls.length, 1);
});

test('키오스크에게 한 말이 아니면(ignored) 화면 문구 없이 닫는다', async () => {
  const { controller, delivered } = setup([status('ignored')]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['너 뭐 먹을래', 0.8]);
  await tick(20);
  assert.deepEqual([controller.getSnapshot().phase, controller.getSnapshot().lastResult], ['idle', null]);
  assert.equal(delivered[0].status, 'ignored');
  assert.equal(controller.getSnapshot().lastTranscript, '', '주변 대화로 무시된 문장은 화면에 남기지 않음');
  assert.equal(FakeRecognition.instances.length, 1);
});

test('확인 질문 중 주변 대화가 무시돼도 질문을 유지하고 다시 말하기의 "네"를 받는다', async () => {
  const question = status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' });
  const { controller, calls } = setup([question, status('ignored'), status('completed', { tool_calls: [addAmericano] })]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.9]);
  await tick(20);
  FakeRecognition.last().final(['너 뭐 먹을래', 0.9]);
  await tick(20);
  assert.equal(controller.getSnapshot().lastResult, question);
  assert.equal(controller.getSnapshot().lastTranscript, '');
  assert.equal(controller.getSnapshot().phase, 'idle');
  assert.equal(FakeRecognition.instances.length, 2, '주변 대화 때문에 마이크를 반복해서 열지 않음');
  controller.listen();
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  assert.deepEqual(calls.map(call => call.body.text), ['아메리카노 두 잔', '너 뭐 먹을래', '네']);
  assert.equal(controller.getSnapshot().lastResult.status, 'completed');
  controller.dispose();
});

test('확인·추가 질문 뒤 서버 실패에도 질문을 유지하고 수동 재청취로 짧은 답변을 보낸다', async () => {
  for (const kind of ['needs_confirmation', 'needs_clarification']) {
    const question = status(kind, { reply_text: '이 메뉴로 할까요?' });
    const failed = status('failed', { error: { code: 'llm_error', detail: '해석 실패' } });
    const { controller, calls, delivered } = setup([question, failed, status('completed')]);
    controller.setEnabled(true);
    FakeRecognition.last().final(['아메리카노 주세요', 0.9]);
    await tick(20);
    FakeRecognition.last().final(['네', 0.9]);
    await tick(20);
    assert.equal(controller.getSnapshot().lastResult, question);
    assert.equal(controller.getSnapshot().error, 'request_failed');
    assert.equal(controller.getSnapshot().phase, 'idle');
    assert.equal(FakeRecognition.instances.length, 2, '실패 뒤 자동 재청취하지 않음');
    controller.listen();
    assert.equal(controller.getSnapshot().error, null);
    FakeRecognition.last().final(['네', 0.9]);
    await tick(20);
    assert.deepEqual(calls.map(call => call.body.text), ['아메리카노 주세요', '네', '네']);
    assert.deepEqual(delivered.map(result => result.status), [kind, 'failed', 'completed']);
    assert.equal(controller.getSnapshot().lastResult.status, 'completed');
    controller.listen();
    FakeRecognition.last().final(['네', 0.9]);
    await tick(20);
    assert.equal(calls.length, 3, '완료 후에는 이전 대답 대기를 지움');
    controller.dispose();
  }
});

test('이전 질문이 없는 서버 실패는 대답 대기를 새로 만들지 않는다', async () => {
  const { controller, calls } = setup([status('failed')]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 주세요', 0.9]);
  await tick(20);
  assert.equal(controller.getSnapshot().lastResult.status, 'failed');
  assert.equal(controller.getSnapshot().error, 'request_failed');
  controller.listen();
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  assert.equal(calls.length, 1);
  controller.dispose();
});

// Chrome의 비동기 stop/abort 종료를 직접 제어하며 중복 마이크 시작을 거부합니다.
function deferredRecognition() {
  let active = null;
  return () => new class extends FakeRecognition {
    start() {
      if (active) throw new Error('previous recognition is still active');
      active = this;
      super.start();
    }
    stop() { this.stopped += 1; }
    abort() { this.aborted += 1; }
    finish() { if (active === this) active = null; this.onend?.(); }
  }();
}

test('빠른 질문 응답이 와도 이전 마이크의 onend 뒤에만 다시 듣는다', async () => {
  const { controller } = setup([status('needs_clarification', { reply_text: '온도를 골라 주세요.' })], { recognition: deferredRecognition() });
  controller.setEnabled(true);
  const first = FakeRecognition.last();
  first.final(['아메리카노 주세요', 0.9]);
  await tick(20);
  assert.equal(FakeRecognition.instances.length, 1);
  controller.listen();
  first.final(['중복 최종 이벤트', 0.9]);
  first.finish();
  assert.equal(FakeRecognition.instances.length, 2);
  assert.deepEqual([controller.getSnapshot().phase, controller.getSnapshot().error], ['listening', null]);
  controller.dispose();
  FakeRecognition.last().finish();
});

test('마이크 종료 대기 중 모드를 끄면 예약된 재청취를 취소한다', async () => {
  const { controller } = setup([status('needs_clarification', { reply_text: '온도를 골라 주세요.' })], { recognition: deferredRecognition() });
  controller.setEnabled(true);
  const first = FakeRecognition.last();
  first.final(['아메리카노 주세요', 0.9]);
  await tick(20);
  controller.setEnabled(false);
  first.finish();
  assert.equal(FakeRecognition.instances.length, 1);
  assert.deepEqual([controller.getSnapshot().enabled, controller.getSnapshot().phase], [false, 'idle']);
});

test('빠르게 OFF→ON해도 이전 abort 종료를 기다리고 늦은 발화는 버린다', () => {
  const { controller, calls } = setup([status('completed')], { recognition: deferredRecognition() });
  controller.setEnabled(true);
  const first = FakeRecognition.last();
  controller.setEnabled(false);
  controller.setEnabled(true);
  first.final(['취소한 발화', 0.9]);
  assert.equal(FakeRecognition.instances.length, 1);
  assert.equal(calls.length, 0);
  first.finish();
  assert.equal(FakeRecognition.instances.length, 2);
  assert.deepEqual([controller.getSnapshot().phase, controller.getSnapshot().error], ['listening', null]);
  controller.dispose();
  FakeRecognition.last().finish();
});

test('음성 모드를 끈 뒤 이전 마이크가 늦게 보낸 오류는 남기지 않는다', () => {
  const { controller } = setup([status('completed')], { recognition: deferredRecognition() });
  controller.setEnabled(true);
  const first = FakeRecognition.last();
  controller.setEnabled(false);
  first.onerror?.({ error: 'network' });
  first.finish();
  assert.deepEqual([controller.getSnapshot().enabled, controller.getSnapshot().phase, controller.getSnapshot().error], [false, 'idle', null]);
});

test('새 세션에서는 이전 세션 마이크가 늦게 보낸 오류를 남기지 않는다', () => {
  const { controller } = setup([status('completed')], { recognition: deferredRecognition() });
  controller.setEnabled(true);
  const first = FakeRecognition.last();
  controller.setEnabled(false);
  controller.setContext({ sessionId: 'session-2', screenId: 'menu' });
  controller.setEnabled(true);
  first.onerror?.({ error: 'not-allowed' });
  assert.equal(controller.getSnapshot().error, null);
  first.finish();
  assert.equal(FakeRecognition.instances.length, 2);
  assert.deepEqual([controller.getSnapshot().phase, controller.getSnapshot().error], ['listening', null]);
  controller.dispose();
  FakeRecognition.last().finish();
});

test('대답을 기다리지 않을 때 한 글자이거나 신뢰도가 아주 낮은 인식은 서버로 보내지 않는다', async () => {
  const { calls, controller } = setup([status('completed')]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['네', 0.9]);
  controller.listen();
  FakeRecognition.last().final(['아메리카노 주세요', 0.1]);
  await tick(10);
  assert.deepEqual([calls.length, controller.getSnapshot().phase], [0, 'idle']);
  controller.listen();
  FakeRecognition.last().final(['아메리카노 주세요', 0]);  // 신뢰도 모름은 보낸다
  await tick(20);
  assert.equal(calls.length, 1);
});

test('처리 중에 음성 모드를 끄면 늦게 온 결과를 버린다', async () => {
  const { controller, delivered } = setup([status('processing'), status('needs_clarification', { reply_text: '어떤 메뉴를 주문할까요?' })]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['음료 하나', 0.9]);
  controller.setEnabled(false);
  await tick(20);
  const snapshot = controller.getSnapshot();
  assert.deepEqual([snapshot.enabled, snapshot.phase, snapshot.lastResult, delivered.length], [false, 'idle', null, 0]);
  assert.equal(FakeRecognition.instances.length, 1);
});

test('화면을 떠나 모드를 끄면 이전 질문을 지우고 다시 켤 때 새 문장으로 시작한다', async () => {
  const { controller, calls } = setup([
    status('needs_clarification', { reply_text: '온도를 골라 주세요.' }),
    status('completed'),
  ]);
  controller.setContext({ sessionId: 'session-1', screenId: 'menu_list' });
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 주세요', 0.9]);
  await tick(20);
  assert.equal(controller.getSnapshot().lastResult.reply_text, '온도를 골라 주세요.');
  assert.equal(controller.getSnapshot().phase, 'listening');

  controller.setEnabled(false);
  assert.deepEqual([controller.getSnapshot().enabled, controller.getSnapshot().phase, controller.getSnapshot().lastResult, controller.getSnapshot().lastTranscript], [false, 'idle', null, '']);
  controller.setContext({ sessionId: 'session-2', screenId: 'menu_list' });
  controller.setEnabled(true);
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  assert.equal(calls.length, 1, '이전 질문의 짧은 대답을 새 세션으로 보내지 않음');
  controller.listen();
  FakeRecognition.last().final(['핫 아메리카노 주세요', 0.9]);
  await tick(20);
  assert.deepEqual(calls.map(call => [call.sessionId, call.body.screen_id]), [
    ['session-1', 'menu_list'], ['session-2', 'menu_list'],
  ]);
});

test('인식기가 없거나 세션이 없으면 켜지 않고 이유를 남긴다', () => {
  const unsupported = new VoiceController({ api: createVoiceApi(), recognition: null });
  assert.equal(unsupported.setEnabled(true), false);
  assert.deepEqual([unsupported.getSnapshot().supported, unsupported.getSnapshot().enabled, unsupported.getSnapshot().error], [false, false, 'not_supported']);

  const noSession = new VoiceController({ api: createVoiceApi(), recognition: factory });
  assert.equal(noSession.setEnabled(true), false);
  assert.deepEqual([noSession.getSnapshot().enabled, noSession.getSnapshot().phase, noSession.getSnapshot().error], [true, 'idle', 'no_session']);
});

test('요청 실패와 해석 지연은 오류로 남기고 다시 듣지 않는다', async () => {
  const failed = setup([new ApiError(409, { code: 'request_in_progress' })]);
  failed.controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 주세요', 0.9]);
  await tick(20);
  assert.deepEqual([failed.controller.getSnapshot().phase, failed.controller.getSnapshot().error], ['idle', 'request_failed']);

  const slow = setup([status('processing')], { pollTimeoutMs: 10 });
  slow.controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 주세요', 0.9]);
  await tick(40);
  assert.deepEqual([slow.controller.getSnapshot().phase, slow.controller.getSnapshot().error], ['idle', 'timeout']);
});

test('주문을 마친 세션의 410은 따로 알리고 이전 질문의 대답 대기를 푼다', async () => {
  const { api, calls, controller } = setup([status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' })]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
  await tick(20);
  api.submit = async () => { throw new ApiError(410, { code: 'session_expired', detail: '새 이용 세션을 시작해 주세요.' }); };
  FakeRecognition.last().final(['네', 0.9]);
  await tick(20);
  const snapshot = controller.getSnapshot();
  assert.deepEqual([snapshot.phase, snapshot.error, snapshot.lastResult], ['idle', 'session_expired', null]);
  assert.equal(FakeRecognition.instances.length, 2, '끝난 세션에서는 마이크를 다시 열지 않음');
  assert.equal(calls.length, 1);
  controller.listen();
  FakeRecognition.last().final(['네', 0.9]);
  assert.equal(controller.getSnapshot().phase, 'idle', '대답 대기가 풀려 한 글자는 보내지 않고 거름');
});

test('음성 API는 같은 출처 경로와 중복 방지 키로 요청하고 오류 형식을 ApiError로 넘긴다', async () => {
  const requests = [];
  const api = createVoiceApi('/backend/', async (url, init) => {
    requests.push({ url, ...init });
    return url.endsWith('/requests')
      ? Response.json({ request_id: 'vr_1', status: 'accepted', accepted_at: '2026-10-13T00:00:00Z' }, { status: 202 })
      : Response.json({ code: 'voice_request_not_found', detail: '음성 요청을 찾을 수 없습니다.' }, { status: 404 });
  });
  const body = { text: '아메리카노', alternatives: [], screen_id: 'menu' };
  assert.equal((await api.submit('s 1', body, 'key-1')).request_id, 'vr_1');
  assert.equal(requests[0].url, '/backend/api/v1/sessions/s%201/voice/requests');
  assert.deepEqual([requests[0].method, requests[0].headers['Idempotency-Key'], JSON.parse(requests[0].body)], ['POST', 'key-1', body]);
  await assert.rejects(api.get('s 1', 'vr/1'), error => error instanceof ApiError && error.status === 404 && error.body.code === 'voice_request_not_found');
  assert.equal(requests[1].url, '/backend/api/v1/sessions/s%201/voice/requests/vr%2F1');
  assert.throws(() => api.submit('', body, 'key'), /세션 ID/);
  assert.throws(() => api.submit('s', body, ' '), /중복 방지 키/);
});
