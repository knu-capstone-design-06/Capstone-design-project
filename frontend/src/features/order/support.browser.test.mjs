// 실행 중인 Vite(개발 서버) + 외부 Playwright. 키오스크가 먼저 띄우는 화면 지원(제안·적용·되돌리기), 버튼 강조 힌트,
// 뺀 줄 되돌리기를 개발용 시험 장치(window.kioskSupportDraft, 주소의 ?support= ?hint=)로 확인합니다.
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
    await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('offer-accept', 'large_text'));
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
    // 고객이 큰 글씨를 켜면 큰 글씨가 앞서 크게 보기가 적용되지 않으므로 [원래대로]도 없고, 끄면 다시 섭니다.
    await target(page, 'support-toggle').click(); await target(page, 'support:largeText').click(); await target(page, 'support-close').click();
    assert.equal(await target(page, 'support-undo').count(), 0, '큰 글씨가 켜져 있으면 [원래대로]가 없음');
    await target(page, 'support-toggle').click(); await target(page, 'support:largeText').click(); await target(page, 'support-close').click();
    await target(page, 'support-undo').waitFor();
    await target(page, 'support-undo').click();
    assert.equal(await page.locator('.kiosk.large-view').count(), 0, '[원래대로]는 크게 보기를 끔');
    assert.equal(await target(page, 'support-undo').count(), 0);
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('[크게 하기]를 250 ms 간격으로 두 번 눌러도 카드가 사라진 자리의 상품은 두 번 클릭 간격 동안 누름을 받지 않는다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const { page, errors, fixture } = await open(browser, bootstrap('offer-repeat'));
    await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('offer-repeat', 'large_text'));
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    const box = await target(page, 'support-offer:accept').boundingBox();
    const point = [box.x + box.width / 2, box.y + box.height / 2];
    await page.mouse.click(...point);
    await page.waitForTimeout(250);
    await page.mouse.click(...point);
    await page.locator('.kiosk.large-view').waitFor();
    assert.equal(await page.locator('dialog[open]').count(), 0, '두 번 클릭 간격 안의 둘째 누름은 상품 옵션 창을 열지 않음');
    const under = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('[data-log-target]')?.dataset.logTarget ?? null, point);
    assert.match(under ?? '', /^product:/, '카드가 사라진 자리에는 상품이 섬');
    await page.locator(`[data-log-target="${under}"][data-armed="true"]`).waitFor();
    assert.equal(await page.locator('dialog[open]').count(), 0);
    await page.mouse.click(...point);
    await page.locator('dialog[open]').waitFor();
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('거절하거나 다른 곳을 누르면 제안이 닫히고 화면은 그대로다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const { page, errors, fixture } = await open(browser, bootstrap('offer-decline'), '?support=large_button');
    await page.locator('.offer-card').waitFor();
    assert.match(await page.locator('.offer-card').innerText(), /글자와 버튼을 크게 해 드릴까요\?/, '큰 버튼 판단도 크게 보기로 묶음');
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    await target(page, 'support-offer:decline').click();
    assert.equal(await page.locator('.offer-card').count(), 0);
    assert.equal(await page.locator('.kiosk.large-button').count(), 0);
    await page.evaluate(() => window.kioskSupportDraft.receive({ session_id: window.kioskTouchLogDraft.read().serverSessionId, ai_available: true,
      support: { preset: 'large_button', requires_confirmation: true, decided_by: 'rule_placeholder' } }));
    await page.locator('.offer-card').waitFor();
    // 카드가 뜬 뒤 두 번 클릭 간격 안의 다른 곳 누름으로는 닫히지 않습니다(PR #87 리뷰: 뜨고 500 ms 안에 분류 탭을 누르면 바로 닫혔음).
    await target(page, 'category:커피').click();
    assert.equal(await page.locator('.offer-card').count(), 1, '뜬 직후(두 번 클릭 간격 안)의 다른 곳 누름은 카드를 닫지 않음');
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    assert.equal(await page.locator('.offer-card').count(), 1);
    await target(page, 'category:커피').click();
    await page.locator('.offer-card').waitFor({ state: 'detached' });
    assert.equal(await page.locator('.kiosk.large-button').count(), 0, '다른 곳을 누르면 제안만 닫힘');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('확인 없이 적용한 지원은 저장하지 않아 새로고침하면 끝나고, 늦거나 쓸 수 없는 판단은 무시한다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const { page, errors, fixture } = await open(browser, [...bootstrap('apply-first'), ...bootstrap('apply-second')]);
    const stale = await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('other-session', 'large_text'));
    assert.deepEqual(stale, { kind: 'ignore', reason: 'stale_session' });
    const none = await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('apply-first', 'none'));
    assert.deepEqual(none, { kind: 'ignore', reason: 'none' });
    const noCopy = await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('apply-first', 'simple_screen'));
    assert.deepEqual(noCopy, { kind: 'ignore', reason: 'no_copy' });
    assert.equal(await page.locator('.offer-card').count(), 0);
    const applied = await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('apply-first', 'large_text', false));
    assert.equal(applied.kind, 'apply');
    await page.locator('.kiosk.large-view').waitFor();
    assert.match(await page.locator('.cart-notice.is-kiosk').innerText(), /글자와 버튼을 크게 했어요/);
    const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('kiosk-ui-settings-v1')));
    assert.equal(saved.largeText || saved.largeButton || 'largeView' in saved, false, '키오스크가 켠 크게 보기는 저장하지 않음');
    await page.reload();
    await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
    assert.equal(await page.locator('.kiosk.large-view').count(), 0, '새로고침하면 끝남');
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
    // [삭제]를 250 ms 간격으로 두 번 누릅니다(PR #87 리뷰의 재현). 둘째 누름은 같은 자리에 선 [되돌리기]에 닿지만 두 번 클릭 간격 안이라 받지 않습니다.
    const removeTwice = async () => {
      const box = await target(page, 'cart:americano:아이스:remove').boundingBox();
      const point = [box.x + box.width / 2, box.y + box.height / 2];
      await page.mouse.click(...point);
      await page.waitForTimeout(250);
      await page.mouse.click(...point);
      const under = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('[data-log-target]')?.dataset.logTarget ?? null, point);
      assert.equal(under, 'cart:americano:아이스:undo', '[되돌리기]는 [삭제]의 자리에 섬');
      await page.locator('[data-log-target="cart:americano:아이스:undo"][data-armed="true"]').waitFor();
      assert.equal(await page.locator('.cart-removed').count(), 1, '두 번 클릭 간격 안의 둘째 누름은 되돌리지 않음');
    };
    await target(page, 'product:americano').click(); await target(page, 'options-increase').click(); await target(page, 'cart-add').click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    await removeTwice();
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
    await removeTwice();
    assert.equal(count('DELETE', '/cart/items/'), 2);
    assert.equal(count('POST', '/cart/items'), 2, '주문 확인 화면에서도 다시 담는 요청이 없음');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('직원 부르기는 화면 도움 안의 한 줄이며 누르면 준비 중 팝업이 뜨고 [확인]·Esc·어두운 곳 누름이나 화면 도움이 닫힐 때 닫힌다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const { page, errors, fixture } = await open(browser, bootstrap('staff-call'));
    assert.equal(await page.locator('.entry-row [data-log-target="staff-call"]').count(), 0, '[화면 도움] 줄에는 직원 호출이 없음');
    await target(page, 'support-toggle').click();
    const call = page.locator('#support-panel [data-log-target="staff-call"]');
    const popup = page.locator('dialog.staff-popup[open]'), sheet = page.locator('dialog#support-panel[open]');
    const focused = () => page.evaluate(() => document.activeElement?.dataset.logTarget);
    const lastPress = () => page.evaluate(() => window.kioskTouchLogDraft.read().events.filter(event => event.kind === 'pointer_start').at(-1).data);
    for (const way of ['확인', 'Esc', '어두운 곳']) {
      await call.click();
      await popup.waitFor();
      assert.equal(await page.getByRole('dialog', { name: '직원 호출은 아직 준비 중이에요' }).count(), 1, '팝업의 이름은 제목');
      assert.equal(await target(page, 'staff-call-close').innerText(), '확인');
      assert.equal(await focused(), 'staff-call-close', '열리면 초점은 [확인]');
      assert.equal(await call.innerText(), '직원 부르기', '누른 뒤에도 이름은 그대로');
      assert.equal(await call.getAttribute('aria-pressed'), null, '호출 상태를 두지 않음');
      assert.equal(await page.locator('#support-panel [role="status"]').count(), 0, '불렀다는 알림을 두지 않음');
      if (way === '확인') {
        await target(page, 'staff-call-close').click();
        assert.equal((await lastPress()).target?.id, 'staff-call-close');
      } else if (way === 'Esc') await page.keyboard.press('Escape');
      else {
        // 팝업 아래로 가려진 [직원 부르기] 위의 어두운 곳을 누릅니다. 가까운 후보는 팝업 안에서만 찾습니다.
        const box = await call.boundingBox();
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        const press = await lastPress();
        assert.equal(press.target, null, '팝업만 닫는 누름은 대상 밖 누름으로 기록');
        assert.deepEqual(press.nearestCandidates.map(candidate => candidate.id), ['staff-call-close'], '가려진 화면 도움의 버튼은 후보가 아님');
      }
      await popup.waitFor({ state: 'detached' });
      assert.equal(await sheet.count(), 1, `${way}: 팝업만 닫히고 화면 도움은 남음`);
      assert.equal(await focused(), 'staff-call', `${way}: 초점은 [직원 부르기]로 돌아감`);
    }
    // Esc를 두 번 누르면 팝업, 그다음 화면 도움이 닫힙니다.
    await call.click(); await popup.waitFor();
    await page.keyboard.press('Escape'); await popup.waitFor({ state: 'detached' });
    assert.equal(await sheet.count(), 1);
    await page.keyboard.press('Escape'); await sheet.waitFor({ state: 'detached' });
    // 낮은 화면과 크게 보기에서도 팝업은 화면 안(낮은 화면은 아래 조작 영역 안)에 뜨고 [확인]을 누를 수 있습니다.
    for (const mode of ['낮은 화면', '크게 보기']) {
      if (mode === '크게 보기') {
        await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('staff-call', 'large_text', false));
        await page.locator('.kiosk.large-view').waitFor();
      }
      await target(page, 'support-toggle').click(); await sheet.waitFor();
      if (mode === '낮은 화면') await target(page, 'support:lowScreen').click();
      await call.click(); await popup.waitFor();
      const area = await page.locator('.kiosk').boundingBox(), box = await popup.boundingBox(), button = await target(page, 'staff-call-close').boundingBox();
      assert(box.x >= 0 && box.x + box.width <= 1080 && box.y >= area.y && box.y + box.height <= 1920, `${mode}: 팝업이 화면 안에 섬`);
      assert(button.x >= box.x && button.x + button.width <= box.x + box.width && button.y + button.height <= box.y + box.height, `${mode}: [확인]이 팝업 안에 섬`);
      await target(page, 'staff-call-close').click(); await popup.waitFor({ state: 'detached' });
      if (mode === '낮은 화면') await target(page, 'support:lowScreen').click();
      await target(page, 'support-close').click(); await sheet.waitFor({ state: 'detached' });
    }
    // 화면 도움이 코드에서 닫혀도 팝업이 함께 닫히고 초점은 [화면 도움]으로 갑니다.
    await target(page, 'support-toggle').click(); await sheet.waitFor();
    await call.click(); await popup.waitFor();
    await page.evaluate(() => document.querySelector('#support-panel').close());
    await popup.waitFor({ state: 'detached' });
    assert.equal(await sheet.count(), 0);
    assert.equal(await focused(), 'support-toggle', '시트와 함께 닫히면 초점은 [화면 도움]');
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('알림은 잠깐 떴다가 스스로 닫히거나 다음 터치에 닫히고, 그 아래의 상품은 막지 않는다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const session = 'short-notice';
    const { page, errors, fixture } = await open(browser, [...bootstrap(session),
      mutation(session, '/cart/items', cartResponse(session, 1, [iced()])), mutation(session, '/cart/items', cartResponse(session, 2, [iced(2)]))]);
    // 큰 글씨: 한 쪽에 사진 카드 2 × 2라 알림이 마지막 줄(레몬 티, 초콜릿 라떼) 위에 뜹니다.
    await target(page, 'support-toggle').click(); await target(page, 'support:largeText').click(); await target(page, 'support-close').click();
    const notice = page.locator('.popup-place .cart-notice');
    await target(page, 'product:americano').click(); await target(page, 'cart-add').click();
    await notice.getByText('메뉴를 담았어요.').waitFor();
    const box = await notice.boundingBox();
    const card = await target(page, 'product:chocolate').boundingBox();
    const point = [card.x + card.width / 2, box.y + box.height / 2];
    const under = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('[data-log-target]')?.dataset.logTarget ?? null, point);
    assert.equal(under, 'product:chocolate', '알림 아래의 상품 줄이 누름을 받음');
    await page.mouse.click(...point);
    await page.locator('dialog[open]').waitFor();
    assert.match(await page.locator('dialog[open]').innerText(), /초콜릿 라떼/, '알림이 떠 있어도 그 아래 상품이 눌림');
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
    await page.goto(`${process.env.ORDER_PRODUCTION_URL}/?support=large_text&hint=cart-remove`);
    await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
    assert.equal(await page.evaluate(() => typeof window.kioskSupportDraft), 'undefined');
    assert.equal(await page.locator('.offer-card').count(), 0);
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
    await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('own-button', 'large_text'));
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    await target(page, 'support-offer:accept').click();
    await page.locator('.kiosk.large-view.large-button').waitFor();
    await target(page, 'support-undo').click();
    assert.equal(await page.locator('.kiosk.large-view').count(), 0, '크게 보기만 꺼짐');
    assert.equal(await page.locator('.kiosk.large-button').count(), 1, '고객이 켠 큰 버튼은 남음');
    await page.evaluate(() => window.kioskSupportDraft.clear());
    await target(page, 'support-toggle').click(); await target(page, 'support:largeText').click(); await target(page, 'support-close').click();
    const ignored = await page.evaluate(response => window.kioskSupportDraft.receive(response), decision('own-button', 'large_button'));
    assert.deepEqual(ignored, { kind: 'ignore', reason: 'already_on' }, '큰 글씨(200 %)가 켜져 있으면 제안하지 않음');
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
    await page.evaluate(response => window.kioskSupportDraft.receive(response), decision(session, 'large_text'));
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.offer-card').count(), 0, '처음으로 확인 창이 열린 동안 제안은 뜨지 않음');
    await target(page, 'order-restart-cancel').click();
    await page.locator('.offer-card[data-armed="true"]').waitFor();
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.offer-card').count(), 1, '창을 닫은 누름은 제안을 닫지 않음');
    await target(page, 'support-offer:decline').click();
    await target(page, 'support-toggle').click();
    await page.evaluate(response => window.kioskSupportDraft.receive(response), decision(session, 'large_text'));
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
