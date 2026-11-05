# E5 Jev ablation 실험 패키지 (2026-11-05)

- 작성일: 2026-11-05 (wdragon92)
- 대상: PR #77(판단 모듈, 브랜치 `feat/jev`) 작성자와 AI 담당
- 목적: PR #77의 판단 모듈 위에서 Jev를 더한 판단이 규칙표만 쓴 판단보다 나은지 본 실험(E5)을 직접 다시 돌리고 결과를 읽을 수 있게, 실행기 · 입력 · 기록한 Jev 답 · 채점 결과를 이 폴더에 묶었습니다.
- 원본: wdragon92 작업 공간의 `4_vision/eval_jev_2026-11-04/`입니다. `results/`는 그 결과 묶음 `real_2026-11-05_3c936ae`(매니페스트 `real_2026-11-05_3c936ae-v4-219d93fe6d27`)의 채점 결과와 답 캐시를 그대로 옮긴 것입니다.
- 읽을 때: 모든 수는 녹화한 카메라 관측에 합성 터치를 더한 명세 시험의 결과입니다. 판단 라벨 v4는 규칙으로 정한 허용 행동(규정한 허용 행동)이고, 관찰한 사용자의 필요가 아닙니다. 라벨이 아직 검토 중이라 아래 수는 모두 잠정값입니다.

## 0. 결과

PR #77 커밋 `3c936ae`, 모델 `jev-1.13.0`, 판단 라벨 v4, 값 묶음 `b0_r0`의 결과입니다. 구간은 판단 라벨 한 줄이 덮는 영상의 시간 범위이고, 규칙표 v0에 행이 있는 지정 구간이 66개, 기다림만 허용된 구간이 86개입니다.

| 정책 | 상황 태그 | 허용 도움 | 거짓 경보 | 지정 지원 전달 |
|---|---|---:|---:|---:|
| A: 규칙표만 | 재생 태그 | 44/66 | 7/86 | 42/66 |
| C: 상태 점수 뒤 거른 후보 + `none` 고르기 | 재생 태그 | 43/66 | 7/86 | 41/66 |
| C0: 거른 후보 + `none` 고르기만 | 재생 태그 | 43/66 | 7/86 | 41/66 |
| J: 거름 없이 지원 6개 + `none` 고르기 | 재생 태그 | 44/66 | 63/86 | 38/66 |
| A_GT: 규칙표만 | 검증한 기준 태그 | 53/66 | 7/86 | 53/66 |
| C_GT: C와 같음 | 검증한 기준 태그 | 52/66 | 7/86 | 52/66 |

- 허용 도움은 지정 구간 가운데 '시작 시각 이후 허용 도움'(1장)이 있는 구간입니다. 거짓 경보는 기다림만 허용된 구간 가운데 새로 보인 선택이 있는 구간입니다. 지정 지원 전달은 같은 규칙을 지정 지원 자체로 좁힌 수입니다.
- 재생 태그는 비전 재생이 값 묶음 `b0_r0`로 낸 상황 태그입니다(3,892창 가운데 태그 없음 3,143 · unknown 749로, 상황 태그가 하나도 나오지 않음). 검증한 기준 태그는 창 라벨(VLM 라벨을 영상 조각으로 다시 확인한 판, `inputs/labels/window_labels_v1_verified.csv`)의 태그입니다.
- 출처: `results/stage2_summary_v4.txt`의 첫 표. A · C · C0는 `results/labels_v4/stage2_1_swap_C_C0/`, J는 `stage2_3_J_b0_r0/`, A_GT · C_GT는 `stage2_5_GT_b0_r0/`의 `metrics.md`입니다.

찾은 것(원본 README, 곧 작성자 작업 공간의 `4_vision/eval_jev_2026-11-04/README.md` §0 '찾은 것' 1~13에서 추림):

1. 거른 Jev(C · C0)는 구간 단위로 규칙표(A)보다 나아지지 않았습니다. 상황 태그가 나오는 값 묶음 `b0_rA` · `b2_rA`에서도 C의 허용 도움이 A보다 하나 적습니다(52 대 53/66).
2. C의 고르기는 '같은 세션에서 철회된 지원은 다시 열지 않는다'는 규칙을 거의 그대로 재현했습니다(후보가 있는 창 125개 가운데 124개가 규칙과 같음). 고르기 state에서 `session.withdrawn` · `session.held`를 빼면(C:nohistory) 거절이 0/125였습니다.
3. 거르지 않은 J는 허용 도움을 늘리지 못했고(44/66), 거짓 경보를 7에서 63/86으로 늘렸습니다. J가 고른 답의 73%(1,877/2,575)는 규칙표가 거른 후보 밖이었습니다.
4. 상황 태그를 검증한 창 라벨의 태그로 바꾸면(A_GT) 허용 도움이 44에서 53/66으로 늘었고, 늘어난 곳은 카메라 지정 구간(4/12 → 12/12)입니다. 태그에 대한 민감도이고, 인식이 완벽할 때의 상한은 아닙니다.
5. 상태 점수(`state_scores`)의 터치 어려움 AUROC는 같은 850창에서 0.937로, 입력 칸 하나 `misses_recent`(0.946)보다 낮았습니다. 헤맴도 0.847로 `backs_recent`(0.942)보다 낮았고, 시각 어려움은 둘 다 0.6 아래입니다(0.589 · 0.557).
6. 고른 지원의 확률과 허용 여부의 AUROC는 C 0.104, C0 0.236이었습니다(n 125). 확률을 지원을 켜는 문턱으로 쓸 근거는 나오지 않았고, 어떤 문턱도 정하지 않았습니다.
7. 같은 요청을 5번 보내면 고르기 요청 75개 가운데 C는 73개, C0는 74개에서 5번 모두 같은 답을 냈습니다. 후보 순서를 뒤집어도 C의 답은 123/125창에서 같았습니다.
8. 다음 10초 어려움 예측(D)은 1,170창 가운데 461창을 맞혀, B의 지금 최고 상태를 그대로 이어 쓴 기준(664창)보다 낮았습니다.

