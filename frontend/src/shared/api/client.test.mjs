import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError, createBackendApi } from './client.ts';

test('명세의 경로, HTTP 메서드와 본문으로 backend만 호출한다', async () => {
  const calls = [];
  const results = [
    { status: 'ok', service: 'backend' },
    { backend: 'ok', ai_server: 'unreachable' },
    { session_id: 'session-1', started_at: '2026-10-01T10:00:00Z' },
    { session_id: 'session-1', ai_available: false, states: null,
      support: { preset: 'none', requires_confirmation: false, decided_by: 'rule_placeholder' } },
  ];
  const api = createBackendApi('http://localhost:8000/', async (url, init) => {
    calls.push({ url, ...init });
    return Response.json(results[calls.length - 1], { status: calls.length === 3 ? 201 : 200 });
  });
  assert.deepEqual(await api.getBackendHealth(), results[0]);
  assert.deepEqual(await api.getConnectivity(), results[1]);
  assert.deepEqual(await api.createSession(), results[2]);
  const features = {
    screen_id: 'menu_list', window_start: '2026-10-01T10:00:00Z',
    window_end: '2026-10-01T10:00:03Z',
    touch: { tap_count: 6, miss_tap_count: 3, repeat_tap_count: 2, back_count: 0, dwell_ms: 3000 },
    vision: null,
  };
  const controller = new AbortController();
  assert.deepEqual(await api.sendFeatureWindow('session/1', features, controller.signal), results[3]);
  assert.deepEqual(calls.map(({ url, method }) => [url, method]), [
    ['http://localhost:8000/health', 'GET'],
    ['http://localhost:8000/api/v1/connectivity', 'GET'],
    ['http://localhost:8000/api/v1/sessions', 'POST'],
    ['http://localhost:8000/api/v1/sessions/session%2F1/features', 'POST'],
  ]);
  assert.equal(calls[2].body, undefined);
  assert.deepEqual(JSON.parse(calls[3].body), features);
  assert.equal(calls[3].headers['Content-Type'], 'application/json');
  assert.equal(calls[3].signal, controller.signal);
});

test('404 및 형식이 확정되지 않은 422 응답을 보존한다', async () => {
  for (const [status, body] of [[404, { detail: 'session not found' }], [422, { detail: [{ msg: 'invalid' }] }]]) {
    const api = createBackendApi('', async () => Response.json(body, { status }));
    await assert.rejects(api.getBackendHealth(), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, status);
      assert.deepEqual(error.body, body);
      return true;
    });
  }
});

test('비 JSON 오류와 잘못된 성공 응답을 처리한다', async () => {
  const api = createBackendApi('', async () => new Response('Bad Gateway', { status: 502 }));
  await assert.rejects(api.getBackendHealth(), (error) => error.status === 502 && error.body === 'Bad Gateway');
  const malformed = createBackendApi('', async () => new Response('invalid'));
  await assert.rejects(malformed.getBackendHealth(), /JSON/);
});

test('네트워크 오류와 취소를 호출자에게 전달하며 자동 재시도하지 않는다', async () => {
  for (const error of [new TypeError('offline'), new DOMException('Aborted', 'AbortError')]) {
    let calls = 0;
    const api = createBackendApi('', async () => { calls++; throw error; });
    await assert.rejects(api.createSession(), (caught) => caught === error);
    assert.equal(calls, 1);
  }
});

test('빈 세션 ID를 서버로 보내지 않는다', () => {
  const api = createBackendApi('', async () => { assert.fail('호출되면 안 됨'); });
  assert.throws(() => api.sendFeatureWindow(' ', {}), /세션 ID/);
});

test('상품·Cart·주문 API의 경로·본문·중복 키와 같은 출처 쿠키를 사용한다', async () => {
  const calls = [], key = 'fcf3640b-d36f-4cf4-8ab0-93ce1a0867c5';
  const api = createBackendApi('/backend', async (url, init) => { calls.push({ url, ...init }); return Response.json({}); });
  await api.getProducts();
  await api.getCart('session/1');
  await api.addCartItem('session/1', { product_id: 'americano', temperature: 'iced', quantity: 2, expected_version: 0 }, key);
  await api.updateCartItem('session/1', 'item/1', { quantity: 3, expected_version: 1 }, key);
  await api.deleteCartItem('session/1', 'item/1', 2, key);
  await api.createOrder('session/1', { expected_version: 3 }, key);
  assert.deepEqual(calls.map(call => [call.method, call.url]), [
    ['GET', '/backend/api/v1/products'], ['GET', '/backend/api/v1/sessions/session%2F1/cart'],
    ['POST', '/backend/api/v1/sessions/session%2F1/cart/items'],
    ['PATCH', '/backend/api/v1/sessions/session%2F1/cart/items/item%2F1'],
    ['DELETE', '/backend/api/v1/sessions/session%2F1/cart/items/item%2F1?expected_version=2'],
    ['POST', '/backend/api/v1/sessions/session%2F1/orders'],
  ]);
  assert(calls.every(call => call.credentials === 'same-origin'));
  assert(calls.slice(2).every(call => call.headers['Idempotency-Key'] === key));
  assert.equal(calls[4].body, undefined);
  assert.equal(calls[4].headers['Content-Type'], undefined);
  assert.deepEqual(JSON.parse(calls[5].body), { expected_version: 3 });
});

test('처리 중 중복의 오류 본문과 Retry-After를 보존한다', async () => {
  // 처리 중 오류 코드는 합의 전이며 클라이언트는 서버 본문과 간격을 보존합니다.
  const body = { code: 'pending_example', detail: '처리 중', cart: null };
  const api = createBackendApi('', async () => Response.json(body, { status: 409, headers: { 'Retry-After': '1' } }));
  await assert.rejects(api.createOrder('session-1', { expected_version: 1 }, 'key'), error => {
    assert.equal(error.status, 409);
    assert.equal(error.retryAfterSeconds, 1);
    assert.deepEqual(error.body, body);
    return true;
  });
});
