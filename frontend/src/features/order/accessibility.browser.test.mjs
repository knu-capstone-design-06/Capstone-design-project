// 실행 중인 Vite + 외부 Playwright. 추가 서비스 의존성은 없습니다.
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { bootstrap, cartResponse, iced, installOrderResponses } from './orderApiFixture.mjs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.ORDER_BROWSER_URL ?? 'http://127.0.0.1:5174';
const channel = process.env.PLAYWRIGHT_CHANNEL ?? 'msedge';
const launch = { headless: true, ...(channel === 'default' ? {} : { channel }) };
const target = (page, id) => page.locator(`[data-log-target="${id}"]`);
async function shot(page, name) {
  if (!process.env.ACCESSIBILITY_SCREENSHOT_DIR) return;
  await mkdir(process.env.ACCESSIBILITY_SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({ path: join(process.env.ACCESSIBILITY_SCREENSHOT_DIR, `${name}.png`), animations: 'disabled' });
}

test('일반 배경·버튼 색상을 바꿔도 고대비 팔레트와 복귀한 일반 색상을 유지한다', async () => {
  const browser = await chromium.launch(launch);
  try {
    for (const [background, accent] of [['#fff7ed', '#9a3412'], ['#eff6ff', '#1e3a8a']]) {
      const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
      await page.route('https://fonts.googleapis.com/**', route => route.abort());
      const fixture = await installOrderResponses(page, bootstrap(`palette-${accent.slice(1)}`));
      await page.goto(url);
      await page.addStyleTag({ content: '.kiosk button { transition: none !important; }' });
      await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
      const palette = () => page.evaluate(() => {
        const root = getComputedStyle(document.querySelector('.kiosk'));
        const button = getComputedStyle(document.querySelector('[data-log-target="category:전체"]'));
        return { background: root.backgroundColor, text: root.color, button: button.backgroundColor, buttonText: button.color };
      });
      await target(page, 'support-toggle').click();
      await target(page, 'support:highContrast').click();
      const high = await palette();
      await target(page, 'support:highContrast').click();
      await page.addStyleTag({ content: `.kiosk { --ui-surface: ${background}; --ui-accent: ${accent}; }` });
      const normal = await palette();
      assert.notEqual(normal.background, high.background);
      assert.notEqual(normal.button, high.button);
      await target(page, 'support:highContrast').click();
      assert.deepEqual(await palette(), high);
      await target(page, 'support:highContrast').click();
      assert.deepEqual(await palette(), normal);
      fixture.verify(); await page.close();
    }
  } finally { await browser.close(); }
});

test('G10 화면에서 200% 글자·고대비·낮은 화면에도 상품·설정·주문 동작에 접근한다', async t => {
  const browser = await chromium.launch(launch);
  try {
    for (const low of [false, true]) for (const large of [false, true]) {
      await t.test(`${low ? 'low' : 'normal'}-${large ? '200' : '100'}`, async () => {
        const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
        try {
          await page.route('https://fonts.googleapis.com/**', route => route.abort());
          await page.addInitScript(({ low, large }) => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify({ lowScreen: low, largeText: large, largeButton: large, highContrast: large })), { low, large });
          const fixture = await installOrderResponses(page, bootstrap(`a11y-${low}-${large}`));
          await page.goto(url);
          await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
          const metrics = await page.evaluate(() => {
            const root = document.querySelector('.kiosk'), bar = document.querySelector('.order-actions');
            const font = getComputedStyle(document.querySelector('.description')).fontSize;
            return { font: parseFloat(font), overflow: document.documentElement.scrollWidth > innerWidth,
              reserved: parseFloat(root.style.getPropertyValue('--order-actions-space')), bar: bar.getBoundingClientRect().height };
          });
          const expectedFont = large ? 56 : 28;
          assert.equal(metrics.font, expectedFont);
          assert.equal(await target(page, 'category:전체').evaluate(element => parseFloat(getComputedStyle(element).fontSize)), expectedFont);
          assert(!metrics.overflow);
          assert(Math.abs(metrics.bar - metrics.reserved) <= 1);
          const contrasts = await page.evaluate(() => {
            const rgb = value => value.match(/[\d.]+/g).map(Number);
            const luminance = color => rgb(color).slice(0, 3).map(x => x / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4).reduce((sum, x, i) => sum + x * [.2126, .7152, .0722][i], 0);
            return ['.intro h1', '.description', '.product-category', '.product-price', '.sample-badge', '.order-actions p'].map(selector => {
              const element = document.querySelector(selector);
              let parent = element, background = 'rgb(255, 255, 255)';
              while (parent) {
                const color = getComputedStyle(parent).backgroundColor;
                if (rgb(color)[3] !== 0) { background = color; break; }
                parent = parent.parentElement;
              }
              const fg = luminance(getComputedStyle(element).color), bg = luminance(background);
              return { selector, ratio: (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05) };
            });
          });
          for (const { selector, ratio } of contrasts) assert(ratio >= (large ? 7 : 4.5), `${selector}: ${ratio}`);
          await shot(page, `menu-${low ? 'low' : 'normal'}-${large ? '200' : '100'}`);
          await target(page, 'product:americano').click();
          for (const id of ['temperature:핫', 'cart-add']) {
            assert.equal(await target(page, id).evaluate(element => parseFloat(getComputedStyle(element).fontSize)), expectedFont, `${id} 글자 확대`);
          }
          await target(page, 'temperature:핫').click();
          await target(page, 'options-increase').click();
          const modal = await page.locator('dialog[open]').boundingBox();
          assert(modal.y >= (low ? 768 : 0) && modal.y + modal.height <= 1920);
          await target(page, 'options-close').click();
          await target(page, 'support-toggle').click();
          for (const id of ['support:largeText', 'read-aloud-toggle']) {
            assert.equal(await target(page, id).evaluate(element => parseFloat(getComputedStyle(element).fontSize)), expectedFont, `${id} 글자 확대`);
          }
          await target(page, 'support:highContrast').click();
          await target(page, 'support-toggle').click();
          const recorded = await page.evaluate(() => window.kioskTouchLogDraft.read().events);
          assert(recorded.some(e => e.kind === 'ui_settings_change' && e.data.after.highContrast === !large));
          assert(recorded.some(e => e.kind === 'pointer_start' && e.data.pointerType === 'mouse'));
          fixture.verify();
        } finally { await page.close(); }
      });
    }
  } finally { await browser.close(); }
});

