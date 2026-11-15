import type { FeatureWindowResponse, UIPreset } from '../../../shared/api/index.ts';
import type { Settings } from '../model.ts';

// 서버의 화면 지원 판단(FeatureWindowResponse.support)을 화면이 할 일로 바꿉니다. 계약에 있는 필드
// (ai_available, support.preset, support.requires_confirmation, session_id)만 읽고 새 필드를 만들지 않습니다.
// 호출자 규칙(frontend README): ai_available이 false이거나 preset이 none이면 화면을 유지하고, requires_confirmation이
// true이면 사용자가 받아들인 뒤 적용하며, 세션이나 화면이 바뀐 뒤 도착한 응답은 적용하지 않습니다.

/**
 * 키오스크가 제안·적용하는 지원입니다. 지금은 크게 보기 하나: 글자를 39 / 47 / 67 px로, 조작을 큰 버튼 높이로 키운 한 단계입니다.
 * 화면 도움의 큰 글씨(200 %)·큰 버튼 설정과는 따로이며, 그 설정을 바꾸지 않습니다.
 */
export type SupportKind = 'enlarge';
export type SupportIgnoreReason = 'ai_unavailable' | 'none' | 'stale_session' | 'stale_screen' | 'order_done' | 'already_on' | 'no_copy';
export type SupportAction =
  | { kind: 'ignore'; reason: SupportIgnoreReason }
  | { kind: 'offer' | 'apply'; preset: UIPreset; support: SupportKind };

/**
 * 서버 프리셋을 지원으로 읽습니다. large_text와 large_button은 모두 크게 보기입니다.
 * 화면 문구가 정해진 프리셋만 바꾸고 simple_screen·step_guide·voice_guide는 문구가 없어 무시합니다.
 */
const supportOf: Partial<Record<UIPreset, SupportKind>> = { large_text: 'enlarge', large_button: 'enlarge' };

/** 크게 보기가 이미 켜져 있거나 고객이 큰 글씨(200 %)를 켰으면 더 키울 것이 없습니다. */
export function alreadyLarge(now: { largeView: boolean; settings: Settings }): boolean {
  return now.largeView || now.settings.largeText;
}

export function readSupportDecision(
  response: FeatureWindowResponse,
  sentFor: { sessionId: string; screen: string },
  now: { sessionId: string | null; screen: string; orderDone: boolean; settings: Settings; largeView: boolean },
): SupportAction {
  if (!response.ai_available) return { kind: 'ignore', reason: 'ai_unavailable' };
  const preset = response.support.preset;
  if (preset === 'none') return { kind: 'ignore', reason: 'none' };
  if (response.session_id !== sentFor.sessionId || now.sessionId !== sentFor.sessionId) return { kind: 'ignore', reason: 'stale_session' };
  if (now.screen !== sentFor.screen) return { kind: 'ignore', reason: 'stale_screen' };
  if (now.orderDone) return { kind: 'ignore', reason: 'order_done' };
  const support = supportOf[preset];
  if (!support) return { kind: 'ignore', reason: 'no_copy' };
  if (alreadyLarge(now)) return { kind: 'ignore', reason: 'already_on' };
  return { kind: response.support.requires_confirmation ? 'offer' : 'apply', preset, support };
}
