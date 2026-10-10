# Supabase DB 준비

- 프로젝트: `Capstone-design-project` (프로젝트 ref는 저장소에 기록하지 않음)
- 리전: 서울 `ap-northeast-2`
- 스키마 변경 원본: `db/migration/`의 SQL 파일. 병합된 마이그레이션은 고치지 않고 새 파일을 추가합니다.
- 적용 방법: Supabase MCP의 `apply_migration`으로 원격 DB에 적용했습니다. 적용된 버전은 `20261007072436`입니다. 원격 적용본과 같은 SQL을 유지하고, 고칠 점은 새 마이그레이션으로 추가합니다.
- 적용 확인: Supabase 마이그레이션 목록 또는 SQL `select version, name from supabase_migrations.schema_migrations order by version;`
- 현재 구조와 접근 범위: [`schema/README.md`](schema/README.md)
- `seed/`는 계약이 확정된 비식별 시연 데이터만 둡니다. 현재 시드는 없습니다.

2026-10-07 프로젝트의 빈 사용자 스키마를 확인한 뒤 첫 마이그레이션
`20261007072436_create_kiosk_sessions`를 적용했습니다. 테이블 조회에서 RLS 활성화와
`anon`·`authenticated`의 스키마·테이블 접근 권한 없음이 확인됐습니다. 보안 진단의
`rls_enabled_no_policy` 정보 알림은 의도한 접근 거부 상태입니다.
DB 비밀번호, 연결 문자열, API 키는 이 저장소에 넣지 않습니다.

백엔드 연결 시에는 서버 전용 환경변수로 DB 접속 정보를 주입합니다. 프론트엔드에
Postgres 접속 문자열이나 서버 비밀키를 전달하지 않습니다. 현재 백엔드 코드의
메모리 세션은 DB로 자동 전환되지 않습니다. 백엔드가 어떤 DB 역할로 접속할지(테이블 소유 역할 또는
`kiosk`에만 권한을 준 전용 역할)는 연결 PR에서 정합니다. 전용 역할을 선택하면 필요한 권한은
새 마이그레이션으로 추가합니다.
