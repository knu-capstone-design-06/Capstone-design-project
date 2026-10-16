// 별도 검증용: 실행 중인 Vite와 외부 제공 Playwright가 필요합니다. 서비스 의존성을 추가하지 않습니다.
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { bootstrap, cartResponse, iced, installOrderResponses, mutation, orderResponse } from './orderApiFixture.mjs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.TOUCH_LOG_BROWSER_URL ?? 'http://127.0.0.1:5173';
const channel = process.env.PLAYWRIGHT_CHANNEL ?? 'msedge';
const launchOptions = { headless: true, ...(channel === 'default' ? {} : { channel }) };

test('원시 요약의 대상·종료 기록과 재방문 표시를 확인하고 새 세션은 이전 입력을 제외한다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    const first = bootstrap('summary-first'); first[2].body = cartResponse('summary-first', 1, [iced()]);
    const responses = await installOrderResponses(page, [...first, ...bootstrap('summary-second')]);
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft?.read().serverSessionId === 'summary-first');
    await page.locator('[data-log-target="category:커피"]').click();
    await page.evaluate(() => {
      const root = document.querySelector('.kiosk');
      const emit = (element, type, pointerId) => element.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerId, clientX: 1, clientY: 1 }));
      emit(root, 'pointerdown', 200); emit(root, 'pointerup', 200);
      const disabled = document.createElement('button'); disabled.disabled = true; root.append(disabled);
      emit(disabled, 'pointerdown', 201); emit(disabled, 'pointerup', 201); disabled.remove();
      const category = document.querySelector('[data-log-target="category:커피"]');
      emit(category, 'pointerdown', 202); emit(category, 'pointercancel', 202);
    });
    await page.locator('[data-log-target="review-open"]').click();
    await page.locator('[data-log-target="review-back"]').click();
    const result = await page.evaluate(() => window.kioskTouchLogDraft.summarize());
    assert.equal(result.counts.presses, 6);
    assert.equal(result.counts.activeTargetPresses, 4);
    assert.equal(result.counts.disabledTargetPresses, 1);
    assert.equal(result.counts.outsideTargetPresses, 1);
    assert.equal(result.counts.releases, 5);
    assert.equal(result.counts.cancellations, 1);
    assert.deepEqual(result.visits.map(visit => visit.screen), ['menu', 'review', 'menu']);
    const ids = await page.evaluate(() => window.kioskTouchLogDraft.read().events.map(event => event.id));
    await page.getByRole('button', { name: '터치 로그 보기', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('[data-touch-count="presses"]')?.textContent === '6');
    assert.equal(await page.locator('[data-touch-count="disabledTargetPresses"]').innerText(), '1');
    assert.match(await page.locator('[data-touch-outside-ratio]').innerText(), /16\.7% \(1 \/ 누름 시작 6\)/);
    await page.locator('.touch-log-visits > summary').click();
    assert.equal(await page.locator('.touch-log-visits tbody tr').count(), 3);
    assert.deepEqual(await page.evaluate(() => window.kioskTouchLogDraft.read().events.map(event => event.id)), ids);
    await page.reload();
    await page.waitForFunction(() => window.kioskTouchLogDraft?.read().serverSessionId === 'summary-second');
    assert.equal(await page.evaluate(() => window.kioskTouchLogDraft.summarize().counts.presses), 0);
    assert.equal(await page.evaluate(() => window.kioskTouchLogDraft.read().events.filter(event => event.kind === 'pointer_start').length), 6);
    await page.getByRole('button', { name: '터치 로그 보기', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('[data-touch-count="presses"]')?.textContent === '0');
    assert.match(await page.locator('[data-touch-outside-ratio]').innerText(), /산출 안 함 · 누름 기록 없음/);
    responses.verify();
  } finally { await browser.close(); }
});

