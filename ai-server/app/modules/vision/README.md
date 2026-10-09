# 비전 관측 뼈대 (`app/modules/vision/`)

카메라나 영상 파일의 프레임마다 MediaPipe 3종(얼굴 점 Face Landmarker · 얼굴 검출 Face Detector short-range · 몸 점 Pose Landmarker lite)을 돌려 관측값과 단계별 처리 시간을 CSV로 남기고, 점 · 선을 그린 영상과 그래프를 만드는 뼈대입니다. **관측과 측정만 합니다** — 불편 상태 판단이나 규칙은 없고, 서버 엔드포인트에도 아직 연결하지 않았습니다(`app.main`에 등록하지 않음).

**어디서 돌리나** — FastAPI · 서버 의존성이 없는 일반 Python 코드라, 카메라가 연결된 키오스크 PC에서 로컬 프로세스로 돌릴 수도 있고(영상이 기기 밖으로 나가지 않음) 팀이 프레임을 보내기로 정하면 ai-server 컨테이너 안에서 돌릴 수도 있습니다. 학교 GPU 서버는 학습에만 쓰고 내보낸 모델은 CPU에서 돌립니다. 프레임 경로(ⓐ 브라우저가 프레임을 서버로 보냄 / ⓑ 키오스크 PC에서 카메라를 직접 읽음)는 팀이 정하며, 이 모듈은 어느 쪽도 전제하지 않습니다.

**코드 주석의 출처 약칭** — `doc 27` · `doc 28` · `research/NN`은 비전 담당(승용)의 설계 노트로 저장소 밖(`01_requirements/research/`)에 있습니다. `[D1]`~`[D3]`은 `app/inference/vision.py` 머리말의 MediaPipe 공식 문서 주소이고, `[C5]` · `[D17]`은 doc 28 출처 목록의 번호입니다. 노트 내용이 필요하면 비전 담당에게 요청해 주세요.

## 층과 파일

비전 쪽 처리를 `입력 → 추론 → 관측값 → 상황 → 전달` 다섯 층으로 나눴고, 파일 하나가 한 층을 맡습니다. 층끼리는 앞 층의 결과만 받습니다. 같은 점 의미와 출력 형식을 유지하는 모델 교체는 추론 층에서 처리하고, 출력 구조가 달라지면 관측값 · 그리기도 함께 맞춥니다. 규칙이 정해지면 상황 층만 채웁니다.

| 층 | 파일 | 하는 일 |
|---|---|---|
| 입력 | `sources.py` | 프레임 입력: 영상 파일 · 이미지 폴더 · 웹캠(`--camera`일 때만 엶). 프레임마다 시각을 붙임 |
| 추론 | `app/inference/vision.py` | MediaPipe 3종 모델 불러오기와 프레임별 추론만(AGENTS.md: 직접 실행하는 모델의 로딩 · 추론 코드는 `app/inference/`에). 결과를 단순한 배열(`FrameInference`)로 넘김. 이 폴더의 `inference.py`는 같은 이름을 다시 내보내는 호환용 |
| 관측값 | `features.py` | 추론 결과로 관측값 계산(아래 CSV 열): 기하 · 연속 구간 · 밝기와 선명도. MediaPipe 없이도 돌아감 |
| 상황 | `situation.py` | **자리만 있음** — 상황 태그 형식과 빈 규칙 표. 어떤 상황을 카메라가 맡을지는 팀 결정과 데이터 분석 뒤에 채움(기준값 없음) |
| 전달 | — | 아직 없음. 다른 서비스로 보내는 형식은 `contract/`에서 정함 |
| 출력 | `render.py` · `run.py` | 점 · 선을 그린 화면 · 모아 보기 · 그래프 · 처리 시간 통계 / 파일 · 카메라 실행, 결과 폴더 저장, `--show` 창, `--replot` |

| 그 밖 | 하는 일 |
|---|---|
| `models/` | 모델 내려받기 스크립트와 출처 · 라이선스(가중치는 Git에 없음) |
| `requirements.txt` | 이 모듈만 쓰는 패키지(mediapipe 0.10.33 고정). 서버 `requirements.txt` · Dockerfile은 그대로 |