이 실험으로 뒷받침하지 못하는 주장(원본 README §0 원문):

- Jev를 더하면 규칙표보다 도움 판단이 낫다(구간 단위 개선 없음; 창 단위 차이는 철회 규칙 하나로 거의 설명됨).
- Jev의 확률을 지원을 켜는 문턱으로 쓸 수 있다(거른 선택에서 확률과 허용 여부가 반대로 움직임).
- 상태 점수가 실제 사용자의 어려움을 알아본다(라벨 양성이 합성 터치 조건에서 나오고, 같은 창에서 입력 칸 하나보다 낮음; 시각은 둘 다 0.6 아래).
- 비전 입력이 상태 판단에 기여한다, 또는 기여하지 않는다(합성 터치 창의 목표는 터치 조건이 만들고, 비전 칸을 빼면 AUROC가 0.037 이하로 움직임; 비전 창 양성 11개, 동등성 기준 없음, `b0_r0`에는 태그가 없음).
- Jev가 다음 어려움을 미리 안다(D가 B의 현재 상태를 이어 쓴 기준보다 낮음, 461 대 664 / 1,170).
- 거름 없는 Jev가 규칙표보다 쓸 만하다(도움으로 인정된 구간이 늘지 않고 거짓 경보가 63 대 7).
- 기준 태그로 바꾼 수가 인식이 완벽할 때의 상한이다(태그 민감도일 뿐).
- 실제 사용자에게 도움이 된다(그림자 재생, 반응 없는 녹화, 합성 터치, 검토 중인 라벨).
- 다른 모델 판 · 다른 질문 문안 · 다른 값 묶음 전체에서도 같다(`jev-1.13.0`, 한 문안, 묶음 3개).

## 1. 실험이 묻는 것

규칙표 v0만 쓴 지원 결정(조건 A)과, 같은 창에서 Jev에게 상태 · 지원 · 다음 어려움을 물은 결정(B · C · C0 · D · E · J)을 견줍니다. 지원 선택은 판단 라벨의 허용 행동으로 채점하고, 상태 점수는 장면이 정한 상태 목표에 대한 AUROC · Brier로 셉니다.

- 판단 모듈: PR #77의 `backend/app/modules/decision/`를 고치지 않고 불러 씁니다. 창마다 규칙표 `tick → decide → apply`를 돌리고, arm마다 PR의 `DecisionService.ask_shadow`로 Jev 단계를 부릅니다. 실행기는 창 기록에서 `WindowInput`을 직접 만들고, `DecisionRepository.add_window`에 넣는 `WindowRecord`만 만들어 줍니다(`tools/run_jev_ablation.py` `add_window`).
- 입력: 10-28 팀 촬영 35개의 카메라 관측에 합성 터치 조건 7개(C0~C6)를 넣은 창 3,892개(값 묶음마다)와, 터치 없는 비전 창 556개입니다(3장).
- 점수 대상: 라벨이 붙은 창 가운데 제외 구간과 모순 칸(누름이 없어야 하는 장면 × 누름이 있는 터치 조건)을 뺀 창입니다. `b0_r0`에서 3,011창이고, 모든 합성 터치 실행이 같은 3,011창을 씁니다.
- 그림자 흐름 가정: 녹화 속 사용자는 지원에 반응하지 않고, Jev의 선택은 다음 창의 세션 상태를 바꾸지 않습니다(PR의 그림자 모드: 결정은 규칙표가 하고 Jev 답은 기록만 함). 그래서 Jev가 고른 지원이 화면에 보이는 시간은 규칙표 흐름 위에서 다시 만듭니다. 규칙표가 같은 지원을 유지(keep)하는 동안은 보이고, 유지하지 않으면 한 창 동안만 보입니다(`tools/metrics.py` `policy_records`). Jev의 선택을 실제로 적용한 닫힌 고리 비교는 하지 않았습니다.
- 시점: PR 구현대로 한 창의 단계들은 차례로 돌고, 2단계는 같은 창의 1단계 답을 봅니다. 오프라인에서는 측정 가능한 창마다 단계가 끝날 때까지 기다립니다(운영 서비스라면 호출이 진행 중이라 건너뛰었을 창은 표시만 함).

