import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { bootstrap, installOrderResponses } from './orderApiFixture.mjs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.ORDER_BROWSER_URL ?? 'http://127.0.0.1:5178';
const click = (page, id) => page.locator(`[data-log-target="${id}"]`).click();

test('낮은 화면·큰 글씨·큰 버튼·고대비에서 도움과 상품에 접근하고 높이 패드를 기록한다', async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    for (const largeButton of [false, true]) for (const highContrast of [false, true]) {
      const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
      await page.addInitScript(settings => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify(settings)), { largeText: true, lowScreen: true, largeButton, highContrast });
      await installOrderResponses(page, bootstrap(`feedback-${largeButton}-${highContrast}`));
      await page.goto(url);
      await page.locator('[data-log-target="product:americano"]:enabled').waitFor();
      await click(page, 'support-toggle');
      const main = await page.locator('main').boundingBox();
      assert(main.height > 150, '도움 패널을 열어도 상품을 조작할 높이 확보');
      const last = page.locator('.product').last();
      await last.evaluate(element => element.scrollIntoView({ block: 'end' }));
      assert(await last.evaluate(element => { const r = element.getBoundingClientRect(); return element.contains(document.elementFromPoint(r.x + r.width / 2, Math.min(r.bottom - 10, document.querySelector('main').getBoundingClientRect().bottom - 10))); }), '목록 끝 상품의 실제 누름 영역이 보임');
      await last.click();
      await page.locator('dialog[open]').waitFor();
      await click(page, 'options-close');
      await click(page, 'support:largeButton');
      assert.equal(await page.locator('[data-log-target="mode:standard"]').getAttribute('aria-pressed'), 'false');
      await click(page, 'support:largeButton');
      await click(page, 'support-toggle');
      await click(page, 'screen-position-pad');
      const events = await page.evaluate(() => window.kioskTouchLogDraft.read().events);
      assert(events.some(event => event.kind === 'pointer_start' && event.data.target?.id === 'screen-position-pad'));
      assert(events.some(event => event.kind === 'pointer_end'));
      assert(events.some(event => event.kind === 'scroll' && event.data.container === 'order-content'));
      await click(page, 'screen-position-pad');
      if (process.env.FEEDBACK_SCREENSHOT_DIR) {
        await mkdir(process.env.FEEDBACK_SCREENSHOT_DIR, { recursive: true });
        await click(page, 'support-toggle');
        await page.locator('.product').first().evaluate(element => element.scrollIntoView({ block: 'start' }));
        await page.locator('.header, .support-panel').evaluateAll(elements => elements.forEach(element => { element.scrollTop = 0; }));
        await page.screenshot({ path: `${process.env.FEEDBACK_SCREENSHOT_DIR}/low-large-${largeButton}-${highContrast}.png` });
      }
      await page.close();
    }
  } finally { await browser.close(); }
});


test('큰 버튼·간편 화면·단계별 안내 각각에서 일반 모드가 선택되지 않고 초기화 시 낮은 높이를 유지한다', async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    for (const setting of ['largeButton', 'simpleScreen', 'stepGuide']) {
      const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
      await page.addInitScript(key => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify({ [key]: true, lowScreen: true })), setting);
      await installOrderResponses(page, bootstrap(`standard-${setting}`));
      await page.goto(url);
      await page.locator('.product:enabled').first().waitFor();
      assert.equal(await page.locator('[data-log-target="mode:standard"]').getAttribute('aria-pressed'), 'false');
      await click(page, 'mode:standard');
      assert.equal(await page.locator('[data-log-target="mode:standard"]').getAttribute('aria-pressed'), 'true');
      assert.equal(await page.locator('.kiosk.low-screen').count(), 1);
      await page.close();
    }
  } finally { await browser.close(); }
});
