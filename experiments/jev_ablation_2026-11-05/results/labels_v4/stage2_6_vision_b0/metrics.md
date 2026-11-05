# E5 지표: `stage2_6_vision_b0`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `<workspace>/4_vision/eval_ab_2026-11-04/judgment_labels_v4.csv`(time)
- 라벨 상태: Claude(Opus 서브에이전트) 2026-11-05; v4 = 결정 227 레드팀 3회차 반영(치명 1 · 중요 2~5는 main 결정); v2 · v3 · v4 고침은 v1 결과를 본 검토 뒤에 했음

## 규칙표(조건 A)

- 창 556개(영상 35개, 테이크 35개, 세션 35개), 측정 가능 447개
- 기록의 상황 태그: {'unknown': 189, 'none': 367}
- 전이: {'none': 556}; 연 지원(open · replace): 없음
- 규칙표 자체 질문이 붙은 창: 0개 ; tick으로 거둔 묻기 0개
- 허용 후보 수별 창: {0: 556}
- 입력 기록의 결정(비전 기록 또는 E3 AB0)과 같음: {'True': 556}
- 계약 터치 5칸: {'absent (contract five not all known)': 556}; 최근 구간 터치 수의 출처: {'segment sum (a window without touch)': 556}
- fixture 기대값: 0개 확인, 어긋남 0개

## 실행(조건 · 변형 · 단계별)

| arm | 창 | 대상 창 | 시도한 창 | 건너뜀(이유) | 단계 | 단계 대상 | build 없음 | 시도 | 답 | 실패(종류) | API 호출 | 캐시 답 | 순서 바꾼 호출 | 지연 p50 · p95 · 최대 ms | 입력 토큰 합 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 556 | 447 | 0 | 조건 A(묻지 않음) | - | - | - | - | - | - | - | - | - | - | - |
| B | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| B:vision_summary | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- B: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:vision_summary: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms

## 같은 요청 점검(실행 동작)

- B:vision_summary vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 0개

## 같은 입력 반복(요청마다 1번)


## 답 요약

| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| B | state_scores | hesitation | 447 | 0.343 | 0.220 | 0.380 |
| B | state_scores | navigation_difficulty | 447 | 0.198 | 0.150 | 0.220 |
| B | state_scores | normal | 447 | 0.430 | 0.350 | 0.440 |
| B | state_scores | touch_difficulty | 447 | 0.144 | 0.100 | 0.160 |
| B | state_scores | visual_difficulty | 447 | 0.142 | 0.130 | 0.300 |
| B:vision_summary | state_scores | hesitation | 447 | 0.362 | 0.220 | 0.470 |
| B:vision_summary | state_scores | navigation_difficulty | 447 | 0.164 | 0.140 | 0.230 |
| B:vision_summary | state_scores | normal | 447 | 0.483 | 0.380 | 0.530 |
| B:vision_summary | state_scores | touch_difficulty | 447 | 0.157 | 0.100 | 0.220 |
| B:vision_summary | state_scores | visual_difficulty | 447 | 0.140 | 0.120 | 0.390 |

## 짝 비교(같은 창)

