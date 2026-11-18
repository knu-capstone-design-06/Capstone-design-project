import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { supportSettings } from '../backendSupport.ts';
import type { SupportPreset } from '../backendSupport.ts';
import { doubleClickMs } from '../utils/timing.ts';
import { Sheet } from './Sheet.tsx';
import './supportConfirm.css';

/** 서버 제안은 사용자가 답하기 전에는 적용하지 않습니다. Escape·배경 누름은 이번 창만 닫습니다. */
export function SupportConfirmSheet({ preset, onAccept, onDecline, onDismiss }: {
  preset: SupportPreset; onAccept: () => void; onDecline: () => void; onDismiss: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [armed, setArmed] = useState(false);
  useLayoutEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); };
  }, []);
  useEffect(() => { const timer = setTimeout(() => setArmed(true), doubleClickMs); return () => clearTimeout(timer); }, []);
  const copy = supportSettings[preset];
  return <Sheet ref={dialog} className="support-confirm-sheet" labelledBy="support-confirm-title" logTarget="support-confirm" onClose={onDismiss}>
    <h2 id="support-confirm-title" className="sheet-name">{copy.question}</h2>
    <p className="sheet-desc">{copy.description}</p>
    <div className="support-confirm-actions" data-armed={armed}>
      <button type="button" autoFocus data-log-target="support-confirm:decline" onClick={() => { if (armed) onDecline(); }}>지금 화면 유지</button>
      <button type="button" data-log-target="support-confirm:accept" className="sheet-main" onClick={() => { if (armed) onAccept(); }}>적용하기</button>
    </div>
  </Sheet>;
}
