# E5 지표: `stage3_b_B_vt_b2_rA`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `<workspace>/4_vision/eval_ab_2026-11-04/admissible_v4.csv`(admissible)
- 합성 터치 창: 값 묶음 `b2_rA`, 배치 `fit-medium`, 조건 C0, C1, C2, C3, C4, C5, C6
- 라벨 상태: 규정한 허용 행동(stipulated admissible actions) (admissible_v4.csv)

## 규칙표(조건 A)

- 창 3892개(영상 35개, 테이크 245개, 세션 257개), 측정 가능 3344개
- 기록의 상황 태그: {'unknown': 569, 'none': 3120, 'looking_around': 31, 'consulting_companion': 130, 'looking_back_with_people_behind': 42}
- 전이: {'none': 2841, 'open': 195, 'keep': 702, 'withdraw': 142, 'replace': 12}; 연 지원(open · replace): {'highlight_next_action': 137, 'large_button': 20, 'wait_hold_timer': 35, 'remaining_steps_notice': 15}
- 규칙표 자체 질문이 붙은 창: 157개 {'fit': 157}; tick으로 거둔 묻기 0개
- 허용 후보 수별 창: {0: 3685, 1: 204, 2: 3}
- 입력 기록의 결정(비전 기록 또는 E3 AB0)과 같음: {'True': 3892}
- 계약 터치 5칸: {'absent (contract five not all known)': 3892}; 최근 구간 터치 수의 출처: {'segment sum (a window without touch)': 820, 'segment sum (n windows)': 3072}
- fixture 기대값: 0개 확인, 어긋남 0개

## 실행(조건 · 변형 · 단계별)

| arm | 창 | 대상 창 | 시도한 창 | 건너뜀(이유) | 단계 | 단계 대상 | build 없음 | 시도 | 답 | 실패(종류) | API 호출 | 캐시 답 | 순서 바꾼 호출 | 지연 p50 · p95 · 최대 ms | 입력 토큰 합 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| B:novision | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 10 | 3334 | 0 | 244.4 · 406.8 · 476.9 | 7670 |
| B:notouch | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 48 | 3296 | 0 | 202.2 · 409.1 · 718.5 | 35762 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- B: API 호출 0번, 캐시 답 3344개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:novision: API 호출 10번, 캐시 답 3334개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 244.4 · p95 406.8 ms
- B:notouch: API 호출 48번, 캐시 답 3296개, 시도한 창마다 호출 0.01번; 사슬 전체 지연 p50 202.2 · p95 409.1 ms

## 같은 요청 점검(실행 동작)

- B:novision vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 0개
- B:notouch vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 0개

## 같은 입력 반복(요청마다 1번)


## 답 요약

| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| B | state_scores | hesitation | 3344 | 0.431 | 0.110 | 0.810 |
| B | state_scores | navigation_difficulty | 3344 | 0.217 | 0.040 | 0.640 |
| B | state_scores | normal | 3344 | 0.512 | 0.080 | 0.890 |
| B | state_scores | proposal_fits | 157 | 0.520 | 0.100 | 0.830 |
| B | state_scores | touch_difficulty | 3344 | 0.199 | 0.050 | 0.770 |
| B | state_scores | visual_difficulty | 3344 | 0.141 | 0.060 | 0.470 |
| B:novision | state_scores | hesitation | 3344 | 0.421 | 0.150 | 0.780 |
| B:novision | state_scores | navigation_difficulty | 3344 | 0.237 | 0.050 | 0.700 |
| B:novision | state_scores | normal | 3344 | 0.474 | 0.070 | 0.860 |
| B:novision | state_scores | proposal_fits | 157 | 0.588 | 0.160 | 0.780 |
| B:novision | state_scores | touch_difficulty | 3344 | 0.209 | 0.060 | 0.730 |
| B:novision | state_scores | visual_difficulty | 3344 | 0.193 | 0.090 | 0.560 |
| B:notouch | state_scores | hesitation | 3344 | 0.461 | 0.150 | 0.820 |
| B:notouch | state_scores | navigation_difficulty | 3344 | 0.217 | 0.060 | 0.600 |
| B:notouch | state_scores | normal | 3344 | 0.521 | 0.060 | 0.770 |
| B:notouch | state_scores | proposal_fits | 157 | 0.454 | 0.120 | 0.830 |
| B:notouch | state_scores | touch_difficulty | 3344 | 0.094 | 0.060 | 0.170 |
| B:notouch | state_scores | visual_difficulty | 3344 | 0.118 | 0.080 | 0.290 |

