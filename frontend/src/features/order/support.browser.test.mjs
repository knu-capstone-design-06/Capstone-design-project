// 실행 중인 Vite(개발 서버) + 외부 Playwright. 키오스크가 먼저 띄우는 화면 지원(제안·적용·되돌리기), 버튼 강조 힌트,
// 뺀 줄 되돌리기를 개발용 시험 장치(window.kioskSupportDraft, 주소의 ?support= ?preview= ?hint=)로 확인합니다.
import assert from 'node:assert/strict';
import test from 'node:test';
import { bootstrap, cartResponse, food, iced, installOrderResponses, mutation, productsResponse } from './orderApiFixture.mjs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.ORDER_BROWSER_URL ?? 'http://127.0.0.1:5173';
const channel = process.env.PLAYWRIGHT_CHANNEL ?? 'msedge';
const launchOptions = { headless: true, ...(channel === 'default' ? {} : { channel }) };
const target = (page, id) => page.locator(`[data-log-target="${id}"]`);
const decision = (session, preset, requires_confirmation = true) => ({ session_id: session, ai_available: true,
  support: { preset, requires_confirmation, decided_by: 'rule_placeholder' } });

async function open(browser, steps, query = '') {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  const fixture = await installOrderResponses(page, steps);
  await page.goto(`${url}/${query}`);
  await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
  return { page, errors, fixture };
}

