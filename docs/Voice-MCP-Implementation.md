# 음성·MCP 제어 구현 항목 정리

- 작성일: 2026-10-07
- 상태: 팀 검토 전 제안. 아래 경로·이벤트·도구 이름은 확정된 계약이 아닙니다. 합의 후 `contract/`에 반영합니다.
- 대상: Decision AI·Back-end·Front-end 담당자
- 목적: 음성 입력과 외부 AI의 MCP 제어를 붙이기 위해 누가 무엇을 구현해야 하는지 정리합니다.

## 1. 목표와 원칙

음성으로 요청하면 외부 AI가 자체 MCP 도구로 키오스크를 조작합니다(장바구니 담기, 프리셋 변경, 화면 이동 등).

- **음성 기능은 독립 API입니다.** 녹음을 텍스트로 바꾸고 요청을 접수하는 데까지만 맡습니다. 음성 모드를 언제 켜고 끌지, 화면을 어떻게 바꿀지는 부르는 쪽(프론트, 지원 결정)이 정합니다.
- **MCP는 backend를 제어합니다.** 브라우저를 직접 조작하지 않습니다. 상태의 기준은 backend 하나입니다.
- **터치·음성·MCP가 같은 backend 서비스를 씁니다.** 장바구니 검증, `expected_version`, `Idempotency-Key` 규칙은 [`Product-Cart-Order-API-Draft.md`](Product-Cart-Order-API-Draft.md) 7장을 그대로 따릅니다.
- **외부 AI API(Whisper·ChatGPT)는 backend가 호출합니다.** 수행계획서 구조를 따릅니다. 프론트는 backend와만 통신합니다.
- **AI가 실패해도 터치 주문은 계속 동작해야 합니다.**

## 2. 전체 흐름

```text
[프론트] 녹음 ──▶ [backend] 음성 API ──Whisper──▶ 텍스트
                         │
                         ▼
                   외부 AI(ChatGPT 등) ⇄ MCP 도구 호출
                         │
                         ▼
               backend 서비스 (장바구니·프리셋·화면 상태)
                         │ 상태 변경
                         ▼
[프론트] ◀── SSE 알림 (cart_updated 등) ── 기존 REST로 재조회·화면 반영
```

MCP 방식에서는 상태 변경이 프론트의 요청에서 시작하지 않습니다. HTTP만으로는 backend가 프론트에 먼저 알릴 수 없으므로 **backend → 프론트 알림 채널이 필요합니다.** 이 채널은 음성 전용이 아니고, Jev가 자동으로 프리셋을 제안할 때도 씁니다.

## 3. 구현 항목

| # | 항목 | 담당 | 선행 조건 |
|---|---|---|---|
| 1 | 음성 API | Decision AI | — |
| 2 | MCP 서버·도구 | Decision AI + Back-end | 3 |
| 3 | backend 서비스 계층 | Back-end | 장바구니 초안 합의 |
| 4 | 알림 채널(SSE) | Back-end + Front-end | 3 |
| 5 | 확인 응답 API | Back-end + Front-end | 4 |
| 6 | 프론트 연동 | Front-end | 1, 4, 5 |

### 3.1 음성 API (Decision AI)

| 메서드 | 경로 | 입력 | 출력 |
|---|---|---|---|
| POST | `/api/v1/voice/transcriptions` | multipart 녹음 파일(MediaRecorder webm/opus), `language`(기본 `ko`) | `{ text, duration_ms }` |
| POST | `/api/v1/sessions/{session_id}/voice/requests` | `{ text, screen_id }` | `202 { request_id }` |

- 텍스트 변환은 Whisper를 씁니다. 상태를 바꾸지 않습니다.
- `voice/requests`는 접수만 하고 바로 응답합니다. backend가 외부 AI와 MCP 도구로 처리하고, 결과는 SSE 이벤트(3.4)로 전달합니다.
- 실패하면 `{ code, detail }`을 반환합니다. 예: `audio_too_long`, `unsupported_format`, `stt_unavailable`, `ai_unavailable`
- 프롬프트·지침은 파일로 관리하고, 실험에 쓴 버전을 기록합니다.

### 3.2 MCP 서버·도구 (Decision AI + Back-end)

도구는 backend 서비스 함수와 1:1로 대응합니다. 프론트용 REST API와 MCP 도구가 같은 함수를 부릅니다.

| 도구 | 하는 일 | 대응 서비스 |
|---|---|---|
| `get_menu` | 상품·옵션·판매 가능 여부 조회 | 상품 조회 |
| `get_cart` | 현재 장바구니와 `version` 조회 | 장바구니 조회 |
| `add_cart_item` | 상품 추가 | 장바구니 추가 |
| `update_cart_item` | 수량 변경(절대값) | 장바구니 수량 변경 |
| `remove_cart_item` | 항목 삭제 | 장바구니 삭제 |
| `set_ui_preset` | 프리셋 변경 제안 | UI 상태 |
| `navigate_screen` | 화면 이동 요청 | UI 상태 |
| `request_order_confirmation` | 주문 확정 **확인만 요청**(확정하지 않음) | 확인 요청 |

