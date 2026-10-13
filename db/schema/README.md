# 현재 DB 스키마

서울 리전 Supabase 프로젝트 `Capstone-design-project`의 현재 적용 상태입니다.
테이블 정의는 [`../migration/20261007072436_create_kiosk_sessions.sql`](../migration/20261007072436_create_kiosk_sessions.sql),
서버 역할과 접근 정책은 [`../migration/20261012110139_grant_kiosk_backend_session_access.sql`](../migration/20261012110139_grant_kiosk_backend_session_access.sql)에 기록했습니다.

| 스키마.테이블 | 컬럼 | 목적 |
| --- | --- | --- |
| `kiosk.sessions` | `session_id text` 기본 키, `started_at timestamptz` 필수 | 백엔드가 발급한 세션 ID와 생성 시각 |

`kiosk`의 Data API 노출 여부는 Supabase 대시보드 설정으로 관리하며 이 SQL 파일에는 포함되지 않습니다.
`anon`과 `authenticated` 역할에는 스키마·테이블 접근 권한을 부여하지 않았고 테이블 RLS를 켰습니다.
따라서 노출 목록에 들어가더라도 이 브라우저 역할로는 읽을 수 없습니다.
`kiosk_backend` 로그인 역할에는 `kiosk` 스키마 사용 및 `sessions` SELECT·INSERT만
허용하는 RLS 정책과 권한을 부여했습니다. 역할 비밀번호는 마이그레이션에 없으며
운영자가 별도로 설정해야 합니다. 브라우저는 DB에 직접 접속하지 않습니다.

현재 `main` 백엔드의 세션 저장소는 메모리 기반입니다. 이 테이블을 실제로 사용하도록
바꾸는 작업은 별도 PR에서 진행해야 합니다. 세션 수명·만료·정리 정책은 아직
정해지지 않았으므로 이 초기 테이블에 임의의 종료 상태나 개인정보 필드를 넣지 않았습니다.
상품·장바구니·주문은 검토용 초안만 있어 이번 버전의 테이블에 포함하지 않았습니다.
