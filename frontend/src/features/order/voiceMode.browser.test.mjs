// Vite와 외부 Playwright로 주문 화면의 음성 연결을 확인합니다. 실제 마이크·백엔드는 사용하지 않습니다.
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { bootstrap, cartResponse, iced, installOrderResponses, mutation } from './orderApiFixture.mjs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.ORDER_BROWSER_URL ?? 'http://127.0.0.1:5173';
const channel = process.env.PLAYWRIGHT_CHANNEL ?? 'msedge';
async function screenshot(page, name, clipHeight = null) {
  if (!process.env.VOICE_SCREENSHOT_DIR) return;
  await mkdir(process.env.VOICE_SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({ path: join(process.env.VOICE_SCREENSHOT_DIR, `${name}.png`),
    ...(clipHeight ? { clip: { x: 0, y: 0, width: 1080, height: clipHeight } } : {}) });
}

async function open(steps, pageUrl = url) {
  const browser = await chromium.launch({ headless: true, ...(channel === 'default' ? {} : { channel }) });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    let active = null;
    class FakeRecognition {
      constructor() { this.aborted = false; window.voiceFakes.push(this); }
      start() { if (active) throw new Error('이전 마이크 종료 전 재시작'); active = this; }
      stop() { setTimeout(() => { if (active === this) active = null; this.onend?.(); }, 30); }
      abort() { this.aborted = true; this.stop(); }
      partial(text) { this.onresult?.({ resultIndex: 0, results: [Object.assign([{ transcript: text, confidence: .9 }], { isFinal: false })] }); }
      final(text) { this.onresult?.({ resultIndex: 0, results: [Object.assign([{ transcript: text, confidence: .9 }], { isFinal: true })] }); }
      fail(error) { this.onerror?.({ error }); if (active === this) active = null; this.onend?.(); }
    }
    window.voiceFakes = [];
    window.SpeechRecognition = FakeRecognition;
    window.webkitSpeechRecognition = FakeRecognition;
  });
  const fixture = await installOrderResponses(page, steps);
  await page.goto(pageUrl);
  await page.locator('[data-log-target="voice-mode-toggle"]:not([disabled])').waitFor();
  return { browser, page, errors, fixture };
}

test('개발 샘플에서 짧은 말도 인식하고 다시 듣기·오류·화면 이동을 처리하며 backend를 호출하지 않는다', { skip: !process.env.ORDER_SAMPLE_BROWSER_URL }, async () => {
  const { browser, page, errors, fixture } = await open([], process.env.ORDER_SAMPLE_BROWSER_URL);
  try {
    const toggle = page.getByRole('switch', { name: '음성 인식 테스트', exact: true });
    await toggle.click();
    await page.evaluate(() => window.voiceFakes.at(-1).partial('아이스 아메리카노'));
    assert.match(await page.locator('.voice-mode-feedback').innerText(), /아이스 아메리카노/);
    const speakingLog = await page.evaluate(() => window.kioskTouchLogDraft.read());
    assert(speakingLog.events.some(event => event.kind === 'voice_state_change' && event.data.after.enabled && event.data.after.microphoneActive));
    assert(!JSON.stringify(speakingLog).includes('아이스 아메리카노'));
    await page.evaluate(() => window.voiceFakes.at(-1).final('네'));
    await page.locator('[data-log-target="voice-listen"]').waitFor();
    assert.match(await page.locator('.voice-mode-transcript').innerText(), /인식한 말\s+네/);
    assert.match(await page.locator('.voice-mode-preview').innerText(), /주문은 바뀌지 않습니다/);
    assert.equal(await page.locator('.cart-row').count(), 0);
    await page.locator('[data-log-target="voice-listen"]').click();
    await page.evaluate(() => window.voiceFakes.at(-1).fail('not-allowed'));
    assert.match(await page.locator('.voice-mode-feedback').innerText(), /마이크 사용을 허용/);
    await page.locator('[data-log-target="voice-listen"]').click();
    await page.evaluate(() => window.voiceFakes.at(-1).final('아메리카노 두 잔'));
    await page.locator('[data-log-target="voice-listen"]').waitFor();
    assert.match(await page.locator('.voice-mode-transcript').innerText(), /아메리카노 두 잔/);
    await page.locator('[data-log-target="product:americano"]').click();
    await page.locator('[data-log-target="cart-add"]').click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    await page.locator('[data-log-target="voice-listen"]').click();
    await page.locator('[data-log-target="review-open"]').click();
    assert.equal(await page.evaluate(() => window.voiceFakes.at(-1).aborted), true);
    await page.locator('[data-log-target="review-back"]').click();
    assert.equal(await toggle.getAttribute('aria-checked'), 'false');
    assert.equal(await page.locator('.voice-mode-transcript').count(), 0);
    const voiceLog = await page.evaluate(() => window.kioskTouchLogDraft.read());
    assert.equal(voiceLog.events.filter(event => event.kind === 'voice_state_change').at(-1).data.after.enabled, false);
    assert(voiceLog.events.some(event => event.kind === 'pointer_start' && event.voiceMode === true));
    assert(!JSON.stringify(voiceLog).includes('아메리카노 두 잔'));
    assert.deepEqual(fixture.requests, []);
    fixture.verify(); assert.deepEqual(errors, []);
    await screenshot(page, 'sample-recognition-test');
  } finally { await browser.close(); }
});

