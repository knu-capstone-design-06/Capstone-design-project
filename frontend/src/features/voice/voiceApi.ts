import { ApiError } from '../../shared/api/index.ts';
import type { Temperature } from '../../shared/api/index.ts';
import type { RecognitionAlternative } from './speech.ts';

// contract/voice.openapi.yaml 0.3.0 형식입니다.
export type VoiceRequestCreate = { text: string; alternatives: RecognitionAlternative[]; screen_id: string };
export type VoiceRequestAccepted = { request_id: string; status: 'accepted'; accepted_at: string };
export type VoiceStatus =
  | 'accepted' | 'processing' | 'completed' | 'needs_confirmation' | 'needs_clarification' | 'ignored' | 'failed';
type CartItemTarget = { product_id: string; temperature: Temperature | null };
/** MCP 장바구니 도구의 입력입니다. 이 기능은 실행하지 않고 부르는 쪽에 넘깁니다. */
export type VoiceToolCall =
  | { tool: 'add_cart_item'; arguments: CartItemTarget & { quantity: number } }
  | { tool: 'update_cart_item'; arguments: CartItemTarget & { quantity: number } }
  | { tool: 'remove_cart_item'; arguments: CartItemTarget };
export type VoiceRequestStatus = {
  request_id: string;
  status: VoiceStatus;
  reply_text: string | null;
  tool_calls: VoiceToolCall[];
  actions: string[];
  error: { code: string; detail: string } | null;
};

const VOICE_REQUEST_TIMEOUT_MS = 10_000;

/** backend의 음성 요청 API만 호출합니다. 기본 주소는 같은 출처 프록시(/backend)입니다. */
export function createVoiceApi(baseUrl = '/backend', fetcher: typeof fetch = fetch) {
  const base = baseUrl.replace(/\/+$/, '');

  function path(sessionId: string, requestId?: string): string {
    if (!sessionId.trim()) throw new Error('세션 ID가 필요합니다.');
    const root = `/api/v1/sessions/${encodeURIComponent(sessionId)}/voice/requests`;
    return requestId === undefined ? root : `${root}/${encodeURIComponent(requestId)}`;
  }

  async function request<T>(url: string, init: RequestInit): Promise<T> {
    const timeout = AbortSignal.timeout(VOICE_REQUEST_TIMEOUT_MS);
    const response = await fetcher(`${base}${url}`, {
      ...init, credentials: 'same-origin',
      signal: init.signal ? AbortSignal.any([init.signal, timeout]) : timeout,
    });
    const text = await response.text();
    let body: unknown = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      if (response.ok) throw new Error('서버가 올바른 JSON 응답을 반환하지 않았습니다.');
      body = text;
    }
    if (!response.ok) throw new ApiError(response.status, body);
    return body as T;
  }

  return {
    /** 발화 하나에 키 하나. 응답을 못 받았을 때만 같은 키로 다시 보냅니다. */
    submit(sessionId: string, body: VoiceRequestCreate, key: string, signal?: AbortSignal): Promise<VoiceRequestAccepted> {
      if (!key.trim()) throw new Error('중복 방지 키가 필요합니다.');
      return request(path(sessionId), {
        method: 'POST', signal, body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      });
    },
    get(sessionId: string, requestId: string, signal?: AbortSignal): Promise<VoiceRequestStatus> {
      return request(path(sessionId, requestId), { method: 'GET', signal });
    },
  };
}

export type VoiceApi = ReturnType<typeof createVoiceApi>;
