# E5 지표: `stage2_5_GT_b0_r0`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `C:/Users/samsung-user/claude/Capstone_Design_Project/4_vision/eval_ab_2026-11-04/admissible_v4.csv`(admissible)
- 합성 터치 창: 값 묶음 `b0_r0`, 배치 `fit-medium`, 조건 C0, C1, C2, C3, C4, C5, C6
- 라벨 상태: 규정한 허용 행동(stipulated admissible actions) (admissible_v4.csv)

## 규칙표(조건 A)

- 창 3892개(영상 35개, 테이크 245개, 세션 257개), 측정 가능 3344개
- 기록의 상황 태그: {'none': 3633, 'looking_around': 70, 'consulting_companion': 126, 'looking_back_with_people_behind': 63}
- 전이: {'none': 2764, 'open': 203, 'keep': 774, 'withdraw': 144, 'replace': 7}; 연 지원(open · replace): {'highlight_next_action': 134, 'large_button': 20, 'wait_hold_timer': 40, 'remaining_steps_notice': 16}
- 규칙표 자체 질문이 붙은 창: 167개 {'fit': 167}; tick으로 거둔 묻기 0개
- 허용 후보 수별 창: {0: 3682, 1: 201, 2: 9}
- 입력 기록의 결정(비전 기록 또는 E3 AB0)과 같음: {'None': 3892}
- 계약 터치 5칸: {'absent (contract five not all known)': 3892}; 최근 구간 터치 수의 출처: {'segment sum (a window without touch)': 820, 'segment sum (n windows)': 3072}
- fixture 기대값: 0개 확인, 어긋남 0개

## 실행(조건 · 변형 · 단계별)

| arm | 창 | 대상 창 | 시도한 창 | 건너뜀(이유) | 단계 | 단계 대상 | build 없음 | 시도 | 답 | 실패(종류) | API 호출 | 캐시 답 | 순서 바꾼 호출 | 지연 p50 · p95 · 최대 ms | 입력 토큰 합 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 3892 | 3344 | 0 | 조건 A(묻지 않음) | - | - | - | - | - | - | - | - | - | - | - |
| C | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| | | | | | support_choice | 3344 | 3134 | 210 | 210 | 0 | 35 | 175 | 35 | 203.2 · 297.4 · 391.9 | 21786 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- C: API 호출 70번, 캐시 답 3694개, 시도한 창마다 호출 0.02번, 2단계까지 간 창 210(전체 3344); 사슬 전체 지연 p50 - · p95 - ms

## 같은 요청 점검(실행 동작)


## 같은 입력 반복(요청마다 1번)


## 답 요약

| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| C | state_scores | hesitation | 3344 | 0.432 | 0.110 | 0.840 |
| C | state_scores | navigation_difficulty | 3344 | 0.217 | 0.040 | 0.640 |
| C | state_scores | normal | 3344 | 0.512 | 0.080 | 0.890 |
| C | state_scores | proposal_fits | 167 | 0.527 | 0.100 | 0.840 |
| C | state_scores | touch_difficulty | 3344 | 0.198 | 0.050 | 0.770 |
| C | state_scores | visual_difficulty | 3344 | 0.141 | 0.060 | 0.510 |
| C | support_choice | support_choice(choice) | 210 | {'highlight_next_action': 81, 'none': 66, 'large_button': 20, 'wait_hold_timer': 29, 'remaining_steps_notice': 14} | conf 평균 0.517 | |

## 짝 비교(같은 창)


## 라벨