도움 규칙 '시작 시각 이후 허용 도움'은 E3(같은 녹화의 규칙표 평가)와 같은 규칙이고, 코드는 `tools/e3/help_rule.py`입니다.

1. 표시 하나는 구간(차례) 안에서 연(open · replace) 보이는 지원(묻기 · 바로 적용 · 직원 호출)입니다. 뒤 창들이 같은 지원을 유지하는 동안 이어지고, 유지하지 않는 첫 창에서 끝납니다.
2. 도움은 구간 시작 시각 이후 어느 때든 보인 표시 가운데 그때 허용된 형태인 것입니다. 시작 시각 전에 같은 차례 안에서 열어 시작 시각에도 보이던 표시도 셉니다. 구간 시작 시각은 그 구간 지정들의 가장 이른 시작 시각입니다(`admissible_v4.csv` `onset_s`).
3. 앞 차례에서 연 제안은 세지 않습니다. 창 끝이 차례 시작과 같은 창은 앞 차례의 시간만 담으므로, 그 창에서 연 제안도 앞 차례의 것입니다.
4. 지연은 max(0, 연 시각 − 시작 시각)입니다. 거짓 경보는 기다림만 허용된 구간에서 새로 보인 선택이 있는 구간입니다.

원문은 작성자 작업 공간의 `4_vision/eval_ab_2026-11-04/JUDGMENT_PROTOCOL.md` §v4-1이고, 지표의 공식과 분모는 `tools/metrics.py`의 `FORMULAS`에 있습니다.

## 2. 조건(arm)과 변형: PR #77의 이름으로

arm 하나는 PR의 `JEV_STAGES` 값 하나입니다(`build_stages()`가 만든 단계를 실행기가 arm마다 넘김).

| arm | `JEV_STAGES` | PR #77의 단계(`jev_questions.py`) | 묻는 것 |
|---|---|---|---|
| A | `off` | 없음 | 규칙표 v0(`rule_table.py`)의 결정만 |
| B | `state_scores` | `ScoreStage` | 계약 `StateScores` 5개(`STATE_QUESTIONS`의 noul 질문: `touch_difficulty` · `navigation_difficulty` · `visual_difficulty` · `hesitation` · `normal`)와 규칙표 자체 질문(`decision.jev_request`의 `proposal_fits` 또는 `queue_support`) |
| C | `state_scores,support_choice` | `ScoreStage` → `SupportChoiceStage` | B 다음 같은 창에서 `allowed_supports()`가 거른 후보 + `none` 가운데 하나(1단계 답은 `state.jev`에 들어감) |
| C0 | `support_choice` | `SupportChoiceStage` | C에서 1단계를 뺀 대조(같은 입력 · 후보 · 질문) |
| D | `state_scores,next_difficulty` | `ScoreStage` → `NextDifficultyStage` | 세션의 앞 창들(`state.history`, `HISTORY_WINDOWS` = 5)로 다음 `FORECAST_HORIZON_S` = 10초의 어려움 예측 |
| E | `state_scores,support_choice,next_difficulty` | 세 단계 | 세 단계 모두 |
| J | `JEV_STAGES` 값이 아님 | 실행기의 `JevAloneStage` | PR의 `SupportChoiceStage` 질문을 규칙표 지원 6개 전부 + `none`으로 묻고 규칙표 거름을 쓰지 않음(선택지 문장은 `rule_table.WHAT`) |

변형은 PR 단계의 `build()`가 만든 state · 질문만 바꿉니다(`tools/run_jev_ablation.py` `VariantStage`). state 칸 이름은 `rule_table.jev_state()`와 `jev_questions.shadow_state()`의 것입니다.

| 변형 | 바꾸는 것 |
|---|---|
| B:novision | `state.situation` · `state.vision`을 null로(예측 단계의 `history[*].tag`도) |
| B:notouch | `state.touch`를 null로(예측 단계의 `history[*].touch`도) |
| B:la_null | 상황을 모르는 창의 `state.vision.looking_around`를 null로. `3c936ae`는 이미 null을 보내서 `b0_r0`에서는 B와 요청이 모두 같았습니다(3,344/3,344) |
| B:sit_dict | 상황 태그가 unknown인 창에서도 상황 칸을 넘겨 `state.situation.tag`가 null 대신 `"unknown"`이 됨. `b0_r0`에서는 B와 요청이 모두 같았습니다 |
| B:vision_summary | 창 기록의 비전 요약 7칸(`frames`, `face_seen_ratio`, `body_seen_ratio`, `head_count_max`, `people_behind_max`, `companion_frames`, `mouth_motion_max`)을 `state.vision`에 더함 |
| B:wording_nocrit | 상태 질문 5개를 `criteria` 없이 `instructions`만으로 보냄 |
| B:perm_vision | `state.situation` · `state.vision`을 같은 세션의 다른 측정 가능 창 값으로 바꿈(seed 0 순열, 섞은 값 대조) |
| B:perm_touch | `state.touch`를 같은 방식으로 바꿈 |
| C:nohistory | 고르기 단계 state에서 `state.session.withdrawn` · `state.session.held`를 뺌 |
| A_GT · C_GT | `--tag-source verified`: 상황 태그를 검증한 창 라벨(`inputs/labels/window_labels_v1_verified.csv`)에서 가져옴 |

