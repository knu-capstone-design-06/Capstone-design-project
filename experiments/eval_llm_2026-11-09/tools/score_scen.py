"""Balanced accuracy on the teammate's scenario sets, as her score_novel.py / v2/score_heldout.py / explore/score_ho2.py
define it (re-implemented here, her code not run): acc = share of help cases whose choice is in `acceptable`;
wait = share of wait cases whose choice is not null and not visible; bal = (acc + wait) / 2.
Visible = the 7 supports that show something (her VISIBLE set).

  python -I score_scen.py verify <her repro dir> <inputs dir>     re-score her stored answers
  python -I score_scen.py runs <runs/scenarios dir>               score our runs (3-run mean per model x set)
"""
import json, statistics, sys
from pathlib import Path

VISIBLE = {"remaining_steps_notice", "delay_responsibility_notice", "large_button", "highlight_next_action",
           "large_text", "low_screen", "step_guide"}


def bal(gold, ans):
    h = [c for c in gold if gold[c]["kind"] == "help"]
    w = [c for c in gold if gold[c]["kind"] == "wait"]
    acc = sum(ans.get(c) in gold[c]["acceptable"] for c in h) / len(h)
    wait = sum(ans.get(c) is not None and ans.get(c) not in VISIBLE for c in w) / len(w)
    return {"acc": acc, "wait": wait, "bal": (acc + wait) / 2}


def load(p, key="window_id"):
    out = {}
    for l in Path(p).read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            out[r[key]] = r["choice"]
    return out


def verify(R, inp):
    gold = {s: json.loads((inp / f"{s}_gold.json").read_text(encoding="utf-8")) for s in ("novel", "heldout1", "heldout2")}
    res = {}
    res["novel rule"] = bal(gold["novel"], load(R / "novel/answers_rule.jsonl"))["bal"]
    for arm in ("jev_NOVEL_SUM", "gpt-6.1-sol_NOVEL_SUM", "gpt-4o-mini_NOVEL_SUM", "gpt-5.4-mini_NOVEL_SUM"):
        v = [bal(gold["novel"], load(R / f"novel/runs/{arm}_r{i}/answers.jsonl"))["bal"] for i in (1, 2, 3)]
        res[f"novel {arm}"] = (v, statistics.mean(v))
    res["heldout1 rule"] = bal(gold["heldout1"], load(R / "v2/heldout_rule.jsonl"))["bal"]
    v = [bal(gold["heldout1"], load(R / f"v2/runs/ho_v0_r{i}/answers.jsonl"))["bal"] for i in (1, 2, 3)]
    res["heldout1 jev v0"] = (v, statistics.mean(v))
    res["heldout1 sol"] = bal(gold["heldout1"], load(R / "explore/runs/sol_ho1/answers.jsonl"))["bal"]
    res["heldout2 rule"] = bal(gold["heldout2"], load(R / "v2/heldout2_rule.jsonl"))["bal"]
    v = []
    for i in (1, 2, 3):
        a = {}
        for l in (R / f"explore/runs/ho2_r{i}/probe.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(l)
            if r.get("set") == "ho2":
                ch = ((r.get("v0") or {}).get("answers") or {}).get("support_choice") or {}
                a[r["case_id"]] = ch.get("choice") if isinstance(ch, dict) else ch
        v.append(bal(gold["heldout2"], a)["bal"])
    res["heldout2 jev v0"] = (v, statistics.mean(v))
    res["heldout2 sol"] = bal(gold["heldout2"], load(R / "explore/runs/sol_ho2/answers.jsonl"))["bal"]
    return res


def runs(root):
    gold = {s: json.loads((root / "inputs" / f"{s}_gold.json").read_text(encoding="utf-8"))
            for s in ("novel", "heldout1", "heldout2")}
    table = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "inputs"):
        model, s, r = d.name.rsplit("__", 2)
        if not (d / "answers.jsonl").exists():
            continue
        sc = bal(gold[s], load(d / "answers.jsonl", "case_id"))
        summ = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        table.setdefault((model, s), []).append({"run": r, **sc, "p50_ms": summ["latency_ms"]["p50"],
                                                 "share_le_1000": summ["latency_ms"]["share_le_1000"],
                                                 "null": summ["null_answers"], "spend": summ["spend_usd"]})
    out = {}
    for (m, s), rs in table.items():
        out[f"{m} | {s}"] = {"runs": [round(x["bal"], 4) for x in rs], "mean_bal": round(statistics.mean(x["bal"] for x in rs), 4),
                             "mean_acc": round(statistics.mean(x["acc"] for x in rs), 4),
                             "mean_wait": round(statistics.mean(x["wait"] for x in rs), 4),
                             "p50_ms_per_run": [x["p50_ms"] for x in rs],
                             "share_le_1000_per_run": [x["share_le_1000"] for x in rs],
                             "nulls": sum(x["null"] for x in rs), "spend_usd": round(sum(x["spend"] for x in rs), 5)}
    for m in sorted({k.split(" | ")[0] for k in out}):
        a, b = out.get(f"{m} | heldout1"), out.get(f"{m} | heldout2")
        if a and b:
            out[f"{m} | heldout mean of 2 sets"] = round((a["mean_bal"] + b["mean_bal"]) / 2, 4)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "verify":
        print(json.dumps(verify(Path(sys.argv[2]), Path(sys.argv[3])), indent=1))
    else:
        print(json.dumps(runs(Path(sys.argv[2])), indent=1))
