"""Ask an Anthropic model the kit's support_choice question, window by window (E5_C0 / E5_J).

Same system and user text as run_gpt.py (build_messages). Answer forced with structured outputs
(output_config.format json_schema, `choice` = enum of the window's options). Thinking off: Haiku 5.5
{"type": "disabled"}, Sonnet 5.5 {"type": "between_tools"} (its thinking-off mode; "disabled" is a 400 there).
No temperature: both models reject non-default sampling values (Anthropic model-migration guide).
Invalid answer or refusal -> one retry, then null. Per-request cache as in run_gpt.py. Output files have the
same fields as run_gpt.py so score.py, one_second.py and the summaries work unchanged.
The API key is read from an env file and never printed or written.
"""
import argparse, hashlib, json, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from run_gpt import build_messages, parse  # noqa: E402

# USD per 1M tokens (input, cache read, output); https://platform.claude.com/docs/en/about-claude/pricing, fetched
# 2026-11-10 (Haiku 5.5: prompts up to 100,000 tokens)
PRICES = {"claude-haiku-5-5": (0.10, 0.01, 0.50), "claude-sonnet-5-5": (2.00, 0.10, 10.00)}
THINKING = {"claude-haiku-5-5": {"type": "disabled"}, "claude-sonnet-5-5": {"type": "between_tools"}}
RETRYABLE = (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError)


def read_key(env_file):
    for line in Path(env_file).read_text(encoding="utf-8").splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            k = line.split("=", 1)[1].strip().strip('"').strip("'")
            if k:
                return k
    sys.exit("ANTHROPIC_API_KEY not found")


def cost(model, it, ot, cr):
    pin, pcr, pout = PRICES[model]
    return ((it or 0) * pin + (cr or 0) * pcr + (ot or 0) * pout) / 1e6


class Client:
    def __init__(self, key, model, timeout, max_tokens, cache_dir):
        self.client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=0)
        self.model, self.max_tokens = model, max_tokens
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def params(self, messages, options):
        return {"model": self.model, "max_tokens": self.max_tokens, "system": messages[0]["content"],
                "messages": [{"role": "user", "content": messages[1]["content"]}],
                "thinking": THINKING[self.model],
                "output_config": {"format": {"type": "json_schema", "schema": {
                    "type": "object", "properties": {"choice": {"type": "string", "enum": options}},
                    "required": ["choice"], "additionalProperties": False}}}}

    def ask(self, messages, options, attempt):
        p = self.params(messages, options)
        ck = hashlib.sha256(json.dumps(["anthropic", p, attempt], sort_keys=True).encode()).hexdigest()
        cf = self.cache_dir / f"{ck}.json"
        if cf.exists():
            rec = json.loads(cf.read_text(encoding="utf-8"))
            rec["cached"], rec["request_hash"] = True, ck
            return rec
        retries = 0
        while True:
            try:
                t0 = time.perf_counter()
                r = self.client.messages.create(**p)
                lat = (time.perf_counter() - t0) * 1000
                text = next((b.text for b in r.content if b.type == "text"), None)
                u = r.usage
                rec = {"latency_ms": round(lat, 1), "model": r.model, "content": text, "finish_reason": r.stop_reason,
                       "prompt_tokens": u.input_tokens, "completion_tokens": u.output_tokens,
                       "cached_tokens": getattr(u, "cache_read_input_tokens", None) or 0,
                       "reasoning_tokens": None, "retries": retries, "temperature_0": False, "schema": True,
                       "error": None}
                cf.write_text(json.dumps(rec), encoding="utf-8")
                rec["cached"], rec["request_hash"] = False, ck
                return rec
            except RETRYABLE as e:
                if retries < 5:
                    retries += 1
                    time.sleep(2 ** retries)
                    continue
                return {"error": type(e).__name__, "retries": retries, "cached": False}
            except anthropic.APIStatusError as e:
                return {"error": f"http {e.status_code}: {str(e)[:200]}", "retries": retries, "cached": False}


