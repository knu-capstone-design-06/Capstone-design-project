import type { ReactNode, Ref } from 'react';
import { money } from '../model.ts';
import { CartLine } from './CartLine.tsx';
import type { CartDisplayLine, CartLineActions } from './CartLine.tsx';
import { Sheet } from './Sheet.tsx';
import './cart.css';

/**
 * 장바구니 시트: 메뉴 화면의 장바구니와 같은 제목 줄, 담은 줄 전부, 이 시트에서 한 일의 안내 줄(있을 때만), 아래 줄에 총 금액·[닫기]·[주문 확인].
 * 열려 있을 때만 줄을 그려 화면의 `.cart-row` 수가 겹치지 않게 합니다.
 */
export function CartSheet({ ref, open, lines, count, total, status, actions, reviewDisabled, onClose, onReview }: {
  ref: Ref<HTMLDialogElement>; open: boolean; lines: CartDisplayLine[]; count: number; total: number; status: ReactNode | null;
  actions: CartLineActions; reviewDisabled: boolean; onClose: () => void; onReview: () => void;
}) {
  return <Sheet ref={ref} className="cart-sheet" labelledBy="cart-sheet-title" onClose={onClose}>
    {open && <>
      <div className="cart-sheet-head">
        <div className="cart-head"><h2 id="cart-sheet-title" className="cart-title">담은 메뉴 {count}개</h2></div>
        {status && <div className="sheet-support">{status}</div>}
      </div>
      <ul className="cart-lines">{lines.length ? lines.map(line => <CartLine key={`${line.item.item_id}:${line.removed}`} line={line} actions={actions} />)
        : <li className="cart-empty">메뉴를 담아 주세요</li>}</ul>
      <div className="sheet-bar">
        <div className="sheet-total"><span className="total-label">총 주문 금액</span><strong className="amount">{money(total)}</strong></div>
        <button type="button" data-log-target="cart-sheet-close" className="sheet-cancel" onClick={onClose}>닫기</button>
        <button type="button" data-log-target="cart-sheet-review" className="primary sheet-main" disabled={reviewDisabled} onClick={onReview}>주문 확인</button>
      </div>
    </>}
  </Sheet>;
}
