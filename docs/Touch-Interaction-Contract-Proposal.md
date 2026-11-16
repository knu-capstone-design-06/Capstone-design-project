# 터치·상호작용 전체 확장 계약 합의안

- 작성일: 2026-11-16
- 상태: **팀 검토용 제안 / 미채택 / 서비스 미적용**
- 작성 범위 결정: 사용자가 PR #72의 전체 확장에 대한 계약 합의안 작성을 선택했다. 이는 아래 정책의 팀 채택이나 기존 계약 수정 허용을 뜻하지 않는다.
- 기준: PR #72 `3d4b79c119aecf750148dc20e306be316b00f9d5`, PR #77 `457a56b513ccbdf1617d46d6b7468822dbc99b45` 및 현재 두 OpenAPI의 TouchFeatures.
- 검토 자료: 이 합의안, [독립 검토 스키마](touch-interaction-contract-proposal.openapi.json), [합성 요청 예시 4종](touch-interaction-contract-examples.json).

## 1. 제안하는 결과와 범위

기존 `POST /api/v1/sessions/{session_id}/features`의 `touch`에 선택형 `interaction` 객체를 추가한다. 기존 필수 정수 5개와 기존 요청은 유지한다. 확장 전체 32개와 중첩 설정 6개의 의미를 명시하여, 수신 모델에서 버리지 않고 백엔드 판단 계층의 관측 근거까지 전달하는 것을 목표로 한다.

프론트는 backend와만 통신한다. backend는 검증된 원래 창 입력을 내부 판단 계층에 직접 넘긴다. 현행 backend→ai-engine `/v1/analyze`에도 같은 확장을 넘기고 보존하는 안을 제안하며, AI 담당자의 채택과 수신 구현이 필요하다. ai-engine 응답에 터치 값을 되돌려 실어 백엔드 판단에 사용하는 경로는 추가하지 않는다.

**수신·보존, 규칙 입력 사용, Jev 질문 사용, 화면 지원 활성화는 각각 별도 완료 조건이다.** 계약 채택만으로 지원 판단·기본 전송·유료 호출·영구 저장을 활성화하지 않는다.

## 2. 합의가 필요한 정책과 권장안

| ID | 결정할 내용 | 권장안 | 확인 담당 |
|---|---|---|---|
| D01 | 수신 범위 | 아래 32개 전체를 한 버전의 선택형 객체로 정의. 기존 5개 필수 필드는 유지 | 프론트·백엔드·AI |
| D02 | 필수·선택·결측 | 객체가 없으면 이전 클라이언트. 객체가 있으면 27개 필수, 음성 추가 5개만 선택. 하위 null 허용은 표대로 | 프론트·백엔드 |
| D03 | 버전·알 수 없는 필드 | `schema_version`은 제안 버전 상수. interaction 및 ui_settings의 알 수 없는 속성과 미지원 버전은 422. 조용히 버리거나 이전 버전으로 해석하지 않음 | 프론트·백엔드·AI |
| D04 | 전달·실패 경로 | backend 판단에 검증된 원창 직접 전달. 기존 내부 분석 경로에도 동일 객체 보존. 내부 분석 실패 시 기존 features fallback 유지; 실패를 이유로 새 판단 실행 여부를 변경하지 않음 | 백엔드·AI |
| D05 | 시각·구간 | 집계는 `(window_start, window_end]`, 프론트 파일럿 2초. 5초 규칙값으로 변환·재명명하지 않고 근거 보존부터 진행 | 프론트·AI·비전·백엔드 |
| D06 | 순서·중복·누락 | sequence는 추적용. 정확히 한 번 처리나 연속 관측 보장 없음. 늦은 창 정책은 #77의 처리를 유지하고, 동일 시각·중복 제거 강화는 별도 합의 | 백엔드·AI·비전 |
| D07 | 화면 식별 | 이번 스키마에서는 screen_id를 string으로 유지하고 menu/menu_list를 자동 치환하지 않음. 공통 표준값·매핑은 별도 확정 | 프론트·AI·백엔드 |
| D08 | pause_s와 fixes_recent | 보정 경과도 우선 근거로만 보존. 수동 읽기·마이크 대기 맥락과 임계값 합의 전 pause_s 미연결. fixes_recent는 없는 값 그대로 None | 프론트·AI·비전 |
| D09 | 설정·판단 상태 | ui_settings는 프론트 관측 맥락으로만 전달. active/refused/withdrawn 같은 서버 판단 상태를 설정값으로 덮어쓰지 않음 | 프론트·AI·백엔드 |
| D10 | 전송·사용 활성화 | 기존 전송 기본 비활성화 및 그림자 단계 정책 유지. 전체 경로 공동 검사 후 별도 결정 | 관련 담당자 |
| D11 | 저장·보관 | 이번 계약은 DB 테이블·보관 기간·새 내보내기 API를 정하지 않음. 기존 메모리 기록을 영구 저장으로 설명하지 않음 | 백엔드·AI·비전 |

