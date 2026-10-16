import type { LogEvent, SavedLog } from './touchLog.ts';

// 보관 중인 원시 기록의 요약입니다. contract의 TouchFeatures가 아닙니다.
export type RawTouchCounts = {
  events: number; presses: number;
  activeTargetPresses: number; disabledTargetPresses: number; outsideTargetPresses: number; unknownTargetPresses: number;
  releases: number; cancellations: number; unknownEnds: number; interruptions: number;
  scrolls: number; screenEntries: number; categoryChanges: number;
  optionsOpened: number; optionsClosed: number; settingsChanges: number;
};
export type RawVisitSummary = { visitId: string | null; screen: string | null; counts: RawTouchCounts };
export type RawTouchSummary = {
  sessionId: string; serverSessionId: string | null; hasSessionStart: boolean;
  counts: RawTouchCounts; outsidePressRatio: number | null; visits: RawVisitSummary[];
};

function emptyCounts(): RawTouchCounts {
  return {
    events: 0, presses: 0, activeTargetPresses: 0, disabledTargetPresses: 0, outsideTargetPresses: 0, unknownTargetPresses: 0,
    releases: 0, cancellations: 0, unknownEnds: 0, interruptions: 0,
    scrolls: 0, screenEntries: 0, categoryChanges: 0, optionsOpened: 0, optionsClosed: 0, settingsChanges: 0,
  };
}

function recordOf(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function countEvent(counts: RawTouchCounts, event: LogEvent) {
  counts.events++;
  const data = recordOf(event.data);
  switch (event.kind) {
    case 'pointer_start': {
      counts.presses++;
      const target = recordOf(data?.target);
      if (data?.target === null) counts.outsideTargetPresses++;
      else if (target && (target.kind === 'button' || target.kind === 'a') && target.disabled === false) counts.activeTargetPresses++;
      else if (target && (target.kind === 'button' || target.kind === 'a') && target.disabled === true) counts.disabledTargetPresses++;
      else counts.unknownTargetPresses++;
      break;
    }
    case 'pointer_end':
      if (data?.cancelled === true) counts.cancellations++;
      else if (data?.cancelled === false) counts.releases++;
      else counts.unknownEnds++;
      break;
    case 'pointer_interrupted': counts.interruptions++; break;
    case 'scroll': counts.scrolls++; break;
    case 'screen_enter': counts.screenEntries++; break;
    case 'category_change': counts.categoryChanges++; break;
    case 'options_open': counts.optionsOpened++; break;
    case 'options_close': counts.optionsClosed++; break;
    case 'ui_settings_change': counts.settingsChanges++; break;
  }
}

export function summarizeTouchLog(saved: SavedLog): RawTouchSummary {
  const counts = emptyCounts();
  const visits = new Map<string, RawVisitSummary>();
  let hasSessionStart = false;
  for (const event of saved.events) {
    if (event.sessionId !== saved.sessionId) continue;
    countEvent(counts, event);
    if (event.kind === 'session_start') hasSessionStart = true;
    const visitId = typeof event.visitId === 'string' && event.visitId ? event.visitId : null;
    const screen = typeof event.screen === 'string' && event.screen ? event.screen : null;
    const key = JSON.stringify([visitId, screen]);
    let visit = visits.get(key);
    if (!visit) {
      visit = { visitId, screen, counts: emptyCounts() };
      visits.set(key, visit);
    }
    countEvent(visit.counts, event);
  }
  return {
    sessionId: saved.sessionId, serverSessionId: saved.serverSessionId, hasSessionStart, counts,
    // 입력 없음·대상 정보 누락을 관측 결과 0%로 채우지 않습니다.
    outsidePressRatio: counts.presses && !counts.unknownTargetPresses ? counts.outsideTargetPresses / counts.presses : null,
    visits: [...visits.values()],
  };
}