고르기 단계는 같은 창에서 후보 순서(`criteria`와 `state.candidates`)를 뒤집어 한 번 더 묻고, 두 순서의 답이 같은 창을 따로 셉니다.

## 3. 입력

| 경로 | 내용 | 원본(작성자 작업 공간) |
|---|---|---|
| `inputs/aligned/<영상>.jsonl.gz` (35개) | 창 × 터치 조건 C0~C5의 합성 터치 값, 배치 `fit-medium`, 재생 창의 비전 요약, `segment_id` | `4_vision/eval_ab_2026-11-04/aligned/` |
| `inputs/aligned_touch_none/<영상>.jsonl.gz` (35개) | 같은 창의 C6(터치 칸이 모두 비어 있음) | `4_vision/eval_ab_2026-11-04/aligned_touch_none/` |
| `inputs/e3_windows/windows_{b0_r0,b0_rA,b2_rA}.csv.gz` | 값 묶음마다 다시 계산한 상황 태그 · 시선 · 측정 가능 · 세션 전환(AB0 줄), 대조용 AB0 결정 | `4_vision/eval_ab_2026-11-04/results/labels_v2/` |
| `inputs/vision_round3/<영상>/windows.jsonl.gz` · `windows_b0.jsonl.gz` | 터치 없는 비전 창 556개(값 묶음 없음 · `b0`) | `4_vision/companion_behind_2026-11-04/round3_replay/team_2026-10-28/` |
| `inputs/labels/judgment_labels_v4.csv` | 판단 라벨 v4: 구간 · 허용 행동 · 지정 지원 · 시작 시각 | `4_vision/eval_ab_2026-11-04/` |
| `inputs/labels/admissible_v4.csv` | 구간 × 터치 조건 × 배치마다 허용 형태 · 지정 지원 · 시작 시각 · 모순 칸 | `4_vision/eval_ab_2026-11-04/` |
| `inputs/labels/window_labels_v1_verified.csv` | 검증한 창 라벨(A_GT · C_GT의 기준 태그) | `datasets/team_recording_2026-10-28/labels/` |
| `inputs/labels/ledger.csv` | 영상 · 차례 · 구간 · 창을 받고 남기고 뺀 장부(실행기는 읽지 않음) | `4_vision/eval_ab_2026-11-04/` |
| `inputs/bundles/*.json` (12개) | E3 값 묶음(상황 창 길이 `window_s`, 역할 경계) | `4_vision/eval_ab_2026-11-04/bundles/` |
| `inputs/synthetic_touch.md` | 합성 터치 조건 7개의 출처와 뜻, 모순 칸 | 이 패키지에서 씀 |
| `inputs/SHA256SUMS.json` | 파일마다 sha256, 원본 경로, 기록한 해시와 같은지(160개 가운데 159개 같음, `ledger.csv`는 기록한 해시 없음) | 이 패키지에서 만듦 |
| `fixtures/` | 손으로 쓴 시험 입력 7테이크 38창과 기대 결정(stub 확인용, 값은 모두 시험용) | `4_vision/eval_jev_2026-11-04/fixtures/` |

- 영상 · 얼굴 좌표 · 음성은 없습니다. 창마다 비전 요약 수치와 상황 태그 이름만 있습니다.
- `.gz` 파일: `inputs/aligned/`, `inputs/aligned_touch_none/`, `inputs/vision_round3/`, `results/jev_cache.jsonl.gz`는 이 패키지를 만들며 `gzip -n -9`로 묶었고, 압축을 푼 내용의 sha256이 원본과 같습니다. `inputs/e3_windows/`는 E3가 `.gz`로 둔 파일을 그대로 옮겼습니다. 도구가 `.gz`를 바로 읽으니 풀 필요가 없습니다.

## 4. 실행 방법

명령은 Windows PowerShell 기준이고, 2단계부터는 이 폴더(`experiments/jev_ablation_2026-11-05/`)에서 돌립니다. 3·4단계는 API를 부르지 않고 키도 읽지 않습니다.

