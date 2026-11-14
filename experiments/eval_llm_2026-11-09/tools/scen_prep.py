"""Build the teammate's scenario-set inputs (data only; none of her code is imported or run).

Sets: novel SUM (60), heldout1 (56), heldout2 (56). For each case: case_id, state, questions (her exact question object),
options (criteria keys). Gold lists are copied. Question sources:
- novel: novel/kit/data/questions.json["NOVEL_SUM.support_choice"] (the object her run_llm.py sent).
- heldout1: v2/runs/ho_v0_r1/questions.json (written by her run_v2.py for the v0 question = the one sol_ho.py sent).
- heldout2: same v0 text with heldout1's extra field glossary replaced by heldout2's, built the way her designs.py does
  ("".join(f"`touch_patterns.{k}`: {v} ") over fields.json). Check: the same construction from heldout1/fields.json
  rebuilds the stored heldout1 text byte for byte.
Usage: python -I scen_prep.py <her repro dir> <out dir>
"""
import json, sys
from pathlib import Path

R, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
rd = lambda p: json.loads((R / p).read_text(encoding="utf-8"))
extra = lambda f: "".join(f"`touch_patterns.{k}`: {v} " for k, v in rd(f).items())

nq = rd("novel/kit/data/questions.json")["NOVEL_SUM.support_choice"]
nq = nq.get("questions", nq)
h1q = rd("v2/runs/ho_v0_r1/questions.json")
ins1 = h1q["support_choice"]["instructions"]
e1 = extra("heldout/fields.json")
assert ins1.endswith(e1), "heldout1 instructions do not end with its field glossary"
base = ins1[: len(ins1) - len(e1)]
assert base + e1 == ins1
h2q = {"support_choice": {**h1q["support_choice"], "instructions": base + extra("heldout2/fields.json")}}
checks = {"heldout1_rebuilt_equal": base + e1 == ins1}

sets = {}
rows = []
for l in (R / "novel/kit/data/NOVEL_SUM.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip():
        r = json.loads(l)
        st = r["stages"][-1]
        assert st["questions"] == "NOVEL_SUM.support_choice" and "<STAGE1_SCORES>" not in json.dumps(st["state"])
        rows.append({"case_id": r["window_id"], "state": st["state"], "questions": nq})
sets["novel"] = (rows, rd("novel/gold.json"))
for name, d, q in (("heldout1", "heldout", h1q), ("heldout2", "heldout2", h2q)):
    rows = [{"case_id": c["case_id"], "state": c["state"], "questions": q}
            for c in (json.loads(l) for l in (R / d / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())]
    sets[name] = (rows, rd(f"{d}/gold.json"))
for name, (rows, gold) in sets.items():
    assert {r["case_id"] for r in rows} == set(gold), name
    with open(out / f"{name}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / f"{name}_gold.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = [g["kind"] for g in gold.values()]
    checks[name] = {"cases": len(rows), "help": kinds.count("help"), "wait": kinds.count("wait"),
                    "options": list(rows[0]["questions"]["support_choice"]["criteria"])}
print(json.dumps(checks, indent=1))
