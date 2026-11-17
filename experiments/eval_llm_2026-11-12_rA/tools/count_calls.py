"""Count, without any API call, what the existing runners would send for this folder's b0_rA inputs, and estimate
the cost. No key is read, no client is built, nothing goes on the network.

For every model and arm the request of each window is built with the runners' own code: run_gpt.build_messages, then
run_gpt.Client.body (GPT) or run_claude.Client.params (Claude), called on a plain namespace instead of a client; the
cache file name is the runners' key, sha256 of [model, body, attempt] (GPT) or ["anthropic", params, attempt]
(Claude). A window whose attempt-0 file exists in the 11-09 cache folder is answered from the cache; the distinct
requests without one are the new calls. Self-check: on the kit's b0_r0 inputs (the 11-09 runs) every request of every
model must be found (72 C0, 547 J cell-window prompts).
GPT temperature: each model's 11-09 run summary records whether temperature 0 was sent (gpt-6.1-sol rejects it, so
its cached bodies carry no temperature); the body is built the same way.

Arms and windows as in the 11-09 runs: E5_C0 every window of the data file; E5_J the windows in the 137 table cells
(prep/E5_J_cell_windows.txt; the 11-09 list for b0_r0).

Cost per new call, two figures (run summaries of eval_llm_2026-11-09):
  paid      = the stage's paid USD / its real calls (the 'Paid' and 'Real calls' columns);
  tokens    = predict_cost.py's method: prompt tokens per prompt character and mean completion tokens of the model's
              11-09 run on the same arm (calls.jsonl), times the new prompts' characters, times the run_gpt / run_claude
              price table.
  python count_calls.py [--json-out <file>] [--cache <runner cache folder>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
RA = Path(__file__).resolve().parents[1]
WS = RA.parents[1]
KIT = WS / "5_deliverables" / "llm_eval_kit_2026-11-08"
LLM = WS / "4_vision" / "eval_llm_2026-11-09"
sys.path.insert(0, str(LLM / "tools"))
import run_gpt  # noqa: E402
import run_claude  # noqa: E402  (imports the anthropic SDK; no client is created)

GPT = ("gpt-4o-mini-2024-07-18", "gpt-5.4-mini-2026-03-17", "gpt-6.1-sol")
CLAUDE = ("claude-haiku-5-5", "claude-sonnet-5-5")
MAX_TOKENS = 256                        # both runners' default
# eval_llm_2026-11-09 run records: (paid USD, real calls) per model and arm. C0: stage 1 '207 new' = 69 per model
# (4o-mini $0.0030, 5.4-mini $0.0174, sol $0.0560) and stage 4 (Haiku C0 $0.0041 / 69, Sonnet C0 $0.0812 / 69);
# J: stage 2 (575 + 573 calls, $0.0387 / $0.2136), 3 (569, $0.6194), 4 (Haiku J 570, $0.0492), 5a (Sonnet J 570, $0.9768).
PAID = {("gpt-4o-mini-2024-07-18", "E5_C0"): (0.0030, 69), ("gpt-5.4-mini-2026-03-17", "E5_C0"): (0.0174, 69),
        ("gpt-6.1-sol", "E5_C0"): (0.0560, 69), ("claude-haiku-5-5", "E5_C0"): (0.0041, 69),
        ("claude-sonnet-5-5", "E5_C0"): (0.0812, 69),
        ("gpt-4o-mini-2024-07-18", "E5_J"): (0.0387, 575), ("gpt-5.4-mini-2026-03-17", "E5_J"): (0.2136, 573),
        ("gpt-6.1-sol", "E5_J"): (0.6194, 569), ("claude-haiku-5-5", "E5_J"): (0.0492, 570),
        ("claude-sonnet-5-5", "E5_J"): (0.9768, 570)}
RUN_SUFFIX = {"E5_C0": "E5_C0", "E5_J": "E5_J_cells"}


def jl(p: Path) -> list:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def requests(folder: Path, arm: str, only: set | None) -> list:
    """(window_id, messages, options, situation tag) per asked window, as the runners build them."""
    qdoc = json.loads((folder / "data" / "questions.json").read_text(encoding="utf-8"))
    out = []
    for r in jl(folder / "data" / f"{arm}.jsonl"):
        if only is not None and r["window_id"] not in only:
            continue
        st = [s for s in r["stages"] if s["stage"] == "support_choice"][0]
        q = qdoc[st["questions"]]["questions"]["support_choice"]
        assert list(q["criteria"]) == st["options"]
        tag = ((st["state"].get("situation") or {}).get("tag"))
        out.append((r["window_id"], run_gpt.build_messages(q, st["state"]), st["options"], tag))
    return out


def temperature_sent(model: str) -> bool:
    s = json.loads((LLM / "runs" / f"{model}_E5_J_cells" / "summary.json").read_text(encoding="utf-8"))
    return bool(s["temperature_0"])


def cache_key(model: str, messages: list, options: list, attempt: int = 0) -> str:
    if model in GPT:
        ns = SimpleNamespace(model=model, max_tokens=MAX_TOKENS, use_schema=True, use_temperature=temperature_sent(model))
        b = run_gpt.Client.body(ns, messages, options)
        return hashlib.sha256(json.dumps([model, b, attempt], sort_keys=True).encode()).hexdigest()
    ns = SimpleNamespace(model=model, max_tokens=MAX_TOKENS)
    p = run_claude.Client.params(ns, messages, options)
    return hashlib.sha256(json.dumps(["anthropic", p, attempt], sort_keys=True).encode()).hexdigest()


def chars(messages: list) -> int:
    return sum(len(m["content"]) for m in messages)


def token_rates(model: str, arm: str, kit_reqs: dict) -> tuple[float, float]:
    """Prompt tokens per prompt character and mean completion tokens of the model's 11-09 run on this arm."""
    calls = [c for c in jl(LLM / "runs" / f"{model}_{RUN_SUFFIX[arm]}" / "calls.jsonl") if not c["error"]]
    ratio = sum(c["prompt_tokens"] for c in calls) / sum(chars(kit_reqs[c["window_id"]]) for c in calls)
    return ratio, sum(c["completion_tokens"] for c in calls) / len(calls)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--cache", type=Path, default=LLM / "cache", help="runner cache folder (default: the 11-09 one)")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cells_r0 = set((LLM / "stage2_prep" / "E5_J_cell_windows.txt").read_text(encoding="utf-8").split())
    cells_ra = set((RA / "prep" / "E5_J_cell_windows.txt").read_text(encoding="utf-8").split())
    c0cells_r0 = set((LLM / "stage2_prep" / "E5_C0_cell_windows.txt").read_text(encoding="utf-8").split())
    c0cells_ra = set((RA / "prep" / "E5_C0_cell_windows.txt").read_text(encoding="utf-8").split())
    # E5_C0 as the 11-09 runs asked it (every window) and, for comparison, only its windows in the 137 table cells
    scope = {"E5_C0": ("E5_C0", None, None), "E5_C0 (table-cell windows only)": ("E5_C0", c0cells_r0, c0cells_ra),
             "E5_J": ("E5_J", cells_r0, cells_ra)}
    res = {"inputs": {}, "models": {}}
    for name, (arm, only0, onlyA) in scope.items():
        r0, rA = requests(KIT, arm, only0), requests(RA, arm, onlyA)
        p0 = {json.dumps(m, ensure_ascii=False) for _, m, _, _ in r0}
        pA = {json.dumps(m, ensure_ascii=False) for _, m, _, _ in rA}
        r0_all = {json.dumps(m, ensure_ascii=False) for _, m, _, _ in requests(KIT, arm, None)}
        tagged = [w for w, _, _, t in rA if t not in ("none", "unknown", None)]
        tags = {}
        for _, _, _, t in rA:
            tags[str(t)] = tags.get(str(t), 0) + 1
        new_prompts = pA - p0
        res["inputs"][name] = {
            "windows_b0_r0": len(r0), "windows_b0_rA": len(rA),
            "distinct_prompts_b0_r0": len(p0), "distinct_prompts_b0_rA": len(pA),
            "distinct_prompts_b0_rA_not_in_b0_r0_same_scope": len(new_prompts),
            "distinct_prompts_b0_rA_not_in_b0_r0_any_window": len(pA - r0_all),
            "windows_b0_rA_with_a_new_prompt": sum(1 for _, m, _, _ in rA if json.dumps(m, ensure_ascii=False) in new_prompts),
            "windows_b0_rA_tagged": len(tagged), "tag_counts_b0_rA": tags,
            "windows_b0_r0_tagged": sum(1 for _, _, _, t in r0 if t not in ("none", "unknown", None))}
        kit_reqs = {w: m for w, m, _, _ in requests(KIT, arm, None)}
        for model in GPT + CLAUDE:
            hit0 = {cache_key(model, m, o) for _, m, o, _ in r0}
            found0 = sum(1 for k in hit0 if (a.cache / f"{k}.json").is_file())
            keysA = {}
            for w, m, o, _ in rA:
                keysA.setdefault(cache_key(model, m, o), m)
            newA = {k: m for k, m in keysA.items() if not (a.cache / f"{k}.json").is_file()}
            ratio, comp = token_rates(model, arm, kit_reqs)
            pin, _, pout = (run_gpt.PRICES if model in GPT else run_claude.PRICES)[model]
            tok_in = sum(chars(m) for m in newA.values()) * ratio
            usd_tokens = (tok_in * pin + len(newA) * comp * pout) / 1e6
            paid, calls = PAID[(model, arm)]
            new_windows = sum(1 for _, m, o, _ in rA if cache_key(model, m, o) in newA)
            res["models"][f"{model} | {name}"] = {
                "selfcheck_b0_r0_requests": len(hit0), "selfcheck_b0_r0_found_in_cache": found0,
                "b0_rA_windows": len(rA), "b0_rA_distinct_requests": len(keysA), "b0_rA_cached": len(keysA) - len(newA),
                "b0_rA_new_calls": len(newA),
                # upper bound on paid calls: every window with an uncached prompt paid once (two workers can ask the
                # same new prompt at the same moment; attempt-1 retries only follow an invalid answer, none in 11-09)
                "b0_rA_windows_with_new_prompt": new_windows,
                "usd_per_call_paid": paid / calls, "usd_new_paid_rate": len(newA) * paid / calls,
                "usd_upper_paid_rate": new_windows * paid / calls,
                "prompt_tokens_per_char_1109": ratio, "completion_tokens_per_call_1109": comp,
                "pred_prompt_tokens_new": round(tok_in), "usd_new_token_rate": usd_tokens}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.json_out:
        a.json_out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
