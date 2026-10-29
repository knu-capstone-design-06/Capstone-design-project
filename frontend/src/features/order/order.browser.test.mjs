// Vite와 외부 Playwright만 사용합니다. 백엔드 서버·저장소는 실행하지 않습니다.
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { bootstrap, cartResponse, food, hot, iced, installOrderResponses, mutation, orderResponse, productsResponse } from './orderApiFixture.mjs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.ORDER_BROWSER_URL ?? 'http://127.0.0.1:5173';
const channel = process.env.PLAYWRIGHT_CHANNEL ?? 'msedge';
const launchOptions = { headless: true, ...(channel === 'default' ? {} : { channel }) };
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

async function bottomAction(page, target) {
  const button = page.locator(`[data-log-target="${target}"]`);
  await button.scrollIntoViewIfNeeded();
  const bounds = await button.boundingBox(), viewport = page.viewportSize();
  const bar = await page.locator('.order-actions').boundingBox();
  assert(bounds && viewport);
  assert(bar && Math.abs(bar.y + bar.height - viewport.height) < 2 && bounds.y >= bar.y, '주요 버튼은 하단 고정 영역 안에 배치');
  assert(bounds.x >= 0 && bounds.x + bounds.width <= viewport.width);
  assert(bounds.y + bounds.height <= viewport.height);
  assert(await button.evaluate(element => {
    const rect = element.getBoundingClientRect();
    return element.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
  }), '하단 주문 버튼이 다른 요소에 가려지지 않음');
}

test('세로·가로 화면과 독립 접근성 설정에서 전체 주문·설정 유지·수동 초기화', async t => {
  const browser = await chromium.launch(launchOptions);
  try {
    for (const viewport of [{ width: 1080, height: 1920 }, { width: 1920, height: 1080 }, { width: 1365, height: 768 }]) {
      for (const settings of [[], ['largeText'], ['largeButton'], ['largeText', 'largeButton']]) {
        const label = `${viewport.width}x${viewport.height}-${settings.join('-') || 'default'}`;
        await t.test(label, async () => {
          const first = `matrix-${label}`, second = `${first}-new`;
          const cart = cartResponse(first, 6, [iced(2), food]);
          const { page, errors, fixture } = await open(browser, [
            ...bootstrap(first),
            mutation(first, '/cart/items', cartResponse(first, 1, [iced(2)])),
            mutation(first, '/cart/items', cartResponse(first, 2, [iced(2), hot])),
            mutation(first, '/cart/items', cartResponse(first, 3, [iced(2), hot, food])),
            mutation(first, '/cart/items/item-iced', cartResponse(first, 4, [iced(3), hot, food]), { method: 'PATCH' }),
            mutation(first, '/cart/items/item-iced', cartResponse(first, 5, [iced(2), hot, food]), { method: 'PATCH' }),
            mutation(first, '/cart/items/item-hot?expected_version=5', cart, { method: 'DELETE' }),
            mutation(first, '/orders', orderResponse(cart), { status: 201 }),
            ...bootstrap(second),
          ]);
          await page.setViewportSize(viewport); await ready(page);
          await click(page, 'support-toggle');
          for (const setting of settings) await click(page, `support:${setting}`);
          await click(page, 'support:stepGuide'); await click(page, 'support-toggle');
          assert.equal(await page.locator('.guide p').count(), 2);
          await click(page, 'product:americano');
          await click(page, 'options-increase'); await click(page, 'cart-add');
          await page.locator('dialog[open]').waitFor({ state: 'hidden' });
          await add(page, 'americano', '핫'); await add(page, 'sandwich');
          await click(page, 'cart:americano:아이스:increase');
          await page.waitForFunction(() => document.querySelector('.total')?.innerText.includes('19,500원'));
          await click(page, 'cart:americano:아이스:decrease');
          await page.waitForFunction(() => document.querySelector('.total')?.innerText.includes('16,000원'));
          await click(page, 'cart:americano:핫:remove');
          await page.waitForFunction(() => document.querySelector('.total')?.innerText.includes('12,500원'));
          await noOverflow(page); await bottomAction(page, 'review-open');
          if (settings.includes('largeText')) assert(await page.locator('.product-info strong').first().evaluate(element => parseFloat(getComputedStyle(element).fontSize) >= 56), '큰 글씨에서 기본 28px의 두 배 이상');
          if (settings.includes('largeButton')) assert((await page.locator('[data-log-target="review-open"]').boundingBox()).height >= 88);
          await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
          await bottomAction(page, 'review-open');
          const lastProduct = await page.locator('.product').last().boundingBox();
          const actions = await page.locator('.order-actions').boundingBox();
          assert(lastProduct.y + lastProduct.height <= actions.y, '목록 끝도 하단 주문 영역 위로 스크롤 가능');
          await screenshot(page, `matrix-menu-${label}`);
          await click(page, 'review-open'); await noOverflow(page); await bottomAction(page, 'simulate-payment');
          await click(page, 'review-back'); await bottomAction(page, 'review-open');
          await click(page, 'review-open'); await screenshot(page, `matrix-review-${label}`);
          await click(page, 'simulate-payment'); await page.locator('.order-number').waitFor();
          await noOverflow(page); await bottomAction(page, 'new-order');
          await screenshot(page, `matrix-complete-${label}`);
          await click(page, 'new-order'); await ready(page);
          assert.equal(await page.locator('.cart-row').count(), 0);
          for (const setting of ['largeText', 'largeButton']) {
            const className = setting === 'largeText' ? 'large-text' : 'large-button';
            assert.equal(await page.locator(`.kiosk.${className}`).count(), Number(settings.includes(setting)), '새 주문에서도 설정 유지');
          }
          await click(page, 'support-toggle'); await click(page, 'support-reset');
          assert.equal(await page.locator('.support-options [aria-pressed="true"]').count(), 0, '기본 화면은 사용자가 명시적으로 초기화');
          assert.equal(await page.locator('.guide').count(), 0);
          fixture.verify(); assert.deepEqual(errors, []); await page.close();
        });
      }
    }
  } finally { await browser.close(); }
});

