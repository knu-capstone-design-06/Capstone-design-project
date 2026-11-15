import type { CartItem } from '../../../shared/api/index.ts';
import { money, orderNumberText, temperatureText } from '../model.ts';
import { Icon } from './icons.tsx';
import './orderBlocks.css';

/** 주문 완료: 확인 표시와 "주문이 끝났어요"(L 굵게) 한 줄, "주문번호"(S)와 번호(96 px), 주문한 메뉴와 총 금액. 남은 자리의 가운데에 섭니다. */
export function DoneBlock({ orderNumber, items, total }: { orderNumber: string; items: CartItem[]; total: number }) {
  return <section className="done-block" aria-label="주문 완료">
    <p className="done-head"><Icon name="check_circle" className="pic done-pic" /><span className="done-title">주문이 끝났어요</span></p>
    <p className="done-label">주문번호</p>
    <strong className="order-number" data-order-number={orderNumber}>{orderNumberText(orderNumber)}</strong>
    <ul className="sum-list" aria-label="주문한 메뉴">
      {items.map(item => {
        const option = temperatureText(item.temperature);
        return <li key={item.item_id} className="sum-row">
          <span className="item"><strong className="name">{item.name}</strong>{option && <span className="opt">{option}</span>}</span>
          <span className="cnt">{item.quantity}개</span>
          <span className="line-price">{money(item.line_amount)}</span>
        </li>;
      })}
      <li className="sum-row total-row"><span className="total-label">총 주문 금액</span><strong className="amount">{money(total)}</strong></li>
    </ul>
  </section>;
}
