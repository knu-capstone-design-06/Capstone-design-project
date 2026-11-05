# E5 지표: `vision_only_round3`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `<workspace>/4_vision/eval_ab_2026-11-04/judgment_labels_v4.csv`(time)
- 라벨 상태: Claude(Opus 서브에이전트) 2026-11-05; v4 = 결정 227 레드팀 3회차 반영(치명 1 · 중요 2~5는 main 결정); v2 · v3 · v4 고침은 v1 결과를 본 검토 뒤에 했음

## 규칙표(조건 A)

- 창 556개(영상 35개, 테이크 35개, 세션 35개), 측정 가능 447개
- 기록의 상황 태그: {'unknown': 556}
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
| C | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| | | | | | support_choice | 447 | 447 | 0 | 0 | 0 | 0 | 0 | 0 | - · - · - | 0 |
| C0 | 556 | 447 | 447 | {'not measurable': 109} | support_choice | 447 | 447 | 0 | 0 | 0 | 0 | 0 | 0 | - · - · - | 0 |
| D | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| | | | | | next_difficulty | 447 | 24 | 423 | 423 | 0 | 33 | 390 | 0 | 203.2 · 448.5 · 777.6 | 46363 |
| E | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| | | | | | support_choice | 447 | 447 | 0 | 0 | 0 | 0 | 0 | 0 | - · - · - | 0 |
| | | | | | next_difficulty | 447 | 24 | 423 | 423 | 0 | 0 | 423 | 0 | - · - · - | 0 |
| B:novision | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| B:notouch | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| B:la_null | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| B:sit_dict | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| B:vision_summary | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 52 | 395 | 0 | 194.7 · 234.9 · 257.1 | 41174 |
| B:wording_nocrit | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| B:perm_vision | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |
| B:perm_touch | 556 | 447 | 447 | {'not measurable': 109} | state_scores | 447 | 0 | 447 | 447 | 0 | 0 | 447 | 0 | - · - · - | 0 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- B: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- C: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 0(전체 447); 사슬 전체 지연 p50 - · p95 - ms
- C0: API 호출 0번, 캐시 답 0개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 0(전체 447); 사슬 전체 지연 p50 0.0 · p95 0.0 ms
- D: API 호출 33번, 캐시 답 837개, 시도한 창마다 호출 0.07번; 사슬 전체 지연 p50 - · p95 - ms
- E: API 호출 0번, 캐시 답 870개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 0(전체 447); 사슬 전체 지연 p50 - · p95 - ms
- B:novision: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:notouch: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:la_null: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:sit_dict: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:vision_summary: API 호출 52번, 캐시 답 395개, 시도한 창마다 호출 0.12번; 사슬 전체 지연 p50 194.7 · p95 234.9 ms
- B:wording_nocrit: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:perm_vision: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- B:perm_touch: API 호출 0번, 캐시 답 447개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms

## 같은 요청 점검(실행 동작)

- B:novision vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 0개
- B:notouch vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 0개
- B:la_null vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 447개
- B:sit_dict vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 447개
- B:vision_summary vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 0개
- B:wording_nocrit vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 0개
- B:perm_vision vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 447개
- B:perm_touch vs B, 단계 state_scores: 짝 창 447개, 요청이 같은 창 447개
- C0 vs C, 단계 support_choice: 짝 창 0개, 요청이 같은 창 0개
- C vs B (state_scores), 단계 state_scores: 짝 창 447개, 요청이 같은 창 447개
- D vs B (state_scores), 단계 state_scores: 짝 창 447개, 요청이 같은 창 447개
- E vs B (state_scores), 단계 state_scores: 짝 창 447개, 요청이 같은 창 447개

## 같은 입력 반복(요청마다 3번)

- B / state_scores: 요청 1개(모두 답 1개); 선택 질문 없음; 확률 폭 평균 {'touch_difficulty': '0.000', 'navigation_difficulty': '0.010', 'visual_difficulty': '0.010', 'hesitation': '0.010', 'normal': '0.020'}
- D / next_difficulty: 요청 121개(모두 답 121개); next_difficulty: 한 가지로 같음 121(전체 121, 95% 0.969~1.000), 바뀐 몫 0.000, Fleiss κ -, 짝 일치 평균 1.000(최소 1.000); 확률 폭 평균 {'next_difficulty': '0.008'}
- B:novision / state_scores: 요청 1개(모두 답 1개); 선택 질문 없음; 확률 폭 평균 {'touch_difficulty': '0.020', 'navigation_difficulty': '0.020', 'visual_difficulty': '0.000', 'hesitation': '0.010', 'normal': '0.010'}
- B:notouch / state_scores: 요청 1개(모두 답 1개); 선택 질문 없음; 확률 폭 평균 {'touch_difficulty': '0.000', 'navigation_difficulty': '0.010', 'visual_difficulty': '0.000', 'hesitation': '0.010', 'normal': '0.010'}
- B:vision_summary / state_scores: 요청 60개(모두 답 60개); 선택 질문 없음; 확률 폭 평균 {'touch_difficulty': '0.008', 'navigation_difficulty': '0.009', 'visual_difficulty': '0.010', 'hesitation': '0.015', 'normal': '0.018'}
- B:wording_nocrit / state_scores: 요청 1개(모두 답 1개); 선택 질문 없음; 확률 폭 평균 {'touch_difficulty': '0.010', 'navigation_difficulty': '0.020', 'visual_difficulty': '0.020', 'hesitation': '0.020', 'normal': '0.020'}

