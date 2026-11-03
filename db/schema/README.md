# 현재 DB 스키마

서울 리전 Supabase 프로젝트 `Capstone-design-project`의 현재 적용 상태입니다.
테이블 정의는 [`../migration/20261007072436_create_kiosk_sessions.sql`](../migration/20261007072436_create_kiosk_sessions.sql),
서버 역할과 세션 접근 정책은 [`../migration/20261012110139_grant_kiosk_backend_session_access.sql`](../migration/20261012110139_grant_kiosk_backend_session_access.sql)에, 주문 구조와 권한은 [`../migration/20261101092640_create_order_storage.sql`](../migration/20261101092640_create_order_storage.sql)에 기록했습니다.

| 스키마.테이블 | 컬럼 | 목적 |
| --- | --- | --- |
| `kiosk.sessions` | `session_id text` 기본 키, `started_at timestamptz` 필수 | 백엔드가 발급한 세션 ID와 생성 시각 |
| `kiosk.products` | 상품 ID·이름·분류·가격·판매 여부·온도 옵션 | 첫 시연 상품 17개 |
| `kiosk.carts` | 세션 ID·버전·갱신 시각 | 세션당 장바구니 한 건 |
| `kiosk.cart_items` | 상품·온도·수량·가격 스냅샷 | 현재 장바구니 항목 |
| `kiosk.orders` | 고유 주문번호·세션 ID·합계·생성 시각 | 세션당 최대 한 건의 모의 주문 |
| `kiosk.order_items` | 상품·온도·수량·가격 스냅샷 | 주문 확정 시점의 항목 |
| `kiosk.order_request_replays` | 세션 ID·중복 방지 키·요청 지문·응답 | 성공한 장바구니·주문 응답 재생 |

`kiosk`의 Data API 노출 여부는 Supabase 대시보드 설정으로 관리하며 이 SQL 파일에는 포함되지 않습니다.
`anon`과 `authenticated` 역할에는 스키마·테이블 접근 권한을 부여하지 않았고 테이블 RLS를 켰습니다.
따라서 노출 목록에 들어가더라도 이 브라우저 역할로는 읽을 수 없습니다.
`kiosk_backend` 로그인 역할에는 `kiosk` 스키마 사용 및 각 테이블에 필요한 작업만
허용하는 RLS 정책과 권한을 부여했습니다. 주문과 주문 항목의 UPDATE·DELETE는 허용하지 않습니다.
역할 비밀번호는 마이그레이션에 없으며 서버 환경에만 설정합니다. 브라우저는 DB에 직접 접속하지 않습니다.

이 브랜치의 백엔드는 `DATABASE_URL`을 설정하면 세션·주문 테이블을 사용하고, 없으면 메모리 저장소를 사용합니다. 세션 수명·만료·정리, 이벤트·지원 이력, 데이터 보관 기간은 아직 정해지지 않아 임의의 종료 상태나 개인정보 필드를 추가하지 않았습니다. 공개 배포 전 세션 소유자 검증도 별도 결정이 필요합니다.
