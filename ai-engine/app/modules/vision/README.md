# 비전 관측 뼈대 (`app/modules/vision/`)

카메라나 영상 파일의 프레임마다 MediaPipe 3종(얼굴 점 Face Landmarker · 얼굴 검출 Face Detector short-range · 몸 점 Pose Landmarker lite)을 돌려 관측값과 단계별 처리 시간을 CSV로 남기고, 점 · 선을 그린 영상과 그래프를 만드는 뼈대입니다. **2026-10-22부터 녹화 재생 · 웹캠 실시간 실행기(`replay.py` · `live.py`)가 머리 탐지기 · 카메라 시점 분류기 · 선택 열 · 터치 로그 · 상황 태그 규칙 3개 · 판단 층 규칙표 v0(장면 3-1 · 3-2 · 4-1 · 4-2, Jev는 질문만 기록)를 창마다 끝까지 잇습니다**(아래 '실행 파이프라인'). 엔드포인트(`app.main`)에는 등록하지 않았습니다. 실시간 실행기에는 주문 화면의 터치 창을 받는 입구(`--serve`)와 창마다 상황 태그를 backend로 보내는 쪽(`--backend-url`)이 있습니다. 그 상대편인 주문 화면의 터치 창 보내기(`VITE_AI_ENGINE_URL`)와 backend의 창 받는 곳 · 시연 스위치(`DECISION_SEND_SUPPORT`)도 저장소에 있습니다(아래 '주문 화면 · backend와 잇는 두 연결'). 상황 규칙의 기준값 13개는 기본값 없이 값 묶음 파일로 넣고, 실행 파이프라인이 새로 쓰는 값은 출처와 함께 `params.py`에 있습니다(출처가 없는 값은 `[파일럿]`).

**어디서 돌리나** — 설계안(2026-10-15): 카메라가 연결된 키오스크 PC에서 로컬 프로세스로 돌립니다(영상이 기기 밖으로 나가지 않음). FastAPI · 서버 의존성이 없는 일반 Python 코드라 ai-engine 컨테이너 안에서도 돌 수 있습니다. GPU 서버는 학습 · 평가에만 쓰고 내보낸 모델(ONNX)은 키오스크 PC의 CPU에서 돌립니다. 데이터 경로는 팀 논문 그림 1을 따릅니다. 주문 화면이 터치 통계를 같은 PC의 이 프로세스에 보내고(한 방향), 이 프로세스가 창마다 상황 태그를 backend로 직접 보냅니다. 주문 화면으로는 비전 값이 가지 않습니다. 세 쪽 끝이 모두 있습니다. 주문 화면의 터치 창 보내기, 이 프로세스의 터치 입구와 상황 태그 보내기, backend의 창 받는 곳입니다(아래 '주문 화면 · backend와 잇는 두 연결').

**코드 주석의 출처 약칭** — `doc 27` · `doc 28` · `research/NN`은 비전 담당(wdragon92)의 설계 노트(doc 27 = 케이스별 전후 표 `27_before_after_table.md`, doc 28 = MediaPipe 한계·도달 범위 조사 `28_mediapipe_limits_and_reach.md`)로 저장소 밖(`01_requirements/research/`)에 있습니다. `[D1]`~`[D3]`은 `app/inference/vision.py` 머리말의 MediaPipe 공식 문서 주소이고, `[C5]` · `[D17]`은 doc 28 출처 목록의 번호입니다. `JP`는 판단 층과 Jev 파이프라인 설계 v2.2(`3_design/jev_pipeline_2026-10-13.md`), `tree`는 시나리오 트리 v1.7(`3_design/scenario_tree_v1_2026-10-13.md`)로, 역시 저장소 밖 설계 노트입니다. 노트 내용이 필요하면 비전 담당에게 요청해 주세요. 실험 기록(각 실행의 데이터 · 설정 · 결과 · 서버 위치)과 라이선스 대장은 비전 담당의 작업 노트(저장소 밖)에 있습니다. 숫자가 필요하면 비전 담당에게 요청해 주세요.

## 층과 파일

현재 재생·실시간 실행기는 `입력 → 추론 → 관측값 → 사건 → 상황 → 판단 → 전달` 일곱 층으로 구현돼 있고(로컬 규칙표는 2026-10-22에 더함), 층마다 파일이 따로 있습니다. 아래 표는 이 기존 구현을 설명합니다. 판단 층은 backend 판단 단계(`backend/app/modules/decision/`)가 맡아 `/features` 창마다 규칙표 v0를 실행하고, 비전 쪽은 창 출력 제공과 전체 파이프라인의 시험 · 안정화를 맡습니다. 층끼리는 앞 층의 결과만 받습니다. 같은 점 의미와 출력 형식을 유지하는 모델 교체는 추론 층에서 처리하고, 출력 구조가 달라지면 관측값 · 그리기도 함께 맞춥니다. 상황 규칙의 기준값이 정해지면 `PilotParams`에 값만 넣습니다.

| 층 | 파일 | 하는 일 |
|---|---|---|
| 입력 | `sources.py` | 프레임 입력: 영상 파일 · 이미지 폴더 · 웹캠(`--camera`일 때만 엶). 프레임마다 시각을 붙임 |
| 입력 | `touch.py` | 터치 로그(주문 화면 개발 모드의 JSON 내보내기)를 영상 시간축에 놓고 누름 · 버튼 밖 누름 · 빗나감 뒤 바로 고침 · 되돌아감을 세며, 관측 구간 · 세션 · 1,000개 잘림을 처리함. 세는 방법은 `[설계 제안]`(아래 '터치 로그') |
| 추론 | `app/inference/vision.py` | MediaPipe 3종 모델 불러오기와 프레임별 추론만(AGENTS.md: 직접 실행하는 모델의 로딩 · 추론 코드는 `app/inference/`에). 결과를 단순한 배열(`FrameInference`)로 넘김. 이 폴더의 `inference.py`는 같은 이름을 다시 내보내는 호환용. blendshape는 `MediaPipeModels(blendshapes=True)`일 때만 냄(기본은 꺼짐; 실행기는 `--blendshapes`로 켬) |
| 추론 | `app/inference/head.py` · `app/inference/head_direction.py` | H1 머리 탐지기(YOLOX-Nano)와 P1 카메라 시점 분류기(ResNet-18, AI Hub 70 '촬영방향' 라벨로 학습)를 ONNX Runtime으로 CPU에서 돌림(스레드 기본 1). ONNX 파일은 `tools/export_onnx.py`가 만듦. 자리는 같은 AGENTS.md 문장(모델 로딩 · 추론 코드는 `app/inference/`)을 따름 |
| 관측값 | `features.py` | 추론 결과로 관측값 계산(아래 CSV 열): 기하 · 연속 구간 · 밝기와 선명도. MediaPipe 없이도 돌아감 |
| 관측값 | `columns.py` | 규칙이 쓰는 선택 열을 만듦(아래 '선택 열'): 머리 상자 트랙 · 주 사용자 트랙 · 뒤에 선 사람 수 · 동행자 상자 · 어깨 위치 · 입 움직임 · 주 사용자 머리의 P1 카메라 시점 확률(관측만) · 모든 머리 상자와 단서(관측만) |
| 사건 | `events.py` | 관측값 줄을 사건으로 묶음(8종, 아래 '상황 층'). 고개를 한 번 돌린 것은 사건 하나. 창 길이 · 횟수 · 각도 · 품질 하한은 모두 `PilotParams`(기본값 없음, `[파일럿]`) |
| 상황 | `situation.py` | 상황 태그 규칙 3개와 장면 태그 6개(아래 '장면 태그 6개') 구현, 값은 `[파일럿]`. 창마다 한 줄(근거 사건 · 품질 · 확신 정보 · 대안)을 내고 검사 규칙으로 확인함. 재생 · 실시간 실행기가 창마다 부름(`run.py` · 엔드포인트는 부르지 않음) |
| 판단 | `judgment/rule_table_v0.py` · `judgment/jev_stub.py` | 장면 3-1 · 3-2 · 4-1 · 4-2의 규칙표 v0: 창마다 지원 하나 · 출력 형태 · 전이를 냄. Jev 질문은 만들어 기록만 함(그림자 모드, 아래 '기존 재생용 규칙표 v0') |
| 전달 | `contract_view.py` | 창 결과의 `support`는 `SupportDecision` 형식을 유지하고, 관측 가능 여부·모델 버전·돌아간 탐지기·상황·결정 정보는 `extension`에 담음. 판단 층이 읽는 키의 상황(`decision_situation`)과 관측 블록(`observations`)도 함께 냄. 불편 상태 점수가 없어 `AnalyzeResponse`는 만들지 않음. 재생 파일 · 콘솔에 기록하고, 실시간 실행기는 이 가운데 상황 · 관측 블록을 backend로 보냄(`tag_sender.py`) |
| 전달 | `touch_entry.py` | 실시간 실행기의 터치 입구(`live.py --serve`): 주문 화면이 보낸 터치 창을 카메라 시간축에 놓고 실행기의 창 판단에 넣음. 답은 받음 · 거절 이유뿐이고 비전 값은 돌려주지 않음. 127.0.0.1에서만 받음(아래 '주문 화면 · backend와 잇는 두 연결') |
| 전달 | `tag_sender.py` | 실시간 실행기가 판단한 창마다 세션 · 창 시각 · 판단 층 키의 상황 · 관측 블록 · 버전 표시를 backend의 `POST /api/v1/sessions/{session_id}/vision-windows`로 보냄(`live.py --backend-url`). 카메라 처리는 보내기를 기다리지 않음 |
| 출력 | `render.py` · `run.py` | 점 · 선을 그린 화면 · 모아 보기 · 그래프 · 처리 시간 통계 / 파일 · 카메라 실행, 결과 폴더 저장, `--show` 창, `--replot` |
| 출력 | `chain.py` · `replay.py` · `live.py` | 프레임에서 창까지 잇는 공용 파이프라인, 녹화 재생(창마다 JSONL 한 줄), 웹캠 실시간(창마다 콘솔 한 줄, `--no-window`) |

| 그 밖 | 하는 일 |
|---|---|
| `models/` | MediaPipe 모델 내려받기 스크립트, ONNX 모델 2개의 해시 · 만드는 법, 출처 · 라이선스(가중치는 Git에 없음) |
| `params.py` | 실행 파이프라인의 값과 출처(`PilotParams`, 기본값 있음), 값 묶음 파일 읽기(상황 규칙 13개는 기본값 없음) |
| `tools/export_onnx.py` | H1 · P1 체크포인트를 ONNX로 바꿈. torch · YOLOX가 든 별도 환경에서 돌림(`models/README.md`) |
| `tools/integration_smoke.py` | 카메라 없이 두 연결을 시험함: 가짜 카메라(검은 프레임)로 실시간 실행기를 돌리고, 주문 화면 대신 2초마다 터치 창을 보내며, 시험 backend가 받은 창을 한 줄씩 찍음. 그림은 저장하지 않음(아래 '주문 화면 · backend와 잇는 두 연결') |
| `tools/companion_eval.py` | 사람 라벨이 있는 녹화로 동행자 · 뒤 사람 단서와 주 사용자 트랙을 평가함: 재생, 단서 분포, 경계 후보별 라벨 일치율, 확인 시트. 평가 전용이라 값을 정하지 않음(아래 '머리 트랙과 역할') |
| `requirements.txt` | 이 모듈만 쓰는 패키지(mediapipe 0.10.33 · onnxruntime 1.30.0 고정). 서버 `requirements.txt` · Dockerfile은 그대로 |

## 현재 상태 (2026-11-22)

