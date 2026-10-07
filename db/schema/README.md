# 현재 DB 스키마

서울 리전 Supabase 프로젝트 `Capstone-design-project`의 첫 버전입니다.
정의 원본은 [`../migration/20261007072436_create_kiosk_sessions.sql`](../migration/20261007072436_create_kiosk_sessions.sql)입니다.

| 스키마.테이블 | 컬럼 | 목적 |
| --- | --- | --- |
| `kiosk.sessions` | `session_id text` 기본 키, `started_at timestamptz` 필수 | 백엔드가 발급한 세션 ID와 생성 시각 |

`kiosk`는 Supabase Data API에 노출하지 않는 비공개 스키마입니다. `anon`과
`authenticated` 역할에는 접근 권한을 부여하지 않았고 테이블 RLS를 켰습니다.
브라우저가 DB에 직접 접속하지 않으며, 이후 백엔드의 서버 측 DB 연결을 통해서만 사용합니다.

현재 백엔드의 세션 저장소는 메모리 기반입니다. 이 테이블을 실제로 사용하도록
바꾸는 작업은 별도 PR에서 진행해야 합니다. 세션 수명·만료·정리 정책은 아직
정해지지 않았으므로 이 초기 테이블에 임의의 종료 상태나 개인정보 필드를 넣지 않았습니다.
상품·장바구니·주문은 검토용 초안만 있어 이번 버전의 테이블에 포함하지 않았습니다.
