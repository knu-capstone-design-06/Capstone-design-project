import { initialSettings } from './model.ts';
import type { Settings } from './model.ts';

/** 프론트 내부 값입니다. 음성 API의 UI 명령 전송 형식은 아직 정해지지 않았습니다. */
export type VoiceSettingChanges = Partial<Settings>;

export type VoiceSettingsContext = {
  sessionId: string | null;
  screen: string;
  available: boolean;
  settings: Settings;
};

const settingKeys = Object.keys(initialSettings) as (keyof Settings)[];

function readChanges(value: unknown): VoiceSettingChanges | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const entries = Object.entries(value);
  if (!entries.length || entries.some(([key, enabled]) => !Object.hasOwn(initialSettings, key) || typeof enabled !== 'boolean')) return null;
  return Object.fromEntries(entries) as VoiceSettingChanges;
}

/**
 * 요청 전에 적용 맥락을 잡고, 백엔드 검증이 끝난 결과만 적용하는 프론트 내부 경계입니다.
 * 자연어·tool_calls·미합의 API 필드를 해석하지 않습니다.
 */
export function createVoiceSettingsReceiver(onApply: (changes: VoiceSettingChanges) => void) {
  let epoch = 0;
  let context: VoiceSettingsContext | null = null;
  function invalidate() { epoch++; }
  return {
    invalidate,
    setContext(next: VoiceSettingsContext) {
      if (!context || context.sessionId !== next.sessionId || context.screen !== next.screen
        || context.available !== next.available || settingKeys.some(key => context!.settings[key] !== next.settings[key])) invalidate();
      context = { ...next, settings: { ...next.settings } };
    },
    prepare(): ((changes: unknown) => boolean) | null {
      if (!context?.available || !context.sessionId || context.screen !== 'menu') return null;
      const preparedEpoch = epoch;
      let used = false;
      return value => {
        if (used) return false;
        used = true;
        if (epoch !== preparedEpoch || !context?.available) return false;
        const changes = readChanges(value);
        if (!changes) return false;
        const changed = Object.fromEntries(Object.entries(changes).filter(([key, enabled]) => context!.settings[key as keyof Settings] !== enabled));
        if (!Object.keys(changed).length) return false;
        // React 갱신 전에 다른 응답이 도착해도 이전 맥락의 명령은 함께 무효화합니다.
        invalidate();
        onApply(changed);
        return true;
      };
    },
  };
}
