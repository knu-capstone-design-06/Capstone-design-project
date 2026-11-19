# 터치·상호작용 전체 확장 계약 합의안

- 작성일: 2026-11-16
- 상태: **팀 검토용 제안 / 미채택 / 서비스 미적용**
- 검토 반영일: 2026-11-18
- 작성 범위 결정: 백엔드 담당자가 PR #72의 전체 확장에 대한 계약 합의안 작성을 요청했다. 이는 아래 정책의 팀 채택이나 기존 계약 수정 허용을 뜻하지 않는다.
- 기준: PR #72 병합 커밋 `f316e708a98a5299e48d7fcfcdc3805dd22eb9ca`의 프론트 생산자·전송기와 두 OpenAPI의 TouchFeatures. #77 판단 계층은 해당 PR의 검토 중 변경으로 구분한다.
- 검토 자료: 이 합의안, [독립 검토 스키마](touch-interaction-contract-proposal.openapi.json), [합성 요청 예시 6종](touch-interaction-contract-examples.json).

## 1. 제안하는 결과와 범위

기존 `POST /api/v1/sessions/{session_id}/features`의 `touch`에 선택형 `interaction` 객체를 추가한다. 기존 필수 정수 5개와 기존 요청은 유지한다. 확장 전체 32개와 중첩 설정 6개의 의미를 명시하여, 수신 모델에서 버리지 않고 백엔드 판단 계층의 관측 근거까지 전달하는 것을 목표로 한다.

프론트는 backend와만 통신한다. backend는 검증된 원래 창 입력을 내부 판단 계층에 직접 넘긴다. 이 배선은 #77에 이미 있으며, 확장을 수신 모델에서 보존하는 일은 후속 구현이다. AI 리뷰를 반영한 수정안은 `AnalyzeRequest`를 구성할 때 `touch.interaction`을 제외해 ai-engine `/v1/analyze`에는 기존 5개 터치 필드만 보내는 것이다. 확장의 내부 분석 전달은 보류하며, ai-engine 응답에 터치 값을 되돌려 실어 판단에 사용하는 경로도 추가하지 않는다. 이 수정안의 팀 채택은 별도다.

**수신·보존, 규칙 입력 사용, Jev 질문 사용, 화면 지원 활성화는 각각 별도 완료 조건이다.** 계약 채택만으로 지원 판단·기본 전송·유료 호출·영구 저장을 활성화하지 않는다.

## 2. 합의가 필요한 정책과 권장안

| ID | 결정할 내용 | 권장안 | 확인 담당 |
|---|---|---|---|
| D01 | 수신 범위 | 아래 32개 전체를 한 버전의 선택형 객체로 정의. 기존 5개 필수 필드는 유지 | 프론트·백엔드·AI |
| D02 | 필수·선택·결측 | 객체가 없으면 이전 클라이언트. 객체가 있으면 27개 필수, 음성 추가 5개만 선택. 하위 null 허용은 표대로 | 프론트·백엔드 |
| D03 | 버전·알 수 없는 필드 | backend 입구의 interaction 및 ui_settings에 미지원 버전·추가 속성 422를 제안. 오류 본문·필드 위치와 전송 중단의 복구 절차는 7절대로 계약 PR에서 확정. ai-engine에 새 422 정책을 적용하는 안은 아님 | 프론트·백엔드·AI |
| D04 | 전달·실패 경로 | 검증된 원창은 backend 판단에 직접 전달. AI 수정 의견에 따라 내부 AnalyzeRequest에서는 interaction 제외 제안. 내부 TouchFeatures의 외부 $ref 분리 필요. 분석 실패 fallback과 그림자 판단 배선은 유지 | 백엔드·AI |
| D05 | 시각·구간 | 프론트 파일럿은 `(window_start, window_end]`의 2초 창 경계를 이어서 전송한다. 5초 터치 집계 범위를 정확히 복원할 수 없어 원창 근거부터 보존한다. 집계 범위 변경·창 길이 변경·별도 5초 집계는 6절에서 검토한다. | 프론트·AI·비전·백엔드 |
| D06 | 순서·중복·누락 | sequence는 추적용. 같은 세션의 창 경계를 비교해 공백을 확인한다. 지연 도착, 동일 시각, 중복 제거는 별도 합의하며 #77의 시각 처리 검토를 참고한다. | 백엔드·AI·비전 |
| D07 | 화면 식별 | 이번 스키마에서는 screen_id를 string으로 유지하고 menu/menu_list를 자동 치환하지 않음. 공통 표준값·매핑은 별도 확정 | 프론트·AI·백엔드 |
| D08 | pause_s와 fixes_recent | 보정 경과는 근거 보존만 하고 pause_s 미연결. 후속 연결 시 listening/마이크 활성 중 None을 제안. fixes_recent는 #72 확장·백엔드 입력에 없으므로 None 유지(비전 replay의 계산과 구분) | 프론트·AI·비전 |
| D09 | 설정·판단 상태 | ui_settings는 프론트 관측 맥락으로만 전달. active/refused/withdrawn 같은 서버 판단 상태를 설정값으로 덮어쓰지 않음 | 프론트·AI·백엔드 |
| D10 | 전송·사용 활성화 | 기존 전송 기본 비활성화 및 그림자 단계 정책 유지. 전체 경로 공동 검사 후 별도 결정 | 관련 담당자 |
| D11 | 저장·보관 | 이번 계약은 DB 테이블·보관 기간·새 내보내기 API를 정하지 않음. 기존 메모리 기록을 영구 저장으로 설명하지 않음 | 백엔드·AI·비전 |

