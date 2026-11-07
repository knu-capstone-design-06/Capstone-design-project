import type { Settings } from './model.ts';

export function KioskModeBar({ settings, voiceEnabled, voiceReady, onStandard, onSetting, onVoice }: {
  settings: Settings;
  voiceEnabled: boolean;
  voiceReady: boolean;
  onStandard: () => void;
  onSetting: (setting: 'largeText' | 'highContrast') => void;
  onVoice: () => void;
}) {
  const modes = [
    { id: 'standard', label: '일반', selected: !settings.highContrast && !settings.largeText && !voiceEnabled, action: onStandard },
    { id: 'contrast', label: '고대비', selected: settings.highContrast, action: () => onSetting('highContrast') },
    { id: 'text', label: '큰 글자', selected: settings.largeText, action: () => onSetting('largeText') },
    { id: 'voice', label: '음성', selected: voiceEnabled, action: onVoice },
  ];
  return <nav className="kiosk-mode-bar" aria-label="화면 모드">
    {modes.map(mode => <button key={mode.id} type="button" data-log-target={`mode:${mode.id}`}
      aria-pressed={mode.selected} disabled={mode.id === 'voice' && !voiceReady} onClick={mode.action}>
      {mode.selected && <span aria-hidden="true">✓</span>}{mode.label}
    </button>)}
  </nav>;
}
