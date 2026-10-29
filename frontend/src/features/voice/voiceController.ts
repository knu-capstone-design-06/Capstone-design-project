import { ApiError } from '../../shared/api/index.ts';
import { createSpeechCapture, findRecognition } from './speech.ts';
import type { RecognitionFactory, SpeechCapture, SpeechErrorCode, SpeechResult } from './speech.ts';
import type { VoiceApi, VoiceRequestStatus, VoiceStatus } from './voiceApi.ts';

export type VoicePhase = 'idle' | 'listening' | 'processing';
/** 음성 모드가 저절로 꺼진 이유. silence: 마이크가 무음으로 연달아 닫힘. */
export type VoiceAutoOffReason = 'silence';
/** session_expired: 주문을 마친 세션이라 backend가 새 음성 요청을 410으로 거절했습니다. */
export type VoiceInputError = SpeechErrorCode | 'no_session' | 'request_failed' | 'session_expired' | 'timeout';
export type VoiceSnapshot = {
  supported: boolean;
  /** 음성 모드. 켜져 있어도 마이크는 phase가 listening일 때만 열립니다. */
  enabled: boolean;
  /** stop/abort 후 실제 onend까지 유지합니다. 화면 읽기와 마이크의 중첩을 막습니다. */
  microphoneActive: boolean;
  phase: VoicePhase;
  partialText: string;
  /** 마지막으로 Chrome이 확정 인식한 문장. 모드를 끄거나 세션이 바뀌면 지웁니다. */
  lastTranscript: string;
  lastResult: VoiceRequestStatus | null;
  error: VoiceInputError | null;
  /** 쓰지 않아 저절로 꺼졌을 때 그 이유. 다시 켜거나 세션이 바뀌면 지웁니다. */
  autoOff: VoiceAutoOffReason | null;
};
export type VoiceControllerOptions = {
  api: VoiceApi;
  /** 개발 샘플의 인식 확인용. 세션 없이 동작하며 서버 요청·결과 콜백을 실행하지 않습니다. */
  recognitionOnly?: boolean;
  /** 기본값은 브라우저의 SpeechRecognition입니다. 없으면 음성 모드를 켤 수 없습니다. */
  recognition?: RecognitionFactory | null;
  /** 결과가 정해질 때마다 불립니다. 장바구니 반영·MCP 실행은 부르는 쪽이 합니다. */
  onResult?: (result: VoiceRequestStatus) => void;
  silenceMs?: number;
  /** 마이크가 무음으로 이 횟수만큼 연달아 닫히면 음성 모드를 끕니다. 0이면 끄지 않습니다. */
  autoOffSilences?: number;
  minConfidence?: number;
  pollIntervalMs?: number;
  pollTimeoutMs?: number;
  createKey?: () => string;
};

// 제안값입니다. docs/Voice-MCP-Implementation.md의 미정 항목을 참고합니다.
export const VOICE_SILENCE_MS = 8_000;
export const VOICE_MIN_CONFIDENCE = 0.3;
// 손님이 떠났거나 음성을 쓰지 않는 것으로 봅니다. 다음 손님이 켜진 음성 모드를 이어받지 않게 합니다.
export const VOICE_AUTO_OFF_SILENCES = 2;
// 계약(contract/voice.openapi.yaml)의 상태 조회 간격 1초 이상을 따릅니다.
const POLL_INTERVAL_MS = 1_000;
const POLL_TIMEOUT_MS = 15_000;
const SETTLED = new Set<VoiceStatus>(['completed', 'needs_confirmation', 'needs_clarification', 'ignored', 'failed']);
// 손님의 대답이 필요한 결과에서는 마이크를 다시 엽니다.
const ASKS_USER = new Set<VoiceStatus>(['needs_confirmation', 'needs_clarification']);

function isSessionExpired(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 410) return false;
  const body = error.body;
  return typeof body === 'object' && body !== null && 'code' in body && body.code === 'session_expired';
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    const timer = setTimeout(() => { signal.removeEventListener('abort', cancel); resolve(); }, ms);
    function cancel() { clearTimeout(timer); reject(signal.reason); }
    signal.addEventListener('abort', cancel, { once: true });
  });
}

/**
 * 음성 모드를 켜고 끄는 독립 기능입니다. 화면 버튼은 만들지 않습니다.
 * 켜면 바로 한 문장을 듣고, 서버 해석 결과가 질문이면 대답을 듣기 위해 다시 엽니다.
 */
