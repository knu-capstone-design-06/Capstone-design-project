# Supabase DB 준비

- 프로젝트: `Capstone-design-project` (`qhykfuyxqbyyurbadpdt`)
- 리전: 서울 `ap-northeast-2`
- 스키마 변경 원본: `db/migration/`의 SQL 파일. 병합된 마이그레이션은 고치지 않고 새 파일을 추가합니다.
- 현재 구조와 접근 범위: [`schema/README.md`](schema/README.md)
- `seed/`는 계약이 확정된 비식별 시연 데이터만 둡니다. 현재 시드는 없습니다.

2026-10-07 프로젝트의 빈 사용자 스키마를 확인한 뒤 첫 마이그레이션
`20261007072436_create_kiosk_sessions`를 적용했습니다. 테이블 조회에서 RLS 활성화와
`anon`·`authenticated`의 스키마·테이블 접근 권한 없음이 확인됐습니다. 보안 진단의
`rls_enabled_no_policy` 정보 알림은 의도한 접근 거부 상태입니다.
DB 비밀번호,
연결 문자열, API 키는 이 저장소에 넣지 않습니다.

백엔드 연결 시에는 서버 전용 환경변수로 DB 접속 정보를 주입합니다. 프론트엔드에
Postgres 접속 문자열이나 서버 비밀키를 전달하지 않습니다. 현재 백엔드 코드의
메모리 세션은 DB로 자동 전환되지 않습니다.
