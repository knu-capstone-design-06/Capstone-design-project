# E5 지표: `stage2_2_C_nohistory`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `C:\Users\samsung-user\claude\Capstone_Design_Project\4_vision\eval_ab_2026-11-04\admissible_v4.csv`(admissible)
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
| C | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| | | | | | support_choice | 3344 | 3183 | 161 | 161 | 0 | 0 | 161 | 0 | - · - · - | 0 |
| C:nohistory | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| | | | | | support_choice | 3344 | 3183 | 161 | 161 | 0 | 23 | 138 | 24 | 247.4 · 483.9 · 489.8 | 13541 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- C: API 호출 0번, 캐시 답 3666개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 161(전체 3344); 사슬 전체 지연 p50 - · p95 - ms
- C:nohistory: API 호출 47번, 캐시 답 3619개, 시도한 창마다 호출 0.01번, 2단계까지 간 창 161(전체 3344); 사슬 전체 지연 p50 - · p95 - ms

## 같은 요청 점검(실행 동작)

- C:nohistory vs C, 단계 state_scores: 짝 창 3344개, 요청이 같은 창 3344개
- C:nohistory vs C, 단계 support_choice: 짝 창 161개, 요청이 같은 창 0개

## 같은 입력 반복(요청마다 1번)


## 답 요약

| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| C | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| C | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| C | state_scores | normal | 3344 | 0.520 | 0.080 | 0.890 |
| C | state_scores | proposal_fits | 134 | 0.459 | 0.130 | 0.780 |
| C | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| C | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| C | support_choice | support_choice(choice) | 161 | {'highlight_next_action': 78, 'none': 63, 'large_button': 20} | conf 평균 0.563 | |
| C:nohistory | state_scores | hesitation | 3344 | 0.428 | 0.110 | 0.810 |
| C:nohistory | state_scores | navigation_difficulty | 3344 | 0.212 | 0.040 | 0.640 |
| C:nohistory | state_scores | normal | 3344 | 0.520 | 0.080 | 0.890 |
| C:nohistory | state_scores | proposal_fits | 134 | 0.459 | 0.130 | 0.780 |
| C:nohistory | state_scores | touch_difficulty | 3344 | 0.200 | 0.050 | 0.770 |
| C:nohistory | state_scores | visual_difficulty | 3344 | 0.140 | 0.060 | 0.470 |
| C:nohistory | support_choice | support_choice(choice) | 161 | {'highlight_next_action': 141, 'large_button': 20} | conf 평균 0.781 | |

## 짝 비교(같은 창)