- 도구는 해당 세션 안에서만 동작하고, 허용 목록에 있는 것만 노출합니다.
- 장바구니 도구는 `expected_version`과 `Idempotency-Key`를 지킵니다. 버전이 충돌하면 최신 장바구니를 다시 조회한 뒤 판단합니다.
- 주문 확정처럼 되돌리기 어려운 동작은 화면에서 사용자 확인(3.5)을 받습니다.
- 한 요청에서 도구를 부를 수 있는 횟수와 전체 처리 시간에 상한을 둡니다.

### 3.3 backend 서비스 계층 (Back-end)

- 상품·장바구니·모의 주문: [`Product-Cart-Order-API-Draft.md`](Product-Cart-Order-API-Draft.md) 기준입니다.
- UI 상태: 세션별 현재 프리셋·화면을 관리하고, 바뀌면 SSE로 알립니다.
- 확인 요청: `confirmation_id`를 발급하고 수락·거절 결과에 따라 후속 동작(주문 확정 등)을 실행합니다.
- 터치 REST API, MCP 도구, Jev 지원 결정이 모두 이 계층을 호출합니다.

### 3.4 알림 채널: SSE (Back-end + Front-end)

`GET /api/v1/sessions/{session_id}/events` (`text/event-stream`)

- backend → 프론트 한 방향만 필요해서 WebSocket보다 단순한 SSE를 씁니다. 브라우저 `EventSource`가 끊기면 자동으로 다시 연결합니다.
- 이벤트에는 **무엇이 바뀌었는지만** 담습니다. 실제 데이터는 프론트가 기존 REST로 다시 조회합니다.

| event | data | 프론트 동작 |
|---|---|---|
| `cart_updated` | `{ version }` | 장바구니 재조회. 가진 버전보다 클 때만 갱신 |
| `ui_changed` | `{ preset?, screen_id? }` | 프리셋 적용 또는 화면 이동 |
| `confirmation_required` | `{ confirmation_id, kind, message }` | 확인 창 표시(주문 확정, 자동 프리셋 제안 등) |
| `assistant_reply` | `{ text }` | 안내 문장 표시·읽기 |

- 모든 이벤트에 SSE `id`와 `occurred_at`를 넣습니다.
- 다시 연결하면 프론트는 장바구니를 재조회합니다. 놓친 이벤트를 다시 보내는 기능은 넣지 않습니다.

### 3.5 확인 응답 API (Back-end + Front-end)

`POST /api/v1/sessions/{session_id}/confirmations/{confirmation_id}` `{ accepted: boolean }`

- 주문 확정 확인과 자동 프리셋 제안(`requires_confirmation`) 수락·거절에 함께 씁니다.
- 수락·거절 결과는 지원 판단 기록에 남깁니다.

### 3.6 프론트 연동 (Front-end)

- MediaRecorder 녹음, 녹음 중·처리 중 상태 표시
- 음성 모드 진입·종료 UI(모드 전환 방식은 프론트가 정함)
- `EventSource` 구독, 재연결 후 장바구니 재조회
- 이벤트에 따라 화면 이동·프리셋 적용·확인 창 표시
- 오래된 버전의 장바구니로 최신 상태를 덮어쓰지 않음

## 4. 구현 순서

1. backend 서비스 계층: 장바구니 초안 합의 후 구현 (3.3)
2. 알림 채널과 확인 응답 API (3.4, 3.5)
3. 음성 API: 텍스트 변환 → 요청 접수 (3.1)
4. MCP 도구 (3.2)
5. 프론트 연동 (3.6)
6. 통합 시나리오 확인 (6장)

1번이 끝나기 전에도 음성 API의 텍스트 변환과 프론트 녹음은 따로 만들 수 있습니다.

## 5. 결정이 필요한 항목

- [ ] TTS 방식: 브라우저 내장 `speechSynthesis` / 서버 TTS(비용 발생)
- [ ] 음성 처리 중 터치 허용 여부
- [ ] 녹음 최대 길이·파일 크기·형식
- [ ] MCP 서버 위치: backend 내부 모듈 / 별도 서비스
- [ ] 외부 AI와 MCP 연결 방식, 도구 호출 횟수·처리 시간 상한
- [ ] 외부 API 월 비용 상한과 사용량 알림
- [ ] SSE 연결 수명, 세션 종료 시 처리

## 6. 확인 시나리오

- "아이스 아메리카노 두 개 담고 결제로 가줘" → `add_cart_item`, `navigate_screen` → `cart_updated`, `ui_changed` → 화면 갱신·이동
- "라떼 하나" → 온도가 빠짐 → `assistant_reply`로 확인 질문
- 음성으로 담는 동안 터치로 수량 변경 → 버전 충돌을 감지하고 최신 상태 표시
- 외부 AI·Whisper 실패 → 안내 후 터치 주문 계속 가능
- 주문 확정 요청 → `confirmation_required` → 사용자 수락 후에만 확정

이 목록은 구현 후 검증할 계획이며, 현재 구현이나 테스트 통과를 의미하지 않습니다.
