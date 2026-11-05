# E5 지표: `stage1_aligned_b0_r0`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `C:/Users/samsung-user/claude/Capstone_Design_Project/4_vision/eval_ab_2026-11-04/admissible_v4.csv`(admissible)
- 합성 터치 창: 값 묶음 `b0_r0`, 배치 `fit-medium`, 조건 C0, C1, C2, C3, C4, C5, C6
- 라벨 상태: 규정한 허용 행동(stipulated admissible actions) (admissible_v4.csv)

## 규칙표(조건 A)

- 창 3892개(영상 35개, 테이크 245개, 세션 257개), 측정 가능 3344개
- 기록의 상황 태그: {'unknown': 749, 'none': 3143}
- 전이: {'none': 2989, 'open': 161, 'keep': 625, 'withdraw': 117}; 연 지원(open · replace): {'highlight_next_action': 141, 'large_button': 20}
- 규칙표 자체 질문이 붙은 창: 134개 {'fit': 134}; tick으로 거둔 묻기 0개
- 허용 후보 수별 창: {0: 3731, 1: 160, 2: 1}
- 입력 기록의 결정(비전 기록 또는 E3 AB0)과 같음: {'True': 3892}
- 계약 터치 5칸: {'absent (contract five not all known)': 3892}; 최근 구간 터치 수의 출처: {'segment sum (a window without touch)': 820, 'segment sum (n windows)': 3072}
- fixture 기대값: 0개 확인, 어긋남 0개

## 실행(조건 · 변형 · 단계별)

| arm | 창 | 대상 창 | 시도한 창 | 건너뜀(이유) | 단계 | 단계 대상 | build 없음 | 시도 | 답 | 실패(종류) | API 호출 | 캐시 답 | 순서 바꾼 호출 | 지연 p50 · p95 · 최대 ms | 입력 토큰 합 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 3892 | 3344 | 0 | 조건 A(묻지 않음) | - | - | - | - | - | - | - | - | - | - | - |
| B | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| C | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| | | | | | support_choice | 3344 | 3183 | 161 | 161 | 0 | 0 | 161 | 0 | - · - · - | 0 |
| C0 | 3892 | 3344 | 3344 | {'not measurable': 548} | support_choice | 3344 | 3183 | 161 | 161 | 0 | 0 | 161 | 0 | - · - · - | 0 |
| D | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| | | | | | next_difficulty | 3344 | 188 | 3156 | 3156 | 0 | 0 | 3156 | 0 | - · - · - | 0 |
| E | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| | | | | | support_choice | 3344 | 3183 | 161 | 161 | 0 | 0 | 161 | 0 | - · - · - | 0 |
| | | | | | next_difficulty | 3344 | 188 | 3156 | 3156 | 0 | 0 | 3156 | 0 | - · - · - | 0 |
| B:novision | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| B:notouch | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| B:la_null | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| B:sit_dict | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| B:vision_summary | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| B:wording_nocrit | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 142 | 3202 | 0 | 197.0 · 310.2 · 982.3 | 71502 |
| B:perm_vision | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 107 | 3237 | 0 | 204.3 · 360.6 · 516.9 | 79134 |
| B:perm_touch | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 155 | 3189 | 0 | 211.0 · 335.0 · 588.1 | 116245 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- B: API 호출 0번, 캐시 답 3344개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- C: API 호출 0번, 캐시 답 3666개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 161(전체 3344); 사슬 전체 지연 p50 - · p95 - ms
- C0: API 호출 0번, 캐시 답 322개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 161(전체 3344); 사슬 전체 지연 p50 0.0 · p95 0.0 ms
- D: API 호출 0번, 캐시 답 6500개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- E: API 호출 0번, 캐시 답 6822개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 161(전체 3344); 사슬 전체 지연 p50 - · p95 - ms
- B:novision: API 호출 0번, 캐시 답 3344개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:notouch: API 호출 0번, 캐시 답 3344개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:la_null: API 호출 0번, 캐시 답 3344개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:sit_dict: API 호출 0번, 캐시 답 3344개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:vision_summary: API 호출 0번, 캐시 답 3344개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:wording_nocrit: API 호출 142번, 캐시 답 3202개, 시도한 창마다 호출 0.04번; 사슬 전체 지연 p50 197.0 · p95 310.2 ms
- B:perm_vision: API 호출 107번, 캐시 답 3237개, 시도한 창마다 호출 0.03번; 사슬 전체 지연 p50 204.3 · p95 360.6 ms
- B:perm_touch: API 호출 155번, 캐시 답 3189개, 시도한 창마다 호출 0.05번; 사슬 전체 지연 p50 211.0 · p95 335.0 ms

## 같은 요청 점검(실행 동작)

- B:novision vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 0개
- B:notouch vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 0개
- B:la_null vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 3344개
- B:sit_dict vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 3344개
- B:vision_summary vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 0개
- B:wording_nocrit vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 0개
- B:perm_vision vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 2387개
- B:perm_touch vs B, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 1113개
- C0 vs C, 단계 support_choice: 짝 창 161개, 요청이 같은 창 0개
- C vs B (state_scores), 단계 state_scores: 짝 창 3344개, 요청이 같은 창 3344개
- D vs B (state_scores), 단계 state_scores: 짝 창 3344개, 요청이 같은 창 3344개
- E vs B (state_scores), 단계 state_scores: 짝 창 3344개, 요청이 같은 창 3344개

## 같은 입력 반복(요청마다 1번)


## 답 요약

| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| B | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| B | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| B | state_scores | normal | 3344 | 0.520 | 0.080 | 0.890 |
| B | state_scores | proposal_fits | 134 | 0.459 | 0.130 | 0.780 |
| B | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| B | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| C | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| C | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| C | state_scores | normal | 3344 | 0.520 | 0.080 | 0.890 |
| C | state_scores | proposal_fits | 134 | 0.459 | 0.130 | 0.780 |
| C | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| C | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| C | support_choice | support_choice(choice) | 161 | {'highlight_next_action': 78, 'none': 63, 'large_button': 20} | conf 평균 0.563 | |
| C0 | support_choice | support_choice(choice) | 161 | {'highlight_next_action': 77, 'none': 65, 'large_button': 19} | conf 평균 0.505 | |
| D | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| D | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| D | state_scores | normal | 3344 | 0.520 | 0.080 | 0.890 |
| D | state_scores | proposal_fits | 134 | 0.459 | 0.130 | 0.780 |
| D | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| D | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| D | next_difficulty | next_difficulty(choice) | 3156 | {'hesitation': 2656, 'touch_difficulty': 345, 'navigation_difficulty': 27, 'none': 128} | conf 평균 0.906 | |
| E | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| E | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| E | state_scores | normal | 3344 | 0.520 | 0.080 | 0.890 |
| E | state_scores | proposal_fits | 134 | 0.459 | 0.130 | 0.780 |
| E | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| E | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| E | next_difficulty | next_difficulty(choice) | 3156 | {'hesitation': 2656, 'touch_difficulty': 342, 'navigation_difficulty': 30, 'none': 128} | conf 평균 0.907 | |
| E | support_choice | support_choice(choice) | 161 | {'highlight_next_action': 78, 'none': 63, 'large_button': 20} | conf 평균 0.563 | |
| B:novision | state_scores | hesitation | 3344 | 0.414 | 0.160 | 0.710 |
| B:novision | state_scores | navigation_difficulty | 3344 | 0.232 | 0.050 | 0.700 |
| B:novision | state_scores | normal | 3344 | 0.483 | 0.080 | 0.860 |
| B:novision | state_scores | proposal_fits | 134 | 0.604 | 0.350 | 0.770 |
| B:novision | state_scores | touch_difficulty | 3344 | 0.209 | 0.060 | 0.730 |
| B:novision | state_scores | visual_difficulty | 3344 | 0.192 | 0.090 | 0.560 |
| B:notouch | state_scores | hesitation | 3344 | 0.453 | 0.150 | 0.720 |
| B:notouch | state_scores | navigation_difficulty | 3344 | 0.203 | 0.060 | 0.430 |
| B:notouch | state_scores | normal | 3344 | 0.545 | 0.220 | 0.770 |
| B:notouch | state_scores | proposal_fits | 134 | 0.389 | 0.120 | 0.630 |
| B:notouch | state_scores | touch_difficulty | 3344 | 0.093 | 0.060 | 0.170 |
| B:notouch | state_scores | visual_difficulty | 3344 | 0.117 | 0.080 | 0.240 |
| B:la_null | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| B:la_null | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| B:la_null | state_scores | normal | 3344 | 0.520 | 0.080 | 0.890 |
| B:la_null | state_scores | proposal_fits | 134 | 0.459 | 0.130 | 0.780 |
| B:la_null | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| B:la_null | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| B:sit_dict | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| B:sit_dict | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| B:sit_dict | state_scores | normal | 3344 | 0.520 | 0.080 | 0.890 |
| B:sit_dict | state_scores | proposal_fits | 134 | 0.459 | 0.130 | 0.780 |
| B:sit_dict | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| B:sit_dict | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| B:vision_summary | state_scores | hesitation | 3344 | 0.461 | 0.140 | 0.800 |
| B:vision_summary | state_scores | navigation_difficulty | 3344 | 0.205 | 0.040 | 0.640 |
| B:vision_summary | state_scores | normal | 3344 | 0.535 | 0.090 | 0.890 |
| B:vision_summary | state_scores | proposal_fits | 134 | 0.481 | 0.140 | 0.790 |
| B:vision_summary | state_scores | touch_difficulty | 3344 | 0.210 | 0.060 | 0.770 |
| B:vision_summary | state_scores | visual_difficulty | 3344 | 0.144 | 0.060 | 0.520 |
| B:wording_nocrit | state_scores | hesitation | 3344 | 0.460 | 0.100 | 0.820 |
| B:wording_nocrit | state_scores | navigation_difficulty | 3344 | 0.211 | 0.050 | 0.600 |
| B:wording_nocrit | state_scores | normal | 3344 | 0.552 | 0.140 | 0.820 |
| B:wording_nocrit | state_scores | proposal_fits | 134 | 0.458 | 0.130 | 0.780 |
| B:wording_nocrit | state_scores | touch_difficulty | 3344 | 0.198 | 0.060 | 0.730 |
| B:wording_nocrit | state_scores | visual_difficulty | 3344 | 0.134 | 0.070 | 0.460 |
| B:perm_vision | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| B:perm_vision | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| B:perm_vision | state_scores | normal | 3344 | 0.521 | 0.080 | 0.890 |
| B:perm_vision | state_scores | proposal_fits | 134 | 0.450 | 0.100 | 0.790 |
| B:perm_vision | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| B:perm_vision | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| B:perm_touch | state_scores | hesitation | 3344 | 0.428 | 0.100 | 0.800 |
| B:perm_touch | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.720 |
| B:perm_touch | state_scores | normal | 3344 | 0.522 | 0.080 | 0.920 |
| B:perm_touch | state_scores | proposal_fits | 134 | 0.368 | 0.080 | 0.790 |
| B:perm_touch | state_scores | touch_difficulty | 3344 | 0.199 | 0.050 | 0.770 |
| B:perm_touch | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.490 |

## 짝 비교(같은 창)

