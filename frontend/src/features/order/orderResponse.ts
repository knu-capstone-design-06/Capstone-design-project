import type { CartItem, Order } from '../../shared/api/types.ts';
import { MAX_QUANTITY } from './model.ts';

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null;
const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0;
const integer = (value: unknown, minimum: number): value is number => typeof value === 'number' && Number.isInteger(value) && value >= minimum;

function item(value: unknown): value is CartItem {
  return object(value) && text(value.item_id) && text(value.product_id) && text(value.name)
    && ['iced', 'hot', null].includes(value.temperature as 'iced' | 'hot' | null)
    && integer(value.quantity, 1) && value.quantity <= MAX_QUANTITY
    && integer(value.unit_price, 0) && integer(value.line_amount, 0)
    && value.line_amount === value.unit_price * value.quantity;
}

/** Validate the draft Order schema before clearing the confirmed cart. */
export function readOrderResponse(value: unknown): Order {
  if (!object(value) || !text(value.order_id) || !text(value.order_number) || !text(value.session_id)
    || value.status !== 'simulated' || value.currency !== 'KRW'
    || !Array.isArray(value.items) || value.items.length === 0 || !value.items.every(item)
    || !integer(value.total_quantity, 1) || !integer(value.total_amount, 0)
    || value.total_quantity !== value.items.reduce((sum, row) => sum + row.quantity, 0)
    || value.total_amount !== value.items.reduce((sum, row) => sum + row.line_amount, 0)
    || typeof value.created_at !== 'string'
    || !/^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$/.test(value.created_at)
    || !Number.isFinite(Date.parse(value.created_at))) {
    throw new Error('주문 응답 형식 불일치');
  }
  return value as unknown as Order;
}