export class VoiceController {
  private readonly api: VoiceApi;
  private readonly recognitionOnly: boolean;
  private readonly recognition: RecognitionFactory | null;
  private readonly onResult: (result: VoiceRequestStatus) => void;
  private readonly minConfidence: number;
  private readonly pollIntervalMs: number;
  private readonly pollTimeoutMs: number;
  private readonly createKey: () => string;
  private readonly silenceMs: number;
  private readonly autoOffSilences: number;
  // 마이크가 무음으로 연달아 닫힌 횟수. 말을 받거나 손님이 다시 듣기를 누르면 0으로 돌아갑니다.
  private silentEnds = 0;
  private state: VoiceSnapshot;
  private listeners = new Set<() => void>();
  private capture: SpeechCapture | null = null;
  // Chrome의 stop/abort 뒤 onend가 올 때까지 다음 인식 시작을 기다립니다.
  private pendingListen: boolean | null = null;
  // 끈 마이크. Chrome은 abort 뒤에도 onend 전까지 결과·오류를 보낼 수 있어 onend만 받습니다.
  private readonly cancelled = new WeakSet<SpeechCapture>();
  private processing: AbortController | null = null;
  private context = { sessionId: '', screenId: '' };
  // 확인·질문 결과 뒤 대답을 기다리는 중. 마이크가 닫혀도 다음 결과가 나올 때까지 유지합니다.
  private awaitingAnswer = false;
  // backend가 이 세션의 새 음성 요청을 410으로 거절함. 세션이 바뀔 때까지 다시 듣지 않습니다.
  private sessionExpired = false;

