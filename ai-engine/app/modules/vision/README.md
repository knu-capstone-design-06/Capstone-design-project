# 비전 관측 뼈대 (`app/modules/vision/`)

카메라나 영상 파일의 프레임마다 MediaPipe 3종(얼굴 점 Face Landmarker · 얼굴 검출 Face Detector short-range · 몸 점 Pose Landmarker lite)을 돌려 관측값과 단계별 처리 시간을 CSV로 남기고, 점 · 선을 그린 영상과 그래프를 만드는 뼈대입니다. **2026-10-22부터 녹화 재생 · 웹캠 실시간 실행기(`replay.py` · `live.py`)가 머리 탐지기 · 머리 방향 분류기 · 선택 열 · 터치 로그 · 상황 태그 규칙 3개 · 판단 층 규칙표 v0(장면 3-1 · 3-2 · 4-1 · 4-2, Jev는 질문만 기록)를 창마다 끝까지 잇습니다**(아래 '실행 파이프라인'). 엔드포인트(`app.main`)에는 아직 등록하지 않았습니다. 상황 규칙의 기준값 13개는 기본값 없이 값 묶음 파일로 넣고, 실행 파이프라인이 새로 쓰는 값은 출처와 함께 `params.py`에 있습니다(출처가 없는 값은 `[파일럿]`).

**어디서 돌리나** — 설계안(2026-10-15): 카메라가 연결된 키오스크 PC에서 로컬 프로세스로 돌립니다(영상이 기기 밖으로 나가지 않음). FastAPI · 서버 의존성이 없는 일반 Python 코드라 ai-engine 컨테이너 안에서도 돌 수 있습니다. GPU 서버는 학습 · 평가에만 쓰고 내보낸 모델(ONNX)은 키오스크 PC의 CPU에서 돌립니다. 관측값은 같은 PC의 프론트엔드가 특징 창의 `vision` 칸으로 backend에 보냅니다(루트 README '구성별 책임').

**코드 주석의 출처 약칭** — `doc 27` · `doc 28` · `research/NN`은 비전 담당(wdragon92)의 설계 노트(doc 27 = 케이스별 전후 표 `27_before_after_table.md`, doc 28 = MediaPipe 한계·도달 범위 조사 `28_mediapipe_limits_and_reach.md`)로 저장소 밖(`01_requirements/research/`)에 있습니다. `[D1]`~`[D3]`은 `app/inference/vision.py` 머리말의 MediaPipe 공식 문서 주소이고, `[C5]` · `[D17]`은 doc 28 출처 목록의 번호입니다. `JP`는 판단 층과 Jev 파이프라인 설계 v2.2(`3_design/jev_pipeline_2026-10-13.md`), `tree`는 시나리오 트리 v1.7(`3_design/scenario_tree_v1_2026-10-13.md`)로, 역시 저장소 밖 설계 노트입니다. 노트 내용이 필요하면 비전 담당에게 요청해 주세요. 실험 기록(각 실행의 데이터 · 설정 · 결과 · 서버 위치)과 라이선스 대장은 비전 담당의 작업 노트(저장소 밖)에 있습니다. 숫자가 필요하면 비전 담당에게 요청해 주세요.

## 층과 파일

비전 쪽 처리를 `입력 → 추론 → 관측값 → 사건 → 상황 → 판단 → 전달` 일곱 층으로 나눴고(판단 층은 2026-10-22에 더함), 층마다 파일이 따로 있습니다. 층끼리는 앞 층의 결과만 받습니다. 같은 점 의미와 출력 형식을 유지하는 모델 교체는 추론 층에서 처리하고, 출력 구조가 달라지면 관측값 · 그리기도 함께 맞춥니다. 상황 규칙의 기준값이 정해지면 `PilotParams`에 값만 넣습니다.

| 층 | 파일 | 하는 일 |
|---|---|---|
| 입력 | `sources.py` | 프레임 입력: 영상 파일 · 이미지 폴더 · 웹캠(`--camera`일 때만 엶). 프레임마다 시각을 붙임 |
| 입력 | `touch.py` | 터치 로그(주문 화면 개발 모드의 JSON 내보내기)를 영상 시간축에 놓고 누름 · 버튼 밖 누름 · 빗나감 뒤 바로 고침 · 되돌아감을 세며, 관측 구간 · 세션 · 1,000개 잘림을 처리함. 세는 방법은 `[설계 제안]`(아래 '터치 로그') |
| 추론 | `app/inference/vision.py` | MediaPipe 3종 모델 불러오기와 프레임별 추론만(AGENTS.md: 직접 실행하는 모델의 로딩 · 추론 코드는 `app/inference/`에). 결과를 단순한 배열(`FrameInference`)로 넘김. 이 폴더의 `inference.py`는 같은 이름을 다시 내보내는 호환용. blendshape는 `MediaPipeModels(blendshapes=True)`일 때만 냄(결정 목록 2026-10-10 §16: 기본 꺼짐; 실행기는 `--blendshapes`로 켬) |
| 추론 | `app/inference/head.py` · `app/inference/head_direction.py` | H1 머리 탐지기(YOLOX-Nano)와 P1 머리 방향 분류기(ResNet-18)를 ONNX Runtime으로 CPU에서 돌림(스레드 기본 1). ONNX 파일은 `tools/export_onnx.py`가 만듦. 자리는 같은 AGENTS.md 문장(모델 로딩 · 추론 코드는 `app/inference/`)을 따름 |
| 관측값 | `features.py` | 추론 결과로 관측값 계산(아래 CSV 열): 기하 · 연속 구간 · 밝기와 선명도. MediaPipe 없이도 돌아감 |
| 관측값 | `columns.py` | 규칙이 쓰는 선택 열을 만듦(아래 '선택 열'): 뒤에 선 사람 수 · 동행자 상자 · 어깨 위치 · 입 움직임 · 주 사용자 머리 방향 확률 |
| 사건 | `events.py` | 관측값 줄을 사건으로 묶음(8종, 아래 '상황 층'). 고개를 한 번 돌린 것은 사건 하나. 창 길이 · 횟수 · 각도 · 품질 하한은 모두 `PilotParams`(기본값 없음, `[파일럿]`) |
| 상황 | `situation.py` | 상황 태그 규칙 3개 구현, 값은 `[파일럿]`. 창마다 한 줄(근거 사건 · 품질 · 확신 정보 · 대안)을 내고 검사 규칙으로 확인함. 재생 · 실시간 실행기가 창마다 부름(`run.py` · 엔드포인트는 부르지 않음) |
| 판단 | `judgment/rule_table_v0.py` · `judgment/jev_stub.py` | 장면 3-1 · 3-2 · 4-1 · 4-2의 규칙표 v0: 창마다 지원 하나 · 출력 형태 · 전이를 냄. Jev 질문은 만들어 기록만 함(그림자 모드, 아래 '판단 층 규칙표 v0') |
| 전달 | `contract_view.py` | 창 결과를 기존 계약 형식(`AnalyzeResponse` · `SupportDecision`)과 명세에 없는 칸을 담은 `extension`으로 바꿈. 다른 서비스로 보내는 길은 아직 없음(`contract/`에서 정함) |
| 출력 | `render.py` · `run.py` | 점 · 선을 그린 화면 · 모아 보기 · 그래프 · 처리 시간 통계 / 파일 · 카메라 실행, 결과 폴더 저장, `--show` 창, `--replot` |
| 출력 | `chain.py` · `replay.py` · `live.py` | 프레임에서 창까지 잇는 공용 파이프라인, 녹화 재생(창마다 JSONL 한 줄), 웹캠 실시간(창마다 콘솔 한 줄, `--no-window`) |

| 그 밖 | 하는 일 |
|---|---|
| `models/` | MediaPipe 모델 내려받기 스크립트, ONNX 모델 2개의 해시 · 만드는 법, 출처 · 라이선스(가중치는 Git에 없음) |
| `params.py` | 실행 파이프라인의 값과 출처(`PilotParams`, 기본값 있음), 값 묶음 파일 읽기(상황 규칙 13개는 기본값 없음) |
| `tools/export_onnx.py` | H1 · P1 체크포인트를 ONNX로 바꿈. torch · YOLOX가 든 별도 환경에서 돌림(`models/README.md`) |
| `requirements.txt` | 이 모듈만 쓰는 패키지(mediapipe 0.10.33 · onnxruntime 1.30.0 고정). 서버 `requirements.txt` · Dockerfile은 그대로 |

## 현재 상태 (2026-10-22)

