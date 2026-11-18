// 실제 /features 요청에 서버 고정 응답을 돌려주어 수신 → 확인 → 개별 설정 적용을 검사합니다.
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { bootstrap, cartResponse, iced, installOrderResponses, mutation } from './orderApiFixture.mjs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.ORDER_BROWSER_URL ?? 'http://127.0.0.1:5173';
const channel = process.env.PLAYWRIGHT_CHANNEL ?? 'msedge';
const options = { headless: true, ...(channel === 'default' ? {} : { channel }) };
const dialog = page => page.locator('section.support-confirm-sheet');
const target = (page, name) => page.locator(`[data-log-target="${name}"]:not([data-armed="false"])`);
const decision = (preset, extra = {}) => ({ session_id: 'support-session', ai_available: true,
  support: { preset, requires_confirmation: true, decided_by: 'jev' }, ...extra });

async function open(browser, reply, settings = {}, steps = bootstrap('support-session'), address = url) {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(value => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify(value)), settings);
  const fixture = await installOrderResponses(page, steps);
  await page.route('**/api/v1/sessions/*/features', async route => {
    const body = route.request().postDataJSON(); requests.push(body);
    const response = await reply(route, requests.length);
    if (response) await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response) }).catch(() => {});
  });
  await page.goto(address);
  await target(page, 'product:americano').waitFor();
  await page.waitForFunction(() => !document.querySelector('[data-log-target="product:americano"]').disabled);
  return { page, requests, fixture, errors };
}

async function answer(page, action) {
  await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
  await target(page, `support-confirm:${action}`).click();
  await dialog(page).waitFor({ state: 'hidden' });
}

