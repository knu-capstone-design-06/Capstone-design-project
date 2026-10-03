import assert from 'node:assert/strict';
import test from 'node:test';
import { addItem, readState, total, initialState } from './model.ts';

test('같은 상품·옵션은 합치고 다른 옵션은 따로 담으며 최대 수량을 지킨다', () => {
  let cart = addItem([], { productId: 'americano', temperature: '아이스', quantity: 2 });
  cart = addItem(cart, { productId: 'americano', temperature: '핫', quantity: 1 });
  cart = addItem(cart, { productId: 'americano', temperature: '아이스', quantity: 20 });
  assert.deepEqual(cart.map(item => item.quantity), [20, 1]);
  assert.equal(total(cart), 73500);
});
test('새로고침용 저장 데이터에서 주문과 접근성 설정을 복원한다', () => {
  const state = { cart: [{ productId: 'latte', temperature: '핫', quantity: 3 }], settings: { ...initialState.settings, largeText: true } };
  assert.deepEqual(readState(JSON.stringify(state)), state);
});
test('손상된 저장 값과 삭제된 상품·잘못된 옵션·수량을 복원하지 않는다', () => {
  assert.deepEqual(readState('{broken'), initialState);
  const invalid = [{ productId: 'unknown', temperature: '핫', quantity: 1 }, { productId: 'latte', temperature: '기본', quantity: 1 }, { productId: 'latte', temperature: '핫', quantity: -1 }, null];
  assert.deepEqual(readState(JSON.stringify({ cart: invalid, settings: { largeText: 'false' } })), initialState);
});
