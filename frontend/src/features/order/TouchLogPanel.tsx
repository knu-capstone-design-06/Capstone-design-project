/// <reference types="vite/client" />
import { useEffect, useMemo, useState } from 'react';
import type { SavedLog } from './touchLog.ts';
import { logLimit } from './touchLog.ts';
import { summarizeTouchLog } from './touchLogSummary.ts';
import type { RawTouchCounts } from './touchLogSummary.ts';
import { measureTouchPilot, touchPilotPolicy } from './touchLogFeatures.ts';
import type { TouchPilotPolicy } from './touchLogFeatures.ts';
import './touchLogPanel.css';

const labels: Record<string, string> = {
  pointer_start: '누름 시작', pointer_end: '누름 종료·취소', pointer_interrupted: '입력 중단',
  scroll: '스크롤 관측', screen_enter: '화면 진입', screen_leave: '화면 이탈',
  category_change: '분류 변경', options_open: '옵션 열기', options_close: '옵션 닫기',
  ui_settings_change: 'UI 설정 변경', session_start: '세션 시작', session_resume: '세션 재개',
  visibility_change: '전경·백그라운드 변경',
  order_state_change: '주문·장바구니 상태 변경', selection_state_change: '옵션·수량 선택 변경', voice_state_change: '음성 모드 상태 변경',
  session_suspend: '세션 일시 중단', session_end: '세션 종료',
};

const countLabels: [keyof RawTouchCounts, string][] = [
  ['presses', '누름 시작'], ['activeTargetPresses', '활성 대상 안 누름'],
  ['disabledTargetPresses', '비활성 대상 안 누름'], ['outsideTargetPresses', '대상 밖 누름'],
  ['releases', '손 뗌 기록'], ['cancellations', '취소 기록'], ['interruptions', '중단 기록'], ['scrolls', '스크롤 관측'],
  ['screenEntries', '화면 진입'], ['categoryChanges', '분류 변경'],
  ['optionsOpened', '옵션 열기'], ['optionsClosed', '옵션 닫기'], ['settingsChanges', 'UI 설정 변경'],
];
const screenLabels: Record<string, string> = { menu: '메뉴', review: '주문 확인', complete: '주문 완료' };

// 주문 UI가 아닌 개발 확인 도구. 프로덕션 빌드에서는 표시하지 않습니다.
export function TouchLogPanel() {
  return import.meta.env.DEV ? <DraftPanel /> : null;
}