test('낮은 화면에서 옵션·전체 주문·접근성 조합·새로고침·높이 복귀를 사용할 수 있다', async t => {
  const browser = await chromium.launch(launchOptions);
  try {
    for (const viewport of [{ width: 1080, height: 1920 }, { width: 1920, height: 1080 }, { width: 1365, height: 768 }, { width: 390, height: 844 }]) {
      for (const settings of [[], ['largeText'], ['largeButton'], ['largeText', 'largeButton', 'simpleScreen', 'stepGuide']]) {
        const label = `${viewport.width}x${viewport.height}-${settings.join('-') || 'default'}`;
        await t.test(label, async () => {
          const first = `low-${label}`, second = `${first}-new`, third = `${first}-reload`;
          const cart = cartResponse(first, 1, [iced()]);
          const { page, errors, fixture } = await open(browser, [
            ...bootstrap(first), mutation(first, '/cart/items', cart),
            mutation(first, '/orders', orderResponse(cart), { status: 201 }),
            ...bootstrap(second), ...bootstrap(third),
          ]);
          await page.setViewportSize(viewport); await ready(page);
          await click(page, 'support-toggle');
          for (const setting of settings) await click(page, `support:${setting}`);
          await click(page, 'support-toggle');
          await click(page, 'screen-height-toggle');
          const top = Math.max(0, viewport.height - Math.max(viewport.height * .6, 720));
          const root = await page.locator('.kiosk.low-screen').boundingBox();
          assert(root && Math.abs(root.y - top) < 2, '선택한 높이에 조작 영역을 배치');
          const reachable = async selector => {
            const element = page.locator(selector);
            await element.scrollIntoViewIfNeeded();
            const rect = await element.boundingBox();
            assert(rect && rect.y >= top - 1 && rect.y + rect.height <= viewport.height + 1, `${selector}은 낮은 조작 영역 안에 있음`);
            assert(await element.evaluate(node => {
              const bounds = node.getBoundingClientRect();
              return node.contains(document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2));
            }), `${selector}이 다른 요소에 가려지지 않음`);
          };
          await reachable('[data-log-target="support-toggle"]');
          await reachable('[data-log-target="screen-height-toggle"]');
          await click(page, 'support-toggle');
          assert.equal(await page.locator('[data-log-target="support:lowScreen"]').getAttribute('aria-pressed'), 'true');
          await click(page, 'support-toggle');
          await click(page, 'product:americano');
          await reachable('dialog[open]');
          await reachable('[data-log-target="options-close"]');
          await reachable('[data-log-target="cart-add"]');
          await click(page, 'cart-add'); await page.locator('dialog[open]').waitFor({ state: 'hidden' });
          await noOverflow(page); await bottomAction(page, 'review-open');
          await page.locator('.low-screen > main').evaluate(element => { element.scrollTop = element.scrollHeight; });
          const lastProduct = await page.locator('.product').last().boundingBox();
          const actions = await page.locator('.order-actions').boundingBox();
          assert(lastProduct.y + lastProduct.height <= actions.y, '낮은 화면에서도 목록 끝을 하단 바 위까지 볼 수 있음');
          await click(page, 'screen-height-toggle');
          assert.equal(await page.locator('.low-screen').count(), 0);
          assert.match(await page.locator('.total').innerText(), /3,500원/, '높이 복귀에도 장바구니 유지');
          await click(page, 'screen-height-toggle');
          await screenshot(page, `low-menu-${label}`);
          await click(page, 'review-open'); await reachable('[data-log-target="review-back"]');
          await click(page, 'simulate-payment'); await page.locator('.order-number').waitFor();
          await bottomAction(page, 'new-order'); await click(page, 'new-order'); await ready(page);
          assert.equal(await page.locator('.kiosk.low-screen').count(), 1, '새 주문에도 낮은 화면 유지');
          assert.equal(await page.locator('.cart-row').count(), 0);
          await page.reload(); await ready(page);
          assert.equal(await page.locator('.kiosk.low-screen').count(), 1, '새로고침에도 낮은 화면 유지');
          await click(page, 'support-toggle'); await click(page, 'support-reset');
          assert.equal(await page.locator('.low-screen').count(), 0);
          assert.equal(await page.locator('.support-options [aria-pressed="true"]').count(), 0);
          fixture.verify(); assert.deepEqual(errors, []); await page.close();
        });
      }
    }
  } finally { await browser.close(); }
});

