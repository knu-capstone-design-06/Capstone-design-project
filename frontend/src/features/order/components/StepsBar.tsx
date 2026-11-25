import type { Ref } from 'react';
import { Icon } from './icons.tsx';
import './topCluster.css';

export type OrderScreen = 'menu' | 'review' | 'complete';
const steps: [OrderScreen, string][] = [['menu', '메뉴 선택'], ['review', '주문 확인'], ['complete', '주문 완료']];

/**
 * 주문 단계 표시가 화면 제목입니다. 지금 단계의 이름이 h1이고, 화면이 바뀌면 이 제목으로 초점을 옮깁니다.
 * 모든 모드에서 한 줄입니다. 큰 글씨에서는 세 번호와 지금 단계의 이름만 보입니다.
 * headingRef가 없으면 보이기만 하는 사본(낮은 화면의 위쪽 읽기 자리)으로, 제목 요소를 두지 않습니다.
 */
export function StepsBar({ screen, headingRef }: { screen: OrderScreen; headingRef?: Ref<HTMLHeadingElement> }) {
  const current = steps.findIndex(([key]) => key === screen);
  return <nav className="steps" aria-label="주문 단계"><ol>
    {steps.map(([key, label], index) => {
      const state = index < current ? 'done' : index === current ? 'current' : 'next';
      return <li key={key} className={`step ${state}`} aria-current={state === 'current' ? 'step' : undefined}>
        <span className="disc" aria-hidden="true">{state === 'done' ? <Icon name="check" /> : <span className="num">{index + 1}</span>}</span>
        {state === 'current' && headingRef ? <h1 ref={headingRef} tabIndex={-1} className="label">{label}</h1> : <span className="label">{label}</span>}
      </li>;
    })}
  </ol></nav>;
}
