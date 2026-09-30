# 백엔드 초기 실행 환경

Python 3.12 기반 FastAPI 실행 뼈대입니다. 상태 확인과 환경변수·CORS 설정만 포함합니다. DB·세션·터치 로그·AI 연동은 후속 작업이며, `/health` 성공이 해당 연결의 성공을 뜻하지 않습니다.

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

예: `CORS_ORIGINS=["http://localhost:5173"]`. 실제 프론트 출처에 맞춰 설정하며 경로나 와일드카드는 허용하지 않습니다. 현재 API는 GET만 지원하므로 CORS도 GET만 허용합니다. CORS는 사용자 인증 기능이 아닙니다.

`.env`에는 실제 비밀값을 넣을 수 있지만 Git에 커밋하지 않습니다. `.env.example`은 항목 설명만 공유합니다. DB·외부 API 설정은 실제 연동 시 추가합니다.

## Docker (실행 검증 보류)

저장소 루트에서 실행하는 명령입니다. Dockerfile만 준비했으며 Docker 빌드·기동 및 서버 3개 통합 테스트는 아직 검증하지 않았습니다.

```powershell
docker build -t capstone-backend ./backend
docker run --rm -p 127.0.0.1:8000:8000 --env-file backend/.env capstone-backend
```

## 참고

- [FastAPI 설정](https://fastapi.tiangolo.com/advanced/settings/)
- [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)
