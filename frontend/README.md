# 프론트엔드 API 연결

`src/shared/api/`는 `contract/frontend-backend.openapi.yaml` 0.1.0의 네 API를 제공합니다. 프론트엔드는 backend와만 통신합니다.

```ts
import { createBackendApi } from './src/shared/api/index.ts';

// 실제 실행 환경의 backend 주소를 전달합니다.
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

HTTP 오류는 `ApiError.status`와 `ApiError.body`로 확인합니다. 404는 `detail` 문자열을 메시지로 사용합니다. 422 응답 본문은 명세에 정의되지 않아 원문을 보존합니다. 네트워크 오류와 요청 취소는 그대로 전달하며 세션 생성 등을 자동 재시도하지 않습니다. 반환 타입은 명세를 표현하며 응답에 대한 런타임 스키마 검증은 제공하지 않습니다.

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
