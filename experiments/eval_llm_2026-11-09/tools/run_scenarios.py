"""Run one model on one of the teammate's scenario sets, one run (call it 3 times with --run 1/2/3).

Prompt replicates her run_llm.py exactly (read, not imported): system = her SYSTEM text; user =
json.dumps({"state": state, "questions": questions}, ensure_ascii=False); answer = JSON object with one key per question
(`support_choice`, enum of the criteria keys). OpenAI: Chat Completions, response_format json_schema
{"name": "answers", "strict": true, ...}, temperature 0 (dropped if refused), no max token limit (as hers).
Anthropic: same system and user text, the same schema through output_config.format, thinking off as in run_claude.py,
no temperature (non-default values are rejected), max_tokens 256.
Each run is paid separately (the run number is part of the cache key); 2 workers; latency = perf_counter around the call.
Usage: python run_scenarios.py --set novel|heldout1|heldout2 --model M --run N --root runs/scenarios --cache cache
       --openai-env F --anthropic-env F [--limit K] [--cap USD]
"""
import argparse, hashlib, json, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SYSTEM = ("You are a decision model for an accessibility-adaptive ordering kiosk. You receive the state of one "
          "observation window and one or more questions. Answer every question from the state alone. For a "
          "`choice` question return exactly one key of its `criteria`. For a `noul` question return the "
          "probability (0 to 1) that the statement is true. Reply with JSON only.")   # her run_llm.py:22-25, verbatim
PRICES = {"gpt-4o-mini-2024-07-18": (0.15, 0.075, 0.60), "gpt-5.4-mini-2026-03-17": (0.75, 0.075, 4.50),
          "claude-haiku-5-5": (0.10, 0.01, 0.50), "claude-sonnet-5-5": (2.00, 0.10, 10.00)}   # as in run_gpt.py / run_claude.py
THINKING = {"claude-haiku-5-5": {"type": "disabled"}, "claude-sonnet-5-5": {"type": "between_tools"}}


def key_from(env, name):
    for line in Path(env).read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            k = line.split("=", 1)[1].strip().strip('"').strip("'")
            if k:
                return k
    sys.exit(f"{name} not found")


def schema(questions):
    props = {n: {"type": "string", "enum": list(q["criteria"])} for n, q in questions.items()}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


