# AGENTS.md

이 저장소에서 작업하는 팀원과 AI 에이전트(Claude Code 등)가 함께 지키는 공통 규칙입니다.
커밋 형식과 PR 양식은 [`Docs/Convention.md`](Docs/Convention.md), 프로젝트 개요와 목표 구조는 [`README.md`](README.md)를 따릅니다.
우리 팀은 GitHub Issue를 쓰지 않습니다. `Docs/Convention.md`에서 이슈를 요구하는 항목은 이 문서의 규칙(PR 본문·회의 기록)으로 대신합니다.
그 밖에 이 문서와 두 문서가 충돌하면 작업을 멈추고 팀에 확인합니다.

## 1. 기본 원칙

- 하나의 브랜치·PR은 하나의 목적만 다룹니다.
- 브랜치 이름은 `타입/작업명` 형식을 씁니다. 예: `feat/voice-ui-command`, `fix/cart-quantity`, `docs/agent-rules`
- `main`, `develop`에 직접 push하지 않습니다. 반드시 PR로 병합합니다.
- 공유 브랜치(`main`, `develop`, 다른 사람의 작업 브랜치)에 force-push, rebase, 기록 수정을 하지 않습니다.
- 자기 작업 브랜치의 기록을 고쳐 force-push할 때는 `--force-with-lease`를 쓰고, 그 브랜치를 받아간 팀원에게 알립니다.
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
| 공통 문서 | `README.md`, `AGENTS.md`, `CLAUDE.md`, `Docs/Convention.md` |

규칙:

- **추가**(새 파일, 새 함수·컴포넌트, 선택적 필드·옵션 추가처럼 기존 사용처가 깨지지 않는 변경)는 PR 리뷰만 거치면 됩니다.
- **수정·삭제**(기존 이름·형식·동작 변경, 필수 인자 추가, 파일·필드 삭제, 이동, 이름 변경)는 **먼저 회의나 팀 채널에서 논의**하고, 영향받는 담당자의 동의를 받은 뒤 구현합니다.
  - PR 본문에 논의한 회의 날짜나 결정 내용을 적습니다.
  - 영향받는 담당자를 PR 리뷰어로 지정합니다.
- 의존성 추가·버전 변경은 해당 서비스 담당자와 공유합니다. 새 인프라(S3, Redis, 큐 등)는 필요성이 확인된 뒤 합의해서 도입합니다.

### 공용 코드를 만들거나 고칠 때 주의할 점

- 공용 폴더에는 **두 개 이상의 기능에서 실제로 쓰는 코드**만 둡니다. "나중에 쓸 것 같아서"는 이유가 되지 않습니다. 처음에는 기능 폴더에 두고, 두 번째 사용처가 생기면 옮깁니다.
- 특정 기능의 업무 로직(예: 장바구니 계산, 특정 화면 전용 문구)을 공용 코드에 넣지 않습니다.
- 기존 공용 함수·컴포넌트의 동작을 바꿔야 하면, 기존 시그니처는 그대로 두고 **선택적 인자·옵션을 추가**하는 방식을 먼저 검토합니다.
- 공용 코드를 바꾸면 그 코드를 쓰는 곳을 모두 검색해 확인하고, PR에 영향 범위를 적습니다.
- 공용 설정(`common/config`, 환경변수 이름, 포트)을 바꾸면 `.env.example`, `docker-compose.yml`, 관련 문서를 같은 PR에서 맞춥니다.
- `contract/` 형식을 바꾸면 이를 사용하는 프론트·백엔드·비전·AI 코드와 샘플 데이터를 같은 시점에 맞추거나, 맞출 일정을 PR 본문에 적습니다.

## 3. 담당 영역

| 영역 | 담당 | 주요 경로 |
|---|---|---|
| 프론트엔드 | frontend | `frontend/` |
| 백엔드 | backend | `backend/`, `db/` |
| 컴퓨터 비전 | vision | 저장 위치는 팀에서 확정 예정 |
| AI | ai | `ai-server/` |
| 문서 | docs | `docs/`, `Docs/` |

- 자기 담당 영역 안의 기능 폴더(예: `frontend/src/features/<feature>/`, `backend/app/modules/<module>/`)는 자유롭게 작업합니다.
- 다른 담당자의 영역을 수정해야 하면 먼저 팀 채널이나 PR에서 공유하고, 그 담당자의 리뷰를 받습니다.

