import type { FeatureWindowRequest, SceneSignals, TouchFeatures } from '../../shared/api/types.ts';
import type { FeatureLog, LogEvent } from './touchLog.ts';
import { measureTouchPilot, touchPilotPolicy } from './touchLogFeatures.ts';
import { observedWaitMs, voiceBusy, voicePhase } from './interactionWait.ts';
import { doubleClickMs } from './utils/timing.ts';

const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {};
const at = (event: LogEvent) => Date.parse(event.occurredAt);
const data = (event: LogEvent) => object(event.data);
const busy = (state: Record<string, unknown>) => state.status === 'loading' || state.status === 'saving';
const last = (events: LogEvent[], predicate: (event: LogEvent) => boolean) => [...events].reverse().find(predicate);
// 보내는 터치 창의 길이이자 다음 창까지의 간격: AI 엔진의 창 간격(비전 segment_s 1초 [파일럿])과 같게 두어 양쪽이 시간을 같은 길이로 자르고, 창은 겹치지 않습니다(backend는 최근 구간의 창별 횟수를 더하고, 엔진은 두 창에 걸친 줄을 비움).
export const FEATURE_WINDOW_MS = 1000;

// 누름(pointer_start)의 대상 정보: target 필드가 있는지, 버튼 밖(null)인지, 닿은 버튼의 ID, 가장 가까운 후보의 ID, 시작 좌표
const hasTarget = (press: LogEvent) => 'target' in data(press);
const missed = (press: LogEvent) => hasTarget(press) && data(press).target === null;
const targetId = (press: LogEvent) => { const id = object(data(press).target).id; return typeof id === 'string' && id ? id : null; };
const candidateIds = (press: LogEvent) => {
  const list = data(press).nearestCandidates;
  return Array.isArray(list) ? list.map(candidate => object(candidate).id).filter((id): id is string => typeof id === 'string' && id !== '') : [];
};
const startPoint = (press: LogEvent) => {
  const p = object(data(press).start);
  return typeof p.x === 'number' && Number.isFinite(p.x) && typeof p.y === 'number' && Number.isFinite(p.y) ? { x: p.x, y: p.y } : null;
};

/**
 * touch.scene_signals(touch-scene-signals-pilot-v1): backend의 장면 행이 읽는 이 구간((from, 끝])의 두 수입니다. 셀 수 없으면 null입니다.
 * events는 이 세션의 기록(구간 끝까지, 기록 순서)이고, historyTrimmed는 보관 기록의 앞부분이 빠졌는지입니다.
 * near_miss_fix_count(4-1): 구간 안의 누름 가운데 바로 앞 누름을 고친 누름의 수입니다. 앞 누름이 어느 버튼에도 닿지 않았고(target null)
 *   이 누름(같은 세션의 다음 누름)이 앞 누름의 가장 가까운 후보(nearestCandidates) 가운데 하나에 닿으면 고친 것입니다. 시간·거리 한계는
 *   없습니다(비전 모듈 ai-engine/app/modules/vision/touch.py의 near_miss_fix_count 정의를 고친 누름의 구간에서 셈). 구간 안에 target 필드가
 *   없는 누름이 있거나, 구간 안 누름의 앞 누름이 빠진 기록에 있었을 수 있으면 null입니다.
 * zoom_attempt_count(2-1): 확대 시도(글자를 두 번 누름)의 수입니다. 연달은 두 누름이 둘 다 버튼에 닿지 않고, 둘째가 첫째에서 두 번 클릭
 *   간격(doubleClickMs) 안이며 같은 자리 거리(touchPilotPolicy.repeatPx) 안이면 둘째 누름의 구간에서 하나로 셉니다. 메뉴 이름과 가격은
 *   상품 버튼 안에 있으므로 제목·안내·빈 곳의 글자만 셉니다. 세 번 누르면 연달은 두 쌍이라 둘입니다. 구간 안에 target 필드나 시작 좌표가 없는
 *   누름이 있거나 같은 자리 거리가 정해지지 않았으면 null입니다. 두 손가락 벌리기는 브라우저 확대에 맡겨 기록되지 않으므로 세지 않습니다.
 * can_offer(1-1·1-2): 화면이 이 구간을 만든 때 묻기를 띄울 수 있었는지(OrderPage의 canOfferSupport)이며 전송기가 넘깁니다. 모르면 null입니다.
 */