test('처음으로의 취소는 장바구니를 보존하고 확인하면 새 서버·로그 세션으로 시작한다', async () => {
  const browser = await chromium.launch(launch);
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    const first = bootstrap('reset-before'); first[2].body = cartResponse('reset-before', 1, [iced()]);
    const fixture = await installOrderResponses(page, [...first, ...bootstrap('reset-after')]);
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft?.read().serverSessionId === 'reset-before');
    const before = await page.evaluate(() => window.kioskTouchLogDraft.read().sessionId);
    await target(page, 'order-restart').click();
    await target(page, 'order-restart-cancel').click();
    assert.equal(await page.evaluate(() => window.kioskTouchLogDraft.read().sessionId), before);
    assert(await target(page, 'review-open').isEnabled());
    await target(page, 'order-restart').click();
    await target(page, 'order-restart-confirm').click();
    await page.waitForFunction(() => window.kioskTouchLogDraft.read().serverSessionId === 'reset-after');
    assert.notEqual(await page.evaluate(() => window.kioskTouchLogDraft.read().sessionId), before);
    assert(await target(page, 'review-open').isDisabled());
    fixture.verify();
  } finally { await browser.close(); }
});

test('화면 읽기를 중단·다시 재생하고 화면 이동 때 이전 안내를 취소한다', async () => {
  const browser = await chromium.launch(launch);
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    await page.addInitScript(() => {
      window.__speechReview = { texts: [], cancelled: 0 };
      Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
        cancel() { window.__speechReview.cancelled++; },
        speak(utterance) { window.__speechReview.texts.push(utterance.text); },
      } });
      window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
    });
    const steps = bootstrap('read-aloud'); steps[2].body = cartResponse('read-aloud', 1, [iced()]);
    const fixture = await installOrderResponses(page, steps);
    await page.goto(url);
    await target(page, 'review-open').waitFor();
    await page.waitForFunction(() => document.querySelector('[data-log-target="review-open"]')?.disabled === false);
    await target(page, 'support-toggle').click();
    await target(page, 'read-aloud-toggle').click();
    await page.waitForFunction(() => window.__speechReview.texts.length === 1);
    assert.match(await page.evaluate(() => window.__speechReview.texts[0]), /메뉴를 골라 주세요/);
    await target(page, 'read-aloud-stop').click();
    assert(await target(page, 'read-aloud-stop').isDisabled());
    await target(page, 'read-aloud-replay').click();
    assert.equal(await page.evaluate(() => window.__speechReview.texts.length), 2);
    await target(page, 'support-toggle').click();
    await target(page, 'review-open').click();
    await page.waitForFunction(() => window.__speechReview.texts.length === 3);
    assert.match(await page.evaluate(() => window.__speechReview.texts.at(-1)), /담은 메뉴를 확인/);
    assert(await page.evaluate(() => window.__speechReview.cancelled >= 3));
    fixture.verify();
  } finally { await browser.close(); }
});