## 4. 서비스 간 경계

```text
frontend ──HTTP/WebSocket──▶ backend ──▶ DB (Supabase PostgreSQL)
vision   ──HTTP────────────▶ backend ──▶ ai-server ──▶ Jev · STT · LLM · TTS
```

- **DB에는 backend만 접근합니다.** frontend, ai-server, 비전 프로그램은 DB에 직접 연결하거나 Supabase 클라이언트로 조회·저장하지 않고, backend API를 거칩니다.
- **frontend는 backend와만 통신합니다.** ai-server나 외부 AI API(Jev, LLM, STT)를 브라우저에서 직접 호출하지 않습니다.
- **ai-server는 판단만 하고 상태를 바꾸지 않습니다.** 해석 결과와 지원 후보를 backend에 돌려주고, 주문 변경·UI 적용 여부는 backend가 검증해서 결정합니다.
- 서비스 간 요청·응답 형식은 `contract/`에 먼저 정의하고 그에 맞춰 구현합니다.
- 서비스 주소·포트·키는 코드에 적지 않고 환경변수로 받습니다.

## 5. 파일별 역할과 규칙

폴더는 필요할 때 만들고, 모든 기능에 같은 파일 구성을 강제하지 않습니다.

### frontend (React + Vite + TypeScript)

| 경로 | 역할 | 하지 않을 것 |
|---|---|---|
| `src/app/App.tsx` | 최상위 컴포넌트. Provider·라우터를 조립합니다. | 화면 내용, 업무 로직 |
| `src/app/router.tsx` | URL과 페이지 연결 | 데이터 호출, 권한 외 로직 |
| `src/app/providers.tsx` | 전역 상태·쿼리·테마 Provider 등록 | 기능 전용 상태 |
| `src/app/layouts/` | 화면 공통 틀(헤더, 접근성 모드별 배치) | 특정 기능의 UI |
| `src/features/<feature>/pages/` | 라우트에 연결되는 화면 | 직접 `fetch` 호출 |
| `src/features/<feature>/components/` | 그 기능 전용 UI 컴포넌트 | API 호출, 전역 상태 직접 수정 |
| `src/features/<feature>/hook/` | 기능의 상태·데이터 로딩 로직 | UI 렌더링 |
| `src/features/<feature>/api/` | 그 기능의 backend 호출 함수 | 직접 URL 조합(공용 클라이언트 사용) |
| `src/features/<feature>/types/`, `utils/` | 기능 전용 타입·순수 함수 | 다른 기능에서 import |
| `src/features/<feature>/index.ts` | 외부에 공개할 것만 내보내는 입구 | 내부 구현 전부 내보내기 |
| `src/shared/api/` | 공용 HTTP·WebSocket 클라이언트(기본 주소, 공통 헤더, 오류 처리) | 기능별 엔드포인트 함수 |
| `src/shared/components/`, `hook/`, `type/`, `utils/` | 두 기능 이상이 쓰는 UI·훅·타입·함수 | 기능 전용 로직 |

- 데이터 흐름: `pages` → `hook` → `api` → `shared/api` 클라이언트 → backend. 컴포넌트에서 직접 `fetch`·`axios`를 호출하지 않습니다.
- 기능끼리는 서로의 내부 파일을 직접 import하지 않고 `index.ts`를 통해 사용합니다.
- `VITE_`로 시작하는 환경변수는 브라우저에 그대로 노출됩니다. API 키·비밀값을 넣지 않습니다.
- 접근성 모드(큰 글씨, 큰 버튼, 낮은 화면 등)를 바꾸거나 터치·음성을 전환해도 장바구니·주문 상태가 유지되어야 합니다. 상태를 컴포넌트 안에만 두지 않습니다.
- 터치 로그 수집은 `contract/`의 이벤트 형식을 따르고, 화면마다 제각각 형식으로 보내지 않습니다.

### backend (FastAPI)

