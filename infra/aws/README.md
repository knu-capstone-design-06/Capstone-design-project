# AWS EC2 개발 서버 준비

시스템 아키텍처의 **backend + ai-server 서버**를 위한 초기 EC2 호스트입니다.
프론트엔드는 추후 Amplify 배포를 검토하고, DB는 서울 리전 Supabase 프로젝트를 사용합니다.
현재 템플릿은 **서버 기반만 생성**합니다. 업무 API 공개·도메인·HTTPS·앱 배포는 별도 작업입니다.

## 계정과 위치

- AWS 계정: 학교에서 제공한 계정. 비용 승인 담당자와 사용 한도는 학교 계정 관리자에게 확인해야 합니다.
- 리전: `ap-northeast-2`(서울), Supabase DB와 동일한 지역입니다.
- VPC·서브넷: 학교 계정의 기본 VPC와 서울 `ap-northeast-2a` 서브넷을 확인했습니다. ID는 저장소에 적지 않고 배포 전에 계정에서 다시 조회합니다. 선택한 서브넷에는 인터넷 게이트웨이 경로와 자동 공인 IP 할당이 있습니다.
- AMI: 스택을 처음 만들 때 SSM 공개 파라미터에서 Amazon Linux 2023 x86_64 ID를 조회해 `AmiId`에 전달합니다. 이후 업데이트에서는 저장된 ID를 재사용합니다.

## 생성 내용

[`ec2-baseline.yaml`](ec2-baseline.yaml) CloudFormation 스택은 `t3.small`(2 vCPU, 2 GiB),
암호화한 30 GiB gp3 루트 디스크, Docker Engine, SSM 접속용 최소 IAM 역할,
수신 규칙이 없는 보안 그룹(송신 규칙은 따로 적지 않아 AWS 기본값인 모든 송신 허용)을 만듭니다. SSH 키와 22/8000/8001 포트는 만들거나 열지 않습니다.
공인 IPv4는 SSM 및 패키지 설치에 필요한 인터넷 송신을 위해 할당됩니다.
EC2 메타데이터는 IMDSv2만 허용하고, T3 CPU 크레딧은 `standard`로 설정했습니다.

SSM Session Manager에서 접속합니다(로컬 AWS CLI 접속에는 Session Manager 플러그인이 필요합니다). 사용자 데이터에는 비밀번호·키·DB 연결 정보가 없습니다.
이 템플릿에는 앱 컨테이너와 Docker Compose 설치는 포함되지 않습니다.
실제 비전 모델의 메모리·CPU 요구량은 아직 측정하지 않았으므로, `t3.small`은 초기 연결 검증용입니다.
백엔드와 AI 서버를 함께 실행할 때 메모리가 부족할 수 있어 배포 후 사용량을 확인해야 합니다.

## 비용 견적 (2026-10-07, 서울 리전, 30일 720시간 연속 실행)

| 항목 | 단가 | 30일 계산 |
| --- | ---: | ---: |
| Linux EC2 t3.small | $0.026/시간 | $18.72 |
| 공인 IPv4 1개 | $0.005/시간 | $3.60 |
| gp3 30 GiB | $0.0912/GiB·월 | 약 $2.74 |
| 합계 | | **약 $25.06** |

