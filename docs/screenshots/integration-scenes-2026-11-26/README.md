# 장면 1-1, 1-2, 2-1, 2-2, 4-1의 주문 화면 연결 (2026-11-26)

- 날짜: 2026-11-26
- 대상: `feat/integration` 로컬 작업본(`4170cd7`)의 주문 화면
- 촬영: Windows Microsoft Edge headless, 1080 × 1920 CSS px, device scale factor 1.
- 범위: Vite 개발 서버를 `VITE_TOUCH_INTERACTION_DRAFT=true`로 실행하고, 모든 `/features` 응답을 시연 스위치(`DECISION_SEND_SUPPORT=true`)를 켠 backend의 응답 형식으로 고정했습니다(`decided_by` `rule_placeholder`, `decision_id` `d0001`, `steps_left` 2). backend·ai-engine·카메라는 실행하지 않았으므로, 실제 규칙표나 비전 판단이 이 지원을 골랐다는 뜻은 아닙니다.

주문 바 위의 작은 회색 줄("마지막 응답 지원: ...")은 개발 서버에서만 보이는 상태 줄입니다. 배포 빌드에는 이 줄이 없습니다.

## 대표 화면

| 파일 | 장면 | 화면 |
|---|---|---|
| [01_voice_order_ask_stub.png](01_voice_order_ask_stub.png) | 1-1 보조기구 | `voice_order` 응답. 기존 묻기 바에 마이크 그림과 "말로 주문하시겠어요?" [말로 주문하기] [이대로 두기]를 표시함 |
| [02_lower_screen_ask_stub.png](02_lower_screen_ask_stub.png) | 1-2 앉은 높이 | `lower_screen` 응답. 아래 화살표 그림과 "화면을 내려 드릴까요?" [내리기] [이대로 두기]를 표시함 |
| [03_lower_screen_after_yes_stub.png](03_lower_screen_after_yes_stub.png) | 1-2 앉은 높이 | [내리기]를 누른 뒤. 키오스크가 켠 낮은 화면이며, 위쪽의 [화면 위로 올리기]로 되돌림 |
| [04_help_ring_stub.png](04_help_ring_stub.png) | 2-1 저시력 | `highlight_large_view_help` 응답. 묻지 않고 [화면 도움](`support-toggle`)에 테두리 강조를 둠 |
| [05_restart_dialog_by_answer_stub.png](05_restart_dialog_by_answer_stub.png) | 2-2 새 손님 | `continue_or_new_order` 응답으로 기존 "처음부터 주문할까요?" 창을 엶. 누름으로 열린 옵션 창은 먼저 닫고, 장바구니(아메리카노 1잔)는 그대로 둠 |
| [06_enlarge_ask_stub.png](06_enlarge_ask_stub.png) | 2-1 저시력, 4-1 손 떨림 | 크게 보기 묻기 "글자와 버튼을 크게 해 드릴까요?" [크게 하기] [이대로 두기]. `large_text` 응답(2-1)으로 촬영했고, `large_button` 응답(4-1)도 같은 묻기를 표시함 |
| [07_enlarge_after_yes_stub.png](07_enlarge_after_yes_stub.png) | 2-1 저시력, 4-1 손 떨림 | [크게 하기]를 누른 뒤. 글자와 버튼이 함께 커진 크게 보기 화면 |

크게 보기는 글자와 버튼을 함께 키우는 지원 하나입니다. `large_text`(2-1)와 `large_button`(4-1)은 그 지원을 묻는 두 응답의 이름입니다.
