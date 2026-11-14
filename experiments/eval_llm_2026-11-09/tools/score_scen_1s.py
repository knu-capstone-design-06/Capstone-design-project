"""1-s variant on the scenario sets, as her why/score_deadline.py and v2/score_heldout.py do it: a case whose answer
is null or whose call took more than 1,000 ms gets the rule table's answer (her rule answer files, copied to
runs/scenarios/inputs/<set>_rule.jsonl). Usage: python -I score_scen_1s.py runs/scenarios"""
import json, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from score_scen import bal, load  # noqa: E402
root = Path(sys.argv[1])
res = {}
for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "inputs"):
    m, s, r = d.name.rsplit("__", 2)
    gold = json.loads((root / "inputs" / f"{s}_gold.json").read_text(encoding="utf-8"))
    rule = load(root / "inputs" / f"{s}_rule.jsonl")
    ans = load(d / "answers.jsonl", "case_id")
    lat = {}
    for l in (d / "calls.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(l)
        if c["choice"] is not None:
            lat[c["case_id"]] = c["latency_ms"]
    one = {c: (ans[c] if ans.get(c) is not None and lat.get(c, 1e9) <= 1000 else rule[c]) for c in gold}
    res.setdefault(f"{m} | {s}", []).append(round(bal(gold, one)["bal"], 4))
print(json.dumps({k: {"runs": v, "mean": round(statistics.mean(v), 4)} for k, v in res.items()}, indent=1))
print("rule:", {s: round(bal(json.loads((root / "inputs" / f"{s}_gold.json").read_text(encoding="utf-8")), load(root / "inputs" / f"{s}_rule.jsonl"))["bal"], 4) for s in ("novel", "heldout1", "heldout2")})