export function measureSceneSignals(events: LogEvent[], from: number, historyTrimmed: boolean, canOffer: boolean | null = null): SceneSignals {
  const presses = events.filter(e => e.kind === 'pointer_start');
  const { repeatPx } = touchPilotPolicy;
  let fixes: number | null = 0;
  let zooms: number | null = repeatPx === null || !Number.isFinite(repeatPx) ? null : 0;
  presses.forEach((press, index) => {
    if (at(press) <= from) return;
    const before = index > 0 ? presses[index - 1] : null;
    if (!hasTarget(press)) { fixes = null; zooms = null; return; }
    if (fixes !== null) {
      if (!before && historyTrimmed) fixes = null;
      else if (before && missed(before)) { const id = targetId(press); if (id && candidateIds(before).includes(id)) fixes++; }
    }
    if (zooms !== null) {
      const b = startPoint(press);
      if (!b) { zooms = null; return; }
      if (!before || !missed(before) || !missed(press) || at(press) - at(before) > doubleClickMs) return;
      const a = startPoint(before);
      if (!a) zooms = null;
      else if (Math.hypot(a.x - b.x, a.y - b.y) <= repeatPx!) zooms++;
    }
  });
  return { schema_version: 'touch-scene-signals-pilot-v1', near_miss_fix_count: fixes, zoom_attempt_count: zooms, can_offer: canOffer };
}

export function featureInputLookbackStart(end: number) {
  return end - FEATURE_WINDOW_MS - (touchPilotPolicy.repeatMs ?? 0);
}

export function hasFeatureHistory(saved: FeatureLog, end: number) {
  return saved.discardedThrough === undefined || saved.discardedThrough <= featureInputLookbackStart(end);
}

/**
 * Existing local pilot policy, with observable interaction counts. No discomfort labels.
 * canOffer: the screen's own gate for showing an ask while this window is built (touch.scene_signals.can_offer); null = not known.
 */
