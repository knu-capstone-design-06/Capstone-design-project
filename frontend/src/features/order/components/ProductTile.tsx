import type { Product, ProductCategory } from '../../../shared/api/index.ts';
import { productPicture } from '../utils/productPictures.ts';
import { Icon } from './icons.tsx';
import type { IconName } from './icons.tsx';
import './productGrid.css';

const categoryIcon: Record<ProductCategory, IconName> = { coffee: 'local_cafe', drink: 'local_drink', food: 'bakery_dining' };

/** 상품 그림 타일입니다. 그림이 없는 상품은 분류 아이콘을 같은 밝은 타일에 둡니다(분류를 모르면 빈 타일). 품절이면 타일에 '품절'을 씁니다. */
export function ProductTile({ product, className = 'tile' }: { product: Pick<Product, 'product_id' | 'available'> & { category: ProductCategory | null }; className?: string }) {
  const picture = productPicture(product.product_id);
  return <span className={`${className}${picture ? '' : ' is-pictogram'}`}>
    {picture ? <img src={picture} alt="" /> : product.category && <Icon name={categoryIcon[product.category]} className="tile-pic" />}
    {!product.available && <span className="soldout">품절</span>}
  </span>;
}
