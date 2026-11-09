# PR #70 피드백 검증 화면

2026-11-09 개발 PC의 Edge 자동화, 1080×1920 뷰포트에서 고정 상품·세션 응답으로 촬영했습니다. 실제 G10·마이크·OpenAI·백엔드 검증이 아닙니다.

모두 낮은 화면·200% 글씨·화면 도움을 켠 상태입니다. 머리글과 도움 패널은 각자 스크롤하며 본문에 상품을 표시할 공간을 남깁니다. 상품 카드가 본문보다 크면 본문 스크롤로 나머지 내용을 확인합니다.

| 큰 버튼 | 고대비 | 화면 |
| --- | --- | --- |
| 꺼짐 | 꺼짐 | [화면](low-large-false-false.png) |
| 꺼짐 | 켜짐 | [화면](low-large-false-true.png) |
| 켜짐 | 꺼짐 | [화면](low-large-true-false.png) |
| 켜짐 | 켜짐 | [화면](low-large-true-true.png) |

재현: Vite 실행 후 외부 Playwright 경로를 `PLAYWRIGHT_MODULE`, 실행 주소를 `ORDER_BROWSER_URL`, 이 폴더를 `FEEDBACK_SCREENSHOT_DIR`로 지정하고 `node --test frontend/src/features/order/reviewFeedback.browser.test.mjs`를 실행합니다. 프로젝트 의존성은 추가하지 않습니다.

실제 장비에서는 Windows·브라우저 배율 100%와 F11 전체 화면에서 글씨·버튼·스크롤 도달 범위를 별도 확인해야 합니다. 빛·파형 시안은 정지 이미지 제안 상태이며, 채택 시 듣는 중/처리 중 구분·고대비·낮은 화면·동작 줄이기·깜박임을 별도 검증해야 합니다.
