# 배포 위치와 통신 경로 제안

> 상태: 팀 검토 중 (2026-10-12). 프론트엔드·백엔드·AI 담당자의 리뷰와 팀 합의 전에는 확정 구성으로 취급하지 않습니다.

## 제안 구성

| 구성요소 | 운영 배포 위치 | 역할 |
| --- | --- | --- |
| `frontend/` | AWS Amplify Hosting (검토안 A) | React/Vite 빌드 결과물(`dist/`) 제공, 브라우저의 HTTPS 진입점. 키오스크 PC 로컬 제공안과 비교 필요 |
| `backend/` | 서울 리전 AWS EC2의 backend 컨테이너 | 세션·주문 API, AI 결과 검증, DB 및 외부 API 호출 |
| `ai-engine/` | backend와 동일한 EC2의 별도 컨테이너 | 백엔드가 요청하는 내부 추론 API. 비전 담당자는 프레임 처리를 키오스크 PC에서 실행하고 이 컨테이너에는 포함하지 않는 안을 제안함(팀 합의 전) |
| DB | 서울 리전 Supabase PostgreSQL | 백엔드가 관리하는 영속 데이터 |

루트 [`docker-compose.yml`](../docker-compose.yml)의 세 서비스 구성은 **로컬 통합 개발용**으로 유지합니다. **Amplify안을 채택하면** 운영에서는 프론트엔드 컨테이너를 배포하지 않고 Amplify가 정적 파일을 제공합니다. 기존 [EC2 템플릿](aws/ec2-baseline.yaml)은 backend·ai-engine용 호스트 준비 단계이며, 앱 배포·도메인·HTTPS를 아직 구성하지 않습니다.

비전 프레임을 키오스크 PC에서 처리해 관측값만 보낼지, 서버로 프레임을 보낼지는 2026-10-14 회의에서 결정할 항목입니다. 서버 처리안을 택하면 전송 대역폭·키오스크 브라우저의 카메라 권한·EC2 CPU 및 메모리 요구량이 달라집니다. 현재 ai-engine 이미지에는 비전 의존성과 모델 파일이 없으므로 이 표만으로 비전 처리 위치를 확정하지 않습니다.

비전 담당자는 **G10 키오스크 PC의 로컬 프로세스에서 프레임을 처리하고 관측값만 브라우저의 `vision` 입력으로 전달**하는 안을 제안했습니다. 원본 영상의 외부 전송을 피할 수 있고 EC2의 비전 처리 부하도 줄일 수 있지만, 로컬 프로세스와 브라우저의 전달 방식 및 권한은 아직 검증·합의되지 않았습니다. 이 안이면 ai-engine에는 비전 패키지·모델을 넣지 않고 G10에서 CPU·메모리를 실측합니다.

