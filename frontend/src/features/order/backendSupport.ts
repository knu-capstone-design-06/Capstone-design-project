import { ApiError } from '../../shared/api/client.ts';
import type { FeatureWindowRequest, FeatureWindowResponse, TouchFeatures } from '../../shared/api/types.ts';
import type { Settings } from './model.ts';
import type { SavedLog } from './touchLog.ts';
import { measureTouchPilot } from './touchLogFeatures.ts';

export const supportSettings = {
  large_text: { key: 'largeText', question: '글씨를 크게 바꿀까요?', description: '메뉴와 안내 글씨를 크게 보여 드려요.' },
  large_button: { key: 'largeButton', question: '버튼을 크게 바꿀까요?', description: '누르는 버튼을 크게 보여 드려요.' },
  simple_screen: { key: 'simpleScreen', question: '간편한 화면으로 바꿀까요?', description: '메뉴를 간단한 목록으로 보여 드려요.' },
  step_guide: { key: 'stepGuide', question: '주문 순서를 안내해 드릴까요?', description: '현재 단계에서 할 일을 화면에 보여 드려요.' },
} as const;
export type SupportPreset = keyof typeof supportSettings;
const currentVisit = (saved: SavedLog) => [...saved.events].reverse().find(event => event.sessionId === saved.sessionId && event.kind === 'screen_enter');

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

/** 2026-11-17 프론트 담당자 선택: 기존 파일럿 기준을 기본 전송에 사용. 확장 interaction은 보내지 않습니다. */
export function buildSupportWindow(saved: SavedLog, now = Date.now()): FeatureWindowRequest | null {
  const pilot = measureTouchPilot(saved, now);
  const visit = currentVisit(saved);
  if (!saved.serverSessionId || !visit || !pilot.observed || !['menu', 'review'].includes(visit.screen)
    || Object.values(pilot.features).some(value => !Number.isSafeInteger(value) || value === null || value < 0)) return null;
  return {
    screen_id: visit.screen === 'menu' ? 'menu_list' : 'order_review',
    window_start: new Date(pilot.from).toISOString(), window_end: new Date(pilot.to).toISOString(),
    touch: pilot.features as TouchFeatures, vision: null,
  };
}

type Send = (session: string, body: FeatureWindowRequest, signal: AbortSignal) => Promise<FeatureWindowResponse>;

/** 한 번에 하나만 보내고 화면·세션·표시 상태가 바뀐 응답은 버립니다. 과거 구간을 재전송하지 않습니다. */
export function createSupportTransport(send: Send, read: () => SavedLog | null, receive: (response: FeatureWindowResponse) => void, now = Date.now) {
  let session: string | null = null, context = '', allowed = false, generation = 0;
  let active: AbortController | null = null, stopped: string | null = null;
  function cancel() { generation++; active?.abort(); active = null; }
  return {
    setContext(nextSession: string | null, nextContext: string, enabled: boolean) {
      if (session !== nextSession || context !== nextContext || allowed !== enabled) cancel();
      if (session !== nextSession) stopped = null;
      session = nextSession; context = nextContext; allowed = enabled;
    },
    async tick() {
      if (!allowed || !session || active || stopped === session) return;
      const saved = read();
      if (!saved || saved.serverSessionId !== session) return;
      const body = buildSupportWindow(saved, now());
      if (!body) return;
      const controller = new AbortController(), token = generation, requestSession = session;
      const visitId = currentVisit(saved)?.visitId;
      active = controller;
      const timer = setTimeout(() => controller.abort(), 5000);
      try {
        const response = await send(requestSession, body, controller.signal);
        const current = read();
        if (generation !== token || controller.signal.aborted || !allowed || current?.sessionId !== saved.sessionId
          || current.serverSessionId !== requestSession || currentVisit(current)?.visitId !== visitId) return;
        receive(response);
      } catch (error) {
        if (generation === token && error instanceof ApiError && [400, 401, 403, 404, 410, 422].includes(error.status)) stopped = requestSession;
        // 특징 전송 실패는 주문 흐름을 막지 않고 다음 새 구간에서 재개합니다.
      } finally {
        clearTimeout(timer);
        if (active === controller) active = null;
      }
    },
    dispose() { allowed = false; cancel(); },
  };
}
