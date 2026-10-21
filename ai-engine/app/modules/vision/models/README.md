# 모델 파일

이 폴더에는 MediaPipe 모델 4개(내려받음)와 ONNX 모델 2개(우리 체크포인트에서 변환)가 들어갑니다. 모델 가중치는 Git에 올리지 않습니다(`AGENTS.md` §5, 이 모듈의 `.gitignore`).

## MediaPipe 모델 4개

`download_models.py`가 아래 네 파일을 이 폴더에 내려받습니다. 받은 파일은 아래 SHA-256과 같을 때만 남깁니다 — 비전 모듈을 시험한 파일과 같은 것입니다.

| 파일 | 바이트 | SHA-256 | 내려받는 주소 |
|---|---|---|---|
| `face_landmarker.task` | 3,758,596 | `64184e22…0bc9ff` | https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task |
| `pose_landmarker_lite.task` | 5,777,746 | `59929e1d…90d574a` | https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task |
| `blaze_face_short_range.tflite` | 229,746 | `b4578f35…380b0152f` | https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite |
| `blaze_face_full_range.tflite` | 1,083,786 | `3698b18f…aed2b181b` | https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite |

- 쓰는 곳: `app/inference/vision.py`(모듈 폴더의 `vision/inference.py`는 같은 이름을 다시 내보냄) — 얼굴 점(Face Landmarker), 얼굴 검출(기본 short-range, `--face-detector full_range`면 full-range), 몸 점(Pose Landmarker lite). full-range 검출기는 mediapipe 0.10.33부터 돕니다. blendshape 52개는 Face Landmarker 묶음 안의 모델이 내고, 재생 · 실시간 실행기만 켭니다(결정 16: 기본 꺼짐).
- 전체 해시는 `download_models.py`에 있고, 실행할 때마다 `runs/<이름>/meta.json`의 `models`에도 적힙니다.

## ONNX 모델 2개 (`tools/export_onnx.py`가 만듦)

| 파일 | 바이트 | SHA-256 | 원본 체크포인트 |
|---|---|---|---|
| `h1_head_yolox_nano_416.onnx` | 3,678,566 | `fab2f4e3…edf674cc` | H1 머리 탐지기 `best_ckpt.pth`(epoch 299, 7,581,047 B, SHA-256 `313be515…d52112bc`) |
| `p1_head_direction_resnet18_56.onnx` | 44,710,617 | `e6109ab0…abdb1302` | P1 머리 방향 분류기 `model_final.pt`(epoch 90, 44,793,035 B, SHA-256 `c9af046c…4c9731d50`) |

전체 SHA-256(2026-10-22 변환, 같은 명령을 두 번 돌려 H1 파일이 같은 해시로 나온 것을 확인함):

```
fab2f4e3f39a084dfa446e3367427594ff99f07ad015a143487cf205edf674cc  h1_head_yolox_nano_416.onnx
e6109ab09fe41e73006792ec7df2bc10715be6fbce34dd93e5fb3f71abdb1302  p1_head_direction_resnet18_56.onnx
313be515126c00761736df3e75f3033f7b06efe1e63ab8a5d44d721fd52112bc  best_ckpt.pth (H1)
c9af046c80b74e384cdfc4e088a25f7e8a0226244e4474736be75664c9731d50  model_final.pt (P1)
```

- 체크포인트는 저장소 밖(학교 GPU 서버와 비전 담당 작업 공간)에 있습니다. 필요하면 비전 담당에게 요청해 주세요.
- 형식: H1은 입력 `images` = 배치 × 3 × 416 × 416(BGR 0~255, letterbox, 정규화 없음), 출력 `output` = 배치 × 3,549 × 6(상자 · objectness · head, 디코딩 전), opset 11. P1은 입력 `crops` = 배치 × 3 × 56 × 56(RGB, 정규화), 출력 `logits` = 배치 × 5(중간 · 위 · 좌 · 우 · 뒤), opset 11. 둘 다 배치 축이 동적이고, 클래스 · 크롭 값은 ONNX 메타데이터에 들어 있습니다.
- 변환 확인(같은 입력에서 ONNX Runtime과 PyTorch 비교, `onnx_export.json`에 기록): H1 원출력 최대 차이 1.4 × 10⁻⁵(무작위 0~255 입력) · 2.0 × 10⁻⁴(그린 화면), 0.01 이상 상자를 NMS한 결과 18개 · 0개가 둘에서 같음. P1 logits 최대 차이 4.3 × 10⁻⁶, 가장 큰 방향이 8장 모두 같음. P1 입력 변환(numpy)과 torchvision 변환의 최대 차이 7.2 × 10⁻⁷.
- 쓰는 곳: `perception/head.py`(H1), `perception/head_direction.py`(P1).