특히 Amplify의 공개 HTTPS 페이지가 같은 PC의 `localhost` 비전 프로그램에 요청하는 경로는 브라우저의 Local Network Access 권한 영향을 받습니다. 비전 담당자의 Edge headless 시험에서는 `fetch`와 WebSocket 연결이 요청 전에 차단됐고, 로컬 출처 페이지에서는 통과했습니다. 이는 **실제 G10 키오스크 브라우저의 권한·정책 검증을 대신하지 않습니다.** [Chrome의 Local Network Access 안내](https://developer.chrome.com/blog/local-network-access)에 따르면 공개 출처에서 loopback으로 보내는 요청은 권한 대상입니다. 10월 14일에는 (A) Amplify 유지 시 키오스크 권한·관리 정책과 로컬 연결을 실기기에서 검증할지, (B) 프론트 화면을 G10의 로컬 출처에서 제공할지, (C) 비전 프로그램이 백엔드로 직접 전달하도록 계약을 바꿀지를 함께 결정합니다. 브라우저 보안 검사를 끄는 설정을 배포 전제로 삼지 않습니다.

## 프론트엔드 제공 방식 비교 (결정 전)

| 판단 항목 | Amplify Hosting 정적 제공안 | G10 로컬 제공안 |
| --- | --- | --- |
| 비용·학교 계정 | 예상 빌드 시간·정적 파일 저장량·데이터 전송량을 기준으로 [Amplify Hosting 요금](https://aws.amazon.com/amplify/pricing/)을 산정하고, 학교 계정의 지원 서비스·크레딧·한도 적용 여부를 관리자에게 확인 | Amplify Hosting 사용료는 발생하지 않음. 백엔드·ai-engine용 EC2와 Supabase 비용 검토는 두 안 모두 필요 |
| 배포·운영 | Git 변경에 따른 빌드·배포 설정과 실패 시 되돌리기 절차 확인 | G10에 정적 파일을 설치·갱신하는 방법, 부팅 시 자동 시작, 장애 복구 절차와 운영 담당자를 정해야 함 |
| 브라우저·비전 연결 | 공개 HTTPS 화면에서 G10의 `localhost` 비전 프로그램으로 연결할 때 Local Network Access·CORS·권한 유지 여부를 실제 장비에서 검증 | 로컬 출처에서 비전 프로그램 연결을 검증하고, 카메라·마이크 권한 및 EC2 백엔드로의 HTTPS 요청 경로를 확인 |

학교 계정의 실제 지원 범위와 예상 사용량은 아직 확인되지 않았으므로 비용 우위나 배포 방식을 확정하지 않습니다. 2026-10-14 팀 회의에서 비용 견적·G10 운영 책임·실기기 연결 결과를 비교해 프론트엔드 제공 위치를 결정합니다.

## HTTP 통신 경로

다음 그림은 **Amplify안을 채택할 경우**의 통신 경로입니다. G10 로컬 제공안을 채택하면 정적 파일의 제공 위치와 `/backend/*` 프록시 구성을 별도로 설계해야 합니다.

```mermaid
flowchart LR
    U[키오스크 브라우저] -->|HTTPS: 화면과 정적 파일| F[Amplify Hosting]
    U -->|HTTPS: /backend/*| F
    F -->|200 역방향 프록시: HTTPS| P[EC2의 API TLS 진입점 :443]
    P -->|호스트 내부 또는 Docker 네트워크| B[backend :8000]
    B -->|Docker 내부 HTTP| A[ai-engine :8001]
    B -->|암호화 연결| D[(Supabase PostgreSQL)]
    B -->|필요한 기능에서만 HTTPS| X[외부 AI API]
```

1. 브라우저는 Amplify가 제공한 같은 출처의 `/backend/*`로 백엔드 요청을 보냅니다. Amplify의 200 역방향 프록시 규칙이 `/backend/<*>`를 `https://<API 도메인>/<*>`로 전달합니다. API 도메인과 유효한 TLS 인증서는 실제 배포 전에 마련해야 합니다. Amplify 역방향 프록시의 대상은 HTTPS여야 합니다.
2. EC2의 TLS 진입점은 요청을 backend의 8000 포트로 전달합니다. TLS 구현 방식(호스트 역방향 프록시 또는 별도 컨테이너)과 인증서 발급·갱신 방식은 배포 구현 PR에서 정합니다.
3. backend는 Docker 내부 주소 `http://ai-engine:8001`로 ai-engine을 호출합니다. 브라우저는 ai-engine에 직접 요청하지 않습니다.
4. Supabase 연결 정보와 외부 AI API 비밀값(`OPENAI_API_KEY` 등)은 백엔드 실행 환경에서만 관리합니다. 프론트엔드 빌드나 Git 저장소에 넣지 않습니다. 주입 방식(EC2의 Git 밖 `.env` 파일 또는 SSM Parameter Store SecureString)은 배포 구현 PR에서 정합니다.

외부 수신 포트는 HTTPS 443을 기준으로 설계합니다. 8000·8001·SSH 22는 직접 공개하지 않습니다. HTTP 80의 사용 여부는 인증서 발급·리디렉션 방식이 정해질 때 결정합니다. 현재 EC2 템플릿의 보안 그룹에는 수신 규칙이 없으므로 배포 전 별도 변경이 필요합니다. 송신은 backend가 Supabase와 외부 AI API(`api.openai.com`)에 연결해야 하므로 현재의 기본 송신 허용을 유지하고, 송신을 제한할 경우에도 필요한 HTTPS 443 경로를 열어 둡니다. 운영용 Compose를 만들 때도 ai-engine에 호스트 공개용 `ports:`를 추가하지 않습니다.

## 기존 코드와의 관계

- 프론트엔드 API 기본 경로는 `/backend/`입니다. 로컬 Vite와 프론트엔드 Docker의 Nginx는 각각 자체 프록시를 사용합니다. Amplify 배포 시에는 **Amplify의 재작성 규칙을 별도로 설정**해야 합니다. [프론트엔드 실행 안내](../frontend/README.md), [Nginx 설정](../frontend/nginx.conf.template), [Vite 설정](../frontend/vite.config.ts)
- 현재 backend의 세션·특징 전송 API는 준비돼 있지만 상품·장바구니·주문 API와 DB 연결은 대기 중입니다. 이 배포 구조 결정만으로 해당 기능이 완료되지는 않습니다. [백엔드 안내](../backend/README.md)
- 비전 관측값은 G10에서 계산해 브라우저가 기존 `vision` 필드로 전달하는 안이 제안됐으나, 로컬 브라우저 통신과 프론트 제공 위치는 2026-10-14 팀 결정 전까지 미정입니다. 직접 백엔드 전송안은 현재 계약과 달라 별도 합의가 필요합니다.
- 기존 `/health`는 프로세스 상태만 나타내고, 백엔드→ai-engine 연결은 이미 `GET /api/v1/connectivity`로 확인할 수 있습니다. 배포 후에는 프론트엔드 → 백엔드, 백엔드 → ai-engine, 백엔드 → DB를 각각 확인합니다.
- 실시간 전달(WebSocket 또는 SSE)이 최종 요구사항이면 Amplify 프록시를 통한 동작을 별도 검증하고, 지원되지 않는 경로는 HTTPS API의 직접 호출과 출처 허용 정책을 팀에서 결정합니다. 직접 호출 시에는 backend `CORS_ORIGINS`에 Amplify 도메인을 넣고 필요한 메서드(PATCH·DELETE)와 `Idempotency-Key` 헤더를 허용해야 합니다. 현재 `main`의 CORS는 GET·POST와 `Content-Type`만 허용합니다. 현재 HTTP API의 경로 확정과 실시간 통신 방식 결정은 분리합니다.

## 프론트엔드 담당자 리뷰 요청

아래 항목을 확인하고 PR 리뷰에 **가능 / 수정 필요 / 추가 결정 필요**로 남겨 주세요.

1. 운영 프론트엔드를 Amplify의 정적 Vite 빌드로 제공해도 되는지, `frontend/dist` 산출물과 monorepo 빌드 설정에 빠진 것이 없는지.
2. 현재 프론트의 `/backend/` API 기본 경로를 운영에서도 유지할 수 있는지. Amplify 규칙에서 접두사 제거 후 경로·쿼리·요청 본문·메서드가 백엔드에 정확히 도착해야 합니다.
3. 장바구니·주문 API의 `Idempotency-Key`, PATCH·DELETE, 오류 상태·`Retry-After`가 프록시를 거쳐도 필요한 형태로 전달되는지. PR #36의 음성 요청 접수(`POST /api/v1/sessions/{session_id}/voice/requests`, `Idempotency-Key` 필수)와 상태 조회(GET 폴링)도 함께 검증해 주세요. 각 API가 실제 백엔드에 반영된 뒤 통합 검증할 항목도 표시해 주세요.
4. SPA 화면 경로 재작성 규칙보다 `/backend/*` 프록시 규칙을 우선 적용할 수 있는지.
5. 실제 키오스크 브라우저에서 HTTPS 카메라·마이크 권한과 음성 기능을 사용할 수 있는지. Chrome Web Speech API 사용 시 학교 네트워크에서 브라우저의 외부 음성 인식 연결이 가능한지도 확인해 주세요. 프레임을 서버로 보내는 안이면 카메라 권한과 대역폭도 확인해야 합니다. WebSocket/SSE가 첫 배포에 꼭 필요한지도 알려 주세요.
6. 운영 빌드에서 개발 샘플 모드가 꺼지고, 현재 로컬 프록시 설정에만 의존하는 코드가 없는지.
7. G10의 로컬 비전 프로그램을 쓸 경우 Amplify HTTPS 화면에서 localhost 연결 권한을 실기기에서 안정적으로 유지할 수 있는지, 아니면 화면의 로컬 제공이 필요한지.

## 다른 담당자 리뷰 요청 및 배포 전 조건

- **백엔드:** 프록시 뒤의 경로·헤더 처리, 세션 접근 정책, DB 접속 역할, 비밀값 주입 방식, 직접 포트 공개 여부를 검토합니다.
- **AI·비전:** ai-engine 호출의 현재 기본 타임아웃은 2초(`AI_ENGINE_TIMEOUT_SECONDS`)입니다. 백엔드의 OpenAI 호출은 별도 비동기 처리·상태 조회 경로이며 기본 10초(`OPENAI_TIMEOUT_SECONDS`)로 검토합니다(PR #36). 비전 프레임 처리 위치와 이미지 의존성·모델 포함 여부를 정한 뒤 EC2의 CPU·메모리 요구량을 측정합니다. 개발 노트북의 MediaPipe 3종 처리 시간은 EC2 실측값을 대신하지 않으며, 프레임 처리 시간과 1~3초 특징 창에 대한 ai-engine 호출 타임아웃은 별개입니다.
- **인프라:** 학교 AWS 계정의 비용 승인자·지원 한도, API 도메인·TLS 방식, 443 보안 그룹, SSM 접속, Docker Compose 설치·재부팅 자동 시작, 로그·백업·복구 절차를 정합니다. 비용 승인 전에는 EC2를 생성하지 않습니다.
- 리뷰 결과와 팀 결정 날짜를 PR에 기록하고, 합의가 끝나면 [루트 README](../README.md)와 [AWS 안내](aws/README.md)의 `제안`·`검토` 표현을 확정 구성에 맞게 갱신합니다. 공용 기존 문서의 수정은 영향받는 담당자 동의를 받은 뒤 별도 PR에서 수행합니다.

## 참고

- [프로젝트 시스템 아키텍처와 현재 구현 상태](../README.md)
- [로컬 Docker Compose](../docker-compose.yml)
- [AWS EC2 초기 호스트 준비](aws/README.md)
- [AWS Amplify 역방향 프록시 재작성 예시](https://docs.aws.amazon.com/amplify/latest/userguide/redirect-rewrite-examples.html#reverse-proxy-rewrite)
