import assert from 'node:assert/strict';
import test from 'node:test';
import { createTouchLog, distanceToRect, logLimit, touchLogKey } from './touchLog.ts';

const context = () => ({ screen: 'menu', visitId: 'visit-1', settings: { largeButton: false } });
function memoryStorage() {
  const values = new Map();
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
}

test('버튼 내부·변·모서리까지 실제 거리만 계산하며 임계값을 사용하지 않는다', () => {
  const rect = { x: 10, y: 20, width: 100, height: 40 };
  assert.equal(distanceToRect({ x: 50, y: 30 }, rect), 0);
  assert.equal(distanceToRect({ x: 110, y: 60 }, rect), 0);
  assert.equal(distanceToRect({ x: 116, y: 30 }, rect), 6);
  assert.equal(distanceToRect({ x: 113, y: 64 }, rect), 5);
});

test('새로고침 복원은 세션을 유지하고 새 주문은 분리하며 이전 로그를 유지한다', () => {
  const storage = memoryStorage();
  let nextId = 0;
  let timestamp = 1000;
  const id = () => `id-${++nextId}`;
  const now = () => timestamp;
  const first = createTouchLog(storage, id, now);
  const firstSession = first.read().sessionId;
  timestamp = 1100;
  first.record(context(), 'pointer_start', { start: { x: 1, y: 2 } });
  const restored = createTouchLog(storage, id, now);
  assert.equal(restored.resumed, true);
  assert.equal(restored.read().sessionId, firstSession);
  assert.equal(restored.read().events[0].elapsedMs, 100);
  restored.newSession();
  restored.record(context(), 'session_start');
  const result = restored.read();
  assert.notEqual(result.sessionId, firstSession);
  assert.equal(result.events[0].sessionId, firstSession);
  assert.equal(result.events[1].sessionId, result.sessionId);
});

test('설정과 읽기 결과 변경이 저장된 과거 로그를 바꾸지 않는다', () => {
  const recorder = createTouchLog(memoryStorage());
  const original = context();
  recorder.record(original, 'pointer_start');
  original.settings.largeButton = true;
  const snapshot = recorder.read();
  snapshot.events[0].settings.largeButton = true;
  assert.equal(recorder.read().events[0].settings.largeButton, false);
});

test('저장 불가·손상 데이터에서도 기록을 계속하고 상태로 알린다', () => {
  const broken = { getItem: () => '{broken', setItem: () => { throw new Error('quota'); } };
  const recorder = createTouchLog(broken);
  assert.equal(recorder.resumed, false);
  recorder.record(context(), 'pointer_start');
  assert.equal(recorder.read().events.length, 1);
  assert.match(recorder.getWarning(), /저장 실패/);
  const malformed = memoryStorage();
  malformed.setItem(touchLogKey, JSON.stringify({ version: 1, sessionId: 'x', startedAt: 0, events: [null] }));
  assert.equal(createTouchLog(malformed).resumed, false);
});

test('로컬 버퍼는 최신 기록만 제한된 개수로 유지한다', () => {
  const recorder = createTouchLog(null);
  for (let i = 0; i <= logLimit; i++) recorder.record(context(), 'scroll', { i });
  const events = recorder.read().events;
  assert.equal(events.length, logLimit);
  assert.equal(events[0].data.i, 1);
  assert.equal(events.at(-1).data.i, logLimit);
});