## 답 요약

| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| B | state_scores | hesitation | 447 | 0.330 | 0.330 | 0.330 |
| B | state_scores | navigation_difficulty | 447 | 0.220 | 0.220 | 0.220 |
| B | state_scores | normal | 447 | 0.420 | 0.420 | 0.420 |
| B | state_scores | touch_difficulty | 447 | 0.160 | 0.160 | 0.160 |
| B | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |
| C | state_scores | hesitation | 447 | 0.330 | 0.330 | 0.330 |
| C | state_scores | navigation_difficulty | 447 | 0.220 | 0.220 | 0.220 |
| C | state_scores | normal | 447 | 0.420 | 0.420 | 0.420 |
| C | state_scores | touch_difficulty | 447 | 0.160 | 0.160 | 0.160 |
| C | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |
| D | state_scores | hesitation | 447 | 0.330 | 0.330 | 0.330 |
| D | state_scores | navigation_difficulty | 447 | 0.220 | 0.220 | 0.220 |
| D | state_scores | normal | 447 | 0.420 | 0.420 | 0.420 |
| D | state_scores | touch_difficulty | 447 | 0.160 | 0.160 | 0.160 |
| D | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |
| D | next_difficulty | next_difficulty(choice) | 423 | {'hesitation': 423} | conf 평균 0.956 | |
| E | state_scores | hesitation | 447 | 0.330 | 0.330 | 0.330 |
| E | state_scores | navigation_difficulty | 447 | 0.220 | 0.220 | 0.220 |
| E | state_scores | normal | 447 | 0.420 | 0.420 | 0.420 |
| E | state_scores | touch_difficulty | 447 | 0.160 | 0.160 | 0.160 |
| E | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |
| E | next_difficulty | next_difficulty(choice) | 423 | {'hesitation': 423} | conf 평균 0.956 | |
| B:novision | state_scores | hesitation | 447 | 0.360 | 0.360 | 0.360 |
| B:novision | state_scores | navigation_difficulty | 447 | 0.270 | 0.270 | 0.270 |
| B:novision | state_scores | normal | 447 | 0.380 | 0.380 | 0.380 |
| B:novision | state_scores | touch_difficulty | 447 | 0.210 | 0.210 | 0.210 |
| B:novision | state_scores | visual_difficulty | 447 | 0.230 | 0.230 | 0.230 |
| B:notouch | state_scores | hesitation | 447 | 0.340 | 0.340 | 0.340 |
| B:notouch | state_scores | navigation_difficulty | 447 | 0.230 | 0.230 | 0.230 |
| B:notouch | state_scores | normal | 447 | 0.350 | 0.350 | 0.350 |
| B:notouch | state_scores | touch_difficulty | 447 | 0.100 | 0.100 | 0.100 |
| B:notouch | state_scores | visual_difficulty | 447 | 0.190 | 0.190 | 0.190 |
| B:la_null | state_scores | hesitation | 447 | 0.330 | 0.330 | 0.330 |
| B:la_null | state_scores | navigation_difficulty | 447 | 0.220 | 0.220 | 0.220 |
| B:la_null | state_scores | normal | 447 | 0.420 | 0.420 | 0.420 |
| B:la_null | state_scores | touch_difficulty | 447 | 0.160 | 0.160 | 0.160 |
| B:la_null | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |
| B:sit_dict | state_scores | hesitation | 447 | 0.330 | 0.330 | 0.330 |
| B:sit_dict | state_scores | navigation_difficulty | 447 | 0.220 | 0.220 | 0.220 |
| B:sit_dict | state_scores | normal | 447 | 0.420 | 0.420 | 0.420 |
| B:sit_dict | state_scores | touch_difficulty | 447 | 0.160 | 0.160 | 0.160 |
| B:sit_dict | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |
| B:vision_summary | state_scores | hesitation | 447 | 0.371 | 0.350 | 0.430 |
| B:vision_summary | state_scores | navigation_difficulty | 447 | 0.199 | 0.170 | 0.250 |
| B:vision_summary | state_scores | normal | 447 | 0.438 | 0.380 | 0.500 |
| B:vision_summary | state_scores | touch_difficulty | 447 | 0.178 | 0.150 | 0.210 |
| B:vision_summary | state_scores | visual_difficulty | 447 | 0.172 | 0.140 | 0.300 |
| B:wording_nocrit | state_scores | hesitation | 447 | 0.430 | 0.430 | 0.430 |
| B:wording_nocrit | state_scores | navigation_difficulty | 447 | 0.260 | 0.260 | 0.260 |
| B:wording_nocrit | state_scores | normal | 447 | 0.470 | 0.470 | 0.470 |
| B:wording_nocrit | state_scores | touch_difficulty | 447 | 0.170 | 0.170 | 0.170 |
| B:wording_nocrit | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |
| B:perm_vision | state_scores | hesitation | 447 | 0.330 | 0.330 | 0.330 |
| B:perm_vision | state_scores | navigation_difficulty | 447 | 0.220 | 0.220 | 0.220 |
| B:perm_vision | state_scores | normal | 447 | 0.420 | 0.420 | 0.420 |
| B:perm_vision | state_scores | touch_difficulty | 447 | 0.160 | 0.160 | 0.160 |
| B:perm_vision | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |
| B:perm_touch | state_scores | hesitation | 447 | 0.330 | 0.330 | 0.330 |
| B:perm_touch | state_scores | navigation_difficulty | 447 | 0.220 | 0.220 | 0.220 |
| B:perm_touch | state_scores | normal | 447 | 0.420 | 0.420 | 0.420 |
| B:perm_touch | state_scores | touch_difficulty | 447 | 0.160 | 0.160 | 0.160 |
| B:perm_touch | state_scores | visual_difficulty | 447 | 0.200 | 0.200 | 0.200 |

