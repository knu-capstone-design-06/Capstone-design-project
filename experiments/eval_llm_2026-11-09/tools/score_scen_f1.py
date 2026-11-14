"""Precision / recall / F1 on the teammate's scenario sets (novel 60; heldout1 56 + heldout2 56 pooled = 112), from stored
answers only (no model call). Same per-case tests as score_scen.py, which is imported unchanged:
  help case: TP when the choice is in the case's `acceptable` list (score_scen.bal "acc" hit), otherwise FN;
  wait case: TN when the choice is not null and not one of score_scen.VISIBLE (score_scen.bal "wait" hit), otherwise FP.
  precision = TP / (TP + FP) (None when TP + FP = 0), recall = TP / (TP + FN), F1 = 2TP / (2TP + FP + FN).
No 1-second fallback. Several runs: metrics per run, then the mean of the per-run values. The held-out pool sums the counts
of heldout1 run i and heldout2 run i (pairing by run number; the other pairings are reported as a sensitivity range).

  python -I score_scen_f1.py [--repro <her repro zip or extracted dir>] [--json-out <file>] [--md-out <file>]

Default --repro: references/team/jiwon_jev_experiment_2026-11-09/jev_touch_experiment_repro.zip, read in memory as data
(nothing of hers is executed or extracted). Our answers: runs/scenarios/<model>__<set>__r<n>/answers.jsonl.
"""
import argparse, importlib.util, itertools, json, math, statistics, sys, zipfile
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
OURS = EVAL / "runs" / "scenarios"
WS = EVAL.parent.parent
REPRO_ZIP = WS / "references" / "team" / "jiwon_jev_experiment_2026-11-09" / "jev_touch_experiment_repro.zip"
PREFIX = "jev_touch_experiment_repro/"

_spec = importlib.util.spec_from_file_location("score_scen", HERE / "score_scen.py")
SS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SS)
VISIBLE = SS.VISIBLE

SETS = ("novel", "heldout1", "heldout2")
ROWS = [("rule", "규칙 기반 판단"), ("jev", "Jev"), ("gpt-4o-mini", "gpt-4o-mini"), ("gpt-5.4-mini", "gpt-5.4-mini"),
        ("gpt-6.1-sol", "gpt-6.1-sol"), ("claude-haiku-5-5", "Haiku 5.5"), ("claude-sonnet-5-5", "Sonnet 5.5")]
OUR_DIR = {"gpt-4o-mini": "gpt-4o-mini-2024-07-18", "gpt-5.4-mini": "gpt-5.4-mini-2026-03-17",
           "claude-haiku-5-5": "claude-haiku-5-5", "claude-sonnet-5-5": "claude-sonnet-5-5"}

# Published balanced accuracies to reproduce first. Sources: novel and held-out per-set values = README.md (scenario sets, stored-answer check) and
# the table there (4 decimals); novel gpt-4o-mini / gpt-5.4-mini = the teammate's recorded values (3 decimals);
# held-out = mean of the two sets, paper 표 5 (3 decimals).
EXP_NOVEL = {"rule": (0.5714, 4), "jev": (0.6317, 4), "gpt-6.1-sol": (0.9382, 4), "gpt-4o-mini": (0.060, 3),
             "gpt-5.4-mini": (0.283, 3), "claude-haiku-5-5": (0.5774, 4), "claude-sonnet-5-5": (0.7708, 4)}
EXP_HO = {"rule": 0.557, "jev": 0.638, "gpt-4o-mini": 0.427, "gpt-5.4-mini": 0.476, "gpt-6.1-sol": 0.842,
          "claude-haiku-5-5": 0.535, "claude-sonnet-5-5": 0.699}
# The teammate's own held-out F1 (paper_metrics.py: TP = help case with any visible support), her recorded values, 4 decimals.
EXP_HER_F1 = {("rule", "heldout1"): 0.5600, ("rule", "heldout2"): 0.5098, ("jev", "heldout1"): 0.7869,
              ("jev", "heldout2"): 0.7101, ("gpt-6.1-sol", "heldout1"): 0.9180, ("gpt-6.1-sol", "heldout2"): 0.8214}


class Repro:
    def __init__(self, p: Path):
        self.p = p
        self.z = zipfile.ZipFile(p) if p.is_file() else None

    def text(self, rel: str) -> str:
        if self.z is not None:
            return self.z.read(PREFIX + rel).decode("utf-8")
        return (self.p / rel).read_text(encoding="utf-8")


