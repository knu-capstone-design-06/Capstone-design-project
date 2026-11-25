import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { askMemory, askSettings, askSettled, cardAfterAnswer, offeredCard } from '../backendSupport.ts';
import type { HeldAsk } from '../backendSupport.ts';
import type { Settings } from '../model.ts';
import { FEATURE_TICK_MS } from '../touchFeatureTransport.ts';
import type { createTouchFeatureTransport, TransmissionState } from '../touchFeatureTransport.ts';

export function useBackendSupport({ sessionId, contextKey, canSend, canOffer, settings, voiceOrder = false, transport, includeInteraction, onApply, onVoiceOrder, onDecision, onTransportState }: {
  sessionId: string | null; contextKey: string; canSend: boolean; canOffer: boolean; settings: Settings;
  /** 1-1 말로 주문을 지금 물을 수 있는지(backendSupport.ts의 voiceOrderAskable)입니다. */
  voiceOrder?: boolean;
  transport: ReturnType<typeof createTouchFeatureTransport>; includeInteraction: boolean;
  onApply: (key: keyof Settings) => void;
  /** 1-1 말로 주문 질문의 예: 마이크 버튼과 같이 말로 주문을 켭니다. */
  onVoiceOrder?: () => void;
  /** 묻지 않고 실행하는 결정(강조·안내)을 읽는 곳입니다. 제안을 띄울 수 없는 동안(옵션 창 등)에도 현재 화면의 응답마다 부릅니다. */
  onDecision?: (response: unknown) => void;
  /** 전송기의 상태(TransmissionState.state)를 확인 주기마다 받습니다. 응답이 끊기면 남아 있는 안내를 끝내는 데 씁니다. */
  onTransportState?: (state: TransmissionState['state']) => void;
}) {
  const [offer, setOffer] = useState<HeldAsk | null>(null);
  // 대답·닫음의 기억은 askMemory의 이름으로 남깁니다(크게 보기는 large_text·large_button 둘 다).
  const answered = useRef(new Set<string>());
  const dismissed = useRef({ context: contextKey, asks: new Set<string>() });
  const lastSession = useRef(sessionId);
  const suspended = useRef(false);
  // canOffer: 새 카드를 띄울 수 있음(카드가 없을 때만). askGate: 화면 자신의 묻기 조건 그대로(touch.scene_signals.can_offer로 보냄).
  const latest = useRef({ settings, voiceOrder, sessionId, contextKey, canSend, canOffer, askGate: canOffer });
  const decision = useRef({ onDecision, onTransportState });
  // 응답 하나가 띄울 새 카드: 화면의 조건(gate)과 페이지가 보이는지, 대답·닫음의 기억, 묻는 지원의 확인(offeredCard)을 거칩니다.
  // 묻지 않고 실행하는 결정(강조·남은 단계 안내·기다림)은 onDecision 쪽이 맡아 여기서 다시 묻지 않습니다.
  const offerable = useCallback((response: unknown, gate: boolean) => {
    const current = latest.current;
    if (!current.sessionId || suspended.current || document.visibilityState !== 'visible') return null;
    return offeredCard(response, { sessionId: current.sessionId, settings: current.settings, voiceOrder: current.voiceOrder,
      context: current.contextKey, gate }, name => answered.current.has(name) || dismissed.current.asks.has(name));
  }, []);
  const act = useCallback((response: unknown) => {
    // 결정 ID로 연 카드는 backend가 그 묻기를 거두거나 다른 결정으로 바꾸면 내리고(keepAsk), 같은 응답이 실은 묻기를 그 자리에 바로
    // 띄웁니다(cardAfterAnswer). 그때 화면의 조건은 내린 카드를 뺀 것(askGate)입니다.
    const session = latest.current.sessionId;
    if (session) {
      const next = offerable(response, latest.current.askGate);   // 지금 확인하고, 카드가 내려갈 때만 씀
      setOffer(previous => cardAfterAnswer(previous, response, session, () => next));
    }
    decision.current.onDecision?.(response);
  }, [offerable]);
  const onState = useCallback((state: TransmissionState['state']) => decision.current.onTransportState?.(state), []);
  // 개발용 고정 응답과 HTTP 응답 모두 같은 확인과 적용을 거칩니다.
  const receive = useCallback((response: unknown) => {
    const next = offerable(response, latest.current.canOffer);
    if (!next) return false;
    setOffer(previous => previous ?? next);
    return true;
  }, [offerable]);
  const current = canOffer && offer?.context === contextKey && !askSettled(offer.ask, settings, voiceOrder) ? offer : null;
  const syncContext = useCallback(() => {
    const { sessionId, contextKey, canSend, canOffer, askGate } = latest.current;
    const visible = !suspended.current && document.visibilityState === 'visible';
    transport.setContext(sessionId, visible && canSend, { key: contextKey, canOffer, includeInteraction, receive, act, onState, askGate });
    if (!visible) setOffer(null);
  }, [transport, includeInteraction, receive, act, onState]);

  useLayoutEffect(() => {
    if (lastSession.current !== sessionId) { answered.current.clear(); lastSession.current = sessionId; }
    if (dismissed.current.context !== contextKey) {
      dismissed.current = { context: contextKey, asks: new Set() };
    }
    latest.current = { settings, voiceOrder, sessionId, contextKey, canSend, canOffer: canOffer && current === null, askGate: canOffer };
    decision.current = { onDecision, onTransportState };
    syncContext();
    if (offer && !current) setOffer(null);
  });

  // 입력 구간의 주기는 화면·분류·장바구니 변경과 별개로 유지합니다.
  useLayoutEffect(() => {
    const suspend = () => { suspended.current = true; syncContext(); };
    const resume = () => { suspended.current = false; syncContext(); };
    syncContext();
    // 전송기는 구간(FEATURE_WINDOW_MS, 1초)이 지난 때만 집계합니다. 아직 종료되지 않은 누름은 다음 확인 때 다시 봅니다.
    const timer = setInterval(() => { void transport.tick(); }, FEATURE_TICK_MS);
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
    for (const name of askMemory(current.ask)) answered.current.add(name);
    // 크게 보기는 두 설정을 함께 켭니다. 말로 주문은 켜는 화면 설정 없이 말로 주문을 켭니다.
    if (accept && current.ask === 'voice_order') onVoiceOrder?.();
    else if (accept) for (const key of askSettings(current.ask)) onApply(key);
    setOffer(null);
  }
  function dismiss() {
    if (!current) return;
    // 같은 화면 상태에서 반복해서 뜨는 것만 막습니다. 세션 전체의 거절로 남기지 않습니다.
    for (const name of askMemory(current.ask)) dismissed.current.asks.add(name);
    setOffer(null);
  }
  // card: 떠 있는 카드와 그 결정 ID(2-2 창을 기다리게 하는지 보는 데 씀: backendSupport.ts의 cardHoldsRestart)
  return { ask: current?.ask ?? null, card: current, accept: () => answer(true), decline: () => answer(false), dismiss, receive };
}
