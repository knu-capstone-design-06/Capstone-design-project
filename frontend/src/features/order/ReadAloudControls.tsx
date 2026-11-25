import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { useVoiceInput } from '../voice/index.ts';
import type { VoiceController } from '../voice/index.ts';
import { Icon } from './components/icons.tsx';
import { SettingTile } from './components/HelpSheet.tsx';

function screenText(root: HTMLElement): string {
  // 화면 도움 시트는 읽기 도구가 있는 곳이라 읽지 않고, 그 뒤의 화면(또는 열린 옵션·장바구니 창)을 읽습니다.
  const scope = root.querySelector('dialog[open]:not(.help-sheet)') ?? root;
  const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  const buttons = new Set<Element>();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const element = node.parentElement;
    if (!element || element.closest('[aria-hidden="true"], [hidden], dialog:not([open]), .help-sheet, [data-read-aloud-tools], .voice-mode-control, .voice-entry')
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
    const owned = utterance.current !== null;
    utterance.current = null;
    if (supported && owned) window.speechSynthesis.cancel();
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
      stop();
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
  // 화면 도움 시트의 '음성 안내' 묶음: 화면 읽기·누름 소리 타일과 [읽기 중단] [다시 읽기]. 동작과 대상 이름은 그대로입니다.
  return <section data-read-aloud-tools aria-label="음성 안내와 누름 소리" className="read-aloud-tools">
    <h3 className="group-title">음성 안내</h3>
    <div className="support-options cols2">
      <SettingTile target="read-aloud-toggle" icon="record_voice_over" label="화면 읽기" on={enabled} disabled={!supported}
        onClick={() => { voiceController.setEnabled(false); setEnabled(current => !current); }} />
      <SettingTile target="touch-sound-toggle" icon="volume_up" label="누름 소리" on={sound} disabled={!soundSupported} onClick={() => {
        try {
          if (!sound) {
            if (!audio.current || audio.current.state === 'closed') audio.current = new AudioContext();
            void audio.current.resume().catch(() => { setSound(false); setMessage('누름 소리를 켜지 못했어요.'); });
          }
          setSound(current => !current);
        } catch { setSound(false); setMessage('누름 소리를 켜지 못했어요.'); }
      }} />
    </div>
    <div className="cols">
      <button data-log-target="read-aloud-stop" type="button" disabled={!reading} onClick={stop}><Icon name="stop" />읽기 중단</button>
      <button data-log-target="read-aloud-replay" type="button" disabled={!supported || !enabled || voice.enabled || voice.microphoneActive} onClick={read}><Icon name="replay" />다시 읽기</button>
    </div>
    <p className="sheet-desc">말로 주문을 켜면 화면 읽기는 멈춰요.</p>
    {!supported && <p className="sheet-desc">이 브라우저에서는 음성 안내를 사용할 수 없습니다.</p>}
    {message && <p className="sheet-status" role="status">{message}</p>}
  </section>;
}