## 짝 비교(같은 창)

- B:novision vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 102(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 -0.011, 평균 |차| 0.044, 최대 |차| 0.320
  - navigation_difficulty: n 3344, 평균 차 0.020, 평균 |차| 0.034, 최대 |차| 0.290
  - normal: n 3344, 평균 차 -0.038, 평균 |차| 0.049, 최대 |차| 0.310
  - proposal_fits: n 157, 평균 차 0.069, 평균 |차| 0.212, 최대 |차| 0.610
  - touch_difficulty: n 3344, 평균 차 0.010, 평균 |차| 0.031, 최대 |차| 0.170
  - visual_difficulty: n 3344, 평균 차 0.053, 평균 |차| 0.055, 최대 |차| 0.190
- B:notouch vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 1477(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.030, 평균 |차| 0.116, 최대 |차| 0.340
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.071, 최대 |차| 0.420
  - normal: n 3344, 평균 차 0.009, 평균 |차| 0.183, 최대 |차| 0.540
  - proposal_fits: n 157, 평균 차 -0.066, 평균 |차| 0.142, 최대 |차| 0.510
  - touch_difficulty: n 3344, 평균 차 -0.105, 평균 |차| 0.110, 최대 |차| 0.680
  - visual_difficulty: n 3344, 평균 차 -0.022, 평균 |차| 0.034, 최대 |차| 0.340

## 라벨

- 라벨이 붙은 창 3892개(안 붙은 창 0개), 수준 {'action': 3892}, 맞춘 방법 {'segment_id': 3892}
- 구간 분류별 창: {'no_user': 105, 'wait_only': 1087, 'designated': 1193, 'allowed_not_designated': 224, 'contradictory': 881, 'time_stop': 402}
- 세션 257개 가운데 라벨 행이 둘 이상인 세션 56개
- 상태 대응(STATE_PROXY)이 있는 창 1543개: {'normal': 580, 'touch_difficulty': 309, 'hesitation,navigation_difficulty': 357, 'hesitation,navigation_difficulty,touch_difficulty': 24, 'visual_difficulty': 195, 'touch_difficulty,visual_difficulty': 39, 'hesitation,navigation_difficulty,visual_difficulty': 39}
- 창의 태그 | 정답 태그(window truth: the segment's truth tag when a GT behaviour second lies in (t - window_s, t], else none (E3 run_eval.py window_truth)): {'none | none': 3559, 'none | looking_around': 52, 'looking_around | looking_around': 4, 'looking_around | none': 24, 'none | consulting_companion': 50, 'looking_around | consulting_companion': 3, 'consulting_companion | none': 99, 'consulting_companion | consulting_companion': 31, 'none | looking_back_with_people_behind': 28, 'looking_back_with_people_behind | looking_back_with_people_behind': 14, 'looking_back_with_people_behind | none': 28}
- 보낸 질문의 선택지가 none 하나뿐인 창: 0개

### 기준이 선택지 밖인 창

- 허용 행동이 선택지(허용 후보 + none)에 없음: 전체 0(전체 3892), 후보가 있는 창 0(전체 207)
- 지정 지원이 허용 후보에 없음: 1066(전체 1168)
- 지정 지원이 규칙표 v0 밖(행 없음): 0(전체 3892) []
- 점수 대상: 제외 · 모순 구간 밖의 라벨 창 3011개(뺀 창 881개). 선택 · 상태 추정 · 규칙표 질문 · 예측 · 섞은 대조가 모두 이 창을 쓴다.

### 지원 선택(주 비교: A 대 C · C0 · E, 같은 창; 제외 구간을 뺀 창 3011개)

- A: 허용 안 2979(전체 3011, 95% 0.985~0.993)(우연 0.995), 후보가 있는 창 108(전체 140, 95% 0.667~0.857)(우연 0.885); 지정 지원과 같음 95(전체 1064, 95% 0.067~0.119)(우연 0.044); 고른 것 {'none': 2871, 'highlight_next_action': 104, 'large_button': 17, 'wait_hold_timer': 4, 'remaining_steps_notice': 15}
  - 구간 2×2: TP/FN/FP/TN = 53/13/7/79; 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 13(전체 66, 95% 0.119~0.308)(v0 행 있음 13(전체 66, 95% 0.119~0.308)), 제안 정밀도 53(전체 60, 95% 0.778~0.942); 2×2 밖 {'no_user': 56, 'allowed_not_designated': 13, 'time_stop': 21}
  - 지정 지원 자체를 시작 시각 이후 낸 구간(v0 행 있음): 53(전체 66, 95% 0.692~0.881); 규칙표 행이 없는 지정 구간(2×2 밖)에서 지정 지원 자체를 낸 구간: 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 낸 구간 4(전체 20)은 도움으로 세지 않음)
  - 도움 규칙: 시작 시각 이후 허용 도움(admissible help after onset; 같은 turn에서 연 지원이 시작 시각 이후 보이면 도움, 시작 시각 전에 열어 그때까지 보이면 지연 0). 시작 시각 전에 연 도움 2구간(앞선 초 [1.0, 3.0]), 지연 중앙값 3.235초(n 53); 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 41, 'FN': 13, 'designated_delivery': {'k': 41, 'n': 54}}}; 옛 규칙(시작 시각 이후 새 제안만) TP/FN 52/14, 지정 지원 {'k': 52, 'n': 66}
  - 허용 밖 결정의 분류(창 정답 태그 기준, 기술만, 인과 주장 아님): {'decision_errors': 32, 'of_windows': 3011, 'with_incorrect_observed_tag': 1, 'with_correct_observed_tag': 25, 'observed_tag_unknown': 6, 'reference_missing': 0}
