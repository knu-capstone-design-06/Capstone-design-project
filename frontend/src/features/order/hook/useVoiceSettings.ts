import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createVoiceSettingsReceiver } from '../voiceSettings.ts';
import type { VoiceSettingChanges, VoiceSettingsContext } from '../voiceSettings.ts';

type VoiceSettingsDraft = { prepare: () => ((changes: unknown) => boolean) | null };
declare global { interface Window { kioskVoiceSettingsDraft?: VoiceSettingsDraft } }

/** 음성 UI 계약 합의 전에는 개발 빌드의 수동 검증 경로만 연결합니다. */
export function useVoiceSettings(context: VoiceSettingsContext, onApply: (changes: VoiceSettingChanges) => void) {
  const latest = useRef({ context, onApply });
  const suspended = useRef(false);
  const [receiver] = useState(() => createVoiceSettingsReceiver(changes => latest.current.onApply(changes)));
  function sync() {
    const next = latest.current.context;
    receiver.setContext({ ...next, available: next.available && !suspended.current && document.visibilityState === 'visible' });
  }
  useLayoutEffect(() => { latest.current = { context, onApply }; sync(); });
  useEffect(() => {
    suspended.current = false; sync();
    const hide = () => { receiver.invalidate(); sync(); };
    const suspend = () => { suspended.current = true; hide(); };
    const resume = () => { suspended.current = false; hide(); };
    document.addEventListener('visibilitychange', hide);
    window.addEventListener('pagehide', suspend);
    window.addEventListener('pageshow', resume);
    const draft: VoiceSettingsDraft = { prepare: () => {
      sync();
      const finish = receiver.prepare();
      return finish ? changes => { sync(); return finish(changes); } : null;
    } };
    if (import.meta.env.DEV) window.kioskVoiceSettingsDraft = draft;
    return () => {
      suspended.current = true;
      receiver.invalidate(); sync();
      document.removeEventListener('visibilitychange', hide);
      window.removeEventListener('pagehide', suspend);
      window.removeEventListener('pageshow', resume);
      if (import.meta.env.DEV && window.kioskVoiceSettingsDraft === draft) delete window.kioskVoiceSettingsDraft;
    };
  }, [receiver]);
  return receiver;
}
