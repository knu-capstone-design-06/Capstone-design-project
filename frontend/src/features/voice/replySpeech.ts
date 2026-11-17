export type ReplySpeaker = (text: string, signal: AbortSignal) => Promise<boolean>;

type SpeechScope = {
  speechSynthesis?: Pick<SpeechSynthesis, 'speak' | 'cancel' | 'getVoices'>
    & Partial<Pick<SpeechSynthesis, 'addEventListener' | 'removeEventListener'>>;
  SpeechSynthesisUtterance?: new (text: string) => SpeechSynthesisUtterance;
};

/** 서버의 짧은 답만 읽습니다. 취소 시 end 이벤트가 없어도 끝내며 늦은 이벤트는 무시합니다. */
export function createReplySpeaker(scope: object = globalThis, timeoutMs = 15_000): ReplySpeaker {
  const { speechSynthesis: synthesis, SpeechSynthesisUtterance: Utterance } = scope as SpeechScope;
  // Chrome may populate the installed voices only after the first read.
  try { synthesis?.getVoices(); } catch { /* Playback handles unavailable synthesis. */ }
  return (text, signal) => new Promise(resolve => {
    if (signal.aborted || !synthesis || !Utterance || !text.trim()) { resolve(false); return; }
    let finished = false;
    let started = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let voiceTimer: ReturnType<typeof setTimeout> | undefined;
    let waitingForVoices = false;
    const utterance = new Utterance(text.trim());
    const stopWaitingForVoices = () => {
      clearTimeout(voiceTimer);
      if (waitingForVoices) synthesis.removeEventListener?.('voiceschanged', voicesChanged);
      waitingForVoices = false;
    };
    const finish = (success: boolean, cancel = false) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      stopWaitingForVoices();
      signal.removeEventListener('abort', abort);
      utterance.onend = null; utterance.onerror = null;
      if (cancel) { try { synthesis.cancel(); } catch { /* 이미 종료된 재생 */ } }
      resolve(success);
    };
    const speak = () => {
      if (finished || started) return;
      started = true;
      stopWaitingForVoices();
      try {
        const korean = synthesis.getVoices().filter(voice => /^ko(?:-|$)/i.test(voice.lang));
        const voice = korean.find(voice => voice.localService) ?? korean[0];
        if (voice) utterance.voice = voice;
        synthesis.speak(utterance);
      } catch { finish(false, true); }
    };
    const voicesChanged = () => {
      if (finished) return;
      try { if (synthesis.getVoices().length) speak(); } catch { finish(false, true); }
    };
    const abort = () => finish(false, true);
    utterance.lang = 'ko-KR';
    utterance.onend = () => finish(true);
    utterance.onerror = () => finish(false, true);
    signal.addEventListener('abort', abort, { once: true });
    timer = setTimeout(() => finish(false, true), timeoutMs);
    try {
      if (synthesis.getVoices().length || !synthesis.addEventListener || !synthesis.removeEventListener) {
        speak();
      } else {
        waitingForVoices = true;
        synthesis.addEventListener('voiceschanged', voicesChanged);
        // A browser that never supplies a voice list must still be able to read.
        // This wait is part of the existing total playback timeout.
        voiceTimer = setTimeout(speak, 1_000);
        voicesChanged();
      }
    } catch { finish(false, true); }
  });
}