  constructor(options: VoiceControllerOptions) {
    this.api = options.api;
    this.recognitionOnly = options.recognitionOnly ?? false;
    this.recognition = options.recognition === undefined ? findRecognition() : options.recognition;
    this.onResult = options.onResult ?? (() => {});
    this.silenceMs = options.silenceMs ?? VOICE_SILENCE_MS;
    this.autoOffSilences = options.autoOffSilences ?? VOICE_AUTO_OFF_SILENCES;
    this.minConfidence = options.minConfidence ?? VOICE_MIN_CONFIDENCE;
    this.pollIntervalMs = options.pollIntervalMs ?? POLL_INTERVAL_MS;
    this.pollTimeoutMs = options.pollTimeoutMs ?? POLL_TIMEOUT_MS;
    this.createKey = options.createKey ?? (() => crypto.randomUUID());
    this.state = { supported: this.recognition !== null, enabled: false, microphoneActive: false, phase: 'idle', partialText: '', lastTranscript: '', lastResult: null, error: null, autoOff: null };
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private set(patch: Partial<VoiceSnapshot>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach(listener => listener());
  }

  /** 세션이 바뀌면 진행 중인 듣기·처리를 버립니다. screen_id는 다음 발화부터 적용됩니다. */
  setContext(context: { sessionId: string; screenId: string }) {
    if (context.sessionId !== this.context.sessionId) {
      this.halt();
      this.awaitingAnswer = false;
      this.sessionExpired = false;
      this.silentEnds = 0;
      this.set({ lastTranscript: '', lastResult: null, error: null, autoOff: null });
    }
    this.context = { ...context };
  }

  /** 판단 모델이나 손님이 음성 모드를 켜고 끕니다. 켜면 바로 듣기 시작합니다. */
  setEnabled(enabled: boolean): boolean {
    if (!enabled) {
      this.halt();
      this.awaitingAnswer = false;
      this.silentEnds = 0;
      this.set({ enabled: false, lastTranscript: '', lastResult: null, error: null, autoOff: null });
      return true;
    }
    if (!this.recognition) { this.set({ error: 'not_supported' }); return false; }
    if (!this.state.enabled) {
      this.silentEnds = 0;
      this.set({ enabled: true, lastTranscript: '', lastResult: null, error: null, autoOff: null });
    }
    return this.listen();
  }

  /** 모드가 켜져 있고 쉬는 중일 때 한 문장을 듣습니다(예: 부르는 쪽의 마이크 버튼). */
  listen(): boolean {
    this.silentEnds = 0;
    return this.open(this.awaitingAnswer);
  }

  /** answering: 확인·질문에 대한 대답이라 "네" 같은 짧은 말도 받습니다. */
  private open(answering: boolean): boolean {
    if (!this.state.enabled || !this.recognition) return false;
    if (this.state.phase === 'listening') return true;
    if (this.state.phase !== 'idle') return false;
    if (!this.recognitionOnly && !this.context.sessionId.trim()) { this.set({ error: 'no_session' }); return false; }
    if (this.sessionExpired) { this.set({ error: 'session_expired' }); return false; }
    if (this.capture) { this.pendingListen = answering; return true; }
    const live = () => this.capture === capture && !this.cancelled.has(capture);
    const capture = createSpeechCapture(this.recognition, {
      onPartial: text => { if (live()) this.set({ partialText: text }); },
      onFinal: result => { if (live()) this.accept(result, answering); },
      onError: code => { if (live()) this.set({ error: code }); },
      onEnd: reason => {
        if (this.capture !== capture) return;
        this.capture = null;
        this.set({ microphoneActive: false, ...(this.state.phase === 'listening' ? { phase: 'idle', partialText: '' } : {}) });
        const pending = this.pendingListen;
        this.pendingListen = null;
        if (pending !== null) { this.open(pending); return; }
        if (reason === 'silence' && !this.cancelled.has(capture)) {
          this.silentEnds += 1;
          if (this.autoOffSilences > 0 && this.silentEnds >= this.autoOffSilences) this.turnOffUnused('silence');
        }
      },
    }, { silenceMs: this.silenceMs });
    this.capture = capture;
    this.set({ phase: 'listening', microphoneActive: true, partialText: '', error: null });
    capture.start();
    return true;
  }

  /** 쓰지 않는 음성 모드를 끕니다. 손님이 끈 것과 같이 정리하고 이유만 남깁니다. */
  private turnOffUnused(reason: VoiceAutoOffReason) {
    this.halt();
    this.awaitingAnswer = false;
    this.silentEnds = 0;
    this.set({ enabled: false, lastTranscript: '', lastResult: null, error: null, autoOff: reason });
  }

  dispose() {
    this.halt();
    this.listeners.clear();
  }

  private halt() {
    this.pendingListen = null;
    this.processing?.abort();
    this.processing = null;
    if (this.state.phase !== 'idle' || this.state.partialText) this.set({ phase: 'idle', partialText: '' });
    if (this.capture) {
      this.cancelled.add(this.capture);
      this.capture.abort();
    }
  }

  /** 짧거나 신뢰도가 아주 낮은 인식은 주변 소리로 보고 보내지 않습니다. 대답을 기다릴 때는 한 글자도 받습니다. */
  private looksLikeNoise(result: SpeechResult, answering: boolean): boolean {
    const confidence = result.alternatives[0]?.confidence ?? null;
    const minLength = answering ? 1 : 2;
    return result.text.replace(/\s/g, '').length < minLength || (confidence !== null && confidence < this.minConfidence);
  }

  private accept(result: SpeechResult, answering: boolean) {
    if (this.recognitionOnly) {
      this.silentEnds = 0;
      // 인식 테스트에서는 짧은 말·낮은 신뢰도도 그대로 확인합니다. onend까지 마이크 종료를 기다립니다.
      this.set({ partialText: '', lastTranscript: result.text, lastResult: null, error: null });
      return;
    }
    if (this.looksLikeNoise(result, answering)) return;
    this.silentEnds = 0;
    const controller = new AbortController();
    this.processing = controller;
    this.set({ phase: 'processing', partialText: result.text, lastTranscript: result.text });
    const { sessionId, screenId } = this.context;
    void this.process(sessionId, { text: result.text, alternatives: result.alternatives, screen_id: screenId }, controller.signal);
  }

  private async process(sessionId: string, body: Parameters<VoiceApi['submit']>[1], signal: AbortSignal) {
    let outcome: VoiceRequestStatus | VoiceInputError;
    try {
      const accepted = await this.api.submit(sessionId, body, this.createKey(), signal);
      outcome = await this.poll(sessionId, accepted.request_id, signal);
    } catch (error) {
      outcome = isSessionExpired(error) ? 'session_expired' : 'request_failed';
    }
    if (signal.aborted || this.processing?.signal !== signal) return;
    this.processing = null;
    if (outcome === 'session_expired') {
      // 끝난 세션의 질문에는 더 대답할 수 없으므로 대기를 풀고, 새 주문은 부르는 쪽이 안내합니다.
      this.awaitingAnswer = false;
      this.sessionExpired = true;
      this.set({ phase: 'idle', partialText: '', lastResult: null, error: outcome });
      return;
    }
    if (typeof outcome === 'string') {
      this.set({ phase: 'idle', partialText: '', error: outcome });
      return;
    }
    if (outcome.status === 'ignored') {
      // 주변 대화는 이전 질문과 대답 대기를 덮어쓰지 않습니다. 재청취는 사용자가 시작합니다.
      this.set({ phase: 'idle', partialText: '', lastTranscript: '', lastResult: this.awaitingAnswer ? this.state.lastResult : null, error: null });
      this.onResult(outcome);
      return;
    }
    if (outcome.status === 'failed') {
      // 서버도 실패한 발화를 대화 맥락에 넣지 않으므로 이전 질문과 대답 대기를 유지합니다.
      this.set({ phase: 'idle', partialText: '', lastResult: this.awaitingAnswer ? this.state.lastResult : outcome, error: 'request_failed' });
      this.onResult(outcome);
      return;
    }
    // 구독자·onResult가 세션을 바꾸거나 모드를 끄면 그 초기화가 남도록, 알리기 전에 대기 상태를 정합니다.
    this.awaitingAnswer = ASKS_USER.has(outcome.status);
    this.set({ phase: 'idle', partialText: '', lastResult: outcome, error: null });
    this.onResult(outcome);
    if (this.awaitingAnswer && this.context.sessionId === sessionId) this.open(true);
  }

  private async poll(sessionId: string, requestId: string, signal: AbortSignal): Promise<VoiceRequestStatus | 'timeout'> {
    const deadline = Date.now() + this.pollTimeoutMs;
    for (;;) {
      const status = await this.api.get(sessionId, requestId, signal);
      if (SETTLED.has(status.status)) return status;
      if (Date.now() + this.pollIntervalMs > deadline) return 'timeout';
      await wait(this.pollIntervalMs, signal);
    }
  }
}
