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
