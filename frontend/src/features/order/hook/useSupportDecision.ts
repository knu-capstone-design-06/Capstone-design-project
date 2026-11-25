import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { answersStoppedStates, createDecisionReader, matchesLogTarget } from '../backendSupport.ts';
import { stepsLeftCopy } from '../copy.ts';
import type { TransmissionState } from '../touchFeatureTransport.ts';
import { useNextTouch } from './useNextTouch.ts';

type Place = { sessionId: string; screen: string };

/**
 * 시연 스위치를 켠 backend가 정한 지원 가운데 묻지 않고 실행하는 것을 화면에 둡니다.
 * 4-2 강조(2-1 화면 도움 강조 highlight_large_view_help도 같음): 결정 ID마다 한 번, 대상 조작에 힌트 강조와 같은 고리·후광(.hint-ring)을
 * 둡니다. 창이 아니고 배치도 바꾸지 않습니다.
 * 같은 결정을 실은 응답이 오는 동안 남고, 다른 결정이나 결정 없는 응답·고객의 다음 터치·화면 전환에 사라지며, 대상이 화면에 없으면
 * 아무것도 하지 않습니다.
 * 3-1 남은 단계 안내: 대기 상태의 안내라서 기존 안내 자리에 그 상태가 끝날 때까지 남습니다(고객의 터치로는 닫히지 않음).
 * 같은 결정 ID를 실은 응답이 오는 동안 남고 남은 단계 수를 따라가며, 그 결정이 없는 응답·화면 전환·세션 변경에 끝납니다.
 * 전송이 멈추면 내렸다가, 뒤에 받아들인 응답이 같은 결정 ID를 다시 실으면 되살립니다.
 * 2-2 새 손님: onRestart(OrderPage)가 "처음부터 주문할까요?" 창을 열었을 때만 그 결정 ID를 씁니다(이미 열려 있던 창도 연 것으로 침).
 * 열지 못했으면(다른 창이나 제안 카드) 같은 결정을 실은 다음 응답에서 다시 부릅니다.
 */
export function useSupportDecision({ sessionId, screen, root, onRestart }: {
  sessionId: string | null; screen: string; root: RefObject<HTMLElement | null>; onRestart?: () => boolean;
}) {
  const [read] = useState(createDecisionReader);
  const [highlight, setHighlight] = useState<(Place & { decisionId: string; targetId: string }) | null>(null);
  const [notice, setNotice] = useState<(Place & { text: string }) | null>(null);
  // 개발 모드의 상태 줄: 마지막 응답의 지원 이름과 결정 ID(3-2 기다림처럼 고객 화면에 아무것도 없는 결정도 보임)
  const [status, setStatus] = useState<{ name: string; decisionId: string } | null>(null);
  const latest = useRef({ sessionId, screen, onRestart });
  useLayoutEffect(() => { latest.current = { sessionId, screen, onRestart }; });

  const act = useCallback((response: unknown) => {
    const { sessionId: session, screen: now, onRestart: openRestart } = latest.current;
    if (!session) return;
    const { status: last, highlight: ring, notice: held, restart } = read(response, session);
    if (restart && openRestart?.()) read.restartOpened(restart.sessionId, restart.decisionId);
    if (import.meta.env.DEV) {
      setStatus(previous => previous?.name === last?.name && previous?.decisionId === last?.decisionId ? previous : last);
    }
    // 강조는 backend의 지금 결정을 따릅니다: 같은 결정이면 그대로, 다른 결정이나 결정 없음이면 내립니다.
    setHighlight(previous => !ring ? null : previous?.sessionId === session && previous.decisionId === ring.decisionId ? previous
      : { sessionId: session, screen: now, decisionId: ring.decisionId, targetId: ring.targetId });
    const text = held ? stepsLeftCopy(held.stepsLeft) : '';
    setNotice(previous => !text ? null : previous?.sessionId === session && previous.text === text ? previous
      : { sessionId: session, screen: previous?.screen ?? now, text });
  }, [read]);
  const endNotice = useCallback(() => { read.endNotice(); setNotice(null); }, [read]);
  const endHighlight = useCallback(() => { read.endHighlight(); setHighlight(null); }, [read]);
  // 응답이 끊기면 내리기만 하고, 뒤의 응답이 같은 결정 ID를 다시 실으면 되살립니다(createDecisionReader).
  const onTransportState = useCallback((state: TransmissionState['state']) => {
    if (answersStoppedStates.includes(state)) { read.pauseNotice(); setNotice(null); }
  }, [read]);

  const target = highlight && highlight.sessionId === sessionId && highlight.screen === screen ? highlight.targetId : null;
  const noticeText = notice && notice.sessionId === sessionId && notice.screen === screen ? notice.text : '';
  useEffect(() => { endHighlight(); endNotice(); }, [sessionId, screen, endHighlight, endNotice]);
  useEffect(() => { setStatus(null); }, [sessionId]);
  useNextTouch(target !== null, root, endHighlight);
  useLayoutEffect(() => {
    const scope = root.current;
    if (!target || !scope) return;
    // 열린 창(dialog)이 있으면 그 안에서만 찾습니다. 창 뒤의 조작은 누를 수 없고, 누를 수 없는 조작에는 고리를 두지 않습니다.
    const area = scope.querySelector('dialog[open]') ?? scope;
    const elements = [...area.querySelectorAll<HTMLElement>('[data-log-target]')].filter(element =>
      matchesLogTarget(target, element.dataset.logTarget ?? '') && !element.closest('dialog:not([open])')
      && !element.matches(':disabled') && element.getClientRects().length > 0);
    for (const element of elements) element.classList.add('hint-ring');
    return () => { for (const element of elements) element.classList.remove('hint-ring'); };
  });

  return { act, onTransportState, notice: noticeText, status };
}