for (const [name, settings] of [
  ['기본', {}], ['큰 버튼', { largeButton: true }], ['큰 글씨·큰 버튼', { largeText: true, largeButton: true }],
  ['낮은 화면·확대·고대비', { lowScreen: true, largeText: true, largeButton: true, highContrast: true }],
]) test(`${name}: 제안은 메뉴 밖의 전용 자리에 보이고 도착 전후 메뉴 위치를 유지한다`, async () => {
  const browser = await chromium.launch(options);
  try {
    const { page, fixture, errors } = await open(browser, async () => decision('none'), settings);
    await page.waitForTimeout(100);
    const positions = () => page.locator('.product').evaluateAll(elements => elements.map(element => {
      const { x, y, width, height } = element.getBoundingClientRect(); return { x, y, width, height };
    }));
    const before = await positions();
    const preset = settings.largeText ? 'step_guide' : 'large_text';
    await page.evaluate(response => window.kioskSupportDraft.receive(response), decision(preset));
    await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
    assert.deepEqual(await positions(), before, '제안이 나타나도 상품이 움직이지 않음');
    const card = await dialog(page).boundingBox(), main = await page.locator('main').boundingBox();
    assert(card.y >= main.y + main.height, '안내 바가 상품 목록·분류·쪽 넘김·장바구니 영역 밖에 있음');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight), true);
    assert.equal(await page.locator(':modal').count(), 0);
    await answer(page, 'decline'); fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

for (const action of ['product', 'category', 'cart', 'review']) test(`제안 중 ${action}: 바깥 조작을 첫 누름에 실행하고 설정은 유지한다`, async () => {
  const browser = await chromium.launch(options);
  try {
    const steps = bootstrap('support-session');
    steps[2].body = cartResponse('support-session', 1, [iced()]);
    if (action === 'cart') steps.push(mutation('support-session', '/cart/items/item-iced', cartResponse('support-session', 2, [iced(2)]), { method: 'PATCH' }));
    const { page, fixture, errors } = await open(browser, async () => decision('large_text'), {}, steps);
    await target(page, 'product:americano').focus();
    await dialog(page).waitFor();
    assert.equal(await target(page, 'product:americano').evaluate(element => element === document.activeElement), true, '제안 도착 전의 초점 유지');
    assert.equal(await page.locator(':modal').count(), 0);
    await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
    if (action === 'product') {
      await target(page, 'product:americano').click();
      await page.locator('dialog.option-sheet[open]').waitFor();
    } else if (action === 'category') {
      await target(page, 'category:커피').click();
      assert.equal(await target(page, 'category:커피').getAttribute('aria-pressed'), 'true');
    } else if (action === 'cart') {
      await target(page, 'cart:americano:아이스:increase').click();
      await page.waitForFunction(() => document.querySelector('.total')?.textContent.includes('7,000원'));
      assert.equal(fixture.requests.filter(request => request.method === 'PATCH').length, 1);
    } else {
      await target(page, 'review-open').click();
      await target(page, 'review-back').waitFor();
    }
    assert.equal(await dialog(page).count(), 0);
    assert.equal(await page.locator('.kiosk.large-text').count(), 0, '바깥 조작을 제안 수락으로 취급하지 않음');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('제안 직후의 수락·Escape·바깥 누름은 제안에 답하지 않고 기존 화면의 조작은 가능하다', async () => {
  const browser = await chromium.launch(options);
  try {
    const { page, fixture, errors } = await open(browser, async () => decision('none'));
    await page.evaluate(() => {
      window.kioskSupportDraft.receive({ session_id: 'support-session', ai_available: true,
        support: { preset: 'large_text', requires_confirmation: true, decided_by: 'jev' } });
      return new Promise(resolve => {
        const observer = new MutationObserver(() => {
          if (!document.querySelector('.support-confirm-sheet')) return;
          observer.disconnect();
          document.querySelector('[data-log-target="support-confirm:accept"]').click();
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
          resolve();
        });
        observer.observe(document.body, { childList: true, subtree: true });
      });
    });
    await dialog(page).waitFor();
    assert.equal(await page.locator('.kiosk.large-text').count(), 0);
    await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
    await page.keyboard.press('Escape');
    await dialog(page).waitFor({ state: 'hidden' });
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

for (const [preset, css, key] of [
  ['large_text', 'large-text', 'largeText'], ['large_button', 'large-button', 'largeButton'],
  ['simple_screen', 'simple-screen', 'simpleScreen'], ['step_guide', '', 'stepGuide'],
]) test(`${preset}: 서버 제안을 확인한 뒤 해당 설정만 켜고 자동 설정을 저장하지 않는다`, async () => {
  const browser = await chromium.launch(options);
  try {
    const steps = bootstrap('support-session'); steps[2].body = cartResponse('support-session', 1, [iced(2)]);
    const { page, requests, fixture, errors } = await open(browser, async () => decision(preset), {}, steps);
    await dialog(page).waitFor();
    assert.equal(await dialog(page).getAttribute('aria-labelledby'), 'support-confirm-title');
    assert.equal(await dialog(page).evaluate(element => element.contains(document.activeElement)), false, '제안이 주문 조작의 초점을 가져가지 않음');
    assert.equal(await page.locator(':modal').count(), 0, '제안 뒤의 화면을 비활성화하지 않음');
    assert.deepEqual(Object.keys(requests[0]).sort(), ['screen_id', 'touch', 'vision', 'window_end', 'window_start']);
    assert.equal(requests[0].screen_id, 'menu'); assert.equal(requests[0].vision, null);
    assert.equal(Date.parse(requests[0].window_end) - Date.parse(requests[0].window_start), 2000);
    assert.deepEqual(Object.keys(requests[0].touch).sort(), ['back_count', 'dwell_ms', 'miss_tap_count', 'repeat_tap_count', 'tap_count']);
    assert(Object.values(requests[0].touch).every(value => Number.isSafeInteger(value) && value >= 0));
    if (process.env.SUPPORT_SCREENSHOT_DIR && preset === 'large_text') {
      await mkdir(process.env.SUPPORT_SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({ path: `${process.env.SUPPORT_SCREENSHOT_DIR}/backend-support-confirm.png`, fullPage: true });
    }
    await answer(page, 'accept');
    if (css) await page.locator(`.kiosk.${css}`).waitFor();
    else await page.locator('.guide').first().waitFor();
    for (const other of ['large-text', 'large-button', 'simple-screen']) {
      assert.equal(await page.locator(`.kiosk.${other}`).count(), other === css ? 1 : 0);
    }
    assert.equal(await page.locator('.kiosk.large-view').count(), 0, '개발용 일괄 확대를 사용하지 않음');
    assert.equal(await page.evaluate(key => JSON.parse(localStorage.getItem('kiosk-ui-settings-v1'))[key], key), false);
    assert.equal(fixture.requests.length, 3, '서버 장바구니 변경 없이 설정만 적용');
    if (process.env.SUPPORT_SCREENSHOT_DIR && preset === 'large_text') await page.screenshot({ path: `${process.env.SUPPORT_SCREENSHOT_DIR}/backend-support-large-text.png`, fullPage: true });
    await page.waitForTimeout(2300);
    assert.equal(await dialog(page).count(), 0, '같은 제안을 반복해서 띄우지 않음');
    fixture.verify(); assert.deepEqual(errors, []); await page.close();
  } finally { await browser.close(); }
});

test('분류 연속 터치와 주문 확인·뒤로가기를 이어지는 구간에 세고 판단 층 화면 ID를 보낸다', async () => {
  const browser = await chromium.launch(options);
  try {
    const steps = bootstrap('support-session');
    steps[2].body = cartResponse('support-session', 1, [iced()]);
    const { page, requests, fixture, errors } = await open(browser, async () => decision('none'), {}, steps);
    const featureRequest = predicate => page.waitForRequest(req => req.url().endsWith('/features') && predicate(req.postDataJSON()));
    await featureRequest(() => true);
    // 2초보다 짧은 간격으로 2초 이상 계속 바꿉니다. 전송 타이머를 매번 다시 시작하면 누름을 보낼 수 없습니다.
    for (let i = 0; i < 6; i++) {
      await target(page, i % 2 === 0 ? 'category:커피' : 'category:전체').click();
      await page.waitForTimeout(450);
    }
    assert(requests.some(body => body.screen_id === 'menu' && body.touch.tap_count > 0), '탐색 중에도 통계가 나감');
    const review = featureRequest(body => body.screen_id === 'review');
    await target(page, 'review-open').click();
    await review;
    const back = featureRequest(body => body.screen_id === 'menu' && body.touch.back_count === 1);
    await target(page, 'review-back').click();
    await back;
    await featureRequest(() => true);
    assert.equal(requests.reduce((sum, body) => sum + body.touch.tap_count, 0), 8, '분류 6회·주문 확인 1회·뒤로가기 1회를 각각 한 번만 집계');
    assert.equal(requests.reduce((sum, body) => sum + body.touch.back_count, 0), 1);
    assert.deepEqual([...new Set(requests.map(body => body.screen_id))], ['menu', 'review']);
    for (let i = 1; i < requests.length; i++) assert.equal(requests[i].window_start, requests[i - 1].window_end);
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('거절한 제안은 반복하지 않고 다른 설정의 제안은 계속 받을 수 있다', async () => {
  const browser = await chromium.launch(options);
  try {
    let preset = 'large_text';
    const { page, fixture, errors } = await open(browser, async () => decision(preset));
    await dialog(page).waitFor(); await answer(page, 'decline');
    await page.waitForTimeout(2300); assert.equal(await dialog(page).count(), 0);
    assert.equal(await page.locator('.kiosk.large-text').count(), 0);
    preset = 'large_button'; await dialog(page).waitFor(); await answer(page, 'accept');
    await page.locator('.kiosk.large-button').waitFor();
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('배경·Escape는 같은 화면 상태에서만 제안을 숨기고 명시적 거절은 화면 상태가 바뀌어도 유지한다', async () => {
  const browser = await chromium.launch(options);
  try {
    const { page, fixture, errors } = await open(browser, async () => decision('large_text'));
    async function noOfferAfterNextResponse() {
      await page.waitForResponse(response => response.url().endsWith('/features') && response.ok());
      await page.waitForTimeout(100);
      assert.equal(await dialog(page).count(), 0);
      assert.equal(await page.locator('.kiosk.large-text').count(), 0);
    }
    await dialog(page).waitFor();
    await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
    await page.mouse.click(15, 15);
    await dialog(page).waitFor({ state: 'hidden' });
    await noOfferAfterNextResponse();

    await target(page, 'category:커피').click();
    await dialog(page).waitFor();
    await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
    await page.keyboard.press('Escape');
    await dialog(page).waitFor({ state: 'hidden' });
    await noOfferAfterNextResponse();

    await target(page, 'category:전체').click();
    await dialog(page).waitFor();
    await answer(page, 'decline');
    await target(page, 'category:커피').click();
    await noOfferAfterNextResponse();
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('none·AI 불가·다른 세션·음성 제안·잘못된 응답은 적용하지 않고 false 확인 플래그도 사용자에게 묻는다', async () => {
  const browser = await chromium.launch(options);
  try {
    const responses = [decision('none'), decision('large_text', { ai_available: false }), decision('large_text', { session_id: 'old' }),
      decision('voice_guide'), { ...decision('large_text'), support: { preset: 'large_text' } },
      decision('step_guide', { support: { preset: 'step_guide', requires_confirmation: false, decided_by: 'jev' } })];
    const { page, requests, fixture, errors } = await open(browser, async (_, count) => responses[Math.min(count - 1, responses.length - 1)]);
    await dialog(page).waitFor({ timeout: 25000 });
    assert.equal(requests.length, 6); assert.match(await dialog(page).innerText(), /주문 순서/);
    assert.equal(await page.locator('.guide').count(), 0);
    await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
    await page.keyboard.press('Escape'); await dialog(page).waitFor({ state: 'hidden' });
    assert.equal(await page.locator('.guide').count(), 0); fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('다른 창을 조작하는 동안 제안은 띄우지 않으며 이전 화면의 늦은 응답을 버린다', async () => {
  const browser = await chromium.launch(options);
  try {
    let release, started;
    const requestStarted = new Promise(resolve => { started = resolve; });
    let useDelayed = true;
    const { page, fixture, errors } = await open(browser, async () => {
      if (useDelayed) { started(); await new Promise(resolve => { release = resolve; }); return decision('large_text'); }
      return decision('large_button');
    });
    await requestStarted;
    await target(page, 'product:americano').click();
    release(); await page.waitForTimeout(300);
    assert.equal(await dialog(page).count(), 0); assert.equal(await page.locator('.kiosk.large-text').count(), 0);
    useDelayed = false;
    await page.keyboard.press('Escape');
    await dialog(page).waitFor(); assert.match(await dialog(page).innerText(), /버튼/);
    await answer(page, 'decline'); fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('큰 글씨·큰 버튼·낮은 화면에서도 확인 팝업과 두 대답을 화면 안에 배치한다', async () => {
  const browser = await chromium.launch(options);
  try {
    const { page, fixture, errors } = await open(browser, async () => decision('step_guide'), { largeText: true, largeButton: true, lowScreen: true });
    await dialog(page).waitFor();
    await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
    const bounds = await dialog(page).boundingBox();
    assert(bounds.y >= 768 && bounds.y + bounds.height <= 1920);
    for (const action of ['accept', 'decline']) {
      const box = await target(page, `support-confirm:${action}`).boundingBox();
      assert(box.x >= 0 && box.x + box.width <= 1080 && box.y >= 768 && box.y + box.height <= 1920);
      assert(box.height >= 96);
      assert(box.y >= bounds.y && box.y + box.height <= bounds.y + bounds.height, '두 대답이 카드 안에서 잘리지 않음');
      assert.equal(await target(page, `support-confirm:${action}`).evaluate(element => {
        const box = element.getBoundingClientRect();
        return element.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2));
      }), true, '카드를 스크롤하지 않아도 대답을 누를 수 있음');
    }
    if (process.env.SUPPORT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SUPPORT_SCREENSHOT_DIR}/backend-support-low-large.png`, fullPage: true });
    await answer(page, 'accept'); fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('새 서버 세션에서는 자동 적용을 해제하고 같은 종류의 제안을 다시 확인한다', async () => {
  const browser = await chromium.launch(options);
  try {
    const { page, fixture, errors } = await open(browser, async route => decision('large_text', { session_id: new URL(route.request().url()).pathname.split('/').at(-2) }), {}, [...bootstrap('support-session'), ...bootstrap('new-session')]);
    await dialog(page).waitFor(); await answer(page, 'accept');
    await target(page, 'order-restart').click();
    await target(page, 'order-restart-confirm').click();
    await page.waitForFunction(() => !document.querySelector('.kiosk.large-text'));
    await dialog(page).waitFor(); await answer(page, 'decline'); fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('페이지를 숨기면 요청을 취소하고 늦은 제안은 버린 뒤 새 구간에서 재개한다', async () => {
  const browser = await chromium.launch(options);
  try {
    let started, release;
    const sent = new Promise(resolve => { started = resolve; });
    const { page, fixture, errors } = await open(browser, async (_, count) => {
      if (count === 1) { started(); await new Promise(resolve => { release = resolve; }); return decision('large_text'); }
      return decision('step_guide');
    });
    await sent;
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    release(); await page.waitForTimeout(300);
    assert.equal(await dialog(page).count(), 0);
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await dialog(page).waitFor(); assert.match(await dialog(page).innerText(), /주문 순서/);
    await answer(page, 'decline'); fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('전송 오류로 주문을 막지 않고 410 이후에는 화면을 바꿔도 재전송하지 않는다', async () => {
  const browser = await chromium.launch(options);
  try {
    const { page, requests, fixture, errors } = await open(browser, async (route, count) => {
      if (count === 1) await route.abort('failed');
      else await route.fulfill({ status: 410, contentType: 'application/json', body: JSON.stringify({ detail: 'Session ended' }) });
    });
    await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]').disabled === false);
    await page.waitForTimeout(6500);
    assert.equal(requests.length, 2); assert.equal(await dialog(page).count(), 0);
    await page.getByRole('button', { name: '커피', exact: true }).click();
    await page.waitForTimeout(2500); assert.equal(requests.length, 2);
    await target(page, 'product:americano').click();
    await page.locator('dialog.option-sheet[open]').waitFor();
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('개발 샘플은 서버 특징을 전송하지 않는다', { skip: !process.env.ORDER_SAMPLE_BROWSER_URL }, async () => {
  const browser = await chromium.launch(options);
  try {
    const { page, requests, fixture, errors } = await open(browser, async () => decision('large_text'), {}, [], process.env.ORDER_SAMPLE_BROWSER_URL);
    await page.waitForTimeout(4500); assert.equal(requests.length, 0); assert.equal(await dialog(page).count(), 0);
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('배포 빌드에서도 서버 제안 확인 후 적용하고 개발용 시험 장치는 노출하지 않는다', { skip: !process.env.ORDER_PRODUCTION_URL }, async () => {
  const browser = await chromium.launch(options);
  try {
    const { page, fixture, errors } = await open(browser, async () => decision('simple_screen'), {}, bootstrap('support-session'), process.env.ORDER_PRODUCTION_URL);
    await dialog(page).waitFor();
    assert.equal(await page.evaluate(() => typeof window.kioskSupportDraft), 'undefined');
    await answer(page, 'accept'); await page.locator('.kiosk.simple-screen').waitFor();
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});
