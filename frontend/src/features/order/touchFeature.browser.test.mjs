import assert from 'node:assert/strict';
import test from 'node:test';
import { bootstrap, installOrderResponses } from './orderApiFixture.mjs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const url = process.env.TOUCH_LOG_BROWSER_URL ?? 'http://127.0.0.1:5173';
const channel = process.env.PLAYWRIGHT_CHANNEL ?? 'msedge';
const launch = () => chromium.launch({ headless: true, ...(channel === 'default' ? {} : { channel }) });

test('periodic aggregate upload works at kiosk size with normal and enlarged low-screen settings', async t => {
  const browser = await launch();
  try {
    for (const enlarged of [false, true]) await t.test(enlarged ? 'large-low' : 'normal', async () => {
      const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
      try {
        await page.route('https://fonts.googleapis.com/**', route => route.abort());
        await page.addInitScript(value => localStorage.setItem('kiosk-ui-settings-v1', JSON.stringify({ largeText: value, largeButton: value, lowScreen: value })), enlarged);
        const fixture = await installOrderResponses(page, bootstrap('telemetry-session'));
        await page.goto(url);
        await page.waitForFunction(() => window.kioskTouchLogDraft?.transmission()?.sent > 0);
        assert(fixture.featureRequests.length > 0);
        const first = fixture.featureRequests[0].body;
        assert.equal(first.touch.interaction.schema_version, 'touch-interaction-pilot-v1');
        assert.equal(first.touch.interaction.ui_settings.large_text, enlarged);
        assert.equal(first.touch.interaction.ui_settings.low_screen, enlarged);
        assert.equal(first.touch.tap_count, 0); assert.equal(first.touch.interaction.outside_tap_ratio, null);
        assert.equal(first.vision, null);
        await page.locator('[data-log-target="product:americano"]').click();
        await page.waitForFunction(() => window.kioskTouchLogDraft?.transmission()?.sent > 1);
        assert(fixture.featureRequests.some(r => r.body.touch.interaction.options_open === true));
        assert(!JSON.stringify(fixture.featureRequests.map(r => r.body)).includes('"events"'));
        fixture.verify();
      } finally { await page.close(); }
    });
  } finally { await browser.close(); }
});

test('page suspension stops samples; a new server session restarts sequence without old records', async () => {
  const browser = await launch(); const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  try {
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    const fixture = await installOrderResponses(page, [...bootstrap('before'), ...bootstrap('after')]);
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft?.transmission()?.sent > 0);
    await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pagehide')));
    const before = fixture.featureRequests.length;
    await page.waitForTimeout(2300);
    assert.equal(fixture.featureRequests.length, before);
    await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
    await page.locator('[data-log-target="order-restart"]').click();
    await page.locator('[data-log-target="order-restart-confirm"]').click();
    await page.waitForFunction(() => window.kioskTouchLogDraft?.read().serverSessionId === 'after' && window.kioskTouchLogDraft.transmission()?.sent > 0);
    const after = fixture.featureRequests.find(r => r.path.includes('/after/'));
    assert.equal(after.body.touch.interaction.window_sequence, 1);
    assert.equal(after.body.touch.tap_count, 0);
    fixture.verify();
  } finally { await page.close(); await browser.close(); }
});

test('feature endpoint failure does not prevent menu and option interactions', async () => {
  const browser = await launch(); const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  try {
    const fixture = await installOrderResponses(page, bootstrap('failed-upload'));
    await page.route('**/features', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"unavailable"}' }));
    await page.goto(url);
    await page.waitForFunction(() => window.kioskTouchLogDraft?.transmission()?.state === 'error');
    await page.locator('[data-log-target="product:americano"]').click();
    await page.locator('dialog[open]').waitFor();
    assert(await page.locator('[data-log-target="cart-add"]').isEnabled());
    fixture.verify();
  } finally { await page.close(); await browser.close(); }
});

test('actual feature endpoint responds to the request; extension forwarding requires separate verification', { skip: !process.env.TOUCH_FEATURE_LIVE_URL }, async () => {
  const browser = await launch(); const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  try {
    const response = page.waitForResponse(r => r.url().endsWith('/features') && r.status() === 200);
    await page.goto(process.env.TOUCH_FEATURE_LIVE_URL);
    const received = await response, payload = received.request().postDataJSON(), result = await received.json();
    assert.equal(result.ai_available, true);
    assert.equal(result.support.preset, 'none');
    assert.equal(payload.touch.interaction.schema_version, 'touch-interaction-pilot-v1');
    assert.equal(payload.touch.interaction.outside_tap_ratio, null);
    assert.equal(result.session_id, await page.evaluate(() => window.kioskTouchLogDraft.read().serverSessionId));
  } finally { await page.close(); await browser.close(); }
});

test('feature transmission is disabled by default pending team agreement', { skip: !process.env.TOUCH_FEATURE_DEFAULT_URL }, async () => {
  const browser = await launch(); const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  try {
    const fixture = await installOrderResponses(page, bootstrap('default-off'));
    await page.goto(process.env.TOUCH_FEATURE_DEFAULT_URL);
    await page.locator('[data-log-target="product:americano"]').waitFor();
    await page.waitForTimeout(4300);
    assert.deepEqual(fixture.featureRequests, []);
    assert.equal(await page.evaluate(() => window.kioskTouchLogDraft.transmission()), null);
    fixture.verify();
  } finally { await page.close(); await browser.close(); }
});

test('development sample never uploads telemetry', { skip: !process.env.TOUCH_FEATURE_SAMPLE_URL }, async () => {
  const browser = await launch(); const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  try {
    const requests = [];
    page.on('request', request => { if (request.url().includes('/backend/')) requests.push(request.url()); });
    await page.goto(process.env.TOUCH_FEATURE_SAMPLE_URL);
    await page.locator('[data-log-target="product:americano"]').click();
    await page.waitForTimeout(4300);
    assert.deepEqual(requests, []);
    assert.equal(await page.evaluate(() => window.kioskTouchLogDraft.transmission()), null);
  } finally { await page.close(); await browser.close(); }
});
