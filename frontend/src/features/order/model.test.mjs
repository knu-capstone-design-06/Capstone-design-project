import assert from 'node:assert/strict';
import test from 'node:test';
import { categoryLabels, initialSettings, money, readSettings, temperatureLabel } from './model.ts';
import { ApiError } from '../../shared/api/client.ts';
import { OrderController } from './orderController.ts';
import { OrderResponseError, readOrderResponse } from './orderResponse.ts';

test('API 값과 화면 표시를 구분하고 푸드 온도는 null로 다룬다', () => {
  assert.equal(categoryLabels.coffee, '커피');
  assert.equal(categoryLabels.drink, '음료');
  assert.equal(categoryLabels.food, '푸드');
  assert.equal(temperatureLabel('iced'), '아이스');
  assert.equal(temperatureLabel('hot'), '핫');
  assert.equal(temperatureLabel(null), '기본');
  assert.equal(money(12500), '12,500원');
});
test('이전 저장 데이터에서는 화면 설정만 읽고 로컬 장바구니를 복원하지 않는다', () => {
  const legacy = { cart: [{ productId: 'latte', temperature: '핫', quantity: 3 }], settings: { ...initialSettings, largeText: true } };
  assert.deepEqual(readSettings(JSON.stringify(legacy)), legacy.settings);
  assert.deepEqual(readSettings(JSON.stringify(legacy.settings)), legacy.settings);
  assert.equal('cart' in readSettings(JSON.stringify(legacy)), false);
});
test('손상된 저장 설정과 boolean이 아닌 값은 기본 설정으로 처리한다', () => {
  assert.deepEqual(readSettings('{broken'), initialSettings);
  assert.deepEqual(readSettings(JSON.stringify({ largeText: 'false' })), initialSettings);
});

const emptyCart = (session = 'session-1') => ({ session_id: session, version: 0, currency: 'KRW', items: [], total_quantity: 0, total_amount: 0, updated_at: '2026-10-09T00:00:00Z' });
const populatedCart = (version = 1) => ({ ...emptyCart(), version,
  items: [{ item_id: 'item-1', product_id: 'americano', name: '아메리카노', temperature: 'iced', quantity: 2, unit_price: 3500, line_amount: 7000 }],
  total_quantity: 2, total_amount: 7000 });
const order = { order_id: 'order-1', order_number: 'A042', session_id: 'session-1', status: 'simulated', currency: 'KRW',
  items: populatedCart().items, total_quantity: 2, total_amount: 7000, created_at: '2026-10-09T00:01:00Z' };
function fixture(overrides = {}, onInvalidOrder) {
  let sessions = 0;
  const api = {
    getProducts: async () => ({ currency: 'KRW', products: [] }),
    createSession: async () => ({ session_id: `session-${++sessions}`, started_at: '2026-10-09T00:00:00Z' }),
    getCart: async session => emptyCart(session),
    ...overrides,
  };
  return new OrderController(api, onInvalidOrder);
}

test('초기화 중 중복 호출은 상품·세션 요청을 한 번만 실행한다', async () => {
  let calls = 0;
  const controller = fixture({ createSession: async () => { calls++; return { session_id: 'session-1', started_at: '' }; } });
  await Promise.all([controller.initialize(), controller.initialize()]);
  assert.equal(calls, 1);
  assert.equal(controller.getSnapshot().status, 'ready');
});

test('주문 API가 없는 서버에서는 연결 대기를 표시하고 로컬 상품·Cart로 대체하지 않는다', async () => {
  let sessions = 0;
  const controller = fixture({
    getProducts: async () => { throw new ApiError(404, { detail: 'Not Found' }); },
    createSession: async () => { sessions++; return { session_id: 'session-1', started_at: '' }; },
  });
  assert.equal(await controller.initialize(), false);
  assert.equal(controller.getSnapshot().status, 'disconnected');
  assert.match(controller.getSnapshot().message, /아직 준비되지/);
  assert.equal(controller.getSnapshot().cart, null);
  assert.deepEqual(controller.getSnapshot().products, []);
  assert.equal(sessions, 0);
});