test('원시 요약은 기본·확대·낮은 화면에서 넘치지 않고 방문 표와 최근 기록에 접근할 수 있다', async t => {
  const browser = await chromium.launch(launchOptions);
  try {
    for (const viewport of [{ width: 1080, height: 1920 }, { width: 1920, height: 1080 }, { width: 1365, height: 768 }, { width: 390, height: 844 }]) {
      for (const enlarged of [false, true]) for (const lowScreen of [false, true]) {
        const label = `${viewport.width}x${viewport.height}-${enlarged ? 'large' : 'default'}-${lowScreen ? 'low' : 'normal'}`;
        await t.test(label, async () => {
          const page = await browser.newPage({ viewport });
          try {
            await page.route('https://fonts.googleapis.com/**', route => route.abort());
            await page.addInitScript(settings => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify(settings)), {
              largeText: enlarged, largeButton: enlarged, simpleScreen: false, stepGuide: false, lowScreen,
            });
            const responses = await installOrderResponses(page, bootstrap(`summary-${label}`));
            await page.goto(url);
            await page.waitForFunction(() => Boolean(window.kioskTouchLogDraft?.read().serverSessionId));
            await page.locator('[data-log-target="category:커피"]').click();
            await page.getByRole('button', { name: '터치 로그 보기', exact: true }).click();
            await page.locator('.touch-log-visits > summary').click();
            const panel = page.locator('.touch-log-panel');
            await page.waitForFunction(() => document.querySelector('[data-touch-count="presses"]')?.textContent === '1');
            const bounds = await panel.boundingBox();
            assert(bounds.x >= 0 && bounds.x + bounds.width <= viewport.width && bounds.y >= 0 && bounds.y + bounds.height <= viewport.height);
            assert(await panel.evaluate(element => element.scrollWidth <= element.clientWidth));
            await page.locator('.touch-log-visits table').scrollIntoViewIfNeeded();
            const table = await page.locator('.touch-log-visits table').boundingBox();
            assert(table.y >= bounds.y && table.y < bounds.y + bounds.height);
            await page.getByRole('heading', { name: '최근 기록 20개 · 최신순' }).scrollIntoViewIfNeeded();
            const screenshotDir = process.env.TOUCH_LOG_SUMMARY_SCREENSHOT_DIR;
            if (screenshotDir && viewport.width === 1080 && (!lowScreen || enlarged)) {
              await mkdir(screenshotDir, { recursive: true });
              await panel.evaluate(element => { element.scrollTop = 0; });
              await page.screenshot({ path: join(screenshotDir, `summary-${enlarged ? 'large' : 'default'}-${lowScreen ? 'low' : 'normal'}.png`) });
            }
            responses.verify();
          } finally { await page.close(); }
        });
      }
    }
  } finally { await browser.close(); }
});

