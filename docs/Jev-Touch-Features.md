# Jev 판단을 위한 터치·상호작용 특징과 전송

- 작성일: 2026-11-02
- 범위: 프론트의 로컬 기록·파일럿 집계·선택적 전송 준비. 백엔드·AI·계약 수정은 담당자에게 요청한다.
- 상태: 팀 검토용 제안. `touch.interaction`은 확정 계약이 아니며 추가 필드·계산 기준·운영 정책을 관련 담당자가 합의해야 한다.
- 제안 형식: `touch-interaction-pilot-v1`. 기존 5개 필드와 `touch.interaction` 확장을 같은 요청에 넣는다. 전송은 기본적으로 꺼져 있다.
- 기존 논의: [터치 로그 검토](Touch-Log-Review.md), [세션·이벤트 정책 제안](Session-Event-Voice-Policy-Proposal.md).

## 1. 프로젝트 구조에서의 역할

```text
주문 화면의 터치·화면 이동·주문 상태·설정·음성 상태 기록
 → 프론트: 최근 2초 특징 + 현재 화면 맥락 계산
 → backend: POST /api/v1/sessions/{session_id}/features
 → [담당자 검토 요청] 추가 필드 검증·보존 → ai-engine /v1/analyze
 → 기존 분석 응답(현재 placeholder)
```

프론트는 backend와만 통신한다. 외부 Jev 호출은 backend가 맡고, 비전 상황과 터치 근거를 사용하는 판단 층은 ai-engine의 책임이라는 목표 구조를 유지한다. 현재 backend의 `TouchFeatures`에는 `interaction`이 없으며 추가 필드를 무시하므로, 프론트가 200 응답을 받더라도 확장 필드가 ai-engine으로 전달되었다는 뜻이 아니다. 팀 합의와 각 담당자의 후속 구현 전까지 파일럿 전송은 기본적으로 꺼진다. Jev 호출·실제 자동 지원·DB 저장도 이번 PR에 없다.

Jev에는 후속 연동에서 시간 구간·관측 여부·현재 화면·비전 상황·허용 가능한 지원과 함께 아래 근거를 전달해야 한다. 개별 통계를 곧바로 장애·감정·불편의 확정값으로 해석하지 않는다.

## 2. 기존 5개와 판단 용도

| 필드 | 이번 전송의 파일럿 계산 | 유용한 판단·주의점 |
| --- | --- | --- |
| `tap_count` | 최근 2초 `pointer_start` 수 | 터치가 이어지는지, 입력이 멈췄는지 확인. 취소·스크롤 시작도 포함하며 조작 성공 수가 아님 |
| `miss_tap_count` | 같은 구간에서 버튼·링크 대상이 없는 누름 수 | 큰 버튼 지원을 검토할 단서. 배경 누름·큰 빈 공간 선택을 실패로 단정하지 않음 |
| `repeat_tap_count` | 기존 로컬 기준 800ms·24 CSS px의 추가 반복 후보 수 | 입력 반응을 찾는 행동을 검토. 정상 수량 증가, 스크롤·취소·동시 접촉, 주문 대기와 함께 봄 |
| `back_count` | 최근 2초 주문 확인 → 메뉴 이동 수 | 탐색 도움·다음 단계 안내 검토. 메뉴 추가를 위한 정상 복귀도 포함 |
| `dwell_ms` | 현재 화면 방문의 전경 체류 누적 ms | 현재 단계에 머무는 정도. 최근 2초의 길이나 마지막 성공 후 시간과 다름 |

이는 기존 로컬 파일럿 기준을 버전으로 식별해 전달하는 구현이다. `Touch-Log-Review.md`의 T01~T14를 팀 합의 완료로 바꾸지 않는다. 반복 후보의 상세 제외 조건은 기존 `touchLogFeatures.ts`를 그대로 따른다.

## 3. 추가 집계와 판단 용도

아래 필드는 `touch.interaction`에 들어간다. 횟수는 기본적으로 요청의 `(window_start, window_end]` 구간이며, 시각 차이는 ms, 거리는 CSS px다.

