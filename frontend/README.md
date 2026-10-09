# 프론트엔드 API 연결

`src/shared/api/`는 기존 네 API(상태 확인·연결 확인·세션 생성·특징 전송)와 신규 상품·장바구니·모의 주문 6개 API의 타입·호출 함수를 제공합니다. `contract/frontend-backend.openapi.yaml` 0.3.0에서도 이 형식을 유지합니다. 호출 함수가 있다는 것이 서버 구현 완료를 의미하지는 않습니다. 프론트엔드는 backend와만 통신합니다.

## 주문 API 명세 반영 상태

OpenAPI 0.3.0에 상품 조회, 장바구니 조회·추가·수량 변경·삭제, 모의 주문 확정의 신규 6개 API를 팀 검토용 초안으로 추가했습니다. 요청·응답의 기준 형식은 [OpenAPI](../contract/frontend-backend.openapi.yaml), 설계 이유와 미정 정책은 [주문 API 검토 문서](../docs/Product-Cart-Order-API-Draft.md)를 확인합니다. 신규 operation의 `x-contract-status: draft`는 팀 검토 대기 상태입니다.

주문 operation의 `x-frontend-status: prepared`는 프론트 준비, `x-backend-status: pending`은 서버 구현 대기를 뜻합니다. 기존 연결 API의 구현 상태는 명세에 적힌 최신 원격 main 기준이며 실제 주문 연결 완료를 뜻하지 않습니다. 원격 main ff79f1a는 사용자 요청으로 현재 브랜치에 병합했습니다.

프론트의 상품·Cart·Order 타입·API 호출·화면 처리를 준비했습니다. 서버 API 연결 완료는 아니며 백엔드 구현과 팀 합의 대기입니다. 이전에 프론트 작업 중 추가한 백엔드 코드·설정은 제거했습니다. 공용 OpenAPI는 후속 사용자 요청에 따라 0.3.0 검토 초안으로 갱신했습니다. 성공 응답 후 수량·금액을 확정 표시하고, 네트워크 오류·응답 유실은 같은 키·본문의 ‘처리 결과 확인’으로 재시도합니다. 처리 중에는 변경 버튼을 막습니다. 변경 요청에는 `expected_version`과 `Idempotency-Key`가 필요하며 DELETE의 버전은 쿼리로 전달합니다. 버전 충돌은 최신 장바구니를 표시하고 재확인하며, 신규 오류는 `code`, `detail`, `cart`로 구분합니다.

아래 예시는 기존 연결 API 호출의 사용법입니다. 최신 원격 main `ff79f1a`에서 구현을 확인했으며 사용자 요청으로 현재 브랜치에 병합했습니다.

