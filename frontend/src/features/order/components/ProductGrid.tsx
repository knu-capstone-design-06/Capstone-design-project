import type { CSSProperties, ReactNode } from 'react';
import type { Product } from '../../../shared/api/index.ts';
import { money } from '../model.ts';
import { Pager } from './Pager.tsx';
import { ProductTile } from './ProductTile.tsx';
import './productGrid.css';

/**
 * 한 쪽의 상품입니다. 사진 카드(타일, 이름 M 굵게, 가격 M)가 세 열(큰 글씨는 두 열)로 서고, 간편 화면은 글자 줄(큰 글씨를 더하면 줄 왼쪽에 작은 사진)입니다.
 * 사진 카드는 탭 줄과 쪽 넘김 줄 사이를 rows 줄로 나눠 채웁니다(글자 칸은 그대로, 사진 칸이 나머지). 쪽마다 줄 수가 같아
 * 마지막 쪽에서도 카드 크기가 바뀌지 않습니다. popup은 목록 위에 뜨는 안내 영역로, 아래 끝이 쪽 넘김 줄 18 px 위입니다.
 * armed가 false인 동안(제안 카드의 [크게 하기]를 누른 뒤 두 번 클릭 간격) 상품은 누름을 받지 않습니다(비활성은 아님, data-armed).
 */
export function ProductGrid({ products, page, pages, rows, disabled, asRows, popup = null, armed = true, onSelect, onPage }: {
  products: Product[]; page: number; pages: number; rows: number; disabled: boolean; asRows: boolean; popup?: ReactNode; armed?: boolean;
  onSelect: (product: Product, button: HTMLButtonElement) => void; onPage: (page: number) => void;
}) {
  return <>
    <div className="grid-area">
      <div className={`product-grid${asRows ? ' as-rows' : ''}${pages > 1 ? ' is-paged' : ''}`} style={{ '--rows': rows } as CSSProperties}>
        {products.map(product => <button type="button" data-log-target={`product:${product.product_id}`} className={asRows ? 'product product-row' : 'product'} key={product.product_id}
          data-armed={armed} disabled={disabled || !product.available} onClick={event => { if (armed) onSelect(product, event.currentTarget); }}>
          <ProductTile product={product} className={asRows ? 'tile row-thumb' : 'tile'} />
          <span className="product-info"><strong>{product.name}</strong><span className="product-price">{money(product.unit_price)}</span>
            {asRows && !product.available && <span className="row-soldout">품절</span>}</span>
        </button>)}
      </div>
      {popup && <div className="popup-place">{popup}</div>}
    </div>
    {pages > 1 && <Pager page={page} pages={pages} target="menu-page" onChange={onPage} />}
  </>;
}
