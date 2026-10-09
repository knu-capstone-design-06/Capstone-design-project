import { ApiError } from '../../shared/api/index.ts';
import type { createBackendApi, Cart, CartItemCreateRequest, Order, OrderApiError, Product, SessionCreateResponse } from '../../shared/api/index.ts';

type Api = ReturnType<typeof createBackendApi>;
export type OrderSnapshot = {
  products: Product[];
  session: SessionCreateResponse | null;
  cart: Cart | null;
  order: Order | null;
  status: 'idle' | 'loading' | 'ready' | 'saving' | 'uncertain' | 'disconnected' | 'ended';
  message: string;
  notice: string;
  retryAt: number;
};
type Pending = { sessionId: string; kind: 'cart' | 'order'; notice: string; run: () => Promise<Cart | Order> };

/** Keeps one confirmed server snapshot and one exact request for a manual retry. */
export class OrderController {
  private api: Api;
  private state: OrderSnapshot = { products: [], session: null, cart: null, order: null, status: 'idle', message: '', notice: '', retryAt: 0 };
  private listeners = new Set<() => void>();
  private initializing: Promise<boolean> | null = null;
  private pending: Pending | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(api: Api) { this.api = api; }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private set(patch: Partial<OrderSnapshot>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach(listener => listener());
  }

  initialize(): Promise<boolean> {
    if (this.initializing) return this.initializing;
    if (this.state.session) return Promise.resolve(true);
    this.initializing = this.connect().finally(() => { this.initializing = null; });
    return this.initializing;
  }

  private async connect(): Promise<boolean> {
    this.set({ status: 'loading', session: null, cart: null, order: null, message: '', notice: '', retryAt: 0 });
    let stage: 'products' | 'session' | 'cart' = 'products';
    try {
      const products = await this.api.getProducts();
      stage = 'session';
      const session = await this.api.createSession();
      stage = 'cart';
      const cart = await this.api.getCart(session.session_id);
      if (cart.session_id !== session.session_id) throw new Error('세션 응답 불일치');
      this.set({ products: products.products, session, cart, status: 'ready' });
      return true;
    } catch (error) {
      const unavailable = error instanceof ApiError && error.status === 404 && stage !== 'session';
      this.set({ status: 'disconnected', message: unavailable
        ? '주문 서비스 연결이 아직 준비되지 않았습니다. 잠시 후 다시 연결해 주세요.'
        : '주문을 시작하지 못했습니다. 연결을 확인하고 다시 시도해 주세요.' });
      return false;
    }
  }

  startNewOrder(): Promise<boolean> {
    if (this.pending || this.state.status === 'saving') return Promise.resolve(false);
    if (!this.state.order && this.state.status !== 'ended' && this.state.status !== 'disconnected') return Promise.resolve(false);
    this.set({ session: null });
    return this.initialize();
  }

  addItem(input: Omit<CartItemCreateRequest, 'expected_version'>): Promise<boolean> {
    const payload = { ...input };
    return this.write('cart', (session, cart, key) => this.api.addCartItem(session, { ...payload, expected_version: cart.version }, key), '메뉴를 담았습니다.');
  }
  updateQuantity(itemId: string, quantity: number): Promise<boolean> {
    return this.write('cart', (session, cart, key) => this.api.updateCartItem(session, itemId, { quantity, expected_version: cart.version }, key), '수량을 변경했습니다.');
  }
  removeItem(itemId: string): Promise<boolean> {
    return this.write('cart', (session, cart, key) => this.api.deleteCartItem(session, itemId, cart.version, key), '메뉴를 삭제했습니다.');
  }
  checkout(): Promise<boolean> {
    if (!this.state.cart?.items.length) return Promise.resolve(false);
    return this.write('order', (session, cart, key) => this.api.createOrder(session, { expected_version: cart.version }, key), '');
  }

  private write(kind: Pending['kind'], run: (session: string, cart: Cart, key: string) => Promise<Cart | Order>, notice: string): Promise<boolean> {
    const { session, cart, status, order } = this.state;
    if (!session || !cart || order || status !== 'ready' || this.pending) return Promise.resolve(false);
    const key = crypto.randomUUID();
    const confirmed = structuredClone(cart);
    this.pending = { sessionId: session.session_id, kind, notice, run: () => run(session.session_id, confirmed, key) };
    return this.execute(this.pending);
  }

  retry(): Promise<boolean> {
    if (!this.pending || this.state.status !== 'uncertain' || Date.now() < this.state.retryAt) return Promise.resolve(false);
    return this.execute(this.pending);
  }

  clearNotice() { this.set({ notice: '' }); }

  private acceptCart(cart: Cart | null): Cart | null {
    if (!cart || cart.session_id !== this.state.session?.session_id) return this.state.cart;
    return !this.state.cart || cart.version >= this.state.cart.version ? cart : this.state.cart;
  }

  private async execute(pending: Pending): Promise<boolean> {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.set({ status: 'saving', message: '', retryAt: 0 });
    try {
      const result = await pending.run();
      if (this.state.session?.session_id !== pending.sessionId) return false;
      if (result.session_id !== pending.sessionId) throw new Error('세션 응답 불일치');
      this.pending = null;
      this.set(pending.kind === 'order'
        ? { order: result as Order, cart: null, status: 'ready', notice: '' }
        : { cart: this.acceptCart(result as Cart), status: 'ready', notice: pending.notice });
      return true;
    } catch (error) {
      if (this.state.session?.session_id !== pending.sessionId) return false;
      const apiError = error instanceof ApiError ? error : null;
      const body = apiError && typeof apiError.body === 'object' && apiError.body !== null
        ? apiError.body as Partial<OrderApiError> : null;
      const uncertain = !apiError || apiError.status >= 500 || apiError.status === 429
        || (apiError.status === 409 && apiError.retryAfterSeconds !== null);
      if (uncertain) {
        const seconds = apiError?.retryAfterSeconds ?? 0;
        const retryAt = Date.now() + seconds * 1000;
        this.set({ status: 'uncertain', retryAt, message: '요청 결과를 아직 확인하지 못했습니다. 잠시 후 결과를 다시 확인해 주세요.' });
        if (seconds > 0) this.retryTimer = setTimeout(() => {
          if (this.pending === pending && this.state.status === 'uncertain') this.set({ retryAt: 0 });
        }, seconds * 1000);
      } else if (apiError) {
        this.pending = null;
        const ended = apiError.status === 401 || apiError.status === 403 || ['session_not_found', 'session_expired'].includes(body?.code ?? '');
        this.set({ status: ended ? 'ended' : 'ready', cart: this.acceptCart(body?.cart ?? null),
          message: apiError.message, retryAt: 0 });
      }
      return false;
    }
  }
}
