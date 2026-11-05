# E5 지표: `stage2_4b_b2_rA`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `C:/Users/samsung-user/claude/Capstone_Design_Project/4_vision/eval_ab_2026-11-04/admissible_v4.csv`(admissible)
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
| A | 3892 | 3344 | 0 | 조건 A(묻지 않음) | - | - | - | - | - | - | - | - | - | - | - |
| B | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 11 | 3333 | 0 | 212.2 · 510.6 · 563.6 | 8074 |
| C | 3892 | 3344 | 3344 | {'not measurable': 548} | state_scores | 3344 | 0 | 3344 | 3344 | 0 | 0 | 3344 | 0 | - · - · - | 0 |
| | | | | | support_choice | 3344 | 3137 | 207 | 207 | 0 | 24 | 183 | 24 | 198.1 · 354.7 · 423.2 | 14774 |
| C0 | 3892 | 3344 | 3344 | {'not measurable': 548} | support_choice | 3344 | 3137 | 207 | 207 | 0 | 24 | 183 | 24 | 197.4 · 266.2 · 421.3 | 13070 |
| J | 3892 | 3344 | 3344 | {'not measurable': 548} | support_choice | 3344 | 0 | 3344 | 3344 | 0 | 160 | 3184 | 160 | 196.1 · 335.3 · 635.5 | 114328 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- B: API 호출 11번, 캐시 답 3333개, 시도한 창마다 호출 0.00번; 사슬 전체 지연 p50 212.2 · p95 510.6 ms
- C: API 호출 48번, 캐시 답 3710개, 시도한 창마다 호출 0.01번, 2단계까지 간 창 207(전체 3344); 사슬 전체 지연 p50 - · p95 - ms
- C0: API 호출 48번, 캐시 답 366개, 시도한 창마다 호출 0.01번, 2단계까지 간 창 207(전체 3344); 사슬 전체 지연 p50 0.0 · p95 0.0 ms
- J: API 호출 320번, 캐시 답 6368개, 시도한 창마다 호출 0.10번, 2단계까지 간 창 3344(전체 3344); 사슬 전체 지연 p50 196.1 · p95 335.3 ms

## 같은 요청 점검(실행 동작)

- C0 vs C, 단계 support_choice: 짝 창 207개, 요청이 같은 창 0개
- C vs B (state_scores), 단계 state_scores: 짝 창 3344개, 요청이 같은 창 3344개

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
| C | state_scores | hesitation | 3344 | 0.431 | 0.110 | 0.810 |
| C | state_scores | navigation_difficulty | 3344 | 0.217 | 0.040 | 0.640 |
| C | state_scores | normal | 3344 | 0.512 | 0.080 | 0.890 |
| C | state_scores | proposal_fits | 157 | 0.520 | 0.100 | 0.830 |
| C | state_scores | touch_difficulty | 3344 | 0.199 | 0.050 | 0.770 |
| C | state_scores | visual_difficulty | 3344 | 0.141 | 0.060 | 0.470 |
| C | support_choice | support_choice(choice) | 207 | {'highlight_next_action': 80, 'none': 63, 'large_button': 20, 'wait_hold_timer': 31, 'remaining_steps_notice': 13} | conf 평균 0.518 | |
| C0 | support_choice | support_choice(choice) | 207 | {'highlight_next_action': 81, 'none': 58, 'large_button': 19, 'wait_hold_timer': 35, 'remaining_steps_notice': 14} | conf 평균 0.494 | |
| J | support_choice | support_choice(choice) | 3344 | {'remaining_steps_notice': 2173, 'none': 684, 'highlight_next_action': 318, 'wait_hold_timer': 142, 'large_button': 18, 'defer_big_button_question': 9} | conf 평균 0.442 | |

## 짝 비교(같은 창)

