# Jev 큰 버튼 제안의 유효기간과 적용 기준

이 문서는 메뉴 이용 중 “버튼을 크게 바꿀까요?”라고 묻는 큰 버튼 제안을 다룬다. 사용자 수락 뒤 버튼을 크게 표시한다. 2026-11-20 기준 프론트·비전·AI 담당자는 바로 다음 연속 창까지 한 번 전달하는 B안을 검토 방향으로 지지했고, 적용 임계값은 보류하고 그림자 모드를 유지하자는 의견을 남겼다. #97에서 비전 담당자는 Jev 답이 없을 때 현재 창의 규칙표를 따르는 안을 제안했다. 아래 표를 결정 기록으로 사용한다. [프론트 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5989459301) · [비전 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5979172342) · [AI 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5979372284) · [비전 후속 의견](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/97#issuecomment-7043157007)

## 현재 구현과 검증 범위

- 공용 계약의 `SupportDecision.preset`은 `large_button`을 허용한다. 현재 백엔드의 실제 지원 응답은 `none`이다. 큰 버튼 제안을 수락하는 프론트 흐름은 #70으로 병합됐다. [공용 계약](../contract/frontend-backend.openapi.yaml) · [백엔드 응답 모델](../backend/app/modules/sessions/schemas.py) · [PR #70](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/70)
- #77이 병합되면서 백엔드가 창마다 규칙표를 실행하고, 설정한 Jev 단계의 답을 백그라운드에서 기록하는 그림자 단계가 들어왔다. `JEV_STAGES` 기본값은 `off`다. 백엔드는 Jev 답을 기다리는 동안 원래 창의 `/features` 응답을 보낼 수 있다. 현재 백엔드 입력에는 4-1에 필요한 `fixes_recent`, 시선 및 비전 상황이 들어오지 않는다. [PR #77](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/77) · [병합 시점의 판단 층 설명](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/2dbb1549c3caeef55c731fdad820adbdf1bf9d7e/docs/Jev-Integration.md#10-판단-층-backend-구현-현황-2026-11-04) · [터치 후속 과업](Jev-Touch-Features.md)
- #95 이전 독립 검사는 백엔드 21개·Edge 25개 사례에서 수락 전 크기 유지, 수락 후 확대, 세션 전환·장애 시 화면 유지를 확인했다. 사용한 사본은 #77 `2aeb780`, 당시 #87 `25df409`이고 관측과 Jev 답은 모의 입력이었다. 그때 사용한 `support_choice`와 `0.75`는 화면 응답 분기를 시험하기 위한 입력이다. [PR #95 검증 범위](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95)

## 결정 1. 같은 방문의 다음 연속 창까지 전달

| 선택지 | 전달 조건 | 검토 결과 |
|---|---|---|
| A. 질문한 창까지만 | 같은 방문에서 원래 창 N의 응답을 아직 보낼 수 있을 때만 전달한다. | 현재 전송기는 요청 하나가 끝나야 다음 창을 보내고 5초 뒤 취소한다. 같은 요청에서 Jev까지 기다리는 구현은 후속 관측을 지연시킬 수 있어, 파일럿 비교 기준으로 둔다. |
| B. 바로 다음 창까지 | 원래 창 N의 답을 같은 방문의 바로 다음 연속 창 N+1의 응답에 최대 한 번 싣는다. 응답 시점까지 Jev 답과 현재 관측 근거가 유효해야 한다. | 프론트·비전·AI 담당자가 선호한 안이다. 연속성 확인, 시간 상한, 상태 변경과 폐기 후 재제안 기준은 아래 조건과 파일럿을 통해 확정한다. |

### 백엔드가 확인해야 할 조건

