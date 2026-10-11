# 비전 관측 뼈대 (`app/modules/vision/`)

카메라나 영상 파일의 프레임마다 MediaPipe 3종(얼굴 점 Face Landmarker · 얼굴 검출 Face Detector short-range · 몸 점 Pose Landmarker lite)을 돌려 관측값과 단계별 처리 시간을 CSV로 남기고, 점 · 선을 그린 영상과 그래프를 만드는 뼈대입니다. **관측과 측정만 합니다** — 불편 상태 판단이나 규칙은 없고, 서버 엔드포인트에도 아직 연결하지 않았습니다(`app.main`에 등록하지 않음).

**어디서 돌리나** — FastAPI · 서버 의존성이 없는 일반 Python 코드라, 카메라가 연결된 키오스크 PC에서 로컬 프로세스로 돌릴 수도 있고(영상이 기기 밖으로 나가지 않음) 팀이 프레임을 보내기로 정하면 ai-server 컨테이너 안에서 돌릴 수도 있습니다. 학교 GPU 서버는 학습에만 쓰고 내보낸 모델은 CPU에서 돌립니다. 프레임 경로(ⓐ 브라우저가 프레임을 서버로 보냄 / ⓑ 키오스크 PC에서 카메라를 직접 읽음)는 팀이 정하며, 이 모듈은 어느 쪽도 전제하지 않습니다.

**코드 주석의 출처 약칭** — `doc 27` · `doc 28` · `research/NN`은 비전 담당(승용)의 설계 노트로 저장소 밖(`01_requirements/research/`)에 있습니다. `[D1]`~`[D3]`은 `app/inference/vision.py` 머리말의 MediaPipe 공식 문서 주소이고, `[C5]` · `[D17]`은 doc 28 출처 목록의 번호입니다. 노트 내용이 필요하면 비전 담당에게 요청해 주세요.

## 층과 파일

비전 쪽 처리를 `입력 → 추론 → 관측값 → 사건 → 상황 → 전달` 여섯 층으로 나눴고, 파일 하나가 한 층을 맡습니다. 층끼리는 앞 층의 결과만 받습니다. 같은 점 의미와 출력 형식을 유지하는 모델 교체는 추론 층에서 처리하고, 출력 구조가 달라지면 관측값 · 그리기도 함께 맞춥니다. 상황 규칙의 기준값이 정해지면 `PilotParams`에 값만 넣습니다.

| 층 | 파일 | 하는 일 |
|---|---|---|
| 입력 | `sources.py` | 프레임 입력: 영상 파일 · 이미지 폴더 · 웹캠(`--camera`일 때만 엶). 프레임마다 시각을 붙임 |
| 추론 | `app/inference/vision.py` | MediaPipe 3종 모델 불러오기와 프레임별 추론만(AGENTS.md: 직접 실행하는 모델의 로딩 · 추론 코드는 `app/inference/`에). 결과를 단순한 배열(`FrameInference`)로 넘김. 이 폴더의 `inference.py`는 같은 이름을 다시 내보내는 호환용 |
| 관측값 | `features.py` | 추론 결과로 관측값 계산(아래 CSV 열): 기하 · 연속 구간 · 밝기와 선명도. MediaPipe 없이도 돌아감 |
| 사건 | `events.py` | 한 창의 관측값을 사건으로 묶음(9종, 아래 '상황 층'). 고개를 한 번 돌린 것은 사건 하나. 창 길이 · 횟수 · 각도 · 품질 하한은 모두 `PilotParams`(기본값 없음, `[파일럿]`) |
| 상황 | `situation.py` | 상황 태그 규칙 3개 구현, 값은 `[파일럿]`. 창마다 한 줄(근거 사건 · 품질 · 확신 정보 · 대안)을 내고 검사 규칙으로 확인함. `run.py`는 아직 부르지 않음 |
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

## 상황 층 (`events.py` · `situation.py`)

관측값 줄을 창 단위로 읽어 사건을 찾고, 사건을 묶어 상황 태그 3개 가운데 하나를 냅니다. 판단할 수 없으면 `unknown`, 모든 태그가 측정된 단서로 빠지면 `none`을 냅니다. 태그 이름 · 표시 문구 · 묶는 관찰 · 빼는 조건은 비전 담당의 결정 목록(2026-10-10) §3을 따르고, 출력 형식과 검사 규칙은 의미 층 설계 노트(2026-10-11) §4를 따릅니다(둘 다 저장소 밖).

