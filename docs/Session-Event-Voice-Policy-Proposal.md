# 세션·이벤트·관측 결과·음성 실행 정책 합의안

- 상태: **팀 검토용 제안. PR 리뷰에서 밝힌 담당자 의견은 팀 전체 합의나 유효한 API 계약·DB 마이그레이션이 아님**
- 기준: `../contract/frontend-backend.openapi.yaml`, `../contract/backend-ai.openapi.yaml`, `../contract/voice.openapi.yaml`, `Touch-Log-Review.md`, `Voice-MCP-Implementation.md`
- 목적: 프론트·백엔드·비전·AI가 세션 종료, 기록 시각, 오래된 결과, 음성 도구 실행을 같은 뜻으로 구현하기 전에 결정한다.

2026-10-31 현재 PR #62의 프론트·AI·비전 담당 리뷰와 AI 담당의 후속 댓글을 반영했다. 각 절의 **담당자 의견**과 **후속 결정 필요**를 구분한다. 문서가 병합되더라도 기존 OpenAPI의 의미나 DB 저장 정책이 자동으로 확정되지는 않는다.

현재 `POST /api/v1/sessions`는 세션을 만들고, 주문 확정은 해당 세션을 완료 상태로 만든다. 완료된 세션의 새 장바구니 변경·특징 전송·음성 요청은 410으로 막지만, 기존 음성 결과 조회와 동일 키·동일 본문 재전송은 허용한다. `POST /features`는 `window_start`·`window_end`를 받지만 수신 시각과 구간 순서를 기록하지 않는다. 음성 API의 `completed`는 **해석 완료**를 뜻하며 `tool_calls`를 실행하지 않는다. 아래 제안은 이 사실을 소급해서 바꾸지 않는다.

## 1. 세션 종료: 주문 완료와 이탈을 구분

| 경우 | 제안한 서버 상태 | 후속 처리 |
| --- | --- | --- |
| 세션 생성 | `active` | 상품·장바구니·특징·음성 요청 허용 |
| 주문 확정 성공 | `completed` | 한 세션 한 주문 유지. 새 변경·특징·음성 요청은 기존대로 410 |
| 주문 없이 새 이용 시작·명시적 이탈 | `ended` | 새 변경·특징·음성 요청은 410. 새 주문은 새 세션 |
| 유휴 만료 | `ended` (`reason=idle_timeout`) | **만료 시간은 별도 결정 전까지 구현하지 않음** |

새 API 제안: `POST /api/v1/sessions/{session_id}/end`에 `Idempotency-Key: <UUID>`와 `{ "reason": "new_order" | "user_exit" }`를 보낸다. 서버가 `ended_at`을 UTC로 생성하고 `{ "session_id", "status", "ended_at", "reason" }`를 반환한다. 같은 키·같은 요청은 원래 응답을 재전송하고, 같은 키에 다른 본문은 409 `idempotency_key_reused`로 응답한다. 없는 세션은 404 `session_not_found`다. 이미 주문을 완료한 세션에 대한 종료 요청은 주문 상태를 바꾸지 않고 `status=completed`로 응답하되, **프론트 리뷰 대안**으로 `ended_at: null`, `reason: null`을 명시해 주문 없는 종료와 구분한다. 최종 nullable 형식은 후속 계약에서 결정한다.

종료와 주문 확정이 동시에 오면 서버에서 순서를 직렬화한다. 먼저 종료되면 주문은 410, 먼저 주문되면 종료는 `completed`를 반환한다. 이미 접수한 음성 요청의 결과 조회는 현재 계약대로 보관 기간 안에서 허용하되, 종료 뒤 늦게 끝난 AI 결과는 장바구니나 지원 상태에 적용하지 않는다. 종료 요청이 실패하면 성공으로 표시하지 않는다. 프론트가 같은 키로 종료를 재시도하는 동안 새 세션 생성을 막을지, 미확정 주문을 어떻게 조회할지는 별도로 정한다. 페이지 종료 신호는 전달이 보장되지 않으므로 종료 API가 호출되지 않은 세션을 자동으로 `ended`로 추정하지 않는다.

**담당자 의견·후속 결정:** 프론트는 `active/completed/ended` 구분에 동의하고 완료 세션의 nullable 응답을 제안했다. AI는 종료 시 대화 맥락 즉시 삭제와 늦은 음성 처리의 `session_expired` 기록을 제안했지만, 기존 요청의 GET 가능 기간과의 관계를 정해야 한다. 비전은 현재 출력의 `measurable=false`를 사용자 부재로 해석할 수 없으므로 `user_absent` 자동 종료를 보류했다. 종료 API의 경로·사유·실패/재시도·보관 기간·유휴 만료값은 아직 합의가 필요하다. 현재 프론트의 로컬 로그 세션은 서버 `session_id`와 다른 ID이며, 서버 세션을 받기 전 이벤트는 임의의 서버 세션에 붙이지 않는다.