class OpenAI:
    def __init__(self, key, model):
        self.key, self.model, self.use_temperature = key, model, True

    def body(self, user, questions):
        b = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
             "response_format": {"type": "json_schema", "json_schema": {"name": "answers", "strict": True,
                                                                         "schema": schema(questions)}}}
        if self.use_temperature:
            b["temperature"] = 0
        return b

    def call(self, b):
        data = json.dumps(b).encode("utf-8")
        retries = 0
        while True:
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=data, method="POST",
                                         headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            try:
                t0 = time.perf_counter()
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                lat = (time.perf_counter() - t0) * 1000
                p = json.loads(raw)
                u = p.get("usage") or {}
                return {"latency_ms": round(lat, 1), "model": p.get("model"), "content": p["choices"][0]["message"].get("content"),
                        "stop": p["choices"][0].get("finish_reason"), "in": u.get("prompt_tokens"),
                        "out": u.get("completion_tokens"), "cache_in": (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
                        "retries": retries, "error": None}
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")
                if e.code == 400 and "temperature" in msg and "temperature" in b:
                    self.use_temperature = False
                    b = dict(b)
                    b.pop("temperature")
                    data = json.dumps(b).encode("utf-8")
                    continue
                if (e.code == 429 or e.code >= 500) and retries < 5:
                    retries += 1
                    time.sleep(2 ** retries)
                    continue
                return {"error": f"http {e.code}: {msg[:200]}", "retries": retries}
            except Exception as e:
                if retries < 2:
                    retries += 1
                    time.sleep(2 ** retries)
                    continue
                return {"error": type(e).__name__, "retries": retries}


class Claude:
    def __init__(self, key, model):
        import anthropic
        self.A = anthropic
        self.client = anthropic.Anthropic(api_key=key, timeout=30, max_retries=0)
        self.model = model

    def body(self, user, questions):
        return {"model": self.model, "max_tokens": 256, "system": SYSTEM, "messages": [{"role": "user", "content": user}],
                "thinking": THINKING[self.model], "output_config": {"format": {"type": "json_schema", "schema": schema(questions)}}}

    def call(self, b):
        retries = 0
        while True:
            try:
                t0 = time.perf_counter()
                r = self.client.messages.create(**b)
                lat = (time.perf_counter() - t0) * 1000
                text = next((x.text for x in r.content if x.type == "text"), None)
                return {"latency_ms": round(lat, 1), "model": r.model, "content": text, "stop": r.stop_reason,
                        "in": r.usage.input_tokens, "out": r.usage.output_tokens,
                        "cache_in": getattr(r.usage, "cache_read_input_tokens", None) or 0, "retries": retries, "error": None}
            except (self.A.RateLimitError, self.A.InternalServerError, self.A.APIConnectionError) as e:
                if retries < 5:
                    retries += 1
                    time.sleep(2 ** retries)
                    continue
                return {"error": type(e).__name__, "retries": retries}
            except self.A.APIStatusError as e:
                return {"error": f"http {e.status_code}: {str(e)[:200]}", "retries": retries}


def main():
    ap = argparse.ArgumentParser()
    for a in ("--set", "--model", "--run", "--root", "--cache", "--openai-env", "--anthropic-env"):
        ap.add_argument(a, required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cap", type=float, default=0)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    root, cache = Path(a.root), Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in (root / "inputs" / f"{a.set}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.limit:
        rows = rows[:a.limit]
    cl = Claude(key_from(a.anthropic_env, "ANTHROPIC_API_KEY"), a.model) if a.model.startswith("claude") \
        else OpenAI(key_from(a.openai_env, "OPENAI_API_KEY"), a.model)
    pin, pc, pout = PRICES[a.model]
    spend = {"new": 0.0}
    lock, stop = threading.Lock(), threading.Event()

    def ask(user, q, attempt):
        b = cl.body(user, q)
        ck = hashlib.sha256(json.dumps(["scen", a.model, b, a.run, attempt], sort_keys=True).encode()).hexdigest()
        cf = cache / f"{ck}.json"
        if cf.exists():
            r = json.loads(cf.read_text(encoding="utf-8"))
            r["cached"] = True
            return r
        r = cl.call(b)
        if not r.get("error"):
            cf.write_text(json.dumps(r), encoding="utf-8")
        r["cached"] = False
        return r

    def one(row):
        if stop.is_set():
            return None
        q = row["questions"]
        opts = list(q["support_choice"]["criteria"])
        user = json.dumps({"state": row["state"], "questions": q}, ensure_ascii=False)
        logs, choice = [], None
        for attempt in range(2):
            r = ask(user, q, attempt)
            ch = None
            if not r.get("error") and r.get("content"):
                try:
                    ch = json.loads(r["content"]).get("support_choice")
                except Exception:
                    ch = None
                ch = ch if ch in opts else None
            c = 0.0 if r.get("error") else (((r["in"] or 0) - r["cache_in"]) * pin + r["cache_in"] * pc + (r["out"] or 0) * pout) / 1e6
            if a.model.startswith("claude") and not r.get("error"):
                c = ((r["in"] or 0) * pin + r["cache_in"] * pc + (r["out"] or 0) * pout) / 1e6   # Anthropic input excludes cache reads
            logs.append({"case_id": row["case_id"], "attempt": attempt, "choice": ch, "raw": r.get("content"),
                         "model": r.get("model"), "stop": r.get("stop"), "latency_ms": r.get("latency_ms"),
                         "prompt_tokens": r.get("in"), "completion_tokens": r.get("out"), "cost_usd": c,
                         "cached": r["cached"], "retries": r.get("retries"), "error": r.get("error")})
            with lock:
                if not r["cached"]:
                    spend["new"] += c
                if a.cap and spend["new"] > a.cap:
                    stop.set()
            if ch is not None:
                choice = ch
                break
        return {"case_id": row["case_id"], "choice": choice}, logs

    with ThreadPoolExecutor(a.workers) as ex:
        res = [r for r in ex.map(one, rows) if r is not None]
    out = root / f"{a.model}__{a.set}__r{a.run}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "answers.jsonl", "w", encoding="utf-8") as fa, open(out / "calls.jsonl", "w", encoding="utf-8") as fc:
        for ans, logs in res:
            fa.write(json.dumps(ans) + "\n")
            for l in logs:
                fc.write(json.dumps(l) + "\n")
    calls = [l for _, ls in res for l in ls]
    first = {}
    for l in calls:      # latency of the call that produced each case's answer (or its last attempt)
        if l["latency_ms"] is not None:
            first[l["case_id"]] = l["latency_ms"] if (l["choice"] is not None or l["case_id"] not in first) else first[l["case_id"]]
    lat = sorted(first.values())
    k = lambda p: lat[max(0, -(-p * len(lat) // 100) - 1)] if lat else None
    summ = {"set": a.set, "model": a.model, "run": a.run, "models_returned": sorted({l["model"] for l in calls if l["model"]}),
            "cases": len(rows), "cases_done": len(res), "stopped_by_cap": stop.is_set(), "calls": len(calls),
            "errors": sum(1 for l in calls if l["error"]), "null_answers": sum(1 for x, _ in res if x["choice"] is None),
            "prompt_tokens": sum(l["prompt_tokens"] or 0 for l in calls), "completion_tokens": sum(l["completion_tokens"] or 0 for l in calls),
            "spend_usd": round(sum(l["cost_usd"] for l in calls), 5), "spend_usd_new": round(spend["new"], 5),
            "latency_ms": {"n": len(lat), "p50": k(50), "p95": k(95), "max": lat[-1] if lat else None,
                           "share_le_1000": round(sum(x <= 1000 for x in lat) / len(lat), 3) if lat else None},
            "stops": {str(s): sum(1 for l in calls if l["stop"] == s) for s in {l["stop"] for l in calls}},
            "temperature_0": getattr(cl, "use_temperature", False), "workers": a.workers}
    (out / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps({x: summ[x] for x in ("set", "model", "run", "cases_done", "errors", "null_answers", "prompt_tokens",
                                           "spend_usd_new", "latency_ms", "temperature_0")}))


if __name__ == "__main__":
    main()