기준값은 정하지 않았습니다. 창 길이 · 횟수 · 각도 · 품질 하한 15개는 모두 `PilotParams`의 필드이고 기본값이 없어서, 부르는 쪽이 값을 모두 넣어야 합니다. 값은 팀원 자가 녹화의 분포로 정합니다(`[파일럿]`). 필드마다 무엇을 정하는지는 `events.py`의 `PilotParams` 주석에 적었습니다. `situation.py`에는 숫자가 없고, 테스트가 이를 확인합니다.

```python
from app.modules.vision.events import PilotParams
from app.modules.vision.situation import assess

params = PilotParams(window_s=..., gap_s=..., ...)                 # 15개 모두 [파일럿], 기본값 없음
out, events = assess(rows, t_end, params, landmarker_num_faces=1)  # 창 = [t_end - window_s, t_end]
```

`rows`는 관측값 줄(`observations.csv`의 한 줄 = dict 하나)에 아래 '선택 열'을 더한 목록입니다. `landmarker_num_faces`는 그 줄을 만든 Face Landmarker의 `num_faces` 설정입니다(이 모듈은 1). `run.py`는 아직 이 층을 부르지 않습니다.

### 규칙 3개 (결정 목록 §3)

1. `looking_back_with_people_behind`(뒤에 사람이 있어 서두르는 듯함): `people_behind` 1개 이상과 `look_back` `look_back_min_count`개 이상. `touch_miss`는 보조 근거라 사건 수에만 더합니다. 지나가는 사람만 있거나 뒤돌아봄이 없으면 빠집니다.
2. `consulting_companion`(일행과 상의하는 듯함): `companion_present`, 그쪽으로 돈 `yaw_sweep_offscreen`, `mouth_moving`, `dwell_no_touch`(창 안 터치 없음), 몸 제자리(어깨 가운데가 움직인 범위가 `body_still_max` 이하). 입 움직임 열이 없거나 smoothing이 꺼졌거나 얼굴 보임 비율이 `face_visible_min` 미만이면 그 단서만 빼고 나머지로 판단하고, `quality_ok`를 false로 둡니다.
3. `looking_around`(무언가를 찾는 듯함): 화면 밖 고개 돌림(`yaw_sweep_offscreen`과 `look_back`) `sweep_min_count`개 이상, `dwell_no_touch`(창 안 터치 없음), 몸 제자리, 뒤에 선 사람 없음. 메뉴를 읽는 작은 yaw는 `offscreen_yaw_deg` 안에 머물러 사건이 되지 않습니다.

### 사건 9종

| 사건 | 찾는 방법 | 쓰는 규칙 |
|---|---|---|
| `look_back` 뒤돌아봄 | 화면을 보던 얼굴이 `offscreen_yaw_deg`를 넘어 돌아가고, 얼굴 점이 사라진 동안 어깨 점이 남고(`shoulder_vis_min`), 다시 화면 쪽으로 돌아옴. yaw 변화 · 얼굴 사라짐 · 어깨 남음을 따로 세지 않고 사건 하나로 셈 | 1 · 3 |
| `yaw_sweep_offscreen` 화면 밖 고개 돌림 | 같은 돌림인데 얼굴이 끝까지 보임. 돌아간 쪽(왼쪽 · 오른쪽)을 함께 적음 | 2(일행 쪽일 때) · 3 |
| `people_behind` 뒤에 선 사람 | `people_behind_count`가 1 이상인 구간이 `stay_min_s` 이상 이어짐. 더 짧으면 지나가는 사람으로 보고 세지 않음 | 1 · 3(빼는 조건) |
| `companion_present` 동행자 | `companion_box`가 `stay_min_s` 이상 이어짐. 사용자 얼굴의 어느 쪽인지 함께 적음 | 2 |
| `mouth_moving` 입 움직임 | 얼굴이 보이는 프레임에서 `mouth_motion`이 `mouth_motion_min` 이상. Face Landmarker의 `num_faces`가 1이 아니면 smoothing이 꺼지므로 찾지 않음 | 2 |
| `dwell_no_touch` 안 누르고 머묾 | 사람이 보이고 터치 없이 `dwell_min_s` 이상 지남. 터치가 들어오면 끊김 | 2 · 3 |
| `touch_miss` 빗나간 터치 | `miss_tap_count`가 0보다 큼 | 1(보조 근거) |
| `back_navigation_loop` 되돌아가기 반복 | 창 안 `back_count` 합이 `back_loop_min_count` 이상 | 없음(막힘 후보용) |
| `first_input_delayed` 첫 입력 지연 | `first_input_delay_ms`가 `first_input_delay_min_ms` 이상 | 없음(망설임 후보용) |

