import { useEffect, useLayoutEffect, useRef } from 'react';
import type { RefObject } from 'react';

/**
 * 고객의 다음 터치에서 한 번 부릅니다(안내는 시간이 아니라 고객의 다음 터치에 닫힙니다).
 * 주문 화면(scope) 안에서 시작한 터치만 세고, ignore 선택자에 걸리는 곳의 터치는 세지 않습니다.
 * 손을 뗀 뒤(그 터치가 누른 버튼의 동작이 끝난 뒤)에 부르므로, 안내가 닫히며 배치가 바뀌어도 누른 버튼의 동작은 잃지 않습니다.
 * 콜백은 터치 시작 시점에 잡아, 버튼 동작으로 새로 뜬 안내와 기존 안내를 구분할 수 있게 합니다.
 */
export function useNextTouch(active: boolean, scope: RefObject<HTMLElement | null>, onTouch: () => void, ignore?: string) {
  const callback = useRef(onTouch);
  useLayoutEffect(() => { callback.current = onTouch; });
  useEffect(() => {
    if (!active) return;
    let onStartedTouch: (() => void) | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const start = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      onStartedTouch = target && scope.current?.contains(target) && !(ignore && target.closest(ignore)) ? callback.current : null;
    };
    const end = () => {
      if (!onStartedTouch) return;
      timer = setTimeout(onStartedTouch, 0);
      onStartedTouch = null;
    };
    document.addEventListener('pointerdown', start, true);
    document.addEventListener('pointerup', end, true);
    document.addEventListener('pointercancel', end, true);
    return () => {
      document.removeEventListener('pointerdown', start, true);
      document.removeEventListener('pointerup', end, true);
      document.removeEventListener('pointercancel', end, true);
      if (timer) clearTimeout(timer);
    };
  }, [active, scope, ignore]);
}