## 2. 서버에 저장할 이벤트와 시각

원시 영상·음성, 얼굴 좌표, API 키는 저장하지 않는다. 현재 프론트의 원시 터치 로그는 로컬 파일럿이며 이 제안만으로 자동 업로드하지 않는다. 아래는 **최소 서버 저장 후보**다. SSE 알림은 화면 갱신용 통로이며, 저장 이벤트와 같은 이름·보관 정책을 자동으로 공유하지 않는다.

| 이벤트 종류 제안 | 발생 주체 | 최소 데이터 | 목적 |
| --- | --- | --- | --- |
| `screen_enter`, `screen_leave` | 프론트 | `screen_id`, `visit_id` | 화면 방문 구간 |
| `interaction_result` | 프론트 | `action_kind`, `outcome` (`success`·`blocked`·`error`·`cancelled` 제안), 연결용 `action_id` 후보 | 터치 조작 결과. 포인터 원시 좌표는 제외. 응답 미확정은 성공·오류로 추정하지 않음 |
| `ui_settings_change` | 프론트 | 변경 전·후 설정 | 수동 지원 변화 |
| `feature_window_received` | 백엔드 | `window_seq`, `screen_id`, `window_start`, `window_end` | 분석 입력 추적 |
| `support_proposed`, `support_responded` | 백엔드 | `decision_id`, `preset`, 수락·거절 여부 | 지원 제안·사용자 선택 이력. 실제 화면 적용 성공과는 구분 |
| `support_applied`, `support_apply_failed`, `support_reverted` (프론트 제안) | 프론트 | `decision_id`, 적용 결과·사유 후보 | 수락 후 실제 적용·실패·되돌리기 구분. 이름과 전송 범위 미정 |
| `cart_changed`, `order_completed` | 백엔드 | 장바구니 `version` 또는 `order_id` | 실제 주문 변경과 평가 시점 |
| `voice_request_finished`, `session_ended` | 백엔드 | `request_id`·최종 상태 또는 종료 사유 | 음성 처리·세션 경계 |

저장 이벤트 공통 필드 제안: `event_id`(세션 안에서 중복되지 않는 문자열), `session_id`(서버 ID), `schema_version`, `kind`, `source`(`frontend`·`backend`), `occurred_at`(원천에서 관측한 UTC RFC 3339 시각), `received_at`(백엔드가 접수할 때 부여한 UTC 시각), `screen_id`(해당하는 경우), 종류별로 제한한 `data`. `event_id`는 재전송 중복 제거에 사용한다. 백엔드 생성 이벤트에서는 `occurred_at`과 `received_at`을 같은 서버 시계로 기록한다. 구간 집계의 관측 시각은 `window_start`·`window_end`로 표현하고 `occurred_at=window_end`를 사용한다. 두 시각의 차이는 측정 지표이지 사용자 기기 시계가 정확하다는 증거가 아니다.

프론트 이벤트 전송 API를 만들 경우 `POST /api/v1/sessions/{session_id}/events/batches`와 `{ "events": [...] }`를 제안한다. 서버는 경로의 세션 ID와 각 이벤트의 ID를 확인하고, 세션이 다르거나 중복 ID에 다른 내용이면 거절한다. `received_at`은 클라이언트가 보내지 않는다. **프론트 대안**은 첫 버전의 배치를 전부 수락 또는 전부 거절하고, 같은 `event_id`·같은 본문은 성공으로 중복 제거하며, 같은 ID·다른 본문이나 유효하지 않은 항목은 위치·사유를 돌려주는 것이다. 정확한 상태 코드·응답 형식, 배치 크기·원시 터치 업로드 범위는 상세 OpenAPI에서 결정한다. DB에는 세션과 별도로 이벤트·지원 결정 이력을 저장하고, 마이그레이션·RLS·보관 기간은 후속 DB PR에서 정합성을 검증한다.