1. **PR #77 코드를 받고 실행기에 알려 주세요.** 실행기는 `backend/` 폴더를 `sys.path`에 넣어 판단 모듈을 불러옵니다. 그 폴더는 git 작업 사본이어야 합니다(실행 때 커밋을 기록하고, 다시 채점할 때 같은 커밋인지 확인함).

   ```powershell
   # 저장소 루트에서
   git fetch origin
   git worktree add ..\wt_jev 3c936ae          # PR #77이 병합된 뒤에는 main의 backend를 써도 됩니다
   $env:E5_BACKEND = (Resolve-Path ..\wt_jev\backend).Path
   cd experiments\jev_ablation_2026-11-05
   python -B tools\check_backend.py            # 기대: 8 of 8 files equal to 3c936ae
   ```

   `check_backend.py`는 실행기가 불러오는 파일 8개가 `3c936ae`와 같은지 봅니다(줄바꿈 CRLF · LF는 가리지 않음). 8개가 모두 같으면 main이어도 판단 모듈은 기록한 실행과 같습니다. 다르면 다시 돌린 결과가 기록과 달라질 수 있습니다.

2. **Python 환경을 만드세요.** 기록한 실행은 Python 3.12.10, pydantic 2.11.4, pydantic-settings 2.9.1, httpx 0.28.1로 돌았습니다. PR 코드가 `typing.Self`를 써서 Python 3.11 이상이 필요합니다.

   ```powershell
   py -3.12 -m venv .venv                       # .venv는 저장소 .gitignore가 뺍니다
   .\.venv\Scripts\python.exe -m pip install -r $env:E5_BACKEND\requirements.txt
   $PY = ".\.venv\Scripts\python.exe"
   ```

   실행기가 쓰는 패키지는 pydantic, pydantic-settings(`.env`를 읽는 python-dotenv가 함께 깔림), httpx입니다. `backend/requirements.txt`(3c936ae: fastapi, uvicorn, pydantic, pydantic-settings, httpx)를 깔면 모두 들어옵니다. 이 패키지의 도구(`metrics.py` 등)는 표준 라이브러리만 씁니다(numpy 필요 없음).

3. **stub으로 동작을 확인하세요(호출 0번).** stub은 해시로 만든 가짜 답이라 Jev 결과가 아닙니다.

   ```powershell
   & $PY -B tools\run_jev_ablation.py --jev stub --stub-fail-every 7 --input fixtures\windows --labels fixtures\fixture_labels.csv --out runs\stub_fixture
   & $PY -B tools\metrics.py --run runs\stub_fixture --null-perms 100
   ```

   기대: 끝 줄 "done: 38 windows in 7 takes, 622 stub calls (fake answers, nothing sent)", `runs\stub_fixture\metrics.md`에 "fixture 기대값: 38개 확인, 어긋남 0개"와 Jev 칸의 "평가하지 않음". 작성자 PC에서 실행 0.6초, 지표 3초가 걸렸습니다.