| 필드 | 계산·결측 표현 | Jev 및 판단 층에서 유용한 점 |
| --- | --- | --- |
| `outside_tap_ratio` | `miss_tap_count / tap_count`. 누름 0회면 `null` | 사용량이 다른 구간의 대상 밖 입력 정도를 비교. 실패율로 명명하지 않음 |
| `outside_nearest_distance_mean_px` | 대상 밖 누름에서 기록된 가장 가까운 활성 대상까지의 거리 평균. 관측 없음은 `null` | 버튼 경계 근처 입력과 멀리 떨어진 배경 입력을 구분할 근거. 임의의 주변 거리 임계값은 두지 않음 |
| `outside_nearest_distance_sample_count` | 위 평균에 사용한 누름 수. 동률 후보가 여럿이어도 누름당 한 표본 | 거리 평균의 근거량과 누락을 확인. 전체 대상 밖 누름 수와 함께 봄 |
| `pointer_cancel_count` | 취소로 끝난 입력 수 | 스크롤 등으로 취소된 입력을 일반 누름과 구분하는 보조 근거. 취소=실패가 아님 |
| `pointer_interrupted_count` | 끝까지 관측하지 못해 중단 기록이 생긴 입력 수 | 측정 품질과 관측 중단 확인. 부재·포기로 단정하지 않음 |
| `scroll_event_count` | 기록된 스크롤 이벤트 수 | 아직 목록을 탐색 중인지 검토하여 성급한 안내를 줄임. 스크롤 제스처 횟수나 이동 거리는 아님 |
| `category_change_count` | 메뉴 분류 변경 수 | 여러 분류를 탐색하는 상황과 정지 상태를 구분. 잦은 변경만으로 헤맴을 판단하지 않음 |
| `options_open_count`, `options_close_count` | 옵션 창 열기·닫기 수 | 옵션 비교·선택 과정을 확인. 정상 취소와 담기를 구분하려면 Cart 변화와 함께 봄 |
| `screen_transition_count` | 출발 화면이 있는 화면 진입 수 | 주문 단계의 진행·왕복을 파악 |
| `screen_revisit_count` | 같은 로컬 세션에서 이미 방문한 화면에 다시 진입한 수. 세션 시작 기록이 잘렸으면 `null` | 반복 탐색·단계 안내 필요성 검토. 정상 메뉴 추가와 구분 필요 |
| `cart_change_count` | 이전·이후 서버 Cart 버전 증가를 관측한 횟수. 최초 기준선 제외 | 주문이 실제로 진행되는지 확인하여 불필요한 도움을 거둘 근거. 터치·음성 원인과 개별 성공 횟수는 구분할 수 없음 |
| `selection_change_count` | 상품·옵션·수량 선택 상태의 변화 수. 최초 기준선 제외 | 옵션을 조정 중인지, 아무 행동 없이 멈춘 상태인지 구분 |
| `ui_settings_change_count` | 접근성 설정 변경 수 | 사용자가 도움을 직접 조정하는 흐름 확인. 지원 제안 수락·거절을 대신하지 않음 |
| `voice_state_change_count` | 음성 모드·마이크·처리 단계의 변화 수. 최초 기준선 제외 | 터치 대신 음성을 사용하는 상황을 함께 고려. 발화 한 번에도 `listening → processing → idle`로 2~3회 늘 수 있어 모드 켬·끔 횟수나 발화 횟수가 아님 |
| `since_last_input_ms` | 현재 방문의 마지막 누름 이후 ms. 누름 이력 없음은 `null` | 선택 후 멈춤을 확인. 성공 조작 후 정지나 사용자 부재를 의미하지 않음 |
| `order_busy_ms` | 구간 내 프론트 주문 상태 `loading/saving` 시간의 합. 구간 시작 상태가 없으면 `null` | 시스템 응답을 기다리는 정지를 사용자 망설임으로 오해하지 않도록 보조. 실제 서버 처리 지연·요청별 소요 시간과 다름 |

구간 종료 시 맥락도 함께 보낸다.