**담당자 의견·후속 결정:** 프론트는 `interaction_result`를 특정 요청·입력과 연결할 `action_id` 또는 `request_id/input_id`를 제안했다. `pending/unknown`을 `error`로 추정하지 않고 정상적인 옵션 취소를 실패와 구분해야 한다. `support_responded`의 수락만으로 실제 적용 성공을 기록하지 않으며 적용·실패·되돌리기의 이벤트 이름과 발생 주체를 정한다. 서버에 보낼 종류, 판정 기준, 배치 원자성·오류 형식, 실험 동의·보관·삭제 기간은 아직 팀 결정이 필요하다. 이는 `Touch-Log-Review.md`의 T06·T09~T12와 연결되며, 로컬 파일럿 값을 정식 계약으로 승격하지 않는다.

## 3. 관측 구간과 오래된 AI 결과

특징 요청에 `window_seq`(서버 세션마다 1부터 증가하는 정수)를 추가하는 안을 제안한다. 프론트 → 백엔드 → ai-engine에 같은 값을 전달하고 ai-engine이 응답에 되돌린다. **프론트·비전 의견**은 화면 전환에도 번호를 초기화하지 않고, 관측하지 못해 번호가 비어도 허용하며, 같은 구간 재전송에는 같은 번호·본문을 쓰는 것이다. 백엔드 응답도 `session_id`, `window_seq`, `window_start`, `window_end`, 서버 `received_at`을 되돌려 프론트가 요청과 결과를 연결한다. 관측 시각은 프론트가 측정한 구간이며, 수신 시각은 백엔드가 생성한다. 비전 특징이 없으면 기존 `vision: null`을 유지한다.

1. 백엔드는 다른 세션 ID·다른 `window_seq`의 ai-engine 응답을 적용하지 않는다.
2. 같은 세션에서 **이미 수락한 가장 큰 `window_seq`보다 작은** 요청 또는 뒤늦은 AI 결과는 지원 선택에 사용하지 않는다. 최신 구간의 분석이 실패해도 더 오래된 결과를 나중에 적용하지 않는다.
3. 같은 `window_seq`·같은 본문의 재전송은 같은 구간으로 취급한다. 같은 번호에 다른 본문은 409 `window_sequence_reused`로 거절한다.
4. 주문 완료·명시적 종료가 처리된 뒤 새 요청은 기존 410 `session_expired`를 유지한다. 처리 중 완료된 구간의 결과도 410으로 버린다.
5. 프론트는 현재 서버 세션과 다른 응답 또는 자신이 마지막으로 보낸 구간보다 작은 `window_seq`의 응답을 UI에 적용하지 않는다. 같은 번호여도 요청 당시 `visit_id`와 현재 화면 방문을 대조해 화면을 떠났거나 같은 화면에 재진입한 뒤의 결과를 적용하지 않는다. `visit_id`를 API 필드로 주고받을지 프론트 요청 맥락에만 둘지는 후속 계약에서 정한다. 같은 구간 응답의 중복 수신도 `last_applied_seq` 또는 `decision_id`로 한 번만 적용한다. 서버가 구간을 버린 응답은 `result_status=discarded`, `discard_reason=stale_window`로 구분하고 지원 변경을 포함하지 않는다.

기기 간 절대 시계가 어긋날 수 있으므로 **고정된 초 단위 나이만으로 구간을 버리지 않는다**. `window_seq`를 적용 순서 기준으로 사용하고 `window_end`와 `received_at`은 지연 측정에 쓴다. 비전 담당은 별도의 비전 시간 폐기 기준을 제안하지 않았으며, 비전 특징을 터치와 같은 구간에 맞춰 전달하는 방향에 동의했다. 현재 ai-engine 호출 2초 타임아웃은 그대로 유지한다. 프론트 파일럿의 로컬 5초 요청·표시 제한은 팀 계약 값으로 간주하지 않는다. 파일럿에서 실제 지연과 시계 오차를 측정한 뒤 별도 시간 임계값이 필요한지 결정한다. 현재 `preset=none` 연결 검증을 자동 지원으로 해석하지 않는다.

응답 형식 제안(기존 필드를 유지하고 구간·결과 상태를 추가):

```json
{
  "session_id": "s1", "window_seq": 12,
  "window_start": "2026-10-29T10:00:00Z", "window_end": "2026-10-29T10:00:02Z",
  "received_at": "2026-10-29T10:00:02.100Z",
  "result_status": "discarded", "discard_reason": "stale_window",
  "ai_available": true, "states": null, "model_version": null,
  "support": { "preset": "none", "requires_confirmation": false, "decided_by": "rule_placeholder" }
}
```

