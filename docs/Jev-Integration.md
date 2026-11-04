# Jev 연결 설계안

- 작성일: 2026-11-01
- 상태: 5장의 1~4번(설정, 환경변수, 클라이언트, 응답 검증)은 #74로 병합됐고, 판단 층 뼈대와 그림자 호출(10장)은 그 다음 PR입니다. 판단 층은 backend에 둡니다(2026-11-04 결정). 임계값은 출처 있는 기준을 찾아 두고 촬영본으로 결과를 확인한 뒤 적용합니다.
- 읽는 순서: **10장이 1·2·5·8장의 호출 위치·시점 설계(ai-engine이 질문을 만들고 backend가 보냄, 창 안/다음 창 미정)를 대체합니다.** 앞 장들은 경위 기록으로 남깁니다. 비전 단서가 backend로 오는 길은 비전 담당이 시연 PC 확인 뒤 정합니다(#78). `contract/`는 바꾸지 않습니다.
- 대상: Back-end·Vision·Front-end·AI 담당자
- 목적: 비전 판단 층이 만들어 두는 Jev 질문(`jev_request`)을 backend가 실제로 TypeSafe Jev API에 보내고, 답을 기록하고, 합의된 임계값이 생기면 지원 결정에 반영하기까지 누가 무엇을 구현하는지 정리합니다.

## 1. 목표와 원칙

- **Jev는 backend만 부릅니다.** ai-engine은 질문을 만들기만 하고 보내지 않습니다(AGENTS.md 4장, `jev_stub.py`). 현재 ai-engine은 그림자 모드라 화면은 규칙표 결과를 따르고, Jev 답은 기록만 합니다. 연결 뒤에도 첫 단계는 그대로입니다.
- **Jev가 실패해도 결정은 멈추지 않습니다.** 시간 초과·오류·한도 초과는 모두 "답 없음"이고, 그때는 규칙표 결과를 그대로 씁니다. 자동 재시도는 하지 않습니다(ai-engine·OpenAI 클라이언트와 같은 원칙).
- **확률은 규칙표가 소비합니다.** Jev는 선택지별 확률과 confidence를 돌려줄 뿐이고, 임계값(`T_LOWER`·`T_AID`·`T_CHOICE`)과 비교해 기다림·묻기·바로 적용을 고르는 것은 코드입니다(README "Jev" 절: 횟수·비율·시간 계산과 필수 적용 조건은 코드).
- **state에는 코드가 만든 이름과 수치만 넣습니다.** 상황 태그 이름, 근거 종류별 개수, 화면 이름, 터치 횟수, 세션의 지원 이력입니다. 원본 영상·얼굴 좌표·음성·인식 문장·API 키는 넣지 않습니다(현재 `jev_request()`가 이미 이 범위로 만듭니다).
- **버전을 고정하고 기록합니다.** 요청 모델은 버전 ID로 고정하고, 응답의 `model`·`usage`·confidence를 실험 기록에 남깁니다(`docs/Convention.md` 7장).

## 2. 전체 흐름

지금(그림자 모드, Jev 미호출):

```text
[프론트] 특징 창 ─ POST /sessions/{id}/features ─▶ [backend sessions.service.analyze]
                                                        │ POST /v1/analyze
                                                        ▼
                                                   [ai-engine]  관측 → 상황 태그 → 규칙표 decide()
                                                        │           └ jev_request (만들기만, ShadowJev가 기록)
                                                        ▼
[프론트] ◀── FeatureWindowResponse { states, support: {preset, requires_confirmation, decided_by: rule_placeholder} }
```

제안(연결 뒤):

```text
[ai-engine] AnalyzeResponse에 결정과 jev_request를 실어 보냄 (비전 README의 extension 제안, 별도 계약 PR)
     │
     ▼
[backend] decision.jev_request가 있으면 ─▶ JevClient.ask() ─▶ TypeSafe POST /v1/systemone
     │                                        └ 답 없음(시간 초과·오류) → 규칙 결과 유지
     ▼
[backend] 답을 기록(모델 버전·확률·confidence·usage·지연) → 임계값이 있으면 policy에 따라 결정 수정, decided_by: jev
     │
     ▼
[프론트] support 반영 (형식은 지금 SupportDecision 그대로)
```

전제 하나: 지금 `/v1/analyze` 응답(`AnalyzeResponse`)에는 `states`와 `model_version`만 있고 규칙표 결정·`jev_request`는 실려 오지 않습니다(`contract_view.py`: "No AnalyzeResponse is emitted"). 비전 README가 제안한 `extension` 칸이 계약에 더해져야 backend가 질문을 받습니다. 그 계약 PR은 비전 담당이 따로 올립니다(PR #68 본문).

## 3. TypeSafe API 요약

출처: https://docs.typesafe.ai/api/system-one.md, https://docs.typesafe.ai/api/errors.md, https://docs.typesafe.ai/models.md (2026-11-01 확인).

| 항목 | 내용 |
|---|---|
| 호출 | `POST https://api.typesafe.ai/v1/systemone`, `Content-Type: application/json` |
| 인증 | `Authorization: Bearer <API 키>`. 모델 목록은 `GET /v1/models` |
| 요청 | `model`(필수), `state`(필수: 문자열·객체·배열), `questions`(필수: 이름 → 질문, 1개 이상) |
| 질문 유형 | `noul`(예/아니오 확률, `criteria`는 `true`/`false` 설명 선택), `choice`(`criteria` 필수, 선택지 1~255개 이름 → 설명), `score`(`criteria` 필수, 단계 1~10개). `instructions`는 문자열·객체·배열 가능 |
| 응답 | `model`(실제 답한 버전 ID), `answers`(질문 이름별: `type`, `noul` 또는 `choice`+`confidence`+`probabilities` 또는 `score`+`confidence`+`probabilities`+`legend`), `usage{input_tokens, output_tokens}` |
| 오류 | 400 규칙 위반·컨텍스트 초과, 401 키 없음·잘못됨, 413 본문 32 MiB 초과, 415 압축 오류, 422 검증 실패, 429 요청 한도, 529 일시 과부하 |
| 한도 | 본문 32 MiB, 요청당 64k·질문당 32k 토큰, `state`·`instructions`·`criteria` 중첩 64단계, 숫자는 유한값만. 429는 지수 백오프 권고 |
| 모델 | `jev-1.13.0`, `jev-1.14.0`(2026-10-14 공개). 별칭 `jev-latest`·`jev-preview`는 새 릴리스에 따라 움직이므로 실험에는 버전 ID를 보냄. 입력 10억 토큰당 $42, 출력 무료 |
| 환경변수 | 업체 권장 이름은 `TYPESAFE_API_KEY`. 이 저장소는 문서·코드가 모두 "Jev"로 부르므로 `JEV_*`를 씁니다(5장) |

## 4. 비전 `jev_request`와의 대응

`ai-engine/app/modules/vision/judgment/rule_table_v0.py`의 `jev_request()`는 이미 API 요청 형식과 같은 `{model, state, questions}`를 만듭니다. 그대로 보내도 되는지 항목별로 보면 다음과 같습니다.

| 항목 | 지금 비전이 만드는 값 | API 요구 | 판단 |
|---|---|---|---|
| `model` | `JEV_MODEL = "jev-1.13.0"` (`jev_stub.py` 상수) | 모델 이름 또는 별칭 | 맞음. 다만 버전을 backend 설정(`JEV_MODEL`)으로 옮겨 요청 직전에 덮어쓸지 결정 필요(8장) |
| `state` | 객체: `situation{tag, evidence(종류별 개수), dropped_cues}`, `screen{name, steps_left}`, `touch{misses_recent, fixes_recent, backs_recent, pause_s}`, `vision{facing_screen, looking_around}`, `session{active, held, refused, withdrawn}` | 문자열·객체·배열 | 맞음. 이름·수치뿐이라 개인정보 없음. `None` 값(`null`)은 JSON으로 그대로 감 |
| `questions` (`fit`) | `proposal_fits`: `type: noul`, `instructions`는 객체(`proposed_support{name, what}`, `question`), `criteria{true, false}` | `noul`, `instructions`는 객체 허용, `criteria` 선택 | 맞음 |
| `questions` (`choice`) | `queue_support`: `type: choice`, `instructions` 문자열, `criteria{선택지: 설명}` (규칙표 행의 `options`, 예: `remaining_steps_notice`·`defer_big_button_question`) | `choice`, `criteria` 필수 1~255개 | 맞음 |
| 언어 | 질문·설명 영어, 값은 코드 이름 | 제한 없음 | 테스트(`test_vision_chain.py`)가 한글 없음을 확인함 |

답의 소비처는 `Decision.policy`입니다. `kind`(`fit`/`choice`), `lowered_action`, `default_choice`, `choice_actions`, `jev_deadline: next_segment`, 그리고 지금은 모두 `None`인 `T_LOWER`·`T_AID`·`T_CHOICE`. 임계값이 `None`이면 "기준 없음"이라 답을 받아도 결정을 바꾸지 않습니다(그림자 모드). `fit`의 답은 `answers.proposal_fits.noul`(0~1), `choice`의 답은 `answers.queue_support.choice`와 `probabilities`입니다.

## 5. backend 구현 항목

| # | 항목 | 위치 | 비고 |
|---|---|---|---|
| 1 | 설정 4개: `jev_api_key`(SecretStr, 없으면 None), `jev_api_url`(기본 `https://api.typesafe.ai`), `jev_model`(기본 `jev-1.13.0`), `jev_timeout_seconds`(제안 3) | `backend/app/common/config/settings.py` | 공용 영역에 **추가**. OpenAI 항목과 같은 꼴 |
| 2 | `.env.example`에 `JEV_API_KEY=`, `JEV_API_URL=`, `JEV_MODEL=`, `JEV_TIMEOUT_SECONDS=`(값 없음), `docker-compose.yml` backend 환경에 같은 4개 | `backend/.env.example`, 루트 `docker-compose.yml` | 공용 영역에 **추가** |
| 3 | `JevClient.ask(request)`: 답이면 검증된 `JevResponse`(`model`, `answers`, `usage`), 실패면 None. `Authorization: Bearer`로 `/v1/systemone` 호출, `asyncio.timeout`으로 전체 제한, 재시도 없음. 4xx·5xx·429·529·시간 초과·형식 오류는 모두 `None`. 로그에는 예외 종류와 상태 코드만 남기고 `state`·`answers`·키 원문은 남기지 않음 | `backend/app/infrastructure/external/jev_client.py` | `openai_client.py`와 같은 구조. 키가 없으면 클라이언트를 만들지 않고 호출 자체를 건너뜀 |
| 4 | 응답 검증 스키마: `model`, `answers`(이름별 `type`과 유형별 필드), `usage`. 어긋나면 `None` | `backend/app/infrastructure/external/jev_schemas.py` | 질문 이름은 비전이 정함(`proposal_fits`, `queue_support`) |
| 5 | 호출 위치: `sessions/service.analyze`가 ai-engine 결과에 `jev_request`가 있으면 `JevClient.ask()`를 부르고 답을 기록. 임계값이 없으면 결정은 그대로, `decided_by`는 `rule_placeholder` 유지 | `backend/app/modules/sessions/service.py` 또는 새 모듈 `decision/` | 모듈 자리는 8장 결정 항목. 전제: 2장의 `extension` 계약 |
| 6 | 기록: 세션 ID, 창 시각, 질문 종류, 요청 모델, 응답 `model`, 답(확률·confidence), `usage`, 지연(ms), 결과(답 있음·없음·오류 종류) | 저장 위치는 8장 결정 항목 | DB 전에는 메모리 또는 파일. 보관 기간은 세션 정책(#62)을 따름 |
| 7 | 임계값 적용(2단계 이후): `policy`의 `T_*`와 답을 비교해 `lowered_action`·`choice_actions`대로 결정을 바꾸고 `decided_by: jev`로 응답 | 5번과 같은 자리 | 계약의 `decided_by` enum에 `jev`가 이미 있어 계약 변경 없음 |

프론트는 바뀌지 않습니다. `SupportDecision` 형식이 그대로이고, `decided_by` 값만 달라집니다.

## 6. 단계별 도입

| 단계 | 하는 것 | 화면 | 필요한 것 |
|---|---|---|---|
| 0. 그림자 | Jev를 부르고 답을 기록만 함 | 규칙표 결과 그대로, `decided_by: rule_placeholder` | 5장 1~6번, 2장의 `extension` 계약, 키 |
| 1. 비교 실험 | 같은 창 입력에서 규칙표 결정과 Jev 답을 나란히 기록해 임계값 후보를 봄 | 그대로 | 0단계 기록, 파일럿 촬영 데이터, 기록 분석 스크립트 |
| 2. 적용 | 합의된 `T_LOWER`·`T_AID`·`T_CHOICE`로 결정을 바꿈 | `decided_by: jev`인 창이 생김 | 5장 7번, 임계값 합의, 프론트의 확인 UI(`requires_confirmation`)가 이미 동작하는지 확인 |

0단계를 먼저 병합해 두면 촬영 기간 동안 Jev 답이 쌓이고, 임계값은 그 기록으로 정합니다. 2단계 전까지는 Jev가 화면을 바꾸는 일이 없습니다.

## 7. 기록과 실험

- 응답의 `model` 값을 매번 기록합니다. 별칭을 쓰지 않아도 어떤 버전이 답했는지 남습니다.
- `usage.input_tokens`를 합산해 비용을 봅니다. 질문 하나의 `state`는 수십 줄의 이름·수치라 크지 않지만, 창마다 부르면 횟수가 쌓입니다.
- 지연을 창마다 재서 p50·p95를 남깁니다. 지금 ai-engine 호출 제한이 2초이므로, Jev 호출을 같은 요청 안에서 기다릴지(응답이 느려짐) 다음 창에 반영할지(`jev_deadline: next_segment`가 이미 그 뜻) 결정이 필요합니다.
- confidence 분포를 질문 종류별로 봅니다. TypeSafe는 버전이 바뀌면 임계값을 다시 맞추라고 합니다(https://docs.typesafe.ai/models.md).
- `docs/Convention.md` 7장대로 실험마다 규칙표 버전(`rule_table_v0`), Jev 모델 버전, 질문 문구 버전(`WHAT`·`FIT_CRITERIA`·`CHOICE_CRITERIA`가 바뀌면 기록)을 함께 적습니다.

### 7.1 실험 조건(arm)과 설정

논문의 비교는 "같은 입력에서 규칙표만 쓴 판단과 Jev를 더한 판단의 정답률"이고, Jev 쪽은 단계 수를 늘리며 최적 단계 수를 봅니다. 조건은 backend 설정 `JEV_STAGES` 하나로 바꾸고, 바꾼 뒤 재시작합니다.

| 조건 | `JEV_STAGES` | 판단 | 기록 |
|---|---|---|---|
| A. 규칙표만 | `off` | 규칙표 v0(if/else) | 창마다 결정(`Decision`)과 세션 상태 |
| B. Jev 1단계 | `state_scores` | 규칙표 + 상태 점수 5개 | A의 기록 + 단계 `state_scores` 답 |
| C. Jev 2단계 | `state_scores,support_choice` | B + 허용 후보 중 지원 선택 | B의 기록 + 단계 `support_choice` 답 |
| D. 예측 단계 | `state_scores,next_difficulty` | B + 최근 창들의 흐름으로 다음 어려움 예측(9.6) | B의 기록 + 단계 `next_difficulty` 답 |
| E. n단계 | 단계 이름을 더 나열 | 새 단계 클래스를 `STAGE_REGISTRY`에 등록 | 단계마다 한 줄 |

- 창마다 창 기록(`WindowRecord`: 입력 한 줄, 규칙표 결정, 설정된 단계, Jev를 물었는지와 그 이유, 단계별 결과)을 세션 전체 동안 남깁니다. 규칙표는 어느 조건에서든 돌므로 **조건 A의 결정은 모든 기록에 있고**, 뒤 단계는 앞 단계의 답만 추가로 보므로 한 설정의 기록에 그 설정의 앞 단계 결과(B)도 함께 있습니다. C와 D는 2단계의 입력이 서로 달라 **따로 돌립니다.** 호출이 겹쳐 건너뛴 창(`skipped_in_flight`)과 앞 단계 답이 없던 단계(`previous_missing`)도 기록에 남아 조건별 분모를 맞춥니다.
- 정답률은 기록된 창마다 "실제 상황·필요했던 지원"(촬영본 라벨)과 (A) 규칙표 결정, (B) 상태 점수에 임계값을 건 결정, (C) 선택 답을 맞춰 셉니다. 임계값은 출처(표준·관행·문헌)가 있는 기준을 찾아 두고 촬영본으로는 결과를 확인합니다. 파일럿 촬영분과 최종 평가분은 분리합니다(AGENTS.md 5장).
- 그림자 모드에서는 어느 조건이든 화면이 바뀌지 않으므로 손님 경험은 같고, 조건은 기록에만 차이를 냅니다. 적용 단계(6장의 2)에서는 조건이 화면을 바꾸므로 참가자별로 조건을 고정합니다.

## 8. 결정이 필요한 항목

- [ ] **호출 위치**: `sessions/service`에 넣을지, 판단 층 전용 모듈 `backend/app/modules/decision/`을 새로 둘지(비전 결정·Jev 답·반응 이력이 한곳에 모임). AI 담당은 새 모듈을 권합니다.
- [ ] **호출 시점**: 특징 창 요청 안에서 Jev 답까지 기다릴지, 답을 다음 창에 반영할지(`jev_deadline: next_segment`). 기다리면 프론트 응답이 Jev 지연만큼 늦어집니다.
- [ ] **`extension` 계약**: 비전의 결정·`jev_request`를 `AnalyzeResponse`에 싣는 계약 PR(비전 담당). 이 설계는 그 PR 뒤에 구현합니다.
- [x] **모델 고정 버전**: 구현에서는 backend 설정 `JEV_MODEL`(기본 `jev-1.13.0`)이 요청의 `model`을 덮어씁니다. 비전 상수는 질문을 만들 때의 기본값으로만 남습니다. `jev-1.14.0`으로 바꿀지는 0단계 기록을 보고 정합니다.
- [ ] **타임아웃**: 제안 3초. ai-engine 2초, OpenAI 10초와의 관계.
- [ ] **429 처리**: SDK를 쓰지 않고 httpx로 직접 부르므로 백오프는 우리가 정합니다. 제안은 재시도 없이 그 창은 "답 없음"으로 두기.
- [ ] **비용 상한**: 하루·세션당 호출 수 상한을 둘지. 둔다면 상한을 넘긴 창은 "답 없음".
- [ ] **기록 저장 위치**: DB 전에는 backend 메모리(세션 정책의 보관 기간) 또는 로컬 파일. 개인정보는 없지만 세션 ID가 들어갑니다.
- [ ] **임계값 초기값**: `T_LOWER`·`T_AID`·`T_CHOICE`. 0단계 기록으로 정합니다. 지금은 "기준 없음".
- [ ] **실험 동의 안내**: 상황 태그와 터치 통계가 외부 API로 간다는 점을 안내 문구에 넣을지(원본 영상·음성은 가지 않음).
- [ ] **공용 영역 변경 합의**: `settings.py`·`.env.example`·`docker-compose.yml`은 항목 **추가**라 PR 리뷰로 충분합니다. `contract/`는 이 설계에서 바꾸지 않습니다(`decided_by: jev`가 이미 enum에 있음).

## 9. 멀티모달 상태 판단 제안 (2026-11-04, AI 담당)

지금 설계(4~6장)는 **규칙표가 먼저 지원을 고르고 Jev는 그 제안이 맞는지(`proposal_fits`) 또는 후보 중 무엇인지(`queue_support`)** 답합니다. 터치 로그와 비전 관측을 **함께 보고 손님의 상태를 판단**하는 일은 아직 아무도 하지 않습니다. 계약의 불편 상태 점수 5개(`StateScores`: `normal`, `touch_difficulty`, `navigation_difficulty`, `visual_difficulty`, `hesitation`)는 ai-engine의 자리표시자가 고정 예시 값을 내고, 비전 파이프라인은 "상태 점수 모델이 없다"고 적어 두었습니다(`contract_view.py`). 이 빈자리를 Jev로 채우자는 제안입니다.

### 9.1 자리

backend입니다. 터치 통계는 프론트 → backend로, 비전 창 결과는 ai-engine → backend로 오므로 둘이 만나는 곳이 backend뿐이고, 외부 AI는 backend만 부릅니다(AGENTS.md 4장). 비전의 `jev_request`가 이미 `state`에 상황·화면·터치·시선·세션을 한 덩어리로 넣고 있어, 입력 모양은 그대로 쓰고 **질문만 더합니다**.

### 9.2 질문: 상태 점수 5개

`noul`(예/아니오 확률) 질문 5개를 한 요청에 넣습니다. 답 `noul`(0~1)을 그대로 `StateScores`의 각 값으로 씁니다. 계약·프론트는 바뀌지 않고, `model_version`에 응답의 `model`(예: `jev-1.13.0`)을 적습니다.

```json
{"model": "jev-1.13.0",
 "state": {
   "screen": {"name": "menu", "steps_left": 2, "since_last_input_ms": 4500, "order_busy": false},
   "touch": {"tap_count": 4, "miss_tap_count": 3, "repeat_tap_count": 2, "back_count": 1, "dwell_ms": 12000,
             "outside_tap_ratio": 0.75, "outside_nearest_distance_mean_px": 9.5,
             "screen_revisit_count": 1, "scroll_event_count": 0, "category_change_count": 0},
   "voice": {"enabled": false, "processing": false, "auto_off": null},
   "ui_settings": {"large_text": false, "large_button": false, "simple_screen": false, "step_guide": false},
   "vision": {"situation": "looking_around", "evidence": {"yaw_sweep_offscreen": 2, "dwell_no_touch": 1},
              "confidence": {"events": 3, "quality_ok": true}, "facing_screen": false,
              "people_behind_max": 0, "companion_frames": 0},
   "session": {"active": [], "refused": [], "withdrawn": []}},
 "questions": {
   "touch_difficulty": {"type": "noul", "instructions": "Is the user having trouble physically hitting the buttons in this window?",
                        "criteria": {"true": "Taps land outside targets near their edges, repeated taps on the same spot, the user keeps facing the screen.", "false": "Taps land on targets, or there are no taps because the user is reading or talking."}},
   "navigation_difficulty": {"type": "noul", "instructions": "Is the user lost in the order flow?",
                        "criteria": {"true": "Going back, revisiting screens, long pauses with no selection while facing the screen.", "false": "Steady progress through the screens, or a pause explained by the system being busy."}},
   "visual_difficulty": {"type": "noul", "instructions": "Does the user seem unable to read or see the screen well?", "criteria": {"true": "Leaning in, large text or high contrast already on, taps far from any target.", "false": "Normal distance and accurate taps."}},
   "hesitation": {"type": "noul", "instructions": "Is the user hesitating rather than acting?",
                        "criteria": {"true": "No input for a long time while facing the screen, options opened and closed without choosing.", "false": "The user is talking to a companion, looking behind, or the kiosk is processing."}},
   "normal": {"type": "noul", "instructions": "Is the user ordering without any sign of trouble?", "criteria": {"true": "Accurate taps, steady progress, no long pauses.", "false": "Any of the difficulties above."}}}}
```

- `touch`는 기존 5개와 #72의 `touch.interaction` 필드(대상 밖 비율, 가장 가까운 대상까지 거리, 재방문, 마지막 입력 뒤 시간, 음성 처리 중, 자동 꺼짐)를 씁니다. `vision`은 비전 창 결과의 `situation`과 `vision` 요약입니다(README '창 한 줄'). 값은 전부 이름과 숫자이고 원본 영상·음성·인식 문장은 없습니다.
- 질문과 기준은 영어이고 `state` 값은 코드 이름입니다(비전 테스트가 한글 없음을 확인하는 것과 같은 이유). 기준 문구는 초안이며 촬영 데이터로 고칩니다.
- `hesitation`과 `touch_difficulty`의 `false` 기준에 "일행과 대화 중", "뒤를 봄", "시스템 처리 중"을 둔 것이 멀티모달의 핵심입니다. 터치만 보면 모두 "멈춤"이지만 비전·음성 상태가 그 멈춤의 이유를 가릅니다.

### 9.3 질문: 지원 선택

지금 비전이 만드는 `proposal_fits`(규칙표 제안이 맞는지) 또는 `queue_support`(후보 중 선택)를 같은 요청에 함께 넣습니다. 둘을 한 번에 물으면 요청 한 번, 입력 토큰 한 번입니다.

### 9.4 순서

| 단계 | 하는 것 | 화면 |
|---|---|---|
| 0 | 터치 통계만으로 상태 점수 5개를 묻고 기록(비전 없이도 가능). 자리표시자 점수와 나란히 저장 | 그대로 |
| 1 | 비전 `extension` 계약 뒤 `state.vision`을 채움. 진짜 멀티모달 | 그대로 |
| 2 | 촬영 데이터로 Jev 점수와 실제 상황을 맞춰 보고 임계값 결정 | 그대로 |
| 3 | `StateScores`를 Jev 답으로 바꾸고(`model_version`에 Jev 버전), 지원 결정도 `decided_by: jev` | 바뀜 |

0단계는 비전과 무관하게 지금 할 수 있습니다. `sessions/service.analyze`에서 ai-engine 응답을 받은 뒤 Jev를 부르고, 결과는 기록만 합니다. 이 호출 위치는 8장의 "호출 위치" 결정과 같이 정합니다.

### 9.5 두 단계 안: 상태 판단 뒤 지원 선택도 Jev에게

한 요청의 질문들은 같은 `state`를 보고 서로 독립으로 답하므로, "상태 점수를 보고 지원을 고르는" 연쇄는 요청 하나로는 안 됩니다. 두 번 부릅니다. 구현은 같은 창의 백그라운드 작업에서 ① 바로 뒤에 ②를 부르고, 둘 다 응답을 막지 않으며 답은 기록에만 남습니다(화면 반영은 다음 창 이후, `next_segment`).

```
창 N (백그라운드) : state(터치·비전·화면·세션) ──► Jev ① ──► 상태 점수 5개 (9.2)
          이어서 : state + jev.state_scores(①의 답) ──► Jev ② choice ──► 허용 후보 중 지원 하나 + 확률
```

- ②의 선택지는 규칙표가 거른 **허용 후보**(켠 것·거절한 것·같은 범위에서 거둔 것 제외)만 넣습니다. 거름·전이(유지·거두기·무응답)·임계값 비교는 계속 코드가 합니다. 지금 규칙표의 `queue_support`(choice)가 ②의 형태이고, 선택지를 "그 창의 허용 후보 전체"로 넓히는 것이 변경점입니다.
- ②의 `state`에는 ①의 점수만 넣지 않고 **원래 단서도 함께** 넣어, ①이 틀렸을 때 ②가 원본을 다시 볼 수 있게 합니다.
- 비용은 두 배여도 호출당 0.00004달러 수준입니다. 지연은 창 하나 뒤로 미루면 응답을 막지 않습니다.
- 평가 때 같은 기록으로 "규칙표만 / ①만 / ①+②" 세 가지를 비교할 수 있어 README의 "규칙 기반과 Jev 기반 선택 비교"와 맞습니다.

호출은 **세션당 한 번에 하나**만 띄웁니다. 앞 창의 답이 오기 전에 들어온 창은 묻지 않고, 그 다음 창이 다시 묻습니다(`DecisionService.observe`).

### 9.6 예측 단계: 상태의 흐름에서 다음 어려움을 미리 보기

상태를 창마다 따로 보는 데서 한 단계 올려, **최근 창들의 흐름**(태그·결정·터치 수·상태 점수의 시간순 배열)을 `state.history`로 주고 "이 흐름이 이어지면 다음 10초 안에 어떤 어려움을 겪을까"를 묻습니다(`next_difficulty`, 선택: 터치·탐색·시각·망설임·없음). 규칙표는 일이 벌어진 뒤(되돌아감 1회) 열리지만, 이 답은 그 전에 신호를 주어 조용한 선제 지원(강조·안내)의 근거가 될 수 있습니다.

- 세션의 첫 창은 흐름이 없어 건너뜁니다. 보관하는 창은 최근 5개(약 10초)입니다. 길면 토큰이 늘고 오래된 상태가 섞입니다.
- 정답률은 7.1과 같은 잣대로 셉니다. 창 N의 예측을 창 N+1..N+5의 촬영본 라벨(실제 상황·필요했던 지원)과 맞춥니다. 뒤 창의 태그·점수도 모델 출력이라 잣대로 쓰지 않습니다.
- 예측이 틀렸을 때 선제 지원이 방해가 되면 안 되므로, 적용은 조용한 지원까지로 두고 묻기·큰 변화는 실제 단서가 있을 때만 합니다.
- 조건표(7.1)의 D에 해당합니다: `JEV_STAGES=state_scores,next_difficulty` 또는 세 단계 모두.

### 9.7 지키는 것

- 임계값 비교, 횟수·시간 계산, 필수 적용 조건, 거절한 지원을 다시 열지 않는 규칙은 모두 코드입니다. Jev는 확률만 냅니다.
- Jev가 실패하면(시간 초과·오류) 그 창은 자리표시자 점수 또는 "측정 불가"로 돌아가고 자동 재시도는 없습니다.
- 상황 태그 이름, 지원 이름, 표시 문구는 비전·프론트 담당의 어휘를 그대로 쓰고 여기서 새로 만들지 않습니다.

## 10. 판단 층 backend 구현 현황 (2026-11-04)

판단 층은 backend에 둡니다(결정 2026-11-04; 이유는 9장과 #74 댓글: 실행 시점에 클라우드는 backend만 남고, 세션 상태·음성·터치 통계·Jev 답이 모두 backend에 있음). `backend/app/modules/decision/`:

| 파일 | 하는 일 |
|---|---|
| `schemas.py` | 창 입력 한 줄(`WindowInput`), 규칙표의 결정(`Decision`), 세션 상태(`SessionState`: 유지·켬·거절·거둔 목록), 기준값(`DecisionParams`; 값마다 비전 `params.py`의 출처를 따름: 정의 1개, 평가 스위치 2개, 나머지는 `[파일럿]`), 창 기록(`WindowRecord`), Jev 기록(`JevRecord`). 그림자 단계의 설정(최근 창 5개, 예측 10초, 화면 순서)은 "기준 없음"으로 표시 |
| `rule_table.py` | 비전 `judgment/rule_table_v0.py`를 행 그대로 옮긴 규칙표 v0: 장면 3-1·3-2·4-1·4-2, 순서, 전이(open·replace·keep·withdraw), 거두는 조건, 무응답 거두기(`tick`: 서비스가 창마다 판단 앞에서 부름), 반응(`react`: 프론트의 반응 전달이 아직 없어 함수만 있음). 규칙표의 Jev 질문(`proposal_fits`·`queue_support`)과 `state`(비전과 같은 칸 이름)도 여기서 만듭니다 |
| `jev_questions.py` | 9장의 상태 점수 질문 5개(`noul`, 계약 `StateScores`와 이름이 같음)와 그림자 호출의 `state`(규칙표 state + 계약의 터치 5개). Jev 호출은 **단계(`JevStage`) 목록**으로 쌓습니다. 단계마다 `build(ctx)`가 자기 `state`와 질문을 만들고, `ctx.previous`로 앞 단계들의 답을 받아 `state.jev`에 넣습니다(9.5의 ①→② 연쇄). 기본은 `ScoreStage` 하나이고, 단계를 더하는 데 서비스 코드는 바뀌지 않습니다 |
| `repository.py` | 세션별 상태, 창 기록(세션 전체), Jev 기록을 메모리에 보관. 1시간 지난 세션은 정리(음성 맥락과 같은 기간) |
| `service.py` | `/features` 창마다 규칙표를 돌려 상태를 갱신하고(`judge`), 키가 있으면 **백그라운드에서** 단계들을 차례로 Jev에 묻고 기록만 남김(`observe` → `ask_shadow`). 응답은 Jev를 기다리지 않고(`jev_deadline: next_segment`), 세션당 진행 중 호출은 하나만 둡니다(답이 오기 전에 들어온 창은 `skipped_in_flight`로 기록). 창마다 `WindowRecord`를 남기고(`off` 조건 포함) 단계 결과가 오는 대로 붙입니다 |

연결: `sessions/service.analyze`가 ai-engine 답을 받은 뒤 `DecisionService.observe()`를 부릅니다. 어느 단계를 돌릴지는 `JEV_STAGES`(7.1의 조건)로 정하고, `off`면 키가 있어도 Jev를 부르지 않습니다. `support_choice` 단계는 규칙표가 그 창에 열 수 있는 후보(`allowed_supports`)와 `none` 중 하나를 고르게 하므로 규칙이 막은 지원은 선택지에 오르지 않습니다. 판단 층의 어떤 오류도 응답을 바꾸지 않습니다. `main.py`는 키가 있을 때만 Jev 클라이언트를 만들고, 없어도 규칙표는 돕니다.

지금 창 입력에 채워지는 것과 비는 것:

| 채워짐 (계약의 터치 5개) | 비어 있음 (None) |
|---|---|
| 누름 수, 빗나간 누름 수, 되돌아감 수, 화면 ID, 화면 순서(menu → review → complete)에서 얻는 남은 단계 수와 화면 진행(되돌아감으로 열린 4-2는 장바구니 화면으로 넘어가면 거둠) | 상황 태그·시선(비전 단서 입구 뒤), 빗나감 뒤 바로 고침·마지막 누름 뒤 초·옵션 창(#72의 `interaction` 또는 계약 확장 뒤) |

그래서 지금 열릴 수 있는 행은 되돌아감에 의한 4-2(`highlight_next_action`)뿐이고, 그것도 그림자라 화면에는 나가지 않습니다. 비전 단서가 들어오면 3-1·3-2가, 빗나감 뒤 고침 수가 들어오면 4-1이 같은 코드로 열립니다. 비전 단서가 없는 창의 Jev state는 태그와 `looking_around`를 `null`로 두어 관측하지 않은 것을 주장하지 않습니다.

회의 항목(비전 리뷰, #77): (1) 터치 단서를 세는 구간. 비전 재생은 최근 `touch_span_s`(5초) 동안 세고 backend는 창 하나(2초)의 횟수를 그대로 씁니다. 어느 쪽을 정의로 삼을지 정하면 Jev state의 `touch`에서 같은 값의 두 이름(`misses_recent`/`miss_tap_count`)도 하나로 정리합니다. (2) 비전 `situation`의 키 모양(`name`·`evidence` vs 제안된 `tag`·`evidence_ids`)은 입구가 정해질 때 `WindowInput.situation`이 읽는 키와 함께 맞춥니다. (3) 3-1을 남은 화면 수를 알고 1 이상일 때만 열도록 고치는 비전 제안.

실제 키 확인(2026-11-04, 시연 PC 아님): 9장 예시 state로 상태 점수 5개를 물었을 때 응답 0.2~0.5초, 입력 약 900토큰. 비전 단서(`looking_around`)가 있을 때 `hesitation` 0.51, 없을 때 0.76으로, 같은 멈춤을 "찾는 중"으로 읽어 주었습니다.

다음: (1) 비전 단서 입구(`extension` 또는 프론트 요청) 확정 뒤 `situation`·`gaze` 채우기, (2) #72 병합 뒤 `interaction` 필드로 `pause_s`·`options_open`·`fixes_recent` 채우기, (3) 기록을 Supabase(#73) 테이블로, (4) 출처 있는 기준으로 임계값을 두고 촬영본으로 확인한 뒤 `StateScores`·`decided_by`를 Jev 답으로 바꾸기, (5) 프론트의 반응 전달이 생기면 `react` 연결.

## 11. 참고 링크

- TypeSafe System One API: https://docs.typesafe.ai/api/system-one.md
- 오류와 한도: https://docs.typesafe.ai/api/errors.md
- 모델과 버전 고정: https://docs.typesafe.ai/models.md
- confidence: https://docs.typesafe.ai/confidence.md
- OpenAPI: https://api.typesafe.ai/openapi.json
- 비전 판단 층: `ai-engine/app/modules/vision/judgment/rule_table_v0.py`, `jev_stub.py`, `contract_view.py`
- 계약: `contract/frontend-backend.openapi.yaml`의 `SupportDecision`, `contract/backend-ai.openapi.yaml`
- 세션·이벤트·음성 실행 합의안: `docs/Session-Event-Voice-Policy-Proposal.md`
