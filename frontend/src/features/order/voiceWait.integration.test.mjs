import assert from 'node:assert/strict';
import test from 'node:test';
import { VoiceController } from '../voice/voiceController.ts';
import { FakeRecognition, factory, tick } from '../voice/voiceFakes.mjs';
import { createTouchLog } from './touchLog.ts';
import { buildTouchFeatureWindow } from './interactionFeatures.ts';

for (const ending of ['complete', 'stop', 'failure', 'off', 'session', 'hidden']) {
  test(`TTS controller → touch wait aggregation: ${ending}`, async t => {
    FakeRecognition.reset();
    let clock = 0, id = 0, finish;
    const recorder = createTouchLog(null, () => `v-${++id}`, () => clock);
    recorder.newSession('server-1');
    const context = { screen: 'menu', visitId: 'visit-1', settings: {} };
    const record = (kind, data) => recorder.record(context, kind, data);
    record('session_start'); record('screen_enter', { visibility: 'visible' });
    record('order_state_change', { before: null, after: { status: 'ready', completed: false } });
    const controller = new VoiceController({
      recognition: factory, autoOffMs: 0, pollIntervalMs: 1,
      api: { submit: async () => ({ request_id: 'request-1' }), get: async () => ({
        request_id: 'request-1', status: 'needs_confirmation', reply_text: '확인해 주세요', tool_calls: [], actions: [], error: null,
      }) },
      replySpeaker: () => new Promise(resolve => { finish = resolve; }),
    });
    let previous = null;
    const capture = () => {
      const { phase, enabled, microphoneActive } = controller.getSnapshot();
      const after = { phase, enabled, microphoneActive };
      record('voice_state_change', { before: previous, after }); previous = after;
    };
    const unsubscribe = controller.subscribe(capture);
    try {
      controller.setContext({ sessionId: 'server-1', screenId: 'menu' }); capture();
      clock = 1000;
      const inputId = record('pointer_start', { start: { x: 1, y: 1 }, target: null, pointerType: 'touch', isPrimary: true });
      record('pointer_end', { inputId, cancelled: false, maxObservedDistance: 0 });
      controller.setEnabled(true);
      clock = 1200; FakeRecognition.last().final(['커피 주세요', .9]);
      assert.equal(controller.getSnapshot().phase, 'processing');
      clock = 2000; await tick(10);
      assert.equal(controller.getSnapshot().phase, 'speaking');
      clock = 3000;
      let extra = buildTouchFeatureWindow(recorder.read(), clock, 1).touch.interaction;
      assert.equal(extra.voice_processing, false); assert.equal(extra.voice_busy, true);
      assert.equal(extra.voice_busy_ms, 1800);
      assert.equal(extra.since_last_input_excluding_system_busy_ms, 200);
      if (ending === 'stop') controller.stopReply();
      if (ending === 'off') controller.setEnabled(false);
      if (ending === 'session') controller.setContext({ sessionId: 'server-2', screenId: 'menu' });
      // The pagehide handler switches voice mode off.
      if (ending === 'hidden') controller.setEnabled(false);
      t.mock.timers.enable({ apis: ['setTimeout'] });
      finish(ending !== 'failure');
      await Promise.resolve();
      if (ending === 'complete') {
        clock = 3399;
        t.mock.timers.tick(399);
        assert.equal(controller.getSnapshot().microphoneActive, false);
        assert.equal(controller.getSnapshot().phase, 'speaking');
        assert.equal(buildTouchFeatureWindow(recorder.read(), clock, 2).touch.interaction.voice_busy, true);
        clock = 3400;
        t.mock.timers.tick(1);
      }
      await Promise.resolve();
      await Promise.resolve();
      assert.notEqual(controller.getSnapshot().phase, 'speaking');
      clock = 4000;
      extra = buildTouchFeatureWindow(recorder.read(), clock, 2).touch.interaction;
      assert.equal(extra.voice_busy, false);
      assert.equal(extra.since_last_input_excluding_system_busy_ms, ending === 'complete' ? 800 : 1200);
      assert.equal(FakeRecognition.instances.length, ending === 'complete' ? 2 : 1);
      if (ending === 'hidden') assert.equal(controller.getSnapshot().enabled, false);
    } finally { unsubscribe(); controller.dispose(); }
  });
}
