import type { Product } from '../../../shared/api/index.ts';
import { pageItems } from '../utils/paging.ts';
import { CartLine } from './CartLine.tsx';
import type { CartDisplayLine, CartLineActions } from './CartLine.tsx';
import { Pager } from './Pager.tsx';
import { ProductTile } from './ProductTile.tsx';
import './orderBlocks.css';

/**
 * 주문 확인의 주문 묶음: 제목 줄 "담은 메뉴 N개"와 [메뉴 더 고르기], 사진이 붙은 줄, 쪽 넘김.
 * 묶음은 하단 주문 바 바로 위, 장바구니가 있던 자리에 섭니다.
 */
export function ReviewBlock({ lines, count, products, page, pages, size, actions, onBack, onPage }: {
  lines: CartDisplayLine[]; count: number; products: Product[]; page: number; pages: number; size: number;
  actions: CartLineActions; onBack: () => void; onPage: (page: number) => void;
}) {
  return <section className="review-block" aria-label="주문 내역">
    <p className="simulation-note">모의 주문 · 실제 결제나 매장 주문은 진행되지 않아요.</p>
    <div className="cart-head">
      <h2 className="cart-title">담은 메뉴 {count}개</h2>
      <button type="button" data-log-target="review-back" className="review-back" onClick={onBack}>메뉴 더 고르기</button>
    </div>
    {lines.length ? <ul className="cart-lines review-lines">
      {pageItems(lines, page, size).map(line => {
        const product = products.find(row => row.product_id === line.item.product_id);
        return <CartLine key={`${line.item.item_id}:${line.removed}`} line={line} actions={actions}
          thumbnail={<ProductTile product={{ product_id: line.item.product_id, category: product?.category ?? null, available: true }} className="tile thumb" />} />;
      })}
    </ul> : <p className="review-empty">아직 담은 메뉴가 없어요. 메뉴를 먼저 골라 주세요.</p>}
    {pages > 1 && <Pager page={page} pages={pages} target="review-page" onChange={onPage} />}
  </section>;
}
