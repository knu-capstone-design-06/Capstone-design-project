import { useEffect, useState } from 'react';
import { doubleClickMs } from '../utils/timing.ts';

/**
 * 두 번 클릭 간격의 보호: change가 바뀐 그 그림부터 doubleClickMs 동안 false이고, 그 밖에는 true입니다(처음 그릴 때도 true).
 * 창이 닫히거나 화면이 바뀌어 같은 자리에 다른 버튼이 설 때, 그 자리를 연달아 누르던 손가락이 새 버튼을 누르지 않게 합니다.
 * change에는 그런 일이 생길 때마다 하나씩 늘리는 수를 줍니다. 쓰는 쪽은 그동안의 누름을 무시할 뿐 버튼을 비활성으로 바꾸지 않습니다
 * (제안 카드의 대답 버튼과 같은 방식, OfferCard).
 */
export function useArmedAfter(change: number) {
  const [armedFor, setArmedFor] = useState(change);
  useEffect(() => {
    const timer = setTimeout(() => setArmedFor(change), doubleClickMs);
    return () => clearTimeout(timer);
  }, [change]);
  return armedFor === change;
}
