# 첫 시연 주문 저장 구조와 적용 순서

이 문서는 `20261101092640_create_order_storage.sql`과
`../seed/20261101_demo_catalog.sql`의 검토·적용 절차다. 현재 원격 Supabase에는
`kiosk.sessions`와 기존 마이그레이션 2건만 확인했다. 이 문서와 SQL 파일을
작성하는 것만으로 원격 DB나 백엔드의 메모리 저장소가 바뀌지 않는다.

## 확정된 범위

첫 시연 정책은 고정 상품 17개, 실제 결제·재고 차감이 없는 모의 주문,
상품·온도별 장바구니 항목 수량 1~20개, 세션당 주문 1건이다.

| 테이블 | 역할 | 주요 제약 |
| --- | --- | --- |
| `kiosk.products` | 시연용 상품 목록 | 상품 ID 고유, 가격 비음수, 종류·온도 제한 |
| `kiosk.carts` | 세션별 장바구니 버전 | 세션 ID 고유, 버전 비음수 |
| `kiosk.cart_items` | 현재 장바구니 항목 | 세션·상품·온도 조합 및 세션·위치 고유, 수량 1~20 |
| `kiosk.orders` | 모의 주문 결과 | 세션당 한 건, 주문번호 고유, 상태 `simulated` |
| `kiosk.order_items` | 확정 당시 항목·가격 스냅샷 | 주문별 항목·위치 고유 |
| `kiosk.order_request_replays` | 성공 응답 재전송 | 세션·멱등 키 조합 고유, 요청 지문과 응답 보관 |

장바구니 합계는 항목에서 계산하며 주문 합계는 확정 시점에 저장한다.
장바구니 응답은 `session_id`로 조회한 항목을 **`position` 오름차순**으로
직렬화한다. 새 상품·온도 조합은 현재 항목의 최대 `position + 1`에 추가하고,
이미 담긴 조합의 수량 변경은 `position`을 유지한다. 항목 삭제 후 같은 조합을
다시 담으면 새 항목으로 마지막에 추가한다. 삭제로 생긴 순번 공백은 허용한다.
주문 확정 시에는 이 순서대로 `order_items.position`에 0부터 연속 순번을
매겨 스냅샷을 만든다. 동시 변경 시 위치 할당도 장바구니 버전 확인·저장과
같은 트랜잭션에서 처리한다.
장바구니 수정·주문 확정·멱등 응답 저장은 추후 백엔드 DB 연결 작업에서
**하나의 트랜잭션**으로 처리해야 한다. 이 SQL만으로 합계 일치나 동시 요청의
원자성이 보장되는 것은 아니다. 상품 변경 시 기존 주문 항목의 스냅샷은 유지한다.

모든 테이블은 비공개 `kiosk` 스키마에 있고 RLS를 활성화한다. 브라우저 역할에는
권한을 주지 않으며, 기존 `kiosk_backend` 역할에 작업에 필요한 권한만 준다.
현재 애플리케이션의 상품·장바구니·주문은 메모리에서 동작하므로, DB로
전환하는 코드는 별도 PR과 통합 검증이 필요하다. 멱등 응답의 보관 기간과
세션 삭제 시점도 아직 결정되지 않았다. 보관·삭제 작업을 임의로 시작하지 않는다.

## 적용 전 필수 확인

1. 이 변경의 PR에서 백엔드 담당자와 DB 변경 영향 범위를 검토한다.
2. [`../BACKUP_RESTORE.md`](../BACKUP_RESTORE.md)에 따라 관리자 연결로
   `roles.sql`, `schema.sql`, `data.sql`, `history_schema.sql`,
   `history_data.sql`을 **저장소 밖**에 덤프한다. 각 파일의 크기가 0보다 크고
   SHA-256 목록이 생성됐는지 확인한 뒤 암호화된 외부 저장소에 보관한다.
   백업 담당자·시각·기존 버전 `20261007072436`, `20261012110139`를 기록한다.
3. 격리 프로젝트 복구 연습을 완료하기 전에는 백업을 검증된 복구 수단으로
   간주하지 않는다. 복구 연습 비용·권한을 먼저 확인한다.
4. 원격 DB에 새 테이블 이름이 이미 없는지, `kiosk_backend` 역할이 있는지,
   기존 두 마이그레이션만 적용됐는지 다시 확인한다.

백업이 확인되기 전에는 마이그레이션·시드를 원격에 적용하지 않는다.
접속 문자열과 백업 파일은 Git에 올리지 않는다.

## 적용과 확인

