# Supabase DB 수동 백업·복구

서울 리전 `Capstone-design-project`는 Free 플랜이라 Supabase 대시보드의 자동 백업이 없습니다. 이 문서는 운영자가 별도 보관 장소에 논리 백업을 만들고, 격리된 프로젝트에서 복구를 검증하는 절차입니다. 현재까지 **백업 파일 생성과 복구 연습은 수행하지 않았습니다.** 백업 파일과 접속 정보는 Git에 넣지 않습니다.

## 백업 시점과 보관

- 스키마 변경 전에는 반드시 백업합니다. 실제 세션·주문 데이터가 쌓이기 시작하면 팀에서 허용 가능한 데이터 손실 시간에 맞춰 정기 주기와 보존 기간을 결정합니다. 주기를 정하기 전에는 운영 데이터를 저장하지 않습니다.
- 백업 담당자, UTC 시각, 마이그레이션 버전, 파일 크기·SHA-256, 암호화된 외부 보관 위치를 운영 기록에 남깁니다. 파일럿과 최종 평가 데이터는 분리합니다.
- 관리자 DB 접속 정보는 비밀 저장소에서 가져옵니다. 백엔드 전용 `kiosk_backend` 역할은 전체 백업 권한이 없으므로 백업에 쓰지 않습니다. 연결할 네트워크가 IPv4 전용이면 Supabase `Connect`의 Session pooler를, IPv6가 가능하면 Direct connection을 사용합니다.
- 백업 파일에는 개인 데이터나 인증 정보가 포함될 수 있습니다. 접근 권한을 최소화하고 암호화된 저장소로 옮긴 뒤, 불필요한 로컬 복사본을 지웁니다. Supabase Storage의 실제 객체는 DB 덤프에 들어가지 않으므로 Storage를 사용하게 되면 별도 백업을 설계합니다.

## 수동 백업 실행 (PowerShell)

1. [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started)와 Docker를 준비하고 `supabase --version`, `supabase db dump --help`를 확인합니다. 비밀 저장소에서 관리자 접속 문자열을 가져와 현재 터미널의 `SUPABASE_ADMIN_DB_URL` 환경변수에만 설정합니다. 문자열이나 실제 값을 명령 기록, CI 로그, 문서에 출력하지 않습니다. 환경변수를 사용해도 실행 중인 프로세스 인수에 연결 문자열이 나타날 수 있으므로 신뢰할 수 있는 장비에서 실행합니다.
2. 저장소 **밖**에 백업 폴더를 만들고 아래 명령을 순서대로 실행합니다. 각 명령의 종료 코드가 0인지 확인합니다.

```powershell
$backupDir = Join-Path $env:USERPROFILE ("supabase-backups\Capstone-design-project\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$roles = Join-Path $backupDir 'roles.sql'
$schema = Join-Path $backupDir 'schema.sql'
$data = Join-Path $backupDir 'data.sql'
$historySchema = Join-Path $backupDir 'history_schema.sql'
$historyData = Join-Path $backupDir 'history_data.sql'

supabase db dump --db-url $env:SUPABASE_ADMIN_DB_URL -f $roles --role-only
if ($LASTEXITCODE -ne 0) { throw 'roles dump failed' }
supabase db dump --db-url $env:SUPABASE_ADMIN_DB_URL -f $schema
if ($LASTEXITCODE -ne 0) { throw 'schema dump failed' }
supabase db dump --db-url $env:SUPABASE_ADMIN_DB_URL -f $data --use-copy --data-only -x 'storage.buckets_vectors' -x 'storage.vector_indexes'
if ($LASTEXITCODE -ne 0) { throw 'data dump failed' }
supabase db dump --db-url $env:SUPABASE_ADMIN_DB_URL -f $historySchema --schema supabase_migrations
if ($LASTEXITCODE -ne 0) { throw 'migration schema dump failed' }
supabase db dump --db-url $env:SUPABASE_ADMIN_DB_URL -f $historyData --use-copy --data-only --schema supabase_migrations
if ($LASTEXITCODE -ne 0) { throw 'migration history dump failed' }

$sqlFiles = @($roles, $schema, $data, $historySchema, $historyData)
foreach ($file in $sqlFiles) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Item -LiteralPath $file).Length -eq 0) {
        throw "backup file missing or empty: $file"
    }
}
Get-FileHash -LiteralPath $sqlFiles -Algorithm SHA256 -ErrorAction Stop |
    Select-Object Hash, @{ Name = 'File'; Expression = { Split-Path $_.Path -Leaf } } |
    Export-Csv -LiteralPath (Join-Path $backupDir 'SHA256SUMS.csv') -NoTypeInformation -Encoding utf8
```