def main():
    ap = argparse.ArgumentParser()
    for a in ("--kit", "--arm", "--model", "--env", "--out", "--cache"):
        ap.add_argument(a, required=True)
    ap.add_argument("--windows")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--cap", type=float, default=0)
    a = ap.parse_args()
    kit = Path(a.kit)
    qdoc = json.loads((kit / "data/questions.json").read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in (kit / f"data/{a.arm}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.windows:
        keep = set(Path(a.windows).read_text(encoding="utf-8").split())
        rows = [r for r in rows if r["window_id"] in keep]
    if a.limit:
        rows = rows[:a.limit]
    client = Client(read_key(a.env), a.model, a.timeout, a.max_tokens, a.cache)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    spend = {"new": 0.0}
    lock = threading.Lock()
    stop = threading.Event()

    def one(row):
        if stop.is_set():
            return None
        st = [s for s in row["stages"] if s["stage"] == "support_choice"][0]
        q = qdoc[st["questions"]]["questions"]["support_choice"]
        assert list(q["criteria"]) == st["options"], row["window_id"]
        msgs = build_messages(q, st["state"])
        logs, choice = [], None
        for attempt in range(2):
            r = client.ask(msgs, st["options"], attempt)
            ch = None if r.get("error") or r.get("content") is None else parse(r["content"], st["options"])
            c = 0.0 if r.get("error") else cost(a.model, r.get("prompt_tokens"), r.get("completion_tokens"),
                                                r.get("cached_tokens"))
            logs.append({"window_id": row["window_id"], "attempt": attempt, "model": r.get("model"), "choice": ch,
                         "raw": r.get("content"), "finish_reason": r.get("finish_reason"),
                         "latency_ms": r.get("latency_ms"), "prompt_tokens": r.get("prompt_tokens"),
                         "completion_tokens": r.get("completion_tokens"), "cached_tokens": r.get("cached_tokens"),
                         "reasoning_tokens": None, "cost_usd": c, "cached": r.get("cached"),
                         "request_hash": r.get("request_hash"), "temperature_0": False,
                         "retries": r.get("retries"), "error": r.get("error")})
            with lock:
                if not r.get("cached"):
                    spend["new"] += c
                if a.cap and spend["new"] > a.cap:
                    stop.set()
            if ch is not None:
                choice = ch
                break
        return {"window_id": row["window_id"], "choice": choice}, logs

    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(one, rows))
    done = [r for r in results if r is not None]
    with open(out / "answers.jsonl", "w", encoding="utf-8") as fa, open(out / "calls.jsonl", "w", encoding="utf-8") as fc:
        for ans, logs in done:
            fa.write(json.dumps(ans) + "\n")
            for l in logs:
                fc.write(json.dumps(l) + "\n")
    calls = [l for _, ls in done for l in ls]
    uniq = {l["request_hash"]: l["latency_ms"] for l in calls if l["latency_ms"] is not None and not l["error"]}
    lat = sorted(uniq.values())

    def pct(p):
        return lat[max(0, min(len(lat) - 1, int(-(-p * len(lat) // 100)) - 1))] if lat else None

    summ = {"arm": a.arm, "model_requested": a.model,
            "models_returned": sorted({l["model"] for l in calls if l["model"]}),
            "windows": len(rows), "windows_done": len(done), "stopped_by_cap": stop.is_set(),
            "calls": len(calls), "distinct_requests": len(uniq), "retry_calls": sum(1 for l in calls if l["attempt"] == 1),
            "errors": sum(1 for l in calls if l["error"]),
            "null_answers": sum(1 for ans, _ in done if ans["choice"] is None),
            "prompt_tokens": sum(l["prompt_tokens"] or 0 for l in calls),
            "completion_tokens": sum(l["completion_tokens"] or 0 for l in calls),
            "cached_tokens": sum(l["cached_tokens"] or 0 for l in calls),
            "spend_usd_all_calls": round(sum(l["cost_usd"] for l in calls), 5),
            "spend_usd_new_this_run": round(spend["new"], 5),
            "latency_ms": {"n": len(lat), "p50": pct(50), "p95": pct(95), "max": lat[-1] if lat else None,
                           "share_le_1000": round(sum(1 for x in lat if x <= 1000) / len(lat), 3) if lat else None},
            "finish_reasons": {str(k): sum(1 for l in calls if l["finish_reason"] == k)
                               for k in {l["finish_reason"] for l in calls}},
            "thinking": THINKING[a.model], "temperature": "not sent (default)", "max_tokens": a.max_tokens,
            "workers": a.workers, "timeout_s": a.timeout, "prices_usd_per_1M_in_cacheread_out": PRICES[a.model]}
    (out / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("model_requested", "models_returned", "windows_done", "stopped_by_cap",
                                           "calls", "distinct_requests", "errors", "null_answers", "prompt_tokens",
                                           "completion_tokens", "spend_usd_all_calls", "spend_usd_new_this_run",
                                           "latency_ms", "finish_reasons")}))


if __name__ == "__main__":
    main()
