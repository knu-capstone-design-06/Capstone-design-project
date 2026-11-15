import { useEffect, useState } from 'react';
import { supportCopy } from '../copy.ts';
import type { SupportKind } from '../utils/supportDecision.ts';
import { doubleClickMs } from '../utils/timing.ts';
import { Icon } from './icons.tsx';
import type { IconName } from './icons.tsx';
import './offerCard.css';

const pictogram: Record<SupportKind, IconName> = { enlarge: 'text_increase' };

/**
 * 키오스크가 먼저 묻는 화면 지원 제안: 한 장뿐인 어두운 층(#1B4975)에 흰 원 안의 지원 아이콘,
 * 흰 질문(M 굵게), 같은 너비의 흰 대답 두 개(88). 모달이 아닙니다. 나타난 뒤 두 번 클릭 간격 동안은 대답이 누름을 받지 않습니다.
 */
export function OfferCard({ support, onAccept, onDecline }: { support: SupportKind; onAccept: () => void; onDecline: () => void }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setArmed(true), doubleClickMs); return () => clearTimeout(timer); }, []);
  const answer = (action: () => void) => () => { if (armed) action(); };
  return <section className="offer-card" aria-label="화면 도움 제안" aria-live="polite" data-armed={armed}>
    <div className="o-head">
      <span className="o-pic" aria-hidden="true"><Icon name={pictogram[support]} /></span>
      <p className="q">{supportCopy[support].question}</p>
    </div>
    <div className="o-buttons">
      <button type="button" data-log-target="support-offer:accept" onClick={answer(onAccept)}>{supportCopy.accept}</button>
      <button type="button" data-log-target="support-offer:decline" onClick={answer(onDecline)}>{supportCopy.decline}</button>
    </div>
  </section>;
}
