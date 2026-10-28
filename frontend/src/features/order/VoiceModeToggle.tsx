import { useId } from 'react';
import { useVoiceInput } from '../voice/index.ts';
import type { VoiceController, VoiceInputError, VoiceRequestStatus } from '../voice/index.ts';
import './voiceModeToggle.css';

const errorCopy: Record<VoiceInputError, string> = {
  not_supported: '이 브라우저에서는 음성 입력을 사용할 수 없어요. 화면을 눌러 주문해 주세요.',
  not_allowed: '마이크를 사용할 수 없어요. Chrome의 마이크 권한을 확인해 주세요.',
  network: '음성 인식 연결에 문제가 생겼어요. 다시 말하거나 화면을 눌러 주문해 주세요.',
  failed: '음성을 듣지 못했어요. 다시 말하거나 화면을 눌러 주문해 주세요.',
  no_session: '주문 준비가 끝나면 음성 입력을 사용할 수 있어요.',
  request_failed: '음성 요청을 처리하지 못했어요. 다시 말하거나 화면을 눌러 주문해 주세요.',
  timeout: '음성 응답이 늦어지고 있어요. 화면을 눌러 주문해 주세요.',
};

function resultCopy(result: VoiceRequestStatus): string {
  switch (result.status) {
    case 'completed': return '말씀을 확인했어요. 음성으로 주문을 변경하는 기능은 아직 준비 중이에요.';
    case 'needs_confirmation': return result.reply_text || '말씀하신 내용을 확인해 주세요.';
    case 'needs_clarification': return result.reply_text || '원하는 메뉴와 옵션을 다시 말씀해 주세요.';
    case 'ignored': return '';
    case 'failed': return '음성을 처리하지 못했어요. 다시 말하거나 화면을 눌러 주문해 주세요.';
    default: return '';
  }
}

export function VoiceModeToggle({ controller, ready, sampleMode }: {
  controller: VoiceController;
  ready: boolean;
  sampleMode: boolean;
}) {
  const voice = useVoiceInput(controller);
  const hintId = useId();
  const canUse = ready && voice.supported && !sampleMode;
  const result = voice.enabled && voice.lastResult;
  const question = result && (result.status === 'needs_confirmation' || result.status === 'needs_clarification');
  const detail = voice.error ? errorCopy[voice.error]
    : voice.phase === 'processing' ? '음성을 확인하고 있어요.'
    : question ? `${resultCopy(result)}${voice.phase === 'listening' ? (voice.partialText ? ` 듣는 중: ${voice.partialText}` : ' 답변을 듣고 있어요.') : ''}`
    : voice.phase === 'listening' ? (voice.partialText ? `듣는 중: ${voice.partialText}` : '듣고 있어요. 말씀해 주세요.')
    : result ? resultCopy(result) : '';

  return <section className="voice-mode-control" data-enabled={voice.enabled} aria-label="음성 모드 설정">
    <button type="button" className="voice-mode-toggle" role="switch" aria-checked={voice.enabled}
      aria-label="음성 모드" aria-describedby={hintId} data-log-target="voice-mode-toggle"
      disabled={!canUse} onClick={() => controller.setEnabled(!voice.enabled)}>
      <span className="voice-mode-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="2" width="6" height="12" rx="3" />
          <path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" />
          {!voice.enabled && <path className="voice-mode-mute" d="M3 3l18 18" />}
        </svg>
      </span>
      <span className="voice-mode-copy"><strong>음성 모드</strong>
        <span className="voice-mode-status" aria-hidden="true">
          <span className="voice-mode-dot" aria-hidden="true" />{voice.enabled ? '켜짐 · 다시 누르면 꺼져요' : '꺼짐 · 누르면 켜져요'}
        </span>
      </span>
      <span className="voice-mode-switch" aria-hidden="true"><span>{voice.enabled ? 'ON' : 'OFF'}</span><span className="voice-mode-knob" /></span>
    </button>
    <p className="voice-mode-preview" id={hintId}>{sampleMode ? '개발용 샘플에서는 음성 요청을 사용할 수 없어요.'
      : !voice.supported ? '이 브라우저에서는 음성 입력을 사용할 수 없어요. 화면을 눌러 주문해 주세요.'
      : !ready ? '주문 준비가 끝나면 음성 모드를 켤 수 있어요.'
      : '켜면 마이크로 한 문장을 듣고 닫아요. Chrome에서 마이크 권한을 허용해 주세요.'}</p>
    {voice.enabled && voice.lastTranscript && <p className="voice-mode-transcript"><span>Chrome이 인식한 말</span><strong>{voice.lastTranscript}</strong></p>}
    {voice.enabled && detail && <p className="voice-mode-feedback" role="status" aria-live="polite">{detail}</p>}
    {voice.enabled && voice.phase === 'idle' && <button type="button" className="voice-mode-listen" data-log-target="voice-listen" onClick={() => controller.listen()}>다시 말하기</button>}
  </section>;
}
