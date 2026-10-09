import type {
  ConnectivityResponse,
  FeatureWindowRequest,
  FeatureWindowResponse,
  HealthResponse,
  SessionCreateResponse,
  Cart,
  CartItemCreateRequest,
  CartItemQuantityUpdateRequest,
  Order,
  OrderCreateRequest,
  ProductList,
} from './types.ts';

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  readonly retryAfterSeconds: number | null;

  constructor(status: number, body: unknown, retryAfterSeconds: number | null = null) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body
      ? body.detail
      : undefined;
    super(typeof detail === 'string' ? detail : `API 요청 실패 (${status})`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** backend 주소를 실행 환경에서 전달합니다. AI 서버를 직접 호출하지 않습니다. */
export function createBackendApi(baseUrl: string, fetcher: typeof fetch = fetch) {
  const base = baseUrl.replace(/\/+$/, '');

  async function request<T>(path: string, init: RequestInit): Promise<T> {
    const response = await fetcher(`${base}${path}`, init);
    const text = await response.text();
    let body: unknown;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      if (!response.ok) throw new ApiError(response.status, text);
      throw new Error('서버가 올바른 JSON 응답을 반환하지 않았습니다.');
    }
    if (!response.ok) {
      const header = response.headers.get('Retry-After');
      const seconds = header === null ? NaN : Number(header);
      throw new ApiError(response.status, body, Number.isFinite(seconds) && seconds >= 0 ? seconds : null);
    }
    return body as T;
  }

  function orderRequest<T>(path: string, init: RequestInit): Promise<T> {
    const timeout = AbortSignal.timeout(15_000);
    return request(path, {
      ...init, credentials: 'same-origin',
      signal: init.signal ? AbortSignal.any([init.signal, timeout]) : timeout,
    });
  }

  function sessionPath(sessionId: string): string {
    if (!sessionId.trim()) throw new Error('세션 ID가 필요합니다.');
    return `/api/v1/sessions/${encodeURIComponent(sessionId)}`;
  }

  function mutation<T>(path: string, method: string, body: unknown, key: string, signal?: AbortSignal): Promise<T> {
    if (!key.trim()) throw new Error('중복 방지 키가 필요합니다.');
    return orderRequest(path, {
      method, signal,
      headers: body === undefined ? { 'Idempotency-Key': key }
        : { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  return {
    getBackendHealth(signal?: AbortSignal): Promise<HealthResponse> {
      return request('/health', { method: 'GET', signal });
    },
    getConnectivity(signal?: AbortSignal): Promise<ConnectivityResponse> {
      return request('/api/v1/connectivity', { method: 'GET', signal });
    },
    createSession(signal?: AbortSignal): Promise<SessionCreateResponse> {
      return orderRequest('/api/v1/sessions', { method: 'POST', signal });
    },
    getProducts(signal?: AbortSignal): Promise<ProductList> {
      return orderRequest('/api/v1/products', { method: 'GET', signal });
    },
    getCart(sessionId: string, signal?: AbortSignal): Promise<Cart> {
      return orderRequest(`${sessionPath(sessionId)}/cart`, { method: 'GET', signal });
    },
    addCartItem(sessionId: string, body: CartItemCreateRequest, key: string, signal?: AbortSignal): Promise<Cart> {
      return mutation(`${sessionPath(sessionId)}/cart/items`, 'POST', body, key, signal);
    },
    updateCartItem(sessionId: string, itemId: string, body: CartItemQuantityUpdateRequest, key: string, signal?: AbortSignal): Promise<Cart> {
      return mutation(`${sessionPath(sessionId)}/cart/items/${encodeURIComponent(itemId)}`, 'PATCH', body, key, signal);
    },
    deleteCartItem(sessionId: string, itemId: string, version: number, key: string, signal?: AbortSignal): Promise<Cart> {
      return mutation(`${sessionPath(sessionId)}/cart/items/${encodeURIComponent(itemId)}?expected_version=${version}`, 'DELETE', undefined, key, signal);
    },
    createOrder(sessionId: string, body: OrderCreateRequest, key: string, signal?: AbortSignal): Promise<Order> {
      return mutation(`${sessionPath(sessionId)}/orders`, 'POST', body, key, signal);
    },
    sendFeatureWindow(
      sessionId: string,
      features: FeatureWindowRequest,
      signal?: AbortSignal,
    ): Promise<FeatureWindowResponse> {
      if (!sessionId.trim()) throw new Error('세션 ID가 필요합니다.');
      return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/features`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(features),
        signal,
      });
    },
  };
}
