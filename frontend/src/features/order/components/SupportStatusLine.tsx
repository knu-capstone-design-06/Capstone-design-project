import './supportStatus.css';

/**
 * 개발 모드에서만 보이는 한 줄: 마지막 /features 응답의 지원 이름과 결정 ID(시연 스위치를 켠 backend)입니다.
 * 3-2 기다림처럼 고객 화면에 아무것도 띄우지 않는 결정도 키오스크가 일부러 기다리는지 볼 수 있게 합니다.
 * 주문 화면 밖(개발용 터치 로그 버튼과 같은 줄의 왼쪽 끝)에 두어 터치 기록·화면 읽기에 들어가지 않습니다.
 */
export function SupportStatusLine({ status }: { status: { name: string; decisionId: string } | null }) {
  if (!import.meta.env.DEV || !status) return null;
  return <p className="support-status-line" data-support-status={status.name}>마지막 응답 지원: {status.name} · {status.decisionId}</p>;
}