export function buildTouchFeatureWindow(saved: FeatureLog, now: number, sequence: number, observedAt = now, canOffer: boolean | null = null): FeatureWindowRequest | null {
  if (!saved.serverSessionId || !hasFeatureHistory(saved, now)) return null;
  const pilot = measureTouchPilot(saved, now, FEATURE_WINDOW_MS, undefined, observedAt);
  // The existing five required integer fields cannot represent unobserved values.
  if (!pilot.observed || Object.values(pilot.features).some(value => value === null)) return null;
  const events = saved.events.filter(e => e.sessionId === saved.sessionId && e.serverSessionId === saved.serverSessionId && at(e) <= now);
  const current = last(events, e => e.kind === 'screen_enter');
  if (!current || current.screen === 'complete') return null;
  const window = events.filter(e => at(e) > pilot.from);
  const count = (kind: string) => window.filter(e => e.kind === kind).length;
  const changed = (kind: string) => {
    const baseline = events.find(e => e.kind === kind);
    return window.filter(e => e.kind === kind && (data(e).before !== null || e !== baseline));
  };
  const lastState = (kind: string) => {
    const event = last(events, e => e.kind === kind);
    return event ? object(data(event).after) : null;
  };
  const order = lastState('order_state_change');
  if (!order || order.completed !== false || !['ready', 'saving'].includes(String(order.status))) return null;
  const voice = lastState('voice_state_change');
  const phase = voicePhase(voice?.phase);
  const lastInput = pilot.sinceLastInputMs;
  const systemWait = lastInput === null ? null : observedWaitMs(events, now - lastInput, now, true);
  const selectionEvent = last(events, e => e.kind === 'selection_state_change');
  const settingsEvent = last(events, e => e.kind === 'ui_settings_change' || e.kind === 'screen_enter');
  const settings = object(settingsEvent?.kind === 'ui_settings_change' ? data(settingsEvent).after : settingsEvent?.settings);

  // Integrate the observed UI busy state, including a request already pending at window start.
  const baseline = last(events, e => e.kind === 'order_state_change' && at(e) <= pilot.from);
  let orderBusyMs: number | null = baseline ? 0 : null;
  if (baseline) {
    let previous = object(data(baseline).after), cursor = pilot.from;
    for (const event of window.filter(e => e.kind === 'order_state_change')) {
      if (busy(previous)) orderBusyMs! += at(event) - cursor;
      previous = object(data(event).after); cursor = at(event);
    }
    if (busy(previous)) orderBusyMs! += now - cursor;
  }
  let revisits: number | null = events.some(e => e.kind === 'session_start') ? 0 : null;
  const seen = new Set<string>();
  for (const event of events.filter(e => e.kind === 'screen_enter')) {
    if (revisits !== null && at(event) > pilot.from && seen.has(event.screen)) revisits++;
    seen.add(event.screen);
  }
  const cartChanges = changed('order_state_change').filter(e => {
    const before = object(object(data(e).before).cart), after = object(object(data(e).after).cart);
    return typeof before.version === 'number' && typeof after.version === 'number' && after.version > before.version;
  }).length;
  // Continuous distance evidence avoids inventing a near-button threshold or intended target.
  const outsideDistances = window.filter(e => e.kind === 'pointer_start' && data(e).target === null).flatMap(e => {
    const candidates = data(e).nearestCandidates;
    if (!Array.isArray(candidates)) return [];
    const distances = candidates.map(candidate => object(candidate).distance)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0);
    return distances.length ? [Math.min(...distances)] : [];
  });
  const touch = pilot.features as TouchFeatures;
  return {
    screen_id: current.screen,
    window_start: new Date(pilot.from).toISOString(), window_end: new Date(now).toISOString(),
    vision: null,
    touch: {
      ...touch,
      interaction: {
        schema_version: 'touch-interaction-pilot-v1', visit_id: current.visitId, window_sequence: sequence,
        outside_tap_ratio: touch.tap_count ? touch.miss_tap_count / touch.tap_count : null,
        outside_nearest_distance_mean_px: outsideDistances.length
          ? outsideDistances.reduce((sum, value) => sum + value, 0) / outsideDistances.length : null,
        outside_nearest_distance_sample_count: outsideDistances.length,
        pointer_cancel_count: window.filter(e => e.kind === 'pointer_end' && data(e).cancelled === true).length,
        pointer_interrupted_count: count('pointer_interrupted'), scroll_event_count: count('scroll'),
        category_change_count: count('category_change'), options_open_count: count('options_open'), options_close_count: count('options_close'),
        screen_transition_count: window.filter(e => e.kind === 'screen_enter' && typeof data(e).from === 'string').length,
        screen_revisit_count: revisits, cart_change_count: cartChanges,
        selection_change_count: events.some(e => e.kind === 'session_start')
          && events.some(e => e.kind === 'selection_state_change' && data(e).before === null)
          ? changed('selection_state_change').length : null,
        ui_settings_change_count: count('ui_settings_change'), voice_state_change_count: changed('voice_state_change').length,
        since_last_input_ms: pilot.sinceLastInputMs, order_busy_ms: orderBusyMs === null ? null : Math.round(orderBusyMs),
        options_open: selectionEvent ? data(selectionEvent).after !== null : null,
        order_busy: busy(order), voice_enabled: typeof voice?.enabled === 'boolean' ? voice.enabled : null,
        microphone_active: typeof voice?.microphoneActive === 'boolean' ? voice.microphoneActive : null,
        voice_processing: typeof voice?.phase === 'string' ? voice.phase === 'processing' : null,
        voice_phase: phase, voice_speaking: phase === null ? null : phase === 'speaking',
        voice_busy: voiceBusy(phase), voice_busy_ms: observedWaitMs(events, pilot.from, now, false),
        since_last_input_excluding_system_busy_ms: lastInput === null || systemWait === null ? null : lastInput - systemWait,
        voice_auto_off: voice?.autoOff === 'silence' || voice?.autoOff === 'idle' ? voice.autoOff : null,
        ui_settings: {
          large_text: settings.largeText === true, large_button: settings.largeButton === true,
          simple_screen: settings.simpleScreen === true, step_guide: settings.stepGuide === true,
          low_screen: settings.lowScreen === true, high_contrast: settings.highContrast === true,
        },
      },
      // touch.interaction의 형제 블록입니다. 전송기가 파일럿 설정(VITE_TOUCH_INTERACTION_DRAFT)에서만 보냅니다.
      scene_signals: measureSceneSignals(events, pilot.from, saved.discardedThrough !== undefined, canOffer),
    },
  };
}