- B:vision_summary vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 12(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.020, 평균 |차| 0.023, 최대 |차| 0.100
  - navigation_difficulty: n 447, 평균 차 -0.034, 평균 |차| 0.035, 최대 |차| 0.050
  - normal: n 447, 평균 차 0.053, 평균 |차| 0.054, 최대 |차| 0.120
  - touch_difficulty: n 447, 평균 차 0.013, 평균 |차| 0.013, 최대 |차| 0.070
  - visual_difficulty: n 447, 평균 차 -0.002, 평균 |차| 0.019, 최대 |차| 0.160

## 라벨

- 라벨이 붙은 창 556개(안 붙은 창 0개), 수준 {'action': 556}, 맞춘 방법 {'inside': 556}
- 구간 분류별 창: {'no_user': 15, 'wait_only': 292, 'designated': 115, 'time_stop': 134}
- 세션 35개 가운데 라벨 행이 둘 이상인 세션 8개
- 상태 대응(STATE_PROXY)이 있는 창 190개: {'normal': 136, 'hesitation,navigation_difficulty': 15, 'visual_difficulty': 39}
- 창의 태그 | 정답 태그(window truth: the segment's truth tag when a GT behaviour second lies in (t - window_s, t], else none (E3 run_eval.py window_truth)): {'none | none': 519, 'none | looking_around': 10, 'none | consulting_companion': 18, 'none | looking_back_with_people_behind': 9}
- 보낸 질문의 선택지가 none 하나뿐인 창: 0개

### 기준이 선택지 밖인 창

- 허용 행동이 선택지(허용 후보 + none)에 없음: 전체 0(전체 556), 후보가 있는 창 0(전체 0)
- 지정 지원이 허용 후보에 없음: 171(전체 171)
- 지정 지원이 규칙표 v0 밖(행 없음): 58(전체 556) ['1-2 아래쪽 화면으로 시작(바로 적용)', '2-1 크게 보기 강조(바로 적용)']
- 점수 대상: 제외 · 모순 구간 밖의 라벨 창 556개(뺀 창 0개). 선택 · 상태 추정 · 규칙표 질문 · 예측 · 섞은 대조가 모두 이 창을 쓴다.

### 지원 선택(주 비교: A 대 C · C0 · E, 같은 창; 제외 구간을 뺀 창 556개)

- A: 허용 안 556(전체 556, 95% 1.000~1.000)(우연 1.000), 후보가 있는 창 0(전체 0)(우연 -); 지정 지원과 같음 0(전체 171, 95% 0.000~0.000)(우연 0.000); 고른 것 {'none': 556}
  - 구간 2×2: TP/FN/FP/TN = 0/4/0/22; 거짓 경보 0(전체 22, 95% 0.000~0.149), 놓친 도움 4(전체 4, 95% 0.510~1.000)(v0 행 있음 4(전체 4, 95% 0.510~1.000)), 제안 정밀도 0(전체 0); 2×2 밖 {'no_user': 8, 'time_stop': 7}
  - 지정 지원 자체를 시작 시각 이후 낸 구간(v0 행 있음): 0(전체 4, 95% 0.000~0.490); 규칙표 행이 없는 지정 구간(2×2 밖)에서 지정 지원 자체를 낸 구간: 0(전체 4, 95% 0.000~0.490)(보이는 허용 형태만 낸 구간 0(전체 4)은 도움으로 세지 않음)
  - 도움 규칙: 시작 시각 이후 허용 도움(admissible help after onset; 같은 turn에서 연 지원이 시작 시각 이후 보이면 도움, 시작 시각 전에 열어 그때까지 보이면 지연 0). 시작 시각 전에 연 도움 0구간(앞선 초 []), 지연 중앙값 -초(n 0); 출처별 {'camera': {'designated_v0_row': 4, 'TP': 0, 'FN': 4, 'designated_delivery': {'k': 0, 'n': 4}}}; 옛 규칙(시작 시각 이후 새 제안만) TP/FN 0/4, 지정 지원 {'k': 0, 'n': 4}
  - 허용 밖 결정의 분류(창 정답 태그 기준, 기술만, 인과 주장 아님): {'decision_errors': 0, 'of_windows': 556, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 0, 'observed_tag_unknown': 0, 'reference_missing': 0}

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)

- B: normal Brier 0.286(기준율 0.183, skill -0.565) · ECE 0.325 · AUROC 0.594(n 154, 양성 117); touch_difficulty Brier 0.020(기준율 0.000, skill -) · ECE 0.140 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.081(기준율 0.066, skill -0.223) · ECE 0.120 · AUROC 0.469(n 154, 양성 11); visual_difficulty Brier 0.139(기준율 0.140, skill 0.008) · ECE 0.033 · AUROC 0.595(n 154, 양성 26); hesitation Brier 0.139(기준율 0.066, skill -1.089) · ECE 0.265 · AUROC 0.391(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:vision_summary: normal Brier 0.256(기준율 0.183, skill -0.401) · ECE 0.277 · AUROC 0.596(n 154, 양성 117); touch_difficulty Brier 0.023(기준율 0.000, skill -) · ECE 0.150 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.071(기준율 0.066, skill -0.077) · ECE 0.081 · AUROC 0.682(n 154, 양성 11); visual_difficulty Brier 0.138(기준율 0.140, skill 0.019) · ECE 0.032 · AUROC 0.603(n 154, 양성 26); hesitation Brier 0.148(기준율 0.066, skill -1.236) · ECE 0.289 · AUROC 0.637(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)

### 규칙표 자체 질문(proposal_fits, 보조)

- B: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:vision_summary: Brier - · ECE - · AUROC -(n 0, 양성 0)

### 다음 어려움 예측(D · E, 따로 셈)


### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 556, 섞은 평균 556.000, 범위 556~556
- 라벨을 섞음 · B normal Brier: 실제 0.286, 섞은 평균 0.286, 범위 0.286~0.286
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.020, 섞은 평균 0.020, 범위 0.020~0.020
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.081, 섞은 평균 0.081, 범위 0.081~0.081
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.139, 섞은 평균 0.139, 범위 0.139~0.139
- 라벨을 섞음 · B hesitation Brier: 실제 0.139, 섞은 평균 0.139, 범위 0.139~0.139
- 라벨을 섞음 · B:vision_summary normal Brier: 실제 0.256, 섞은 평균 0.256, 범위 0.256~0.256
- 라벨을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.023, 섞은 평균 0.023, 범위 0.023~0.023
- 라벨을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.071, 섞은 평균 0.071, 범위 0.071~0.071
- 라벨을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 라벨을 섞음 · B:vision_summary hesitation Brier: 실제 0.148, 섞은 평균 0.148, 범위 0.148~0.148
- 답을 섞음 · B normal Brier: 실제 0.286, 섞은 평균 0.286, 범위 0.286~0.286
- 답을 섞음 · B touch_difficulty Brier: 실제 0.020, 섞은 평균 0.020, 범위 0.020~0.020
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.081, 섞은 평균 0.081, 범위 0.081~0.081
- 답을 섞음 · B visual_difficulty Brier: 실제 0.139, 섞은 평균 0.139, 범위 0.139~0.139
- 답을 섞음 · B hesitation Brier: 실제 0.139, 섞은 평균 0.138, 범위 0.137~0.139
- 답을 섞음 · B:vision_summary normal Brier: 실제 0.256, 섞은 평균 0.256, 범위 0.255~0.257
- 답을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.023, 섞은 평균 0.023, 범위 0.022~0.023
- 답을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.071, 섞은 평균 0.072, 범위 0.071~0.074
- 답을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.138, 섞은 평균 0.137, 범위 0.137~0.138
- 답을 섞음 · B:vision_summary hesitation Brier: 실제 0.148, 섞은 평균 0.149, 범위 0.148~0.150

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 556, 섞은 평균 556.000, 범위 556~556
- 라벨을 섞음 · B normal Brier: 실제 0.286, 섞은 평균 0.283, 범위 0.276~0.291
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.020, 섞은 평균 0.020, 범위 0.020~0.020
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.081, 섞은 평균 0.085, 범위 0.065~0.097
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.139, 섞은 평균 0.169, 범위 0.128~0.199
- 라벨을 섞음 · B hesitation Brier: 실제 0.139, 섞은 평균 0.139, 범위 0.128~0.148
- 라벨을 섞음 · B:vision_summary normal Brier: 실제 0.256, 섞은 평균 0.258, 범위 0.252~0.264
- 라벨을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.023, 섞은 평균 0.023, 범위 0.023~0.023
- 라벨을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.071, 섞은 평균 0.078, 범위 0.054~0.094
- 라벨을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.138, 섞은 평균 0.169, 범위 0.127~0.204
- 라벨을 섞음 · B:vision_summary hesitation Brier: 실제 0.148, 섞은 평균 0.152, 범위 0.142~0.159
- 답을 섞음 · B normal Brier: 실제 0.286, 섞은 평균 0.291, 범위 0.288~0.295
- 답을 섞음 · B touch_difficulty Brier: 실제 0.020, 섞은 평균 0.021, 범위 0.020~0.021
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.081, 섞은 평균 0.082, 범위 0.080~0.084
- 답을 섞음 · B visual_difficulty Brier: 실제 0.139, 섞은 평균 0.141, 범위 0.138~0.145
- 답을 섞음 · B hesitation Brier: 실제 0.139, 섞은 평균 0.140, 범위 0.137~0.145
- 답을 섞음 · B:vision_summary normal Brier: 실제 0.256, 섞은 평균 0.260, 범위 0.253~0.266
- 답을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.023, 섞은 평균 0.025, 범위 0.024~0.026
- 답을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.071, 섞은 평균 0.075, 범위 0.072~0.078
- 답을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.138, 섞은 평균 0.142, 범위 0.135~0.148
- 답을 섞음 · B:vision_summary hesitation Brier: 실제 0.148, 섞은 평균 0.152, 범위 0.147~0.156
