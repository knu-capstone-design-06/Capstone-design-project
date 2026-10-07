# AWS EC2 개발 서버 준비

시스템 아키텍처의 **backend + ai-server 서버**를 위한 초기 EC2 호스트입니다.
프론트엔드는 추후 Amplify 배포를 검토하고, DB는 서울 리전 Supabase 프로젝트를 사용합니다.
현재 템플릿은 **서버 기반만 생성**합니다. 업무 API 공개·도메인·HTTPS·앱 배포는 별도 작업입니다.

## 계정과 위치

- AWS 계정: `514090179227`의 IAM 사용자로 접근을 확인했습니다. 계정 번호는 비밀키가 아닙니다.
- 리전: `ap-northeast-2`(서울), Supabase DB와 동일한 지역입니다.
- VPC: `vpc-068d5c56c83af9f7f`(기본 VPC).
- 서브넷: `subnet-0b9790aa4a9d650df`(`ap-northeast-2a`). 기본 라우팅 테이블의 인터넷 게이트웨이 경로와 자동 공인 IP 할당을 확인했습니다.
- AMI: SSM 공개 파라미터의 최신 Amazon Linux 2023 x86_64. 특정 AMI ID를 고정하지 않습니다.

## 생성 내용

[`ec2-baseline.yaml`](ec2-baseline.yaml) CloudFormation 스택은 `t3.medium`(2 vCPU, 4 GiB),
암호화한 30 GiB gp3 루트 디스크, Docker Engine, SSM 접속용 최소 IAM 역할,
수신 규칙이 없는 보안 그룹을 만듭니다. SSH 키와 22/8000/8001 포트는 만들거나 열지 않습니다.
공인 IPv4는 SSM 및 패키지 설치에 필요한 인터넷 송신을 위해 할당됩니다.
EC2 메타데이터는 IMDSv2만 허용하고, T3 CPU 크레딧은 `standard`로 설정했습니다.

SSM Session Manager에서 접속합니다. 사용자 데이터에는 비밀번호·키·DB 연결 정보가 없습니다.
이 템플릿에는 앱 컨테이너와 Docker Compose 설치는 포함되지 않습니다.
실제 비전 모델의 메모리·CPU 요구량은 아직 측정하지 않았으므로, `t3.medium`은 초기 연결 검증용입니다.

## 비용 견적 (2026-10-07, 서울 리전, 30일 720시간 연속 실행)

| 항목 | 단가 | 30일 계산 |
| --- | ---: | ---: |
| Linux EC2 t3.medium | $0.052/시간 | $37.44 |
| 공인 IPv4 1개 | $0.005/시간 | $3.60 |
| gp3 30 GiB | $0.0912/GiB·월 | 약 $2.74 |
| 합계 | | **약 $43.78** |

AWS의 2026-10-07 공개 가격 조회 결과입니다. 네트워크 전송, 세금, 추가 리소스는 제외했고
계정의 무료 크레딧·할인 적용 여부는 확인해야 합니다. EC2를 중지해도 디스크 비용은 지속될 수
있습니다. AWS Budgets 알림은 지출을 알려주지만 결제를 자동 차단하지는 않습니다.

## 확인 및 배포 절차

AWS CLI는 만료 가능한 브라우저 로그인 프로필 `capstone`을 사용합니다. 비밀 액세스 키를
저장소에 넣지 않습니다. 계정·리전을 확인하고 템플릿을 검증합니다.

```powershell
aws sts get-caller-identity --profile capstone
aws cloudformation validate-template --profile capstone --region ap-northeast-2 --template-body file://infra/aws/ec2-baseline.yaml
```

검토와 비용 확인 후 스택을 만들 때:

```powershell
aws cloudformation deploy --profile capstone --region ap-northeast-2 `
  --stack-name capstone-ec2-dev `
  --template-file infra/aws/ec2-baseline.yaml `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides VpcId=vpc-068d5c56c83af9f7f SubnetId=subnet-0b9790aa4a9d650df
```

스택이 `CREATE_COMPLETE`가 된 뒤 인스턴스 상태와 SSM 관리 상태를 확인합니다.

```powershell
aws cloudformation describe-stacks --profile capstone --region ap-northeast-2 --stack-name capstone-ec2-dev --query 'Stacks[0].{Status:StackStatus,Outputs:Outputs}'
aws ssm describe-instance-information --profile capstone --region ap-northeast-2 --query 'InstanceInformationList[].{Id:InstanceId,Status:PingStatus}'
```

앱을 실제 공개할 때는 도메인·TLS·443 수신 규칙과 서버 운영 방식을 별도 검토합니다.
리소스 정리 시 `cloudformation delete-stack`이 **서버와 루트 디스크를 제거**하므로
저장할 데이터가 있는지 확인한 뒤 실행해야 합니다.
