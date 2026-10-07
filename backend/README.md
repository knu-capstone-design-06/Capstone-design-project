# 백엔드 초기 실행 환경

Python 3.12 기반 FastAPI 백엔드입니다. 상태 확인, 환경변수·CORS 설정 및 내부 AI 서버 호출 클라이언트를 포함합니다. DB·세션·프론트엔드 요청 처리는 후속 작업이며, `/health` 성공이 DB나 AI 연결의 성공을 뜻하지 않습니다.

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

[프론트엔드 ↔ 백엔드 OpenAPI](../contract/frontend-backend.openapi.yaml)는 0.2.0이며 기존 0.1.0의 네 API 형식을 유지합니다. 상품 조회, 세션 장바구니 조회·추가·수량 변경·삭제, 모의 주문 확정의 신규 6개 API를 `x-contract-status: draft`로 추가했습니다. 이 명세 수정에서는 백엔드 라우터·서비스·DB를 구현하지 않았습니다. 실행 중인 FastAPI `/docs`는 실제 라우터에서 생성되므로 저장소 YAML 수정만으로 신규 경로가 표시되지는 않습니다.

설계 이유·미정 정책은 [주문 API 검토 문서](../docs/Product-Cart-Order-API-Draft.md)를 확인합니다. 팀 검토 후 상품·옵션·가격 검증, 서버 장바구니, 모의 주문 스냅샷을 구현하고 프론트 타입·호출 함수·화면과 샘플 데이터를 함께 맞춥니다. 장바구니 버전 확인·변경과 멱등성 성공 응답 저장, 주문 생성·장바구니 비우기는 각각 원자적 처리가 필요합니다. 신규 API 검증 오류는 `OrderApiError` 형식으로 반환하되 기존 API 오류 형식은 유지합니다.

세션 수명·접근 정책, 멱등성 키 보관·처리 중·실패 응답 정책, 가격 갱신 시 버전 처리, 주문번호·주문 조회·영속 보관은 팀 검토 항목입니다. 모의 주문에는 실제 결제·재고 차감을 포함하지 않습니다.

브라우저에서 백엔드를 다른 출처로 직접 호출하는 구현을 추가할 때는 POST·PATCH·DELETE와 `Idempotency-Key` 헤더의 CORS 허용도 함께 검토합니다. 같은 출처의 `/backend/` 프록시를 통한 호출과 구분하며, 이번 명세 수정에서는 현재 CORS 설정을 바꾸지 않습니다.

## 환경변수

`backend/.env` 또는 프로세스 환경변수에서 읽으며 프로세스 환경변수가 우선합니다. 설정 변경 후 서버를 다시 시작합니다. 빈 값은 기본값을 사용합니다.

| 변수 | 기본값 | 형식 |
| --- | --- | --- |
| APP_NAME | Capstone Backend | 문자열 |
| DOCS_ENABLED | true | true / false |
| CORS_ORIGINS | localhost:5173, localhost:3000의 HTTP 출처 | JSON 배열 |
| AI_SERVER_URL | http://ai-server:8001 | AI 서버 HTTP(S) 출처 |
| AI_SERVER_TIMEOUT_SECONDS | 2 | 양의 유한한 초 단위 숫자 |

예: `CORS_ORIGINS=["http://localhost:5173"]`. 실제 프론트 출처에 맞춰 설정하며 경로나 와일드카드는 허용하지 않습니다. 현재 API는 GET만 지원하므로 CORS도 GET만 허용합니다. CORS는 사용자 인증 기능이 아닙니다.

`.env`에는 실제 비밀값을 넣을 수 있지만 Git에 커밋하지 않습니다. `.env.example`은 항목 설명만 공유합니다. DB·외부 API 설정은 실제 연동 시 추가합니다.

## Docker Compose

루트 Compose에 백엔드와 AI 서버가 포함돼 있습니다. Docker 엔진을 실행한 뒤 저장소 루트에서 두 서비스를 함께 시작합니다.

```powershell
docker compose up --build
```

백엔드는 `http://127.0.0.1:8000`, AI 서버는 Docker 내부의 `http://ai-server:8001`을 사용합니다. Compose에는 `env_file`이 없고 이미지에도 `.env`가 없으므로, 로컬 직접 실행과 달리 `backend/.env`는 읽지 않습니다. 필요한 값은 실행 환경에서 컨테이너에 주입합니다.

