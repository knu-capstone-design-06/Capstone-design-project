# Supabase DB 준비

- 프로젝트: `Capstone-design-project` (프로젝트 ref는 저장소에 기록하지 않음)
- 리전: 서울 `ap-northeast-2`
- 스키마 변경 원본: `db/migration/`의 SQL 파일. 병합된 마이그레이션은 고치지 않고 새 파일을 추가합니다.
- 적용 이력: 원격 DB에 `20261007072436`, `20261012110139`, `20261101092640` 세 버전이 적용됐습니다. 마지막 주문 마이그레이션은 2026-11-03에 저장소와 같은 버전으로 적용했습니다. 이미 적용한 SQL은 재실행하거나 수정하지 않습니다.
- 적용 확인: Supabase 마이그레이션 목록 또는 SQL `select version, name from supabase_migrations.schema_migrations order by version;`
- 현재 구조와 접근 범위: [`schema/README.md`](schema/README.md)
- `seed/20261101_demo_catalog.sql`의 비식별 상품 17개(커피 6·음료 5·음식 6)를 적용했습니다.

2026-10-07 프로젝트의 빈 사용자 스키마를 확인한 뒤 첫 마이그레이션
`20261007072436_create_kiosk_sessions`를 적용했습니다. 테이블 조회에서 RLS 활성화와
`anon`·`authenticated`의 스키마·테이블 접근 권한 없음이 확인됐습니다.
두 번째 마이그레이션 뒤에는 백엔드 역할에만 RLS 정책이 있습니다.
2026-10-12 두 번째 마이그레이션으로 로그인 역할 `kiosk_backend`를 만들고
`kiosk.sessions`에 SELECT·INSERT 권한과 해당 RLS 정책만 부여했습니다.
비밀번호는 마이그레이션에 포함되지 않습니다. 전용 역할의 비밀값은 서버 환경에만 설정합니다.
DB 비밀번호, 연결 문자열, API 키는 이 저장소에 넣지 않습니다.

백엔드 연결 시에는 서버 전용 `DATABASE_URL`로 `kiosk_backend` 접속 정보를 주입합니다.
프론트엔드에 Postgres 접속 문자열이나 서버 비밀키를 전달하지 않습니다. 이 브랜치의
백엔드는 URL이 설정되면 세션·상품·Cart·주문·성공 응답 재생 기록을 DB에서 읽고 쓰며,
설정하지 않으면 기존 메모리 저장 방식을 사용합니다. 원격 DB에서 합성 세션으로 재시작·동시 주문·음성 도구 롤백을 검증한 뒤 테스트 데이터를 삭제했습니다.

2026-11-02 주문 마이그레이션 적용 전 수동 백업을 만들고 저장소 밖 OneDrive에 암호화해 보관했습니다. 2026-11-03 격리 로컬 PostgreSQL에서 복구를 확인했습니다. 정기 백업 주기와 보관 정책은 아직 결정되지 않았습니다. 절차와 검증 범위는 [`BACKUP_RESTORE.md`](BACKUP_RESTORE.md)를 따릅니다.