const voiceStatus = (status, extra = {}) => ({ request_id: 'voice-1', status, reply_text: null, tool_calls: [], actions: [], error: null, ...extra });
const voicePost = session => ({ method: 'POST', path: `/api/v1/sessions/${session}/voice/requests`, status: 202,
  body: { request_id: 'voice-1', status: 'accepted', accepted_at: '2026-10-19T00:00:00Z' } });
const voiceGet = (session, status) => ({ method: 'GET', path: `/api/v1/sessions/${session}/voice/requests/voice-1`, body: status });

test('메뉴에서 마이크·질문·해석 결과를 표시하고 주문 확인으로 이동하면 듣기를 중단한다', async () => {
  const session = 'voice-screen', cart = cartResponse(session, 1, [iced()]);
  const { browser, page, errors, fixture } = await open([
    ...bootstrap(session),
    voicePost(session), voiceGet(session, voiceStatus('needs_clarification', { reply_text: '온도를 골라 주세요.' })),
    voicePost(session), voiceGet(session, voiceStatus('completed', { tool_calls: [{ tool: 'add_cart_item', arguments: { product_id: 'americano', temperature: 'hot', quantity: 1 } }] })),
    mutation(session, '/cart/items', cart),
  ]);
  try {
    const toggle = page.locator('[data-log-target="voice-mode-toggle"]');
    await toggle.click();
    assert.equal(await toggle.getAttribute('aria-checked'), 'true');
    await page.evaluate(() => window.voiceFakes.at(-1).partial('아메리카노'));
    assert.match(await page.locator('.voice-mode-feedback').innerText(), /듣는 중: 아메리카노/);
    await screenshot(page, 'voice-listening-menu', 450);
    await page.evaluate(() => window.voiceFakes.at(-1).final('아메리카노 주세요'));
    await page.locator('.voice-mode-feedback').getByText('온도를 골라 주세요.').waitFor();
    assert.match(await page.locator('.voice-mode-transcript').innerText(), /아메리카노 주세요/);
    await page.waitForFunction(() => window.voiceFakes.length === 2);
    assert.equal(await page.evaluate(() => window.voiceFakes.length), 2, '질문 뒤 다시 듣기 시작');
    await page.evaluate(() => window.voiceFakes.at(-1).partial('따뜻한'));
    assert.match(await page.locator('.voice-mode-feedback').innerText(), /온도를 골라 주세요.*듣는 중: 따뜻한/);
    await screenshot(page, 'voice-question-menu', 450);
    await page.evaluate(() => window.voiceFakes.at(-1).final('핫'));
    await page.locator('.voice-mode-feedback').getByText(/주문을 변경하는 기능은 아직 준비 중/).waitFor();
    assert.match(await page.locator('.voice-mode-transcript').innerText(), /인식한 말\s+핫/);
    assert.match(await page.locator('.total').innerText(), /0원/, '해석만으로 장바구니를 변경하지 않음');
    await screenshot(page, 'voice-result-menu');
    const submitted = fixture.requests.filter(request => request.path.endsWith('/voice/requests') && request.method === 'POST');
    assert.deepEqual(submitted.map(request => [request.body.text, request.body.screen_id]), [
      ['아메리카노 주세요', 'menu_list'], ['핫', 'menu_list'],
    ]);
    await page.locator('[data-log-target="voice-listen"]').click();
    await page.locator('[data-log-target="product:americano"]').click();
    await page.locator('[data-log-target="cart-add"]').click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden' });
    await page.locator('[data-log-target="review-open"]').click();
    assert.equal(await page.locator('.voice-mode-control').count(), 0);
    assert.equal(await page.evaluate(() => window.voiceFakes.at(-1).aborted), true);
    await page.locator('[data-log-target="review-back"]').click();
    assert.equal(await toggle.getAttribute('aria-checked'), 'false');
    assert.equal(await page.locator('.voice-mode-transcript').count(), 0);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('주변 대화는 표시하지 않고 이전 확인 질문에 짧게 답할 수 있다', async () => {
  const session = 'voice-ignored';
  const { browser, page, errors, fixture } = await open([
    ...bootstrap(session),
    voicePost(session), voiceGet(session, voiceStatus('ignored')),
    voicePost(session), voiceGet(session, voiceStatus('needs_confirmation', { reply_text: '아이스 아메리카노 2잔 담을까요?' })),
    voicePost(session), voiceGet(session, voiceStatus('ignored')),
    voicePost(session), voiceGet(session, voiceStatus('completed')),
  ]);
  try {
    await page.locator('[data-log-target="voice-mode-toggle"]').click();
    await page.evaluate(() => window.voiceFakes.at(-1).final('오늘 날씨 덥다'));
    await page.locator('[data-log-target="voice-listen"]').waitFor();
    assert.equal(await page.locator('.voice-mode-feedback').count(), 0);
    assert.equal(await page.locator('.voice-mode-transcript').count(), 0);
    await page.locator('[data-log-target="voice-listen"]').click();
    await page.waitForFunction(() => window.voiceFakes.length === 2);
    await page.evaluate(() => window.voiceFakes.at(-1).final('아메리카노 두 잔'));
    await page.waitForFunction(() => window.voiceFakes.length === 3);
    await page.evaluate(() => window.voiceFakes.at(-1).final('너 뭐 먹을래'));
    await page.locator('[data-log-target="voice-listen"]').waitFor();
    assert.equal(await page.locator('.voice-mode-feedback').innerText(), '아이스 아메리카노 2잔 담을까요?');
    assert.equal(await page.locator('.voice-mode-transcript').count(), 0);
    await page.locator('[data-log-target="voice-listen"]').click();
    await page.waitForFunction(() => window.voiceFakes.length === 4);
    await page.evaluate(() => window.voiceFakes.at(-1).partial('네'));
    assert.match(await page.locator('.voice-mode-feedback').innerText(), /듣는 중: 네/);
    await page.evaluate(() => window.voiceFakes.at(-1).final('네'));
    await page.locator('.voice-mode-feedback').getByText(/주문을 변경하는 기능은 아직 준비 중/).waitFor();
    assert.equal(fixture.requests.filter(request => request.method === 'POST' && request.path.endsWith('/voice/requests')).at(-1).body.text, '네');
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('확인 질문 뒤 서버 실패를 알리고 다시 말하기에서 질문과 짧은 답변을 유지한다', async () => {
  const session = 'voice-failed';
  const { browser, page, errors, fixture } = await open([
    ...bootstrap(session),
    voicePost(session), voiceGet(session, voiceStatus('needs_confirmation', { reply_text: '아이스 아메리카노 담을까요?' })),
    voicePost(session), voiceGet(session, voiceStatus('failed', { error: { code: 'llm_error', detail: '해석 실패' } })),
    voicePost(session), voiceGet(session, voiceStatus('completed')),
  ]);
  try {
    await page.locator('[data-log-target="voice-mode-toggle"]').click();
    await page.evaluate(() => window.voiceFakes.at(-1).final('아메리카노 주세요'));
    await page.waitForFunction(() => window.voiceFakes.length === 2);
    await page.evaluate(() => window.voiceFakes.at(-1).final('네'));
    await page.locator('.voice-mode-feedback').getByText(/음성 요청을 처리하지 못했어요/).waitFor();
    assert.equal(await page.evaluate(() => window.voiceFakes.length), 2);
    await page.locator('[data-log-target="voice-listen"]').click();
    await page.waitForFunction(() => window.voiceFakes.length === 3);
    assert.match(await page.locator('.voice-mode-feedback').innerText(), /아이스 아메리카노 담을까요/);
    await page.evaluate(() => window.voiceFakes.at(-1).final('네'));
    await page.locator('.voice-mode-feedback').getByText(/주문을 변경하는 기능은 아직 준비 중/).waitFor();
    assert.deepEqual(fixture.requests.filter(request => request.method === 'POST' && request.path.endsWith('/voice/requests')).map(request => request.body.text), ['아메리카노 주세요', '네', '네']);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('터치로 상품 추가·수량 변경·삭제를 저장하는 동안과 저장 후에도 음성 모드를 유지한다', async () => {
  const session = 'voice-cart-saving';
  const { browser, page, errors, fixture } = await open([
    ...bootstrap(session),
    mutation(session, '/cart/items', cartResponse(session, 1, [iced()])),
    mutation(session, '/cart/items/item-iced', cartResponse(session, 2, [iced(2)]), { method: 'PATCH' }),
    mutation(session, '/cart/items/item-iced?expected_version=2', cartResponse(session, 3), { method: 'DELETE' }),
  ]);
  let release;
  try {
    // 응답을 보류해 실제 saving 상태에서도 모드와 인식기가 유지되는지 확인합니다.
    await page.route('**/cart/items**', async route => {
      await new Promise(resolve => { release = resolve; });
      await route.fallback();
    });
    const toggle = page.locator('[data-log-target="voice-mode-toggle"]');
    await toggle.click();
    await page.locator('[data-log-target="product:americano"]').click();
    for (const target of ['cart-add', 'cart:americano:아이스:increase', 'cart:americano:아이스:remove']) {
      await page.locator(`[data-log-target="${target}"]`).click();
      await page.locator('.order-progress').waitFor();
      assert.equal(await toggle.getAttribute('aria-checked'), 'true');
      assert.equal(await toggle.isEnabled(), true, '저장 중에도 모드 해제 가능');
      assert.equal(await page.evaluate(() => window.voiceFakes.at(-1).aborted), false);
      release();
      await page.locator('.order-progress').waitFor({ state: 'hidden' });
      await page.locator('dialog[open]').waitFor({ state: 'hidden' });
      assert.equal(await toggle.getAttribute('aria-checked'), 'true');
    }
    assert.equal(await page.evaluate(() => window.voiceFakes.length), 1, '저장 후 마이크를 새로 열지 않음');
    await toggle.click();
    assert.equal(await page.evaluate(() => window.voiceFakes.at(-1).aborted), true);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { release?.(); await browser.close(); }
});

test('마이크 권한 오류를 알리고 큰 글씨·큰 버튼·낮은 화면에서도 조작할 수 있다', async () => {
  const { browser, page, errors, fixture } = await open(bootstrap('voice-layout'));
  try {
    await page.locator('[data-log-target="support-toggle"]').click();
    await page.locator('[data-log-target="support:largeText"]').click();
    await page.locator('[data-log-target="support:largeButton"]').click();
    await page.locator('[data-log-target="support:lowScreen"]').click();
    await page.locator('[data-log-target="support-toggle"]').click();
    await page.locator('[data-log-target="voice-mode-toggle"]').click();
    await page.evaluate(() => window.voiceFakes.at(-1).fail('not-allowed'));
    assert.match(await page.locator('.voice-mode-feedback').innerText(), /마이크 사용을 허용/);
    assert.equal(await page.locator('[data-log-target="voice-listen"]').isVisible(), true);
    await screenshot(page, 'voice-permission-low-large');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    const button = await page.locator('[data-log-target="voice-listen"]').boundingBox();
    assert(button && button.x >= 0 && button.x + button.width <= 1080);
    await page.locator('[data-log-target="voice-mode-toggle"]').click();
    assert.equal(await page.locator('.voice-mode-feedback').count(), 0);
    fixture.verify();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});