| 경로 | 역할 | 하지 않을 것 |
|---|---|---|
| `app/main.py` | 앱 생성, 라우터 등록, 미들웨어·CORS·예외 처리기 연결 | 엔드포인트 구현, 업무 로직 |
| `modules/<module>/router.py` | 엔드포인트 정의, 요청 검증, 의존성 주입, service 호출 | DB 조회, 업무 규칙 |
| `modules/<module>/service.py` | 업무 로직, 트랜잭션 단위 결정, 다른 서비스·AI 연동 | `Request`·`Response` 같은 HTTP 객체 사용, SQL 작성 |
| `modules/<module>/repository.py` | DB 조회·저장만 담당 | 업무 규칙 판단, 외부 API 호출 |
| `modules/<module>/schemas.py` | 요청·응답 Pydantic 모델 | DB 모델 역할 |
| `modules/<module>/models.py` | DB 테이블 모델 | API 응답으로 그대로 반환 |
| `modules/<module>/exceptions.py` | 모듈 전용 예외 | 공용 예외(→ `common/exceptions/`) |
| `modules/<module>/tests/` | 모듈 테스트 | 실제 운영 DB 사용 |
| `infrastructure/database/` | DB 연결·세션 관리 | 모듈별 쿼리 |
| `infrastructure/external/` | ai-server 등 외부 서비스 클라이언트 | 업무 로직 |
| `infrastructure/storage/`, `queue/` | 스토리지·큐 연결(도입이 합의된 경우만) | — |
| `common/config/` | 환경변수를 읽는 설정 객체 | 코드 곳곳에서 `os.getenv` 직접 호출 |
| `common/exceptions/`, `constants/`, `utils/` | 공용 예외·상수·도구 | 모듈 전용 내용 |

- 호출 방향은 `router → service → repository`만 허용합니다. 거꾸로 호출하거나 단계를 건너뛰지 않습니다.
- 다른 모듈의 데이터가 필요하면 그 모듈의 `repository`를 직접 쓰지 않고 `service`를 호출합니다.
- API 응답은 항상 `schemas.py`의 모델로 반환합니다. DB 모델을 그대로 내보내지 않습니다.
- ai-server·비전의 결과는 그대로 믿지 않고, 현재 세션·화면·주문 상태와 맞는지 검증한 뒤 반영합니다. 오래된 판단 결과는 적용하지 않습니다.
- 외부 호출(ai-server, Jev 등)에는 타임아웃과 실패 시 동작을 정합니다. 외부 호출이 실패해도 주문 기능은 계속 동작해야 합니다.
- 오류 응답은 `contract/`에 정한 공통 오류 형식을 따릅니다.

### ai-server (FastAPI)

| 경로 | 역할 | 하지 않을 것 |
|---|---|---|
| `app/main.py` | 앱 생성, 라우터 등록 | 모델 로딩 외 무거운 초기화 로직 |
| `app/modules/<module>/` | 음성 처리, 명령 해석, 지원 판단 로직 | DB 접근, 주문 상태 변경 |
| `app/inference/` | 직접 실행하는 모델의 로딩·추론 | API 엔드포인트, 외부 API 호출 |
| `app/infrastructure/` | Jev·LLM·STT·TTS API 클라이언트 | 판단 로직 |
| `app/common/` | 설정, 공용 예외·상수 | 모듈 전용 내용 |

- 결과는 `contract/`에 정한 구조화된 형식(허용된 명령·지원 선택지 안에서)으로만 반환합니다. 자유 형식 텍스트를 명령으로 넘기지 않습니다.
- Jev 지침·LLM 프롬프트는 코드에 흩어 두지 않고 파일로 관리하며, 실험에 쓴 버전을 기록할 수 있게 합니다.
- 외부 AI API 호출에는 타임아웃·재시도 횟수를 정하고, 실패하면 규칙 기반 결과나 "판단 불가"를 명시적으로 반환합니다.
- 모델 가중치와 대용량 데이터는 Git에 올리지 않고, 저장 위치·버전·사용 방법을 문서로 남깁니다.

### db

| 경로 | 역할 | 하지 않을 것 |
|---|---|---|
| `migration/` | 스키마 변경 이력 | 이미 병합된 파일 수정 |
| `schema/` | 현재 스키마 정의(참고용) | 마이그레이션 없이 단독 변경 |
| `seed/` | 개발·시연용 초기 데이터 | 실제 개인정보·실험 데이터 |