기존 두 서버 실행·통신 검증 기록은 [PR #14](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/14)를 참고합니다. 2026-10-07 문서 정리에서는 Docker 테스트를 재실행하지 않았습니다. 프론트엔드는 Compose에 포함되지 않으며 세 서비스 전체 연동은 후속 작업입니다.

## Backend → AI 내부 연동

`app/infrastructure/external/ai_client.py`의 `AiServerClient`가 AI 서버의
`POST /v1/analyze`, `GET /health`를 호출합니다. FastAPI lifespan이 HTTP 연결을
생성·재사용·종료하며 `get_ai_server_client`를 `Depends`로 주입할 수 있습니다.
서버 시작이나 백엔드 `/health` 호출 시에는 AI 서버 접속을 시도하지 않습니다.

`/v1/analyze`는 **AI 서버의 엔드포인트**입니다. 백엔드에 동일 경로를 추가하지
않았습니다. 프론트엔드용 라우터와 세션 생성·인증이 아직 없으므로 실제 사용자
요청에서 AI 분석을 호출하는 흐름은 `contract/frontend-backend.openapi.yaml`에 맞춰 후속 구현해야 합니다.

서비스 계층에서 사용할 패턴:

```python
from app.infrastructure.external.ai_client import AiServerClient
from app.infrastructure.external.ai_schemas import AnalyzeRequest


async def analyze_window(ai: AiServerClient, window: AnalyzeRequest):
    result = await ai.analyze(window)
    if result is None or not result.measurable:
        return None  # 판단을 생성하지 않고 현재 흐름 유지
    return result
```

- `session_id`는 백엔드가 관리하는 세션 값으로 채워 전달합니다. 이 클라이언트는
  세션을 생성하거나 인증하지 않습니다.
- 기본 2초는 HTTP I/O 제한과 전체 호출 제한에 모두 적용합니다. 자동 재시도는 없습니다.
- 연결 오류, 타임아웃, HTTP 오류(422 포함), 잘못된 JSON·응답 구조, 세션 불일치는
  `None`을 반환합니다. 정상 상태 점수를 임의로 만들어 반환하지 않습니다.
- `measurable=false`는 유효한 응답으로 유지하고 `states`는 `None`입니다.
  `measurable=true`인데 점수가 없거나, false인데 점수가 있으면 응답 오류로 처리합니다.
  OpenAPI의 required 목록에 따라 false 응답에서 states 생략도 허용합니다.
- 호출자의 취소는 상위로 전달합니다. 로그에는 오류 종류만 기록합니다.
- 시간 필드는 시간대가 있는 날짜·시간이어야 하며 종료 시각이 시작 시각보다 뒤여야 합니다.
- `TouchFeatures`, `VisionFeatures`, `StateScores`의 현재 형식은
  `contract/frontend-backend.openapi.yaml`(0.2.0, 기존 0.1.0 형식 유지)에 정의돼 있습니다. 다만 비전
  세부 특징과 터치 통계 계산 기준에는 팀 검토 항목이 남아 있습니다.
  백엔드 구현은 아직 JSON 객체로 전달·수신하며 내부 필드, 점수 범위, 5개 상태
  키를 검증하지 않습니다. 예시의 `hesitation`을 다른 이름으로 변환하지 않습니다.
  `ai_schemas.py`의 임시 `JsonObject`를 계약에 맞는 구체 모델로 교체하는 작업이 남아 있습니다.
  따라서 현재 결과를 검증된 상태 점수로 간주해 실제 UI 결정에 사용하면 안 됩니다.

`ai-server` 호스트 이름은 동일 Docker 네트워크에서 해석됩니다. 루트 Compose는
AI 서버의 호스트 포트를 공개하지 않습니다. 두 서버를
호스트에서 직접 실행할 때만 `AI_SERVER_URL=http://127.0.0.1:8001`로 변경합니다.

## 테스트

의존성 설치 후 `backend/`에서 실행합니다. 표준 라이브러리 unittest와 HTTPX
MockTransport를 사용하므로 실제 AI 서버·DB·Docker가 필요하지 않습니다.

```powershell
python -m unittest discover -s tests -v
```

정상 요청·응답, vision 생략/null, 판단 불가, HTTP 오류, 연결 실패, 전체 타임아웃,
잘못된 응답·세션 불일치, 호출 취소, health 응답 및 연결 종료를 확인합니다.

## 참고

- [FastAPI 설정](https://fastapi.tiangolo.com/advanced/settings/)
- [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)
