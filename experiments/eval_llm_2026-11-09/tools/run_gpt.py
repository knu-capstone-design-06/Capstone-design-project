"""Ask an OpenAI model the kit's support_choice question, window by window (E5_C0 / E5_J).

Prompt: system = the question's `instructions` + its options with their `criteria` text (verbatim from the kit's
questions.json) + one output-format line; user = the window's `state` JSON. The answer is forced to one option
with a strict json_schema enum. Invalid answer -> one retry, then null. Per-request cache (sha256 of model,
request body, attempt) so a rerun never pays twice. Standard library only.
The API key is read from an env file and never printed or written.
"""
import argparse, hashlib, json, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.openai.com/v1/chat/completions"
# USD per 1M tokens (input, cached input, output); https://developers.openai.com/api/docs/pricing, fetched 2026-11-09
PRICES = {"gpt-4o-mini-2024-07-18": (0.15, 0.075, 0.60),   # listed as gpt-4o-mini
          "gpt-5.4-mini-2026-03-17": (0.75, 0.075, 4.50),  # listed as gpt-5.4-mini
          "gpt-6.1-sol": (2.00, 0.10, 10.00)}
FORMAT_LINE = 'Reply with JSON only: {"choice": "<one option key>"}.'


def read_key(env_file):
    for line in Path(env_file).read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAI_API_KEY="):
            k = line.split("=", 1)[1].strip().strip('"').strip("'")
            if k:
                return k
    sys.exit("OPENAI_API_KEY not found")


def build_messages(q, state):
    opts = "\n".join(f"- `{k}`: {v}" for k, v in q["criteria"].items())
    system = f"{q['instructions']}\n\nOptions:\n{opts}\n\n{FORMAT_LINE}"
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps(state, ensure_ascii=False)}]


def cost(model, pt, ct, cached):
    pin, pc, pout = PRICES[model]
    pt, ct, cached = pt or 0, ct or 0, cached or 0
    return ((pt - cached) * pin + cached * pc + ct * pout) / 1e6


