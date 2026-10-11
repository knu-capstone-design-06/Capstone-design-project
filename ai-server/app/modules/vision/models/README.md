# MediaPipe 모델 파일

`download_models.py`가 아래 네 파일을 이 폴더에 내려받습니다. 모델 가중치는 Git에 올리지 않습니다(`AGENTS.md` §5). 받은 파일은 아래 SHA-256과 같을 때만 남깁니다 — 비전 모듈을 시험한 파일과 같은 것입니다.

| 파일 | 바이트 | SHA-256 | 내려받는 주소 |
|---|---|---|---|
| `face_landmarker.task` | 3,758,596 | `64184e22…0bc9ff` | https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task |
| `pose_landmarker_lite.task` | 5,777,746 | `59929e1d…90d574a` | https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task |
| `blaze_face_short_range.tflite` | 229,746 | `b4578f35…380b0152f` | https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite |
| `blaze_face_full_range.tflite` | 1,083,786 | `3698b18f…aed2b181b` | https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite |

- 쓰는 곳: `inference.py` — 얼굴 점(Face Landmarker), 얼굴 검출(기본 short-range, `--face-detector full_range`면 full-range), 몸 점(Pose Landmarker lite). full-range 검출기는 mediapipe 0.10.33부터 돕니다.
- 전체 해시는 `download_models.py`에 있고, 실행할 때마다 `runs/<이름>/meta.json`의 `models`에도 적힙니다.

## 라이선스

- **Apache License 2.0** — MediaPipe 관리자 답변: "Our source and the models (unless otherwise noted) are licensed under Apache2." (https://github.com/google-ai-edge/mediapipe/issues/6355). 모델 카드에도 같은 라이선스가 적혀 있습니다(비전 설계 노트 28 ⑧에 확인 기록, 저장소 밖).
- 라이선스 원문: https://www.apache.org/licenses/LICENSE-2.0
- 이 저장소는 모델 파일을 넣지 않고 내려받는 주소만 둡니다. 모델 파일을 다른 사람에게 함께 넘길 때는 Apache-2.0 §4에 따라 라이선스 사본을 함께 주고 원래의 저작권 · 고지 문구를 유지합니다.
