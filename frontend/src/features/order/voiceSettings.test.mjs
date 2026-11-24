import assert from 'node:assert/strict';
import test from 'node:test';
import { initialSettings } from './model.ts';
import { createVoiceSettingsReceiver } from './voiceSettings.ts';

function setup() {
  const applied = [];
  const receiver = createVoiceSettingsReceiver(changes => applied.push(changes));
  const context = { sessionId: 'session-1', screen: 'menu', available: true, settings: { ...initialSettings } };
  receiver.setContext(context);
  return { receiver, context, applied };
}

test('한 요청에서 여섯 설정을 변경하고 끄기 요청도 처리한다', () => {
  const { receiver, context, applied } = setup();
  const changes = Object.fromEntries(Object.keys(initialSettings).map(key => [key, true]));
  assert.equal(receiver.prepare()(changes), true);
  assert.deepEqual(applied, [changes]);
  receiver.setContext({ ...context, settings: changes });
  assert.equal(receiver.prepare()({ largeText: false, lowScreen: false }), true);
  assert.deepEqual(applied[1], { largeText: false, lowScreen: false });
  assert.deepEqual(context.settings, initialSettings, '입력 맥락을 직접 수정하지 않는다');
});

test('자연어·추측한 서버 응답·알 수 없는 필드·잘못된 값은 일부도 적용하지 않는다', () => {
  const { receiver, applied } = setup();
  for (const value of [null, [], {}, '글씨 크게 해줘', { largeText: 'true' }, { largeText: 1 },
    { largeText: true, unknown: false }, { largeText: true, lowScreen: null },
    { preset: 'large_text' }, { actions: ['ui_changed'] }, JSON.parse('{"__proto__":true,"largeText":true}')]) {
    assert.equal(receiver.prepare()(value), false, JSON.stringify(value));
  }
  assert.deepEqual(applied, []);
});

test('현재와 같은 값은 적용·알림을 만들지 않고 변경된 키만 전달한다', () => {
  const { receiver, applied } = setup();
  assert.equal(receiver.prepare()({ largeText: false }), false);
  assert.equal(receiver.prepare()({ largeText: true, lowScreen: false }), true);
  assert.deepEqual(applied, [{ largeText: true }]);
});

test('응답 중복과 React 갱신 전에 도착한 다른 요청을 한 번만 처리한다', () => {
  const { receiver, applied } = setup();
  const first = receiver.prepare(), second = receiver.prepare();
  assert.equal(first({ largeText: true }), true);
  assert.equal(first({ lowScreen: true }), false);
  assert.equal(second({ largeButton: true }), false);
  assert.deepEqual(applied, [{ largeText: true }]);
});

test('실패한 응답도 소비해 같은 요청을 다른 내용으로 다시 실행하지 않는다', () => {
  const { receiver, applied } = setup();
  const finish = receiver.prepare();
  assert.equal(finish({ largeText: 'true' }), false);
  assert.equal(finish({ largeText: true }), false);
  assert.deepEqual(applied, []);
});

for (const [name, change] of [
  ['새 세션', { sessionId: 'session-2' }], ['세션 종료', { sessionId: null }],
  ['화면 이동', { screen: 'review' }], ['모달·마이크 종료·숨김·주문 대기', { available: false }],
  ['터치 또는 서버 지원 설정 변경', { settings: { ...initialSettings, highContrast: true } }],
]) {
  test(`${name} 이전에 준비한 응답은 원래 맥락으로 돌아와도 적용하지 않는다`, () => {
    const { receiver, context, applied } = setup();
    const finish = receiver.prepare();
    receiver.setContext({ ...context, ...change });
    receiver.setContext(context);
    assert.equal(finish({ largeText: true }), false);
    assert.deepEqual(applied, []);
  });
}

test('세션 없음·메뉴 외 화면·적용 불가 상태에서는 요청 맥락을 만들지 않는다', () => {
  const { receiver, context } = setup();
  for (const change of [{ sessionId: null }, { sessionId: '' }, { screen: 'review' }, { screen: 'complete' }, { available: false }]) {
    receiver.setContext({ ...context, ...change });
    assert.equal(receiver.prepare(), null);
  }
});

test('설정값이 같아도 수동 초기화·복귀·이탈로 무효화한 요청은 적용하지 않는다', () => {
  const { receiver, applied } = setup();
  const finish = receiver.prepare();
  receiver.invalidate();
  assert.equal(finish({ lowScreen: true }), false);
  assert.deepEqual(applied, []);
});
