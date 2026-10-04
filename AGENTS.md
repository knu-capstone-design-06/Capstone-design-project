# AGENTS.md

이 저장소에서 작업하는 팀원과 AI 에이전트(Claude Code 등)가 함께 지키는 공통 규칙입니다.
브랜치·커밋·PR의 세부 규칙은 [`docs/Convention.md`](docs/Convention.md), 프로젝트 개요와 목표 구조는 [`README.md`](README.md)를 따릅니다.
우리 팀은 GitHub Issue를 쓰지 않습니다. 논의와 결정은 PR 본문과 회의 기록에 남깁니다.
이 문서와 두 문서가 충돌하면 작업을 멈추고 팀에 확인합니다.

## 1. 기본 원칙

- 하나의 PR은 하나의 목적만 다룹니다.
- 다른 이름의 브랜치를 만들지 않고 `docs/Convention.md`의 작업 브랜치에서 작업합니다. 역할 브랜치는 `feat/frontend`, `feat/backend`, `feat/vision`, `feat/ai`이고, 공용 브랜치 `feat/infra`, `feat/db`, `feat/docs`는 필요할 때 이 이름으로 만들어 씁니다.
- `main`에 직접 push하지 않습니다. 반드시 PR로 병합합니다.
- 공유 브랜치(`main`, 공용 브랜치, 다른 사람의 역할 브랜치)에 force-push, rebase, 기록 수정을 하지 않습니다.
- 자기 역할 브랜치의 기록을 고쳐 force-push할 때는 `--force-with-lease`를 쓰고, 그 브랜치를 받아간 팀원에게 알립니다.
- 작업 범위를 벗어난 파일은 건드리지 않습니다. 발견한 문제는 PR 본문의 "남은 작업 또는 주의사항"이나 팀 채널에 남깁니다.
- 회의에서 결정한 내용은 `docs/`의 회의 기록과 관련 문서에 반영합니다.

## 2. 공용 영역: 추가는 자유, 수정·삭제는 합의 후

아래 경로는 여러 담당자가 함께 쓰는 **공용 영역**입니다.

| 공용 영역 | 내용 |
|---|---|
| `contract/` | API·이벤트·비전 결과·AI 명령 형식 |
| `db/` | 마이그레이션, 스키마, 시드 데이터 |
| `frontend/src/shared/`, `frontend/src/app/` | 공통 UI·API·훅·타입, 라우팅·Provider·레이아웃 |
| `backend/app/common/`, `backend/app/infrastructure/` | 공통 설정·예외·상수, DB·외부 연결 |
| `ai-server/app/common/`, `ai-server/app/infrastructure/` | 공통 설정, 외부 연결 |
| 루트 설정 파일 | `docker-compose.yml`, `.gitignore`, `infra/`, 각 서비스의 `Dockerfile`·의존성 파일 |
| 공통 문서 | `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/Convention.md` |

규칙:

- **추가**(새 파일, 새 함수·컴포넌트, 새 필드 추가처럼 기존 동작을 바꾸지 않는 변경)는 PR 리뷰만 거치면 됩니다.
- **수정·삭제**(기존 이름·형식·동작 변경, 파일·필드 삭제, 이동, 이름 변경)는 **먼저 회의나 팀 채널에서 논의**하고, 영향받는 담당자의 동의를 받은 뒤 구현합니다.
  - PR 본문에 논의한 회의 날짜나 결정 내용을 적습니다.
  - 영향받는 담당자를 PR 리뷰어로 지정합니다.
- 의존성 추가·버전 변경은 해당 서비스 담당자와 공유합니다. 새 인프라(S3, Redis, 큐 등)는 필요성이 확인된 뒤 합의해서 도입합니다.
- `contract/` 형식을 바꾸면 이를 사용하는 프론트·백엔드·비전·AI 코드와 샘플 데이터를 같은 시점에 맞추거나, 맞출 일정을 PR 본문에 적습니다.

## 3. 담당 영역

| 영역 | 담당 | 주요 경로 |
|---|---|---|
| 프론트엔드 | frontend | `frontend/` |
| 백엔드 | backend | `backend/`, `db/` |
| 컴퓨터 비전 | vision | 저장 위치는 팀에서 확정 예정 |
| AI | ai | `ai-server/` |
| 문서 | docs | `docs/` |

- 자기 담당 영역 안의 기능 폴더(예: `frontend/src/features/<feature>/`, `backend/app/modules/<module>/`)는 자유롭게 작업합니다.
- 다른 담당자의 영역을 수정해야 하면 먼저 팀 채널이나 PR에서 공유하고, 그 담당자의 리뷰를 받습니다.

## 4. 파일 구조 규칙

폴더는 필요할 때 만들고, 모든 기능에 같은 파일 구성을 강제하지 않습니다.

### frontend (React + Vite + TypeScript)