test('파일럿 기본값과 기준 변경·집계 내보내기는 원시 입력을 추가하지 않는다', async () => {
  const browser = await chromium.launch(launch);
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    const fixture = await installOrderResponses(page, bootstrap('pilot-controls'));
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft?.read().serverSessionId === 'pilot-controls');
    await page.getByRole('button', { name: '터치 로그 보기', exact: true }).click();
    await page.getByText('파일럿 기준 선택 · 팀 계약과 별개', { exact: true }).click();
    assert.equal(await page.getByLabel('반복 시간(ms)', { exact: true }).inputValue(), '800');
    assert.equal(await page.getByLabel('반복 거리(CSS px)', { exact: true }).inputValue(), '24');
    assert.equal(await page.getByLabel('체류 시간 정의').inputValue(), 'foreground_visit');
    await page.waitForFunction(() => document.querySelector('[data-touch-feature="tap_count"]')?.textContent === '0');
    assert.notEqual(await page.locator('[data-touch-feature="dwell_ms"]').textContent(), '미산출');
    const ids = await page.evaluate(() => window.kioskTouchLogDraft.read().events.map(e => e.id));
    await page.getByLabel('반복 시간(ms)', { exact: true }).fill('500');
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button', { name: '파일럿 집계 내보내기', exact: true }).click();
    const download = await downloadEvent;
    assert.equal(download.suggestedFilename(), 'touch-features-pilot.json');
    const stream = await download.createReadStream();
    const chunks = []; for await (const chunk of stream) chunks.push(chunk);
    const exported = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    assert.equal(exported.policy.repeatMs, 500);
    assert.equal(exported.features.tap_count, 0);
    assert.equal(exported.serverSessionId, 'pilot-controls');
    assert.deepEqual(await page.evaluate(() => window.kioskTouchLogDraft.read().events.map(e => e.id)), ids);
    fixture.verify();
  } finally { await browser.close(); }
});