**담당자 의견·후속 결정:** `window_seq`의 생성·재전송 책임, 중복 결과의 응답 방식, `discarded` 응답의 `ai_available` 의미, `visit_id` 전달 방식과 중복 적용 방지를 정해야 한다. 프론트의 로컬 집계 `null`과 현행 계약의 필수 터치 정수 5개가 다르므로, 관측 불충분 구간의 제외 또는 명시적 관측 상태를 결정하고 0으로 임의 대체하지 않는다. 합의 후 두 특징 API 계약과 프론트·백엔드·ai-engine 샘플을 같은 시점에 맞춘다.

## 4. 음성 `tool_calls`의 실행과 실패

현재 `../contract/voice.openapi.yaml`의 `completed`는 해석 성공일 뿐 장바구니 변경을 뜻하지 않는다. 아래는 **후속 계약 변경 제안**이며, 기존 API의 의미를 이 PR에서 바꾸지 않는다. 프론트는 실행 완료를 별도 상태·필드·계약 버전으로 구분할지와 전환 시점을 정한 뒤에만 “담았어요”처럼 실제 변경을 알린다.

| 해석 결과 | 후속 계약에 제안한 실행 시점 |
| --- | --- |
| `completed` | 백엔드가 메뉴·현재 장바구니·세션 상태·수량·옵션을 재검증한 뒤 실행. 실제 반영이 끝나기 전에는 `processing` 유지. 현행 `completed`의 의미 변경·호환 방식은 미결정 |
| `needs_confirmation` | 제안만 보관하고 실행하지 않음. 같은 세션의 새 음성 수락이나 확인 UI의 수락을 별도로 확인한 뒤 한 번만 실행. 확인 경로는 미결정 |
| `needs_clarification`, `ignored`, `failed` | 실행하지 않음 |

**실행 위치에 대한 AI 담당 의견(2026-10-29):** backend의 voice 모듈이 같은 프로세스의 ordering 서비스를 호출한다. 별도 MCP 서버·SDK를 추가하지 않고 현재 `add_cart_item`·`update_cart_item`·`remove_cart_item` 입력 형식을 MCP 도구 입력과 호환되게 유지한다. 이는 AI 담당의 채택 의견이며 backend의 배치·잠금 설계와 팀 계약 반영은 별도 확인 대상이다.

프론트는 AI가 만든 `tool_calls`를 직접 주문 API로 보내지 않는다. 백엔드는 기존 주문 서비스의 상품·장바구니·버전·멱등성 검사를 재사용한다. AI 담당은 ordering 잠금 안에서 최신 Cart와 세션을 읽고 **여러 도구를 전부 먼저 검증한 뒤 말한 순서대로 반영**하는 안을 제안했다. 한 도구라도 실패하면 버전·Cart·주문 상태를 바꾸지 않는 원자성이 필요하다. 음성 요청 1건에 장바구니 버전을 한 번 올리고 `cart_updated`를 한 번 기록할지는 backend 담당이 결정한다. 터치 변경과 경합하면 최신 Cart를 기준으로 검사하되, 사용자 의도를 자동으로 다시 실행하지 않는다. 재전송된 동일 음성 `Idempotency-Key`는 원래 결과를 돌려주고 도구를 다시 실행하지 않는다. `cart_updated`는 변경이 실제로 커밋된 뒤에만 `actions`와 알림에 넣고, 프론트는 최신 Cart를 다시 조회한다.

**후속 구현 PR #66 (검토 중):** AI 담당은 별도 MCP 서버·SDK 없이 backend 내부에서 `OrderingService`를 호출하는 실행부를 올렸다. 제안 문서의 사전 일괄 검증안과 달리 도구를 순서대로 실행하고 하나라도 실패하면 장바구니·재전송 기록을 되돌리는 `transaction()` 방식이다. 현재 제안 코드는 **도구 입력마다** 버전을 올리고 `voice:{request_id}:{순서}` 키를 사용하며, 음성 요청 재전송은 실행을 반복하지 않는다. `needs_confirmation`은 실행하지 않고 다음 “네” 발화만 처리한다. 버튼 수락 API는 없다. `VOICE_EXECUTE_TOOLS` 기본값이 꺼져 있어 PR #66이 병합되더라도 기본 동작은 해석만 수행한다. 이 구현안의 원자성·버전 증가 단위·멱등성은 backend 리뷰와 테스트로 확인해야 하며, 이 문서만으로 확정하지 않는다.

**확인 경로 제안:** AI 담당은 확인 제안 뒤 같은 세션의 새 “네” 발화를 기본 경로로 제안했다. 버튼 수락은 저장된 제안을 한 번만 소비하는 별도 API가 필요할 수 있으며, 기존 공용 확인 API와 음성 전용 API 중 어느 쪽을 사용할지 정해야 한다. 음성·버튼이 동시에 수락해도 한 번만 실행되도록 제안 ID, 중복 키와 소비 상태를 정한다. 주문 확인 중 화면 이동·세션 교체가 일어났을 때의 처리도 프론트와 합의한다.