백업과 PR 검토가 끝나면 `db/migration/20261101092640_create_order_storage.sql`을
새 마이그레이션으로 **한 번** 적용하고, 적용 이력을 확인한다. 이어서
`db/seed/20261101_demo_catalog.sql`을 실행한다. 시드는 기존 상품 행을
덮어쓰지 않으므로, 재실행 전에는 값이 코드의 고정 카탈로그와 일치하는지
먼저 비교한다. 한 번에 여러 관리 도구로 같은 마이그레이션을 중복 실행하지 않는다.

```sql
select version, name
from supabase_migrations.schema_migrations
order by version;

select count(*) as product_count from kiosk.products;
select category, count(*) from kiosk.products group by category order by category;

select c.relname, c.relrowsecurity
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'kiosk'
  and c.relname in ('products', 'carts', 'cart_items', 'orders',
                    'order_items', 'order_request_replays')
order by c.relname;

-- 명시적 테이블 GRANT: grantee 0은 PUBLIC이다.
select c.relname as table_name,
       case when a.grantee = 0 then 'PUBLIC' else r.rolname end as grantee,
       a.privilege_type
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
left join pg_roles r on r.oid = a.grantee
where n.nspname = 'kiosk'
  and c.relname in ('products', 'carts', 'cart_items', 'orders',
                    'order_items', 'order_request_replays')
  and (a.grantee = 0 or r.rolname in ('kiosk_backend', 'anon', 'authenticated'))
order by table_name, grantee, privilege_type;

-- 실제 유효 권한: PUBLIC과 상속된 역할의 GRANT도 반영한다.
with roles(role_name) as (
    values ('kiosk_backend'), ('anon'), ('authenticated')
), tables(table_name) as (
    values ('products'), ('carts'), ('cart_items'), ('orders'),
           ('order_items'), ('order_request_replays')
)
select role_name, table_name,
       has_schema_privilege(role_name, 'kiosk', 'USAGE') as schema_usage,
       has_table_privilege(role_name, format('kiosk.%I', table_name), 'SELECT') as can_select,
       has_table_privilege(role_name, format('kiosk.%I', table_name), 'INSERT') as can_insert,
       has_table_privilege(role_name, format('kiosk.%I', table_name), 'UPDATE') as can_update,
       has_table_privilege(role_name, format('kiosk.%I', table_name), 'DELETE') as can_delete
from roles cross join tables
order by role_name, table_name;
```

기대 결과는 상품 17건, 새 테이블 6개 모두 RLS `true`, 브라우저 역할의 권한
없음이다. 유효 권한 표에서 `anon`·`authenticated`의 `schema_usage`와 네 가지
테이블 권한은 모두 `false`여야 한다. `kiosk_backend`는 스키마 사용·상품 조회,
각 테이블에 마이그레이션에서 허용한 작업만 `true`여야 한다. 예상 밖의 `true`는
PUBLIC 또는 상속된 역할의 권한을 포함해 원인을 확인한다.

관리자 연결에서 아래 블록을 **각각 따로** 실행해 실제 역할도 확인한다.
`SET LOCAL ROLE`이 허용된 연결이어야 하며, 실패하면 테스트한 것으로 기록하지
않는다. 거부 예상 쿼리는 오류로 트랜잭션이 중단되므로 `ROLLBACK`을 별도로
실행한다. 테스트는 조회만 수행하며 운영 데이터를 변경하지 않는다.

```sql
begin;
set local role kiosk_backend;
select current_user, count(*) from kiosk.products;
rollback;
```

```sql
begin;
set local role anon;
select current_user;
select count(*) from kiosk.products; -- permission denied 예상
-- 위 오류 뒤 별도로 ROLLBACK 실행
```

```sql
begin;
set local role authenticated;
select current_user;
select count(*) from kiosk.products; -- permission denied 예상
-- 위 오류 뒤 별도로 ROLLBACK 실행
```

`kiosk_backend`의 쓰기 권한은 위 유효 권한 표로 확인하고, 실제 INSERT·UPDATE·DELETE와
RLS 동작은 격리된 복구 연습 환경에서 트랜잭션 롤백과 함께 검증한다. 기존 세션
생성·조회도 회귀 확인한다. 실제 주문 DB 저장 검증은 백엔드 연결 PR에서 수행한다.

## 이벤트·지원 이력

[`event_support_draft.sql`](event_support_draft.sql)은 **검토용 설계안**이며
마이그레이션이나 시드가 아니다. PR #62에서 이벤트 종류, 중복 판정,
허용 필드, 보관 기간이 확정되지 않았으므로 원격 DB에 적용하지 않는다.
프론트·AI·비전·백엔드가 계약을 확정한 뒤 새 마이그레이션을 작성한다.
