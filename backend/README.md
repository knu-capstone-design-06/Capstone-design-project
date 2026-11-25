# 백엔드 실행 및 API 현황

Python 3.12 기반 FastAPI 백엔드입니다. 상태·AI 연결 확인, 세션·특징 전송, AI 엔진 창 수신, 상품·장바구니·모의 주문 API를 제공합니다. 음성 요청 접수·해석 API도 등록돼 있습니다. `DATABASE_URL`을 설정하면 세션·상품·장바구니·주문·주문 API의 성공 응답 재생 기록을 Supabase에 저장하고, 비워 두면 기존 프로세스 메모리 방식으로 동작합니다. 음성 요청·대화 기록과 사용자 인증은 DB에 연결하지 않았습니다. `/health` 성공은 프로세스 생존만 뜻하고 DB나 AI 연결 성공을 보장하지 않습니다.

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

[프론트엔드 ↔ 백엔드 OpenAPI](../contract/frontend-backend.openapi.yaml) 0.4.1의 상품 조회, 세션 장바구니 조회·추가·수량 변경·삭제, 모의 주문 확정 6개 API를 구현했습니다. 첫 시연의 고정 17개 상품·현재 가격·옵션·항목별 최대 20개, 실제 결제·재고 차감 없는 모의 주문, 한 세션 한 주문·새 주문 새 세션은 채택됐습니다. 계약 문서의 `draft` 표시는 미정 정책의 팀 리뷰가 끝날 때까지 유지합니다. FastAPI `/docs`에는 현재 등록된 여섯 경로가 표시됩니다.

설계 이유·미정 정책은 [주문 API 검토 문서](../docs/Product-Cart-Order-API-Draft.md)를 확인합니다. 상품 목록은 프론트 개발 샘플의 17개 메뉴와 가격을 서버의 고정 시연 데이터로 옮겼습니다. 가격·옵션·수량을 서버가 검증하고, 세션별 Cart 버전과 `Idempotency-Key`의 성공 결과를 메모리 모드에서는 프로세스 잠금으로, DB 모드에서는 트랜잭션 잠금으로 저장합니다. 모의 주문은 항목·금액 스냅샷을 반환하고 Cart를 비우며 같은 키 재시도에는 원래 주문 응답을 반환합니다. 신규 API의 검증 오류는 `OrderApiError` 형식이고 기존 API 오류 형식은 유지합니다.

`DATABASE_URL` 설정 시 세션·Cart·주문·중복 방지 기록은 프로세스 재시작 후에도 유지됩니다. 동일 세션의 변경은 DB 트랜잭션 잠금으로 순서를 정하며, 여러 백엔드 인스턴스가 동시에 주문해도 세션당 주문은 한 건만 생성합니다. 음성 도구 묶음에서 뒤 명령이 실패하면 앞 장바구니 변경도 롤백합니다. 서버가 반환한 `session_id`를 보유한 클라이언트가 해당 Cart에 접근하므로 공개 배포 전 세션 접근·만료 정책을 정해야 합니다. 주문번호는 서버가 생성한 `SIM-` 접두의 고유 UUID 문자열이며 형식과 보관 정책은 팀 리뷰 대상입니다. 처리 중 중복 응답·장기 보관·동적 가격 변경은 미구현입니다. 실제 결제와 재고 차감은 포함하지 않습니다.

모의 주문을 확정한 세션의 장바구니 조회·변경은 `410 session_expired`로 거절합니다. 같은 `Idempotency-Key`와 동일한 주문 요청을 재시도하면 저장된 첫 주문 성공 응답을 다시 반환합니다. 완료 세션의 복원·보관·만료 정책은 팀 합의 전입니다.

허용한 프론트 출처에서 GET·POST·PATCH·DELETE와 `Idempotency-Key` 헤더의 CORS 요청을 처리합니다. 현재 주문 API는 `Retry-After`를 반환하지 않습니다. 세션 ID를 가진 누구나 Cart에 접근할 수 있으므로 공개 배포 전 접근 정책과 인증 방식은 별도 합의가 필요합니다.

## Supabase DB 연결 상태

서울 리전 Supabase 프로젝트에는 세션과 첫 시연 주문 저장용 마이그레이션 3개, 고정 상품 17개 시드가 적용돼 있습니다. 서버 전용 `DATABASE_URL`은 `kiosk_backend` 역할의 PostgreSQL URL만 허용합니다. `app/infrastructure/database/`의 연결은 TLS를 사용하며, 앱 시작 시 실제 DB 역할을 확인합니다. URL이 없으면 DB 연결을 시도하지 않고 메모리 저장소를 사용합니다. 비밀번호와 URL은 Git에 넣지 않습니다. 원격 DB에 합성 세션으로 주문·재시작·동시 요청·음성 도구 롤백을 검증한 뒤 합성 데이터를 삭제했습니다. 현재 구조와 백업 상태는 [DB 안내](../db/README.md)와 [백업·복구 절차](../db/BACKUP_RESTORE.md)를 참고합니다.

## 음성 API 상태

