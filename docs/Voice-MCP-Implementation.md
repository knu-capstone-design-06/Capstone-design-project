# 음성·MCP 제어 구현 항목 정리

- 작성일: 2026-10-07 (수정: 2026-10-07 STT를 Chrome 내장 인식 기본으로 변경, 2026-10-13 구현 상태 반영)
- 상태: 음성 API(PR #36)와 frontend 음성 입력(PR #42)은 구현했습니다. MCP 도구 실행·SSE·확인 응답 API는 팀 검토 전 제안이며, 그 경로·이벤트·도구 이름은 확정된 계약이 아닙니다. 합의 후 `contract/`에 반영합니다. 현재 상태는 7장을 봅니다.
- 대상: Decision AI·Back-end·Front-end 담당자
- 목적: 음성 입력과 외부 AI의 MCP 제어를 붙이기 위해 누가 무엇을 구현해야 하는지 정리합니다.

## 1. 목표와 원칙

음성으로 요청하면 외부 AI가 자체 MCP 도구로 키오스크를 조작합니다(장바구니 담기, 프리셋 변경, 화면 이동 등).

- **음성 기능은 독립 API입니다.** 인식된 텍스트로 요청을 접수하는 데까지만 맡습니다. 음성 모드를 언제 켜고 끌지, 화면을 어떻게 바꿀지는 부르는 쪽(프론트, 지원 결정)이 정합니다.
- **MCP는 backend를 제어합니다.** 브라우저를 직접 조작하지 않습니다. 상태의 기준은 backend 하나입니다.
- **터치·음성·MCP가 같은 backend 서비스를 씁니다.** 장바구니 검증, `expected_version`, `Idempotency-Key` 규칙은 [`Product-Cart-Order-API-Draft.md`](Product-Cart-Order-API-Draft.md) 7장을 그대로 따릅니다.
- **STT(음성 → 텍스트)는 프론트의 Chrome 내장 Web Speech API를 기본으로 합니다.** 실시간으로 인식되고 말 끝을 자동으로 감지하며 비용이 없습니다. 서버 STT(Whisper)는 사용하지 않습니다. Chrome 인식을 쓸 수 없으면 터치로 주문합니다.
- **인식이 조금 틀려도 OpenAI가 맥락으로 해석합니다.** 인식 후보와 신뢰도, 메뉴 목록(MCP 도구)을 함께 주고, 애매하면 확인 질문을 돌려줍니다.
- **외부 AI API(OpenAI)는 backend가 호출합니다.** 프론트는 backend와만 통신합니다.
- **AI가 실패해도 터치 주문은 계속 동작해야 합니다.**

## 2. 전체 흐름

```text
[프론트] 마이크 → Chrome 음성 인식 → 텍스트·후보·신뢰도
                         │ POST voice/requests
                         ▼
                  [backend] 음성 API (202 접수)
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

명세: [`contract/voice.openapi.yaml`](../contract/voice.openapi.yaml)

| 메서드 | 경로 | 입력 | 출력 |
|---|---|---|---|
| POST | `/api/v1/sessions/{session_id}/voice/requests` | `{ text, alternatives[], screen_id }` + `Idempotency-Key` | `202 { request_id }` |
| GET | `/api/v1/sessions/{session_id}/voice/requests/{request_id}` | — | `{ status, reply_text, tool_calls, actions, error }` |

- `voice/requests`는 접수만 하고 바로 응답합니다. backend가 OpenAI API로 이용자(세션)별 최근 대화 맥락과 함께 해석해 MCP 장바구니 도구의 입력(`tool_calls`)을 만들고, 상태 조회로 전달합니다. 음성 API는 도구를 실행하지 않습니다.
- 확실하면 `completed`, 애매하면 이해한 내용을 `needs_confirmation`으로 짧게 확인받고(예: "아이스 아메리카노 2잔 담을까요?"), 정할 수 없으면 `needs_clarification`으로 묻습니다. 키오스크에게 한 말이 아니면(잡담·일행과의 대화) `ignored`로 답하고 아무것도 하지 않습니다. 대답은 같은 세션의 다음 음성 요청으로 받습니다. 확인 UI와 적용 시점은 부르는 쪽이 정합니다.
- `alternatives`는 Chrome 인식 후보와 신뢰도입니다(`maxAlternatives`). OpenAI 해석 시 맥락으로 함께 씁니다.
- 상태 조회는 SSE가 준비되기 전이나 연결이 끊겼을 때 음성 기능을 확인하는 용도입니다.
- 실패하면 `{ code, detail }`을 반환합니다. 예: `request_in_progress`, `ai_unavailable`
- 프롬프트·지침은 파일로 관리하고, 실험에 쓴 버전을 기록합니다. 현재는 `prompts/interpret_v2.md`입니다.

### 3.2 MCP 서버·도구 (Decision AI + Back-end)

MCP 서버는 외부 AI의 도구 호출을 backend 호출로 바꿔 주는 역할입니다.

- **도구 이름·설명·입력 형식과 도구를 묶는 단위는 MCP 담당이 정합니다.** backend의 함수 이름이나 API 경로와 맞출 필요가 없습니다.
- **backend와 맞춰야 하는 것은 데이터 형식입니다.** 도구가 backend에 넘기는 값(`product_id`, `temperature`, `quantity`, `expected_version` 등)은 backend가 받는 형식과 같아야 합니다. 기준은 [`Product-Cart-Order-API-Draft.md`](Product-Cart-Order-API-Draft.md)이고, backend 형식이 바뀌면 도구도 함께 고칩니다.
- 도구와 backend API가 1:1일 필요는 없습니다. 예를 들어 도구 하나가 장바구니를 조회해 `version`을 얻은 뒤 추가 API를 부르면, AI가 버전을 직접 다루지 않아도 됩니다.
- AI는 이름보다 **설명**을 보고 도구를 고르므로 설명을 명확하게 씁니다. 이름은 영문·숫자·밑줄로 짓고 서버 안에서 겹치지 않게 합니다.

아래는 필요한 기능의 예시이며, 도구 이름은 확정이 아닙니다.

| 도구(예시) | 하는 일 | 사용하는 backend 기능 |
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

구현됨 (`frontend/src/features/voice/`, AI 담당, 화면 요소 없음. 7.1 참고)

- Chrome `SpeechRecognition`(ko-KR) 인식, 말하는 중 부분 텍스트(`partialText`)와 최종 인식 문장
- 인식 후보·신뢰도와 함께 `voice/requests` 호출, 상태 조회, 듣는 중·처리 중 상태(`phase`)
- Chrome 인식 지원 여부 판별(`isSpeechSupported`)

남음 (Front-end)

- 위 상태를 화면에 표시하고, Chrome 인식을 쓸 수 없으면 음성 버튼을 숨기거나 비활성화하고 터치 주문으로 안내
- 음성 모드 진입·종료 UI(모드 전환 방식은 프론트가 정함)
- `EventSource` 구독, 재연결 후 장바구니 재조회
- 이벤트에 따라 화면 이동·프리셋 적용·확인 창 표시
- 오래된 버전의 장바구니로 최신 상태를 덮어쓰지 않음

2026-10-13 프론트에서 수동 낮은 화면을 구현했습니다. 하단의 ‘낮은 화면’으로 켜고 ‘기본 높이’로 높이만 되돌리며, 다른 설정·Cart를 유지합니다. [수동 화면의 동작·검증](../frontend/src/features/order/README.md#낮은-화면)을 참고합니다.

로컬 `lowScreen` 설정은 현재 `contract/frontend-backend.openapi.yaml`의 `UIPreset`과 `contract/voice.openapi.yaml`의 도구 입력에 포함되지 않습니다. ‘화면 좀 내려줘’를 처리하거나 `set_ui_preset`·`ui_changed`로 높이를 바꾸는 기능은 아직 미구현입니다. 연결할 때는 프리셋 값, 기존 수동 설정과의 조합, 사용자 수락·해제·복귀 규칙과 상태 공유 범위를 프론트·백엔드·AI 담당자가 합의한 뒤 계약과 구현을 함께 맞춥니다.

## 4. 구현 순서

1. backend 서비스 계층: 상품·장바구니·모의 주문은 완료(PR #40). UI 상태·확인 요청은 남음 (3.3)
2. 알림 채널과 확인 응답 API (3.4, 3.5)
3. 음성 API: 요청 접수·상태 조회 완료(PR #36) (3.1)
4. MCP 도구 (3.2)
5. 프론트 연동: 인식·요청·상태 조회는 완료(PR #42), 화면 연결·SSE는 남음 (3.6)
6. 통합 시나리오 확인 (6장)

1번이 끝나기 전에도 프론트의 Chrome 음성 인식과 음성 요청 접수·상태 조회는 따로 만들 수 있습니다.

## 5. 결정이 필요한 항목

- [ ] TTS 방식: 브라우저 내장 `speechSynthesis` / 서버 TTS(비용 발생)
- [ ] 음성 처리 중 터치 허용 여부
- [ ] STT 변경 공유: 수행계획서는 Whisper 기준이므로 Chrome 내장 인식으로 바꾸는 것을 멘토·팀과 공유하고 보고서에 반영
- [ ] Chrome 인식은 음성을 Google 서버로 보냄: 실험 참가자 동의 안내에 포함할지
- [ ] 제한값: 텍스트 500자, 후보 5개, 세션당 처리 중 요청 1개
- [ ] MCP 서버 위치: 7.3으로 옮겨 함께 정합니다
- [ ] 외부 AI와 MCP 연결 방식, 도구 호출 횟수·처리 시간 상한
- [ ] 외부 API 월 비용 상한과 사용량 알림
- [ ] SSE 연결 수명, 세션 종료 시 처리
- [ ] 낮은 화면의 음성·AI·MCP 지원: 프리셋 값·수동 설정 조합·수락·복귀·상태 공유 범위 합의 후 계약과 구현 반영

## 6. 확인 시나리오

- "아이스 아메리카노 두 개 담고 결제로 가줘" → `add_cart_item`, `navigate_screen` → `cart_updated`, `ui_changed` → 화면 갱신·이동
- "라떼 하나" → 온도가 빠짐 → `needs_clarification`의 `reply_text`로 질문(SSE가 생기면 `assistant_reply`)
- "아메리카노 두 잔"(신뢰도 낮음) → `needs_confirmation` "아이스 아메리카노 2잔 담을까요?" → 마이크 다시 열림 → "네" → `completed`
- 마이크가 열린 동안 일행이 "너 뭐 먹을래?" → `ignored`, 화면 변화 없음
- 음성으로 담는 동안 터치로 수량 변경 → 버전 충돌을 감지하고 최신 상태 표시
- "카페라떼"가 "카페모카"로 인식될 수 있는 상황 → 후보·신뢰도로 확인 질문, 인식 문장을 화면에 표시
- Chrome 인식·외부 AI 실패 → 안내 후 터치 주문 계속 가능
- 주문 확정 요청 → `confirmation_required` → 사용자 수락 후에만 확정

이 목록은 구현 후 검증할 계획이며, 현재 구현이나 테스트 통과를 의미하지 않습니다.

## 7. 현재 구현 상태와 MCP 자동 제어까지 남은 작업

- 작성일: 2026-10-12 (수정: 2026-10-13, ignored와 frontend 음성 입력 추가)

### 7.1 지금 되는 것

backend 음성 해석 (`backend/app/modules/voice/`)

- 음성 요청 접수·상태 조회 API(`contract/voice.openapi.yaml` 0.3.0).
- OpenAI가 세션별 최근 10턴 대화 맥락과 메뉴 목록으로 발화를 해석해 MCP 장바구니 도구 입력(`tool_calls`)을 만듭니다.
  - 확실하면 `completed`, 애매하면 `needs_confirmation`(제안 + 짧은 확인 문장), 정할 수 없으면 `needs_clarification`(질문), 키오스크에게 한 말이 아니면 `ignored`.
  - 메뉴에 없는 상품·품절 상품 담기·허용되지 않은 온도는 서버가 거르고 실패로 처리합니다.
- `OPENAI_API_KEY`가 없으면 OpenAI를 호출하지 않고 개발용 응답을 돌려줍니다. 메뉴는 주문 API와 같은 시연 카탈로그(17개)를 씁니다. 판매 메뉴가 비어 있으면 OpenAI를 호출하지 않고 `failed`(`ai_unavailable`)로 알립니다. 실제 키로는 아직 확인하지 않았습니다.
- 키 설정: `backend/`에서 직접 실행하면 `backend/.env`, Docker Compose로 실행하면 셸 환경변수나 루트 `.env`(커밋하지 않음)의 `OPENAI_API_KEY`를 씁니다.
- 브라우저 frontend는 기본으로 같은 출처 프록시(`/backend/`)로 호출합니다. backend CORS는 `Idempotency-Key`를 허용하므로 `CORS_ORIGINS`에 넣은 출처에서는 직접 호출도 됩니다(PR #40).
- 요청 기록·`Idempotency-Key`는 접수 후 1시간, 대화 맥락은 마지막 발화 후 1시간 보관합니다(제안값, `repository.py`의 `RETENTION`).
- 음성 API는 도구를 **실행하지 않습니다.** 장바구니는 아직 바뀌지 않고 `actions`는 항상 빈 배열입니다.
- 키오스크에게 한 말이 아니면(일행과의 대화, 잡담) `ignored`로 답합니다. 문장을 띄우지 않고 대화 맥락에도 넣지 않습니다.

frontend 음성 입력 (`frontend/src/features/voice/`, 화면 요소 없음)

- **음성 모드와 마이크를 나눕니다.** `VoiceController.setEnabled(true)`로 모드를 켜면 바로 한 문장을 듣고, 문장을 받거나 8초 동안 말이 없으면 마이크를 닫습니다. 서버가 처리하는 동안에는 듣지 않습니다.
  - 계속 듣지 않는 이유: Chrome 인식은 화자를 구분하지 못해 옆 사람 말이 그대로 요청이 되고, 듣는 동안 음성이 Google 서버로 전송됩니다.
- 결과가 `needs_confirmation`·`needs_clarification`이면 대답을 듣기 위해 마이크를 자동으로 다시 엽니다. `completed`·`ignored`·`failed`면 닫고, 부르는 쪽이 `listen()`으로 다시 열 수 있습니다(예: 마이크 버튼).
- 신뢰도 0.3 미만 인식은 주변 소리로 보고 보내지 않습니다. Chrome이 신뢰도를 0으로 주면 "모름"(null)으로 보냅니다.
- 한 글자 인식은 첫 발화에서는 보내지 않고, 확인·질문에 대한 대답("네", "응")에서는 보냅니다. 대답 대기 상태는 마이크가 무음으로 닫힌 뒤 `listen()`으로 다시 열어도 유지되고, 다음 해석 결과가 나오거나 세션이 바뀌거나 음성 모드를 끄면 지워집니다.
- 모드를 언제 켤지(판단 모델의 `voice_guide`, 손님의 버튼), 결과로 장바구니를 다시 불러오거나 MCP를 실행하는 일, 문구 표시는 부르는 쪽이 합니다. `onResult` 콜백과 `useVoiceInput` 훅으로 상태를 받습니다.
- 테스트: `frontend/`에서 `npm test`에 포함됩니다(프론트 담당 제안). 음성만 돌릴 때는 `node --test src/features/voice/*.test.mjs`.

방식: 일반적인 MCP처럼 AI가 도구를 하나씩 호출하며 반복하지 않고, OpenAI 한 번 호출로 실행할 도구 목록을 정한 뒤 검증해서 MCP가 차례로 실행합니다. 도구 입력 형식은 MCP 도구와 같게 맞춰 두었으므로 나중에 반복 호출 방식으로 바꿔도 도구 정의는 그대로 씁니다.

### 7.2 남은 작업

| # | 작업 | 담당 | 선행 |
|---|---|---|---|
| 1 | ~~상품 조회·장바구니 추가·수량 변경·삭제 서비스~~ 완료(PR #40, 메모리 저장, 계약 `draft`) | Back-end | — |
| 2 | ~~음성 해석에 실제 메뉴 연결~~ 완료: `main.py`가 주문 카탈로그(`menu_from_products(PRODUCTS)`)를 넘김. 상품을 DB로 옮기면 그 조회로 바꿈 | Decision AI | 1 |
| 3 | (선택) 해석할 때 현재 장바구니도 전달: 터치로 담은 상품까지 "하나 더", "라떼 빼 줘"를 정확히 해석 | Decision AI | 1 |
| 4 | `tool_calls` 실행부(MCP 도구): 상품+온도로 `item_id` 조회, `expected_version` 채움, 요청별 `Idempotency-Key` 생성, 말한 순서대로 실행 | Decision AI + Back-end | 1 |
| 5 | 실행 결과를 `actions`(`cart_updated` 등)와 SSE 알림으로 전달 | Back-end + Front-end | 4, 3.4 |
| 6 | 프론트 화면 연결: 메뉴 화면의 음성 모드 버튼·다시 말하기·인식 문장과 `reply_text` 표시는 완료(PR #53). `voice_guide`로 모드 자동 켜기, 확인·취소 버튼, 메뉴 외 화면은 남음 | Front-end | 판단 모델 결과 수신 |
| 7 | 실행 환경: CORS의 `Idempotency-Key`·메서드 허용은 PR #40에서 반영됨. 배포 출처를 `CORS_ORIGINS`에 넣을지는 배포 구성에서 정함. Compose의 키 전달은 반영함 | Back-end·infra | — |
| 8 | 실제 키로 프롬프트 검증, 실험에 쓴 프롬프트 버전(현재 `interpret_v2`, v1은 ignored 없음)·모델 기록 | Decision AI | 2 |

### 7.3 결정이 필요한 항목

- [ ] **실행 시점**: `completed`가 되면 backend가 바로 실행할지, 부르는 쪽(프론트 등)이 실행 API를 부를지
- [ ] **확인 버튼으로 수락**: `needs_confirmation`의 제안을 버튼으로 수락하면 그 `tool_calls`를 바로 실행할지, "네" 발화와 같은 경로로 보낼지
- [ ] **중간 실패**: 도구 여러 개 중 일부가 실패하면(버전 충돌·수량 초과) 앞서 실행한 것을 되돌릴지, 재조회 후 재시도 횟수
- [ ] **MCP 서버 위치·방식**: backend 내부 모듈 / 별도 서비스, MCP SDK 의존성 추가 여부
- [ ] **대화 기록 보관**: 세션별 최근 10턴·1시간 보관(제안값), 인식 문장을 서버 메모리에 보관하는 것을 실험 동의 안내에 넣을지. 세션 종료 API가 생기면 그때 바로 지울지
- [ ] **확인 문장 길이**: 최대 60자(제안값)
- [ ] **마이크 여는 시간·거르는 기준**: 무음 8초, 신뢰도 0.3 미만 버림(제안값, `voiceController.ts`의 `VOICE_SILENCE_MS`·`VOICE_MIN_CONFIDENCE`). 실제 키오스크 소음 환경에서 조정
- [x] **주문을 마친 세션의 음성 요청**: 접수 단계에서 410 `session_expired`로 거절합니다(주문 정책 PR #51 리뷰에서 합의, backend 구현은 PR #56). 같은 키·같은 본문 재전송은 원래 202를 돌려주고, 상태 조회는 막지 않습니다. frontend는 `session_expired` 오류로 구분해 대답 대기를 풀고 새 주문을 안내합니다
- [ ] **`screen_id` 값**: 메뉴 화면은 지금 `menu_list`를 보냅니다(PR #53). 터치 로그는 `menu`를 쓰고, 계약 설명은 "터치 로그와 같은 값"이라 서로 어긋납니다. 어느 쪽으로 맞출지
