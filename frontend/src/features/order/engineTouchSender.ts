import type { FeatureWindowRequest } from '../../shared/api/types.ts';

/** 같은 키오스크 PC의 AI 엔진(실시간 실행기의 터치 입구, ai-engine/app/modules/vision/touch_entry.py)이 터치 창을 받는 경로입니다. */
export const engineTouchPath = '/touch-windows';
/** 응답 없는 엔진 요청이 쌓이지 않게 끊는 시간: backend /features 요청을 끊는 시간(touchFeatureTransport.ts의 5초)과 같습니다. */
const engineSendTimeoutMs = 5000;

/**
 * 터치 창 하나를 엔진에 보냅니다. 돌려주는 Promise는 엔진이 답했을 때(상태와 관계없이, 본문을 끝까지 읽은 뒤), 요청이 실패했을 때,
 * 제한 시간이 지나 요청이 끊겼을 때 끝나며 거부(reject)하지 않습니다. 엔진의 답은 돌려주지 않습니다.
 */
export type EngineTouchSend = (sessionId: string, window: FeatureWindowRequest) => Promise<void>;

/**
 * /features로 보내는 터치 창을 서버 세션 ID와 함께 AI 엔진에도 한 방향으로 보냅니다(팀 논문 그림 1의 '주문 화면 → AI 엔진' 연결).
 * 주소가 없으면 보내는 함수를 만들지 않습니다. 엔진의 답은 쓰지 않지만 요청이 끝나도록 본문은 끝까지 읽고, 끝난 때를 Promise로 알립니다.
 * 전송기(touchFeatureTransport.ts)는 창을 엔진에 먼저 보내고, 이 Promise가 끝나거나 확인 주기 한 번(FEATURE_TICK_MS)이 지나면 같은
 * 창을 /features로 보냅니다. 실패·지연은 다시 보내지 않고 넘깁니다.
 */
export function createEngineTouchSender(baseUrl: string | undefined, fetcher: typeof fetch = fetch): EngineTouchSend | undefined {
  const base = typeof baseUrl === 'string' ? baseUrl.trim().replace(/\/+$/, '') : '';
  if (!base) return undefined;
  const url = `${base}${engineTouchPath}`;
  return (sessionId, window) => {
    try {
      return fetcher(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...window, session_id: sessionId }),
        signal: AbortSignal.timeout(engineSendTimeoutMs),
      }).then(response => response.text()).then(() => undefined, () => undefined);
    } catch {
      // 엔진 전송의 실패는 주문 화면과 /features 전송에 영향을 주지 않습니다.
      return Promise.resolve();
    }
  };
}