[PR #36](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/36)에서 음성 요청 접수 `POST /api/v1/sessions/{session_id}/voice/requests`와 상태 조회 `GET /api/v1/sessions/{session_id}/voice/requests/{request_id}`를 병합했습니다. [PR #42](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/42)에서 주문 카탈로그를 음성 메뉴에 연결하고 `ignored` 상태를 추가했습니다. 세션별 대화 맥락을 사용해 OpenAI 해석 결과를 `tool_calls`로 만듭니다. 기본 설정에서는 도구를 실행하지 않아 `actions`가 비어 있고, `VOICE_EXECUTE_TOOLS=true`면 `completed`의 `tool_calls`를 주문 서비스로 반영한 뒤 `actions: ["cart_updated"]`를 돌려줍니다(`app/modules/voice/executor.py`). `OPENAI_API_KEY`가 없으면 개발용 응답을 사용하며, 터치 주문과 백엔드 기동은 가능합니다.

실제 OpenAI 키를 사용한 검증은 해석(PR #61)과 도구 실행(PR #66)에서 했으며, 결과 표는 각 PR 본문에 있습니다. 음성 요청 형식은 [음성 OpenAPI](../contract/voice.openapi.yaml)를 확인합니다.

주문 완료 세션의 **새 음성 요청**은 410 `{ "code": "session_expired", "detail": "새 이용 세션을 시작해 주세요." }`로 거절합니다. 완료 전에 접수한 요청의 같은 키·같은 본문은 기록이 남아 있으면 기존 202를 재생하고, 같은 키·다른 본문은 409입니다. 기존 요청의 GET은 주문 완료만으로 막지 않으며, 음성 기록의 기존 1시간 정리 규칙을 따릅니다. 기본 설정(`VOICE_EXECUTE_TOOLS` 꺼짐)에서 음성 해석은 Cart를 변경하지 않습니다.

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
| VOICE_EXECUTE_TOOLS | false | true면 completed 음성 결과의 tool_calls를 장바구니에 반영 |
| DATABASE_URL | 미설정 | 서버 전용 `kiosk_backend` PostgreSQL URL. 미설정 시 메모리 저장 |
| JEV_API_KEY | 미설정 | 서버 전용 비밀값. 없으면 Jev를 호출하지 않음 |
| JEV_API_URL | https://api.typesafe.ai | HTTPS 오리진만. 평문 HTTP는 localhost·127.0.0.1 모의 서버에만 허용 |
| JEV_MODEL | jev-1.13.0 | 버전 ID. 별칭(jev-latest)은 실험 기록을 위해 쓰지 않음 |
| JEV_TIMEOUT_SECONDS | 3 | Jev 호출 한 번의 전체 제한, 재시도 없음 |
| JEV_STAGES | off | 실험 조건. 창마다 돌릴 Jev 단계를 쉼표로 나열(`state_scores`, `support_choice`, `next_difficulty`). 기본 `off`는 키가 있어도 규칙표만 돌리고 Jev를 부르지 않음 |
| DECISION_SEND_SUPPORT | false | 시연 스위치. true면 `/features` 응답의 support에 규칙표 결정을 실음(아래 [시연 스위치](#시연-스위치-decision_send_support)). Jev 답은 켜도 기록만 함 |

판단 층(`app/modules/decision/`)은 `/features` 창마다 규칙표(`RULES_VERSION`)를 돌려 세션 상태를 갱신하고, `JEV_API_KEY`가 있고 `JEV_STAGES`에 단계가 있으면 백그라운드에서 그 단계의 질문(`state_scores`: 상태 점수와, 상황을 알 때 규칙표 제안의 적합성; `support_choice`·`next_difficulty`: 지원 고르기·다음 어려움)을 Jev에 물어 기록만 남깁니다(그림자 모드). 기본 설정에서는 응답이 바뀌지 않고, 창 기록에는 짝 지은 엔진 창 정보(`vision_window`)가 더해집니다. `DECISION_SEND_SUPPORT`를 켜면 규칙표 결정이 support에 실립니다. 규칙표가 읽는 상황 태그와 시선은 AI 엔진이 보낸 창에서 옵니다([AI 엔진 창 입구](#ai-엔진-창-입구)). 설계와 현황은 [`docs/Jev-Integration.md`](../docs/Jev-Integration.md) 9·10장입니다.

예: `CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]`. 실제 프론트 출처에 맞춰 설정하며 경로나 와일드카드는 허용하지 않습니다. CORS는 GET·POST·PATCH·DELETE를 허용합니다. 기본 허용 출처는 localhost이므로 127.0.0.1에서 직접 교차 출처 요청을 보낼 때는 위 설정이 필요합니다. CORS는 사용자 인증 기능이 아닙니다.

`.env`에는 실제 비밀값을 넣을 수 있지만 Git에 커밋하지 않습니다. `.env.example`은 항목 설명만 공유합니다. 음성 메뉴는 주문 카탈로그와 연결돼 있으며, 실제 OpenAI 키를 사용한 검증 결과는 PR #61과 #66 본문에 있습니다. 로컬에서 DB 모드를 실행하려면 `backend/.env`의 `DATABASE_URL`에 전용 역할 URL을 설정합니다. 관리자 `postgres` 계정 URL을 넣으면 시작 단계에서 거절합니다.

## Docker Compose

루트 Compose는 프론트엔드·백엔드·ai-engine을 실행합니다. Docker 엔진을 실행한 뒤 저장소 루트에서 시작합니다.

```powershell
docker compose up --build
```

프론트 화면은 `http://127.0.0.1:8080`에서 제공하고 `/backend/` 요청을 백엔드로 전달합니다. 백엔드의 직접 주소는 `http://127.0.0.1:8000`이며 ai-engine은 Docker 내부의 `http://ai-engine:8001`을 사용합니다. Compose에는 `env_file`이 없고 이미지에도 `.env`가 없으므로, 로컬 직접 실행과 달리 `backend/.env`는 읽지 않습니다. DB 모드가 필요하면 실행 터미널의 `DATABASE_URL` 환경변수로 전용 역할 URL을 주입합니다. 값을 넣지 않으면 메모리 모드입니다.

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
  `contract/frontend-backend.openapi.yaml`(0.4.1, 기존 0.1.0 형식 유지)에 정의돼 있습니다. 다만 비전
  세부 특징과 터치 통계 계산 기준에는 팀 검토 항목이 남아 있습니다.
  연결 API는 `modules/sessions/schemas.py`에서 입력 필드와 반환 점수 5개·범위·타입을 검증합니다.
  내부 전송 클라이언트의 `JsonObject`는 그대로 유지하므로 직접 사용하는 다른 호출자는 별도의 의미 검증이 필요합니다.
  현재 AI는 dummy 모델이고 지원 선택 기준도 미정이므로 검증된 점수라도 자동 UI 결정에는 사용하지 않습니다.

`ai-engine` 호스트 이름은 동일 Docker 네트워크에서 해석됩니다. 루트 Compose는
ai-engine의 호스트 포트를 공개하지 않습니다. 두 서버를
호스트에서 직접 실행할 때만 `AI_ENGINE_URL=http://127.0.0.1:8001`로 변경합니다.

## 테스트

의존성 설치 후 `backend/`에서 실행합니다. 일반 테스트는 표준 라이브러리 unittest와 HTTPX
MockTransport를 사용하므로 실제 ai-engine·DB·Docker가 필요하지 않습니다. `TEST_DATABASE_URL`이 없으면 PostgreSQL 통합 테스트 3개는 건너뜁니다.

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s app/modules -p 'test_*.py' -v
```

별도 CI 작업 `Backend DB integration`은 일회용 PostgreSQL 17에 저장소의 마이그레이션 3개와 상품 17개 시드를 적용한 뒤 `python -m unittest tests.test_postgres_ordering -v`를 실행합니다. 실제 Supabase 접속 정보는 사용하지 않고, Cart·주문 성공 응답의 재시작 뒤 재생, 두 저장소 인스턴스의 동시 주문, 실패한 음성 도구 묶음의 롤백을 검사합니다.

기존 AI 클라이언트 테스트는 정상 요청·응답, vision 생략/null, 판단 불가, HTTP 오류,
연결 실패, 전체 타임아웃, 잘못된 응답·세션 불일치, 호출 취소, health 응답과 연결 종료를 확인합니다.
모듈 테스트는 세션 생성·격리, 입력 검증, AI 점수 검증, 연결 장애와 측정 불가의 구분,
주문 API와 POST CORS를 확인합니다. AI 엔진 창 테스트(`app/modules/sessions/tests/test_vision_windows.py`)는 입구의 검증·거절·보관 기간, 짝 짓기 구간의 경계, 엔진 창을 읽은 장면 3-1·3-2·4-2, 시연 스위치를 켜고 끈 응답, 시험 블록 `touch.interaction`의 시연 대응을 확인합니다. 장면 행 테스트(`app/modules/decision/tests/test_scene_rows.py`, `app/modules/sessions/tests/test_scene_rows_features.py`)는 1-1·1-2·2-1·2-2 행과 4-1의 입력을 규칙표 입력과 실제 `/features`·엔진 창 본문으로 확인합니다. 위 Docker 검증은 고정 HTTP 응답을 쓰는 프론트 단위·브라우저 검사와 별도로 실제 서버 응답을 사용했습니다.

## 연결 API (0.1.0 형식 유지)

| 요청 | 결과 |
| --- | --- |
| GET /api/v1/connectivity | 200, backend=ok 및 ai_engine=ok 또는 unreachable |
| POST /api/v1/sessions | 201, session_id와 UTC started_at |
| POST /api/v1/sessions/{session_id}/features | 200, AI 점수 또는 판단 없는 응답 |

`DATABASE_URL`이 없으면 세션은 단일 프로세스 메모리에만 보관하며 재시작하면 초기화됩니다. 전용 역할의 `DATABASE_URL`을 설정하면 세션·Cart·주문·성공 요청 재생 기록을 DB에 저장하고 재시작 뒤에도 조회할 수 있습니다. 음성 요청·대화 이력은 두 모드 모두 메모리에만 남습니다.
세션 만료·정리와 공개 접속자의 세션 접근 통제는 아직 없으므로, DB 모드에서도 공개 장기 운영 준비가 끝난 것은 아닙니다.
터치 원시 로그의 통계 계산과 비전 추출은 구현하지 않고 계약에 정의된 특징만 전달합니다.
주문 완료 세션의 새 특징 요청은 AI 호출 전에 410 `{ "detail": "session_expired" }`로 거절합니다. AI 호출 중 주문이 완료된 경우에도 결과를 반환하지 않고 410으로 처리합니다. 프론트가 이미 수신한 늦은 결과의 화면 적용 차단은 특징 전송 연결 시 함께 확인해야 합니다.
AI 측정 불가는 ai_available=true, states=null입니다. 통신 오류·타임아웃·잘못된 AI 응답은
ai_available=false, states=null, model_version=null입니다. `DECISION_SEND_SUPPORT`가 꺼져 있으면(기본값) 모든 경우 support는
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

## AI 엔진 창 입구

AI 엔진의 실시간 실행기(`ai-engine/app/modules/vision/tag_sender.py`)가 판단한 창마다 상황 태그를 이 경로로 보냅니다(형식: [`contract/ai-backend.openapi.json`](../contract/ai-backend.openapi.json)). 주문 화면은 비전 값을 전달하지 않으며, `/features`의 `vision` 필드는 이 연결과 관계없이 그대로입니다. 주소 두 개는 서로 다른 프로세스입니다: backend의 `AI_ENGINE_URL`은 ai-engine 앱의 `/v1/analyze`(기본 `http://ai-engine:8001`)이고, 주문 화면의 `VITE_AI_ENGINE_URL`은 실시간 실행기의 터치 입구(`live.py --serve PORT`의 `http://127.0.0.1:<PORT>`, 형식: [`contract/frontend-ai.openapi.json`](../contract/frontend-ai.openapi.json))입니다.

| 요청 | 결과 |
| --- | --- |
| POST /api/v1/sessions/{session_id}/vision-windows | 202 `{"status":"accepted"}`. 없는 세션 404, 주문을 마친 세션 410(`/features`와 같은 본문), 형식 오류와 경로와 다른 본문 `session_id`는 422 |

- 본문: `window_start`·`window_end`(시간대가 있는 시각, 끝이 시작보다 뒤), `situation`(규칙표가 읽는 `name`·`evidence`·`confidence`), `observations`(`gaze`: true·false·null, `face_seen`, `scene_tags`), `model_version`입니다. `session_id`는 있을 때만 읽고 경로와 같아야 합니다. 그 밖의 키는 읽지 않습니다.
- 보관: 판단 층 저장소의 메모리에 세션별로 둡니다. 세션의 다른 판단 기록처럼 1시간 동안 쓰이지 않으면 정리되고, 재시작하면 사라집니다. 엔진 창이 오는 것은 세션을 쓴 것으로 치지 않으므로, 주문 화면이 멈춘 세션은 엔진이 계속 보내도 마지막 사용부터 1시간 뒤 정리됩니다. 가장 최근 터치 창의 짝 짓기 경계(아래) 이전에 끝난 엔진 창은 도착할 때 버립니다.
- 짝 짓기: `/features` 창 하나는 같은 세션의 엔진 창 가운데 `touch_start - (touch_end - touch_start) < 엔진 창 끝 <= touch_end`를 만족하는 창을 읽습니다. 시선·얼굴·장면 태그는 그 가운데 가장 늦은 창에서 가져오고, 상황은 그 가운데 상황 태그(`looking_back_with_people_behind`·`consulting_companion`·`looking_around`)를 단 가장 늦은 창에서 가져옵니다. 태그를 단 창이 없으면 가장 늦은 창의 상황(`none`·`unknown`)이고, 가장 늦은 창의 태그는 늘 이깁니다. 짝 짓기 구간은 터치 창 길이의 두 배라 엔진의 1초 구간 두 개가 들어가므로, 한 구간에서만 잡힌 태그도 앞 구간이든 뒤 구간이든 판단에 닿습니다. 주문 화면은 터치 창을 엔진에 먼저 보내고, 엔진이 답한 뒤(답이 없으면 전송기의 확인 주기 한 번 뒤) `/features`를 보냅니다. 엔진은 그 터치 창이 풀어 준 엔진 창을 엔진의 창 간격(`segment_s`) 안에 backend에 넘기면 그 뒤에 답하므로, 같은 구간의 엔진 창은 대개 같은 터치 창의 `/features` 요청이 읽습니다. 늦게 도착한 엔진 창은 다음 요청의 짝 짓기 구간 안에 끝났으면 그 요청이 읽습니다. 넘겨 주기와 읽기는 최선을 다하는 것이고 보장이 아닙니다: 보내기가 실패로 끝난 창은 backend에 닿았는지 알 수 없고, 보내기 전에 바뀐 창과 짝 짓기 구간을 지나 도착한 창은 어느 요청도 읽지 못합니다. 허용 폭은 그 터치 창의 길이뿐이고, 두 시각은 모두 키오스크 PC의 시계입니다. 구간의 앞 경계(`touch_start - (touch_end - touch_start)`)나 그 전에 끝난 엔진 창은 이때 버립니다.
- 짝 지은 창의 `situation`과 `gaze`가 규칙표 입력이 됩니다. 짝이 없으면 둘 다 None이라 엔진 창이 없을 때와 같습니다. 누름·뒤로가기가 없는 창도 짝 지은 창이 얼굴을 보았으면 측정 가능으로 봅니다(ai-engine 자리표시자가 `vision.face_detected`에 쓰는 규칙과 같음). ai-engine 호출은 그대로입니다. 스위치가 꺼져 있으면 ai-engine이 답하지 못한 창은 얼굴이 보여도 측정 불가이고, 켜면 아래 '시연 스위치' 절에 적은 대로 backend가 정합니다.
- 창 기록(`WindowRecord.vision_window`)에 짝 지은 가장 늦은 창의 시작·끝 시각, 받은 시각, `model_version`, `face_seen`, `scene_tags`와, 상황을 준 창의 끝 시각(`situation_window_end`, 가장 늦은 창이 주었으면 같은 값)을 남깁니다. 스위치의 로그 줄은 두 끝 시각이 다를 때 둘 다 적습니다.
- `scene_tags`는 창 기록에 남깁니다. 규칙표는 시연 스위치를 켰을 때만 장면 태그를 읽습니다(아래 [장면 행](#장면-행-1-1-1-2-2-1-2-2)).

### 시연 스위치 (DECISION_SEND_SUPPORT)

기본값(false)에서는 `/features` 응답의 support가 언제나 `{"preset":"none","requires_confirmation":false,"decided_by":"rule_placeholder"}`입니다. true로 켜면 그 창에서 규칙표가 내린 결정을 싣습니다.

- `preset`·`requires_confirmation`은 결정의 계약 형식입니다(`Decision.form()`, `decision/schemas.py`의 `CONTRACT_FORM`). 4-1 크게 보기 묻기는 `large_button`·`true`(먼저 물음), 3-1 남은 단계 안내는 `step_guide`·`false`, 3-2 기다림과 4-2 강조는 `none`·`false`입니다. 장면 행의 형식은 [장면 행](#장면-행-1-1-1-2-2-1-2-2)에 적었습니다.
- 지원이 화면에 떠 있는 동안(열기·바꾸기·유지)에는 `name`(지원 이름), `decision_id`, `steps_left`, `target_id`, `message_id`를 더합니다. 값이 없는 필드는 빠집니다.
- `decision_id`는 규칙표 결정의 ID입니다. 유지되는 결정은 매 응답에 같은 ID로 다시 오고, 새로 열거나 바꾼 결정은 새 ID로 옵니다. 주문 화면이 반복된 응답과 새 결정을 가르도록 싣습니다.
- 유지되는 결정의 `steps_left`·`target_id`·`message_id`는 지금 답하는 창의 입력으로 규칙표의 `execution()`이 다시 구합니다. 그래서 옵션 창이 열린 메뉴에서 시작한 4-2는 옵션 창이 닫힌 창의 응답에서 대상 없이 오고, 옵션 창이 다시 열린 창의 응답에서는 `cart-add`를 가리킵니다. 열리거나 바뀐 결정은 처음부터 그 창의 값입니다.
- 측정 가능 여부는 backend가 정합니다. 창에 누름이나 뒤로가기가 있거나, 짝 짓기 구간(앞 경계 `touch_start - (touch_end - touch_start)` 뒤) 안에 끝난 같은 세션의 앞 터치 창에 누름이나 뒤로가기가 있거나, 짝 지은 엔진 창 가운데 가장 늦은 창이나 상황을 준 창이 얼굴을 보았으면 측정 가능입니다(ai-engine 자리표시자의 규칙을 짝 짓기 구간에서 읽음). 누름 근거와 카메라 근거를 판단이 읽는 엔진 창과 같은 구간에서 읽으므로, 1초 창에서 누름이 든 창 다음 창에 처음 온 단서도 그 누름과 만납니다. 앞 터치 창은 판단한 창만 셉니다. 기록만 한 늦은 창과 프론트 시계가 옮겨지기 전의 창은 세지 않습니다. 앞 구간에 태그와 얼굴이 있고 뒤 구간에서 얼굴이 사라진 창(뒤나 일행 쪽으로 몸을 돌린 경우)도 측정 가능입니다. 그래서 `/v1/analyze`가 꺼지거나 늦거나 잘못된 점수를 주어도 판단 층이 돈 창의 결정이 응답에 실립니다. `ai_available`·`states`·`model_version`은 그대로 ai-engine 분석의 결과입니다.
- 거두기, 열리는 행이 없는 창, 기록만 하는 늦은 창, 판단 층 오류에서는 기본값을 보냅니다.
- 스위치를 켜면 `/features` 창마다 로그 한 줄(INFO, `app.modules.sessions.service`)을 남깁니다. 세션, 창 끝, 전이, 지원 이름, 장면, 측정 가능 여부, 짝 지은 엔진 창의 끝과 상황 이름(없으면 None)입니다. uvicorn은 자기 로거만 설정하므로, 스위치를 켠 앱이 이 로거에 콘솔 출력을 하나 붙입니다. 새 2-2 사건 ID를 실은 엔진 창마다 같은 로거에 한 줄(`new customer event`: 세션, 엔진 창 끝, ID)을 더 남겨, 사건이 됐는지(`pending`) 기억만 했는지와 그 까닭(첫 누름 없음, 앞 엔진 창 없음, 앞 창이 첫 누름 창 끝 전에 끝남)을 보입니다.
- `decided_by`는 켜도 `rule_placeholder`입니다. Jev 답은 응답을 기다리게 하지 않고 기록만 하므로, 제때 유효한 답이 없어도 규칙표 결과가 그대로 나갑니다.
- 4-1이 읽는 빗나간 뒤 바로 고친 횟수(`fixes_recent`)는 시험 블록 `touch.scene_signals`에서 옵니다([장면 행](#장면-행-1-1-1-2-2-1-2-2)). 블록이 없으면 None이라 4-1은 열리지 않습니다.

스위치를 켜면 주문 화면이 `/features`의 `touch`에 함께 보내는 시험 블록 `touch.interaction`(`schema_version` `touch-interaction-pilot-v1`, `frontend/src/features/order/interactionFeatures.ts`)에서 두 값을 규칙표 입력으로 읽습니다. 이 대응은 시연용입니다. 멈춘 시간은 `docs/Touch-Interaction-Contract-Proposal.md` 4.3절(표 아래 문단)이 제안한 대응을 그대로 따르고, 최종 정의는 팀의 터치 계약이 정합니다(`docs/Jev-Integration.md` 10장 '다음'의 남은 항목, 같은 합의안). 주문 화면은 `VITE_TOUCH_INTERACTION_DRAFT=true`(Vite를 시작할 때 읽음)일 때만 이 블록을 보내므로, 멈춘 시간으로 여는 4-2와 옵션 창 대상에는 이 설정이 필요합니다.

- `options_open`은 입력 `options_open`이 됩니다. 메뉴 화면에서 옵션 창이 열려 있으면 4-2 강조가 담기 버튼(`target_id` `cart-add`)을 가리킵니다.
- 멈춘 시간은 입력 `pause_s`(초)가 됩니다. 주문 처리·음성 처리·안내 음성 시간을 뺀 경과 `since_last_input_excluding_system_busy_ms`를 1000으로 나눈 값만 쓰고, 그 값이 없으면 None입니다. 원래 경과(`since_last_input_ms`)나 `dwell_ms`로 대신하지 않습니다.
- `voice_phase`가 `listening`이거나 `microphone_active`가 true이면 `pause_s`는 None입니다. 이용자가 말하는 시간은 위 보정값에서 빠지지 않기 때문입니다.
- 스위치가 꺼져 있거나, 블록이 없거나, 읽는 네 필드나 `schema_version`의 형식이 맞지 않으면 두 입력은 None입니다. 그래서 기본 모드에서는 두 입력이 지금처럼 비어 있습니다. 형식이 틀린 블록도 요청을 실패시키지 않으며, 블록은 ai-engine으로 보내지 않습니다.

시험 블록이 없는 창(옵션 창 상태를 모름)에서 뒤로가기 뒤 메뉴 화면의 4-2 예:

```json
{"preset":"none","requires_confirmation":false,"decided_by":"rule_placeholder","name":"highlight_next_action","decision_id":"d0001","steps_left":2}
```

### 장면 행 (1-1, 1-2, 2-1, 2-2)

시연 스위치를 켜면 규칙표가 AI 엔진 창의 장면 태그, 주문 화면의 시험 블록, 세션 장바구니를 읽어 아래 행을 엽니다. 스위치가 꺼져 있으면 이 입력을 읽지 않으므로 결정과 응답이 이 행들을 더하기 전과 같습니다. 순위가 작은 행이 먼저 열립니다. backend는 화면의 대답을 받지 않으므로(반응을 받는 경로가 아직 없음), 묻기는 대답이 있었든 없었든 `no_response_s`(10초, 파일럿 값) 동안 붙잡고 그 뒤에 거둡니다. 붙잡은 동안에는 그보다 순위가 앞선 3-2 기다림 말고는 다른 행이 열리지 않고(2-2 포함), 거둔 뒤에는 표의 범위 안에서 다시 묻지 않습니다. 규칙표 버전(`RULES_VERSION`)은 이 행들과 4-2의 옵션 창 조건을 더하면서 `rule_table_v1`이 됐고, 스위치를 끈 기록에도 이 버전이 남습니다. Jev 질문 버전(`QUESTIONS_VERSION`)은 2-1 행의 질문과 그 state 키를 더하면서 `jev_questions_v2`가 됐습니다.

| 장면 | 지원 이름 | 형식 | 순위 | 여는 조건 | 다시 묻지 않는 범위 |
| --- | --- | --- | --- | --- | --- |
| 2-2 새 손님 | `continue_or_new_order` | 묻기 | 0 | 이 창에 누름이 있고, 세션 장바구니에 메뉴가 있고, 아직 쓰이지 않은 이용자 바뀜(`user_changed`) 사건이 있음(아래 '이용자 바뀜 사건') | 그 사건 |
| 1-2 앉은 높이 | `lower_screen` | 묻기 | 1 | `seated_height`가 참이거나, `aid_use`가 참이고 근거의 보조기구가 휠체어(`aid_class` `wheelchair`)임. 세션에 누름이 있었고 옵션 창이 닫혀 있으며, 주문 화면이 묻기를 띄울 수 있음(`can_offer`가 거짓이 아님) | 세션 |
| 1-1 보조기구 | `voice_order` | 묻기 | 1 | `aid_use`가 참(보조기구 종류와 관계없음). 세션에 누름이 있었고 옵션 창이 닫혀 있으며, 주문 화면이 묻기를 띄울 수 있고(`can_offer`가 거짓이 아님) 메뉴 화면임. 1-2와 함께 열릴 수 있으면 1-2를 먼저 묻고, 그 묻기가 끝난 뒤 물음 | 세션 |
| 4-1 손 떨림 | `large_button` | 묻기 | 4 | 조건은 그대로이고 `fixes_recent`가 시험 블록에서 옴. 2-1의 크게 보기 묻기와 서로 막음 | 화면 방문 |
| 2-1 저시력 | `large_text` | 묻기 | 6 | 최근 `touch_span_s` 안에 확대 시도가 있고 남은 단계가 있음. 4-1의 크게 보기 묻기와 서로 막음 | 화면 방문 |
| 4-2 헤맴 | `highlight_next_action` | 바로 적용(조용히) | 7 | 메뉴 화면에서 옵션 창이 닫힌 것을 알면(`options_open` false) 열지 않음. 아직 고른 것이 없어 가리킬 대상이 없기 때문이며, 비전 규칙표와 다른 점으로 담당자 확인 전임. 뒤로가기는 옵션 창이 닫힌 메뉴 화면에 닿으므로, 뒤로가기가 든 창도 메뉴 화면에서 끝나고 옵션 창이 닫힌 것을 알면 열지 않음(옵션 창이 열린 채 끝나면 `cart-add`를 가리키며 열림). 메뉴 화면이 아닌 화면에서 끝난 창과 옵션 창 상태를 모르는 창에서는 비전 규칙표처럼 열림 | 화면 방문 |
| 2-1 저시력 | `highlight_large_view_help` | 바로 적용(조용히) | 8 | `face_approach`가 참, 세션에 누름이 있었고 옵션 창이 닫혀 있으며 남은 단계가 있음. 크게 보기가 켜져 있거나 거절되지 않았음 | 화면 방문 |

- 크게 보기는 글자와 버튼을 함께 키우는 지원 하나입니다. `large_text`(2-1)와 `large_button`(4-1)은 그 지원을 묻는 두 행의 이름입니다. 한쪽이 떠 있거나 켜졌거나 거절됐거나 같은 화면 방문에서 거둬졌으면 다른 쪽도 열리지 않습니다.
- 장면 태그: 짝 짓기 구간 안의 엔진 창 가운데 한 창이라도 참이면 참입니다. 그렇지 않으면 가장 늦은 창이 거짓일 때 거짓이고, 그 밖에는 모름입니다. 모름인 태그는 행을 열지 않습니다. `aid_use`의 보조기구 종류는 그 태그를 참으로 준 창의 근거(`aid_head` 사건의 `aid_class`)에서 읽습니다. 종류가 없으면(이전 읽기 방식의 `aid_score` 사건) 1-2의 휠체어 조건만 거짓이고 1-1은 그대로 열립니다.
- 이용자 바뀜 사건: `user_changed`가 참인 엔진 창은 짝 지을 때가 아니라 backend에 도착할 때, 그 태그 근거의 엔진 사건 ID(`main_user_changed@<프레임>`)로 세션에 남깁니다. 그래서 측정할 수 없는 구간에 온 사건도 잃지 않습니다.
  - 엔진의 상황 창(`window_s`)이 구간(`segment_s`)보다 길어 창이 겹치므로, 손님이 한 번 바뀌면 이어지는 엔진 창 여러 개(창 3초·구간 1초이면 세 개쯤)에서 같은 ID로 참입니다. 세션이 이미 받은 ID는 그 바뀜을 다시 본 것이라 새 사건이 아닙니다. 사건 ID는 엔진 실시간 실행기의 한 번 실행 안에서만 서로 다르므로, 주문 화면 세션 하나 안에서 엔진을 다시 시작하면 새 바뀜이 세션이 이미 받은 ID를 달고 올 수 있고, 그 바뀜은 사건으로 치지 않습니다.
  - backend는 받은 ID를 모두 기억하고, 세션의 첫 누름 뒤에 받은 ID 가운데 그 ID를 처음 받은 엔진 창 바로 앞에 받은 엔진 창이 첫 누름이 든 `/features` 창이 끝난 때나 그 뒤에 끝났을 때만 사건으로 둡니다. 앞 창은 그 ID를 싣지 않았으므로 바뀜은 앞 창이 끝난 뒤에 일어났고, 사이에 잃은 창이 있어도 이 판단은 맞습니다. 앞 창이 첫 누름 창이 끝나기 전에 끝났거나 세션의 첫 엔진 창이면 그 ID는 기억만 합니다(2-2를 놓치는 쪽이 덜 나쁨).
  - 사건 ID가 없는 참 태그는 같은 바뀜인지 가를 수 없어 사건으로 치지 않습니다. 엔진은 이 태그가 참일 때 늘 이 ID를 근거에 붙입니다.
  - 사건 뒤의 첫 누름이 행이 열리든 아니든 그 사건을 씁니다. 장바구니에 메뉴가 있으면 2-2를 묻고, 비어 있거나 모르면 묻지 않고 사건만 씁니다. 다른 묻기를 붙잡은 동안의 누름은 사건을 쓰지 않고, 그 묻기를 거둔 뒤의 첫 누름이 정합니다.
- 장바구니: 누름이 있는 창에서 backend가 가진 세션 장바구니의 총수량을 읽습니다. 요청에 새 필드는 없습니다.
- 켜진 설정: 시험 블록 `touch.interaction`의 `ui_settings`(`large_text`·`large_button`·`low_screen`)와 `voice_enabled`가 true인 지원은 이미 켜진 것으로 보고 묻지 않습니다. 블록이 없거나 이 부분의 형식이 맞지 않으면 모름으로 보고, 행은 블록이 없을 때처럼 엽니다.
- 응답: `large_text`는 `preset` `large_text`와 `requires_confirmation` true입니다. `lower_screen`·`voice_order`·`continue_or_new_order`는 맞는 프리셋이 없어 `preset` `none`, `requires_confirmation` true와 `name`으로 묻습니다. `highlight_large_view_help`는 `preset` `none`, `requires_confirmation` false, `name`과 `target_id` `support-toggle`(화면 도움 입구)입니다.

시험 블록 `touch.scene_signals`(형식: 계약의 `TouchSceneSignals`)는 `touch.interaction`과 따로 오는 블록입니다.

- 키는 `schema_version` `touch-scene-signals-pilot-v1`, `near_miss_fix_count`, `zoom_attempt_count`, `can_offer`이고 모두 있어야 합니다. 두 횟수는 0 이상의 정수나 null입니다. 주문 화면은 `VITE_TOUCH_INTERACTION_DRAFT=true`일 때만 보내고, backend는 스위치를 켰을 때만 읽습니다. 스위치가 꺼져 있으면 받기만 하고, 어느 쪽이든 ai-engine으로 보내지 않습니다.
- `can_offer`는 주문 화면이 그 창을 만든 때 묻기를 띄울 수 있었는지(참·거짓·null)입니다. 화면 자신의 조건(옵션·화면 도움·장바구니·처음으로 창과 미리보기 카드가 닫혀 있고, 말로 주문이 꺼져 있고, 안내 메시지가 없고, 주문을 바꿀 수 있음)을 그대로 씁니다. 거짓인 창에서는 1-1과 1-2를 열지 않습니다. 세션에서 한 번만 묻는 두 묻기가 화면에 보이지 않은 채 거둬지지 않게 하려는 것입니다. 다른 행은 이 값을 읽지 않습니다.
- `fixes_recent`는 같은 세션에서 끝 시각이 최근 `touch_span_s`(5초, 파일럿 값) 안에 드는 `/features` 창들의 `near_miss_fix_count` 합입니다. 창 단위로 세므로, 이어지는 창에서 합이 덮는 시간은 1초 창에서 약 5초(2초 창에서는 약 6초)입니다. 그 창 가운데 하나라도 블록이 없거나 값이 null이면 None이고, 4-1은 열리지 않습니다.
- `zoom_attempt`는 같은 창들의 `zoom_attempt_count` 합이 1 이상이면 true, 0이면 false입니다. 합이 None이면 None입니다.
- 다른 `schema_version`이나 형식이 맞지 않는 블록은 읽지 않고, 요청도 실패시키지 않습니다.

첫 누름 뒤 장바구니에 메뉴가 있는 세션에서 이용자 바뀜 뒤 누른 창의 응답 예:

```json
{"preset":"none","requires_confirmation":true,"decided_by":"rule_placeholder","name":"continue_or_new_order","decision_id":"d0001","steps_left":2}
```

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
- 처리 중 중복 요청의 오류·간격, 실패 결과와 성공 키의 보관 기간. DB 모드의 Cart·주문·성공 응답은 트랜잭션으로 원자적 저장을 구현했습니다.
- 서버 주문번호의 장기 보관 범위, 세션 시간 만료·복원, 프론트의 늦은 특징·음성 결과 화면 적용 차단
- 공개 주소의 세션 접근·인증·쿠키 및 배포 정책

복원·장기 보관·정밀 만료·동적 가격 변경은 첫 시연 후순위 방향입니다. 프론트 담당자와 검토한 방향이며 팀 전체 합의는 아직 확인되지 않았습니다. 세부 서버 정책은 담당자가 결정·구현하고 계약에는 합의 후 반영합니다.

