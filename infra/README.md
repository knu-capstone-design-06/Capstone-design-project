# 로컬 Docker 통합 환경

Docker Desktop의 Linux 컨테이너 엔진이 실행 중이어야 합니다. 저장소 루트에서:

```powershell
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
docker compose ps
```

프로젝트 이름은 `capstone-local`입니다. frontend, backend, ai-server가 모두 healthy인지 확인합니다.

| 주소 | 용도 |
| --- | --- |
| http://127.0.0.1:5173 | 빌드된 프론트엔드 샘플 화면 |
| http://127.0.0.1:5173/healthz | 프론트엔드 웹서버 상태 |
| http://127.0.0.1:5173/backend/health | 프론트엔드 웹서버를 거친 백엔드 상태 |
| http://127.0.0.1:8000/health | 백엔드 직접 상태 확인 |
| http://127.0.0.1:8000/docs | 백엔드 API 문서 |

브라우저는 Docker 내부 이름을 해석할 수 없습니다. Compose에서 API 모듈을 사용할 때
`createBackendApi('/backend')`를 사용하면 같은 출처의 Nginx 프록시를 통해 백엔드에 연결됩니다.
예를 들어 `/backend/api/v1/sessions`는 백엔드의 `/api/v1/sessions`로 전달됩니다.
이 접두어는 로컬 웹서버 경로이며 `contract/`의 API 경로를 변경하지 않습니다.
정적 앱이므로 소스를 바꾸면 이미지를 다시 빌드해야 합니다. 개발 중 자동 반영은 기존 `pnpm dev`를 사용합니다.

현재 주문 화면은 샘플 데이터로 동작합니다. 세션·특징 전송·connectivity API는 아직
미구현이므로 실제 주문·DB·지원 판단까지 연결된 것은 아닙니다. 미구현 API는 프록시에서도
백엔드의 404를 그대로 반환합니다. AI 서버는 예시 점수(dummy-0.1)를 반환합니다.

## 환경변수

| 항목 | 기본값 | 적용 위치 |
| --- | --- | --- |
| FRONTEND_PORT | 5173 | 호스트 공개 포트 |
| BACKEND_PORT | 8000 | 호스트 공개 포트 |
| AI_SERVER_TIMEOUT_SECONDS | 2 | 백엔드에 전달되는 전체 호출 제한(초) |

PowerShell 환경변수 또는 루트 `.env`로 위 값을 바꿀 수 있습니다. Compose는 이 값을
치환한 뒤 명시된 `environment`만 컨테이너에 전달합니다. `backend/.env`는 자동으로
읽지 않으며 어느 이미지에도 `.env`를 넣지 않습니다. 실제 비밀값은 Git에 올리지 않습니다.
포트를 바꿔도 컨테이너 내부 주소 `http://ai-server:8001`은 유지합니다.

AI 서버의 8001은 호스트에 바인딩하지 않습니다. frontend와 backend의 포트는
127.0.0.1에만 바인딩하므로 현재 구성은 이 PC의 로컬 검증용입니다.

## 검증과 관리

세 서버가 healthy가 된 뒤 PowerShell에서:

```powershell
./infra/check-local.ps1
```

이 검사는 화면·상태 응답, 프록시의 404 보존, 백엔드의 실제 AiServerClient를 통한
AI 정상·측정 불가 응답과 잘못된 요청(422)을 확인합니다. 실제 주문이나 영상 처리는 하지 않습니다.

```powershell
docker compose logs --tail 100
docker compose stop
docker compose start
```

`unless-stopped`는 프로세스 종료 시 재시작하고 수동으로 중지한 컨테이너는 그대로 둡니다.
Docker 엔진이 다시 시작돼야 재부팅 후 컨테이너도 복구할 수 있습니다. unhealthy 판정만으로
컨테이너가 자동 재시작되는 것은 아닙니다. health 기반 의존성은 최초 기동 순서를 제어하며,
실행 중 의존 서버 장애는 클라이언트가 처리해야 합니다.

각 컨테이너 로그는 파일당 10MB, 최대 3개로 회전합니다. 컨테이너와 네트워크를 정리하려면
이 저장소 루트에서 `docker compose down`을 사용합니다. 이 구성에는 DB 볼륨이 없습니다.
