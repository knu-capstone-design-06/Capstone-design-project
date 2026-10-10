// Vite와 외부 Playwright만 사용합니다. 백엔드 서버·저장소는 실행하지 않습니다.
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { bootstrap, cartResponse, food, hot, iced, installOrderResponses, mutation, orderResponse, productsResponse } from './orderApiFixture.mjs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.ORDER_BROWSER_URL ?? 'http://127.0.0.1:5173';
async function open(browser, steps) {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, hasTouch: true });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const fixture = await installOrderResponses(page, steps);
  await page.goto(url);
  return { page, errors, fixture };
}
async function ready(page) {
  await page.waitForFunction(() => {
    const product = document.querySelector('[data-log-target="product:americano"]');
    return product && !product.disabled;
  });
}
const click = (page, target) => page.locator(`[data-log-target="${target}"]`).click();
async function add(page, product = 'americano', temperature = '아이스') {
  await click(page, `product:${product}`);
  if (product === 'americano') await click(page, `temperature:${temperature}`);
  await click(page, 'cart-add');
  await page.locator('dialog[open]').waitFor({ state: 'hidden' });
}
async function screenshot(page, name) {
  if (!process.env.ORDER_SCREENSHOT_DIR) return;
  await mkdir(process.env.ORDER_SCREENSHOT_DIR, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(process.env.ORDER_SCREENSHOT_DIR, `${name}.png`) });
}
async function noOverflow(page) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
}

