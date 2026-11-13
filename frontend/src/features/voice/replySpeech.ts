export type ReplySpeaker = (text: string, signal: AbortSignal) => Promise<boolean>;

type SpeechScope = {
  speechSynthesis?: Pick<SpeechSynthesis, 'speak' | 'cancel' | 'getVoices'>;
  SpeechSynthesisUtterance?: new (text: string) => SpeechSynthesisUtterance;
};

/** 서버의 짧은 답만 읽습니다. 취소 시 end 이벤트가 없어도 끝내며 늦은 이벤트는 무시합니다. */
export function createReplySpeaker(scope: object = globalThis, timeoutMs = 15_000): ReplySpeaker {
  const { speechSynthesis: synthesis, SpeechSynthesisUtterance: Utterance } = scope as SpeechScope;
  return (text, signal) => new Promise(resolve => {
    if (signal.aborted || !synthesis || !Utterance || !text.trim()) { resolve(false); return; }
    let finished = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const utterance = new Utterance(text.trim());
    const finish = (success: boolean, cancel = false) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
      utterance.onend = null; utterance.onerror = null;
      if (cancel) { try { synthesis.cancel(); } catch { /* 이미 종료된 재생 */ } }
      resolve(success);
    };
    const abort = () => finish(false, true);
    utterance.lang = 'ko-KR';
    utterance.onend = () => finish(true);
    utterance.onerror = () => finish(false, true);
    signal.addEventListener('abort', abort, { once: true });
    timer = setTimeout(() => finish(false, true), timeoutMs);
    try {
      const korean = synthesis.getVoices().filter(voice => /^ko(?:-|$)/i.test(voice.lang));
      const voice = korean.find(voice => voice.localService) ?? korean[0];
      if (voice) utterance.voice = voice;
      synthesis.speak(utterance);
    } catch { finish(false, true); }
  });
}