위 표의 모든 행은 **미채택**이다. PR 검토자는 채택·수정·보류를 ID별로 명시한다. 단순 승인 또는 문서 PR 병합을 전체 정책의 자동 채택으로 처리하지 않는다.

## 3. 공통 표기와 검증 제안

- 아래 필수는 interaction을 보낼 때의 하위 속성 존재 여부다. interaction 자체는 선택이며 생략을 허용한다. `interaction: null`은 허용하지 않는 안이다.
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

`order_busy_ms + voice_busy_ms`를 전체 시스템 대기로 더하지 않는다. 두 대기가 겹칠 수 있다. 마지막 입력 이후 보정값은 현재 2초 구간보다 클 수 있고, 원래 경과와 dwell_ms도 구간 길이로 잘라서는 안 된다. 수동 화면 읽기 시간은 현재 보정값에서 제외되지 않는다.

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
| interaction 전체 | 검증 후 창 근거에 손실 없이 보존 | 수신 성공만으로 규칙/Jev에 사용됐다고 설명 |
| options_open | 합의 후 동일 boolean을 판단 입력으로 전달 | options_open_count를 열림 상태로 사용 |
| 보정 경과 | 먼저 근거로 보존, pause_s 연결 보류 | 보정값 없이 원래 경과나 dwell_ms를 pause_s로 사용 |
| voice_busy/order_busy | 대기 맥락으로 제공 | true인 동안 무입력을 사용자 망설임으로 단정 |
| repeat_tap_count·거리 평균 | 각각의 관측 근거 | fixes_recent·의도한 버튼·손 떨림·장애로 대체 |
| cart_change_count | Cart 진행 관측 근거 | 개별 조작 성공·화면 전진·사용자 확인으로 대체 |
| 2초 miss/back 집계 | 구간 길이와 함께 전달 | 5초 판단 근거라고 재명명·단순 3창 합산 |

PR #77의 기존 5개 값 연결 자체도 2초/5초 의미 차이가 있으므로 D05가 미결인 동안 새로 임계값을 강화하거나 자동 지원을 켜지 않는다. 전체 확장 보존으로 이 차이가 해결됐다고 설명하지 않는다.

## 6. 시간·중복·화면·품질

- 시간 구간은 timezone이 있는 window_start/end, end > start를 유지한다. 파일럿 생산자의 2초 주기와 서버가 허용하는 모든 기존 요청 길이를 혼동하지 않는다. 서버에서 길이=2초를 일괄 강제하는 변경은 제안하지 않는다.
- 프론트는 요청 중 지나간 구간을 대기열에 쌓지 않는다. 재시도 대신 최신 구간을 보내므로 창 누락이 있을 수 있다. 누락을 0회 관측으로 채우지 않는다.
- sequence는 새 서버 세션 범위의 추적 값이다. 여러 탭·생산자·프로세스 사이 전역 유일성과 저장 키로의 사용은 미정이다.
- 늦은 응답·창, 동일 종료 시각, 중복 창의 정책은 서로 구분한다. PR #77의 늦은 창 기록 처리가 정확히 한 번 판단을 보장하는 것은 아니다.
- 화면·visit_id는 구간 끝 시점이고, 구간의 집계는 같은 세션의 여러 방문을 포함할 수 있다. 화면별 집계로 오해하지 않는다.
- menu/menu_list는 확정 매핑 없이 자동 치환하지 않는다. 현재 상태의 화면 진행값을 정확하다고 주장하지 않는다.
- 낮은 화면 상단 안내는 수집 루트 밖이다. 전체 키오스크 영역 관측이라고 설명하지 않는다. 화면 상태 변화 기록도 거래 감사 기록을 보장하지 않는다.
- 원시 좌표·포인터 이벤트·상품별 선택 내역·음성·인식 문장·영상은 이 확장에 넣지 않는다. 비전은 이번 합의 범위에 새 필드를 추가하지 않는다.

## 7. 오류·하위 호환·배포

제안하는 오류는 기존 422 검증 응답 형식을 따른다. 새 error_code나 오류 envelope를 임의 추가하지 않는다. 타입/범위 오류·필수 속성 누락·미지원 버전·알 수 없는 확장 속성은 해당 필드 위치를 확인할 수 있어야 한다. 기존 세션 없음/완료 404/410, 분석 실패 fallback 및 응답 support 정책은 유지한다.

기존 프론트는 interaction을 보내지 않아 계속 동작한다. #72의 이전 생산자는 27개 필수 값만 보내도 유효하며, 음성 추가 5개를 생략해도 된다. 그 5개를 서버에서 false/0으로 만들어 판단하지 않는다.

엄격한 새 속성 거절은 향후 프론트의 무버전 추가를 막고, 422를 받은 #72는 해당 세션 전송을 멈춘다. 이 트레이드오프는 D03으로 명시 승인받는다. 미지원 버전을 버리고 200을 주는 방향과 섞어 적용하지 않는다.

내부 analyze에도 전달하는 안을 채택한다면 계약 공유 정의, backend 수신, ai-engine 수신을 함께 맞춘다. 수신 코드가 여전히 값을 버리는 상태에서 전달 성공으로 발표하지 않는다. 내부 서비스 준비 후 검증된 backend를 배포하고, 마지막에 프론트 파일럿을 명시 활성화해 공동 확인한다. 자동 지원 활성화와 분리한다.