4. **기록한 묶음을 캐시로 다시 만드세요(호출 0번).** 답은 `results/jev_cache.jsonl.gz`에서만 가져오고(읽기만 함), 캐시에 없는 요청은 답 없음(`cache miss`)으로 따로 셉니다.

   ```powershell
   & $PY -B tools\run_set.py --jev cache --items stage2_1_swap_C_C0 --rescore --compare   # 실행 하나
   & $PY -B tools\run_set.py --jev cache --rescore --compare                              # 13개 전부
   ```

   - 출력: `runs\cache\<실행>\`(실행 파일), `runs\cache\labels_v4\<실행>\metrics.{md,json}`, `runs\cache\run_log.json`. `--compare`는 새 `metrics.json`을 `results\labels_v4\<실행>\metrics.json`과 값마다 견주고 "scores identical"을 찍습니다(`tools/compare_metrics.py`).
   - 작성자 PC에서 확인한 것(2026-11-05): `stage2_1_swap_C_C0`(실행 5.6초 + 채점 63초), `stage2_2_C_nohistory`(3.4초 + 148초, 답 핀 1개), `stage2_6_vision_b0`(0.7초 + 20초) 세 실행에서 API 호출 0번, 캐시에 없는 요청 0개, 채점 수가 `results/labels_v4/`와 모두 같았습니다. 나머지 10개는 이 패키지로 돌려 보지 않았습니다. 13개의 채점은 2026-11-05 기록으로 약 1시간(04:56~05:57)이 걸렸습니다.
   - 기록과 다르게 나오는 칸: `metrics.md` 머리의 Jev 칸(`cache`)과 라벨 경로, 그리고 기록 때 API를 부른 실행의 실행 표(API 호출 · 지연 · 토큰은 API 답에만 있고 캐시 답에는 없음).
   - 답 핀: 같은 요청이 같은 순간 두 번 나가(테이크 2개를 동시에 물음) 답이 둘 저장된 요청이 캐시에 198개 있습니다. 캐시 모드는 뒤 답을 주므로, 기록한 실행이 다른 답을 쓴 71곳(실행 8개)은 `results/answer_pins.json`이 그 실행이 쓴 답을 돌려줍니다.
   - 메모리: stage1(창 3,892개 × arm 14개)이 가장 큽니다. 2026-11-05 첫 실제 실행은 작성자 PC의 남은 메모리가 145 MB까지 줄어 멈췄습니다. 멈추면 같은 명령을 다시 돌리세요.

5. **본인 키로 실제 실행을 하세요(유료).**
   - 키: `$env:E5_BACKEND\.env`에 `JEV_API_KEY` 줄(등호 뒤에 본인 키)을 두거나, 환경변수 `JEV_API_KEY`를 쓰세요. 실행기는 키를 출력하지 않고, `run_settings.json`의 `key`에는 출처(환경변수 또는 파일 경로)만 적습니다. `.env`는 저장소 `.gitignore`가 빼지만, 커밋 전에 한 번 더 확인하세요.

   ```powershell
   & $PY -B tools\run_set.py --jev real --concurrency 2 --rescore
   ```

   - 출력: `runs\real_<날짜>\`. 새 캐시 `runs\real_<날짜>\jev_cache.jsonl`을 실행 13개가 함께 써서, 앞 실행에서 물은 요청은 다시 묻지 않습니다. 끊기면 같은 명령으로 이어 갑니다. 이번 명령에서 부를 호출 수에 상한을 두려면 `--cap N`을 더하세요. `--items`로 실행 몇 개만 고를 수도 있습니다.
   - 예상 호출: 13개 전부 14,848번입니다. 서로 다른 요청 11,288개(상태 점수 5,997 · 다음 어려움 3,537 · 고르기 1,754), 순서를 뒤집은 고르기 1,754번, 반복 1,806번(stage3 a1 600 · a2 836 · `vision_only_round3` 370)입니다. 기록한 실행의 요청을 세어 낸 수이고, 답이 없으면 같은 요청을 다시 부르므로 조금 늘 수 있습니다.
   - 예상 비용: 이 요청들의 입력 토큰은 기록한 usage로 약 1,330만 개(호출당 평균 896개)입니다. 입력 100만 토큰당 $0.042(LiteLLM · Maxim의 제3자 가격표, TypeSafe 자체 가격 안내는 확인하지 못함), 출력 무료로 셈하면 약 $0.56입니다.
   - 예상 시간: 기록한 응답 시간의 중앙값이 0.19초(답 21,736개)라서, 한 번에 하나씩 부르면 약 47분입니다. `--concurrency 2`(기록한 실행의 설정)면 약 30분입니다(2026-11-05 1단계 첫 시도: 3,339번에 6분 45초).
   - 요청 한도는 알려져 있지 않습니다. HTTP 429 · 529가 오면 실행기가 1초부터 두 배씩 기다려 최대 5번 다시 부르고(`--backoff-base-s`, `--backoff-tries`), 실패가 호출의 1%를 넘으면 멈춥니다(`--max-failure-rate`).
   - 모델은 PR 설정의 기본값 `jev-1.13.0`입니다(`JEV_MODEL`로 바꿀 수 있음). 기록과 견주려면 그대로 두세요.
   - 같은 요청에도 Jev 답이 조금씩 달라서(0장 7번), 새 실행의 수는 기록과 조금 다를 수 있습니다. 그 차이로 0장의 결론이 유지되는지 볼 수 있습니다.

6. **다시 채점하고 결과를 읽으세요(호출 0번).** `run_set.py --rescore`가 실행마다 아래 첫 명령을 부릅니다.

   ```powershell
   & $PY -B tools\rescore_labels.py --run runs\real_<날짜>\stage2_1_swap_C_C0 --version v4 --dest runs\real_<날짜>
   & $PY -X utf8 -B tools\stage2_summary.py --set runs\real_<날짜> > runs\real_<날짜>\stage2_summary_v4.txt
   & $PY -B tools\compare_metrics.py results\labels_v4\stage2_1_swap_C_C0\metrics.json runs\real_<날짜>\labels_v4\stage2_1_swap_C_C0\metrics.json
   ```

   - `rescore_labels.py`는 먼저 오늘 입력으로 조건 A를 다시 만들어 실행 때 입력과 창마다 견주고(`input_check.json`), 같은 창만 라벨 v4로 채점합니다.
   - `metrics.md`: `## 라벨` 아래 `### 지원 선택`에 창 단위 허용 비율 · 우연 수준 · 구간 2×2 · 지정 지원 전달이 있고, `### 상태 추정`(AUROC · Brier · ECE), `### 다음 어려움 예측`, `### 섞은 대조`가 이어집니다. 호출 · 캐시 · 지연은 `## 실행`에 있습니다.
   - `stage2_summary_v4.txt`: 첫 표가 0장의 주 표이고, 실행마다 핵심 수가 이어지고, 끝에 두 판의 비교가 있습니다. 이 패키지로 `results/`를 요약하면 기록한 파일 185줄 가운데 122번째 줄의 마지막 절 하나만 빠집니다(옛 판의 실행 파일이 필요함).

## 5. 결과 파일과 실행 13개

