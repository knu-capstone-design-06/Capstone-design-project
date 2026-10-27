import type { LogEvent, SavedLog } from './touchLog.ts';

// 로컬 파일럿 전용입니다. 이 타입은 서버 TouchFeatures 계약을 대체하지 않습니다.
export type TouchPilotPolicy = {
  repeatMs: number | null;
  repeatPx: number | null;
  dwellMode: 'foreground_visit' | 'since_last_input' | null;
};
// 2026-10-25 프론트 담당자 선택. 팀 계약 합의나 불편 판단 임계값은 아닙니다.
export const touchPilotPolicy: TouchPilotPolicy = { repeatMs: 800, repeatPx: 24, dwellMode: 'foreground_visit' };
export type TouchPilotFeatures = {
  tap_count: number | null; miss_tap_count: number | null; repeat_tap_count: number | null;
  back_count: number | null; dwell_ms: number | null;
};
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {};
const time = (event: LogEvent) => Date.parse(event.occurredAt);
function point(value: unknown) {
  const p = object(value);
  return typeof p.x === 'number' && Number.isFinite(p.x) && typeof p.y === 'number' && Number.isFinite(p.y)
    ? { x: p.x, y: p.y } : null;
}
function repeatCount(events: LogEvent[], from: number, policy: TouchPilotPolicy): number | null {
  const { repeatMs, repeatPx } = policy;
  if (repeatMs === null || repeatPx === null || !Number.isFinite(repeatMs) || !Number.isFinite(repeatPx) || repeatMs < 0 || repeatPx < 0) return null;
  const ends = new Map<string, Record<string, unknown>>();
  const scrolled = new Set<string>();
  const interrupted = new Set<string>();
  for (const e of events) {
    const d = object(e.data);
    if (e.kind === 'pointer_end' && typeof d.inputId === 'string') ends.set(d.inputId, d);
    if (e.kind === 'pointer_interrupted' && typeof d.inputId === 'string') interrupted.add(d.inputId);
    if (e.kind === 'scroll' && Array.isArray(d.inputCandidates)) for (const id of d.inputCandidates) if (typeof id === 'string') scrolled.add(id);
  }
  const hasInputDetails = (e: LogEvent) => {
    const d = object(e.data), target = object(d.target), end = ends.get(e.id);
    return !!point(d.start) && typeof d.isPrimary === 'boolean' && ['mouse', 'touch', 'pen'].includes(String(d.pointerType))
      && (d.target === null || (typeof target.id === 'string' && ['button', 'a'].includes(String(target.kind)) && typeof target.disabled === 'boolean'))
      && (interrupted.has(e.id) || (typeof end?.cancelled === 'boolean' && typeof end.maxObservedDistance === 'number'
        && Number.isFinite(end.maxObservedDistance) && end.maxObservedDistance >= 0));
  };
  if (events.some(e => e.kind === 'pointer_start' && time(e) > from && !hasInputDetails(e))) return null;
  let previous: LogEvent | null = null;
  let count = 0;
  const eligible = (e: LogEvent) => {
    const d = object(e.data), end = ends.get(e.id), target = object(d.target);
    return hasInputDetails(e) && d.isPrimary === true
      && point(d.start) && (d.target === null || (typeof target.id === 'string' && target.disabled === false))
      && end?.cancelled === false && typeof end.maxObservedDistance === 'number' && end.maxObservedDistance <= repeatPx
      && !scrolled.has(e.id) && !interrupted.has(e.id);
  };
  for (const e of events) {
    if (['screen_enter', 'screen_leave', 'session_suspend', 'visibility_change'].includes(e.kind)) previous = null;
    if (e.kind !== 'pointer_start') continue;
    // 구간 안의 첫 누름도 직전 누름과 비교하므로 구간 밖 선행 기록의 누락을 0이나 반복으로 추정하지 않습니다.
    if (previous && time(e) > from && previous.visitId === e.visitId && time(e) - time(previous) <= repeatMs
      && !hasInputDetails(previous)) return null;
    if (previous && eligible(previous) && eligible(e)) {
      const a = object(previous.data), b = object(e.data), pa = point(a.start)!, pb = point(b.start)!;
      const sameTarget = a.target === null && b.target === null
        || typeof object(a.target).id === 'string' && object(a.target).id === object(b.target).id;
      if (time(e) > from && previous.visitId === e.visitId && a.pointerType === b.pointerType && sameTarget
        && time(e) - time(previous) <= repeatMs && Math.hypot(pa.x - pb.x, pa.y - pb.y) <= repeatPx) count++;
    }
    previous = e;
  }
  return count;
}

