# 주문 UI 검증 스크린샷

PR 리뷰에서 배치와 고객 안내를 확인할 수 있도록 대표 UI 화면을 보관하고 PR 본문에도 첨부합니다. 모든 자동 테스트 결과를 커밋하지 않습니다. 이 보관 방향은 2026-10-11 프론트 담당자의 승인으로 정했으며 팀 전체의 영구 보관 정책과 정리 주기는 별도 검토합니다.

## 현재 화면

`bottom-actions-`로 시작하는 이미지는 2026-10-11 변경 후 Edge headless 브라우저에서 촬영했습니다. 기본 API 모드는 고정된 테스트 응답, 샘플 모드는 명시적인 개발 샘플 설정으로 실행했습니다. CSS 픽셀 뷰포트와 브라우저 100% 확대율 기준이며 실제 장비의 F11·물리적 조작 도달 범위를 검증한 사진은 아닙니다.

| 이미지 | 화면·설정 | 뷰포트 |
|---|---|---|
| bottom-actions-menu-default.png | 메뉴·기본 | 1080×1920 |
| bottom-actions-menu-large.png | 메뉴·큰 글씨 + 큰 버튼 | 1080×1920 |
| bottom-actions-review-large.png | 주문 확인·큰 글씨 + 큰 버튼 | 1080×1920 |
| bottom-actions-complete-large.png | 주문 완료·큰 글씨 + 큰 버튼 | 1080×1920 |
| bottom-actions-review-landscape.png | 주문 확인·큰 글씨 + 큰 버튼 | 1365×768 |
| bottom-actions-sample-large.png | 개발 샘플 메뉴·큰 글씨 + 큰 버튼 | 1080×1920 |

하단 버튼의 가림·가로 넘침·목록 끝 스크롤과 설정별 전체 주문 흐름은 브라우저 테스트로 확인합니다. 촬영 환경·검증 범위가 바뀌면 이 표와 PR을 함께 갱신합니다. 자동 실행의 나머지 이미지는 `ORDER_SCREENSHOT_DIR`로 지정한 저장소 밖의 작업 경로에 둡니다.

## 이전 자료

기존 `menu-default`, `review-large`, `retry-recovery-*`, `sample-menu-*` 이미지는 하단 주문 영역·문구 변경 전의 검증 기록입니다. 현재 화면을 나타내는 자료로 사용하지 않습니다.
