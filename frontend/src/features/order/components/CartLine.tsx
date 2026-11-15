import type { ReactNode } from 'react';
import type { CartItem } from '../../../shared/api/index.ts';
import { MAX_QUANTITY, money, temperatureLabel, temperatureText } from '../model.ts';
import { Icon } from './icons.tsx';
import './cart.css';

export type CartDisplayLine = { item: CartItem; removed: boolean };
export type CartLineActions = {
  disabled: boolean;
  onQuantity: (item: CartItem, quantity: number) => void;
  onRemove: (item: CartItem) => void;
  onUndo: () => void;
};

/**
 * 담은 메뉴 한 줄: 이름(M 굵게)과 옵션(S), − n +, 줄 금액, [삭제]. 뺀 줄은 다음 터치까지 제자리에 흐리게 남고
 * [삭제] 자리에 [되돌리기]가 섭니다. 뺀 줄은 `.cart-row`로 세지 않습니다.
 */
export function CartLine({ line, actions, thumbnail = null }: { line: CartDisplayLine; actions: CartLineActions; thumbnail?: ReactNode }) {
  const { item, removed } = line;
  const target = `cart:${item.product_id}:${temperatureLabel(item.temperature)}`;
  const option = temperatureText(item.temperature);
  const name = option ? `${item.name} ${option}` : item.name;
  return <li className={removed ? 'cart-line cart-removed' : 'cart-line cart-row'}>
    {thumbnail}
    <span className="item"><strong className="name">{item.name}</strong>{option && <span className="opt">{option}</span>}</span>
    <div className="quantity stepper">
      <button type="button" data-log-target={removed ? undefined : `${target}:decrease`} aria-label={`${name} 수량 줄이기`}
        disabled={removed || actions.disabled || item.quantity === 1} onClick={() => actions.onQuantity(item, item.quantity - 1)}><Icon name="remove" /></button>
      <span>{item.quantity}</span>
      <button type="button" data-log-target={removed ? undefined : `${target}:increase`} aria-label={`${name} 수량 늘리기`}
        disabled={removed || actions.disabled || item.quantity === MAX_QUANTITY} onClick={() => actions.onQuantity(item, item.quantity + 1)}><Icon name="add" /></button>
    </div>
    <span className="line-price">{money(item.line_amount)}</span>
    {removed
      ? <button type="button" data-log-target={`${target}:undo`} className="line-action" aria-label={`${name} 되돌리기`} disabled={actions.disabled} onClick={actions.onUndo}>되돌리기</button>
      : <button type="button" data-log-target={`${target}:remove`} className="line-action" aria-label={`${name} 삭제`} disabled={actions.disabled} onClick={() => actions.onRemove(item)}>삭제</button>}
  </li>;
}