- 라벨이 붙은 창 3892개(안 붙은 창 0개), 수준 {'action': 3892}, 맞춘 방법 {'segment_id': 3892}
- 구간 분류별 창: {'no_user': 105, 'wait_only': 1087, 'designated': 1193, 'allowed_not_designated': 224, 'contradictory': 881, 'time_stop': 402}
- 세션 257개 가운데 라벨 행이 둘 이상인 세션 56개
- 상태 대응(STATE_PROXY)이 있는 창 1543개: {'normal': 580, 'touch_difficulty': 309, 'hesitation,navigation_difficulty': 357, 'hesitation,navigation_difficulty,touch_difficulty': 24, 'visual_difficulty': 195, 'touch_difficulty,visual_difficulty': 39, 'hesitation,navigation_difficulty,visual_difficulty': 39}
- 창의 태그 | 정답 태그(window truth: the segment's truth tag when a GT behaviour second lies in (t - window_s, t], else none (E3 run_eval.py window_truth)): {'none | none': 3633, 'looking_around | looking_around': 70, 'consulting_companion | consulting_companion': 126, 'looking_back_with_people_behind | looking_back_with_people_behind': 63}
- 보낸 질문의 선택지가 none 하나뿐인 창: 0개

### 기준이 선택지 밖인 창

- 허용 행동이 선택지(허용 후보 + none)에 없음: 전체 0(전체 3892), 후보가 있는 창 0(전체 210)
- 지정 지원이 허용 후보에 없음: 1065(전체 1168)
- 지정 지원이 규칙표 v0 밖(행 없음): 0(전체 3892) []
- 점수 대상: 제외 · 모순 구간 밖의 라벨 창 3011개(뺀 창 881개). 선택 · 상태 추정 · 규칙표 질문 · 예측 · 섞은 대조가 모두 이 창을 쓴다.

### 지원 선택(주 비교: A 대 C · C0 · E, 같은 창; 제외 구간을 뺀 창 3011개)

- A: 허용 안 2978(전체 3011, 95% 0.985~0.993)(우연 0.994), 후보가 있는 창 112(전체 145, 95% 0.671~0.856)(우연 0.885); 지정 지원과 같음 96(전체 1064, 95% 0.067~0.122)(우연 0.045); 고른 것 {'none': 2866, 'highlight_next_action': 104, 'large_button': 17, 'wait_hold_timer': 8, 'remaining_steps_notice': 16}
  - 구간 2×2: TP/FN/FP/TN = 53/13/7/79; 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 13(전체 66, 95% 0.119~0.308)(v0 행 있음 13(전체 66, 95% 0.119~0.308)), 제안 정밀도 53(전체 60, 95% 0.778~0.942); 2×2 밖 {'no_user': 56, 'allowed_not_designated': 13, 'time_stop': 21}
  - 지정 지원 자체를 시작 시각 이후 낸 구간(v0 행 있음): 53(전체 66, 95% 0.692~0.881); 규칙표 행이 없는 지정 구간(2×2 밖)에서 지정 지원 자체를 낸 구간: 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 낸 구간 4(전체 20)은 도움으로 세지 않음)
  - 도움 규칙: 시작 시각 이후 허용 도움(admissible help after onset; 같은 turn에서 연 지원이 시작 시각 이후 보이면 도움, 시작 시각 전에 열어 그때까지 보이면 지연 0). 시작 시각 전에 연 도움 1구간(앞선 초 [1.0]), 지연 중앙값 2.294초(n 53); 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 41, 'FN': 13, 'designated_delivery': {'k': 41, 'n': 54}}}; 옛 규칙(시작 시각 이후 새 제안만) TP/FN 52/14, 지정 지원 {'k': 52, 'n': 66}
  - 허용 밖 결정의 분류(창 정답 태그 기준, 기술만, 인과 주장 아님): {'decision_errors': 33, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 33, 'observed_tag_unknown': 0, 'reference_missing': 0}
- 오프라인 기준(호출 없음, 후보가 있는 창 145개): 늘 none 145(전체 145, 95% 1.000~1.000), 늘 후보 112(전체 145, 95% 0.671~0.856), 철회된 지원이면 none 116(전체 145, 95% 0.723~0.867)(철회 목록을 아는 창 145개); 철회 규칙의 구간 2×2 TP/FN/FP/TN = 52/14/7/79
- C: 선택지(the sent question's options (a support besides none))가 있는 창 145개, 상태 {'answered': 145}
  - 첫 순서: 답한 창에서 허용 안 116(전체 145, 95% 0.723~0.867)(우연 0.885; 같은 창의 A 112(전체 145, 95% 0.671~0.856)); 규칙표로 채운 전체 2982(전체 3011, 95% 0.987~0.993); 지정 지원과 같음 56(전체 100, 95% 0.436~0.676)(우연 0.477); 고른 지원 확률 Brier 0.226 · ECE 0.340 · AUROC 0.093(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 142, 'order_disagree': 3}; 허용 안 114(전체 142, 95% 0.727~0.868)(우연 0.887); 같은 창의 A 110(전체 142, 95% 0.672~0.857); 순서 일관성 142(전체 145, 95% 0.955~1.000)(무작위 선택자 0.497, 합의 · 허용 0.440)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 52/14/7/79(A는 53/13/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 14(전체 66, 95% 0.131~0.325), 제안 정밀도 52(전체 59, 95% 0.775~0.941); 허용 밖 결정의 분류 {'decision_errors': 29, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 29, 'observed_tag_unknown': 0, 'reference_missing': 0}
  - 다음 창 적용: 짝 132개에서 C 108, 한 창 늦춘 A 105, 같은 창 A 132; 한 창 늦춘 A 전체 2771(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 52(전체 66, 95% 0.675~0.869); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 40, 'FN': 14, 'designated_delivery': {'k': 40, 'n': 54}}}; 시작 시각 전에 연 도움 1구간; 옛 규칙 TP/FN 51/15, 지정 지원 {'k': 51, 'n': 66}
  - 고르지 않은 창 46개(전체 145): {'kept_inadmissible_candidate': 29, 'declined_inadmissible_candidate': 4, 'kept_admissible_candidate': 70, 'declined_admissible_candidate': 42}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 122.5 대 실제 116; 철회 규칙 재현 142(전체 145, 95% 0.941~0.993)(철회된 후보에서 고르지 않음 45(전체 47), 처음 후보에서 1(전체 98))

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)

