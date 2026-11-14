"""Ask a Gemini model the kit's support_choice question, window by window (E5_C0 / E5_J), REST generateContent.

Same system and user text as run_gpt.py (build_messages). Answer forced with responseSchema (enum of the window's
options), temperature 0, thinkingLevel "minimal" (the lowest level; dropped automatically if the model rejects it).
Invalid answer -> one retry, then null. Per-request cache as in run_gpt.py; output files have the same fields.
The API key is read from an env file, sent only in the x-goog-api-key header, and never printed or written.
"""
import argparse, hashlib, json, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_gpt import build_messages, parse  # noqa: E402

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# USD per 1M tokens (input, cached input [not used: no cached tokens expected], output incl. thinking);
# https://aistudio.google.com/docs/pricing (redirected from ai.google.dev/gemini-api/docs/pricing), fetched 2026-11-10,
# paid tier standard, price "through December 31, 2026"
PRICES = {"gemini-3.8-flash": (0.75, None, 3.75)}


def read_key(env_file):
    for line in Path(env_file).read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            k = line.split("=", 1)[1].strip().strip('"').strip("'")
            if k:
                return k
    sys.exit("GEMINI_API_KEY not found")


def cost(model, pt, ot):
    pin, _, pout = PRICES[model]
    return ((pt or 0) * pin + (ot or 0) * pout) / 1e6


class Client:
    def __init__(self, key, model, timeout, max_tokens, cache_dir):
        self.key, self.model, self.timeout, self.max_tokens = key, model, timeout, max_tokens
        self.use_thinking_level = True
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def body(self, messages, options):
        gc = {"temperature": 0, "maxOutputTokens": self.max_tokens, "responseMimeType": "application/json",
              "responseSchema": {"type": "OBJECT", "properties": {"choice": {"type": "STRING", "enum": options}},
                                 "required": ["choice"]}}
        if self.use_thinking_level:
            gc["thinkingConfig"] = {"thinkingLevel": "minimal"}
        return {"systemInstruction": {"parts": [{"text": messages[0]["content"]}]},
                "contents": [{"role": "user", "parts": [{"text": messages[1]["content"]}]}],
                "generationConfig": gc}

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
                req = urllib.request.Request(URL.format(model=self.model), data=data, method="POST", headers={
                    "x-goog-api-key": self.key, "Content-Type": "application/json"})
                try:
                    t0 = time.perf_counter()
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        raw = resp.read()
                    lat = (time.perf_counter() - t0) * 1000
                    p = json.loads(raw)
                    u = p.get("usageMetadata", {}) or {}
                    cand = (p.get("candidates") or [{}])[0]
                    parts = (cand.get("content") or {}).get("parts") or []
                    text = "".join(x.get("text", "") for x in parts if not x.get("thought")) or None
                    out_tok = (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
                    rec = {"latency_ms": round(lat, 1), "model": p.get("modelVersion"), "content": text,
                           "finish_reason": cand.get("finishReason"), "prompt_tokens": u.get("promptTokenCount"),
                           "completion_tokens": out_tok, "cached_tokens": u.get("cachedContentTokenCount") or 0,
                           "reasoning_tokens": u.get("thoughtsTokenCount") or 0, "retries": retries,
                           "temperature_0": True, "thinking_level": "minimal" if self.use_thinking_level else "default",
                           "schema": True, "error": None}
                    cf.write_text(json.dumps(rec), encoding="utf-8")
                    rec["cached"], rec["request_hash"] = False, ck
                    return rec
                except urllib.error.HTTPError as e:
                    msg = e.read().decode("utf-8", "replace")
                    if e.code == 400 and "thinking" in msg.lower() and "thinkingConfig" in b["generationConfig"]:
                        self.use_thinking_level = False
                        changed = True
                        break
                    if (e.code == 429 or e.code >= 500) and retries < 5:
                        retries += 1
                        time.sleep(2 ** retries)
                        continue
                    return {"error": f"http {e.code}: {msg[:200]}", "retries": retries, "cached": False}
                except Exception as e:
                    if retries < 2:
                        retries += 1
                        time.sleep(2 ** retries)
                        continue
                    return {"error": type(e).__name__, "retries": retries, "cached": False}
            if not changed:
                return {"error": "unreachable", "cached": False}


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
            c = 0.0 if r.get("error") else cost(a.model, r.get("prompt_tokens"), r.get("completion_tokens"))
            logs.append({"window_id": row["window_id"], "attempt": attempt, "model": r.get("model"), "choice": ch,
                         "raw": r.get("content"), "finish_reason": r.get("finish_reason"),
                         "latency_ms": r.get("latency_ms"), "prompt_tokens": r.get("prompt_tokens"),
                         "completion_tokens": r.get("completion_tokens"), "cached_tokens": r.get("cached_tokens"),
                         "reasoning_tokens": r.get("reasoning_tokens"), "cost_usd": c, "cached": r.get("cached"),
                         "request_hash": r.get("request_hash"), "temperature_0": True,
                         "thinking_level": r.get("thinking_level"), "retries": r.get("retries"), "error": r.get("error")})
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
            "reasoning_tokens": sum(l["reasoning_tokens"] or 0 for l in calls),
            "spend_usd_all_calls": round(sum(l["cost_usd"] for l in calls), 5),
            "spend_usd_new_this_run": round(spend["new"], 5),
            "latency_ms": {"n": len(lat), "p50": pct(50), "p95": pct(95), "max": lat[-1] if lat else None,
                           "share_le_1000": round(sum(1 for x in lat if x <= 1000) / len(lat), 3) if lat else None},
            "finish_reasons": {str(k): sum(1 for l in calls if l["finish_reason"] == k)
                               for k in {l["finish_reason"] for l in calls}},
            "thinking_levels": sorted({str(l["thinking_level"]) for l in calls}),
            "temperature_0": True, "max_output_tokens": a.max_tokens, "workers": a.workers, "timeout_s": a.timeout,
            "prices_usd_per_1M_in_cachedin_out": PRICES[a.model]}
    (out / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("model_requested", "models_returned", "windows_done", "stopped_by_cap",
                                           "calls", "distinct_requests", "errors", "null_answers", "prompt_tokens",
                                           "completion_tokens", "reasoning_tokens", "spend_usd_all_calls",
                                           "spend_usd_new_this_run", "latency_ms", "finish_reasons",
                                           "thinking_levels")}))


if __name__ == "__main__":
    main()
