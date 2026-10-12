import type { CartItem, Order } from '../../shared/api/types.ts';
import { MAX_QUANTITY } from './model.ts';

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0;
const integer = (value: unknown, minimum: number): value is number => typeof value === 'number' && Number.isInteger(value) && value >= minimum;

/** Field paths only; never retain or print the server response or its values. */
export class OrderResponseError extends Error {
  readonly fields: readonly string[];
  constructor(fields: string[]) {
    super('주문 응답 형식 불일치');
    this.name = 'OrderResponseError';
    this.fields = Object.freeze([...fields]);
  }
}

/** Validate the draft Order schema before clearing the confirmed cart. */
export function readOrderResponse(value: unknown): Order {
  if (!object(value)) throw new OrderResponseError(['$']);
  const invalid = new Set<string>();
  const check = (field: string, valid: boolean) => { if (!valid) invalid.add(field); };
  for (const field of ['order_id', 'order_number', 'session_id']) check(field, text(value[field]));
  check('status', value.status === 'simulated');
  check('currency', value.currency === 'KRW');
  check('total_quantity', integer(value.total_quantity, 1));
  check('total_amount', integer(value.total_amount, 0));
  check('created_at', typeof value.created_at === 'string'
    && /^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$/.test(value.created_at)
    && Number.isFinite(Date.parse(value.created_at)));
  check('items', Array.isArray(value.items) && value.items.length > 0);
  if (Array.isArray(value.items)) {
    const before = invalid.size;
    value.items.forEach((row: unknown, index: number) => {
      const path = `items[${index}]`;
      if (!object(row)) { invalid.add(path); return; }
      for (const field of ['item_id', 'product_id', 'name']) check(`${path}.${field}`, text(row[field]));
      check(`${path}.temperature`, ['iced', 'hot', null].includes(row.temperature as 'iced' | 'hot' | null));
      check(`${path}.quantity`, integer(row.quantity, 1) && row.quantity <= MAX_QUANTITY);
      check(`${path}.unit_price`, integer(row.unit_price, 0));
      check(`${path}.line_amount`, integer(row.line_amount, 0)
        && integer(row.quantity, 1) && integer(row.unit_price, 0) && row.line_amount === row.quantity * row.unit_price);
    });
    if (invalid.size === before) {
      const items = value.items as CartItem[];
      check('total_quantity', value.total_quantity === items.reduce((sum, row) => sum + row.quantity, 0));
      check('total_amount', value.total_amount === items.reduce((sum, row) => sum + row.line_amount, 0));
    }
  }
  if (invalid.size) throw new OrderResponseError([...invalid]);
  return value as unknown as Order;
}