| 항목 | 상태 |
|---|---|
| 뼈대 | 병합됨(PR #32 관측·측정, PR #35 상황 층) |
| 상황 규칙 | 상황 태그 3개의 규칙 · 사건 8종 · 출력 형식을 구현했습니다(PR #35, 2026-10-12 병합; 아래 '상황 층'). 태그 이름과 표시 문구는 아래 '상황 태그 3개 요약' 표와 같고 팀 어휘 확정 전입니다. 기준값 13개는 모두 `[파일럿]`이고 기본값 없이 값 묶음 파일로 넣습니다. 값 묶음이 없으면 `unknown`(이유 `no_value_bundle`)을 냅니다 |
| 실행 파이프라인 | 재생 · 실시간 실행기, 선택 열, 터치 로그 정렬, 판단 층 규칙표 v0, 계약 형식 변환(2026-10-22, 아래 '실행 파이프라인'). 엔드포인트에는 연결하지 않았습니다 |
| 서버 연결 | 없음. 창 결과는 기존 계약 형식과 `extension`으로 바꿀 수 있고(아래 '계약과의 관계'), 명세에 칸을 더하는 일은 추가형 제안입니다 |
| 처리 시간 | 아래 '처리 시간' 절. 실행 파이프라인 전체는 이 노트북의 논리 CPU 1개에서 한 프레임 p50 42~49 ms입니다 |
| 학습 | GPU 서버(GPU 1장, 팀 계정 공유)에서 머리 탐지기(Open Images 'Human head', YOLOX-Nano)를 학습했고(2026-10-12 끝), 머리 방향 분류기(AI Hub 「안내 로봇 인터랙션 멀티모달」 머리 크롭, ResNet-18)를 학습했습니다(2026-10-14 끝). 두 모델은 2026-10-22에 ONNX로 바꿨습니다(`models/README.md`). AI Hub 「사람 행동 인식 로봇 자율 행동 데이터」로 다가옴·사용·떠남 구간 모델을 파일럿 학습했습니다. 숫자는 발표 자료에서 다룹니다 |
| 데이터 규칙 | AI Hub 데이터는 승인받은 사람만 열람합니다(팀원 각자 신청). 원본 프레임은 저장소·발표에 넣지 않고 집계 숫자만 쓰며, 결과물에는 NIA 출처 문구를 붙입니다 |
| 검토 문서 | `docs/Vision-Review.md`(관측값 후보·상황 태그 형식·팀 결정 항목 V01\~V16)는 아직 저장소에 없습니다(초안은 저장소 밖) |

### 상황 태그 3개 요약 (비전 담당, 2026-10-10; 팀 어휘 확정 전)

규칙 3개는 구현했습니다(PR #35; 규칙 원문과 사건 · 출력 형식은 아래 '상황 층'). 아래 표는 비전 담당이 2026-11-02 중간발표 범위로 정한 태그 3개의 요약입니다. 태그 이름과 표시 문구는 팀이 어휘와 전달 형식을 정하기 전의 것이며(2026-10-14 회의 안건), 창 길이 · 횟수 · 각도는 기준이 없어 모두 `[파일럿]`입니다. 값은 촬영 전에 출처와 공개 데이터로 고정하고, 출처가 없는 값은 값 묶음마다 결과를 나란히 보입니다(결정 목록 2026-10-13의 3 · 19번: 촬영본은 평가에만 씀). 측정 전 태그는 '후보(측정 전)'로 표시합니다. 상황 태그만으로 지원을 적용하지 않습니다. 판단 층(규칙 · Jev)이 터치 통계 · 현재 화면과 함께 지원을 고릅니다.

| 태그 이름 | 표시 문구 | 묶는 관찰(같은 창 안) | 빼는 조건 | 근거 수준 |
|---|---|---|---|---|
| `looking_back_with_people_behind` | 뒤에 사람이 있어 서두르는 듯함 | 뒤에 기다리는 사람(주 사용자보다 작은 상자, 뒤쪽, 멈춰 선 사람만) + 뒤돌아봄(yaw 커짐, 얼굴 점 사라짐, 어깨 점 남음, 복귀)의 반복. 터치 빨라짐 · 빗나감과 표정 변동은 보조 근거 | 지나가는 사람만 있을 때, 뒤돌아봄 없이 뒷사람만 있을 때(붐빔 자체는 근거가 아님) | 문헌 + AI Hub 71827 일부(뒷사람의 높이 비). 뒤돌아봄은 측정 전 |
| `consulting_companion` | 일행과 상의하는 듯함 | 동행자(비슷한 크기의 두 번째 상자, 옆) + 주 사용자 yaw가 일행 쪽 + 입 움직임(blendshape, 켜야 함) + 안 누르고 머묾, 몸 점 제자리 | Face Landmarker의 `num_faces`를 2 이상으로 두면 smoothing이 꺼짐(현재 코드는 `num_faces=1`, 얼굴 수는 별도 검출기로 셈). 흔들림을 입 움직임으로 세지 않음 | AI Hub 71827 동행 라벨 + 문헌. 말함은 측정 전 |
| `looking_around` | 무언가를 찾는 듯함 | 화면 밖으로 크게 오가는 yaw 왕복(창 안 횟수) + 몸 점 제자리 + 터치 없음 + 뒤에 사람 없음 | 메뉴 읽기의 작은 yaw(범위는 `[파일럿]`) | 문헌. 71827에는 없음 |

- 층: 관찰(이 모듈의 CSV 열) → 상황 태그(위 표) → 판단 층(지원 선택). 표정은 근거 하나로만 쓰고 혼자 쓰지 않습니다. 감정 이름과 결제 수단은 태그에 넣지 않습니다.
- 고개를 크게 돌린 구간은 각도 대신 '얼굴 점 사라짐 + 몸 점 남음' 패턴을 근거로 씁니다(`look_back` 사건으로 구현, 아래 '사건 8종'). 근거: AFLW2000-3D 2,000장 평가에서 고개를 좌우로 60\~90° 돌린 얼굴은 얼굴 점이 37.7 %에서만 나왔습니다(저장소 밖 측정, 2026-10-08, 평가 전용 데이터).
- 전달 형식: `VisionFeatures`에 선택 칸(관측값 14개 + `situations[]`)을 더하는 추가형 제안입니다. 전달 형식은 2026-10-14 팀 회의의 검토 안건이고, 기존 4칸은 그대로입니다.
- AI Hub 71827 관련 숫자는 과학기술정보통신부의 재원으로 한국지능정보사회진흥원의 지원을 받아 구축된 「사람 행동 인식 로봇 자율 행동 데이터」(AI 허브, aihub.or.kr)를 활용한 분석 결과입니다. 원본 영상과 프레임은 공개하지 않습니다.

## 실행 파이프라인 (2026-10-22)

녹화 재생(`replay.py`)과 웹캠 실시간(`live.py`)이 같은 파이프라인(`chain.py`)을 씁니다. 파이프라인은 프레임마다 한 줄을 만들고, `segment_s`초마다 창 하나를 판단하며, 입력이 끝나면 남은 구간을 길이를 적은 창(`partial`) 하나로 더 판단합니다.

```
프레임 ─ MediaPipe 3종 + blendshape ─ features.Observer 한 줄 ─────────┐
       └ H1 머리 상자 ─ 주 사용자 · 동행자 · 뒤 사람 ─ P1 머리 방향 ──┤ columns.py: 선택 열
터치 로그 ─ touch.py: 영상 시간축, 직전 줄 이후의 누름 · 버튼 밖 누름 ───┘
segment_s마다 ─ situation.assess([t − window_s, t]) + 모름 이유
              ─ 구간 (t − segment_s, t]의 터치 횟수 · measurable · 화면 · 고개 방향
              ─ judgment/rule_table_v0.py: 지원 하나 · 형태 · 전이 (Jev 질문은 기록만)
              ─ contract_view.py: AnalyzeResponse · SupportDecision 모양 + extension
```

- 창 끝 뒤의 줄은 어느 단계도 읽지 않습니다. 창마다 창 끝 시각 이하의 관측 줄과 터치 기록만으로 계산합니다. 사용자 반응(수락 · 거절) · 세션 신호 · 실시간 지연은 재현하지 않습니다.
- 빠진 재료는 결측으로 남깁니다. ONNX 파일이 없으면 머리 상자 · 방향 열이, blendshape를 켜지 않으면(`--blendshapes`, 기본 꺼짐) `mouth_motion`이, 터치 로그가 없으면 터치 열이 비고, 그 단서가 필요한 태그는 `unknown`이 됩니다. 왜 모르는지는 창 결과의 `unknown_reason`에 적힙니다.
- 창 하나에 필요한 줄은 `window_s + 2 × gap_s`초어치입니다. 실시간은 이만큼만 기억하고, 재생도 창마다 이만큼만 넘깁니다(테스트로 전체 기록과 같은 결과임을 확인함).

### 재생 (녹화 + 터치 로그)

```powershell
.venv\Scripts\python.exe -m app.modules.vision.replay --video S1a_P2_1.mp4 --touch-log S1a_P2_1_touch.json --params bundle_b0.json --out runs\replay\S1a_P2_1
```

- 녹화 옆의 `S1a_P2_1.mp4.times.csv`(프레임마다 잡은 시각)와 `S1a_P2_1.mp4.clock.json`(첫 프레임의 노트북 시각)을 저절로 읽습니다. 둘 다 시제품 `record_clip.py`가 만드는 파일입니다(촬영 대본 §4).
- 시계 파일이 없으면 `--start-offset`에 터치 로그 첫 기록이 영상의 몇 초인지 넣습니다(휴대폰 시계 · 손뼉으로 찾은 값). 둘 다 없으면 오류로 멈춥니다. `--touch-log`를 빼면 터치 열 없이 돌아갑니다.
- `--step 2`(두 장마다 한 장) · `--width 640`은 `run.py`와 같습니다. `--max-seconds`로 앞부분만 돌릴 수 있습니다. `--threads`는 ONNX Runtime 스레드 수이고 기본값은 1입니다. `--blendshapes`는 blendshape를 켭니다(기본 꺼짐, 결정 목록 2026-10-10 §16). `--no-heads`는 머리 탐지기를 일부러 빼고 돌립니다. 터치 로그에 경고(1,000개 잘림)가 있으면 시작할 때 출력합니다.
- 결과: `windows.jsonl`(창마다 한 줄, 아래), `rows.csv`(프레임마다 한 줄: 'CSV 열' + 선택 열 + 처리 시간), `meta.json`(입력 · 값 묶음과 값마다의 출처 · 모델 해시 · 패키지 판 · 처리 시간 p50 · p95 · 태그와 결정의 개수 · 얼굴 · 머리 상자 · 머리 방향이 있는 프레임 수 · 세션 초기화 횟수 · 마지막 창의 길이). 영상과 그림은 만들지 않습니다.

### 실시간 (웹캠)

```powershell
.venv\Scripts\python.exe -m app.modules.vision.live --camera 0 --no-window --seconds 60 --params bundle_b0.json --out runs\live_test
```

- 창마다 콘솔에 한 줄이 나옵니다. 형식 예: `[   12.0초] 상황 unknown(모름: column:tap_count) | 머리 2 · 뒤 1 · 동행 프레임 0 · 입 0.08 · 화면 봄 예 | 판단 none | 프레임 처리 45 ms`.
- `--no-window`면 화면에 아무것도 띄우지 않습니다. 빼면 창에 프레임과 주 사용자 · 동행자 상자를 그리고, 창에서 `q`를 누르거나 창을 닫으면 멈춥니다. `--seconds`가 없으면 Ctrl+C로 멈춥니다.
- 실시간에는 터치 로그가 없습니다(주문 화면이 이 실행기와 이어져 있지 않음). 그래서 '터치 없음'이 필요한 태그는 `unknown`(이유 `column:tap_count`)으로 남고, 규칙표의 터치 행(4-1 · 4-2)은 열리지 않습니다.
- `--out`에는 `windows.jsonl`과 `meta.json`만 씁니다. 카메라 그림은 저장하지 않습니다.

### 값 묶음 파일 (`--params`)

상황 규칙의 기준값 13개(`events.PilotParams`)는 기본값이 없습니다. 값은 촬영 전에 출처(표준 · 관행 · 문헌)와 공개 데이터로 고정하고, 출처가 없는 값은 값 묶음마다 결과를 나란히 보입니다(결정 목록 2026-10-13의 3 · 19번, 저장소 밖). 촬영본으로 값을 정하지 않습니다. 실행 파이프라인이 새로 쓰는 값(`params.PilotParams`)에는 기본값과 출처가 있고, 값 묶음 파일에서 바꿀 수 있습니다.

```json
{
  "bundle_id": "b0",
  "note": "값 묶음을 고정한 날짜와 커밋",
  "situation": {"window_s": {"value": "<값>", "source": "<출처>"}, "...": "13개 모두"},
  "chain": {"lost_pause_s": {"value": "<값>", "source": "<출처>"}}
}
```

- 형식 예입니다. `situation`에는 13개를 모두 넣어야 하고, 하나라도 빠지면 오류입니다. `chain`에는 바꿀 값만 넣습니다. 값마다 `value`와 비어 있지 않은 `source`가 있어야 하고, 숫자만 쓰거나 출처를 비우면 오류로 멈춥니다(값마다 출처를 적는 규칙).
- `--params`가 없으면 상황 출력은 `unknown`(이유 `no_value_bundle`)이고, 규칙표는 터치 행만 봅니다.
- 쓴 값과 출처는 값마다 `meta.json`의 `bundle`에 남고, `origin`이 값 묶음에서 온 값(`bundle`) · 코드 기본값(`default`) · 코드에서 준 값(`code`)을 구분합니다. `[파일럿]` 목록(`pilot_fields`)도 기록된 출처를 따릅니다.

### 창 한 줄 (`windows.jsonl`)

아래는 테스트의 합성 배열(가짜 추론 결과: 고개를 오른쪽 · 왼쪽으로 한 번씩 돌림, 영상 시작 0.5초 전에 누름 한 번, 그 뒤 터치 없음, 메뉴 화면)로 돌린 재생의 실제 출력이고, `"..."`는 줄인 곳이며 소수는 둘째 자리까지 줄였습니다. 숫자는 합성 입력의 값이고 기준값이 아닙니다.

```json
{"t": 4.0, "segment_s": [3.0, 4.0], "frames": 10,
 "situation": {"name": "looking_around", "display_text": "무언가를 찾는 듯함",
               "evidence_ids": ["dwell_no_touch@0", "yaw_sweep_offscreen@10", "yaw_sweep_offscreen@24"],
               "evidence": [{"event_id": "dwell_no_touch@0", "obs": "no_touch_s", "value": 4.0, "t": 4.0},
                            {"event_id": "yaw_sweep_offscreen@10", "obs": "yaw_deg", "value": 55.0, "t": 1.4},
                            {"event_id": "yaw_sweep_offscreen@10", "obs": "side", "value": "right", "t": 1.4}, "..."],
               "confidence": {"events": 3, "quality_ok": true}, "alternatives": [], "unknown_reason": [],
               "quality": {"face_visible_ratio": 1.0, "track_conf": 1.0}, "window_s": [-2.0, 4.0], "source": "rules_v1"},
 "touch": {"tap_count": 0, "miss_tap_count": 0, "near_miss_fix_count": 0, "back_count": 0, "unknown_target_presses": 0,
           "repeat_tap_count": null, "dwell_ms": null},
 "screen": {"name": "menu", "steps_left": 2, "pause_s": 4.5, "options_open": false},
 "vision": {"frames": 10, "face_seen_ratio": 1.0, "body_seen_ratio": 1.0, "head_count_max": 1.0,
            "people_behind_max": 0.0, "companion_frames": 0, "mouth_motion_max": null, "facing_screen": true},
 "measurable": true,
 "decision": {"transition": "open", "support": "highlight_next_action", "scene": "4-2", "action": "apply",
              "intervention": "바로 적용", "rank": 7, "scope": ["screen", "menu", 1.0], "withdraw_on": "cart_progress",
              "decision_id": "d0001", "withdrawn_id": null, "preset": "none", "requires_confirmation": false,
              "session_signal": null, "steps_left": 2, "target_id": null, "message_id": null,
              "policy": {"kind": "fit", "ask_jev": true, "lowered_action": "wait", "T_LOWER": null, "...": "..."},
              "jev_request": {"model": "jev-1.13.0", "state": {"...": "..."}, "questions": {"proposal_fits": {"...": "..."}}},
              "meta": {"t": 4.0, "tag": "looking_around", "tag_since": 3.0, "screen": "menu", "screen_since": 1.0}},
 "session": {"held": {"decision_id": "d0001", "support": "highlight_next_action", "scene": "4-2", "status": "shown", "...": "..."},
             "active": [], "refused": [], "withdrawn": []},
 "session_reset": false,
 "jev": {"kind": "fit", "answer": null, "shadow": true, "applied": false, "decided_by": "rule_placeholder"},
 "contract": {"analyze_response": {"session_id": "example", "measurable": true, "states": null,
                                   "model_version": "vision-situation-rules_v1+rule_table_v0-shadow"},
              "support": {"preset": "none", "requires_confirmation": false, "decided_by": "rule_placeholder"},
              "extension": {"situation": {"...": "..."}, "decision_meta": {"...": "..."}}},
 "ms_window": 0.7}
```

- `situation`: 창의 `assess` 출력입니다. `evidence_ids`는 근거 사건 ID 목록이고, `evidence`에는 사건마다의 관찰 값이 있습니다(아래 '출력 형식'). 대안은 이름 · 확신 정보 · 근거 사건 ID만 남깁니다. `unknown_reason`(모름 이유)은 `name`이 `unknown`일 때만 채웁니다: `no_value_bundle`(값 묶음 없음) · `no_frames`(창에 프레임 없음) · `sensor_failure`(몸 추적 비율이 `track_conf_min` 미만) · `tie`(두 태그의 근거 사건 수가 같음) · `missing_cue`(태그마다 모자란 단서: `column:tap_count` · `column:people_behind_count` · `column:companion_box` · `yaw_missing` · `shoulder_visibility_missing` · `turn_unresolved` · `face_visible_ratio<face_visible_min` · `companion_side_unknown` · `body_position_missing`) · `too_few_events`(근거 사건이 `min_events`보다 적음).
- `touch`: 구간 (t − `segment_s`, t]의 횟수입니다. 터치 로그가 없거나 구간이 로그의 관측 구간에 통째로 들지 않으면 `touch` 전체가 `null`입니다. `near_miss_fix_count`는 버튼 밖 누름 뒤 그 옆 버튼을 바로 누른 횟수이고, 구간 안에 대상 정보가 없는 누름이 있으면 `miss_tap_count`와 함께 `null`입니다.
- `screen`: 그 시각의 화면(`menu` · `review` · `complete`; 로그가 멈춘 뒤는 `null`), 주문 끝까지 남은 화면 수, 이 화면 방문에서 누른 뒤 지난 초(`pause_s`; 이 방문에서 아직 누르지 않았으면 `null`), 옵션 창이 열려 있는지(`options_open`)입니다.
- `vision.facing_screen`: 구간에서 얼굴이나 몸을 마지막으로 본 프레임 기준으로, 얼굴이 보이고 |yaw|가 `offscreen_yaw_deg` 미만이면 참, 그 이상이면 거짓입니다. 그 프레임에 얼굴 없이 몸만 보이면 고개 방향을 못 잰 것이라 `null`이고(터치 행은 올린 기준으로 봄, tree §4 ⑦), 본 프레임이 없거나 값 묶음이 없어도 `null`입니다.
- `measurable`: 팀 자리표시자(`app/inference/placeholder.py`)와 같은 뜻입니다. 구간에 누름이나 되돌아감이 있거나 얼굴이 한 번이라도 보이면 참입니다. JP §0-1 2항의 뜻(고른 뒤 멈춤 같은 터치 단서와 카메라 관측도 셈)과 맞추는 일은 2026-10-14 안건 3이라, 여기서는 자리표시자의 뜻을 따릅니다.
- `session_reset`: 터치 로그의 세션(`sessionId`)이 바뀐 창이면 참이고, 그 창부터 판단 상태(유지 중인 결정 · 거절 · 거둔 목록)를 처음부터 다시 셉니다(tree §4 ①). `partial`은 입력의 마지막 남은 구간을 판단한 창에만 있고 그 길이를 적습니다.

### 판단 층 규칙표 v0 (`judgment/rule_table_v0.py`)

JP §0-2 · §0-3과 장면 표, tree 표 3-가 · 3-나 · §4에서 장면 4개의 지원 이름 · 형태 · 순서 · 전이 · 거두는 조건을 옮겼습니다. 창마다 지원 하나 또는 없음을 냅니다. 순서(`rank`)는 JP 순서표의 번호입니다. 원문과 다르게 둔 것은 아래 '터치 단서의 범위'와 '아직 하지 않는 것'에 적었습니다.

| 장면 | 지원 | 형태 | 순서 | 여는 조건 | Jev(그림자) | 거두는 조건 |
|---|---|---|---|---|---|---|
| 3-2 일행 상의 | `wait_hold_timer` | 기다림(`session_signal` `{name: hold_timer}`를 열 때와 측정 가능한 창의 유지에 실음) | 2 | 태그 `consulting_companion`(일행 길). 세션 동작이라 거둔 뒤에도 방아쇠마다 다시 엶 | 없음 | 터치가 이어짐(`touch_resumed`) |
| 3-1 뒤에 줄 | `remaining_steps_notice`(조건표가 켜면 `delay_responsibility_notice`) | 바로 적용 | 3 | 태그 `looking_back_with_people_behind`, 남은 화면이 있거나 모름 | 허용 후보가 둘(알림 · 큰 버튼 질문 미룸; 미룸은 고개 게이트를 지난 4-1 행이 같은 창에 있을 때만)이면 Choice, 하나면 적합성 Noul. 안내는 없음 | 장바구니가 나아감(`cart_progress`) |
| 4-1 손 떨림 | `large_button` | 묻기 | 4 | 남은 화면이 있는 화면에서, 최근 `touch_span_s`초의 '버튼 밖 누름 뒤 그 옆 버튼을 바로 누름'(`near_miss_fix_count`)이 `tremor_miss_min` 이상이고 화면을 봄. 카메라가 고개 방향을 못 재면 `tremor_miss_min_no_gaze` 이상(Jev 없음). 화면을 보지 않으면 행 없음 | 적합성 Noul | 없음(반응 · 무응답으로 끝남) |
| 4-2 헤맴 | `highlight_next_action` | 바로 적용(조용히) | 7 | 남은 화면이 있는 화면에서 되돌아감 `lost_back_min` 이상, 또는 이 화면 방문에서 누른 뒤 `lost_pause_s` 이상 멈춤(두리번 태그나 화면을 보는 고개가 있으면 `lost_pause_s_vision`; 아직 누르지 않았으면 멈춤 아님) | 적합성 Noul | `cart_progress` |
| 직원 호출 | — | 직원 호출 | 9 | 만들지 않음(JP: 조건 미정) | — | — |

판단 순서(JP §0-3)는 다음과 같습니다.

1. 측정할 수 없는 창(`measurable` 거짓)은 유지 중인 결정을 되풀이하거나 아무것도 내지 않습니다.
2. 유지 중인 결정의 거두는 조건이 맞으면 거둡니다.
3. 후보 행이 없으면 유지 중인 결정을 되풀이하거나 아무것도 내지 않습니다.
4. 유지 중인 결정이 없으면 순서가 가장 앞선 행을 엽니다.
5. 떠 있는 묻기는 끝날 때까지 두고, 순서가 앞선 3-2 기다림만 그 자리를 바꿉니다.
6. 그 밖에는 순서가 앞선 행이 바꿔 들어갑니다. 한 창 동안 보인 조용한 알림 · 강조는 묻기에 자리를 내줍니다.

- 터치 단서의 범위: tree 표 3-가의 4-1 '같은 버튼 근처 빗나감 · 바로 고침'은 프론트가 버튼 밖 누름마다 남기는 가장 가까운 버튼 목록(`nearestCandidates`; 거리 상한 없음, T03 미정)과 그다음 누름을 이어 '빗나감 뒤 그 옆 버튼을 바로 누름'으로 셉니다(연결 기준 T07 미정이라 `[설계 제안]`). 버튼 밖 누름 수만으로는 열지 않습니다. 4-2의 '담지 않고 오감'(옵션 창을 열었다가 담지 않고 닫음)은 아직 세지 않고, 되돌아감과 고른 뒤 멈춤만 봅니다. 터치 로그가 시작된 뒤와 세션이 바뀐 뒤 `touch_span_s`초(기본 5초) 동안은 최근 구간이 통째로 관측되지 않아 4-1과 4-2의 되돌아감 단서가 열리지 않습니다.
- 후보 거르기(JP §0-2): 켠 지원(`active`), 거절한 지원(`refused`, 세션 동안), 같은 범위에서 거둔 지원(`withdrawn`)과 지금 유지 중인 지원은 열지 않습니다. 범위는 태그 행이면 태그 구간, 그 밖이면 화면 방문이고, 범위가 바뀌면 거둔 지원이 다시 후보가 됩니다. 3-2 기다림은 화면에 띄우는 지원이 아니라 세션 동작이라 거둔 목록으로 거르지 않습니다(JP v1.6).
- 상황이 `unknown`이거나 값 묶음이 없으면 태그 행은 열리지 않고 터치 행만 판단합니다(JP §0-2: 상황 근거만 빼고 판단). Jev 질문(`jev_request`)도 상황이 알려진 창에서만 만듭니다(JP §0-4).
- 세션 상태(유지 중인 결정 · 켠 지원 · 거절 · 거둔 목록)는 설계상 backend가 갖습니다(JP §0-1). 재생은 같은 규칙으로 흉내 냅니다: 그림자 모드라 연 결정은 그 창에 바로 보인 것으로 두고, 묻기에 `no_response_s`초 동안 반응이 없으면 무응답으로 거둡니다. 재생에는 사용자 반응 기록이 없어 수락 · 거절은 일어나지 않습니다. 유지 중인 결정은 결정 전체를 갖고, 되풀이(keep)는 같은 `decision_id`로 장면 · 정책 · 단서 · 실행 칸을 다시 싣습니다(JP §0-1). 터치 로그의 세션이 바뀌면 상태를 처음부터 다시 셉니다(tree §4 ①).
- Jev: 질문을 만들어 기록만 합니다(`jev_stub.ShadowJev`). ai-engine은 외부 AI API를 부르지 않으므로(AGENTS.md §4) 실제 호출은 backend 어댑터의 몫이고, 화면은 규칙 결과를 따릅니다(`decided_by` = `rule_placeholder`). 질문 글은 영어이고, 3-1 후보의 설명(`criteria`)은 JP §2-2의 문장이며, 질문 지시문과 `state`의 구성은 이 모듈이 정했습니다. 4-1 · 4-2의 맞음 · 안 맞음 경계 문장은 설계 노트에 없어 이 모듈에서 가안으로 적었습니다.

### 계약과의 관계 (추가형 제안, 명세는 그대로)

- `contract/backend-ai.openapi.yaml`(0.2.0)과 `contract/frontend-backend.openapi.yaml`은 바꾸지 않았습니다.
- 창 결과는 기존 형식으로 바꿀 수 있습니다: `analyze_response` = `AnalyzeResponse`(`session_id` · `measurable` · `states` · `model_version`), `support` = `SupportDecision`(`preset` · `requires_confirmation` · `decided_by`). `states`는 불편 상태 모델이 이 파이프라인에 없어 `null`이고, `decided_by`는 그림자 모드라 늘 `rule_placeholder`입니다. 지원과 `UIPreset`의 대응은 JP §2-5 표를 따랐습니다(알림 = `step_guide`, 큰 버튼 묻기 = `large_button` · 확인 필요, 강조 · 기다림 = `none`).
- 명세에 없는 칸(상황 태그 · 표시 문구 · 근거 사건 ID · 모름 이유 · 대안 · 품질, 결정의 지원 · 형태 · 전이 · 범위 · 정책 · Jev 종류, 실행 칸 `steps_left` · `target_id` · `message_id` · `session_signal`)은 `extension`에 담았습니다. 실행 칸은 JP §2-5의 `decision_meta`를 따른 `[설계 제안]`입니다: 3-1 알림은 `cart_progress` · `steps_left_notice`(지연 책임 안내는 `delay_responsibility_notice`), 4-2 강조는 옵션 창이 열린 메뉴 화면이면 `cart-add`, 장바구니 화면이면 `cart:*:decrease`(줄마다 다른 '−' 버튼 ID의 패턴), 그 밖은 비움(자주 찾는 메뉴 줄 · 검색은 화면에 아직 없음)이고, 문구 ID는 문구가 정해지기 전이라 비웁니다. 이 칸을 응답의 선택 칸으로 더하는 것은 추가형 제안이고, 화면이 실제로 읽게 하려면 형식과 뜻을 팀이 정해야 합니다(2026-10-14 회의 안건 V04 · 6). `extension`은 재생 파일의 출력이지 기존 API의 응답이 아닙니다.
- 요청 쪽 `TouchFeatures`는 `tap_count` · `miss_tap_count` · `back_count`만 채울 수 있습니다. `repeat_tap_count` · `dwell_ms`는 기준이 정해지지 않아 `null`이라, 지금 창 결과로 `FeatureWindowRequest`를 완전히 만들 수는 없습니다.

### [파일럿] 값과 출처 (`params.py`)

실행 파이프라인이 새로 쓰는 값입니다. 모두 기본값이 있고, 값마다 출처 문장이 코드(`PilotParams` 필드의 `source`)와 `meta.json`에 함께 있습니다. `[파일럿]` 값 11개는 표준도 측정 자료도 없는 시작값이라, 촬영(2026-10-28) 전에 출처나 공개 데이터로 바꾸거나 값 묶음 여러 개로 결과를 나란히 보입니다.

| 값 | 기본값 | 단위 | 출처 |
|---|---|---|---|
| `head_score_min` | 0.65 | 점수 0~1 | 데이터(E3b): H1의 Open Images 검증 전부(입력 416)에서 F1이 가장 큰 점수 기준(정밀도 0.682 · 재현율 0.676). 키오스크 시점 값 아님 |
| `head_nms_iou` | 0.65 | IoU 0~1 | 관행값: YOLOX `yolox_base.py`의 `nmsthre` 기본값(H1 평가 설정과 같음) |
| `primary_rule` | `face_then_largest` | — | `[파일럿]` 규칙(위 '선택 열') |
| `companion_min_area_ratio` | 0.5 | 넓이 비 | `[파일럿]` 시작값: 길이 비 약 0.71, 대략 1.4배 먼 머리까지 '비슷한 크기'(결정 §3, 대본 §1-1 C는 A와 같은 거리) |
| `companion_max_dist_widths` | 3.0 | 주 사용자 머리 폭 | `[파일럿]` 시작값(결정 §3 '옆') |
| `behind_max_area_ratio` | 1.0 | 넓이 비 | 결정 §3 '주 사용자보다 작은 상자' |
| `mouth_dials` | jaw · mouth로 시작하는 27개 | — | Apple ARKit `ARFaceAnchor.BlendShapeLocation`의 'Mouth and Jaw' 묶음, 결정 §3 '입 다이얼' |
| `mouth_baseline_s` | 2.0 | 초 | `[파일럿]` 시작값(결정 목록 2026-10-10 §16: 기준선을 뺀 변화) |
| `segment_s` | 1.0 | 초 | 계약 `sendFeatureWindow`의 '1~3초 구간' 안에서 고른 `[파일럿]` 값 |
| `touch_span_s` | 5.0 | 초 | `[파일럿]` 시작값: 4-1(빗나감 뒤 바로 고침) · 4-2(되돌아감)의 터치 단서를 세는 최근 구간 |
| `tremor_miss_min` | 2 | 번 | `[파일럿]` 읽기: tree 표 3-가 4-1 '빗나감 · 바로 고침 반복'의 '반복'을 2번 이상으로 읽음(버튼 밖 누름 뒤 그 옆 버튼을 바로 누른 횟수) |
| `tremor_miss_min_no_gaze` | 3 | 번 | `[파일럿]`: 고개 방향을 못 재는 창의 올린 기준(JP §0-2) = 한 번 더 |
| `lost_back_min` | 1 | 번 | 정의: tree 표 3-가 4-2 '되돌아감'이 있음 |
| `lost_pause_s` | 8.0 | 초 | `[파일럿]` 시작값: 4-2 '고른 뒤 멈춤' |
| `lost_pause_s_vision` | 4.0 | 초 | `[파일럿]` 시작값: 두리번 · 화면을 보는 고개가 있을 때 낮춘 기준(조정량은 기준 없음, JP §0-2) |
| `no_response_s` | 10.0 | 초 | `[파일럿]` 시작값: 무응답 시간(JP §0-6) |
| `delay_notice_on` | 거짓 | — | 평가 조건표 스위치(결정 목록 2026-10-10 §14, JP §0-2) |
| `defer_option_on` | 참 | — | 평가 조건표 스위치(JP §0-2) |

## 처리 시간 (개발 노트북)

### 관측 뼈대 (저장소 밖 시제품)

같은 MediaPipe 3종과 0.10.33으로 만든 저장소 밖 시제품에서 잰 한 프레임 처리 시간입니다(같은 입력에서 이 저장소 코드와 관측값이 같았음). 조건: Intel Core i5-1340P 노트북, 성능 코어 고정 · 높은 우선순위, Windows 11, Python 3.12.10, CPU만, 세 모델을 매 프레임 모두 실행, 프레임 640×480(합성 입력) · 640×360(공개 영상), 첫 프레임 제외(2026-10-08 측정).

- p50은 처리 시간의 중앙값이고 p95는 95백분위수입니다(100번 중 95번은 그 시간 안에 끝남).
- 합계(얼굴 점 + 얼굴 검출 + 몸 점 + 밝기 · 선명도): 입력 6개에서 p50 20.7\~25.3 ms · p95 24.2\~32.6 ms(얼굴 검출 short-range). full-range 검출이면 합성 다가옴에서 p50 25.9 ms · p95 29.7 ms.
- 얼굴을 새로 찾는 프레임은 더 걸립니다(장면 전환 영상에서 중앙값 40 ms, 따라가는 프레임 26 ms). 오버레이 그리기는 따로 p50 7.0\~8.7 ms입니다.
- 키오스크 PC(G10) 값은 없습니다. 실기기 단계는 미정입니다(2026-10-10).

### 실행 파이프라인 전체 (이 저장소, 2026-10-22)

`replay.py`의 프레임 한 장 처리(MediaPipe 3종 + blendshape(켠 조건; 지금은 `--blendshapes`를 줘야 같은 조건) + 관측값 + H1 머리 탐지 + P1 머리 방향 + 선택 열)와 창 하나의 판단(상황 + 규칙표)을 같은 조건으로 3번 쟀습니다. 조건: 개발 노트북(i5-1340P), Windows 11, Python 3.12.10, mediapipe 0.10.33, onnxruntime 1.30.0, 프로세스를 논리 CPU 1개(CPU 2)에 고정 · 보통 우선순위, ONNX Runtime 스레드 1, OpenCV 스레드 1, 첫 프레임 제외. 입력: 시제품 `samples/was_ist_ein_vlog_360p.mov`(웹캠 앞 한 사람, CC BY-SA 3.0)의 앞 30초를 `--step 2 --width 640`(640×360, 초당 12.5장, 376장)으로 돌렸고, 얼굴은 371장에서 보였습니다. 결과 파일은 숫자만 보고 지웠습니다.

| 단계 | p50 (ms) | p95 (ms) |
|---|---|---|
| MediaPipe 3종 + 관측값 계산(`ms_total`) | 21.4~24.9 | 23.7~29.1 |
| H1 머리 탐지: 전처리 · 추론 · 후처리(`ms_heads`) | 16.1~19.0 | 18.4~21.8 |
| P1 머리 방향, 주 사용자 1명(`ms_head_dir`) | 4.0~4.6 | 4.7~5.5 |
| 프레임 한 장 전체, 벽시계(`ms_chain`) | 42.1~49.0 | 50.7~58.8 |
| 창 하나의 판단, 1초에 한 번(`ms_window`; 시험용 값 묶음, 창 6초) | 0.62~0.74 | 0.68~0.80 |

- 범위는 3번의 최솟값~최댓값입니다. 프로세스 CPU 시간(모든 스레드, 영상 디코딩 · 창 판단 포함)은 프레임당 43.3 · 49.8 ms였습니다(2번 잼).
- 프레임 처리 중앙값의 역수는 초당 20~24장입니다(1000 ÷ 49~42 ms). 카메라 캡처 · 디코딩 · 창 판단까지 합친 지속 처리량은 따로 재지 않았습니다. 팀의 설계 목표(초당 10~15장, doc 28 §0)를 이 노트북에서는 CPU 1개로 넘지만, G10 값은 아닙니다.
- P1은 주 사용자 머리에만 돌립니다. 사람이 더 보여도 P1은 한 번이고, H1은 같은 크기(416 × 416)의 입력을 씁니다.

## 준비 (`ai-engine/`에서, PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r app\modules\vision\requirements.txt
.venv\Scripts\python.exe app\modules\vision\models\download_models.py
```

- 재생 · 실시간 실행기가 쓰는 ONNX 모델 2개는 `models/README.md`의 '다시 만들기'대로 만들거나 비전 담당에게 받아 `app\modules\vision\models\`에 둡니다.

## 실행 (`run.py`: 관측 CSV · 오버레이)

```powershell
# 영상 파일 (--step 2 = 두 장마다 한 장, --width 640 = 폭 640으로 줄임, 비율 유지)
.venv\Scripts\python.exe -m app.modules.vision.run <영상 파일> --step 2 --width 640
# 이미지 폴더: 사진에는 시각이 없어 명목 초당 장수(--fps)가 필요. manifest.json이 있으면 그 값을 씀(실측 촬영 시각이 아님)
.venv\Scripts\python.exe -m app.modules.vision.run <이미지 폴더> --fps 15 --width 640
# 카메라: 창을 띄우고 q로 멈춤, 또는 창 없이 정한 시간만
.venv\Scripts\python.exe -m app.modules.vision.run --camera 0 --show
.venv\Scripts\python.exe -m app.modules.vision.run --camera 0 --seconds 30
```

- 결과 폴더: `app/modules/vision/runs/<입력 이름 또는 live>_<날짜>_<시각>/`(Git에 올라가지 않음). 시작과 끝에 콘솔에 나옵니다. 다른 곳에 두려면 `--out <폴더>`.
- 카메라 실행 결과(`overlay.mp4` · `contact_sheet.png`)에는 찍힌 사람의 얼굴이 담깁니다. `runs/`는 Git(`.gitignore`)과 ai-engine Docker 이미지(`ai-engine/.dockerignore`)에서 빠지며, 결과를 옮기거나 보관할 때는 `AGENTS.md` §5의 데이터 규칙을 따릅니다.
- 결과 파일: `observations.csv`(프레임마다 한 줄, 아래), `overlay.mp4`(점 · 선 + 값 칸), `contact_sheet.png`(고르게 뽑은 12장), `plot_observations.png` · `plot_quality_timing.png`, `timing.csv`(단계별 p50 · p95 · 최대 · 첫 프레임 ms), `meta.json`(입력 · 설정 · 모델 해시 · 환경 · 끝난 이유), `run.log`(단계별 기록 · 오류 전문).
- 멈추기: `--show` 창에서 `q` · 창 닫기, 또는 콘솔에서 Ctrl+C. 그때까지 처리한 프레임이 저장됩니다. 창도 `--seconds`도 없이 카메라를 돌리면 멈추는 방법을 알려 주는 오류가 납니다.
- 카메라 실행의 `overlay.mp4`는 실제로 처리한 초당 장수로 저장됩니다(`imageio-ffmpeg`가 있을 때 H.264로 바꾸면서; 없으면 MPEG-4 Part 2, 카메라가 알린 초당 장수). `imageio-ffmpeg`는 고정하지 않은 선택 패키지이고, 들어 있는 ffmpeg 실행 파일은 GPL입니다.
- 저장 도중 끊겨 그래프 등이 빠졌으면 `--replot <결과 폴더>`로 `observations.csv`에서 다시 만듭니다.
- 녹화 영상 옆에 `<영상>.times.csv`(`frame,t_s`)가 있으면 그 실측 시각을 씁니다. 번호가 0, 1, 2…로 이어지지 않거나 시각이 되돌아가거나 프레임보다 짧으면 오류로 멈춥니다. 한 실행 안에서 프레임 크기가 바뀌어도 멈춥니다(overlay 영상은 첫 프레임 크기로 고정).
- 처리 시간을 잴 때는 `--show` 없이 돌립니다(창에 그리는 시간은 `meta.json`의 `output_ms`에 따로 적힘).

## 상황 층 (`events.py` · `situation.py`)

관측값 줄을 창 단위로 읽어 사건을 찾고, 사건을 묶어 상황 태그 3개 가운데 하나를 냅니다. 판단할 수 없으면 `unknown`, 모든 태그가 관측된 단서로 빠지면 `none`을 냅니다. 재생 · 실시간 실행기가 창마다 이 층을 부르고(아래 '실행 파이프라인'), `run.py`와 엔드포인트는 부르지 않습니다.

기준값은 정하지 않았습니다. 창 길이 · 횟수 · 각도 · 품질 하한 13개는 모두 `PilotParams`의 필드이고 기본값이 없어서, 부르는 쪽이 값을 모두 넣어야 합니다. 값은 촬영 전에 출처와 공개 데이터로 고정하고, 출처가 없는 값은 값 묶음마다 결과를 보입니다(`[파일럿]`; 결정 목록 2026-10-13의 3 · 19번). 실행기는 이 13개를 값 묶음 파일(`--params`)에서만 읽습니다. 필드마다 무엇을 정하는지는 `events.py`의 `PilotParams` 주석에 적었습니다. 횟수 3개는 1 이상만 받습니다. 0을 넣으면 결정 표가 요구하는 관찰 없이도 규칙이 맞기 때문입니다. 비율(0~1)과 비교하는 하한 3개(`shoulder_vis_min` · `face_visible_min` · `track_conf_min`)는 1 이하만 받고, 창 길이와 끊김 간격(`window_s` · `gap_s`)은 0보다 커야 합니다. 백분율로 잘못 넣은 값이나 0초 창은 모든 창을 `unknown`으로 만들거나 사건을 프레임 하나씩 쪼개므로 바로 막습니다. `situation.py`에는 숫자가 없고, 테스트가 이를 확인합니다.

```python
from app.modules.vision.events import PilotParams
from app.modules.vision.situation import assess

params = PilotParams(window_s=..., gap_s=..., ...)                 # 13개 모두 [파일럿], 기본값 없음
out, events = assess(rows, t_end, params, landmarker_num_faces=1)  # 창 = [t_end - window_s, t_end]
```

`rows`는 관측값 줄(`observations.csv`의 한 줄 = dict 하나)에 아래 '선택 열'을 더한 목록입니다. `landmarker_num_faces`는 그 줄을 만든 Face Landmarker의 `num_faces` 설정입니다(이 모듈은 1).

### 기준: 저장소 밖 두 문서의 원문

규칙의 기준은 아래 두 원문입니다. 원문에 없이 더한 것은 그다음 '추가 제안'에 따로 적었습니다. 인용 안의 (…)는 줄인 곳입니다.

**비전 담당 결정(2026-10-10) §3, 상황 태그 3개의 규칙표**

> 출력 한 줄 = { name(행동 이름) · display_text('…해 보임') · window_s · evidence[](관찰 이름 + 값) · source }. 모든 창 길이 · 횟수 · 각도는 `[파일럿]` — 기준 없음 / 정할 수 없음이라 팀원 자가 녹화(20번 ①)의 분포에서 정하고 그 전에는 숫자를 넣지 않습니다. 관찰 이름은 R33 ①의 표를 따릅니다.

| 태그(name) | 표시 문구 | 묶는 관찰(사실) — 전부 같은 창 안 | 빼는 조건 | 근거 수준 |
|---|---|---|---|---|
| `looking_back_with_people_behind` | 뒤에 사람이 있어 서두르는 듯함 | 뒤에 기다리는 사람(주 사용자보다 작은 상자, 뒤쪽, 멈춰 선 사람만) + 뒤돌아봄(yaw 커짐 → 얼굴 점 사라짐 · 어깨 점 남음 → 복귀) 반복 (+ 터치 빨라짐 · 빗나감, + 표정 변동은 보조) | 지나가는 사람만 있을 때 · 뒤돌아봄 없이 뒷사람만 있을 때(붐빔 자체는 근거 아님 [S2]) | 문헌 [S1][S2] + 71827 일부(뒷사람 높이 비) · 뒤돌아봄은 측정 전 |
| `consulting_companion` | 일행과 상의하는 듯함 | 동행자 있음(비슷한 크기의 두 번째 상자 · 옆) + 주 사용자 yaw가 일행 쪽 + 입 움직임(jawOpen 등 입 다이얼의 흔들림, blendshape 켜야 함) + 안 누르고 머묾, 몸 점 제자리 | 얼굴 2개면 smoothing 꺼짐 — 흔들림을 입 움직임으로 세지 않도록 | 71827 동행 라벨(2명+ 클립 10.7 %) + [S9] · 말함은 측정 전 |
| `looking_around` | 무언가를 찾는 듯함 | 화면 밖으로 크게 오가는 yaw 왕복(창 안 횟수) + 몸 점 제자리 + 터치 없음 + 뒤에 사람 없음 | 메뉴 읽기(화면 안 훑기)의 작은 yaw — 범위는 파일럿 | 문헌 [S5][S6] · 71827 없음 |

> - 고개를 크게 돌린 구간은 각도 대신 '얼굴 사라짐 + 몸 남음'으로 셉니다(…). (…)
> - 세 태그는 혼자 지원을 열지 않습니다 — 판단 층이 후보(…)를 고릅니다.

[S1] 등과 R33 ①은 비전 담당 조사 노트(research/33)의 출처 번호와 절이고, '20번 ①'은 같은 결정 목록의 항목 번호입니다. 모두 저장소 밖에 있습니다. 근거 수준 칸의 71827은 과학기술정보통신부의 재원으로 한국지능정보사회진흥원의 지원을 받아 구축된 「사람 행동 인식 로봇 자율 행동 데이터」(AI 허브, aihub.or.kr)이고, 그 칸의 비율 · 높이 비는 이 데이터의 라벨을 분석한 결과입니다.

**의미 층 설계 노트 v1.1(2026-10-11) §4, 상태 층 출력 계약과 검사 규칙**

> - 한 줄: `{ name, display_text, window_s, evidence[]: [{event_id, obs, value, t}], quality: {face_visible_ratio, track_conf}, confidence | "unknown", alternatives[], source }` (…). 결정 §3의 출력 줄에 quality · confidence · alternatives와 사건 ID를 더한 것이다.
> - 검사 규칙 1(근거 연결): 각 상태 해석은 근거 사건 ID에 연결된다. 프로그램은 ID의 존재와 시간 범위(창 안)를 검사한다. (…)
> - 검사 규칙 2(모름): 사건이 k개 미만이면 `confidence = "unknown"`이다. 품질은 단서별로 적용한다: 얼굴 소실이 유효 단서인 뒤돌아봄은 얼굴 보임 비율이 낮아도 보류하지 않고, 얼굴이 필요한 단서(입 움직임 · 표정)만 결측으로 처리한다. 센서 실패(추적 신뢰도 하한 미만, 카메라 없음)와 "얼굴이 돌아가서 안 보임"은 구분한다. 상태가 '모름'이면 판단 층은 Jev를 부르지 않고 터치 규칙만 쓴다. k · 하한은 `[파일럿]`.
> - 근거 중복: 같은 원인에서 난 관찰(한 번의 고개 돌림에서 나온 yaw 변화와 얼굴 소실)은 한 사건으로 묶어 센다.
> - 상태 수명: 시작 조건(사건 k개 충족), 유지(창 안에 새 사건), 해제(반대 근거 사건 또는 만료 창 경과), 만료 창 길이는 `[파일럿]`.
> - 복수 상태: 동시에 충족하면 지지 사건 수가 많은 것을 `name`으로, 나머지를 `alternatives[]`로 낸다. 판단 층은 대안이 있으면 보류를 고를 수 있다.
> - 동점 `[설계 제안]`(구현 2026-10-11 밤): 지지 사건 수가 같으면 `name = "unknown"`으로 내고 두 태그를 모두 `alternatives[]`에 둔다. 판단 층은 이때 터치 규칙만 쓴다. 대안에도 같은 최소 사건 수 k를 적용한다.
> - confidence: 라벨로 보정하기 전에는 확률처럼 쓰지 않고 "충족한 사건 수 / 품질"의 규칙 충족 정보로만 표시한다.

위 인용 가운데 판단 층의 동작(모름 · 동점일 때 터치 규칙만 씀, 대안이 있으면 보류를 고름)은 비전 설계 노트의 제안입니다. 판단 층 담당(AI · 백엔드)과는 아직 합의하지 않았고, 정해지면 `contract/`에 반영합니다.

### 추가 제안 (`[설계 제안]`, 위 두 원문에 없음)

- 본 근거 먼저, 세 값 논리: 창 안에서 본 근거(터치, 뒤에 선 사람, 입 움직임, 일행 쪽 yaw, 몸 움직임)는 그 열이 일부 줄에서 빠져도 씁니다. 어떤 단서가 '없다'는 결론은 필요한 관측이 빠짐없이 있을 때만 내고, 아니면 그 단서는 '모름'(None)입니다. 모름은 다른 단서가 그 태그를 빼지 않을 때만 결과를 모름으로 만듭니다. 그래서 `none`은 모든 태그가 관측된 단서로 빠졌을 때만 나옵니다.
- '없음'에 필요한 관측: 터치 · 뒷사람은 창의 모든 줄에 그 열이 있어야 합니다. 입 움직임은 얼굴 프레임마다 값이 있어야 합니다. 고개 돌림은 얼굴 프레임마다 yaw가, 얼굴이 사라진 프레임마다 어깨 값이 있어야 하고, 얼굴과 몸이 함께 끊기거나 기록이 비어 결말을 못 본 돌림이 창 안에 없어야 합니다. 일행 쪽 yaw는 yaw가 0이 아닌 얼굴 프레임마다 동행자 쪽을 알아야 합니다. 몸은 가로 · 세로 축마다 보고, 한 축이라도 `body_still_max`를 넘으면 움직임입니다. '제자리'는 몸 프레임마다 두 축 값이 다 있어야 냅니다.
- 터치 열 이름: `tap_count` · `miss_tap_count`는 명세 `TouchFeatures`의 이름과 뜻을 따르고, 세는 구간만 창 대신 직전 줄 이후입니다. 값은 명세대로 0 이상의 정수만 받습니다(CSV의 정수 문자열 포함, `1.0` 같은 실수 표기는 오류). API의 `TouchFeatures`는 1~3초 구간의 집계라 프레임 간격 집계와 경계가 다르므로, 서버로 넘길 때의 집계 경계는 계약에서 정합니다.
- 터치 횟수와 창 시작: 한 줄의 횟수는 그 줄 시각에서 끝나는 구간(직전 줄 이후)의 것으로 보고, 줄 시각이 창 안이면 그 줄을 창에 넣습니다. 그래서 창 시작 직전의 한 샘플 간격 안에서 난 터치가 창 안의 터치로 셀 수 있습니다. 원시 터치 시각을 받으면 이 한계가 없어집니다.
- 일행 쪽 yaw와 메뉴 읽기: 결정 표대로 yaw의 부호가 그 프레임의 동행자 쪽이면 각도와 상관없이 일행 쪽 yaw로 셉니다(`gap_s` 안에서 이어지면 한 구간). 그래서 동행자 옆에서 메뉴를 읽는 작은 yaw도 일행 쪽 yaw로 셀 수 있습니다. 각도 하한을 둘지는 2026-10-14 팀 촬영의 혼동 장면(S2의 '말없이 기다리는 일행')을 보고 정합니다.
- 동행자의 쪽: 그 프레임의 동행자 상자와 사용자 얼굴 위치를 견줍니다. 둘 중 하나가 없는 프레임은 `gap_s` 안에서 가장 가까운 프레임의 값을 쓰고, 그보다 오래된 위치는 쓰지 않습니다. 동행자가 근처에 있을 수 있는데(`gap_s` 안에 상자가 있거나 그 열이 빠짐) 쪽을 모르는 프레임은 '모름'으로 둡니다.
- 창 경계: 사건의 관찰 줄이 전부 창 안에 있어야 근거가 됩니다(결정 표 §3 '전부 같은 창 안', 설계 §4 '시간 범위(창 안)'). 고개 돌림은 창 끝까지의 기록에서 찾되, 창 앞의 기록은 문맥으로만 씁니다. 예를 들어 창 바로 앞의 정면 프레임에서 시작한 고개 돌림도 찾지만, 돌림의 줄이 전부 창 안일 때만 셉니다. 뒷사람 · 동행자 · 일행 쪽 yaw · 입 움직임 · 머묾 · 빗나간 터치는 창 안의 줄에서만 찾습니다. 그래서 창 앞부터 이어지는 상태는 창 안 부분이 근거가 되고, 길이 조건(`stay_min_s` · `dwell_min_s`)도 창 안 부분으로 판단합니다. 사건의 끝 시각이 창 안인 것을 고르는 안과 창과 겹치는 사건을 고르는 안은 쓰지 않았습니다. 둘 다 창 밖의 관찰이 근거에 섞이기 때문입니다.
- 창마다 다시 찾기: 창마다 창 끝까지의 기록에서 사건을 다시 찾습니다. 오프라인 재생용이고, 실시간 연결에는 앞 결과를 이어 쓰는 증분 처리가 필요합니다. 창 끝 뒤의 기록은 어느 함수도 읽지 않으므로(`detect_events`에 창을 주어도 같음) 재생 결과는 키오스크에서 낸 결과와 같습니다.
- `track_conf`: 창 안에서 몸 점이 잡힌 프레임 비율입니다(MediaPipe가 자체 기준을 넘겨 몸 점을 낸 프레임).
- 출력 세부: `window_s`는 [시작, 끝](초)이고, `evidence`는 사건의 관찰을 하나씩 펼친 목록입니다. `unknown` · `none`의 `display_text`는 빈 문자열이고, `alternatives`에는 근거 사건이 있는 태그만 둡니다.

### 규칙 3개 (구현)

1. `looking_back_with_people_behind`(뒤에 사람이 있어 서두르는 듯함): 창 안에 `people_behind` 사건이 있고, `look_back`이 `look_back_min_count`개 이상 있어야 합니다. 횟수 값은 1 이상이므로 뒤돌아봄이 실제로 있어야 맞습니다. `touch_miss`는 보조 근거라 사건 수에만 더합니다. 지나가는 사람만 있거나 뒤돌아봄이 없으면 빠집니다. 뒤돌아봄이 '없다'는 결론은 위 '없음에 필요한 관측'을 다 갖췄을 때만 냅니다(결말을 못 본 돌림이 있으면 모름).
2. `consulting_companion`(일행과 상의하는 듯함): `companion_present`, `yaw_toward_companion`, `mouth_moving`, `dwell_no_touch`가 모두 있어야 합니다. 일행 쪽 yaw는 yaw의 부호가 그 프레임의 동행자 쪽인 구간입니다(각도 하한 없음, 위 '추가 제안'). 창 안에 터치가 없고, 몸이 제자리여야 합니다(어깨 가운데가 움직인 범위가 `body_still_max` 이하). 일행 쪽 yaw는 얼굴이 필요해서, 얼굴 보임 비율이 `face_visible_min` 미만이면 잴 수 없음(모름)이 됩니다. 본 일행 쪽 yaw는 그대로 쓰고, '없다'는 yaw가 0이 아닌 얼굴 프레임마다 동행자 쪽을 알 때만 냅니다. 입 움직임은 본 움직임이 있으면 맞고, '없다'는 얼굴 프레임마다 값이 있을 때만 냅니다. 값이 모자라거나 smoothing이 꺼졌거나 얼굴 보임 비율이 모자라면 그 단서만 빼고 나머지로 판단하고, `quality_ok`를 false로 둡니다.
3. `looking_around`(무언가를 찾는 듯함): 화면 밖 고개 돌림이 `sweep_min_count`개 이상이어야 합니다. `look_back`은 늘 세고, `yaw_sweep_offscreen`은 얼굴 보임 비율이 `face_visible_min` 이상일 때만 셉니다. 창 안에 터치가 없고, 몸이 제자리이고, 뒤에 선 사람이 없어야 합니다. 본 터치 · 뒤에 선 사람 · 몸 움직임은 그 열이 일부 줄에서 빠져도 이 태그를 뺍니다. `dwell_no_touch`는 있으면 근거에 더하고, 없어도 됩니다. 메뉴를 읽는 작은 yaw는 `offscreen_yaw_deg` 안에 머물러 사건이 되지 않습니다.

### 사건 8종

| 사건 | 찾는 방법 | 쓰는 규칙 |
|---|---|---|
| `look_back` 뒤돌아봄 | 화면을 보던 얼굴이 `offscreen_yaw_deg`를 넘어 돌아가고, 얼굴 점이 사라진 동안 어깨 점이 남고(`shoulder_vis_min`), 다시 화면 쪽으로 돌아옴. yaw 변화 · 얼굴 사라짐 · 어깨 남음을 따로 세지 않고 사건 하나로 셈 | 1 · 3 |
| `yaw_sweep_offscreen` 화면 밖 고개 돌림 | 같은 돌림인데 얼굴이 끝까지 보임. 돌아간 쪽(왼쪽 · 오른쪽)을 함께 적음 | 3 |
| `people_behind` 뒤에 선 사람 | `people_behind_count`가 1 이상인 구간이 `stay_min_s` 이상 이어짐. 더 짧으면 지나가는 사람으로 보고 세지 않음 | 1 · 3(빼는 조건) |
| `companion_present` 동행자 | `companion_box`가 있는 구간(머문 시간 조건 없음) | 2 |
| `yaw_toward_companion` 일행 쪽 yaw | 얼굴이 보이고, yaw의 부호가 그 프레임 동행자 쪽인 구간(각도 하한 없음). 동행자 쪽은 그 프레임의 상자와 얼굴 위치로 정함. 화면 쪽으로 돌아오지 않아도 됨 | 2 |
| `mouth_moving` 입 움직임 | 얼굴이 보이는 프레임에서 `mouth_motion`이 `mouth_motion_min` 이상. Face Landmarker의 `num_faces`가 1이 아니면 smoothing이 꺼지므로 찾지 않음 | 2 |
| `dwell_no_touch` 안 누르고 머묾 | 사람이 보이고 터치 없이 `dwell_min_s` 이상 지남. 터치가 들어오면 끊김 | 2 · 3(보조 근거) |
| `touch_miss` 빗나간 터치 | `miss_tap_count`가 0보다 큼 | 1(보조 근거) |

동행자 쪽으로 화면 밖까지 고개를 돌렸다가 돌아오면, 같은 프레임에서 `yaw_sweep_offscreen`(두리번거림의 단서)과 `yaw_toward_companion`(상의의 단서)이 함께 생깁니다. 한 규칙 안에서는 한 번만 셉니다.

`gap_s`는 한 사건으로 이어 볼 두 관측 사이의 가장 긴 시간입니다(잠깐 끊김을 거르는 시간 창). 이웃한 줄도 시각 차이로 판단하므로 평소 프레임 간격보다 커야 하고, 이보다 긴 공백(끊김이나 빠진 기록)이 있으면 사건이 끊깁니다.

### 출력 형식

창 하나에 한 줄을 냅니다. 아래는 테스트의 합성 창(`test_person_behind_and_repeated_look_backs`, 창 길이만 3초로 바꿈)에서 나온 실제 출력이고, 소수는 둘째 자리까지 줄였습니다. 숫자는 합성 프레임의 값이고 기준값이 아닙니다.

```json
{
  "name": "looking_back_with_people_behind",
  "display_text": "뒤에 사람이 있어 서두르는 듯함",
  "window_s": [0.0, 3.0],
  "evidence": [
    {"event_id": "people_behind@0", "obs": "people_behind_count", "value": 1, "t": 3.0},
    {"event_id": "people_behind@0", "obs": "stay_s", "value": 3.0, "t": 3.0},
    {"event_id": "look_back@5", "obs": "yaw_deg", "value": 60.0, "t": 1.3},
    {"event_id": "look_back@5", "obs": "side", "value": "right", "t": 1.3},
    {"event_id": "look_back@5", "obs": "face_lost_s", "value": 0.6, "t": 1.3},
    {"event_id": "look_back@5", "obs": "pose_vis_shoulders", "value": 0.9, "t": 1.3},
    {"event_id": "look_back@18", "obs": "yaw_deg", "value": 60.0, "t": 2.6},
    {"event_id": "look_back@18", "obs": "side", "value": "right", "t": 2.6},
    {"event_id": "look_back@18", "obs": "face_lost_s", "value": 0.6, "t": 2.6},
    {"event_id": "look_back@18", "obs": "pose_vis_shoulders", "value": 0.9, "t": 2.6}
  ],
  "quality": {"face_visible_ratio": 0.68, "track_conf": 1.0},
  "confidence": {"events": 3, "quality_ok": true},
  "alternatives": [],
  "source": "rules_v1"
}
```

- `name`: 태그 이름, `unknown`(판단할 수 없음), `none`(모든 태그가 관측된 단서로 빠짐) 가운데 하나입니다.
- `display_text`: 태그마다 정해 둔 문구(`DISPLAY_TEXT`)만 씁니다.
- `evidence`: 근거 사건의 관찰을 한 줄씩 펼친 목록입니다. 근거 사건은 관찰 줄이 전부 창 안에 있습니다. `event_id`는 `사건 종류@첫 프레임 번호`이고, `t`는 사건이 끝난 시각(초)입니다. 위의 `look_back@5` 관찰 넷은 고개를 한 번 돌린 사건 하나에서 나왔고, 1.3초는 얼굴이 화면 쪽으로 돌아온 시각입니다.
- `quality`: `face_visible_ratio`는 창 안에서 얼굴이 보인 프레임 비율이고, `track_conf`는 몸 점이 잡힌 프레임 비율입니다.
- `confidence`: 확률이 아닙니다. 라벨로 보정하기 전이라 근거 사건 수(`events`)와, 결측이라 뺀 단서가 없는지(`quality_ok`)만 적습니다. `contract/`의 `VisionFeatures.confidence`(0~1 측정 신뢰도)와 이름만 같고 뜻과 형식이 다릅니다. 다른 서비스로 보내는 형식을 정할 때 이름을 다시 정합니다.
- `alternatives`: 관측된 단서로 빠지지 않았고 근거 사건이 있는 다른 태그입니다. 근거 사건이 많은 순서이고, 항목마다 `name` · `display_text` · `evidence` · `confidence`가 있습니다. 근거 사건이 `min_events`개보다 적은 대안의 `confidence`는 `unknown`이고, 대안마다 이 창의 근거 사건이 하나 이상 있어야 합니다.

검사 규칙 두 개는 `check_output`이 코드로 확인합니다. `assess`가 낸 출력이 규칙을 어기면 오류가 납니다.

1. 근거 연결: `evidence`의 모든 항목은 이 창의 사건 ID를 가리킵니다. 그 사건의 관찰 줄은 전부 창 안에 있고, 항목의 `t`는 사건이 끝난 시각이며, 관찰 이름과 값은 그 사건의 관찰과 같습니다.
2. 모름: 아래 경우에 `unknown`을 냅니다.
   - 근거 사건이 `min_events`개보다 적을 때. 대안에도 같은 기준을 적용합니다
   - 꼭 필요한 단서를 잴 수 없을 때: 입력 열이 없거나, 얼굴이 필요한 단서인데 얼굴 보임 비율이 `face_visible_min` 미만일 때
   - 몸 추적 비율이 `track_conf_min` 미만일 때(센서 실패로 보고 규칙을 읽지 않음)
   - 두 태그가 함께 맞고 근거 사건 수가 같을 때(설계 노트 §4의 동점 행, `[설계 제안]`). 수가 다르면 많은 쪽이 `name`이 되고 다른 쪽은 `alternatives`에 들어갑니다

   얼굴이 사라지는 것은 뒤돌아봄의 단서이므로, 얼굴 보임 비율이 낮아도 뒤돌아봄 태그는 막지 않습니다. `none`은 모든 태그가 관측된 단서로 빠졌을 때만 냅니다. 그래서 선택 열이 하나도 없는 지금의 `observations.csv`만 넣으면, yaw가 0이 아닌 얼굴 프레임이 하나라도 있는 한 출력은 `unknown`입니다(동행자 쪽을 몰라 상의 태그를 뺄 수 없음).

`check_output`은 출력의 형식도 봅니다. `window_s`는 유한한 [시작, 끝](시작 ≤ 끝)이어야 하고, `quality`의 두 비율은 0~1이어야 합니다(프레임이 없는 창은 `unknown`과 빈 값). 표시 문구는 이름마다 정해 둔 문구여야 하고(자유 문장 없음), 대안마다 이 창의 근거 사건이 있어야 합니다. 확정 `confidence`를 가진 대안도 `track_conf_min`을 지켜야 합니다. 형식이 틀린 출력은 예외 대신 문제 목록으로 돌려줍니다.

상태 수명: 창은 `t_end`와 함께 밀립니다. 창 안의 근거 사건이 `min_events`개 이상이면 상태가 시작됩니다. 고개 돌림은 첫 줄이 창 밖으로 나가면 근거에서 빠지고, 이어지는 상태(뒷사람 · 머묾 등)는 창 안 부분이 조건을 못 채우면 빠집니다(`window_s` = 만료 창). 반대 근거(터치, 뒤에 선 사람, 몸 이동)가 창에 들어와도 풀립니다.

### 선택 열 (2026-10-22부터 `columns.py` · `touch.py`가 만듦)

규칙이 쓰는 선택 열은 재생 · 실시간 실행기가 프레임마다 만듭니다(`run.py`의 `observations.csv`에는 없음). 사건은 값이 있는 곳에서 찾고, 본 근거는 열이 일부 줄에서 빠져도 씁니다. 어떤 단서가 '없다'는 결론은 그 열이 창의 모든 줄에 있을 때만 냅니다(입 움직임 · 어깨 위치는 얼굴 · 몸이 보인 프레임마다 값이 있어야 함). 그렇지 않으면 0으로 채우지 않고 결측으로 봅니다. 몸 움직임은 축마다 보고, '제자리'는 몸 프레임마다 두 축 값이 다 있고 두 번 이상 관측돼야 판단합니다. 횟수 열은 명세 `TouchFeatures`처럼 0 이상의 정수여야 하고, 다른 값이 오면 오류를 냅니다(빈칸은 결측). 기준값과 출처는 위 '[파일럿] 값과 출처'에 있습니다.

| 열 | 뜻 | 만드는 곳 |
|---|---|---|
| `people_behind_count` | 주 사용자 뒤에 선 사람 수: 주 사용자 · 동행자가 아닌 머리 상자 가운데 넓이가 주 사용자의 `behind_max_area_ratio`배 미만인 것(결정 §3 '주 사용자보다 작은 상자'). 머리가 하나도 없으면 0. 멈춰 섰는지는 사건 층(`stay_min_s`)이 봄 | `columns.py`(H1 머리 상자). H1 파일이 없으면 열이 없음(결측) |
| `companion_box` | 주 사용자가 아닌 머리를 큰 순서로 보며, 넓이 비 `companion_min_area_ratio` 이상('비슷한 크기')이고 머리 중심 사이가 주 사용자 머리 폭의 `companion_max_dist_widths`배 이하('옆')인 첫 머리의 상자 `(x0, y0, x1, y1)`, 화면 비율. 맞는 머리가 없으면 `None`. '옆'에 가로 방향 조건은 없어(출처 없음) 바로 뒤의 비슷한 크기 머리도 동행자로 셀 수 있음 | 같은 곳 |
| `mouth_motion` | 입 · 턱 blendshape 27개(`mouth_dials`) 가운데 기준선에서 가장 많이 바뀐 값. 기준선은 같은 얼굴 연속 구간의 직전 `mouth_baseline_s`초 중앙값입니다(결정 목록 2026-10-10 §16: 사람별 기준선을 뺀 변화만). 얼굴을 못 본 프레임, 연속 구간이 `mouth_baseline_s`보다 짧은 동안, blendshape를 끈 실행은 빈칸 | `columns.py`(MediaPipe blendshape, 실행기에 `--blendshapes`를 줄 때만 켬) |
| `shoulder_cx` · `shoulder_cy` | 어깨 두 점(11 · 12)의 가운데, 화면 비율. 몸을 못 본 프레임은 빈칸 | `columns.py`(몸 점) |
| `tap_count` · `miss_tap_count` | 직전 줄 이후의 누름 · 버튼 밖 누름 횟수(아래 '터치 로그'). 이름과 뜻은 `contract/frontend-backend.openapi.yaml`의 `TouchFeatures`를 따르고(0 이상의 정수), 세는 구간만 프레임 간격. 터치 로그가 관측하지 않은 구간의 줄은 빈칸(아래 '터치 로그')이고, 대상 정보가 없는 누름이 든 구간은 `miss_tap_count`가 빈칸 | `touch.py` · `chain.py`(재생만. 실시간에는 터치 로그가 없음) |
| (관측만) `head_count` · `primary_box` · `primary_score` · `primary_from` | 머리 상자 수, 주 사용자 머리 상자 · 점수 · 고른 방법(`face` = 얼굴을 품은 상자, `largest` = 가장 큰 상자). 읽는 규칙 없음 | `columns.py` |
| (관측만) `head_dir_middle` · `head_dir_up` · `head_dir_left` · `head_dir_right` · `head_dir_back` | 주 사용자 머리의 P1 확률(중간 · 위 · 좌 · 우 · 뒤; AI Hub 70 '촬영방향' = 카메라가 사람을 보는 방향). 읽는 규칙 없음. P1 시험에서 '뒤' 재현율은 30.2 %였음 | `columns.py`(P1) |

주 사용자는 `primary_rule`(`[파일럿]` 규칙)로 고릅니다. 기본값 `face_then_largest`는 Face Landmarker가 따라가는 얼굴의 중심(`face_cx`, `face_cy`)을 품은 머리 상자 가운데 가장 큰 것을 고르고, 그런 상자가 없으면 가장 큰 상자를 고릅니다(같으면 화면 가운데에 가까운 것). 얼굴을 품은 상자를 고른 프레임(`primary_from` = `face`)에서는 yaw · 입 움직임 · 머리 상자가 같은 사람의 값입니다. 얼굴을 못 본 프레임은 가장 큰 상자를 고르므로 사람이 바뀔 수 있습니다.

### 터치 로그 (`touch.py`)

- 입력: 주문 화면 개발 모드의 'JSON 내보내기' 파일(`touchLog.ts`의 `SavedLog`). 원시 기록은 계약이 아니라 로컬 초안입니다(`docs/Touch-Log-Review.md` 1 · 7장).
- 시간축: 녹화 옆 `<영상>.clock.json`이 있으면 터치 시각 = (`occurredAt` − `first_frame.wall_epoch_ms`) ÷ 1000초이고, `--start-offset`은 그 위에 더하는 보정입니다. 시계 파일이 없으면 `--start-offset` = 터치 로그 첫 기록의 영상 시각입니다(촬영 대본 §4 '시각 맞추기', 저장소 밖).
- 세는 방법(`[설계 제안]`: 팀 기준 T01 · T02 · T08이 미정이라 프론트의 요약 코드 `touchLogSummary.ts`를 따름): 누름 = `pointer_start`, 버튼 밖 누름 = `data.target`이 `null`인 `pointer_start`(요약의 `outsideTargetPresses`; 비활성 버튼을 누른 것은 버튼 밖이 아님), 되돌아감 = `review`에서 `menu`로 가는 `screen_enter`(`← 메뉴 더 고르기`와 로고 링크). `complete`에서 `menu`는 새 주문이라 세지 않습니다. `repeat_tap_count` · `dwell_ms`는 기준이 정해지지 않아(T04 · T05) 세지 않습니다. 빗나감 뒤 바로 고침(`near_miss_fix_count`) = 버튼 밖 누름 뒤 같은 세션의 다음 누름이 그 누름의 가장 가까운 버튼 목록(`nearestCandidates`) 안의 버튼이면 1회(T03 · T07 미정). 대상 정보가 없는 누름이 구간에 있으면 `miss_tap_count` · `near_miss_fix_count`는 빈칸입니다.
- 관측 구간: 첫 기록(또는 `session_start` · `session_resume`)부터 다음 `session_end` · `session_suspend`까지를 관측한 것으로 보고, 마지막 기록 뒤 멈춤 기록이 없으면 내보낼 때까지 열려 있던 것으로 봅니다. 구간이 관측 구간에 통째로 들 때만 횟수를 내고(안에 터치가 없으면 0), 첫 기록 전이나 걸친 구간은 결측입니다. 로그가 1,000개(`touchLog.ts`의 상한)면 앞 기록이 잘렸을 수 있어 경고하고(`meta.touch.warnings`), 시계 파일 없이 `--start-offset`으로는 놓을 수 없어 오류입니다. 세션 목록(`meta.touch.sessions`)과 관측 구간(`spans`)도 기록합니다.

## 테스트

```powershell
.venv\Scripts\python.exe -m unittest tests.test_vision tests.test_situation tests.test_vision_chain -v
```

- 관측값 층: 테스트 안에서 만든 가짜 추론 결과(눈꼬리 위치를 정해 둔 얼굴 점, 몸 점, 검출 상자)로 눈 사이 거리 · 시작 대비 비율 · 얼굴 위치 · 연속 구간 · 몸 점 평균 · 밝기를 계산해 정해진 값과 같은지 봅니다. MediaPipe와 모델 파일 없이 돌아갑니다(numpy · OpenCV만 필요).
- 상황 층(`tests/test_situation.py`): 테스트 안에서 만든 합성 관측 줄(초당 10장)로 태그마다 맞는 경우 · 빼는 조건 · `unknown` · 대안 · 동점을 보고, 긴 시간 공백 · 값이 빈 열 · 일부 줄이 빠진 열 · 창 이동(상태 유지와 만료) · 창 시작의 터치 · 창 뒤의 줄 · 얼굴과 몸이 함께 끊긴 돌림도 봅니다. 고개 한 번이 사건 하나인지와 검사 규칙(사건 ID · 관찰 줄의 창 · 고정 문구 · 최소 사건 수 · 대안의 근거 · 창과 품질의 형식)을 확인합니다. `PilotParams`에 기본값이 없는지, `situation.py`에 숫자가 없는지도 봅니다. 테스트의 값은 합성 프레임용이고 기준값 제안이 아닙니다. 표준 라이브러리만 쓰므로 서버 패키지만 깔린 환경에서도 돌아갑니다(`features.py`와 표시 값을 맞춰 보는 1개만 OpenCV가 없으면 건너뜀).
- 추론까지: 테스트 안에서 만든 빈 화면 프레임으로 MediaPipe 모델을 실제로 돌려 CSV 열 구성, '못 봄' 상태, 처리 시간 기록을 확인합니다(모델 파일 필요).
- 그 밖: 연속 구간 계산, 고개 각도 분해, 실측 초당 장수 공식.
- 녹화 클립의 시각 파일(`<영상>.times.csv`): 완전한 파일만 받아들이고, 번호가 빠지거나 시각이 되돌아가면 오류로 멈추는지 봅니다(3개). 눈 사이 거리가 0인 기준 프레임이면 비율이 빈칸이 되는지도 봅니다.
- 실행 파이프라인(`tests/test_vision_chain.py`, 53개; 환경 변수가 없으면 52개 실행): 값과 출처(기본값 · 범위 · 값 묶음 파일), H1 후처리(letterbox · 격자 · 디코딩 · NMS, 점수 거르기 순서가 결과를 바꾸지 않음, ONNX 대신 가짜 세션으로 전체 호출), P1 입력(정사각 크롭 · 회색 바깥 · RGB · 정규화), 선택 열(주 사용자 · 동행자 · 뒤 사람 · 어깨 · 입 움직임 기준선), 터치 로그(시계 파일 · 시작 오프셋 · 누름 · 버튼 밖 · 빗나감 뒤 바로 고침 · 되돌아감 · 관측 구간 · 세션 · 1,000개 잘림 · 옵션 창 상태), 규칙표 v0(장면 4개의 여는 조건 · 고개 방향 게이트 · 미룸의 전제 · 순서 · 교체 · 기다림의 신호와 재진입 · 유지 결정의 내용 · 실행 칸 · 무응답 · 거절 · 범위, 규칙표에 숫자가 없음), 창 판단(`WindowJudge`: 고른 뒤 멈춤 · 얼굴 없는 몸 · 세션 초기화), 모름 이유(열 결측 · 센서 실패 · 동점 · 근거 부족, 모든 `unknown` 창에 이유가 있음), 창 기록이 전체 기록과 같은 결과를 내는지, 가짜 추론 결과로 돌린 재생(두리번 태그가 나오고 4-2 강조가 열리는지, 계약 형식 검사: `UIPreset` · `decided_by` 목록과 팀 pydantic `AnalyzeResponse`), 창 없는 실시간(가짜 카메라), 그린 영상으로 돌린 실제 모델 재생(창 1초 · 2초 · 남은 0.9초, 머리 상자 0: 도형이라 H1 → P1 경로는 안 돎)을 봅니다. 사람 머리 사진으로 H1 → P1을 확인하는 테스트는 환경 변수 `VISION_TEST_HEAD_IMAGE`에 사진 경로를 줄 때만 돌고, 사진은 저장소에 두지도 보여 주지도 않습니다. 숫자는 합성 입력용이고 기준값 제안이 아닙니다. ONNX 파일이나 MediaPipe가 없으면 그 테스트만 건너뜁니다.
- 사진 · 사람이 나온 영상 · `runs/`는 쓰지 않습니다(재생 시험의 영상은 테스트가 도형을 그려 만듦). 필요한 패키지나 모델 파일이 없으면 그 테스트만 건너뛰므로, 서버 패키지만 깔린 환경의 `python -m unittest discover -s tests`에는 영향이 없습니다.

## V 모델 추적표 (실행 파이프라인, 2026-10-22)

요구에서 코드로 내려가고, 같은 높이의 검사로 올라옵니다. '결과에서 보는 것'은 결과 파일에서 직접 확인할 항목입니다.

| # | 요구 | 코드 | 검사 | 결과에서 보는 것 |
|---|---|---|---|---|
| V1 | 머리 상자를 키오스크 PC의 CPU에서 찾는다(H1) | `app/inference/head.py`, `tools/export_onnx.py` | 변환 확인(ONNX와 PyTorch의 출력 차이 · NMS 뒤 상자, `models/onnx_export.json`), `HeadPostprocessTests`, `OnnxModelTests` | `models/README.md` 표의 크기 · 해시, '처리 시간'의 `ms_heads` |
| V2 | 주 사용자 머리의 방향 확률(P1) | `app/inference/head_direction.py` | 변환 확인(logits 차이, 입력 변환과 torchvision의 차이), `HeadDirectionInputTests`, `OnnxModelTests` | `rows.csv`의 `head_dir_*` |
| V3 | 규칙이 쓰는 선택 열(뒤 사람 · 동행자 · 어깨 · 입 움직임) | `columns.py`, `chain.py` | `ColumnsTests`, `FrameChainTests` | `rows.csv`의 선택 열, `windows.jsonl`의 `vision` |
| V4 | 터치 로그를 영상 시간에 맞춰 센다 | `touch.py` | `TouchTests` | `windows.jsonl`의 `touch` · `screen`, `meta.json`의 `touch.anchor` |
| V5 | 창마다 상황 태그 · 근거 사건 ID · 모름 이유 · 대안 | `chain.py`(`WindowJudge`, `unknown_reasons`), `situation.py` | `UnknownReasonTests`, `HistoryTests`, `ReplayWithFakePerceptionTests` | `windows.jsonl`의 `situation` |
| V6 | 판단 층 규칙표 v0(장면 4개)와 Jev 그림자 기록 | `judgment/` | `RuleTableTests`, `WindowJudgeTests` | `windows.jsonl`의 `decision` · `session` · `jev` |
| V7 | 기존 계약 형식으로 바꾸고, 없는 칸은 `extension`에 | `contract_view.py` | `test_contract_view_fits_the_existing_contract`(`UIPreset` · `decided_by` 목록, 팀 pydantic `AnalyzeResponse`) | `windows.jsonl`의 `contract` |
| V8 | 녹화 재생과 웹캠 실시간 | `replay.py`, `live.py` | `ReplaySmokeTests`(그린 영상 + 실제 모델; 남은 구간 창, 머리 상자 0), `LiveTests`(창 없음, 가짜 카메라) | `replay`의 마지막 콘솔 줄, `live`의 창마다 한 줄 |
| V9 | 재료가 빠지면 모름으로 | 모든 층 | `test_without_touch_log_or_values_the_tags_stay_unknown_with_reasons`, `test_missing_sources_leave_their_columns_missing` | `unknown_reason`의 코드 |
| V10 | 처리 시간을 잰다 | `replay.py`(`meta.json`의 `timing_ms`) | 같은 조건 3번(위 '처리 시간') | '처리 시간'의 표 |

검증 없음: 실제 웹캠으로 돌린 실행(아직 하지 않음), `live.py`의 창 모드, 2026-10-28 촬영본의 재생. 키오스크 시점의 H1 · P1은 회사 제공 영상 1개(비공개, 저장소 밖)로만 봤습니다(아래 '아직 하지 않는 것'의 키오스크 시점).

## 아직 하지 않는 것

- 연결: 재생 · 실시간 실행기까지 이었습니다. 엔드포인트(`app.main`)와 backend로 보내는 길은 없습니다.
- 기준값: 상황 규칙 13개는 값 묶음 파일로만 들어갑니다. 출처나 공개 데이터로 고정한 값 묶음은 아직 없습니다(결정 목록 2026-10-13의 3 · 19번). 실행 파이프라인의 `[파일럿]` 값 11개도 시작값입니다(위 '[파일럿] 값과 출처').
- 터치 매핑: 누름 · 버튼 밖 누름 · 빗나감 뒤 바로 고침 · 되돌아감을 원시 기록에서 세는 방법은 `[설계 제안]`입니다(T01 · T02 · T03 · T07 · T08 미정). `repeat_tap_count` · `dwell_ms`는 세지 않습니다(T04 · T05).
- 판단 층: 규칙표 v0는 장면 3-1 · 3-2 · 4-1 · 4-2만 다룹니다. 세션 신호(2-2 · 자리 비움), 시작 지원(1-1 · 1-2), 2-1, 직원 호출(조건 미정)은 없습니다. 3-2의 고개 숙임 길은 `look_down` 사건이 없어 빠졌습니다. Jev는 질문을 기록만 하고, 세 문턱(`T_LOWER` · `T_AID` · `T_CHOICE`)은 기준이 없어 비어 있습니다. 판단 층 코드의 자리(이 모듈 또는 `app/modules/decision/`)는 팀이 정합니다(2026-10-14 안건 6). 재생에 사용자 반응(수락 · 거절 · 원래대로)을 넣는 입력 경로는 없고(프론트에 지원 UI가 생긴 뒤 기록 형식부터), `react()` 함수만 있습니다.
- 키오스크 시점: H1 · P1의 정확도는 공개 데이터의 숫자뿐입니다(H1 Open Images 검증 AP50 64.2, P1 시험 '뒤' 재현율 30.2 %). 회사 제공 키오스크 영상 1개(비공개, 저장소 밖; 한 사람, 15초, 463장)로 돌려 본 결과 H1은 448장에서 머리 상자를 찾았고(점수 중앙값 0.83), P1은 얼굴이 보이는데도 '뒤'를 89 %로 내 키오스크 시점에서는 이대로 쓸 수 없습니다(규칙은 P1 값을 읽지 않음). 2026-10-28 촬영본에서 다시 봅니다.
- 2026-10-28 재생 준비: 촬영 전에 있어야 하는 것은 출처를 적은 값 묶음 파일, 테이크마다 영상 · `.times.csv` · `.clock.json` · 터치 로그의 짝과 세션 대응, 1,000개를 넘기지 않는 로그 수집(테이크마다 새 로그), 화면 문맥(옵션 창 · 장바구니)과 강조 대상의 대응, 반응 · 설정 기록 형식, 상황 · 허용 행동 라벨표의 형식입니다. 촬영 뒤에 하는 것은 구간 라벨 작성과 `windows.jsonl`을 라벨과 대조하는 평가 스크립트(창 · 라벨 대응, `unknown` 사유, 태그별 맞음 · 틀림 · 놓침, 허용 밖 제안, 첫 제안 시각, 평가에서 뺀 구간)입니다.
- 실제 웹캠: `live.py`는 가짜 카메라로만 시험했습니다. 창 모드도 화면에서 확인하지 않았습니다.
- 서버 연결: 비전 관측 뼈대는 서버에 연결하지 않았고 엔드포인트가 없습니다. 기존 `VisionFeatures` 4칸 형식은 있지만, 새 관측값과 상황 태그의 전달 형식은 아직 합의하지 않았습니다(추가형 명세 제안). 카메라 영상을 ai-engine으로 보내는 방식도 `contract/`에서 정합니다(루트 `README.md`).
- 처리 위치: 설계안은 키오스크 PC에서 계산하고 서버에는 값만 보내는 쪽입니다(루트 README '구성별 책임', 2026-10-16). 팀 확인은 PR #48 리뷰에서 받습니다.
- 표정: blendshape 설정은 생겼고(`MediaPipeModels(blendshapes=True)`; 실행기에서 `--blendshapes`로만 켜고 기본은 꺼짐) 입 움직임에만 씁니다. 표정 변동을 상황 층에 넣는 일과 표정 모델은 없습니다. 감정 이름은 붙이지 않습니다.
- 보조기구: 휠체어 · 목발은 공개 데이터(Open Images)로 기성 탐지기(Grounding DINO · OWLv2 · Florence-2)의 baseline을 평가하는 중이고(2026-10-15, GPU 서버), 보행기는 보류입니다. 학습 여부는 평가 결과를 본 뒤 정합니다.
- 실기기(G10): 측정 시점 미정(2026-10-10). 처리 시간은 개발 노트북 값뿐입니다.
- 구간 모델: 학습용 영상(TS_)은 받지 않았고 Validation만으로 한 파일럿입니다. 키오스크용 모델의 ONNX · CPU 지연은 아직 없습니다.
- 브라우저 실시간 화면(대시보드) · 웹캠 녹화 도구: 시제품에만 있고 이 저장소에는 없습니다.
- 서버의 판단: ai-engine `/v1/analyze`의 판단은 자리 표시이고, 백엔드 지원 응답은 늘 `preset=none`입니다(`backend/README.md`).
- 상황 태그를 실을 명세 칸과 `StateScores`와의 관계: 2026-10-14 회의 안건(V04)입니다.

## CSV 열

빈칸 = 얼굴이나 몸을 못 본 프레임이라 계산할 수 없는 값(0이 아님). 예외: 못 봤을 때 `face_run_s` · `body_run_s`는 0이고 `face_unseen_s` · `body_unseen_s`가 채워집니다.

| 열 | 뜻 |
|---|---|
| `frame_idx` · `src_frame` · `t_s` | 처리한 프레임 번호(0부터) · 원본 프레임 번호나 파일 이름 · 프레임 시각(초; 파일 = 번호 ÷ 초당 장수, 카메라 = 잡은 시각, 첫 프레임 0) |
| `source_kind` · `syn_phase` | 입력 종류(영상 · 이미지 · 카메라 · 합성) · 합성 입력의 단계(저장소 밖 생성기로 만든 이미지 폴더의 `manifest.json`에서 읽음, 그 밖의 입력은 빈칸) |
| `face_state` · `body_state` | 얼굴 · 몸 보임 / 못 봄(모델 결과 유무). 결과가 비면 '못 봄'이고 '사람 없음'이 아님 |
| `face_count` | 얼굴 검출 결과 개수 |
| `iod_px` · `iod_frac_w` · `iod_ratio_start` | 눈 사이 거리(px, 두 눈꼬리 쌍 33·133, 362·263의 중심 사이) · ÷ 화면 폭 · 세션의 첫 얼굴 프레임 대비 비율 |
| `yaw_deg` · `pitch_deg` · `roll_deg` | 고개 방향(도): 얼굴 변환 행렬의 회전을 OpenCV `RQDecomp3x3`으로 나눈 각. 부호는 MediaPipe 얼굴 기하 공간(오른손 좌표계, 카메라는 원점에서 −Z 방향을 봄 — MediaPipe Face Mesh 문서)과 "+ 회전 → + 각"(테스트로 고정)에서 풀어 쓴 방향입니다: yaw + = 화면 오른쪽, pitch + = 아래, roll + = 반시계. 실제로 고개를 돌린 영상으로는 아직 확인하지 않았습니다 |
| `dyaw_start_deg` · `dpitch_start_deg` | 세션 첫 얼굴 프레임 대비 yaw · pitch 차이 |
| `face_cx` · `face_cy` · `face_y_max` | 얼굴 점 상자 중심(0~1) · 얼굴 점의 가장 아래 y |
| `face_run_id` · `face_run_s` · `face_unseen_s` | 얼굴이 이어서 보인 구간 번호 · 그 구간의 지난 시간(초) · 마지막으로 본 뒤 지난 시간(초) |
| `face_shift` · `iod_step` | 직전 '보임' 프레임 대비 얼굴 중심 이동 ÷ 화면 폭 · 눈 사이 거리 비 |
| `body_run_s` · `body_unseen_s` | 몸의 같은 값 |
| `face_det_score` · `det_box_w_frac` | 가장 높은 얼굴 검출 점수(0~1) · 그 상자 폭 ÷ 화면 폭 |
| `pose_vis_mean` · `pose_pres_mean` · `pose_vis_shoulders` | 몸 33점의 visibility · presence 평균 · 어깨 두 점(11 · 12) visibility 평균 |
| `bright_frame` · `bright_face` | 밝기 = 회색조 평균(0~255), 화면 전체 · 얼굴 점 상자 안 |
| `lapvar_frame` · `lapvar_face` | 선명도 = 라플라시안 분산(클수록 선명), 화면 전체 · 얼굴 점 상자 안 |
| `ms_read` · `ms_prep` · `ms_face_lm` · `ms_face_det` · `ms_pose` · `ms_features` · `ms_quality` · `ms_total` | 단계별 처리 시간(ms): 파일 읽기 · 입력 준비 · 얼굴 점 · 얼굴 검출 · 몸 점 · 기하 계산 · 밝기와 선명도 · 합계(입력 준비부터, 파일 읽기 제외) |

재생의 `rows.csv`는 위 열 뒤에 선택 열(위 '선택 열'), 터치 횟수, 처리 시간 넷을 붙입니다: `ms_heads`(H1 전처리 · 추론 · 후처리), `ms_head_dir`(P1 크롭 · 추론), `ms_chain`(프레임 한 장의 파이프라인 전체, 벽시계), `cpu_ms_chain`(같은 구간의 프로세스 CPU 시간; 이 PC에서는 15.6 ms 단위로 올라감). 상자 칸은 `x0;y0;x1;y1`입니다.

## 발표·보고서에 쓸 수 있는 데이터 (라이선스 대장, 비전 담당 작업 노트 기준)

- AI Hub 71827 · 82: 원본 영상 · 프레임 · 라벨은 발표 · 보고서 · 시연에 넣지 않습니다(허용 문구 없음). 집계 숫자 · 그래프와 학습한 모델만 쓰고, 출처 문구(한국지능정보사회진흥원 사업결과 · 데이터셋 정식 명칭 · AI 허브)를 붙입니다. 데이터를 볼 사람은 각자 승인받습니다.
- AFLW2000-3D: 비상업 연구 전용. 사진은 어디에도 띄우지 않고 숫자만 씁니다. 제품 경로에 쓰지 않습니다.
- Open Images: 주석 CC BY 4.0, 사진 CC BY 2.0(사진마다 표기 확인). 사진을 쓰면 저작자 · 제목 · 주소 · 라이선스 주소와 변경 표시가 필요합니다. 지금은 발표 · 보고서에 넣지 않습니다(넣을지는 비전 담당 결정).
- 연구 전용 가중치(ImageNet ResNet-50 · ResNet-18)로 낸 숫자는 '연구 숫자'로만 적고 제품 성능처럼 쓰지 않습니다.
- 머리 방향 분류기(P1)는 ImageNet 가중치 없이 무작위 초기값에서 AI Hub 70으로 학습해서 제품 경로에 쓸 수 있고, 쓸 때 NIA 출처 문구를 붙입니다(`models/README.md`). 머리 탐지기(H1)는 Open Images 주석 출처와 YOLOX Apache-2.0 고지를 함께 둡니다.
