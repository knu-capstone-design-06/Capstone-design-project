import { useRef } from 'react';
import type { ReactNode, Ref } from 'react';
import type { Settings } from '../model.ts';
import { staffCopy } from '../copy.ts';
import { Icon } from './icons.tsx';
import type { IconName } from './icons.tsx';
import { Sheet } from './Sheet.tsx';
import './sheet.css';

const tiles: [keyof Settings, string, IconName][] = [
  ['largeText', '큰 글씨', 'text_increase'], ['largeButton', '큰 버튼', 'touch_app'], ['highContrast', '고대비', 'contrast'],
  ['lowScreen', '낮은 화면', 'vertical_align_bottom'], ['simpleScreen', '간편 화면', 'view_agenda'], ['stepGuide', '단계별 안내', 'format_list_numbered'],
];

/** 설정 하나를 켜고 끄는 타일: 아이콘과 이름(M), 아래에 지금 상태(S, 켜짐·꺼짐). */
export function SettingTile({ target, icon, label, on, disabled = false, onClick }: {
  target: string; icon: IconName; label: string; on: boolean; disabled?: boolean; onClick: () => void;
}) {
  return <button type="button" data-log-target={target} className="opt-tile" aria-pressed={on} disabled={disabled} onClick={onClick}>
    <span className="t-label"><Icon name={icon} />{label}</span>
    <span className="t-state">{on && <Icon name="check" />}{on ? '켜짐' : '꺼짐'}</span>
  </button>;
}

/**
 * 화면 도움: 옵션·장바구니 시트와 같은 모달 시트(<dialog>, 여는 쪽은 OrderPage)입니다. [닫기]·Esc·어두운 곳 누름으로 닫힙니다.
 * 모달이라 터치 기록의 가까운 후보도 이 시트 안에서만 찾습니다. 화면 읽기 상태를 지키려고 닫혀도 내용을 남겨 둡니다.
 * 직원 호출은 설정 타일 아래 한 줄입니다. 받는 쪽이 아직 없어 누르면 준비 중이라는 팝업(제목 한 줄과 [확인])이 화면 가운데에
 * 뜹니다. 팝업도 모달 창이라 [확인]·Esc·어두운 곳 누름으로 닫히고, 닫히면 [직원 부르기]로 초점이 돌아갑니다. 터치 기록은 처음 열린
 * 창 안에서 가까운 후보를 찾으므로 팝업을 이 시트보다 앞에 두어, 팝업이 열린 동안에는 팝업 안에서만 찾게 합니다.
 */
export function HelpSheet({ ref, settings, combined, onToggle, onCombined, onReset, onClose, readAloud }: {
  ref: Ref<HTMLDialogElement>; settings: Settings; combined: boolean;
  onToggle: (key: keyof Settings) => void; onCombined: () => void; onReset: () => void; onClose: () => void; readAloud: ReactNode;
}) {
  const staffButton = useRef<HTMLButtonElement>(null);
  const staffPopup = useRef<HTMLDialogElement>(null);
  const closeStaffPopup = () => { staffPopup.current?.close(); staffButton.current?.focus(); };
  return <>
    <Sheet ref={staffPopup} className="staff-popup" labelledBy="staff-popup-title" onClose={closeStaffPopup}>
      <h2 id="staff-popup-title" className="sheet-name">{staffCopy.notReady}</h2>
      <button type="button" data-log-target="staff-call-close" className="primary" onClick={closeStaffPopup}>{staffCopy.close}</button>
    </Sheet>
    <Sheet ref={ref} id="support-panel" className="help-sheet" labelledBy="help-sheet-title" onClose={onClose}>
      <div>
        <h2 id="help-sheet-title" className="sheet-name">편한 화면으로 주문해 주세요</h2>
        <div className="sheet-support"><p className="sheet-desc">설정을 바꿔도 담은 메뉴는 그대로예요.</p></div>
      </div>
      <div className="support-options cols">
        {tiles.map(([key, label, icon]) => <SettingTile key={key} target={`support:${key}`} icon={icon} label={label} on={settings[key]} onClick={() => onToggle(key)} />)}
        {import.meta.env.DEV && <SettingTile target="support:combinedEnlargement" icon="text_increase" label="큰 글씨 + 큰 버튼" on={combined} onClick={onCombined} />}
      </div>
      <button type="button" ref={staffButton} data-log-target="staff-call" className="staff-row" onClick={() => staffPopup.current?.showModal()}>
        <Icon name="notifications" />{staffCopy.call}</button>
      {readAloud}
      <div className="sheet-bar">
        <button type="button" data-log-target="support-reset" className="sheet-reset" onClick={onReset}><Icon name="undo" />기본 화면으로</button>
        <button type="button" data-log-target="support-close" className="sheet-cancel" onClick={onClose}><Icon name="close" />닫기</button>
      </div>
    </Sheet>
  </>;
}
