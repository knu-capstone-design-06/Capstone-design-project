import { useLayoutEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { useVoiceInput } from '../voice/index.ts';
import type { VoiceController, VoiceInputError, VoiceRequestStatus } from '../voice/index.ts';
import { Icon } from './components/icons.tsx';
import './voiceModeToggle.css';

const errorCopy: Record<VoiceInputError, string> = {
  not_supported: '이 브라우저에서는 음성 입력을 사용할 수 없어요. 화면을 눌러 주문해 주세요.',
  not_allowed: '마이크를 사용할 수 없어요. 마이크 사용을 허용하거나 화면을 눌러 주문해 주세요.',
  network: '음성 인식 연결에 문제가 생겼어요. 다시 말하거나 화면을 눌러 주문해 주세요.',
  failed: '음성을 듣지 못했어요. 다시 말하거나 화면을 눌러 주문해 주세요.',
  no_session: '주문 준비가 끝나면 음성 입력을 사용할 수 있어요.',
  request_failed: '음성 요청을 처리하지 못했어요. 다시 말하거나 화면을 눌러 주문해 주세요.',
  session_expired: '이미 주문을 마쳤어요. 새로 주문하려면 처음부터 다시 주문해 주세요.',
  timeout: '음성 응답이 늦어지고 있어요. 화면을 눌러 주문해 주세요.',
};

function resultCopy(result: VoiceRequestStatus): string {
  switch (result.status) {
    case 'completed': return result.reply_text?.trim() || (result.actions.includes('cart_updated')
      ? '음성 주문 결과를 장바구니에 반영하고 있어요.' : '말씀을 확인했어요.');
    case 'needs_confirmation': return result.reply_text || '말씀하신 내용을 확인해 주세요.';
    case 'needs_clarification': return result.reply_text || '원하는 메뉴와 옵션을 다시 말씀해 주세요.';
    case 'ignored': return '';
    case 'failed': return result.reply_text?.trim() || '음성을 처리하지 못했어요. 다시 말하거나 화면을 눌러 주문해 주세요.';
    default: return '';
  }
}

/** 화면에 한 번만 쓰는 말로 주문 버튼의 설명 문장 id(aria-describedby). */
const previewId = 'voice-mode-preview';
/** 자동으로 꺼졌을 때 안내 영역에 보이는 문장입니다. */
export const voiceAutoOffNotice = '한동안 말씀이 없어 말로 주문을 껐어요. 다시 쓰려면 위의 마이크 버튼을 눌러 주세요.';

function useVoiceView(controller: VoiceController, sampleMode: boolean, ready = true) {
  const voice = useVoiceInput(controller);
  const recognitionTest = import.meta.env.DEV && sampleMode;
  const canUse = ready && voice.supported && (!sampleMode || recognitionTest);
  const result = voice.enabled && voice.lastResult;
  const question = result && (result.status === 'needs_confirmation' || result.status === 'needs_clarification');
  const spokenReply = voice.phase === 'speaking' ? voice.lastReplyText : null;
  const failure = spokenReply && question && spokenReply !== result.reply_text?.trim() ? spokenReply
    : voice.error === 'request_failed' ? voice.failureReplyText || errorCopy.request_failed
    : voice.error ? errorCopy[voice.error] : '';
  const detail = spokenReply && !question ? spokenReply
    : failure && !question ? failure
    : failure && question ? resultCopy(result)
    : voice.phase === 'processing' ? '음성을 확인하고 있어요.'
    : voice.phase === 'speaking' ? `${voice.lastReplyText || (result ? resultCopy(result) : '')} 안내를 읽고 있어요.`
    : question ? `${resultCopy(result)}${voice.phase === 'listening' ? (voice.partialText ? ` 듣는 중: ${voice.partialText}` : ' 답변을 듣고 있어요.') : ''}`
    : voice.phase === 'listening' ? (voice.partialText ? `듣는 중: ${voice.partialText}` : '듣고 있어요. 말씀해 주세요.')
    : result ? resultCopy(result) : '';
  return { voice, recognitionTest, canUse, detail, question, failure };
}

/**
 * 말로 주문 버튼: 탭 줄 오른쪽 끝의 둥근 마이크 버튼입니다(글자 없음, 지름 = 그 모드의 조작 높이, 채움 #163F35, 흰 마이크).
 * 켜지면 고른 모습에 멈춘 고리가 둘레에 서고, 상태 문장은 말로 주문 영역에 보입니다. 설명 문장은 낭독기용으로만 둡니다.
 * 이 브라우저가 음성 인식을 지원하지 않으면 버튼을 두지 않고(이유 문장은 낭독기에 남김), 주문 준비 전에는 누를 수 없는 모습입니다.
 */
export function VoiceButton({ controller, ready, sampleMode }: { controller: VoiceController; ready: boolean; sampleMode: boolean }) {
  const { voice, canUse } = useVoiceView(controller, sampleMode, ready);
  return <div className={`voice-entry${voice.enabled ? ' is-on' : ''}${canUse ? ' is-ready' : ''}`}>
    {voice.supported && <>
      <span className="mic-ring" aria-hidden="true" /><span className="mic-ring" aria-hidden="true" />
      <button type="button" className={`voice-mic${voice.enabled ? ' is-on' : ''}`} role="switch" aria-checked={voice.enabled}
        aria-label="말로 주문하기" aria-describedby={previewId} data-log-target="voice-mode-toggle"
        disabled={!canUse} onClick={() => controller.setEnabled(!voice.enabled)}><Icon name="mic" /></button>
    </>}
    <p className="voice-mode-preview sr-only" id={previewId} hidden={!voice.enabled && canUse}>{!voice.supported ? '이 브라우저에서는 음성 입력을 사용할 수 없어요. 음성 인식을 지원하는 Chrome에서 열어 주세요.'
      : !ready ? '주문 준비가 끝나면 말로 주문을 켤 수 있어요.'
      : '켜면 한 문장을 듣고 마이크를 닫아요. 마이크 사용을 허용해 주세요.'}</p>
  </div>;
}

/**
 * 말로 주문 영역: 켜져 있는 동안 하단 주문 바 바로 위에 보조색으로 섭니다. 상태 줄, 들은 말(오른쪽의 흰 말풍선, M,
 * 한 줄, 긴 문장은 끝부분), 질문·결과 문장(왼쪽, M 굵게), [다시 말하기]. 주문 안내는 다른 모드처럼 상품 목록 위의 자리에 뜹니다.
 */
export function VoicePanel({ controller, sampleMode, messages = null }: { controller: VoiceController; sampleMode: boolean; messages?: ReactNode }) {
  const { voice, detail, question, failure } = useVoiceView(controller, sampleMode);
  const stopButton = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    if (voice.phase === 'speaking') stopButton.current?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  }, [voice.phase]);
  if (!voice.enabled) return null;
  const state = voice.phase === 'listening' ? '듣고 있어요' : voice.phase === 'processing' ? '알아듣는 중이에요'
    : voice.phase === 'speaking' ? '안내를 읽고 있어요' : '마이크 꺼짐';
  return <section className="voice-mode-control" data-enabled={voice.enabled} aria-label="말로 주문">
    <p className="voice-state"><Icon name={voice.phase === 'idle' ? 'mic_off' : 'mic'} />{state}</p>
    <div className="voice-text">
      {voice.lastTranscript && <p className="voice-mode-transcript"><span className="sr-only">인식한 말 </span><strong dir="rtl"><span dir="ltr">{voice.lastTranscript}</span></strong></p>}
      {messages}
      {detail && <p className="voice-mode-feedback" role="status" aria-live="polite">{detail}</p>}
      {question && failure && <p className="voice-mode-failure" role="status" aria-live="polite">{failure}</p>}
      {voice.replyAudioError && <p className="voice-mode-failure" role="status">음성 안내를 재생하지 못했어요. 화면을 확인하고 ‘다시 말하기’를 눌러 주세요.</p>}
    </div>
    <div className="voice-answers">
      {voice.phase === 'idle' && voice.error !== 'session_expired' && <button type="button" className="voice-mode-listen" data-log-target="voice-listen" onClick={() => controller.listen()}>다시 말하기</button>}
      {voice.phase === 'speaking' && <button ref={stopButton} type="button" className="voice-mode-listen" data-log-target="voice-reply-stop" onClick={() => controller.stopReply()}>안내 중단</button>}
      {voice.lastReplyText && (voice.phase === 'idle' || voice.phase === 'listening') && <button type="button" className="voice-mode-listen" data-log-target="voice-reply-replay" onClick={() => controller.replayReply()}>마지막 안내 다시 듣기</button>}
    </div>
  </section>;
}
