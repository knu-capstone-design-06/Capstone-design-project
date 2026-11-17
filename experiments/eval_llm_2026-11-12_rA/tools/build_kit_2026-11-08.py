"""Build llm_eval_kit_2026-11-08 from the recorded E5 / E12 runs (reads the run records, writes only the kit folder).

Checks while building (any failure stops the build):
  - the three runs share one rule_windows.jsonl (sha256);
  - every state / question set written to the kit hashes (run_jev_ablation.digest) to the hash the run recorded;
  - every stage-2 template, filled with the recorded stage-1 answers, hashes to the recorded stage-2 state;
  - the window -> cell mapping is E5 metrics.py's AdmissibleLabels.match_record (labels v5, judgment labels by time).
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import os
WORKSPACE = Path(os.environ.get("KIOSK_WORKSPACE", "."))  # 실험 기록이 있는 작업 폴더
W = WORKSPACE
KIT = W / "5_deliverables" / "llm_eval_kit_2026-11-08"
E5 = W / "4_vision" / "eval_jev_2026-11-04"
E5R = E5 / "results" / "real_2026-11-05_3c936ae"
RUN_J, RUN_C = E5R / "stage2_3_J_b0_r0", E5R / "stage2_1_swap_C_C0"
RUN_RAW = W / "4_vision" / "eval_jev_raw_2026-11-08" / "results" / "c_full"
AB = W / "4_vision" / "eval_ab_2026-11-04"
ADM, JL = AB / "admissible_v5.csv", AB / "judgment_labels_v5.csv"
EXCLUDED = "20261028_165108"          # 1x zoom, out of every evaluation
VARIANT = "fit-medium"                # E3 / E5 main placement of the synthetic touch session
PLACEHOLDER = "<STAGE1_SCORES>"

sys.path.insert(0, str(E5 / "tools"))
import metrics as M  # noqa: E402  (stdlib only at import; help_rule is imported lazily and not used here)


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj) -> str:
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()[:16]


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


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
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:   # BOM: Excel opens the Korean form names
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    # ---- one rule-table flow for all runs
    hashes = {sha_file(r / "rule_windows.jsonl") for r in (RUN_J, RUN_C, RUN_RAW)}
    assert len(hashes) == 1, hashes
    rules = read_jsonl(RUN_J / "rule_windows.jsonl")
    rules.sort(key=lambda r: (r["take"], r["i"]))
    kept = [r for r in rules if r["clip"] != EXCLUDED]
    ids = [wid(r["clip"], r["condition"], r["t"]) for r in kept]
    assert len(set(ids)) == len(ids)
    print(f"windows {len(rules)}, outside {EXCLUDED}: {len(kept)}")

    # ---- window -> cell mapping, E5's own label join
    labels = M.AdmissibleLabels.load(ADM, JL)
    cells = []
    scored = 0
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
    print(f"scored windows {scored} (recorded scoring: 2710)")
    assert scored == 2710
    write_csv(KIT / "labels" / "window_cells.csv",
              ["window_id", "clip", "condition", "t", "measurable", "rule_transition", "rule_support", "segment_id",
               "cell_id", "cell_class", "scored"], cells)

    # ---- trimmed label tables (the columns score.py reads, plus names)
    with open(JL, encoding="utf-8-sig", newline="") as fh:
        jl = [r for r in csv.DictReader(fh) if r["take"] != EXCLUDED]
    jcols = ["take", "turn", "segment_id", "t_start", "t_end", "scene_plan", "segment_class"]
    write_csv(KIT / "labels" / "judgment_labels_v5.csv", jcols, [[r[c] for c in jcols] for r in jl])
    with open(ADM, encoding="utf-8-sig", newline="") as fh:
        adm = [r for r in csv.DictReader(fh) if r["variant"] == VARIANT]
    acols = ["segment_id", "take", "turn", "condition", "variant", "scene_plan", "eff_class", "base_admissible",
             "addon_admissible", "addon_onset_s", "onset_s", "designated", "designated_v0_row", "rules"]
    assert all(r["take"] != EXCLUDED for r in adm)
    write_csv(KIT / "labels" / "admissible_v5.csv", acols, [[r[c] for c in acols] for r in adm])
    print(f"labels: judgment rows {len(jl)}, admissible rows {len(adm)}")

    # ---- not-asked windows
    na = [[w, r["clip"], r["condition"], json.dumps(r["t"]), "not measurable", r["rule"]["transition"],
           r["rule"]["support"] or "", c[9]] for r, w, c in zip(kept, ids, cells) if not r["measurable"]]
    assert all(x[5] in ("none", "keep") for x in na)
    write_csv(KIT / "data" / "not_asked_windows.csv",
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

    def template(state2: dict, stage1_answers: dict) -> dict:
        """The stage-2 state with the stage-1 scores replaced by the placeholder; checked against the record."""
        assert state2["jev"] == {"state_scores": {k: v["p"] for k, v in stage1_answers.items()}}, state2["jev"]
        out = {k: ({"state_scores": PLACEHOLDER} if k == "jev" else v) for k, v in state2.items()}
        filled = {k: ({"state_scores": {q: a["p"] for q, a in stage1_answers.items()}} if k == "jev" else v)
                  for k, v in out.items()}
        assert canon(filled) == canon(state2)
        return out

    out_rows, ref_rows = {}, {}

    # E5 J
    calls, states, questions = load_run(RUN_J)
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

    # E5 C0 and C
    calls, states, questions = load_run(RUN_C)
    c0_names = {"691a8c15a528d32a": "E5_candidates.support_choice[highlight_next_action]",
                "11f41bd1d6136f08": "E5_candidates.support_choice[large_button]",
                "62cf52a170f0c1a2": "E5_candidates.support_choice[large_button,highlight_next_action]"}
    s1_names = {"3fab243012f90066": "E5_C.state_scores",
                "febec567cf333ffb": "E5_C.state_scores+proposal_fits[highlight_next_action]",
                "4809168e2b72ff73": "E5_C.state_scores+proposal_fits[large_button]"}
    rows0, refs0, rowsC, refsC = [], [], [], []
    for c in calls:
        if not c["asked"] or c["take"].startswith(EXCLUDED):
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
        name2 = qid(c0_names[sc["questions_hash"]], sc["questions_hash"], questions)
        o = opts(questions[sc["questions_hash"]])
        assert o == r["allowed_candidates"] + ["none"]
        choice = sc["answers"]["support_choice"]["choice"]
        if c["arm"] == "C0":
            rows0.append({**b, "arm": "E5_C0", "option_set": "candidates",
                          "stages": [{"stage": "support_choice", "questions": name2, "options": o, "state": st2}]})
            refs0.append({"window_id": b["window_id"], "choice": choice})
        else:
            s1 = M.stage_of(c, "state_scores")
            assert s1["outcome"] == "answered"
            st1 = states[s1["state_hash"]]
            assert digest(st1) == s1["state_hash"]
            name1 = qid(s1_names[s1["questions_hash"]], s1["questions_hash"], questions)
            tpl = template(st2, s1["answers"])
            assert {k: v for k, v in tpl.items() if k not in ("jev", "candidates")} == st1
            rowsC.append({**b, "arm": "E5_C", "option_set": "candidates",
                          "stages": [{"stage": "state_scores", "questions": name1, "state": st1},
                                     {"stage": "support_choice", "questions": name2, "options": o, "state": tpl}]})
            refsC.append({"window_id": b["window_id"],
                          "state_scores": {q: a["p"] for q, a in s1["answers"].items()}, "choice": choice})
    assert [x["window_id"] for x in rows0] == [x["window_id"] for x in rowsC]
    out_rows["E5_C0"], ref_rows["E5_C0"] = rows0, refs0
    out_rows["E5_C"], ref_rows["E5_C"] = rowsC, refsC

    # E12 RAW-1 and RAW-2
    calls, states, questions = load_run(RUN_RAW)
    r1, f1, r2, f2 = [], [], [], []
    for c in calls:
        if not c["asked"] or c["take"].startswith(EXCLUDED):
            continue
        b = base(c)
        sc = M.stage_of(c, "support_choice")
        assert sc["outcome"] == "answered"
        st2 = states[sc["state_hash"]]
        assert digest(st2) == sc["state_hash"]
        name2 = qid("E12.support_choice", sc["questions_hash"], questions)
        o = opts(questions[sc["questions_hash"]])
        choice = sc["answers"]["support_choice"]["choice"]
        if c["arm"] == "RAW-1":
            r1.append({**b, "arm": "E12_RAW-1", "option_set": "all",
                       "stages": [{"stage": "support_choice", "questions": name2, "options": o, "state": st2}]})
            f1.append({"window_id": b["window_id"], "choice": choice})
        else:
            s1 = M.stage_of(c, "state_scores")
            assert s1["outcome"] == "answered"
            st1 = states[s1["state_hash"]]
            assert digest(st1) == s1["state_hash"]
            name1 = qid("E12.state_scores", s1["questions_hash"], questions)
            tpl = template(st2, s1["answers"])
            assert {k: v for k, v in tpl.items() if k not in ("jev", "candidates")} == st1
            r2.append({**b, "arm": "E12_RAW-2", "option_set": "all",
                       "stages": [{"stage": "state_scores", "questions": name1, "state": st1},
                                  {"stage": "support_choice", "questions": name2, "options": o, "state": tpl}]})
            f2.append({"window_id": b["window_id"],
                       "state_scores": {q: a["p"] for q, a in s1["answers"].items()}, "choice": choice})
    out_rows["E12_RAW-1"], ref_rows["E12_RAW-1"] = r1, f1
    out_rows["E12_RAW-2"], ref_rows["E12_RAW-2"] = r2, f2

    # ---- asked sets: J / RAW = every measurable window, C0 / C = measurable windows with rule-table candidates
    measurable = {w for r, w in zip(kept, ids) if r["measurable"]}
    with_cand = {w for r, w in zip(kept, ids) if r["measurable"] and r["allowed_candidates"]}
    for arm, rows in out_rows.items():
        got = [x["window_id"] for x in rows]
        assert len(set(got)) == len(got)
        want = with_cand if arm in ("E5_C0", "E5_C") else measurable
        assert set(got) == want, (arm, len(got), len(want))
        order = {w: k for k, w in enumerate(ids)}
        rows.sort(key=lambda x: order[x["window_id"]])
        ref_rows[arm].sort(key=lambda x: order[x["window_id"]])
        write_jsonl(KIT / "data" / f"{arm}.jsonl", rows)
        write_jsonl(KIT / "reference_answers" / f"{arm}.jsonl", ref_rows[arm])
        print(f"{arm}: {len(rows)} windows, choices {dict(Counter(x['choice'] for x in ref_rows[arm]))}")
    (KIT / "data" / "questions.json").write_text(json.dumps(qsets, ensure_ascii=False, indent=1) + "\n",
                                                 encoding="utf-8", newline="\n")
    print("question sets:", list(qsets))
    print("sources sha256:", {p.name: sha_file(p) for p in (ADM, JL)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