test('HTML 409 오류의 Retry-After 동안 주문 재확인을 막고 동일 요청으로 복구', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'session-html-retry', cart = cartResponse(session, 1, [iced()]);
    const { page, errors, fixture } = await open(browser, [
      ...bootstrap(session), mutation(session, '/cart/items', cart),
      mutation(session, '/orders', null, { status: 409, rawBody: '<html>Please wait</html>', contentType: 'text/html', headers: { 'Retry-After': '1' } }),
      mutation(session, '/orders', orderResponse(cart), { status: 201 }),
    ]);
    await ready(page); await add(page); await click(page, 'review-open'); await click(page, 'simulate-payment');
    const retry = page.locator('[data-log-target="order-result-retry"]');
    await retry.waitFor(); assert(await retry.isDisabled());
    assert.doesNotMatch(await page.locator('.order-feedback').innerText(), /Please wait|API|409/);
    assert.match(await page.locator('.total').innerText(), /3,500원/);
    await retry.click(); await page.locator('.order-number').waitFor();
    const orders = fixture.requests.filter(request => request.path.endsWith('/orders'));
    assert.deepEqual(orders[0], orders[1]); fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('불완전한 주문 성공 응답은 완료 화면을 열지 않고 같은 요청 재확인으로 복구한다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'session-malformed-order', cart = cartResponse(session, 1, [iced()]);
    const incomplete = orderResponse(cart);
    delete incomplete.order_number;
    const { page, fixture, errors } = await open(browser, [
      ...bootstrap(session), mutation(session, '/cart/items', cart),
      mutation(session, '/orders', incomplete, { status: 201 }),
      mutation(session, '/orders', orderResponse(cart), { status: 201 }),
    ]);
    const diagnostics = [];
    page.on('console', message => { if (message.type() === 'warning') diagnostics.push(message.text()); });
    await ready(page);
    await add(page);
    await click(page, 'review-open');
    await click(page, 'simulate-payment');
    await page.locator('[data-log-target="order-result-retry"]').waitFor();
    assert(diagnostics.some(message => message.includes('order_number')));
    assert.doesNotMatch(await page.locator('.order-feedback').innerText(), /order_number/);
    assert.equal(await page.locator('.order-number').count(), 0);
    assert.match(await page.locator('.total').innerText(), /3,500원/);
    assert(await page.locator('[data-log-target="simulate-payment"]').isDisabled());
    await click(page, 'order-result-retry');
    await page.locator('.order-number').waitFor();
    assert.equal(await page.locator('.order-number').innerText(), 'DEMO-042');
    const orders = fixture.requests.filter(request => request.path.endsWith('/orders'));
    assert.deepEqual(orders[0], orders[1]);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('명시적으로 켠 개발 샘플은 서버 없이 17개 메뉴·주문·새 이용·새로고침을 제공한다', { skip: !process.env.ORDER_SAMPLE_BROWSER_URL }, async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    for (const large of [false, true]) {
      const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, hasTouch: true });
      const errors = [], backendRequests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (request.url().includes('/backend/')) backendRequests.push(request.url()); });
      await page.goto(process.env.ORDER_SAMPLE_BROWSER_URL);
      await ready(page);
      assert.match(await page.locator('.sample-badge').innerText(), /개발용 샘플/);
      assert.equal(await page.locator('.product').count(), 17);
      await page.waitForFunction(() => window.kioskTouchLogDraft?.read().serverSessionId?.startsWith('sample-session-'));
      const first = await page.evaluate(() => window.kioskTouchLogDraft.read().serverSessionId);
      if (large) {
        await click(page, 'support-toggle'); await click(page, 'support:largeText'); await click(page, 'support:largeButton'); await click(page, 'support-toggle');
      }
      await add(page);
      await add(page, 'sandwich');
      assert.match(await page.locator('.total').innerText(), /9,000원/);
      await noOverflow(page);
      await screenshot(page, `sample-menu-${large ? 'large' : 'default'}`);
      await click(page, 'review-open'); await click(page, 'simulate-payment');
      await page.locator('.order-number').waitFor();
      assert.match(await page.locator('.order-number').innerText(), /^DEV-SAMPLE-/);
      await click(page, 'new-order'); await ready(page);
      await page.waitForFunction(id => window.kioskTouchLogDraft.read().serverSessionId !== id, first);
      assert.equal(await page.locator('.cart-row').count(), 0);
      await add(page);
      await page.reload(); await ready(page);
      assert.equal(await page.locator('.cart-row').count(), 0);
      if (large) assert.equal(await page.locator('.kiosk.large-text.large-button').count(), 1);
      assert.deepEqual(backendRequests, []);
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally { await browser.close(); }
});

