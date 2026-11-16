// PR #70의 높이 복귀·도움·설정 검사를 새 모달 배치에 맞춰 유지합니다.
import assert from 'node:assert/strict';
import test from 'node:test';
import { bootstrap, installOrderResponses } from './orderApiFixture.mjs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.ORDER_BROWSER_URL ?? 'http://127.0.0.1:5178';
const click = (page, id) => page.locator(`[data-log-target="${id}"]`).click();

test('낮은 화면·큰 글씨·큰 버튼·고대비에서 도움·상품을 조작하고 높이 복귀와 창 스크롤을 기록한다', async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    for (const largeButton of [false, true]) for (const highContrast of [false, true]) {
      const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
      const fixture = await installOrderResponses(page, bootstrap(`feedback-${largeButton}-${highContrast}`));
      await page.addInitScript(settings => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify(settings)), { largeText: true, lowScreen: true, largeButton, highContrast });
      await page.goto(url);
      await page.locator('[data-log-target="product:americano"]:enabled').waitFor();
      await click(page, 'support-toggle');
      await page.locator('#support-panel[open]').waitFor();
      assert.equal(await page.locator('[data-log-target="support:largeButton"]').getAttribute('aria-pressed'), String(largeButton));
      await click(page, 'support:largeButton');
      assert.equal(await page.locator('[data-log-target="support:largeButton"]').getAttribute('aria-pressed'), String(!largeButton));
      await click(page, 'support:largeButton');
      await page.locator('[data-log-target="read-aloud-replay"]').scrollIntoViewIfNeeded();
      await click(page, 'support-close');
      await page.locator('.product').last().click();
      await page.locator('dialog.option-sheet[open]').waitFor();
      await click(page, 'options-close');
      await click(page, 'screen-position-pad');
      await page.waitForFunction(() => !document.querySelector('.kiosk.low-screen'));
      const events = await page.evaluate(() => window.kioskTouchLogDraft.read().events);
      const padStart = events.find(event => event.kind === 'pointer_start' && event.data.target?.id === 'screen-position-pad');
      assert(padStart, '낮은 화면의 복귀 영역 누름 시작을 기록');
      assert(events.some(event => event.kind === 'pointer_end' && event.data.inputId === padStart.id), '같은 누름의 종료를 기록');
      assert(events.some(event => event.kind === 'scroll' && event.data.container === 'support-panel'), '모달 스크롤의 영역 이름을 보존');
      assert.equal(await page.locator('.kiosk.large-text').count(), 1, '높이 복귀 뒤 큰 글씨 유지');
      assert.equal(await page.locator('.kiosk.large-button').count(), Number(largeButton), '높이 복귀 뒤 큰 버튼 유지');
      assert.equal(await page.locator('.kiosk.high-contrast').count(), Number(highContrast), '높이 복귀 뒤 고대비 유지');
      fixture.verify();
      await page.close();
    }
  } finally { await browser.close(); }
});

test('각 수동 지원의 선택 상태를 표시하고 기본 화면으로에서 높이를 포함한 설정을 초기화한다', async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    for (const setting of ['largeButton', 'simpleScreen', 'stepGuide']) {
      const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
      const fixture = await installOrderResponses(page, bootstrap(`reset-${setting}`));
      await page.addInitScript(key => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify({ [key]: true, lowScreen: true })), setting);
      await page.goto(url);
      await page.locator('.product:enabled').first().waitFor();
      await click(page, 'support-toggle');
      assert.equal(await page.locator(`[data-log-target="support:${setting}"]`).getAttribute('aria-pressed'), 'true');
      await click(page, 'support-reset');
      assert.equal(await page.locator(`[data-log-target="support:${setting}"]`).getAttribute('aria-pressed'), 'false');
      assert.equal(await page.locator('[data-log-target="support:lowScreen"]').getAttribute('aria-pressed'), 'false');
      await click(page, 'support-close');
      assert.equal(await page.locator('.kiosk.low-screen').count(), 0);
      const settings = await page.evaluate(() => JSON.parse(localStorage.getItem('kiosk-ui-settings-v1')));
      assert(Object.values(settings).every(value => value === false));
      fixture.verify();
      await page.close();
    }
  } finally { await browser.close(); }
});