- 스키마를 바꿀 때는 새 마이그레이션 파일 추가, `schema/` 갱신, backend `models.py` 수정을 같은 PR에서 합니다.
- 공용 Supabase DB의 테이블·컬럼을 콘솔에서 직접 수정하지 않습니다. 모든 변경은 마이그레이션으로 남깁니다.
- 컬럼 삭제·이름 변경은 공용 영역 수정이므로 합의 후 진행합니다.

### contract · docs · infra

- `contract/`: 인터페이스마다 필드 이름, 타입, 단위, 필수 여부, 결측값, 오류 형식과 예시를 적습니다. 시간은 관측 시각과 서버 수신 시각을 구분합니다.
- `docs/`: 시나리오·설계·실험·회의 문서를 둡니다.
- `infra/`: 배포·운영 설정. 비밀값은 넣지 않습니다.

## 6. 새 기능을 만들 때 체크리스트

1. 필요한 서비스 간 요청·응답이 `contract/`에 있는지 확인하고, 없으면 먼저 추가합니다.
2. 자기 담당 영역의 기능 폴더 안에서 시작합니다(`features/<feature>/`, `modules/<module>/`).
3. 공용 코드를 새로 만들어야 하면 정말 두 곳 이상에서 쓰는지 확인합니다.
4. 기존 공용 코드를 고쳐야 하면 작업 전에 합의합니다.
5. DB 변경이 있으면 마이그레이션·`schema/`·`models.py`를 함께 수정합니다.
6. 새 환경변수가 생기면 `.env.example`에 값 없이 추가합니다.
7. 외부 호출 실패, 빈 데이터, 잘못된 입력일 때의 동작을 확인합니다.
8. 관련 테스트나 수동 확인을 하고 결과를 PR에 적습니다.

## 7. 보안과 데이터

- API 키, 비밀번호, DB 접속 정보, `.env`, 개인 식별 정보는 커밋하지 않습니다.
- 필요한 환경변수는 값 없이 `.env.example`에 기록합니다.
- 원본 영상, 촬영 이미지, 대용량 데이터셋, 모델 가중치는 Git에 직접 올리지 않습니다.
- 카메라 영상은 필요한 특징만 추출해 전달하고, 원본 영상을 서버에 저장하지 않는 것을 기본으로 합니다.
- 실험 참가자 데이터는 파일럿과 최종 평가를 분리하고, 정해진 저장소에만 보관합니다.

## 8. PR 전 확인

- 변경과 관련된 빌드·테스트·수동 확인을 수행하고 결과를 PR에 적습니다.
- 공용 영역을 수정·삭제했다면 논의한 회의 날짜나 결정 내용을 PR에 적습니다.
- UI 변경은 스크린샷, API 변경은 요청·응답 예시를 첨부합니다.
- 작성자 외 1명 이상 승인 후 병합하고, 병합 후 작업 브랜치를 삭제합니다.

## 9. AI 에이전트 작업 규칙

AI 에이전트는 위 규칙을 모두 따르고, 추가로 다음을 지킵니다.

- 공용 영역의 기존 코드를 수정·삭제하거나 파일을 이동해야 하면, 실행 전에 사용자에게 먼저 확인합니다.
- 4장의 서비스 간 경계(DB 직접 접근 금지 등)와 5장의 파일별 역할을 어기는 코드를 만들지 않습니다.
- 요청받지 않은 리팩터링, 의존성 추가, 폴더 구조 변경을 하지 않습니다.
- `main`, `develop`에 push하거나 force-push하지 않습니다. 저장소 규칙(브랜치 보호 등)을 우회하지 않습니다.
- 커밋과 PR의 작성자는 작업한 팀원입니다. 커밋 메시지와 PR 본문에 `Co-Authored-By: Claude ...`, `Generated with Claude Code` 같은 AI 표시를 넣지 않습니다.
- 커밋 메시지·PR 본문은 `Docs/Convention.md` 형식과 PR 양식을 따릅니다.
- 비밀값이나 개인정보로 보이는 내용을 발견하면 커밋하지 않고 사용자에게 알립니다.
- 확실하지 않은 인터페이스·요구사항은 추측해서 구현하지 않고 `contract/`나 사용자에게 확인합니다.