AWS의 2026-10-07 공개 가격 조회 결과입니다. 네트워크 전송, 세금, 추가 리소스는 제외했고
계정의 무료 크레딧·할인 적용 여부는 확인해야 합니다. EC2를 중지해도 디스크 비용은 지속될 수
있습니다. AWS Budgets 알림은 지출을 알려주지만 결제를 자동 차단하지는 않습니다.
단가 출처: [EC2 온디맨드 요금](https://aws.amazon.com/ec2/pricing/on-demand/)(서울 Linux `t3.small`은 AWS Pricing API 조회값 $0.026/시간),
[VPC 공인 IPv4 요금](https://aws.amazon.com/vpc/pricing/), [EBS gp3 요금](https://aws.amazon.com/ebs/pricing/).
`t3.small`의 무료 이용 대상 표시는 계정의 실제 무료 혜택 보장을 뜻하지 않습니다.
이 계정에는 다른 실행 중인 EC2가 있고, 현재 IAM 사용자는 조직 정책으로 Free Tier 사용량과
청구 내역을 조회할 수 없습니다. 계정 관리자에게 남은 크레딧과 적용 기간을 확인해야 합니다.

## 확인 및 배포 절차

AWS CLI는 만료 가능한 브라우저 로그인 프로필 `capstone`을 사용합니다. 비밀 액세스 키를
저장소에 넣지 않습니다. 계정·리전을 확인하고 템플릿을 검증합니다.

```powershell
aws sts get-caller-identity --profile capstone
aws cloudformation validate-template --profile capstone --region ap-northeast-2 --template-body file://infra/aws/ec2-baseline.yaml
```

변경 세트만 준비할 때(이 명령은 서버를 생성하지 않습니다):

```powershell
$vpcId = aws ec2 describe-vpcs --profile capstone --region ap-northeast-2 --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text
$subnetId = aws ec2 describe-subnets --profile capstone --region ap-northeast-2 --filters "Name=vpc-id,Values=$vpcId" Name=availability-zone,Values=ap-northeast-2a --query 'Subnets[0].SubnetId' --output text
$amiId = aws ssm get-parameter --profile capstone --region ap-northeast-2 --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query 'Parameter.Value' --output text
aws cloudformation deploy --profile capstone --region ap-northeast-2 `
  --stack-name capstone-ec2-dev `
  --template-file infra/aws/ec2-baseline.yaml `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides "VpcId=$vpcId" "SubnetId=$subnetId" "AmiId=$amiId" `
  --no-execute-changeset
```

스택이 실제로 생성된 뒤에는 다음처럼 **이 스택의** 인스턴스와 SSM 상태를 확인합니다.

```powershell
aws cloudformation describe-stacks --profile capstone --region ap-northeast-2 --stack-name capstone-ec2-dev --query 'Stacks[0].{Status:StackStatus,Outputs:Outputs}'
$instanceId = aws cloudformation describe-stacks --profile capstone --region ap-northeast-2 --stack-name capstone-ec2-dev --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" --output text
aws ssm describe-instance-information --profile capstone --region ap-northeast-2 --filters "Key=InstanceIds,Values=$instanceId" --query 'InstanceInformationList[].{Id:InstanceId,Status:PingStatus}'
```

`CREATE_COMPLETE`와 SSM `Online`은 사용자 데이터의 Docker 설치 성공을 뜻하지 않습니다. 로컬에
[Session Manager 플러그인](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)을 설치한 뒤 접속해서 확인합니다.

```powershell
aws ssm start-session --profile capstone --region ap-northeast-2 --target $instanceId
```

접속한 인스턴스의 셸에서:

```sh
sudo cloud-init status --wait
sudo systemctl is-active docker
sudo docker info
```

실패하면 `/var/log/cloud-init-output.log`에서 초기화 오류를 확인합니다.

앱을 실제 공개할 때는 도메인·TLS·443 수신 규칙과 서버 운영 방식을 별도 검토합니다.
리소스 정리 시 `cloudformation delete-stack`이 **서버와 루트 디스크를 제거**하므로
저장할 데이터가 있는지 확인한 뒤 실행해야 합니다.

이미 만든 스택을 수정할 때는 새 AMI를 조회하지 않고, `describe-stacks`의
`Parameters`에서 기존 `AmiId`를 읽어 `--parameter-overrides`에 재사용합니다.

```powershell
$amiId = aws cloudformation describe-stacks --profile capstone --region ap-northeast-2 --stack-name capstone-ec2-dev --query "Stacks[0].Parameters[?ParameterKey=='AmiId'].ParameterValue | [0]" --output text
```

위 `deploy` 명령에는 `--no-execute-changeset`를 유지하고, 출력된 변경 세트 ARN을
`aws cloudformation describe-change-set --change-set-name <ARN> --stack-name capstone-ec2-dev`로 확인합니다.
`Ec2Instance`의 `Replacement`가 `True`이면 실행하지 말고 원인을 확인합니다.
AMI ID를 의도적으로 바꾸면 인스턴스가 교체되고 루트 디스크의 데이터와 공인 IP가 바뀔 수 있습니다.