1. **같은 이용과 연속 관측**. 세션과 화면 방문을 확인하고, 순번과 N의 종료 시각·N+1의 시작 시각을 대조한다. 기본 계약은 방문 ID와 순번을 제공하지 않는다. 프론트의 `visit_id`와 `window_sequence`는 공동 파일럿 요청에만 포함되므로, 정식 수신·응답 형식과 원래 창 및 `decision_id` 연결을 먼저 협의한다. 순번 누락·역전, 불연속 구간, 완료된 세션, 이전 방문은 폐기한다. [터치 관측 창 합의안](Touch-Interaction-Contract-Proposal.md)
2. **전달할 창의 근거 재검사**. N+1에서 측정 가능 여부, 시선, 합의한 집계 기간의 `fixes_recent`, 우선순위가 앞서는 상황을 확인한다. 시선 `false`와 `null`, 상황 `none`과 `unknown`, 고침 횟수 0과 미수집을 구분한다. 시선·상황을 알 수 없는 창에서 제안할 조건과 누락 처리 방식은 팀 검토 항목이다. 4-1은 한 번 열린 지원을 다음 창의 `allowed_supports()` 후보에서 제외한다. 기존 `keep`도 근거가 사라진 창에서 반환될 수 있으므로, 발송 대기 중인 제안의 적합성을 별도로 다시 확인해야 한다. [비전 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5979172342) · [AI 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5979372284)
3. **화면 문맥과 반응**. 메뉴 재방문뿐 아니라 두 창 사이의 분류·쪽·Cart 버전·설정 변경을 폐기 조건에 포함할 범위를 정한다. 프론트는 화면 표시 직전 전경 상태, 열린 창, 주문·음성 상태와 현재 설정을 확인한다. 수락·명시적 거절·화면 이동에 따른 닫기는 구분한다. 사용자의 수동 적용·반응은 현재 프론트가 관리한다. 백엔드에서 이 조건을 검사하려면 표시 확인과 반응 전달 계약이 필요하다. [프론트 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5989459301)
4. **판단 대기와 실제 표시**. 동일 세션의 동일 제안은 재시도나 중복 응답에도 한 번만 유효해야 한다. N+1의 응답이 이미 끝났거나 시간 상한을 지나면 폐기한다. Jev 답 대기, 발송, 실제 화면 표시와 이용자 무응답을 각각 기록한다. 사용자 무응답 시간은 실제 표시 뒤부터 재는 방향을 검토한다. 현재 규칙표의 무응답 10초는 실험값이며 창 N의 `shown_t`부터 센다. 폐기 후 같은 방문에서 다시 묻는 조건과 시간 상한은 후속 결정이다. [AI 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5979372284)

## 결정 2. `proposal_fits.noul` 평가 후 임계값 결정

1. **판정값**. #77의 큰 버튼 4-1이 자체 질문을 만드는 경우, `state_scores` 단계에 포함된 `proposal_fits`의 `noul`(0~1)을 사용한다는 AI 담당 제안에 맞춘다. `support_choice`의 `confidence`와 `probabilities.large_button`은 다단계 실험의 비교 기록에 둔다. [AI 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5979372284)
2. **답이 없는 경우**. 파일럿 비교의 기준은 비전 담당이 제안한 **전달 시점의 규칙표 결과 유지**로 둔다. 제때 유효한 답이 없으면 늦은 답은 폐기하고, 현재 창에서 4-1의 근거와 방문·문맥 조건을 충족할 때에만 제안하는 안이다. 관측 근거 자체가 부족하면 Jev 상태와 무관하게 새 제안을 생략한다. AI 담당이 #95에서 찬성한 **큰 버튼에 한해 제때 유효한 Jev 답을 요구하는 예외안**을 같은 입력으로 비교한다. 시선·상황을 알 수 없어 4-1을 Jev 질문 없이 여는 경우도 별도로 센다. 두 안에서 크기 변경은 사용자 수락 후 적용한다. [비전 후속 의견](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/97#issuecomment-7043157007) · [AI 리뷰](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/95#pullrequestreview-5979372284)
3. **후보 기준과 파일럿**. AI 담당자가 출처(표준·관행·문헌)와 함께 후보 기준을 제안하고, 비전·프론트 담당자가 큰 버튼 제안이 적절했는지 라벨을 확인한다. 같은 창 묶음에서 규칙표 유지안과 Jev 답 필수안을 비교한다. 적절한 제안·불필요한 제안·놓친 제안, 같은 방문에서 반복해 묻는 수를 집계하고 제때 유효 답을 얻은 창, 답이 없거나 기한을 넘긴 창, 관측 부족 창을 나눠 본다. 파일럿 촬영분과 최종 평가분은 분리한다. 그림자 기록에는 실제 수락률이 없다.
4. **보류 해제**. 사용 모델·질문 버전, 사용한 라벨과 결과, 기준값의 출처와 적용 날짜를 남긴다. 근거가 확보될 때까지 임계값 적용을 보류한다.

## 백엔드가 준비할 파일럿 기록

