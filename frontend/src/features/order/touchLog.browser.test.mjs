// 별도 검증용: 실행 중인 Vite와 외부 제공 Playwright가 필요합니다. 서비스 의존성을 추가하지 않습니다.
import assert from 'node:assert/strict';
import test from 'node:test';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.TOUCH_LOG_BROWSER_URL ?? 'http://127.0.0.1:5173';

test('로컬 로그: 중복 방지, 화면·옵션·설정, 세션 복원·분리, 실제 터치 스크롤', async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1100, height: 650 }, hasTouch: true });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft);
    const read = () => page.evaluate(() => window.kioskTouchLogDraft.read());
    const click = id => page.locator(`[data-log-target="${id}"]`).click();
    let log = await read();
    assert.equal(log.events.filter(event => event.kind === 'session_start').length, 1);
    assert.equal(log.events.filter(event => event.kind === 'screen_enter').length, 1);
    const session = log.sessionId;
    const visit = log.events.at(-1).visitId;
    await click('category:커피');
    log = await read();
    assert.equal(log.events.filter(event => event.kind === 'pointer_start').length, 1);
    assert.equal(log.events.filter(event => event.kind === 'pointer_end').length, 1);
    assert.equal(log.events.find(event => event.kind === 'category_change').visitId, visit);
    await click('product:americano');
    log = await read();
    assert.equal(log.events.find(event => event.kind === 'options_open').visitId, visit);
    // 배경 누름은 주변 후보를 기록하되 모달 뒤 상품 버튼을 후보로 선택하지 않습니다.
    await page.evaluate(() => {
      const dialog = document.querySelector('dialog');
      dialog.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 77, clientX: 1, clientY: 1 }));
      dialog.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 77, clientX: 1, clientY: 1 }));
    });
    log = await read();
    const outside = log.events.filter(event => event.kind === 'pointer_start').at(-1);
    assert.equal(outside.data.target, null);
    assert(outside.data.nearestCandidates.length > 0);
    assert(outside.data.nearestCandidates.every(candidate => !candidate.id.startsWith('product:')));
    await click('cart-add');
    await click('support-toggle');
    await click('support:largeButton');
    await click('support-toggle');
    await click('review-open');
    log = await read();
    assert(log.events.some(event => event.kind === 'ui_settings_change'));
    assert.notEqual(log.events.filter(event => event.kind === 'screen_enter').at(-1).visitId, visit);
    await page.reload();
    await page.waitForFunction(() => window.kioskTouchLogDraft);
    log = await read();
    assert.equal(log.sessionId, session);
    assert(log.events.some(event => event.kind === 'session_resume'));
    await click('review-open');
    await click('simulate-payment');
    await click('new-order');
    log = await read();
    assert.notEqual(log.sessionId, session);
    assert.equal(log.events.filter(event => event.kind === 'screen_enter' && event.sessionId === log.sessionId).length, 1);
    assert(log.events.some(event => event.kind === 'session_end' && event.sessionId === session));
    // 터치 제스처를 브라우저에 전달하여 기본 스크롤과 pointercancel을 확인합니다.
    await page.evaluate(() => window.scrollTo(0, 0));
    const cdp = await context.newCDPSession(page);
    const touch = async (type, y) => cdp.send('Input.dispatchTouchEvent', {
      type, touchPoints: type === 'touchEnd' ? [] : [{ x: 350, y, id: 1 }],
    });
    const previousCount = (await read()).events.length;
    await touch('touchStart', 550);
    for (const y of [520, 470, 420, 350, 280]) {
      await touch('touchMove', y);
      await new Promise(resolve => setTimeout(resolve, 30));
    }
    await touch('touchEnd', 280);
    await page.waitForFunction(() => window.scrollY > 0);
    log = await read();
    const gestureEvents = log.events.slice(previousCount);
    assert.equal(gestureEvents.filter(event => event.kind === 'pointer_start').length, 1);
    assert(gestureEvents.some(event => event.kind === 'pointer_end' && event.data.cancelled));
    assert(gestureEvents.some(event => event.kind === 'scroll' && event.data.after.y > 0));
    assert.deepEqual(errors, []);
    console.log('브라우저 확인: StrictMode 중복 없음, 세션·방문, 모달 주변 입력, UI 설정, 실제 터치 스크롤 통과');
  } finally { await browser.close(); }
});