- C:nohistory vs C, state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - proposal_fits: n 134, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
- C:nohistory vs C, support_choice: 가장 큰 상태 점수가 바뀐 창 0(전체 0); 고른 답이 바뀐 창 {'support_choice': '63(전체 161)'}

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
- C:nohistory: 선택지(the sent question's options (a support besides none))가 있는 창 125개, 상태 {'answered': 125}
  - 첫 순서: 답한 창에서 허용 안 91(전체 125, 95% 0.626~0.815)(우연 0.863; 같은 창의 A 91(전체 125, 95% 0.626~0.815)); 규칙표로 채운 전체 2977(전체 3011, 95% 0.985~0.992); 지정 지원과 같음 82(전체 87, 95% 0.899~0.987)(우연 0.471); 고른 지원 확률 Brier 0.250 · ECE 0.265 · AUROC 0.399(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 124, 'order_disagree': 1}; 허용 안 91(전체 124, 95% 0.633~0.818)(우연 0.867); 같은 창의 A 91(전체 124, 95% 0.633~0.818); 순서 일관성 124(전체 125, 95% 0.976~1.000)(무작위 선택자 0.499, 합의 · 허용 0.431)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 44/22/7/79(A는 44/22/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 22(전체 66, 95% 0.232~0.453), 제안 정밀도 44(전체 51, 95% 0.743~0.932); 허용 밖 결정의 분류 {'decision_errors': 34, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 19, 'observed_tag_unknown': 15, 'reference_missing': 0}
  - 다음 창 적용: 짝 113개에서 C 85, 한 창 늦춘 A 85, 같은 창 A 113; 한 창 늦춘 A 전체 2770(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 42(전체 66, 95% 0.516~0.742); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 4, 'FN': 8, 'designated_delivery': {'k': 2, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 40, 'FN': 14, 'designated_delivery': {'k': 40, 'n': 54}}}; 시작 시각 전에 연 도움 2구간; 옛 규칙 TP/FN 42/24, 지정 지원 {'k': 41, 'n': 66}
  - 고르지 않은 창 0개(전체 125): {'kept_inadmissible_candidate': 34, 'kept_admissible_candidate': 91}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 91.0 대 실제 91; 철회 규칙 재현 79(전체 125, 95% 0.545~0.711)(철회된 후보에서 고르지 않음 0(전체 46), 처음 후보에서 0(전체 79))

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)

- C: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.174 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.793(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.099) · ECE 0.195 · AUROC 0.761(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.793(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.761(n 1287)
- C:nohistory: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.174 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.793(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.040 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.194(기준율 0.177, skill -0.099) · ECE 0.195 · AUROC 0.761(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.793(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.735(n 850), backs_recent 0.942 대 0.735(n 850), fixes_recent 0.322 대 0.735(n 850), condition_C2 0.322 대 0.761(n 1287)

### 규칙표 자체 질문(proposal_fits, 보조)

- C: Brier 0.392 · ECE 0.421 · AUROC 0.403(n 102, 양성 83)
- C:nohistory: Brier 0.392 · ECE 0.421 · AUROC 0.403(n 102, 양성 83)

### 다음 어려움 예측(D · E, 따로 셈)


### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 2977, 섞은 평균 2972.431, 범위 2964~2982
- 라벨을 섞음 · C selection (answered): 실제 95, 섞은 평균 97.087, 범위 88~105
- 라벨을 섞음 · C:nohistory selection (answered): 실제 91, 섞은 평균 86.431, 범위 78~96
- 라벨을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.130
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.144~0.150
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · C hesitation Brier: 실제 0.194, 섞은 평균 0.201, 범위 0.198~0.204
- 라벨을 섞음 · C:nohistory normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · C:nohistory touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.130
- 라벨을 섞음 · C:nohistory navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.144~0.150
- 라벨을 섞음 · C:nohistory visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · C:nohistory hesitation Brier: 실제 0.194, 섞은 평균 0.201, 범위 0.198~0.204
- 답을 섞음 · C selection (answered): 실제 95, 섞은 평균 95.485, 범위 95~96
- 답을 섞음 · C:nohistory selection (answered): 실제 91, 섞은 평균 91.000, 범위 91~91
- 답을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.238~0.248
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.132
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.149~0.156
- 답을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · C hesitation Brier: 실제 0.194, 섞은 평균 0.206, 범위 0.202~0.209
- 답을 섞음 · C:nohistory normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.238~0.248
- 답을 섞음 · C:nohistory touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · C:nohistory navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.148~0.156
- 답을 섞음 · C:nohistory visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · C:nohistory hesitation Brier: 실제 0.194, 섞은 평균 0.206, 범위 0.202~0.209

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 2977, 섞은 평균 2923.263, 범위 2909~2941
- 라벨을 섞음 · C selection (answered): 실제 95, 섞은 평균 67.479, 범위 56~83
- 라벨을 섞음 · C:nohistory selection (answered): 실제 91, 섞은 평균 37.263, 범위 23~55
- 라벨을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.284~0.318
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.199~0.231
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.173~0.191
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.152~0.170
- 라벨을 섞음 · C hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.224~0.251
- 라벨을 섞음 · C:nohistory normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.284~0.318
- 라벨을 섞음 · C:nohistory touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.199~0.231
- 라벨을 섞음 · C:nohistory navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.173~0.191
- 라벨을 섞음 · C:nohistory visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.152~0.170
- 라벨을 섞음 · C:nohistory hesitation Brier: 실제 0.194, 섞은 평균 0.239, 범위 0.224~0.251
- 답을 섞음 · C selection (answered): 실제 95, 섞은 평균 104.252, 범위 95~111
- 답을 섞음 · C:nohistory selection (answered): 실제 91, 섞은 평균 91.000, 범위 91~91
- 답을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.306, 범위 0.290~0.323
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.217~0.244
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.179~0.194
- 답을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.139~0.146
- 답을 섞음 · C hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.225~0.256
- 답을 섞음 · C:nohistory normal Brier: 실제 0.233, 섞은 평균 0.306, 범위 0.289~0.323
- 답을 섞음 · C:nohistory touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.217~0.244
- 답을 섞음 · C:nohistory navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.180~0.193
- 답을 섞음 · C:nohistory visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.139~0.146
- 답을 섞음 · C:nohistory hesitation Brier: 실제 0.194, 섞은 평균 0.241, 범위 0.224~0.254
