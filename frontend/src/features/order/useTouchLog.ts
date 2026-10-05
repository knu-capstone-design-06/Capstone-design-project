import { useEffect, useRef } from 'react';
import { createTouchLog, distanceToRect } from './touchLog.ts';
import type { LogContext, Point, Rect } from './touchLog.ts';
import type { Settings } from './model.ts';

type DraftInspector = { read: () => unknown; exportJson: () => void; status: () => string | null };
declare global { interface Window { kioskTouchLogDraft?: DraftInspector } }
type Gesture = {
  id: string; context: LogContext; start: Point; last: Point; maxDistance: number;
  cancelled: boolean;
};
const selector = 'button, a[href]';
function rectOf(element: HTMLElement): Rect {
  const rect = element.getBoundingClientRect();
  return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
}
function targetInfo(element: HTMLElement) {
  return {
    id: element.dataset.logTarget ?? null,
    kind: element.tagName.toLowerCase(),
    disabled: element.matches(':disabled, [aria-disabled="true"]'),
    rect: rectOf(element),
  };
}

export function useTouchLog(screen: string, category: string, productId: string | null, settings: Settings) {
  const root = useRef<HTMLDivElement>(null);
  const tracker = useRef<ReturnType<typeof createTouchLog> | null>(null);
  const context = useRef<LogContext>({ screen, visitId: '', settings });
  const previous = useRef<{ screen: string; category: string; productId: string | null; settings: Settings } | null>(null);

  // effect에서 초기화하고 StrictMode 재설정에서도 세션·방문을 유지합니다.
  useEffect(() => {
    if (!tracker.current) {
      let storage: Storage | null = null;
      try { storage = sessionStorage; } catch { /* 메모리에만 기록 */ }
      tracker.current = createTouchLog(storage);
      context.current = { screen, visitId: crypto.randomUUID(), settings: { ...settings } };
      tracker.current.record(context.current, tracker.current.resumed ? 'session_resume' : 'session_start');
      tracker.current.record(context.current, 'screen_enter');
      previous.current = { screen, category, productId, settings: { ...settings } };
    }
    const recorder = tracker.current;
    const gestures = new Map<number, Gesture>();
    const cancelled = new Map<number, Gesture>();
    const record = (kind: string, data: unknown) => recorder.record(context.current, kind, data);
    const point = (event: PointerEvent) => ({ x: event.clientX, y: event.clientY });
    function down(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) return;
      // 이전 취소 입력을 다음 제스처와 연결하지 않습니다.
      if (!gestures.size) cancelled.clear();
      const scope = root.current.querySelector<HTMLDialogElement>('dialog[open]') ?? root.current;
      const element = (event.target as Element).closest<HTMLElement>(selector);
      const target = element && scope.contains(element) ? targetInfo(element) : null;
      const start = point(event);
      const candidates = target ? [] : [...scope.querySelectorAll<HTMLElement>(selector)]
        .filter(candidate => !candidate.matches(':disabled, [aria-disabled="true"]')
          && candidate.getClientRects().length > 0 && getComputedStyle(candidate).visibility === 'visible')
        .map(candidate => ({ ...targetInfo(candidate), distance: distanceToRect(start, rectOf(candidate)) }));
      const minimum = candidates.length ? Math.min(...candidates.map(candidate => candidate.distance)) : null;
      const id = record('pointer_start', {
        start, target,
        nearestCandidates: candidates.filter(candidate => candidate.distance === minimum),
      });
      gestures.set(event.pointerId, { id, context: structuredClone(context.current), start, last: start, maxDistance: 0, cancelled: false });
    }
    function move(event: PointerEvent) {
      const gesture = gestures.get(event.pointerId);
      if (!gesture) return;
      gesture.last = point(event);
      gesture.maxDistance = Math.max(gesture.maxDistance, Math.hypot(gesture.last.x - gesture.start.x, gesture.last.y - gesture.start.y));
    }
    function end(event: PointerEvent) {
      const gesture = gestures.get(event.pointerId);
      if (!gesture) return;
      if (event.type !== 'pointercancel') move(event);
      gesture.cancelled = event.type === 'pointercancel';
      recorder.record(gesture.context, 'pointer_end', {
        inputId: gesture.id, start: gesture.start,
        end: gesture.cancelled ? null : gesture.last, lastObserved: gesture.last,
        maxObservedDistance: gesture.maxDistance, cancelled: gesture.cancelled,
      });
      gestures.delete(event.pointerId);
      if (gesture.cancelled) cancelled.set(event.pointerId, gesture);
    }
    const positions = new WeakMap<Element, Point>();
    function scroll(event: Event) {
      const element = event.target === document ? document.scrollingElement : event.target;
      if (!(element instanceof Element)) return;
      if (element !== document.scrollingElement && !root.current?.contains(element)) return;
      const position = { x: element.scrollLeft, y: element.scrollTop };
      const before = positions.get(element);
      if (before && before.x === position.x && before.y === position.y) return;
      positions.set(element, position);
      record('scroll', {
        container: element === document.scrollingElement ? 'document' : (element as HTMLElement).dataset.logTarget ?? null,
        before: before ?? null, after: position,
        // 시간상 겹치는 후보일 뿐, 프로그램 스크롤이나 입력 의도를 확정하지 않습니다.
        inputCandidates: [...gestures.values(), ...cancelled.values()].map(gesture => gesture.id),
      });
    }
    if (document.scrollingElement) positions.set(document.scrollingElement, { x: document.scrollingElement.scrollLeft, y: document.scrollingElement.scrollTop });
    root.current?.querySelectorAll('*').forEach(element => positions.set(element, { x: element.scrollLeft, y: element.scrollTop }));
    function touchEnd(event: TouchEvent) { if (!event.touches.length) cancelled.clear(); }
    function pageHide() {
      for (const gesture of gestures.values()) recorder.record(gesture.context, 'pointer_interrupted', { inputId: gesture.id, lastObserved: gesture.last });
      gestures.clear(); cancelled.clear();
      record('screen_leave', { reason: 'pagehide' });
      record('session_suspend', { reason: 'pagehide' });
    }
    function pageShow(event: PageTransitionEvent) {
      if (event.persisted) {
        context.current = { ...context.current, visitId: crypto.randomUUID() };
        record('session_resume', { reason: 'bfcache' }); record('screen_enter', null);
      }
    }
    const inspector: DraftInspector = {
      read: () => recorder.read(), status: () => recorder.getWarning(),
      exportJson() {
        const url = URL.createObjectURL(new Blob([JSON.stringify(recorder.read(), null, 2)], { type: 'application/json' }));
        const link = document.createElement('a'); link.href = url; link.download = 'touch-log-draft.json'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
    };
    window.kioskTouchLogDraft = inspector;
    document.addEventListener('pointerdown', down, true);
    document.addEventListener('pointermove', move, true);
    document.addEventListener('pointerup', end, true);
    document.addEventListener('pointercancel', end, true);
    document.addEventListener('scroll', scroll, true);
    document.addEventListener('touchend', touchEnd, { passive: true });
    document.addEventListener('touchcancel', touchEnd, { passive: true });
    window.addEventListener('pagehide', pageHide);
    window.addEventListener('pageshow', pageShow);
    return () => {
      document.removeEventListener('pointerdown', down, true); document.removeEventListener('pointermove', move, true);
      document.removeEventListener('pointerup', end, true); document.removeEventListener('pointercancel', end, true);
      document.removeEventListener('scroll', scroll, true);
      document.removeEventListener('touchend', touchEnd); document.removeEventListener('touchcancel', touchEnd);
      window.removeEventListener('pagehide', pageHide); window.removeEventListener('pageshow', pageShow);
      if (window.kioskTouchLogDraft === inspector) delete window.kioskTouchLogDraft;
    };
  }, []);

  useEffect(() => {
    const recorder = tracker.current;
    const prior = previous.current;
    if (!recorder || !prior) return;
    if (prior.screen !== screen) {
      recorder.record(context.current, 'screen_leave', { to: screen });
      context.current = { screen, visitId: crypto.randomUUID(), settings: { ...settings } };
      recorder.record(context.current, 'screen_enter', { from: prior.screen });
    }
    if (prior.category !== category) recorder.record(context.current, 'category_change', { from: prior.category, to: category });
    if (prior.productId !== productId) {
      if (prior.productId) recorder.record(context.current, 'options_close', { productId: prior.productId });
      if (productId) recorder.record(context.current, 'options_open', { productId });
    }
    if (JSON.stringify(prior.settings) !== JSON.stringify(settings)) {
      recorder.record(context.current, 'ui_settings_change', { before: prior.settings, after: settings });
    }
    context.current.settings = { ...settings };
    previous.current = { screen, category, productId, settings: { ...settings } };
  }, [screen, category, productId, settings]);

  function startNewSession() {
    const recorder = tracker.current;
    if (!recorder) return;
    recorder.record(context.current, 'screen_leave', { reason: 'new_order' });
    recorder.record(context.current, 'session_end', { reason: 'new_order' });
    recorder.newSession();
    context.current = { screen: 'menu', visitId: crypto.randomUUID(), settings: structuredClone(context.current.settings) };
    recorder.record(context.current, 'session_start', { reason: 'new_order' });
    recorder.record(context.current, 'screen_enter', { from: 'complete' });
    if (previous.current) previous.current.screen = 'menu';
  }
  return { root, startNewSession };
}