test('1080×1920: API 응답으로 상품·옵션·수량·삭제·완료·새 이용과 접근성 설정 표시', async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const a = 'session-test-1', b = 'session-test-2', c = 'session-test-3';
    const confirmed = cartResponse(a, 5, [iced(3), food]);
    const { page, errors, fixture } = await open(browser, [
      ...bootstrap(a),
      mutation(a, '/cart/items', cartResponse(a, 1, [iced(2)])),
      mutation(a, '/cart/items', cartResponse(a, 2, [iced(2), hot])),
      mutation(a, '/cart/items', cartResponse(a, 3, [iced(2), hot, food])),
      mutation(a, '/cart/items/item-iced', cartResponse(a, 4, [iced(3), hot, food]), { method: 'PATCH' }),
      mutation(a, '/cart/items/item-hot?expected_version=4', confirmed, { method: 'DELETE' }),
      mutation(a, '/orders', orderResponse(confirmed), { status: 201 }),
      { method: 'GET', path: '/api/v1/products', body: productsResponse },
      { method: 'POST', path: '/api/v1/sessions', fail: true },
      ...bootstrap(b),
      mutation(b, '/cart/items', cartResponse(b, 1, [iced()])),
      ...bootstrap(c),
    ]);
    await ready(page);
    await click(page, 'product:americano');
    await click(page, 'options-increase');
    await click(page, 'cart-add');
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    await add(page, 'americano', '핫');
    await add(page, 'sandwich');
    assert.equal(await page.locator('.cart-row').count(), 3);
    assert.match(await page.locator('.total').innerText(), /16,000원/);
    await click(page, 'cart:americano:아이스:increase');
    await page.waitForFunction(() => document.querySelector('.total')?.innerText.includes('19,500원'));
    await click(page, 'cart:americano:핫:remove');
    await page.waitForFunction(() => document.querySelector('.total')?.innerText.includes('16,000원'));
    await noOverflow(page);
    await screenshot(page, 'order-menu-default');
    await click(page, 'support-toggle');
    await click(page, 'support:largeText');
    await click(page, 'support:largeButton');
    await click(page, 'support-toggle');
    await screenshot(page, 'order-menu-large');
    await click(page, 'product:sandwich');
    assert.equal(await page.locator('dialog fieldset').count(), 0);
    await screenshot(page, 'order-options-large');
    await click(page, 'options-close');
    await click(page, 'review-open');
    await noOverflow(page);
    await screenshot(page, 'order-review-large');
    await click(page, 'simulate-payment');
    await page.locator('.order-number').waitFor();
    assert.equal(await page.locator('.order-number').innerText(), 'DEMO-042', '서버 번호 형식을 가정하지 않음');
    await screenshot(page, 'order-complete-large');
    await click(page, 'new-order');
    await click(page, 'order-connect-retry');
    await ready(page);
    assert.match(await page.locator('.total').innerText(), /0원/);
    assert(await page.locator('.kiosk.large-text.large-button').count());
    await add(page);
    await page.reload();
    await ready(page);
    assert.equal(await page.locator('.cart-row').count(), 0);
    assert(await page.locator('.kiosk.large-text.large-button').count());
    const adds = fixture.requests.filter(request => request.method === 'POST' && request.path.endsWith('/cart/items'));
    assert.deepEqual(adds[0].body, { product_id: 'americano', temperature: 'iced', quantity: 2, expected_version: 0 });
    assert.equal(adds[2].body.temperature, null);
    assert.equal(fixture.requests.filter(request => request.path === '/api/v1/sessions').length, 4);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('응답 유실에는 로컬 확정 표시 없이 같은 키·버전·본문으로 추가·주문을 재시도', async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const session = 'session-retry', cart = cartResponse(session, 1, [iced()]);
    const { page, errors, fixture } = await open(browser, [
      ...bootstrap(session),
      mutation(session, '/cart/items', null, { fail: true }),
      mutation(session, '/cart/items', cart),
      mutation(session, '/orders', null, { fail: true }),
      mutation(session, '/orders', orderResponse(cart), { status: 201 }),
    ]);
    await ready(page);
    await click(page, 'product:americano');
    await click(page, 'cart-add');
    await page.getByRole('button', { name: '결과 다시 확인', exact: true }).waitFor();
    assert.equal(await page.locator('.cart-row').count(), 0, '성공 응답 전 로컬 확정 표시 없음');
    await click(page, 'order-result-retry');
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    const adds = fixture.requests.filter(request => request.path.endsWith('/cart/items'));
    assert.deepEqual(adds[0], adds[1]);
    await click(page, 'review-open');
    await click(page, 'simulate-payment');
    await page.getByRole('button', { name: '결과 다시 확인', exact: true }).waitFor();
    assert.equal(await page.locator('.order-number').count(), 0);
    assert(await page.locator('[data-log-target="simulate-payment"]').isDisabled());
    await click(page, 'order-result-retry');
    await page.locator('.order-number').waitFor();
    const orders = fixture.requests.filter(request => request.path.endsWith('/orders'));
    assert.deepEqual(orders[0], orders[1]);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('버전 충돌 응답의 최신 Cart를 표시하고 재조작에는 최신 버전·새 키를 사용', async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const session = 'session-conflict';
    const { page, errors, fixture } = await open(browser, [
      ...bootstrap(session),
      mutation(session, '/cart/items', cartResponse(session, 1, [iced()])),
      mutation(session, '/cart/items/item-iced', { code: 'cart_version_conflict',
        detail: '담은 메뉴가 변경되었습니다. 최신 내용을 확인해 주세요.',
        cart: cartResponse(session, 2, [iced(3)]) }, { method: 'PATCH', status: 409 }),
      mutation(session, '/cart/items/item-iced', cartResponse(session, 3, [iced(4)]), { method: 'PATCH' }),
    ]);
    await ready(page);
    await add(page);
    await click(page, 'cart:americano:아이스:increase');
    await page.waitForFunction(() => document.querySelector('.order-feedback')?.innerText.includes('최신 내용을 확인'));
    assert.equal(await page.locator('.cart-row .quantity > span').innerText(), '3');
    await click(page, 'cart:americano:아이스:increase');
    await page.waitForFunction(() => document.querySelector('.cart-row .quantity > span')?.textContent === '4');
    const patches = fixture.requests.filter(request => request.method === 'PATCH');
    assert.equal(patches[0].body.expected_version, 1);
    assert.equal(patches[1].body.expected_version, 2);
    assert.notEqual(patches[0].key, patches[1].key);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('주문 API가 없는 서버에서는 연결 대기를 표시하고 임의의 상품·주문을 만들지 않음', async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const { page, errors, fixture } = await open(browser, [
      { method: 'GET', path: '/api/v1/products', status: 404, body: { detail: 'Not Found' } },
    ]);
    await page.getByRole('alert').waitFor();
    assert.match(await page.getByRole('alert').innerText(), /아직 준비되지/);
    assert.equal(await page.locator('.product').count(), 0);
    assert.equal(await page.locator('.cart-row').count(), 0);
    assert(await page.locator('[data-log-target="review-open"]').isDisabled());
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});