## 짝 비교(같은 창)

- B:novision vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.030, 평균 |차| 0.030, 최대 |차| 0.030
  - navigation_difficulty: n 447, 평균 차 0.050, 평균 |차| 0.050, 최대 |차| 0.050
  - normal: n 447, 평균 차 -0.040, 평균 |차| 0.040, 최대 |차| 0.040
  - touch_difficulty: n 447, 평균 차 0.050, 평균 |차| 0.050, 최대 |차| 0.050
  - visual_difficulty: n 447, 평균 차 0.030, 평균 |차| 0.030, 최대 |차| 0.030
- B:notouch vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.010, 평균 |차| 0.010, 최대 |차| 0.010
  - navigation_difficulty: n 447, 평균 차 0.010, 평균 |차| 0.010, 최대 |차| 0.010
  - normal: n 447, 평균 차 -0.070, 평균 |차| 0.070, 최대 |차| 0.070
  - touch_difficulty: n 447, 평균 차 -0.060, 평균 |차| 0.060, 최대 |차| 0.060
  - visual_difficulty: n 447, 평균 차 -0.010, 평균 |차| 0.010, 최대 |차| 0.010
- B:la_null vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- B:sit_dict vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- B:vision_summary vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 11(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.041, 평균 |차| 0.041, 최대 |차| 0.100
  - navigation_difficulty: n 447, 평균 차 -0.021, 평균 |차| 0.021, 최대 |차| 0.050
  - normal: n 447, 평균 차 0.018, 평균 |차| 0.021, 최대 |차| 0.080
  - touch_difficulty: n 447, 평균 차 0.018, 평균 |차| 0.018, 최대 |차| 0.050
  - visual_difficulty: n 447, 평균 차 -0.028, 평균 |차| 0.040, 최대 |차| 0.100
- B:wording_nocrit vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.100, 평균 |차| 0.100, 최대 |차| 0.100
  - navigation_difficulty: n 447, 평균 차 0.040, 평균 |차| 0.040, 최대 |차| 0.040
  - normal: n 447, 평균 차 0.050, 평균 |차| 0.050, 최대 |차| 0.050
  - touch_difficulty: n 447, 평균 차 0.010, 평균 |차| 0.010, 최대 |차| 0.010
  - visual_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- B:perm_vision vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- B:perm_touch vs B, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- C0 vs C, support_choice: 가장 큰 상태 점수가 바뀐 창 0(전체 0); 고른 답이 바뀐 창 없음
- C vs B (state_scores), state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- D vs B (state_scores), state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- E vs B (state_scores), state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 447); 고른 답이 바뀐 창 없음
  - hesitation: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 447, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000

## 라벨