| 항목 | 상태 |
|---|---|
| 뼈대 | 병합됨(PR #32 관측·측정, PR #35 상황 층) |
| 장면 구분 | 핵심 장면 8개 모두 구분 신호가 있습니다: 1-1 `aid_use`(보조기구 사용 중), 1-2 `seated_height`(앉은 높이), 2-1 `face_approach`(얼굴 접근), 2-2 `user_changed`(사용자 교체 가능성)는 장면 태그로, 3-1 · 3-2는 상황 태그로(3-2는 휴대폰 탐지기를 켜면 장면 태그 `phone_use`의 휴대폰 길도), 4-1 · 4-2는 터치 규칙(4-2는 두리번 태그를 함께 씀)으로 냅니다. 자리 비움은 `none_seen`. 장면 태그는 카메라별 경계값과 모델 파일을 주어야 판정합니다(아래 '장면 태그 6개') |
| 상황 규칙 | 상황 태그 3개의 규칙 · 사건 8종 · 출력 형식을 구현했습니다(PR #35, 2026-10-12 병합; 아래 '상황 층'). 태그 이름과 표시 문구는 아래 '상황 태그 3개 요약' 표와 같습니다. 기준값 13개는 모두 `[파일럿]`이고 기본값 없이 값 묶음 파일로 넣습니다. 값 묶음이 없으면 `unknown`(이유 `no_value_bundle`)을 냅니다 |
| 실행 파이프라인 | 재생 · 실시간 실행기, 선택 열, 터치 로그 정렬, 판단 층 규칙표 v0, `SupportDecision` 형식과 `extension` 출력(2026-10-22, 아래 '실행 파이프라인'). 실시간 실행기의 터치 입구와 상황 태그 보내기(2026-11-25)는 아래 '주문 화면 · backend와 잇는 두 연결' |
| 연결 | 팀 논문 그림 1의 경로를 따릅니다. 주문 화면이 터치 통계를 같은 PC의 이 프로세스에 보내고(한 방향, `live.py --serve`), 이 프로세스가 창마다 상황 태그를 backend로 직접 보냅니다(`live.py --backend-url`). 주문 화면으로는 비전 값이 가지 않습니다. 세 쪽 끝이 모두 있습니다. 주문 화면의 터치 창 보내기(`VITE_AI_ENGINE_URL`), 이 프로세스의 터치 입구와 상황 태그 보내기, backend의 창 받는 곳(`POST /api/v1/sessions/{session_id}/vision-windows`)과 시연 스위치(`DECISION_SEND_SUPPORT`, 기본 꺼짐)입니다. 판단은 시연 스위치를 켰을 때만 `/features` 응답에 실려 주문 화면에 닿습니다. 남은 일은 아래 '주문 화면 · backend와 잇는 두 연결'의 '아직 남은 것'입니다. 창 결과는 `SupportDecision` 형식의 `support`와 재생 파일용 `extension`으로 기록합니다. 불편 상태 점수가 없어 `AnalyzeResponse`는 만들지 않습니다. 두 연결의 형식은 `contract/frontend-ai.openapi.json` · `contract/ai-backend.openapi.json`에 있습니다 |
| 처리 시간 | 아래 '처리 시간' 절. 측정 조건이 달라 따로 적습니다: 공개 영상 재생 프레임당 p50 42~49 ms(2026-10-22, 논리 CPU 1개), 녹화한 재현 영상 재생 중앙값 64 ms(팀 논문 3.1절, ONNX Runtime 스레드 2개) |
| 학습 | GPU 서버(GPU 1장, 팀 계정 공유)에서 머리 탐지기(Open Images 'Human head', YOLOX-Nano)를 학습했고(2026-10-12 끝), 카메라 시점 분류기(AI Hub 「안내 로봇 인터랙션 멀티모달」 머리 크롭과 '촬영방향' 라벨, ResNet-18)를 학습했습니다(2026-10-14 끝). 두 모델은 2026-10-22에 ONNX로 바꿨습니다(`models/README.md`). AI Hub 「사람 행동 인식 로봇 자율 행동 데이터」로 다가옴·사용·떠남 구간 모델을 파일럿 학습했습니다. 보조기구 탐지기(YOLOX-Nano, 공개 데이터 PMMA와 TU Graz를 함께 학습)를 `--aid-model` 선택 입력으로 연결했습니다(2026-11-22). 숫자는 발표 자료에서 다룹니다 |
| 데이터 규칙 | AI Hub 데이터는 승인받은 사람만 열람합니다(팀원 각자 신청). 원본 프레임은 저장소·발표에 넣지 않고 집계 숫자만 쓰며, 결과물에는 NIA 출처 문구를 붙입니다 |
| 검토 문서 | 관측값 후보 · 상황 태그 형식 · 팀 결정 항목 V01\~V16의 초안은 저장소 밖에 있고, 팀 결정은 통합 제안 PR에서 다룹니다 |

### 상황 태그 3개 요약 (비전 담당, 2026-10-10)

규칙 3개는 구현했습니다(PR #35; 규칙 원문과 사건 · 출력 형식은 아래 '상황 층'). 아래 표는 비전 담당이 2026-11-02 중간발표 범위로 정한 태그 3개의 요약입니다. 창 길이 · 횟수 · 각도는 기준이 없어 모두 `[파일럿]`입니다. 2026-10-28 촬영한 재현 영상 34편으로 관측 성능(팀 논문 표 1)과 상황 태그를 넣은 지원 판단(팀 논문 3.2절)을 평가했습니다. 촬영본은 평가에만 씁니다. 상황 태그만으로 지원을 적용하지 않습니다. backend 판단 단계가 비전 창 출력과 터치 통계 · 현재 화면을 함께 보고, 규칙 기반 후보 선별 뒤 Jev로 접근성 기능을 고릅니다.

| 태그 이름 | 표시 문구 | 묶는 관찰(같은 창 안) | 빼는 조건 | 근거 수준 |
|---|---|---|---|---|
| `looking_back_with_people_behind` | 뒤에 사람이 있어 서두르는 듯함 | 뒤에 기다리는 사람(주 사용자보다 작은 상자, 뒤쪽, 멈춰 선 사람만) + 뒤돌아봄(yaw 커짐, 얼굴 점 사라짐, 어깨 점 남음, 복귀)의 반복. 터치 빨라짐 · 빗나감과 표정 변동은 보조 근거 | 지나가는 사람만 있을 때, 뒤돌아봄 없이 뒷사람만 있을 때(붐빔 자체는 근거가 아님) | 문헌 + AI Hub 71827 일부(뒷사람의 높이 비). 재현 영상으로 평가함(뒷사람 정밀도 0.908, 팀 논문 표 1) |
| `consulting_companion` | 일행과 상의하는 듯함 | 동행자(비슷한 크기의 두 번째 상자, 옆) + 주 사용자 yaw가 일행 쪽 + 입 움직임(blendshape, 켜야 함) + 안 누르고 머묾, 몸 점 제자리. 입 움직임을 관측하지 못하면(blendshape 꺼짐, 값 없음) 그 조건은 결측으로 보고 조건 묶음에서 빼며, 근거(`evidence`)에는 실제로 쓴 단서만 남고 `confidence.quality_ok`가 거짓이 됨 | Face Landmarker의 `num_faces`를 2 이상으로 두면 smoothing이 꺼짐(현재 코드는 `num_faces=1`, 얼굴 수는 별도 검출기로 셈). 흔들림을 입 움직임으로 세지 않음 | AI Hub 71827 동행 라벨 + 문헌. 일행 구분은 재현 영상으로 평가함(일행 정밀도 1.000, 팀 논문 표 1) |
| `looking_around` | 무언가를 찾는 듯함 | 화면 밖으로 크게 오가는 yaw 왕복(창 안 횟수) + 몸 점 제자리 + 터치 없음 + 뒤에 사람 없음 | 메뉴 읽기의 작은 yaw(범위는 `[파일럿]`) | 문헌. 71827에는 없음 |

- 역할: 비전 쪽이 관측값과 상황 태그를 창 출력으로 제공하고, backend 판단 단계가 터치 통계와 함께 규칙 기반 후보 선별과 Jev로 접근성 기능을 고릅니다. 표정은 근거 하나로만 쓰고 혼자 쓰지 않습니다. 감정 이름과 결제 수단은 태그에 넣지 않습니다.
- 고개를 크게 돌린 구간은 각도 대신 '얼굴 점 사라짐 + 몸 점 남음' 패턴을 근거로 씁니다(`look_back` 사건으로 구현, 아래 '사건 8종'). 근거: AFLW2000-3D 2,000장 평가에서 고개를 좌우로 60\~90° 돌린 얼굴은 얼굴 점이 37.7 %에서만 나왔습니다(저장소 밖 측정, 2026-10-08, 평가 전용 데이터).
- 전달 형식: 실시간 실행기가 backend로 보내는 창은 아래 '주문 화면 · backend와 잇는 두 연결'의 형식(판단 층 키의 상황 · 관측 블록)이고, `contract/ai-backend.openapi.json`에 있습니다. 창 기록에는 창마다의 관측 요약 값 8개(`vision`)와 상황 태그(`extension.situation`)도 남습니다(아래 '계약과의 관계'). 처음 제안(관측값 14개 + `situations[]`, 2026-10-10)을 지금 출력에 맞췄습니다. 계약의 `VisionFeatures` 4칸은 그대로입니다.
- AI Hub 71827 관련 숫자는 과학기술정보통신부의 재원으로 한국지능정보사회진흥원의 지원을 받아 구축된 「사람 행동 인식 로봇 자율 행동 데이터」(AI 허브, aihub.or.kr)를 활용한 분석 결과입니다. 원본 영상과 프레임은 공개하지 않습니다.

## 실행 파이프라인 (2026-10-22)

녹화 재생(`replay.py`)과 웹캠 실시간(`live.py`)이 같은 파이프라인(`chain.py`)을 씁니다. 파이프라인은 프레임마다 한 줄을 만들고, `segment_s`초마다 창 하나를 판단하며, 입력이 끝나면 남은 구간을 길이를 적은 창(`partial`) 하나로 더 판단합니다.

```
프레임 ─ MediaPipe 3종 + blendshape ─ features.Observer 한 줄 ─────────────────────┐
       └ H1 머리 상자 ─ 트랙 · 주 사용자 트랙 · 동행자 · 뒤 사람 ─ P1 카메라 시점 ─┤ columns.py: 선택 열
터치 로그 ─ touch.py: 영상 시간축, 직전 줄 이후의 누름 · 버튼 밖 누름 ─────────────┘
segment_s마다 ─ situation.assess([t − window_s, t]) + 모름 이유
              ─ 구간 (t − segment_s, t]의 터치 횟수 · measurable · 화면 · 고개 방향
              ─ judgment/rule_table_v0.py: 지원 하나 · 형태 · 전이 (Jev 질문은 기록만)
              ─ contract_view.py: SupportDecision 형식의 support + extension (관측 가능 여부 포함)
```

- 창 끝 뒤의 줄은 어느 단계도 읽지 않습니다. 창마다 창 끝 시각 이하의 관측 줄과 터치 기록만으로 계산합니다. 사용자 반응(수락 · 거절) · 세션 신호 · 실시간 지연은 재현하지 않습니다.
- 빠진 재료는 결측으로 남깁니다. ONNX 파일이 없으면 머리 상자 · P1 카메라 시점 열이, blendshape를 켜지 않으면(`--blendshapes`, 기본 꺼짐) `mouth_motion`이, 터치 로그가 없으면 터치 열이 비고, 그 단서가 필요한 태그는 `unknown`이 됩니다. 왜 모르는지는 창 결과의 `unknown_reason`에 적힙니다.
- 창 하나에 필요한 줄은 `window_s + 2 × gap_s`초어치입니다. 실시간은 이만큼만 기억하고, 재생도 창마다 이만큼만 넘깁니다(테스트로 전체 기록과 같은 결과임을 확인함).

### 재생 (녹화 + 터치 로그)

```powershell
.venv\Scripts\python.exe -m app.modules.vision.replay --video S1a_P2_1.mp4 --touch-log S1a_P2_1_touch.json --params bundle_b0.json --out runs\replay\S1a_P2_1
```

- 녹화 옆의 `S1a_P2_1.mp4.times.csv`(프레임마다 잡은 시각)와 `S1a_P2_1.mp4.clock.json`(첫 프레임의 노트북 시각)을 저절로 읽습니다. 둘 다 시제품 `record_clip.py`가 만드는 파일입니다(촬영 대본 §4).
- 시계 파일이 없으면 `--start-offset`에 터치 로그 첫 기록이 영상의 몇 초인지 넣습니다(휴대폰 시계 · 손뼉으로 찾은 값). 둘 다 없으면 오류로 멈춥니다. `--touch-log`를 빼면 터치 열 없이 돌아갑니다.
- `--step 2`(두 장마다 한 장) · `--width 640`은 `run.py`와 같습니다. `--max-seconds`로 앞부분만 돌릴 수 있습니다. `--threads`는 ONNX Runtime 스레드 수이고 기본값은 1입니다. blendshape는 기본으로 끄며 `--blendshapes`로 켭니다. `--no-heads`는 머리 탐지기를 일부러 빼고 돌립니다. 터치 로그에 경고(1,000개 잘림)가 있으면 시작할 때 출력합니다.
- 결과: `windows.jsonl`(창마다 한 줄, 아래), `rows.csv`(프레임마다 한 줄: 'CSV 열' + 선택 열 + 처리 시간), `meta.json`(입력 · 값 묶음과 값마다의 출처 · 모델 해시 · 패키지 판 · 처리 시간 p50 · p95 · 태그와 결정의 개수 · 얼굴 · 머리 상자 · P1 확률이 있는 프레임 수 · 세션 초기화 횟수 · 마지막 창의 길이). 영상과 그림은 만들지 않습니다.

### 실시간 (웹캠)

```powershell
.venv\Scripts\python.exe -m app.modules.vision.live --camera 0 --no-window --seconds 60 --params bundle_b0.json --out runs\live_test
```

- 창마다 콘솔에 한 줄이 나옵니다. 형식 예: `[   12.0초] 상황 unknown(모름: column:tap_count) | 머리 2 · 뒤 1 · 동행 프레임 0 · 입 0.08 · 화면 봄 예 | 판단 none | 프레임 처리 45 ms`.
- `--no-window`면 화면에 아무것도 띄우지 않습니다. 빼면 창에 프레임과 주 사용자 · 동행자 상자를 그리고, 창에서 `q`를 누르거나 창을 닫으면 멈춥니다. `--seconds`가 없으면 Ctrl+C로 멈춥니다.
- `--serve` 없이 돌리면 터치 입력이 없어서, '터치 없음'이 필요한 태그는 `unknown`(이유 `column:tap_count`)으로 남고 규칙표의 터치 행(4-1 · 4-2)은 열리지 않습니다. `--serve`를 주면 주문 화면이 보낸 터치 창이 실행기의 창 판단에 들어갑니다(아래 '주문 화면 · backend와 잇는 두 연결'). 콘솔 줄의 판단(로컬 규칙표)은 그때도 터치 횟수를 읽지 않아 터치 행이 열리지 않습니다. 지원은 backend 판단 단계가 고르고, `--backend-url`을 주면 이 칸을 '로컬 규칙표'로 적습니다.
- `--seconds`도 `--out`도 없는 실행(키오스크에서 하루 종일 켜 두는 실행)은 프레임 · 창마다의 처리 시간 줄을 남기지 않습니다. 끝날 때는 프레임 수 · 창 수 · 멈춘 이유와 상황 태그 보내기의 수만 찍고, 처리 시간 백분위는 내지 않습니다(`--serve`로 시작할 때만 한 줄로 알림).
- `--out`에는 `windows.jsonl`과 `meta.json`만 씁니다. 카메라 그림은 저장하지 않습니다. `meta.json`의 `source`에는 카메라가 실제로 준 크기(`size_wh`)와 드라이버가 알린 초당 장수(`reported_fps`)가 남습니다.

### 주문 화면 · backend와 잇는 두 연결 (`--serve` · `--backend-url`, 2026-11-25)

```powershell
.venv\Scripts\python.exe -m app.modules.vision.live --camera 0 --no-window --params bundle_b0.json --serve <포트> --allow-origin http://127.0.0.1:5173 --backend-url http://127.0.0.1:8000
```

팀 논문 그림 1의 두 경로이고, 세 쪽 끝이 모두 저장소에 있습니다.

- 주문 화면: `/features`로 보내는 터치 창마다 같은 본문에 서버 세션 ID(`session_id`)를 더해 이 프로세스의 터치 입구로도 보냅니다. 주소는 `VITE_AI_ENGINE_URL`이고, 5초에 끊으며 다시 보내지 않습니다(`frontend/src/features/order/engineTouchSender.ts`, 형식: `contract/frontend-ai.openapi.json`). 답은 읽지 않습니다.
- 이 프로세스: 터치 입구(`touch_entry.py`)가 터치 창을 받아 창 판단에 넣고, 상황 태그 보내기(`tag_sender.py`)가 판단한 창을 backend로 직접 보냅니다(형식: `contract/ai-backend.openapi.json`). 카메라 처리 · 터치 입구 · 보내기는 한 프로세스에서 돌고, 카메라 그림은 프로세스 밖으로 나가지 않습니다.
- backend: `POST /api/v1/sessions/{session_id}/vision-windows`로 받은 창 가운데 끝이 짝 짓는 범위에 드는 창을 같은 세션의 `/features` 창과 짝지어, 상황과 고개 방향을 규칙표 입력으로 씁니다(`backend/README.md` 'AI 엔진 창 입구'). 그 판단은 시연 스위치(`DECISION_SEND_SUPPORT`, 기본 꺼짐)를 켰을 때만 `/features` 응답에 실려 주문 화면에 닿습니다.
- 주문 화면으로는 비전 값이 가지 않습니다.

| 옵션 | 뜻 |
|---|---|
| `--serve <포트>` | 터치 입구를 127.0.0.1의 이 포트에 엶. 정해 둔 포트가 없어 실행할 때 줌(`0`이면 운영체제가 빈 포트를 골라 시작 줄에 찍음) |
| `--allow-origin <출처>` | 터치 창을 보내도 되는 주문 화면의 출처. 주문 화면 주소창에 보이는 출처를 그대로 적음. 이 저장소의 개발 서버(`pnpm dev` = `vite --host 127.0.0.1`, `frontend/package.json`)는 `http://127.0.0.1:5173`이고, `http://localhost:5173`은 다른 출처라서 그 이름으로 열면 그 출처도 줘야 함. 출처마다 한 번씩 주고, 여러 번 줄 수 있음. `--serve`가 있어야 함. Compose의 프론트 이미지(`127.0.0.1:8080`)는 `VITE_AI_ENGINE_URL` 없이 빌드되어(`frontend/Dockerfile`) 터치 창을 보내지 않음 |
| `--backend-url <주소>` | backend 기본 주소(예: Compose backend `http://127.0.0.1:8000`). 주면 창마다 상황 태그를 보내고, 주지 않으면 보내지 않음. 창의 세션을 터치 창이 알려 주므로 `--serve`가 있어야 함 |

- `--serve`로 시작하면 콘솔에 터치 입구의 주소와 허용 출처, 주문 화면 환경 변수에 그대로 넣을 `VITE_AI_ENGINE_URL=http://127.0.0.1:<포트>` 줄, 이 주소가 backend의 `AI_ENGINE_URL`(ai-engine 앱의 `/v1/analyze`)과 다른 프로세스라는 줄을 찍습니다.
- 3-1(뒤에 줄)과 3-2(일행 상의)를 보이려면 값 묶음의 `chain`에 역할 경계 3개(`companion_rel_dist_max` · `companion_lateral_min` · `behind_rel_dist_min`)가 있어야 합니다. 경계가 없는 값 묶음(위 명령의 예처럼 상황 값만 든 것)에서는 동행자와 뒤 사람이 `unknown`이라 두 장면이 나오지 않습니다. 저장소에는 경계를 든 값 묶음을 두지 않았습니다(값마다 출처를 적어 값 묶음에 넣음, 아래 '머리 트랙과 역할').
- 새 옵션(`--serve` · `--allow-origin` · `--backend-url`)을 하나도 주지 않으면 판단 값과 창마다의 콘솔 줄은 전과 같습니다. 창 기록과 `meta.json`에는 키가 더해집니다(`contract.extension`의 `decision_situation` · `observations`, 창 기록의 `evaluated`, `meta.json`의 `source` · `tag_sender`).

**들어오는 것: 터치 창** (`POST http://127.0.0.1:<포트>/touch-windows`)

- 본문은 주문 화면의 `FeatureWindowRequest` 가운데 이 입구가 읽는 칸입니다. 다른 칸은 무시합니다.
  - `window_start` · `window_end`: 시간대가 붙은 ISO 8601 시각(주문 화면이 `Date.toISOString()`으로 만드는 형식). 끝이 시작보다 뒤여야 합니다.
  - `touch`: 그 창의 `tap_count` · `miss_tap_count` · `back_count`(0 이상의 정수, 계약 `TouchFeatures`).
  - `session_id`(선택): backend의 세션 ID. 바뀌면 세션별 상태를 처음부터 다시 세고, 상황 태그는 이 세션으로 보냅니다.
  - `screen_id`(선택): 현재 화면. 창과 함께 두고 `GET /status`에 보입니다.
- 답에는 비전 값(상황 · 장면 태그 · 고개 방향 · 관측 요약 · `measurable`)이 없습니다. 받으면 202 `{"status": "accepted"}`이고, 거절하면 `{"status": "refused", "reason": "..."}`입니다. 202는 상황 태그 보내기가 그 터치 창이 푼 창을 끝낸 뒤에, 늦어도 받은 지 `segment_s` 안에 씁니다(아래 '받은 터치 창에 답하는 때').
  - 400: 본문 형식이 틀리거나, `Content-Length`가 길이가 아님(음수 · 숫자가 아님). `Content-Length`가 없으면 411입니다.
  - 403: `Host` 머리글이 `127.0.0.1:<포트>`나 `localhost:<포트>`가 아님(메서드와 관계없이; DNS 리바인딩 막기), 또는 허용하지 않은 출처의 브라우저 페이지. `Origin` 머리글이 없는 요청(로컬 도구)은 출처로 거절하지 않습니다. 거절한 `Host`와 출처는 처음 한 번만 고칠 점과 함께 콘솔에 남습니다.
  - 503: 첫 카메라 프레임 전이거나 카메라 처리가 멈춤. 다른 경로는 404, 이 코드의 오류는 500(`status: error`)입니다.
  - `Host` · 경로 · 출처 · `Content-Length`는 머리글만 보고 판단합니다. 그래서 이 가운데 하나로 거절한 요청은 본문을 읽지 않고 `Connection: close`로 답한 뒤 연결을 닫습니다. 받는 요청만 본문을 읽습니다.
- CORS 머리글은 허용한 출처의 `POST /touch-windows`와 그 사전 요청에만 붙이고, Chrome의 Private Network Access 사전 요청에도 답합니다(WICG Private Network Access 초안).
- `GET /status`는 카메라가 도는지, 처리한 프레임 수, 마지막 프레임 시각, 기억 구간, 마지막으로 받은 터치 창(시각 · 세션 · 화면), 받은 터치 창의 마지막 번호와, 1번부터 그 번호까지의 창을 모두 마친 가장 큰 번호(`settling`)를 답합니다. CORS 머리글이 없어 페이지는 읽지 못하고 로컬 도구만 읽습니다. 터치 창을 받을 때마다 콘솔에 한 줄이 더 나옵니다.
- 시각 맞추기: 창 시각은 주문 화면의 시계(`Date.now()`)이고, 한 컴퓨터 안에서는 `time.time()`이 읽는 시스템 시계와 같습니다. 카메라 프레임마다 잡은 순간의 시스템 시각(`sources.Frame.epoch_s`)을 함께 남기고, 요청 시각 E를 마지막 프레임의 (시스템 시각 − 카메라 시각) 차이로 카메라 시간축에 옮깁니다(줄 시각과 같은 0.1 ms 단위로 반올림). 실행기가 backend로 보내는 창 시각도 같은 차이로 벽시계에 옮깁니다. 실행 중에 시스템 시계를 손으로 바꾸거나 시간 동기화가 시계를 건너뛰게 하면, 그 전에 남은 줄은 그만큼 어긋납니다.
- 터치 횟수 배치(`[설계 제안]`): 상황 규칙은 줄마다 터치 수를 읽는데 보고는 터치 창 하나의 합계라서, 실행기가 창을 판단할 때마다 상황 창 [t − `window_s`, t]의 줄 사본에 횟수를 이렇게 놓습니다. 횟수가 0인 보고 창 하나에 든 줄은 0입니다. 횟수가 있는 보고 창이 상황 창 안에 통째로 들면 그 횟수를 그 창의 마지막 줄에 놓고 나머지 줄은 비웁니다. 상황 창의 시작에 걸친 보고 창은 누름이 어디였는지 몰라 비웁니다. 보고 창에 들지 않은 줄과 두 보고 창에 겹쳐 든 줄도 비웁니다. 빈칸은 '재지 않음'이라 그 단서로 정할 수 없으면 태그는 `unknown`이 됩니다. 같은 창을 다시 보내면 앞 보고를 바꿉니다. 요청에 누름 시각을 실으면 이 배치가 정확해집니다(팀 확인 사항).
- 첫 누름 기준: 누름이 있는 창이 보고되면 다음 프레임부터 얼굴 크기 기준(`iod_ratio_user`)을 첫 누름 기준으로 모읍니다. 세션에서 누름이 보고되기 전에는 모으지 않습니다(터치 로그가 있는 재생과 같음). 그래서 오래 다가가 있어도 기준이 따라 올라가지 않습니다(아래 '장면 태그 6개').
- 세션: 새 `session_id`가 오면 다음 프레임부터 세션별 상태(트랙 · 얼굴 크기 기준 · 시작 기준)를 다시 잡고, 그 세션의 창은 첫 보고 창의 시작 뒤의 줄만 읽습니다. 그 시작과 요청 사이의 줄은 앞 세션의 상태로 처리된 채 남습니다.

**창을 판단하고 보내는 때**

- 주문 화면이 없거나(`--serve` 없음) 터치 창이 아직 세션을 알리지 않았으면, 실행기는 전처럼 자기 간격(`segment_s`)마다 창을 판단하고 아무것도 보내지 않습니다.
- 세션이 알려진 뒤에는 주문 화면의 그 구간 터치가 도착한 다음에 판단해 보냅니다. 구간 끝과 같거나 그 뒤에 끝나는 그 세션의 터치 창이 와야 그 구간을 판단합니다. 주문 화면은 창이 끝난 뒤에 보내므로, 그 전에 판단하면 마지막 터치 창 뒤의 줄이 비어 '터치 없음' 단서를 모르게 되기 때문입니다. 터치 창이 온 뒤 첫 프레임에서 판단합니다. 터치 창은 주문 화면의 창 길이(2026-11-26부터 1초)라서, 터치 창 하나가 오면 그 안에서 끝나는 1초 구간 하나를 판단합니다. 늦거나 건너뛴 터치 창 뒤에는 터치 창 하나가 구간 여러 개를 함께 판단합니다. 실행기는 창마다 자기 길이를 읽으므로 2초 터치 창도 그대로 받습니다(구간 두 개).
- 기다림의 한도는 실행기가 이미 쓰는 기억 구간(`keep_s` = `window_s + 2 × gap_s + segment_s`)입니다. 구간의 시작이 최근 프레임에서 `keep_s`보다 멀어지려 하면, 터치가 오지 않았어도 그대로 판단합니다(터치가 빈 줄은 모름). 그래서 한 구간은 길어야 `keep_s − segment_s` 기다립니다. 그동안 실행기는 그 창이 읽을 줄을 남겨 두어, 늦게 판단한 창도 바로 판단한 창과 같은 줄을 읽습니다. 남겨 두는 줄은 길어야 `2 × keep_s − segment_s`초어치입니다.
- 세션이 바뀌면 전처럼 처음부터 다시 셉니다. 앞 세션의 터치 창은 새 세션의 구간을 풀어 주지 않습니다. 새 세션의 구간이 먼저 준비되면 앞 세션에서 기다리던 구간은 그대로 판단합니다. 입력이 끝나면 남은 구간을 모두 판단합니다. 구간은 늘 시간 순서로 판단합니다.
- 창 기록의 `evaluated`가 어떻게 판단했는지 적습니다. `how`는 `touch`(터치 창이 온 뒤) · `cadence`(자기 간격) · `kept_history`(기억 구간 한도) · `later_ready`(새 세션의 구간이 먼저 준비됨) · `input_end`(입력 끝)입니다. `at`은 판단한 프레임의 시각, `touch_until`은 그 세션의 터치를 받은 끝 시각입니다. `touch_complete`는 규칙이 상황 창의 터치 단서를 정할 수 있었는지입니다. 누름이 한 줄에라도 보였거나 모든 줄에 횟수가 있으면 참입니다(`events.window_any_tap`, 규칙의 `any_tap`과 같은 조건).
- 실행기를 켠 뒤 첫 세션도 나중 세션처럼 그 세션의 첫 터치 창 시작 뒤의 줄만 읽고, 첫 세션이 알려진 다음 프레임부터 세션별 상태(머리 트랙 · 주 사용자 · 얼굴 크기와 시작 기준)를 처음부터 다시 잡습니다. 실행기는 주문 세션이 생기기 전부터 돌고 있어, 그 앞의 줄과 상태는 어느 세션의 것도 아니기 때문입니다. 재생의 터치 로그는 첫 세션과 함께 시작하므로 재생은 전과 같습니다. 기다림의 한도 `keep_s − segment_s`(= `window_s + 2 × gap_s`)가 터치 창 하나의 길이(2026-11-26부터 1초)와 전달 시간을 더한 것보다 짧은 값 묶음에서는, 터치가 오기 전에 한도에서 판단하는 구간이 생깁니다.

**받은 터치 창에 답하는 때**

- 받은 터치 창에는 받은 순서대로 1부터 번호를 매깁니다. 번호는 창을 저장하는 잠금 안에서 줍니다.
- 실행기는 다음 두 조건이 모두 맞으면 창 n을 마친 것으로 적습니다.
  - 카메라 시간축에서 창 n의 끝과 같거나 그 뒤의 프레임을 처리했고, 창 n을 담은 터치 상태 사본으로 그 프레임이나 그 뒤의 flush(`live.run_live`가 프레임마다 준비된 구간을 판단해 내보내는 단계)가 돌았습니다. flush는 판단할 구간이 없어도 프레임마다 한 번 돕니다. 이때까지 창 n의 끝 이전에 끝나는 구간은 모두 풀렸습니다.
  - 상황 태그 보내기가 그 flush가 푼 묶음과 그 앞의 묶음을 모두 끝냈습니다. 묶음의 창마다 보냄 · 실패 · 건너뜀이 정해졌거나, 묶음이 보내지 않은 채 새 묶음으로 바뀌었거나, 보내기가 끝내는 중이면 그 묶음은 끝난 것으로 봅니다. 푼 창이 없는 flush는 앞 묶음이 끝나면 마치고(보내기가 쉬고 있으면 바로), 보내기가 없는 실행은 바로 마칩니다.
- 창은 하나씩 따로 마칩니다. 요청 두 개가 동시에 오가면 받은 순서와 창이 끝나는 순서가 다를 수 있어서, flush는 그 프레임까지 끝난 창만 마칩니다. `GET /status`의 마친 번호(`settled`)는 1번부터 그 번호까지의 창을 모두 마친 가장 큰 번호이고, 줄지 않습니다.
- 받은 창의 HTTP 처리기는 그 창을 마칠 때까지 기다렸다가 전과 같은 202 본문을 씁니다. 기다림은 길어야 값 묶음의 `segment_s`(상황 태그 보내기의 제한 시간과 같은 값)이고, 카메라 처리가 멈추면 바로 씁니다. 거절(400 · 403 · 404 · 411 · 503)은 전처럼 바로 답합니다.
- 그래서 202는 '받았고, 이 터치 창이 푼 창을 상황 태그 보내기가 끝냈다(위 두 번째 조건), 또는 `segment_s`가 지났거나 카메라 처리가 멈췄다'는 뜻입니다. 주문 화면이 이 답을 받은 뒤 보내는 `/features` 요청은 대개 그 엔진 창을 읽습니다. 다만 엔진 창을 backend에 넘기는 일과 요청이 읽는 일은 보장하지 않습니다(best effort). 보내기가 실패로 끝난 엔진 창은 backend에 닿았는지 알 수 없습니다. 답을 읽다가 제한 시간을 넘긴 보내기는 backend가 창을 이미 받았어도 실패로 셉니다. 보내기 전에 새 묶음으로 바뀐 엔진 창은 어느 요청도 읽지 못합니다. 답에는 여전히 비전 값이 없습니다.
- 기다리는 동안 카메라 처리나 보내기가 쓰는 잠금은 잡지 않고, 카메라 처리는 답을 기다리지 않습니다.
- 두 번째 조건이 그 flush의 묶음뿐 아니라 앞 묶음까지 기다리는 이유: 카메라 처리가 주문 화면의 시계보다 조금 늦으면, 창 끝 전의 프레임에서 그 터치 창이 푼 구간이 먼저 나가고 창 끝 뒤의 flush는 풀 것이 없습니다. 이때도 답은 보내기가 그 구간을 끝낸 뒤에 나갑니다.

**나가는 것: 상황 태그** (`POST <backend>/api/v1/sessions/{session_id}/vision-windows`)

- 실행기가 창을 판단하면(위 '창을 판단하고 보내는 때'; 재생과 같은 `WindowJudge`가 위의 터치 배치를 함께 읽음), 그 창 끝이 터치 창이 알린 세션 안에 있을 때 그 창을 보냅니다. 터치 창이 아직 세션을 알리지 않았으면 보내지 않습니다.
- 실행기는 터치 창마다 그 터치 창이 함께 푼 구간을 모두 backend로 보냅니다. 어떤 창을 버리는지는 아래 우편함 항목과 404 · 410 항목에 있습니다. 팀 논문의 1초는 구간(`segment_s`)의 길이입니다. 1초 터치 창 하나는 그 안에서 끝나는 구간 하나를 풀고, 늦거나 건너뛴 터치 창 뒤에 한 터치 창이 구간 여러 개를 함께 풀면 그 구간들은 우편함의 한 묶음으로 시간 순서대로 보내집니다.
- 본문의 키는 6개입니다.
  - `session_id`: 경로의 세션과 같습니다. backend → ai-engine 계약의 `AnalyzeRequest`도 세션을 본문에 싣습니다.
  - `window_start` · `window_end`: 창 기록의 `segment_s` 구간을 위의 시각 맞추기로 벽시계에 옮긴 ISO 8601 UTC 시각(밀리초까지)입니다. 판단한 때가 늦어도 구간의 시각은 그대로입니다.
  - `situation`: 아래 '계약과의 관계'의 `decision_situation`, 곧 판단 층이 읽는 `name` · `evidence` · `confidence`입니다.
  - `observations`: `gaze` · `face_seen` · `scene_tags`입니다.
  - `model_version`: 창 결과의 버전 표시입니다.
- 카메라 처리는 보내기를 기다리지 않습니다. 한 번의 판단이 함께 푼 창들(터치 창 하나가 푼 구간들, 또는 홀로 풀린 창 하나)은 한 묶음으로 칸 하나짜리 우편함에 들어가고, 스레드 하나가 그 묶음의 창을 시간 순서로 보냅니다. backend가 느려 앞 묶음을 보내는 동안 묶음이 쌓이면, 아직 보내기 시작하지 않은 묶음은 새 묶음이 통째로 바꿉니다(그 창들은 `replaced`로 셈). 묶음의 크기는 실행기의 기다림 한도로 이미 정해집니다. 응답이 2xx가 아니거나, 연결이 안 되거나, 제한 시간을 넘기면 실패로 세고 버리며 다시 보내지 않습니다. 첫 실패만 콘솔에 한 줄 찍습니다.
- 묶음에는 끝났을 때 한 번 부를 함수(`done`)를 실을 수 있습니다. 그 묶음과 앞 묶음이 모두 끝나면 부릅니다. 빈 묶음은 `done`만 싣고 우편함의 묶음을 바꾸지 않습니다. 실행기는 이것으로 터치 창을 마친 것으로 적습니다(위 '받은 터치 창에 답하는 때').
- backend가 404(모르는 세션, 예: backend를 다시 켠 뒤)나 410(주문을 마친 세션)으로 답하면 실패로 세지 않습니다. `ended_404` · `ended_410`으로 세고 종류마다 처음 한 번 콘솔에 찍으며, 새 세션 ID의 창이 올 때까지 그 세션의 창은 보내지 않습니다(`skipped_ended`).
- 제한 시간은 창 간격 `segment_s`(값 묶음, 기본 1.0초 `[파일럿]`)라 보내기가 자기 창보다 오래 걸리지 않습니다. 이 시간은 연결과 읽기 한 번마다 걸립니다(urllib의 소켓 제한 시간). 프록시를 거치지 않고 바로 연결하며, 표준 라이브러리만 씁니다.
- 실행이 끝나면 우편함에 남은 묶음과 보내던 묶음의 나머지를 제한 시간 하나 안에서 보냅니다. 보낸 수 · 실패 수 · 새 창으로 바뀐 수 · 끝에 못 보낸 수 · 끝난 세션의 답과 건너뛴 수 · 마지막 오류는 `meta.json`의 `tag_sender`와 마지막 콘솔 줄에 남습니다.
- `--backend-url`을 주면 창마다의 콘솔 줄에서 판단 칸을 '로컬 규칙표'로 적습니다. 그 칸은 이 실행기의 규칙표이고, 화면에 닿는 판단은 backend 판단 층의 것입니다.

아래는 테스트의 합성 줄(오른쪽 · 왼쪽으로 한 번씩 고개를 돌림, 터치 없음)로 만든 실제 본문이고, `"..."`는 줄인 곳입니다. 시각은 테스트의 가짜 시계 값입니다.

```json
{"session_id": "s1", "window_start": "2027-01-15T08:00:01.700Z", "window_end": "2027-01-15T08:00:02.700Z",
 "situation": {"name": "looking_around",
               "evidence": [{"event_id": "dwell_no_touch@0", "obs": "no_touch_s", "value": 2.7, "t": 2.7},
                            {"event_id": "yaw_sweep_offscreen@5", "obs": "yaw_deg", "value": 55.0, "t": 0.9}, "..."],
               "confidence": {"events": 3, "quality_ok": true}},
 "observations": {"gaze": true, "face_seen": true,
                  "scene_tags": [{"name": "seated_height", "status": "unknown", "unknown_reason": "no_value_for_camera",
                                  "evidence": []}, "...",
                                 {"name": "phone_use", "status": "unknown", "unknown_reason": "column:phone_owner",
                                  "evidence": []}]},
 "model_version": "vision-situation-rules_v1+rule_table_v0-shadow"}
```

**아직 남은 것**

- 4-1의 횟수: 빗나간 뒤 바로 고친 횟수(`fixes_recent`)를 만드는 곳이 주문 화면에 없어, backend 규칙표의 4-1은 열리지 않습니다(`backend/README.md` '시연 스위치').
- backend의 `/v1/analyze` 호출: backend는 `/features` 창마다 ai-engine 앱의 `/v1/analyze`를 아직 부릅니다(그림 1에 없는 화살표). 시연 스위치를 켜면 그 답과 관계없이 판단이 응답에 실립니다.
- 2단계 행: 장면 태그(1-1 · 1-2 · 2-1 · 2-2 · 자리 비움)를 지원으로 잇는 판단 행은 아직 구현하지 않았습니다. backend는 짝 지은 창의 `scene_tags`를 창 기록에 남깁니다.
- backend의 3-2 휴대폰 길: backend 규칙표에는 `phone_use` 길과, 측정할 수 없는 창에서 그 길만 통과시키는 예외가 아직 없습니다. 이 엔진의 로컬 규칙표에만 있습니다(아래 '기존 재생용 규칙표 v0').
- 입구의 포트는 정해 두지 않았습니다(실행할 때 줌).
- 벽시계가 건너뛸 때: 구간이 터치 창을 기다리는 동안 PC의 벽시계가 건너뛰면(손으로 바꾸거나 시간 동기화가 맞춤), 기다리던 구간은 건너뛴 뒤의 차이로 벽시계 시각이 찍혀 backend로 갈 수 있습니다. 늦게 온 터치 창도 그 차이로 카메라 시간축에 놓입니다. 실행기는 이 경우를 다루지 않습니다(프레임마다 시계 차이를 따로 두지 않음).

**시험 도구(카메라 없음)**

```powershell
.venv\Scripts\python.exe -m app.modules.vision.tools.integration_smoke --seconds 30 --params bundle_b0.json --out runs\integration_smoke
```

- 가짜 카메라(검은 프레임, 기본 640×480: 아래 '처리 시간'의 합성 입력 크기)로 실제 모델을 돌립니다. 주문 화면 대신 카메라가 돌기 시작하면 2초(`FEATURE_WINDOW_MS`)마다 방금 끝난 창을 터치 0회 · 세션 `smoke` · 화면 `menu`로 보냅니다.
- 시험 backend(127.0.0.1, 202로 답함)는 받은 창마다 한 줄을 찍습니다. 구간(`window_start`~`window_end`), 세션, 상황 태그, 터치 단서를 판정했는지(`evaluated.touch_complete`)와 실행기가 언제 판단했는지(터치 창이 온 뒤 · 기억 구간 한도 · 입력 끝 등), 고개 방향, 얼굴, 장면 태그, 구간 끝 뒤 도착 시간입니다. 두 구간은 그 터치 창이 온 뒤 함께 보내지므로, 2초 터치 창의 앞 구간은 자기 끝보다 1초쯤 늦게 도착합니다. 화면에 사람이 없어 상황은 `none`이나 `unknown`입니다. 이 도구는 무엇을 언제 어느 세션으로 보내는지만 봅니다.
- `--out`을 주면 `smoke_summary.json`(설정 · 보낸 수 · 창 끝 뒤 도착 시간 p50 · p95 · 받은 본문)과 실행기의 `live/` 파일을 남깁니다. 그림은 저장하지 않습니다.

### 값 묶음 파일 (`--params`)

상황 규칙의 기준값 13개(`events.PilotParams`)는 기본값이 없습니다. 값은 출처(표준 · 관행 · 문헌)와 공개 데이터로 정하고, 출처가 없는 값은 값 묶음마다 결과를 나란히 보입니다. 재현 영상(2026-10-28 팀 촬영본)으로는 값을 정하지 않고 평가에만 씁니다. 실행 파이프라인이 새로 쓰는 값(`params.PilotParams`)에는 기본값과 출처가 있고, 값 묶음 파일에서 바꿀 수 있습니다.

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
 "detectors": {"heads": true, "aids": false, "phones": false},
 "turns": [{"event_id": "yaw_sweep_offscreen@10", "kind": "yaw_sweep_offscreen", "t_start": 1.0, "t_end": 1.4,
            "obs": {"yaw_deg": 55.0, "side": "right", "offscreen_s": 0.4}}, "..."],
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
 "contract": {"support": {"preset": "none", "requires_confirmation": false, "decided_by": "rule_placeholder"},
              "extension": {"measurement": {"measurable": true,
                                            "basis": "A tap or back in the segment, or a face seen in the segment (team placeholder)."},
                            "model_version": "vision-situation-rules_v1+rule_table_v0-shadow",
                            "detectors": {"heads": true, "aids": false, "phones": false},
                            "situation": {"...": "..."}, "decision_meta": {"...": "..."}}},
 "ms_window": 0.7}
```

- `situation`: 창의 `assess` 출력입니다. `evidence_ids`는 근거 사건 ID 목록이고, `evidence`에는 사건마다의 관찰 값이 있습니다(아래 '출력 형식'). 대안은 이름 · 확신 정보 · 근거 사건 ID만 남깁니다. `unknown_reason`(모름 이유)은 `name`이 `unknown`일 때만 채웁니다: `no_value_bundle`(값 묶음 없음) · `no_frames`(창에 프레임 없음) · `sensor_failure`(몸 추적 비율이 `track_conf_min` 미만) · `tie`(두 태그의 근거 사건 수가 같음) · `missing_cue`(태그마다 모자란 단서: `column:tap_count` · `column:people_behind_count` · `column:companion_box` · `yaw_missing` · `shoulder_visibility_missing` · `turn_unresolved` · `face_visible_ratio<face_visible_min` · `companion_side_unknown` · `body_position_missing`) · `too_few_events`(근거 사건이 `min_events`보다 적음).
- `touch`: 구간 (t − `segment_s`, t]의 횟수입니다. 터치 로그가 없거나 구간이 로그의 관측 구간에 통째로 들지 않으면 `touch` 전체가 `null`입니다. `near_miss_fix_count`는 버튼 밖 누름 뒤 그 옆 버튼을 바로 누른 횟수이고, 구간 안에 대상 정보가 없는 누름이 있으면 `miss_tap_count`와 함께 `null`입니다.
- `screen`: 그 시각의 화면(`menu` · `review` · `complete`; 로그가 멈춘 뒤는 `null`), 주문 끝까지 남은 화면 수, 이 화면 방문에서 누른 뒤 지난 초(`pause_s`; 이 방문에서 아직 누르지 않았으면 `null`), 옵션 창이 열려 있는지(`options_open`)입니다.
- `vision.facing_screen`: 구간에서 얼굴이나 몸을 마지막으로 본 프레임 기준으로, 얼굴이 보이고 |yaw|가 `offscreen_yaw_deg` 미만이면 참, 그 이상이면 거짓입니다. 그 프레임에 얼굴 없이 몸만 보이면 고개 방향을 못 잰 것이라 `null`이고(터치 행은 올린 기준으로 봄, tree §4 ⑦), 본 프레임이 없거나 값 묶음이 없어도 `null`입니다. 구간 안에서 사용자가 바뀌면(`user_changed`가 교체로 세는 트랙 바뀜) 새 사용자의 줄만 봅니다. 앞 사용자의 얼굴 방향으로 새 사용자의 고개 방향을 정하지 않기 위해서입니다.
- `measurable`: 팀 자리표시자(`app/inference/placeholder.py`)와 같은 뜻입니다. 구간에 누름이나 되돌아감이 있거나 얼굴이 한 번이라도 보이면 참입니다. 휴대폰 탐지기를 켰을 때 장면 태그 `phone_use`가 참인 창은 `measurable`이 거짓이어도 3-2 기다림을 열거나 유지(`hold_timer` 신호)할 수 있고, 다른 행은 그 창에서 열리지 않습니다. 휴대폰 길은 주 사용자를 카메라로 본 관측이고, 휴대폰을 내려다보면 얼굴을 놓치기 때문입니다. `measurable` 값 자체는 탐지기를 켜도 자리표시자의 뜻 그대로입니다. JP §0-1 2항의 뜻(고른 뒤 멈춤 같은 터치 단서와 카메라 관측도 셈)과 맞추는 일은 2026-10-14 안건 3이라, 여기서는 자리표시자의 뜻을 따릅니다.
- `detectors`: 그 창 구간의 줄에서 돌아간 선택 탐지기입니다. 머리 탐지기(`heads`) · 보조기구 탐지기(`aids`) · 휴대폰 탐지기(`phones`)가 켜져 있으면 구간의 줄마다 각자의 열(`head_count` · `aid_owner` · `phone_owner`)을 쓰므로, 그 열이 있는 줄이 구간에 하나라도 있으면 참입니다. `phone_every`로 탐지기가 건너뛴 줄도 빈 `phone_owner` 열이 있어 참으로 셉니다. 구간에 줄이 없으면(`frames` 0) 셋 다 거짓입니다. 계약 변환 출력의 `extension.detectors`에도 같은 값을 싣고, `extension.model_version`은 탐지기를 켜든 끄든 같은 문자열입니다.
- `turns`: 창 안의 고개 돌림 사건(`look_back` · `yaw_sweep_offscreen`) 목록입니다. 사건마다 `event_id` · `kind` · `t_start` · `t_end`와 관찰 값(`obs`)이 있고, 뒤돌아봄은 아래 '사건 8종'의 맥락 값 넷도 담습니다. 관측 기록이라 계약 변환 출력에는 넣지 않습니다. 값 묶음이 없으면 사건을 찾지 않으므로 `null`입니다.
- `session_reset`: 터치 로그의 세션(`sessionId`)이 바뀐 창이면 참이고, 그 창부터 판단 상태(유지 중인 결정 · 거절 · 거둔 목록)를 처음부터 다시 셉니다(tree §4 ①). 세션이 바뀐 뒤의 창은 새 세션의 첫 기록 이후 관측 줄만 읽습니다. 그래서 이전 사용자의 관측은 상황 · `measurable` · 고개 방향에 들어가지 않습니다. `partial`은 입력의 마지막 남은 구간을 판단한 창에만 있고 그 길이를 적습니다.

### 기존 재생용 규칙표 v0 (`judgment/rule_table_v0.py`)

아래는 로컬 재생 구현의 설명입니다. backend 판단 단계(`backend/app/modules/decision/rule_table.py`)가 이 규칙표를 행 그대로 옮겨 `/features` 창마다 실행합니다(`docs/Jev-Integration.md` 10장). 다만 3-2 휴대폰 길(`phone_use`)과 측정할 수 없는 창에서 그 길만 통과시키는 예외는 backend 사본에 아직 없습니다(통합 작업). 팀 논문의 시스템 설계에서는 판단 모델 호출이 실패하거나 제한 시간을 넘기면 규칙 기반 결과를 적용하고(2.3절), 팀 논문 실험은 규칙 모델을 비교 기준으로 썼습니다(3.3절).

JP §0-2 · §0-3과 장면 표, tree 표 3-가 · 3-나 · §4에서 장면 4개의 지원 이름 · 형태 · 순서 · 전이 · 거두는 조건을 옮겼습니다. 창마다 지원 하나 또는 없음을 냅니다. 순서(`rank`)는 JP 순서표의 번호입니다. 원문과 다르게 둔 것은 아래 표의 여는 조건과 '터치 단서의 범위'에 적었습니다.

| 장면 | 지원 | 형태 | 순서 | 여는 조건 | Jev(그림자) | 거두는 조건 |
|---|---|---|---|---|---|---|
| 3-2 일행 상의 | `wait_hold_timer` | 기다림(`session_signal` `{name: hold_timer}`를 열 때와 유지할 때 실음. 측정할 수 없는 창의 유지에는 휴대폰 길(`phone_use` 참)일 때만 실음) | 2 | 태그 `consulting_companion`(일행 길) 또는 장면 태그 `phone_use`(휴대폰 길, 휴대폰 탐지기를 켤 때만). 세션 동작이라 거둔 뒤에도 방아쇠마다 다시 엶 | 없음 | 터치가 이어짐(`touch_resumed`) |
| 3-1 뒤에 줄 | `remaining_steps_notice`(조건표가 켜면 격려 메시지 `delay_responsibility_notice`) | 바로 적용 | 3 | 태그 `looking_back_with_people_behind`, 남은 화면이 있거나 모름 | 허용 후보가 둘(알림 · 큰 버튼 질문 미룸; 미룸은 고개 게이트를 지난 4-1 행이 같은 창에 있을 때만)이면 Choice, 하나면 적합성 Noul. 안내는 없음 | 장바구니가 나아감(`cart_progress`) |
| 4-1 손 떨림 | `large_button` | 묻기 | 4 | 남은 화면이 있는 화면에서, 최근 `touch_span_s`초의 '버튼 밖 누름 뒤 그 옆 버튼을 바로 누름'(`near_miss_fix_count`)이 `tremor_miss_min` 이상이고 화면을 봄. 카메라가 고개 방향을 못 재면 `tremor_miss_min_no_gaze` 이상(Jev 없음). 화면을 보지 않으면 행 없음 | 적합성 Noul | 없음(반응 · 무응답으로 끝남) |
| 4-2 헤맴 | `highlight_next_action` | 바로 적용(조용히) | 7 | 남은 화면이 있는 화면에서 되돌아감 `lost_back_min` 이상, 또는 이 화면 방문에서 누른 뒤 `lost_pause_s` 이상 멈춤(두리번 태그나 화면을 보는 고개가 있으면 `lost_pause_s_vision`; 아직 누르지 않았으면 멈춤 아님) | 적합성 Noul | `cart_progress` |
| 직원 호출 | — | 직원 호출 | 9 | 규칙표가 열지 않음(JP에 여는 조건이 없음) | — | — |

판단 순서(JP §0-3)는 다음과 같습니다.

1. 측정할 수 없는 창(`measurable` 거짓)은 유지 중인 결정을 되풀이하거나 아무것도 내지 않습니다.
2. 유지 중인 결정의 거두는 조건이 맞으면 거둡니다.
3. 후보 행이 없으면 유지 중인 결정을 되풀이하거나 아무것도 내지 않습니다.
4. 유지 중인 결정이 없으면 순서가 가장 앞선 행을 엽니다.
5. 떠 있는 묻기는 끝날 때까지 두고, 순서가 앞선 3-2 기다림만 그 자리를 바꿉니다.
6. 그 밖에는 순서가 앞선 행이 바꿔 들어갑니다. 한 창 동안 보인 조용한 알림 · 강조는 묻기에 자리를 내줍니다.

- 터치 단서의 범위: tree 표 3-가의 4-1 '같은 버튼 근처 빗나감 · 바로 고침'은 프론트가 버튼 밖 누름마다 남기는 가장 가까운 버튼 목록(`nearestCandidates`; 거리 상한 없음, 팀 항목 T03)과 그다음 누름을 이어 '빗나감 뒤 그 옆 버튼을 바로 누름'으로 셉니다(연결 기준은 팀 항목 T07에서 정하므로 `[설계 제안]`). 버튼 밖 누름 수만으로는 열지 않습니다. 4-2는 되돌아감과 고른 뒤 멈춤을 봅니다('담지 않고 오감', 곧 옵션 창을 열었다가 담지 않고 닫음은 세지 않습니다). 터치 로그가 시작된 뒤와 세션이 바뀐 뒤 `touch_span_s`초(기본 5초) 동안은 최근 구간이 통째로 관측되지 않아 4-1과 4-2의 되돌아감 단서가 열리지 않습니다. 거두는 조건 `cart_progress`는 다음 화면으로 넘어감(`menu`에서 `review`, `review`에서 `complete`)만 진행으로 봅니다. '담기'(`cart-add`) 누름은 시도라서, 누름이 취소되거나 주문 API 저장이 실패하면 장바구니는 그대로입니다. 원시 기록에는 그 결과가 없어(팀 항목 T06) '담기' 누름은 진행 여부를 모름으로 두고 지원을 거두지 않습니다.
- 후보 거르기(JP §0-2): 켠 지원(`active`), 거절한 지원(`refused`, 세션 동안), 같은 범위에서 거둔 지원(`withdrawn`)과 지금 유지 중인 지원은 열지 않습니다. 범위는 태그 행이면 태그 구간, 그 밖이면 화면 방문이고, 범위가 바뀌면 거둔 지원이 다시 후보가 됩니다. 3-2 기다림은 화면에 띄우는 지원이 아니라 세션 동작이라 거둔 목록으로 거르지 않습니다(JP v1.6).
- 상황이 `unknown`이거나 값 묶음이 없으면 태그 행은 열리지 않고 터치 행만 판단합니다(JP §0-2: 상황 근거만 빼고 판단). Jev 질문(`jev_request`)도 상황이 알려진 창에서만 만듭니다(JP §0-4).
- 세션 상태(유지 중인 결정 · 켠 지원 · 거절 · 거둔 목록)는 설계상 backend가 갖습니다(JP §0-1). 재생은 같은 규칙으로 흉내 냅니다: 그림자 모드라 연 결정은 그 창에 바로 보인 것으로 두고, 묻기에 `no_response_s`초 동안 반응이 없으면 무응답으로 거둡니다. 재생에는 사용자 반응 기록이 없어 수락 · 거절은 일어나지 않습니다. 유지 중인 결정은 결정 전체를 갖고, 되풀이(keep)는 같은 `decision_id`로 장면 · 정책 · 단서 · 실행 칸을 다시 싣습니다(JP §0-1). 터치 로그의 세션이 바뀌면 상태를 처음부터 다시 세고, 관측 줄도 새 세션 것만 읽습니다(tree §4 ①).
- Jev: 질문을 만들어 기록만 합니다(`jev_stub.ShadowJev`). ai-engine은 외부 AI API를 부르지 않으므로(AGENTS.md §4) 실제 호출은 backend 어댑터의 몫이고, 화면은 규칙 결과를 따릅니다(`decided_by` = `rule_placeholder`). 질문 글은 영어이고, 3-1 후보의 설명(`criteria`)은 JP §2-2의 문장이며, 질문 지시문과 `state`의 구성은 이 모듈이 정했습니다. 4-1 · 4-2의 맞음 · 안 맞음 경계 문장은 설계 노트에 없어 이 모듈에서 가안으로 적었습니다.

### 계약과의 관계 (추가형 제안, 명세는 그대로)

- 이 모듈은 `contract/backend-ai.openapi.yaml`(0.2.0)과 `contract/frontend-backend.openapi.yaml`을 바꾸지 않았습니다. `frontend-backend.openapi.yaml`의 `SupportDecision`에는 backend 시연 스위치가 싣는 선택 필드가 더해졌습니다(backend). 두 연결의 형식은 `contract/frontend-ai.openapi.json`(주문 화면 → 터치 입구)과 `contract/ai-backend.openapi.json`(실행기 → backend)입니다.
- 불편 상태 모델이 이 파이프라인에 없어 상태 점수를 만들지 않습니다. 백엔드 `AnalyzeResponse`는 `measurable=true`일 때 비어 있지 않은 `states`를 요구하므로 `analyze_response` 키를 출력에서 뺐습니다. `measurable=false` · `states=null`은 백엔드 모델에서 유효하지만, 센서 관측이 있는 창도 이 응답으로 표시하지 않습니다.
- `support`는 기존 `SupportDecision` 형식(`preset` · `requires_confirmation` · `decided_by`)을 유지합니다. `decided_by`는 그림자 모드라 늘 `rule_placeholder`입니다. 지원과 `UIPreset`의 대응은 JP §2-5 표를 따랐습니다(알림 = `step_guide`, 큰 버튼 묻기 = `large_button` · 확인 필요, 강조 · 기다림 = `none`).
- 계약 변환 출력에서 센서 관측 가능 여부는 `extension.measurement`의 `measurable`과 `basis`에만 담고, 파이프라인 버전은 `extension.model_version`에 둡니다. `basis`는 팀 자리표시자와 같은 기준인 ‘구간에 누름이나 되돌아감이 있거나 얼굴이 한 번이라도 보임’을 설명하고, `phone_use`가 참이고 `measurable`이 거짓인 창에서는 그 창에서 3-2 기다림만 열거나 유지할 수 있다고 덧붙입니다. `measurable`이 참인 창은 `phone_use`와 상관없이 모든 행을 판단하므로 이 문장을 붙이지 않습니다. 창 기록 자체의 `measurable`은 내부 판단용으로 유지하며, 불편 상태 점수 산출 여부를 뜻하지 않습니다. 센서 관측 가능 여부와 상태 점수 산출 여부를 계약에서 분리하는 안은 추가형 계약 제안으로 팀 합의에서 정합니다.
- 명세에 없는 칸(상황 태그 · 표시 문구 · 근거 사건 ID · 모름 이유 · 대안 · 품질, 결정의 지원 · 형태 · 전이 · 범위 · 정책 · Jev 종류, 실행 칸 `steps_left` · `target_id` · `message_id` · `session_signal`)은 `extension`에 담았습니다. 실행 칸은 JP §2-5의 `decision_meta`를 따른 `[설계 제안]`입니다: 3-1 알림은 `cart_progress` · `steps_left_notice`(격려 메시지는 `delay_responsibility_notice`; 서두르지 않아도 된다는 한 줄입니다. 이전 이름은 '지연 책임 안내'이며 코드 이름은 그대로 둡니다), 4-2 강조는 옵션 창이 열린 메뉴 화면이면 `cart-add`, 장바구니 화면이면 `cart:*:decrease`(줄마다 다른 '−' 버튼 ID의 패턴), 그 밖은 비움(자주 찾는 메뉴 줄 · 검색은 강조 대상에 없음)이고, 문구 ID는 비워 둡니다. 이 칸을 응답의 선택 칸으로 더하는 것은 추가형 제안이고, 화면이 이 칸을 읽는 형식과 뜻은 팀 통합에서 정합니다(2026-10-14 회의 안건 V04 · 6). `extension`은 재생 파일의 출력이지 기존 API의 응답이 아닙니다.
- 요청 쪽 `TouchFeatures` 가운데 이 모듈의 창 결과는 `tap_count` · `miss_tap_count` · `back_count`를 채웁니다. `repeat_tap_count` · `dwell_ms`는 주문 화면이 파일럿 기준으로 계산해 보냅니다(`frontend/README.md`, 2026-11-17).

위 '창 한 줄'의 창(t = 4.0)에서 `contract_view.to_contract`가 낸 `contract`를 줄이지 않고 옮기면 다음과 같습니다. 숫자는 합성 입력과 기본값(`[파일럿]` 포함)의 값이고 기준값이 아닙니다.

```json
{"support": {"preset": "none", "requires_confirmation": false, "decided_by": "rule_placeholder"},
 "extension": {
   "measurement": {"measurable": true,
                   "basis": "A tap or back in the segment, or a face seen in the segment (team placeholder)."},
   "model_version": "vision-situation-rules_v1+rule_table_v0-shadow",
   "detectors": {"heads": true, "aids": false, "phones": false},
   "situation": {"tag": "looking_around", "display_text": "무언가를 찾는 듯함",
                 "evidence_ids": ["dwell_no_touch@0", "yaw_sweep_offscreen@10", "yaw_sweep_offscreen@24"],
                 "confidence": {"events": 3, "quality_ok": true}, "alternatives": [], "unknown_reason": [],
                 "quality": {"face_visible_ratio": 1.0, "track_conf": 1.0}, "source": "rules_v1",
                 "tags": [{"name": "seated_height", "status": "unknown", "unknown_reason": "no_value_for_camera",
                           "evidence_ids": []},
                          {"name": "face_approach", "status": "unknown", "unknown_reason": "no_value", "evidence_ids": []},
                          {"name": "user_changed", "status": false, "unknown_reason": null, "evidence_ids": []},
                          {"name": "none_seen", "status": false, "unknown_reason": null, "evidence_ids": []},
                          {"name": "aid_use", "status": "unknown", "unknown_reason": "column:aid_owner",
                           "evidence_ids": []},
                          {"name": "phone_use", "status": "unknown", "unknown_reason": "column:phone_owner",
                           "evidence_ids": []}]},
   "decision_meta": {"decision_id": "d0001", "withdrawn_id": null, "support": "highlight_next_action", "scene": "4-2",
                     "action": "apply", "intervention": "바로 적용", "transition": "open",
                     "scope": ["screen", "menu", 1.0], "rank": 7, "withdraw_on": "cart_progress",
                     "policy": {"kind": "fit", "ask_jev": true, "lowered_action": "wait", "raised_action": null,
                                "T_LOWER": null, "T_AID": null, "T_CHOICE": null, "default_choice": null,
                                "choice_actions": null, "jev_deadline": "next_segment", "no_response_s": 10.0},
                     "meta": {"t": 4.0, "tag": "looking_around", "tag_since": 3.0, "screen": "menu",
                              "screen_since": 1.0, "situation_known": true},
                     "steps_left": 2, "target_id": null, "message_id": null, "session_signal": null,
                     "jev_kind": "fit", "jev": {"shadow": true, "applied": false, "answer": null}},
   "decision_situation": {"name": "looking_around",
                          "evidence": [{"event_id": "dwell_no_touch@0", "obs": "no_touch_s", "value": 4.0, "t": 4.0},
                                       {"event_id": "yaw_sweep_offscreen@10", "obs": "yaw_deg", "value": 55.0, "t": 1.4},
                                       {"event_id": "yaw_sweep_offscreen@10", "obs": "side", "value": "right", "t": 1.4},
                                       {"event_id": "yaw_sweep_offscreen@10", "obs": "offscreen_s", "value": 0.4, "t": 1.4},
                                       {"event_id": "yaw_sweep_offscreen@24", "obs": "yaw_deg", "value": -55.0, "t": 2.8},
                                       {"event_id": "yaw_sweep_offscreen@24", "obs": "side", "value": "left", "t": 2.8},
                                       {"event_id": "yaw_sweep_offscreen@24", "obs": "offscreen_s", "value": 0.4, "t": 2.8}],
                          "confidence": {"events": 3, "quality_ok": true}},
   "observations": {"gaze": true, "face_seen": true,
                    "scene_tags": [{"name": "seated_height", "status": "unknown", "unknown_reason": "no_value_for_camera",
                                    "evidence": []},
                                   {"name": "face_approach", "status": "unknown", "unknown_reason": "no_value", "evidence": []},
                                   {"name": "user_changed", "status": false, "unknown_reason": null, "evidence": []},
                                   {"name": "none_seen", "status": false, "unknown_reason": null, "evidence": []},
                                   {"name": "aid_use", "status": "unknown", "unknown_reason": "column:aid_owner",
                                    "evidence": []},
                                   {"name": "phone_use", "status": "unknown", "unknown_reason": "column:phone_owner",
                                    "evidence": []}]}}}
```

- `extension.detectors`는 창 기록의 `detectors`를 그대로 옮긴 것입니다.
- `extension.situation`은 창 기록의 `situation`에서 근거 사건의 관찰 값(`evidence`)과 창 구간(`window_s`)을 빼고 `name`을 `tag`로 옮긴 것입니다. 장면 태그(`tags`)는 근거 사건 ID만 남깁니다. 재생 도구가 이 키를 읽으므로 이름을 바꾸지 않습니다.
- `extension.decision_meta`는 창 기록의 `decision`에서 `support`로 옮긴 `preset` · `requires_confirmation`과 Jev 질문(`jev_request`) · 단서(`cues`) · 사유(`reason`)를 빼고, Jev 종류(`jev_kind`)와 그림자 모드 표시(`jev`; Jev 질문이 없는 창은 `null`)를 더한 것입니다.
- `extension.decision_situation`(2026-11-22 추가)은 backend 판단 층(`backend/app/modules/decision/`)이 `WindowInput.situation`에서 읽는 키 이름으로 옮긴 상황입니다. `rule_table.py`의 `situation_known`이 `name`을, `evidence_counts`가 `evidence`의 항목마다 `event_id`를, `jev_state`가 `confidence`의 `quality_ok`를 읽습니다. `evidence`는 창 기록의 `situation.evidence`(근거 사건마다의 관찰 값)를 그대로 옮깁니다. `extension.situation`의 `tag` · `evidence_ids`는 판단 층이 읽지 못해 상황이 없는 창으로 처리됩니다(테스트 `BackendReadsTheViewTests`가 이 저장소의 판단 층 코드로 두 형태를 비교함).
- `extension.observations`(2026-11-22 추가, 선택 블록)는 판단 층이 상황 말고 더 읽을 관측과 장면 태그를 담습니다. `gaze`는 창 기록의 `vision.facing_screen`과 같고 판단 층의 `WindowInput.gaze` 자리에 들어갑니다. `face_seen`은 구간에서 얼굴이 한 번이라도 보였는지이며, 팀 자리표시자(`app/inference/placeholder.py`)가 `vision.face_detected`로 `measurable`을 정할 때 쓰는 근거와 같은 뜻입니다. `scene_tags`는 장면 태그 6개(이름 · 상태 · 모름 이유 · 근거 관찰 값)이고, 태그 3개와 경쟁하지 않습니다. 이 엔진의 로컬 규칙표 v0는 이 가운데 `phone_use`만 읽습니다(3-2 기다림의 휴대폰 길). backend 판단 층의 규칙표는 아직 장면 태그를 하나도 읽지 않습니다(위 '주문 화면 · backend와 잇는 두 연결'의 '아직 남은 것'). 값 묶음이 없으면 `[]`입니다.
- 실시간 실행기는 두 키를 상황 태그 본문의 `situation` · `observations`로 backend에 보냅니다(위 '주문 화면 · backend와 잇는 두 연결', `contract/ai-backend.openapi.json`).

관측 요약: 위 `contract`에는 관측값이 없습니다. 관측값은 창마다 창 기록의 `vision` 칸에 담깁니다(`chain.vision_summary`, 위 '창 한 줄'). 상황 태그 본문에는 이 8개 가운데 고개 방향(`gaze`)과 얼굴을 봤는지(`face_seen`)만 실립니다(위 '주문 화면 · backend와 잇는 두 연결').

- `vision`의 값 8개는 `frames`(구간의 프레임 수) · `face_seen_ratio` · `body_seen_ratio`(얼굴 · 몸을 본 프레임 비율) · `head_count_max`(머리 상자 수의 최댓값) · `people_behind_max`(뒤에 선 사람 수의 최댓값) · `companion_frames`(동행자 상자가 있는 프레임 수) · `mouth_motion_max`(입 움직임의 최댓값) · `facing_screen`(위 '창 한 줄')입니다. 값은 구간 (t − `segment_s`, t]의 요약입니다. `frames`와 `companion_frames`는 개수라 늘 숫자입니다. 얼굴 · 몸 비율은 프레임이 없으면 `null`입니다. 프레임이 있으면 상태 열(`face_state` · `body_state`)이 '보임'인 프레임 수를 구간의 프레임 수로 나누므로, 상태 값이 없는 프레임은 못 본 프레임으로 셉니다(상태 값이 모두 없으면 0). 최댓값 3개(`head_count_max` · `people_behind_max` · `mouth_motion_max`)는 구간에 유한한 값이 없으면(프레임이 없거나, 그 열이 없거나, 모두 빈칸) `null`이고, `facing_screen`은 위 '창 한 줄'의 규칙을 따릅니다. `companion_frames`는 머리 탐지기가 없거나 동행자인지 모를 때(경계값이 없는 기본 상태)도 0이라 '동행자 없음'과 구분되지 않습니다.
- 계약의 `VisionFeatures` 4칸(`face_detected` · `face_size_ratio` · `assistive_device` · `confidence`)은 그대로 둡니다. 이 모듈의 창 결과는 그 4칸을 채우지 않습니다.
- 처음 제안(관측값 14개 + `situations[]`, 2026-10-10)은 프레임 한 장의 값을 보내는 안이었습니다. 현재 재생 파일에서는 관측값을 창 요약으로 남기고, 상황 태그와 로컬 규칙표 결과를 `extension`에 담습니다. 프레임마다의 값은 재생의 `rows.csv`에 남습니다. P1의 `head_dir_*`는 관측만 하는 열이라 관측 요약 8개에 넣지 않았습니다.
- 비전 값의 전달 경로와 형식을 합의한 뒤, 필요한 명세 변경은 이 README와 따로 목적 하나만 담은 PR로 올립니다(AGENTS.md 1장). `contract/`는 공용 영역이라 새 칸 추가도 PR 리뷰를 거치고, 그 형식을 쓰는 코드와 샘플을 같은 때 맞추거나 맞출 일정을 그 PR 본문에 적습니다(AGENTS.md 2장).

### [파일럿] 값과 출처 (`params.py`)

실행 파이프라인이 새로 쓰는 값입니다. 모두 기본값이 있고(동행자 · 뒤 사람 경계 3개의 기본값은 '값 없음'), 값마다 출처 문장이 코드(`PilotParams` 필드의 `source`)와 `meta.json`에 함께 있습니다. `[파일럿]` 값은 키오스크 시점의 측정 자료 없이 둔 시작값이고, 출처나 공개 데이터로 바꾸거나 값 묶음 여러 개로 결과를 나란히 보입니다. 장면 태그 경계값은 카메라마다 서서 쓰는 영상으로 보정합니다(아래 '장면 태그 6개').

| 값 | 기본값 | 단위 | 출처 |
|---|---|---|---|
| `head_score_min` | 0.65 | 점수 0~1 | 데이터: H1의 Open Images 검증 전부(입력 416)에서 F1이 가장 큰 점수 기준(정밀도 0.682 · 재현율 0.676). 키오스크 시점 값 아님 |
| `head_nms_iou` | 0.65 | IoU 0~1 | 관행값: YOLOX `yolox_base.py`의 `nmsthre` 기본값(H1 평가 설정과 같음) |
| `primary_rule` | `face_then_largest` | — | `[파일럿]` 규칙(위 '선택 열') |
| `mouth_dials` | jaw · mouth로 시작하는 27개 | — | Apple ARKit `ARFaceAnchor.BlendShapeLocation`의 'Mouth and Jaw' 묶음, 아래 상황 태그 규칙표의 '입 다이얼' |
| `mouth_baseline_s` | 2.0 | 초 | `[파일럿]` 시작값(입 움직임은 사람별 기준선을 뺀 변화로 봄) |
| `track_iou_min` | 0.3 | IoU 0~1 | 관행값: SORT 공개 구현(`abewley/sort`의 `sort.py`)의 `iou_threshold` 기본값. 논문(Bewley 외, ICIP 2016) §3.3은 최소 IoU를 두지만 값은 적지 않음. 이 모듈은 칼만 예측 없이 직전 상자와 견주고, 헝가리안 대신 IoU 큰 순으로 배정 |
| `track_max_gap_s` | 1.0 | 초 | `[파일럿]` 시작값: `segment_s`와 같은 값. 이만큼 넘게 상자가 없는 트랙은 끝남 |
| `role_window_s` | 2.0 | 초 | `[파일럿]` 시작값: `mouth_baseline_s`와 같은 값(같은 사람의 직전 구간 중앙값) |
| `companion_rel_dist_max` | 없음 | 상대 거리 | 정할 수 없음: 아래 상황 태그 규칙표의 '비슷한 크기'. 값 묶음별 곡선으로 보고(촬영본은 평가에만 씀) |
| `companion_lateral_min` | 없음 | 주 사용자 머리 높이 | 정할 수 없음: 같은 규칙표의 '옆'. 값 묶음별 곡선으로 보고 |
| `behind_rel_dist_min` | 없음 | 상대 거리 | 정할 수 없음: 같은 규칙표의 '뒤쪽'. 값 묶음별 곡선으로 보고. '주 사용자보다 작은 상자'(상대 거리 > 1)는 값과 상관없이 늘 봄 |
| `seated_face_cy_min` | 없음 | `face_cy`(위 0 · 아래 1) | 정할 수 없음: 카메라 높이 · 기울기마다 다름. 정하는 방법은 아래 '장면 태그 6개'. 값 묶음별로 보고 |
| `head_approach_ratio_min` | 없음 | 머리 상자 높이 ÷ 기준 머리 상자 높이 | 정할 수 없음: 카메라마다 다름. 머리 탐지기를 켠 서서 쓰는 녹화의 창 중앙값 `head_ratio_user`로 평균 + 2 SD. 값 묶음별로 보고 |
| `seated_head_cy_min` | 없음 | 머리 상자 세로 가운데(위 0 · 아래 1) | 정할 수 없음: 카메라마다 다름. 앉은 높이와 같은 방법으로 머리 탐지기를 켠 서서 쓰는 녹화에서 정함. 값 묶음별로 보고 |
| `head_down_pitch_min` | 없음 | 도(+ = 아래) | 정할 수 없음: 카메라마다 다름. 서서 조작하는 녹화의 창 중앙값 `dpitch_user_deg`로 평균 + 2 SD. 값 묶음별로 보고 |
| `stitch_shift_max` | 없음 | 앞 상자 폭 · 높이 | 정할 수 없음: 카메라마다 다름. 서서 쓰는 녹화에서 같은 주 사용자 트랙의 머리 상자가 `track_max_gap_s` 안에 움직인 위치 차(R-CNN 상자 변화량 tx · ty의 유클리드 거리)로 평균 + 2 SD. 값 묶음별로 보고 |
| `stitch_size_max` | 없음 | \|ln(높이 비)\| | 정할 수 없음: 같은 상자 짝의 크기 차(R-CNN 상자 변화량 th의 절댓값)로 평균 + 2 SD. 값 묶음별로 보고 |
| `approach_ratio_min` | 없음 | `iod_px` ÷ 기준 `iod_px` | 정할 수 없음: 정하는 방법은 아래 '장면 태그 6개'. 값 묶음별로 보고 |
| `aid_score_min` | 0.01 | 점수 0~1 | 관행값: 보조기구 탐지기 평가 설정의 점수 하한(YOLOX 평가 conf 0.01). 상자를 기록하는 하한이고 쓴다 · 안 쓴다를 가르는 값이 아님 |
| `aid_nms_iou` | 0.65 | IoU 0~1 | 관행값: YOLOX `nmsthre` 기본값(탐지기 평가와 같은 IoU). 사람 하나에 상자 하나를 남기려고 클래스를 가리지 않고 적용(`head_centre` 읽기에서는 클래스마다 그 클래스 안에서 적용: 평가의 클래스별 NMS와 같은 방식) |
| `aid_person_min` | 0.390 | 점수 0~1 | `[파일럿]` 시작값, 공개 자료에서 잰 값: 같은 검증 분할의 '사람 아무나' 과제에서 F1이 가장 큰 점수 기준(F1 0.813). 이 값을 넘는 사람 상자만 사람이 보인 것(`none_seen`)과 주 사용자 상자로 셈 |
| `aid_use_min` | 0.350 | 점수 0~1 | `[파일럿]` 시작값, 공개 자료에서 잰 값: TU Graz Mobility Aid Users v1.0 검증 분할에서 F1이 가장 큰 점수 기준(목발 · 지팡이 · 보행기 · 휠체어 점수의 최댓값, 모델 aid_det joint_416, 입력 416). 시험 분할에 그대로 적용하면 정밀도 0.698 · 재현율 0.736. 주의할 점은 아래 '보조기구 입력' |
| `aid_rule` | `owner_box` | — | 규칙 스위치: 보조기구 탐지기를 읽는 방법. `owner_box` = 주 사용자의 사람 상자와 그 `aid_any_score`, `head_centre` = 주 사용자 머리 상자 가운데를 품은 보조기구 클래스 상자의 점수 `aid_head_score`(키오스크 시점 탐지기 파일용), `head_centre_carry` = `head_centre`에 더해 머리 상자가 없는 프레임은 그 상자를 머리 트랙 규칙(`track_iou_min` · `track_max_gap_s`)으로 따라가 읽음(아래 '보조기구 입력'의 '세 읽기'). 값 묶음의 `chain` 칸이나 실행 옵션 `--aid-rule`로 바꿈 |
| `aid_head_min` | 없음 | 점수 0~1 | 정할 수 없음: `head_centre` · `head_centre_carry` 읽기의 `aid_use` 컷(창 안 `aid_head_score` 중앙값이 이 값을 넘으면 참). 키오스크 시점 탐지기 파일의 값은 아직 정하지 않음. 값이 없으면 `aid_use`는 모름(`no_value_for_model`). 값 묶음이나 실행 옵션 `--aid-head-min`으로 줌 |
| `phone_score_min` | 0.3 | 점수 0~1 | 관행값: YOLOX ONNX Runtime 데모(`demo/ONNXRuntime/onnx_inference.py`)의 `--score_thr` 기본값(이 점수 이상인 상자만 그림). 키오스크 시점 값 아님 |
| `phone_nms_iou` | 0.45 | IoU 0~1 | 관행값: 같은 데모의 `multiclass_nms(nms_thr=0.45)`(클래스를 가리지 않는 판) |
| `hand_vis_min` | 없음 | visibility 0~1 | 정할 수 없음: 휴대폰 손 길에서 손 점을 손 상자에 넣는 visibility 하한. 값이 없으면 손 상자를 만들지 않아 손 길은 판정하지 않음(머리 길은 그대로, 아래 '휴대폰 입력') |
| `segment_s` | 1.0 | 초 | 계약 `sendFeatureWindow`의 '1~3초 구간' 안에서 고른 `[파일럿]` 값 |
| `touch_span_s` | 5.0 | 초 | `[파일럿]` 시작값: 4-1(빗나감 뒤 바로 고침) · 4-2(되돌아감)의 터치 단서를 세는 최근 구간 |
| `tremor_miss_min` | 2 | 번 | `[파일럿]` 읽기: tree 표 3-가 4-1 '빗나감 · 바로 고침 반복'의 '반복'을 2번 이상으로 읽음(버튼 밖 누름 뒤 그 옆 버튼을 바로 누른 횟수) |
| `tremor_miss_min_no_gaze` | 3 | 번 | `[파일럿]`: 고개 방향을 못 재는 창의 올린 기준(JP §0-2) = 한 번 더 |
| `lost_back_min` | 1 | 번 | 정의: tree 표 3-가 4-2 '되돌아감'이 있음 |
| `lost_pause_s` | 8.0 | 초 | `[파일럿]` 시작값: 4-2 '고른 뒤 멈춤' |
| `lost_pause_s_vision` | 4.0 | 초 | `[파일럿]` 시작값: 두리번 · 화면을 보는 고개가 있을 때 낮춘 기준(조정량은 기준 없음, JP §0-2) |
| `no_response_s` | 10.0 | 초 | `[파일럿]` 시작값: 무응답 시간(JP §0-6) |
| `delay_notice_on` | 거짓 | — | 평가 조건표 스위치(격려 메시지 있음 · 없음 비교, JP §0-2) |
| `defer_option_on` | 참 | — | 평가 조건표 스위치(JP §0-2) |

## 처리 시간 (개발 노트북)

### 관측 뼈대 (저장소 밖 시제품)

같은 MediaPipe 3종과 0.10.33으로 만든 저장소 밖 시제품에서 잰 한 프레임 처리 시간입니다(같은 입력에서 이 저장소 코드와 관측값이 같았음). 조건: Intel Core i5-1340P 노트북, 성능 코어 고정 · 높은 우선순위, Windows 11, Python 3.12.10, CPU만, 세 모델을 매 프레임 모두 실행, 프레임 640×480(합성 입력) · 640×360(공개 영상), 첫 프레임 제외(2026-10-08 측정).

- p50은 처리 시간의 중앙값이고 p95는 95백분위수입니다(100번 중 95번은 그 시간 안에 끝남).
- 합계(얼굴 점 + 얼굴 검출 + 몸 점 + 밝기 · 선명도): 입력 6개에서 p50 20.7\~25.3 ms · p95 24.2\~32.6 ms(얼굴 검출 short-range). full-range 검출이면 합성 다가옴에서 p50 25.9 ms · p95 29.7 ms.
- 얼굴을 새로 찾는 프레임은 더 걸립니다(장면 전환 영상에서 중앙값 40 ms, 따라가는 프레임 26 ms). 오버레이 그리기는 따로 p50 7.0\~8.7 ms입니다.
- 위 값은 개발 노트북(i5-1340P)에서 잰 값이고, 키오스크 PC의 처리 시간으로 쓰지 않습니다.

### 실행 파이프라인 전체 (이 저장소, 2026-10-22)

`replay.py`의 프레임 한 장 처리(MediaPipe 3종 + blendshape(켠 조건; 지금은 `--blendshapes`를 줘야 같은 조건) + 관측값 + H1 머리 탐지 + P1 카메라 시점 + 선택 열)와 창 하나의 판단(상황 + 규칙표)을 같은 조건으로 3번 쟀습니다. 조건: 개발 노트북(i5-1340P), Windows 11, Python 3.12.10, mediapipe 0.10.33, onnxruntime 1.30.0, 프로세스를 논리 CPU 1개(CPU 2)에 고정 · 보통 우선순위, ONNX Runtime 스레드 1, OpenCV 스레드 1, 첫 프레임 제외. 입력: 시제품 `samples/was_ist_ein_vlog_360p.mov`(웹캠 앞 한 사람, CC BY-SA 3.0)의 앞 30초를 `--step 2 --width 640`(640×360, 초당 12.5장, 376장)으로 돌렸고, 얼굴은 371장에서 보였습니다. 결과 파일은 숫자만 보고 지웠습니다.

| 단계 | p50 (ms) | p95 (ms) |
|---|---|---|
| MediaPipe 3종 + 관측값 계산(`ms_total`) | 21.4~24.9 | 23.7~29.1 |
| H1 머리 탐지: 전처리 · 추론 · 후처리(`ms_heads`) | 16.1~19.0 | 18.4~21.8 |
| P1 카메라 시점, 주 사용자 1명(`ms_head_dir`) | 4.0~4.6 | 4.7~5.5 |
| 프레임 한 장 전체, 벽시계(`ms_chain`) | 42.1~49.0 | 50.7~58.8 |
| 창 하나의 판단, 1초에 한 번(`ms_window`; 시험용 값 묶음, 창 6초) | 0.62~0.74 | 0.68~0.80 |

- 범위는 3번의 최솟값~최댓값입니다. 프로세스 CPU 시간(모든 스레드, 영상 디코딩 · 창 판단 포함)은 프레임당 43.3 · 49.8 ms였습니다(2번 잼).
- 프레임 처리 중앙값의 역수는 초당 20~24장입니다(1000 ÷ 49~42 ms). 카메라 캡처 · 디코딩 · 창 판단까지 합친 지속 처리량은 따로 재지 않았습니다. 팀의 설계 목표(초당 10~15장)를 이 노트북에서는 CPU 1개로 넘지만, 키오스크 PC(시험 기기)의 값은 아닙니다.
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

기준값은 코드에 기본값으로 두지 않습니다. 창 길이 · 횟수 · 각도 · 품질 하한 13개는 모두 `PilotParams`의 필드이고 기본값이 없어서, 부르는 쪽이 값을 모두 넣어야 합니다. 값은 출처와 공개 데이터로 정하고, 출처가 없는 값은 값 묶음마다 결과를 보입니다(`[파일럿]`). 실행기는 이 13개를 값 묶음 파일(`--params`)에서만 읽습니다. 필드마다 무엇을 정하는지는 `events.py`의 `PilotParams` 주석에 적었습니다. 횟수 3개는 1 이상만 받습니다. 0을 넣으면 아래 상황 태그 규칙표가 요구하는 관찰 없이도 규칙이 맞기 때문입니다. 비율(0~1)과 비교하는 하한 3개(`shoulder_vis_min` · `face_visible_min` · `track_conf_min`)는 1 이하만 받고, 창 길이와 끊김 간격(`window_s` · `gap_s`)은 0보다 커야 합니다. 백분율로 잘못 넣은 값이나 0초 창은 모든 창을 `unknown`으로 만들거나 사건을 프레임 하나씩 쪼개므로 바로 막습니다. `situation.py`에는 숫자가 없고, 테스트가 이를 확인합니다.

```python
from app.modules.vision.events import PilotParams
from app.modules.vision.situation import assess

params = PilotParams(window_s=..., gap_s=..., ...)                 # 13개 모두 [파일럿], 기본값 없음
out, events = assess(rows, t_end, params, landmarker_num_faces=1)  # 창 = [t_end - window_s, t_end]
```

`rows`는 관측값 줄(`observations.csv`의 한 줄 = dict 하나)에 아래 '선택 열'을 더한 목록입니다. `landmarker_num_faces`는 그 줄을 만든 Face Landmarker의 `num_faces` 설정입니다(이 모듈은 1).

### 기준: 저장소 밖 두 문서의 원문

규칙의 기준은 아래 두 원문입니다. 원문에 없이 더한 것은 그다음 '추가 제안'에 따로 적었습니다. 인용 안의 (…)는 줄인 곳이고, 저장소 밖 문서의 항목 번호와 출처 번호는 빼거나 [ ] 안의 말로 바꿨습니다.

**비전 담당이 정한 상황 태그 3개의 규칙표(2026-10-10)**

> 출력 한 줄 = { name(행동 이름) · display_text('…해 보임') · window_s · evidence[](관찰 이름 + 값) · source }. 모든 창 길이 · 횟수 · 각도는 `[파일럿]` — 기준 없음 / 정할 수 없음이라 팀원 자가 녹화의 분포에서 정하고 그 전에는 숫자를 넣지 않습니다. (…)

| 태그(name) | 표시 문구 | 묶는 관찰(사실) — 전부 같은 창 안 | 빼는 조건 | 근거 수준 |
|---|---|---|---|---|
| `looking_back_with_people_behind` | 뒤에 사람이 있어 서두르는 듯함 | 뒤에 기다리는 사람(주 사용자보다 작은 상자, 뒤쪽, 멈춰 선 사람만) + 뒤돌아봄(yaw 커짐 → 얼굴 점 사라짐 · 어깨 점 남음 → 복귀) 반복 (+ 터치 빨라짐 · 빗나감, + 표정 변동은 보조) | 지나가는 사람만 있을 때 · 뒤돌아봄 없이 뒷사람만 있을 때(붐빔 자체는 근거 아님) | 문헌 + 71827 일부(뒷사람 높이 비) · 뒤돌아봄은 측정 전 |
| `consulting_companion` | 일행과 상의하는 듯함 | 동행자 있음(비슷한 크기의 두 번째 상자 · 옆) + 주 사용자 yaw가 일행 쪽 + 입 움직임(jawOpen 등 입 다이얼의 흔들림, blendshape 켜야 함) + 안 누르고 머묾, 몸 점 제자리 | 얼굴 2개면 smoothing 꺼짐 — 흔들림을 입 움직임으로 세지 않도록 | 71827 동행 라벨(2명+ 클립 10.7 %) + [문헌] · 말함은 측정 전 |
| `looking_around` | 무언가를 찾는 듯함 | 화면 밖으로 크게 오가는 yaw 왕복(창 안 횟수) + 몸 점 제자리 + 터치 없음 + 뒤에 사람 없음 | 메뉴 읽기(화면 안 훑기)의 작은 yaw — 범위는 파일럿 | 문헌 · 71827 없음 |

> - 고개를 크게 돌린 구간은 각도 대신 '얼굴 사라짐 + 몸 남음'으로 셉니다(…). (…)
> - 세 태그는 혼자 지원을 열지 않습니다 — 판단 층이 후보(…)를 고릅니다.

근거 수준 칸의 71827은 과학기술정보통신부의 재원으로 한국지능정보사회진흥원의 지원을 받아 구축된 「사람 행동 인식 로봇 자율 행동 데이터」(AI 허브, aihub.or.kr)이고, 그 칸의 비율 · 높이 비는 이 데이터의 라벨을 분석한 결과입니다.

**의미 층 설계 노트 v1.1(2026-10-11)의 상태 층 출력 계약과 검사 규칙**

> - 한 줄: `{ name, display_text, window_s, evidence[]: [{event_id, obs, value, t}], quality: {face_visible_ratio, track_conf}, confidence | "unknown", alternatives[], source }` (…). [위 규칙표]의 출력 줄에 quality · confidence · alternatives와 사건 ID를 더한 것이다.
> - 검사 규칙 1(근거 연결): 각 상태 해석은 근거 사건 ID에 연결된다. 프로그램은 ID의 존재와 시간 범위(창 안)를 검사한다. (…)
> - 검사 규칙 2(모름): 사건이 k개 미만이면 `confidence = "unknown"`이다. 품질은 단서별로 적용한다: 얼굴 소실이 유효 단서인 뒤돌아봄은 얼굴 보임 비율이 낮아도 보류하지 않고, 얼굴이 필요한 단서(입 움직임 · 표정)만 결측으로 처리한다. 센서 실패(추적 신뢰도 하한 미만, 카메라 없음)와 "얼굴이 돌아가서 안 보임"은 구분한다. 상태가 '모름'이면 판단 층은 Jev를 부르지 않고 터치 규칙만 쓴다. k · 하한은 `[파일럿]`.
> - 근거 중복: 같은 원인에서 난 관찰(한 번의 고개 돌림에서 나온 yaw 변화와 얼굴 소실)은 한 사건으로 묶어 센다.
> - 상태 수명: 시작 조건(사건 k개 충족), 유지(창 안에 새 사건), 해제(반대 근거 사건 또는 만료 창 경과), 만료 창 길이는 `[파일럿]`.
> - 복수 상태: 동시에 충족하면 지지 사건 수가 많은 것을 `name`으로, 나머지를 `alternatives[]`로 낸다. 판단 층은 대안이 있으면 보류를 고를 수 있다.
> - 동점 `[설계 제안]`(구현 2026-10-11 밤): 지지 사건 수가 같으면 `name = "unknown"`으로 내고 두 태그를 모두 `alternatives[]`에 둔다. 판단 층은 이때 터치 규칙만 쓴다. 대안에도 같은 최소 사건 수 k를 적용한다.
> - confidence: 라벨로 보정하기 전에는 확률처럼 쓰지 않고 "충족한 사건 수 / 품질"의 규칙 충족 정보로만 표시한다.

위 인용 가운데 판단 층의 동작(모름 · 동점일 때 터치 규칙만 씀, 대안이 있으면 보류를 고름)은 비전 설계 노트의 제안입니다. 모름 · 동점일 때 터치 행만 보는 동작은 규칙표 v0에 있고(위 '기존 재생용 규칙표 v0'), backend 판단 단계는 이 규칙표를 행 그대로 옮겨 실행합니다(`docs/Jev-Integration.md` 10장). 다만 3-2 휴대폰 길(`phone_use`)과 측정할 수 없는 창에서 그 길만 통과시키는 예외는 backend 사본에 아직 없습니다(통합 작업). 계약에 들어갈 형식은 추가형 제안으로 팀 합의에서 정합니다.

### 추가 제안 (`[설계 제안]`, 위 두 원문에 없음)

- 본 근거 먼저, 세 값 논리: 창 안에서 본 근거(터치, 뒤에 선 사람, 입 움직임, 일행 쪽 yaw, 몸 움직임)는 그 열이 일부 줄에서 빠져도 씁니다. 어떤 단서가 '없다'는 결론은 필요한 관측이 빠짐없이 있을 때만 내고, 아니면 그 단서는 '모름'(None)입니다. 모름은 다른 단서가 그 태그를 빼지 않을 때만 결과를 모름으로 만듭니다. 그래서 `none`은 모든 태그가 관측된 단서로 빠졌을 때만 나옵니다.
- '없음'에 필요한 관측: 터치 · 뒷사람은 창의 모든 줄에 그 열이 있어야 합니다. 입 움직임은 얼굴 프레임마다 값이 있어야 합니다. 고개 돌림은 얼굴 프레임마다 yaw가, 얼굴이 사라진 프레임마다 어깨 값이 있어야 하고, 얼굴과 몸이 함께 끊기거나 기록이 비어 결말을 못 본 돌림이 창 안에 없어야 합니다. 일행 쪽 yaw는 yaw가 0이 아닌 얼굴 프레임마다 동행자 쪽을 알아야 합니다. 몸은 가로 · 세로 축마다 보고, 한 축이라도 `body_still_max`를 넘으면 움직임입니다. '제자리'는 몸 프레임마다 두 축 값이 다 있어야 냅니다.
- 터치 열 이름: `tap_count` · `miss_tap_count`는 명세 `TouchFeatures`의 이름과 뜻을 따르고, 세는 구간만 창 대신 직전 줄 이후입니다. 값은 명세대로 0 이상의 정수만 받습니다(CSV의 정수 문자열 포함, `1.0` 같은 실수 표기는 오류). API의 `TouchFeatures`는 1~3초 구간의 집계라 프레임 간격 집계와 경계가 다르므로, 서버로 넘길 때의 집계 경계는 계약에서 정합니다.
- 터치 횟수와 창 시작: 한 줄의 횟수는 그 줄 시각에서 끝나는 구간(직전 줄 이후)의 것으로 보고, 줄 시각이 창 안이면 그 줄을 창에 넣습니다. 그래서 창 시작 직전의 한 샘플 간격 안에서 난 터치가 창 안의 터치로 셀 수 있습니다. 원시 터치 시각을 받으면 이 한계가 없어집니다.
- 일행 쪽 yaw와 메뉴 읽기: 위 상황 태그 규칙표대로 yaw의 부호가 그 프레임의 동행자 쪽이면 각도와 상관없이 일행 쪽 yaw로 셉니다(`gap_s` 안에서 이어지면 한 구간). 그래서 동행자 옆에서 메뉴를 읽는 작은 yaw도 일행 쪽 yaw로 셀 수 있습니다. 각도 하한을 둘지는 2026-10-14 팀 촬영의 혼동 장면(S2의 '말없이 기다리는 일행')을 보고 정합니다.
- 동행자의 쪽: 그 프레임의 동행자 상자와 사용자 얼굴 위치를 견줍니다. 둘 중 하나가 없는 프레임은 `gap_s` 안에서 가장 가까운 프레임의 값을 쓰고, 그보다 오래된 위치는 쓰지 않습니다. 동행자가 근처에 있을 수 있는데(`gap_s` 안에 상자가 있거나 그 열이 빠짐) 쪽을 모르는 프레임은 '모름'으로 둡니다.
- 창 경계: 사건의 관찰 줄이 전부 창 안에 있어야 근거가 됩니다(위 상황 태그 규칙표의 '전부 같은 창 안', 설계 노트 검사 규칙 1의 '시간 범위(창 안)'). 고개 돌림은 창 끝까지의 기록에서 찾되, 창 앞의 기록은 문맥으로만 씁니다. 예를 들어 창 바로 앞의 정면 프레임에서 시작한 고개 돌림도 찾지만, 돌림의 줄이 전부 창 안일 때만 셉니다. 뒷사람 · 동행자 · 일행 쪽 yaw · 입 움직임 · 머묾 · 빗나간 터치는 창 안의 줄에서만 찾습니다. 그래서 창 앞부터 이어지는 상태는 창 안 부분이 근거가 되고, 길이 조건(`stay_min_s` · `dwell_min_s`)도 창 안 부분으로 판단합니다. 사건의 끝 시각이 창 안인 것을 고르는 안과 창과 겹치는 사건을 고르는 안은 쓰지 않았습니다. 둘 다 창 밖의 관찰이 근거에 섞이기 때문입니다.
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
| `look_back` 뒤돌아봄 | 화면을 보던 얼굴이 돌아가는 동안 얼굴 점이 사라지고 어깨 점이 남고(`shoulder_vis_min`), 다시 화면 쪽으로 돌아옴. 시작은 두 길: 얼굴이 `offscreen_yaw_deg`를 넘어 돌아감, 또는 화면을 보던 얼굴의 점이 어깨 점을 남긴 채 바로 사라짐(크게 돌린 고개는 yaw가 커지기 전에 얼굴 점이 사라지기 때문). 두 번째 길에서 화면 밖 yaw가 한 번도 보이지 않은 돌림은 얼굴이 `gap_s`보다 오래 사라졌을 때만 셈(더 짧은 사라짐은 `gap_s`가 잇는 잠깐 끊김). 그 사건은 `yaw_deg` · `side`가 비어 있음. 뒤돌아봄마다 맥락 값 넷을 함께 적음(돌아봄과 고개 숙임 · 가림을 나중에 가르는 데 쓰는 관측, 기준값 없음): `pre_loss_yaw_deg` · `pre_loss_pitch_deg`(돌림 시작 전 `mouth_baseline_s`초 동안 화면을 본 프레임의 yaw · pitch 중앙값), `loss_duration_s`(첫 사라짐 프레임부터 마지막 사라짐 프레임까지), `shoulder_vis_mean`(사라진 프레임의 어깨 보임 평균) yaw 변화 · 얼굴 사라짐 · 어깨 남음을 따로 세지 않고 사건 하나로 셈 | 1 · 3 |
| `yaw_sweep_offscreen` 화면 밖 고개 돌림 | 같은 돌림인데 얼굴이 끝까지 보임. 돌아간 쪽(왼쪽 · 오른쪽)을 함께 적음 | 3 |
| `people_behind` 뒤에 선 사람 | `people_behind_count`가 1 이상인 구간이 `stay_min_s` 이상 이어짐. 더 짧으면 지나가는 사람으로 보고 세지 않음 | 1 · 3(빼는 조건) |
| `companion_present` 동행자 | `companion_box`가 있는 구간(머문 시간 조건 없음) | 2 |
| `yaw_toward_companion` 일행 쪽 yaw | 얼굴이 보이고, yaw의 부호가 그 프레임 동행자 쪽인 구간(각도 하한 없음). 동행자 쪽은 그 프레임의 상자와 얼굴 위치로 정함. 화면 쪽으로 돌아오지 않아도 됨 | 2 |
| `mouth_moving` 입 움직임 | 얼굴이 보이는 프레임에서 `mouth_motion`이 `mouth_motion_min` 이상. Face Landmarker의 `num_faces`가 1이 아니면 smoothing이 꺼지므로 찾지 않음 | 2 |
| `dwell_no_touch` 안 누르고 머묾 | 사람이 보이고 터치 없이 `dwell_min_s` 이상 지남. 터치가 들어오면 끊김 | 2 · 3(보조 근거) |
| `touch_miss` 빗나간 터치 | `miss_tap_count`가 0보다 큼 | 1(보조 근거) |

동행자 쪽으로 화면 밖까지 고개를 돌렸다가 돌아오면, 같은 프레임에서 `yaw_sweep_offscreen`(두리번거림의 단서)과 `yaw_toward_companion`(상의의 단서)이 함께 생깁니다. 한 규칙 안에서는 한 번만 셉니다.

`gap_s`는 한 사건으로 이어 볼 두 관측 사이의 가장 긴 시간입니다(잠깐 끊김을 거르는 시간 창). 이웃한 줄도 시각 차이로 판단하므로 평소 프레임 간격보다 커야 하고, 이보다 긴 공백(끊김이나 빠진 기록)이 있으면 사건이 끊깁니다.

### 장면 태그 6개 (2026-11-22)

상황 출력에 `tags` 목록을 더했습니다. 위 세 태그는 창마다 하나(`name`)를 고르지만, 장면 태그는 서로 겨루지 않고 태그마다 따로 참 · 거짓 · `unknown`을 냅니다. 앉은 사용자도 뒤에 줄이 있으면 뒤돌아볼 수 있어서 한 이름으로 묶지 않았습니다. `name` · 대안 · 근거는 장면 태그가 있든 없든 같습니다(테스트로 확인). 이 PR의 규칙표 v0는 장면 태그 가운데 `phone_use`만 읽고(3-2 기다림), 나머지 장면 태그를 지원으로 잇는 판단 행은 아직 구현하지 않았으며 제안(팀 검토 전)입니다(아래 '연결과 이어지는 일'). 장면 키는 `judgment/rule_table_v0.py`의 `SCENE_OF_TAG`에 있습니다.

| 태그(표시 문구) | 장면 | 읽는 열 · 사건 | 참 | 모름(`unknown_reason`) |
|---|---|---|---|---|
| `seated_height`(앉은 높이) | 1-2 `wheelchair` | 주 사용자 얼굴의 `face_cy`(사건 `face_height`), 얼굴로 판정하지 못하는 창은 주 사용자 머리 상자의 세로 가운데(사건 `head_height`) | 창 안 `face_cy` 중앙값 > `seated_face_cy_min`. 얼굴로 판정하지 못하는 창(얼굴이 안 보이거나 줄이 적음)은 머리 탐지기와 `seated_head_cy_min`이 있으면 머리 상자 세로 가운데의 중앙값 > `seated_head_cy_min`. `iod_ratio_user` > `approach_ratio_min`인 줄은 뺌(화면에 얼굴을 대면 얼굴도 아래로 내려감). 머리 상자 판정에서는 `head_ratio_user` > `head_approach_ratio_min`인 줄을 뺌 | 이 카메라의 값 없음(`no_value_for_camera`), 주 사용자 얼굴 줄 없음(`no_main_user_face`), 머리 상자 기준에서 창에 주 사용자 머리 상자가 없음(`no_main_user_box`), 얼굴 줄이 모두 접근 줄이라 뺌(`face_near`), 머리 상자 줄이 모두 다가가 커진 줄이라 뺌(`head_near`), 중앙값을 낸 줄이 창의 `face_visible_min`보다 적음(`too_few_rows`) |
| `face_approach`(얼굴 접근) | 2-1 `lowvision` | `iod_ratio_user` · `dpitch_user_deg`, 사건 `face_size` · `head_pitch` | 창 안 `iod_ratio_user` 중앙값 > `approach_ratio_min`. 다만 그 창의 `dpitch_user_deg` 중앙값이 `head_down_pitch_min`보다 크면(고개 숙임) 거짓(판정한 창으로 셈). 이 중앙값은 창 프레임의 `face_visible_min` 이상의 줄에서 낸 것만 씀(값을 정한 방법과 같음). 얼굴이 커지지 않은 창은 고개 숙임과 상관없이 크기로만 판정 | 값 없음(`no_value`), 주 사용자 얼굴 줄 없음(`no_main_user_face`: 얼굴을 바싹 대 얼굴을 놓친 창도 여기), 기준이 아직 없음(`no_reference`), 거짓일 때 중앙값을 낸 줄이 창의 `face_visible_min`보다 적음(`too_few_rows`) |
| `user_changed`(사용자 교체 가능성) | 2-2 `newcustomer` | `main_user_prev_track` · `main_user_gap_s` · `main_user_body_kept` · `main_user_body_gap_s` · `main_user_reacquired` · `main_user_stitched`, 사건 `main_user_changed` | 창 안 줄에서 새 주 사용자 트랙이 시작됨(같은 자리에서 다시 잡은 트랙, 제자리에서 끊겼다 이어 붙인 트랙, 앞 주 사용자가 자리 잡기 전의 트랙 바뀜은 빼고) | 같은 자리에서 다시 잡은 트랙뿐(`reacquired_same_place`; 이어 붙이기도 한 트랙은 이어 붙인 쪽을 따라 거짓), 머리 탐지기가 돌지 않음(`column:primary_track`) |
| `none_seen`(카메라에 사람이 안 보임) | 자리 비움 `absence` | `face_state` · `face_count` · `body_state` · `head_count`(보조기구 탐지기를 켜면 `aid_person_count`도), 사건 `nothing_seen` | 창의 모든 줄에 얼굴(얼굴 점 · 얼굴 검출 상자) · 몸 · 머리 상자 · 보조기구 탐지기의 사람 상자(`aid_person_min` 초과)가 없음 | 창에 줄이 없음(`no_frames`), 머리 탐지기가 돌지 않아 머리 상자가 없는지 모름(`column:head_count`) |
| `aid_use`(보조기구 사용 중) | 1-1 `aid`(휠체어면 1-2: `owner_box`는 `aid_kind`, `head_centre` · `head_centre_carry`는 근거의 `aid_class`로 나눔) | `aid_any_score` · `aid_owner`(아래 '보조기구 입력'), 사건 `aid_score`. `aid_rule`이 `head_centre` · `head_centre_carry`이면 `aid_head_score` · `aid_head_class`, 사건 `aid_head` | 창 안 주 사용자 사람 상자의 `aid_any_score` 중앙값 > `aid_use_min`. `head_centre` · `head_centre_carry`이면 창 안 `aid_head_score` 중앙값 > `aid_head_min`(근거에 그 중앙값을 낸 클래스 `aid_class`) | 탐지기를 켜지 않음(`column:aid_owner`), 값 없음(`no_value`, 값 묶음이 `null`을 줄 때), 주 사용자 기준점 없음(`no_anchor`), 기준점을 품은 상자 없음(`no_user_box`), 줄이 적음(`too_few_rows`). `head_centre`이면 열 없음(`column:aid_head_score`), 컷 없음(`no_value_for_model`), 창에 주 사용자 머리 상자 없음(`no_main_user_box`), 줄이 적음(`too_few_rows`) |
| `phone_use`(잠시 딴 일 중(휴대폰)) | 3-2 `busy`의 휴대폰 길 | `phone_owner` · `phone_at`(아래 '휴대폰 입력'), 사건 `phone_at_head` · `phone_in_hand`, 터치 횟수, 어깨 위치, 구간 끝 주 사용자 얼굴의 고개 방향(고개 방향 게이트를 주 사용자 얼굴로만 읽음)과 머리 상자 | 창의 `segment_s` 구간 가운데 `min_events`개 이상에서 휴대폰이 주 사용자 머리에 있음(머리 길: 통화), 또는 머리나 손에 있으면서 주 사용자가 화면을 보지 않음(손 길) + 창 안 터치 없음 + 몸 제자리(일행 길 `consulting_companion`과 같은 터치 · 몸 조건). 다른 장면 태그와 달리 3-2 행의 길 하나라서 터치와 고개 방향을 읽음 | 탐지기를 켜지 않음(`column:phone_owner`), 창 간격 `segment_s`를 받지 못함(`no_segments`), 판정하지 못한 구간이 많음(`phone_owner_unknown`), 손 길인데 화면을 보는지 모름(고개 방향 게이트가 모르고 머리 상자도 없음, `gaze_unknown`), 터치 횟수가 없음(`column:tap_count`), 몸 위치를 못 봄(`body_position_missing`) |

- 여섯 태그 모두 창에 줄이 없으면 모름(`no_frames`)입니다.
- 창 안에서 사용자가 바뀌면(`user_changed`가 교체로 세는 트랙 바뀜, `events.user_since`) 주 사용자를 재는 값은 새 사용자의 첫 줄부터만 읽습니다. 장면 태그에서는 얼굴 높이 · 얼굴 크기 · 고개 숙임(`face_height` · `face_size` · `head_pitch`), 머리 상자의 세로 가운데와 크기(`head_height` · `head_size`), 보조기구 점수(`aid_score`), 휴대폰 구간, 손 길의 화면을 보지 않음(바뀐 줄이 마지막 구간 안에 있으면 그 구간의 새 사용자 줄)이 여기에 듭니다. 상황 태그 3개에서는 고개 돌림(`look_back` · `yaw_sweep_offscreen`; 바뀐 줄이 창의 첫 줄이어도 그 앞의 맥락 줄은 읽지 않음), 일행 쪽 고개(`yaw_toward_companion`, 일행 쪽을 모르는지도), 입 움직임(`mouth_moving`), 머묾(`dwell_no_touch`), 얼굴이 보인 비율과 몸 추적 비율(`face_visible_ratio` · `track_conf`), 몸 제자리(`body_still`, `phone_use`의 몸 조건도 같음), 고개 방향 · 어깨 · 입 값의 관측 확인이 여기에 듭니다. 창 기록에서는 바뀐 줄이 그 구간 안에 있을 때 규칙표의 고개 방향 게이트, `measurable`의 얼굴, `vision`의 얼굴 · 몸 비율과 입 움직임 최댓값이 여기에 듭니다. 앞 사용자의 얼굴 · 머리 · 몸 · 보조기구는 새 사용자의 것이 아니기 때문입니다. 중앙값 판정에 필요한 관측 줄 비율(`face_visible_min`)과 위의 비율은 그대로 창(창 기록은 구간) 전체 프레임 수에 견줍니다. 그래서 바뀐 직후의 창은 줄이 모자라 모름(`too_few_rows`)이나 센서 실패(`sensor_failure`)가 되기 쉽습니다. `face_approach`는 참 판정에 이 비율을 요구하지 않아서 새 사용자의 관측 줄 몇 개로도 참이 나옵니다. 같은 자리에서 다시 잡은 트랙, 이어 붙인 트랙, 앞 사용자가 자리 잡기 전의 트랙 바뀜은 교체로 세지 않으므로 앞 줄도 읽습니다. 장면을 재는 값(사용자 교체 사건, 사람 안 보임, 일행 상자, 뒷사람, 머리 상자 수)과 터치 횟수는 창 전체를 읽습니다.
- 저장소 기본값만으로는 새 태그가 참이 될 수 없습니다. 앉은 높이 · 얼굴 접근 경계값은 기본값이 없어 모름이고, 사용자 교체 · 사람 안 보임은 머리 탐지기, 보조기구 사용은 보조기구 탐지기의 ONNX 파일이 있어야 하는데 둘 다 저장소에 없습니다(보조기구의 `head_centre` · `head_centre_carry` 읽기는 컷 `aid_head_min`도 있어야 함). 카메라마다 보정한 값 묶음과 모델 파일을 주어야 태그가 판정합니다.
- 앉은 높이는 얼굴로 판정하지 못하는 창에서 주 사용자 머리 상자의 세로 가운데를 읽습니다(머리 탐지기와 `seated_head_cy_min`이 있을 때). 얼굴을 못 보는 앉은 사용자도 판정하려는 것입니다. 머리 상자가 같은 사용자의 기준 머리 높이(`head_ratio_user`, `iod_ratio_user`와 같은 기준점)보다 `head_approach_ratio_min`을 넘게 커진 줄은 이 판정에서 뺍니다. 화면에 다가가면 머리가 커지고 아래로 내려가지만, 조작 거리에 앉은 사용자의 머리는 커지지 않기 때문입니다. 회사 키오스크 영상(카메라 값 150, 경계값은 다른 사람들의 서서 쓰는 테이크로 정하고 한 사람씩 빼 가며 견줌)에서 얼굴만 쓰면 앉은 영상 40편 가운데 33편을 찾고 7편은 끝내 판정하지 못했는데, 머리 상자를 함께 쓰면 40편을 모두 찾았습니다. 서서 쓰는 영상 92편 가운데 잘못 잡은 영상은 6편으로 같고, 잘못 잡은 창은 68/1158(5.9 %)에서 71/1394(5.1 %)가 됐습니다. 팀 촬영본에서는 T10(뒤에서 대신 조작)까지 잡았지만, 화면에 얼굴을 바싹 댄 T02 · T05에서 머리가 내려가 참인 창이 생깁니다.
- 경계값(`params.SCENE_BOUNDARIES`)은 기본값이 없고 값 묶음의 `chain` 칸으로 넣습니다. 얼굴 위치는 카메라 높이 · 기울기에 따라 달라서 `seated_face_cy_min`은 카메라마다 따로 정합니다. 정하는 방법은 Wu 외(W4A 2021)의 기준선 + 2 SD입니다. 그 카메라 앞에서 서서 보통으로 쓰는 녹화를 창으로 나누고(창 길이 = 값 묶음의 `window_s`), 창 중앙값의 평균에 표준편차 2배를 더하고, 태그는 그 값을 넘을 때 참입니다. 보정 녹화는 평가 촬영본과 따로 찍습니다. 같은 테이크로 값을 정하고 그 테이크로 평가하면 평가가 아무것도 말해 주지 않기 때문입니다. `approach_ratio_min`이 1 이하로 나오면(기준 크기와 같거나 작음) 쓰지 않고, 값 묶음도 1 이하의 `approach_ratio_min` · `head_approach_ratio_min`을 받지 않습니다.
- 보정 도구: `python -m app.modules.vision.tools.calibrate_scene --params 값묶음.json --rows 보정녹화1/rows.csv 보정녹화2/rows.csv --note "녹화 설명" --out 조각.json`. 창 중앙값 · 프레임 · 녹화 중앙값 세 가지로 n · 평균 · 표준편차 · 평균 + 2 SD를 출력하고, 창 중앙값 값을 값 묶음의 `chain` 칸 조각으로 씁니다. 최소 개수는 두지 않았습니다. n이 충분한지는 출력을 보고 판단합니다. `--note`에는 녹화를 묶어서 설명하고, 파일 이름이나 사람 이름은 적지 않습니다. 머리 탐지기를 켠 녹화를 주면 트랙 잇기 경계 2개(`stitch_shift_max` · `stitch_size_max`)도 냅니다. 같은 주 사용자 트랙의 머리 상자 하나와 그 뒤 `track_max_gap_s` 안의 마지막 상자를 짝지어 위치 차 · 크기 차를 재고(`columns.stitch_motion`), 그 평균 + 2 SD를 씁니다. 짝이 나온 녹화가 2개보다 적으면 값을 쓰지 않습니다. 보정 도구와 `companion_eval rewindow`는 `rows.csv`에 없는 장면 열을 값 묶음의 `chain` 값으로 채웁니다. 교체 열(`main_user_*`)은 하나라도 없으면(트랙 잇기 열이 생기기 전에 쓴 기록 등) 모두 다시 씁니다. 고개 숙임 열(`dpitch_user_deg`)은 이미 있으면 다시 쓰지 않습니다. 그래서 이어 붙인 트랙에서도 고개 숙임 기준을 이어 쓰게 고치기 전(2026-11-22)에 쓴 `rows.csv`는, 이어 붙인 끊김에서 기준을 다시 잡은 저장값을 그대로 씁니다. 교체 열을 다시 써서 이어 붙인 끊김이 새로 생긴 기록도 같습니다. 이런 기록으로 다시 낸 창 판단(`rewindow`)과 `head_down_pitch_min` 보정은 경고 없이 저장된 기준을 따릅니다. 영상으로 다시 재생하면(`replay.py`) 이 값을 새로 계산합니다.
- `iod_ratio_user`의 기준은 같은 주 사용자의 눈 사이 거리입니다. 기준점(터치 로그가 있으면 그 세션의 첫 누름, 없으면 트랙 시작)부터 모은 크기 가운데 위쪽 절반의 중앙값이라, 걸어 들어오는 동안의 작은 크기는 빠집니다. 첫 누름이 사용자가 아직 다가오는 중에 와도 기준은 터치 로그가 없을 때와 같은 방법으로 잡습니다. 그래도 걸어 들어오는 속도에 따라 도착 직후 창이 얼굴 접근으로 잡힐 수 있습니다.
- 터치 로그가 있으면 비가 이미 `approach_ratio_min`을 넘은 줄은 기준에 넣지 않습니다. 그래서 바싹 다가간 채 오래 머물러도 기준이 따라 올라가지 않고 `face_approach`가 이어집니다. 터치 로그가 없으면(`--serve` 없이 돌린 실시간 실행 `live.py`, 터치 로그 없는 재생) 다가간 줄도 기준에 들어가서, 오래 다가가 있으면 접근이 사라집니다. 합성 입력(6초 동안 40 px, 그 뒤 10초 동안 52 px, 줄마다 ±1 px)에서는 다가간 뒤 3초 동안만 참이었습니다. `--serve`로 돌린 실시간 실행에서는 주문 화면이 보낸 터치 창이 터치 로그 자리를 맡습니다(위 '주문 화면 · backend와 잇는 두 연결'의 첫 누름 기준). 첫 누름(터치 로그가 없으면 트랙 시작) 때부터 이미 가까이 있던 사용자는 그 크기가 기준이라 잡히지 않습니다. 반대로 첫 누름 직후의 얼굴이 유난히 작게 잡히면(고개를 크게 돌린 채 누른 경우) 그 크기가 기준이 되어, 그 뒤 보통 거리의 줄도 접근으로 남을 수 있습니다. 첫 누름 뒤에도 얼굴이 기준보다 `approach_ratio_min` 넘게 빨리 커지며 다가오면 그 줄도 기준에 들어가지 않아 같은 일이 생깁니다. 이 경우는 따로 거르지 않습니다. 주 사용자 트랙이 바뀌면 기준을 다시 잡지만, 같은 자리에서 다시 잡은 트랙(`main_user_reacquired`, 아래)은 같은 사람이라 기준을 이어 씁니다. 제자리에서 이어 붙인 트랙(`main_user_stitched`, 아래)은 사용자 교체로 세지 않지만 크기 기준은 다시 잡습니다. 이어 붙는 끊김은 대개 다가오는 중에 생겨서, 앞 트랙의 작은 크기가 기준에 남으면 다가간 줄로 잘못 빠지기 때문입니다(회사 영상 카메라 값 150에서 이은 끊김 4개 가운데 3개가 자리 잡기 전이었고, 기준을 이어 쓰면 앉은 높이 머리 상자 판정 창이 366개에서 360개로 줄었습니다). 고개 숙임 기준(`dpitch_user_deg`)은 이어 붙인 트랙에서도 이어 씁니다. 깊이 숙여 끊긴 트랙의 첫 얼굴은 숙인 각도라서, 그 줄로 기준을 다시 잡으면 그 뒤의 숙임을 거르지 못하기 때문입니다. 이 기준은 첫 얼굴 한 줄이라, 이어 쓰면 트랙이 끊기지 않았을 때와 같은 값이 됩니다. 머리 탐지기가 없는 실행은 얼굴과 몸을 `track_max_gap_s`보다 오래 못 보면 기준을 다시 잡습니다. 그래서 손님이 쉬지 않고 이어지면 앞 손님의 크기가 기준에 남습니다. 기준 표본은 0.1 px 간격으로 묶어 개수만 남깁니다. 그래서 오래 켜 둬도 상태가 커지지 않고, 중앙값은 0.05 px 안에서 같습니다.
- 머리 탐지기를 켠 실행은 주 사용자 머리 상자에 맞춘 얼굴(`face_in_primary` 참)만 `seated_height` · `face_approach`와 `iod_ratio_user`의 기준에 씁니다. 머리 상자가 잠깐 빠진 프레임에서 어느 상자에도 들지 않은 얼굴처럼 누구 것인지 모르는 얼굴은 쓰지 않습니다.
- `seated_height` · `aid_use`는 중앙값을 낸 줄이 창 프레임의 `face_visible_min`보다 적으면 모름(`too_few_rows`)입니다. 세 태그가 얼굴 단서에 이미 요구하는 비율을 그대로 써서, 줄 몇 개로 참 · 거짓을 내지 않습니다. `face_approach`는 참에는 이 비율을 묻지 않습니다. 얼굴을 바싹 대면 얼굴 점을 놓치는 일이 잦아서, 비율을 두면 이 장면을 가리게 됩니다. 거짓에는 비율을 묻습니다. 얼굴을 놓치기 직전 줄 몇 개로 창 전체를 거짓이라 하지 않으려는 것입니다.
- 얼굴만 가려진 경우(모자 · 손)는 머리 상자 트랙이 이어져서 사용자 교체로 세지 않습니다. 머리 상자까지 `track_max_gap_s`보다 오래 놓쳐 트랙이 끝나도, 새 주 사용자 상자가 끝난 트랙의 마지막 상자와 `track_iou_min`(추적기가 상자를 잇는 SORT 관행값) 이상 겹치고 그동안 자리가 비지 않았으면 같은 자리에서 다시 잡은 것으로 보고(`main_user_reacquired`) 교체로 세지 않습니다. 자리가 비었다는 것은 머리 상자도 몸도 `track_max_gap_s`(머리 트랙이 끊기지 않는 시간)보다 오래 이어서 안 보였다는 뜻입니다(`main_user_body_gap_s`, 관측값 `body_unseen_s`로 잼). 그래서 깊이 숙일 때 자세 추정이 잠깐 몸을 놓쳐도 자리가 빈 것으로 보지 않습니다. `body_unseen_s`가 없는 줄이면 전처럼 몸이 모든 줄에 보여야 합니다(`main_user_body_kept`). 그 사이 몸까지 그보다 오래 안 보였으면 자리가 비었던 것이라 같은 자리에 선 다음 손님도 교체로 셉니다. 카메라가 잠깐 멈춘 경우도 같습니다. 깊이 숙이거나 모자를 쓰면 머리 상자가 크게 바뀌어, 추적기가 같은 사람에게 곧바로 새 트랙을 시작할 수 있습니다. 새 주 사용자 트랙이 앞 트랙의 마지막 상자 뒤 `track_max_gap_s` 안에 처음 잡혔고, 그 첫 상자의 위치 차가 `stitch_shift_max` 이하이고 크기 차가 `stitch_size_max` 이하이면 제자리에서 끊긴 같은 사용자로 보고 이어 붙입니다(`main_user_stitched`). 모양은 보지 않고 시간 · 위치 · 크기만 봅니다(StrongSORT AFLink와 같은 방식). 두 머리가 한 프레임에 함께 보였으면 두 사람이라 잇지 않습니다. 같은 자리에서 다시 잡았고 이어 붙이기도 한 끊김은 이어 붙인 쪽을 따라 교체가 아닌 것(거짓)으로 보고, 모름으로 두지 않습니다. 이어 붙이기는 새 머리가 앞 트랙의 마지막 상자 뒤 `track_max_gap_s` 안에 처음 잡혀야 한다는 시간 조건까지 맞춘 것이고, 다시 잡음은 이 조건을 보지 않기 때문입니다. 두 경계는 서서 쓰는 녹화에서 같은 주 사용자 머리 상자가 `track_max_gap_s` 안에 움직인 위치 차 · 크기 차의 평균 + 2 SD입니다. 상자 하나를 그 뒤 `track_max_gap_s` 안의 같은 트랙 마지막 상자와 짝짓기 때문에, 짝은 대개 `track_max_gap_s`만큼 떨어져 있습니다. 그래서 두 경계는 잇기가 건너는 가장 긴 끊김에 맞고, 자주 만나는 짧은 끊김(0.1초)에는 느슨합니다. 짝을 지을 때는 시간 차가 꼭 `track_max_gap_s`인 짝이 부동소수점 반올림으로 빠지지 않게 1e-9초를 더 받지만, 잇기 규칙과 추적기는 그 여유 없이 비교합니다. 회사 키오스크 영상(카메라 값 120 · 150 · 200, 311편)은 영상마다 참가자 한 명이라 영상 안의 교체는 모두 잘못 센 것입니다. 두 경계를 다른 사람들의 서서 쓰는 테이크로 정하고 한 사람씩 빼 가며 견주니, 교체로 잘못 센 창이 카메라 150에서 3/2414개(132편 중 1편)에서 0개, 120에서 52/1651개(90편 중 16편)에서 29개(9편)로 줄었고, 200은 4/1661개(89편 중 2편) 그대로입니다. 150의 1편은 트랙 잇기로, 120의 23창은 위의 몸 공백 허용으로 빠졌습니다. 대신 120에서 같은 자리 다시 잡음의 모름 창이 9개에서 32개가 됐습니다. 남은 잘못 센 바뀜 12개(120에서 10개, 200에서 2개) 가운데 10개는 새 상자가 앞 상자와 `track_iou_min`보다 덜 겹치고, 2개는 같은 자리지만 몸이 1.06초 · 1.23초 동안 안 보였습니다. 팀 촬영본의 교체 장면 2편(T03 · T08)은 그대로 잡히고 다른 테이크는 0창입니다. 앞 주 사용자가 키오스크 앞에 자리 잡기 전(머리 상자 높이가 1초 구간마다 계속 커지는 동안, `segment_s` 구간 중앙값이 앞 구간보다 커지지 않은 첫 구간부터 자리 잡음)에 트랙이 바뀌면, 처음 다가오는 중의 바뀜이라 교체로 세지 않습니다(`main_user_prev_settled`). 터치(장바구니가 남은 채 한참 무입력 뒤 첫 터치)와 묶는 일은 판단 층이 합니다.
- `none_seen`은 카메라가 아무도 보지 못한 창입니다. 못 봄은 사람 없음과 다르므로, 터치가 없는지와 얼마나 이어졌는지(경고 시작)는 판단 층이 정합니다. 머리 탐지기가 돌지 않으면 머리 상자가 없는지 몰라 모름입니다.

### 보조기구 입력 (2026-11-22, 선택)

보조기구 탐지기(YOLOX-Nano, 사람 단위 5클래스: `pedestrian` · `crutch` · `cane` · `walker` · `wheelchair`)를 선택 입력으로 연결했습니다. 재생 · 실시간 실행기에 `--aid-model 파일.onnx`를 줄 때만 돌고, 주지 않으면 보조기구 열이 없습니다(다른 열과 상황 출력은 그대로). 가중치와 ONNX 파일은 이 저장소에 두지 않습니다. 쓰는 파일은 TU Graz 학습 분할과 PMMA 학습 분할로 함께 학습한 `aid_det_joint_416_416.onnx`(입력 416, 내보낸 파일의 메타데이터에 클래스 · 라이선스 · 출처 문구가 있음)입니다.

- 상자 하나가 사람 하나이고, 클래스는 그 사람이 무엇을 짚고 움직이는지입니다. 상자마다 다섯 클래스의 점수(objectness × 클래스 점수)를 모두 남깁니다.
- 점수 하한 `aid_score_min` 0.01은 기록용이라 배경에서도 상자가 남을 수 있습니다. 그래서 사람이 보였는지(`none_seen`)와 주 사용자 상자 고르기에는 `aid_person_min`(0.390, 공개 자료의 사람 검출 F1 최대점)을 넘는 상자만 쓰고, 그 수를 `aid_person_count`로 남깁니다.
- 클래스가 사람 단위라 보조기구 자체의 위치는 나오지 않습니다. 그래서 어깨선은 주 사용자의 사람 상자를 찾는 데 쓰고, 보조기구를 어떻게 짚는지(의존 정도)는 판정하지 않습니다.
- 주 사용자의 상자: 머리 탐지기를 켜면 주 사용자 머리 상자 가운데를 품은 상자들 가운데, 위 끝이 머리 상자 위 끝에 가장 가까운 상자입니다. 몸 점은 쓰지 않습니다. 몸 점은 한 사람만 따라가서, 겹쳐 선 동행인의 어깨가 주 사용자 머리 아래에 오면 주 사용자 자신의 상자가 후보에서 빠지기 때문입니다. 그 프레임에 주 사용자 머리 상자가 없으면 기준점 없음(`aid_owner` `unknown`)입니다. 머리 탐지기 없이 돌리면 몸 점의 두 어깨(11 · 12)를 품은 상자를 씁니다(어깨 열과 같은 가정). 그 한 상자에서 다섯 클래스 점수, 가장 높은 클래스(`aid_top_class`), 목발 · 지팡이 · 보행기 · 휠체어 점수 가운데 가장 큰 값(`aid_any_score`, 보조기구를 쓰는 사람인가), 휠체어 점수(`aid_wheelchair_score`), 어느 쪽 보조기구인지(`aid_kind`)를 냅니다. `aid_kind`는 휠체어 점수가 목발 · 지팡이 · 보행기 점수 가운데 가장 큰 값보다 크면 `wheelchair`, 아니면 `standing`입니다. 판단 층은 이 칸으로 휠체어는 1-2, 서서 짚는 보조기구는 1-1로 보냅니다. `aid_owner`는 그 상자의 가장 높은 클래스가 네 보조기구 가운데 하나면 `yes`입니다. 다른 사람의 보조기구는 주 사용자의 것으로 세지 않습니다.
- 탐지기를 불러올 때 빈 입력 한 장으로 출력 모양이 클래스 목록과 맞는지 봅니다. 실시간 실행의 `meta.json`에도 파일의 해시 · 라이선스 · 출처 문구를 적습니다.
- 출처 문구(내보낸 파일의 `attribution`): aid_det joint weights (YOLOX-Nano, 5 person-level classes) were trained on the train split of "Crossroad Camera Dataset - Mobility Aid Users" v1.0 by Ludwig Mohr, Nadezda Kirillova, Horst Possegger, Horst Bischof (Graz University of Technology), https://doi.org/10.3217/2gat1-pev27, licensed under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/), together with the train split of PMMA v1.1 (CC0 1.0). 가중치는 CC BY-SA 4.0이라, 파일을 넘길 때는 이 문구와 라이선스를 함께 넘깁니다. 코드는 YOLOX(Apache-2.0)의 전처리 · 디코딩 · NMS를 `app/inference/head.py`와 함께 씁니다.
- 정확도: 공개 시험 자료(TU Graz 시험 분할, 입력 416)에서 목발 AP50 22.2 · 휠체어 82.1 · 보조기구 있음 76.0입니다. 교차로 카메라 시점에서 잰 값이라, 키오스크 시점의 정확도로 쓰지 않습니다.
- 키오스크 앞 가까운 사용자: 길거리 카메라 영상으로 학습한 이 탐지기는 키오스크 앞에 가까이 선 사용자를 사람 상자로 잡지 않고, 그때 `aid_use`는 추측하지 않고 모름(`no_user_box`)을 냅니다. 팀 촬영본 32편(T10 · T33 제외, 2026-11-22)에서 주 사용자 기준점을 품은 상자가 나온 프레임은 4,638장 가운데 0장이었고, `aid_person_min`을 넘는 사람 상자 268프레임은 모두 더 멀리 있는 다른 사람이었습니다(창 480개 모두 모름: `no_user_box` 477 · `no_anchor` 3). 라벨 방식이 다른 키오스크 시점용 탐지기 파일은 아래 '세 읽기'의 `head_centre`나 `head_centre_carry`로 읽습니다.
- `aid_use`의 기준값 `aid_use_min` 0.350(`[파일럿]`)은 TU Graz 검증 분할에서 F1이 가장 큰 점수 기준을 그대로 옮긴 것입니다. `aid_any_score`와 같은 점수 규칙(목발 · 지팡이 · 보행기 · 휠체어 점수의 최댓값)의 줄에서 가져왔고, 시험 분할에 그대로 적용하면 정밀도 0.698 · 재현율 0.736(사람 상자 3,966개)입니다. 1-1 경로(목발 · 지팡이 · 보행기)만 보는 독자를 위해 적으면, 같은 파일에서 그 셋의 묶음은 자기 검증 기준(0.350)에서 시험 정밀도 0.618 · 재현율 0.510(사람 상자 2,306개)입니다. 주의할 점은 넷입니다.
  - 이 값은 그 공개 자료와 그 자료의 보조기구 사용자 비율에 맞춘 값입니다. 키오스크 앞 손님 가운데 보조기구 사용자 비율은 재지 않았고, 다른 공개 자료(PMMA 검증 분할)로 같은 방법을 쓰면 0.480이 나옵니다.
  - 키오스크 시점에서 잰 기준이 아닙니다(위 '정확도').
  - 작은 사람 상자에서 재현율이 낮습니다. 같은 규칙에서 작은 상자 0.386(158개), 중간 0.760, 큰 상자 0.730입니다(COCO 넓이 구간).
  - 영상 한 장에서 가장 큰 사람만 보는 방식(이미지 단위)의 기준값은 쓸 만한 값이 나오지 않아 쓰지 않았습니다.

#### 세 읽기 (`aid_rule`, 2026-11-26)

탐지기 파일마다 라벨 방식이 달라서 `aid_use`를 읽는 방법이 셋입니다. 값 `aid_rule`로 고르고, 기본값은 지금 규칙인 `owner_box`입니다. `head_centre_carry`는 `head_centre`에 머리 상자가 없는 프레임의 읽기를 더한 것입니다.

| 읽기 | 맞는 파일 | 프레임마다 읽는 값 | `aid_use` 참 |
|---|---|---|---|
| `owner_box`(기본값) | 사람마다 사람 상자가 있고 클래스가 그 사람의 이동 방법인 파일(`aid_det_joint_416_416.onnx`) | 위 '주 사용자의 상자'와 그 상자의 `aid_any_score` | 창 안 `aid_any_score` 중앙값 > `aid_use_min`(0.350, `[파일럿]`) |
| `head_centre` | 키오스크 시점용 파일: `pedestrian`은 서 있거나 걷는 사람만, 보조기구 사용자는 사용자와 보조기구를 함께 두른 보조기구 클래스 상자 하나(그 사람에게는 `pedestrian` 상자가 없음), 앉은 사람은 상자 없음 | `aid_head_score`: `pedestrian`을 뺀 클래스마다 모든 anchor의 그 클래스 점수(objectness × 클래스 점수)를 `aid_score_min`으로 거르고 그 클래스 안에서 `aid_nms_iou`로 NMS를 한 뒤, 주 사용자 머리 상자 가운데를 품은 상자의 가장 큰 점수. 클래스들 가운데 가장 큰 값과 그 클래스(`aid_head_class`) | 창 안 `aid_head_score` 중앙값 > `aid_head_min`(값 없음) |
| `head_centre_carry` | `head_centre`와 같은 파일 | 주 사용자 머리 상자가 있는 프레임은 `head_centre`와 같은 값이고, 그 값을 낸 상자를 기억함. 머리 상자가 없는 프레임은 모든 보조기구 클래스의 남은 상자 가운데 기억한 상자와 IoU가 가장 큰 상자(IoU `track_iou_min` 이상)의 점수와 클래스이고, 그 상자를 다음에 따라감. 값의 출처는 `aid_head_from`(`head` · `carried`) | `head_centre`와 같음 |

- `head_centre`는 키오스크 시점용 파일을 시험한 재생 도구(저장소 밖)와 같은 읽기이고, 디코딩은 `app/inference/aid.py`와 같습니다. 그 도구는 휠체어 클래스만 읽고, 이 모듈은 `pedestrian`을 뺀 네 클래스 가운데 가장 큰 값을 씁니다.
- 머리 상자는 있는데 그 가운데를 품은 상자가 없으면 그 프레임의 값은 0입니다. 주 사용자 머리 상자가 없는 프레임은 값이 없습니다. 그래서 이 읽기는 머리 탐지기가 있어야 하고, 머리 탐지기 없이 돌리면 `aid_use`는 늘 모름(`no_main_user_box`)입니다.
- 창 판단은 `owner_box`와 같습니다. 창의 가장 새 사용자 줄부터 값이 있는 줄의 중앙값을 내고, 그 줄이 `face_visible_min`보다 적으면 모름(`too_few_rows`)입니다. 근거(사건 `aid_head`)에는 그 중앙값을 낸 클래스(`aid_class`: 점수 순으로 놓은 줄 가운데 위쪽 가운데 줄의 클래스)가 들어갑니다.
- 컷 `aid_head_min`은 아직 정하지 않아 기본값이 없습니다. 값이 없으면 `aid_use`는 모름(`no_value_for_model`)이고, 저장소에는 값을 두지 않습니다.
- 이 읽기에서도 위 `aid_*` 열은 전과 같이 적습니다(`none_seen`이 읽는 `aid_person_count` 포함). `aid_use`만 새 열을 읽습니다.
- `head_centre_carry`는 머리 상자가 적게 잡히는 사용자를 읽으려고 더한 읽기입니다. 머리 상자가 없는 프레임에서는 주 사용자가 누구인지 줄에 남지 않으므로, 직전 머리 프레임에서 사용자 머리 가운데를 품었던 보조기구 상자를 머리 트랙과 같은 규칙으로 따라갑니다. IoU가 가장 큰 상자를 고르고, 그 IoU가 `track_iou_min`(0.3, 관행값: SORT 공개 구현의 기본값) 이상이어야 합니다. `track_max_gap_s`(1.0초, `[파일럿]`)보다 오래 맞는 상자가 없으면 따라가기를 끝냅니다. 새 값은 없습니다.
  - 값이 0인 머리 프레임(머리 가운데를 품은 상자가 없음)은 기억한 상자를 지우고, 값이 있는 머리 프레임은 그 상자로 바꿉니다. 새 주 사용자의 첫 줄은 늘 머리 프레임이라 그 사람의 상자로 바뀝니다. 머리 프레임이 한 번도 없었으면 아무것도 따라가지 않습니다.
  - 머리 트랙이 끝난 뒤에도 상자가 맞는 동안은 따라갑니다. 그래서 다른 태그가 주 사용자로 보지 않는 사람의 보조기구를 읽을 수 있고, 겹쳐 지나가는 다른 사람의 상자로 옮겨 갈 수도 있습니다(머리 트랙처럼 움직임 예측이 없음).
  - 터치 로그 세션이 바뀌면 머리 트랙 · 기준과 함께 지웁니다. 창 판단, 컷 `aid_head_min`, 근거(`aid_head`, `aid_class`)는 `head_centre`와 같습니다.
- 두 값은 값 묶음의 `chain` 칸으로 주거나, 재생 · 실시간 실행기에 `--aid-model 파일.onnx --aid-rule head_centre --aid-head-min <컷>`(또는 `--aid-rule head_centre_carry`)으로 줍니다. 옵션이 값 묶음보다 앞서고, `meta.json`에는 출처 `실행 옵션 --aid-head-min`, origin `option`으로 남습니다. `--aid-model` 없이 두 옵션 가운데 하나라도 주면 시작하지 않습니다. 키오스크 시점용 파일은 내부 시험 파일이라 저장소에 두지 않고 경로로 줍니다.

#### 휠체어 확인 분류기 (`--aid-confirm-model`, 2026-11-27, 선택)

`aid_use`가 참이고 근거의 `aid_class`가 휠체어인 창만 다시 봅니다. 같은 창에서 사람 crop 분류기도 휠체어로 읽을 때만 그 답을 남기고, 아니면 `aid_use`를 거짓(보조기구 없음)으로 바꿉니다. 지팡이 · 목발 답과 거짓 · 모름 창은 바꾸지 않습니다. 옵션을 주지 않으면 출력은 지금과 같습니다. 코드는 `aid_confirm.py`(줄 · 창)와 `app/inference/aid_confirm.py`(분류기)입니다.

- 쓰는 때: `--aid-model`과 `--aid-rule head_centre`(또는 `head_centre_carry`)를 함께 줄 때만 켤 수 있습니다. 재생 · 실시간 실행기에 `--aid-confirm-model 파일.onnx`를 줍니다. 여러 번 주면 파일마다 softmax 확률을 낸 뒤 평균합니다(deep ensemble, Lakshminarayanan et al. 2017).
- 사람 상자: 머리 상자가 있는 줄은 머리 상자 가운데를 품은 탐지기 사람 상자(`Aids.boxes`, 클래스 무관) 가운데 점수가 가장 큰 상자를 씁니다. `head_centre_carry`로 따라간 줄은 따라간 보조기구 상자와 IoU가 가장 큰 사람 상자를 씁니다. 둘 다 없으면 그 줄은 값이 없습니다.
- crop: 분류기를 학습하고 잰 crop과 같습니다. 사람 상자를 사방 20 px 넓혀 정수 픽셀로 내림 · 올림하고 화면 안으로 자릅니다. 이어 RGB로 224 × 224 bilinear로 줄이고, ImageNet 평균 · 표준편차로 정규화합니다. 머리 상자와 몸 점으로 몸 상자를 어림한 crop은 이 분류기를 학습한 crop과 달라서 쓰지 않습니다.
- 창 판단: 줄마다 crop 이미지만 만들어 두고(프레임당 약 2 ms), 분류기는 휠체어로 판단한 창에서만 그 창의 줄을 처음 한 번 읽습니다. 그 창의 줄 값을 P(wheelchair)로 바꿔 `aid_use`와 같은 창 규칙(새 사용자 줄부터, 줄 수 하한, 중앙값)으로 판단하고, 중앙값이 `--aid-confirm-min`을 넘으면 답을 남깁니다. 기본값 0.5는 분류기 자체의 결정점이고, 측정의 모든 표가 쓴 컷입니다.
- 실시간 실행기(`live.py`)에서는 창 판단을 작업 스레드 하나(`ReleaseWorker`)에서 합니다. 프레임 처리는 기다리지 않고, 창은 줄과 crop 이미지를 그 자리에서 떼어 두었다가 만든 순서대로 판단해 보냅니다. 그래서 뒤 창이 앞 창보다 먼저 나가지 않고, 판단 결과는 재생과 같으며 분류기가 읽는 시간만큼 늦게 나갑니다. 재생(`replay.py`)은 지금처럼 그 자리에서 판단합니다.
- 미리 읽기(실시간 실행기): 창 안의 어떤 줄이 탐지기 자체 읽기로 휠체어(`aid_head_class`가 휠체어이고 `aid_head_score`가 `aid_head_min`을 넘음, 창 규칙과 같은 값)이면, 그 창 구간에서 아직 읽지 않은 줄을 오래된 줄부터 분류기 스레드 하나에 넣고, 그런 줄이 구간 안에 있는 동안 새 줄도 넣습니다. 창 판단은 끝나지 않은 읽기만 기다립니다. 줄마다 값은 같아서 창 판단 결과도 같습니다. 탐지기가 휠체어로 읽지 않는 사용자에게는 분류기를 부르지 않습니다.
- `--aid-confirm-hold`: 분류기가 한 번 휠체어 창에 동의하면, 같은 사용자의 뒤 창 가운데 엔진이 휠체어로 판단한 창은 다시 읽지 않고 유지합니다. 홀드는 네 경우에 끝납니다. 새 주 사용자(`user_changed` 태그의 처음 보는 `main_user_changed` 사건), 새 터치 세션, `aid_use`가 모름이고 엔진의 모름 이유가 `no_main_user_box`(창에 주 사용자 상자가 없음)인 창, 모름 이유가 `no_frames`(창에 줄이 없음)인 창입니다. 그 창은 엔진 답을 그대로 두고, 그 뒤로는 다시 동의가 있어야 합니다. 새 터치 세션은 재생에서는 창 기록의 `session_reset`입니다. 실시간 실행기에서는 창을 내보낼 때 붙는 세션 ID(`evaluated.session_id`)가 앞서 붙은 세션 ID와 다른 창이고, 터치 입구가 있으면 처음 이름이 붙은 세션도 새 세션으로 셉니다(실시간의 창 판단에는 터치 로그가 없어 `session_reset`이 늘 거짓이고, 첫 세션에서 `FrameChain`이 주 사용자 추적을 처음부터 다시 하기 때문입니다). 홀드가 끝나면 미리 읽기는 그 창의 줄부터 다시 시작하고, 그보다 앞선 줄은 읽지 않습니다. 시간 값은 없습니다.
  - 홀드가 시작되는 창: 창 범위 안의 줄이 모두 `FrameChain`이 세션마다 주 사용자 추적을 처음부터 다시 한 줄(그 줄의 시각) 이후여야 홀드를 시작합니다. 창을 내보낼 때 세션 ID가 붙으면(실시간 실행기) 그 세션이 그 다시 시작한 세션과 같아야 합니다. 다시 시작하기 전의 줄은 앞 주 사용자의 줄이기 때문입니다. 예를 들어 휠체어 사용자가 아직 화면에 있는데 다른 사람이 세션을 시작하면, 그 세션의 첫 창은 대부분 휠체어 사용자의 줄입니다. 창 자체의 답(유지 · 거짓)은 바뀌지 않으므로 재생과의 일치도 그대로입니다. 홀드를 시작할 수 있는 창은 다시 시작한 줄에서 `window_s`와 `window_s + segment_s` 사이에 끝나는 창이고(창은 `segment_s` 간격으로 끝남), 첫 유지 창은 그다음 창입니다. 새 값은 없습니다.
- `--aid-confirm-hold-user`(`--aid-confirm-hold`를 포함): 같은 동의 뒤에는 같은 사용자의 모든 창이 엔진 답과 관계없이 `aid_use` 참이 됩니다. 끝나는 때는 위와 같고, 줄이 없거나 주 사용자가 없는 창은 참으로 답하지 않습니다. 홀드가 끝난 창의 `aid_confirm`에는 `hold_end`(`session`, `user_changed`, `no_main_user_box`, `no_frames`)가 붙습니다. 태그의 근거(`evidence`)는 엔진 것 그대로 두므로 근거의 `aid_class`는 엔진 중앙값 뒤의 클래스입니다. 휠체어일 수도 있고, 다른 클래스나 없음(null)일 수도 있습니다. backend 규칙표는 `aid_class`가 휠체어일 때만 1-2(화면 낮추기)를 열고, 1-1(음성 주문)은 클래스와 관계없이 엽니다. 그래서 다른 클래스나 없음인 홀드 창에서는 1-1만 열 수 있습니다. 창 기록의 `aid_confirm`에 `hold_user`와 엔진 자체 답(`engine_status`, `engine_class`, `engine_unknown_reason`)을 남깁니다.
- `--aid-start-only`(`--aid-confirm-model`이 필요하고 두 홀드 옵션과는 함께 쓸 수 없음): 보조기구를 사용 구간마다 처음에 한 번 판단합니다. 사용 구간은 터치 세션이 바뀐 줄(첫 세션 포함)과 엔진이 사용자 교체로 센 줄(`user_changed` 태그가 세는 `main_user_changed`)에서 새로 시작합니다. 세션은 재생에서는 터치 로그의 세션이고, 실시간 실행기에서는 터치 창이 알려 준 세션입니다. 실시간에서는 새 세션의 첫 터치 창이 도착한 다음 프레임에서 구간이 시작하므로, 그 터치 창의 시작보다 1초쯤 늦습니다. 세션이 없으면 아무것도 끄지 않습니다. 옵션을 주지 않으면 출력은 이 옵션이 없을 때와 같습니다.
  - 끄는 때: 구간 안에서 누름이 처음 기록된 줄의 시각 이후에 시작하는 창 가운데, 보조기구 없음으로 판정한 첫 창에서 끕니다. 보조기구 없음 판정은 엔진 자체의 거짓과, 분류기가 읽고 동의하지 않은 휠체어 창(`reason`이 `median`)입니다. 모름 창은 판정으로 치지 않습니다. 분류기 오류, 줄 수 부족, 주 사용자 상자 없음 때문에 거짓이 된 창도 치지 않습니다. 그 구간에서 먼저 `aid_use` 참으로 답한 창(분류기가 동의한 휠체어 창, 지팡이 · 목발 · 보행기 클래스의 참 창)이 있으면 끄지 않습니다. 구간 시작 전부터 걸쳐 있어도 구간 안에서 끝나는 창이면 셉니다. 구간 안에 누름이 없으면 끄지 않습니다. 실시간에서는 누름이 그 터치 창의 마지막 줄에 기록되므로, 세션의 첫 터치 창에 든 누름은 대개 구간 시작보다 앞이라 세지 않습니다.
  - 끈 뒤: 그 구간이 끝날 때까지 보조기구 탐지기를 돌리지 않고, 분류기의 crop과 미리 읽기도 하지 않습니다. 그 줄의 보조기구 열과 `ms_aids`는 빈칸입니다. 탐지기는 끄기로 판단한 창을 내보낸 다음 줄부터 꺼집니다. 그 구간에서 끝나는 그 세션의 창은 `aid_use`를 거짓으로 답하고 근거(`evidence`)를 비우며, 창 기록의 `aid_confirm`에 `start_off: true`를 남깁니다. 끄기로 판단한 창에는 `start_judgment: true`를 남깁니다. `meta.json`의 `aid_confirm`에는 끈 구간 수(`sessions_off`), `start_off`로 답한 창 수(`windows_start_off`), 탐지기를 건너뛴 프레임 수(`frames_aid_skipped`)를 남깁니다. 다음 구간의 첫 줄부터 탐지기를 다시 돌리고, 그 뒤의 누름부터 다시 판단합니다.
  - 다루지 않는 것: 세션이 시작되기 전, 사람이 다가오는 동안 읽은 결과는 그 사람이 누름으로 연 세션으로 넘기지 않습니다. 엔진이 사용자 교체로 세지 않은 교체(같은 자리에서 다시 잡은 트랙, 이어 붙인 트랙, 앞 사용자가 자리를 잡기 전의 교체)에서는 판단을 다시 시작하지 않습니다. 실시간에서 꺼진 구간 뒤에 새 세션이 오면, 그 세션의 첫 터치 창이 도착할 때까지 1초쯤은 앞 구간이 이어져 탐지기가 꺼져 있습니다. 그 사이 줄의 보조기구 열이 비어 있어서 새 세션의 첫 한두 창은 `aid_use`가 모름일 수 있습니다. 재생에서 터치 로그의 첫 사건이 누름이면 그 누름은 세지 않습니다. 터치 로그는 첫 사건 앞 구간의 누름 수를 알 수 없기 때문입니다. 그래서 재생용 터치 로그는 누름 앞에 세션을 여는 사건(`session_start`나 `screen_enter`)을 둡니다.
- `--aid-stick-model 파일.onnx [파일.onnx ...]`와 `--aid-stick-frames N`(둘 다 주어야 하고, `--aid-confirm-model`과 `--aid-start-only`가 필요함): 지팡이를 든 사용자를 처음에 찾아 음성 주문을 묻게 합니다. 옵션을 주지 않으면 출력은 이 옵션이 없을 때와 같습니다.
  - 지팡이 줄: 휠체어 확인 분류기가 crop을 만드는 줄(주 사용자의 사람 상자가 있고 구간이 꺼지지 않은 줄)마다 지팡이 파일이 같은 crop을 읽습니다. 실시간 실행기에서는 분류기 스레드에서 읽고 프레임 처리는 기다리지 않습니다. 파일마다 max(P(crutch), P(cane))를 내고, 어느 파일이든 0.5를 넘으면 지팡이 줄입니다. 0.5는 파일 자체의 결정점이고 `--aid-confirm-min`의 기본값과 같습니다. 파일은 휠체어 확인 분류기와 입력 크기가 같아야 합니다.
  - 세는 범위: 지팡이 줄은 주 사용자마다 셉니다. 엔진이 사용자 교체로 센 줄에서 새로 세고, 새 세션에서도 새로 셉니다. 다만 세션 앞 구간이 다가오는 사람의 구간(첫 세션 전의 줄, 또는 사용자 교체로 시작한 구간)이면 그 수를 새 세션으로 넘깁니다. 그래서 첫 누름 전에 걸어오는 동안의 줄도 셉니다.
  - 답: 주 사용자의 지팡이 줄이 N개 이상이면, 시작 판단(끄기)보다 먼저 그 창을 `aid_use` 참으로 답하고 근거의 `aid_class`를 `cane`으로 둡니다. backend 규칙표는 이 답으로 1-1(음성 주문)을 엽니다. 창 기록의 `aid_confirm`에 `stick: true`, `stick_frames`(센 수), `stick_min`(N)을 남깁니다. 그 뒤로 같은 사용자의 창은 더 읽지 않고 같은 답을 내고, 그 구간은 끄지 않습니다. 이미 참인 창, 줄이 없는 창(`no_frames`), 주 사용자가 없는 창(`no_main_user_box`)은 바꾸지 않습니다.
  - 휠체어 먼저: 탐지기가 그 사용자의 줄을 휠체어로 읽으면(`aid_head_class`가 휠체어이고 `aid_head_score`가 `aid_head_min`을 넘음) 그때까지 센 수를 지우고, 그 사용자는 더 읽지 않습니다. 측정한 휠체어 사용자 영상에서는 분류기가 지팡이로 읽은 줄이 모두 이런 줄 뒤에 나왔기 때문입니다. 휠체어 확인 분류기가 휠체어에 동의한 창도 그 답을 그대로 두고, 그 사용자에게는 지팡이 답을 내지 않습니다.
  - N은 엔진에 기본값이 없고 실행기에서 줍니다. 지금 쓰는 1은 `[파일럿]` 값입니다. 분류기가 지팡이로 읽은 줄이 하나라도 있으면 답합니다. 지팡이 녹화 2개에서 지팡이 줄이 6개와 9개, 일반 사용자 촬영 5개의 805줄에서 0개였던 측정에서 정했습니다. 2로 두면 처리 속도가 떨어진 실행에서 짧게 나오는 지팡이 줄을 한 개만 잡아 답하지 못했습니다. `meta.json`의 `aid_confirm.stick`에 파일 수, 읽은 수, 지팡이 줄 수와 시각, 사용자별 수, 답한 창 수, 읽기 오류 수를 남깁니다. 지팡이 파일이 읽다가 예외를 내면 실행마다 한 줄만 찍고, 그 줄은 지팡이 줄로 세지 않습니다.
- 분류기 입력 정규화: ONNX 파일의 메타데이터에 `mean` · `std`(0~1 픽셀 단위의 세 수, JSON 목록)가 있으면 그 값을, 없으면 잰 ResNet-18 분류기의 ImageNet 값을 씁니다. `classes`(JSON 목록)가 있으면 `pedestrian, crutch, cane, walker, wheelchair` 순서와 같아야 하고, `output`은 `logits`(기본) 또는 `probs`입니다. 입력 크기는 파일의 입력 모양에서 읽고, 여러 파일은 크기가 같아야 합니다.
- 거짓으로 바꾼 창의 `aid_confirm.reason`: 분류기 값으로 본 창 규칙의 모름 이유(`too_few_rows`, `no_main_user_box`), 중앙값이 컷을 넘지 못함(`median`, 컷 비교는 `>`), 분류기 오류(`reader_error`) 가운데 하나입니다.
- 실시간 실행기에서 기다리는 창: 줄 버퍼가 아직 들고 있는 줄의 crop과 분류기 값은 지우지 않습니다(`run_live`가 버퍼의 첫 줄 시각을 넘김). 그래서 늦게 내보내는 창도 재생과 같은 줄과 중앙값으로 판단합니다. 지운 줄의 대기 중인 읽기는 취소합니다. 창을 대기열에 넣은 뒤 내보내기까지 `segment_s`보다 오래 걸리면 실행마다 한 줄만 찍고, 횟수를 `meta.json`의 `aid_confirm.releases_later_than_segment`에 남깁니다. 그 창이 돌아오기 전에도 알립니다. 프레임 루프가 프레임마다 대기열의 가장 오래된 묶음이 들어간 지 `segment_s`가 지났는지 보고, 지났으면 같은 줄을 한 번 찍습니다(같은 기준, 새 값 없음). 분류기 읽기에는 시간 한도를 두지 않습니다(근거 있는 값이 없음). 지운 줄을 창이 다시 읽을 때는 그 읽기를 대기 표(`futures`)에 넣지 않으므로 표가 커지지 않습니다.
- 분류기 오류: 시작한 뒤 분류기가 예외를 내면(crop이나 읽기) 그 줄이 든 창은 확인되지 않은 창(`aid_use` 거짓)이 되고, 창 기록의 `aid_confirm.error`에 오류를 남깁니다. 로그는 실행마다 한 줄만 찍고, 실행은 계속됩니다. 시작할 때 파일이 없거나 읽을 수 없으면 지금처럼 시작하지 않습니다. 작업 스레드에서 다른 예외가 나면 프레임 처리를 멈추고 터치 입구 · 태그 보내기 · `meta.json`(`aid_confirm.release_error`)을 마친 뒤 그 예외를 냅니다.
- 기록: 확인한 창의 `windows.jsonl` 줄에 `aid_confirm`(유지 여부 · 컷 · 중앙값 · 줄 수 · 이번에 읽은 줄 수)을 남기고, `meta.json`에 확인한 창 · 거짓으로 바꾼 창 · 읽은 수 · 읽기 시간 · 홀드가 끝난 신호별 횟수 · 분류기 오류 수를 남깁니다. 실시간 실행기는 옵션을 켰을 때 창마다 `evaluated`에 작업 대기열에 넣은 뒤 내보내기까지 걸린 초(`release_delay_s`)와 그때까지의 분류기 호출 수(`reader_calls_total`)를 남깁니다. 그래서 `meta.json` 없이 끝난 실행(`taskkill`)도 이 값을 볼 수 있습니다. 분류기 파일은 내부 시험 파일이라 저장소에 두지 않고 경로로 줍니다.

### 휴대폰 입력과 3-2 휴대폰 길 (2026-11-22, 선택)

3-2(일행 · 딴 일)의 두 번째 길로 COCO로 학습한 YOLOX-Nano(YOLOX 공개 release 0.1.1rc0의 `yolox_nano.onnx`, 입력 416, 80클래스)를 선택 입력으로 연결했습니다. 재생 · 실시간 실행기에 `--phone-model 파일.onnx`를 줄 때만 돌고, 주지 않으면 휴대폰 열이 없고 `phone_use`는 모름(`column:phone_owner`)입니다. 가중치 파일은 이 저장소에 두지 않습니다(Apache-2.0, Megvii; https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx, 3,659,407 B, sha256 `c789161e…bd18a0b7d`). 고개 숙임 길(`look_down`)은 팀 휴대폰 테이크 5편에서 하나도 잡지 못해 넣지 않았습니다.

- 후처리는 YOLOX ONNX Runtime 데모의 순서를 따릅니다. 상자마다 가장 높은 클래스를 고르고(objectness × 클래스 점수), `phone_score_min` 0.3 이상만 남겨 클래스를 가리지 않는 NMS(`phone_nms_iou` 0.45)를 한 뒤 `cell phone` 상자만 남깁니다. 두 값은 데모의 기본값입니다. 다만 NMS의 IoU는 머리 탐지기와 같은 함수로 재므로, 데모가 원본 픽셀 넓이에 더하는 1픽셀(`(x2 - x1 + 1) * (y2 - y1 + 1)`)이 없습니다. IoU가 0.45 근처인 작은 상자 쌍에서는 남는 상자가 데모와 하나 다를 수 있습니다.
- 주 사용자의 휴대폰: 휴대폰 상자가 주 사용자 머리 상자에 닿으면 `head`(귀에 댄 통화, 얼굴 앞), 주 사용자의 손 상자에 닿으면 `hand`(얼굴 아래에서 보기)입니다. 머리에 걸친 휴대폰은 휴대폰 상자를 더 많이 담은 머리 상자(겹친 넓이 ÷ 휴대폰 상자 넓이, 같으면 주 사용자)의 것으로 봅니다. 그래서 옆 일행이 귀에 댄 휴대폰이 주 사용자 머리 상자 가장자리에 닿아도 주 사용자 것이 아니고, 다른 사람 머리에 걸친 휴대폰은 주 사용자 손에 닿아도 세지 않습니다. 겹침을 IoU로 재면 작은 머리 쪽이 유리해져, 가까이 선 주 사용자의 통화를 옆 사람 것으로 보게 됩니다. 손 상자는 몸 점 한 손의 네 점(손목 · 새끼 · 검지 · 엄지: 15 · 17 · 19 · 21, 16 · 18 · 20 · 22)이 이루는 상자이고, 몸 점의 코(0)가 주 사용자 머리 상자 안에 있을 때만 주 사용자의 몸 점으로 봅니다. 몸 점은 한 사람만 따라가기 때문입니다. 손 점이 하나도 유한하지 않으면 손을 확인하지 못한 것으로 봅니다. 비율 같은 새 값은 없습니다. 몸 점의 보임 정도(visibility)는 값 묶음의 `chain` 칸에 `hand_vis_min`을 줄 때만 읽습니다. 이 값에는 기본값이 없습니다(`params.HAND_BOUNDARIES`). 값을 주면 visibility가 그보다 낮은 손 점은 손 상자에 넣지 않습니다. 가려지거나 화면 밖에 있어 위치를 추정한 점이라 주 사용자 휴대폰의 근거가 아니기 때문입니다. visibility가 없는 점(NaN)도 위치를 확인할 수 없어 넣지 않습니다. 남은 손 점이 없으면 손을 확인하지 못한 것으로 봅니다. 값을 주지 않으면 손 점의 위치를 확인할 수 없어 손 상자를 만들지 않습니다. 그래서 머리에 걸치지 않은 휴대폰은 판정하지 못함(`unknown`)으로 남고 손 길은 열리지 않습니다. 값이 없는 경계는 판정하지 않는다는 이 모듈의 규칙과 같습니다. 머리 길은 손 점을 읽지 않으므로 값과 상관없이 그대로입니다.
- 지속: 탐지기가 프레임마다 휴대폰을 잡지는 못해서, 프레임 비율 대신 창의 `segment_s` 구간(창 3초면 1초 구간 셋) 가운데 `min_events`개 이상에서 한 번이라도 주 사용자 휴대폰이 잡혔는지 봅니다. `min_events`는 새 값이 아니고 같은 값 묶음의 상황 값을 다시 씁니다. 세 상황 태그가 근거 사건 수로 쓰는 값이고, 값 묶음 파일에 [파일럿]으로 적혀 있습니다. 휴대폰이 잡힌 구간 하나를 근거 하나로 세는 읽기는 이 길에서 새로 정한 [파일럿] 읽기입니다. 창 안에서 사용자가 바뀌면(`user_changed`가 교체로 세는 트랙 바뀜) 구간은 새 사용자의 첫 줄부터만 읽습니다. 앞 사용자의 휴대폰은 새 사용자의 것이 아니기 때문입니다. 그래서 바뀌기 전 구간은 줄이 없어 판정하지 못한 구간이 됩니다. 같은 자리에서 다시 잡은 트랙, 이어 붙인 트랙, 앞 사용자가 자리 잡기 전의 트랙 바뀜은 `user_changed`가 교체로 세지 않으므로 그 앞 줄도 읽습니다.
- 두 길: 휴대폰이 머리에 있는 구간이 `min_events`개 이상이면 머리 길(통화)이고, 고개 방향을 읽지 않습니다. 손에 든 휴대폰은 구간 끝에 주 사용자가 화면을 보지 않을 때만 셉니다. 화면을 읽으며 휴대폰을 든 사람은 3-2가 아니고 4-2의 멈춤이기 때문입니다(장면 트리 3-2의 제외). 화면을 보지 않음은 고개 방향 게이트를 주 사용자 얼굴로만 읽어 거짓이거나(머리 탐지기를 켠 실행에서 주 사용자 머리 상자에 맞춰지지 않은 얼굴은 방향 근거에서 빼고 그 앞의 주 사용자 얼굴로 읽음), 구간에서 주 사용자 머리 상자가 있는 줄 가운데 화면 쪽을 향한 주 사용자 얼굴(고개 방향이 게이트와 같은 `offscreen_yaw_deg` 안이거나 값이 없음)이 보인 줄이 하나도 없을 때입니다(`chain.away_from_screen`). 카메라가 화면 위에 있어서, 얼굴 없이 머리만 보이면 화면을 향하지 않은 것입니다. 휴대폰을 내려다보며 얼굴을 놓친 경우와, 화면 밖으로 돌린 얼굴만 보이다 더 돌아 얼굴을 놓친 경우가 여기에 듭니다. 머리 상자 안에 화면 쪽을 향한 얼굴이 한 번이라도 보인 구간은 화면을 보지 않음이 아닙니다. 그래서 화면을 읽다 얼굴을 한 프레임 놓쳐도 손 길이 켜지지 않습니다. 구간에 머리 상자가 있는 줄이 없고 고개 방향 게이트도 모르면 손 길도 모름(`gaze_unknown`)입니다. 얼굴이 주 사용자 것인지는 `columns.main_user_face`로 읽어, rows.csv에서 다시 읽은 줄도 같은 값을 냅니다. 여기에 창 안 터치 없음과 몸 제자리(일행 길과 같은 조건)가 함께 맞아야 `phone_use`가 참이고, 규칙표 v0는 그때 3-2 기다림을 엽니다(결정의 `cues.path` = `phone_use`, 일행 길과 함께 켜질 때만 `cues.tag` = `consulting_companion`도 남음).
- 처리 시간(개발 노트북 i5-1340P, ONNX Runtime 스레드 1, T13 재생 `--step 3 --width 960`, 머리 탐지기 · P1 켬): 탐지기 한 번에 p50 23 ms로 머리 탐지기(19 ms)와 비슷합니다. 프레임 한 장 전체(`ms_chain`)는 탐지기 없이 p50 66 ms(평균 69 ms), 프레임마다 돌리면 103 ms(평균 117 ms), `phone_every` 5면 67 ms(평균 72 ms)였습니다. 프레임마다 돌리면 이 노트북에서 초당 10장 아래로 떨어지므로, 켤 때는 처리 속도와 아래 간격을 함께 정해야 합니다.
- 탐지기 간격(`phone_every`): 기본은 처리하는 프레임마다 돌립니다(머리 탐지기와 같음). 값 묶음의 `phone_every`로 N장마다 돌리게 할 수 있고, 돌지 않은 줄은 구간 판정에서 뺍니다. 구간(1초)마다 한 번 이상 돌아야 하므로 처리 속도가 초당 f장이면 N은 f × `segment_s` 이하여야 합니다. 팀 휴대폰 테이크(초당 10장, 아래와 같은 측정, 합성 터치 조건 C0)에서 N = 5(구간마다 두 번)로 돌리면 기다림이 열린 테이크는 5편 가운데 4편(T13 · T17 · T21 · T23)에서 3편(T13 · T17 · T23)으로 줄었고, `phone_use`가 참인 창은 34개에서 14개로 줄었으며, T18에서 열리던 1번이 없어졌습니다. 탐지기가 휴대폰을 잡는 프레임이 드문드문이라, 덜 돌리면 구간을 놓칩니다.
- 팀 촬영본 측정(평가 전용, 값을 정하지 않음; c150 값 묶음): 재생 실행기(`replay.py --phone-model`, `--step 3 --width 960`)로 34테이크를 돌리면 터치 기록이 없어 `phone_use`가 참인 창은 0개이고, 휴대폰 부분이 맞은 창은 터치 횟수가 없어 모름(`column:tap_count`)으로 남습니다(T13 13창, T17 6, T21 5, T23 10, T18 4). 판단 층은 저장된 관측 줄에 이 재생의 휴대폰 열을 붙여, 논문 실험의 합성 터치 조건 7개(C0~C6, C6 = 터치 기록 없음)로 창 판단을 다시 돌려 셉니다. 휴대폰 · 통화 5테이크 가운데 3-2 기다림이 열린 테이크는 C0 · C4에서 4편(T13 · T23은 통화: 머리 길, T17 · T21은 손에 든 휴대폰: 손 길), C1에서 3편, C3 · C5에서 1편, C2 · C6에서 0편입니다. T17 · T21은 휴대폰을 내려다보며 얼굴을 놓치지만 머리 상자가 남아 화면을 보지 않음으로 셉니다. T19(휴대폰을 보며 조작, 휴대폰이 프레임 아래쪽)는 탐지기가 휴대폰을 한 프레임도 잡지 못했습니다. 다른 29테이크에서는 T18(두리번 + 머리 긁음)에서 C0 · C4에 1번씩 열렸습니다(머리 상자에 닿은 휴대폰 상자; 눈으로 확인하지 않음). 이 수치와 아래 '탐지기 간격'의 수치는 손 점의 보임 정도를 읽지 않던 코드(2026-11-22)로 잰 것입니다. 지금 코드는 `hand_vis_min`이 없으면 손 길을 판정하지 않으므로, 손 길로 열린 T17 · T21의 결과는 지금 기본값의 결과가 아닙니다. 값을 정한 뒤의 결과는 아직 재지 않았습니다.
- 회사 단말 영상 측정(카메라 값 150의 132편: 서서 쓰는 92편 · 앉은 40편, 창 2,282개; 터치 기록이 없어 터치 없음으로 놓고 셈): 휴대폰 길이 켜진 창은 0개(`phone_every` 1과 5 모두)였고, 같은 방법으로 센 일행 길(`consulting_companion`)은 44개(1.93 %, 10편)였습니다. 휴대폰 상자는 23,506프레임 가운데 26프레임에서 나왔고 주 사용자에게 닿은 것은 5프레임이라, 휴대폰이 구간 2개를 채운 창이 없었습니다. 이 영상에 휴대폰 결제가 있었는지는 라벨이 없어 모릅니다. 이 수는 휴대폰 길 조건을 옮긴 평가 스크립트로 셌습니다. 지금 코드의 조건은 그보다 좁아서(손 길의 고개 방향, 다른 머리 상자와의 겹침) 켜지는 창이 늘 수 없습니다.
- 결제에 휴대폰을 쓰는 손님도 이 길이 켜질 수 있습니다. 화면을 보며 손에 든 경우는 손 길에서 빠지지만, 얼굴 앞에 든 휴대폰은 머리 길로 셉니다. 결제 화면의 누름이 터치 없음 조건으로 거르는지는 터치 기록이 있는 녹화로 재지 않았습니다.
- `phone_use`의 거짓은 '주 사용자에게서 휴대폰 상자를 못 봄'입니다. 탐지기가 보이는 휴대폰을 놓쳐도 거짓이 됩니다(T19). 기다림은 참일 때만 열리므로 결정은 바뀌지 않습니다. 열린 기다림은 휴대폰이 사라져도 다음 터치까지 유지됩니다(일행 길과 같음).

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
   - 두 태그가 함께 맞고 근거 사건 수가 같을 때(위 설계 노트 인용의 '동점' 줄, `[설계 제안]`). 수가 다르면 많은 쪽이 `name`이 되고 다른 쪽은 `alternatives`에 들어갑니다

   얼굴이 사라지는 것은 뒤돌아봄의 단서이므로, 얼굴 보임 비율이 낮아도 뒤돌아봄 태그는 막지 않습니다. `none`은 모든 태그가 관측된 단서로 빠졌을 때만 냅니다. 그래서 선택 열이 하나도 없는 지금의 `observations.csv`만 넣으면, yaw가 0이 아닌 얼굴 프레임이 하나라도 있는 한 출력은 `unknown`입니다(동행자 쪽을 몰라 상의 태그를 뺄 수 없음).

`check_output`은 출력의 형식도 봅니다. `window_s`는 유한한 [시작, 끝](시작 ≤ 끝)이어야 하고, `quality`의 두 비율은 0~1이어야 합니다(프레임이 없는 창은 `unknown`과 빈 값). 표시 문구는 이름마다 정해 둔 문구여야 하고(자유 문장 없음), 대안마다 이 창의 근거 사건이 있어야 합니다. 확정 `confidence`를 가진 대안도 `track_conf_min`을 지켜야 합니다. 형식이 틀린 출력은 예외 대신 문제 목록으로 돌려줍니다.

상태 수명: 창은 `t_end`와 함께 밀립니다. 창 안의 근거 사건이 `min_events`개 이상이면 상태가 시작됩니다. 고개 돌림은 첫 줄이 창 밖으로 나가면 근거에서 빠지고, 이어지는 상태(뒷사람 · 머묾 등)는 창 안 부분이 조건을 못 채우면 빠집니다(`window_s` = 만료 창). 반대 근거(터치, 뒤에 선 사람, 몸 이동)가 창에 들어와도 풀립니다.

### 선택 열 (2026-10-22부터 `columns.py` · `touch.py`가 만듦)

규칙이 쓰는 선택 열은 재생 · 실시간 실행기가 프레임마다 만듭니다(`run.py`의 `observations.csv`에는 없음). 사건은 값이 있는 곳에서 찾고, 본 근거는 열이 일부 줄에서 빠져도 씁니다. 어떤 단서가 '없다'는 결론은 그 열이 창의 모든 줄에 있을 때만 냅니다(입 움직임 · 어깨 위치는 얼굴 · 몸이 보인 프레임마다 값이 있어야 함). 그렇지 않으면 0으로 채우지 않고 결측으로 봅니다. 몸 움직임은 축마다 보고, '제자리'는 몸 프레임마다 두 축 값이 다 있고 두 번 이상 관측돼야 판단합니다. 횟수 열은 명세 `TouchFeatures`처럼 0 이상의 정수여야 하고, 다른 값이 오면 오류를 냅니다(빈칸은 결측). 기준값과 출처는 위 '[파일럿] 값과 출처'에 있습니다.

| 열 | 뜻 | 만드는 곳 |
|---|---|---|
| `people_behind_count` | 주 사용자 뒤에 선 사람 수: 이 프레임의 머리 상자 가운데 트랙의 역할이 `behind`인 것(아래 '머리 트랙과 역할'). 주 사용자 말고 다른 머리가 없으면 0. 뒤 사람인지 모르는 머리가 있으면 빈칸(결측). 멈춰 섰는지는 사건 층(`stay_min_s`)이 봄 | `columns.py`(H1 머리 상자). H1 파일이 없으면 열이 없음(결측) |
| `companion_box` | 트랙의 역할이 `companion`인 머리 가운데 이 프레임에서 가장 큰 상자 `(x0, y0, x1, y1)`, 화면 비율. 다른 머리가 모두 동행자가 아니라고 정해지면 `None`. 동행자는 없고 역할을 모르는 머리가 있으면 그 줄에 이 열을 넣지 않음(사건 층은 '동행자 모름'으로 읽음). `rows.csv`에서는 두 경우 모두 빈칸이라 `head_boxes`의 역할로 가름 | 같은 곳 |
| `mouth_motion` | 입 · 턱 blendshape 27개(`mouth_dials`) 가운데 기준선에서 가장 많이 바뀐 값. 기준선은 같은 얼굴 연속 구간의 직전 `mouth_baseline_s`초 중앙값입니다(사람별 기준선을 뺀 변화만 씀). 얼굴을 못 본 프레임, 연속 구간이 `mouth_baseline_s`보다 짧은 동안, blendshape를 끈 실행은 빈칸 | `columns.py`(MediaPipe blendshape, 실행기에 `--blendshapes`를 줄 때만 켬) |
| `shoulder_cx` · `shoulder_cy` | 어깨 두 점(11 · 12)의 가운데, 화면 비율. 몸을 못 본 프레임은 빈칸 | `columns.py`(몸 점) |
| `aid_owner` · `aid_top_class` · `aid_any_score` · `aid_wheelchair_score` · `aid_kind` · `aid_class_scores` · `aid_box` · `aid_count` | 보조기구 탐지기를 켰을 때만(위 '보조기구 입력'): 주 사용자 상자의 판정(`yes` = 그 상자의 가장 높은 클래스가 네 보조기구 가운데 하나, `no` = 기준점은 있는데 `pedestrian`이거나 품는 상자가 없음, `unknown` = 기준점이 없음), 그 상자의 가장 높은 클래스, 목발 · 지팡이 · 보행기 · 휠체어 점수 가운데 가장 큰 값, 휠체어 점수, 어느 쪽 보조기구인지(`wheelchair` · `standing`), 다섯 클래스 점수(JSON 한 칸), 상자, 프레임의 사람 상자 수(`aid_score_min` 이상)와 그 가운데 `aid_person_min`을 넘는 수. 기준값을 적용하지 않음 | `columns.py`(`aid_columns`), `app/inference/aid.py` |
| `aid_head_score` · `aid_head_class` · `aid_head_box` | 보조기구 탐지기를 `aid_rule` `head_centre` · `head_centre_carry`로 켰을 때만(위 '세 읽기'): 주 사용자 머리 상자 가운데를 품은 보조기구 클래스 상자(`pedestrian`을 뺀 클래스마다 따로 거르고 NMS를 한 상자)의 가장 큰 점수, 그 클래스와 상자. 머리 상자는 있고 품는 상자가 없으면 0과 빈칸 둘, 머리 상자가 없으면 모두 빈칸(`head_centre_carry`에서는 따라간 상자가 맞은 프레임이면 그 상자의 점수 · 클래스 · 상자). 기준값을 적용하지 않음 | `columns.py`(`aid_head_columns`, `AidCarry`), `app/inference/aid.py`(`per_class`) |
| `aid_head_from` | `aid_rule` `head_centre_carry`일 때만: 그 줄 값이 어디서 왔는지. `head` = 주 사용자 머리 상자가 있는 줄(`head_centre`와 같은 값), `carried` = 직전 머리 줄의 상자를 따라가 읽은 값, 빈칸 = 값 없음 | `columns.py`(`AidCarry`) |
| `phone_owner` · `phone_at` · `phone_score` · `phone_box` · `phone_count` | 휴대폰 탐지기를 켰을 때만(아래 '휴대폰 입력'): 주 사용자의 휴대폰인지(`yes` = 휴대폰 상자가 주 사용자 머리 상자에 닿고 다른 머리 상자가 그 상자를 더 많이 담지 않음, 또는 어느 머리에도 걸치지 않고 주 사용자 손 상자에 닿음, `no` = 머리 상자가 있고 휴대폰이 없거나 모두 닿지 않음(탐지기가 놓친 휴대폰도 `no`), `unknown` = 머리 상자가 없거나, 머리에 닿지 않은 휴대폰이 있는데 몸 점이 주 사용자 것이 아니거나 손 점을 확인하지 못함(`hand_vis_min`이 없을 때 포함)), 닿은 곳(`head` · `hand`), 그 휴대폰의 점수와 상자, 프레임의 휴대폰 상자 수. 기준값을 적용하지 않음 | `columns.py`(`phone_columns`), `app/inference/phone.py` |
| `iod_ratio_user` | 주 사용자의 눈 사이 거리(`iod_px`) ÷ 같은 사용자의 기준점부터 직전 얼굴 줄까지의 `iod_px` 가운데 위쪽 절반의 중앙값(터치 로그가 있으면 비가 `approach_ratio_min`을 넘은 줄은 뺌). 기준점 = 주 사용자 트랙의 시작과 터치 로그 세션의 시작이고, 터치 로그가 있으면 그 세션의 첫 누름. 다른 사람의 얼굴, 기준이 아직 없는 줄, 첫 누름 전은 빈칸(위 '장면 태그 6개') | `columns.py`(`FaceSizeRef`) · `chain.py` |
| `head_ratio_user` | 주 사용자의 머리 상자 높이 ÷ 같은 사용자의 기준 머리 상자 높이(`HeadSizeRef`). 기준점과 규칙은 `iod_ratio_user`와 같고, 기준에서 빼는 경계는 `head_approach_ratio_min`. 주 사용자 상자가 없는 줄, 기준이 아직 없는 줄, 첫 누름 전은 빈칸. 머리 탐지기가 돌지 않으면 열이 없음 | `columns.py`(`HeadSizeRef`) · `chain.py` |
| `dpitch_user_deg` | 주 사용자의 고개 숙임(`pitch_deg`, + = 아래) − 같은 사용자의 기준점 뒤 첫 얼굴 줄의 `pitch_deg`. 기준점은 `iod_ratio_user`와 같음(같은 자리에서 다시 잡은 트랙은 이어 씀, 머리 탐지기가 없으면 아무도 `track_max_gap_s`보다 오래 안 보인 뒤 다시 잡음). 다만 제자리에서 이어 붙인 트랙(`main_user_stitched`)도 이어 씀(깊이 숙여 끊긴 트랙의 첫 얼굴이 숙인 각도일 수 있음). 다른 사람의 얼굴, 각도 없음, 첫 누름 전은 빈칸. `face_approach`의 고개 숙임 거르기가 읽음(`features.py`의 세션 첫 얼굴 대비 `dpitch_start_deg`는 관측 열로 남음) | `columns.py`(`PitchRef`) · `chain.py` |
| `main_user_reacquired` | 교체 줄에만: 새 주 사용자 상자가 끝난 트랙의 마지막 상자와 `track_iou_min` 이상 겹치고 자리가 비지 않았으면(`main_user_body_gap_s` ≤ `track_max_gap_s`, 이 열이 없으면 `main_user_body_kept`) 참(같은 자리에서 다시 잡음: 모자 · 깊은 숙임 · 카메라 멈춤), 아니면 거짓, 상자가 없으면 빈칸 | `columns.py`(`MainUserChange`) |
| `main_user_body_gap_s` | 교체 줄에만: 끝난 트랙의 마지막 머리 상자부터 이 줄까지 그 상자도 몸도 이어서 안 보인 가장 긴 시간(`body_unseen_s`, 마지막 상자부터 지난 시간을 넘지 않음). `body_unseen_s`가 없는 줄이 끼면 빈칸 | `columns.py`(`MainUserChange`) |
| `main_user_new_start_s` · `main_user_start_shift` · `main_user_start_size` · `main_user_stitched` | 교체 줄에만: 끝난 트랙의 마지막 머리 상자부터 새 트랙의 첫 상자(다른 머리로 먼저 잡혔으면 그때)까지의 초(0 이하 = 두 머리가 함께 보임, 두 사람), 그 두 상자의 위치 차(가로 차 ÷ 앞 상자 폭, 세로 차 ÷ 앞 상자 높이의 유클리드 거리)와 크기 차(\|ln(첫 상자 높이 ÷ 마지막 상자 높이)\|). `main_user_stitched` = 새 트랙이 `track_max_gap_s` 안에 시작했고 위치 차 ≤ `stitch_shift_max`, 크기 차 ≤ `stitch_size_max`이면 참(제자리에서 끊긴 같은 사용자), 아니면 거짓, 경계값이나 상자가 없으면 빈칸 | `columns.py`(`MainUserChange`) |
| `main_user_prev_track` · `main_user_gap_s` · `main_user_body_kept` | 같은 터치 로그 세션에서 앞 주 사용자 트랙 다음에 새 주 사용자 트랙이 시작된 줄에만: 앞 트랙 번호, 앞 트랙의 마지막 머리 상자부터 지난 초, 그사이 모든 줄에 몸이 보였는지(누구의 몸인지는 모름). 다른 줄은 빈칸. H1 파일이 없으면 열이 없음 | `columns.py`(`MainUserChange`) |
| (관측만) `main_user_prev_h` · `main_user_new_h` · `main_user_h_ratio` · `main_user_new_was_role` · `main_user_new_rel_dist` · `main_user_new_growth` | 같은 줄의 크기 근거(기준값 없음): 앞 주 사용자의 마지막 머리 상자 높이와 새 주 사용자의 머리 상자 높이(화면 비율), 새 ÷ 앞. 새 트랙이 바뀌기 전에 다른 머리로 보였으면 그때의 마지막 역할(`head_boxes`의 `role`), 마지막 `rel_dist_med`(앞 주 사용자 높이 ÷ 그 머리 높이, 1보다 크면 더 작음 = 더 멂), 그리고 지금 높이 ÷ 주 사용자가 아니던 동안 직전 `role_window_s`초 높이의 중앙값(커진 정도). 다른 머리의 기록은 `track_max_gap_s`보다 오래 안 보이면 지웁니다. 뒤에 선 사람은 앞으로 나와야 다음 사용자가 되므로, 커진 정도가 1에 가깝고 `rel_dist`가 1보다 크면 뒤 사람 크기 그대로 주 사용자가 된 것입니다. 읽는 규칙 없음 | `columns.py`(`MainUserChange`) |
| `tap_count` · `miss_tap_count` | 직전 줄 이후의 누름 · 버튼 밖 누름 횟수(아래 '터치 로그'). 이름과 뜻은 `contract/frontend-backend.openapi.yaml`의 `TouchFeatures`를 따르고(0 이상의 정수), 세는 구간만 프레임 간격. 터치 로그가 관측하지 않은 구간의 줄은 빈칸(아래 '터치 로그')이고, 대상 정보가 없는 누름이 든 구간은 `miss_tap_count`가 빈칸 | `touch.py` · `chain.py`(재생. 실시간 실행은 줄에 비워 두고, `--serve`로 받은 터치 창의 횟수를 창마다 줄 사본에 놓음: `touch_entry.place_touch`) |
| (관측만) `head_count` · `primary_box` · `primary_score` · `primary_from` | 머리 상자 수, 주 사용자 머리 상자 · 점수 · 고른 방법(`track` = 앞 프레임부터 이어진 주 사용자 트랙, `face` = 이 프레임에서 얼굴을 품은 상자로 새로 고름, `largest` = 이 프레임에서 가장 큰 상자로 새로 고름). 주 사용자 트랙이 살아 있지만 이 프레임에 상자가 없으면 `primary_box`는 빈칸. 읽는 규칙 없음 | `columns.py` |
| (관측만) `primary_track` | 주 사용자 트랙 번호. 트랙이 살아 있는 동안은 이 프레임에 상자가 없어도 적음 | `columns.py` |
| `face_in_primary` | Face Landmarker가 따라가는 얼굴의 중심이 주 사용자 머리 상자 안에 있는지(참 · 거짓). 얼굴이나 주 사용자가 없으면 빈칸. 주 사용자 트랙은 살아 있는데 이 프레임에 그 상자가 없으면, 얼굴 중심이 다른 트랙의 머리 상자 안에 있을 때 거짓이고 어느 머리 상자 안에도 없을 때 빈칸(머리 탐지기가 주 사용자 머리를 놓쳤을 수 있음). 거짓이면 그 얼굴은 다른 사람의 것이라, 그 줄의 얼굴 값 15개(`columns.FACE_VALUE_COLUMNS`: 고개 각도 · 눈 사이 거리 · 얼굴 위치 · 얼굴 상자 밝기와 선명도)와 `mouth_motion`을 비움. 사건 층은 이를 주 사용자의 값이 아닌 결측으로 읽음 | `chain.py`(`columns.FACE_VALUE_COLUMNS`) |
| (관측만) `face_track` | 얼굴 중심을 품은 가장 큰 머리 상자의 트랙 번호(Face Landmarker가 누구의 얼굴을 따라가는지). 없으면 빈칸 | `chain.py` |
| (관측만) `head_boxes` | 이 프레임의 모든 머리 상자(H1 순서). 상자마다 `track`(트랙 번호) · `cx` · `cy` · `w` · `h`(화면 비율) · `score`(H1 점수) · `role`(`primary` · `companion` · `behind` · `other` · `unknown`) · `rel_dist` · `lateral`(이 프레임의 단서) · `rel_dist_med` · `lateral_med`(직전 `role_window_s`초 중앙값). 주 사용자 상자와 계산할 수 없는 단서는 `null`. `rows.csv`에는 JSON 한 칸으로 쓰고, 머리가 없으면 `[]` | `columns.py` |
| (관측만) `head_dir_middle` · `head_dir_up` · `head_dir_left` · `head_dir_right` · `head_dir_back` | 주 사용자 머리의 P1 카메라 시점 확률(중간 · 위 · 좌 · 우 · 뒤; AI Hub 70 '촬영방향' = 카메라가 사람을 보는 방향, 고개 방향이 아님). 읽는 규칙 없음. 한계는 아래 'P1 표시 이름과 한계' | `columns.py`(P1) |

### 머리 트랙과 역할 (2026-11-04부터)

머리 상자는 프레임마다 트랙으로 이어집니다. 상자 하나는 직전 상자와 가장 많이 겹치는 살아 있는 트랙에 붙고(IoU가 큰 순서, `track_iou_min` 이상), 붙을 트랙이 없으면 새 트랙이 됩니다. SORT의 연결 단계를 줄여 쓴 것으로, 칼만 예측 없이 직전 상자와 견주고 헝가리안 대신 IoU 큰 순서로 배정합니다. `track_max_gap_s`초 넘게 상자가 없는 트랙은 끝납니다.

주 사용자는 트랙입니다. 주 사용자 트랙이 살아 있는 동안은 그 트랙이 주 사용자이고, 트랙이 끝난 뒤에만 `primary_rule`(`[파일럿]` 규칙)로 새로 고릅니다. 기본값 `face_then_largest`는 Face Landmarker가 따라가는 얼굴의 중심(`face_cx`, `face_cy`)을 품은 머리 상자 가운데 가장 큰 것을 고르고, 그런 상자가 없으면 가장 큰 상자를 고릅니다(같으면 화면 가운데에 가까운 것). 고른 뒤에는 Face Landmarker가 따로 얼굴을 따라갑니다. 얼굴 중심이 `primary_box` 밖에 있는 프레임은 얼굴이 다른 사람의 것이므로, 그 프레임의 얼굴 값과 입 움직임을 비우고 `face_in_primary`를 거짓으로 적습니다(위 '선택 열'). 주 사용자 트랙이 살아 있지만 그 프레임에 상자가 없을 때(`track_max_gap_s` 안)도, 얼굴 중심이 다른 트랙의 머리 상자 안에 있으면 똑같이 비우고 거짓으로 적습니다. 얼굴 중심이 어느 머리 상자 안에도 없으면 머리 탐지기가 주 사용자 머리를 놓친 경우일 수 있어서, 값을 그대로 두고 `face_in_primary`를 빈칸으로 적습니다. 터치 로그의 `sessionId`가 바뀌면 트랙 · 주 사용자 · 단서 기록을 처음부터 다시 시작하고, 그 세션의 첫 프레임에서 주 사용자를 새로 고릅니다(새 세션은 처음부터 다시 판정). 트랙 번호는 한 실행 안에서 겹치지 않게 이어서 셉니다.

주 사용자가 아닌 트랙마다 주 사용자와 함께 보인 프레임에서 단서 두 개를 잽니다.

- 상대 거리 `rel_dist` = 주 사용자 머리 상자 높이 ÷ 그 머리 상자 높이(주 사용자 = 1). 핀홀 카메라에서 머리 상자 크기는 카메라와의 거리에 반비례하므로, 머리 크기가 비슷하면 카메라에서 떨어진 거리를 주 사용자와 견준 값이 됩니다. 머리가 작은 사람(아이)은 실제보다 멀게 읽힙니다. 폭 대신 높이를 쓰는 까닭은 화면 왼쪽 · 오른쪽 끝에서 높이가 덜 잘리기 때문입니다.
- 옆 거리 `lateral` = (그 머리 중심 x − 주 사용자 머리 중심 x) ÷ 주 사용자 머리 높이, 픽셀 단위. 부호가 있고 +는 화면 오른쪽입니다. 화면 위의 가로 차를 주 사용자 머리 크기로 잰 값이고, 그 사람의 머리 크기로 잰 옆 거리(옆 거리 × 상대 거리)는 규칙에 쓰지 않습니다(평가 도구의 `lateral_x_rel`에만 있음).

트랙마다 직전 `role_window_s`초 단서의 중앙값으로 역할을 정합니다. 주 사용자가 바뀌면 단서 기록을 새로 시작합니다.

| 역할 | 조건(모두 중앙값) |
|---|---|
| `companion` 동행자 | 상대 거리 ≤ `companion_rel_dist_max`('비슷한 크기'), \|옆 거리\| ≥ `companion_lateral_min`('옆') |
| `behind` 뒤 사람 | 상대 거리 > 1('주 사용자보다 작은 상자'), 상대 거리 ≥ `behind_rel_dist_min`('뒤쪽'), 동행자가 아님 |
| `other` | 동행자도 뒤 사람도 아니라고 정해짐(예: 주 사용자보다 큰 머리가 옆에 있지 않음) |
| `unknown` | 경계값이 없거나 창 안에 단서가 없어 정할 수 없음 |

경계값 3개는 출처가 없어 값이 없습니다. 녹화로 값을 정하지 않고, 값 묶음별 곡선으로 보고합니다(촬영본은 평가에만 씀). 값 묶음 파일의 `chain`에 값을 넣기 전에는 동행자 여부와 주 사용자보다 작은 머리의 뒤 사람 여부가 `unknown`입니다. 그래서 다른 머리가 보이는 프레임은 `companion_box` 열이 빠지고, 주 사용자보다 작은 머리가 보이면 `people_behind_count`도 빈칸입니다. 단서는 그때도 `head_boxes`에 프레임마다 남습니다. 팀 논문 실험은 값 묶음에 `[파일럿]` 시작값(`companion_rel_dist_max` · `behind_rel_dist_min` 1.5, `companion_lateral_min` 0.5)을 넣어 평가했습니다(재현 영상의 뒷사람 정밀도 0.908 · 일행 정밀도 1.000, 팀 논문 표 1). 이 값은 회사 단말 영상에서 계산한 값이 아닙니다.

넓이 비 0.5배('비슷한 크기')와 머리 폭 3.0배 거리('옆') 조건은 2026-11-04에 뺐습니다. 10-28 팀 촬영(평가 전용)에서 넓이 비 조건은 옆의 일행을 자주 뒤 사람으로 셌고, 3.0배 거리 조건은 주 사용자 바로 뒤에 선 사람도 모두 품었습니다.

평가 도구(`tools/companion_eval.py`)는 사람 라벨이 있는 녹화로 이 단서들을 잽니다. `replay`는 영상 폴더의 녹화를 이 파이프라인으로 재생하고, `analyze`는 라벨과 이어 단서 분포 · 경계 후보별 라벨 일치율 · 주 사용자가 라벨의 사용자인 프레임 비율을 CSV와 그림으로 냅니다. `analyze --behind-only`는 일행 조건 없이 상대 거리만으로 뒤 사람인지 아닌지를 가를 때의 일치율도 냅니다. `sheets`는 상자 · 트랙 · 역할을 그린 확인 시트를 만듭니다. 시트에는 찍힌 사람이 나오므로 저장소에 두지 않습니다. 도구는 경계값을 고르지 않습니다. 쓰는 법은 파일 머리말에 있습니다.

### P1 표시 이름과 한계

P1은 머리 크롭 한 장을 보고 카메라가 그 사람을 어느 쪽에서 찍었는지 고르는 카메라 시점 분류기입니다. AI Hub 70의 '촬영방향' 라벨(데이터 설명: "인물을 바라보는 카메라 시선")로 학습했고, 다섯 클래스 중간 · 위 · 좌 · 우 · 뒤가 그 라벨입니다. 라벨에는 사람이 어디를 보는지가 없으므로 P1 확률은 고개 방향이나 시선을 잰 값이 아닙니다. 그래서 콘솔 안내와 이 README는 P1을 카메라 시점 분류기라고 부릅니다. 코드 이름(`head_direction.py` · `HeadDirection` · `DIR_CLASSES`)과 열 이름(`head_dir_*`)은 바꾸지 않았습니다.

- 교차표(2026-10-30): 화면 위 카메라 영상 41개(2026-10-28 팀 촬영본 35개, 회사 제공 영상 6개; 비공개, 저장소 밖)를 재생해 P1 클래스를 MediaPipe yaw · pitch와 맞대어 셌습니다. 중간과 위는 고개 자세보다 사용자의 키(얼굴이 카메라 높이에 가까운지)로 갈렸습니다. 팀 촬영본에서 P1이 중간을 내고 같은 머리의 얼굴 각도도 잰 프레임 614개 가운데 581개가 얼굴이 카메라 높이에 가까운 서 있는 참가자 한 명의 것이었습니다. 그래서 중간을 '올려다봄' 같은 고개 방향 이름으로 바꿔 읽을 근거는 없습니다.
- 관측만: 상황 규칙과 규칙표는 `head_dir_*`를 읽지 않습니다.
- 공개 데이터 성적: AI Hub 70 시험 분할에서 P1의 '뒤' 재현율은 30.2 %였습니다.
- AI Hub 70 관련 숫자는 과학기술정보통신부의 재원으로 한국지능정보사회진흥원의 지원을 받아 구축된 「안내 로봇 인터랙션 멀티모달」(AI 허브, aihub.or.kr)을 활용한 결과입니다.

### 터치 로그 (`touch.py`)

- 입력: 주문 화면 개발 모드의 'JSON 내보내기' 파일(`touchLog.ts`의 `SavedLog`). 원시 기록은 계약이 아니라 로컬 초안입니다(`docs/Touch-Log-Review.md` 1 · 7장).
- 시간축: 녹화 옆 `<영상>.clock.json`이 있으면 터치 시각 = (`occurredAt` − `first_frame.wall_epoch_ms`) ÷ 1000초이고, `--start-offset`은 그 위에 더하는 보정입니다. 시계 파일이 없으면 `--start-offset` = 터치 로그 첫 기록의 영상 시각입니다(촬영 대본 §4 '시각 맞추기', 저장소 밖).
- 세는 방법(`[설계 제안]`: 기준은 팀 항목 T01 · T02 · T08에서 정하므로 프론트의 요약 코드 `touchLogSummary.ts`를 따름): 누름 = `pointer_start`, 버튼 밖 누름 = `data.target`이 `null`인 `pointer_start`(요약의 `outsideTargetPresses`; 비활성 버튼을 누른 것은 버튼 밖이 아님), 되돌아감 = `review`에서 `menu`로 가는 `screen_enter`(`← 메뉴 더 고르기`와 로고 링크). `complete`에서 `menu`는 새 주문이라 세지 않습니다. `repeat_tap_count` · `dwell_ms`는 이 모듈에서 세지 않습니다(주문 화면이 파일럿 기준으로 계산함, 팀 항목 T04 · T05). 빗나감 뒤 바로 고침(`near_miss_fix_count`) = 버튼 밖 누름 뒤 같은 세션의 다음 누름이 그 누름의 가장 가까운 버튼 목록(`nearestCandidates`) 안의 버튼이면 1회(팀 항목 T03 · T07). 대상 정보가 없는 누름이 구간에 있으면 `miss_tap_count` · `near_miss_fix_count`는 빈칸입니다.
- 관측 구간: 첫 기록(또는 `session_start` · `session_resume`)부터 다음 `session_end` · `session_suspend`까지를 관측한 것으로 보고, 마지막 기록 뒤 멈춤 기록이 없으면 내보낼 때까지 열려 있던 것으로 봅니다. 구간이 관측 구간에 통째로 들 때만 횟수를 내고(안에 터치가 없으면 0), 첫 기록 전이나 걸친 구간은 결측입니다. 로그가 1,000개(`touchLog.ts`의 상한)면 앞 기록이 잘렸을 수 있어 경고하고(`meta.touch.warnings`), 시계 파일 없이 `--start-offset`으로는 놓을 수 없어 오류입니다. 세션 목록(`meta.touch.sessions`)과 관측 구간(`spans`)도 기록합니다.

## 테스트

```powershell
.venv\Scripts\python.exe -m unittest tests.test_vision tests.test_situation tests.test_vision_chain tests.test_vision_links -v
```

- 판단 층 형태(`tests/test_vision_links.py`의 `DecisionViewTests` · `BackendReadsTheViewTests`): 창 결과의 `extension.decision_situation`이 창 기록의 상황과 같고 기존 키(`tag` · `evidence_ids`)가 남는지, `observations`의 `gaze` · `face_seen` · `scene_tags`, 값 묶음이 없을 때를 봅니다. 저장소의 backend 판단 층 코드(`rule_table.decide`)를 따로 띄운 Python으로 돌려, 새 형태는 아는 상황으로 읽혀 두리번 태그가 4-2의 멈춤 기준을 낮추고 옛 키는 상황이 없는 창으로 읽히는지 확인합니다. backend 파일이 없으면 건너뜁니다.
- 터치 입구(같은 파일): 본문 검사(시간대 없는 시각 · 끝이 시작보다 앞 · 정수가 아닌 횟수 · 빈 세션 · 빈 화면), 보고 창의 세션 · 누름 · 정리, 터치 횟수 배치(0인 창 · 안에 든 창 · 시작에 걸친 창 · 빈 구간 · 겹침)와 받은 본문이 같은 배치가 되는지, 그 배치로 '터치 없음' 태그가 정해지는지를 봅니다. 실행기의 창이 받은 터치를 읽어 같은 줄의 재생과 같은 상황을 내는지, 새 세션이 자기 줄만 읽는지, 누름 보고와 새 세션이 얼굴 크기 기준에 닿는지(`FrameChain`), 가짜 카메라로 돌린 `run_live`가 보고 창이 닿은 창에서만 '터치 없음'을 아는지도 봅니다. 답(받음 · 형식 오류 · 첫 프레임 전 · 카메라 멈춤 · `/status` · HTTP의 403 · 404 · 400 · 500)마다 비전 키가 하나도 없는지 확인하고, 허용한 출처의 CORS 머리글 · 사전 요청과 Private Network Access 머리글 · 옛 경로 `/window`의 404, 명령줄 스위치도 봅니다. 첫 세션도 자기 줄만 읽는지, `Host`가 이 입구가 아니면 메서드와 관계없이 403인지, `/status`에 CORS 머리글이 없는지, 음수 · 숫자가 아닌 `Content-Length`가 400인지, 거절한 출처와 `Host`가 한 번씩만 알림 줄을 남기는지, 시작 줄에 `VITE_AI_ENGINE_URL=` 줄이 그대로 있는지, 기간 없는 실행이 처리 시간 줄을 남기지 않는지, `--backend-url`을 주면 콘솔의 판단 칸이 '로컬 규칙표'인지도 봅니다. 프레임 시각은 가짜 시계(테스트가 정한 시스템 시각)입니다.
- 상황 태그 보내기(같은 파일): 시험 backend(127.0.0.1)로 본문의 키 6개와 경로, 세션 ID의 경로 인코딩, 터치 창이 세션을 알리기 전에는 보내지 않는지, 한 번에 풀린 창들이 느린 backend에도 모두 순서대로 닿는지, 앞 묶음을 보내는 동안 쌓인 묶음 가운데 아직 보내지 않은 묶음은 새 묶음이 통째로 바꾸는지, 실패를 세고 다시 보내지 않는지, backend가 404 · 410으로 답한 세션의 창은 새 세션이 올 때까지 보내지 않고 따로 세는지, 연결이 안 되거나 답이 없는 backend에서도 `run_live`가 모든 프레임과 창을 처리하는지, `--backend-url`이 `--serve`를 요구하는지를 봅니다.
- 창을 판단하는 때(같은 파일의 `TouchPacedEvaluationTests`): 세션이 알려진 뒤 터치 창마다 그 창이 덮는 1초 구간이 그 터치 창이 온 프레임에서 판단되고(2초 터치 창은 구간 두 개, 2026-11-26부터의 1초 터치 창은 구간 하나) 터치를 빠짐없이 읽는지('터치 없음' 단서가 `column:tap_count`로 모름이 되지 않고 두리번이 나옴), 보낸 묶음의 창이 하나도 빠지지 않고 터치 창마다 바로 뒤따르며 본문 키가 그대로인지, 누름이 있는 창이 그 누름으로 판정한 창이 되는지, 터치가 0인 창에서 일행 상의가 판정되는지, 터치 창이 끊기면 기다리던 구간이 기억 구간 한도에서 풀리고 기다리는 구간 수 · 기억하는 줄(`2 × keep_s − segment_s` 이하) · 함께 남는 터치 보고가 한도 안에 머무는지, 세션이 없으면 전처럼 자기 간격으로 판단하는지, 앞 세션의 터치 창이 새 세션의 구간을 풀지 않는지를 봅니다. 1초 보고의 횟수가 그 보고의 마지막 줄에 놓이는지도 봅니다(`PlaceTouchTests`).
- 받은 터치 창에 답하는 때(같은 파일의 `SettlingTests`, `HttpTests` · `TagSenderTests` · `TouchEntryTests`의 새 시험): 창 끝과 같거나 그 뒤의 프레임에서만 마치는지(판단할 구간이 없는 프레임 포함), 푼 창이 없으면 바로 마치는지, 시험 backend가 답을 붙잡는 동안은 마치지 않고 답한 뒤에 마치는지, 창 끝 전에 나간 구간이 끝난 뒤에 마치는지, 새 묶음으로 바뀐 묶음은 앞 묶음이 끝난 뒤에 마치는지, 번호가 한 flush에만 넘어가는지, 받은 순서와 끝나는 순서가 다른 두 창이 저마다 자기 끝의 프레임에서 마치고 마친 번호는 1번부터 모두 마친 데까지만 오르는지를 봅니다. 보내기의 `done`이 그 묶음과 앞 묶음이 끝난 뒤 한 번 불리는지(빈 묶음 · 쉬는 보내기 · 끝내는 중 · `close`)도 봅니다. HTTP로는 시험 backend가 그 터치 창이 푼 창을 받고 답한 뒤에 202가 오는지(두 일의 순서), 더 오는 프레임이 없으면 `segment_s` 뒤에 오는지, 카메라 처리가 멈추면 바로 오는지, 거절은 바로 오는지, 답을 기다리는 요청이 있어도 서버를 바로 끌 수 있는지를 봅니다.
- 시험 도구(같은 파일): 도구의 도우미 함수와 기본값, 그리고 가짜 추론(초당 10장)으로 6.5초 돌려 시험 backend가 세션 `smoke`의 창을 받고 줄마다 구간 · 상황 · 터치 단서 판정 여부를 찍는지, 터치 창이 푼 창이 '터치 단서 판정함(터치 창이 온 뒤)'인지, `live/`에 그림이 없는지를 봅니다.

- 휠체어 확인 분류기(같은 파일의 `AidConfirmTests`): 가짜 분류기 세션으로 crop 상자(사방 20 px, 화면 밖은 화면 전체), 여러 파일의 확률 평균과 RGB 순서, 출력 크기가 다른 파일 거절, 머리 상자 · 따라간 상자의 사람 상자 고르기, 실행 옵션 검사를 봅니다. 가짜 탐지기로 돌린 재생에서 옵션이 없으면 창 기록과 `meta.json`에 `aid_confirm`이 없고, 휠체어 확률을 0.9로 읽는 분류기는 휠체어 창을 그대로 두며 0.1로 읽는 분류기는 그 창을 거짓으로 바꾸는지, 겹치는 창에서도 줄마다 한 번만 읽는지 확인합니다. 실시간 실행기(`run_live`)로는 세션 ID 두 개를 보내 두 번째 세션의 첫 창부터 새 동의 전까지 유지된 창이 없는지, 처음 이름이 붙은 세션에서 두 홀드가 끝나는지, 체인이 스스로 찾은 사용자 교체에서 사용자 홀드가 끝나는지, 주 사용자가 떠난 `no_main_user_box` 창과 줄이 없는 `no_frames` 창에서 두 홀드가 끝나는지, 컷과 같은 값은 거짓이 되는지, 2초 늦게 내보낸 창과 `kept_history`로 내보낸 창이 재생과 같은 줄 수와 중앙값을 내는지, 미리 읽기가 창 판단 전에 그 창의 모든 줄을 넘겼고 앞선 줄부터 읽는지, 느린 분류기와 실제 태그 보내기에서 창이 순서대로 빠짐없이 가고 터치 창이 모두 마무리되는지, 읽기마다 예외를 내는 분류기에서 창이 확인되지 않은 창이 되고 로그가 한 줄이며 실행이 끝까지 가는지, 작업 스레드의 다른 예외에도 터치 입구가 멈추고 `meta.json`이 남는지 봅니다. 2026-11-28에 더한 시험: 휠체어 사용자가 화면에 남은 채 다른 사람이 첫 세션이나 두 번째 세션을 시작할 때 그 세션의 어느 창도 홀드되지 않는지, 세션 두 개인 터치 로그의 재생에서 홀드가 새 세션에서 끝나고 그 세션의 줄로 다시 시작하는지, 홀드가 끝난 뒤 미리 읽기가 그 창의 줄부터만 채우는지, 지운 줄의 대기 읽기가 취소되고 기다리던 창이 그 줄을 다시 읽는지, 지운 뒤 끝난 읽기가 값을 남기지 않는지, 오류 기록을 한 번에 찾는지, 분류기가 막혔을 때 프레임 루프가 늦음을 먼저 알리고 늦은 창을 세는지, 분류기가 프레임보다 느릴 때 창마다 재생과 같은 줄 수 · 중앙값 · 답을 내는지 봅니다.
- 관측값 층: 테스트 안에서 만든 가짜 추론 결과(눈꼬리 위치를 정해 둔 얼굴 점, 몸 점, 검출 상자)로 눈 사이 거리 · 시작 대비 비율 · 얼굴 위치 · 연속 구간 · 몸 점 평균 · 밝기를 계산해 정해진 값과 같은지 봅니다. MediaPipe와 모델 파일 없이 돌아갑니다(numpy · OpenCV만 필요).
- 상황 층(`tests/test_situation.py`): 테스트 안에서 만든 합성 관측 줄(초당 10장)로 태그마다 맞는 경우 · 빼는 조건 · `unknown` · 대안 · 동점을 보고, 긴 시간 공백 · 값이 빈 열 · 일부 줄이 빠진 열 · 창 이동(상태 유지와 만료) · 창 시작의 터치 · 창 뒤의 줄 · 얼굴과 몸이 함께 끊긴 돌림도 봅니다. 고개 한 번이 사건 하나인지와 검사 규칙(사건 ID · 관찰 줄의 창 · 고정 문구 · 최소 사건 수 · 대안의 근거 · 창과 품질의 형식)을 확인합니다. `PilotParams`에 기본값이 없는지, `situation.py`에 숫자가 없는지도 봅니다. 장면 태그는 값이나 열이 없을 때의 모름 이유, 창 중앙값 비교, 얼굴 접근 줄을 뺀 얼굴 높이, 사용자 교체(다시 잡았고 이어 붙이기도 한 끊김은 거짓)와 사람 안 보임, 사용자가 바뀐 창의 얼굴 · 머리 상자 · 보조기구 값과 상황 태그 3개의 고개 돌림 · 일행 쪽 고개 · 입 움직임 · 몸 · 머묾(새 사용자 줄만 읽음, 다시 잡음 · 이어 붙임 · 자리 잡기 전 바뀜은 앞 줄도 읽음), 장면 태그가 세 태그의 출력을 바꾸지 않는지, 태그 목록의 검사 규칙, 휴대폰 길(구간 수 · 구간 끝 줄 · 탐지기가 건너뛴 줄 · 구간별 사건 종류 · 터치 · 몸 · 손 길의 고개 방향과 머리 길 · 모름)을 봅니다. 테스트의 값은 합성 프레임용이고 기준값 제안이 아닙니다. 표준 라이브러리만 쓰므로 서버 패키지만 깔린 환경에서도 돌아갑니다(`features.py`와 표시 값을 맞춰 보는 1개만 OpenCV가 없으면 건너뜀).
- 추론까지: 테스트 안에서 만든 빈 화면 프레임으로 MediaPipe 모델을 실제로 돌려 CSV 열 구성, '못 봄' 상태, 처리 시간 기록을 확인합니다(모델 파일 필요).
- 그 밖: 연속 구간 계산, 고개 각도 분해, 실측 초당 장수 공식.
- 녹화 클립의 시각 파일(`<영상>.times.csv`): 완전한 파일만 받아들이고, 번호가 빠지거나 시각이 되돌아가면 오류로 멈추는지 봅니다(3개). 눈 사이 거리가 0인 기준 프레임이면 비율이 빈칸이 되는지도 봅니다.
- 실행 파이프라인(`tests/test_vision_chain.py`, 145개; 필요한 패키지·파일에 따라 일부 건너뜀): 값과 출처(기본값 · 범위 · 값 묶음 파일 · 값이 없는 경계 3개와 장면 태그 경계 5개 · 트랙 잇기 경계 2개 · 손 점 하한 1개), H1 후처리(letterbox · 격자 · 디코딩 · NMS, 점수 거르기 순서가 결과를 바꾸지 않음, ONNX 대신 가짜 세션으로 전체 호출), 휴대폰 탐지기(가짜 세션: 상자마다 가장 높은 클래스 · 점수 하한 · 클래스를 가리지 않는 NMS 뒤 휴대폰만 남김)와 휴대폰 열(머리 상자 · 손 상자에 닿음, 다른 머리 상자가 휴대폰 상자를 더 많이 담으면 주 사용자 것이 아님(같으면 주 사용자), 다른 머리에 걸친 휴대폰은 손에 대지 않음, 남의 몸 점이거나 손 점이 없으면 모름, `hand_vis_min`을 주면 보이지 않거나 visibility가 없는 손 점은 손 상자에서 빠지고 그 입력으로 기다림이 열리지 않음, 값이 없으면 손 길은 판정하지 않고 머리 길은 그대로), 가짜 탐지기로 3-2 휴대폰 길이 기다림을 여는지(탐지기를 N장마다 돌리는 경우, 화면을 보며 든 휴대폰, 얼굴을 놓치고 머리 상자만 남은 손 길, 머리 상자도 없으면 모름, 얼굴을 놓친 통화의 열기와 `hold_timer` 유지, 계약 `basis`의 휴대폰 문장은 측정할 수 없는 창에만 붙음 포함), 사용자가 바뀐 창의 휴대폰 구간(앞 사용자의 통화로 기다림을 열지 않음, 같은 자리 다시 잡음 · 이어 붙임 · 자리 잡기 전 바뀜은 앞 줄도 읽음)과 구간 안에서 바뀐 뒤의 화면을 보지 않음 · 규칙표의 고개 방향 게이트 · `measurable`의 얼굴 · `vision`의 얼굴 · 몸 · 입 값(새 사용자 줄만 읽음; 다시 잡음 · 이어 붙임은 앞 줄도 읽음)과 창의 첫 줄에서 바뀐 창(창 앞의 맥락 줄을 읽지 않음), 손 길의 '화면을 보지 않음'(고개 방향 게이트 · 얼굴 없는 머리 상자 · 남의 얼굴 · 머리 상자가 빠진 프레임의 맞춰지지 않은 얼굴은 양쪽 방향 모두 방향 근거가 아님 · 규칙표 게이트는 모든 얼굴을 읽음 · 화면 밖을 향한 얼굴만 보인 뒤 놓침 · 얼굴을 한 프레임 놓침 · rows.csv의 문자열 값), rows.csv로 읽은 휴대폰 열, 보정 도구(창 중앙값의 평균 + 2 SD, 녹화 하나면 값 없음, 다가간 줄과 판정하지 않을 창을 뺌, 눈 사이 거리가 완전히 같거나 1 근처에서만 흔들리는 녹화는 `approach_ratio_min`을 쓰지 않음, 트랙 잇기 경계와 머리 상자 경계), P1 입력(정사각 크롭 · 회색 바깥 · RGB · 정규화), 선택 열(머리 트랙의 번호 유지와 끝남 · 주 사용자 트랙 고정과 트랙이 끝난 뒤 새로 고름 · 손으로 만든 상자의 상대 거리와 옆 거리 · 창 중앙값 · 경계값이 있을 때의 동행자 · 뒤 사람과 없을 때의 `unknown` · 모르는 역할이 사건 층에 결측으로 닿음 · 주 사용자 상자 밖 얼굴의 값을 비움 · 주 사용자 상자가 빠진 동안 다른 트랙의 얼굴 값을 비우고 상자가 돌아오면 되살림 · 어느 상자에도 없는 얼굴은 빈칸으로 둠 · 새 터치 로그 세션에서 트랙을 다시 시작(앞 세션의 다른 사람 얼굴 값이 남지 않음) · 어깨 · 입 움직임 기준선 · `iod_ratio_user`의 계속 갱신하는 기준(새 트랙에서 다시 시작, 첫 누름 전에는 모으지 않음, 가까이 오래 머물면 기준이 올라감) · 주 사용자 트랙이 바뀐 줄(얼굴만 가려지면 트랙이 이어지고, 머리 상자를 `track_max_gap_s`보다 오래 놓치면 새 트랙; 같은 자리 다시 잡음은 몸이 `track_max_gap_s` 안에서 잠깐 안 보여도 인정(꼭 `track_max_gap_s`까지 인정, 몸 공백은 마지막 머리 상자부터 셈); 제자리에서 끊겼다 곧바로 시작한 트랙은 이어 붙이고, 함께 보인 머리 · 앞 트랙의 마지막 상자와 같은 프레임에 처음 보인 머리 · `track_max_gap_s` 뒤에 시작한 트랙 · 다른 자리 · 작은 머리 · 경계값 없음은 잇지 않음; 이은 줄은 앞 사용자의 자리 잡음을 이어 쓰고 크기 기준은 다시 잡음; 값 묶음의 잇기 경계 2개가 체인 · 기록 채우기 · 보정 도구까지 닿음; 좌표가 유한하지 않은 상자는 잇기 측정에서 뺌) · 재생 기록에 장면 열 채우기(교체 열이 하나라도 없는 기록은 교체 열을 모두 다시 씀)), 터치 로그(시계 파일 · 시작 오프셋 · 누름 · 버튼 밖 · 빗나감 뒤 바로 고침 · 되돌아감 · 관측 구간 · 세션 · 1,000개 잘림 · 옵션 창 상태), 규칙표 v0(장면 4개의 여는 조건 · 고개 방향 게이트 · 미룸의 전제 · 순서 · 교체 · 휴대폰 길의 기다림과 다른 행 · 측정할 수 없는 창에서 휴대폰 길은 3-2만 엶(기다림을 거절했으면 유지 중인 4-2를 되풀이) · 기다림의 신호와 재진입 · 유지 결정의 내용 · 실행 칸 · 무응답 · 거절 · 범위, 규칙표에 숫자가 없음), 창 판단(`WindowJudge`: 고른 뒤 멈춤 · 얼굴 없는 몸 · 세션 초기화 · 새 세션은 그 세션의 관측 줄만 읽음 · 취소되거나 저장되지 않은 '담기' 누름은 지원을 거두지 않음 · 창 기록의 고개 돌림 목록 `turns` · 창 기록과 `extension`의 장면 태그와 돌아간 탐지기 `detectors`), 모름 이유(열 결측 · 센서 실패 · 동점 · 근거 부족, 모든 `unknown` 창에 이유가 있음), 창 기록이 전체 기록과 같은 결과를 내는지, 가짜 추론 결과로 돌린 재생(두리번 태그가 나오고 4-2 강조가 열리는지, 출력 검사: `SupportDecision` 형식과 `extension`의 관측 가능 여부·모델 버전, `analyze_response` 제외), 창 없는 실시간(가짜 카메라), 두 실행기의 `meta.json` `timing_ms`가 처리 시간 열(`ms_aids` · `ms_phones` 포함)을 모두 요약하는지, 그린 영상으로 돌린 실제 모델 재생(창 1초 · 2초 · 남은 0.9초, 머리 상자 0: 도형이라 H1 → P1 경로는 안 돎)을 봅니다. 사람 머리 사진으로 H1 → P1을 확인하는 테스트는 환경 변수 `VISION_TEST_HEAD_IMAGE`에 사진 경로를 줄 때만 돌고, 사진은 저장소에 두지도 보여 주지도 않습니다. 숫자는 합성 입력용이고 기준값 제안이 아닙니다. ONNX 파일이나 MediaPipe가 없으면 그 테스트만 건너뜁니다. 별도 교차 검사(`ContractViewTests`)는 백엔드 파일을 경로로 불러와 `measurable=true` · `states=null`의 거부와 `measurable=false` · `states=null`의 허용을 확인합니다. 이 검사는 GPU·ONNX·OpenCV 없이 돌며, 백엔드 파일이나 pydantic v2 등 import에 필요한 항목이 없으면 이유를 남기고 건너뜁니다.
- 사진 · 사람이 나온 영상 · `runs/`는 쓰지 않습니다(재생 시험의 영상은 테스트가 도형을 그려 만듦). 필요한 패키지나 모델 파일이 없으면 그 테스트만 건너뛰므로, 서버 패키지만 깔린 환경의 `python -m unittest discover -s tests`에는 영향이 없습니다.

## V 모델 추적표 (실행 파이프라인, 2026-10-22)

요구에서 코드로 내려가고, 같은 높이의 검사로 올라옵니다. '결과에서 보는 것'은 결과 파일에서 직접 확인할 항목입니다.

| # | 요구 | 코드 | 검사 | 결과에서 보는 것 |
|---|---|---|---|---|
| V1 | 머리 상자를 키오스크 PC의 CPU에서 찾는다(H1) | `app/inference/head.py`, `tools/export_onnx.py` | 변환 확인(ONNX와 PyTorch의 출력 차이 · NMS 뒤 상자, `models/onnx_export.json`), `HeadPostprocessTests`, `OnnxModelTests` | `models/README.md` 표의 크기 · 해시, '처리 시간'의 `ms_heads` |
| V2 | 주 사용자 머리의 카메라 시점 확률(P1, 관측만) | `app/inference/head_direction.py` | 변환 확인(logits 차이, 입력 변환과 torchvision의 차이), `HeadDirectionInputTests`, `OnnxModelTests` | `rows.csv`의 `head_dir_*` |
| V3 | 규칙이 쓰는 선택 열(머리 트랙 · 주 사용자 트랙 · 뒤 사람 · 동행자 · 어깨 · 입 움직임) | `columns.py`, `chain.py` | `ColumnsTests`, `FrameChainTests` | `rows.csv`의 선택 열, `windows.jsonl`의 `vision` |
| V4 | 터치 로그를 영상 시간에 맞춰 센다 | `touch.py` | `TouchTests` | `windows.jsonl`의 `touch` · `screen`, `meta.json`의 `touch.anchor` |
| V5 | 창마다 상황 태그 · 근거 사건 ID · 모름 이유 · 대안 | `chain.py`(`WindowJudge`, `unknown_reasons`), `situation.py` | `UnknownReasonTests`, `HistoryTests`, `ReplayWithFakePerceptionTests` | `windows.jsonl`의 `situation` |
| V6 | 판단 층 규칙표 v0(장면 4개)와 Jev 그림자 기록 | `judgment/` | `RuleTableTests`, `WindowJudgeTests` | `windows.jsonl`의 `decision` · `session` · `jev` |
| V7 | `support` 형식 유지, 관측 가능 여부는 `extension`에, `AnalyzeResponse` 제외 | `contract_view.py` | `test_contract_view_fits_the_existing_contract`(`support`·확장 데이터 검사), `test_backend_analyze_response_requires_state_scores`(백엔드 검증 조건) | `windows.jsonl`의 `contract` |
| V8 | 녹화 재생과 웹캠 실시간 | `replay.py`, `live.py` | `ReplaySmokeTests`(그린 영상 + 실제 모델; 남은 구간 창, 머리 상자 0), `LiveTests`(창 없음, 가짜 카메라) | `replay`의 마지막 콘솔 줄, `live`의 창마다 한 줄 |
| V9 | 재료가 빠지면 모름으로 | 모든 층 | `test_without_touch_log_or_values_the_tags_stay_unknown_with_reasons`, `test_missing_sources_leave_their_columns_missing` | `unknown_reason`의 코드 |
| V10 | 처리 시간을 잰다 | `replay.py`(`meta.json`의 `timing_ms`) | 같은 조건 3번(위 '처리 시간') | '처리 시간'의 표 |
| V11 | 판단 층이 읽는 키로 상황을 낸다 | `contract_view.py`(`decision_situation` · `observations`) | `DecisionViewTests`, `BackendReadsTheViewTests`(저장소의 backend 판단 층 코드로 읽음) | `windows.jsonl`의 `contract.extension` |
| V12 | 주문 화면의 터치 통계를 한 방향으로 받아 창 판단에 넣는다(로컬) | `touch_entry.py`, `live.py --serve` | `ParseRequestTests`, `LiveTouchTests`, `PlaceTouchTests`, `TouchEntryTests`, `LiveEntryTests`(가짜 카메라 · 가짜 시계), `TouchPacedEvaluationTests`, `HttpTests` | 답의 `status`(비전 값 없음), 실행기 콘솔의 터치 창마다 한 줄, `windows.jsonl`의 `evaluated` |
| V13 | 창마다 상황 태그를 backend로 직접 보낸다 | `tag_sender.py`, `live.py --backend-url` | `TagSenderTests`, `LiveSenderTests`(시험 backend), 가짜 카메라 시험 도구(`tools/integration_smoke.py`, `SmokeToolTests`) | `meta.json`의 `tag_sender`, 시험 도구의 `smoke_summary.json` |

검증: 2026-10-28 팀 촬영본(재현 영상 34편)으로 관측값과 지원 판단을 정답 라벨에 대조했습니다(팀 논문 표 1 · 3.2절). 팀 촬영본으로 P1 클래스와 얼굴 각도의 교차표도 확인했습니다. 키오스크 시점의 H1 · P1은 회사 제공 영상 1개(비공개, 저장소 밖)로 봤고, P1은 화면 위 카메라 영상 41개의 교차표로 다시 봤습니다(위 'P1 표시 이름과 한계').

## 연결과 이어지는 일 (2026-11-22)

- 연결: 세 쪽 끝(주문 화면의 터치 창 보내기, 이 프로세스의 터치 입구와 상황 태그 보내기, backend의 창 받는 곳과 시연 스위치)이 있고, 형식은 `contract/frontend-ai.openapi.json` · `contract/ai-backend.openapi.json`에 있습니다. 남은 일은 4-1의 횟수, backend의 `/v1/analyze` 호출, 장면 태그의 2단계 행입니다(위 '주문 화면 · backend와 잇는 두 연결'의 '아직 남은 것').
- 창을 판단하는 때: 세션이 알려진 뒤에는 그 구간의 터치가 도착한 다음에 판단하고, 주문 화면이 없으면 자기 간격으로 판단합니다. 짧은 값 묶음의 한계는 위 '주문 화면 · backend와 잇는 두 연결'에 적었습니다.
- 기준값: 상황 규칙 13개는 값 묶음 파일로 들어갑니다. 장면 태그의 경계값은 카메라마다 서서 쓰는 보정 녹화로 `tools/calibrate_scene.py`가 정하고(평균 + 2 SD, Wu 외 W4A 2021), 저장소 기본값은 비워 둡니다. 출처가 없는 값은 `[파일럿]` 시작값으로 표시합니다(위 '[파일럿] 값과 출처').
- 터치 매핑: 누름 · 버튼 밖 누름 · 빗나감 뒤 바로 고침 · 되돌아감을 원시 기록에서 세는 방법은 `[설계 제안]`이고 팀 항목 T01 · T02 · T03 · T07 · T08에서 정합니다.
- 판단 층: 규칙표 v0는 장면 3-1 · 3-2 · 4-1 · 4-2의 지원을 고릅니다. 1-1 · 1-2 · 2-1 · 2-2 · 자리 비움은 장면 태그까지 냅니다. 그 지원 행(시작 지원, 세션 신호)은 아직 구현하지 않았으며 제안(팀 검토 전)입니다.
- 3-2 휴대폰 길: 휴대폰 탐지기는 `--phone-model`을 줄 때만 도는 선택 입력이고, 주지 않으면 `phone_use`는 모름(`column:phone_owner`)이며 3-2는 일행 길로 엽니다. 탐지기 한 번에 p50 23 ms이고, 프레임 한 장 전체는 탐지기 없이 p50 66 ms, 프레임마다 돌리면 103 ms, `phone_every` 5면 67 ms입니다(개발 노트북, 위 '휴대폰 입력과 3-2 휴대폰 길').
- 키오스크 시점 확인: 장면 태그는 회사 단말 영상에서 사람 단위로 나눠 확인했습니다(위 '장면 태그 6개'). 머리 탐지기는 Open Images 시험 AP50 64.3입니다. 보조기구 탐지기는 키오스크 앞 가까운 사용자를 사람 상자로 잡지 않습니다(위 '보조기구 입력').
- 연구용 기기: 광명테크 연구용 기기에서는 그 기기의 카메라로 서서 쓰는 영상을 찍어 같은 도구로 값을 정합니다. 처리 시간은 지금 개발 노트북 값입니다(위 '처리 시간').
- 처리 위치: 키오스크 PC에서 계산하고 서버에는 값만 보냅니다(루트 README '구성별 책임', 2026-10-16).
- 표정: blendshape 설정은 입 움직임에만 씁니다(`--blendshapes`, 기본 꺼짐). 감정 이름을 붙이는 판단은 하지 않습니다.
- 구간 모델: AI Hub Validation으로 한 파일럿입니다.
- 서버의 판단: ai-engine `/v1/analyze`의 판단은 자리 표시입니다. 백엔드 지원 응답은 기본값에서 `preset=none`이고, 시연 스위치(`DECISION_SEND_SUPPORT`)를 켰을 때만 규칙표 결정을 싣습니다(`backend/README.md`).
- 브라우저 실시간 화면(대시보드) · 웹캠 녹화 도구: 시제품에 있고 이 저장소에는 넣지 않았습니다.
- 상황 태그를 실을 명세 칸과 `StateScores`와의 관계: 팀 회의 안건(V04)입니다.

## CSV 열

빈칸 = 얼굴이나 몸을 못 본 프레임이라 계산할 수 없는 값(0이 아님). 예외: 못 봤을 때 `face_run_s` · `body_run_s`는 0이고 `face_unseen_s` · `body_unseen_s`가 채워집니다.

| 열 | 뜻 |
|---|---|
| `frame_idx` · `src_frame` · `t_s` | 처리한 프레임 번호(0부터) · 원본 프레임 번호나 파일 이름 · 프레임 시각(초; 파일 = 번호 ÷ 초당 장수, 카메라 = 잡은 시각, 첫 프레임 0) |
| `source_kind` · `syn_phase` | 입력 종류(영상 · 이미지 · 카메라 · 합성) · 합성 입력의 단계(저장소 밖 생성기로 만든 이미지 폴더의 `manifest.json`에서 읽음, 그 밖의 입력은 빈칸) |
| `face_state` · `body_state` | 얼굴 · 몸 보임 / 못 봄(모델 결과 유무). 결과가 비면 '못 봄'이고 '사람 없음'이 아님 |
| `face_count` | 얼굴 검출 결과 개수 |
| `iod_px` · `iod_frac_w` · `iod_ratio_start` | 눈 사이 거리(px, 두 눈꼬리 쌍 33·133, 362·263의 중심 사이) · ÷ 화면 폭 · 세션의 첫 얼굴 프레임 대비 비율 |
| `yaw_deg` · `pitch_deg` · `roll_deg` | 고개 방향(도): 얼굴 변환 행렬의 회전을 OpenCV `RQDecomp3x3`으로 나눈 각. 부호는 MediaPipe 얼굴 기하 공간(오른손 좌표계, 카메라는 원점에서 −Z 방향을 봄 — MediaPipe Face Mesh 문서)과 "+ 회전 → + 각"(테스트로 고정)에서 풀어 쓴 방향입니다: yaw + = 화면 오른쪽, pitch + = 아래, roll + = 반시계. 테스트는 축마다 순수 회전 행렬(+10°)을 넣어 이 부호를 확인합니다 |
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

재생의 `rows.csv`는 위 열 뒤에 선택 열(위 '선택 열'), 터치 횟수, 처리 시간 열을 붙입니다: `ms_heads`(H1 전처리 · 추론 · 후처리), `ms_head_dir`(P1 크롭 · 추론), `ms_aids`(보조기구 탐지기, `--aid-model`을 줄 때만), `ms_phones`(휴대폰 탐지기, `--phone-model`을 줄 때만; `phone_every`로 탐지기가 돌지 않은 줄은 빈칸), `ms_chain`(프레임 한 장의 파이프라인 전체, 벽시계), `cpu_ms_chain`(같은 구간의 프로세스 CPU 시간; 이 PC에서는 15.6 ms 단위로 올라감). 상자 칸은 `x0;y0;x1;y1`이고, `head_boxes`는 JSON 한 칸입니다.

## 발표·보고서에 쓸 수 있는 데이터 (라이선스 대장, 비전 담당 작업 노트 기준)

- AI Hub 71827 · 82: 원본 영상 · 프레임 · 라벨은 발표 · 보고서 · 시연에 넣지 않습니다(허용 문구 없음). 집계 숫자 · 그래프와 학습한 모델만 쓰고, 출처 문구(한국지능정보사회진흥원 사업결과 · 데이터셋 정식 명칭 · AI 허브)를 붙입니다. 데이터를 볼 사람은 각자 승인받습니다.
- AFLW2000-3D: 비상업 연구 전용. 사진은 어디에도 띄우지 않고 숫자만 씁니다. 제품 경로에 쓰지 않습니다.
- Open Images: 주석 CC BY 4.0, 사진 CC BY 2.0(사진마다 표기 확인). 사진을 쓰면 저작자 · 제목 · 주소 · 라이선스 주소와 변경 표시가 필요합니다. 지금은 발표 · 보고서에 넣지 않습니다(넣을지는 비전 담당 결정).
- 연구 전용 가중치(ImageNet ResNet-50 · ResNet-18)로 낸 숫자는 '연구 숫자'로만 적고 제품 성능처럼 쓰지 않습니다.
- 카메라 시점 분류기(P1)는 ImageNet 가중치 없이 무작위 초기값에서 AI Hub 70으로 학습해서 제품 경로에 쓸 수 있고, 쓸 때 NIA 출처 문구를 붙입니다(`models/README.md`). 머리 탐지기(H1)는 Open Images 주석 출처와 YOLOX Apache-2.0 고지를 함께 둡니다.
