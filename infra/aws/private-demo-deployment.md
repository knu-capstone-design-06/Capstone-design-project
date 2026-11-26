# EC2 비공개 시연 배포 및 검증

서울 리전(`ap-northeast-2`)의 시연용 EC2에서 Docker Compose로 주문 시연을 실행한다. 기준 호스트는 개인 AWS 계정에서 콘솔로 준비한 Amazon Linux 2023(x86_64) 인스턴스다. 시연 PC는 SSM 포트 포워딩으로 EC2의 프론트에 접속하고, 브라우저는 같은 출처의 `/backend/` 경로를 사용한다.

```text
시연 PC 127.0.0.1:18080 → SSM → EC2 127.0.0.1:8080 (frontend)
  └─ /backend/ → Compose 내부 backend:8000 → 내부 ai-engine:8001
                                      └─ DB 모드일 때 시연용 Supabase
```

## 1. 호스트 준비

1. 서울 리전의 EC2 콘솔에서 시연 인스턴스 한 대를 확인한다. 초기 사양은 `t3.small`과 암호화한 `gp3` 루트 디스크 30 GiB다. 보안 그룹은 인바운드 규칙 0개로 두고 SSM과 패키지 저장소에 연결할 수 있는 아웃바운드 경로를 사용한다. 공인 IPv4를 할당하는 구성에서는 인터넷 게이트웨이로 나가는 경로가 있는 서브넷을 사용한다. [EC2 콘솔 생성 안내](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-launch-instance-wizard.html)
2. 인스턴스에 `AmazonSSMManagedInstanceCore` 권한을 가진 EC2용 인스턴스 프로파일을 연결한다. 시연 인스턴스가 `Running`이고 상태 검사를 통과하면 EC2 콘솔에서 **연결 → Session Manager**로 셸을 연다. 시연 PC에서 터널을 여는 사용자의 AWS 권한은 대상 인스턴스와 포트 포워딩 세션 문서에 대해 별도로 필요하다. [SSM 인스턴스 권한](https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-instance-permissions.html) · [세션 시작 안내](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)
3. 시연 PC에 AWS CLI v2와 Session Manager 플러그인을 준비한다. 시연 인스턴스가 속한 개인 계정용 프로파일을 사용한다. 예를 들어 브라우저 인증을 사용하는 경우 `aws login --profile capstone-personal --region ap-northeast-2`로 연결한다. [AWS CLI 로그인 안내](https://docs.aws.amazon.com/cli/latest/reference/login/) · [Session Manager 플러그인 설치](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)

콘솔에서 수동 생성한 Amazon Linux 2023 호스트에서는 SSM 셸에서 다음 명령으로 Docker Engine과 Git을 설치한다. Docker가 이미 설치된 호스트에서는 서비스와 버전을 확인한다. [Amazon Linux Docker 설치](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-docker.html)

```bash
sudo cloud-init status --wait
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo systemctl is-active docker
sudo docker info --format '{{.ServerVersion}}'
```

아래 명령으로 Compose와 이미지 빌드에 사용하는 Buildx 플러그인을 확인한다. 플러그인이 없으면 공식 안내에 따라 설치한 뒤 재확인한다. 아래 배포 명령은 `sudo docker compose`를 사용하므로 수동 설치 시 플러그인을 `/usr/local/lib/docker/cli-plugins`에 둔다. [Docker Compose 수동 설치 안내](https://docs.docker.com/compose/install/linux/#install-the-plugin-manually) · [Docker Buildx 설치 안내](https://github.com/docker/buildx#installing)

```bash
sudo docker compose version
sudo docker compose up --help | grep -F -- '--wait-timeout'
sudo docker buildx version
```

## 2. 실행할 버전과 환경 준비

SSM 셸에서 승인된 읽기 권한으로 저장소를 `~/capstone-demo/repo`에 준비한다. 배포와 이전 버전 복귀에 같은 Compose 프로젝트 이름을 사용한다. 시연마다 배포 커밋 SHA를 기록한다.

```sh
deploy_root="$HOME/capstone-demo"
repo="$deploy_root/repo"
demo_env="$deploy_root/demo.env"
umask 077
mkdir -p "$deploy_root/releases"
touch "$demo_env"
chmod 600 "$demo_env"

git -C "$repo" fetch origin main
printf '배포할 승인된 main 커밋 SHA: '
read -r release
release_id=$(git -C "$repo" rev-parse --verify "${release}^{commit}")
git -C "$repo" merge-base --is-ancestor "$release_id" origin/main
```

커밋 확인이 성공하면 아래를 실행한다. 같은 SHA의 릴리스 디렉터리를 이미 준비했다면 해당 디렉터리를 재사용한다.

```sh
release_dir="$deploy_root/releases/$release_id"
if [ ! -d "$release_dir" ]; then
  git -C "$repo" worktree add --detach "$release_dir" "$release_id"
fi
```

`demo.env`는 호스트의 저장소 밖에 보관한다. 서버 환경변수는 승인된 비밀 저장소에서 가져와 호스트에서 입력하며, 팀과 공유하는 실행 기록에는 설정 이름과 활성화 여부만 남긴다.

| 시연 범위 | 환경변수 |
| --- | --- |
| 기본 연결 및 터치 주문 | `OPENAI_API_KEY=`, `JEV_API_KEY=`, `JEV_STAGES=off`, `VOICE_EXECUTE_TOOLS=false`, `DATABASE_URL=` |
| DB 저장 및 재시작 검증 | 검증용 프로젝트의 `kiosk_backend` 전용 TLS 연결 문자열을 `DATABASE_URL`에 설정한다. 사전에 마이그레이션과 상품 시드 상태를 확인한다. [DB 설정](../../db/README.md) |
| 실제 음성 주문까지 시연 | 팀의 `OPENAI_API_KEY`를 서버에 주입하고 `VOICE_EXECUTE_TOOLS=true`를 설정한다. 시연 PC 브라우저에서 마이크 권한을 허용한다. [백엔드 음성 설정](../../backend/README.md) |

## 3. 배포 및 SSM 접속

릴리스별 이미지 태그를 만드는 Compose 파일을 EC2의 저장소 밖에 둔다. 같은 SHA의 이미지 세 개를 이미 빌드했다면 `dc build`를 생략한다. 이전 이미지와 해당 릴리스 디렉터리는 다음 배포가 검증될 때까지 보관한다.

```sh
cat > "$deploy_root/release-images.yml" <<'YAML'
services:
  frontend:
    image: capstone-demo-frontend:${RELEASE_ID:?set RELEASE_ID}
  backend:
    image: capstone-demo-backend:${RELEASE_ID:?set RELEASE_ID}
  ai-engine:
    image: capstone-demo-ai-engine:${RELEASE_ID:?set RELEASE_ID}
YAML

dc() {
  sudo env RELEASE_ID="$release_id" docker compose -p capstone-demo \
    --env-file "$demo_env" -f "$release_dir/docker-compose.yml" \
    -f "$deploy_root/release-images.yml" "$@"
}

dc config --quiet
dc build
dc up -d --no-build --pull never --wait --wait-timeout 180
dc ps
curl -fsS http://127.0.0.1:8080/backend/health
```

각 명령의 성공을 확인하고 다음 명령으로 진행한다. 설정 유효성만 확인할 때는 `config --quiet`를 사용한다. 시작 실패 시 `dc ps`, `dc logs --tail=80 backend frontend ai-engine`으로 원인을 확인하고, 공유하는 로그에서는 인증정보와 세션 식별자를 가린다. [Compose config](https://docs.docker.com/reference/cli/docker/compose/config/) · [Compose up](https://docs.docker.com/reference/cli/docker/compose/up/)

시연 PC의 별도 PowerShell에서 AWS CLI 프로파일을 고른다. 첫 명령의 계정 ID를 EC2 콘솔의 계정 ID와 대조한다. 두 계정이 같고 `Online`이 출력되면 포트 포워딩을 연다.

```powershell
$awsProfile = Read-Host '시연용 개인 AWS CLI 프로파일 이름'
aws sts get-caller-identity --profile $awsProfile --region ap-northeast-2 --query Account --output text
$instanceId = Read-Host '위 계정과 서울 리전을 확인한 시연 EC2 인스턴스 ID'
aws ssm describe-instance-information --profile $awsProfile --region ap-northeast-2 `
  --filters "Key=InstanceIds,Values=$instanceId" --query 'InstanceInformationList[0].PingStatus' --output text
```

같은 PowerShell에서 아래 명령을 실행하고 터널이 열린 동안 브라우저에서 `http://127.0.0.1:18080/`을 사용한다.

```powershell
aws ssm start-session --profile $awsProfile --region ap-northeast-2 `
  --target $instanceId --document-name AWS-StartPortForwardingSession `
  --parameters 'portNumber=8080,localPortNumber=18080'
```

## 4. 시연 검증

1. 시연 PC에서 `/backend/health` 응답의 `status=ok`, `service=backend`를 확인한다. 같은 터널에서 저장소의 `backend/`를 작업 위치로 두고 아래 검사를 실행한다. `PASS`와 종료 코드 0은 프록시 경유, 내부 AI 연결, 세션 발급, 특징 전송이 성공했음을 뜻한다. [연결 검사 설명](../../backend/DEPLOYMENT_READINESS.md#연결-스모크-검사)

   ```powershell
   python -m app.modules.connectivity.smoke --base-url http://127.0.0.1:18080/backend
   ```

2. 브라우저에서 상품 목록을 열고 테스트 세션으로 상품 1개를 담아 모의 주문을 확정한다. 화면에 모의 주문번호가 표시되고 새 주문 시작 시 빈 장바구니가 보이면 통과다. 음성 실행을 켠 검증에서는 실제 마이크로 장바구니 반영을 확인한 뒤 화면에서 모의 주문을 확정한다.
3. DB 모드에서는 브라우저 주문과 별개인 테스트 세션으로 아래 API 검사를 실행한다. PowerShell은 같은 창을 유지해 원래 주문의 세션·본문·키를 재사용한다. 해당 키와 응답 본문은 시연 기록에 복사하지 않는다. [주문 API 계약](../../contract/frontend-backend.openapi.yaml)

   ```powershell
   $api = 'http://127.0.0.1:18080/backend/api/v1'
   $sessionId = (Invoke-RestMethod -Method Post -Uri "$api/sessions").session_id
   $session = "$api/sessions/$sessionId"
   $cart = Invoke-RestMethod -Uri "$session/cart"
   $cartBody = @{
       product_id = 'americano'
       temperature = 'iced'
       quantity = 1
       expected_version = $cart.version
   } | ConvertTo-Json -Compress
   $cart = Invoke-RestMethod -Method Post -Uri "$session/cart/items" `
       -Headers @{ 'Idempotency-Key' = [guid]::NewGuid().ToString() } `
       -ContentType 'application/json' -Body $cartBody
   $orderHeaders = @{ 'Idempotency-Key' = [guid]::NewGuid().ToString() }
   $orderBody = @{ expected_version = $cart.version } | ConvertTo-Json -Compress
   $order = Invoke-RestMethod -Method Post -Uri "$session/orders" `
       -Headers $orderHeaders -ContentType 'application/json' -Body $orderBody
   if ($order.status -ne 'simulated' -or !$order.order_id -or !$order.order_number) {
       throw '모의 주문 결과 확인 실패'
   }
   ```

4. EC2의 SSM 셸에서 `dc restart backend` 후 `dc up -d --no-build --pull never --wait --wait-timeout 180`을 실행한다. 새 연결 검사에서 `PASS`를 확인한 뒤, 앞의 PowerShell 창에서 같은 주문 요청을 다시 보낸다.

   ```powershell
   $replayed = Invoke-RestMethod -Method Post -Uri "$session/orders" `
       -Headers $orderHeaders -ContentType 'application/json' -Body $orderBody
   if ($replayed.status -ne 'simulated' -or $replayed.order_id -ne $order.order_id -or
       $replayed.order_number -ne $order.order_number) {
       throw '재시작 후 이전 주문 응답 재전송 실패'
   }
   'PASS: 재시작 후 동일 주문 결과'
   ```

   DB 검증 담당자는 해당 테스트 세션의 주문 행이 한 건인지도 확인한다. 검증 기록에는 배포 SHA, 저장 모드, 연결·터치·음성·재전송의 결과와 미실행 항목을 남긴다. [DB 검증 기록](../../docs/DB-Voice-Order-Integration-Verification-2026-11-16.md)

## 5. 이전 버전으로 복귀

배포 뒤 연결이나 주문 검증에 실패하면 시연을 멈추고 마지막으로 검증한 SHA를 선택한다. 앱 복귀의 전제는 이전 버전과 현재 DB 스키마의 호환이다. 스키마가 함께 바뀐 경우에는 별도 DB 복구 판단을 따른다. [백업·복구 절차](../../db/BACKUP_RESTORE.md)

```sh
printf '복귀할 마지막 검증 릴리스의 전체 SHA: '
read -r release_id
release_dir="$deploy_root/releases/$release_id"
sudo docker image inspect \
  "capstone-demo-frontend:$release_id" "capstone-demo-backend:$release_id" \
  "capstone-demo-ai-engine:$release_id" --format '{{.Id}}'
dc config --quiet
dc up -d --no-build --pull never --wait --wait-timeout 180
dc ps
```

이전 릴리스에 별도 환경 설정이 필요했다면 그때 사용한 승인된 설정을 적용한다. 복귀 후 같은 터널에서 연결 검사와 새 세션의 모의 주문을 다시 확인한다. 첫 배포에 실패해 검증된 이전 이미지가 없으면 시연을 중단하고 실패 원인을 확인한다.