- 라벨이 붙은 창 556개(안 붙은 창 0개), 수준 {'action': 556}, 맞춘 방법 {'inside': 556}
- 구간 분류별 창: {'no_user': 15, 'wait_only': 292, 'designated': 115, 'time_stop': 134}
- 세션 35개 가운데 라벨 행이 둘 이상인 세션 8개
- 상태 대응(STATE_PROXY)이 있는 창 190개: {'normal': 136, 'hesitation,navigation_difficulty': 15, 'visual_difficulty': 39}
- 창의 태그 | 정답 태그(window truth: the segment's truth tag when a GT behaviour second lies in (t - window_s, t], else none (E3 run_eval.py window_truth)): {'none | none': 452, 'none | looking_around': 25, 'none | consulting_companion': 47, 'none | looking_back_with_people_behind': 32}
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
- C: 선택지(the sent question's options (a support besides none))가 있는 창 0개, 상태 {}
  - 첫 순서: 답한 창에서 허용 안 0(전체 0)(우연 -; 같은 창의 A 0(전체 0)); 규칙표로 채운 전체 556(전체 556, 95% 1.000~1.000); 지정 지원과 같음 0(전체 0)(우연 -); 고른 지원 확률 Brier - · ECE - · AUROC -(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {}; 허용 안 0(전체 0)(우연 -); 같은 창의 A 0(전체 0); 순서 일관성 0(전체 0)(무작위 선택자 -, 합의 · 허용 -)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 0/4/0/22(A는 0/4/0/22); 거짓 경보 0(전체 22, 95% 0.000~0.149), 놓친 도움 4(전체 4, 95% 0.510~1.000), 제안 정밀도 0(전체 0); 허용 밖 결정의 분류 {'decision_errors': 0, 'of_windows': 556, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 0, 'observed_tag_unknown': 0, 'reference_missing': 0}
  - 다음 창 적용: 짝 0개에서 C 0, 한 창 늦춘 A 0, 같은 창 A 0; 한 창 늦춘 A 전체 521(전체 521)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 0(전체 4, 95% 0.000~0.490); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 4, 95% 0.000~0.490)(보이는 허용 형태만 0(전체 4), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 4, 'TP': 0, 'FN': 4, 'designated_delivery': {'k': 0, 'n': 4}}}; 시작 시각 전에 연 도움 0구간; 옛 규칙 TP/FN 0/4, 지정 지원 {'k': 0, 'n': 4}
- C0: 선택지(the sent question's options (a support besides none))가 있는 창 0개, 상태 {}
  - 첫 순서: 답한 창에서 허용 안 0(전체 0)(우연 -; 같은 창의 A 0(전체 0)); 규칙표로 채운 전체 556(전체 556, 95% 1.000~1.000); 지정 지원과 같음 0(전체 0)(우연 -); 고른 지원 확률 Brier - · ECE - · AUROC -(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {}; 허용 안 0(전체 0)(우연 -); 같은 창의 A 0(전체 0); 순서 일관성 0(전체 0)(무작위 선택자 -, 합의 · 허용 -)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 0/4/0/22(A는 0/4/0/22); 거짓 경보 0(전체 22, 95% 0.000~0.149), 놓친 도움 4(전체 4, 95% 0.510~1.000), 제안 정밀도 0(전체 0); 허용 밖 결정의 분류 {'decision_errors': 0, 'of_windows': 556, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 0, 'observed_tag_unknown': 0, 'reference_missing': 0}
  - 다음 창 적용: 짝 0개에서 C 0, 한 창 늦춘 A 0, 같은 창 A 0; 한 창 늦춘 A 전체 521(전체 521)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 0(전체 4, 95% 0.000~0.490); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 4, 95% 0.000~0.490)(보이는 허용 형태만 0(전체 4), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 4, 'TP': 0, 'FN': 4, 'designated_delivery': {'k': 0, 'n': 4}}}; 시작 시각 전에 연 도움 0구간; 옛 규칙 TP/FN 0/4, 지정 지원 {'k': 0, 'n': 4}
- E: 선택지(the sent question's options (a support besides none))가 있는 창 0개, 상태 {}
  - 첫 순서: 답한 창에서 허용 안 0(전체 0)(우연 -; 같은 창의 A 0(전체 0)); 규칙표로 채운 전체 556(전체 556, 95% 1.000~1.000); 지정 지원과 같음 0(전체 0)(우연 -); 고른 지원 확률 Brier - · ECE - · AUROC -(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {}; 허용 안 0(전체 0)(우연 -); 같은 창의 A 0(전체 0); 순서 일관성 0(전체 0)(무작위 선택자 -, 합의 · 허용 -)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 0/4/0/22(A는 0/4/0/22); 거짓 경보 0(전체 22, 95% 0.000~0.149), 놓친 도움 4(전체 4, 95% 0.510~1.000), 제안 정밀도 0(전체 0); 허용 밖 결정의 분류 {'decision_errors': 0, 'of_windows': 556, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 0, 'observed_tag_unknown': 0, 'reference_missing': 0}
  - 다음 창 적용: 짝 0개에서 C 0, 한 창 늦춘 A 0, 같은 창 A 0; 한 창 늦춘 A 전체 521(전체 521)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 0(전체 4, 95% 0.000~0.490); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 4, 95% 0.000~0.490)(보이는 허용 형태만 0(전체 4), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 4, 'TP': 0, 'FN': 4, 'designated_delivery': {'k': 0, 'n': 4}}}; 시작 시각 전에 연 도움 0구간; 옛 규칙 TP/FN 0/4, 지정 지원 {'k': 0, 'n': 4}

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)

