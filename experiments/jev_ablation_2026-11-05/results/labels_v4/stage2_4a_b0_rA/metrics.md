# E5 지표: `stage2_4a_b0_rA`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `C:/Users/samsung-user/claude/Capstone_Design_Project/4_vision/eval_ab_2026-11-04/admissible_v4.csv`(admissible)
- 합성 터치 창: 값 묶음 `b0_rA`, 배치 `fit-medium`, 조건 C0, C1, C2, C3, C4, C5, C6
- 라벨 상태: 규정한 허용 행동(stipulated admissible actions) (admissible_v4.csv)

## 규칙표(조건 A)

- 창 3892개(영상 35개, 테이크 245개, 세션 257개), 측정 가능 3344개
- 기록의 상황 태그: {'unknown': 467, 'none': 3311, 'consulting_companion': 93, 'looking_back_with_people_behind': 21}
- 전이: {'none': 2868, 'open': 190, 'keep': 689, 'withdraw': 137, 'replace': 8}; 연 지원(open · replace): {'highlight_next_action': 139, 'large_button': 20, 'wait_hold_timer': 26, 'remaining_steps_notice': 13}
- 규칙표 자체 질문이 붙은 창: 155개 {'fit': 155}; tick으로 거둔 묻기 0개
- 허용 후보 수별 창: {0: 3694, 1: 197, 2: 1}
- 입력 기록의 결정(비전 기록 또는 E3 AB0)과 같음: {'True': 3892}
- 계약 터치 5칸: {'absent (contract five not all known)': 3892}; 최근 구간 터치 수의 출처: {'segment sum (a window without touch)': 820, 'segment sum (n windows)': 3072}
- fixture 기대값: 0개 확인, 어긋남 0개

## 실행(조건 · 변형 · 단계별)

| arm | 창 | 대상 창 | 시도한 창 | 건너뜀(이유) | 단계 | 단계 대상 | build 없음 | 시도 | 답 | 실패(종류) | API 호출 | 캐시 답 | 순서 바꾼 호출 | 지연 p50 · p95 · 최대 ms | 입력 토큰 합 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 3892 | 3344 | 0 | 조건 A(묻지 않음) | - | - | - | - | - | - | - | - | - | - | - |
| B | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| C | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| | | | | | support_choice | 3344 | 3146 | 198 | 198 | 0 | 0 | 198 | 0 | - · - · - | 0 |
| C0 | 3892 | 3344 | 3344 | {'not measurable': 548} | support_choice | 3344 | 3146 | 198 | 198 | 0 | 0 | 198 | 0 | - · - · - | 0 |
| J | 3892 | 3344 | 3344 | {'not measurable': 548} | support_choice | 3344 | 0 | 3344 | 3344 | 0 | 65 | 3279 | 65 | 196.0 · 325.9 · 654.9 | 46062 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- B: API 호출 0번, 캐시 답 3344개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 - · p95 - ms
- C: API 호출 0번, 캐시 답 3740개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 198(전체 3344); 사슬 전체 지연 p50 - · p95 - ms
- C0: API 호출 0번, 캐시 답 396개, 시도한 창마다 호출 0.00번, 2단계까지 간 창 198(전체 3344); 사슬 전체 지연 p50 0.0 · p95 0.0 ms
- J: API 호출 130번, 캐시 답 6558개, 시도한 창마다 호출 0.04번, 2단계까지 간 창 3344(전체 3344); 사슬 전체 지연 p50 196.0 · p95 325.9 ms

## 같은 요청 점검(실행 동작)

- C0 vs C, 단계 support_choice: 짝 창 198개, 요청이 같은 창 0개
- C vs B (state_scores), 단계 state_scores: 짝 창 3344개, 요청이 같은 창 3344개

## 같은 입력 반복(요청마다 1번)


## 답 요약

| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| B | state_scores | hesitation | 3344 | 0.431 | 0.110 | 0.810 |
| B | state_scores | navigation_difficulty | 3344 | 0.214 | 0.040 | 0.640 |
| B | state_scores | normal | 3344 | 0.516 | 0.070 | 0.890 |
| B | state_scores | proposal_fits | 155 | 0.492 | 0.100 | 0.830 |
| B | state_scores | touch_difficulty | 3344 | 0.199 | 0.050 | 0.770 |
| B | state_scores | visual_difficulty | 3344 | 0.139 | 0.060 | 0.470 |
| C | state_scores | hesitation | 3344 | 0.431 | 0.110 | 0.810 |
| C | state_scores | navigation_difficulty | 3344 | 0.214 | 0.040 | 0.640 |
| C | state_scores | normal | 3344 | 0.516 | 0.070 | 0.890 |
| C | state_scores | proposal_fits | 155 | 0.492 | 0.100 | 0.830 |
| C | state_scores | touch_difficulty | 3344 | 0.199 | 0.050 | 0.770 |
| C | state_scores | visual_difficulty | 3344 | 0.139 | 0.060 | 0.470 |
| C | support_choice | support_choice(choice) | 198 | {'highlight_next_action': 76, 'none': 70, 'large_button': 20, 'wait_hold_timer': 19, 'remaining_steps_notice': 13} | conf 평균 0.519 | |
| C0 | support_choice | support_choice(choice) | 198 | {'highlight_next_action': 76, 'none': 69, 'large_button': 19, 'wait_hold_timer': 21, 'remaining_steps_notice': 13} | conf 평균 0.502 | |
| J | support_choice | support_choice(choice) | 3344 | {'remaining_steps_notice': 2191, 'none': 700, 'highlight_next_action': 318, 'large_button': 18, 'wait_hold_timer': 112, 'defer_big_button_question': 5} | conf 평균 0.443 | |

## 짝 비교(같은 창)

- C0 vs C, support_choice: 가장 큰 상태 점수가 바뀐 창 0(전체 0); 고른 답이 바뀐 창 {'support_choice': '10(전체 198)'}
- C vs B (state_scores), state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - proposal_fits: n 155, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000

## 라벨

- 라벨이 붙은 창 3892개(안 붙은 창 0개), 수준 {'action': 3892}, 맞춘 방법 {'segment_id': 3892}
- 구간 분류별 창: {'no_user': 105, 'wait_only': 1087, 'designated': 1193, 'allowed_not_designated': 224, 'contradictory': 881, 'time_stop': 402}
- 세션 257개 가운데 라벨 행이 둘 이상인 세션 56개
- 상태 대응(STATE_PROXY)이 있는 창 1543개: {'normal': 580, 'touch_difficulty': 309, 'hesitation,navigation_difficulty': 357, 'hesitation,navigation_difficulty,touch_difficulty': 24, 'visual_difficulty': 195, 'touch_difficulty,visual_difficulty': 39, 'hesitation,navigation_difficulty,visual_difficulty': 39}
- 창의 태그 | 정답 태그(window truth: the segment's truth tag when a GT behaviour second lies in (t - window_s, t], else none (E3 run_eval.py window_truth)): {'none | none': 3571, 'none | looking_around': 70, 'none | consulting_companion': 88, 'consulting_companion | consulting_companion': 38, 'consulting_companion | none': 55, 'none | looking_back_with_people_behind': 49, 'looking_back_with_people_behind | looking_back_with_people_behind': 14, 'looking_back_with_people_behind | none': 7}
- 보낸 질문의 선택지가 none 하나뿐인 창: 0개

### 기준이 선택지 밖인 창

- 허용 행동이 선택지(허용 후보 + none)에 없음: 전체 0(전체 3892), 후보가 있는 창 0(전체 198)
- 지정 지원이 허용 후보에 없음: 1066(전체 1168)
- 지정 지원이 규칙표 v0 밖(행 없음): 0(전체 3892) []
- 점수 대상: 제외 · 모순 구간 밖의 라벨 창 3011개(뺀 창 881개). 선택 · 상태 추정 · 규칙표 질문 · 예측 · 섞은 대조가 모두 이 창을 쓴다.

### 지원 선택(주 비교: A 대 C · C0 · E, 같은 창; 제외 구간을 뺀 창 3011개)

- A: 허용 안 2979(전체 3011, 95% 0.985~0.993)(우연 0.995), 후보가 있는 창 108(전체 140, 95% 0.667~0.857)(우연 0.885); 지정 지원과 같음 95(전체 1064, 95% 0.067~0.119)(우연 0.045); 고른 것 {'none': 2871, 'highlight_next_action': 106, 'large_button': 17, 'wait_hold_timer': 4, 'remaining_steps_notice': 13}
  - 구간 2×2: TP/FN/FP/TN = 53/13/7/79; 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 13(전체 66, 95% 0.119~0.308)(v0 행 있음 13(전체 66, 95% 0.119~0.308)), 제안 정밀도 53(전체 60, 95% 0.778~0.942); 2×2 밖 {'no_user': 56, 'allowed_not_designated': 13, 'time_stop': 21}
  - 지정 지원 자체를 시작 시각 이후 낸 구간(v0 행 있음): 53(전체 66, 95% 0.692~0.881); 규칙표 행이 없는 지정 구간(2×2 밖)에서 지정 지원 자체를 낸 구간: 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 낸 구간 4(전체 20)은 도움으로 세지 않음)
  - 도움 규칙: 시작 시각 이후 허용 도움(admissible help after onset; 같은 turn에서 연 지원이 시작 시각 이후 보이면 도움, 시작 시각 전에 열어 그때까지 보이면 지연 0). 시작 시각 전에 연 도움 2구간(앞선 초 [1.0, 3.0]), 지연 중앙값 3.235초(n 53); 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 41, 'FN': 13, 'designated_delivery': {'k': 41, 'n': 54}}}; 옛 규칙(시작 시각 이후 새 제안만) TP/FN 52/14, 지정 지원 {'k': 52, 'n': 66}
  - 허용 밖 결정의 분류(창 정답 태그 기준, 기술만, 인과 주장 아님): {'decision_errors': 32, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 23, 'observed_tag_unknown': 9, 'reference_missing': 0}