def parse(text: str, key: str) -> dict:
    """score_scen.load on a string: last line of a key wins."""
    out = {}
    for l in text.splitlines():
        if l.strip():
            r = json.loads(l)
            out[r[key]] = r["choice"]
    return out


def parse_ho2_probe(text: str) -> dict:
    """score_scen.verify's reading of her explore/runs/ho2_r<i>/probe.jsonl (Jev v0 arm)."""
    a = {}
    for l in text.splitlines():
        r = json.loads(l)
        if r.get("set") == "ho2":
            ch = ((r.get("v0") or {}).get("answers") or {}).get("support_choice") or {}
            a[r["case_id"]] = ch.get("choice") if isinstance(ch, dict) else ch
    return a


def sources(R: Repro):
    """(row, set) -> (list of answer dicts, one per run; source label)."""
    S = {}
    her_novel = {"jev": "jev_NOVEL_SUM", "gpt-4o-mini": "gpt-4o-mini_NOVEL_SUM", "gpt-5.4-mini": "gpt-5.4-mini_NOVEL_SUM",
                 "gpt-6.1-sol": "gpt-6.1-sol_NOVEL_SUM"}
    S[("rule", "novel")] = ([parse(R.text("novel/answers_rule.jsonl"), "window_id")], "hers: novel/answers_rule.jsonl")
    for m, arm in her_novel.items():
        S[(m, "novel")] = ([parse(R.text(f"novel/runs/{arm}_r{i}/answers.jsonl"), "window_id") for i in (1, 2, 3)],
                           f"hers: novel/runs/{arm}_r1..3")
    S[("rule", "heldout1")] = ([parse(R.text("v2/heldout_rule.jsonl"), "window_id")], "hers: v2/heldout_rule.jsonl")
    S[("rule", "heldout2")] = ([parse(R.text("v2/heldout2_rule.jsonl"), "window_id")], "hers: v2/heldout2_rule.jsonl")
    S[("jev", "heldout1")] = ([parse(R.text(f"v2/runs/ho_v0_r{i}/answers.jsonl"), "window_id") for i in (1, 2, 3)],
                              "hers: v2/runs/ho_v0_r1..3")
    S[("jev", "heldout2")] = ([parse_ho2_probe(R.text(f"explore/runs/ho2_r{i}/probe.jsonl")) for i in (1, 2, 3)],
                              "hers: explore/runs/ho2_r1..3/probe.jsonl (v0)")
    S[("gpt-6.1-sol", "heldout1")] = ([parse(R.text("explore/runs/sol_ho1/answers.jsonl"), "window_id")],
                                      "hers: explore/runs/sol_ho1")
    S[("gpt-6.1-sol", "heldout2")] = ([parse(R.text("explore/runs/sol_ho2/answers.jsonl"), "window_id")],
                                      "hers: explore/runs/sol_ho2")
    for m, d in OUR_DIR.items():
        for s in SETS:
            if (m, s) in S:
                continue
            runs = sorted(p for p in OURS.iterdir() if p.is_dir() and p.name.startswith(f"{d}__{s}__r"))
            if not runs:
                S[(m, s)] = ([], "MISSING")
                continue
            S[(m, s)] = ([SS.load(p / "answers.jsonl", "case_id") for p in runs],
                         f"ours: runs/scenarios/{d}__{s}__r1..{len(runs)}")
    return S


