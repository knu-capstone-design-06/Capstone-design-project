import assert from 'node:assert/strict';
import test from 'node:test';
import { createSampleOrderApi } from './sampleOrderApi.ts';
import { OrderController } from './orderController.ts';
import { ApiError } from '../../shared/api/client.ts';

test('개발 샘플의 기존 17개 상품으로 옵션·수량·삭제·주문·새 이용을 시연한다', async () => {
  const controller = new OrderController(createSampleOrderApi());
  assert.equal(await controller.initialize(), true);
  assert.equal(controller.getSnapshot().products.length, 17);
  const first = controller.getSnapshot().session.session_id;
  await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 });
  await controller.addItem({ product_id: 'sandwich', temperature: null, quantity: 1 });
  assert.equal(controller.getSnapshot().cart.total_amount, 12500);
  const [drink, food] = controller.getSnapshot().cart.items;
  assert.equal(food.temperature, null);
  await controller.updateQuantity(drink.item_id, 3);
  await controller.removeItem(food.item_id);
  assert.equal(controller.getSnapshot().cart.total_amount, 10500);
  assert.equal(await controller.checkout(), true);
  assert.match(controller.getSnapshot().order.order_number, /^DEV-SAMPLE-/);
  assert.equal(await controller.startNewOrder(), true);
  assert.notEqual(controller.getSnapshot().session.session_id, first);
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
});

test('개발 샘플의 동일 요청 재확인은 메뉴·주문을 중복 생성하지 않는다', async () => {
  const api = createSampleOrderApi();
  const { session_id: session } = await api.createSession();
  const input = { product_id: 'americano', temperature: 'hot', quantity: 2, expected_version: 0 };
  const cart = await api.addCartItem(session, input, 'add-key');
  assert.deepEqual(await api.addCartItem(session, input, 'add-key'), cart);
  assert.equal((await api.getCart(session)).total_quantity, 2);
  await assert.rejects(api.addCartItem(session, { ...input, quantity: 3 }, 'add-key'), error => error instanceof ApiError && error.body.code === 'idempotency_key_reused');
  const order = await api.createOrder(session, { expected_version: 1 }, 'order-key');
  assert.deepEqual(await api.createOrder(session, { expected_version: 1 }, 'order-key'), order);
  assert.equal((await api.getCart(session)).total_quantity, 0);
});

test('샘플의 옵션·합산 한도·버전 오류는 기존 장바구니를 유지한다', async () => {
  const api = createSampleOrderApi();
  const { session_id: session } = await api.createSession();
  const input = { product_id: 'americano', temperature: 'iced', quantity: 20, expected_version: 0 };
  const cart = await api.addCartItem(session, input, 'first');
  await assert.rejects(api.addCartItem(session, { ...input, quantity: 1, expected_version: 1 }, 'over-limit'), error => error.body.code === 'quantity_limit_exceeded');
  await assert.rejects(api.addCartItem(session, { product_id: 'sandwich', temperature: 'hot', quantity: 1, expected_version: 1 }, 'bad-option'), error => error.body.code === 'invalid_option');
  await assert.rejects(api.updateCartItem(session, cart.items[0].item_id, { quantity: 2, expected_version: 0 }, 'old-version'), error => error.body.code === 'cart_version_conflict');
  assert.deepEqual(await api.getCart(session), cart);
});
