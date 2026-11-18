import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { backendApi } from '../../../shared/api/index.ts';
import { createSupportTransport, readBackendSupport, supportSettings } from '../backendSupport.ts';
import type { SupportPreset } from '../backendSupport.ts';
import type { Settings } from '../model.ts';
import type { SavedLog } from '../touchLog.ts';

export function useBackendSupport({ sessionId, contextKey, canSend, canOffer, settings, read, onApply }: {
  sessionId: string | null; contextKey: string; canSend: boolean; canOffer: boolean; settings: Settings;
  read: () => SavedLog | null; onApply: (key: keyof Settings) => void;
}) {
  const [offer, setOffer] = useState<{ preset: SupportPreset; context: string } | null>(null);
  const answered = useRef(new Set<SupportPreset>());
  const dismissed = useRef({ context: contextKey, presets: new Set<SupportPreset>() });
  const lastSession = useRef(sessionId);
  const suspended = useRef(false);
  const latest = useRef({ settings, sessionId, contextKey, canSend, canOffer });
  const [transport] = useState(() => createSupportTransport(backendApi.sendFeatureWindow, read, response => {
    const current = latest.current;
    const preset = readBackendSupport(response, current.sessionId ?? '', current.settings);
    if (preset && !answered.current.has(preset) && !dismissed.current.presets.has(preset)) {
      setOffer(previous => previous ?? { preset, context: current.contextKey });
    }
  }));
  const current = canOffer && offer?.context === contextKey && !settings[supportSettings[offer.preset].key] ? offer : null;
  const syncContext = useCallback(() => {
    const { sessionId, contextKey, canSend, canOffer } = latest.current;
    const visible = !suspended.current && document.visibilityState === 'visible';
    transport.setContext(sessionId, contextKey, visible && canSend, canOffer);
    if (!visible) setOffer(null);
  }, [transport]);

  useLayoutEffect(() => {
    if (lastSession.current !== sessionId) { answered.current.clear(); lastSession.current = sessionId; }
    if (dismissed.current.context !== contextKey) {
      dismissed.current = { context: contextKey, presets: new Set() };
    }
    latest.current = { settings, sessionId, contextKey, canSend, canOffer: canOffer && current === null };
    syncContext();
    if (offer && !current) setOffer(null);
  });

  // 입력 구간의 주기는 화면·분류·장바구니 변경과 별개로 유지합니다.
  useLayoutEffect(() => {
    const suspend = () => { suspended.current = true; syncContext(); };
    const resume = () => { suspended.current = false; syncContext(); };
    syncContext();
    // 전송기는 2초가 지난 때만 집계합니다. 아직 종료되지 않은 누름은 다음 확인 때 다시 봅니다.
    const timer = setInterval(() => { void transport.tick(); }, 250);
    document.addEventListener('visibilitychange', syncContext);
    window.addEventListener('pagehide', suspend);
    window.addEventListener('pageshow', resume);
    return () => {
      clearInterval(timer); transport.dispose();
      document.removeEventListener('visibilitychange', syncContext);
      window.removeEventListener('pagehide', suspend); window.removeEventListener('pageshow', resume);
    };
  }, [syncContext, transport]);

  function answer(accept: boolean) {
    if (!current) return;
    answered.current.add(current.preset);
    if (accept) onApply(supportSettings[current.preset].key);
    setOffer(null);
  }
  function dismiss() {
    if (!current) return;
    // 같은 화면 상태에서 반복해서 뜨는 것만 막습니다. 세션 전체의 거절로 남기지 않습니다.
    dismissed.current.presets.add(current.preset);
    setOffer(null);
  }
  return { preset: current?.preset ?? null, accept: () => answer(true), decline: () => answer(false), dismiss };
}