```ts
import { createBackendApi } from './src/shared/api/index.ts';

// 기존 프록시를 사용합니다. 세션 접근·인증 정책은 백엔드와 별도 합의합니다.
const api = createBackendApi('/backend');
await api.getBackendHealth();
await api.getConnectivity();
const session = await api.createSession();
// 최신 원격 main에는 특징 전송도 구현돼 있으나 주문 화면에서는 호출하지 않습니다.
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

기존 네 API의 HTTP 오류는 `ApiError.status`와 `ApiError.body`로 확인합니다. 404는 `detail` 문자열을 메시지로 사용합니다. 기존 특징 API의 422 응답 본문은 명세에 정의되지 않아 원문을 보존합니다. 신규 주문 API의 422는 별도로 `OrderApiError`에 정의했습니다. 네트워크 오류와 요청 취소는 그대로 전달하며 자동 재시도하지 않습니다. 세션·주문 요청은 15초 타임아웃을 사용하고 `ApiError.retryAfterSeconds`로 서버 재시도 간격을 전달합니다. 반환 타입은 기존 명세를 표현하며 응답에 대한 런타임 스키마 검증은 제공하지 않습니다.

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

상품 선택·서버 Cart 표시·주문 확인·서버 응답의 모의 주문번호 표시와 수동 접근성 설정 코드를 준비했습니다. 실제 주문에는 상품·Cart·Order API를 구현한 백엔드가 필요하며 최신 main에는 아직 해당 API가 없습니다. 미구현 API의 404에는 연결 대기를 표시하고 로컬 상품·주문으로 대체하지 않습니다. 새로고침은 새 세션·빈 장바구니로 시작하며 접근성 설정만 유지합니다. 상세 동작과 수동 확인 절차는 [`src/features/order/README.md`](src/features/order/README.md)에 있습니다. 실제 결제, 주기적인 특징 전송, 음성 및 자동 지원 판단은 연결하지 않았습니다. 완료 화면 복원·서버 재시작 후 보관·정밀 만료·동적 가격 변경은 후순위입니다. API 모듈의 `.ts` 확장자 import를 위해 `noEmit`과 `allowImportingTsExtensions`를 설정했습니다.

## 백엔드 없이 프론트 화면 검증

브라우저 테스트는 `src/features/order/orderApiFixture.mjs`의 고정된 HTTP 응답을 주입합니다. 실제 앱에는 테스트 응답을 연결하지 않습니다. Vite와 외부 Playwright만 있으면 백엔드 서버 없이 주문 화면·오류·재시도를 확인할 수 있습니다. 서버 저장·인증·멱등성을 검증하는 통합 테스트와 구분합니다. [상세 검증 방법](src/features/order/README.md)을 참고합니다.

## 키오스크 화면 개발 및 검증 기준

전시 대상은 G10의 32인치 세로 디스플레이입니다. 아래 설정은 2026-10-06 프론트엔드 담당 사용자가 제공한 실제 장비의 Windows 디스플레이 설정 화면을 기준으로 합니다. 제품소개서의 32인치 표기만으로 해상도를 추정한 값이 아닙니다.

| 항목 | 개발·전시 기준 |
|---|---|
| 디스플레이 해상도 | 가로 1080 × 세로 1920 픽셀 |
| 화면 방향 | 세로 |
| Windows 배율 | 100% |
| 브라우저 확대율 | 100% (`Ctrl+0`으로 초기화) |
| 실제 장비 확인 모드 | 브라우저 F11 전체 화면 |
| 개발 PC 미리보기 | Chrome·Edge의 F12 기기 모드에서 Responsive 1080 × 1920 |

프론트 UI를 구현하거나 수정할 때는 이 세로 화면을 기본 검증 크기로 사용합니다. 개발 PC의 가로 모니터에서 F11만 누른 화면은 가로 해상도를 그대로 사용하므로 전시 배치의 기준이 아닙니다. 기기 미리보기의 `Fit to window`는 세로 화면을 개발 PC에 맞춰 축소해 보여주는 표시 옵션입니다.

### 확인 절차

1. `pnpm dev`로 주문 화면을 실행하고 브라우저 확대율을 100%로 맞춥니다.
2. 개발 PC에서는 F12 → `Ctrl+Shift+M` → Responsive에서 가로 1080, 세로 1920을 설정합니다. F12 도구를 단순히 옆에 열어 둔 화면 대신 지정한 기기 화면 크기로 확인합니다.
3. 상품 목록·분류, 옵션 창, 장바구니, 주문 확인·완료의 잘림·겹침·가로 넘침과 필요한 세로 스크롤을 확인합니다. 스크롤 후에도 주요 조작에 접근할 수 있어야 합니다.
4. 큰 글씨·큰 버튼을 각각 켜고 함께 적용한 상태도 확인합니다. 옵션 선택·수량 조절·담기·주문 확인 버튼을 실제로 조작합니다.
5. 터치 입력 좌표·대상 경계와 스크롤 기록은 이 배치에서 확인합니다. 개발용 로그 창은 주문 배치를 가릴 수 있으므로 창을 접은 상태에서도 확인합니다.
6. 실제 장비에서는 Windows 해상도·방향·배율을 다시 확인하고, 브라우저 확대율 100%·F11 전체 화면에서 최종 검증합니다. 폰트·스크롤바·브라우저 차이를 확인하고 실제 화면의 스크린샷과 결과를 PR에 첨부합니다.

화면 크기는 물리적인 인치 수와 별개입니다. 배치가 예상과 다르면 브라우저 콘솔의 `window.innerWidth`, `window.innerHeight`, `window.devicePixelRatio`로 실제 뷰포트·배율 정보를 확인해 검증 결과에 남깁니다. 실제 장비의 화면 설정이 달라지면 변경 내용을 공유하고 이 기준도 갱신합니다.

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

최신 원격 main에는 `/health`, 연결 확인, 임시 세션 생성, 특징 전송이 구현돼 있습니다. 상품·장바구니·모의 주문은 아직 구현 전이며 현재 프론트 브랜치에 main의 연결·세션 구현을 병합했습니다. 공개 환경의 세션 접근·인증·쿠키·CORS 정책은 백엔드 담당자와 합의할 사항입니다. 프론트 작업에서 서버 설정을 변경하지 않습니다.

로컬 `pnpm dev`도 `/backend/`를 `http://127.0.0.1:8000`으로 전달합니다. 다른 백엔드에 연결하려면 `BACKEND_URL=http://127.0.0.1:8000 pnpm dev`처럼 실행 환경에서 주소를 전달합니다. Docker에서는 Compose의 frontend `BACKEND_URL` 환경변수로 대상 주소를 설정합니다. 주소는 브라우저에 Docker 서비스 이름을 노출하지 않고 프록시에서 사용합니다.

종료는 저장소 루트에서 `docker compose down`으로 합니다.
