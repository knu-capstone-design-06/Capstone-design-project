import type { Ref } from 'react';
import { CartLine } from './CartLine.tsx';
import type { CartDisplayLine, CartLineActions } from './CartLine.tsx';
import './cart.css';

/** 메뉴 화면의 장바구니: "담은 메뉴 N개", 최근 줄부터 두 줄, 더 있으면 제목 줄 끝의 [모두 보기]가 장바구니 시트를 엽니다. */
export function CartPanel({ lines, count, visible, actions, openerRef, onOpenAll }: {
  lines: CartDisplayLine[]; count: number; visible: number; actions: CartLineActions;
  openerRef: Ref<HTMLButtonElement>; onOpenAll: () => void;
}) {
  return <section className="cart-panel" aria-label="담은 메뉴">
    <div className="cart-head">
      <h2 className="cart-title">담은 메뉴 {count}개</h2>
      {lines.length > visible && <button type="button" ref={openerRef} data-log-target="cart-sheet-open" className="cart-all" onClick={onOpenAll}>모두 보기</button>}
    </div>
    <ul className="cart-lines">
      {lines.length ? lines.slice(0, visible).map(line => <CartLine key={`${line.item.item_id}:${line.removed}`} line={line} actions={actions} />)
        : <li className="cart-empty">메뉴를 담아 주세요</li>}
    </ul>
  </section>;
}