- `src/app/`: 앱 진입점, 라우터, 전역 Provider, 레이아웃만 둡니다.
- `src/features/<feature>/`: 기능별 코드(`api/`, `components/`, `hook/`, `types/`, `utils/`, `pages/`)를 둡니다. 외부에는 `index.ts`로 공개할 것만 내보냅니다.
- `src/shared/`: 두 개 이상의 기능에서 실제로 쓰는 코드만 둡니다. 한 기능에서만 쓰는 코드는 그 기능 폴더에 둡니다.
- 기능끼리는 서로의 내부 파일을 직접 import하지 않고 `index.ts`를 통해 사용합니다.

### backend (FastAPI)

- `app/modules/<module>/`: `router.py`(엔드포인트) → `service.py`(업무 로직) → `repository.py`(DB 접근) 방향으로만 호출합니다.
- 요청·응답 형식은 `schemas.py`, DB 모델은 `models.py`, 모듈 전용 예외는 `exceptions.py`, 테스트는 `tests/`에 둡니다.
- DB·스토리지·외부 API 연결 코드는 `app/infrastructure/`에, 여러 모듈이 쓰는 설정·상수·예외는 `app/common/`에 둡니다.
- AI 서버와 외부 AI API의 결과는 백엔드가 검증한 뒤 주문 상태나 UI에 반영합니다.
- 외부 AI API(STT·LLM·Jev)는 backend가 호출합니다. ai-server는 외부 AI API를 호출하지 않습니다.

### ai-server (FastAPI)

- `app/modules/<module>/`: 비전 특징 추출, 불편 상태 판단 엔드포인트를 둡니다.
- `app/inference/`: 직접 실행하는 모델의 로딩·추론 코드만 둡니다.
- 모델 가중치와 대용량 데이터는 Git에 올리지 않고, 저장 위치·버전·사용 방법을 문서로 남깁니다.

### db

- `migration/`: 스키마 변경 이력. **이미 병합된 마이그레이션 파일은 수정하지 않고** 새 파일을 추가합니다.
- `schema/`: 현재 스키마 정의. `seed/`: 개발·시연용 초기 데이터(개인정보 없음).

### contract · docs · infra

- `contract/`: 인터페이스마다 필드 이름, 타입, 단위, 필수 여부, 결측값, 오류 형식과 예시를 적습니다.
- `docs/`: 시나리오·설계·실험·회의 문서를 둡니다.
- `infra/`: 배포·운영 설정. 비밀값은 넣지 않습니다.

## 5. 보안과 데이터

- API 키, 비밀번호, DB 접속 정보, `.env`, 개인 식별 정보는 커밋하지 않습니다.
- 필요한 환경변수는 값 없이 `.env.example`에 기록합니다.
- 원본 영상, 촬영 이미지, 대용량 데이터셋, 모델 가중치는 Git에 직접 올리지 않습니다.
- 실험 참가자 데이터는 파일럿과 최종 평가를 분리하고, 정해진 저장소에만 보관합니다.

## 6. PR 전 확인

- 변경과 관련된 빌드·테스트·수동 확인을 수행하고 결과를 PR에 적습니다.
- 공용 영역을 수정·삭제했다면 논의한 회의 날짜나 결정 내용을 PR에 적습니다.
- UI 변경은 스크린샷, API 변경은 요청·응답 예시를 첨부합니다.
- 작성자 외 1명 이상 승인 후 병합합니다. 역할 브랜치는 병합 후에도 삭제하지 않습니다.

## 7. AI 에이전트 작업 규칙

AI 에이전트는 위 규칙을 모두 따르고, 추가로 다음을 지킵니다.

- 공용 영역의 기존 코드를 수정·삭제하거나 파일을 이동해야 하면, 실행 전에 사용자에게 먼저 확인합니다.
- 요청받지 않은 리팩터링, 의존성 추가, 폴더 구조 변경을 하지 않습니다.
- `main`에 push하거나 force-push하지 않습니다. 저장소 규칙(브랜치 보호 등)을 우회하지 않습니다.
- 커밋과 PR의 작성자는 작업한 팀원입니다. 커밋 메시지와 PR 본문에 `Co-Authored-By: Claude ...`, `Generated with Claude Code` 같은 AI 표시를 넣지 않습니다.
- 커밋 메시지·PR 본문은 `docs/Convention.md` 형식과 PR 양식을 따릅니다.
- 비밀값이나 개인정보로 보이는 내용을 발견하면 커밋하지 않고 사용자에게 알립니다.
- 확실하지 않은 인터페이스·요구사항은 추측해서 구현하지 않고 `contract/`나 사용자에게 확인합니다.
- 상품·장바구니·주문 또는 음성 주문 연동 작업 전에는 [`docs/Product-Cart-Order-API-Draft.md`](docs/Product-Cart-Order-API-Draft.md)를 확인합니다.
- 해당 문서는 검토용 초안이며 확정 명세가 아닙니다. 구현 기준은 합의 후 반영된 `contract/`입니다.
