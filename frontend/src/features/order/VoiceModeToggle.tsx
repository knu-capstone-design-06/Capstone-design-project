import { useId, useState } from 'react';
import './voiceModeToggle.css';

/** 화면 미리보기용 모드 버튼입니다. 마이크·음성 API는 호출하지 않습니다. */
export function VoiceModeToggle() {
  const [enabled, setEnabled] = useState(false);
  const previewId = useId();

  return <section className="voice-mode-control" data-enabled={enabled} aria-label="음성 모드 설정">
    <button type="button" className="voice-mode-toggle" role="switch" aria-checked={enabled}
      aria-label="음성 모드 미리보기" aria-describedby={previewId} data-log-target="voice-mode-toggle"
      onClick={() => setEnabled(current => !current)}>
      <span className="voice-mode-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="2" width="6" height="12" rx="3" />
          <path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" />
          {!enabled && <path className="voice-mode-mute" d="M3 3l18 18" />}
        </svg>
      </span>
      <span className="voice-mode-copy"><strong>음성 모드</strong>
        <span className="voice-mode-status" aria-hidden="true">
          <span className="voice-mode-dot" aria-hidden="true" />{enabled ? '켜짐 · 다시 누르면 꺼져요' : '꺼짐 · 누르면 켜져요'}
        </span>
      </span>
      <span className="voice-mode-switch" aria-hidden="true"><span>{enabled ? 'ON' : 'OFF'}</span><span className="voice-mode-knob" /></span>
    </button>
    <p className="voice-mode-preview" id={previewId}>버튼 미리보기예요. 마이크는 켜지지 않아요.</p>
  </section>;
}