## 준비 (`ai-server/`에서, PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r app\modules\vision\requirements.txt
.venv\Scripts\python.exe app\modules\vision\models\download_models.py
```

## 실행

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
- 카메라 실행 결과(`overlay.mp4` · `contact_sheet.png`)에는 찍힌 사람의 얼굴이 담깁니다. `runs/`는 Git(`.gitignore`)과 ai-server Docker 이미지(`ai-server/.dockerignore`)에서 빠지며, 결과를 옮기거나 보관할 때는 `AGENTS.md` §5의 데이터 규칙을 따릅니다.
- 결과 파일: `observations.csv`(프레임마다 한 줄, 아래), `overlay.mp4`(점 · 선 + 값 칸), `contact_sheet.png`(고르게 뽑은 12장), `plot_observations.png` · `plot_quality_timing.png`, `timing.csv`(단계별 p50 · p95 · 최대 · 첫 프레임 ms), `meta.json`(입력 · 설정 · 모델 해시 · 환경 · 끝난 이유), `run.log`(단계별 기록 · 오류 전문).
- 멈추기: `--show` 창에서 `q` · 창 닫기, 또는 콘솔에서 Ctrl+C. 그때까지 처리한 프레임이 저장됩니다. 창도 `--seconds`도 없이 카메라를 돌리면 멈추는 방법을 알려 주는 오류가 납니다.
- 카메라 실행의 `overlay.mp4`는 실제로 처리한 초당 장수로 저장됩니다(`imageio-ffmpeg`가 있을 때 H.264로 바꾸면서; 없으면 MPEG-4 Part 2, 카메라가 알린 초당 장수). `imageio-ffmpeg`는 고정하지 않은 선택 패키지이고, 들어 있는 ffmpeg 실행 파일은 GPL입니다.
- 저장 도중 끊겨 그래프 등이 빠졌으면 `--replot <결과 폴더>`로 `observations.csv`에서 다시 만듭니다.
- 녹화 영상 옆에 `<영상>.times.csv`(`frame,t_s`)가 있으면 그 실측 시각을 씁니다. 번호가 0, 1, 2…로 이어지지 않거나 시각이 되돌아가거나 프레임보다 짧으면 오류로 멈춥니다. 한 실행 안에서 프레임 크기가 바뀌어도 멈춥니다(overlay 영상은 첫 프레임 크기로 고정).
- 처리 시간을 잴 때는 `--show` 없이 돌립니다(창에 그리는 시간은 `meta.json`의 `output_ms`에 따로 적힘).

## 테스트

```powershell
.venv\Scripts\python.exe -m unittest tests.test_vision -v
```

- 관측값 층: 테스트 안에서 만든 가짜 추론 결과(눈꼬리 위치를 정해 둔 얼굴 점, 몸 점, 검출 상자)로 눈 사이 거리 · 시작 대비 비율 · 얼굴 위치 · 연속 구간 · 몸 점 평균 · 밝기를 계산해 정해진 값과 같은지 봅니다. MediaPipe와 모델 파일 없이 돌아갑니다(numpy · OpenCV만 필요).
- 추론까지: 테스트 안에서 만든 빈 화면 프레임으로 MediaPipe 모델을 실제로 돌려 CSV 열 구성, '못 봄' 상태, 처리 시간 기록을 확인합니다(모델 파일 필요).
- 그 밖: 연속 구간 계산, 고개 각도 분해, 실측 초당 장수 공식.
- 사진 · 영상 · `runs/`는 쓰지 않습니다. 필요한 패키지나 모델 파일이 없으면 그 테스트만 건너뛰므로, 서버 패키지만 깔린 환경의 `python -m unittest discover -s tests`에는 영향이 없습니다.

## 아직 하지 않는 것

- 판단 · 규칙: 없습니다(관측과 측정만). 잠깐 끊김을 거르는 시간 창 같은 기준은 파일럿에서 정합니다.
- 서버 연결: 엔드포인트 · `contract/` 형식이 없습니다. 카메라 영상을 AI 서버로 보내는 방식은 `contract/`에서 정합니다(루트 `README.md`).
- 브라우저 실시간 화면(대시보드): 다음 PR에서 따로 다룹니다.
- 키오스크 PC(G10)에서의 처리 시간: 아직 재지 않았습니다.

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
