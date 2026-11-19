import { supportCopy } from '../copy.ts';
import { Icon } from './icons.tsx';
import './bottomCluster.css';

/**
 * 조용한 [화면 도움] 줄입니다. 화면 왼쪽 부분에만 두어 주요 버튼 아래에는 아무것도 없습니다.
 * 직원 호출은 매장에 물리 버튼이 있을 수 있어 화면 도움 시트 안에 둡니다.
 * [원래대로]는 키오스크가 켠 화면 지원이 있을 때만 보조색으로 섭니다.
 */
export function EntryRow({ supportOpen, onToggleSupport, onUndo = null }: {
  supportOpen: boolean; onToggleSupport: () => void; onUndo?: (() => void) | null;
}) {
  return <nav className="entry-row" aria-label="화면 도움"><div className="entries">
    <button data-log-target="support-toggle" className="entry e-help" aria-expanded={supportOpen} aria-controls="support-panel" onClick={onToggleSupport}><Icon name="accessibility_new" />화면 도움</button>
    {onUndo && <button type="button" data-log-target="support-undo" className="entry e-undo is-undo" onClick={onUndo}><Icon name="undo" />{supportCopy.undo}</button>}
  </div></nav>;
}
