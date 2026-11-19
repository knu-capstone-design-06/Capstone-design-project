import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { FeatureWindowResponse } from '../../../shared/api/index.ts';
import { supportSettings } from '../backendSupport.ts';
import type { SupportPreset } from '../backendSupport.ts';
import type { HintKind } from '../copy.ts';
import type { Settings } from '../model.ts';

type SupportLocation = { sessionId: string; screen: string };

/** 개발용 일괄 확대 시안입니다. 표시 상태와 되돌리기만 관리합니다. */
export function useEnlargementPreview({ settings, screen, sessionId, orderDone }: {
  settings: Settings; screen: string; sessionId: string | null; orderDone: boolean;
}) {
  const [offer, setOffer] = useState<SupportLocation | null>(null);
  const [largeView, setLargeView] = useState(false);
  const [applied, setApplied] = useState(false);
  const canPreview = !orderDone && !largeView && !settings.largeText;
  const current = canPreview && offer?.screen === screen && offer.sessionId === sessionId ? offer : null;
  useEffect(() => { if (offer && !current) setOffer(null); }, [offer, current]);

  function reset() { setLargeView(false); setApplied(false); setOffer(null); }
  return {
    offer: current, largeView, applied,
    open() {
      if (import.meta.env.DEV && canPreview && sessionId) {
        setApplied(false);
        setOffer({ sessionId, screen });
      }
    },
    accept() {
      if (current) { setLargeView(true); setApplied(true); }
      setOffer(null);
    },
    decline() { setOffer(null); },
    closeApplied() { setApplied(false); },
    reset,
  };
}

type SupportDraft = {
  receive: (response: FeatureWindowResponse, sentFor?: SupportLocation) => boolean;
  previewEnlargement: () => void;
  hint: (kind: HintKind | null) => void;
  clear: () => void;
};
declare global { interface Window { kioskSupportDraft?: SupportDraft } }

export function useSupportDraft(api: Omit<SupportDraft, 'receive'> & { receive: (response: unknown) => boolean },
  context: { sessionId: string | null; screen: string; ready: boolean }) {
  const latest = useRef({ api, context });
  useLayoutEffect(() => { latest.current = { api, context }; });
  useEffect(() => {
    if (import.meta.env.DEV) {
      const draft: SupportDraft = {
        receive(response, sentFor) {
          const { api: current, context: now } = latest.current;
          if (sentFor && (sentFor.sessionId !== now.sessionId || sentFor.screen !== now.screen)) return false;
          return current.receive(response);
        },
        previewEnlargement: () => latest.current.api.previewEnlargement(),
        hint: kind => latest.current.api.hint(kind),
        clear: () => latest.current.api.clear(),
      };
      window.kioskSupportDraft = draft;
      return () => { if (window.kioskSupportDraft === draft) delete window.kioskSupportDraft; };
    }
  }, []);
  const fromAddress = useRef(false);
  useEffect(() => {
    if (import.meta.env.DEV) {
      const { api: current, context: now } = latest.current;
      if (fromAddress.current || !now.sessionId || !now.ready) return;
      fromAddress.current = true;
      const params = new URLSearchParams(location.search);
      const preset = params.get('support');
      if (preset && Object.hasOwn(supportSettings, preset)) {
        current.receive({ session_id: now.sessionId, ai_available: true, support: {
          preset: preset as SupportPreset,
          requires_confirmation: params.get('confirm') !== '0',
          decided_by: 'rule_placeholder',
        } });
      } else if (params.get('preview') === 'enlarge') {
        current.previewEnlargement();
      }
      const hint = params.get('hint');
      if (hint === 'option-add' || hint === 'cart-remove') current.hint(hint);
    }
  }, [context.sessionId, context.ready]);
}