function DraftPanel() {
  const [open, setOpen] = useState(false);
  const [paused, setPaused] = useState(false);
  const [snapshot, setSnapshot] = useState<SavedLog | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sampledAt, setSampledAt] = useState(Date.now);
  const [policy, setPolicy] = useState<TouchPilotPolicy>(() => ({ ...touchPilotPolicy }));
  useEffect(() => {
    if (!open || paused) return;
    function refresh() {
      const inspector = window.kioskTouchLogDraft;
      if (!inspector) {
        setWarning('수집기 연결을 기다리는 중입니다.');
        return;
      }
      const next = inspector.read();
      setSampledAt(Date.now());
      setSnapshot(previous => previous?.sessionId === next.sessionId
        && previous.events.at(-1)?.id === next.events.at(-1)?.id ? previous : next);
      setWarning(inspector.status());
    }
    refresh();
    const timer = window.setInterval(refresh, 500);
    return () => window.clearInterval(timer);
  }, [open, paused]);

  const recent = snapshot?.events.slice(-20).reverse() ?? [];
  const selected = recent.find(event => event.id === selectedId) ?? recent[0];
  const summary = useMemo(() => snapshot ? summarizeTouchLog(snapshot) : null, [snapshot]);
  const pilot = useMemo(() => snapshot ? measureTouchPilot(snapshot, sampledAt, 2000, policy) : null, [snapshot, sampledAt, policy]);
  return <aside className="touch-log-tools" aria-label="개발용 터치 로그 확인">
    {open && <section id="touch-log-panel" className="touch-log-panel" aria-labelledby="touch-log-title">
      <header className="touch-log-heading">
        <div><span>개발 확인용 · 로컬 초안</span><h2 id="touch-log-title">터치 로그</h2></div>
        <button type="button" aria-label="터치 로그 창 닫기" onClick={() => setOpen(false)}>닫기</button>
      </header>
      <div className="touch-log-toolbar">
        <button type="button" aria-pressed={paused} onClick={() => setPaused(!paused)}>{paused ? '표시 재개' : '표시 일시정지'}</button>
        <button type="button" disabled={!snapshot} onClick={() => window.kioskTouchLogDraft?.exportJson()}>JSON 내보내기</button>
      </div>
      <p className="touch-log-hint">{paused ? '표시만 멈췄습니다. 로그 수집은 계속됩니다.' : '0.5초마다 갱신 · 확인 창 입력은 수집 제외'}</p>
      {warning && <p className="touch-log-warning" role="status">{warning}</p>}
      <div className="touch-log-summary">
        <span>보관 <strong>{snapshot?.events.length ?? 0}</strong> / {logLimit.toLocaleString('ko-KR')}</span>
        <span>보관 중인 현재 세션 누름 <strong>{summary?.counts.presses ?? 0}</strong></span>
      </div>
      <p className="touch-log-session">세션 <code>{snapshot?.sessionId ?? '연결 대기'}</code></p>
      {pilot && <section className="touch-log-pilot" aria-label="로컬 파일럿 집계">
        <h3>최근 2초 · 로컬 파일럿</h3>
        <details><summary>파일럿 기준 선택 · 팀 계약과 별개</summary>
          <p className="touch-log-hint">프론트 파일럿 시작값은 800ms·24 CSS px입니다. 빈 기준은 미산출로 유지합니다. 정상 수량 조절도 반복 후보에 포함되며 오류나 불편을 뜻하지 않습니다.</p>
          <button type="button" onClick={() => setPolicy(current => ({ ...current, repeatMs: 800, repeatPx: 24 }))}>추천 반복 기준 사용</button>
          <div className="touch-log-policy">
            <label>반복 시간(ms)<input aria-label="반복 시간(ms)" type="number" min="0" value={policy.repeatMs ?? ''} placeholder="800" onChange={event => setPolicy(current => ({ ...current, repeatMs: event.target.value === '' ? null : Number(event.target.value) }))} /></label>
            <label>반복 거리(CSS px)<input aria-label="반복 거리(CSS px)" type="number" min="0" value={policy.repeatPx ?? ''} placeholder="24" onChange={event => setPolicy(current => ({ ...current, repeatPx: event.target.value === '' ? null : Number(event.target.value) }))} /></label>
            <label>체류 시간 정의<select aria-label="체류 시간 정의" value={policy.dwellMode ?? ''} onChange={event => setPolicy(current => ({ ...current, dwellMode: event.target.value as TouchPilotPolicy['dwellMode'] || null }))}>
              <option value="">미정 · 미산출</option><option value="foreground_visit">현재 방문 전경 체류</option><option value="since_last_input">마지막 누름 이후 경과</option>
            </select></label>
          </div>
        </details>
        <dl className="touch-log-counts">{Object.entries(pilot.features).map(([key, value]) => <div key={key}><dt>{key}</dt><dd data-touch-feature={key}>{value ?? '미산출'}</dd></div>)}</dl>
        {pilot.reason && <p className="touch-log-warning">{pilot.reason}</p>}
        <p className="touch-log-hint">누름 시작·대상 밖 누름·주문 확인에서 메뉴로 이동을 셉니다. 서버에 전송하지 않습니다.</p>
        <p className="touch-log-hint">반복 기준: {pilot.policy.repeatMs === null ? '시간 미정' : `${pilot.policy.repeatMs}ms`} · {pilot.policy.repeatPx === null ? '거리 미정' : `${pilot.policy.repeatPx}px`}. 체류 정의: {pilot.policy.dwellMode ?? '미정'}. 미산출은 0이 아닙니다.</p>
        <button type="button" onClick={() => {
          const url = URL.createObjectURL(new Blob([JSON.stringify({ version: 'touch-pilot-v1', sessionId: snapshot?.sessionId, serverSessionId: snapshot?.serverSessionId, ...pilot }, null, 2)], { type: 'application/json' }));
          const link = document.createElement('a'); link.href = url; link.download = 'touch-features-pilot.json'; link.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}>파일럿 집계 내보내기</button>
      </section>}
      {summary && <section className="touch-log-raw-summary" aria-labelledby="touch-log-raw-title">
        <h3 id="touch-log-raw-title">현재 세션 원시 로그 요약</h3>
        <p className="touch-log-hint">보관 중인 현재 세션 기록 {summary.counts.events}개만 계산합니다. 최대 {logLimit.toLocaleString('ko-KR')}개 버퍼에서 지워진 기록은 포함하지 않습니다.</p>
        {!summary.hasSessionStart && <p className="touch-log-warning">현재 세션의 시작 기록이 없습니다. 세션 전체 수치로 해석하지 마세요.</p>}
        <dl className="touch-log-counts" aria-label="보관 중인 현재 세션 원시 기록 수">
          {countLabels.map(([key, label]) => <div key={key}><dt>{label}</dt><dd data-touch-count={key}>{summary.counts[key]}</dd></div>)}
        </dl>
        <p className="touch-log-hint" data-touch-outside-ratio>대상 밖 비율: {summary.outsidePressRatio === null
          ? `산출 안 함 · ${summary.counts.presses ? '대상 판정 정보 부족' : '누름 기록 없음'}`
          : `${(summary.outsidePressRatio * 100).toFixed(1)}% (${summary.counts.outsideTargetPresses} / 누름 시작 ${summary.counts.presses})`}</p>
        {(summary.counts.unknownTargetPresses > 0 || summary.counts.unknownEnds > 0) && <p className="touch-log-warning">
          대상 정보 없는 누름 {summary.counts.unknownTargetPresses}개 · 취소 여부 없는 종료 {summary.counts.unknownEnds}개. 다른 항목에 추측해 넣지 않습니다.
        </p>}
        <details className="touch-log-visits">
          <summary>화면 방문별 요약 · 보관 순서</summary>
          <div className="touch-log-table-scroll"><table>
            <caption>같은 화면의 재방문은 별도 행입니다. 방문 정보가 없으면 별도로 표시합니다.</caption>
            <thead><tr><th scope="col">화면</th><th scope="col">누름</th><th scope="col">대상 밖</th><th scope="col">손 뗌</th><th scope="col">취소</th><th scope="col">스크롤</th></tr></thead>
            <tbody>{summary.visits.map((visit, index) => <tr key={JSON.stringify([visit.visitId, visit.screen])}>
              <th scope="row">{index + 1}. {visit.screen ? screenLabels[visit.screen] ?? visit.screen : '화면 정보 없음'}{!visit.visitId && ' · 방문 정보 없음'}</th>
              <td>{visit.counts.presses}</td><td>{visit.counts.outsideTargetPresses}</td><td>{visit.counts.releases}</td><td>{visit.counts.cancellations}</td><td>{visit.counts.scrolls}</td>
            </tr>)}</tbody>
          </table></div>
        </details>
        <p className="touch-log-hint">대상은 수집 당시 버튼·링크입니다. 대상 밖 누름은 실패, 손 뗌은 조작 성공을 뜻하지 않습니다. 취소·스크롤도 각각의 기록 수입니다.</p>
        <p className="touch-log-hint">위 반복·체류 값은 로컬 파일럿입니다. 주변 입력·성공/실패 판정과 서버용 통계는 기준 합의 후 연결합니다.</p>
      </section>}
      <h3>최근 기록 20개 · 최신순</h3>
      <ol className="touch-log-events" aria-label="최근 터치 로그">
        {recent.map(event => <li key={event.id}><button type="button" aria-pressed={selected?.id === event.id} onClick={() => setSelectedId(event.id)}>
          <span>{labels[event.kind] ?? event.kind}<small>{event.screen}</small></span>
          <time dateTime={event.occurredAt}>{new Date(event.occurredAt).toLocaleTimeString('ko-KR', { hour12: false })}</time>
        </button></li>)}
      </ol>
      {!recent.length && <p>아직 기록이 없습니다.</p>}
      {selected && <details className="touch-log-detail">
        <summary>선택한 기록 상세 · {labels[selected.kind] ?? selected.kind}</summary>
        <pre>{JSON.stringify(selected, null, 2)}</pre>
      </details>}
    </section>}
    <button type="button" className="touch-log-launcher" aria-expanded={open} aria-controls="touch-log-panel" onClick={() => setOpen(!open)}>
      {open ? '로그 창 접기' : '터치 로그 보기'}
    </button>
  </aside>;
}