test('추가 응답 전에는 기존 상태를 유지하고 처리 중 중복 클릭을 막는다', async () => {
  let finish, calls = 0;
  const controller = fixture({ addCartItem: () => { calls++; return new Promise(resolve => { finish = resolve; }); } });
  await controller.initialize();
  const first = controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 });
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
  assert.equal(controller.getSnapshot().status, 'saving');
  assert.equal(await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 }), false);
  finish(populatedCart());
  assert.equal(await first, true);
  assert.equal(controller.getSnapshot().cart.total_amount, 7000);
  assert.equal(calls, 1);
});

test('응답 유실 재시도는 같은 키·버전·본문을 유지하고 새 변경을 막는다', async () => {
  const requests = [];
  const controller = fixture({ addCartItem: async (...args) => {
    requests.push(structuredClone(args));
    if (requests.length === 1) throw new TypeError('response lost');
    return populatedCart();
  } });
  await controller.initialize();
  const input = { product_id: 'americano', temperature: 'iced', quantity: 2 };
  assert.equal(await controller.addItem(input), false);
  input.quantity = 10;
  assert.equal(controller.getSnapshot().status, 'uncertain');
  assert.equal(await controller.checkout(), false);
  assert.equal(await controller.addItem(input), false);
  assert.equal(await controller.retry(), true);
  assert.deepEqual(requests[0], requests[1]);
  assert.equal(controller.getSnapshot().cart.total_quantity, 2);
});

test('버전 충돌은 최신 Cart를 표시하고 사용자 재조작에 새 키를 쓴다', async () => {
  const requests = [], latest = populatedCart(5);
  const controller = fixture({ getCart: async () => populatedCart(1), updateCartItem: async (...args) => {
    requests.push(args);
    if (requests.length === 1) throw new ApiError(409, { code: 'cart_version_conflict', detail: '최신 내용을 확인해주세요.', cart: latest });
    return { ...latest, version: 6 };
  } });
  await controller.initialize();
  assert.equal(await controller.updateQuantity('item-1', 3), false);
  assert.equal(requests.length, 1);
  assert.equal(controller.getSnapshot().cart.version, 5);
  assert.equal(await controller.retry(), false);
  assert.equal(await controller.updateQuantity('item-1', 3), true);
  assert.equal(requests[1][2].expected_version, 5);
  assert.notEqual(requests[0][3], requests[1][3]);
});

test('낮은 버전 응답으로 현재 Cart를 덮어쓰지 않는다', async () => {
  const controller = fixture({ getCart: async () => populatedCart(5), updateCartItem: async () => populatedCart(2) });
  await controller.initialize();
  await controller.updateQuantity('item-1', 3);
  assert.equal(controller.getSnapshot().cart.version, 5);
});

test('처리 중 응답의 재시도 간격을 존중하고 그동안 새 키를 만들지 않는다', async () => {
  let calls = 0;
  const controller = fixture({ addCartItem: async () => {
    calls++;
    // 처리 중 오류 코드는 미정입니다. 서버가 제공한 Retry-After를 사용합니다.
    throw new ApiError(409, { code: 'pending_example', detail: '처리 중', cart: null }, 0.02);
  } });
  await controller.initialize();
  await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 1 });
  assert.equal(await controller.retry(), false);
  assert.equal(calls, 1);
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(controller.getSnapshot().retryAt, 0);
});

test('주문 실패는 Cart를 유지하고 응답 유실 재확인으로 서버 주문번호를 표시한다', async () => {
  const requests = [];
  const controller = fixture({ getCart: async session => session === 'session-1' ? populatedCart() : emptyCart(session), createOrder: async (...args) => {
    requests.push(args);
    if (requests.length === 1) throw new ApiError(409, { code: 'product_unavailable', detail: '품절', cart: null });
    if (requests.length === 2) throw new TypeError('response lost');
    return order;
  } });
  await controller.initialize();
  assert.equal(await controller.checkout(), false);
  assert.equal(controller.getSnapshot().cart.total_amount, 7000);
  assert.equal(controller.getSnapshot().order, null);
  assert.equal(await controller.checkout(), false);
  assert.equal(await controller.retry(), true);
  assert.deepEqual(requests[1], requests[2]);
  assert.equal(controller.getSnapshot().order.order_number, 'A042');
  assert.equal(await controller.checkout(), false);
  assert.equal(await controller.startNewOrder(), true);
  assert.equal(controller.getSnapshot().session.session_id, 'session-2');
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
});