- B:novision vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 83(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 -0.014, 평균 |차| 0.043, 최대 |차| 0.270
  - navigation_difficulty: n 3344, 평균 차 0.020, 평균 |차| 0.032, 최대 |차| 0.140
  - normal: n 3344, 평균 차 -0.038, 평균 |차| 0.048, 최대 |차| 0.200
  - proposal_fits: n 134, 평균 차 0.145, 평균 |차| 0.215, 최대 |차| 0.610
  - touch_difficulty: n 3344, 평균 차 0.009, 평균 |차| 0.030, 최대 |차| 0.170
  - visual_difficulty: n 3344, 평균 차 0.052, 평균 |차| 0.053, 최대 |차| 0.190
- B:notouch vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 1512(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.025, 평균 |차| 0.120, 최대 |차| 0.340
  - navigation_difficulty: n 3344, 평균 차 -0.009, 평균 |차| 0.070, 최대 |차| 0.420
  - normal: n 3344, 평균 차 0.024, 평균 |차| 0.182, 최대 |차| 0.520
  - proposal_fits: n 134, 평균 차 -0.070, 평균 |차| 0.158, 최대 |차| 0.510
  - touch_difficulty: n 3344, 평균 차 -0.106, 평균 |차| 0.111, 최대 |차| 0.680
  - visual_difficulty: n 3344, 평균 차 -0.023, 평균 |차| 0.035, 최대 |차| 0.340
- B:la_null vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - proposal_fits: n 134, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- B:sit_dict vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - proposal_fits: n 134, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- B:vision_summary vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 104(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.033, 평균 |차| 0.037, 최대 |차| 0.190
  - navigation_difficulty: n 3344, 평균 차 -0.007, 평균 |차| 0.015, 최대 |차| 0.080
  - normal: n 3344, 평균 차 0.015, 평균 |차| 0.029, 최대 |차| 0.160
  - proposal_fits: n 134, 평균 차 0.021, 평균 |차| 0.030, 최대 |차| 0.120
  - touch_difficulty: n 3344, 평균 차 0.011, 평균 |차| 0.014, 최대 |차| 0.080
  - visual_difficulty: n 3344, 평균 차 0.004, 평균 |차| 0.015, 최대 |차| 0.160
- B:wording_nocrit vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 305(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.033, 평균 |차| 0.039, 최대 |차| 0.410
  - navigation_difficulty: n 3344, 평균 차 -0.001, 평균 |차| 0.046, 최대 |차| 0.210
  - normal: n 3344, 평균 차 0.032, 평균 |차| 0.092, 최대 |차| 0.310
  - proposal_fits: n 134, 평균 차 -0.001, 평균 |차| 0.013, 최대 |차| 0.040
  - touch_difficulty: n 3344, 평균 차 -0.002, 평균 |차| 0.018, 최대 |차| 0.170
  - visual_difficulty: n 3344, 평균 차 -0.006, 평균 |차| 0.017, 최대 |차| 0.220
- B:perm_vision vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 26(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 -0.000, 평균 |차| 0.011, 최대 |차| 0.440
  - navigation_difficulty: n 3344, 평균 차 -0.000, 평균 |차| 0.005, 최대 |차| 0.140
  - normal: n 3344, 평균 차 0.001, 평균 |차| 0.009, 최대 |차| 0.170
  - proposal_fits: n 134, 평균 차 -0.009, 평균 |차| 0.020, 최대 |차| 0.230
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.005, 최대 |차| 0.190
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.008, 최대 |차| 0.220
- B:perm_touch vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 876(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.094, 최대 |차| 0.590
  - navigation_difficulty: n 3344, 평균 차 -0.000, 평균 |차| 0.059, 최대 |차| 0.450
  - normal: n 3344, 평균 차 0.002, 평균 |차| 0.126, 최대 |차| 0.710
  - proposal_fits: n 134, 평균 차 -0.091, 평균 |차| 0.097, 최대 |차| 0.550
  - touch_difficulty: n 3344, 평균 차 -0.001, 평균 |차| 0.071, 최대 |차| 0.680
  - visual_difficulty: n 3344, 평균 차 -0.000, 평균 |차| 0.027, 최대 |차| 0.340
- C0 vs C, support_choice: 가장 큰 상태 점수가 바뀐 창 0(전체 0); 고른 답이 바뀐 창 {'support_choice': '3(전체 161)'}
- C vs B (state_scores), state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - proposal_fits: n 134, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- D vs B (state_scores), state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - proposal_fits: n 134, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- E vs B (state_scores), state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - proposal_fits: n 134, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000

## 라벨

- 라벨이 붙은 창 3892개(안 붙은 창 0개), 수준 {'action': 3892}, 맞춘 방법 {'segment_id': 3892}
- 구간 분류별 창: {'no_user': 105, 'wait_only': 1087, 'designated': 1193, 'allowed_not_designated': 224, 'contradictory': 881, 'time_stop': 402}
- 세션 257개 가운데 라벨 행이 둘 이상인 세션 56개
- 상태 대응(STATE_PROXY)이 있는 창 1543개: {'normal': 580, 'touch_difficulty': 309, 'hesitation,navigation_difficulty': 357, 'hesitation,navigation_difficulty,touch_difficulty': 24, 'visual_difficulty': 195, 'touch_difficulty,visual_difficulty': 39, 'hesitation,navigation_difficulty,visual_difficulty': 39}
- 창의 태그 | 정답 태그(window truth: the segment's truth tag when a GT behaviour second lies in (t - window_s, t], else none (E3 run_eval.py window_truth)): {'none | none': 3633, 'none | looking_around': 70, 'none | consulting_companion': 126, 'none | looking_back_with_people_behind': 63}
- 보낸 질문의 선택지가 none 하나뿐인 창: 0개

### 기준이 선택지 밖인 창

- 허용 행동이 선택지(허용 후보 + none)에 없음: 전체 0(전체 3892), 후보가 있는 창 0(전체 161)
- 지정 지원이 허용 후보에 없음: 1079(전체 1168)
- 지정 지원이 규칙표 v0 밖(행 없음): 0(전체 3892) []
- 점수 대상: 제외 · 모순 구간 밖의 라벨 창 3011개(뺀 창 881개). 선택 · 상태 추정 · 규칙표 질문 · 예측 · 섞은 대조가 모두 이 창을 쓴다.

### 지원 선택(주 비교: A 대 C · C0 · E, 같은 창; 제외 구간을 뺀 창 3011개)

- A: 허용 안 2977(전체 3011, 95% 0.985~0.992)(우연 0.994), 후보가 있는 창 91(전체 125, 95% 0.626~0.815)(우연 0.863); 지정 지원과 같음 82(전체 1064, 95% 0.058~0.107)(우연 0.039); 고른 것 {'none': 2886, 'highlight_next_action': 108, 'large_button': 17}
  - 구간 2×2: TP/FN/FP/TN = 44/22/7/79; 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 22(전체 66, 95% 0.232~0.453)(v0 행 있음 22(전체 66, 95% 0.232~0.453)), 제안 정밀도 44(전체 51, 95% 0.743~0.932); 2×2 밖 {'no_user': 56, 'allowed_not_designated': 13, 'time_stop': 21}
  - 지정 지원 자체를 시작 시각 이후 낸 구간(v0 행 있음): 42(전체 66, 95% 0.516~0.742); 규칙표 행이 없는 지정 구간(2×2 밖)에서 지정 지원 자체를 낸 구간: 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 낸 구간 4(전체 20)은 도움으로 세지 않음)
  - 도움 규칙: 시작 시각 이후 허용 도움(admissible help after onset; 같은 turn에서 연 지원이 시작 시각 이후 보이면 도움, 시작 시각 전에 열어 그때까지 보이면 지연 0). 시작 시각 전에 연 도움 2구간(앞선 초 [1.0, 3.0]), 지연 중앙값 3.117초(n 44); 출처별 {'camera': {'designated_v0_row': 12, 'TP': 4, 'FN': 8, 'designated_delivery': {'k': 2, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 40, 'FN': 14, 'designated_delivery': {'k': 40, 'n': 54}}}; 옛 규칙(시작 시각 이후 새 제안만) TP/FN 42/24, 지정 지원 {'k': 41, 'n': 66}
  - 허용 밖 결정의 분류(창 정답 태그 기준, 기술만, 인과 주장 아님): {'decision_errors': 34, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 19, 'observed_tag_unknown': 15, 'reference_missing': 0}
- 오프라인 기준(호출 없음, 후보가 있는 창 125개): 늘 none 125(전체 125, 95% 1.000~1.000), 늘 후보 91(전체 125, 95% 0.626~0.815), 철회된 지원이면 none 95(전체 125, 95% 0.685~0.828)(철회 목록을 아는 창 125개); 철회 규칙의 구간 2×2 TP/FN/FP/TN = 43/23/7/79
- C: 선택지(the sent question's options (a support besides none))가 있는 창 125개, 상태 {'answered': 125}
  - 첫 순서: 답한 창에서 허용 안 95(전체 125, 95% 0.685~0.828)(우연 0.863; 같은 창의 A 91(전체 125, 95% 0.626~0.815)); 규칙표로 채운 전체 2981(전체 3011, 95% 0.987~0.993); 지정 지원과 같음 41(전체 87, 95% 0.404~0.549)(우연 0.471); 고른 지원 확률 Brier 0.258 · ECE 0.356 · AUROC 0.104(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 123, 'order_disagree': 2}; 허용 안 94(전체 123, 95% 0.692~0.830)(우연 0.866); 같은 창의 A 90(전체 123, 95% 0.628~0.817); 순서 일관성 123(전체 125, 95% 0.961~1.000)(무작위 선택자 0.499, 합의 · 허용 0.431)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 43/23/7/79(A는 44/22/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 23(전체 66, 95% 0.245~0.469), 제안 정밀도 43(전체 50, 95% 0.738~0.930); 허용 밖 결정의 분류 {'decision_errors': 30, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 15, 'observed_tag_unknown': 15, 'reference_missing': 0}
  - 다음 창 적용: 짝 113개에서 C 88, 한 창 늦춘 A 85, 같은 창 A 113; 한 창 늦춘 A 전체 2770(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 41(전체 66, 95% 0.501~0.729); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 4, 'FN': 8, 'designated_delivery': {'k': 2, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 39, 'FN': 15, 'designated_delivery': {'k': 39, 'n': 54}}}; 시작 시각 전에 연 도움 2구간; 옛 규칙 TP/FN 41/25, 지정 지원 {'k': 40, 'n': 66}
  - 고르지 않은 창 45개(전체 125): {'kept_inadmissible_candidate': 30, 'declined_inadmissible_candidate': 4, 'kept_admissible_candidate': 50, 'declined_admissible_candidate': 41}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 103.2 대 실제 95; 철회 규칙 재현 124(전체 125, 95% 0.956~0.999)(철회된 후보에서 고르지 않음 45(전체 46), 처음 후보에서 0(전체 79))
- C0: 선택지(the sent question's options (a support besides none))가 있는 창 125개, 상태 {'answered': 125}
  - 첫 순서: 답한 창에서 허용 안 95(전체 125, 95% 0.685~0.828)(우연 0.863; 같은 창의 A 91(전체 125, 95% 0.626~0.815)); 규칙표로 채운 전체 2981(전체 3011, 95% 0.987~0.993); 지정 지원과 같음 40(전체 87, 95% 0.394~0.537)(우연 0.471); 고른 지원 확률 Brier 0.221 · ECE 0.262 · AUROC 0.236(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 123, 'order_disagree': 2}; 허용 안 93(전체 123, 95% 0.679~0.825)(우연 0.864); 같은 창의 A 90(전체 123, 95% 0.636~0.814); 순서 일관성 123(전체 125, 95% 0.959~1.000)(무작위 선택자 0.499, 합의 · 허용 0.431)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 43/23/7/79(A는 44/22/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 23(전체 66, 95% 0.245~0.469), 제안 정밀도 43(전체 50, 95% 0.738~0.930); 허용 밖 결정의 분류 {'decision_errors': 30, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 15, 'observed_tag_unknown': 15, 'reference_missing': 0}
  - 다음 창 적용: 짝 113개에서 C 88, 한 창 늦춘 A 85, 같은 창 A 113; 한 창 늦춘 A 전체 2770(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 41(전체 66, 95% 0.501~0.729); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 4, 'FN': 8, 'designated_delivery': {'k': 2, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 39, 'FN': 15, 'designated_delivery': {'k': 39, 'n': 54}}}; 시작 시각 전에 연 도움 2구간; 옛 규칙 TP/FN 41/25, 지정 지원 {'k': 40, 'n': 66}
  - 고르지 않은 창 46개(전체 125): {'kept_inadmissible_candidate': 30, 'declined_inadmissible_candidate': 4, 'kept_admissible_candidate': 49, 'declined_admissible_candidate': 42}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 103.5 대 실제 95; 철회 규칙 재현 125(전체 125, 95% 0.970~1.000)(철회된 후보에서 고르지 않음 46(전체 46), 처음 후보에서 0(전체 79))
- E: 선택지(the sent question's options (a support besides none))가 있는 창 125개, 상태 {'answered': 125}
  - 첫 순서: 답한 창에서 허용 안 95(전체 125, 95% 0.685~0.828)(우연 0.863; 같은 창의 A 91(전체 125, 95% 0.626~0.815)); 규칙표로 채운 전체 2981(전체 3011, 95% 0.987~0.993); 지정 지원과 같음 41(전체 87, 95% 0.404~0.549)(우연 0.471); 고른 지원 확률 Brier 0.258 · ECE 0.356 · AUROC 0.104(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 123, 'order_disagree': 2}; 허용 안 94(전체 123, 95% 0.692~0.830)(우연 0.866); 같은 창의 A 90(전체 123, 95% 0.628~0.817); 순서 일관성 123(전체 125, 95% 0.961~1.000)(무작위 선택자 0.499, 합의 · 허용 0.431)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 43/23/7/79(A는 44/22/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 23(전체 66, 95% 0.245~0.469), 제안 정밀도 43(전체 50, 95% 0.738~0.930); 허용 밖 결정의 분류 {'decision_errors': 30, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 15, 'observed_tag_unknown': 15, 'reference_missing': 0}
  - 다음 창 적용: 짝 113개에서 C 88, 한 창 늦춘 A 85, 같은 창 A 113; 한 창 늦춘 A 전체 2770(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 41(전체 66, 95% 0.501~0.729); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 4, 'FN': 8, 'designated_delivery': {'k': 2, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 39, 'FN': 15, 'designated_delivery': {'k': 39, 'n': 54}}}; 시작 시각 전에 연 도움 2구간; 옛 규칙 TP/FN 41/25, 지정 지원 {'k': 40, 'n': 66}
  - 고르지 않은 창 45개(전체 125): {'kept_inadmissible_candidate': 30, 'declined_inadmissible_candidate': 4, 'kept_admissible_candidate': 50, 'declined_admissible_candidate': 41}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 103.2 대 실제 95; 철회 규칙 재현 124(전체 125, 95% 0.956~0.999)(철회된 후보에서 고르지 않음 45(전체 46), 처음 후보에서 0(전체 79))

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)

- B: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.174 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.793(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.099) · ECE 0.195 · AUROC 0.761(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.793(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.761(n 1287)
- C: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.174 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.793(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.099) · ECE 0.195 · AUROC 0.761(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.793(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.761(n 1287)
- D: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.174 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.793(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.099) · ECE 0.195 · AUROC 0.761(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.793(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.761(n 1287)
- E: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.174 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.793(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.099) · ECE 0.195 · AUROC 0.761(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.793(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.761(n 1287)
- B:novision: normal Brier 0.230(기준율 0.239, skill 0.037) · ECE 0.199 · AUROC 0.666(n 1287, 양성 507); touch_difficulty Brier 0.137(기준율 0.197, skill 0.303) · ECE 0.132 · AUROC 0.861(n 1287, 양성 346); navigation_difficulty Brier 0.144(기준율 0.177, skill 0.183) · ECE 0.118 · AUROC 0.794(n 1287, 양성 295); visual_difficulty Brier 0.140(기준율 0.138, skill -0.014) · ECE 0.038 · AUROC 0.553(n 1287, 양성 213); hesitation Brier 0.183(기준율 0.177, skill -0.038) · ECE 0.200 · AUROC 0.787(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.796(n 850), backs_recent 0.309 대 0.796(n 850), fixes_recent 0.316 대 0.796(n 850), condition_C2 0.285 대 0.666(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.934(n 850), backs_recent 0.314 대 0.934(n 850), fixes_recent 0.919 대 0.934(n 850), condition_C2 0.996 대 0.861(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.860(n 850), backs_recent 0.942 대 0.860(n 850), fixes_recent 0.322 대 0.860(n 850), condition_C2 0.322 대 0.794(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.538(n 850), backs_recent 0.464 대 0.538(n 850), fixes_recent 0.477 대 0.538(n 850), condition_C2 0.445 대 0.553(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.766(n 850), backs_recent 0.942 대 0.766(n 850), fixes_recent 0.322 대 0.766(n 850), condition_C2 0.322 대 0.787(n 1287)
- B:notouch: normal Brier 0.268(기준율 0.239, skill -0.122) · ECE 0.220 · AUROC 0.516(n 1287, 양성 507); touch_difficulty Brier 0.224(기준율 0.197, skill -0.142) · ECE 0.173 · AUROC 0.498(n 1287, 양성 346); navigation_difficulty Brier 0.164(기준율 0.177, skill 0.069) · ECE 0.102 · AUROC 0.623(n 1287, 양성 295); visual_difficulty Brier 0.138(기준율 0.138, skill -0.001) · ECE 0.053 · AUROC 0.618(n 1287, 양성 213); hesitation Brier 0.199(기준율 0.177, skill -0.128) · ECE 0.307 · AUROC 0.762(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.629(n 850), backs_recent 0.309 대 0.629(n 850), fixes_recent 0.316 대 0.629(n 850), condition_C2 0.285 대 0.516(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.579(n 850), backs_recent 0.314 대 0.579(n 850), fixes_recent 0.919 대 0.579(n 850), condition_C2 0.996 대 0.498(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.727(n 850), backs_recent 0.942 대 0.727(n 850), fixes_recent 0.322 대 0.727(n 850), condition_C2 0.322 대 0.623(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.633(n 850), backs_recent 0.464 대 0.633(n 850), fixes_recent 0.477 대 0.633(n 850), condition_C2 0.445 대 0.618(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.798(n 850), backs_recent 0.942 대 0.798(n 850), fixes_recent 0.322 대 0.798(n 850), condition_C2 0.322 대 0.762(n 1287)
- B:la_null: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.174 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.793(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.099) · ECE 0.195 · AUROC 0.761(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.793(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.761(n 1287)
- B:sit_dict: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.174 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.793(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.099) · ECE 0.195 · AUROC 0.761(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.793(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.761(n 1287)
- B:vision_summary: normal Brier 0.229(기준율 0.239, skill 0.042) · ECE 0.176 · AUROC 0.713(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.095 · AUROC 0.861(n 1287, 양성 346); navigation_difficulty Brier 0.138(기준율 0.177, skill 0.221) · ECE 0.094 · AUROC 0.817(n 1287, 양성 295); visual_difficulty Brier 0.135(기준율 0.138, skill 0.023) · ECE 0.042 · AUROC 0.613(n 1287, 양성 213); hesitation Brier 0.202(기준율 0.177, skill -0.145) · ECE 0.231 · AUROC 0.783(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.830(n 850), backs_recent 0.309 대 0.830(n 850), fixes_recent 0.316 대 0.830(n 850), condition_C2 0.285 대 0.713(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.940(n 850), backs_recent 0.314 대 0.940(n 850), fixes_recent 0.919 대 0.940(n 850), condition_C2 0.996 대 0.861(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.870(n 850), backs_recent 0.942 대 0.870(n 850), fixes_recent 0.322 대 0.870(n 850), condition_C2 0.322 대 0.817(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.621(n 850), backs_recent 0.464 대 0.621(n 850), fixes_recent 0.477 대 0.621(n 850), condition_C2 0.445 대 0.613(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.764(n 850), backs_recent 0.942 대 0.764(n 850), fixes_recent 0.322 대 0.764(n 850), condition_C2 0.322 대 0.783(n 1287)
- B:wording_nocrit: normal Brier 0.214(기준율 0.239, skill 0.103) · ECE 0.152 · AUROC 0.782(n 1287, 양성 507); touch_difficulty Brier 0.134(기준율 0.197, skill 0.317) · ECE 0.104 · AUROC 0.848(n 1287, 양성 346); navigation_difficulty Brier 0.152(기준율 0.177, skill 0.140) · ECE 0.068 · AUROC 0.787(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.007) · ECE 0.036 · AUROC 0.569(n 1287, 양성 213); hesitation Brier 0.209(기준율 0.177, skill -0.184) · ECE 0.225 · AUROC 0.736(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.921(n 850), backs_recent 0.309 대 0.921(n 850), fixes_recent 0.316 대 0.921(n 850), condition_C2 0.285 대 0.782(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.933(n 850), backs_recent 0.314 대 0.933(n 850), fixes_recent 0.919 대 0.933(n 850), condition_C2 0.996 대 0.848(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.845(n 850), backs_recent 0.942 대 0.845(n 850), fixes_recent 0.322 대 0.845(n 850), condition_C2 0.322 대 0.787(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.590(n 850), backs_recent 0.464 대 0.590(n 850), fixes_recent 0.477 대 0.590(n 850), condition_C2 0.445 대 0.569(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.714(n 850), backs_recent 0.942 대 0.714(n 850), fixes_recent 0.322 대 0.714(n 850), condition_C2 0.322 대 0.736(n 1287)
- B:perm_vision: normal Brier 0.233(기준율 0.239, skill 0.024) · ECE 0.173 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.359) · ECE 0.094 · AUROC 0.861(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.096 · AUROC 0.792(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.587(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.100) · ECE 0.195 · AUROC 0.758(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.818(n 850), backs_recent 0.309 대 0.818(n 850), fixes_recent 0.316 대 0.818(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.936(n 850), backs_recent 0.314 대 0.936(n 850), fixes_recent 0.919 대 0.936(n 850), condition_C2 0.996 대 0.861(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.845(n 850), backs_recent 0.942 대 0.845(n 850), fixes_recent 0.322 대 0.845(n 850), condition_C2 0.322 대 0.792(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.593(n 850), backs_recent 0.464 대 0.593(n 850), fixes_recent 0.477 대 0.593(n 850), condition_C2 0.445 대 0.587(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.758(n 1287)
- B:perm_touch: normal Brier 0.241(기준율 0.239, skill -0.008) · ECE 0.170 · AUROC 0.671(n 1287, 양성 507); touch_difficulty Brier 0.130(기준율 0.197, skill 0.339) · ECE 0.098 · AUROC 0.863(n 1287, 양성 346); navigation_difficulty Brier 0.150(기준율 0.177, skill 0.154) · ECE 0.079 · AUROC 0.747(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.010) · ECE 0.038 · AUROC 0.585(n 1287, 양성 213); hesitation Brier 0.196(기준율 0.177, skill -0.111) · ECE 0.193 · AUROC 0.743(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.756(n 850), backs_recent 0.309 대 0.756(n 850), fixes_recent 0.316 대 0.756(n 850), condition_C2 0.285 대 0.671(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.903(n 850), backs_recent 0.314 대 0.903(n 850), fixes_recent 0.919 대 0.903(n 850), condition_C2 0.996 대 0.863(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.763(n 850), backs_recent 0.942 대 0.763(n 850), fixes_recent 0.322 대 0.763(n 850), condition_C2 0.322 대 0.747(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.585(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.730(n 850), backs_recent 0.942 대 0.730(n 850), fixes_recent 0.322 대 0.730(n 850), condition_C2 0.322 대 0.743(n 1287)

### 규칙표 자체 질문(proposal_fits, 보조)

- B: Brier 0.392 · ECE 0.421 · AUROC 0.403(n 102, 양성 83)
- C: Brier 0.392 · ECE 0.421 · AUROC 0.403(n 102, 양성 83)
- D: Brier 0.392 · ECE 0.421 · AUROC 0.403(n 102, 양성 83)
- E: Brier 0.392 · ECE 0.421 · AUROC 0.403(n 102, 양성 83)
- B:novision: Brier 0.227 · ECE 0.326 · AUROC 0.505(n 102, 양성 83)
- B:notouch: Brier 0.415 · ECE 0.415 · AUROC 0.254(n 102, 양성 83)
- B:la_null: Brier 0.392 · ECE 0.421 · AUROC 0.403(n 102, 양성 83)
- B:sit_dict: Brier 0.392 · ECE 0.421 · AUROC 0.403(n 102, 양성 83)
- B:vision_summary: Brier 0.368 · ECE 0.403 · AUROC 0.374(n 102, 양성 83)
- B:wording_nocrit: Brier 0.389 · ECE 0.419 · AUROC 0.402(n 102, 양성 83)
- B:perm_vision: Brier 0.391 · ECE 0.408 · AUROC 0.411(n 102, 양성 83)
- B:perm_touch: Brier 0.453 · ECE 0.497 · AUROC 0.339(n 102, 양성 83)

### 다음 어려움 예측(D · E, 따로 셈)

- D: 예측 461(전체 1170, 95% 0.306~0.534); 관측 가능한 기준: B의 지금 최고 상태를 그대로 씀 664(전체 1170, 95% 0.462~0.646), 상수 {'touch_difficulty': 307, 'navigation_difficulty': 308, 'visual_difficulty': 183, 'hesitation': 308, 'none': 451}(전체 1170), 다수 범주(none) 451(전체 1170, 95% 0.189~0.519), 우연 0.266; 지금 창의 라벨을 쓰는 지속(오라클)과 같은 창에서 예측 439(전체 1146, 95% 0.299~0.519) 대 1136(전체 1146, 95% 0.988~0.996); 예측 분포 {'hesitation': 934, 'touch_difficulty': 164, 'navigation_difficulty': 19, 'none': 53}
- E: 예측 459(전체 1170, 95% 0.305~0.531); 관측 가능한 기준: B의 지금 최고 상태를 그대로 씀 664(전체 1170, 95% 0.462~0.646), 상수 {'touch_difficulty': 307, 'navigation_difficulty': 308, 'visual_difficulty': 183, 'hesitation': 308, 'none': 451}(전체 1170), 다수 범주(none) 451(전체 1170, 95% 0.189~0.519), 우연 0.266; 지금 창의 라벨을 쓰는 지속(오라클)과 같은 창에서 예측 437(전체 1146, 95% 0.298~0.517) 대 1136(전체 1146, 95% 0.988~0.996); 예측 분포 {'hesitation': 934, 'touch_difficulty': 162, 'navigation_difficulty': 19, 'none': 55}

### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 2977, 섞은 평균 2972.503, 범위 2961~2983
- 라벨을 섞음 · C selection (answered): 실제 95, 섞은 평균 97.264, 범위 86~105
- 라벨을 섞음 · C0 selection (answered): 실제 95, 섞은 평균 96.979, 범위 86~105
- 라벨을 섞음 · E selection (answered): 실제 95, 섞은 평균 97.264, 범위 86~105
- 라벨을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B hesitation Brier: 실제 0.194, 섞은 평균 0.201, 범위 0.198~0.204
- 라벨을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · C hesitation Brier: 실제 0.194, 섞은 평균 0.201, 범위 0.198~0.204
- 라벨을 섞음 · D normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · D touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · D navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · D visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · D hesitation Brier: 실제 0.194, 섞은 평균 0.201, 범위 0.198~0.204
- 라벨을 섞음 · E normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · E touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · E navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · E visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · E hesitation Brier: 실제 0.194, 섞은 평균 0.201, 범위 0.198~0.204
- 라벨을 섞음 · B:novision normal Brier: 실제 0.230, 섞은 평균 0.234, 범위 0.230~0.237
- 라벨을 섞음 · B:novision touch_difficulty Brier: 실제 0.137, 섞은 평균 0.139, 범위 0.137~0.141
- 라벨을 섞음 · B:novision navigation_difficulty Brier: 실제 0.144, 섞은 평균 0.149, 범위 0.147~0.152
- 라벨을 섞음 · B:novision visual_difficulty Brier: 실제 0.140, 섞은 평균 0.140, 범위 0.140~0.140
- 라벨을 섞음 · B:novision hesitation Brier: 실제 0.183, 섞은 평균 0.189, 범위 0.186~0.192
- 라벨을 섞음 · B:notouch normal Brier: 실제 0.268, 섞은 평균 0.273, 범위 0.269~0.276
- 라벨을 섞음 · B:notouch touch_difficulty Brier: 실제 0.224, 섞은 평균 0.224, 범위 0.224~0.225
- 라벨을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.164, 섞은 평균 0.167, 범위 0.165~0.170
- 라벨을 섞음 · B:notouch visual_difficulty Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 라벨을 섞음 · B:notouch hesitation Brier: 실제 0.199, 섞은 평균 0.205, 범위 0.202~0.207
- 라벨을 섞음 · B:la_null normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · B:la_null touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · B:la_null navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · B:la_null visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B:la_null hesitation Brier: 실제 0.194, 섞은 평균 0.201, 범위 0.198~0.204
- 라벨을 섞음 · B:sit_dict normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · B:sit_dict touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · B:sit_dict navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · B:sit_dict visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B:sit_dict hesitation Brier: 실제 0.194, 섞은 평균 0.201, 범위 0.198~0.204
- 라벨을 섞음 · B:vision_summary normal Brier: 실제 0.229, 섞은 평균 0.236, 범위 0.232~0.240
- 라벨을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.126, 섞은 평균 0.128, 범위 0.126~0.130
- 라벨을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.138, 섞은 평균 0.144, 범위 0.141~0.146
- 라벨을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.135, 섞은 평균 0.135, 범위 0.135~0.135
- 라벨을 섞음 · B:vision_summary hesitation Brier: 실제 0.202, 섞은 평균 0.210, 범위 0.207~0.214
- 라벨을 섞음 · B:wording_nocrit normal Brier: 실제 0.214, 섞은 평균 0.223, 범위 0.220~0.226
- 라벨을 섞음 · B:wording_nocrit touch_difficulty Brier: 실제 0.134, 섞은 평균 0.136, 범위 0.135~0.138
- 라벨을 섞음 · B:wording_nocrit navigation_difficulty Brier: 실제 0.152, 섞은 평균 0.156, 범위 0.153~0.158
- 라벨을 섞음 · B:wording_nocrit visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B:wording_nocrit hesitation Brier: 실제 0.209, 섞은 평균 0.218, 범위 0.215~0.221
- 라벨을 섞음 · B:perm_vision normal Brier: 실제 0.233, 섞은 평균 0.241, 범위 0.236~0.245
- 라벨을 섞음 · B:perm_vision touch_difficulty Brier: 실제 0.126, 섞은 평균 0.128, 범위 0.126~0.130
- 라벨을 섞음 · B:perm_vision navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · B:perm_vision visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B:perm_vision hesitation Brier: 실제 0.194, 섞은 평균 0.202, 범위 0.198~0.205
- 라벨을 섞음 · B:perm_touch normal Brier: 실제 0.241, 섞은 평균 0.244, 범위 0.240~0.248
- 라벨을 섞음 · B:perm_touch touch_difficulty Brier: 실제 0.130, 섞은 평균 0.130, 범위 0.128~0.132
- 라벨을 섞음 · B:perm_touch navigation_difficulty Brier: 실제 0.150, 섞은 평균 0.151, 범위 0.148~0.154
- 라벨을 섞음 · B:perm_touch visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B:perm_touch hesitation Brier: 실제 0.196, 섞은 평균 0.201, 범위 0.198~0.204
- 답을 섞음 · C selection (answered): 실제 95, 섞은 평균 95.491, 범위 95~96
- 답을 섞음 · C0 selection (answered): 실제 95, 섞은 평균 95.496, 범위 95~96
- 답을 섞음 · E selection (answered): 실제 95, 섞은 평균 95.499, 범위 95~96
- 답을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.244, 범위 0.238~0.248
- 답을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.149~0.156
- 답을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B hesitation Brier: 실제 0.194, 섞은 평균 0.206, 범위 0.202~0.210
- 답을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.244, 범위 0.238~0.248
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.149~0.156
- 답을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · C hesitation Brier: 실제 0.194, 섞은 평균 0.205, 범위 0.201~0.209
- 답을 섞음 · D normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.239~0.248
- 답을 섞음 · D touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · D navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.149~0.156
- 답을 섞음 · D visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · D hesitation Brier: 실제 0.194, 섞은 평균 0.205, 범위 0.201~0.209
- 답을 섞음 · E normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.239~0.248
- 답을 섞음 · E touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · E navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.149~0.156
- 답을 섞음 · E visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · E hesitation Brier: 실제 0.194, 섞은 평균 0.205, 범위 0.202~0.209
- 답을 섞음 · B:novision normal Brier: 실제 0.230, 섞은 평균 0.235, 범위 0.231~0.238
- 답을 섞음 · B:novision touch_difficulty Brier: 실제 0.137, 섞은 평균 0.139, 범위 0.138~0.141
- 답을 섞음 · B:novision navigation_difficulty Brier: 실제 0.144, 섞은 평균 0.154, 범위 0.150~0.158
- 답을 섞음 · B:novision visual_difficulty Brier: 실제 0.140, 섞은 평균 0.140, 범위 0.140~0.140
- 답을 섞음 · B:novision hesitation Brier: 실제 0.183, 섞은 평균 0.193, 범위 0.190~0.196
- 답을 섞음 · B:notouch normal Brier: 실제 0.268, 섞은 평균 0.274, 범위 0.272~0.277
- 답을 섞음 · B:notouch touch_difficulty Brier: 실제 0.224, 섞은 평균 0.225, 범위 0.224~0.225
- 답을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.164, 섞은 평균 0.170, 범위 0.168~0.172
- 답을 섞음 · B:notouch visual_difficulty Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 답을 섞음 · B:notouch hesitation Brier: 실제 0.199, 섞은 평균 0.207, 범위 0.205~0.211
- 답을 섞음 · B:la_null normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.238~0.248
- 답을 섞음 · B:la_null touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.132
- 답을 섞음 · B:la_null navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.149~0.156
- 답을 섞음 · B:la_null visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B:la_null hesitation Brier: 실제 0.194, 섞은 평균 0.206, 범위 0.201~0.209
- 답을 섞음 · B:sit_dict normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.239~0.248
- 답을 섞음 · B:sit_dict touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.132
- 답을 섞음 · B:sit_dict navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.149~0.156
- 답을 섞음 · B:sit_dict visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B:sit_dict hesitation Brier: 실제 0.194, 섞은 평균 0.205, 범위 0.201~0.210
- 답을 섞음 · B:vision_summary normal Brier: 실제 0.229, 섞은 평균 0.239, 범위 0.234~0.244
- 답을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 답을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.138, 섞은 평균 0.149, 범위 0.145~0.153
- 답을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.135, 섞은 평균 0.135, 범위 0.135~0.135
- 답을 섞음 · B:vision_summary hesitation Brier: 실제 0.202, 섞은 평균 0.215, 범위 0.212~0.218
- 답을 섞음 · B:wording_nocrit normal Brier: 실제 0.214, 섞은 평균 0.227, 범위 0.223~0.230
- 답을 섞음 · B:wording_nocrit touch_difficulty Brier: 실제 0.134, 섞은 평균 0.137, 범위 0.134~0.139
- 답을 섞음 · B:wording_nocrit navigation_difficulty Brier: 실제 0.152, 섞은 평균 0.159, 범위 0.157~0.162
- 답을 섞음 · B:wording_nocrit visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B:wording_nocrit hesitation Brier: 실제 0.209, 섞은 평균 0.223, 범위 0.217~0.227
- 답을 섞음 · B:perm_vision normal Brier: 실제 0.233, 섞은 평균 0.244, 범위 0.240~0.248
- 답을 섞음 · B:perm_vision touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 답을 섞음 · B:perm_vision navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.148~0.156
- 답을 섞음 · B:perm_vision visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B:perm_vision hesitation Brier: 실제 0.194, 섞은 평균 0.206, 범위 0.202~0.210
- 답을 섞음 · B:perm_touch normal Brier: 실제 0.241, 섞은 평균 0.244, 범위 0.238~0.249
- 답을 섞음 · B:perm_touch touch_difficulty Brier: 실제 0.130, 섞은 평균 0.130, 범위 0.127~0.133
- 답을 섞음 · B:perm_touch navigation_difficulty Brier: 실제 0.150, 섞은 평균 0.152, 범위 0.148~0.155
- 답을 섞음 · B:perm_touch visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B:perm_touch hesitation Brier: 실제 0.196, 섞은 평균 0.202, 범위 0.199~0.206

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 2977, 섞은 평균 2923.200, 범위 2909~2943
- 라벨을 섞음 · C selection (answered): 실제 95, 섞은 평균 67.533, 범위 55~81
- 라벨을 섞음 · C0 selection (answered): 실제 95, 섞은 평균 68.408, 범위 57~82
- 라벨을 섞음 · E selection (answered): 실제 95, 섞은 평균 67.533, 범위 55~81
- 라벨을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.320
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.202~0.233
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.151~0.168
- 라벨을 섞음 · B hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.227~0.253
- 라벨을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.320
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.202~0.233
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.151~0.168
- 라벨을 섞음 · C hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.227~0.253
- 라벨을 섞음 · D normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.320
- 라벨을 섞음 · D touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.202~0.233
- 라벨을 섞음 · D navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · D visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.151~0.168
- 라벨을 섞음 · D hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.227~0.253
- 라벨을 섞음 · E normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.320
- 라벨을 섞음 · E touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.202~0.233
- 라벨을 섞음 · E navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · E visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.151~0.168
- 라벨을 섞음 · E hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.227~0.253
- 라벨을 섞음 · B:novision normal Brier: 실제 0.230, 섞은 평균 0.285, 범위 0.269~0.301
- 라벨을 섞음 · B:novision touch_difficulty Brier: 실제 0.137, 섞은 평균 0.207, 범위 0.193~0.222
- 라벨을 섞음 · B:novision navigation_difficulty Brier: 실제 0.144, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · B:novision visual_difficulty Brier: 실제 0.140, 섞은 평균 0.160, 범위 0.151~0.168
- 라벨을 섞음 · B:novision hesitation Brier: 실제 0.183, 섞은 평균 0.223, 범위 0.214~0.234
- 라벨을 섞음 · B:notouch normal Brier: 실제 0.268, 섞은 평균 0.271, 범위 0.263~0.279
- 라벨을 섞음 · B:notouch touch_difficulty Brier: 실제 0.224, 섞은 평균 0.205, 범위 0.195~0.214
- 라벨을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.164, 섞은 평균 0.174, 범위 0.166~0.182
- 라벨을 섞음 · B:notouch visual_difficulty Brier: 실제 0.138, 섞은 평균 0.159, 범위 0.150~0.167
- 라벨을 섞음 · B:notouch hesitation Brier: 실제 0.199, 섞은 평균 0.240, 범위 0.234~0.246
- 라벨을 섞음 · B:la_null normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.320
- 라벨을 섞음 · B:la_null touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.202~0.233
- 라벨을 섞음 · B:la_null navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · B:la_null visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.151~0.168
- 라벨을 섞음 · B:la_null hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.227~0.253
- 라벨을 섞음 · B:sit_dict normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.320
- 라벨을 섞음 · B:sit_dict touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.202~0.233
- 라벨을 섞음 · B:sit_dict navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · B:sit_dict visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.151~0.168
- 라벨을 섞음 · B:sit_dict hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.227~0.253
- 라벨을 섞음 · B:vision_summary normal Brier: 실제 0.229, 섞은 평균 0.301, 범위 0.285~0.319
- 라벨을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.126, 섞은 평균 0.215, 범위 0.200~0.231
- 라벨을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.138, 섞은 평균 0.182, 범위 0.172~0.192
- 라벨을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.135, 섞은 평균 0.160, 범위 0.151~0.168
- 라벨을 섞음 · B:vision_summary hesitation Brier: 실제 0.202, 섞은 평균 0.253, 범위 0.242~0.266
- 라벨을 섞음 · B:wording_nocrit normal Brier: 실제 0.214, 섞은 평균 0.283, 범위 0.271~0.296
- 라벨을 섞음 · B:wording_nocrit touch_difficulty Brier: 실제 0.134, 섞은 평균 0.209, 범위 0.196~0.223
- 라벨을 섞음 · B:wording_nocrit navigation_difficulty Brier: 실제 0.152, 섞은 평균 0.176, 범위 0.168~0.185
- 라벨을 섞음 · B:wording_nocrit visual_difficulty Brier: 실제 0.137, 섞은 평균 0.159, 범위 0.150~0.166
- 라벨을 섞음 · B:wording_nocrit hesitation Brier: 실제 0.209, 섞은 평균 0.252, 범위 0.241~0.266
- 라벨을 섞음 · B:perm_vision normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.320
- 라벨을 섞음 · B:perm_vision touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.203~0.234
- 라벨을 섞음 · B:perm_vision navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · B:perm_vision visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.150~0.168
- 라벨을 섞음 · B:perm_vision hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.228~0.252
- 라벨을 섞음 · B:perm_touch normal Brier: 실제 0.241, 섞은 평균 0.302, 범위 0.286~0.319
- 라벨을 섞음 · B:perm_touch touch_difficulty Brier: 실제 0.130, 섞은 평균 0.216, 범위 0.200~0.232
- 라벨을 섞음 · B:perm_touch navigation_difficulty Brier: 실제 0.150, 섞은 평균 0.181, 범위 0.170~0.190
- 라벨을 섞음 · B:perm_touch visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.151~0.167
- 라벨을 섞음 · B:perm_touch hesitation Brier: 실제 0.196, 섞은 평균 0.237, 범위 0.224~0.248
- 답을 섞음 · C selection (answered): 실제 95, 섞은 평균 104.323, 범위 98~112
- 답을 섞음 · C0 selection (answered): 실제 95, 섞은 평균 104.667, 범위 98~112
- 답을 섞음 · E selection (answered): 실제 95, 섞은 평균 104.295, 범위 98~111
- 답을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.307, 범위 0.285~0.330
- 답을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.217~0.244
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.187, 범위 0.180~0.194
- 답을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.139~0.146
- 답을 섞음 · B hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.229~0.255
- 답을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.307, 범위 0.291~0.324
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.218~0.242
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.179~0.193
- 답을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.139~0.146
- 답을 섞음 · C hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.229~0.257
- 답을 섞음 · D normal Brier: 실제 0.233, 섞은 평균 0.306, 범위 0.287~0.324
- 답을 섞음 · D touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.219~0.242
- 답을 섞음 · D navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.180~0.194
- 답을 섞음 · D visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.138~0.146
- 답을 섞음 · D hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.228~0.255
- 답을 섞음 · E normal Brier: 실제 0.233, 섞은 평균 0.306, 범위 0.287~0.326
- 답을 섞음 · E touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.218~0.244
- 답을 섞음 · E navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.187, 범위 0.179~0.195
- 답을 섞음 · E visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.139~0.146
- 답을 섞음 · E hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.227~0.256
- 답을 섞음 · B:novision normal Brier: 실제 0.230, 섞은 평균 0.290, 범위 0.272~0.307
- 답을 섞음 · B:novision touch_difficulty Brier: 실제 0.137, 섞은 평균 0.223, 범위 0.212~0.234
- 답을 섞음 · B:novision navigation_difficulty Brier: 실제 0.144, 섞은 평균 0.186, 범위 0.179~0.193
- 답을 섞음 · B:novision visual_difficulty Brier: 실제 0.140, 섞은 평균 0.144, 범위 0.139~0.148
- 답을 섞음 · B:novision hesitation Brier: 실제 0.183, 섞은 평균 0.225, 범위 0.214~0.235
- 답을 섞음 · B:notouch normal Brier: 실제 0.268, 섞은 평균 0.269, 범위 0.260~0.278
- 답을 섞음 · B:notouch touch_difficulty Brier: 실제 0.224, 섞은 평균 0.227, 범위 0.226~0.228
- 답을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.164, 섞은 평균 0.179, 범위 0.176~0.183
- 답을 섞음 · B:notouch visual_difficulty Brier: 실제 0.138, 섞은 평균 0.141, 범위 0.139~0.142
- 답을 섞음 · B:notouch hesitation Brier: 실제 0.199, 섞은 평균 0.231, 범위 0.224~0.238
- 답을 섞음 · B:la_null normal Brier: 실제 0.233, 섞은 평균 0.306, 범위 0.289~0.325
- 답을 섞음 · B:la_null touch_difficulty Brier: 실제 0.126, 섞은 평균 0.230, 범위 0.217~0.242
- 답을 섞음 · B:la_null navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.180~0.195
- 답을 섞음 · B:la_null visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.138~0.146
- 답을 섞음 · B:la_null hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.224~0.258
- 답을 섞음 · B:sit_dict normal Brier: 실제 0.233, 섞은 평균 0.306, 범위 0.288~0.325
- 답을 섞음 · B:sit_dict touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.216~0.243
- 답을 섞음 · B:sit_dict navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.179~0.193
- 답을 섞음 · B:sit_dict visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.139~0.146
- 답을 섞음 · B:sit_dict hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.225~0.254
- 답을 섞음 · B:vision_summary normal Brier: 실제 0.229, 섞은 평균 0.308, 범위 0.291~0.327
- 답을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.126, 섞은 평균 0.228, 범위 0.215~0.241
- 답을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.138, 섞은 평균 0.187, 범위 0.179~0.194
- 답을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.135, 섞은 평균 0.143, 범위 0.139~0.147
- 답을 섞음 · B:vision_summary hesitation Brier: 실제 0.202, 섞은 평균 0.253, 범위 0.241~0.266
- 답을 섞음 · B:wording_nocrit normal Brier: 실제 0.214, 섞은 평균 0.290, 범위 0.279~0.302
- 답을 섞음 · B:wording_nocrit touch_difficulty Brier: 실제 0.134, 섞은 평균 0.225, 범위 0.214~0.235
- 답을 섞음 · B:wording_nocrit navigation_difficulty Brier: 실제 0.152, 섞은 평균 0.182, 범위 0.176~0.187
- 답을 섞음 · B:wording_nocrit visual_difficulty Brier: 실제 0.137, 섞은 평균 0.141, 범위 0.138~0.144
- 답을 섞음 · B:wording_nocrit hesitation Brier: 실제 0.209, 섞은 평균 0.257, 범위 0.243~0.272
- 답을 섞음 · B:perm_vision normal Brier: 실제 0.233, 섞은 평균 0.307, 범위 0.286~0.327
- 답을 섞음 · B:perm_vision touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.220~0.244
- 답을 섞음 · B:perm_vision navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.180~0.194
- 답을 섞음 · B:perm_vision visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.138~0.147
- 답을 섞음 · B:perm_vision hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.227~0.255
- 답을 섞음 · B:perm_touch normal Brier: 실제 0.241, 섞은 평균 0.307, 범위 0.289~0.325
- 답을 섞음 · B:perm_touch touch_difficulty Brier: 실제 0.130, 섞은 평균 0.231, 범위 0.218~0.245
- 답을 섞음 · B:perm_touch navigation_difficulty Brier: 실제 0.150, 섞은 평균 0.186, 범위 0.178~0.193
- 답을 섞음 · B:perm_touch visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.138~0.146
- 답을 섞음 · B:perm_touch hesitation Brier: 실제 0.196, 섞은 평균 0.240, 범위 0.225~0.254