`gap_s` 안의 짧은 끊김은 이어 붙여 사건 하나로 봅니다(잠깐 끊김을 거르는 시간 창).

### 출력 형식

창 하나에 한 줄을 냅니다. 아래는 테스트의 합성 창(`test_person_behind_and_repeated_look_backs`, 창 길이만 3초로 바꿈)에서 나온 실제 출력이고, 소수는 둘째 자리까지 줄였습니다. 숫자는 합성 프레임의 값이고 기준값이 아닙니다.

```json
{
  "name": "looking_back_with_people_behind",
  "display_text": "뒤에 사람이 있어 서두르는 듯함",
  "window_s": [0.0, 3.0],
  "evidence": [
    {"event_id": "people_behind@0", "obs": "people_behind_count", "value": 1, "t": 0.0},
    {"event_id": "people_behind@0", "obs": "stay_s", "value": 3.0, "t": 0.0},
    {"event_id": "look_back@5", "obs": "yaw_deg", "value": 60.0, "t": 0.5},
    {"event_id": "look_back@5", "obs": "side", "value": "right", "t": 0.5},
    {"event_id": "look_back@5", "obs": "face_lost_s", "value": 0.6, "t": 0.5},
    {"event_id": "look_back@5", "obs": "pose_vis_shoulders", "value": 0.9, "t": 0.5},
    {"event_id": "look_back@18", "obs": "yaw_deg", "value": 60.0, "t": 1.8},
    {"event_id": "look_back@18", "obs": "side", "value": "right", "t": 1.8},
    {"event_id": "look_back@18", "obs": "face_lost_s", "value": 0.6, "t": 1.8},
    {"event_id": "look_back@18", "obs": "pose_vis_shoulders", "value": 0.9, "t": 1.8}
  ],
  "quality": {"face_visible_ratio": 0.68, "track_conf": 1.0},
  "confidence": {"events": 3, "quality_ok": true},
  "alternatives": [],
  "source": "rules_v1"
}
```

- `name`: 태그 이름, `unknown`(판단할 수 없음), `none`(모든 태그가 측정된 단서로 빠짐) 가운데 하나입니다.
- `display_text`: 태그마다 정해 둔 문구(`DISPLAY_TEXT`)만 씁니다. `unknown` · `none`은 빈 문자열입니다.
- `evidence`: 근거 사건의 관찰을 한 줄씩 펼친 목록입니다. `event_id`는 `사건 종류@첫 프레임 번호`이고, `t`는 사건이 시작한 시각(초)입니다. 위의 `look_back@5` 관찰 넷은 고개를 한 번 돌린 사건 하나에서 나왔습니다.
- `quality`: `face_visible_ratio`는 창 안에서 얼굴이 보인 프레임 비율이고, `track_conf`는 몸 점이 잡힌 프레임 비율입니다(MediaPipe가 자체 기준을 넘겨 몸 점을 낸 프레임).
- `confidence`: 확률이 아닙니다. 라벨로 보정하기 전이라 근거 사건 수(`events`)와, 결측이라 뺀 단서가 없는지(`quality_ok`)만 적습니다.
- `alternatives`: 측정된 단서로 빠지지 않은 다른 태그입니다. 근거 사건이 많은 순서이고, 항목마다 `name` · `display_text` · `evidence` · `confidence`가 있습니다.

검사 규칙 두 개는 `check_output`이 코드로 확인합니다. `assess`가 낸 출력이 규칙을 어기면 오류가 납니다.