test('로컬 로그: 중복 방지, 화면·옵션·설정, 서버 세션 연결·새로고침 분리, 실제 터치 스크롤', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const context = await browser.newContext({ viewport: { width: 1100, height: 650 }, hasTouch: true });
    const page = await context.newPage();
    const first = 'log-order-1', second = 'log-order-2', third = 'log-order-3';
    const secondCart = cartResponse(second, 1, [iced()]);
    const responses = await installOrderResponses(page, [
      ...bootstrap(first),
      mutation(first, '/cart/items', cartResponse(first, 1, [iced()])),
      ...bootstrap(second),
      mutation(second, '/cart/items', secondCart),
      mutation(second, '/orders', orderResponse(secondCart), { status: 201 }),
      ...bootstrap(third),
    ]);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft);
    await page.waitForFunction(id => window.kioskTouchLogDraft.read().serverSessionId === id, first);
    const read = () => page.evaluate(() => window.kioskTouchLogDraft.read());
    const click = id => page.locator(`[data-log-target="${id}"]`).click();
    let log = await read();
    assert.equal(log.events.filter(event => event.kind === 'session_start' && event.serverSessionId === first).length, 1);
    assert.equal(log.events.filter(event => event.kind === 'screen_enter' && event.sessionId === log.sessionId).length, 1);
    assert.equal(log.events.find(event => event.kind === 'session_start' && event.serverSessionId === first).data.server_session_id, first);
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
    await page.evaluate(() => document.querySelector('.kiosk').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 123, clientX: 1, clientY: 1 })));
    await page.reload();
    await page.waitForFunction(() => window.kioskTouchLogDraft);
    await page.waitForFunction(id => window.kioskTouchLogDraft.read().serverSessionId === id, second);
    log = await read();
    assert.notEqual(log.sessionId, session);
    assert(log.events.some(event => event.kind === 'session_end' && event.sessionId === session));
    assert.equal(log.events.filter(event => event.kind === 'session_start' && event.serverSessionId === second).length, 1);
    assert(log.events.some(event => event.kind === 'pointer_start' && event.sessionId === session && event.serverSessionId === first));
    assert(log.events.some(event => event.kind === 'pointer_interrupted' && event.serverSessionId === first));
    // 이전 기록은 보관하지만 새 서버 주문은 별도 로컬 세션에 연결됩니다.
    await click('product:americano');
    await click('cart-add');
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    await click('review-open');
    await click('simulate-payment');
    await page.locator('.order-number').waitFor();
    await page.evaluate(() => document.querySelector('.kiosk').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 124, clientX: 1, clientY: 1 })));
    await click('new-order');
    await page.waitForFunction(id => window.kioskTouchLogDraft.read().serverSessionId === id, third);
    log = await read();
    assert.notEqual(log.sessionId, session);
    assert.equal(log.events.filter(event => event.kind === 'screen_enter' && event.sessionId === log.sessionId).length, 1);
    assert(log.events.some(event => event.kind === 'session_end' && event.sessionId === session));
    assert.equal(log.events.find(event => event.kind === 'session_start' && event.serverSessionId === third).data.server_session_id, third);
    assert(log.events.some(event => event.kind === 'pointer_interrupted' && event.serverSessionId === second));
    for (const local of new Set(log.events.map(event => event.sessionId))) {
      assert.equal(new Set(log.events.filter(event => event.sessionId === local).map(event => event.serverSessionId)).size, 1);
    }
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
    responses.verify();
    assert.deepEqual(errors, []);
    console.log('브라우저 확인: StrictMode 중복 없음, 세션·방문, 모달 주변 입력, UI 설정, 실제 터치 스크롤 통과');
  } finally { await browser.close(); }
});

test('주변 후보는 화면·컨테이너에서 보이는 부분만 사용하고 누름 표시는 보관 범위를 밝힌다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({ viewport: { width: 1100, height: 650 } });
    const responses = await installOrderResponses(page, bootstrap('log-near'));
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.kioskTouchLogDraft);
    await page.waitForFunction(() => {
      const product = document.querySelector('[data-log-target="product:americano"]');
      return product && !product.disabled;
    });
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
    responses.verify();
  } finally { await browser.close(); }
});

test('개발 확인 창은 수집을 오염시키지 않고 표시 정지·재개·내보내기를 제공한다', async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
    const responses = await installOrderResponses(page, bootstrap('log-tools'));
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft);
    await page.waitForFunction(() => window.kioskTouchLogDraft.read().serverSessionId === 'log-tools');
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
    responses.verify();
    if (process.env.TOUCH_LOG_PRODUCTION_URL) {
      await page.goto(process.env.TOUCH_LOG_PRODUCTION_URL);
      await page.locator('.kiosk').waitFor();
      assert.equal(await page.locator('.touch-log-tools').count(), 0);
    }
  } finally { await browser.close(); }
});