## 8. 구현 파일·검사·브랜치 순서

1. 이 합의안의 D01~D11에 담당자별 답과 수정값을 기록한다. 채택된 내용만 두 OpenAPI와 예시에 반영하는 계약 PR을 준비한다.
2. backend sessions 입력 검증과 전달 spy 검사, ai-engine 입력 모델 검사는 각 담당 영역에서 준비한다. 공용 기존 코드 수정은 별도 사용자 확인을 따른다.
3. #77 반영 후 backend decision 창 근거 보존과 선택한 입력 매핑을 연결한다. AI 담당자의 작업 브랜치에는 직접 커밋하지 않는다.
4. 이전 5개만 있는 요청, 확장 27개/32개 요청, null/생략/0, 잘못된 타입·버전·속성, 취소·완료·늦은 창·대기를 고정 응답으로 검증한다. API 수신→전달→판단 기록을 대조한다.
5. 실제 공동 검사는 샘플 세션으로 수행한다. API 200, ai-engine 보존, 판단 기록, 규칙 사용은 각각 관찰 근거를 남긴다. 실제 AI 호출·DB 저장은 별도 필요성에 따라 시행한다.

작성 시 feat/backend에는 #88이 열려 있다. 열린 PR과 미병합 커밋이 없는 공용 feat/docs에 최신 main을 fast-forward로 반영하고, 새 검토 문서 3개만 추가해 #88과 분리한다. #88은 사용자가 병합한다. 계약안 작성은 #72/#77 병합을 기다리지 않아도 되지만 해당 서비스 파일의 구현·통합은 병합 순서를 맞춘다.

## 9. 담당자에게 요청할 답변

- 프론트: 32개 이름/타입, 27+5 구분, order_busy의 non-null, visit_id 비어 있지 않음, 미지원/추가 속성 422 시 중단 정책이 생산자와 맞는가?
- AI: 원래 창을 backend 판단에 직접 전달하고 내부 analyze에도 같은 확장을 보존할 것인가? 관측 보존과 규칙/Jev 사용의 구분, 대기 경과·수동 읽기 한계에 동의하는가?
- 비전: 2초 터치와 5초 판단 구간·비전 창의 정합성을 어떤 별도 계약으로 정할 것인가? 현재 fixes_recent와 시선 부재를 추정하지 않는가?
- 백엔드: 런타임 strict 타입, null/생략 유지, fallback/410, 창 식별·유실 경계의 검사 범위에 동의하는가?

기록 양식: `D번호 / 채택·수정·보류 / 수정 내용 / 확인 담당자 / 확인일 / 결정 링크`. 부분 채택도 명시한다.

## 10. 근거

- [PR #72](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/72)
- [기준 TypeScript 필드](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/3d4b79c119aecf750148dc20e306be316b00f9d5/frontend/src/shared/api/interactionTypes.ts)
- [기준 집계 구현](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/3d4b79c119aecf750148dc20e306be316b00f9d5/frontend/src/features/order/interactionFeatures.ts)
- [기준 대기 시간 집계](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/3d4b79c119aecf750148dc20e306be316b00f9d5/frontend/src/features/order/interactionWait.ts)
- [프론트 필드·미합의 정책 문서](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/3d4b79c119aecf750148dc20e306be316b00f9d5/docs/Jev-Touch-Features.md)
- [PR #77 판단 입력](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/457a56b513ccbdf1617d46d6b7468822dbc99b45/backend/app/modules/decision/schemas.py)
- [현행 외부 계약](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/main/contract/frontend-backend.openapi.yaml), [현행 내부 계약](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/main/contract/backend-ai.openapi.yaml)

실제 기존 계약·프론트·백엔드·ai-engine·DB 파일은 이번 작성으로 변경하지 않았다.

## 11. 작성 후 확인 결과

- 디스크에 저장한 스키마·요청 예시 JSON을 다시 읽어 문법을 확인했다.
- 기준 TypeScript의 32개 속성 이름, 필수 27개/선택 5개, null 허용과 스키마가 일치한다. 중첩 설정은 6개다.
- 필드 목록·결측 허용 대조, 요청 예시, 타입·범위·미지원 버전·추가 속성·필수 누락에 대한 **79개 구조 검사**가 통과했다. 예시는 기존 요청, 27개 기본 확장, 32개 전체 확장, 음성 대기 중 확장 네 종류다.
- 이 검사는 사용한 JSON Schema 부분집합에 대한 로컬 구조 검사다. OpenAPI 전체 적합성 검사기나 실제 서버 통합 검증을 실행한 것은 아니다. 런타임 422 직렬화·타입 검증은 구현 후 확인한다.
- 로컬 합의안 작성 단계에서 git status --short는 빈 출력이고 git diff --check는 통과했다. 게시 준비 단계는 새 문서 3개의 추가만 포함한다. 실제 AI·DB 호출은 하지 않았다.
