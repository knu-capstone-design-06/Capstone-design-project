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
  assert.deepEqual(delivered.map(result => result.tool_calls), [[addAmericano]]);
  assert.equal(FakeRecognition.instances.length, 1);
});

test('확인·질문 결과에는 대답을 듣기 위해 마이크를 다시 연다', async () => {
  const { controller } = setup([status('needs_confirmation', { tool_calls: [addAmericano], reply_text: '아이스 아메리카노 2잔 담을까요?' })]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['아메리카노 두 잔', 0.5]);
  await tick(20);
  assert.equal(controller.getSnapshot().lastResult.reply_text, '아이스 아메리카노 2잔 담을까요?');
  assert.equal(controller.getSnapshot().phase, 'listening');
  assert.equal(FakeRecognition.instances.length, 2);
});

test('키오스크에게 한 말이 아니면(ignored) 화면 문구 없이 닫는다', async () => {
  const { controller, delivered } = setup([status('ignored')]);
  controller.setEnabled(true);
  FakeRecognition.last().final(['너 뭐 먹을래', 0.8]);
  await tick(20);
  assert.deepEqual([controller.getSnapshot().phase, controller.getSnapshot().lastResult.reply_text], ['idle', null]);
  assert.equal(delivered[0].status, 'ignored');
  assert.equal(FakeRecognition.instances.length, 1);
});

test('한 글자이거나 신뢰도가 아주 낮은 인식은 서버로 보내지 않는다', async () => {
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