| 필드 | 판단에 필요한 맥락 |
| --- | --- |
| `options_open` | 현재 옵션 선택 중인지. 상태 기록 없음은 `null` |
| `order_busy` | 현재 주문 처리·조회 대기 중인지 |
| `voice_enabled`, `microphone_active` | 음성 입력 중이라 터치가 없는 경우를 구분. 상태 기록 없음은 `null` |
| `voice_processing` | backend 음성 요청을 기다리는 단계인지. 상태 기록 없음은 `null` |
| `voice_auto_off` | 음성 모드가 무음(`silence`) 또는 유휴 시간(`idle`)으로 저절로 꺼진 이유. 값이 있으면 사용자가 직접 끈 것과 구분하며, `null`은 자동 종료 이유를 관측하지 못했거나 자동 종료가 아니었음을 뜻함 |
| `ui_settings` | 큰 글씨·큰 버튼·간편 화면·단계 안내·낮은 화면·고대비 적용 여부. 이미 켠 도움을 다시 제안하지 않을 근거 |
| `visit_id` | 구간 종료 시 화면 방문. 같은 화면 재방문과 이전 방문을 구분 |
| `window_sequence` | 현재 서버 세션에서 전송을 시도한 구간의 순서. 서버 중복 제거·최신 결과 적용을 보장하는 필드는 아님 |
| `schema_version` | 파일럿 계산 정책 식별자. 정책이 달라지면 버전도 바꿔야 함 |

## 4. 아직 계산하지 않는 항목

다음은 원시 기록만으로 확정할 수 없거나 T03·T06·T07·T08 합의가 필요한 항목이다. 전송 형식에 가짜 0을 만들지 않는다.

- 버튼 주변 입력 수: 거리 임계값 미정. 이번에는 거리 평균과 표본 수만 전송한다.
- 주변 입력 후 같은 대상 조작 성공 수: 가까운 대상을 사용자의 의도로 단정할 수 없고 입력과 성공 결과의 연결 기준도 미정이다.
- 조작 성공·차단·오류 수 및 마지막 성공 이후 시간: 서버 Cart 변화는 관측하지만 개별 입력과 요청 결과의 인과 관계는 아직 없다. `cart_change_count`로 대체 해석하지 않는다.
- 실제 시스템 요청 대기 시간: 이번 `order_busy_ms`는 화면 상태의 지속 시간이며 요청별 네트워크·서버 시간 측정과 다르다.
- 자동 지원 제안·수락·거절·적용·되돌리기: 지원 UI와 결과 이벤트 계약을 연결한 뒤 추가한다. 현재 설정 변경만으로 거절 여부를 만들지 않는다.

원시 영상·음성·인식 문장·상품별 선택 내역·포인터 좌표·전체 원시 이벤트는 이 요청에 포함하지 않는다.

`since_last_input_ms`는 마지막 터치 누름만 기준으로 하므로 음성 요청을 처리하는 동안에도 늘어날 수 있다. 따라서 판단 층은 `voice_processing: true` 또는 `order_busy: true`인 구간을 사용자 망설임으로 단정하지 않는다. `voice_auto_off`는 자동 종료 사유만 보내며, 사용자가 끈 동작·인식 문장·음성 오류 상세는 보내지 않는다.

## 5. 전송 조건과 실패 처리