def counts(gold: dict, ans: dict) -> dict:
    c = Counter()
    for cid, g in gold.items():
        x = ans.get(cid)
        if cid not in ans:
            c["missing"] += 1
        elif x is None:
            c["null"] += 1
        if g["kind"] == "help":
            if x in g["acceptable"]:
                c["TP"] += 1
            else:
                c["FN"] += 1
                c["FN_visible_not_acceptable" if x in VISIBLE else "FN_no_visible"] += 1
        elif g["kind"] == "wait":
            if x is not None and x not in VISIBLE:
                c["TN"] += 1
            else:
                c["FP"] += 1
                c["FP_null" if x is None else "FP_visible"] += 1
        else:
            raise ValueError(f"unknown kind {g['kind']} in {cid}")
        if x in VISIBLE:
            c["visible_choices"] += 1
        # the teammate's paper_metrics.py detection counts (shown = a visible support), for the side check only
        shown = x is not None and x in VISIBLE
        c[("her_TP" if shown else "her_FN") if g["kind"] == "help" else ("her_FP" if shown else "her_TN")] += 1
    for k in ("TP", "FP", "FN", "TN", "her_TP", "her_FP", "her_FN", "her_TN"):
        c.setdefault(k, 0)
    # agreement with the existing scorer's own function
    b = SS.bal(gold, ans)
    nh = sum(g["kind"] == "help" for g in gold.values())
    nw = sum(g["kind"] == "wait" for g in gold.values())
    assert c["TP"] / nh == b["acc"] and c["TN"] / nw == b["wait"], "per-case counts disagree with score_scen.bal"
    assert c["TP"] + c["FN"] == nh and c["FP"] + c["TN"] == nw
    return dict(c)


def metrics(c: dict) -> dict:
    tp, fp, fn, tn = c["TP"], c["FP"], c["FN"], c["TN"]
    rec = tp / (tp + fn)
    spec = tn / (tn + fp)
    her_p = c["her_TP"] / (c["her_TP"] + c["her_FP"]) if c["her_TP"] + c["her_FP"] else float("nan")
    her_r = c["her_TP"] / (c["her_TP"] + c["her_FN"])
    return {"precision": tp / (tp + fp) if tp + fp else None, "recall": rec,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0, "ba": (rec + spec) / 2,
            "her_f1": 2 * her_p * her_r / (her_p + her_r) if her_p == her_p and her_p + her_r else float("nan")}


def add(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)}


def mean_or_none(v):
    v = [x for x in v]
    if any(x is None for x in v):
        return None if all(x is None for x in v) else ("partial", statistics.mean(x for x in v if x is not None))
    return statistics.mean(v)


