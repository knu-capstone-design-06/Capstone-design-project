import type {
  ConnectivityResponse,
  FeatureWindowRequest,
  FeatureWindowResponse,
  HealthResponse,
  SessionCreateResponse,
} from './types.ts';

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body
      ? body.detail
      : undefined;
    super(typeof detail === 'string' ? detail : `API 요청 실패 (${status})`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
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
    if (!response.ok) throw new ApiError(response.status, body);
    return body as T;
  }

  return {
    getBackendHealth(signal?: AbortSignal): Promise<HealthResponse> {
      return request('/health', { method: 'GET', signal });
    },
    getConnectivity(signal?: AbortSignal): Promise<ConnectivityResponse> {
      return request('/api/v1/connectivity', { method: 'GET', signal });
    },
    createSession(signal?: AbortSignal): Promise<SessionCreateResponse> {
      return request('/api/v1/sessions', { method: 'POST', signal });
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
