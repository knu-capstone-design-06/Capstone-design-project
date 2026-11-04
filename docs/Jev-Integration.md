# Jev 연결 설계안

- 작성일: 2026-11-01
- 상태: 팀 검토용 제안(AI 담당). 5장의 1~4번(설정, 환경변수, 클라이언트, 응답 검증)은 이 PR에 구현했고, 호출 위치·기록·임계값(5~7번)은 비전의 `extension` 계약 뒤에 합의해 구현합니다. `contract/`는 바꾸지 않습니다.
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
| 3 | `JevClient.ask(request)`: 답(`answers`)이면 dict, 실패면 None. `Authorization: Bearer`로 `/v1/systemone` 호출, `asyncio.timeout`으로 전체 제한, 재시도 없음. 4xx·5xx·429·529·시간 초과·형식 오류는 모두 `None`. 로그에는 예외 종류와 상태 코드만 남기고 `state`·`answers`·키 원문은 남기지 않음 | `backend/app/infrastructure/external/jev_client.py` | `openai_client.py`와 같은 구조. 키가 없으면 클라이언트를 만들지 않고 호출 자체를 건너뜀 |
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

## 10. 멀티모달 상태 판단 제안 (2026-11-04, AI 담당)

지금 설계(4~6장)는 **규칙표가 먼저 지원을 고르고 Jev는 그 제안이 맞는지(`proposal_fits`) 또는 후보 중 무엇인지(`queue_support`)** 답합니다. 터치 로그와 비전 관측을 **함께 보고 손님의 상태를 판단**하는 일은 아직 아무도 하지 않습니다. 계약의 불편 상태 점수 5개(`StateScores`: `normal`, `touch_difficulty`, `navigation_difficulty`, `visual_difficulty`, `hesitation`)는 ai-engine의 자리표시자가 고정 예시 값을 내고, 비전 파이프라인은 "상태 점수 모델이 없다"고 적어 두었습니다(`contract_view.py`). 이 빈자리를 Jev로 채우자는 제안입니다.

### 10.1 자리

backend입니다. 터치 통계는 프론트 → backend로, 비전 창 결과는 ai-engine → backend로 오므로 둘이 만나는 곳이 backend뿐이고, 외부 AI는 backend만 부릅니다(AGENTS.md 4장). 비전의 `jev_request`가 이미 `state`에 상황·화면·터치·시선·세션을 한 덩어리로 넣고 있어, 입력 모양은 그대로 쓰고 **질문만 더합니다**.

### 10.2 질문: 상태 점수 5개

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

### 10.3 질문: 지원 선택

지금 비전이 만드는 `proposal_fits`(규칙표 제안이 맞는지) 또는 `queue_support`(후보 중 선택)를 같은 요청에 함께 넣습니다. 둘을 한 번에 물으면 요청 한 번, 입력 토큰 한 번입니다.

### 10.4 순서

| 단계 | 하는 것 | 화면 |
|---|---|---|
| 0 | 터치 통계만으로 상태 점수 5개를 묻고 기록(비전 없이도 가능). 자리표시자 점수와 나란히 저장 | 그대로 |
| 1 | 비전 `extension` 계약 뒤 `state.vision`을 채움. 진짜 멀티모달 | 그대로 |
| 2 | 촬영 데이터로 Jev 점수와 실제 상황을 맞춰 보고 임계값 결정 | 그대로 |
| 3 | `StateScores`를 Jev 답으로 바꾸고(`model_version`에 Jev 버전), 지원 결정도 `decided_by: jev` | 바뀜 |

0단계는 비전과 무관하게 지금 할 수 있습니다. `sessions/service.analyze`에서 ai-engine 응답을 받은 뒤 Jev를 부르고, 결과는 기록만 합니다. 이 호출 위치는 8장의 "호출 위치" 결정과 같이 정합니다.

### 10.5 지키는 것

- 임계값 비교, 횟수·시간 계산, 필수 적용 조건, 거절한 지원을 다시 열지 않는 규칙은 모두 코드입니다. Jev는 확률만 냅니다.
- Jev가 실패하면(시간 초과·오류) 그 창은 자리표시자 점수 또는 "측정 불가"로 돌아가고 자동 재시도는 없습니다.
- 상황 태그 이름, 지원 이름, 표시 문구는 비전·프론트 담당의 어휘를 그대로 쓰고 여기서 새로 만들지 않습니다.

## 9. 참고 링크

- TypeSafe System One API: https://docs.typesafe.ai/api/system-one.md
- 오류와 한도: https://docs.typesafe.ai/api/errors.md
- 모델과 버전 고정: https://docs.typesafe.ai/models.md
- confidence: https://docs.typesafe.ai/confidence.md
- OpenAPI: https://api.typesafe.ai/openapi.json
- 비전 판단 층: `ai-engine/app/modules/vision/judgment/rule_table_v0.py`, `jev_stub.py`, `contract_view.py`
- 계약: `contract/frontend-backend.openapi.yaml`의 `SupportDecision`, `contract/backend-ai.openapi.yaml`
- 세션·이벤트·음성 실행 합의안: `docs/Session-Event-Voice-Policy-Proposal.md`
