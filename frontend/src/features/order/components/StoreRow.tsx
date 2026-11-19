import './topCluster.css';

/** 매장 이름 줄입니다. 고객 화면에는 시험·샘플 표시를 두지 않습니다(샘플 모드는 .kiosk의 data-order-mode로 구분). */
export function StoreRow() {
  return <header className="header">
    <p className="store-name">온기 카페</p>
  </header>;
}
