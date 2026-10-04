# AI 서버 초기 실행 환경

Python 3.12 기반 FastAPI 서버입니다. `contract/backend-ai.openapi.yaml`(0.1.0)의 `GET /health`, `POST /v1/analyze`를 제공합니다. backend만 호출하는 내부 서버이며 DB·외부 AI API를 쓰지 않습니다.

판단 모델은 아직 없습니다. `/v1/analyze`는 점수를 계산하지 않고 명세의 예시 값을 그대로 돌려주는 **자리 표시**입니다. 이 결과를 실제 UI 결정에 쓰면 안 됩니다.

## 로컬 실행 (PowerShell)

저장소 루트에서 Python 3.12를 사용해 실행합니다.

```powershell
py -3.12 -m venv ai-server/.venv
ai-server/.venv/Scripts/python.exe -m pip install -r ai-server/requirements.txt
cd ai-server
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

http://127.0.0.1:8001/health 응답:

```json
{"status":"ok","service":"ai-server"}
```

API 문서: http://127.0.0.1:8001/docs

backend를 호스트에서 직접 실행해 연결할 때는 backend의 `AI_SERVER_URL=http://127.0.0.1:8001`로 둡니다.

## POST /v1/analyze

요청·응답 형식은 명세와 같습니다. 요청이 명세와 다르면 422로 거절합니다(필수 필드 누락, 음수 횟수, 0~1을 벗어난 비율, 시간대 없는 시각, 숫자 자리에 문자열).

자리 표시 동작 (`app/inference/placeholder.py`):

| 요청 | 응답 |
| --- | --- |
| 터치(`tap_count`, `back_count`)가 있거나 얼굴이 검출됨(`vision.face_detected=true`) | `measurable=true`, 명세 예시 점수, `model_version=dummy-0.1` |
| 둘 다 없음 | `measurable=false`, `states=null` |

입력 값에 따라 점수가 달라지지 않습니다. 판단 모델을 붙일 때 `placeholder.py`의 `judge()`를 교체합니다.

## Docker

저장소 루트에서 실행합니다.

```powershell
docker build -t capstone-ai-server ./ai-server
docker run --rm -p 127.0.0.1:8001:8001 capstone-ai-server
```

Compose에서는 포트를 외부에 공개하지 않고 backend가 `http://ai-server:8001`로 호출합니다. Compose 파일은 이번 변경에 포함하지 않았습니다.

## 테스트

의존성 설치 후 `ai-server/`에서 실행합니다. 표준 라이브러리 unittest와 FastAPI TestClient를 사용하므로 Docker나 backend가 필요하지 않습니다.

```powershell
python -m unittest discover -s tests -v
```

명세 예시 요청·응답, vision 생략/null, 판단 불가, 세션 ID 유지, 점수 범위, 잘못된 요청 거절, 명세와 같은 operationId를 확인합니다.

## 구조

| 경로 | 역할 |
| --- | --- |
| `app/main.py` | 앱 생성, `/health`, 라우터 등록 |
| `app/modules/analyze/` | `/v1/analyze` 엔드포인트와 요청·응답 모델 |
| `app/inference/` | 모델 로딩·추론 (지금은 자리 표시) |
