import type { ReactNode, Ref } from 'react';
import './sheet.css';

/**
 * 아래에서 올라오는 시트의 껍데기입니다. 기존과 같이 <dialog>의 showModal로 열고(여는 쪽은 OrderPage),
 * Esc와 배경 누름은 닫기와 같습니다. 시트는 [화면 도움] 줄 바로 위에서 끝나고 나머지 화면은 어둡게 덮습니다.
 */
export function Sheet({ ref, id, className, labelledBy, onClose, children }: {
  ref: Ref<HTMLDialogElement>; id?: string; className: string; labelledBy: string; onClose: () => void; children: ReactNode;
}) {
  return <dialog ref={ref} id={id} className={`sheet ${className}`} aria-labelledby={labelledBy}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => {
      // 시트 자신의 여백이 아니라 시트 밖(어두운 배경)을 누른 경우에만 닫습니다.
      const box = event.currentTarget.getBoundingClientRect();
      if (event.target === event.currentTarget && (event.clientY < box.top || event.clientY > box.bottom || event.clientX < box.left || event.clientX > box.right)) onClose();
    }}>
    {children}
  </dialog>;
}