| 파일 | 내용 |
|---|---|
| `results/labels_v4/<실행>/metrics.{md,json}` | 실행 13개를 라벨 v4로 채점한 결과(2026-11-05, 순열 1,000번) |
| `results/stage2_summary_v4.txt` | 핵심 수 요약(`tools/stage2_summary.py`) |
| `results/manifest.json` | 결과 묶음의 판 기록: PR #77 파일 해시, 도구 해시, 입력 해시, 캐시 규칙, 실행마다 캐시에서 온 답의 수, 대체한 묶음. 작성자 PC의 경로가 그대로 들어 있습니다 |
| `results/version_comparison.json` | `0114ed1` 묶음과의 비교(6장) |
| `results/run_log.json` | 2026-11-05 실제 실행의 항목마다 시작 · 끝 시각, 호출 · 반복 호출 · 실패 · 캐시 답 수, 메모리 부족으로 멈춘 첫 시도 |
| `results/jev_cache.jsonl.gz` | 받은 답 21,736줄(서로 다른 요청 21,538개, 순서를 뒤집은 요청 3,404개 포함)과 반복 묶음 718개. `0114ed1` · `3c936ae` 두 판의 답이 함께 있습니다 |
| `results/answer_pins.json` | 캐시 모드의 답 핀 71개(4장 4단계) |

실행마다 남기는 `jev_calls.jsonl` · `rule_windows.jsonl` · `states.jsonl`(13개에 약 200 MB)은 넣지 않았습니다. 4단계가 같은 파일을 다시 만듭니다.

| 실행 | 입력 | arm | 반복 |
|---|---|---|---|
| `stage1_aligned_b0_r0` | 합성 터치 창, `b0_r0` | 기본 14개 | 1 |
| `stage2_1_swap_C_C0` | 합성 터치 창, `b0_r0` | C, C0 | 1 |
| `stage2_2_C_nohistory` | 합성 터치 창, `b0_r0` | C, C:nohistory | 1 |
| `stage2_3_J_b0_r0` | 합성 터치 창, `b0_r0` | J | 1 |
| `stage2_4a_b0_rA` | 합성 터치 창, `b0_rA` | A, B, C, C0, J | 1 |
| `stage2_4b_b2_rA` | 합성 터치 창, `b2_rA` | A, B, C, C0, J | 1 |
| `stage2_5_GT_b0_r0` | 합성 터치 창, `b0_r0`, 검증한 기준 태그 | A, C | 1 |
| `stage2_6_vision_b0` | 비전 창(`windows_b0`) | A, B, B:vision_summary | 1 |
| `vision_only_round3` | 비전 창(`windows`) | 기본 14개 | 3 |
| `stage3_a1_repeats_C_C0` | 합성 터치 창, `b0_r0` | C, C0 | 고르기만 5 |
| `stage3_a2_repeats_B10` | 합성 터치 창, `b0_r0` | B | 창 10%(seed 0)만 5 |
| `stage3_b_B_vt_b0_rA` | 합성 터치 창, `b0_rA` | B, B:novision, B:notouch | 1 |
| `stage3_b_B_vt_b2_rA` | 합성 터치 창, `b2_rA` | B, B:novision, B:notouch | 1 |

- 기본 14개: A, B, C, C0, D, E와 B의 변형 8개(novision, notouch, la_null, sit_dict, vision_summary, wording_nocrit, perm_vision, perm_touch)입니다.
- 반복: 서로 다른 요청마다 캐시를 거치지 않고 같은 요청을 더 보낸 횟수를 포함한 답의 수입니다.
- 각 실행의 정확한 인자는 `tools/run_set.py`의 `RUNS`에 있습니다.

## 6. 판 메모: `0114ed1` → `3c936ae`

- 처음에는 PR #77 `0114ed1`로 돌렸고(묶음 `real_2026-11-04`, 대체되어 이 패키지에 없음), PR이 `3c936ae`로 승인된 뒤 같은 실행 9개를 다시 돌리고 3단계 4개를 더했습니다(2026-11-05 04:19~04:53, 실제 호출 9,991번, 실패 0번).
- `3c936ae`에서 바뀐 요청: 상황을 모르는 창에 `situation.tag`와 `vision.looking_around`를 false 대신 null로 보내고, `rule_table.WHAT`에 3-2 기다림 줄이 생겨 기다림만 허용된 창에 `none` 하나뿐인 질문이 없어졌습니다.
- 규칙표 결정은 입력이 같은 창에서 두 판이 같았습니다. stage1만 옛 실행이 다른 E3 입력으로 돌아 입력이 같은 3,221창 가운데 6창에서 결정이 갈렸고, 6창 모두 같은 테이크의 앞 창 입력이 달라 세션 이력이 달랐던 창입니다.
- Jev 답은 요청이 바뀐 곳에서만 바뀌었습니다. `b0_r0`에서 C의 고르기 답은 161창 가운데 0창 바뀌었고, 상태 점수 답은 요청이 바뀐 458창에서만 바뀌었습니다. J는 기다림 선택지 문장이 바뀌어 요청 3,344개가 모두 바뀌었고, 답은 595창에서 바뀌었습니다(`results/version_comparison.json`).

## 7. 도구

