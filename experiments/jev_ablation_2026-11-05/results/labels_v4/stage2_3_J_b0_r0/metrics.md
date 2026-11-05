# E5 지표: `stage2_3_J_b0_r0`

- 매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27` · 라벨 판 `v4` · 채점 판 `2026-11-05 Codex 209 (#1 exact no-row delivery, #2 time-mode onset, #3 paired AUROC, #4 window truth, #7 sent-question options)`
- Jev: `real` · 모델 `jev-1.13.0` · 라벨 `<workspace>/4_vision/eval_ab_2026-11-04/admissible_v4.csv`(admissible)
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
| J | 3892 | 3344 | 3344 | {'not measurable': 548} | support_choice | 3344 | 0 | 3344 | 3344 | 0 | 239 | 3105 | 240 | 185.7 · 266.3 · 700.9 | 168064 |

- 지연 측정: wall clock (time.perf_counter) around the client call of each API request; answers from the identical-request cache are excluded; machine and network of the run
- J: API 호출 479번, 캐시 답 6209개, 시도한 창마다 호출 0.14번, 2단계까지 간 창 3344(전체 3344); 사슬 전체 지연 p50 185.7 · p95 266.3 ms

## 같은 요청 점검(실행 동작)


## 같은 입력 반복(요청마다 1번)


## 답 요약

| arm | 단계 | 질문 | n | 평균 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| J | support_choice | support_choice(choice) | 3344 | {'remaining_steps_notice': 2162, 'none': 785, 'highlight_next_action': 378, 'large_button': 18, 'wait_hold_timer': 1} | conf 평균 0.436 | |

## 짝 비교(같은 창)


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
- J: 선택지(all supports + none)가 있는 창 3011개, 상태 {'not asked': 436, 'answered': 2575}; 기준이 선택지 밖 0(전체 3011), 규칙표 거름 밖을 고른 답 1877(전체 2575, 95% 0.693~0.758)
  - 첫 순서: 답한 창에서 허용 안 1431(전체 2575, 95% 0.460~0.659)(우연 0.593; 같은 창의 A 2541(전체 2575, 95% 0.982~0.991)); 규칙표로 채운 전체 1867(전체 3011, 95% 0.535~0.712); 지정 지원과 같음 182(전체 967, 95% 0.080~0.324)(우연 0.110); 고른 지원 확률 Brier 0.213 · ECE 0.055 · AUROC 0.604(고른 확률 대 허용; 게이트로 쓰지 않음)
  - 두 순서가 같을 때만: 상태 {'not asked': 436, 'answered': 2242, 'order_disagree': 333}; 허용 안 1149(전체 2242, 95% 0.410~0.627)(우연 0.590); 같은 창의 A 2208(전체 2242, 95% 0.979~0.990); 순서 일관성 2242(전체 2575, 95% 0.851~0.889)(무작위 선택자 0.143, 합의 · 허용 0.085)
  - 구간 2×2(답 없는 창은 규칙표): TP/FN/FP/TN = 44/22/63/23(A는 44/22/7/79); 거짓 경보 63(전체 86, 95% 0.631~0.815), 놓친 도움 22(전체 66, 95% 0.232~0.453), 제안 정밀도 44(전체 107, 95% 0.323~0.506); 허용 밖 결정의 분류 {'decision_errors': 1144, 'of_windows': 3011, 'with_incorrect_observed_tag': 6, 'with_correct_observed_tag': 992, 'observed_tag_unknown': 146, 'reference_missing': 0}
  - 다음 창 적용: 짝 2398개에서 C 1348, 한 창 늦춘 A 2370, 같은 창 A 2375; 한 창 늦춘 A 전체 2770(전체 2798)
  - 지정 지원 자체를 낸 구간(v0 행 있음): 38(전체 66, 95% 0.456~0.688); 행이 없는 지정 구간에서 지정 지원 자체 0(전체 20, 95% 0.000~0.161)(보이는 허용 형태만 16(전체 20), 도움 아님)
  - 출처별 {'camera': {'designated_v0_row': 12, 'TP': 10, 'FN': 2, 'designated_delivery': {'k': 9, 'n': 12}}, 'touch': {'designated_v0_row': 54, 'TP': 34, 'FN': 20, 'designated_delivery': {'k': 29, 'n': 54}}}; 시작 시각 전에 연 도움 20구간; 옛 규칙 TP/FN 44/22, 지정 지원 {'k': 38, 'n': 66}

### 상태 추정(B 등 state_scores, 상태 대응이 있는 창)


### 규칙표 자체 질문(proposal_fits, 보조)


### 다음 어려움 예측(D · E, 따로 셈)


### 섞은 대조(순열 1000번, seed 0; 위와 같은 점수 대상 창)

최소~최대 범위는 섞은 값이 낸 수의 폭일 뿐이고 유의성 검정이 아니다. 세션 안 대조와 전체 대조를 따로 적는다.

#### 세션 안에서 섞음

- 라벨을 섞음 · A selection: 실제 2977, 섞은 평균 2972.570, 범위 2961~2982
- 라벨을 섞음 · J selection (answered): 실제 1431, 섞은 평균 1425.668, 범위 1412~1436
- 답을 섞음 · J selection (answered): 실제 1431, 섞은 평균 1440.346, 범위 1433~1448

#### 전체에서 섞음

- 라벨을 섞음 · A selection: 실제 2977, 섞은 평균 2923.080, 범위 2910~2939
- 라벨을 섞음 · J selection (answered): 실제 1431, 섞은 평균 1307.687, 범위 1265~1349
- 답을 섞음 · J selection (answered): 실제 1431, 섞은 평균 1344.597, 범위 1301~1376
