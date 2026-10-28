// Chrome Web Speech API(SpeechRecognition)를 한 문장 단위로 짧게 여닫습니다.
// TypeScript DOM 타입에 SpeechRecognition이 없어 필요한 부분만 직접 정의합니다.

export type RecognitionAlternative = { text: string; confidence: number | null };
export type SpeechResult = { text: string; alternatives: RecognitionAlternative[] };
export type SpeechErrorCode = 'not_supported' | 'not_allowed' | 'network' | 'failed';
export type SpeechEndReason = 'final' | 'silence' | 'stopped' | 'error';

type RecognitionResult = ArrayLike<{ transcript: string; confidence: number }> & { isFinal: boolean };
export type RecognitionResultEvent = { resultIndex: number; results: ArrayLike<RecognitionResult> };
export type RecognitionErrorEvent = { error: string };
export interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
export type RecognitionFactory = () => RecognitionLike;

type RecognitionScope = { SpeechRecognition?: new () => RecognitionLike; webkitSpeechRecognition?: new () => RecognitionLike };

/** Chrome은 아직 webkit 접두어 이름으로 제공합니다. 없으면 null입니다. */
export function findRecognition(scope: object = globalThis): RecognitionFactory | null {
  const { SpeechRecognition, webkitSpeechRecognition } = scope as RecognitionScope;
  const Recognition = SpeechRecognition ?? webkitSpeechRecognition;
  return Recognition ? () => new Recognition() : null;
}

export function isSpeechSupported(scope: object = globalThis): boolean {
  return findRecognition(scope) !== null;
}

export type SpeechCaptureOptions = { lang?: string; maxAlternatives?: number; silenceMs?: number };
export type SpeechCaptureHandlers = {
  onPartial?: (text: string) => void;
  onFinal: (result: SpeechResult) => void;
  onError?: (code: SpeechErrorCode) => void;
  onEnd?: (reason: SpeechEndReason) => void;
};
export type SpeechCapture = { start(): void; stop(): void; abort(): void; readonly active: boolean };

function errorCode(error: string): SpeechErrorCode | null {
  if (error === 'no-speech' || error === 'aborted') return null;
  if (error === 'not-allowed' || error === 'service-not-allowed' || error === 'audio-capture') return 'not_allowed';
  return error === 'network' ? 'network' : 'failed';
}

/**
 * 한 번 start()하면 최종 문장 하나를 받거나 silenceMs 동안 말이 없으면 닫힙니다.
 * 계속 듣지 않으므로 주변 대화가 덜 섞이고, 음성이 외부로 전송되는 시간도 줄어듭니다.
 */
export function createSpeechCapture(
  factory: RecognitionFactory, handlers: SpeechCaptureHandlers, options: SpeechCaptureOptions = {},
): SpeechCapture {
  const { lang = 'ko-KR', maxAlternatives = 5, silenceMs = 8_000 } = options;
  let recognition: RecognitionLike | null = null;
  let acceptingResults = false;
  let reason: SpeechEndReason = 'stopped';
  let timer: ReturnType<typeof setTimeout> | null = null;

  function clearTimer() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }
  function armTimer() {
    clearTimer();
    timer = setTimeout(() => { reason = 'silence'; acceptingResults = false; recognition?.abort(); }, silenceMs);
  }

  return {
    get active() { return recognition !== null; },
    start() {
      if (recognition) return;
      const current = factory();
      recognition = current;
      acceptingResults = true;
      reason = 'stopped';
      Object.assign(current, { lang, maxAlternatives, continuous: false, interimResults: true });
      current.onresult = event => {
        if (recognition !== current || !acceptingResults) return;
        armTimer();
        let partial = '';
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          if (!result.isFinal) { partial += result[0]?.transcript ?? ''; continue; }
          const alternatives = Array.from(result, item => ({
            text: item.transcript.trim(),
            // Chrome은 신뢰도를 모를 때 0을 줍니다. 0은 "모름"으로 보냅니다.
            confidence: item.confidence > 0 ? Math.min(item.confidence, 1) : null,
          })).filter(item => item.text);
          if (!alternatives.length) continue;
          reason = 'final';
          acceptingResults = false;
          clearTimer();
          handlers.onFinal({ text: alternatives[0].text, alternatives });
          current.stop();
          return;
        }
        if (partial.trim()) handlers.onPartial?.(partial.trim());
      };
      current.onerror = event => {
        if (recognition !== current) return;
        const code = errorCode(event.error);
        if (code === null) { if (event.error === 'no-speech') reason = 'silence'; return; }
        reason = 'error';
        handlers.onError?.(code);
      };
      current.onend = () => {
        if (recognition !== current) return;
        clearTimer();
        recognition = null;
        handlers.onEnd?.(reason);
      };
      try {
        current.start();
        armTimer();
      } catch {
        recognition = null;
        handlers.onError?.('failed');
        handlers.onEnd?.('error');
      }
    },
    stop() { if (recognition) { reason = reason === 'final' ? 'final' : 'stopped'; recognition.stop(); } },
    abort() {
      const current = recognition;
      if (!current) return;
      clearTimer();
      acceptingResults = false;
      reason = 'stopped';
      current.abort();
    },
  };
}
