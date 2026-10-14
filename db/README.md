# Supabase DB 준비

- 프로젝트: `Capstone-design-project` (프로젝트 ref는 저장소에 기록하지 않음)
- 리전: 서울 `ap-northeast-2`
- 스키마 변경 원본: `db/migration/`의 SQL 파일. 병합된 마이그레이션은 고치지 않고 새 파일을 추가합니다.
- 적용 이력: Supabase MCP의 `apply_migration`으로 원격 DB에 `20261007072436`, `20261012110139`를 적용했습니다. 두 번째 SQL은 원격에서 이미 실행됐으며, 저장소에 누락된 파일을 같은 버전으로 복원했습니다. 현재 프로젝트에 재실행하지 않습니다. 이후 변경은 새 마이그레이션으로 추가합니다.
- 적용 확인: Supabase 마이그레이션 목록 또는 SQL `select version, name from supabase_migrations.schema_migrations order by version;`
- 현재 구조와 접근 범위: [`schema/README.md`](schema/README.md)
- `seed/`는 계약이 확정된 비식별 시연 데이터만 둡니다. 현재 시드는 없습니다.

2026-10-07 프로젝트의 빈 사용자 스키마를 확인한 뒤 첫 마이그레이션
`20261007072436_create_kiosk_sessions`를 적용했습니다. 테이블 조회에서 RLS 활성화와
`anon`·`authenticated`의 스키마·테이블 접근 권한 없음이 확인됐습니다.
두 번째 마이그레이션 뒤에는 백엔드 역할에만 RLS 정책이 있습니다.
2026-10-12 두 번째 마이그레이션으로 로그인 역할 `kiosk_backend`를 만들고
`kiosk.sessions`에 SELECT·INSERT 권한과 해당 RLS 정책만 부여했습니다.
비밀번호는 마이그레이션에 포함되지 않았으며 서버 배포 시 별도로 설정해야 합니다.
DB 비밀번호, 연결 문자열, API 키는 이 저장소에 넣지 않습니다.

백엔드 연결 시에는 서버 전용 환경변수로 DB 접속 정보를 주입합니다. 프론트엔드에
Postgres 접속 문자열이나 서버 비밀키를 전달하지 않습니다. 현재 `main`의 백엔드
세션은 메모리에 저장되며 DB로 자동 전환되지 않습니다. DB 연결 코드는 별도 PR에서
`kiosk_backend` 역할을 사용하도록 준비해야 합니다.

Free 플랜에는 자동 백업이 없습니다. 정기 백업·복구 연습과 운영 시 확인할 항목은
[`BACKUP_RESTORE.md`](BACKUP_RESTORE.md)를 따릅니다. 백업 파일은 저장소 밖에 보관합니다.
