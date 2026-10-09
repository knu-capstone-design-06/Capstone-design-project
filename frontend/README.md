# 프론트엔드 API 연결

`src/shared/api/`는 기존 0.1.0의 네 API(상태 확인·연결 확인·세션 생성·특징 전송) 호출 함수를 제공합니다. `contract/frontend-backend.openapi.yaml` 0.2.0에서도 이 형식을 유지합니다. 호출 함수가 있다는 것이 서버 구현 완료를 의미하지는 않습니다. 프론트엔드는 backend와만 통신합니다.

## 주문 API 명세 반영 상태

OpenAPI 0.2.0에 상품 조회, 장바구니 조회·추가·수량 변경·삭제, 모의 주문 확정의 신규 6개 API를 팀 검토용 초안으로 추가했습니다. 요청·응답의 기준 형식은 [OpenAPI](../contract/frontend-backend.openapi.yaml), 설계 이유와 미정 정책은 [주문 API 검토 문서](../docs/Product-Cart-Order-API-Draft.md)를 확인합니다. 신규 operation의 `x-contract-status: draft`는 팀 검토 대기 상태입니다.

현재 API 클라이언트에는 신규 주문 API 타입·호출 함수가 없고 주문 화면은 샘플 상태를 사용합니다. 팀 검토 후 백엔드 구현·샘플 데이터와 함께 상품 조회, 서버 장바구니, 주문 확정을 연결합니다. 변경 요청에는 `expected_version`과 `Idempotency-Key`가 필요하며 DELETE의 버전은 쿼리로 전달합니다. 버전 충돌은 최신 장바구니를 표시하고 재확인하며, 신규 오류는 `code`, `detail`, `cart`로 구분합니다.

아래 예시는 기존 네 API 클라이언트의 사용법입니다.

```ts
import { createBackendApi } from './src/shared/api/index.ts';

// 직접 연결할 때는 실제 backend 주소를 전달합니다.
const api = createBackendApi('http://localhost:8000');
await api.getBackendHealth();
await api.getConnectivity();
const session = await api.createSession();
const result = await api.sendFeatureWindow(session.session_id, {
  screen_id: 'menu_list',
  window_start: '2026-10-01T10:00:00Z',
  window_end: '2026-10-01T10:00:03Z',
  touch: {
    tap_count: 6, miss_tap_count: 3, repeat_tap_count: 2,
    back_count: 0, dwell_ms: 3000,
  },
  vision: null,
});
```

특징은 화면에서 실제 측정한 1~3초 구간의 통계를 전달해야 합니다. 비전 측정이 없으면 `vision: null`을 사용합니다. `dwell_ms`는 밀리초이며 터치 통계는 0 이상의 정수, 비전 비율·신뢰도와 상태 점수는 0~1입니다.

호출자는 `ai_available: false` 또는 `preset: none`이면 화면을 유지하고, `requires_confirmation: true`이면 사용자 수락 후 지원을 적용해야 합니다. 세션이나 화면이 바뀐 뒤 도착한 이전 응답은 적용하지 않아야 합니다. 각 메서드의 마지막 인자로 `AbortSignal`을 전달해 요청을 취소할 수 있습니다.

기존 네 API의 HTTP 오류는 `ApiError.status`와 `ApiError.body`로 확인합니다. 404는 `detail` 문자열을 메시지로 사용합니다. 기존 특징 API의 422 응답 본문은 명세에 정의되지 않아 원문을 보존합니다. 신규 주문 API의 422는 별도로 `OrderApiError`에 정의했습니다. 네트워크 오류와 요청 취소는 그대로 전달하며 세션 생성 등을 자동 재시도하지 않습니다. 반환 타입은 기존 명세를 표현하며 응답에 대한 런타임 스키마 검증은 제공하지 않습니다.

검증(Node.js 22.18 이상, 추가 의존성 없음):

```sh
node --test frontend/src/shared/api/client.test.mjs
```

## 샘플 주문 화면 실행

React·Vite·TypeScript로 샘플 주문 화면을 실행할 수 있습니다. Node.js 22.18 이상에서 `frontend/`로 이동한 뒤 실행합니다.

```sh
pnpm install
pnpm dev
```

`pnpm build`로 TypeScript 검사와 배포 빌드를, `pnpm test`로 API 및 주문 상태 테스트를 실행합니다. 의존성 버전은 `pnpm-lock.yaml`에 기록합니다.

상품 선택·장바구니·주문 확인·모의 결제, 새로고침 후 상태 복원과 수동 접근성 설정을 제공합니다. 상세 동작과 수동 확인 절차는 [`src/features/order/README.md`](src/features/order/README.md)에 있습니다. 실제 주문 API, 주기적인 특징 수집, 음성 및 자동 지원 판단은 아직 연결하지 않았습니다. API 모듈의 `.ts` 확장자 import를 위해 `noEmit`과 `allowImportingTsExtensions`를 설정했습니다.

## Docker 실행과 백엔드 연결

Docker Desktop의 Linux 엔진과 WSL 통합을 활성화한 뒤 저장소 루트에서 실행합니다.

```sh
docker compose up --build -d
curl --fail http://127.0.0.1:8080/backend/health
```

화면은 `http://127.0.0.1:8080`에서 열립니다. 상태 확인 응답은 `{"status":"ok","service":"backend"}`입니다. 이는 백엔드 프로세스 상태만 확인하며 DB·AI 연결을 보장하지 않습니다.

프론트 이미지는 Node.js에서 빌드한 정적 파일을 Nginx로 제공합니다. 브라우저의 `/backend/health` 요청은 Nginx가 Docker 내부 `http://backend:8000/health`로 전달합니다. `/backend/api/v1/...`도 같은 방식으로 전달하며 백엔드 오류 응답을 그대로 반환합니다. 화면 경로는 `index.html`로 처리합니다.

화면 코드에서 기본 프록시 클라이언트를 사용할 수 있습니다.

```ts
import { backendApi } from './src/shared/api/index.ts';

const health = await backendApi.getBackendHealth();
```

현재 백엔드에는 `/health`와 연결 확인·임시 세션 생성·특징 전송 API가 구현돼 있습니다. 주문 화면은 아직 이 API를 호출하지 않고 계속 샘플 데이터와 모의 결제를 사용합니다.

로컬 `pnpm dev`도 `/backend/`를 `http://127.0.0.1:8000`으로 전달합니다. 다른 백엔드에 연결하려면 `BACKEND_URL=http://127.0.0.1:8000 pnpm dev`처럼 실행 환경에서 주소를 전달합니다. Docker에서는 Compose의 frontend `BACKEND_URL` 환경변수로 대상 주소를 설정합니다. 주소는 브라우저에 Docker 서비스 이름을 노출하지 않고 프록시에서 사용합니다.

종료는 저장소 루트에서 `docker compose down`으로 합니다.
