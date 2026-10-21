# 백엔드 실행 및 API 현황

Python 3.12 기반 FastAPI 백엔드입니다. 상태·AI 연결 확인, 임시 세션·특징 전송, 상품·장바구니·모의 주문 API를 제공합니다. 음성 요청 접수·해석 API도 등록돼 있습니다. 세션·주문·음성 기록은 현재 프로세스 메모리에 저장하며, Supabase DB·사용자 인증은 연결하지 않았습니다. `/health` 성공은 프로세스 생존만 뜻하고 DB나 AI 연결 성공을 보장하지 않습니다.

## 프론트 주문 연동 상태

상품·장바구니·모의 주문 서버 API 6개를 [PR #40](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/40)에서 PR #33의 초안 형식으로 구현했습니다. [PR #43](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/43) 병합 후 계약에는 `x-backend-status: implemented`로 표시돼 있습니다. 2026-10-15 첫 시연 정책 A·B·C를 백엔드 담당자가 채택했으며, 나머지 정책이 남아 `x-contract-status: draft`는 유지됩니다. 2026-10-14 PR #43 병합 직후 `main`의 Docker 환경에서 실제 프론트 화면과 백엔드의 주문 흐름을 검증했습니다. 미정 정책은 [담당자 검토](#프론트-주문-연동-준비와-담당자-검토)에 정리했습니다.

## 로컬 실행 (PowerShell)

저장소 루트에서 Python 3.12를 사용해 실행합니다.

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

이미 가상환경이 있으면 해당 환경의 python.exe를 사용합니다. `.env`가 이미 있으면 덮어쓰지 않습니다. VS Code의 `Python: Select Interpreter`에서 사용할 가상환경을 선택합니다.

http://127.0.0.1:8000/health 응답:

```json
{"status":"ok","service":"backend"}
```

API 문서: http://127.0.0.1:8000/docs

## 주문 API 명세 반영 상태

[프론트엔드 ↔ 백엔드 OpenAPI](../contract/frontend-backend.openapi.yaml) 0.3.0의 상품 조회, 세션 장바구니 조회·추가·수량 변경·삭제, 모의 주문 확정 6개 API를 구현했습니다. 첫 시연의 고정 17개 상품·현재 가격·옵션·항목별 최대 20개, 실제 결제·재고 차감 없는 모의 주문, 한 세션 한 주문·새 주문 새 세션은 채택됐습니다. 계약 문서의 `draft` 표시는 미정 정책의 팀 리뷰가 끝날 때까지 유지합니다. FastAPI `/docs`에는 현재 등록된 여섯 경로가 표시됩니다.

설계 이유·미정 정책은 [주문 API 검토 문서](../docs/Product-Cart-Order-API-Draft.md)를 확인합니다. 상품 목록은 프론트 개발 샘플의 17개 메뉴와 가격을 서버의 고정 시연 데이터로 옮겼습니다. 가격·옵션·수량을 서버가 검증하고, 세션별 Cart 버전과 `Idempotency-Key`의 성공 결과를 같은 프로세스의 잠금 아래 저장합니다. 모의 주문은 항목·금액 스냅샷을 반환하고 Cart를 비우며 같은 키 재시도에는 원래 주문 응답을 반환합니다. 신규 API의 검증 오류는 `OrderApiError` 형식이고 기존 API 오류 형식은 유지합니다.

현재 세션·Cart·주문·중복 방지 기록은 프로세스 재시작이나 여러 백엔드 인스턴스 사이에 유지되지 않습니다. 서버가 반환한 `session_id`를 보유한 클라이언트가 해당 Cart에 접근하므로 공개 배포 전 세션 접근·만료 정책을 정해야 합니다. 주문번호는 서버가 생성한 `SIM-` 접두의 고유 UUID 문자열이며 형식과 보관 정책은 팀 리뷰 대상입니다. 처리 중 중복 응답·장기 보관·동적 가격 변경은 미구현입니다. 실제 결제와 재고 차감은 포함하지 않습니다.

모의 주문을 확정한 세션의 장바구니 조회·변경은 `410 session_expired`로 거절합니다. 같은 `Idempotency-Key`와 동일한 주문 요청을 재시도하면 저장된 첫 주문 성공 응답을 다시 반환합니다. 완료 세션의 복원·보관·만료 정책은 팀 합의 전입니다.

허용한 프론트 출처에서 GET·POST·PATCH·DELETE와 `Idempotency-Key` 헤더의 CORS 요청을 처리합니다. 현재 주문 API는 `Retry-After`를 반환하지 않습니다. 세션 ID를 가진 누구나 Cart에 접근할 수 있으므로 공개 배포 전 접근 정책과 인증 방식은 별도 합의가 필요합니다.

## Supabase DB 연결 상태

서울 리전 Supabase 프로젝트에는 `kiosk.sessions` 테이블과 백엔드 전용 `kiosk_backend` 역할을 만드는 마이그레이션 2개가 적용돼 있습니다. 역할에는 현재 세션 테이블의 SELECT·INSERT 권한만 있으며, 비밀번호는 마이그레이션에 넣지 않았습니다. **백엔드 코드는 아직 이 테이블을 사용하지 않습니다.** `app/infrastructure/database/`에는 연결 구현이 없고 DB 접속 환경변수도 아직 정의하지 않았습니다. 주문 관련 테이블은 계약·보관 정책을 합의한 뒤 새 마이그레이션으로 설계해야 합니다. 이미 적용한 마이그레이션은 수정하지 않습니다. 현재 구조와 백업 상태는 [DB 안내](../db/README.md)와 [백업·복구 절차](../db/BACKUP_RESTORE.md)를 참고합니다.

## 음성 API 상태

[PR #36](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/36)에서 음성 요청 접수 `POST /api/v1/sessions/{session_id}/voice/requests`와 상태 조회 `GET /api/v1/sessions/{session_id}/voice/requests/{request_id}`를 병합했습니다. [PR #42](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/42)에서 주문 카탈로그를 음성 메뉴에 연결하고 `ignored` 상태를 추가했습니다. 세션별 대화 맥락을 사용해 OpenAI 해석 결과를 `tool_calls`로 만들지만, 도구를 실행하거나 장바구니를 변경하지 않으므로 `actions`는 비어 있습니다. `OPENAI_API_KEY`가 없으면 개발용 응답을 사용하며, 터치 주문과 백엔드 기동은 가능합니다.

도구 실행·장바구니 변경, 주문 완료 세션의 음성 처리 정책, 실제 OpenAI 키를 사용한 검증은 별도 작업입니다. 음성 요청 형식은 [음성 OpenAPI](../contract/voice.openapi.yaml)를 확인합니다.

## 환경변수

`backend/.env` 또는 프로세스 환경변수에서 읽으며 프로세스 환경변수가 우선합니다. 설정 변경 후 서버를 다시 시작합니다. 빈 값은 기본값을 사용합니다.

| 변수 | 기본값 | 형식 |
| --- | --- | --- |
| APP_NAME | Capstone Backend | 문자열 |
| DOCS_ENABLED | true | true / false |
| CORS_ORIGINS | localhost:5173, localhost:3000의 HTTP 출처 | JSON 배열 |
| AI_ENGINE_URL | http://ai-engine:8001 | ai-engine HTTP(S) 출처 |
| AI_ENGINE_TIMEOUT_SECONDS | 2 | 양의 유한한 초 단위 숫자 |
| OPENAI_API_KEY | 미설정 | 서버 전용 비밀값 |
| OPENAI_MODEL | gpt-4o-mini | 모델 이름 |
| OPENAI_TIMEOUT_SECONDS | 10 | 양의 유한한 초 단위 숫자 |

예: `CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]`. 실제 프론트 출처에 맞춰 설정하며 경로나 와일드카드는 허용하지 않습니다. CORS는 GET·POST·PATCH·DELETE를 허용합니다. 기본 허용 출처는 localhost이므로 127.0.0.1에서 직접 교차 출처 요청을 보낼 때는 위 설정이 필요합니다. CORS는 사용자 인증 기능이 아닙니다.

`.env`에는 실제 비밀값을 넣을 수 있지만 Git에 커밋하지 않습니다. `.env.example`은 항목 설명만 공유합니다. 음성 메뉴는 주문 카탈로그와 연결돼 있으며, 실제 OpenAI 키를 사용한 음성 해석은 아직 검증하지 않았습니다. DB 접속 설정은 실제 연동 시 추가합니다.

## Docker Compose

루트 Compose는 프론트엔드·백엔드·ai-engine을 실행합니다. Docker 엔진을 실행한 뒤 저장소 루트에서 시작합니다.

```powershell
docker compose up --build
```

프론트 화면은 `http://127.0.0.1:8080`에서 제공하고 `/backend/` 요청을 백엔드로 전달합니다. 백엔드의 직접 주소는 `http://127.0.0.1:8000`이며 ai-engine은 Docker 내부의 `http://ai-engine:8001`을 사용합니다. Compose에는 `env_file`이 없고 이미지에도 `.env`가 없으므로, 로컬 직접 실행과 달리 `backend/.env`는 읽지 않습니다. 필요한 값은 실행 환경에서 컨테이너에 주입합니다.

연결 API의 기존 실행·통신 검증은 [PR #26](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/26)를 참고합니다. 2026-10-14에는 PR #43이 병합된 `main`(`3cb8529`)으로 세 이미지를 빌드해 모두 healthy 상태를 확인했습니다. 실제 브라우저의 기본 API 모드에서 상품 조회 → 세션·장바구니 생성 → 상품 추가 → 모의 주문 확정 → 새 주문 시작이 통과했습니다. 주문은 서버에서 처리하되 첫 응답만 유실시킨 검사에서는 화면의 `주문 반영 확인`이 같은 키·본문으로 재요청해 원래 주문번호를 표시했습니다. `/backend/` 프록시를 거친 HTTP 검사에서는 17개 상품, 옵션 오류, 버전 충돌과 최신 Cart, 중복 키·주문 재시도, 완료 세션 410을 확인했습니다. 이 검증은 DB 영속성, 실제 결제, 음성 도구 실행, AI 판단을 확인한 것은 아닙니다.

## Backend → AI 내부 연동

`app/infrastructure/external/ai_client.py`의 `AiEngineClient`가 ai-engine의
`POST /v1/analyze`, `GET /health`를 호출합니다. FastAPI lifespan이 HTTP 연결을
생성·재사용·종료하며 `get_ai_engine_client`를 `Depends`로 주입할 수 있습니다.
서버 시작이나 백엔드 `/health` 호출 시에는 ai-engine 접속을 시도하지 않습니다.

`/v1/analyze`는 **ai-engine의 엔드포인트**입니다. 백엔드에 동일 경로를 추가하지
않았습니다. 프론트엔드용 특징 전송 라우터가 임시 세션을 확인한 뒤 이 클라이언트를 호출합니다. 사용자 인증은 아직 구현하지 않았습니다.

서비스 계층에서 사용할 패턴:

```python
from app.infrastructure.external.ai_client import AiEngineClient
from app.infrastructure.external.ai_schemas import AnalyzeRequest


async def analyze_window(ai: AiEngineClient, window: AnalyzeRequest):
    result = await ai.analyze(window)
    if result is None or not result.measurable:
        return None  # 판단을 생성하지 않고 현재 흐름 유지
    return result
```

- `session_id`는 백엔드가 관리하는 세션 값으로 채워 전달합니다. 이 클라이언트는
  세션을 생성하거나 인증하지 않습니다. 세션 생성과 존재 확인은 `modules/sessions/`에서 처리합니다.
- 기본 2초는 HTTP I/O 제한과 전체 호출 제한에 모두 적용합니다. 자동 재시도는 없습니다.
- 연결 오류, 타임아웃, HTTP 오류(422 포함), 잘못된 JSON·응답 구조, 세션 불일치는
  `None`을 반환합니다. 정상 상태 점수를 임의로 만들어 반환하지 않습니다.
- `measurable=false`는 유효한 응답으로 유지하고 `states`는 `None`입니다.
  `measurable=true`인데 점수가 없거나, false인데 점수가 있으면 응답 오류로 처리합니다.
  OpenAPI의 required 목록에 따라 false 응답에서 states 생략도 허용합니다.
- 호출자의 취소는 상위로 전달합니다. 로그에는 오류 종류만 기록합니다.
- 시간 필드는 시간대가 있는 날짜·시간이어야 하며 종료 시각이 시작 시각보다 뒤여야 합니다.
- `TouchFeatures`, `VisionFeatures`, `StateScores`의 현재 형식은
  `contract/frontend-backend.openapi.yaml`(0.3.0, 기존 0.1.0 형식 유지)에 정의돼 있습니다. 다만 비전
  세부 특징과 터치 통계 계산 기준에는 팀 검토 항목이 남아 있습니다.
  연결 API는 `modules/sessions/schemas.py`에서 입력 필드와 반환 점수 5개·범위·타입을 검증합니다.
  내부 전송 클라이언트의 `JsonObject`는 그대로 유지하므로 직접 사용하는 다른 호출자는 별도의 의미 검증이 필요합니다.
  현재 AI는 dummy 모델이고 지원 선택 기준도 미정이므로 검증된 점수라도 자동 UI 결정에는 사용하지 않습니다.

`ai-engine` 호스트 이름은 동일 Docker 네트워크에서 해석됩니다. 루트 Compose는
ai-engine의 호스트 포트를 공개하지 않습니다. 두 서버를
호스트에서 직접 실행할 때만 `AI_ENGINE_URL=http://127.0.0.1:8001`로 변경합니다.

## 테스트

의존성 설치 후 `backend/`에서 실행합니다. 표준 라이브러리 unittest와 HTTPX
MockTransport를 사용하므로 실제 ai-engine·DB·Docker가 필요하지 않습니다.

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s app/modules -p 'test_*.py' -v
```

기존 AI 클라이언트 테스트는 정상 요청·응답, vision 생략/null, 판단 불가, HTTP 오류,
연결 실패, 전체 타임아웃, 잘못된 응답·세션 불일치, 호출 취소, health 응답과 연결 종료를 확인합니다.
모듈 테스트는 세션 생성·격리, 입력 검증, AI 점수 검증, 연결 장애와 측정 불가의 구분,
주문 API와 POST CORS를 확인합니다. 위 Docker 검증은 고정 HTTP 응답을 쓰는 프론트 단위·브라우저 검사와 별도로 실제 서버 응답을 사용했습니다.

## 연결 API (0.1.0 형식 유지)

| 요청 | 결과 |
| --- | --- |
| GET /api/v1/connectivity | 200, backend=ok 및 ai_engine=ok 또는 unreachable |
| POST /api/v1/sessions | 201, session_id와 UTC started_at |
| POST /api/v1/sessions/{session_id}/features | 200, AI 점수 또는 판단 없는 응답 |

세션은 단일 프로세스 메모리에만 보관하며 재시작하면 초기화됩니다.
세션 만료·정리·영속 저장은 아직 없으므로 장기 운영 또는 여러 worker/인스턴스에 사용하지 않습니다.
터치 원시 로그의 통계 계산과 비전 추출은 구현하지 않고 계약에 정의된 특징만 전달합니다.
AI 측정 불가는 ai_available=true, states=null입니다. 통신 오류·타임아웃·잘못된 AI 응답은
ai_available=false, states=null, model_version=null입니다. 모든 경우 support는
`{"preset":"none","requires_confirmation":false,"decided_by":"rule_placeholder"}`로 화면을 유지합니다.
없는 세션은 404 `{"detail":"session not found"}`, 잘못된 입력은 422를 반환합니다.

PowerShell에서 실행할 예시(백엔드 실행 후):

```powershell
$base = 'http://127.0.0.1:8000'
Invoke-RestMethod "$base/api/v1/connectivity"
$session = Invoke-RestMethod -Method Post "$base/api/v1/sessions"
$body = @{
    screen_id = 'menu_list'
    window_start = '2026-10-01T10:00:00Z'
    window_end = '2026-10-01T10:00:03Z'
    touch = @{ tap_count=6; miss_tap_count=3; repeat_tap_count=2; back_count=0; dwell_ms=3000 }
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post "$base/api/v1/sessions/$($session.session_id)/features" -ContentType 'application/json' -Body $body
```

프론트 호출·화면 반영 상태는 [프론트엔드 README](../frontend/README.md)를 확인합니다.

## 참고

- [FastAPI 설정](https://fastapi.tiangolo.com/advanced/settings/)
- [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)

## 프론트 주문 연동 준비와 담당자 검토

기존 상태·AI 연결 확인, 임시 세션 생성, 특징 전송 API를 사용합니다. 상품·장바구니·주문 API는 기존 세션에 연결했고, 2026-10-14 Docker 기본 화면에서 실제 요청·응답으로 주요 주문 흐름과 재시도를 확인했습니다.

프론트는 [상품·장바구니·주문 초안](../docs/Product-Cart-Order-API-Draft.md)에 맞춰 API 호출·응답 표시·수동 재시도를 준비했습니다. 위 통합 검증이 팀의 최종 계약 합의나 공개 배포 준비 완료를 뜻하지는 않습니다.

백엔드가 이미 구현·검증한 사항:
- 기존 `modules/sessions/`의 세션 ID로 상품 조회·Cart 조회/변경·모의 주문 연결
- 고정 17개 상품과 `coffee`/`drink`/`food`, 음료 `iced`/`hot`·푸드 `null` 제공, 가격·옵션·수량·금액 서버 검증
- `expected_version` 충돌 시 최신 Cart 반환, 동일 키·동일 요청의 성공 결과 재사용, 한 세션의 주문 완료 뒤 Cart 요청 410

팀과 결정하고 이후 구현할 사항:
- 프론트 요청 타임아웃은 15초입니다. 최종 시간과 시간 초과 후 처리 중 응답·재시도 정책은 백엔드 담당자와 합의할 항목입니다.
- 처리 중 중복 요청의 오류·간격, 실패 결과와 성공 키의 보관 기간, DB 전환 시 원자적 저장
- 완료 후 특징·음성 요청, 서버 주문번호의 형식·보관 범위, 세션 만료·복원
- 공개 주소의 세션 접근·인증·쿠키 및 배포 정책

복원·장기 보관·정밀 만료·동적 가격 변경은 첫 시연 후순위 방향입니다. 프론트 담당자와 검토한 방향이며 팀 전체 합의는 아직 확인되지 않았습니다. 세부 서버 정책은 담당자가 결정·구현하고 계약에는 합의 후 반영합니다.