test('주변 후보는 화면·컨테이너에서 보이는 부분만 사용하고 누름 표시는 보관 범위를 밝힌다', async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1100, height: 650 } });
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.kioskTouchLogDraft);
    await page.evaluate(() => window.scrollTo(0, 250));
    await page.waitForFunction(() => window.scrollY === 250);
    await page.mouse.click(890, 2);
    const outside = await page.evaluate(() => window.kioskTouchLogDraft.read().events.filter(event => event.kind === 'pointer_start').at(-1));
    assert.equal(outside.data.target, null);
    assert(outside.data.nearestCandidates.every(candidate => candidate.rect.y + candidate.rect.height > 0));
    assert(outside.data.nearestCandidates.every(candidate => candidate.id !== 'support-toggle'));
    // 중첩 컨테이너 안의 완전 가림과 부분 가림을 모두 검사합니다.
    const fixture = await page.evaluate(() => {
      document.querySelectorAll('.kiosk button, .kiosk a').forEach(element => {
        element.dataset.reviewAriaDisabled = element.getAttribute('aria-disabled') ?? '';
        element.setAttribute('aria-disabled', 'true');
      });
      const box = document.createElement('div');
      box.style.cssText = 'position:fixed;left:20px;top:100px;width:200px;height:100px;overflow:hidden;background:white;z-index:50';
      box.innerHTML = '<button data-log-target="clipped-hidden" style="position:absolute;left:0;top:-60px;width:80px;height:40px;min-height:0;padding:0">hidden</button><button data-log-target="clipped-partial" style="position:absolute;left:0;top:70px;width:80px;height:60px;min-height:0;padding:0">partial</button>';
      document.querySelector('.kiosk').append(box);
      box.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 91, clientX: 25, clientY: 105 }));
      box.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 91, clientX: 25, clientY: 105 }));
      return window.kioskTouchLogDraft.read().events.filter(event => event.kind === 'pointer_start').at(-1);
    });
    assert.equal(fixture.data.nearestCandidates[0].id, 'clipped-partial');
    assert.equal(fixture.data.nearestCandidates[0].visibleRect.height, 30);
    assert.equal(fixture.data.nearestCandidates[0].distance, 65);
    await page.evaluate(() => {
      document.querySelector('[data-log-target="clipped-partial"]').parentElement.remove();
      document.querySelectorAll('[data-review-aria-disabled]').forEach(element => {
        if (element.dataset.reviewAriaDisabled) element.setAttribute('aria-disabled', element.dataset.reviewAriaDisabled);
        else element.removeAttribute('aria-disabled');
        delete element.dataset.reviewAriaDisabled;
      });
      window.scrollTo(0, 0);
    });
    await page.getByRole('button', { name: '터치 로그 보기', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.touch-log-summary')?.innerText.includes('보관 중인 현재 세션 누름'));
    await page.evaluate(() => {
      for (let i = 0; i < 1010; i++) {
        document.scrollingElement.scrollTop = i % 2;
        document.dispatchEvent(new Event('scroll'));
      }
    });
    await page.waitForFunction(() => document.querySelector('.touch-log-summary strong')?.textContent === '1000');
    assert.match(await page.locator('.touch-log-summary').innerText(), /보관 중인 현재 세션 누름 0/);
  } finally { await browser.close(); }
});

test('개발 확인 창은 수집을 오염시키지 않고 표시 정지·재개·내보내기를 제공한다', async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft);
    const read = () => page.evaluate(() => window.kioskTouchLogDraft.read());
    const originalIds = (await read()).events.map(event => event.id);
    await page.getByRole('button', { name: '터치 로그 보기', exact: true }).click();
    await page.locator('.touch-log-events button').first().waitFor();
    await page.locator('.touch-log-events button').last().click();
    await page.locator('.touch-log-detail summary').click();
    assert.deepEqual((await read()).events.map(event => event.id), originalIds);
    await page.getByRole('button', { name: '표시 일시정지', exact: true }).click();
    const frozen = await page.locator('.touch-log-summary').innerText();
    await page.locator('[data-log-target="category:커피"]').click();
    assert((await read()).events.some(event => event.kind === 'category_change'));
    await new Promise(resolve => setTimeout(resolve, 600));
    assert.equal(await page.locator('.touch-log-summary').innerText(), frozen);
    await page.getByRole('button', { name: '표시 재개', exact: true }).click();
    await page.waitForFunction(value => document.querySelector('.touch-log-summary')?.innerText !== value, frozen);
    assert.notEqual(await page.locator('.touch-log-summary').innerText(), frozen);
    const beforeTools = (await read()).events.map(event => event.id);
    await page.locator('.touch-log-events').evaluate(element => { element.scrollTop = 100; });
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button', { name: 'JSON 내보내기', exact: true }).click();
    const download = await downloadEvent;
    assert.equal(download.suggestedFilename(), 'touch-log-draft.json');
    assert.deepEqual((await read()).events.map(event => event.id), beforeTools);
    if (process.env.TOUCH_LOG_SCREENSHOT) await page.screenshot({ path: process.env.TOUCH_LOG_SCREENSHOT });
    await page.setViewportSize({ width: 390, height: 700 });
    const bounds = await page.locator('.touch-log-panel').boundingBox();
    assert(bounds.x >= 0 && bounds.x + bounds.width <= 390 && bounds.y >= 0 && bounds.y + bounds.height <= 700);
    await page.getByRole('button', { name: '터치 로그 창 닫기', exact: true }).click();
    assert.equal(await page.locator('#touch-log-panel').count(), 0);
    if (process.env.TOUCH_LOG_PRODUCTION_URL) {
      await page.goto(process.env.TOUCH_LOG_PRODUCTION_URL);
      await page.locator('.kiosk').waitFor();
      assert.equal(await page.locator('.touch-log-tools').count(), 0);
    }
  } finally { await browser.close(); }
});
