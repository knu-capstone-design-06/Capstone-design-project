"""Experiment A runner: ask a general LLM (OpenAI Chat Completions) the kit's questions, window by window.

Same state and question text Jev received (kit data/<arm>.jsonl + data/questions.json); the reply is forced
into a JSON schema (choice = one criteria key, noul = a probability). Writes the kit's answers file
({"window_id", "choice"}) and a per-call log (latency, tokens, answers, error). Standard library only.

Time: the copy in the reproduction bundle (jev_touch_experiment_repro/run_llm.py, kept as it is for the stored
runs) restarted its timer on every HTTP attempt, so a line's latency_ms left out a failed attempt, the wait after
it and a request refused for temperature 0. This copy sends the same requests and adds to every calls.jsonl line
the fields of experiments/eval_llm_2026-11-09/tools/call_time.py:
    http_attempts  every HTTP attempt of this stage's request, a refused body's included: {"ms", "result", "wait_ms"}
    request_ms     the sum of those attempts and waits
    cumulative_ms  request_ms of this stage plus that of the window's earlier stages: on the last stage's line, the
                   time from the window's first request to its answer
latency_ms and retries keep their meaning (the attempt that answered; the retries this stage used: the count is
not reset when the request is sent again without temperature, unlike run_gpt.py). An error
line carries the three new fields too. A 1-s rule reads the window's last line with call_time.whole_ms, not the sum
of latency_ms.

The key is read from an env file and never printed or written.
"""

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval_llm_2026-11-09" / "tools"))
from call_time import Attempts, add_ms, ms_since, whole_ms  # noqa: E402

API = "https://api.openai.com/v1/chat/completions"
SYSTEM = ("You are a decision model for an accessibility-adaptive ordering kiosk. You receive the state of one "
          "observation window and one or more questions. Answer every question from the state alone. For a "
          "`choice` question return exactly one key of its `criteria`. For a `noul` question return the "
          "probability (0 to 1) that the statement is true. Reply with JSON only.")
PLACEHOLDER = "<STAGE1_SCORES>"


