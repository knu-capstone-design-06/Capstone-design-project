import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { FeatureWindowResponse } from '../../../shared/api/index.ts';
import type { Settings } from '../model.ts';
import type { HintKind } from '../copy.ts';
import { alreadyLarge, readSupportDecision } from '../utils/supportDecision.ts';
import type { SupportAction, SupportKind } from '../utils/supportDecision.ts';

export type SupportOffer = { support: SupportKind; sessionId: string; screen: string };

/**
 * 키오스크가 먼저 띄우는 화면 지원: 기다리는 제안 하나, 크게 보기의 켜짐(largeView), 적용 알림.
 * 크게 보기는 화면 설정(Settings)에 넣지 않은 이 화면만의 상태라서 저장하지 않고, 새로고침·[새 주문 시작]·[기본 화면으로]에서 끝납니다.
 * 받아들이면 크게 보기를 켜고 적용 알림을 보입니다. [원래대로]는 크게 보기를 끕니다. 제안은 화면이나 세션이 바뀌면 버립니다.
 */
export function useSupportOffer({ settings, screen, sessionId, orderDone }: {
  settings: Settings; screen: string; sessionId: string | null; orderDone: boolean;
}) {
  const [offer, setOffer] = useState<SupportOffer | null>(null);
  const [largeView, setLargeView] = useState(false);
  const [applied, setApplied] = useState<SupportKind | null>(null);
  // 기다리는 동안 고객이 큰 글씨를 켰거나 크게 보기가 이미 켜졌으면 더 키울 것이 없으므로 제안을 버립니다(보이지도 알리지도 않음).
  const current = offer && offer.screen === screen && offer.sessionId === sessionId && !alreadyLarge({ largeView, settings }) ? offer : null;
  useEffect(() => { if (offer && !current) setOffer(null); }, [offer, current]);

  function turnOn(support: SupportKind) {
    setLargeView(true);
    setApplied(support);
    setOffer(null);
  }
  return {
    offer: current, largeView, applied,
    /** 서버 응답 하나를 받습니다. sentFor는 그 요청을 보낸 때의 세션과 화면입니다. */
    receive(response: FeatureWindowResponse, sentFor: { sessionId: string; screen: string }): SupportAction {
      const action = readSupportDecision(response, sentFor, { sessionId, screen, orderDone, settings, largeView });
      if (action.kind === 'offer' && sessionId) { setApplied(null); setOffer({ support: action.support, sessionId, screen }); }
      if (action.kind === 'apply') turnOn(action.support);
      return action;
    },
    /** 받아들일 때 다시 확인합니다: 그사이 큰 글씨나 크게 보기가 켜졌으면 제안만 닫습니다. */
    accept() { if (current && !alreadyLarge({ largeView, settings })) turnOn(current.support); else setOffer(null); },
    decline() { setOffer(null); },
    closeApplied() { setApplied(null); },
    /** [원래대로]: 크게 보기를 끕니다. 고객이 화면 도움에서 켠 설정은 그대로입니다. */
    undo() { setLargeView(false); setApplied(null); },
    /** 화면 도움의 [기본 화면으로]는 크게 보기도 끝냅니다. */
    resetView() { setLargeView(false); setApplied(null); },
    /** 한 이용이 끝날 때(주문 완료의 [새 주문 시작]) 크게 보기를 끕니다. [처음으로]에서는 유지합니다. */
    endUse() { setLargeView(false); setOffer(null); setApplied(null); },
  };
}

type SupportDraft = {
  receive: (response: FeatureWindowResponse, sentFor?: { sessionId: string; screen: string }) => SupportAction | null;
  hint: (kind: HintKind | null) => void;
  clear: () => void;
};
declare global { interface Window { kioskSupportDraft?: SupportDraft } }

/**
 * 개발용 시험 장치(개발 서버에서만): 서버 없이 제안·적용·힌트 화면을 띄웁니다. 화면에는 아무것도 더하지 않습니다.
 * - window.kioskSupportDraft.receive(response, sentFor?): FeatureWindowResponse 하나를 받은 것처럼 처리
 * - window.kioskSupportDraft.hint('option-add' | 'cart-remove' | null), .clear()
 * - 주소의 ?support=large_text|large_button(&confirm=0), ?hint=option-add|cart-remove: 세션이 준비되면 한 번 적용
 * 프로덕션 빌드에서는 import.meta.env.DEV가 false라 이 코드가 빠집니다.
 */
export function useSupportDraft(api: { receive: (response: FeatureWindowResponse, sentFor: { sessionId: string; screen: string }) => SupportAction; hint: (kind: HintKind | null) => void; clear: () => void },
  context: { sessionId: string | null; screen: string }) {
  const latest = useRef({ api, context });
  useLayoutEffect(() => { latest.current = { api, context }; });
  useEffect(() => {
    if (import.meta.env.DEV) {
      const draft: SupportDraft = {
        receive(response, sentFor) {
          const { api: current, context: now } = latest.current;
          const target = sentFor ?? (now.sessionId ? { sessionId: now.sessionId, screen: now.screen } : null);
          return target ? current.receive(response, target) : null;
        },
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
      if (fromAddress.current || !now.sessionId) return;
      fromAddress.current = true;
      const params = new URLSearchParams(location.search);
      const preset = params.get('support');
      if (preset === 'large_text' || preset === 'large_button') {
        current.receive({ session_id: now.sessionId, ai_available: true, support: { preset, requires_confirmation: params.get('confirm') !== '0', decided_by: 'rule_placeholder' } },
          { sessionId: now.sessionId, screen: now.screen });
      }
      const hint = params.get('hint');
      if (hint === 'option-add' || hint === 'cart-remove') current.hint(hint);
    }
  }, [context.sessionId]);
}