### 다시 만들기 (서버 환경과 따로, CPU)

```powershell
py -3.12 -m venv <작업 폴더>\venv_export
<작업 폴더>\venv_export\Scripts\python.exe -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cpu
<작업 폴더>\venv_export\Scripts\python.exe -m pip install loguru thop tabulate psutil tqdm opencv-python-headless onnx onnxsim onnxruntime==1.30.0
git clone https://github.com/Megvii-BaseDetection/YOLOX <작업 폴더>\yolox_src
git -C <작업 폴더>\yolox_src checkout 6ddff48
<작업 폴더>\venv_export\Scripts\python.exe -m pip install --no-deps -e <작업 폴더>\yolox_src
# ai-engine\ 에서
<작업 폴더>\venv_export\Scripts\python.exe -m app.modules.vision.tools.export_onnx --h1-ckpt <best_ckpt.pth> --p1-ckpt <model_final.pt>
```

- 2026-10-22 변환 환경: Python 3.12.10, torch 2.7.1+cpu, torchvision 0.22.1+cpu, YOLOX 0.3.0(6ddff48), onnx 1.23.2, onnxsim 0.8.1, onnxruntime 1.30.0, Windows 11.
- YOLOX의 `tools/export_onnx.py`와 다른 점: torch 2.7.1에 없는 `torch.onnx._export` 대신 공개 함수 `torch.onnx.export`를 같은 인자로 부르고, 고정판 onnx-simplifier 0.4.10 대신 onnxsim 0.8.1을 씁니다(Run 1 변환 도구와 같은 처리). 체크포인트는 `weights_only=True`로 읽고, YOLOX 체크포인트에 든 numpy 값만 따로 허용합니다.

## 라이선스

- **MediaPipe 모델: Apache License 2.0** — MediaPipe 관리자 답변: "Our source and the models (unless otherwise noted) are licensed under Apache2." (https://github.com/google-ai-edge/mediapipe/issues/6355). 모델 카드에도 같은 라이선스가 적혀 있습니다(비전 설계 노트 28 ⑧에 확인 기록, 저장소 밖). 원문: https://www.apache.org/licenses/LICENSE-2.0
- **H1(우리 가중치)**: 코드는 YOLOX(Apache-2.0, "Copyright (c) 2021-2022 Megvii Inc. All rights reserved."), 학습 데이터는 Open Images V7 'Human head'(주석 CC BY 4.0, 사진 CC BY 2.0), 시작 가중치는 YOLOX-Nano COCO 가중치입니다. COCO 약관이 가중치에 미치는지는 문서에 없습니다. 넘겨줄 때는 Open Images 주석 출처 표기와 YOLOX Apache-2.0 고지를 함께 둡니다(라이선스 대장 §3 H1 행, §5-5; 저장소 밖).
- **P1(우리 가중치)**: torchvision ResNet-18 구조(BSD-3-Clause)를 무작위 초기값에서 학습했고, 학습 데이터는 과학기술정보통신부의 재원으로 한국지능정보사회진흥원의 지원을 받아 구축된 「안내 로봇 인터랙션 멀티모달」(AI 허브, aihub.or.kr)입니다. AI Hub 정책상 학습한 모델은 2차 저작물로 공유 · 상업 이용이 가능하고, 쓸 때 위 출처 문구를 붙입니다(라이선스 대장 §3 P1 행, §5-1).
- 이 저장소는 모델 파일을 넣지 않습니다. 모델 파일을 다른 사람에게 함께 넘길 때는 Apache-2.0 §4에 따라 라이선스 사본을 함께 주고 원래의 저작권 · 고지 문구를 유지합니다.
