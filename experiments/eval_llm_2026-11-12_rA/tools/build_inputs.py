"""Build the per-window model inputs of the E5 arms E5_J and E5_C0 for one value bundle, in the layout of the LLM
evaluation kit (5_deliverables/llm_eval_kit_2026-11-08), from the records of an E5 run (run_jev_ablation.py output:
jev_calls.jsonl, states.jsonl, questions.json, rule_windows.jsonl).

Derived from the kit's own builder, build_kit.py of 2026-11-08 (its
copy: tools/build_kit_2026-11-08.py). The code for E5_J, E5_C0, window_cells.csv, not_asked_windows.csv and the two
trimmed label tables is that builder's, with these changes only:
  - the run folders and the output folder are arguments (build_kit.py had them fixed and also read the E12 run);
  - only the arms E5_J and E5_C0 are written (table 4 uses these two; E5_C and E12 are left out);
  - in a run with more arms (e.g. A, B, C, C0, J) only the C0 lines feed E5_C0;
  - a candidate question set whose hash build_kit.py did not know is named by the same pattern
    'E5_candidates.support_choice[<candidates, comma-separated, in sent order>]'; the three known names are checked
    against that pattern.
Checks while building (any failure stops it): the J and C0 runs share one rule_windows.jsonl (same lines for the
kept windows); every state and question set written hashes (run_jev_ablation.digest) to the hash the run recorded;
the C0 options equal the rule table's allowed candidates + none; the asked windows are exactly the measurable windows
(E5_J) and the measurable windows with candidates (E5_C0); the window -> cell mapping is E5 metrics.py's
AdmissibleLabels.match_record (labels v5, judgment labels by time) and gives the recorded 2,710 scored windows.

  python build_inputs.py --run-j <run folder> --run-c0 <run folder> --out <folder>
Standard library only (imports 4_vision/eval_jev_2026-11-04/tools/metrics.py, stdlib at import).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

W = Path(__file__).resolve().parents[3]                      # the workspace root
E5 = W / "4_vision" / "eval_jev_2026-11-04"
AB = W / "4_vision" / "eval_ab_2026-11-04"
ADM, JL = AB / "admissible_v5.csv", AB / "judgment_labels_v5.csv"
EXCLUDED = "20261028_165108"          # 1x zoom, out of every evaluation
VARIANT = "fit-medium"                # E3 / E5 main placement of the synthetic touch session
SCORED_WINDOWS = 2710                 # recorded by build_kit.py for labels v5 (the label join, not the bundle)
C0_NAMES = {"691a8c15a528d32a": "E5_candidates.support_choice[highlight_next_action]",      # build_kit.py
            "11f41bd1d6136f08": "E5_candidates.support_choice[large_button]",
            "62cf52a170f0c1a2": "E5_candidates.support_choice[large_button,highlight_next_action]"}

sys.dont_write_bytecode = True        # never write __pycache__ into the E5 tools folder
sys.path.insert(0, str(E5 / "tools"))
import metrics as M  # noqa: E402


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj) -> str:
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()[:16]


def read_jsonl(p: Path) -> list:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def wid(clip: str, cond: str, t: float) -> str:
    return f"{clip}@{cond}@{json.dumps(t)}"


def load_run(run: Path) -> tuple[list, dict, dict]:
    calls = read_jsonl(run / "jev_calls.jsonl")
    states = {x["state_hash"]: x["state"] for x in read_jsonl(run / "states.jsonl")}
    questions = json.loads((run / "questions.json").read_text(encoding="utf-8"))
    return calls, states, questions


def write_jsonl(p: Path, rows: list) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(p: Path, header: list, rows: list) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:   # BOM, as the kit (Excel shows the Korean form names)
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def kept_rules(run: Path) -> list:
    rules = [r for r in read_jsonl(run / "rule_windows.jsonl") if r["clip"] != EXCLUDED]
    rules.sort(key=lambda r: (r["take"], r["i"]))
    return rules


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-j", required=True, help="E5 run folder with arm J")
    ap.add_argument("--run-c0", required=True, help="E5 run folder with arm C0 (may be the same folder)")
    ap.add_argument("--out", required=True, help="output folder (data/, labels/, reference_answers/)")
    a = ap.parse_args()
    run_j, run_c, out = Path(a.run_j), Path(a.run_c0), Path(a.out)

    # ---- one rule-table flow for both arms (kept windows; a run may also hold clip 20261028_165108)
    kept = kept_rules(run_j)
    assert [canon(r) for r in kept] == [canon(r) for r in kept_rules(run_c)], "J and C0 runs differ in rule_windows"
    ids = [wid(r["clip"], r["condition"], r["t"]) for r in kept]
    assert len(set(ids)) == len(ids)
    bundles = sorted({r.get("bundle") or "" for r in kept})
    print(f"windows outside {EXCLUDED}: {len(kept)}; bundle {bundles}")

    # ---- window -> cell mapping, E5's own label join
    labels = M.AdmissibleLabels.load(ADM, JL)
    cells, scored = [], 0
    for r, w in zip(kept, ids):
        assert r["variant"] == VARIANT
        lab = labels.match_record(r)
        assert lab is not None, w
        cls = lab["eff_class"]
        ok = cls not in M.NOT_EVALUABLE
        scored += ok
        rule = r["rule"]
        cells.append([w, r["clip"], r["condition"], json.dumps(r["t"]), int(r["measurable"]), rule["transition"],
                      rule["support"] or "", lab["segment"], lab["row"], cls, int(ok)])
    print(f"scored windows {scored} (recorded scoring: {SCORED_WINDOWS})")
    assert scored == SCORED_WINDOWS
    write_csv(out / "labels" / "window_cells.csv",
              ["window_id", "clip", "condition", "t", "measurable", "rule_transition", "rule_support", "segment_id",
               "cell_id", "cell_class", "scored"], cells)

    # ---- trimmed label tables (the columns score.py reads, plus names)
    with open(JL, encoding="utf-8-sig", newline="") as fh:
        jl = [r for r in csv.DictReader(fh) if r["take"] != EXCLUDED]
    jcols = ["take", "turn", "segment_id", "t_start", "t_end", "scene_plan", "segment_class"]
    write_csv(out / "labels" / "judgment_labels_v5.csv", jcols, [[r[c] for c in jcols] for r in jl])
    with open(ADM, encoding="utf-8-sig", newline="") as fh:
        adm = [r for r in csv.DictReader(fh) if r["variant"] == VARIANT]
    acols = ["segment_id", "take", "turn", "condition", "variant", "scene_plan", "eff_class", "base_admissible",
             "addon_admissible", "addon_onset_s", "onset_s", "designated", "designated_v0_row", "rules"]
    assert all(r["take"] != EXCLUDED for r in adm)
    write_csv(out / "labels" / "admissible_v5.csv", acols, [[r[c] for c in acols] for r in adm])

    # ---- not-asked windows
    na = [[w, r["clip"], r["condition"], json.dumps(r["t"]), "not measurable", r["rule"]["transition"],
           r["rule"]["support"] or "", c[9]] for r, w, c in zip(kept, ids, cells) if not r["measurable"]]
    assert all(x[5] in ("none", "keep") for x in na)
    write_csv(out / "data" / "not_asked_windows.csv",
              ["window_id", "clip", "condition", "t", "reason", "rule_transition", "rule_support", "cell_class"], na)
    print(f"not asked (not measurable): {len(na)}")

    # ---- question sets
    qsets: dict = {}
    qnames: dict = {}

    def qid(name: str, h: str, catalog: dict) -> str:
        q = catalog[h]
        assert digest(q) == h
        if h in qnames:
            return qnames[h]
        qnames[h] = name
        qsets[name] = {"questions_hash": h, "questions": q}
        return name

    meta = {wid(r["clip"], r["condition"], r["t"]): r for r in kept}

    def base(c) -> dict:
        r = meta[wid(c["take"].split("@")[0], c["take"].split("@")[1], c["t"])]
        return {"window_id": wid(r["clip"], r["condition"], r["t"]), "clip": r["clip"], "condition": r["condition"],
                "t": r["t"]}

    def opts(q: dict) -> list:
        return list(q["support_choice"]["criteria"])

    def c0_name(h: str, options: list) -> str:
        pattern = "E5_candidates.support_choice[" + ",".join(o for o in options if o != "none") + "]"
        if h in C0_NAMES:
            assert C0_NAMES[h] == pattern, (C0_NAMES[h], pattern)
        return pattern

    out_rows, ref_rows = {}, {}

    # E5 J
    calls, states, questions = load_run(run_j)
    rows, refs = [], []
    for c in calls:
        if c["arm"] != "J" or not c["asked"] or c["take"].startswith(EXCLUDED):
            continue
        (s,) = c["stages"]
        assert s["stage"] == "support_choice" and s["outcome"] == "answered"
        st = states[s["state_hash"]]
        assert digest(st) == s["state_hash"]
        name = qid("E5_J.support_choice", s["questions_hash"], questions)
        b = base(c)
        rows.append({**b, "arm": "E5_J", "option_set": "all",
                     "stages": [{"stage": "support_choice", "questions": name,
                                 "options": opts(questions[s["questions_hash"]]), "state": st}]})
        refs.append({"window_id": b["window_id"], "choice": s["answers"]["support_choice"]["choice"]})
    out_rows["E5_J"], ref_rows["E5_J"] = rows, refs

    # E5 C0
    calls, states, questions = load_run(run_c)
    rows0, refs0 = [], []
    for c in calls:
        if c["arm"] != "C0" or not c["asked"] or c["take"].startswith(EXCLUDED):
            continue
        sc = M.stage_of(c, "support_choice")
        if sc["outcome"] == "skipped":
            continue
        assert sc["outcome"] == "answered"
        b = base(c)
        r = meta[b["window_id"]]
        st2 = states[sc["state_hash"]]
        assert digest(st2) == sc["state_hash"]
        assert st2["candidates"] == r["allowed_candidates"], (st2["candidates"], r["allowed_candidates"])
        o = opts(questions[sc["questions_hash"]])
        assert o == r["allowed_candidates"] + ["none"]
        name2 = qid(c0_name(sc["questions_hash"], o), sc["questions_hash"], questions)
        rows0.append({**b, "arm": "E5_C0", "option_set": "candidates",
                      "stages": [{"stage": "support_choice", "questions": name2, "options": o, "state": st2}]})
        refs0.append({"window_id": b["window_id"], "choice": sc["answers"]["support_choice"]["choice"]})
    out_rows["E5_C0"], ref_rows["E5_C0"] = rows0, refs0

    # ---- asked sets: J = every measurable window, C0 = measurable windows with rule-table candidates
    measurable = {w for r, w in zip(kept, ids) if r["measurable"]}
    with_cand = {w for r, w in zip(kept, ids) if r["measurable"] and r["allowed_candidates"]}
    order = {w: k for k, w in enumerate(ids)}
    for arm, rows in out_rows.items():
        got = [x["window_id"] for x in rows]
        assert len(set(got)) == len(got)
        want = with_cand if arm == "E5_C0" else measurable
        assert set(got) == want, (arm, len(got), len(want))
        rows.sort(key=lambda x: order[x["window_id"]])
        ref_rows[arm].sort(key=lambda x: order[x["window_id"]])
        write_jsonl(out / "data" / f"{arm}.jsonl", rows)
        write_jsonl(out / "reference_answers" / f"{arm}.jsonl", ref_rows[arm])
        print(f"{arm}: {len(rows)} windows, choices {dict(Counter(x['choice'] for x in ref_rows[arm]))}")
    (out / "data" / "questions.json").write_text(json.dumps(qsets, ensure_ascii=False, indent=1) + "\n",
                                                 encoding="utf-8", newline="\n")
    print("question sets:", list(qsets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