test('세션 소실은 새 이용 시작을 안내하고 로컬 Cart로 복구하지 않는다', async () => {
  const controller = fixture({ getCart: async session => session === 'session-1' ? populatedCart() : emptyCart(session),
    updateCartItem: async () => { throw new ApiError(404, { code: 'session_not_found', detail: '새로 시작해주세요.', cart: null }); } });
  await controller.initialize();
  await controller.updateQuantity('item-1', 3);
  assert.equal(controller.getSnapshot().status, 'ended');
  assert.equal(await controller.startNewOrder(), true);
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
});

test('코드 없는 404·410과 접근 오류 뒤에는 새 서버 세션으로 시작할 수 있다', async () => {
  for (const status of [404, 410, 401, 403]) {
    const controller = fixture({ getCart: async session => session === 'session-1' ? populatedCart() : emptyCart(session),
      updateCartItem: async () => { throw new ApiError(status, { detail: 'session not found' }); } });
    await controller.initialize();
    assert.equal(await controller.updateQuantity('item-1', 3), false);
    assert.equal(controller.getSnapshot().status, 'ended', `HTTP ${status}`);
    assert.equal(await controller.startNewOrder(), true);
    assert.equal(controller.getSnapshot().session.session_id, 'session-2');
    assert.equal(controller.getSnapshot().cart.total_quantity, 0);
  }
});

test('상품·장바구니 항목 없음 404는 현재 세션과 장바구니를 유지한다', async () => {
  for (const code of ['product_not_found', 'cart_item_not_found']) {
    const controller = fixture({ getCart: async () => populatedCart(),
      updateCartItem: async () => { throw new ApiError(404, { code, detail: '항목을 찾을 수 없습니다.', cart: null }); } });
    await controller.initialize();
    await controller.updateQuantity('item-1', 3);
    assert.equal(controller.getSnapshot().status, 'ready', code);
    assert.equal(controller.getSnapshot().session.session_id, 'session-1');
    assert.equal(controller.getSnapshot().cart.total_quantity, 2);
    assert.equal(await controller.startNewOrder(), false);
  }
});

test('재확인 실패 뒤에만 대기 요청을 버리고 새 주문을 시작할 수 있다', async () => {
  const requests = [];
  let failRetry;
  const controller = fixture({ getCart: async session => session === 'session-1' ? populatedCart() : emptyCart(session),
    createOrder: (...args) => {
      requests.push(structuredClone(args));
      return requests.length === 1 ? Promise.reject(new TypeError('response lost'))
        : new Promise((resolve, reject) => { failRetry = reject; });
    } });
  await controller.initialize();
  assert.equal(await controller.checkout(), false);
  assert.equal(controller.getSnapshot().canAbandonPending, false);
  assert.equal(controller.abandonPending(), false);
  const retry = controller.retry();
  assert.equal(controller.getSnapshot().status, 'saving');
  assert.equal(controller.abandonPending(), false, '처리 중인 요청은 버리지 않음');
  assert.equal(await controller.startNewOrder(), false);
  failRetry(new ApiError(503, { detail: '처리 결과를 확인할 수 없습니다.' }, 0.02));
  assert.equal(await retry, false);
  assert.deepEqual(requests[0], requests[1], '재확인은 같은 키·버전·본문');
  assert.equal(controller.getSnapshot().canAbandonPending, true);
  assert.match(controller.getSnapshot().abandonWarning, /이전 샘플 주문은 자동으로 취소되지/);
  assert.equal(controller.getSnapshot().cart.total_amount, 7000);
  assert.equal(controller.abandonPending(), true);
  assert.equal(controller.getSnapshot().status, 'ended');
  assert.equal(controller.getSnapshot().retryAt, 0);
  assert.equal(controller.getSnapshot().canAbandonPending, false);
  assert.equal(await controller.retry(), false);
  assert.equal(await controller.startNewOrder(), true);
  assert.equal(controller.getSnapshot().session.session_id, 'session-2');
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
  assert.equal(controller.getSnapshot().order, null);
  assert.equal(requests.length, 2, '이전 요청을 새 세션에서 다시 실행하지 않음');
});

