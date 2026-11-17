import { useLayoutEffect, useRef, useState } from 'react';
import { backendApi } from '../../../shared/api/index.ts';
import { createSupportTransport, readBackendSupport, supportSettings } from '../backendSupport.ts';
import type { SupportPreset } from '../backendSupport.ts';
import type { Settings } from '../model.ts';
import type { SavedLog } from '../touchLog.ts';

export function useBackendSupport({ sessionId, contextKey, enabled, settings, read, onApply }: {
  sessionId: string | null; contextKey: string; enabled: boolean; settings: Settings;
  read: () => SavedLog | null; onApply: (key: keyof Settings) => void;
}) {
  const [offer, setOffer] = useState<{ preset: SupportPreset; context: string } | null>(null);
  const answered = useRef(new Set<SupportPreset>());
  const pending = useRef(false);
  const lastSession = useRef(sessionId);
  const latest = useRef({ settings, onApply, sessionId, contextKey });
  useLayoutEffect(() => { latest.current = { settings, onApply, sessionId, contextKey }; });
  const [transport] = useState(() => createSupportTransport(backendApi.sendFeatureWindow, read, response => {
    const current = latest.current;
    const preset = readBackendSupport(response, current.sessionId ?? '', current.settings);
    if (preset && !pending.current && !answered.current.has(preset)) {
      pending.current = true;
      setOffer({ preset, context: current.contextKey });
    }
  }));
  // 설정·화면·주문 상태 변경은 응답뿐 아니라 이미 열린 제안도 무효화합니다.
  useLayoutEffect(() => {
    if (lastSession.current !== sessionId) { answered.current.clear(); lastSession.current = sessionId; }
    pending.current = false; setOffer(null);
    const ready = () => enabled && document.visibilityState === 'visible';
    const update = () => {
      transport.setContext(sessionId, contextKey, ready());
      if (!ready()) { pending.current = false; setOffer(null); }
    };
    const suspend = () => { transport.setContext(sessionId, contextKey, false); pending.current = false; setOffer(null); };
    update();
    const timer = setInterval(() => { if (!pending.current) void transport.tick(); }, 2000);
    document.addEventListener('visibilitychange', update);
    window.addEventListener('pagehide', suspend);
    window.addEventListener('pageshow', update);
    return () => {
      clearInterval(timer); transport.dispose();
      document.removeEventListener('visibilitychange', update);
      window.removeEventListener('pagehide', suspend); window.removeEventListener('pageshow', update);
    };
  }, [sessionId, contextKey, enabled, read, transport]);

  const current = enabled && offer?.context === contextKey && !settings[supportSettings[offer.preset].key] ? offer : null;
  function answer(accept: boolean) {
    if (!current) return;
    answered.current.add(current.preset);
    if (accept) latest.current.onApply(supportSettings[current.preset].key);
    pending.current = false; setOffer(null);
  }
  return { preset: current?.preset ?? null, accept: () => answer(true), decline: () => answer(false) };
}
