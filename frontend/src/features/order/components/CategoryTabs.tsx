import type { ProductCategory } from '../../../shared/api/index.ts';
import { categoryLabels } from '../model.ts';
import { Icon } from './icons.tsx';
import type { IconName } from './icons.tsx';
import './topCluster.css';

export type CategoryFilter = ProductCategory | 'all';
const categories: [CategoryFilter, IconName][] = [['all', 'grid_view'], ['coffee', 'local_cafe'], ['drink', 'local_drink'], ['food', 'bakery_dining']];

/** 분류 탭 네 개입니다. 고른 탭은 녹색 바탕에 확인 표시, 나머지는 분류 아이콘을 붙입니다. 대상 이름은 기존 `category:<이름>`입니다. */
export function CategoryTabs({ category, onChange }: { category: CategoryFilter; onChange: (category: CategoryFilter) => void }) {
  return <div className="categories" aria-label="상품 분류">
    {categories.map(([value, icon]) => {
      const label = value === 'all' ? '전체' : categoryLabels[value];
      const selected = category === value;
      return <button type="button" data-log-target={`category:${label}`} key={value} className="tab" aria-pressed={selected} onClick={() => onChange(value)}>
        <Icon name={selected ? 'check' : icon} />{label}
      </button>;
    })}
  </div>;
}
