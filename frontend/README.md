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

현재 저장소의 React 진입 파일과 패키지 설정은 비어 있습니다. 이번 추가는 API 연결 모듈이며 실행 가능한 화면, 주기적인 특징 수집, 지원 UI 적용은 포함하지 않습니다. TypeScript에서 `.ts` 확장자 import를 사용하므로 추후 Vite 구성 시 `noEmit`과 `allowImportingTsExtensions`를 설정해야 합니다.
