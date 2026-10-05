/// <reference types="vite/client" />
import { useEffect, useState } from 'react';
import type { SavedLog } from './touchLog.ts';
import { logLimit } from './touchLog.ts';
import './touchLogPanel.css';

const labels: Record<string, string> = {
  pointer_start: '누름 시작', pointer_end: '누름 종료·취소', pointer_interrupted: '입력 중단',
  scroll: '스크롤 관측', screen_enter: '화면 진입', screen_leave: '화면 이탈',
  category_change: '분류 변경', options_open: '옵션 열기', options_close: '옵션 닫기',
  ui_settings_change: 'UI 설정 변경', session_start: '세션 시작', session_resume: '세션 재개',
  session_suspend: '세션 일시 중단', session_end: '세션 종료',
};

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
  useEffect(() => {
    if (!open || paused) return;
    function refresh() {
      const inspector = window.kioskTouchLogDraft;
      if (!inspector) {
        setWarning('수집기 연결을 기다리는 중입니다.');
        return;
      }
      const next = inspector.read();
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
  const currentEvents = snapshot?.events.filter(event => event.sessionId === snapshot.sessionId) ?? [];
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
        <span>보관 중인 현재 세션 누름 <strong>{currentEvents.filter(event => event.kind === 'pointer_start').length}</strong></span>
      </div>
      <p className="touch-log-session">세션 <code>{snapshot?.sessionId ?? '연결 대기'}</code></p>
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