- 기본 실행에서는 전송하지 않는다. 팀 합의 후 공동 파일럿에서 빌드 또는 개발 서버 실행 시 `VITE_TOUCH_INTERACTION_DRAFT=true`로 명시하면 실제 API 모드에서 2초마다 최근 2초 집계를 시도한다. 개발 샘플 모드에서는 설정과 관계없이 요청하지 않는다.
- 서버 세션이 있고 현재 주문 상태가 `ready/saving`이며, 화면이 전경이고 주문이 완료되지 않았을 때 전송한다.
- 기존 5개 정수 필드가 전부 산출된 구간만 보낸다. 시작 직후, 백그라운드 복귀 직후, 기록 잘림, 종료되지 않은 입력 등으로 기존 집계가 `null`이면 그 구간은 건너뛴다. `null`을 0으로 바꾸지 않는다.
- 한 번에 요청 하나만 실행하며 5초에 중단한다. 지연 중 지나간 구간은 쌓아두지 않는다. 이후 최신 구간을 보낸다. 따라서 전 구간 보존·정확한 누적 이벤트 수를 보장하는 실험 저장소가 아니다.
- 일시적 연결 실패 후에는 새 표본을 보낸다. 이전 구간을 자동 재전송하지 않는다. 400·401·403·404·410·422는 해당 세션의 전송을 중단하고 새 세션/새로고침 때 다시 시작한다.
- 세션 변경·주문 완료·전경 이탈·언마운트 때 요청을 취소하고 이전 응답은 무시한다. 서버가 이미 받은 요청은 취소만으로 되돌릴 수 없으며, backend는 기존대로 완료 전·후를 확인한다.
- 전송 성공·오류는 주문 상태나 화면 도움 설정을 바꾸지 않는다. 성공은 HTTP 응답 수신일 뿐 추가 필드 보존·AI 사용을 보장하지 않는다. 서버 장애 중에도 기존 터치 주문 흐름을 유지한다.
- `window_sequence`는 추적용이다. 서버에서 영구 저장·구간 중복 제거·새 판단의 적용 순서를 관리하는 기능은 추가하지 않았다.
- 시간은 기존 로그의 벽시계를 따른다. 기록의 역행·미래 시각을 감지하면 집계를 보내지 않으며, 여러 기기의 시계 일치나 탭 정지·브라우저 지연 동안의 완전 관측은 보장하지 않는다.
- 한 구간이 화면 이동을 포함할 수 있다. `screen_id/visit_id`는 구간 종료 시 화면이며 횟수는 같은 세션의 구간 전체다. 방문 누적 `dwell_ms`와 `since_last_input_ms`는 현재 방문만 사용한다.

낮은 화면 상단 안내는 기존 수집 루트 밖이다. 해당 영역의 터치는 포함하지 않으며 전체 화면 입력으로 해석하지 않는다. `order_state_change`의 React 관측은 빠르게 합쳐진 중간 상태를 모두 보장하지 않으므로 주문 거래 감사 로그로 쓰지 않는다.

## 6. 담당자별 수정 요청 — 팀 합의 후 후속 PR

### 공통 계약·백엔드 담당

- 기존 5개 필드와 하위 호환되는 선택형 `touch.interaction`의 필드 이름·타입·단위·필수 여부·`null` 의미와 오류 형식을 검토하고, 합의된 내용만 `contract/frontend-backend.openapi.yaml`과 `contract/backend-ai.openapi.yaml`에 반영해 주세요.
- `POST /api/v1/sessions/{session_id}/features`에서 합의된 추가 값을 검증하고 버리지 않고 ai-engine으로 전달해 주세요. 기존 5개만 있는 요청도 유지하는 방향을 제안합니다.
- 없는 값은 0으로 바꾸지 말고 타입·범위 오류, 알 수 없는 필드, 세션 종료, 시간 구간, 중복·지연 처리와 이전 클라이언트 호환을 검증해 주세요.
- `window_sequence`를 추적에만 쓸지 중복 제거·오래된 응답 차단에 사용할지는 별도 합의해 주세요. 이 PR의 번호는 중복 제거를 보장하지 않습니다.
- Jev 어댑터·저장·보관 정책과 지원 결과 이벤트는 별도 결정해 주세요.

### AI·비전 담당

- 백엔드와 합의한 추가 통계 입력을 ai-engine에서 받아 보존하는 형식과, 비전 관측·상황 태그의 시간 구간을 어떻게 맞출지 검토해 주세요.
- 위 표의 각 필드가 규칙표·Jev 질문에서 유용한지와 관측 부족·모름 처리, 지원 판단의 근거·품질 표현을 검토해 주세요.
- 현재의 placeholder 응답을 실제 판단 결과로 취급하지 않고, Jev 호출 위치·지연·실패 시 대체 동작을 백엔드와 합의해 주세요.

### 프론트·공통 검증

