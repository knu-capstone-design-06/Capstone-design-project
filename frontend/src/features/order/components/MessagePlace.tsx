import type { ReactNode } from 'react';
import { Icon } from './icons.tsx';
import type { IconName } from './icons.tsx';
import './messagePlace.css';

/**
 * 안내 영역: 위 묶음과 아래 묶음 사이의 빈 곳에 한 번에 한 층만 보여 줍니다.
 * 순서: 오류·처리 중(feedback) > 제안 카드(offer) > 알림(notice) > 늘 서 있는 줄(단계별 안내). 키오스크가 한 일의 알림과 힌트(kiosk)는 보조색에 그 아이콘(적용은 확인, 힌트는 가리키는 손). 알림 영역은 낭독기를 위해 늘 두고 숨깁니다.
 * 늘 서 있는 줄은 다른 층 뒤에 보이지 않게 남겨 자리 높이를 지킵니다.
 * variant="popup"은 메뉴 화면의 상품 목록 위에 뜨는 자리입니다(비워 두는 자리 없음). 버튼이 있는 카드만 누름을 받습니다.
 */
export function MessagePlace({ feedback, offer = null, notice, kiosk = null, standing, variant = 'place' }: {
  feedback: ReactNode | null; offer?: ReactNode; notice: string; kiosk?: IconName | null; standing: string[] | null; variant?: 'place' | 'popup';
}) {
  const showOffer = !feedback && offer !== null;
  const showNotice = !feedback && !showOffer && notice !== '';
  return <div className={`message-${variant}`}>
    {feedback}
    {showOffer && offer}
    <div className={`cart-notice${kiosk ? ' is-kiosk' : ''}`} role="status" aria-live="polite" hidden={!showNotice}>{showNotice && kiosk && <Icon name={kiosk} />}{showNotice ? notice : ''}</div>
    {standing && <div className={`guide${feedback || showOffer || showNotice ? ' is-behind' : ''}`} role="status">{standing.map(line => <p key={line}>{line}</p>)}</div>}
  </div>;
}
