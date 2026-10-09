// 브라우저 테스트 전용 고정 응답입니다. 앱 실행 코드에서 import하지 않습니다.
// 서버 저장·검증·주문번호 발급 로직을 구현하지 않고 프론트가 받을 응답만 준비합니다.
import assert from 'node:assert/strict';

export const productsResponse = { currency: 'KRW', products: [
  { product_id: 'americano', name: '아메리카노', category: 'coffee', description: '깊고 깔끔한 에스프레소', unit_price: 3500, available: true, temperatures: ['iced', 'hot'] },
  { product_id: 'latte', name: '카페 라떼', category: 'coffee', description: '부드러운 우유와 진한 커피', unit_price: 4200, available: true, temperatures: ['iced', 'hot'] },
  { product_id: 'tea', name: '레몬 티', category: 'drink', description: '상큼하게 즐기는 레몬 티', unit_price: 4000, available: true, temperatures: ['iced', 'hot'] },
  { product_id: 'chocolate', name: '초콜릿 라떼', category: 'drink', description: '진한 초콜릿과 부드러운 우유', unit_price: 4500, available: true, temperatures: ['iced', 'hot'] },
  { product_id: 'sandwich', name: '에그 샌드위치', category: 'food', description: '든든한 달걀 샌드위치', unit_price: 5500, available: true, temperatures: [] },
  { product_id: 'croissant', name: '버터 크루아상', category: 'food', description: '겹겹이 구운 버터의 풍미', unit_price: 3200, available: true, temperatures: [] },
] };
export const iced = (quantity = 1) => ({ item_id: 'item-iced', product_id: 'americano', name: '아메리카노',
  temperature: 'iced', quantity, unit_price: 3500, line_amount: 3500 * quantity });
export const hot = { ...iced(), item_id: 'item-hot', temperature: 'hot' };
export const food = { item_id: 'item-food', product_id: 'sandwich', name: '에그 샌드위치',
  temperature: null, quantity: 1, unit_price: 5500, line_amount: 5500 };
export const cartResponse = (session, version = 0, items = []) => ({
  session_id: session, version, currency: 'KRW', items,
  total_quantity: items.reduce((sum, item) => sum + item.quantity, 0),
  total_amount: items.reduce((sum, item) => sum + item.line_amount, 0),
  updated_at: '2026-10-10T00:00:00Z',
});
export const orderResponse = cart => ({
  order_id: 'order-test', order_number: 'DEMO-042', session_id: cart.session_id,
  status: 'simulated', currency: 'KRW', items: cart.items,
  total_quantity: cart.total_quantity, total_amount: cart.total_amount,
  created_at: '2026-10-10T00:01:00Z',
});
export const bootstrap = session => [
  { method: 'GET', path: '/api/v1/products', body: productsResponse },
  { method: 'POST', path: '/api/v1/sessions', status: 201, body: { session_id: session, started_at: '2026-10-10T00:00:00Z' } },
  { method: 'GET', path: `/api/v1/sessions/${session}/cart`, body: cartResponse(session) },
];
export const mutation = (session, suffix, body, options = {}) => ({
  method: 'POST', path: `/api/v1/sessions/${session}${suffix}`, body, ...options,
});

export async function installOrderResponses(page, steps) {
  const queue = [...steps], requests = [], errors = [];
  await page.route('**/backend/**', async route => {
    const request = route.request();
    const parsed = new URL(request.url());
    const actual = { method: request.method(), path: parsed.pathname.replace(/^\/backend/, '') + parsed.search,
      key: request.headers()['idempotency-key'], body: request.postData() ? request.postDataJSON() : null };
    requests.push(actual);
    try {
      const expected = queue.shift();
      assert(expected, `예상하지 않은 요청: ${actual.method} ${actual.path}`);
      assert.equal(actual.method, expected.method);
      assert.equal(actual.path, expected.path);
      if (expected.fail) return await route.abort('failed');
      await route.fulfill({ status: expected.status ?? 200, contentType: 'application/json',
        headers: expected.headers, body: JSON.stringify(expected.body) });
    } catch (error) {
      errors.push(error.message);
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: '테스트 응답 불일치' }) });
    }
  });
  return { requests, verify() { assert.deepEqual(errors, []); assert.equal(queue.length, 0, '준비된 요청 흐름을 모두 확인'); } };
}