- 전송은 프론트 파일럿으로만 준비했습니다. 서버의 필드 수신·AI 전달과 팀 계약이 확정되면 기본 활성화 여부를 별도 결정하고 각 서비스의 실제 입력을 함께 검증합니다.
- `window.kioskTouchLogDraft.transmission()`은 HTTP 요청 상태·성공 수·마지막 구간 종료 시각만 보여 줍니다. 추가 필드가 백엔드에서 보존되거나 AI에 전달됐는지 증명하지 않습니다.
- [기존 프론트↔백엔드 계약](../contract/frontend-backend.openapi.yaml), [기존 백엔드↔AI 계약](../contract/backend-ai.openapi.yaml), [터치 로그 검토](Touch-Log-Review.md)를 함께 검토합니다.
- 열린 PR #70도 `OrderPage.tsx`를 수정하므로 작성자들이 병합 순서를 정하고 뒤에 병합하는 쪽에서 충돌과 동작을 확인해야 합니다.

### 합성 요청 예시 — 확정 계약이 아닌 제안

```json
{
  "screen_id": "menu",
  "window_start": "2026-11-02T01:00:00Z",
  "window_end": "2026-11-02T01:00:02Z",
  "touch": {
    "tap_count": 4,
    "miss_tap_count": 1,
    "repeat_tap_count": 0,
    "back_count": 0,
    "dwell_ms": 12000,
    "interaction": {
      "schema_version": "touch-interaction-pilot-v1",
      "visit_id": "example-visit",
      "window_sequence": 1,
      "outside_tap_ratio": 0.25,
      "pointer_cancel_count": 0,
      "pointer_interrupted_count": 0,
      "scroll_event_count": 3,
      "category_change_count": 1,
      "options_open_count": 1,
      "options_close_count": 0,
      "screen_transition_count": 0,
      "screen_revisit_count": 0,
      "cart_change_count": 1,
      "selection_change_count": 2,
      "ui_settings_change_count": 0,
      "voice_state_change_count": 0,
      "since_last_input_ms": 500,
      "order_busy_ms": 300,
      "options_open": true,
      "order_busy": false,
      "voice_enabled": false,
      "microphone_active": false,
      "voice_processing": false,
      "voice_auto_off": null,
      "ui_settings": {
        "large_text": false,
        "large_button": false,
        "simple_screen": false,
        "step_guide": false,
        "low_screen": false,
        "high_contrast": false
      },
      "outside_nearest_distance_mean_px": 8.5,
      "outside_nearest_distance_sample_count": 1
    }
  },
  "vision": null
}
```

위 예시의 모든 횟수는 0 이상의 정수, 시간은 밀리초, 거리는 CSS px이며 비율은 0~1이다. `outside_tap_ratio`, `outside_nearest_distance_mean_px`, `screen_revisit_count`, `since_last_input_ms`, `order_busy_ms`, `options_open`, `voice_enabled`, `microphone_active`, `voice_processing`은 관측 불충분 시 `null`을 제안한다. `voice_auto_off`의 `null`은 자동 종료 이유가 없거나 관측되지 않았음을 뜻한다. `vision`은 측정값이 없으면 `null`이다. 이 예시는 서버 수신·저장·Jev 판단 완료를 의미하지 않는다.

## 7. 검증 범위

- 2026-11-03 프론트 단위 테스트 111개와 TypeScript/Vite 빌드가 통과했다. Chromium 검사는 고정 서버 응답으로 7개 통과(하위 검사 포함), 실제 서비스 선택 검사는 1개 건너뛰었다. 기본 비활성화, 명시적 파일럿 전송, 세션 교체·실패, 샘플 모드를 확인했다.
- 현재 backend 모델에 추가 필드를 넣는 로컬 확인에서 `interaction`이 유지되지 않음을 확인했다. 서버 응답 성공만으로 추가 필드 보존이 증명되지 않는다.
- 서버 모델·계약을 이 PR에서 수정하지 않는다. 따라서 추가 필드가 백엔드에서 유지되거나 ai-engine까지 전달되는 통합 검증은 담당자 후속 구현 후 수행해야 한다.
- 실제 G10·카메라·참가자 데이터·Jev 판단 효과는 이 검증에 포함하지 않는다.