- C: normal Brier 0.231(기준율 0.239, skill 0.032) · ECE 0.173 · AUROC 0.699(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.863(n 1287, 양성 346); navigation_difficulty Brier 0.140(기준율 0.177, skill 0.205) · ECE 0.102 · AUROC 0.801(n 1287, 양성 295); visual_difficulty Brier 0.138(기준율 0.138, skill 0.004) · ECE 0.040 · AUROC 0.575(n 1287, 양성 213); hesitation Brier 0.196(기준율 0.177, skill -0.111) · ECE 0.193 · AUROC 0.744(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.824(n 850), backs_recent 0.309 대 0.824(n 850), fixes_recent 0.316 대 0.824(n 850), condition_C2 0.285 대 0.699(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.863(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.852(n 850), backs_recent 0.942 대 0.852(n 850), fixes_recent 0.322 대 0.852(n 850), condition_C2 0.322 대 0.801(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.578(n 850), backs_recent 0.464 대 0.578(n 850), fixes_recent 0.477 대 0.578(n 850), condition_C2 0.445 대 0.575(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.719(n 850), backs_recent 0.942 대 0.719(n 850), fixes_recent 0.322 대 0.719(n 850), condition_C2 0.322 대 0.744(n 1287)

### 규칙표 자체 질문(proposal_fits, 보조)

- C: Brier 0.358 · ECE 0.384 · AUROC 0.420(n 134, 양성 102)

### 다음 어려움 예측(D · E, 따로 셈)


### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 2978, 섞은 평균 2973.392, 범위 2965~2983
- 라벨을 섞음 · C selection (answered): 실제 116, 섞은 평균 118.077, 범위 107~125
- 라벨을 섞음 · C normal Brier: 실제 0.231, 섞은 평균 0.239, 범위 0.235~0.243
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.131
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.140, 섞은 평균 0.146, 범위 0.143~0.149
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.138, 섞은 평균 0.138, 범위 0.138~0.138
- 라벨을 섞음 · C hesitation Brier: 실제 0.196, 섞은 평균 0.204, 범위 0.201~0.206
- 답을 섞음 · C selection (answered): 실제 116, 섞은 평균 116.508, 범위 116~117
- 답을 섞음 · C normal Brier: 실제 0.231, 섞은 평균 0.243, 범위 0.238~0.247
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.131
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.140, 섞은 평균 0.152, 범위 0.148~0.155
- 답을 섞음 · C visual_difficulty Brier: 실제 0.138, 섞은 평균 0.137, 범위 0.137~0.138
- 답을 섞음 · C hesitation Brier: 실제 0.196, 섞은 평균 0.207, 범위 0.204~0.211

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 2978, 섞은 평균 2915.136, 범위 2900~2930
- 라벨을 섞음 · C selection (answered): 실제 116, 섞은 평균 78.919, 범위 65~93
- 라벨을 섞음 · C normal Brier: 실제 0.231, 섞은 평균 0.302, 범위 0.285~0.321
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.216, 범위 0.200~0.231
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.140, 섞은 평균 0.182, 범위 0.172~0.191
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.138, 섞은 평균 0.160, 범위 0.152~0.170
- 라벨을 섞음 · C hesitation Brier: 실제 0.196, 섞은 평균 0.238, 범위 0.226~0.251
- 답을 섞음 · C selection (answered): 실제 116, 섞은 평균 124.792, 범위 118~131
- 답을 섞음 · C normal Brier: 실제 0.231, 섞은 평균 0.307, 범위 0.286~0.326
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.219~0.244
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.140, 섞은 평균 0.187, 범위 0.178~0.194
- 답을 섞음 · C visual_difficulty Brier: 실제 0.138, 섞은 평균 0.142, 범위 0.137~0.146
- 답을 섞음 · C hesitation Brier: 실제 0.196, 섞은 평균 0.242, 범위 0.229~0.256
