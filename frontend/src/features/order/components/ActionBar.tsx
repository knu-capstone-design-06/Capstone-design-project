import type { Ref } from 'react';
import { money } from '../model.ts';
import './bottomCluster.css';

export type PrimaryAction = { target: string; label: string; disabled: boolean; onClick: () => void };
export type CartButton = { ref: Ref<HTMLButtonElement>; amount: number | null; onClick: () => void };

/**
 * 하단 주문 바: 총 주문 금액, [처음으로], 주요 버튼. 주요 버튼은 모든 화면에서 같은 자리에 있습니다.
 * 장바구니가 [담은 메뉴 보기] 뒤에 있는 모드(큰 글씨, 낮은 화면)에서는 그 버튼이 함께 섭니다. 낮은 화면에서는 금액을 담아
 * 총 금액 묶음을 대신합니다.
 * armed가 false인 동안(바를 덮던 창이 닫히거나 화면이 바뀐 뒤 두 번 클릭 간격) [처음으로]와 주요 버튼은 누름을 받지 않습니다.
 * 버튼은 비활성으로 바꾸지 않고, data-armed로 그 상태를 보입니다.
 */
export function ActionBar({ total, cartButton = null, restart, primary, armed, onBlockedPress }: {
  total: number | null;
  cartButton?: CartButton | null;
  restart: { ref: Ref<HTMLButtonElement>; disabled: boolean; onClick: () => void } | null;
  primary: PrimaryAction;
  armed: boolean;
  onBlockedPress: () => void;
}) {
  // 무시한 연속 입력도 보호를 다시 시작해, 긴 연타가 보호 종료 직후 다음 동작으로 이어지지 않게 합니다.
  const press = (action: () => void) => () => { if (armed) action(); else onBlockedPress(); };
  return <div className={`action-bar${total === null && !cartButton ? ' only-action' : ''}`}>
    {total !== null && <div className="total"><span className="total-label">총 주문 금액</span><strong className="amount">{money(total)}</strong></div>}
    {cartButton && <button type="button" ref={cartButton.ref} data-log-target="cart-sheet-open" className={`cart-button${cartButton.amount === null ? '' : ' with-amount'}`} onClick={cartButton.onClick}>
      <span>담은 메뉴 보기</span>{cartButton.amount !== null && <b>{money(cartButton.amount)}</b>}
    </button>}
    <div className="bar-pair">
      {restart && <button ref={restart.ref} data-log-target="order-restart" className="order-restart" data-armed={armed} disabled={restart.disabled} onClick={press(restart.onClick)}>처음으로</button>}
      <button data-log-target={primary.target} className="primary order-confirm" data-armed={armed} disabled={primary.disabled} onClick={press(primary.onClick)}>{primary.label}</button>
    </div>
  </div>;
}
