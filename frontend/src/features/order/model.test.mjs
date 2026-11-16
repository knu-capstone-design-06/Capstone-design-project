import assert from 'node:assert/strict';
import test from 'node:test';
import { categoryLabels, initialSettings, money, orderNumberText, readSettings, temperatureLabel, temperatureText } from './model.ts';
import { ApiError } from '../../shared/api/client.ts';
import { OrderController } from './orderController.ts';
import { OrderResponseError, readOrderResponse } from './orderResponse.ts';
import { clampPage, menuColumns, menuPageSize, pageCount, pageItems, reviewPageSize } from './utils/paging.ts';
import { alreadyLarge, readSupportDecision } from './utils/supportDecision.ts';

test('API 값과 화면 표시를 구분하고 푸드 온도는 null로 다룬다', () => {
  assert.equal(categoryLabels.coffee, '커피');
  assert.equal(categoryLabels.drink, '음료');
  assert.equal(categoryLabels.food, '푸드');
  assert.equal(temperatureLabel('iced'), '아이스');
  assert.equal(temperatureLabel('hot'), '핫');
  assert.equal(temperatureLabel(null), '기본');
  assert.equal(money(12500), '12,500원');
});
test('고객 화면의 온도 이름은 아이스·핫이고 푸드에는 온도를 쓰지 않는다', () => {
  assert.equal(temperatureText('iced'), '아이스');
  assert.equal(temperatureText('hot'), '핫');
  // 개발 샘플과 서버 주문번호 모두 원래 값을 보여 모의 번호의 접두사를 숨기지 않습니다.
  assert.equal(orderNumberText('DEV-SAMPLE-001'), 'DEV-SAMPLE-001');
  assert.equal(orderNumberText('DEMO-042'), 'DEMO-042');
  assert.equal(orderNumberText('A001'), 'A001');
  assert.equal(temperatureText(null), '');
  assert.equal(temperatureLabel('iced'), '아이스');
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

test('낮은 화면 설정을 복원하고 이전 저장 형식에서는 기본 높이를 사용한다', () => {
  const oldSettings = { largeText: true, largeButton: false, simpleScreen: false, stepGuide: true };
  assert.deepEqual(readSettings(JSON.stringify(oldSettings)), { ...oldSettings, lowScreen: false, highContrast: false });
  assert.deepEqual(readSettings(JSON.stringify({ ...oldSettings, lowScreen: true })), { ...oldSettings, lowScreen: true, highContrast: false });
  assert.deepEqual(readSettings(JSON.stringify({ ...oldSettings, lowScreen: 'true' })), { ...oldSettings, lowScreen: false, highContrast: false });
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

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('초기화 중 중복 호출은 상품·세션 요청을 한 번만 실행한다', async () => {
  let calls = 0;
  const controller = fixture({ createSession: async () => { calls++; return { session_id: 'session-1', started_at: '' }; } });
  await Promise.all([controller.initialize(), controller.initialize()]);
  assert.equal(calls, 1);
  assert.equal(controller.getSnapshot().status, 'ready');
});

test('확인한 처음으로 동작은 새 서버 세션을 만들고 미확정 요청은 버리지 않는다', async () => {
  const controller = fixture();
  await controller.initialize();
  const previous = controller.getSnapshot().session.session_id;
  assert.equal(await controller.restartCurrentOrder(), true);
  assert.notEqual(controller.getSnapshot().session.session_id, previous);
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
  const uncertain = fixture({ addCartItem: async () => { throw new TypeError('response lost'); } });
  await uncertain.initialize();
  await uncertain.addItem({ product_id: 'americano', temperature: 'iced', quantity: 1 });
  const session = uncertain.getSnapshot().session.session_id;
  assert.equal(await uncertain.restartCurrentOrder(), false);
  assert.equal(uncertain.getSnapshot().session.session_id, session);
  assert.equal(uncertain.getSnapshot().status, 'uncertain');
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

test('음성 장바구니 변경 뒤에는 최신 Cart를 다시 읽고, 실패해도 이전 Cart를 보존한다', async () => {
  let reads = 0;
  const latest = { ...populatedCart(3), items: [{ ...populatedCart().items[0], quantity: 3, line_amount: 10500 }], total_quantity: 3, total_amount: 10500 };
  const controller = fixture({ getCart: async () => {
    reads += 1;
    if (reads === 1) return populatedCart(1);
    if (reads === 2) return latest;
    throw new ApiError(503, { detail: 'temporary failure' });
  } });
  await controller.initialize();
  assert.equal(await controller.refreshCartAfterVoice(), true);
  assert.equal(controller.getSnapshot().cart.total_quantity, 3);
  assert.match(controller.getSnapshot().notice, /음성 주문/);
  assert.equal(await controller.refreshCartAfterVoice(), false);
  assert.equal(controller.getSnapshot().status, 'ready');
  assert.equal(controller.getSnapshot().cart.total_quantity, 3);
  assert.match(controller.getSnapshot().message, /음성 주문 결과/);
});

test('터치 응답보다 먼저 온 음성 변경은 저장 뒤 한 번 조회하고 다음 변경에 최신 버전을 쓴다', async () => {
  const touch = deferred(), refresh = deferred();
  let reads = 0, nextVersion;
  const controller = fixture({
    getCart: () => ++reads === 1 ? Promise.resolve(emptyCart()) : refresh.promise,
    addCartItem: () => touch.promise,
    updateCartItem: async (_session, _item, input) => { nextVersion = input.expected_version; return populatedCart(3); },
  });
  await controller.initialize();
  const writing = controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 });
  await controller.refreshCartAfterVoice();
  await controller.refreshCartAfterVoice();
  assert.equal(reads, 1, '터치 저장 중에는 재조회를 보류');
  touch.resolve(populatedCart(1));
  assert.equal(await writing, true);
  assert.equal(reads, 2, '저장 중의 알림들을 한 번의 조회로 처리');
  assert.equal(controller.getSnapshot().status, 'saving');
  assert.equal(await controller.updateQuantity('item-1', 3), false, '재조회가 끝나기 전에는 추가 변경 차단');
  refresh.resolve(populatedCart(2));
  await refresh.promise;
  assert.equal(controller.getSnapshot().status, 'ready');
  assert.equal(controller.getSnapshot().cart.version, 2);
  assert.equal(await controller.updateQuantity('item-1', 3), true);
  assert.equal(nextVersion, 2);
});

test('음성 재조회 도중 새 변경이 오면 현재 조회 뒤 한 번 더 조회하고 중간에 조작을 열지 않는다', async () => {
  const first = deferred(), second = deferred();
  let reads = 0;
  const controller = fixture({ getCart: () => {
    reads++;
    return reads === 1 ? Promise.resolve(populatedCart(1)) : reads === 2 ? first.promise : second.promise;
  } });
  await controller.initialize();
  const snapshots = [];
  controller.subscribe(() => snapshots.push(controller.getSnapshot()));
  const refreshing = controller.refreshCartAfterVoice();
  await controller.refreshCartAfterVoice();
  await controller.refreshCartAfterVoice();
  assert.equal(reads, 2);
  first.resolve(populatedCart(2));
  await refreshing;
  assert.equal(reads, 3);
  assert.equal(controller.getSnapshot().status, 'saving');
  assert(!snapshots.some(snapshot => snapshot.status === 'ready'), '중간 응답으로 조작을 재개하지 않음');
  second.resolve(populatedCart(3));
  await second.promise;
  assert.equal(controller.getSnapshot().status, 'ready');
  assert.equal(controller.getSnapshot().cart.version, 3);
});

test('응답 유실 중 음성 변경은 동일 요청 재확인이 끝난 뒤 조회한다', async () => {
  const requests = [], refresh = deferred();
  let reads = 0;
  const controller = fixture({
    getCart: () => ++reads === 1 ? Promise.resolve(emptyCart()) : refresh.promise,
    addCartItem: async (...args) => {
      requests.push(structuredClone(args));
      if (requests.length === 1) throw new TypeError('response lost');
      return populatedCart(1);
    },
  });
  await controller.initialize();
  await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 });
  await controller.refreshCartAfterVoice();
  assert.equal(controller.getSnapshot().status, 'uncertain');
  assert.equal(reads, 1, '음성 조회로 미확정 요청을 버리지 않음');
  assert.equal(await controller.retry(), true);
  assert.deepEqual(requests[0], requests[1]);
  assert.equal(reads, 2);
  refresh.resolve(populatedCart(2));
  await refresh.promise;
  assert.equal(controller.getSnapshot().cart.version, 2);
});

test('터치 요청이 확정 오류로 끝나도 보류한 음성 변경은 조회한다', async () => {
  const touch = deferred(), refresh = deferred();
  let reads = 0;
  const controller = fixture({
    getCart: () => ++reads === 1 ? Promise.resolve(populatedCart(1)) : refresh.promise,
    updateCartItem: () => touch.promise,
  });
  await controller.initialize();
  const writing = controller.updateQuantity('item-1', 3);
  await controller.refreshCartAfterVoice();
  touch.reject(new ApiError(409, { code: 'cart_version_conflict', detail: '최신 내용을 확인해주세요.', cart: populatedCart(2) }));
  assert.equal(await writing, false);
  assert.equal(reads, 2);
  refresh.resolve(populatedCart(3));
  await refresh.promise;
  assert.equal(controller.getSnapshot().cart.version, 3);
});

test('세션이 끝나면 보류한 음성 조회를 버리고 새 주문에 가져가지 않는다', async () => {
  const touch = deferred(), sessions = [];
  const controller = fixture({
    getCart: async session => { sessions.push(session); return session === 'session-1' ? populatedCart(1) : emptyCart(session); },
    updateCartItem: () => touch.promise,
  });
  await controller.initialize();
  const writing = controller.updateQuantity('item-1', 3);
  await controller.refreshCartAfterVoice();
  touch.reject(new ApiError(410, { code: 'session_expired', detail: '새로 시작해주세요.', cart: null }));
  await writing;
  assert.equal(controller.getSnapshot().status, 'ended');
  assert.deepEqual(sessions, ['session-1']);
  assert.equal(await controller.startNewOrder(), true);
  assert.deepEqual(sessions, ['session-1', 'session-2']);
  assert.equal(controller.getSnapshot().cart.session_id, 'session-2');
});

test('주문 완료로 확정되면 보류한 음성 조회가 완료 Cart를 다시 읽지 않는다', async () => {
  const checkout = deferred(), sessions = [];
  const controller = fixture({
    getCart: async session => { sessions.push(session); return session === 'session-1' ? populatedCart(1) : emptyCart(session); },
    createOrder: () => checkout.promise,
  });
  await controller.initialize();
  const writing = controller.checkout();
  await controller.refreshCartAfterVoice();
  checkout.resolve(structuredClone(order));
  assert.equal(await writing, true);
  assert.equal(controller.getSnapshot().order.order_id, order.order_id);
  assert.equal(controller.getSnapshot().cart, null);
  assert.deepEqual(sessions, ['session-1']);
  assert.equal(await controller.startNewOrder(), true);
  assert.deepEqual(sessions, ['session-1', 'session-2']);
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
  assert.match(controller.getSnapshot().abandonWarning, /이전 주문은 자동으로 취소되지/);
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

test('메뉴는 화면 설정에 맞는 수로 쪽을 나누고 범위를 벗어난 쪽을 마지막 쪽으로 되돌린다', () => {
  const mode = (settings = {}) => ({ largeText: false, largeButton: false, lowScreen: false, simpleScreen: false, ...settings });
  assert.equal(menuPageSize(mode()), 9, '기본: 사진 카드 3 × 3, 17개 메뉴는 2쪽');
  assert.equal(menuPageSize(mode({ largeButton: true })), 9);
  assert.equal(menuPageSize(mode({ stepGuide: true })), 6, '단계별 안내 줄이 서면 한 줄 줄어듦');
  assert.equal(menuPageSize(mode({ largeText: true })), 4, '큰 글씨: 사진 카드 2 × 2, 17개 메뉴는 5쪽');
  assert.equal(menuColumns(mode({ largeText: true })), 2);
  assert.equal(menuPageSize(mode({ largeText: true, stepGuide: true })), 2, '큰 글씨 + 단계별 안내: 사진 카드 한 줄');
  assert.equal(menuPageSize(mode({ largeText: true, voiceOn: true })), 2, '큰 글씨 + 말로 주문: 사진 카드 한 줄');
  assert.equal(menuPageSize(mode({ largeText: true, simpleScreen: true, stepGuide: true })), 4, '큰 글씨 + 간편 화면: 글자 줄 4개');
  assert.equal(menuColumns(mode({ largeText: true, simpleScreen: true })), 1);
  assert.equal(menuPageSize(mode({ lowScreen: true })), 6);
  assert.equal(menuPageSize(mode({ lowScreen: true, stepGuide: true })), 3);
  assert.equal(menuPageSize(mode({ lowScreen: true, largeText: true })), 2);
  assert.equal(menuPageSize(mode({ simpleScreen: true })), 10);
  assert.equal(menuPageSize(mode({ simpleScreen: true, largeButton: true, lowScreen: true, stepGuide: true })), 5);
  assert.equal(menuPageSize(mode({ voiceOn: true })), 6, '말로 주문: 사진 카드 2 × 3');
  assert.equal(menuPageSize(mode({ voiceOn: true, stepGuide: true })), 6, '말로 주문 중에는 단계별 안내가 없음');
  assert.equal(menuPageSize(mode({ voiceOn: true, largeButton: true })), 3);
  assert.equal(menuPageSize(mode({ voiceOn: true, simpleScreen: true })), 5, '말로 주문 + 간편 화면: 글자 줄 5개(담은 메뉴 위 32 px를 지킴)');
  assert.equal(menuPageSize(mode({ largeView: true })), 6, '크게 보기: 세 열 두 줄, 17개 메뉴는 3쪽');
  assert.equal(menuPageSize(mode({ largeView: true, lowScreen: true })), 3, '낮은 화면 + 크게 보기: 세 열 한 줄');
  const products = Array.from({ length: 17 }, (_, index) => index);
  assert.equal(pageCount(products.length, 6), 3);
  assert.deepEqual([0, 1, 2].map(page => pageItems(products, page, 6).length), [6, 6, 5]);
  assert.equal(pageCount(0, 6), 1, '빈 목록도 한 쪽');
  assert.equal(clampPage(5, products.length, 6), 2);
  assert.equal(clampPage(-1, products.length, 6), 0);
  assert.deepEqual(pageItems(products, 9, 6), [12, 13, 14, 15, 16]);
});

test('주문 확인은 화면 설정과 줄 수에 맞춰 쪽을 나눈다', () => {
  const mode = (settings = {}) => ({ largeText: false, largeButton: false, lowScreen: false, simpleScreen: false, ...settings });
  assert.equal(reviewPageSize(mode(), 0), 1, '빈 주문도 한 줄 자리');
  assert.equal(reviewPageSize(mode(), 4), 4);
  assert.equal(reviewPageSize(mode(), 7), 5, '기본 크기는 다섯 줄까지');
  assert.equal(reviewPageSize(mode({ largeButton: true }), 7), 5);
  assert.equal(reviewPageSize(mode({ largeText: true }), 3), 3);
  assert.equal(reviewPageSize(mode({ largeText: true }), 4), 2);
  assert.equal(reviewPageSize(mode({ lowScreen: true }), 3), 3);
  assert.equal(reviewPageSize(mode({ lowScreen: true }), 4), 2);
  assert.equal(reviewPageSize(mode({ lowScreen: true, largeButton: true }), 3), 2);
  assert.equal(reviewPageSize(mode({ lowScreen: true, largeText: true }), 3), 1);
  assert.equal(pageCount(17, reviewPageSize(mode(), 17)), 4);
});

test('화면 지원 판단은 계약의 필드만 읽고 늦거나 쓸 수 없는 응답은 무시한다', () => {
  const response = (preset, requires_confirmation = true, extra = {}) => ({ session_id: 's1', ai_available: true, support: { preset, requires_confirmation, decided_by: 'rule_placeholder' }, ...extra });
  const sent = { sessionId: 's1', screen: 'menu' };
  const now = (extra = {}) => ({ sessionId: 's1', screen: 'menu', orderDone: false, settings: { ...initialSettings }, largeView: false, ...extra });
  assert.deepEqual(readSupportDecision(response('none'), sent, now()), { kind: 'ignore', reason: 'none' });
  assert.deepEqual(readSupportDecision(response('large_text', true, { ai_available: false }), sent, now()), { kind: 'ignore', reason: 'ai_unavailable' });
  assert.deepEqual(readSupportDecision(response('large_text'), sent, now({ sessionId: 's2' })), { kind: 'ignore', reason: 'stale_session' });
  assert.deepEqual(readSupportDecision(response('large_text', true, { session_id: 'other' }), sent, now()), { kind: 'ignore', reason: 'stale_session' });
  assert.deepEqual(readSupportDecision(response('large_text'), sent, now({ screen: 'review' })), { kind: 'ignore', reason: 'stale_screen' });
  assert.deepEqual(readSupportDecision(response('large_text'), sent, now({ orderDone: true })), { kind: 'ignore', reason: 'order_done' });
  // 크게 보기: 이미 켜져 있거나 고객이 큰 글씨(200 %)를 켰으면 제안하지 않습니다. 큰 버튼만 켜져 있으면 제안합니다.
  assert.deepEqual(readSupportDecision(response('large_text'), sent, now({ largeView: true })), { kind: 'ignore', reason: 'already_on' });
  assert.deepEqual(readSupportDecision(response('large_button'), sent, now({ settings: { ...initialSettings, largeText: true } })), { kind: 'ignore', reason: 'already_on' });
  assert.deepEqual(readSupportDecision(response('large_button'), sent, now({ settings: { ...initialSettings, largeButton: true } })), { kind: 'offer', preset: 'large_button', support: 'enlarge' });
  for (const preset of ['simple_screen', 'step_guide', 'voice_guide']) assert.deepEqual(readSupportDecision(response(preset), sent, now()), { kind: 'ignore', reason: 'no_copy' });
  assert.deepEqual(readSupportDecision(response('large_text', true), sent, now()), { kind: 'offer', preset: 'large_text', support: 'enlarge' });
  assert.deepEqual(readSupportDecision(response('large_button', false), sent, now()), { kind: 'apply', preset: 'large_button', support: 'enlarge' });
});

test('크게 보기는 화면 설정과 따로인 한 단계이고, 큰 글씨(200 %)가 켜져 있으면 더 키우지 않는다', () => {
  assert.equal(alreadyLarge({ largeView: false, settings: { ...initialSettings, largeButton: true } }), false, '큰 버튼만으로는 크게 보기가 아님');
  assert.equal(alreadyLarge({ largeView: true, settings: initialSettings }), true);
  assert.equal(alreadyLarge({ largeView: false, settings: { ...initialSettings, largeText: true } }), true);
  assert.equal('largeView' in initialSettings, false, '저장하는 화면 설정에는 크게 보기가 없음');
});
