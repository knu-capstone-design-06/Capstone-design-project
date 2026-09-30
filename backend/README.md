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

## Docker (실행 검증 보류)

저장소 루트에서 실행하는 명령입니다. Dockerfile만 준비했으며 Docker 빌드·기동 및 서버 3개 통합 테스트는 아직 검증하지 않았습니다.

```powershell
docker build -t capstone-backend ./backend
docker run --rm -p 127.0.0.1:8000:8000 --env-file backend/.env capstone-backend
```

## Backend → AI 내부 연동

`app/infrastructure/external/ai_client.py`의 `AiServerClient`가 AI 서버의
`POST /v1/analyze`, `GET /health`를 호출합니다. FastAPI lifespan이 HTTP 연결을
생성·재사용·종료하며 `get_ai_server_client`를 `Depends`로 주입할 수 있습니다.
서버 시작이나 백엔드 `/health` 호출 시에는 AI 서버 접속을 시도하지 않습니다.

`/v1/analyze`는 **AI 서버의 엔드포인트**입니다. 백엔드에 동일 경로를 추가하지
않았습니다. 프론트엔드용 라우터와 세션 생성·인증이 아직 없으므로 실제 사용자
요청에서 AI 분석을 호출하는 흐름은 해당 명세가 확정된 후 연결해야 합니다.

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
- 공통 `TouchFeatures`, `VisionFeatures`, `StateScores`는 **아직 미정**입니다.
  현재는 JSON 객체로 전달·수신하며 내부 필드, 점수 범위, 5개 상태 키를 검증하지
  않습니다. 예시의 `hesitation`을 다른 이름으로 변환하지 않습니다. 공통 스키마
  확정 후 `ai_schemas.py`의 임시 `JsonObject`를 구체 모델로 교체해야 합니다.
  따라서 현재 결과를 검증된 상태 점수로 간주해 실제 UI 결정에 사용하면 안 됩니다.

`ai-server` 호스트 이름은 동일 Docker 네트워크에서 해석됩니다. Compose 설정과
AI 서버 포트 비공개 설정은 이번 백엔드 변경에 포함되지 않습니다. 두 서버를
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