test('불완전한 주문 성공 응답은 Cart와 정확한 요청을 유지하고 유효한 재확인 후에만 완료한다', async () => {
  const invalid = [null, [], { session_id: 'session-1' }];
  for (const field of Object.keys(order)) {
    const missing = structuredClone(order);
    delete missing[field];
    invalid.push(missing);
  }
  for (const patch of [
    { order_id: '' }, { order_number: 42 }, { status: 'paid' }, { currency: 'USD' }, { items: [] },
    { total_quantity: 1.5 }, { total_amount: -1 }, { total_amount: 100 }, { created_at: 'yesterday' },
    { created_at: '2026-10-09' }, { items: [{ ...order.items[0], quantity: 21 }] },
    { items: [{ ...order.items[0], temperature: 'warm' }] },
    { items: [{ ...order.items[0], line_amount: '7000' }] },
  ]) invalid.push({ ...structuredClone(order), ...patch });
  for (const field of Object.keys(order.items[0])) {
    const broken = structuredClone(order);
    delete broken.items[0][field];
    invalid.push(broken);
  }
  for (const response of invalid) {
    const requests = [];
    const diagnostics = [];
    const controller = fixture({ getCart: async () => populatedCart(), createOrder: async (...args) => {
      requests.push(structuredClone(args));
      return requests.length === 1 ? response : structuredClone(order);
    } }, fields => diagnostics.push([...fields]));
    await controller.initialize();
    assert.equal(await controller.checkout(), false, JSON.stringify(response));
    assert.equal(controller.getSnapshot().status, 'uncertain');
    assert.equal(diagnostics.length, 1);
    assert(diagnostics[0].length > 0);
    assert.equal(controller.getSnapshot().order, null);
    assert.deepEqual(controller.getSnapshot().cart, populatedCart());
    assert.equal(await controller.checkout(), false);
    assert.equal(await controller.retry(), true);
    assert.deepEqual(requests[0], requests[1]);
    assert.equal(controller.getSnapshot().order.order_number, 'A042');
    assert.equal(controller.getSnapshot().cart, null);
  }
});

test('주문 응답 진단은 잘못된 필드 경로만 제공하고 응답 값은 보관하지 않는다', () => {
  const broken = structuredClone(order);
  broken.items[0].temperature = 'private-value';
  broken.total_amount = 99;
  assert.throws(() => readOrderResponse(broken), error => {
    assert(error instanceof OrderResponseError);
    assert.deepEqual(error.fields, ['items[0].temperature']);
    assert.equal('body' in error, false);
    assert(!JSON.stringify(error).includes('private-value'));
    return true;
  });
  assert.throws(() => readOrderResponse({ ...order, total_amount: 99 }), error => {
    assert.deepEqual(error.fields, ['total_amount']);
    return true;
  });
});

test('장바구니 변경 재확인과 새 시작은 주문 취소 안내를 표시하지 않는다', async () => {
  const controller = fixture({ addCartItem: async () => { throw new TypeError('response lost'); } });
  await controller.initialize();
  await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 1 });
  await controller.retry();
  assert.match(controller.getSnapshot().message, /메뉴 변경/);
  assert.match(controller.getSnapshot().abandonWarning, /새 장바구니/);
  assert.doesNotMatch(controller.getSnapshot().abandonWarning, /주문은 자동으로 취소/);
  assert(controller.abandonPending());
  assert.match(controller.getSnapshot().message, /이전 메뉴 변경/);
});

test('Cart 조회가 실패해도 받은 서버 세션을 기록하고 재연결은 새 세션으로 시도한다', async () => {
  let carts = 0;
  const controller = fixture({ getCart: async session => {
    if (++carts === 1) throw new ApiError(503, { detail: '연결 대기' });
    return emptyCart(session);
  } });
  await controller.initialize();
  assert.equal(controller.getSnapshot().status, 'disconnected');
  assert.equal(controller.getSnapshot().session.session_id, 'session-1');
  assert.equal(controller.getSnapshot().cart, null);
  assert.equal(await controller.initialize(), true);
  assert.equal(controller.getSnapshot().session.session_id, 'session-2');
  assert.equal(controller.getSnapshot().status, 'ready');
});