실행 실패 시 상태 조회는 `status=failed`, `actions=[]`, `tool_calls=[]`, 기존 `{code, detail}` 오류 형식을 제안한다. `error.code`에 기존 주문 오류인 `cart_version_conflict`, `product_unavailable`, `product_not_found`, `cart_item_not_found`, `quantity_limit_exceeded`, `invalid_option`, `session_expired`를 필요한 범위에서 추가한다. 사용자에게는 수정 가능한 오류를 `reply_text`로 안내하고, 장바구니 관련 실패나 변경 성공 뒤 프론트가 최신 Cart를 재조회한다. AI 원문이나 내부 예외를 오류에 넣지 않는다. **현재 구현에서는** 판매 메뉴 미연결과 메뉴 대조 거절도 `ai_unavailable`로 표현한다. 이를 AI 호출·형식 실패에만 한정하려면 두 경우의 대체 오류 코드·응답을 후속 계약에서 함께 정하고 구현을 바꿔야 한다. 장바구니 충돌을 `ai_unavailable`로 새로 표현하지 않는다.

```json
{
  "request_id": "vr_example", "status": "failed",
  "reply_text": "장바구니가 바뀌었어요. 내용을 확인해 주세요.",
  "tool_calls": [], "actions": [],
  "error": { "code": "cart_version_conflict", "detail": "최신 장바구니를 다시 확인해 주세요." }
}
```

**담당자 의견·후속 결정:** PR #61은 2026-10-30 병합됐고, AI 담당에 따르면 온도 누락·맥락 없는 대답·이름을 공유하는 상품의 오인식 검토도 그 PR에서 끝났다. 따라서 AI 담당이 제시한 “#61 병합 뒤” 선행 조건은 충족됐다. 다만 PR #66의 실제 키 검증에서 “하나 더요”가 의도한 총 3잔 대신 기존 2잔에 3잔을 더해 5잔이 되는 사례가 확인됐다. 현재 장바구니를 해석 입력에 전달하는 후속 수정과 프론트의 `cart_updated` 재조회 연결 전에는 실행 기본값을 켜지 않는 방향으로 검토한다. 프론트는 기존 `completed` 의미를 곧바로 바꾸지 말고 실행 여부·결과 표현과 구버전 클라이언트 호환을 결정하자고 했다. 여러 도구의 원자성, 버전 증가 단위, 확인 버튼 API·음성 수락의 동일한 중복 방지 경계, 오류 코드와 Cart 재조회·재시도 범위는 아직 팀 결정이 필요하다. PR #66은 `voice.openapi.yaml` 변경도 제안하지만 열린 PR이며, 계약·프론트 결과 처리와 백엔드 구현의 최종 정합성은 후속 리뷰에서 확인한다.

## 5. 저장 설계에 전달할 최소 기준과 PR 완료 조건

- 후속 DB 설계안에는 `sessions.status`·`ended_at`·`end_reason`, 구간의 `window_seq`·관측/수신 시각·처리 상태, 제한된 이벤트 종류와 중복 키, 지원 제안/수락/거절 및 실제 적용·실패·되돌리기 후보, 장바구니·주문 변경의 원자성을 검토한다. 미결정 필드와 이벤트 종류를 확정 스키마로 적용하지 않으며 이미 적용한 마이그레이션은 수정하지 않는다.
- 세션과 주문의 보관·삭제 기간, 음성 텍스트 보관 여부, 실험 데이터의 파일럿/최종 분리는 **팀 결정 전에는 DB 기본값으로 만들지 않는다**. 현재 음성 맥락의 메모리 1시간 보관은 DB 정책의 합의로 간주하지 않는다.
- 프론트는 기존 로컬 원시 로그와 수동 접근성 설정을 유지한다. 이 PR은 서버 업로드, 자동 지원, SSE, MCP 실행이나 Supabase 변경을 구현하지 않는다.
- 리뷰어가 각 절의 **채택·대안·보류**와 결정 날짜를 PR에 남기면, 합의된 항목만 기존 OpenAPI에 반영하는 후속 변경을 작성한다. 현재 프론트·AI·비전의 리뷰는 담당자별 의견이며 백엔드·DB 확정과 팀 전체 합의가 남았다. 미합의 항목은 확정 명세로 표시하지 않는다.