test('하단 주문 바의 완전·부분 가림을 제외하고 주문 버튼과 옵션 창 입력은 유지한다', async t => {
  const browser = await chromium.launch(launchOptions);
  try {
    for (const viewport of [{ width: 1080, height: 1920 }, { width: 1365, height: 768 }, { width: 1920, height: 1080 }]) {
      for (const settings of [[], ['largeText'], ['largeButton'], ['largeText', 'largeButton']]) {
        const label = `${viewport.width}x${viewport.height}-${settings.join('-') || 'default'}`;
        await t.test(label, async () => {
          const page = await browser.newPage({ viewport, hasTouch: true });
          const session = `occlusion-${label}`;
          const steps = bootstrap(session); steps[2].body = cartResponse(session, 1, [iced()]);
          const responses = await installOrderResponses(page, steps);
          await page.goto(url);
          await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
          const click = id => page.locator(`[data-log-target="${id}"]`).click();
          if (settings.length) {
            await click('support-toggle');
            for (const setting of settings) await click(`support:${setting}`);
            await click('support-toggle');
          }
          const point = await page.evaluate(() => {
            const bar = document.querySelector('.order-actions').getBoundingClientRect();
            document.querySelectorAll('.kiosk button, .kiosk a').forEach(element => {
              if (element.closest('.order-actions')) return;
              element.dataset.occlusionDisabled = element.getAttribute('aria-disabled') ?? '';
              element.setAttribute('aria-disabled', 'true');
            });
            for (const [id, top] of [['occluded-full', bar.top + 4], ['occluded-partial', bar.top - 24]]) {
              const button = document.createElement('button');
              button.dataset.logTarget = id;
              button.textContent = id;
              button.style.cssText = `position:fixed;left:4px;top:${top}px;width:60px;height:80px;min-height:0;padding:0;z-index:0`;
              document.querySelector('.kiosk').append(button);
            }
            const x = 12, y = bar.top + 12;
            const hit = document.elementFromPoint(x, y);
            if (!hit.closest('.order-actions') || hit.closest('button,a[href]')) throw new Error('주문 바의 버튼 밖 위치');
            return { x, y };
          });
          const latest = () => page.evaluate(() => window.kioskTouchLogDraft.read().events.filter(event => event.kind === 'pointer_start').at(-1));
          await page.mouse.click(point.x, point.y);
          const partial = (await latest()).data;
          assert.equal(partial.target, null);
          assert.equal(partial.nearestCandidates.length, 1);
          assert.equal(partial.nearestCandidates[0].id, 'occluded-partial');
          assert.equal(partial.nearestCandidates[0].visibleRect.height, 24);
          assert.equal(partial.nearestCandidates[0].distance, 12);
          await page.locator('[data-log-target="occluded-partial"]').evaluate(element => element.remove());
          await page.mouse.click(point.x, point.y);
          assert((await latest()).data.nearestCandidates.every(candidate => candidate.id !== 'occluded-full'));
          await page.evaluate(() => {
            document.querySelector('[data-log-target="occluded-full"]').remove();
            document.querySelectorAll('[data-occlusion-disabled]').forEach(element => {
              if (element.dataset.occlusionDisabled) element.setAttribute('aria-disabled', element.dataset.occlusionDisabled);
              else element.removeAttribute('aria-disabled');
              delete element.dataset.occlusionDisabled;
            });
          });
          await click('review-open');
          assert.equal((await latest()).data.target.id, 'review-open');
          await click('review-back');
          await click('product:americano');
          const dialogPoint = await page.evaluate(() => {
            const dialog = document.querySelector('dialog[open]');
            dialog.style.cssText = 'position:fixed;inset:0;margin:auto;width:80vw;height:95vh;max-height:none;max-width:none';
            const bounds = dialog.getBoundingClientRect();
            const bar = document.querySelector('.order-actions').getBoundingClientRect();
            dialog.querySelectorAll('button').forEach(button => button.setAttribute('aria-disabled', 'true'));
            const button = document.createElement('button');
            button.dataset.logTarget = 'dialog-above-bar';
            button.textContent = '옵션 창 후보';
            button.style.cssText = `position:fixed;left:${bounds.left + 20}px;top:${bar.top + 8}px;width:80px;height:20px;min-height:0;padding:0`;
            dialog.append(button);
            return { x: bounds.left + 120, y: bar.top + 15 };
          });
          await page.mouse.click(dialogPoint.x, dialogPoint.y);
          const modal = (await latest()).data;
          assert.equal(modal.target, null);
          assert.equal(modal.nearestCandidates[0].id, 'dialog-above-bar');
          assert.equal(modal.nearestCandidates[0].distance, 20);
          responses.verify();
          await page.close();
        });
      }
    }
  } finally { await browser.close(); }
});