test('마이크 시작 전에 낭독·누름 소리를 멈추고 실제 종료 뒤 화면 읽기를 시작한다', async () => {
  const browser = await chromium.launch(launch);
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      const review = window.__audioReview = { speaking: false, microphone: false, tones: 0, texts: [], overlaps: [] };
      Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
        cancel() { review.speaking = false; },
        speak(utterance) {
          if (review.microphone) review.overlaps.push('마이크 종료 전 낭독');
          review.speaking = true; review.texts.push(utterance.text);
        },
      } });
      window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
      class Recognition {
        constructor() { window.__recognition = this; }
        start() {
          if (review.speaking || review.tones) review.overlaps.push('소리 재생 중 마이크 시작');
          review.microphone = true;
        }
        stop() {}
        abort() {}
        finish() { review.microphone = false; this.onend?.(); }
      }
      window.SpeechRecognition = Recognition;
      window.webkitSpeechRecognition = Recognition;
      window.AudioContext = class {
        state = 'running'; currentTime = 0; destination = {};
        resume() { return Promise.resolve(); }
        close() { this.state = 'closed'; return Promise.resolve(); }
        createGain() { return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, disconnect() {} }; }
        createOscillator() {
          let playing = false;
          return { frequency: { value: 0 }, connect() {}, disconnect() {},
            start() { playing = true; review.tones++; },
            stop(when) { if (when === undefined && playing) { playing = false; review.tones--; this.onended?.(); } },
          };
        }
      };
    });
    const fixture = await installOrderResponses(page, bootstrap('audio-transition'));
    await page.goto(url);
    await target(page, 'voice-mode-toggle').waitFor({ state: 'visible' });
    await page.waitForFunction(() => !document.querySelector('[data-log-target="voice-mode-toggle"]').disabled);
    await target(page, 'support-toggle').click();
    await target(page, 'read-aloud-toggle').click();
    await page.waitForFunction(() => window.__audioReview.texts.length === 1);
    await target(page, 'support-toggle').click();
    await target(page, 'voice-mode-toggle').click();
    assert.equal(await page.evaluate(() => window.__audioReview.speaking), false);
    await target(page, 'support-toggle').click();
    await target(page, 'read-aloud-toggle').click();
    assert.equal(await page.evaluate(() => window.__audioReview.texts.length), 1);
    assert(await target(page, 'read-aloud-replay').isDisabled());
    await page.evaluate(() => window.__recognition.finish());
    await page.waitForFunction(() => window.__audioReview.texts.length === 2);
    await target(page, 'read-aloud-toggle').click();
    await target(page, 'touch-sound-toggle').click();
    await target(page, 'support-toggle').click();
    await target(page, 'category:커피').click();
    assert(await page.evaluate(() => window.__audioReview.tones > 0));
    await target(page, 'voice-mode-toggle').click();
    assert.equal(await page.evaluate(() => window.__audioReview.tones), 0);
    assert.deepEqual(await page.evaluate(() => window.__audioReview.overlaps), []);
    await target(page, 'voice-mode-toggle').click();
    await page.evaluate(() => window.__recognition.finish());
    fixture.verify(); assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('화면 읽기는 열린 옵션·처음으로 확인 창만 읽고 닫으면 메뉴 안내로 돌아온다', async () => {
  const browser = await chromium.launch(launch);
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    await page.addInitScript(() => {
      window.__dialogTexts = [];
      Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
        cancel() {}, speak(utterance) { window.__dialogTexts.push(utterance.text); },
      } });
      window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
    });
    const fixture = await installOrderResponses(page, bootstrap('dialog-reading'));
    await page.goto(url);
    await page.waitForFunction(() => document.querySelector('[data-log-target="product:americano"]')?.disabled === false);
    await target(page, 'support-toggle').click();
    await target(page, 'read-aloud-toggle').click();
    await target(page, 'support-toggle').click();
    await target(page, 'product:americano').click();
    await page.waitForFunction(() => window.__dialogTexts.length === 2);
    const optionText = await page.evaluate(() => window.__dialogTexts.at(-1));
    assert.match(optionText, /아메리카노.*온도/);
    assert.doesNotMatch(optionText, /메뉴를 골라 주세요/);
    await target(page, 'options-close').click();
    await page.waitForFunction(() => window.__dialogTexts.length === 3);
    await target(page, 'order-restart').click();
    await page.waitForFunction(() => window.__dialogTexts.length === 4);
    const restartText = await page.evaluate(() => window.__dialogTexts.at(-1));
    assert.match(restartText, /처음부터 주문할까요/);
    assert.doesNotMatch(restartText, /메뉴를 골라 주세요/);
    await target(page, 'order-restart-cancel').click();
    await page.waitForFunction(() => window.__dialogTexts.length === 5);
    assert.match(await page.evaluate(() => window.__dialogTexts.at(-1)), /메뉴를 골라 주세요/);
    fixture.verify();
  } finally { await browser.close(); }
});
