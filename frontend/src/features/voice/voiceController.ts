import { createSpeechCapture, findRecognition } from './speech.ts';
import type { RecognitionFactory, SpeechCapture, SpeechErrorCode, SpeechResult } from './speech.ts';
import type { VoiceApi, VoiceRequestStatus, VoiceStatus } from './voiceApi.ts';

export type VoicePhase = 'idle' | 'listening' | 'processing';
export type VoiceInputError = SpeechErrorCode | 'no_session' | 'request_failed' | 'timeout';
export type VoiceSnapshot = {
  supported: boolean;
  /** 음성 모드. 켜져 있어도 마이크는 phase가 listening일 때만 열립니다. */
  enabled: boolean;
  phase: VoicePhase;
  partialText: string;
  lastResult: VoiceRequestStatus | null;
  error: VoiceInputError | null;
};
export type VoiceControllerOptions = {
  api: VoiceApi;
  /** 기본값은 브라우저의 SpeechRecognition입니다. 없으면 음성 모드를 켤 수 없습니다. */
  recognition?: RecognitionFactory | null;
  /** 결과가 정해질 때마다 불립니다. 장바구니 반영·MCP 실행은 부르는 쪽이 합니다. */
  onResult?: (result: VoiceRequestStatus) => void;
  silenceMs?: number;
  minConfidence?: number;
  pollIntervalMs?: number;
  pollTimeoutMs?: number;
  createKey?: () => string;
};

