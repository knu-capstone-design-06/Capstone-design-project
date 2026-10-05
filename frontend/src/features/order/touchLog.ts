// 로컬 검토용 초안. contract의 집계 통계나 서버 전송 형식이 아닙니다.
export const touchLogKey = 'kiosk-touch-log-draft-v1';
export const logLimit = 1000;
export type Point = { x: number; y: number };
export type Rect = { x: number; y: number; width: number; height: number };
export type LogContext = { screen: string; visitId: string; settings: unknown };
export type LogEvent = LogContext & {
  id: string; sessionId: string; occurredAt: string; elapsedMs: number;
  kind: string; data: unknown;
};
type StoragePort = Pick<Storage, 'getItem' | 'setItem'>;
export type SavedLog = { version: 1; sessionId: string; startedAt: number; events: LogEvent[] };

export function distanceToRect(point: Point, rect: Rect) {
  return Math.hypot(
    Math.max(rect.x - point.x, 0, point.x - rect.x - rect.width),
    Math.max(rect.y - point.y, 0, point.y - rect.y - rect.height),
  );
}

export function createTouchLog(storage: StoragePort | null, id = () => crypto.randomUUID(), now = () => Date.now()) {
  let warning: string | null = null;
  let saved: SavedLog = { version: 1, sessionId: id(), startedAt: now(), events: [] };
  let resumed = false;
  try {
    const raw = storage?.getItem(touchLogKey);
    if (raw) {
      const value = JSON.parse(raw) as SavedLog;
      if (value.version !== 1 || typeof value.sessionId !== 'string' || !Number.isFinite(value.startedAt)
        || !Array.isArray(value.events) || !value.events.every(event => event && typeof event.id === 'string'
          && typeof event.sessionId === 'string' && typeof event.kind === 'string')) throw new Error('invalid log');
      saved = { ...value, events: value.events.slice(-logLimit) };
      resumed = true;
    }
  } catch { warning = '저장된 로그를 복원하지 못해 새 로컬 세션을 시작했습니다.'; }
  if (!storage) warning = '저장소를 사용할 수 없어 메모리에만 기록합니다.';
  function persist() {
    try { storage?.setItem(touchLogKey, JSON.stringify(saved)); }
    catch { warning = '로그 저장 실패: 메모리에만 기록되며 새로고침 시 유실될 수 있습니다.'; }
  }
  function record(context: LogContext, kind: string, data: unknown = null) {
    const timestamp = now();
    const event: LogEvent = {
      ...context, id: id(), sessionId: saved.sessionId,
      occurredAt: new Date(timestamp).toISOString(), elapsedMs: Math.max(0, timestamp - saved.startedAt), kind, data,
    };
    // 설정·이벤트 객체의 후속 변경으로 이전 기록이 변하지 않게 복사합니다.
    saved.events.push(structuredClone(event));
    saved.events = saved.events.slice(-logLimit);
    persist();
    return event.id;
  }
  return {
    resumed,
    record,
    newSession() { saved.sessionId = id(); saved.startedAt = now(); persist(); },
    read() { return structuredClone(saved); },
    getWarning() { return warning; },
  };
}
