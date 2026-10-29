import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { useVoiceInput } from '../voice/index.ts';
import type { VoiceController } from '../voice/index.ts';

function screenText(root: HTMLElement): string {
  const scope = root.querySelector('dialog[open]') ?? root;
  const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  const buttons = new Set<Element>();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const element = node.parentElement;
    if (!element || element.closest('[aria-hidden="true"], [hidden], dialog:not([open]), [data-read-aloud-tools], .voice-mode-control')
      || !element.getClientRects().length || getComputedStyle(element).visibility !== 'visible') continue;
    const button = element.closest('button, a[href]');
    if (button) {
      if (buttons.has(button)) continue;
      buttons.add(button);
      parts.push(button.getAttribute('aria-label') ?? button.textContent ?? '');
    } else parts.push(node.textContent ?? '');
  }
  return parts.map(text => text.trim()).filter(Boolean).join('. ');
}

export function ReadAloudControls({ root, screenKey, voiceController }: {
  root: RefObject<HTMLDivElement | null>; screenKey: string; voiceController: VoiceController;
}) {
  const voice = useVoiceInput(voiceController);
  const [enabled, setEnabled] = useState(false);
  const [reading, setReading] = useState(false);
  const [sound, setSound] = useState(false);
  const [message, setMessage] = useState('');
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const tones = useRef(new Set<OscillatorNode>());
  const supported = typeof window.speechSynthesis !== 'undefined' && typeof window.SpeechSynthesisUtterance !== 'undefined';
  const soundSupported = typeof window.AudioContext !== 'undefined';

  function stop() {
    utterance.current = null;
    if (supported) window.speechSynthesis.cancel();
    setReading(false);
  }
  function stopSounds() {
    for (const tone of tones.current) { try { tone.stop(); } catch { /* 이미 끝난 소리 */ } }
    tones.current.clear();
  }
  function read() {
    stop(); setMessage('');
    const microphone = voiceController.getSnapshot();
    if (!supported || !root.current || microphone.enabled || microphone.microphoneActive) return;
    const text = screenText(root.current);
    if (!text) { setMessage('읽을 화면 내용이 없습니다.'); return; }
    const next = new SpeechSynthesisUtterance(text);
    next.lang = 'ko-KR';
    next.onend = () => { if (utterance.current === next) { utterance.current = null; setReading(false); } };
    next.onerror = event => {
      if (utterance.current !== next) return;
      utterance.current = null; setReading(false);
      if (event.error !== 'canceled' && event.error !== 'interrupted') setMessage('음성 안내를 재생하지 못했어요. 화면을 확인해 주세요.');
    };
    utterance.current = next;
    setReading(true);
    try { window.speechSynthesis.speak(next); }
    catch { utterance.current = null; setReading(false); setMessage('음성 안내를 재생하지 못했어요. 화면을 확인해 주세요.'); }
  }
  useEffect(() => voiceController.subscribe(() => {
    const microphone = voiceController.getSnapshot();
    // setEnabled가 인식기를 시작하기 전에 알리므로 효과 실행을 기다리지 않고 멈춥니다.
    if (microphone.enabled || microphone.microphoneActive) { stop(); stopSounds(); }
    if (microphone.enabled) setEnabled(false);
  }), [voiceController]);
  useEffect(() => {
    if (voice.enabled) { stop(); setEnabled(false); return; }
    if (voice.microphoneActive) { stop(); return; }
    if (enabled) read(); else stop();
  }, [enabled, screenKey, voice.enabled, voice.microphoneActive]);
  useEffect(() => {
    const suspend = () => { stop(); setEnabled(false); };
    const hide = () => { if (document.visibilityState !== 'visible') suspend(); };
    document.addEventListener('visibilitychange', hide);
    window.addEventListener('pagehide', suspend);
    return () => {
      document.removeEventListener('visibilitychange', hide);
      window.removeEventListener('pagehide', suspend);
      utterance.current = null;
      if (supported) window.speechSynthesis.cancel();
      stopSounds();
      if (audio.current && audio.current.state !== 'closed') void audio.current.close();
      audio.current = null;
    };
  }, []);
  useEffect(() => {
    if (!sound || !soundSupported) return;
    const click = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const button = event.target.closest('button, a[href]');
      const microphone = voiceController.getSnapshot();
      if (!button || !root.current?.contains(button) || button.matches(':disabled, [aria-disabled=true], [data-log-target="voice-mode-toggle"], [data-log-target="voice-listen"]')
        || microphone.enabled || microphone.microphoneActive) return;
      const context = audio.current;
      if (!context || context.state !== 'running') return;
      const oscillator = context.createOscillator(), gain = context.createGain();
      oscillator.frequency.value = 740;
      gain.gain.setValueAtTime(0.025, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.05);
      oscillator.connect(gain); gain.connect(context.destination);
      tones.current.add(oscillator);
      oscillator.onended = () => { tones.current.delete(oscillator); oscillator.disconnect(); gain.disconnect(); };
      oscillator.start(); oscillator.stop(context.currentTime + 0.05);
    };
    document.addEventListener('click', click, true);
    return () => document.removeEventListener('click', click, true);
  }, [sound, soundSupported, voiceController, root]);
  return <section data-read-aloud-tools aria-label="음성 안내와 누름 소리" className="read-aloud-tools">
    <h3>음성 안내</h3>
    <p>음성 입력을 켜면 화면 읽기는 멈춥니다.</p>
    <div className="support-options">
      <button data-log-target="read-aloud-toggle" type="button" aria-pressed={enabled} disabled={!supported} onClick={() => { voiceController.setEnabled(false); setEnabled(current => !current); }}>화면 읽기 {enabled ? '켜짐' : '꺼짐'}</button>
      <button data-log-target="read-aloud-stop" type="button" disabled={!reading} onClick={stop}>읽기 중단</button>
      <button data-log-target="read-aloud-replay" type="button" disabled={!supported || !enabled || voice.enabled || voice.microphoneActive} onClick={read}>다시 읽기</button>
      <button data-log-target="touch-sound-toggle" type="button" aria-pressed={sound} disabled={!soundSupported} onClick={() => {
        try {
          if (!sound) {
            if (!audio.current || audio.current.state === 'closed') audio.current = new AudioContext();
            void audio.current.resume().catch(() => { setSound(false); setMessage('누름 소리를 켜지 못했어요.'); });
          }
          setSound(current => !current);
        } catch { setSound(false); setMessage('누름 소리를 켜지 못했어요.'); }
      }}>누름 소리 {sound ? '켜짐' : '꺼짐'}</button>
    </div>
    {!supported && <p>이 브라우저에서는 음성 안내를 사용할 수 없습니다.</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