- C0 vs C, support_choice: 가장 큰 상태 점수가 바뀐 창 0(전체 0); 고른 답이 바뀐 창 {'support_choice': '6(전체 207)'}
- C vs B (state_scores), state_scores: 가장 큰 상태 점수가 바뀐 창 0(전체 3344); 고른 답이 바뀐 창 없음
  - hesitation: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - navigation_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - normal: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - proposal_fits: n 157, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - touch_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000
  - visual_difficulty: n 3344, 평균 차 0.000, 평균 |차| 0.000, 최대 |차| 0.000

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
- C: 선택지(the sent question's options (a support besides none))가 있는 창 140개, 상태 {'answered': 140}
  - 첫 순서: 답한 창에서 허용 안 112(전체 140, 95% 0.722~0.869)(우연 0.885; 같은 창의 A 108(전체 140, 95% 0.667~0.857)); 규칙표로 채운 전체 2983(전체 3011, 95% 0.987~0.994); 지정 지원과 같음 53(전체 100, 95% 0.433~0.619)(우연 0.472); 고른 지원 확률 Brier 0.230 · ECE 0.339 · AUROC 0.098(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 138, 'order_disagree': 2}; 허용 안 111(전체 138, 95% 0.727~0.870)(우연 0.888); 같은 창의 A 107(전체 138, 95% 0.671~0.860); 순서 일관성 138(전체 140, 95% 0.965~1.000)(무작위 선택자 0.496, 합의 · 허용 0.439)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 52/14/7/79(A는 53/13/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 14(전체 66, 95% 0.131~0.325), 제안 정밀도 52(전체 59, 95% 0.775~0.941); 허용 밖 결정의 분류 {'decision_errors': 28, 'of_windows': 3011, 'with_incorrect_observed_tag': 1, 'with_correct_observed_tag': 21, 'observed_tag_unknown': 6, 'reference_missing': 0}
  - 다음 창 적용: 짝 128개에서 C 105, 한 창 늦춘 A 102, 같은 창 A 128; 한 창 늦춘 A 전체 2772(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 52(전체 66, 95% 0.675~0.869); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 40, 'FN': 14, 'designated_delivery': {'k': 40, 'n': 54}}}; 시작 시각 전에 연 도움 2구간; 옛 규칙 TP/FN 51/15, 지정 지원 {'k': 51, 'n': 66}
  - 고르지 않은 창 46개(전체 140): {'kept_inadmissible_candidate': 28, 'declined_inadmissible_candidate': 4, 'kept_admissible_candidate': 66, 'declined_admissible_candidate': 42}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 118.5 대 실제 112; 철회 규칙 재현 140(전체 140, 95% 0.973~1.000)(철회된 후보에서 고르지 않음 46(전체 46), 처음 후보에서 0(전체 94))
- C0: 선택지(the sent question's options (a support besides none))가 있는 창 140개, 상태 {'answered': 140}
  - 첫 순서: 답한 창에서 허용 안 112(전체 140, 95% 0.722~0.869)(우연 0.885; 같은 창의 A 108(전체 140, 95% 0.667~0.857)); 규칙표로 채운 전체 2983(전체 3011, 95% 0.987~0.994); 지정 지원과 같음 54(전체 100, 95% 0.435~0.636)(우연 0.472); 고른 지원 확률 Brier 0.195 · ECE 0.240 · AUROC 0.290(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'answered': 138, 'order_disagree': 2}; 허용 안 110(전체 138, 95% 0.718~0.866)(우연 0.886); 같은 창의 A 107(전체 138, 95% 0.678~0.857); 순서 일관성 138(전체 140, 95% 0.966~1.000)(무작위 선택자 0.496, 합의 · 허용 0.439)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 52/14/7/79(A는 53/13/7/79); 거짓 경보 7(전체 86, 95% 0.040~0.159), 놓친 도움 14(전체 66, 95% 0.131~0.325), 제안 정밀도 52(전체 59, 95% 0.775~0.941); 허용 밖 결정의 분류 {'decision_errors': 28, 'of_windows': 3011, 'with_incorrect_observed_tag': 1, 'with_correct_observed_tag': 21, 'observed_tag_unknown': 6, 'reference_missing': 0}
  - 다음 창 적용: 짝 128개에서 C 105, 한 창 늦춘 A 102, 같은 창 A 128; 한 창 늦춘 A 전체 2772(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 52(전체 66, 95% 0.675~0.869); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 4(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 40, 'FN': 14, 'designated_delivery': {'k': 40, 'n': 54}}}; 시작 시각 전에 연 도움 2구간; 옛 규칙 TP/FN 51/15, 지정 지원 {'k': 51, 'n': 66}
  - 고르지 않은 창 45개(전체 140): {'kept_inadmissible_candidate': 28, 'declined_inadmissible_candidate': 4, 'kept_admissible_candidate': 67, 'declined_admissible_candidate': 41}; 같은 수를 무작위로 고르지 않았을 때 허용 기대 118.3 대 실제 112; 철회 규칙 재현 139(전체 140, 95% 0.961~0.999)(철회된 후보에서 고르지 않음 45(전체 46), 처음 후보에서 0(전체 94))
- J: 선택지(all supports + none)가 있는 창 3011개, 상태 {'not asked': 436, 'answered': 2575}; 기준이 선택지 밖 0(전체 3011), 규칙표 거름 밖을 고른 답 1949(전체 2575, 95% 0.733~0.777)
  - 첫 순서: 답한 창에서 허용 안 1448(전체 2575, 95% 0.461~0.671)(우연 0.593; 같은 창의 A 2543(전체 2575, 95% 0.983~0.992)); 규칙표로 채운 전체 1884(전체 3011, 95% 0.536~0.722); 지정 지원과 같음 192(전체 967, 95% 0.079~0.351)(우연 0.110); 고른 지원 확률 Brier 0.206 · ECE 0.092 · AUROC 0.644(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'not asked': 436, 'answered': 2317, 'order_disagree': 258}; 허용 안 1236(전체 2317, 95% 0.424~0.650)(우연 0.587); 같은 창의 A 2286(전체 2317, 95% 0.981~0.992); 순서 일관성 2317(전체 2575, 95% 0.886~0.913)(무작위 선택자 0.143, 합의 · 허용 0.085)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 46/20/63/23(A는 53/13/7/79); 거짓 경보 63(전체 86, 95% 0.631~0.815), 놓친 도움 20(전체 66, 95% 0.206~0.422), 제안 정밀도 46(전체 109, 95% 0.334~0.516); 허용 밖 결정의 분류 {'decision_errors': 1127, 'of_windows': 3011, 'with_incorrect_observed_tag': 20, 'with_correct_observed_tag': 1032, 'observed_tag_unknown': 75, 'reference_missing': 0}
  - 다음 창 적용: 짝 2398개에서 C 1368, 한 창 늦춘 A 2372, 같은 창 A 2377; 한 창 늦춘 A 전체 2772(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 41(전체 66, 95% 0.501~0.729); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 16(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 12, 'FN': 0, 'designated_delivery': {'k': 12, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 34, 'FN': 20, 'designated_delivery': {'k': 29, 'n': 54}}}; 시작 시각 전에 연 도움 20구간; 옛 규칙 TP/FN 46/20, 지정 지원 {'k': 41, 'n': 66}

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)

- B: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.171 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.861(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.794(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.039 · AUROC 0.582(n 1287, 양성 213); hesitation Brier 0.196(기준율 0.177, skill -0.111) · ECE 0.194 · AUROC 0.748(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.820(n 850), backs_recent 0.309 대 0.820(n 850), fixes_recent 0.316 대 0.820(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.861(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.794(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.582(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.721(n 850), backs_recent 0.942 대 0.721(n 850), fixes_recent 0.322 대 0.721(n 850), condition_C2 0.322 대 0.748(n 1287)
- C: normal Brier 0.233(기준율 0.239, skill 0.025) · ECE 0.171 · AUROC 0.694(n 1287, 양성 507); touch_difficulty Brier 0.126(기준율 0.197, skill 0.358) · ECE 0.093 · AUROC 0.861(n 1287, 양성 346); navigation_difficulty Brier 0.142(기준율 0.177, skill 0.199) · ECE 0.097 · AUROC 0.794(n 1287, 양성 295); visual_difficulty Brier 0.137(기준율 0.138, skill 0.008) · ECE 0.039 · AUROC 0.582(n 1287, 양성 213); hesitation Brier 0.196(기준율 0.177, skill -0.111) · ECE 0.194 · AUROC 0.748(n 1287, 양성 295)
  - normal 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.276 대 0.820(n 850), backs_recent 0.309 대 0.820(n 850), fixes_recent 0.316 대 0.820(n 850), condition_C2 0.285 대 0.694(n 1287)
  - touch_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.946 대 0.937(n 850), backs_recent 0.314 대 0.937(n 850), fixes_recent 0.919 대 0.937(n 850), condition_C2 0.996 대 0.861(n 1287)
  - navigation_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.847(n 850), backs_recent 0.942 대 0.847(n 850), fixes_recent 0.322 대 0.847(n 850), condition_C2 0.322 대 0.794(n 1287)
  - visual_difficulty 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.557 대 0.589(n 850), backs_recent 0.464 대 0.589(n 850), fixes_recent 0.477 대 0.589(n 850), condition_C2 0.445 대 0.582(n 1287)
  - hesitation 입력 칸 하나의 AUROC 대 같은 창의 Jev AUROC(짝지은 비교): misses_recent 0.283 대 0.721(n 850), backs_recent 0.942 대 0.721(n 850), fixes_recent 0.322 대 0.721(n 850), condition_C2 0.322 대 0.748(n 1287)

### 규칙표 자체 질문(proposal_fits, 보조)

- B: Brier 0.371 · ECE 0.404 · AUROC 0.408(n 122, 양성 96)
- C: Brier 0.371 · ECE 0.404 · AUROC 0.408(n 122, 양성 96)

### 다음 어려움 예측(D · E, 따로 셈)


### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 2979, 섞은 평균 2974.397, 범위 2963~2984
- 라벨을 섞음 · C selection (answered): 실제 112, 섞은 평균 114.129, 범위 104~123
- 라벨을 섞음 · C0 selection (answered): 실제 112, 섞은 평균 113.845, 범위 104~122
- 라벨을 섞음 · J selection (answered): 실제 1448, 섞은 평균 1443.187, 범위 1432~1459
- 라벨을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · B hesitation Brier: 실제 0.196, 섞은 평균 0.203, 범위 0.201~0.206
- 라벨을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.240, 범위 0.236~0.244
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.131
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.147, 범위 0.145~0.150
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 라벨을 섞음 · C hesitation Brier: 실제 0.196, 섞은 평균 0.203, 범위 0.201~0.206
- 답을 섞음 · C selection (answered): 실제 112, 섞은 평균 112.524, 범위 112~113
- 답을 섞음 · C0 selection (answered): 실제 112, 섞은 평균 112.504, 범위 112~113
- 답을 섞음 · J selection (answered): 실제 1448, 섞은 평균 1458.007, 범위 1449~1466
- 답을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.244, 범위 0.239~0.248
- 답을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.126~0.132
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.153, 범위 0.149~0.156
- 답을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · B hesitation Brier: 실제 0.196, 섞은 평균 0.207, 범위 0.203~0.211
- 답을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.244, 범위 0.238~0.247
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.129, 범위 0.127~0.132
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.153, 범위 0.148~0.156
- 답을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.137, 범위 0.137~0.137
- 답을 섞음 · C hesitation Brier: 실제 0.196, 섞은 평균 0.207, 범위 0.204~0.211

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 2979, 섞은 평균 2915.585, 범위 2901~2939
- 라벨을 섞음 · C selection (answered): 실제 112, 섞은 평균 75.720, 범위 62~89
- 라벨을 섞음 · C0 selection (answered): 실제 112, 섞은 평균 75.230, 범위 61~90
- 라벨을 섞음 · J selection (answered): 실제 1448, 섞은 평균 1312.121, 범위 1274~1358
- 라벨을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.321
- 라벨을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.216, 범위 0.200~0.231
- 라벨을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.171~0.195
- 라벨을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.152~0.169
- 라벨을 섞음 · B hesitation Brier: 실제 0.196, 섞은 평균 0.238, 범위 0.227~0.251
- 라벨을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.301, 범위 0.283~0.321
- 라벨을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.216, 범위 0.200~0.231
- 라벨을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.182, 범위 0.171~0.195
- 라벨을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.160, 범위 0.152~0.169
- 라벨을 섞음 · C hesitation Brier: 실제 0.196, 섞은 평균 0.238, 범위 0.227~0.251
- 답을 섞음 · C selection (answered): 실제 112, 섞은 평균 120.721, 범위 113~127
- 답을 섞음 · C0 selection (answered): 실제 112, 섞은 평균 120.734, 범위 114~128
- 답을 섞음 · J selection (answered): 실제 1448, 섞은 평균 1348.861, 범위 1317~1383
- 답을 섞음 · B normal Brier: 실제 0.233, 섞은 평균 0.305, 범위 0.288~0.324
- 답을 섞음 · B touch_difficulty Brier: 실제 0.126, 섞은 평균 0.230, 범위 0.217~0.243
- 답을 섞음 · B navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.187, 범위 0.179~0.193
- 답을 섞음 · B visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.139~0.146
- 답을 섞음 · B hesitation Brier: 실제 0.196, 섞은 평균 0.240, 범위 0.227~0.253
- 답을 섞음 · C normal Brier: 실제 0.233, 섞은 평균 0.305, 범위 0.287~0.325
- 답을 섞음 · C touch_difficulty Brier: 실제 0.126, 섞은 평균 0.231, 범위 0.217~0.244
- 답을 섞음 · C navigation_difficulty Brier: 실제 0.142, 섞은 평균 0.187, 범위 0.180~0.196
- 답을 섞음 · C visual_difficulty Brier: 실제 0.137, 섞은 평균 0.142, 범위 0.138~0.146
- 답을 섞음 · C hesitation Brier: 실제 0.196, 섞은 평균 0.240, 범위 0.228~0.253