- 오프라인 기준(호출 없음, 후보가 있는 창 140개): 늘 none 140(전체 140, 95% 1.000~1.000), 늘 후보 108(전체 140, 95% 0.667~0.857), 철회된 지원이면 none 112(전체 140, 95% 0.722~0.869)(철회 목록을 아는 창 140개); 철회 규칙의 구간 2×2 TP/FN/FP/TN = 52/14/7/79

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)

- B: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.171 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.861(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.794(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.039 · AUROC 0.582(n 1287, 양성 213); hesitation Brier 0.196(기준율 0.177, skill -0.111) · ECE 0.194 · AUROC 0.748(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.820(n 850), backs_recent 0.309 대 0.820(n 850), fixes_recent 0.316 대 0.820(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.861(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.794(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.582(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.721(n 850), backs_recent 0.942 대 0.721(n 850), fixes_recent 0.322 대 0.721(n 850), condition_C2 0.322 대 0.748(n 1287)
- B:novision: normal Brier 0.229(기준율 0.239, skill 0.040) · ECE 0.196 · AUROC 0.669(n 1287, 양성 507); touch_difficulty Brier 0.137(기준율 0.197, skill 0.302) · ECE 0.132 · AUROC 0.862(n 1287, 양성 346); navigation_difficulty Brier 0.144(기준율 0.177, skill 0.184) · ECE 0.119 · AUROC 0.796(n 1287, 양성 295); visual_difficulty Brier 0.140(기준율 0.138, skill -0.014) · ECE 0.038 · AUROC 0.551(n 1287, 양성 213); hesitation Brier 0.184(기준율 0.177, skill -0.042) · ECE 0.200 · AUROC 0.785(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.798(n 850), backs_recent 0.309 대 0.798(n 850), fixes_recent 0.316 대 0.798(n 850), condition_C2 0.285 대 0.669(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.934(n 850), backs_recent 0.314 대 0.934(n 850), fixes_recent 0.919 대 0.934(n 850), condition_C2 0.996 대 0.862(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.862(n 850), backs_recent 0.942 대 0.862(n 850), fixes_recent 0.322 대 0.862(n 850), condition_C2 0.322 대 0.796(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.535(n 850), backs_recent 0.464 대 0.535(n 850), fixes_recent 0.477 대 0.535(n 850), condition_C2 0.445 대 0.551(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.762(n 850), backs_recent 0.942 대 0.762(n 850), fixes_recent 0.322 대 0.762(n 850), condition_C2 0.322 대 0.785(n 1287)
- B:notouch: normal Brier 0.266(기준율 0.239, skill -0.115) · ECE 0.216 · AUROC 0.522(n 1287, 양성 507); touch_difficulty Brier 0.225(기준율 0.197, skill -0.143) · ECE 0.173 · AUROC 0.490(n 1287, 양성 346); navigation_difficulty Brier 0.164(기준율 0.177, skill 0.074) · ECE 0.101 · AUROC 0.622(n 1287, 양성 295); visual_difficulty Brier 0.138(기준율 0.138, skill -0.002) · ECE 0.052 · AUROC 0.615(n 1287, 양성 213); hesitation Brier 0.200(기준율 0.177, skill -0.132) · ECE 0.305 · AUROC 0.752(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.631(n 850), backs_recent 0.309 대 0.631(n 850), fixes_recent 0.316 대 0.631(n 850), condition_C2 0.285 대 0.522(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.570(n 850), backs_recent 0.314 대 0.570(n 850), fixes_recent 0.919 대 0.570(n 850), condition_C2 0.996 대 0.490(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.720(n 850), backs_recent 0.942 대 0.720(n 850), fixes_recent 0.322 대 0.720(n 850), condition_C2 0.322 대 0.622(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.624(n 850), backs_recent 0.464 대 0.624(n 850), fixes_recent 0.477 대 0.624(n 850), condition_C2 0.445 대 0.615(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.787(n 850), backs_recent 0.942 대 0.787(n 850), fixes_recent 0.322 대 0.787(n 850), condition_C2 0.322 대 0.752(n 1287)

### 규칙표 자체 질문(proposal_fits, 보조)

- B: Brier 0.371 · ECE 0.404 · AUROC 0.408(n 122, 양성 96)
- B:novision: Brier 0.274 · ECE 0.346 · AUROC 0.401(n 122, 양성 96)
- B:notouch: Brier 0.371 · ECE 0.386 · AUROC 0.329(n 122, 양성 96)

### 다음 어려움 예측(D · E, 따로 셈)


### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 2979, 섞은 평균 2974.508, 범위 2963~2984
- 라벨을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.245
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.144~0.151
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B hesitation Brier: 실제 0.196, 섞은 평균 0.203, 범위 0.200~0.207
- 라벨을 섞음 · B:novision normal Brier: 실제 0.229, 섞은 평균 0.233, 범위 0.230~0.236
- 라벨을 섞음 · B:novision touch_difficulty Brier: 실제 0.137, 섞은 평균 0.139, 범위 0.137~0.141
- 라벨을 섞음 · B:novision navigation_difficulty Brier: 실제 0.144, 섞은 평균 0.149, 범위 0.146~0.153
- 라벨을 섞음 · B:novision visual_difficulty Brier: 실제 0.140, 섞은 평균 0.140, 범위 0.140~0.140
- 라벨을 섞음 · B:novision hesitation Brier: 실제 0.184, 섞은 평균 0.190, 범위 0.187~0.193
- 라벨을 섞음 · B:notouch normal Brier: 실제 0.266, 섞은 평균 0.271, 범위 0.268~0.274
- 라벨을 섞음 · B:notouch touch_difficulty Brier: 실제 0.225, 섞은 평균 0.225, 범위 0.225~0.225
- 라벨을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.164, 섞은 평균 0.167, 범위 0.164~0.169
- 라벨을 섞음 · B:notouch visual_difficulty Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 라벨을 섞음 · B:notouch hesitation Brier: 실제 0.200, 섞은 평균 0.206, 범위 0.203~0.208
- 답을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.236~0.248
- 답을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.148~0.156
- 답을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B hesitation Brier: 실제 0.196, 섞은 평균 0.207, 범위 0.203~0.211
- 답을 섞음 · B:novision normal Brier: 실제 0.229, 섞은 평균 0.234, 범위 0.230~0.238
- 답을 섞음 · B:novision touch_difficulty Brier: 실제 0.137, 섞은 평균 0.140, 범위 0.138~0.142
- 답을 섞음 · B:novision navigation_difficulty Brier: 실제 0.144, 섞은 평균 0.154, 범위 0.151~0.158
- 답을 섞음 · B:novision visual_difficulty Brier: 실제 0.140, 섞은 평균 0.140, 범위 0.140~0.140
- 답을 섞음 · B:novision hesitation Brier: 실제 0.184, 섞은 평균 0.193, 범위 0.191~0.196
- 답을 섞음 · B:notouch normal Brier: 실제 0.266, 섞은 평균 0.273, 범위 0.270~0.276
- 답을 섞음 · B:notouch touch_difficulty Brier: 실제 0.225, 섞은 평균 0.225, 범위 0.224~0.225
- 답을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.164, 섞은 평균 0.169, 범위 0.167~0.172
- 답을 섞음 · B:notouch visual_difficulty Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 답을 섞음 · B:notouch hesitation Brier: 실제 0.200, 섞은 평균 0.208, 범위 0.205~0.211

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 2979, 섞은 평균 2915.903, 범위 2900~2931
- 라벨을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.319
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.201~0.231
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.172~0.193
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.150~0.169
- 라벨을 섞음 · B hesitation Brier: 실제 0.196, 섞은 평균 0.238, 범위 0.225~0.249
- 라벨을 섞음 · B:novision normal Brier: 실제 0.229, 섞은 평균 0.284, 범위 0.267~0.300
- 라벨을 섞음 · B:novision touch_difficulty Brier: 실제 0.137, 섞은 평균 0.208, 범위 0.192~0.219
- 라벨을 섞음 · B:novision navigation_difficulty Brier: 실제 0.144, 섞은 평균 0.182, 범위 0.172~0.193
- 라벨을 섞음 · B:novision visual_difficulty Brier: 실제 0.140, 섞은 평균 0.160, 범위 0.150~0.169
- 라벨을 섞음 · B:novision hesitation Brier: 실제 0.184, 섞은 평균 0.223, 범위 0.213~0.232
- 라벨을 섞음 · B:notouch normal Brier: 실제 0.266, 섞은 평균 0.270, 범위 0.262~0.280
- 라벨을 섞음 · B:notouch touch_difficulty Brier: 실제 0.225, 섞은 평균 0.205, 범위 0.194~0.214
- 라벨을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.164, 섞은 평균 0.175, 범위 0.166~0.184
- 라벨을 섞음 · B:notouch visual_difficulty Brier: 실제 0.138, 섞은 평균 0.160, 범위 0.150~0.168
- 라벨을 섞음 · B:notouch hesitation Brier: 실제 0.200, 섞은 평균 0.240, 범위 0.233~0.247
- 답을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.305, 범위 0.285~0.323
- 답을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.217~0.245
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.179~0.193
- 답을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.137~0.146
- 답을 섞음 · B hesitation Brier: 실제 0.196, 섞은 평균 0.240, 범위 0.229~0.256
- 답을 섞음 · B:novision normal Brier: 실제 0.229, 섞은 평균 0.289, 범위 0.264~0.306
- 답을 섞음 · B:novision touch_difficulty Brier: 실제 0.137, 섞은 평균 0.222, 범위 0.209~0.235
- 답을 섞음 · B:novision navigation_difficulty Brier: 실제 0.144, 섞은 평균 0.186, 범위 0.179~0.192
- 답을 섞음 · B:novision visual_difficulty Brier: 실제 0.140, 섞은 평균 0.144, 범위 0.138~0.148
- 답을 섞음 · B:novision hesitation Brier: 실제 0.184, 섞은 평균 0.226, 범위 0.215~0.240
- 답을 섞음 · B:notouch normal Brier: 실제 0.266, 섞은 평균 0.269, 범위 0.257~0.277
- 답을 섞음 · B:notouch touch_difficulty Brier: 실제 0.225, 섞은 평균 0.227, 범위 0.226~0.228
- 답을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.164, 섞은 평균 0.180, 범위 0.176~0.185
- 답을 섞음 · B:notouch visual_difficulty Brier: 실제 0.138, 섞은 평균 0.141, 범위 0.139~0.143
- 답을 섞음 · B:notouch hesitation Brier: 실제 0.200, 섞은 평균 0.233, 범위 0.227~0.241
