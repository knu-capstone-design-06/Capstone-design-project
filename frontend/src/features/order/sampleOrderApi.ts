import { createBackendApi } from '../../shared/api/client.ts';
import type { Cart, CartItem, Order, Product, ProductCategory } from '../../shared/api/types.ts';
import { MAX_QUANTITY } from './model.ts';

// Development-only samples from the original menu; never a fallback for backend errors.
const menu: [string, string, ProductCategory, number, string][] = [
  ['americano', '아메리카노', 'coffee', 3500, '깊고 깔끔한 에스프레소'],
  ['latte', '카페 라떼', 'coffee', 4200, '부드러운 우유와 진한 커피'],
  ['vanilla', '바닐라 라떼', 'coffee', 4700, '달콤한 바닐라의 여유'],
  ['tea', '레몬 티', 'drink', 4000, '상큼하게 즐기는 레몬 티'],
  ['chocolate', '초콜릿 라떼', 'drink', 4500, '진한 초콜릿과 부드러운 우유'],
  ['sandwich', '에그 샌드위치', 'food', 5500, '든든한 달걀 샌드위치'],
  ['croissant', '버터 크루아상', 'food', 3200, '겹겹이 구운 버터의 풍미'],
  ['mocha', '카페 모카', 'coffee', 4800, '커피와 초콜릿의 달콤한 조화'],
  ['caramel', '카라멜 라떼', 'coffee', 4800, '부드럽게 즐기는 카라멜 커피'],
  ['cappuccino', '카푸치노', 'coffee', 4300, '풍성한 우유 거품과 에스프레소'],
  ['matcha', '말차 라떼', 'drink', 4900, '향긋한 말차와 고소한 우유'],
  ['earl-grey', '얼그레이 티', 'drink', 4000, '은은한 베르가모트 향의 홍차'],
  ['peach-tea', '복숭아 티', 'drink', 4200, '달콤한 복숭아 향을 담은 티'],
  ['bagel', '플레인 베이글', 'food', 3500, '담백하고 쫄깃한 베이글'],
  ['muffin', '블루베리 머핀', 'food', 3800, '블루베리가 들어간 촉촉한 머핀'],
  ['cookie', '초콜릿 쿠키', 'food', 2800, '초콜릿 칩이 가득한 쿠키'],
  ['cake', '딸기 케이크', 'food', 6500, '딸기와 크림을 올린 조각 케이크'],
];
/** In-memory HTTP response adapter for explicitly selected development demonstrations. */
export function createSampleOrderApi() {
  const products: Product[] = menu.map(([product_id, name, category, unit_price, description]) => ({
    product_id, name, category, unit_price, description, available: true,
    temperatures: category === 'food' ? [] : ['iced', 'hot'],
  }));
  const carts = new Map<string, Cart>();
  const completed = new Set<string>();
  const results = new Map<string, { fingerprint: string; body: Cart | Order; status: number }>();
  let orderNumber = 0;
  const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  });
  const error = (status: number, code: string, detail: string, cart: Cart | null = null) => reply({ code, detail, cart }, status);
  const snapshot = (session: string, version: number, items: CartItem[]): Cart => ({
    session_id: session, version, currency: 'KRW', items,
    total_quantity: items.reduce((sum, row) => sum + row.quantity, 0),
    total_amount: items.reduce((sum, row) => sum + row.line_amount, 0),
    updated_at: new Date().toISOString(),
  });

  const fetcher: typeof fetch = async (input, init) => {
    const url = new URL(String(input));
    const method = init?.method ?? 'GET';
    if (method === 'GET' && url.pathname === '/api/v1/products') return reply({ currency: 'KRW', products });
    if (method === 'POST' && url.pathname === '/api/v1/sessions') {
      const session = `sample-session-${crypto.randomUUID()}`;
      carts.set(session, snapshot(session, 0, []));
      return reply({ session_id: session, started_at: new Date().toISOString() }, 201);
    }
    const match = /^\/api\/v1\/sessions\/([^/]+)\/(cart(?:\/items(?:\/([^/]+))?)?|orders)$/.exec(url.pathname);
    if (!match) return error(404, 'invalid_request', '개발 샘플에서 제공하지 않는 API입니다.');
    const [, session, path, itemId] = match;
    const cart = carts.get(session);
    if (!cart) return error(404, 'session_not_found', '개발 샘플 세션이 없습니다.');
    if (method === 'GET' && path === 'cart') return reply(cart);
    if (!((method === 'POST' && ['cart/items', 'orders'].includes(path))
      || (itemId && ['PATCH', 'DELETE'].includes(method)))) return error(405, 'invalid_request', '지원하지 않는 샘플 요청입니다.');
    const key = new Headers(init?.headers).get('Idempotency-Key');
    if (!key?.trim()) return error(422, 'invalid_request', '중복 방지 키가 필요합니다.');
    const fingerprint = JSON.stringify([method, url.pathname, url.search, init?.body ?? null]);
    const resultKey = `${session}:${key}`;
    const previous = results.get(resultKey);
    if (previous) return previous.fingerprint === fingerprint ? reply(previous.body, previous.status)
      : error(409, 'idempotency_key_reused', '같은 샘플 키에 다른 요청을 보냈습니다.');
    if (completed.has(session)) return error(410, 'session_expired', '새 개발 샘플 주문을 시작해 주세요.');
    let payload;
    try { payload = typeof init?.body === 'string' ? JSON.parse(init.body) : null; }
    catch { return error(422, 'invalid_request', '샘플 요청 본문을 확인해 주세요.'); }
    const expected = method === 'DELETE' ? url.searchParams.get('expected_version') : payload?.expected_version;
    if (expected === null || expected === undefined || !Number.isInteger(Number(expected)) || Number(expected) < 0) {
      return error(422, 'invalid_request', '샘플 장바구니 버전이 필요합니다.');
    }
    if (Number(expected) !== cart.version) return error(409, 'cart_version_conflict', '변경된 샘플 장바구니를 확인해 주세요.', cart);
    let body: Cart | Order;
    let status = 200;
    if (path === 'orders') {
      if (!cart.items.length) return error(409, 'empty_cart', '샘플 메뉴를 먼저 담아 주세요.', cart);
      body = { order_id: `sample-order-${crypto.randomUUID()}`, order_number: `DEV-SAMPLE-${String(++orderNumber).padStart(3, '0')}`,
        session_id: session, status: 'simulated', currency: 'KRW', items: structuredClone(cart.items),
        total_quantity: cart.total_quantity, total_amount: cart.total_amount, created_at: new Date().toISOString() };
      carts.set(session, snapshot(session, cart.version + 1, []));
      completed.add(session);
      status = 201;
    } else {
      let items = structuredClone(cart.items);
      if (method === 'POST') {
        const product = products.find(row => row.product_id === payload?.product_id);
        if (!product) return error(404, 'product_not_found', '샘플 상품이 없습니다.');
        if (!(product.temperatures.length ? product.temperatures.includes(payload?.temperature) : payload?.temperature === null)) {
          return error(422, 'invalid_option', '샘플 온도를 확인해 주세요.');
        }
        if (!Number.isInteger(payload?.quantity) || payload.quantity < 1 || payload.quantity > MAX_QUANTITY) {
          return error(422, 'invalid_request', '샘플 수량은 1~20개입니다.');
        }
        const existing = items.find(row => row.product_id === product.product_id && row.temperature === payload.temperature);
        const quantity = (existing?.quantity ?? 0) + payload.quantity;
        if (quantity > MAX_QUANTITY) return error(409, 'quantity_limit_exceeded', '같은 샘플 메뉴는 최대 20개입니다.', cart);
        const row: CartItem = { item_id: existing?.item_id ?? crypto.randomUUID(), product_id: product.product_id,
          name: product.name, temperature: payload.temperature, quantity, unit_price: product.unit_price, line_amount: product.unit_price * quantity };
        items = existing ? items.map(item => item.item_id === row.item_id ? row : item) : [...items, row];
      } else {
        const existing = items.find(row => row.item_id === itemId);
        if (!existing) return error(404, 'cart_item_not_found', '샘플 항목이 없습니다.');
        if (method === 'DELETE') items = items.filter(row => row.item_id !== itemId);
        else {
          if (!Number.isInteger(payload?.quantity) || payload.quantity < 1 || payload.quantity > MAX_QUANTITY) {
            return error(422, 'invalid_request', '샘플 수량은 1~20개입니다.');
          }
          items = items.map(row => row.item_id === itemId ? { ...row, quantity: payload.quantity, line_amount: row.unit_price * payload.quantity } : row);
        }
      }
      body = snapshot(session, cart.version + 1, items);
      carts.set(session, body);
    }
    results.set(resultKey, { fingerprint, body: structuredClone(body), status });
    return reply(body, status);
  };
  return createBackendApi('https://sample.invalid', fetcher);
}