def read_key(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAI_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    sys.exit(f"OPENAI_API_KEY not found in {env_file}")


def schema_for(questions: dict) -> dict:
    props = {}
    for name, q in questions.items():
        if q["type"] == "choice":
            props[name] = {"type": "string", "enum": list(q["criteria"])}
        elif q["type"] == "noul":
            props[name] = {"type": "number"}
        else:
            raise ValueError(f"question type {q['type']} not handled")
    return {"name": "answers", "strict": True,
            "schema": {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}}


def fill_stage1(state: dict, stage1: dict | None) -> dict:
    """Put stage-1 answers where the kit marks them; drop `jev` when stage 1 had no answer (kit README 3.4)."""
    if json.dumps(state).find(PLACEHOLDER) < 0:
        return state
    state = json.loads(json.dumps(state))
    if stage1 is None:
        state.pop("jev", None)
        return state
    for key, value in list(state.get("jev", {}).items()):
        if value == PLACEHOLDER:
            state["jev"][key] = stage1
    return state


class Client:
    def __init__(self, key: str, model: str, timeout: float, reasoning_effort: str | None = None):
        self.key, self.model, self.timeout = key, model, timeout
        self.reasoning_effort = reasoning_effort
        self.use_temperature = True   # reasoning models refuse temperature=0; dropped on the first refusal

    def ask(self, state: dict, questions: dict) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": json.dumps({"state": state, "questions": questions}, ensure_ascii=False)}],
            "response_format": {"type": "json_schema", "json_schema": schema_for(questions)},
        }
        if self.use_temperature:
            body["temperature"] = 0
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        data = json.dumps(body).encode("utf-8")
        retries = 0
        tries = Attempts()  # every HTTP attempt of this request, a refused body's included
        while True:
            req = urllib.request.Request(API, data=data, method="POST", headers={
                "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read())
                latency = ms_since(started)
                answers = json.loads(payload["choices"][0]["message"]["content"])
            except urllib.error.HTTPError as e:
                try:
                    message = e.read().decode("utf-8", "replace")
                except Exception:  # the connection dropped while the error body was read: the status still stands
                    message = ""
                tries.add(ms_since(started), f"http {e.code}")
                if e.code == 400 and "temperature" in body:
                    if "temperature" in message:
                        tries.items[-1]["result"] += ", temperature refused"
                        self.use_temperature = False
                        body.pop("temperature")
                        data = json.dumps(body).encode("utf-8")
                        continue
                    return self.failed(f"http 400: {message[:200]}", retries, tries)
                if e.code in (429, 500, 502, 503) and retries < 3:
                    retries += 1
                    tries.wait(2 ** retries)
                    continue
                return self.failed(f"http {e.code}", retries, tries)
            except Exception as e:  # timeout, bad JSON
                tries.add(ms_since(started), type(e).__name__)
                if retries < 1:
                    retries += 1
                    continue
                return self.failed(type(e).__name__, retries, tries)
            # the attempt answered (every except branch above leaves this pass), so it is recorded once here
            tries.add(latency, "ok")
            usage = payload.get("usage") or {}   # a null usage must not stop the run
            details = usage.get("completion_tokens_details") or {}
            return {"answers": answers, "latency_ms": round(latency), "retries": retries,
                    "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                    "reasoning_tokens": details.get("reasoning_tokens"), "model": payload.get("model"),
                    "http_attempts": tries.items, "request_ms": tries.total()}

    @staticmethod
    def failed(error: str, retries: int, tries: Attempts) -> dict:
        return {"error": error, "retries": retries, "http_attempts": tries.items, "request_ms": tries.total()}


def run_window(client: Client, questions_doc: dict, row: dict) -> tuple[dict, list[dict]]:
    logs, stage1, final, so_far = [], None, None, 0.0
    for stage in row["stages"]:
        questions = questions_doc[stage["questions"]]["questions"]
        state = fill_stage1(stage["state"], stage1)
        result = client.ask(state, questions)
        so_far = add_ms(so_far, result.get("request_ms"))
        logs.append({"window_id": row["window_id"], "stage": stage["stage"], **result, "cumulative_ms": so_far})
        answers = result.get("answers")
        if stage["stage"] == "state_scores":
            stage1 = None if answers is None else {k: max(0.0, min(1.0, float(v))) for k, v in answers.items()}
        else:
            final = None if answers is None else answers.get("support_choice")
    choice = final if final in row["stages"][-1].get("options", []) else None
    return {"window_id": row["window_id"], "choice": choice}, logs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--arm", required=True, help="E5_C0, E5_C, E5_J, E12_RAW-1, E12_RAW-2")
    ap.add_argument("--model", required=True)
    ap.add_argument("--env", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--windows", help="file with one window_id per line: ask only these")
    ap.add_argument("--reasoning-effort", help="for reasoning models (e.g. minimal, low)")
    args = ap.parse_args()

    kit = Path(args.kit)
    questions_doc = json.loads((kit / "data/questions.json").read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in (kit / f"data/{args.arm}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.windows:
        wanted = set(Path(args.windows).read_text(encoding="utf-8").split())
        rows = [r for r in rows if r["window_id"] in wanted]
    if args.limit:
        rows = rows[: args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    client = Client(read_key(Path(args.env)), args.model, args.timeout, args.reasoning_effort)

    lock = threading.Lock()
    answers_path, log_path = out / "answers.jsonl", out / "calls.jsonl"
    done = 0
    with open(answers_path, "w", encoding="utf-8") as fa, open(log_path, "w", encoding="utf-8") as fl, \
            ThreadPoolExecutor(args.workers) as pool:
        for answer, logs in pool.map(lambda r: run_window(client, questions_doc, r), rows):
            with lock:
                fa.write(json.dumps(answer, ensure_ascii=False) + "\n")
                for log in logs:
                    fl.write(json.dumps(log, ensure_ascii=False) + "\n")
                fa.flush()
                fl.flush()
                done += 1
                if done % 50 == 0:
                    print(f"{done}/{len(rows)} windows", flush=True)

    calls = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines()]
    ok = [c for c in calls if "error" not in c]
    lat = sorted(c["latency_ms"] for c in ok)
    last = {c["window_id"]: c for c in calls}  # the window's last line carries the time to its answer
    whole = sorted(whole_ms(c) for c in last.values() if "error" not in c)
    summary = {
        "arm": args.arm, "model": args.model, "served_models": sorted({c["model"] for c in ok if c.get("model")}),
        "windows": len(rows), "calls": len(calls), "errors": len(calls) - len(ok),
        "null_choices": sum(1 for l in answers_path.read_text(encoding="utf-8").splitlines() if json.loads(l)["choice"] is None),
        "latency_ms_p50": statistics.median(lat) if lat else None,
        "latency_ms_p95": lat[int(0.95 * (len(lat) - 1))] if lat else None,
        "window_ms_p50": statistics.median(whole) if whole else None,
        "window_ms_p95": whole[int(0.95 * (len(whole) - 1))] if whole else None,
        "windows_timed": len(whole),  # windows whose last stage answered; the base of windows_within_1s
        "windows_within_1s": sum(1 for t in whole if t <= 1000),
        "calls_with_more_than_one_http_attempt": sum(1 for c in calls if len(c["http_attempts"]) > 1),
        "prompt_tokens": sum(c["prompt_tokens"] or 0 for c in ok),
        "completion_tokens": sum(c["completion_tokens"] or 0 for c in ok),
        "reasoning_tokens": sum(c.get("reasoning_tokens") or 0 for c in ok),
        "temperature_0": client.use_temperature,
        "reasoning_effort": args.reasoning_effort,
        "workers": args.workers,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