export function measureTouchPilot(saved: SavedLog, now = Date.now(), windowMs = 2000, policy = touchPilotPolicy) {
  const missing: TouchPilotFeatures = { tap_count: null, miss_tap_count: null, repeat_tap_count: null, back_count: null, dwell_ms: null };
  const events = saved.events.filter(e => e.sessionId === saved.sessionId && time(e) <= now);
  const from = now - windowMs;
  const invalid = !Number.isFinite(now) || !Number.isFinite(windowMs) || windowMs <= 0
    || saved.events.some(e => e.sessionId === saved.sessionId && (!Number.isFinite(time(e)) || time(e) > now))
    || events.some((e, i) => i > 0 && time(e) < time(events[i - 1]));
  if (invalid) return { features: missing, windowMs, from, to: now, observed: false, reason: '시각 또는 집계 구간을 확인할 수 없습니다.', foregroundVisitMs: null, sinceLastInputMs: null, policy: { ...policy } };
  // 세션 시작/재개부터 전경 관측이 연속한 구간에만 0을 포함한 통계를 냅니다.
  let observedSince: number | null = null;
  let currentVisit: LogEvent | null = null;
  let foreground = false, visibleSince: number | null = null, foregroundMs = 0, visibilityKnown = false;
  let lastInput: number | null = null;
  for (const e of events) {
    const t = time(e), d = object(e.data);
    if (e.kind === 'screen_enter') {
      currentVisit = e; foregroundMs = 0; lastInput = null;
      visibilityKnown = d.visibility === 'visible' || d.visibility === 'hidden';
      foreground = d.visibility === 'visible'; visibleSince = foreground ? t : null;
      if (!foreground) observedSince = null;
      if (observedSince === null && foreground) observedSince = t;
    }
    if (e.kind === 'pointer_start' && e.visitId === currentVisit?.visitId) lastInput = t;
    if (e.kind === 'visibility_change' || e.kind === 'screen_leave' || e.kind === 'session_suspend' || e.kind === 'session_end') {
      if (visibleSince !== null) foregroundMs += Math.max(0, t - visibleSince);
      const visible = e.kind === 'visibility_change' && d.visibility === 'visible';
      if (e.kind === 'visibility_change') visibilityKnown &&= d.visibility === 'visible' || d.visibility === 'hidden';
      foreground = visible; visibleSince = visible ? t : null;
      // 전경 화면 간 이동은 관측을 잇고, 페이지 중단·백그라운드는 끊습니다.
      const screenTransition = e.kind === 'screen_leave' && typeof d.to === 'string';
      if (!visible && !screenTransition) observedSince = null;
      else if (visible) observedSince = t;
    }
  }
  const observed = observedSince !== null && observedSince <= from;
  const window = events.filter(e => time(e) > from);
  const presses = window.filter(e => e.kind === 'pointer_start');
  const targetKnown = presses.every(e => {
    const d = object(e.data), target = object(d.target);
    return d.target === null || (['button', 'a'].includes(String(target.kind)) && typeof target.disabled === 'boolean');
  });
  const visitMs = currentVisit && visibilityKnown ? Math.round(foregroundMs + (foreground && visibleSince !== null ? now - visibleSince : 0)) : null;
  const idleMs = lastInput !== null && foreground ? Math.round(now - lastInput) : null;
  return {
    features: {
      tap_count: observed ? presses.length : null,
      miss_tap_count: observed && targetKnown ? presses.filter(e => object(e.data).target === null).length : null,
      repeat_tap_count: observed ? repeatCount(events, from, policy) : null,
      back_count: observed && window.every(e => e.kind !== 'screen_enter' || typeof object(e.data).from === 'string')
        ? window.filter(e => e.kind === 'screen_enter' && e.screen === 'menu' && object(e.data).from === 'review').length : null,
      dwell_ms: policy.dwellMode === 'foreground_visit' ? visitMs : policy.dwellMode === 'since_last_input' ? idleMs : null,
    },
    windowMs, from, to: now, observed, reason: observed ? null : '집계 구간 전체의 전경 관측이 없습니다.',
    foregroundVisitMs: visitMs, sinceLastInputMs: idleMs, policy: { ...policy },
  };
}
