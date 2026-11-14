"""1-s variant: a window whose answer came from a real call slower than 1,000 ms gets choice null (score.py then uses the
rule table's decision, checked: an all-null answers file scores exactly the rule-table row). Windows answered from the
cache inherit the latency of the real call that produced the answer (our runner and the E5 Jev runner both log it so).

GPT runs: runs/<run>/calls.jsonl (latency of the attempt that gave the answer).
Jev: E5 logs 4_vision/eval_jev_2026-11-04/results/real_2026-11-05_3c936ae/{stage2_3_J_b0_r0 (arm J), stage2_1_swap_C_C0
(arm C0)}/jev_calls.jsonl, support_choice stage; window_id = take@t; the logged choice is checked against the kit's
reference answers before use.
Writes runs/<run>/answers_1s.jsonl (GPT) or runs/jev_<arm>_1s/answers_1s.jsonl, and prints the per-run counts.
"""
import json, sys
from pathlib import Path

root, kit, e5 = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
LIMIT_MS = 1000.0  # the kiosk's 1-s judgment window (paper's 1-s rule)


def write(out, answers):
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for wid, ch in answers:
            f.write(json.dumps({"window_id": wid, "choice": ch}) + "\n")


report = {}
for run in sorted(p for p in (root / "runs").iterdir() if p.is_dir() and (p / "calls.jsonl").exists() and not p.name.startswith("jev_")):
    calls = [json.loads(l) for l in (run / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    by = {}
    for c in calls:
        if c["choice"] is not None:
            by[c["window_id"]] = c
    ans = [json.loads(l) for l in (run / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
    out, slow = [], 0
    for a in ans:
        c = by.get(a["window_id"])
        ok = c is not None and c["latency_ms"] is not None and c["latency_ms"] <= LIMIT_MS
        slow += not ok
        out.append((a["window_id"], a["choice"] if ok else None))
    write(run / "answers_1s.jsonl", out)
    report[run.name] = {"windows": len(ans), "set_null_over_1s": slow}

for arm, d in (("E5_J", "stage2_3_J_b0_r0"), ("E5_C0", "stage2_1_swap_C_C0")):
    jarm = "J" if arm == "E5_J" else "C0"
    ref = {}
    for l in (kit / f"reference_answers/{arm}.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(l)
        ref[r["window_id"]] = r["choice"]
    lat, mism = {}, 0
    for l in (e5 / d / "jev_calls.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(l)
        if r["arm"] != jarm:
            continue
        for s in r["stages"]:
            if s["stage"] == "support_choice" and s.get("latency_ms") is not None:
                wid = f"{r['take']}@{r['t']}"
                if wid in ref:
                    ch = ((s.get("answers") or {}).get("support_choice") or {}).get("choice")
                    mism += ch != ref[wid]
                    lat[wid] = s["latency_ms"]
    out = [(w, ch if (w in lat and lat[w] <= LIMIT_MS) else None) for w, ch in ref.items()]
    write(root / "runs" / f"jev_{arm}_1s" / "answers_1s.jsonl", out)
    L = sorted(lat.values())
    report[f"jev_{arm}"] = {"windows": len(ref), "with_latency": len(lat), "choice_mismatch_vs_reference": mism,
                            "set_null_over_1s": sum(1 for w, c in out if c is None and ref[w] is not None),
                            "missing_latency": len(ref) - len(lat),
                            "max_ms": L[-1] if L else None}
print(json.dumps(report, indent=1))
