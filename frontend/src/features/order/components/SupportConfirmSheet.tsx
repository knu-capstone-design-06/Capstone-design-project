import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { askedSupports, isAskedSupport, supportSettings } from '../backendSupport.ts';
import type { SupportAsk } from '../backendSupport.ts';
import { doubleClickMs } from '../utils/timing.ts';
import { Icon } from './icons.tsx';
import './supportConfirm.css';

/**
 * 주문을 막거나 초점을 옮기지 않는 제안 카드입니다. 수락한 설정만 적용합니다.
 * 결정으로 묻는 지원(askedSupports)은 그 질문·설명·대답 글을 쓰고, 그림은 화면에 이미 있는 같은 지원의 그림입니다
 * (크게 보기: 개발용 크게 보기 카드 OfferCard와 같은 text_increase, 화면 내리기: 화면 도움의 낮은 화면 타일과 같은
 * vertical_align_bottom, 말로 주문: 마이크 버튼과 같은 mic).
 */
export function SupportConfirmSheet({ ask, onAccept, onDecline, onDismiss }: {
  ask: SupportAsk; onAccept: () => void; onDecline: () => void; onDismiss: () => void;
}) {
  const card = useRef<HTMLElement>(null);
  const [armed, setArmed] = useState(false);
  useLayoutEffect(() => {
    const element = card.current;
    const previous = document.activeElement;
    return () => {
      if (element?.contains(document.activeElement) && previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);
  useEffect(() => { const timer = setTimeout(() => setArmed(true), doubleClickMs); return () => clearTimeout(timer); }, []);
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      // 바깥의 조작도 그대로 전달합니다. 닫기 때문에 입력을 소비하거나 배경을 덮지 않습니다.
      if (armed && event.target instanceof Node && !card.current?.contains(event.target)) onDismiss();
    };
    const escape = (event: KeyboardEvent) => { if (armed && event.key === 'Escape' && !event.defaultPrevented) onDismiss(); };
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside, true); document.removeEventListener('keydown', escape); };
  }, [armed, onDismiss]);
  const copy = isAskedSupport(ask) ? askedSupports[ask] : { ...supportSettings[ask], accept: '적용하기' };
  return <section ref={card} className="support-confirm-sheet" aria-labelledby="support-confirm-title" aria-describedby="support-confirm-description" data-log-target="support-confirm">
    <div className="support-confirm-copy">
      <span className="support-confirm-symbol"><Icon name={ask === 'large_text' || ask === 'enlarge' ? 'text_increase' : ask === 'large_button' ? 'touch_app' : ask === 'simple_screen' ? 'grid_view'
        : ask === 'lower_screen' ? 'vertical_align_bottom' : ask === 'voice_order' ? 'mic' : 'format_list_numbered'} /></span>
      <div aria-live="polite">
        <h2 id="support-confirm-title">{copy.question}</h2>
        <p id="support-confirm-description" className="sr-only">{copy.description}</p>
      </div>
    </div>
    <div className="support-confirm-actions" data-armed={armed}>
      <button type="button" data-log-target="support-confirm:accept" className="support-confirm-accept" onClick={() => { if (armed) onAccept(); }}>{copy.accept}</button>
      <button type="button" data-log-target="support-confirm:decline" onClick={() => { if (armed) onDecline(); }}>이대로 두기</button>
    </div>
  </section>;
}
