"""Calls, tokens and cost of an E12 run folder (no API call).

Price: $42 per 10^9 input tokens, output free (TypeSafe price in docs/Jev-Integration.md 3, the rate E5 used).
Cost = the sum of the responses' usage.input_tokens over the API calls of the run (answers from the identical-request
cache are counted apart: they cost nothing in this run).

  python -B cost_report.py --run <run folder> [--projection <stub run folder>] > <run>/cost.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

PRICE_PER_TOKEN = 42 / 1e9


def read_jsonl(p: Path) -> list:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def pct(v: list, q: float):
    if not v:
        return None
    s = sorted(v)
    h = (len(s) - 1) * q            # linear interpolation between order statistics (Hyndman & Fan type 7, as E5)
    lo = int(h)
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (h - lo)


def report(run: Path) -> dict:
    calls = read_jsonl(run / "jev_calls.jsonl")
    agg = defaultdict(lambda: {"api_calls": 0, "answered": 0, "failed": Counter(), "cached_answers": 0,
                               "tokens": [], "bytes": [], "latency_ms": []})
    windows = Counter()
    for c in calls:
        windows[(c["arm"], "asked" if c["asked"] else (c["skip_reason"] or "not asked"))] += 1
        for s in c["stages"]:
            if s["outcome"] == "skipped":
                continue
            a = agg[(c["arm"], s["stage"])]
            if s.get("cached"):
                a["cached_answers"] += 1
                continue
            a["api_calls"] += 1
            a["bytes"].append(s["request_bytes"])
            if s["outcome"] == "answered":
                a["answered"] += 1
                a["tokens"].append((s.get("usage") or {}).get("input_tokens") or 0)
                a["latency_ms"].append(s["latency_ms"])
            else:
                a["failed"][s.get("failure") or "no_answer"] += 1
    out, tot_tok, tot_calls = {}, 0, 0
    for (arm, stage), a in sorted(agg.items()):
        t = sum(a["tokens"])
        tot_tok += t
        tot_calls += a["api_calls"]
        out[f"{arm} / {stage}"] = {
            "api_calls": a["api_calls"], "answered": a["answered"], "failed": dict(a["failed"]),
            "answers_from_cache": a["cached_answers"], "input_tokens_sum": t,
            "input_tokens_median": statistics.median(a["tokens"]) if a["tokens"] else None,
            "tokens_per_request_byte": round(t / sum(a["bytes"]), 4) if a["bytes"] and t else None,
            "cost_usd": round(t * PRICE_PER_TOKEN, 6),
            "cost_per_call_usd": round(t * PRICE_PER_TOKEN / a["answered"], 8) if a["answered"] else None,
            "latency_ms_p50": pct(a["latency_ms"], 0.5), "latency_ms_p95": pct(a["latency_ms"], 0.95)}
    return {"run": str(run), "price": "USD 42 per 1e9 input tokens, output free (docs/Jev-Integration.md 3)",
            "windows": {f"{a} / {k}": n for (a, k), n in sorted(windows.items())}, "by_arm_stage": out,
            "api_calls_total": tot_calls, "input_tokens_total": tot_tok, "cost_usd_total": round(tot_tok * PRICE_PER_TOKEN, 6)}


def projection(stub: Path, measured: dict) -> dict:
    """Distinct requests of a stub run (= the API calls a real run makes when every call succeeds) times the measured
    tokens per request byte of each arm and stage."""
    calls = read_jsonl(stub / "jev_calls.jsonl")
    size = defaultdict(list)
    for c in calls:
        for s in c["stages"]:
            if s["outcome"] != "skipped" and not s.get("cached"):
                size[f"{c['arm']} / {s['stage']}"].append(s["request_bytes"])
    out, tot = {}, 0.0
    for k, v in sorted(size.items()):
        r = (measured["by_arm_stage"].get(k) or {}).get("tokens_per_request_byte")
        tok = None if r is None else sum(v) * r
        tot += tok or 0.0
        out[k] = {"distinct_requests": len(v), "request_bytes_sum": sum(v), "tokens_per_byte_measured": r,
                  "tokens_projected": None if tok is None else round(tok), "cost_usd_projected":
                  None if tok is None else round(tok * PRICE_PER_TOKEN, 4)}
    return {"stub_run": str(stub), "by_arm_stage": out, "cost_usd_projected_total": round(tot * PRICE_PER_TOKEN, 4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--projection", help="a stub run folder over all windows: project the full run's cost")
    args = ap.parse_args()
    m = report(Path(args.run))
    if args.projection:
        m["projection_full_run"] = projection(Path(args.projection), m)
    print(json.dumps(m, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
