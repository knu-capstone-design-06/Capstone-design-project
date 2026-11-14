"""Predict the spend of an E5_J run (all windows, or the table-cell windows only) per model from stage-1 usage.

Prompt tokens: stage-1 calls give tokens per prompt character for each model (sum prompt_tokens / sum prompt chars of
the same messages); the J prompts' characters times that ratio give the J prompt tokens. Completion tokens per call:
the stage-1 mean. Two figures per model: every window billed (as a deployed kiosk would pay), and distinct prompts only
(what this runner pays, since identical prompts share one cached response).
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_gpt import build_messages, PRICES  # noqa: E402

kit, runs, prep = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
qdoc = json.loads((kit / "data/questions.json").read_text(encoding="utf-8"))


def prompts(arm, only=None):
    out = {}
    for l in (kit / f"data/{arm}.jsonl").read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if only is not None and r["window_id"] not in only:
            continue
        st = r["stages"][-1]
        out[r["window_id"]] = json.dumps(build_messages(qdoc[st["questions"]]["questions"]["support_choice"], st["state"]))
    return out


def chars(m):
    return sum(len(x["content"]) for x in json.loads(m))


c0 = prompts("E5_C0")
cell = set((prep / "E5_J_cell_windows.txt").read_text(encoding="utf-8").split())
sets = {"E5_J all": prompts("E5_J"), "E5_J table-cell windows": prompts("E5_J", cell)}
res = {}
for model in PRICES:
    calls = [json.loads(l) for l in (runs / f"{model}_E5_C0" / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    ok = [c for c in calls if not c["error"]]
    ratio = sum(c["prompt_tokens"] for c in ok) / sum(chars(c0[c["window_id"]]) for c in ok)
    comp = sum(c["completion_tokens"] for c in ok) / len(ok)
    pin, _, pout = PRICES[model]
    for name, ps in sets.items():
        tot = sum(chars(m) for m in ps.values()) * ratio
        distinct = {}
        for m in ps.values():
            distinct[m] = chars(m) * ratio
        cost_all = (tot * pin + len(ps) * comp * pout) / 1e6
        cost_dist = (sum(distinct.values()) * pin + len(distinct) * comp * pout) / 1e6
        res[f"{model} | {name}"] = {"windows": len(ps), "distinct_prompts": len(distinct),
                                    "pred_prompt_tokens": round(tot), "completion_per_call": round(comp, 2),
                                    "usd_every_window_billed": round(cost_all, 4), "usd_distinct_prompts_only": round(cost_dist, 4)}
print(json.dumps(res, indent=1))