- B: normal Brier 0.298(기준율 0.183, skill -0.632) · ECE 0.340 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.026(기준율 0.000, skill -) · ECE 0.160 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.088(기준율 0.066, skill -0.333) · ECE 0.149 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.133(기준율 0.066, skill -1.008) · ECE 0.259 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- C: normal Brier 0.298(기준율 0.183, skill -0.632) · ECE 0.340 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.026(기준율 0.000, skill -) · ECE 0.160 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.088(기준율 0.066, skill -0.333) · ECE 0.149 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.133(기준율 0.066, skill -1.008) · ECE 0.259 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- D: normal Brier 0.298(기준율 0.183, skill -0.632) · ECE 0.340 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.026(기준율 0.000, skill -) · ECE 0.160 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.088(기준율 0.066, skill -0.333) · ECE 0.149 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.133(기준율 0.066, skill -1.008) · ECE 0.259 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- E: normal Brier 0.298(기준율 0.183, skill -0.632) · ECE 0.340 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.026(기준율 0.000, skill -) · ECE 0.160 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.088(기준율 0.066, skill -0.333) · ECE 0.149 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.133(기준율 0.066, skill -1.008) · ECE 0.259 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:novision: normal Brier 0.327(기준율 0.183, skill -0.790) · ECE 0.380 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.044(기준율 0.000, skill -) · ECE 0.210 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.106(기준율 0.066, skill -0.594) · ECE 0.199 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.144(기준율 0.140, skill -0.027) · ECE 0.061 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.150(기준율 0.066, skill -1.256) · ECE 0.289 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:notouch: normal Brier 0.350(기준율 0.183, skill -0.920) · ECE 0.410 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.010(기준율 0.000, skill -) · ECE 0.100 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.091(기준율 0.066, skill -0.379) · ECE 0.159 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.003) · ECE 0.021 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.138(기준율 0.066, skill -1.088) · ECE 0.269 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:la_null: normal Brier 0.298(기준율 0.183, skill -0.632) · ECE 0.340 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.026(기준율 0.000, skill -) · ECE 0.160 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.088(기준율 0.066, skill -0.333) · ECE 0.149 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.133(기준율 0.066, skill -1.008) · ECE 0.259 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:sit_dict: normal Brier 0.298(기준율 0.183, skill -0.632) · ECE 0.340 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.026(기준율 0.000, skill -) · ECE 0.160 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.088(기준율 0.066, skill -0.333) · ECE 0.149 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.133(기준율 0.066, skill -1.008) · ECE 0.259 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:vision_summary: normal Brier 0.289(기준율 0.183, skill -0.584) · ECE 0.327 · AUROC 0.523(n 154, 양성 117); touch_difficulty Brier 0.031(기준율 0.000, skill -) · ECE 0.175 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.083(기준율 0.066, skill -0.247) · ECE 0.130 · AUROC 0.643(n 154, 양성 11); visual_difficulty Brier 0.138(기준율 0.140, skill 0.020) · ECE 0.017 · AUROC 0.595(n 154, 양성 26); hesitation Brier 0.158(기준율 0.066, skill -1.381) · ECE 0.304 · AUROC 0.701(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:wording_nocrit: normal Brier 0.266(기준율 0.183, skill -0.460) · ECE 0.290 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.029(기준율 0.000, skill -) · ECE 0.170 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.102(기준율 0.066, skill -0.536) · ECE 0.189 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.195(기준율 0.066, skill -1.938) · ECE 0.359 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:perm_vision: normal Brier 0.298(기준율 0.183, skill -0.632) · ECE 0.340 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.026(기준율 0.000, skill -) · ECE 0.160 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.088(기준율 0.066, skill -0.333) · ECE 0.149 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.133(기준율 0.066, skill -1.008) · ECE 0.259 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
- B:perm_touch: normal Brier 0.298(기준율 0.183, skill -0.632) · ECE 0.340 · AUROC 0.500(n 154, 양성 117); touch_difficulty Brier 0.026(기준율 0.000, skill -) · ECE 0.160 · AUROC undefined(한 부류뿐)(n 154, 양성 0); navigation_difficulty Brier 0.088(기준율 0.066, skill -0.333) · ECE 0.149 · AUROC 0.500(n 154, 양성 11); visual_difficulty Brier 0.141(기준율 0.140, skill -0.007) · ECE 0.031 · AUROC 0.500(n 154, 양성 26); hesitation Brier 0.133(기준율 0.066, skill -1.008) · ECE 0.259 · AUROC 0.500(n 154, 양성 11)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent - 대 -(n 0), backs_recent - 대 -(n 0), fixes_recent - 대 -(n 0), condition_C2 - 대 -(n 0)

### 규칙표 자체 질문(proposal_fits, 보조)

- B: Brier - · ECE - · AUROC -(n 0, 양성 0)
- C: Brier - · ECE - · AUROC -(n 0, 양성 0)
- D: Brier - · ECE - · AUROC -(n 0, 양성 0)
- E: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:novision: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:notouch: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:la_null: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:sit_dict: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:vision_summary: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:wording_nocrit: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:perm_vision: Brier - · ECE - · AUROC -(n 0, 양성 0)
- B:perm_touch: Brier - · ECE - · AUROC -(n 0, 양성 0)

### 다음 어려움 예측(D · E, 따로 셈)

- D: 예측 19(전체 149, 95% 0.000~0.350); 관측 가능한 기준: B의 지금 최고 상태를 그대로 씀 107(전체 149, 95% 0.413~0.926), 상수 {'touch_difficulty': 0, 'navigation_difficulty': 19, 'visual_difficulty': 23, 'hesitation': 19, 'none': 107}(전체 149), 다수 범주(none) 107(전체 149, 95% 0.413~0.926), 우연 0.226; 지금 창의 라벨을 쓰는 지속(오라클)과 같은 창에서 예측 10(전체 140, 95% 0.000~0.219) 대 140(전체 140, 95% 1.000~1.000); 예측 분포 {'hesitation': 149}
- E: 예측 19(전체 149, 95% 0.000~0.350); 관측 가능한 기준: B의 지금 최고 상태를 그대로 씀 107(전체 149, 95% 0.413~0.926), 상수 {'touch_difficulty': 0, 'navigation_difficulty': 19, 'visual_difficulty': 23, 'hesitation': 19, 'none': 107}(전체 149), 다수 범주(none) 107(전체 149, 95% 0.413~0.926), 우연 0.226; 지금 창의 라벨을 쓰는 지속(오라클)과 같은 창에서 예측 10(전체 140, 95% 0.000~0.219) 대 140(전체 140, 95% 1.000~1.000); 예측 분포 {'hesitation': 149}

### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 556, 섞은 평균 556.000, 범위 556~556
- 라벨을 섞음 · C selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 라벨을 섞음 · C0 selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 라벨을 섞음 · E selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 라벨을 섞음 · B normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · B hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 라벨을 섞음 · C normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · C hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 라벨을 섞음 · D normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 라벨을 섞음 · D touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · D navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 라벨을 섞음 · D visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · D hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 라벨을 섞음 · E normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 라벨을 섞음 · E touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · E navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 라벨을 섞음 · E visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · E hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 라벨을 섞음 · B:novision normal Brier: 실제 0.327, 섞은 평균 0.327, 범위 0.327~0.327
- 라벨을 섞음 · B:novision touch_difficulty Brier: 실제 0.044, 섞은 평균 0.044, 범위 0.044~0.044
- 라벨을 섞음 · B:novision navigation_difficulty Brier: 실제 0.106, 섞은 평균 0.106, 범위 0.106~0.106
- 라벨을 섞음 · B:novision visual_difficulty Brier: 실제 0.144, 섞은 평균 0.144, 범위 0.144~0.144
- 라벨을 섞음 · B:novision hesitation Brier: 실제 0.150, 섞은 평균 0.150, 범위 0.150~0.150
- 라벨을 섞음 · B:notouch normal Brier: 실제 0.350, 섞은 평균 0.350, 범위 0.350~0.350
- 라벨을 섞음 · B:notouch touch_difficulty Brier: 실제 0.010, 섞은 평균 0.010, 범위 0.010~0.010
- 라벨을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.091, 섞은 평균 0.091, 범위 0.091~0.091
- 라벨을 섞음 · B:notouch visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · B:notouch hesitation Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 라벨을 섞음 · B:la_null normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 라벨을 섞음 · B:la_null touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B:la_null navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 라벨을 섞음 · B:la_null visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · B:la_null hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 라벨을 섞음 · B:sit_dict normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 라벨을 섞음 · B:sit_dict touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B:sit_dict navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 라벨을 섞음 · B:sit_dict visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · B:sit_dict hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 라벨을 섞음 · B:vision_summary normal Brier: 실제 0.289, 섞은 평균 0.289, 범위 0.289~0.289
- 라벨을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.031, 섞은 평균 0.031, 범위 0.031~0.031
- 라벨을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.083, 섞은 평균 0.083, 범위 0.083~0.083
- 라벨을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 라벨을 섞음 · B:vision_summary hesitation Brier: 실제 0.158, 섞은 평균 0.158, 범위 0.158~0.158
- 라벨을 섞음 · B:wording_nocrit normal Brier: 실제 0.266, 섞은 평균 0.266, 범위 0.266~0.266
- 라벨을 섞음 · B:wording_nocrit touch_difficulty Brier: 실제 0.029, 섞은 평균 0.029, 범위 0.029~0.029
- 라벨을 섞음 · B:wording_nocrit navigation_difficulty Brier: 실제 0.102, 섞은 평균 0.102, 범위 0.102~0.102
- 라벨을 섞음 · B:wording_nocrit visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · B:wording_nocrit hesitation Brier: 실제 0.195, 섞은 평균 0.195, 범위 0.195~0.195
- 라벨을 섞음 · B:perm_vision normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 라벨을 섞음 · B:perm_vision touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B:perm_vision navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 라벨을 섞음 · B:perm_vision visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · B:perm_vision hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 라벨을 섞음 · B:perm_touch normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 라벨을 섞음 · B:perm_touch touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B:perm_touch navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 라벨을 섞음 · B:perm_touch visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 라벨을 섞음 · B:perm_touch hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · C selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 답을 섞음 · C0 selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 답을 섞음 · E selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 답을 섞음 · B normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · C normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · C touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · C visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · C hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · D normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · D touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · D navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · D visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · D hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · E normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · E touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · E navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · E visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · E hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · B:novision normal Brier: 실제 0.327, 섞은 평균 0.327, 범위 0.327~0.327
- 답을 섞음 · B:novision touch_difficulty Brier: 실제 0.044, 섞은 평균 0.044, 범위 0.044~0.044
- 답을 섞음 · B:novision navigation_difficulty Brier: 실제 0.106, 섞은 평균 0.106, 범위 0.106~0.106
- 답을 섞음 · B:novision visual_difficulty Brier: 실제 0.144, 섞은 평균 0.144, 범위 0.144~0.144
- 답을 섞음 · B:novision hesitation Brier: 실제 0.150, 섞은 평균 0.150, 범위 0.150~0.150
- 답을 섞음 · B:notouch normal Brier: 실제 0.350, 섞은 평균 0.350, 범위 0.350~0.350
- 답을 섞음 · B:notouch touch_difficulty Brier: 실제 0.010, 섞은 평균 0.010, 범위 0.010~0.010
- 답을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.091, 섞은 평균 0.091, 범위 0.091~0.091
- 답을 섞음 · B:notouch visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:notouch hesitation Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 답을 섞음 · B:la_null normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B:la_null touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B:la_null navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B:la_null visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:la_null hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · B:sit_dict normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B:sit_dict touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B:sit_dict navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B:sit_dict visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:sit_dict hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · B:vision_summary normal Brier: 실제 0.289, 섞은 평균 0.289, 범위 0.288~0.290
- 답을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.031, 섞은 평균 0.031, 범위 0.030~0.031
- 답을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.083, 섞은 평균 0.083, 범위 0.082~0.084
- 답을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.138, 섞은 평균 0.137, 범위 0.136~0.138
- 답을 섞음 · B:vision_summary hesitation Brier: 실제 0.158, 섞은 평균 0.158, 범위 0.158~0.159
- 답을 섞음 · B:wording_nocrit normal Brier: 실제 0.266, 섞은 평균 0.266, 범위 0.266~0.266
- 답을 섞음 · B:wording_nocrit touch_difficulty Brier: 실제 0.029, 섞은 평균 0.029, 범위 0.029~0.029
- 답을 섞음 · B:wording_nocrit navigation_difficulty Brier: 실제 0.102, 섞은 평균 0.102, 범위 0.102~0.102
- 답을 섞음 · B:wording_nocrit visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:wording_nocrit hesitation Brier: 실제 0.195, 섞은 평균 0.195, 범위 0.195~0.195
- 답을 섞음 · B:perm_vision normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B:perm_vision touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B:perm_vision navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B:perm_vision visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:perm_vision hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · B:perm_touch normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B:perm_touch touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B:perm_touch navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B:perm_touch visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:perm_touch hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 556, 섞은 평균 556.000, 범위 556~556
- 라벨을 섞음 · C selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 라벨을 섞음 · C0 selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 라벨을 섞음 · E selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 라벨을 섞음 · B normal Brier: 실제 0.298, 섞은 평균 0.291, 범위 0.283~0.300
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.093, 범위 0.074~0.103
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · B hesitation Brier: 실제 0.133, 섞은 평균 0.136, 범위 0.124~0.142
- 라벨을 섞음 · C normal Brier: 실제 0.298, 섞은 평균 0.291, 범위 0.283~0.300
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.093, 범위 0.074~0.103
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · C hesitation Brier: 실제 0.133, 섞은 평균 0.136, 범위 0.124~0.142
- 라벨을 섞음 · D normal Brier: 실제 0.298, 섞은 평균 0.291, 범위 0.283~0.300
- 라벨을 섞음 · D touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · D navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.093, 범위 0.074~0.103
- 라벨을 섞음 · D visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · D hesitation Brier: 실제 0.133, 섞은 평균 0.136, 범위 0.124~0.142
- 라벨을 섞음 · E normal Brier: 실제 0.298, 섞은 평균 0.291, 범위 0.283~0.300
- 라벨을 섞음 · E touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · E navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.093, 범위 0.074~0.103
- 라벨을 섞음 · E visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · E hesitation Brier: 실제 0.133, 섞은 평균 0.136, 범위 0.124~0.142
- 라벨을 섞음 · B:novision normal Brier: 실제 0.327, 섞은 평균 0.316, 범위 0.305~0.330
- 라벨을 섞음 · B:novision touch_difficulty Brier: 실제 0.044, 섞은 평균 0.044, 범위 0.044~0.044
- 라벨을 섞음 · B:novision navigation_difficulty Brier: 실제 0.106, 섞은 평균 0.109, 범위 0.094~0.118
- 라벨을 섞음 · B:novision visual_difficulty Brier: 실제 0.144, 섞은 평균 0.164, 범위 0.130~0.183
- 라벨을 섞음 · B:novision hesitation Brier: 실제 0.150, 섞은 평균 0.152, 범위 0.142~0.157
- 라벨을 섞음 · B:notouch normal Brier: 실제 0.350, 섞은 평균 0.337, 범위 0.323~0.354
- 라벨을 섞음 · B:notouch touch_difficulty Brier: 실제 0.010, 섞은 평균 0.010, 범위 0.010~0.010
- 라벨을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.091, 섞은 평균 0.096, 범위 0.077~0.105
- 라벨을 섞음 · B:notouch visual_difficulty Brier: 실제 0.141, 섞은 평균 0.164, 범위 0.125~0.185
- 라벨을 섞음 · B:notouch hesitation Brier: 실제 0.138, 섞은 평균 0.141, 범위 0.130~0.147
- 라벨을 섞음 · B:la_null normal Brier: 실제 0.298, 섞은 평균 0.291, 범위 0.283~0.300
- 라벨을 섞음 · B:la_null touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B:la_null navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.093, 범위 0.074~0.103
- 라벨을 섞음 · B:la_null visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · B:la_null hesitation Brier: 실제 0.133, 섞은 평균 0.136, 범위 0.124~0.142
- 라벨을 섞음 · B:sit_dict normal Brier: 실제 0.298, 섞은 평균 0.291, 범위 0.283~0.300
- 라벨을 섞음 · B:sit_dict touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B:sit_dict navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.093, 범위 0.074~0.103
- 라벨을 섞음 · B:sit_dict visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · B:sit_dict hesitation Brier: 실제 0.133, 섞은 평균 0.136, 범위 0.124~0.142
- 라벨을 섞음 · B:vision_summary normal Brier: 실제 0.289, 섞은 평균 0.284, 범위 0.276~0.293
- 라벨을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.031, 섞은 평균 0.031, 범위 0.031~0.031
- 라벨을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.083, 섞은 평균 0.088, 범위 0.067~0.100
- 라벨을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.138, 섞은 평균 0.166, 범위 0.126~0.191
- 라벨을 섞음 · B:vision_summary hesitation Brier: 실제 0.158, 섞은 평균 0.160, 범위 0.151~0.166
- 라벨을 섞음 · B:wording_nocrit normal Brier: 실제 0.266, 섞은 평균 0.264, 범위 0.261~0.267
- 라벨을 섞음 · B:wording_nocrit touch_difficulty Brier: 실제 0.029, 섞은 평균 0.029, 범위 0.029~0.029
- 라벨을 섞음 · B:wording_nocrit navigation_difficulty Brier: 실제 0.102, 섞은 평균 0.106, 범위 0.089~0.114
- 라벨을 섞음 · B:wording_nocrit visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · B:wording_nocrit hesitation Brier: 실제 0.195, 섞은 평균 0.196, 범위 0.191~0.199
- 라벨을 섞음 · B:perm_vision normal Brier: 실제 0.298, 섞은 평균 0.291, 범위 0.283~0.300
- 라벨을 섞음 · B:perm_vision touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B:perm_vision navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.093, 범위 0.074~0.103
- 라벨을 섞음 · B:perm_vision visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · B:perm_vision hesitation Brier: 실제 0.133, 섞은 평균 0.136, 범위 0.124~0.142
- 라벨을 섞음 · B:perm_touch normal Brier: 실제 0.298, 섞은 평균 0.291, 범위 0.283~0.300
- 라벨을 섞음 · B:perm_touch touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 라벨을 섞음 · B:perm_touch navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.093, 범위 0.074~0.103
- 라벨을 섞음 · B:perm_touch visual_difficulty Brier: 실제 0.141, 섞은 평균 0.163, 범위 0.126~0.184
- 라벨을 섞음 · B:perm_touch hesitation Brier: 실제 0.133, 섞은 평균 0.136, 범위 0.124~0.142
- 답을 섞음 · C selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 답을 섞음 · C0 selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 답을 섞음 · E selection (answered): 실제 0, 섞은 평균 0.000, 범위 0~0
- 답을 섞음 · B normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · C normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · C touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · C visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · C hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · D normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · D touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · D navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · D visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · D hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · E normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · E touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · E navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · E visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · E hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · B:novision normal Brier: 실제 0.327, 섞은 평균 0.327, 범위 0.327~0.327
- 답을 섞음 · B:novision touch_difficulty Brier: 실제 0.044, 섞은 평균 0.044, 범위 0.044~0.044
- 답을 섞음 · B:novision navigation_difficulty Brier: 실제 0.106, 섞은 평균 0.106, 범위 0.106~0.106
- 답을 섞음 · B:novision visual_difficulty Brier: 실제 0.144, 섞은 평균 0.144, 범위 0.144~0.144
- 답을 섞음 · B:novision hesitation Brier: 실제 0.150, 섞은 평균 0.150, 범위 0.150~0.150
- 답을 섞음 · B:notouch normal Brier: 실제 0.350, 섞은 평균 0.350, 범위 0.350~0.350
- 답을 섞음 · B:notouch touch_difficulty Brier: 실제 0.010, 섞은 평균 0.010, 범위 0.010~0.010
- 답을 섞음 · B:notouch navigation_difficulty Brier: 실제 0.091, 섞은 평균 0.091, 범위 0.091~0.091
- 답을 섞음 · B:notouch visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:notouch hesitation Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 답을 섞음 · B:la_null normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B:la_null touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B:la_null navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B:la_null visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:la_null hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · B:sit_dict normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B:sit_dict touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B:sit_dict navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B:sit_dict visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:sit_dict hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · B:vision_summary normal Brier: 실제 0.289, 섞은 평균 0.287, 범위 0.282~0.292
- 답을 섞음 · B:vision_summary touch_difficulty Brier: 실제 0.031, 섞은 평균 0.032, 범위 0.031~0.033
- 답을 섞음 · B:vision_summary navigation_difficulty Brier: 실제 0.083, 섞은 평균 0.083, 범위 0.081~0.084
- 답을 섞음 · B:vision_summary visual_difficulty Brier: 실제 0.138, 섞은 평균 0.141, 범위 0.135~0.147
- 답을 섞음 · B:vision_summary hesitation Brier: 실제 0.158, 섞은 평균 0.156, 범위 0.154~0.159
- 답을 섞음 · B:wording_nocrit normal Brier: 실제 0.266, 섞은 평균 0.266, 범위 0.266~0.266
- 답을 섞음 · B:wording_nocrit touch_difficulty Brier: 실제 0.029, 섞은 평균 0.029, 범위 0.029~0.029
- 답을 섞음 · B:wording_nocrit navigation_difficulty Brier: 실제 0.102, 섞은 평균 0.102, 범위 0.102~0.102
- 답을 섞음 · B:wording_nocrit visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:wording_nocrit hesitation Brier: 실제 0.195, 섞은 평균 0.195, 범위 0.195~0.195
- 답을 섞음 · B:perm_vision normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B:perm_vision touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B:perm_vision navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B:perm_vision visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:perm_vision hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
- 답을 섞음 · B:perm_touch normal Brier: 실제 0.298, 섞은 평균 0.298, 범위 0.298~0.298
- 답을 섞음 · B:perm_touch touch_difficulty Brier: 실제 0.026, 섞은 평균 0.026, 범위 0.026~0.026
- 답을 섞음 · B:perm_touch navigation_difficulty Brier: 실제 0.088, 섞은 평균 0.088, 범위 0.088~0.088
- 답을 섞음 · B:perm_touch visual_difficulty Brier: 실제 0.141, 섞은 평균 0.141, 범위 0.141~0.141
- 답을 섞음 · B:perm_touch hesitation Brier: 실제 0.133, 섞은 평균 0.133, 범위 0.133~0.133