class Client:
    def __init__(self, key, model, timeout, max_tokens, cache_dir):
        self.key, self.model, self.timeout, self.max_tokens = key, model, timeout, max_tokens
        self.use_temperature, self.use_schema = True, True
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def body(self, messages, options):
        b = {"model": self.model, "messages": messages, "max_completion_tokens": self.max_tokens}
        if self.use_schema:
            b["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {
                "type": "object", "properties": {"choice": {"type": "string", "enum": options}},
                "required": ["choice"], "additionalProperties": False}}}
        if self.use_temperature:
            b["temperature"] = 0
        return b

    def ask(self, messages, options, attempt):
        while True:
            b = self.body(messages, options)
            ck = hashlib.sha256(json.dumps([self.model, b, attempt], sort_keys=True).encode()).hexdigest()
            cf = self.cache_dir / f"{ck}.json"
            if cf.exists():
                rec = json.loads(cf.read_text(encoding="utf-8"))
                rec["cached"], rec["request_hash"] = True, ck
                return rec
            data = json.dumps(b).encode("utf-8")
            retries, changed = 0, False
            while True:
                req = urllib.request.Request(API, data=data, method="POST", headers={
                    "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
                try:
                    t0 = time.perf_counter()
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        raw = resp.read()
                    lat = (time.perf_counter() - t0) * 1000
                    p = json.loads(raw)
                    u = p.get("usage", {}) or {}
                    rec = {"latency_ms": round(lat, 1), "model": p.get("model"),
                           "content": p["choices"][0]["message"].get("content"),
                           "finish_reason": p["choices"][0].get("finish_reason"),
                           "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                           "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                           "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                           "retries": retries, "temperature_0": self.use_temperature, "schema": self.use_schema,
                           "error": None}
                    cf.write_text(json.dumps(rec), encoding="utf-8")
                    rec["cached"], rec["request_hash"] = False, ck
                    return rec
                except urllib.error.HTTPError as e:
                    msg = e.read().decode("utf-8", "replace")
                    if e.code == 400 and "temperature" in msg and "temperature" in b:
                        self.use_temperature = False
                        changed = True
                        break
                    if e.code == 400 and "response_format" in msg and "response_format" in b:
                        self.use_schema = False
                        changed = True
                        break
                    if (e.code == 429 or e.code >= 500) and retries < 5:
                        retries += 1
                        time.sleep(2 ** retries)
                        continue
                    return {"error": f"http {e.code}: {msg[:200]}", "retries": retries, "cached": False}
                except Exception as e:  # timeout, connection, bad JSON
                    if retries < 2:
                        retries += 1
                        time.sleep(2 ** retries)
                        continue
                    return {"error": type(e).__name__, "retries": retries, "cached": False}
            if not changed:
                return {"error": "unreachable", "cached": False}


def parse(content, options):
    try:
        c = json.loads(content).get("choice")
    except Exception:
        return None
    return c if c in options else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--env", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--cap", type=float, default=0, help="stop starting new windows once new spend (USD) exceeds this")
    ap.add_argument("--print-example", action="store_true")
    ap.add_argument("--windows", help="file with one window_id per line; only these windows are asked")
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
        logs, choice = [], None
        for attempt in range(2):
            msgs = build_messages(q, st["state"])
            if not client.use_schema:
                msgs[0]["content"] += "\nAnswer with exactly one of these keys: " + ", ".join(st["options"]) + "."
            r = client.ask(msgs, st["options"], attempt)
            ch = None if r.get("error") else parse(r.get("content"), st["options"])
            c = 0.0 if r.get("error") else cost(a.model, r.get("prompt_tokens"), r.get("completion_tokens"),
                                                r.get("cached_tokens"))
            logs.append({"window_id": row["window_id"], "attempt": attempt, "model": r.get("model"), "choice": ch,
                         "raw": r.get("content"), "finish_reason": r.get("finish_reason"),
                         "latency_ms": r.get("latency_ms"), "prompt_tokens": r.get("prompt_tokens"),
                         "completion_tokens": r.get("completion_tokens"), "cached_tokens": r.get("cached_tokens"),
                         "reasoning_tokens": r.get("reasoning_tokens"), "cost_usd": c, "cached": r.get("cached"), "request_hash": r.get("request_hash"),
                         "temperature_0": r.get("temperature_0"), "retries": r.get("retries"), "error": r.get("error")})
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
    # identical prompts share one cached response, so latency is taken once per distinct request (= one real HTTP call)
    uniq = {l["request_hash"]: l["latency_ms"] for l in calls if l["latency_ms"] is not None and not l["error"]}
    lat = sorted(uniq.values())

    def pct(p):  # nearest-rank percentile
        if not lat:
            return None
        i = max(0, min(len(lat) - 1, -(-p * len(lat) // 100) - 1))
        return lat[int(i)]

    summ = {"arm": a.arm, "model_requested": a.model,
            "models_returned": sorted({l["model"] for l in calls if l["model"]}),
            "windows": len(rows), "windows_done": len(done), "stopped_by_cap": stop.is_set(),
            "calls": len(calls), "distinct_requests": len(uniq), "retry_calls": sum(1 for l in calls if l["attempt"] == 1),
            "errors": sum(1 for l in calls if l["error"]),
            "null_answers": sum(1 for ans, _ in done if ans["choice"] is None),
            "prompt_tokens": sum(l["prompt_tokens"] or 0 for l in calls),
            "completion_tokens": sum(l["completion_tokens"] or 0 for l in calls),
            "cached_tokens": sum(l["cached_tokens"] or 0 for l in calls),
            "reasoning_tokens": sum(l["reasoning_tokens"] or 0 for l in calls),
            "spend_usd_all_calls": round(sum(l["cost_usd"] for l in calls), 5),
            "spend_usd_distinct_requests": round(sum({l["request_hash"]: l["cost_usd"] for l in calls if l["request_hash"]}.values()), 5),
            "spend_usd_new_this_run": round(spend["new"], 5),
            "latency_ms": {"n": len(lat), "p50": pct(50), "p95": pct(95), "max": lat[-1] if lat else None,
                           "share_le_1000": round(sum(1 for x in lat if x <= 1000) / len(lat), 3) if lat else None},
            "finish_reasons": {str(k): sum(1 for l in calls if l["finish_reason"] == k)
                               for k in {l["finish_reason"] for l in calls}},
            "temperature_0": client.use_temperature, "json_schema": client.use_schema,
            "max_completion_tokens": a.max_tokens, "workers": a.workers, "timeout_s": a.timeout,
            "prices_usd_per_1M_in_cachedin_out": PRICES[a.model]}
    (out / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("model_requested", "models_returned", "windows_done", "stopped_by_cap",
                                           "calls", "distinct_requests", "errors", "null_answers", "prompt_tokens", "completion_tokens",
                                           "reasoning_tokens", "spend_usd_all_calls", "spend_usd_new_this_run",
                                           "latency_ms", "finish_reasons", "temperature_0")}))
    if a.print_example:
        st = rows[0]["stages"][-1]
        print(json.dumps(build_messages(qdoc[st["questions"]]["questions"]["support_choice"], st["state"]),
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
