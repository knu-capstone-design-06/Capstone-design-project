# 개발용 터치 로그 UI 제거 검증

- 날짜: 2026-11-25
- 기준: 최신 `origin/main`의 `c06085e`를 반영한 `design` 브랜치
- 변경: ‘터치 로그 보기’ 버튼과 확인 창·전용 CSS 제거
- 유지: 원시 터치 수집·로컬 보관·요약·파일럿 집계·서버 전송·콘솔 확인 API

## 대표 화면

| 파일 | 상태 |
|---|---|
| [default.png](default.png) | 기본 크기·기본 높이, 커피 분류 |
| [large-low.png](large-low.png) | 큰 글씨 200%·큰 버튼·낮은 화면, 커피 분류 |

두 화면 모두 개발용 로그 버튼·확인 창이 없습니다. Linux의 Chromium headless에서 뷰포트 1080×1920, 기본 배율로 촬영했습니다. 고정 상품·세션·장바구니 API 응답을 사용했으며 실제 매장 데이터가 아닙니다. 낮은 화면의 상품 목록은 기존 내부 스크롤 영역입니다.

## 확인 방법과 결과

Node.js 22.22.2, 기존 프론트 의존성과 외부 Playwright 1.64.1을 사용했습니다. 의존성을 추가하거나 변경하지 않았습니다.

| 검사 | 결과 |
|---|---|
| `frontend/`의 `npm run build` | TypeScript·Vite 빌드 통과 |
| `frontend/`의 `npm test` | 158개 통과 |
| `voiceWait.integration.test.mjs` | 음성·터치 통합 6개 통과 |
| `touchLog.browser.test.mjs`, `accessibility.browser.test.mjs` | 44개 통과 |
| `touchFeature.browser.test.mjs` | 11개 통과, 실서버 URL을 요구하는 1개 생략 |
| `order.browser.test.mjs`, `backendSupport.browser.test.mjs`, `voiceMode.browser.test.mjs` | 106개 통과, 샘플·배포 모드 포함 |

기본·큰 글씨·큰 버튼·동시 적용과 낮은 화면 켜기·끄기의 8가지 조합에서 개발용 UI가 없고 터치 수집과 문서 높이·가로 폭이 유지되는지 확인했습니다. 콘솔의 원시 요약·반복 기준 비교·JSON 내보내기, 새 세션 분리·1,000개 버퍼 제한·실제 터치 스크롤도 검사했습니다. 기본 통계 5개의 단일 전송과 선택적 확장 통계, 샘플 모드 전송 차단을 고정 API 응답으로 확인했습니다.

주문·장바구니 변경·주문 완료·새 주문 시작·응답 유실 재시도·버전 충돌, 서버 지원 제안과 수락 후 설정 적용, 음성 입력·자동 응답 읽기·재청취·창이 열리는 동안의 보류도 기존 검사로 확인했습니다. 단위·통합 164개와 브라우저 161개가 통과했으며, 실서버 URL이 필요한 브라우저 검사 1개는 생략했습니다. 콘솔 파일럿 정책 인자를 정리한 뒤 해당 검사 1개를 재실행해 통과했습니다(합계에 중복 포함하지 않음).

`useTouchLog.ts`, `touchLog.ts`, `touchLogSummary.ts`, `touchLogFeatures.ts`, `interactionFeatures.ts`, `touchFeatureTransport.ts`와 음성·공용 API·앱 코드는 기준 커밋과 동일합니다. 배포 결과물에서 삭제한 컴포넌트·스타일·버튼 문구가 남지 않은 것도 확인했습니다.

실제 백엔드·외부 AI·마이크·스피커·시험 기기는 검증 범위에 포함하지 않습니다. Windows 배율·브라우저 확대율 100%와 F11 전체 화면의 실기기 최종 확인은 별도로 필요합니다.