test('제안을 받아들이면 크게 보기로 바꾸고 적용 안내와 [원래대로]를 보이며, 되돌리면 원래 화면으로 돌아간다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const { page, errors, fixture } = await open(browser, bootstrap('offer-accept'));
    // 카드가 나타나는 바로 그 순간에 [크게 하기]를 누릅니다(두 번 클릭 간격 안의 누름).
    const early = page.evaluate(() => new Promise(resolve => {
      const observer = new MutationObserver(() => {
        const button = document.querySelector('[data-log-target="support-offer:accept"]');
        if (button) { observer.disconnect(); button.click(); resolve(true); }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }));
    await page.evaluate(() => window.kioskSupportDraft.previewEnlargement());
    await early;
    const card = page.locator('.offer-card');
    await card.waitFor();
    assert.match(await card.innerText(), /글자와 버튼을 크게 해 드릴까요\?/);
    assert.equal(await page.locator('.kiosk.large-view').count(), 0, '나타난 직후(두 번 클릭 간격 안)의 누름은 대답이 되지 않음');
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    await target(page, 'support-offer:accept').click();
    await page.locator('.kiosk.large-view').waitFor();
    assert.equal(await page.locator('.kiosk.large-text, .kiosk.large-button').count(), 0, '크게 보기는 화면 도움의 큰 글씨·큰 버튼 설정을 켜지 않음');
    assert.equal(await card.count(), 0);
    assert.match(await page.locator('.cart-notice.is-kiosk').innerText(), /글자와 버튼을 크게 했어요/);
    await target(page, 'support-undo').click();
    assert.equal(await page.locator('.kiosk.large-view').count(), 0, '[원래대로]는 크게 보기를 끔');
    assert.equal(await target(page, 'support-undo').count(), 0);
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('거절하거나 다른 곳을 누르면 제안이 닫히고 화면은 그대로다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const { page, errors, fixture } = await open(browser, bootstrap('offer-decline'), '?preview=enlarge');
    await page.locator('.offer-card').waitFor();
    assert.match(await page.locator('.offer-card').innerText(), /글자와 버튼을 크게 해 드릴까요\?/, '일괄 확대 시안 문구');
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    await target(page, 'support-offer:decline').click();
    assert.equal(await page.locator('.offer-card').count(), 0);
    assert.equal(await page.locator('.kiosk.large-button').count(), 0);
    await page.evaluate(() => window.kioskSupportDraft.previewEnlargement());
    await page.locator('.offer-card').waitFor();
    await target(page, 'category:커피').click();
    await page.locator('.offer-card').waitFor({ state: 'detached' });
    assert.equal(await page.locator('.kiosk.large-button').count(), 0, '다른 곳을 누르면 제안만 닫힘');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('개발용 서버 응답도 네 가지 개별 설정을 확인 후 적용하고 저장하지 않는다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'apply-first';
    const { page, errors, fixture } = await open(browser, [...bootstrap(session), ...bootstrap('apply-second')], '?support=large_button&confirm=0');
    const dialog = page.locator('section.support-confirm-sheet');
    const receive = (response, sentFor) => page.evaluate(
      ({ response, sentFor }) => window.kioskSupportDraft.receive(response, sentFor), { response, sentFor });
    async function accept(question) {
      await dialog.getByRole('heading', { name: question, exact: true }).waitFor();
      await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
      await target(page, 'support-confirm:accept').click();
      await dialog.waitFor({ state: 'hidden' });
    }
    await dialog.waitFor();
    assert.equal(await page.locator('.kiosk.large-button').count(), 0, 'confirm=0도 먼저 확인');
    await accept('버튼을 크게 바꿀까요?');
    await page.locator('.kiosk.large-button').waitFor();
    assert.equal(await page.locator('.kiosk.large-text, .kiosk.large-view, .offer-card').count(), 0);

    assert.equal(await receive(decision('other-session', 'large_text')), false);
    assert.equal(await receive(decision(session, 'large_text'), { sessionId: session, screen: 'review' }), false);
    assert.equal(await receive(decision(session, 'none')), false);
    assert.equal(await receive(decision(session, 'voice_guide')), false);
    assert.equal(await receive(decision(session, 'large_button')), false, '이미 켜진 설정에는 제안하지 않음');
    assert.equal(await dialog.count(), 0);

    for (const [preset, question, selector] of [
      ['large_text', '글씨를 크게 바꿀까요?', '.kiosk.large-text'],
      ['simple_screen', '간편한 화면으로 바꿀까요?', '.kiosk.simple-screen'],
      ['step_guide', '주문 순서를 안내해 드릴까요?', '.guide'],
    ]) {
      assert.equal(await receive(decision(session, preset)), true);
      assert.equal(await page.locator(selector).count(), 0);
      await accept(question);
      await page.locator(selector).first().waitFor();
    }
    const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('kiosk-ui-settings-v1')));
    assert.equal(saved.largeText || saved.largeButton || saved.simpleScreen || saved.stepGuide, false);
    await page.evaluate(() => history.replaceState(null, '', location.pathname));
    await page.reload();
    await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
    assert.equal(await page.locator('.kiosk.large-text, .kiosk.large-button, .kiosk.simple-screen, .guide').count(), 0);
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('힌트는 이름 붙은 조작에 고리를 두고 한 줄 안내를 보이며, 그 조작을 쓰면 고리가 사라진다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'hint-ring';
    const { page, errors, fixture } = await open(browser, [...bootstrap(session), mutation(session, '/cart/items', cartResponse(session, 1, [iced()]))]);
    await target(page, 'product:americano').click();
    await page.evaluate(() => window.kioskSupportDraft.hint('option-add'));
    await page.locator('[data-log-target="cart-add"].hint-ring').waitFor();
    assert.match(await page.locator('dialog .hint-callout').innerText(), /아래 '담기'를\s+눌러 주세요/);
    const outline = await target(page, 'cart-add').evaluate(element => getComputedStyle(element).outlineWidth);
    assert.equal(outline, '6px');
    await target(page, 'cart-add').click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('.hint-ring').count(), 0, '쓴 조작의 고리는 사라짐');
    await page.evaluate(() => window.kioskSupportDraft.hint('cart-remove'));
    await page.locator('[data-log-target="cart:americano:아이스:remove"].hint-ring').waitFor();
    assert.match(await page.locator('.cart-notice.is-kiosk').innerText(), /빼려는 메뉴 옆 '삭제'를 눌러 주세요/);
    await page.evaluate(() => window.kioskSupportDraft.clear());
    assert.equal(await page.locator('.hint-ring').count(), 0);
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('뺀 줄은 다음 터치까지 제자리에 남고 [되돌리기]는 같은 메뉴를 최신 버전과 새 키로 다시 담는다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'undo-line';
    const { page, errors, fixture } = await open(browser, [...bootstrap(session),
      mutation(session, '/cart/items', cartResponse(session, 1, [iced(2)])),
      mutation(session, '/cart/items/item-iced?expected_version=1', cartResponse(session, 2), { method: 'DELETE' }),
      mutation(session, '/cart/items', cartResponse(session, 3, [iced(2)])),
      mutation(session, '/cart/items/item-iced?expected_version=3', cartResponse(session, 4), { method: 'DELETE' })]);
    const count = (method, path) => fixture.requests.filter(request => request.method === method && request.path.startsWith(`/api/v1/sessions/${session}${path}`)).length;
    // [삭제]를 250 ms 간격으로 네 번 누릅니다. 같은 자리의 [되돌리기]에 닿는 연속 누름도 보호를 연장합니다.
    const removeRepeatedly = async () => {
      const box = await target(page, 'cart:americano:아이스:remove').boundingBox();
      const point = [box.x + box.width / 2, box.y + box.height / 2];
      await page.mouse.click(...point);
      await page.waitForTimeout(250);
      await page.mouse.click(...point);
      await page.waitForTimeout(250);
      await page.mouse.click(...point);
      await page.waitForTimeout(250);
      await page.mouse.click(...point);
      const under = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('[data-log-target]')?.dataset.logTarget ?? null, point);
      assert.equal(under, 'cart:americano:아이스:undo', '[되돌리기]는 [삭제]의 자리에 섬');
      await page.locator('[data-log-target="cart:americano:아이스:undo"][data-armed="true"]').waitFor();
      assert.equal(await page.locator('.cart-removed').count(), 1, '보호 중 이어진 연속 누름은 되돌리지 않음');
    };
    await target(page, 'product:americano').click(); await target(page, 'options-increase').click(); await target(page, 'cart-add').click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    await removeRepeatedly();
    assert.equal(count('DELETE', '/cart/items/'), 1);
    assert.equal(count('POST', '/cart/items'), 1, '다시 담는 요청이 없음');
    assert.equal(await page.locator('.cart-row').count(), 0, '뺀 줄은 담은 줄로 세지 않음');
    assert.equal(await page.locator('.cart-removed').count(), 1);
    assert.match(await page.locator('.total').innerText(), /0원/, '금액은 바로 바뀜');
    await target(page, 'cart:americano:아이스:undo').click();
    await page.waitForFunction(() => document.querySelector('.total')?.innerText.includes('7,000원'));
    assert.equal(await page.locator('.cart-removed').count(), 0);
    const adds = fixture.requests.filter(request => request.method === 'POST' && request.path.endsWith('/cart/items'));
    assert.deepEqual(adds[1].body, { product_id: 'americano', temperature: 'iced', quantity: 2, expected_version: 2 });
    assert.notEqual(adds[0].key, adds[1].key);
    // 주문 확인 화면의 줄도 같습니다.
    await page.locator('[data-log-target="review-open"][data-armed="true"]').waitFor();
    await target(page, 'review-open').click();
    await removeRepeatedly();
    assert.equal(count('DELETE', '/cart/items/'), 2);
    assert.equal(count('POST', '/cart/items'), 2, '주문 확인 화면에서도 다시 담는 요청이 없음');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('직원 호출이 연결되지 않은 동안 호출 버튼과 완료 안내를 표시하지 않는다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const { page, errors, fixture } = await open(browser, bootstrap('staff-call'));
    await target(page, 'support-toggle').click();
    assert.equal(await page.locator('[data-log-target="staff-call"]').count(), 0);
    assert.doesNotMatch(await page.locator('#support-panel').innerText(), /직원을 불렀어요|호출 취소/);
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('알림은 잠깐 떴다가 스스로 닫히거나 다음 터치에 닫히고, 그 아래의 상품은 막지 않는다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'short-notice';
    const { page, errors, fixture } = await open(browser, [...bootstrap(session),
      mutation(session, '/cart/items', cartResponse(session, 1, [iced()])), mutation(session, '/cart/items', cartResponse(session, 2, [iced(2)]))]);
    // 안내 바 자리를 확보한 큰 글씨 화면은 사진 한 줄이며 알림이 그 줄 위에 뜹니다.
    await target(page, 'support-toggle').click(); await target(page, 'support:largeText').click(); await target(page, 'support-close').click();
    const notice = page.locator('.popup-place .cart-notice');
    await target(page, 'product:americano').click(); await target(page, 'cart-add').click();
    await notice.getByText('메뉴를 담았어요.').waitFor();
    const box = await notice.boundingBox();
    const card = await target(page, 'product:latte').boundingBox();
    const point = [card.x + card.width / 2, box.y + box.height / 2];
    const under = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('[data-log-target]')?.dataset.logTarget ?? null, point);
    assert.equal(under, 'product:latte', '알림 아래의 상품 줄이 누름을 받음');
    await page.mouse.click(...point);
    await page.locator('dialog[open]').waitFor();
    assert.match(await page.locator('dialog[open]').innerText(), /카페 라떼/, '알림이 떠 있어도 그 아래 상품이 눌림');
    await notice.waitFor({ state: 'hidden', timeout: 1000 });
    await target(page, 'cart-add').click();
    await notice.getByText('메뉴를 담았어요.').waitFor();
    const shown = Date.now();
    await notice.waitFor({ state: 'hidden', timeout: 5000 });
    assert(Date.now() - shown >= 2000, '터치가 없으면 2,750 ms 가까이 보인 뒤 스스로 닫힘');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('프로덕션 빌드에는 개발용 지원 시험 장치가 없다', { skip: !process.env.ORDER_PRODUCTION_URL }, async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    const fixture = await installOrderResponses(page, bootstrap('production-draft'));
    await page.goto(`${process.env.ORDER_PRODUCTION_URL}/?support=large_text&preview=enlarge&hint=cart-remove`);
    await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
    assert.equal(await page.evaluate(() => typeof window.kioskSupportDraft), 'undefined');
    assert.equal(await page.locator('.offer-card, .support-confirm-sheet').count(), 0);
    assert.equal(await page.locator('.hint-ring').count(), 0);
    fixture.verify();
  } finally { await browser.close(); }
});

test('고객이 켠 큰 버튼은 크게 보기를 받아들였다가 [원래대로]를 눌러도 그대로 남고, 큰 글씨가 켜져 있으면 제안하지 않는다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const { page, errors, fixture } = await open(browser, bootstrap('own-button'));
    await target(page, 'support-toggle').click(); await target(page, 'support:largeButton').click(); await target(page, 'support-close').click();
    await page.locator('.kiosk.large-button').waitFor();
    await page.evaluate(() => window.kioskSupportDraft.previewEnlargement());
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    await target(page, 'support-offer:accept').click();
    await page.locator('.kiosk.large-view.large-button').waitFor();
    await target(page, 'support-undo').click();
    assert.equal(await page.locator('.kiosk.large-view').count(), 0, '크게 보기만 꺼짐');
    assert.equal(await page.locator('.kiosk.large-button').count(), 1, '고객이 켠 큰 버튼은 남음');
    await page.evaluate(() => window.kioskSupportDraft.clear());
    await target(page, 'support-toggle').click(); await target(page, 'support:largeText').click(); await target(page, 'support-close').click();
    await page.evaluate(() => window.kioskSupportDraft.previewEnlargement());
    assert.equal(await page.locator('.offer-card').count(), 0, '큰 글씨(200 %)가 켜져 있으면 일괄 확대 시안을 띄우지 않음');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('제안은 처음으로 확인 창이 열린 동안 기다리고, 그사이 큰 글씨가 켜지면 버린다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'offer-wait';
    const { page, errors, fixture } = await open(browser, [...bootstrap(session), mutation(session, '/cart/items', cartResponse(session, 1, [iced()]))]);
    await target(page, 'product:americano').click(); await target(page, 'cart-add').click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    // 창이 닫힌 뒤 두 번 클릭 간격 동안 하단 바는 누름을 받지 않습니다.
    await page.locator('[data-log-target="order-restart"][data-armed="true"]').waitFor();
    await target(page, 'order-restart').click(); await page.locator('dialog[open]').waitFor();
    await page.evaluate(() => window.kioskSupportDraft.previewEnlargement());
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.offer-card').count(), 0, '처음으로 확인 창이 열린 동안 제안은 뜨지 않음');
    await page.locator('[data-log-target="order-restart-cancel"][data-armed="true"]').click();
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.offer-card').count(), 1, '창을 닫은 누름은 제안을 닫지 않음');
    await target(page, 'support-offer:decline').click();
    await target(page, 'support-toggle').click();
    await page.evaluate(() => window.kioskSupportDraft.previewEnlargement());
    await target(page, 'support:largeText').click(); await target(page, 'support-close').click();
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.offer-card').count(), 0, '기다리는 동안 큰 글씨가 켜졌으면 제안을 버림');
    assert.equal(await page.locator('.cart-notice.is-kiosk').count(), 0, '적용 알림도 없음');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('장바구니 창이 열려 있으면 빼기 힌트의 고리는 창 안의 [삭제]에 선다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'hint-sheet';
    const { page, errors, fixture } = await open(browser, [...bootstrap(session),
      mutation(session, '/cart/items', cartResponse(session, 1, [iced()])), mutation(session, '/cart/items', cartResponse(session, 2, [iced(), food]))]);
    await target(page, 'product:americano').click(); await target(page, 'cart-add').click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    await target(page, 'product:sandwich').click(); await target(page, 'cart-add').click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    await page.locator('.kiosk [data-log-target="cart-sheet-open"]').first().click();
    await page.locator('dialog.cart-sheet[open]').waitFor();
    await page.evaluate(() => window.kioskSupportDraft.hint('cart-remove'));
    await page.locator('dialog.cart-sheet[open] .hint-ring').waitFor();
    assert.equal(await page.locator('.hint-ring').count(), 1, '고리는 하나');
    assert.match(await page.locator('dialog.cart-sheet[open] .hint-ring').getAttribute('data-log-target'), /:remove$/);
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('글자 줄은 품절을 글자로 보이고 버튼 이름에 담으며, 쪽 번호는 바뀔 때 읽힌다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify({ simpleScreen: true, largeText: true })));
    const products = { ...productsResponse, products: productsResponse.products.map(row => row.product_id === 'chocolate' ? { ...row, available: false } : row) };
    const steps = bootstrap('sold-out-row'); steps[0] = { ...steps[0], body: products };
    const fixture = await installOrderResponses(page, steps);
    await page.goto(`${url}/`);
    await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
    const row = target(page, 'product:chocolate');
    assert.equal(await row.isDisabled(), true);
    assert.match(await row.innerText(), /품절/, '품절이 보이는 글자로 남음');
    assert.equal(await page.getByRole('button', { name: /초콜릿 라떼.*품절/ }).count(), 1, '버튼 이름에 품절');
    const count = page.locator('.menu-section .pager .page');
    assert.equal(await count.getAttribute('aria-live'), 'polite');
    assert.equal((await count.innerText()).trim(), '1 / 2');
    await target(page, 'menu-page:next').click();
    assert.equal((await count.innerText()).trim(), '2 / 2');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});
test('처음으로 확인 창은 어느 대답이 무엇을 지우는지 알리고, 같은 너비의 두 대답을 [처음으로] 자리 밖에 둔다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'restart-look';
    const steps = bootstrap(session); steps[2].body = cartResponse(session, 1, [iced()]);
    const { page, errors, fixture } = await open(browser, steps);
    await page.evaluate(() => document.fonts.ready);
    const dialog = page.locator('dialog[aria-labelledby="restart-title"]'), opened = page.locator('dialog[aria-labelledby="restart-title"][open]');
    const armedAnswer = id => page.locator(`[data-log-target="${id}"][data-armed="true"]`);
    const box = id => target(page, id).boundingBox();
    const openDialog = async () => {
      await page.locator('[data-log-target="order-restart"][data-armed="true"]').waitFor();
      await target(page, 'order-restart').click(); await opened.waitFor();
    };
    const apart = (a, b) => a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y;
    // 창의 안쪽 끝(테두리와 안쪽 여백 안)과 토큰 값: 대답 줄이 창의 폭을 다 쓰는지 봅니다.
    const inner = () => dialog.evaluate(element => {
      const rect = element.getBoundingClientRect(), style = getComputedStyle(element), px = name => parseFloat(style.getPropertyValue(name));
      return { left: rect.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft), right: rect.right - parseFloat(style.borderRightWidth) - parseFloat(style.paddingRight),
        top: rect.top, bottom: rect.bottom, gap: px('--gap-btn'), kiosk: px('--h-kiosk'), fits: element.scrollHeight <= element.clientHeight,
        areaTop: innerHeight - parseFloat(getComputedStyle(element.closest('.kiosk')).height), viewBottom: innerHeight };
    });
    await openDialog();
    assert.match(await dialog.innerText(), /'처음부터 주문하기'를 누르면 담은 메뉴 1개\(3,500원\)가 모두 지워져요\./);
    assert.doesNotMatch(await dialog.innerText(), /그대로예요/, '화면 도움에서 고른 설정이 없으면 설정 안내 줄을 보이지 않음');
    const frame = await dialog.boundingBox(), main = await page.locator('main').evaluate(element => {
      const rect = element.getBoundingClientRect(), style = getComputedStyle(element);
      return { left: rect.left + parseFloat(style.paddingLeft), right: rect.right - parseFloat(style.paddingRight) };
    });
    assert.equal(frame.x, main.left, '창의 왼쪽 끝 = 내용 열의 왼쪽 끝');
    assert.equal(frame.x + frame.width, main.right, '창의 오른쪽 끝 = 내용 열의 오른쪽 끝');
    let [stay, restart, opener, edge] = [await box('order-restart-cancel'), await box('order-restart-confirm'), await box('order-restart'), await inner()];
    assert.equal(stay.x, edge.left, '첫 대답의 왼쪽 끝 = 창 안쪽의 왼쪽 끝');
    assert.equal(restart.x + restart.width, edge.right, '둘째 대답의 오른쪽 끝 = 창 안쪽의 오른쪽 끝');
    assert.equal(restart.x - (stay.x + stay.width), edge.gap, '대답 사이 = 버튼 간격');
    assert.equal(stay.width, restart.width, '두 대답의 너비가 같음');
    assert.equal(stay.y, restart.y); assert.equal(stay.height, restart.height);
    assert(stay.height >= edge.kiosk, '대답 높이 = 키오스크 버튼 높이 이상');
    assert(apart(stay, opener) && apart(restart, opener), '기본 화면: 대답이 [처음으로] 자리와 겹치지 않음');
    await armedAnswer('order-restart-cancel').click(); await opened.waitFor({ state: 'hidden' });
    assert.equal(await page.locator('dialog[open]').count(), 0);

    // 큰 글씨 + 낮은 화면: 대답은 한 줄에 하나씩 창의 폭을 다 쓰고, 이때도 [처음으로] 자리 밖에 섭니다.
    await target(page, 'support-toggle').click();
    await target(page, 'support:largeText').click(); await target(page, 'support:lowScreen').click();
    await target(page, 'support-close').click();
    await openDialog();
    assert.match(await dialog.innerText(), /화면 도움에서 고른 설정은 그대로예요\./, '화면 도움에서 고른 설정이 켜져 있으면 그 설정이 남는다고 알림');
    [stay, restart, opener, edge] = [await box('order-restart-cancel'), await box('order-restart-confirm'), await box('order-restart'), await inner()];
    for (const answer of [stay, restart]) {
      assert.equal(answer.x, edge.left); assert.equal(answer.x + answer.width, edge.right, '큰 글씨: 대답이 창의 폭을 다 씀');
    }
    assert.equal(restart.y - (stay.y + stay.height), edge.gap, '위아래 대답 사이 = 버튼 간격');
    assert(apart(stay, opener) && apart(restart, opener), '큰 글씨 + 낮은 화면: 대답이 [처음으로] 자리와 겹치지 않음');
    assert.equal(edge.top, edge.areaTop, '낮은 화면: 창이 아래 조작 영역의 위 끝에서부터 섬');
    assert(edge.fits && edge.bottom <= edge.viewBottom, '낮은 화면: 창이 아래 조작 영역 안에 스크롤 없이 들어옴');
    await armedAnswer('order-restart-cancel').click();
    fixture.verify(); assert.deepEqual(errors, []);

    const empty = await open(browser, bootstrap('restart-empty'));
    await empty.page.locator('[data-log-target="order-restart"][data-armed="true"]').waitFor();
    await target(empty.page, 'order-restart').click();
    const text = await empty.page.locator('dialog[aria-labelledby="restart-title"]').innerText();
    assert.match(text, /'처음부터 주문하기'를 누르면 처음 화면으로 돌아가요\./); assert.doesNotMatch(text, /담은 메뉴|지워져요/, '담은 메뉴가 없으면 지운다는 말을 하지 않음');
    empty.fixture.verify(); assert.deepEqual(empty.errors, []);
  } finally { await browser.close(); }
});

test('처음으로 확인 창의 대답은 창이 뜬 직후의 누름을 받지 않고, 처음으로를 연달아 누른 손가락은 대답이 되지 않는다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    // 낮은 창(1080 × 560)에서는 가운데 뜨는 확인 창의 [처음부터 주문하기]가 하단 주문 바의 [처음으로] 위에 섭니다(2026-11-26 측정: 대답 y 295–383, [처음으로] y 360–432).
    const session = 'restart-twice';
    const steps = bootstrap(session); steps[2].body = cartResponse(session, 1, [iced()]);
    const page = await browser.newPage({ viewport: { width: 1080, height: 560 } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    const fixture = await installOrderResponses(page, steps);
    await page.goto(url);
    await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
    await page.evaluate(() => document.fonts.ready);
    const opened = page.locator('dialog[aria-labelledby="restart-title"][open]');
    const armed = id => page.locator(`[data-log-target="${id}"][data-armed="true"]`);
    const center = box => [box.x + box.width / 2, box.y + box.height / 2];
    const targetAt = point => page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('[data-log-target]')?.getAttribute('data-log-target'), point);
    const sessionNow = () => page.evaluate(() => window.kioskTouchLogDraft.read().serverSessionId);
    await armed('order-restart').waitFor();
    // 부하가 누름 간격을 늘리지 않도록 앱의 시간을 멈추고 직접 보냅니다.
    await page.clock.install();
    await page.clock.pauseAt(new Date(Date.now() + 1000));

    // 처음 열 때: 창이 뜬 직후에는 두 대답 모두 누름을 받지 않습니다.
    await target(page, 'order-restart').click(); await opened.waitFor();
    const [stay, restart, opener] = [await target(page, 'order-restart-cancel').boundingBox(), await target(page, 'order-restart-confirm').boundingBox(), await target(page, 'order-restart').boundingBox()];
    await page.mouse.click(...center(restart));
    await page.clock.runFor(100);
    await page.mouse.click(...center(stay));
    assert.equal(await opened.count(), 1, '창이 뜬 직후의 누름은 대답이 되지 않음'); assert.equal(await sessionNow(), session);
    // 받지 않은 누름은 보호를 다시 시작합니다: 마지막 누름에서 두 번 클릭 간격이 지나야 누름을 받습니다.
    await page.clock.runFor(450);
    assert.equal(await armed('order-restart-cancel').count(), 0, '창이 뜬 지 550ms여도 마지막 누름에서 450ms라 아직 받지 않음');
    // Esc는 보호 중에도 창을 닫습니다(새 주문을 시작하지 않는 쪽).
    await page.keyboard.press('Escape'); await opened.waitFor({ state: 'hidden' });
    assert.equal(await sessionNow(), session);

    // 같은 자리를 연달아 누름: 첫 누름이 창을 열고, 다음 누름들은 그 자리에 선 [처음부터 주문하기]에 닿습니다.
    await page.clock.runFor(501); await armed('order-restart').waitFor();
    const point = [Math.max(restart.x, opener.x) + 4, Math.max(restart.y, opener.y) + 4];
    assert(point[0] < Math.min(restart.x + restart.width, opener.x + opener.width) && point[1] < Math.min(restart.y + restart.height, opener.y + opener.height),
      '검사의 전제: 이 창 높이에서 [처음부터 주문하기]가 [처음으로] 자리와 겹침');
    await page.mouse.click(...point); await opened.waitFor();
    assert.equal(await targetAt(point), 'order-restart-confirm', '다음 누름이 닿을 자리에 [처음부터 주문하기]가 섬');
    await page.clock.runFor(250);
    await page.mouse.click(...point);
    await page.clock.runFor(250);
    await page.mouse.click(...point);
    assert.equal(await opened.count(), 1, '250ms 간격으로 이어진 누름은 대답이 되지 않아 확인 창이 그대로 열려 있음');
    assert.equal(await sessionNow(), session, '새 주문이 시작되지 않음');
    assert.match(await opened.innerText(), /담은 메뉴 1개/);
    await page.clock.runFor(501);
    await armed('order-restart-cancel').click(); await opened.waitFor({ state: 'hidden' });
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});
test('서버 제안을 받아들이면 적용 알림과 [원래대로]를 보이고, 되돌리면 키오스크가 켠 설정만 꺼진다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'apply-undo';
    const { page, errors, fixture } = await open(browser, bootstrap(session));
    await page.evaluate(() => document.fonts.ready);
    const card = page.locator('section.support-confirm-sheet');
    const shown = () => page.evaluate(() => document.querySelector('.cart-notice:not([hidden])')?.textContent.trim() ?? '');
    const receive = response => page.evaluate(value => window.kioskSupportDraft.receive(value), response);
    const helpTile = async key => {
      await target(page, 'support-toggle').click(); await target(page, `support:${key}`).click(); await target(page, 'support-close').click();
      await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    };
    // 고객이 화면 도움에서 고대비를 직접 켭니다: 직접 켠 설정만 있을 때는 되돌릴 것이 없습니다.
    await helpTile('highContrast');
    assert.equal(await target(page, 'support-undo').count(), 0, '고객이 직접 켠 설정만 있을 때는 [원래대로]가 없음');
    // 알림이 터치로 닫히는지와 시간으로 닫히는지를 가르려고 앱의 시간을 멈추고 직접 보냅니다.
    await page.clock.install();
    await page.clock.pauseAt(new Date(Date.now() + 1000));
    const accept = async question => {
      await card.getByRole('heading', { name: question, exact: true }).waitFor();
      await page.clock.runFor(501);
      await page.locator('.support-confirm-actions[data-armed="true"]').waitFor();
      await target(page, 'support-confirm:accept').click();
      await card.waitFor({ state: 'hidden' });
    };

    assert.equal(await receive(decision(session, 'large_text')), true);
    await accept('글씨를 크게 바꿀까요?');
    await page.locator('.kiosk.large-text').waitFor();
    assert.equal(await shown(), '글씨를 크게 바꿨어요.');
    await target(page, 'support-undo').waitFor();
    // [원래대로]는 [화면 도움] 옆에 같은 높이로, 버튼 간격만큼 떨어져 섭니다.
    const [help, undo, gap] = [await target(page, 'support-toggle').boundingBox(), await target(page, 'support-undo').boundingBox(),
      await page.locator('.kiosk').evaluate(element => parseFloat(getComputedStyle(element).getPropertyValue('--gap-btn')))];
    assert.equal(undo.y, help.y); assert.equal(undo.height, help.height); assert.equal(undo.x - (help.x + help.width), gap);

    // 앞의 알림이 떠 있는 동안 둘째 제안을 받아들입니다: 그 누름은 앞의 알림만 닫고, 자기가 띄운 알림은 닫지 않습니다.
    assert.equal(await receive(decision(session, 'simple_screen')), true);
    await accept('간편한 화면으로 바꿀까요?');
    await page.clock.runFor(1);
    await page.locator('.kiosk.large-text.simple-screen').waitFor();
    assert.equal(await shown(), '간편한 화면으로 바꿨어요.', '알림을 띄운 누름은 그 알림을 닫지 않음');
    // 그 뒤의 터치가 알림을 닫고(시간은 멈춰 있음) [원래대로]는 남습니다.
    await page.locator('.store-name').first().click();
    await page.clock.runFor(1);
    assert.equal(await shown(), '', '다음 터치에 알림이 닫힘');
    assert.equal(await target(page, 'support-undo').count(), 1);

    // [원래대로] 한 번이면 키오스크가 켠 설정이 모두 꺼지고, 고객이 켠 설정은 남습니다.
    await target(page, 'support-undo').click();
    await page.clock.runFor(1);
    await page.waitForFunction(() => !document.querySelector('.kiosk.large-text, .kiosk.simple-screen'));
    assert.equal(await page.locator('.kiosk.high-contrast').count(), 1, '고객이 화면 도움에서 켠 고대비는 그대로');
    assert.equal(await shown(), '바꾸기 전 화면으로 돌아갔어요.');
    assert.equal(await target(page, 'support-undo').count(), 0, '되돌린 뒤에는 [원래대로]가 없음');
    // 되돌림 알림은 시간이 지나면 닫힙니다.
    await page.clock.runFor(2751);
    assert.equal(await shown(), '', '2,750ms 뒤에 알림이 닫힘');
    assert.equal(await receive(decision(session, 'large_text')), false, '같은 세션에서 이미 답한 제안은 다시 뜨지 않음');

    // 키오스크가 켠 설정을 고객이 화면 도움에서 직접 끄면 되돌릴 것이 없습니다.
    assert.equal(await receive(decision(session, 'step_guide')), true);
    await accept('주문 순서를 안내해 드릴까요?');
    assert.equal(await shown(), '주문 순서 안내를 켰어요.');
    await target(page, 'support-undo').waitFor();
    await helpTile('stepGuide');
    assert.equal(await page.locator('.guide').count(), 0);
    assert.equal(await target(page, 'support-undo').count(), 0, '화면 도움에서 직접 끈 뒤에는 [원래대로]가 없음');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});