- **입력과 식별**. 창 N과 N+1의 세션·방문·순번 및 관측 구간, 분석 가능 여부, 시선·상황과 `fixes_recent`의 결측 여부, 원래 판단과 제안 ID를 기록한다. 실제 입력 연결은 터치 T06·T07과 비전 전달 합의 뒤 진행한다.
- **응답 시각과 폐기 이유**. #77은 `WindowRecord.received_at`, `JevRecord.answered_at`와 `latency_ms`를 기록하고, 답이 없으면 `reason`을 `unavailable`·`mismatch`·`build_error`로 구분한다. 파일럿에서는 N·N+1의 HTTP 응답 종료와 대기·만료·현재 근거 부족으로 인한 폐기 이유를 함께 기록하고 세션별 기록을 내보낼 수 있어야 한다. 경과 시간 측정에는 백엔드의 모노토닉 시계를 사용하고, G10 관측 종료 시각과 비교할 때는 장비 간 시계 기준부터 확인한다. [병합된 창·Jev 기록 정의](https://github.com/knu-capstone-design-06/Capstone-design-project/blob/2dbb1549c3caeef55c731fdad820adbdf1bf9d7e/backend/app/modules/decision/schemas.py#L201)
- **비교 방법**. 대기 없는 같은 기록에 A와 B를 대입해 전달 가능한 건수, N+1에서 조건을 잃은 건수, 응답 지연 p50·p95를 비교한다. A에 서버 대기를 추가할 때의 요청 지연은 별도로 잰다. 발화 원문·카메라 프레임은 평가 기록에 넣지 않는다.
- **자료와 재현 절차**. 비전 담당 작업 폴더의 평가 키트 `llm_eval_kit_2026-11-08`에서 `reference_answers/E5_C.jsonl`의 `state_scores.proposal_fits`가 있는 행만 골라 `labels/window_cells.csv`와 `window_id`로 연결한다. 중복 ID와 연결 실패가 없음을 확인한 뒤 `rule_transition=open`인 행을 `rule_support`로 집계하면 127개 중 `large_button` 16개, `highlight_next_action` 111개다. 참조 답에는 창별 답 도착·HTTP 응답 종료 시각이 없어 채점 절차 확인에 사용한다. [평가 키트 위치와 구성](../experiments/eval_llm_2026-11-09/README.md#실행)
- **기존 비교의 범위**. 비전 담당이 인용한 두 실험은 Jev 호출 시간과 지원 전체의 결과를 기록했다. 후보 내 비교 137건의 규칙표와 Jev 집계는 각각 TP/FP/FN/TN 52/5/15/65, 51/5/16/65다. 합성 터치와 잠정 라벨을 사용한 집계이므로, 큰 버튼 전용 정확도와 G10의 N+1 전달 기한은 위 파일럿에서 별도로 확인한다. [11월 9일 비교와 시간 측정 한계](../experiments/eval_llm_2026-11-09/README.md) · [11월 12일 비교](../experiments/eval_llm_2026-11-12_rA/README.md)
- **코드 대조**. 큰 버튼 4-1이 열린 뒤 정상 창·시선 `false` 창·측정 불가 창에 모두 같은 `decision_id`의 `keep`이 반환되고 새 후보에는 큰 버튼이 없었다. 이 순서를 후속 재검사의 회귀 사례로 사용한다. [프론트 검증](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/97#pullrequestreview-5992461450) · [비전 검증](https://github.com/knu-capstone-design-06/Capstone-design-project/pull/97#pullrequestreview-5992556128)

## 결정 기록과 후속 구현

| 항목 | 상태 | 근거 확인일 |
|---|---|---|
| 1. 창 유효범위 | B안에 담당자 의견 일치. 방문·창 식별, 문맥 변경, 실제 시간 상한과 재제안 규칙은 미결 | 2026-11-20 · 프론트·비전·AI 리뷰 |
| 2. 적용 기준 | `proposal_fits.noul` 평가안을 기록. 수치 적용 보류와 그림자 모드 유지에 담당자 의견 일치 | 2026-11-20 · 프론트·비전·AI 리뷰 |
| 3. 제때 유효한 답이 없을 때 | 규칙표 유지안을 파일럿 비교 기준으로 제안. Jev 답 필수안과 비교한 뒤 적용 정책을 결정 | #95 AI 의견 · #97 비전 후속 의견 |

백엔드는 방문·창 식별과 기록 내보내기를, 프론트·비전 담당은 관측 입력과 큰 버튼 적합 라벨을, AI 담당은 기준값의 출처와 답의 해석을 검토한다. 파일럿 뒤 채택안, 결정 날짜·확인자, 근거 링크를 이 표에 기록한다. 이후 계약·구현 PR에 결정 기록과 회귀 테스트를 함께 반영한다. 검증할 경계는 늦거나 중복된 답, 방문·문맥 변경, 현재 관측 부족, 유효한 Jev 답이 없는 창, 사용자가 수락하기 전의 화면 유지다.