| 파일 | 하는 일 | 이 패키지에서 |
|---|---|---|
| `tools/run_jev_ablation.py` | 실행기: 창 입력 → 규칙표 → arm마다 Jev 단계(stub · cache · real) | 돌아감 |
| `tools/run_set.py` | 실행 13개를 차례로 돌리고 채점 · 비교 | 돌아감(작성자의 `run_3c936ae.py`를 패키지용으로 바꾼 것) |
| `tools/metrics.py` | 지표(`metrics.json` · `metrics.md`) | 돌아감(표준 라이브러리만) |
| `tools/rescore_labels.py` | 입력 확인 뒤 다른 라벨 판으로 채점 | 돌아감 |
| `tools/stage2_summary.py` | 핵심 수 요약 | 돌아감 |
| `tools/compare_metrics.py` | 두 `metrics.json`을 값마다 비교 | 돌아감(패키지에서 새로 만듦) |
| `tools/check_backend.py` | backend 파일 8개가 `3c936ae`와 같은지 확인 | 돌아감(패키지에서 새로 만듦) |
| `tools/count_requests.py` | 계획한 실행의 호출 수를 캐시에 대고 셈 | 돌아감(4단계로 다시 만든 실행 폴더에) |
| `tools/e3/help_rule.py`, `tools/e3/harness.py` | 도움 규칙 | `help_rule.py`는 E3 파일 그대로(sha256 `0e3584a7…`), `harness.py`는 그 파일이 읽는 이름 4개만 옮김 |
| `tools/wording/*.json` | 질문 문구 변형 2개(돌리지 않음) | 실행기가 `B:wording_formal` · `B:wording_short`로 읽음 |
| `tools/compare_versions.py`, `tools/payload_diff.py` | 두 판의 요청 · 답 비교 기록 | 옛 판의 실행 파일이 필요해 여기서는 돌아가지 않음 |
| `tools/make_manifest.py`, `tools/hash_inputs.py` | `manifest.json`을 만든 기록 | 작성자 작업 공간의 폴더 배치에서만 돌아감 |

## 8. 이 패키지에서 바꾼 것과 새로 정한 것

기록한 실행기에서 바꾼 것(입력 · 출력과 답의 출처만 바꿨고, 요청을 만드는 코드와 채점 코드는 그대로입니다):

- 경로: 작성자 PC의 절대 경로와 임시 폴더 대신 이 폴더의 `inputs/` · `results/`와 `--backend`(또는 `E5_BACKEND`)를 씁니다.
- `.gz` 입력과 `.gz` 캐시를 읽습니다. 실행 기록의 `input_sha256_uncompressed`에 압축을 푼 내용의 해시를 더 적습니다.
- `--jev cache` 모드와 답 핀(`--answer-pins`, `--pin-run`)을 더했고, 캐시에 없는 요청을 API 호출과 따로 셉니다(`cache_misses`).
- `--labels`를 주고 돌리면 `rule_windows.jsonl`을 쓰다 멈추던 오류(시간 라벨 줄의 집합을 JSON으로 쓰지 못함)를 고쳤습니다. 기록한 실행은 모두 `--no-labels`라 이 줄을 지나지 않았습니다.
- 키를 찾는 곳은 환경변수, `<backend>/.env`, `--env-file`뿐입니다(작성자 PC의 팀 저장소 경로를 뺌).
- stub 실행의 끝 줄이 "API calls" 대신 "stub calls (fake answers, nothing sent)"를 찍습니다.
- `metrics.py`는 도움 규칙을 `tools/e3/`에서 불러옵니다. E3의 harness 전체는 비전 모듈과 numpy가 필요해서, `help_rule.py`가 읽는 이름만 `harness.py`로 옮겼습니다.

새로 정한 것: 폴더 배치와 이름(`inputs/` 아래 폴더, 출력 폴더 `runs/`), `.gz`로 묶을 파일, `run_set.py`의 기본값(동시 호출 1, 실제 실행의 새 캐시 위치), 답 핀의 형식, `compare_metrics.py`가 경로 칸을 빼고 실행 칸을 따로 세는 규칙, 4장 5단계의 예상 호출 · 비용 · 시간을 셈한 방법(기록한 실행의 요청 수 · usage · 응답 시간).

## 9. 원본 위치와 문의

- 질문과 결과 공유: PR #77 댓글.
- 원본(wdragon92 작업 공간):
  - `4_vision/eval_jev_2026-11-04/README.md`: 설계(§1~§3, 지표 표), 입력 변환(§4), 출력(§6), 확인한 것(§7), 알려진 한계(§8), 정한 것(§9)
  - `4_vision/eval_jev_2026-11-04/results/RUN_PLAN.md`: 단계마다 호출 수와 비용
  - `4_vision/eval_ab_2026-11-04/JUDGMENT_PROTOCOL.md`: 판단 라벨 규칙과 도움 규칙(§v4-1)
  - `4_vision/eval_ab_2026-11-04/tools/conditions.py`: 합성 터치 조건
- 지표 공식과 분모: `tools/metrics.py`의 `FORMULAS`.