// 제안값입니다. docs/Voice-MCP-Implementation.md의 미정 항목을 참고합니다.
export const VOICE_SILENCE_MS = 8_000;
export const VOICE_MIN_CONFIDENCE = 0.3;
// 계약(contract/voice.openapi.yaml)의 상태 조회 간격 1초 이상을 따릅니다.
const POLL_INTERVAL_MS = 1_000;
const POLL_TIMEOUT_MS = 15_000;
const SETTLED = new Set<VoiceStatus>(['completed', 'needs_confirmation', 'needs_clarification', 'ignored', 'failed']);
// 손님의 대답이 필요한 결과에서는 마이크를 다시 엽니다.
const ASKS_USER = new Set<VoiceStatus>(['needs_confirmation', 'needs_clarification']);

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
  private readonly recognition: RecognitionFactory | null;
  private readonly onResult: (result: VoiceRequestStatus) => void;
  private readonly minConfidence: number;
  private readonly pollIntervalMs: number;
  private readonly pollTimeoutMs: number;
  private readonly createKey: () => string;
  private readonly silenceMs: number;
  private state: VoiceSnapshot;
  private listeners = new Set<() => void>();
  private capture: SpeechCapture | null = null;
  private processing: AbortController | null = null;
  private context = { sessionId: '', screenId: '' };
  // 확인·질문 결과 뒤 대답을 기다리는 중. 마이크가 닫혀도 다음 결과가 나올 때까지 유지합니다.
  private awaitingAnswer = false;

  constructor(options: VoiceControllerOptions) {
    this.api = options.api;
    this.recognition = options.recognition === undefined ? findRecognition() : options.recognition;
    this.onResult = options.onResult ?? (() => {});
    this.silenceMs = options.silenceMs ?? VOICE_SILENCE_MS;
    this.minConfidence = options.minConfidence ?? VOICE_MIN_CONFIDENCE;
    this.pollIntervalMs = options.pollIntervalMs ?? POLL_INTERVAL_MS;
    this.pollTimeoutMs = options.pollTimeoutMs ?? POLL_TIMEOUT_MS;
    this.createKey = options.createKey ?? (() => crypto.randomUUID());
    this.state = { supported: this.recognition !== null, enabled: false, phase: 'idle', partialText: '', lastResult: null, error: null };
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private set(patch: Partial<VoiceSnapshot>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach(listener => listener());
  }

  /** 세션이 바뀌면 진행 중인 듣기·처리를 버립니다. screen_id는 다음 발화부터 적용됩니다. */
  setContext(context: { sessionId: string; screenId: string }) {
    if (context.sessionId !== this.context.sessionId) { this.halt(); this.awaitingAnswer = false; }
    this.context = { ...context };
  }

  /** 판단 모델이나 손님이 음성 모드를 켜고 끕니다. 켜면 바로 듣기 시작합니다. */
  setEnabled(enabled: boolean): boolean {
    if (!enabled) {
      this.halt();
      this.awaitingAnswer = false;
      this.set({ enabled: false });
      return true;
    }
    if (!this.recognition) { this.set({ error: 'not_supported' }); return false; }
    if (!this.state.enabled) this.set({ enabled: true, error: null });
    return this.listen();
  }

  /** 모드가 켜져 있고 쉬는 중일 때 한 문장을 듣습니다(예: 부르는 쪽의 마이크 버튼). */
  listen(): boolean {
    return this.open(this.awaitingAnswer);
  }

  /** answering: 확인·질문에 대한 대답이라 "네" 같은 짧은 말도 받습니다. */
  private open(answering: boolean): boolean {
    if (!this.state.enabled || !this.recognition) return false;
    if (this.state.phase === 'listening') return true;
    if (this.state.phase !== 'idle') return false;
    if (!this.context.sessionId.trim()) { this.set({ error: 'no_session' }); return false; }
    const capture = createSpeechCapture(this.recognition, {
      onPartial: text => { if (this.capture === capture) this.set({ partialText: text }); },
      onFinal: result => { if (this.capture === capture) this.accept(result, answering); },
      onError: code => { if (this.capture === capture) this.set({ error: code }); },
      onEnd: () => {
        if (this.capture !== capture) return;
        this.capture = null;
        if (this.state.phase === 'listening') this.set({ phase: 'idle', partialText: '' });
      },
    }, { silenceMs: this.silenceMs });
    this.capture = capture;
    this.set({ phase: 'listening', partialText: '', error: null });
    capture.start();
    return true;
  }

  dispose() {
    this.halt();
    this.listeners.clear();
  }

  private halt() {
    const capture = this.capture;
    this.capture = null;
    capture?.abort();
    this.processing?.abort();
    this.processing = null;
    if (this.state.phase !== 'idle' || this.state.partialText) this.set({ phase: 'idle', partialText: '' });
  }

  /** 짧거나 신뢰도가 아주 낮은 인식은 주변 소리로 보고 보내지 않습니다. 대답을 기다릴 때는 한 글자도 받습니다. */
  private looksLikeNoise(result: SpeechResult, answering: boolean): boolean {
    const confidence = result.alternatives[0]?.confidence ?? null;
    const minLength = answering ? 1 : 2;
    return result.text.replace(/\s/g, '').length < minLength || (confidence !== null && confidence < this.minConfidence);
  }

  private accept(result: SpeechResult, answering: boolean) {
    if (this.looksLikeNoise(result, answering)) return;
    const controller = new AbortController();
    this.processing = controller;
    this.set({ phase: 'processing', partialText: result.text });
    const { sessionId, screenId } = this.context;
    void this.process(sessionId, { text: result.text, alternatives: result.alternatives, screen_id: screenId }, controller.signal);
  }

  private async process(sessionId: string, body: Parameters<VoiceApi['submit']>[1], signal: AbortSignal) {
    let outcome: VoiceRequestStatus | VoiceInputError;
    try {
      const accepted = await this.api.submit(sessionId, body, this.createKey(), signal);
      outcome = await this.poll(sessionId, accepted.request_id, signal);
    } catch {
      outcome = 'request_failed';
    }
    if (signal.aborted || this.processing?.signal !== signal) return;
    this.processing = null;
    if (typeof outcome === 'string') {
      this.set({ phase: 'idle', partialText: '', error: outcome });
      return;
    }
    this.set({ phase: 'idle', partialText: '', lastResult: outcome, error: null });
    this.onResult(outcome);
    this.awaitingAnswer = ASKS_USER.has(outcome.status);
    if (this.awaitingAnswer) this.open(true);
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
