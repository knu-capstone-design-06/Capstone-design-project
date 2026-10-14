// 음성 테스트용 가짜 SpeechRecognition입니다. 브라우저 없이 결과·오류·종료 이벤트를 만듭니다.
export class FakeRecognition {
  static instances = [];
  constructor() {
    this.started = 0; this.stopped = 0; this.aborted = 0;
    this.onresult = null; this.onerror = null; this.onend = null;
    FakeRecognition.instances.push(this);
  }
  start() { this.started += 1; }
  stop() { this.stopped += 1; this.onend?.(); }
  abort() { this.aborted += 1; this.onerror?.({ error: 'aborted' }); this.onend?.(); }
  partial(text) { this.onresult?.({ resultIndex: 0, results: [Object.assign([{ transcript: text, confidence: 0 }], { isFinal: false })] }); }
  final(...alternatives) {
    const items = alternatives.map(([transcript, confidence]) => ({ transcript, confidence }));
    this.onresult?.({ resultIndex: 0, results: [Object.assign(items, { isFinal: true })] });
  }
  fail(error) { this.onerror?.({ error }); this.onend?.(); }
  static reset() { FakeRecognition.instances = []; }
  static last() { return FakeRecognition.instances.at(-1); }
}

export const factory = () => new FakeRecognition();
export const tick = (ms = 0) => new Promise(resolve => setTimeout(resolve, ms));
