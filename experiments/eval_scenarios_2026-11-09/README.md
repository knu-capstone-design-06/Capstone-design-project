# 시나리오 판단 실험(2026-11-09)의 GPT 실행기

AI 담당의 시나리오 판단 실험(규칙표에 없는 터치 패턴과 상황 조합으로 규칙표 · Jev · 범용 LLM을 비교, 2026-11-09)에서 GPT를 부른 실행기 `run_llm.py`의 고친 판입니다. 다음 실행부터 이 판을 씁니다.

실험의 데이터 · 사전 등록 · 채점기 · 저장된 실행 기록은 저장소에 없고 AI 담당의 재현 자료(`jev_touch_experiment_repro`)에 있습니다. 재현 자료 안의 `run_llm.py`는 저장된 실행을 만든 판 그대로 두었습니다(`MANIFEST.sha256`에 해시가 있고, `eval_llm_2026-11-09`의 `--repro` 도구가 이 자료를 읽습니다).

## 무엇을 고쳤나

재현 자료의 실행기는 HTTP 시도마다 타이머를 다시 시작했습니다. 그래서 `calls.jsonl`의 `latency_ms`에는 답을 받은 마지막 시도의 시간만 남고, 실패한 시도, 재시도 전 대기, temperature 0을 거부당한 요청의 시간이 빠졌습니다. 1초 제한 채점은 창마다 `latency_ms`를 더해 판정했으므로, 재시도가 있었던 창은 실제보다 빠르게 보일 수 있었습니다(#85 리뷰의 지적).

이 판은 같은 요청을 보내고, `calls.jsonl`의 줄마다 `eval_llm_2026-11-09/tools/call_time.py`의 시간 필드를 더 남깁니다.

| 필드 | 뜻 |
|---|---|
| `latency_ms`, `retries` | 그대로입니다. 답을 받은 시도의 시간, 받아들여진 요청의 HTTP 재시도 횟수 |
| `http_attempts` | 이 단계 요청의 모든 HTTP 시도. 시도마다 `ms`(걸린 시간), `result`(`ok`, `http 503`, `TimeoutError`, `http 400, temperature refused` 등), `wait_ms`(다음 시도 전 대기) |
| `request_ms` | 그 시도와 대기의 합 |
| `cumulative_ms` | 이 단계의 `request_ms`에 같은 창의 앞 단계 값을 더한 것. 창의 마지막 줄에서는 창의 첫 요청부터 답까지의 시간 |

- 실패한 줄(`error`)에도 새 필드 세 개가 남습니다.
- `summary.json`에 창 단위 시간(`window_ms_p50`, `window_ms_p95`), 1초 안에 답한 창 수(`windows_within_1s`), HTTP 시도가 둘 이상이었던 호출 수(`calls_with_more_than_one_http_attempt`)가 더해집니다.
- 프롬프트, JSON 스키마, 재시도 규칙(429 · 500 · 502 · 503은 2 · 4 · 8초 뒤 세 번까지, 시간 초과와 읽을 수 없는 답은 바로 한 번), 답과 기존 필드는 바뀌지 않습니다.

## 1초 제한을 채점할 때

새 실행의 1초 판정은 `latency_ms`의 합이 아니라 창 마지막 줄의 `cumulative_ms`로 합니다. `call_time.whole_ms(줄)`이 이 값을 돌려줍니다. 재현 자료의 채점기(`why/score_deadline.py`, `v2/score_heldout.py`, `sit/score_sit.py`)는 `latency_ms`를 더하므로, 새 실행을 채점하기 전에 채점기도 이 값을 읽도록 바꿔야 합니다. 채점기는 재현 자료에 있어 이 폴더에서는 바꾸지 않았습니다.

저장된 실행의 숫자는 바뀌지 않습니다. 저장된 호출 기록 129개 파일(17,536줄)에서 재시도가 있었던 호출은 18건이고, 논문 표에 쓴 세트의 GPT 실행에는 0건이며, 나머지도 1초 판정이 달라지지 않습니다(#85 리뷰에 적은 확인).

## 실행

저장소 루트에서 실행합니다. 표준 라이브러리만 쓰고, `call_time.py`를 `experiments/eval_llm_2026-11-09/tools/`에서 불러옵니다(두 폴더가 저장소 배치대로 있어야 합니다). 키는 `--env`로 준 파일의 `OPENAI_API_KEY`에서 읽고, 출력이나 기록에 남기지 않습니다. 호출하면 비용이 듭니다.

```powershell
$R = "<AI 담당의 재현 폴더 jev_touch_experiment_repro>"
python experiments\eval_scenarios_2026-11-09\tools\run_llm.py --kit "$R\novel\kit" --arm NOVEL_SUM --model gpt-4o-mini --env backend\.env --out "<결과 폴더>" --workers 2
```

인자는 재현 자료의 실행기와 같습니다(`--kit`, `--arm`, `--model`, `--env`, `--out`, `--limit`, `--workers`, `--timeout`, `--windows`, `--reasoning-effort`).

## 테스트

```
python -m unittest discover -s experiments/eval_scenarios_2026-11-09/tests -v
```

HTTP 응답 · 시계 · 대기를 가짜로 바꿔 돌리므로 API를 부르지 않습니다. 확인하는 경우는 재시도 없는 호출, 503 뒤 대기하고 다시 보낸 호출, temperature 0을 거부당해 다시 보낸 호출, 시간 초과, 읽을 수 없는 답, 끝내 실패한 호출, 두 단계 창의 누적(첫 단계에 재시도가 있으면 `latency_ms` 합은 600 ms인데 실제는 2,900 ms), 첫 단계가 실패한 창, 실행 전체(`calls.jsonl`과 `summary.json`)입니다.