test('개발 샘플 설정으로 빌드해도 프로덕션에서는 서버 API를 사용한다', { skip: !process.env.ORDER_PRODUCTION_URL }, async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage();
    const fixture = await installOrderResponses(page, [{ method: 'GET', path: '/api/v1/products', status: 404, body: { detail: 'Not Found' } }]);
    await page.goto(process.env.ORDER_PRODUCTION_URL);
    await page.locator('[data-log-target="order-connect-retry"]').waitFor();
    assert.equal(await page.locator('.product').count(), 0);
    assert.doesNotMatch(await page.locator('.sample-badge').innerText(), /개발용/);
    assert.equal(await page.locator('.touch-log-tools').count(), 0);
    fixture.verify();
  } finally { await browser.close(); }
});

test('1080×1920: API 응답으로 상품·옵션·수량·삭제·완료·새 이용과 접근성 설정 표시', async () => {
  const browser = await chromium.launch(launchOptions);
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
  const browser = await chromium.launch(launchOptions);
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
    await page.getByRole('button', { name: '주문 반영 확인', exact: true }).waitFor();
    assert.equal(await page.locator('.cart-row').count(), 0, '성공 응답 전 로컬 확정 표시 없음');
    await click(page, 'order-result-retry');
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    const adds = fixture.requests.filter(request => request.path.endsWith('/cart/items'));
    assert.deepEqual(adds[0], adds[1]);
    await click(page, 'review-open');
    await click(page, 'simulate-payment');
    await page.getByRole('button', { name: '주문 반영 확인', exact: true }).waitFor();
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
  const browser = await chromium.launch(launchOptions);
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

test('재확인 실패 뒤 처음부터 다시 주문하고 새 연결 실패에서도 복구한다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    for (const large of [false, true]) {
      const first = `session-abandon-${large}`, second = `session-restart-${large}`;
      const cart = cartResponse(first, 1, [iced()]);
      const { page, errors, fixture } = await open(browser, [
        ...bootstrap(first),
        mutation(first, '/cart/items', cart),
        mutation(first, '/orders', null, { fail: true }),
        mutation(first, '/orders', { detail: '서비스를 사용할 수 없습니다.' }, { status: 503, headers: { 'Retry-After': '30' } }),
        { method: 'GET', path: '/api/v1/products', body: productsResponse },
        { method: 'POST', path: '/api/v1/sessions', fail: true },
        ...bootstrap(second),
      ]);
      await ready(page);
      if (large) {
        await click(page, 'support-toggle');
        await click(page, 'support:largeText');
        await click(page, 'support:largeButton');
        await click(page, 'support-toggle');
      }
      await add(page);
      await click(page, 'review-open');
      await click(page, 'simulate-payment');
      await page.locator('[data-log-target="order-result-retry"]').waitFor();
      assert.equal(await page.locator('[data-log-target="order-pending-restart"]').count(), 0);
      await click(page, 'order-result-retry');
      await page.locator('[data-log-target="order-pending-restart"]').waitFor();
      assert(await page.locator('[data-log-target="order-result-retry"]').isDisabled());
      assert.match(await page.locator('.order-feedback').innerText(), /자동으로 취소되지/);
      await noOverflow(page);
      const button = await page.locator('[data-log-target="order-pending-restart"]').boundingBox();
      assert(button && button.x >= 0 && button.x + button.width <= 1080);
      await screenshot(page, `order-retry-recovery-${large ? 'large' : 'default'}`);
      await click(page, 'order-pending-restart');
      await page.locator('[data-log-target="order-connect-retry"]').waitFor();
      await click(page, 'order-connect-retry');
      await ready(page);
      assert.equal(await page.locator('.cart-row').count(), 0);
      assert.equal(await page.locator('.order-number').count(), 0);
      assert.equal(await page.locator('[data-log-target="order-result-retry"]').count(), 0);
      const orders = fixture.requests.filter(request => request.path.endsWith('/orders'));
      assert.deepEqual(orders[0], orders[1]);
      assert.equal(fixture.requests.filter(request => request.path === '/api/v1/sessions').length, 3);
      fixture.verify();
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally { await browser.close(); }
});

test('상품 담기 재확인 실패 뒤 옵션 창을 닫고 새 주문을 시작한다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const first = 'session-modal-abandon', second = 'session-modal-restart';
    const { page, errors, fixture } = await open(browser, [
      ...bootstrap(first),
      mutation(first, '/cart/items', null, { fail: true }),
      mutation(first, '/cart/items', { detail: '처리 결과 확인 실패' }, { status: 503 }),
      ...bootstrap(second),
    ]);
    await ready(page);
    await click(page, 'product:americano');
    await click(page, 'cart-add');
    await page.locator('dialog [data-log-target="order-result-retry"]').waitFor();
    await click(page, 'order-result-retry');
    await page.locator('dialog [data-log-target="order-pending-restart"]').waitFor();
    assert.match(await page.locator('dialog .order-feedback').innerText(), /새 장바구니/);
    assert.doesNotMatch(await page.locator('dialog .order-feedback').innerText(), /주문은 자동으로 취소/);
    await click(page, 'order-pending-restart');
    await ready(page);
    assert.equal(await page.locator('dialog[open]').count(), 0);
    assert.equal(await page.locator('.cart-row').count(), 0);
    const adds = fixture.requests.filter(request => request.path.endsWith('/cart/items'));
    assert.deepEqual(adds[0], adds[1]);
    assert.equal(fixture.requests.filter(request => request.path.endsWith('/orders')).length, 0);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('변경 요청의 코드 없는 404·410 뒤 새 이용을 시작할 수 있다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    for (const status of [404, 410]) {
      const first = `session-ended-${status}`, second = `session-new-${status}`;
      const { page, errors, fixture } = await open(browser, [
        ...bootstrap(first),
        mutation(first, '/cart/items', { detail: 'session not found' }, { status }),
        ...bootstrap(second),
      ]);
      await ready(page);
      await click(page, 'product:americano');
      await click(page, 'cart-add');
      await page.locator('[data-log-target="order-session-restart"]').waitFor();
      await click(page, 'order-session-restart');
      await ready(page);
      assert.equal(await page.locator('.cart-row').count(), 0);
      assert.equal(await page.locator('dialog[open]').count(), 0);
      assert.equal(fixture.requests.filter(request => request.path === '/api/v1/sessions').length, 2);
      fixture.verify();
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally { await browser.close(); }
});

test('주문 API가 없는 서버에서는 연결 대기를 표시하고 임의의 상품·주문을 만들지 않음', async () => {
  const browser = await chromium.launch(launchOptions);
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

test('긴 주문 내역 아래에서 실패해도 안내와 재확인 버튼을 화면 안에 표시한다', async t => {
  const browser = await chromium.launch(launchOptions);
  try {
    for (const viewport of [{ width: 1080, height: 1920 }, { width: 1365, height: 768 }, { width: 1920, height: 1080 }]) {
      for (const large of [false, true]) {
        await t.test(`${viewport.width}x${viewport.height}-${large ? 'large' : 'default'}`, async () => {
          const session = `long-error-${viewport.width}-${large}`;
          const products = Array.from({ length: 17 }, (_, index) => {
            const source = productsResponse.products[index % productsResponse.products.length];
            return { ...source, product_id: `long-${index}` };
          });
          const items = products.map((product, index) => ({ item_id: `long-item-${index}`, product_id: product.product_id,
            name: product.name, temperature: product.temperatures[0] ?? null, quantity: 1,
            unit_price: product.unit_price, line_amount: product.unit_price }));
          const cart = cartResponse(session, 1, items);
          const steps = bootstrap(session); steps[0].body = { ...productsResponse, products }; steps[2].body = cart;
          const { page, errors, fixture } = await open(browser, [...steps,
            mutation(session, '/orders', { code: 'service_unavailable', detail: '서버 내부 오류' }, { status: 503 })]);
          await page.setViewportSize(viewport);
          await page.waitForFunction(() => !document.querySelector('[data-log-target="review-open"]').disabled);
          if (large) {
            await click(page, 'support-toggle');
            await click(page, 'support:largeText'); await click(page, 'support:largeButton');
            await click(page, 'support-toggle');
          }
          await click(page, 'review-open');
          await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
          assert(await page.evaluate(() => window.scrollY > 0));
          await click(page, 'simulate-payment');
          await page.locator('.order-feedback').waitFor();
          const feedback = await page.locator('.order-feedback').boundingBox();
          const retry = await page.locator('[data-log-target="order-result-retry"]').boundingBox();
          const bar = await page.locator('.order-actions').boundingBox();
          assert(feedback.y >= 0 && feedback.y + feedback.height <= bar.y);
          assert(retry.y >= 0 && retry.y + retry.height <= bar.y);
          assert(await page.locator('[data-log-target="order-result-retry"]').evaluate(element => {
            const bounds = element.getBoundingClientRect();
            return element.contains(document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2));
          }));
          assert.doesNotMatch(await page.locator('.order-feedback').innerText(), /서버 내부 오류/);
          if (viewport.width === 1365 && large) await screenshot(page, 'review-error-visible');
          fixture.verify(); assert.deepEqual(errors, []);
          await page.close();
        });
      }
    }
  } finally { await browser.close(); }
});