- 오프라인 기준(호출 없음, 후보가 있는 창 140개): 늘 none 140(전체 140, 95% 1.000~1.000), 늘 후보 108(전체 140, 95% 0.667~0.857), 철회된 지원이면 none 112(전체 140, 95% 0.722~0.869)(철회 목록을 아는 창 140개); 철회 규칙의 구간 2×2 TP/FN/FP/TN = 52/14/7/79
- C: 선택지(the sent question's options (a support besides none))가 있는 창 140개, 상태 {'answered': 140}
  - 첫 순서: 답한 창에서 허용 안 112(전체 140, 95% 0.722~0.869)(우연 0.885; 같은 창의 A 108(전체 140, 95% 0.667~0.857)); 규칙표로 채운 전체 2983(전체 3011, 95% 0.987~0.994); 지정 지원과 같음 54(전체 100, 95% 0.443~0.627)(우연 0.475); 고른 지원 확률 Brier 0.226 · ECE 0.335 · AUROC 0.099(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 137, 'order_disagree': 3}; 허용 안 110(전체 137, 95% 0.725~0.869)(우연 0.887); 같은 창의 A 106(전체 137, 95% 0.669~0.859); 순서 일관성 137(전체 140, 95% 0.952~1.000)(무작위 선택자 0.499, 합의 · 허용 0.442)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 52/14/7/79(A는 53/13/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 14(전체 66, 95% 0.131~0.325), 제안 정밀도 52(전체 59, 95% 0.775~0.941); 허용 밖 결정의 분류 {'decision_errors': 28, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 19, 'observed_tag_unknown': 9, 'reference_missing': 0}
  - 다음 창 적용: 짝 128개에서 C 105, 한 창 늦춘 A 102, 같은 창 A 128; 한 창 늦춘 A 전체 2772(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 52(전체 66, 95% 0.675~0.869); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 40, 'FN': 14, 'designated_delivery': {'k': 40, 'n': 54}}}; 시작 시각 전에 연 도움 2구간; 옛 규칙 TP/FN 51/15, 지정 지원 {'k': 51, 'n': 66}
  - 고르지 않은 창 46개(전체 140): {'kept_inadmissible_candidate': 28, 'declined_inadmissible_candidate': 4, 'kept_admissible_candidate': 66, 'declined_admissible_candidate': 42}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 118.5 대 실제 112; 철회 규칙 재현 138(전체 140, 95% 0.949~0.996)(철회된 후보에서 고르지 않음 45(전체 46), 처음 후보에서 1(전체 94))
- C0: 선택지(the sent question's options (a support besides none))가 있는 창 140개, 상태 {'answered': 140}
  - 첫 순서: 답한 창에서 허용 안 112(전체 140, 95% 0.722~0.869)(우연 0.885; 같은 창의 A 108(전체 140, 95% 0.667~0.857)); 규칙표로 채운 전체 2983(전체 3011, 95% 0.987~0.994); 지정 지원과 같음 53(전체 100, 95% 0.433~0.619)(우연 0.475); 고른 지원 확률 Brier 0.191 · ECE 0.236 · AUROC 0.294(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 138, 'order_disagree': 2}; 허용 안 110(전체 138, 95% 0.718~0.866)(우연 0.886); 같은 창의 A 107(전체 138, 95% 0.678~0.857); 순서 일관성 138(전체 140, 95% 0.966~1.000)(무작위 선택자 0.499, 합의 · 허용 0.442)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 52/14/7/79(A는 53/13/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 14(전체 66, 95% 0.131~0.325), 제안 정밀도 52(전체 59, 95% 0.775~0.941); 허용 밖 결정의 분류 {'decision_errors': 28, 'of_windows': 3011, 'with_incorrect_observed_tag': 0, 'with_correct_observed_tag': 19, 'observed_tag_unknown': 9, 'reference_missing': 0}
  - 다음 창 적용: 짝 128개에서 C 105, 한 창 늦춘 A 102, 같은 창 A 128; 한 창 늦춘 A 전체 2772(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 52(전체 66, 95% 0.675~0.869); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 40, 'FN': 14, 'designated_delivery': {'k': 40, 'n': 54}}}; 시작 시각 전에 연 도움 2구간; 옛 규칙 TP/FN 51/15, 지정 지원 {'k': 51, 'n': 66}
  - 고르지 않은 창 46개(전체 140): {'kept_inadmissible_candidate': 28, 'declined_inadmissible_candidate': 4, 'kept_admissible_candidate': 66, 'declined_admissible_candidate': 42}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 118.5 대 실제 112; 철회 규칙 재현 140(전체 140, 95% 0.973~1.000)(철회된 후보에서 고르지 않음 46(전체 46), 처음 후보에서 0(전체 94))
- J: 선택지(all supports + none)가 있는 창 3011개, 상태 {'not asked': 436, 'answered': 2575}; 기준이 선택지 밖 0(전체 3011), 규칙표 거름 밖을 고른 답 1943(전체 2575, 95% 0.731~0.774)
  - 첫 순서: 답한 창에서 허용 안 1445(전체 2575, 95% 0.461~0.669)(우연 0.593; 같은 창의 A 2543(전체 2575, 95% 0.983~0.992)); 규칙표로 채운 전체 1881(전체 3011, 95% 0.535~0.720); 지정 지원과 같음 195(전체 967, 95% 0.080~0.355)(우연 0.110); 고른 지원 확률 Brier 0.206 · ECE 0.094 · AUROC 0.646(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'not asked': 436, 'answered': 2309, 'order_disagree': 266}; 허용 안 1227(전체 2309, 95% 0.423~0.648)(우연 0.586); 같은 창의 A 2277(전체 2309, 95% 0.981~0.991); 순서 일관성 2309(전체 2575, 95% 0.883~0.910)(무작위 선택자 0.143, 합의 · 허용 0.085)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 46/20/63/23(A는 53/13/7/79); 거짓 경보 63(전체 86, 95% 0.631~0.815), 놓친 도움 20(전체 66, 95% 0.206~0.422), 제안 정밀도 46(전체 109, 95% 0.334~0.516); 허용 밖 결정의 분류 {'decision_errors': 1130, 'of_windows': 3011, 'with_incorrect_observed_tag': 7, 'with_correct_observed_tag': 1060, 'observed_tag_unknown': 63, 'reference_missing': 0}
  - 다음 창 적용: 짝 2398개에서 C 1364, 한 창 늦춘 A 2372, 같은 창 A 2377; 한 창 늦춘 A 전체 2772(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 41(전체 66, 95% 0.501~0.729); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 16(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 34, 'FN': 20, 'designated_delivery': {'k': 29, 'n': 54}}}; 시작 시각 전에 연 도움 20구간; 옛 규칙 TP/FN 46/20, 지정 지원 {'k': 41, 'n': 66}

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)

- B: normal Brier 0.233(기준율 0.239, skill 0.026) · ECE 0.171 · AUROC 0.693(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.198) · ECE 0.099 · AUROC 0.795(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.039 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.195(기준율 0.177, skill -0.105) · ECE 0.195 · AUROC 0.757(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.693(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.848(n 850), backs_recent 0.942 대 0.848(n 850), fixes_recent 0.322 대 0.848(n 850), condition_C2 0.322 대 0.795(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.730(n 850), backs_recent 0.942 대 0.730(n 850), fixes_recent 0.322 대 0.730(n 850), condition_C2 0.322 대 0.757(n 1287)
- C: normal Brier 0.233(기준율 0.239, skill 0.026) · ECE 0.171 · AUROC 0.693(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.860(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.198) · ECE 0.099 · AUROC 0.795(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.039 · AUROC 0.581(n 1287, 양성 213); hesitation Brier 0.195(기준율 0.177, skill -0.105) · ECE 0.195 · AUROC 0.757(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.821(n 850), backs_recent 0.309 대 0.821(n 850), fixes_recent 0.316 대 0.821(n 850), condition_C2 0.285 대 0.693(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.860(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.848(n 850), backs_recent 0.942 대 0.848(n 850), fixes_recent 0.322 대 0.848(n 850), condition_C2 0.322 대 0.795(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.581(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.730(n 850), backs_recent 0.942 대 0.730(n 850), fixes_recent 0.322 대 0.730(n 850), condition_C2 0.322 대 0.757(n 1287)

### 규칙표 자체 질문(proposal_fits, 보조)

- B: Brier 0.361 · ECE 0.402 · AUROC 0.442(n 120, 양성 97)
- C: Brier 0.361 · ECE 0.402 · AUROC 0.442(n 120, 양성 97)

### 다음 어려움 예측(D · E, 따로 셈)


### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 2979, 섞은 평균 2974.551, 범위 2964~2984
- 라벨을 섞음 · C selection (answered): 실제 112, 섞은 평균 114.184, 범위 107~123
- 라벨을 섞음 · C0 selection (answered): 실제 112, 섞은 평균 113.893, 범위 106~122
- 라벨을 섞음 · J selection (answered): 실제 1445, 섞은 평균 1440.318, 범위 1429~1457
- 라벨을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.144~0.150
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B hesitation Brier: 실제 0.195, 섞은 평균 0.202, 범위 0.200~0.205
- 라벨을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.144~0.150
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · C hesitation Brier: 실제 0.195, 섞은 평균 0.202, 범위 0.200~0.205
- 답을 섞음 · C selection (answered): 실제 112, 섞은 평균 112.471, 범위 112~113
- 답을 섞음 · C0 selection (answered): 실제 112, 섞은 평균 112.502, 범위 112~113
- 답을 섞음 · J selection (answered): 실제 1445, 섞은 평균 1455.056, 범위 1446~1463
- 답을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.239~0.247
- 답을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.152, 범위 0.149~0.156
- 답을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B hesitation Brier: 실제 0.195, 섞은 평균 0.206, 범위 0.202~0.210
- 답을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.243, 범위 0.238~0.247
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.153, 범위 0.149~0.156
- 답을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · C hesitation Brier: 실제 0.195, 섞은 평균 0.206, 범위 0.201~0.210

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 2979, 섞은 평균 2915.610, 범위 2900~2931
- 라벨을 섞음 · C selection (answered): 실제 112, 섞은 평균 75.114, 범위 61~89
- 라벨을 섞음 · C0 selection (answered): 실제 112, 섞은 평균 75.997, 범위 63~90
- 라벨을 섞음 · J selection (answered): 실제 1445, 섞은 평균 1309.871, 범위 1275~1351
- 라벨을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.321
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.202~0.232
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.173~0.194
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.152~0.168
- 라벨을 섞음 · B hesitation Brier: 실제 0.195, 섞은 평균 0.239, 범위 0.226~0.251
- 라벨을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.321
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.217, 범위 0.202~0.232
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.173~0.194
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.152~0.168
- 라벨을 섞음 · C hesitation Brier: 실제 0.195, 섞은 평균 0.239, 범위 0.226~0.251
- 답을 섞음 · C selection (answered): 실제 112, 섞은 평균 120.710, 범위 112~128
- 답을 섞음 · C0 selection (answered): 실제 112, 섞은 평균 121.091, 범위 113~128
- 답을 섞음 · J selection (answered): 실제 1445, 섞은 평균 1346.829, 범위 1316~1380
- 답을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.306, 범위 0.286~0.323
- 답을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.217~0.243
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.179~0.193
- 답을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.139~0.146
- 답을 섞음 · B hesitation Brier: 실제 0.195, 섞은 평균 0.241, 범위 0.226~0.252
- 답을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.306, 범위 0.289~0.325
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.218~0.244
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.186, 범위 0.179~0.194
- 답을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.138~0.146
- 답을 섞음 · C hesitation Brier: 실제 0.195, 섞은 평균 0.241, 범위 0.225~0.257
