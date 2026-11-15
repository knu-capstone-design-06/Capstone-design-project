import type { ReactNode, Ref } from 'react';
import type { Product, Temperature } from '../../../shared/api/index.ts';
import { MAX_QUANTITY, money, temperatureLabel, temperatureText } from '../model.ts';
import { Icon } from './icons.tsx';
import { ProductTile } from './ProductTile.tsx';
import { Sheet } from './Sheet.tsx';

/**
 * 옵션 시트: 그림, 이름, 설명(또는 이 시트의 처리 중·오류 안내), 온도, 수량, [취소] [금액 담기]. 금액은 [담기] 버튼에만 둡니다.
 * [취소]와 [담기]는 하단 주문 바의 [처음으로]·주요 버튼과 같은 자리에 섭니다. 대상 이름은 기존과 같습니다.
 */
export function OptionSheet({ ref, product, temperature, quantity, remaining, writeDisabled, status, hint = null, onTemperature, onQuantity, onAdd, onClose }: {
  ref: Ref<HTMLDialogElement>; product: Product | null; temperature: Temperature; quantity: number; remaining: number;
  writeDisabled: boolean; status: ReactNode | null; hint?: string | null;
  onTemperature: (temperature: Temperature) => void; onQuantity: (quantity: number) => void; onAdd: () => void; onClose: () => void;
}) {
  return <Sheet ref={ref} className="option-sheet" labelledBy="option-title" onClose={onClose}>
    {product && <>
      <div className="sheet-head">
        <ProductTile product={product} />
        <div className="sheet-head-text">
          <h2 id="option-title" className="sheet-name">{product.name}</h2>
          <div className="sheet-support">{status ?? <p className="sheet-desc">{product.description}</p>}</div>
        </div>
      </div>
      {product.temperatures.length > 0 && <fieldset className="field">
        <legend className="field-label">온도</legend>
        <div className="cols">{product.temperatures.map(option => <button type="button" data-log-target={`temperature:${temperatureLabel(option)}`} key={option}
          aria-pressed={temperature === option} disabled={writeDisabled} onClick={() => onTemperature(option)}>
          {temperature === option && <Icon name="check" />}{temperatureText(option)}
        </button>)}</div>
      </fieldset>}
      <div className="qty-row">
        <span className="field-label">수량<span className="field-note">(최대 {MAX_QUANTITY}개)</span></span>
        <div className="quantity stepper">
          <button type="button" data-log-target="options-decrease" disabled={writeDisabled || quantity === 1} aria-label="선택 수량 줄이기" onClick={() => onQuantity(quantity - 1)}><Icon name="remove" /></button>
          <span>{quantity}</span>
          <button type="button" data-log-target="options-increase" disabled={writeDisabled || quantity >= remaining} aria-label="선택 수량 늘리기" onClick={() => onQuantity(quantity + 1)}><Icon name="add" /></button>
        </div>
      </div>
      {remaining <= 0 && <p className="sheet-note" role="status">이 메뉴와 온도는 이미 최대 수량을 담았어요.</p>}
      <div className="sheet-bar">
        {hint && <p className="hint-callout" role="status"><Icon name="pan_tool_alt" />{hint}</p>}
        <button type="button" data-log-target="options-close" className="sheet-cancel" onClick={onClose}>취소</button>
        <button type="button" data-log-target="cart-add" className="primary sheet-main" disabled={writeDisabled || quantity > remaining} onClick={onAdd}>{money(product.unit_price * quantity)} 담기</button>
      </div>
    </>}
  </Sheet>;
}