def summarise(per_run: list) -> dict:
    ms = [metrics(c) for c in per_run]
    out = {"runs": len(per_run), "per_run_counts": [{k: c[k] for k in ("TP", "FP", "FN", "TN")} for c in per_run],
           "per_run": ms}
    for k in ("precision", "recall", "f1", "ba", "her_f1"):
        out[f"mean_{k}"] = mean_or_none([m[k] for m in ms])
    for k in ("TP", "FP", "FN", "TN", "FN_visible_not_acceptable", "FN_no_visible", "FP_null", "FP_visible", "null",
              "missing", "visible_choices"):
        out[f"mean_{k}"] = statistics.mean(c.get(k, 0) for c in per_run)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repro", type=Path, default=REPRO_ZIP)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--md-out", type=Path)
    a = ap.parse_args()
    R = Repro(a.repro)
    gold = {s: json.loads((OURS / "inputs" / f"{s}_gold.json").read_text(encoding="utf-8")) for s in SETS}
    checks = []
    # input checks: our gold copies and rule copies equal hers
    for s, her in (("novel", "novel/gold.json"), ("heldout1", "heldout/gold.json"), ("heldout2", "heldout2/gold.json")):
        checks.append((f"gold {s} equals her {her}", json.loads(R.text(her)) == gold[s]))
    for s, her in (("novel", "novel/answers_rule.jsonl"), ("heldout1", "v2/heldout_rule.jsonl"),
                   ("heldout2", "v2/heldout2_rule.jsonl")):
        checks.append((f"our inputs/{s}_rule.jsonl choices equal her {her}",
                       SS.load(OURS / "inputs" / f"{s}_rule.jsonl") == parse(R.text(her), "window_id")))
    S = sources(R)
    res = {}
    for m, _ in ROWS:
        res[m] = {}
        for s in SETS:
            runs, src = S[(m, s)]
            if not runs:
                res[m][s] = {"source": src, "runs": 0}
                continue
            res[m][s] = {"source": src, **summarise([counts(gold[s], x) for x in runs])}
            res[m][s]["n"] = len(gold[s])
        c1 = [counts(gold["heldout1"], x) for x in S[(m, "heldout1")][0]]
        c2 = [counts(gold["heldout2"], x) for x in S[(m, "heldout2")][0]]
        if c1 and c2 and len(c1) == len(c2):
            pooled = summarise([add(x, y) for x, y in zip(c1, c2)])
            pooled["source"] = "heldout1 run i + heldout2 run i"
            pooled["n"] = len(gold["heldout1"]) + len(gold["heldout2"])
            pooled["ba_mean_of_two_sets"] = (res[m]["heldout1"]["mean_ba"] + res[m]["heldout2"]["mean_ba"]) / 2
            pooled["f1_mean_of_two_sets"] = (res[m]["heldout1"]["mean_f1"] + res[m]["heldout2"]["mean_f1"]) / 2
            f1s = []
            for perm in itertools.permutations(range(len(c2))):
                f1s.append(statistics.mean(metrics(add(c1[i], c2[j]))["f1"] for i, j in enumerate(perm)))
            pooled["f1_pairing_range"] = (min(f1s), max(f1s))
            pooled["f1_from_summed_counts_all_runs"] = metrics(
                {k: sum(add(x, y)[k] for x, y in zip(c1, c2)) for k in ("TP", "FP", "FN", "TN", "her_TP", "her_FP",
                                                                         "her_FN", "her_TN")})["f1"]
            res[m]["heldout_pooled"] = pooled
        else:
            res[m]["heldout_pooled"] = {"runs": 0, "source": f"cannot pool: runs {len(c1)} / {len(c2)}"}
    # reproduction checks
    for m, (v, d) in EXP_NOVEL.items():
        got = res[m]["novel"]["mean_ba"]
        checks.append((f"novel BA {m}: {got:.4f} vs published {v:.{d}f}", round(got, d) == v))
    for m, v in EXP_HO.items():
        got = res[m]["heldout_pooled"]["ba_mean_of_two_sets"]
        checks.append((f"held-out BA mean of two sets {m}: {got:.4f} vs paper {v:.3f}", round(got, 3) == v))
    for (m, s), v in EXP_HER_F1.items():
        got = res[m][s]["mean_her_f1"]
        checks.append((f"her F1 definition, {s} {m}: {got:.4f} vs her {v:.4f}", round(got, 4) == v))
    for k, s in (("novel", "novel"), ("heldout_pooled", "heldout_pooled")):
        for m, _ in ROWS:
            r = res[m][k]
            tot = r["mean_TP"] + r["mean_FP"] + r["mean_FN"] + r["mean_TN"]
            checks.append((f"{k} {m}: TP+FP+FN+TN = {tot:g} (expected {r['n']})", tot == r["n"]))
    out = {"checks": [{"check": c, "ok": ok} for c, ok in checks], "results": res, "repro": str(a.repro)}
    if a.json_out:
        a.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = render(res, checks, gold)
    if a.md_out:
        a.md_out.write_text(md, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(md)
    return 0 if all(ok for _, ok in checks) else 1


def f3(x):
    if x is None:
        return "–"
    if isinstance(x, tuple):
        return f"{x[1]:.3f}*"
    return f"{x:.3f}"


def g(x):
    return f"{x:g}" if float(x).is_integer() else f"{x:.2f}"


def ranking(res, key, metric):
    vals = [(name, res[m][key][metric]) for m, name in ROWS]
    vals = [(n, (-1 if v is None else v)) for n, v in vals]
    return sorted(vals, key=lambda t: -t[1])


def render(res, checks, gold) -> str:
    L = []
    L.append("### Checks (computed)\n")
    for c, ok in checks:
        L.append(f"- {'OK  ' if ok else 'FAIL'} {c}")
    for key, title, bakeys in (("novel", "규칙 밖 패턴 (novel, 60 cases: help 28, wait 32)", ("mean_ba",)),
                               ("heldout_pooled", "평가 시나리오 (heldout1 + heldout2 pooled, 112 cases: help 60, wait 52)",
                                ("mean_ba", "ba_mean_of_two_sets"))):
        L.append(f"\n### {title}\n")
        hdr = "| Row | Runs | TP | FP | FN | TN | Precision | Recall | F1 |"
        sep = "|---|---|---|---|---|---|---|---|---|"
        if key == "novel":
            hdr += " BA (mean of runs) | Per-run F1 | Source |"
            sep += "---|---|---|"
        else:
            hdr += " BA pooled 112 | BA mean of 2 sets | Per-run F1 | F1 range over run pairings | Source |"
            sep += "---|---|---|---|---|"
        L += [hdr, sep]
        for m, name in ROWS:
            r = res[m][key]
            row = (f"| {name} | {r['runs']} | {g(r['mean_TP'])} | {g(r['mean_FP'])} | {g(r['mean_FN'])} | {g(r['mean_TN'])} | "
                   f"{f3(r['mean_precision'])} | {f3(r['mean_recall'])} | {f3(r['mean_f1'])} | {f3(r['mean_ba'])} | ")
            if key != "novel":
                row += f"{f3(r['ba_mean_of_two_sets'])} | "
            row += " / ".join(f"{x['f1']:.3f}" for x in r["per_run"]) + " | "
            if key != "novel":
                lo, hi = r["f1_pairing_range"]
                row += (f"{lo:.4f}–{hi:.4f} | " if r["runs"] > 1 else "– | ")
                row += f"{res[m]['heldout1']['source']}; {res[m]['heldout2']['source']} |"
            else:
                row += f"{r['source']} |"
            L.append(row)
        L.append("\nTP/FP/FN/TN are means over the runs when a row has several runs (non-integer values come from that).")
        L.append("\nError make-up (means over runs): FN split into 'visible support not in acceptable' / 'no visible support';"
                 " FP split into 'visible support' / 'null answer'; null and missing answers over all cases; visible choices"
                 " over all cases.\n")
        L.append("| Row | FN wrong visible | FN no visible | FP visible | FP null | Null answers | Missing cases |"
                 " Visible choices / n |")
        L.append("|---|---|---|---|---|---|---|---|")
        for m, name in ROWS:
            r = res[m][key]
            L.append(f"| {name} | {g(r['mean_FN_visible_not_acceptable'])} | {g(r['mean_FN_no_visible'])} | "
                     f"{g(r['mean_FP_visible'])} | {g(r['mean_FP_null'])} | {g(r['mean_null'])} | {g(r['mean_missing'])} | "
                     f"{g(r['mean_visible_choices'])} / {r['n']} |")
    L.append("\n### Held-out sets separately (supplement; mean of per-run values)\n")
    L.append("| Row | heldout1 TP/FP/FN/TN | heldout1 P / R / F1 | heldout2 TP/FP/FN/TN | heldout2 P / R / F1 |"
             " F1 mean of 2 sets | F1 pooled 112 |")
    L.append("|---|---|---|---|---|---|---|")
    for m, name in ROWS:
        h1, h2 = res[m]["heldout1"], res[m]["heldout2"]
        cell = lambda r: "/".join(g(r[f"mean_{k}"]) for k in ("TP", "FP", "FN", "TN"))
        prf = lambda r: f"{f3(r['mean_precision'])} / {f3(r['mean_recall'])} / {f3(r['mean_f1'])}"
        L.append(f"| {name} | {cell(h1)} | {prf(h1)} | {cell(h2)} | {prf(h2)} | "
                 f"{(h1['mean_f1'] + h2['mean_f1']) / 2:.3f} | {f3(res[m]['heldout_pooled']['mean_f1'])} |")
    L.append("\n### Paper-ready values (three decimals; mean of per-run values)\n")
    L.append("| 판단 모델 | 규칙 밖 패턴 F1 | 평가 시나리오 F1 |")
    L.append("|---|---|---|")
    for m, name in ROWS:
        L.append(f"| {name} | {f3(res[m]['novel']['mean_f1'])} | {f3(res[m]['heldout_pooled']['mean_f1'])} |")
    L.append("\n| 판단 모델 | 규칙 밖 패턴 정밀도 | 규칙 밖 패턴 재현율 | 평가 시나리오 정밀도 | 평가 시나리오 재현율 |")
    L.append("|---|---|---|---|---|")
    for m, name in ROWS:
        a, b = res[m]["novel"], res[m]["heldout_pooled"]
        L.append(f"| {name} | {f3(a['mean_precision'])} | {f3(a['mean_recall'])} | {f3(b['mean_precision'])} | "
                 f"{f3(b['mean_recall'])} |")
    L.append("\n### For comparison only: detection F1 with the teammate's rule (paper_metrics.py: TP = help case with any"
             " visible support, FP = wait case with a visible support; mean of per-run values)\n")
    L.append("| 판단 모델 | 규칙 밖 패턴 detection F1 | 평가 시나리오 detection F1 (pooled 112) |")
    L.append("|---|---|---|")
    for m, name in ROWS:
        L.append(f"| {name} | {f3(res[m]['novel']['mean_her_f1'])} | {f3(res[m]['heldout_pooled']['mean_her_f1'])} |")
    L.append("\n### Rankings (high to low)\n")
    for key, label, bak in (("novel", "규칙 밖 패턴", "mean_ba"), ("heldout_pooled", "평가 시나리오", "ba_mean_of_two_sets")):
        rb = ranking(res, key, bak)
        rf = ranking(res, key, "mean_f1")
        L.append(f"- {label}, balanced accuracy ({'mean of runs' if key == 'novel' else 'mean of the two sets, as in 표 5'}): "
                 + " > ".join(f"{n} {v:.3f}" for n, v in rb))
        if key != "novel":
            rp = ranking(res, key, "mean_ba")
            L.append(f"- {label}, balanced accuracy pooled over 112: " + " > ".join(f"{n} {v:.3f}" for n, v in rp))
        L.append(f"- {label}, F1{' (pooled 112)' if key != 'novel' else ''}: " + " > ".join(f"{n} {v:.3f}" for n, v in rf))
        if key != "novel":
            L.append(f"- {label}, F1 mean of the two sets (supplement): "
                     + " > ".join(f"{n} {v:.3f}" for n, v in ranking(res, key, "f1_mean_of_two_sets")))
        pos_b = {n: i + 1 for i, (n, _) in enumerate(rb)}
        pos_f = {n: i + 1 for i, (n, _) in enumerate(rf)}
        moved = [f"{n} {pos_b[n]}→{pos_f[n]}" for _, n in ROWS if pos_b[n] != pos_f[n]]
        L.append(f"- {label}, rank changes BA→F1: " + (", ".join(moved) if moved else "none"))
        rule_b = res["rule"][key][bak]
        rule_f = res["rule"][key]["mean_f1"]
        above_b = [n for m, n in ROWS if m != "rule" and res[m][key][bak] > rule_b]
        above_f = [n for m, n in ROWS if m != "rule" and res[m][key]["mean_f1"] > rule_f]
        L.append(f"- {label}, rows above the rule table: BA {', '.join(above_b) or 'none'}; F1 {', '.join(above_f) or 'none'}")
    L.append("\n### 3.4 statements under F1\n")
    for m, name in (("gpt-6.1-sol", "gpt-6.1-sol"), ("claude-sonnet-5-5", "Sonnet 5.5"), ("jev", "Jev")):
        for key, label in (("novel", "규칙 밖 패턴"), ("heldout_pooled", "평가 시나리오")):
            fm, fr = res[m][key]["mean_f1"], res["rule"][key]["mean_f1"]
            L.append(f"- {name} F1 > rule F1 on {label}: {fm > fr} ({fm:.3f} vs {fr:.3f})")
    L.append("\n### Reference policies (built from the gold labels, not models)\n")
    L.append("'Always intervene, right support' = an acceptable support on every help case and a visible support on every"
             " wait case (the most an always-intervening policy can get); 'always <support>' = that one visible support on"
             " every case (the best of the 7 visible supports per set is listed); 'always none' = `none` on every case.\n")
    L.append("| Policy | Set | TP | FP | FN | TN | Precision | Recall | F1 | BA |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    vis0 = sorted(VISIBLE)[0]

    def pol_counts(s, pol):
        if pol == "right":
            ans = {cid: (gg["acceptable"][0] if gg["kind"] == "help" else vis0) for cid, gg in gold[s].items()}
        else:
            ans = {cid: pol for cid in gold[s]}
        return counts(gold[s], ans)

    def row(pname, label, c):
        mt = metrics(c)
        L.append(f"| {pname} | {label} | {c['TP']} | {c['FP']} | {c['FN']} | {c['TN']} | {f3(mt['precision'])} | "
                 f"{f3(mt['recall'])} | {f3(mt['f1'])} | {f3(mt['ba'])} |")

    for label, ss in (("규칙 밖 패턴", ("novel",)), ("평가 시나리오 (pooled)", ("heldout1", "heldout2"))):
        tot = lambda pol: (lambda cs: cs[0] if len(cs) == 1 else add(cs[0], cs[1]))([pol_counts(s, pol) for s in ss])
        row("always intervene, right support", label, tot("right"))
        best = max(sorted(VISIBLE), key=lambda v: metrics(tot(v))["f1"])
        row(f"always {best} (best single support)", label, tot(best))
        row("always none", label, tot("none"))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