3. 다섯 SQL 파일과 `SHA256SUMS.csv`를 함께 암호화된 외부 저장소에 올립니다. 복구 전 내려받은 SQL 파일의 해시를 CSV와 다시 비교합니다. 정한 보존 기간에 따라 오래된 백업을 폐기하고 작업이 끝나면 터미널의 관리자 접속 환경변수를 지웁니다.

## 격리된 프로젝트에서 복구 연습

1. 새 Supabase 프로젝트 생성에 따른 비용·권한을 확인하고, 운영 프로젝트와 분리된 연습 프로젝트를 만듭니다. 대상 프로젝트의 Postgres 버전, 확장 기능, Webhook 설정을 확인합니다. 운영 DB에 덮어쓰지 않습니다.
2. 새 프로젝트의 관리자 접속 문자열을 비밀 저장소에서 가져와 `SUPABASE_RESTORE_DB_URL`에 설정합니다. [Supabase 공식 CLI 복구 절차](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)에 따라 `roles.sql` → `schema.sql` → `data.sql` 순서로 복구합니다. 환경에 따라 확장 기능이나 관리 스키마와 충돌하면 원인을 확인하고 새 연습 프로젝트에서 다시 검증합니다.

```powershell
$backupDir = '<내려받아 복호화한 백업 폴더 경로>'
$roles = Join-Path $backupDir 'roles.sql'
$schema = Join-Path $backupDir 'schema.sql'
$data = Join-Path $backupDir 'data.sql'
$historySchema = Join-Path $backupDir 'history_schema.sql'
$historyData = Join-Path $backupDir 'history_data.sql'

$expectedFiles = @('roles.sql', 'schema.sql', 'data.sql', 'history_schema.sql', 'history_data.sql')
$checksums = @(Import-Csv -LiteralPath (Join-Path $backupDir 'SHA256SUMS.csv') -ErrorAction Stop)
if ($checksums.Count -ne $expectedFiles.Count) { throw 'backup checksum list is incomplete' }
foreach ($name in $expectedFiles) {
    $entry = @($checksums | Where-Object File -EQ $name)
    if ($entry.Count -ne 1) { throw "backup checksum entry missing or duplicated: $name" }
    $file = Join-Path $backupDir $name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry[0].Hash) {
        throw "backup checksum mismatch: $file"
    }
}

psql --single-transaction --variable ON_ERROR_STOP=1 --file $roles --file $schema --command 'SET session_replication_role = replica' --file $data --dbname $env:SUPABASE_RESTORE_DB_URL
if ($LASTEXITCODE -ne 0) { throw 'restore failed' }
```

3. CLI 마이그레이션 이력은 기본 덤프에 포함되지 않을 수 있으므로 `history_schema.sql`과 `history_data.sql`을 별도로 복원합니다. 대상 프로젝트에 이미 이력이 있으면 중복 삽입하지 말고 버전과 내용을 먼저 대조합니다.

```powershell
psql --single-transaction --variable ON_ERROR_STOP=1 --file $historySchema --file $historyData --dbname $env:SUPABASE_RESTORE_DB_URL
if ($LASTEXITCODE -ne 0) { throw 'migration history restore failed' }
```

4. `kiosk.sessions` 행 수와 샘플 세션 조회, 두 마이그레이션 버전, RLS 활성화, `anon`·`authenticated` 접근 거부, `kiosk_backend`의 SELECT·INSERT만 허용되는지 확인합니다. 실제 데이터가 있다면 개인 식별값 대신 집계로 검증합니다. 커스텀 로그인 역할의 **비밀번호는 덤프에 포함되지 않으므로**, 필요한 경우 새 비밀값을 별도로 설정합니다.
5. 복구 연습 날짜, 소요 시간, 복원된 행 수·해시, 실패와 수정 사항을 운영 기록에 남깁니다. 복구가 검증되기 전에는 이 백업을 운영 복구 수단으로 간주하지 않습니다.

## 실제 장애 시

쓰기 요청을 중단하고 복구 목표 시각과 예상 데이터 손실 구간을 정합니다. 사용 가능한 백업의 해시와 격리 프로젝트 복구 결과를 확인한 뒤 팀이 대상과 서비스 중단을 결정합니다. 검증한 복구 절차로 복원하고 비밀 저장소의 연결 정보·커스텀 역할 비밀번호를 재설정한 뒤 세션 생성·조회, RLS, 서비스 상태를 점검합니다. 복구 시각과 손실 범위를 기록합니다.

참고: [Supabase Database Backups](https://supabase.com/docs/guides/platform/backups), [Backup and Restore using the CLI](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore), [Connect to your database](https://supabase.com/docs/guides/database/connecting-to-postgres).