위 표의 모든 행은 **팀 최종 미채택**이다. 담당자의 채택 의견은 아래에 기록하되 팀 전체의 채택과 구분한다. 단순 승인 또는 문서 PR 병합을 전체 정책의 자동 채택으로 처리하지 않는다.

### 2.1 게시된 검토 응답과 반영 상태

| 담당·검토일·근거 | 항목별 의견 | 이번 반영과 남은 결정 |
|---|---|---|
| 프론트 · 2026-11-16 · [리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/89#pullrequestreview-5920084506) | D01/D02의 32개·27+5·null 대조, D03의 visit_id·422 중단 확인. 문서 추가 승인, 팀 정책 채택과 구분 | 정상 생산자는 현재 32키를 보낸다는 설명 추가. #70 화면 개편의 수집 범위·largeView는 후속 버전 검토로 분리 |
| AI · 2026-11-17 · [리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/89#pullrequestreview-5935066824) | D01/D03/D06/D08/D09/D10/D11 채택 의견. D04 직접 전달 동의·내부 전달 보류, options_open 직접 매핑 동의. D05 시간 집계 제안 | D04 수정안을 반영. D05 집계 제안은 아래 11-18 정정으로 대체. D02/D07을 비롯한 미답·공동 결정은 자동 채택하지 않음 |
| 비전 · 2026-11-17 · [리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/89#pullrequestreview-5937683293) | D05/D06/D08/D11 채택 의견. 5초는 터치 단서 집계 범위이며 비전 replay는 fixes_recent 계산. null 거절은 새 제한 | 집계 범위·서버 입력/비전 replay 구분과 더 엄격한 null 제안을 명시. 당시 동의한 D05의 집계 방법은 AI 정정 후 재확인 필요 |
| AI · 2026-11-18 · [추가 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/89#pullrequestreview-5949603279) | D04에서 확장 제외 및 내부 $ref 분리 제안. D05의 끝 시각 기준 5초 합산안을 철회. listening 보호·누락 원인·예시·422 보완 요청 | 1·5~9절과 예시에 반영. Jev 요청에 기존 터치 5개만 고르는 변경은 #77의 `ce3fcf4`에 반영됨 |
| 비전 · 2026-11-18 · [재검토](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/89#pullrequestreview-5952727263) | #72 병합으로 달라진 전송기 동작과 5초 집계 설명 수정 요청. 시선 관측 시 4초 기준 및 비전 replay와의 집계 범위 확인 권고 | 병합된 전송기 기준으로 6절을 정리하고, 4초 기준과 backend·비전 replay의 집계 범위를 4.3절과 D05에 반영 |

D04 수정안은 원창을 판단 층까지 보존하고 Jev 요청에는 허용된 필드만 보낸다. #77의 `ce3fcf4`에서 `shadow_state`를 수정해 프론트의 터치 필드 중 기존 5개만 명시적으로 선택한다. 판단 계층이 만드는 터치 단서와는 별개다. 이 변경은 #77 브랜치 기준이며, `AnalyzeRequest`에서 확장을 제외하는 작업은 D04에 따라 별도로 검증한다.

## 3. 공통 표기와 검증 제안

- 아래 필수는 interaction을 보낼 때의 하위 속성 존재 여부다. interaction 자체는 선택이며 생략을 허용한다. `interaction: null` 거절은 #72의 `InteractionFeatures | null`보다 엄격한 **새 제안**이다. 현재 정상 집계는 객체를 만들지만 타입상 null을 허용하므로, 최종 거절 여부와 생산자·하위 호환을 D02/D03에서 프론트와 재확인한다.
- 숫자 0과 boolean false는 관측한 결과다. null은 아래 각 정의의 결측·불명확 의미다. 선택 필드 생략은 그 생산자가 제공하지 않았다는 뜻이며, 자동으로 null/0/false로 채우지 않는다.
- 정수는 비음수이며 bool·문자열·소수의 강제 변환을 하지 않는 런타임 검증을 제안한다. 거리·비율은 유한한 숫자만 허용한다. NaN/Infinity는 JSON 값으로 허용하지 않는다.
- 독립 JSON 스키마는 구조·범위를 표현한다. JSON Schema의 integer 판정은 수학적 정수이며 일부 검증기는 1.0을 허용하므로 Python strict integer와 완전히 같은 판정기를 뜻하지 않는다. 런타임 strict 검사도 별도 검증한다.
- `visit_id`는 빈 문자열을 거절하는 안이다. 이는 기존 TypeScript의 string보다 강한 **새 제안**이며 프론트 확인이 필요하다. 길이 상한·총 요청 크기·서버 시계 허용 오차는 근거 없이 이번에 정하지 않는다.
- 상위 요청·기존 5개 필드의 extra 처리나 응답 구조를 이 제안으로 일괄 변경하지 않는다. `additionalProperties: false`는 새 interaction과 그 ui_settings에 한정한다.

## 4. 전체 필드 사전

### 4.1 버전·방문·순서

| 필드 | 타입·범위 | 필수 | 단위·의미·결측 |
|---|---|---|---|
| schema_version | string const `touch-interaction-pilot-v1` | 예 | 계산 정책 식별자. 버전명 자체가 팀 정책 채택을 뜻하지 않음 |
| visit_id | 비어 있지 않은 string 제안 | 예 | 끝 시점 현재 화면 방문 식별자. 세션 소유자 인증·DB 키 아님 |
| window_sequence | integer ≥0 | 예 | 현재 서버 세션의 전송 시도 구간 순번. 추적용, 멱등성 키 아님 |

### 4.2 입력·거리·이동·선택 집계

다음 횟수는 같은 세션에서 해당 시간 구간 전체의 관측이다. 구간이 화면 이동을 포함하면 모두 마지막 화면에서 일어났다고 해석하지 않는다.

| 필드 | 타입·범위 | 필수 | 단위·의미·결측 |
|---|---|---|---|
| outside_tap_ratio | number 0~1 또는 null | 예 | miss_tap_count / tap_count. 누름 0회는 null. 실패율 아님 |
| outside_nearest_distance_mean_px | number ≥0 또는 null | 예 | CSS px. 대상 밖 누름의 가장 가까운 활성 대상 거리 평균. 관측 표본 없음은 null |
| outside_nearest_distance_sample_count | integer ≥0 | 예 | 평균에 사용한 누름 수. 동률 후보가 많아도 누름당 한 표본 |
| pointer_cancel_count | integer ≥0 | 예 | 취소로 끝난 입력 수. 실패 수 아님 |
| pointer_interrupted_count | integer ≥0 | 예 | 끝까지 관측하지 못한 입력의 중단 기록 수 |
| scroll_event_count | integer ≥0 | 예 | 관측 영역 전체 스크롤 이벤트 수. 제스처 수·이동 거리·메뉴 탐색 수 아님 |
| category_change_count | integer ≥0 | 예 | 메뉴 분류 변경 수 |
| options_open_count | integer ≥0 | 예 | 옵션 창 열기 수 |
| options_close_count | integer ≥0 | 예 | 옵션 창 닫기 수. 선택 포기나 주문 취소로 단정하지 않음 |
| screen_transition_count | integer ≥0 | 예 | 출발 화면이 있는 화면 진입 수 |
| screen_revisit_count | integer ≥0 또는 null | 예 | 같은 로컬 세션에서 방문한 화면 재진입 수. 세션 시작 기록 잘림은 null |
| cart_change_count | integer ≥0 | 예 | 서버 Cart 버전 증가 관측 횟수. 최초 기준선 제외, 개별 성공·터치/음성 원인 아님 |
| selection_change_count | integer ≥0 또는 null | 예 | 상품·옵션·수량 상태 변화 수. 최초 기준선 제외. 세션 시작/최초 기준선 없으면 null |
| ui_settings_change_count | integer ≥0 | 예 | 접근성 설정 변경 수. 제안 수락·거절·적용 성공 수 아님 |
| voice_state_change_count | integer ≥0 | 예 | 모드·마이크·처리 단계 변화 수. 최초 기준선 제외, 발화 횟수 아님 |

### 4.3 경과·처리 대기 시간

| 필드 | 타입·범위 | 필수 | 단위·의미·결측 |
|---|---|---|---|
| since_last_input_ms | integer ≥0 또는 null | 예 | ms. 현재 방문 마지막 터치 누름 이후 벽시계 시간. 누름 이력 없음은 null. 숨김·시스템 대기 포함 |
| order_busy_ms | integer ≥0 또는 null | 예 | ms. 구간 내 loading/saving 화면 상태 지속 합. 시작 상태 모름은 null. 실제 네트워크·서버 시간 아님 |
| voice_busy_ms | integer ≥0 또는 null | 아니오 | ms. 구간 내 processing/speaking 관측 시간 합. 시작/중간 상태 모름은 null |
| since_last_input_excluding_system_busy_ms | integer ≥0 또는 null | 아니오 | ms. 현재 방문 마지막 누름부터 주문 loading/saving 또는 음성 processing/speaking 시간의 합집합을 뺀 경과. 누름 없음·이력 부족·대상 기간 숨김/중단은 null |

`order_busy_ms + voice_busy_ms`를 전체 시스템 대기로 더하지 않는다. 두 대기가 겹칠 수 있다. 마지막 입력 이후 보정값은 현재 2초 구간보다 클 수 있고, 원래 경과와 dwell_ms도 구간 길이로 잘라서는 안 된다. 수동 화면 읽기와 음성 `listening`(키오스크 이용자 발화) 시간은 현재 보정값에서 제외되지 않는다.

예를 들어 마지막 누름 뒤 9초 동안 listening이면 보정값도 9000ms일 수 있다. 이를 그대로 `pause_s=9`로 쓰면 파일럿 `lost_pause_s=8.0`을 넘어 발화 중 헤맴으로 판단할 수 있다. 이후 비전 정보를 연결하면 이용자가 화면을 향하거나 두리번거림 단서가 있을 때 4-2의 `lost_pause_s_vision=4.0`이 적용돼 더 짧은 발화도 해당 기준에 걸릴 수 있다. D08의 연결 보류를 유지하며, 후속 연결에서는 `voice_phase == listening` 또는 `microphone_active == true`일 때 `pause_s=None`으로 두는 보호 조건을 제안한다. 연결이 채택된 관측 가능 구간에서만 `since_last_input_excluding_system_busy_ms / 1000`을 사용하고, 결측은 None으로 둔다. 음성 맥락이 결측인 구간과 수동 읽기 중의 판정 기준도 별도 합의하며, 원래 경과·dwell_ms로 대체하지 않는다.

### 4.4 구간 끝 시점 맥락

| 필드 | 타입 | 필수 | 의미·결측 |
|---|---|---|---|
| options_open | boolean 또는 null | 예 | 옵션 창 열림. 관련 상태 미관측은 null |
| order_busy | boolean | 예 | 주문 상태 loading/saving 여부. 현재 생산자의 전송 전제상 관측됨. 다른 버전에서 미관측이면 false를 만들지 말고 형식을 다시 합의 |
| voice_enabled | boolean 또는 null | 예 | 음성 모드 켜짐. 미관측은 null |
| microphone_active | boolean 또는 null | 예 | 마이크 활성 상태. 미관측은 null |
| voice_processing | boolean 또는 null | 예 | backend 요청 processing 단계. 미관측은 null |
| voice_phase | idle/listening/processing/speaking/null | 아니오 | 음성 제어 단계. 상태 없음·미지원 단계는 null |
| voice_speaking | boolean 또는 null | 아니오 | speaking 단계 여부. 마이크 종료 대기부터 포함할 수 있어 순수 재생 시간 아님 |
| voice_busy | boolean 또는 null | 아니오 | processing 또는 speaking 여부. 단계 미관측은 null |
| voice_auto_off | silence/idle/null | 예 | 자동 종료 사유. null은 자동 종료 아님 또는 사유 미관측. 두 경우를 구별하지 못함 |
| ui_settings | 아래 객체 | 예 | 관측된 설정. 지원 판단·사용자 반응을 대신하지 않음 |

ui_settings는 `large_text`, `large_button`, `simple_screen`, `step_guide`, `low_screen`, `high_contrast` 여섯 boolean을 모두 보낸다. 각 값은 프론트의 현재 설정이며 수동 화면 읽기 켜짐/재생 상태는 없다. 알려지지 않은 새 설정 필드는 이 버전에 조용히 추가하지 않는 안이다.

합계: interaction 속성 **32개 = 필수 27개 + 선택 5개**, ui_settings 내부 속성 **6개**.

## 5. 기존 필드·판단 입력의 경계

기존 tap_count/miss_tap_count/repeat_tap_count/back_count/dwell_ms는 필수 비음수 정수로 유지한다. #72는 다섯 값이 산출되지 않은 구간을 보내지 않으며, 서버가 null을 0으로 바꾸지 않는다.

| 입력 | 사용 제안 | 금지·보류할 해석 |
|---|---|---|
| interaction 전체 | 검증 후 backend 판단의 창 근거에 손실 없이 보존, 외부 Jev에는 별도 필드 선택 | 수신 성공만으로 규칙/Jev에 사용됐다고 설명·32개 전부를 자동 외부 전송 |
| options_open | 합의 후 끝 시점 boolean/null을 WindowInput.options_open에 그대로 전달 | options_open_count를 열림 상태로 사용·null을 false로 대체 |
| 보정 경과 | 먼저 근거로 보존, pause_s 연결 보류 | 보정값 없이 원래 경과나 dwell_ms를 pause_s로 사용 |
| voice_busy/order_busy | 대기 맥락으로 제공 | true인 동안 무입력을 사용자 망설임으로 단정 |
| repeat_tap_count·거리 평균 | 각각의 관측 근거 | 백엔드에 없는 fixes_recent·의도한 버튼·손 떨림·장애로 대체 |
| cart_change_count | Cart 진행 관측 근거 | 개별 조작 성공·화면 전진·사용자 확인으로 대체 |
| 2초 miss/back 집계 | 원래 구간 길이와 함께 보존 | 5초 터치 단서 집계라고 재명명·단순 3창 합산 |

PR #77의 기존 5개 값 연결 자체도 2초/5초 의미 차이가 있으므로 D05가 미결인 동안 새로 임계값을 강화하거나 자동 지원을 켜지 않는다. 전체 확장 보존으로 이 차이가 해결됐다고 설명하지 않는다.

AI 리뷰 기준 #77은 수신 창마다 판단하며 2초 창의 miss/back을 그대로 연결한다. 5초는 판단 실행 주기나 비전 관측 창 길이가 아니라 `PILOT_PARAMS.touch_span_s`의 터치 단서 집계 범위다. D05 확정 전에는 **확장에서** `misses_recent`·`backs_recent`·`fixes_recent`를 새로 채우지 않는다는 AI 의견을 기록한다. 비전 replay는 원시 터치로 `fixes_recent`를 계산하지만 #72 확장과 현재 백엔드 입력에는 그 값이 없으므로 None을 유지한다.

`options_open`은 #77에서 4-2의 강조 대상(메뉴 옵션 창이 열렸으면 `cart-add`)을 정하는 맥락이며 지원을 열지 말지 결정하는 횟수 지표가 아니다. `ui_settings`는 판단 층의 active/refused/withdrawn 상태를 대신하지 않는다.

## 6. 시간·중복·화면·품질

- 시간 구간은 timezone이 있는 window_start/end, end > start를 유지한다. 2초는 #72 생산자의 창 길이이며, 기존 서버 요청에는 계약의 허용 범위를 적용한다.
- #72가 병합된 main의 전송기는 250ms 간격으로 준비 여부를 확인하고 요청은 한 건씩 보낸다. 한 창을 전송할 때 다음 종료 시각을 현재 종료 시각에 2초를 더해 정한다. 요청이 느려도 필요한 기록이 남아 있으면 지나간 창을 이 경계로 순서대로 집계해 보낸다. 종료를 기다리는 누름이 있고 다른 관측 근거가 충분하면 같은 종료 시각으로 다시 확인한다.
- 시작·전경 복귀 직후 또는 기록 한도 초과로 관측이 부족하면 창을 건너뛸 수 있다. 시험 전송용 메모리는 스크롤과 나머지 이벤트를 각각 최대 1,000개 보관한다. 스크롤이 쌓여도 전송용 화면 진입·주문 상태 기록은 별도 버퍼에 남으며, 스크롤 버퍼에서 필요한 구간이 잘린 창은 제외된다. 일반 로컬 저장·내보내기는 전체 이벤트 최근 1,000개를 사용한다.
- 일시 실패한 요청에 같은 구간을 자동 재전송하지 않는다. 같은 세션의 수신 창을 관측 시각 순서로 비교할 때 `window_start == 직전 window_end`이면 경계가 이어지고, 더 뒤이면 두 창 사이에 관측 근거가 비어 있다. 건너뛴 창·전송 실패에 따른 비어 있는 구간은 0회로 채우지 않는다. 겹침과 지연 도착의 처리 기준은 D06에서 별도로 정한다. [병합된 전송기 설명](Jev-Touch-Features.md#5-전송-조건과-실패-처리)
- sequence는 새 서버 세션 범위의 추적 값이다. 여러 탭·생산자·프로세스 사이 전역 유일성과 저장 키로의 사용은 미정이다.
- 늦은 응답·창, 동일 종료 시각, 중복 창의 정책은 서로 구분한다. PR #77의 늦은 창 기록 처리가 정확히 한 번 판단을 보장하는 것은 아니다.
- 화면·visit_id는 구간 끝 시점이고, 구간의 집계는 같은 세션의 여러 방문을 포함할 수 있다. 화면별 집계로 오해하지 않는다.
- menu/menu_list는 확정 매핑 없이 자동 치환하지 않는다. 현재 상태의 화면 진행값을 정확하다고 주장하지 않는다.
- 기준 #72에서 낮은 화면 상단 안내는 수집 루트 밖이다. #70 `7264577`의 화면 개편은 복귀 영역을 루트 안으로 옮기고 별도 largeView를 사용하므로, 합칠 때 수집 범위·실제 확대 관측을 다시 대조한다. 현재 버전에 새 설정을 조용히 추가하면 D03의 422 중단과 충돌하므로 후속 버전/계약 검토로 둔다. 전체 키오스크 영역 관측이나 거래 감사 기록을 보장하지 않는다.
- 원시 좌표·포인터 이벤트·상품별 선택 내역·음성·인식 문장·영상은 이 확장에 넣지 않는다. 비전은 이번 합의 범위에 새 필드를 추가하지 않는다.

### D05: 2초 합계로 정확한 최근 5초를 복원할 수 없는 이유와 선택지

끝 시각 t=10일 때 연속 창 `(4,6]`, `(6,8]`, `(8,10]`을 끝 시각이 `(5,10]`에 든다는 이유로 합치면 실제 범위는 `(4,10]`의 6초다. 창 전체가 포함되는 것만 고르면 `(6,10]`의 4초뿐이다. 첫 2초 창 안에서 누름이 5초 전후 어디서 발생했는지 합계만으로는 알 수 없어 비례 배분으로도 정확하게 복원할 수 없다. 이 한계는 병합된 #72 전송기의 창 경계가 정확히 이어져도 동일하다. AI 담당자의 11-17 끝 시각 기준 합산 의견은 11-18 리뷰에서 철회됐다.

| 회의 선택지 | 함께 정할 조건 |
|---|---|
| (가) 판단 층 touch_span_s를 4초 또는 6초로 변경 | 연속 2초 창 2개 또는 3개가 필요하다. AI는 6초의 구현 비용이 낮다는 의견을 제시했다. 현재 backend 규칙표와 비전 replay는 5초 기준이므로 양쪽의 범위를 함께 바꿀지 backend만 다르게 둘지 정한다. 규칙표 임계값과 실험 비교 조건, 실제 창의 빈틈·중복도 함께 검증한다. |
| (나) 프론트 창 길이와 경계 간격을 1초 또는 2.5초로 변경 | 정확히 이어진 창 5개 또는 2개가 있어야 5초를 덮는다. 창 누락 시 처리, 전송 부하, 임계값을 재검토한다. 250ms 준비 확인 간격은 별도다. |
| (다) 프론트가 원시 기록에서 최근 5초 집계를 별도 제공 | 정확한 관측 범위·필드/버전·결측·겹친 창 중복 처리와 백엔드/비전 결합 계약 필요 |

어느 안도 자동 채택하지 않는다. 관측 구간이 덮이지 않거나 부분 창의 원래 입력 시각을 알 수 없으면 임의로 보간·0 채우기하지 않는다. 비전 replay의 segment_s 파일럿 1초, 터치 집계 touch_span_s 5초, 별도 상황 태그 window_s는 서로 다른 길이이므로 값과 구간을 함께 전달하는 후속 계약에서 맞춘다.

기존 [터치 로그 검토 문서](Touch-Log-Review.md#5-회의에서-결정할-항목)의 T03(거리·대상), T05(체류·대기), T13(집계 범위·분모·결측·버전)을 함께 검토한다. 두 문서의 제안을 별개의 확정 정책으로 취급하지 않는다. 역방향 링크는 해당 문서 담당자의 후속 변경에서 추가하도록 요청한다.

## 7. 오류·하위 호환·배포

현행 `/features` OpenAPI의 422는 설명만 있고 응답 본문 스키마가 없다. FastAPI 기본 검증 응답은 `detail` 배열이며, 계약의 문자열 `detail`을 쓰는 `ErrorResponse`와 다르다. 따라서 “기존 형식”으로 확정됐다고 하지 않는다. D03을 채택하는 계약 PR에서 실제 런타임과 맞는 422 본문·예시·오류 필드 위치를 프론트와 확정하고 검사한다. 새 error_code나 오류 envelope는 이 문서로 추가하지 않는다. 타입/범위·필수 누락·버전·추가 속성의 오류 위치를 구별하며, 세션 없음/완료 404/410과 분석 실패 fallback 및 응답 support 정책은 유지한다.

interaction을 보내지 않는 기존 형식은 계속 유효하게 한다. 27개 필수 값만 있는 예시는 음성 추가 5개를 생략하는 **하위 호환용 합성 형식**이며, 기준 #72의 현재 정상 생산자가 보내는 형식은 32개다. 선택 5개 생략을 허용하되 서버에서 false/0으로 만들어 판단하지 않는다. 명시적 interaction:null의 허용 여부는 3절의 더 엄격한 제안으로 별도 확인한다.

합성 요청 예시의 용도는 다음과 같다. 모두 문서용 가상 값이며 실제 생산 함수 출력·동일 이용자의 연속 기록으로 취급하지 않는다. 기본·전체 예시의 sequence가 같은 것은 대체 표현을 보여 주기 때문이며, sequence가 증가하는 busy 예시는 시각도 뒤 구간으로 옮겼다. 서로 다른 방문 ID를 써 독립 스냅샷을 구분한다.

| 예시 키 | 확인할 범위 |
|---|---|
| legacy_request | interaction 없는 기존 요청 |
| base_interaction_request | 27개 필수 키만 있는 하위 호환용 합성 요청. 기준 #72가 현재 직접 만드는 형식은 아님 |
| full_interaction_request | 32개 전체 키. session_start/선택 기준선 이력 부족을 나타내 revisit·selection은 null |
| busy_interaction_request | processing/speaking 중 대기 관측 예시. 앞 대체 예시보다 늦은 창 시각 |
| normal_interaction_request | 정상 관측 이력이 있어 revisit·selection 모두 0인 전체 확장 |
| listening_interaction_request | listening·마이크 활성 상태에서 voice_busy는 false, 보정 경과는 9000ms인 반례. 후속 pause_s 보호가 필요하며 현재 지원 실행 예시는 아님 |

엄격한 새 속성 거절은 향후 프론트의 무버전 추가를 막고, 422를 한 번 받은 #72는 해당 세션 전송을 멈춘다. D03에서는 형식뿐 아니라 운영 중 버전 불일치 시 배포 순서·안내·전송 재개 절차도 프론트와 정한다. 미지원 버전을 버리고 200을 주는 방향과 섞어 적용하지 않는다.

현행 `contract/backend-ai.openapi.yaml`의 TouchFeatures는 외부 계약 정의를 `$ref`로 공유한다. 외부 정의에 interaction을 더하면 내부 계약도 바뀌므로, **전달하지 않는 수정안을 채택할 때 내부 TouchFeatures를 기존 5개 필드 전용 정의로 분리**해야 한다. AI 담당자는 계약 PR에서 내부 계약을 맡겠다는 의견을 남겼다. backend가 AnalyzeRequest를 만들며 확장을 제외하는 검사와 내부 요청이 5개만 유지되는 검사를 함께 준비한다. 반대로 내부 전달안을 택하면 두 수신 모델과 계약을 맞춘 뒤 배포한다. 어느 경우든 값을 버리는 상태를 전달 성공으로 발표하지 않는다. 계약·수신 backend·판단/Jev 필드 선택 준비를 확인한 뒤 마지막에 프론트 파일럿을 명시 활성화하며, 자동 지원 활성화와 분리한다.

## 8. 구현 파일·검사·브랜치 순서

1. 이 합의안의 D01~D11에 담당자별 답과 수정값을 기록한다. 채택된 내용만 두 OpenAPI와 예시에 반영하는 계약 PR을 준비한다.
2. backend sessions 입력 검증·판단 원창 전달·내부 analyze 확장 제외 spy 검사를 준비한다. 내부 5개 전용 정의와 ai-engine 입력 경계는 AI 담당과 대조한다. 공용 기존 코드 수정은 별도 백엔드 담당자 확인을 따른다.
3. #77 반영 후 backend decision 창 근거 보존과 선택한 입력 매핑을 연결한다. AI 담당자의 작업 브랜치에는 직접 커밋하지 않는다.
4. 이전 5개만 있는 요청, 확장 27개/32개 요청, null/생략/0, 잘못된 타입·버전·속성, 취소·완료·늦은 창·대기를 고정 응답으로 검증한다. API 수신→전달→판단 기록을 대조한다.
5. 실제 공동 검사는 샘플 세션으로 수행한다. API 200, backend 원창 보존, 내부 analyze 제외, 판단 기록, Jev에 고른 필드만 전달, 규칙 사용은 각각 관찰 근거를 남긴다. 실제 AI 호출·DB 저장은 별도 필요성에 따라 시행한다.

PR #72는 `f316e70`으로 main에 병합됐다. #89의 최신 설명은 병합된 전송기를 기준으로 하며, 판단 계층 연결은 #77 반영 뒤에 진행한다. PR 병합은 작성자인 백엔드 담당자가 직접 한다.

이번 수정은 단순 오탈자 정리가 아니라 전달 경계·시간 집계·호환 제한·오판 방지 조건을 보완하므로 마지막 커밋 재검토가 필요하다. AI는 D04·D05·D08과 Jev 필드 선택, 프론트는 interaction:null·422·예시와 집계 선택지, 비전은 D05의 집계 범위 변경 선택지와 fixes_recent 범위를 재확인한다. [협업 규칙](Convention.md#4-pull-request)은 승인 후 새 커밋이 있으면 마지막 커밋을 다시 검토·승인하도록 하므로, 이전 승인이 화면에 남아 있어도 재검토 완료로 간주하지 않는다.

## 9. 담당자에게 요청할 답변

- 프론트: 32개 이름/타입, 27+5 하위 호환, order_busy의 non-null, visit_id와 interaction:null의 추가 제한을 재확인한다. D05 선택지·422 본문과 중단 복구·#70 화면 개편 후 수집 범위를 함께 정할 수 있는가?
- AI: D04의 내부 analyze 제외·공유 $ref 분리와 Jev 허용 필드 선택, options_open 매핑을 확정할 것인가? D05 정정 후 선택지와 발화·수동 읽기의 pause_s 보호를 확인해 줄 수 있는가?
- 비전: 2초 터치·5초 터치 집계 범위·비전 관측 창의 정합성을 어떤 별도 계약으로 정할 것인가? fixes_recent는 비전 replay에서만 계산되며 백엔드 경로에는 없는 범위와 서비스의 gaze 부재를 확인하는가?
- 백엔드: 런타임 strict 타입, null/생략 유지, fallback/410, 창 식별·유실 경계의 검사 범위에 동의하는가?

기록 양식: `D번호 / 채택·수정·보류 / 수정 내용 / 확인 담당자 / 확인일 / 결정 링크`. 부분 채택도 명시한다.

## 10. 근거

- [PR #72](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/72)
- [기준 TypeScript 필드](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/f316e708a98a5299e48d7fcfcdc3805dd22eb9ca/frontend/src/shared/api/interactionTypes.ts)
- [기준 집계 구현](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/f316e708a98a5299e48d7fcfcdc3805dd22eb9ca/frontend/src/features/order/interactionFeatures.ts)
- [기준 대기 시간 집계](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/f316e708a98a5299e48d7fcfcdc3805dd22eb9ca/frontend/src/features/order/interactionWait.ts)
- [병합된 프론트 전송기](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/f316e708a98a5299e48d7fcfcdc3805dd22eb9ca/frontend/src/features/order/touchFeatureTransport.ts), [프론트 필드·미합의 정책 문서](Jev-Touch-Features.md)
- [PR #77의 Jev 터치 필드 선택](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/ce3fcf4/backend/app/modules/decision/jev_questions.py), [PR #77의 파일럿 기준](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/4c1fabb07977e66713360f86eb4a4b2947d05658/backend/app/modules/decision/schemas.py)
- [현행 외부 계약](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/main/contract/frontend-backend.openapi.yaml), [현행 내부 계약](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/main/contract/backend-ai.openapi.yaml)

실제 기존 계약·프론트·백엔드·ai-engine·DB 파일은 이번 작성으로 변경하지 않았다.

## 11. 작성 후 확인 결과

- 디스크에 저장한 스키마·요청 예시 JSON을 다시 읽어 문법을 확인했다.
- 기준 TypeScript의 32개 속성 이름, 필수 27개/선택 5개, null 허용과 스키마가 일치한다. 중첩 설정은 6개다.
- 최초 작성 때 필드 목록·결측 허용 대조, 당시 요청 예시 4종, 타입·범위·미지원 버전·추가 속성·필수 누락에 대한 **79개 구조 검사**가 통과했다. 2026-11-18 수정으로 정상 관측·음성 listening 반례를 더해 예시는 6종이다.
- 이 검사는 사용한 JSON Schema 부분집합에 대한 로컬 구조 검사다. OpenAPI 전체 적합성 검사기나 실제 서버 통합 검증을 실행한 것은 아니다. 런타임 422 직렬화·타입 검증은 구현 후 확인한다.
- 최초 합의안 작성 단계에서 git status --short는 빈 출력이고 git diff --check는 통과했다. 리뷰 반영도 같은 문서 3개만 수정하며 실제 계약·서비스 코드·DB는 바꾸지 않는다. 실제 AI·DB 호출은 하지 않았다.
- 2026-11-18 리뷰 반영 후 **293개 오프라인 부분집합 검사**가 통과했다. 32개 속성·27개 필수·5개 선택의 타입/결측/enum을 기준 TypeScript와 대조했고, 스키마의 설명을 제외한 검증 제약은 c9807dc와 동일하다. 6종 요청의 바깥 형식은 현행 FeatureWindowRequest로, 확장은 검토 스키마의 사용된 부분집합으로 검사했다. 필수 누락·각 필드 null/오타입·음수/비유한 수·추가 속성·선택 5개 생략·시각 예시·listening 반례·문서 상대 링크도 확인했다.
- 위 검사는 전체 JSON Schema/OpenAPI 검증기, 현재 프론트 생산 함수 실행, strict 수신 서버 구현, 실제 API/DB 통합 검증을 대신하지 않는다. 문서·예시 변경이므로 제품 빌드·실제 유료 호출은 반복하지 않았다.
- #72 병합 기준으로 프론트의 `interactionFeatures.test.mjs` 22개가 통과했다. 기록 버퍼 분리, 관측 부족 시 건너뛰기, 길게 누른 입력의 원래 창 유지, 지연 중 누락·중복 방지 및 전송 오류 후 다음 표본을 확인했다. 병합 전후 TypeScript 필드 정의는 동일하며, 예시 6종을 포함한 오프라인 부분집합 검사 295개도 통과했다.
