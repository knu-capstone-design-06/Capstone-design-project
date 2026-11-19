import type { FeatureWindowResponse } from '../../shared/api/types.ts';
import type { Settings } from './model.ts';

export const supportSettings = {
  large_text: { key: 'largeText', question: '글씨를 크게 바꿀까요?', description: '메뉴와 안내 글씨를 크게 보여 드려요.' },
  large_button: { key: 'largeButton', question: '버튼을 크게 바꿀까요?', description: '누르는 버튼을 크게 보여 드려요.' },
  simple_screen: { key: 'simpleScreen', question: '간편한 화면으로 바꿀까요?', description: '메뉴를 간단한 목록으로 보여 드려요.' },
  step_guide: { key: 'stepGuide', question: '주문 순서를 안내해 드릴까요?', description: '현재 단계에서 할 일을 화면에 보여 드려요.' },
} as const;
export type SupportPreset = keyof typeof supportSettings;
/** 지원 여부만 읽습니다. 서버 문구나 알 수 없는 프리셋을 화면에 실행하지 않습니다. */
export function readBackendSupport(response: unknown, sessionId: string, settings: Settings): SupportPreset | null {
  if (!response || typeof response !== 'object') return null;
  const value = response as Partial<FeatureWindowResponse>;
  if (value.session_id !== sessionId || value.ai_available !== true || !value.support) return null;
  const support = value.support;
  if (typeof support.requires_confirmation !== 'boolean' || !['rule_placeholder', 'jev'].includes(support.decided_by)
    || !Object.hasOwn(supportSettings, support.preset)) return null;
  const preset = support.preset as SupportPreset;
  return settings[supportSettings[preset].key] ? null : preset;
}