1. 근거 연결: `evidence`의 모든 항목은 이 창의 사건 ID를 가리킵니다. 그 사건은 창 안에 있고, 항목의 관찰 이름과 값은 그 사건의 관찰과 같습니다. 표시 문구도 이름마다 정해 둔 문구와 같아야 합니다.
2. 모름: 근거 사건이 `min_events`개보다 적거나, 꼭 필요한 단서를 잴 수 없으면 `unknown`입니다. 입력 열이 없거나, 얼굴이 필요한 단서인데 얼굴 보임 비율이 `face_visible_min` 미만인 경우입니다. 몸 추적 비율이 `track_conf_min` 미만이면 센서 실패로 보고 규칙을 읽지 않고 `unknown`을 냅니다. 얼굴이 사라지는 것은 뒤돌아봄의 단서이므로, 얼굴 보임 비율이 낮아도 뒤돌아봄 태그는 막지 않습니다. 두 태그가 함께 맞으면 근거 사건이 많은 쪽이 `name`이 되고 다른 쪽은 `alternatives`에 들어갑니다. 사건 수가 같으면 `unknown`입니다.

상태 수명: 창은 `t_end`와 함께 밀립니다. 창 안 사건이 `min_events`개 이상이면 상태가 시작되고, 사건이 창 밖으로 나가거나(`window_s` = 만료 창) 반대 근거(터치, 뒤에 선 사람, 몸 이동)가 창에 들어오면 풀립니다.

### 선택 열 (이 저장소의 코드가 아직 만들지 않음)

규칙이 쓰는 열 가운데 아래 열은 아직 아무 코드도 만들지 않습니다. 창의 모든 줄에 그 열이 있을 때만 단서로 쓰고, 열이 없으면 0으로 채우지 않고 결측으로 봅니다.

| 열 | 뜻 | 만들 곳 |
|---|---|---|
| `people_behind_count` | 주 사용자 뒤에 선 사람 수(주 사용자보다 작은 상자, 뒤쪽) | 머리 탐지기(학습 중, 연결 전) |
| `companion_box` | 옆에 선 비슷한 크기의 두 번째 상자 `(x0, y0, x1, y1)`, 화면 비율. 없으면 `None` | 같은 탐지기 |
| `mouth_motion` | blendshape 입 다이얼(jawOpen 등)의 변화, 사람별 기준선을 뺀 값. 얼굴을 못 본 프레임은 빈칸 | blendshape를 켜는 설정(이 저장소에는 아직 없음) |
| `shoulder_cx` · `shoulder_cy` | 어깨 두 점(11 · 12)의 가운데, 화면 비율. 몸을 못 본 프레임은 빈칸 | 관측값 층(몸 점 좌표는 이미 추론 결과에 있음) |
| `tap_count` · `miss_tap_count` · `back_count` | 직전 줄 이후의 터치 · 버튼 밖 터치 · 뒤로가기 횟수. 이름과 뜻은 `contract/frontend-backend.openapi.yaml`의 `TouchFeatures`를 따르고, 세는 구간만 프레임 간격 | 터치 로그(`docs/Touch-Log-Review.md`) |
| `first_input_delay_ms` | 화면의 첫 입력 프레임에 적는, 그 화면에 들어온 뒤 걸린 시간(ms). 명세에 없는 이름 | 터치 로그 |

## 테스트

```powershell
.venv\Scripts\python.exe -m unittest tests.test_vision tests.test_situation -v
```

- 관측값 층: 테스트 안에서 만든 가짜 추론 결과(눈꼬리 위치를 정해 둔 얼굴 점, 몸 점, 검출 상자)로 눈 사이 거리 · 시작 대비 비율 · 얼굴 위치 · 연속 구간 · 몸 점 평균 · 밝기를 계산해 정해진 값과 같은지 봅니다. MediaPipe와 모델 파일 없이 돌아갑니다(numpy · OpenCV만 필요).
- 상황 층(`tests/test_situation.py`): 테스트 안에서 만든 합성 관측 줄(초당 10장)로 태그마다 맞는 경우 · 빼는 조건 · `unknown` · 대안 · 동점을 보고, 고개 한 번이 사건 하나인지와 검사 규칙(사건 ID · 고정 문구)을 확인합니다. `PilotParams`에 기본값이 없는지, `situation.py`에 숫자가 없는지도 봅니다. 테스트의 값은 합성 프레임용이고 기준값 제안이 아닙니다. 표준 라이브러리만 쓰므로 서버 패키지만 깔린 환경에서도 돌아갑니다(`features.py`와 표시 값을 맞춰 보는 1개만 OpenCV가 없으면 건너뜀).
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
