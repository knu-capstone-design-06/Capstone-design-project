"""Metrics that also credit correct waiting, on the teammate's scenario sets (novel 60; heldout1 + heldout2 pooled 112),
from stored answers only. Case outcomes (TP / FP / FN / TN) come unchanged from score_scen_f1.py (which takes its tests
from score_scen.py); runs, pooling and run means as there (metrics per run, then the mean of the per-run values).

Per run, from TP, FP, FN, TN (n = their sum):
  help class:  precision = TP/(TP+FP), recall = TP/(TP+FN), F1_help = 2TP/(2TP+FP+FN)
  wait class (positive = a correct wait): precision_wait = TN/(TN+FN), recall_wait = specificity = TN/(TN+FP),
               F1_wait = 2TN/(2TN+FN+FP)
  macro-F1 = (F1_help + F1_wait) / 2   (scikit-learn f1_score(average='macro'): unweighted mean of the per-class F1)
  accuracy = (TP+TN)/n; balanced accuracy = (recall + specificity)/2;
  MCC = (TP*TN - FP*FN) / sqrt((TP+FP)(TP+FN)(TN+FP)(TN+FN))
A ratio whose denominator is 0 is undefined and printed "–" (no substitute value).

  python -I score_scen_f1_macro.py [--repro <her repro zip or extracted dir>] [--json-out <file>] [--md-out <file>]
"""
import argparse, importlib.util, json, math, statistics, sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("score_scen_f1", HERE / "score_scen_f1.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

METRICS = ("f1_help", "precision", "recall", "f1_wait", "precision_wait", "specificity", "macro_f1", "accuracy", "ba",
           "mcc")
LABEL = {"f1_help": "F1 (help)", "precision": "Precision", "recall": "Recall", "f1_wait": "F1 (wait)",
         "precision_wait": "Precision (wait)", "specificity": "Specificity", "macro_f1": "Macro-F1",
         "accuracy": "Accuracy", "ba": "Balanced acc.", "mcc": "MCC"}


def cm_metrics(tp, fp, fn, tn) -> dict:
    div = lambda a, b: a / b if b else None
    n = tp + fp + fn + tn
    f1h = div(2 * tp, 2 * tp + fp + fn)
    f1w = div(2 * tn, 2 * tn + fn + fp)
    rec, spec = div(tp, tp + fn), div(tn, tn + fp)
    d = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {"f1_help": f1h, "precision": div(tp, tp + fp), "recall": rec, "f1_wait": f1w,
            "precision_wait": div(tn, tn + fn), "specificity": spec,
            "macro_f1": None if f1h is None or f1w is None else (f1h + f1w) / 2, "accuracy": div(tp + tn, n),
            "ba": None if rec is None or spec is None else (rec + spec) / 2, "mcc": div(tp * tn - fp * fn, d)}


def run_mean(ms: list) -> dict:
    out = {}
    for k in METRICS:
        v = [m[k] for m in ms]
        out[k] = None if any(x is None for x in v) else statistics.mean(v)
        out[f"{k}_undefined_runs"] = sum(x is None for x in v)
    return out


def f3(x):
    return "–" if x is None else f"{x:.3f}"


def ranks(vals: dict) -> dict:
    """Competition ranking (1 = best; equal values share a rank; undefined last)."""
    key = lambda v: -1e9 if v is None else round(v, 12)
    return {n: 1 + sum(key(w) > key(v) for w in vals.values()) for n, v in vals.items()}


def order_report(L, title, rows: dict, metrics=("f1_help", "macro_f1", "ba")):
    """rows: name -> metric dict. Prints the order per metric and the rank changes."""
    rk = {m: ranks({n: r[m] for n, r in rows.items()}) for m in metrics}
    for m in metrics:
        srt = sorted(rows, key=lambda n: (rk[m][n], list(rows).index(n)))
        s = f"{srt[0]} {f3(rows[srt[0]][m])}"
        for p, n in zip(srt, srt[1:]):
            s += f" {'=' if rk[m][p] == rk[m][n] else '>'} {n} {f3(rows[n][m])}"
        L.append(f"- {title}, {LABEL[m]}: {s}")
    for a, b in ((metrics[0], metrics[1]), (metrics[1], metrics[2]), (metrics[0], metrics[2])):
        moved = [f"{n} {rk[a][n]}→{rk[b][n]}" for n in rows if rk[a][n] != rk[b][n]]
        L.append(f"- {title}, rank changes {LABEL[a]} → {LABEL[b]}: " + (", ".join(moved) if moved else "none"))


def extremes(L, title, rows: dict, metrics=METRICS):
    hits = []
    for n, r in rows.items():
        for m in metrics:
            v = r[m]
            if v is not None and f3(v) in ("0.000", "1.000"):
                hits.append(f"{n} {LABEL[m]} {f3(v)}{'' if v in (0, 1) else ' (rounded)'}")
    L.append(f"- {title}: " + ("; ".join(hits) if hits else "none"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repro", type=Path, default=F.REPRO_ZIP)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--md-out", type=Path)
    a = ap.parse_args()
    R = F.Repro(a.repro)
    gold = {s: json.loads((F.OURS / "inputs" / f"{s}_gold.json").read_text(encoding="utf-8")) for s in F.SETS}
    S = F.sources(R)
    res, checks = {}, []
    for m, name in F.ROWS:
        cn = [F.counts(gold["novel"], x) for x in S[(m, "novel")][0]]
        c1 = [F.counts(gold["heldout1"], x) for x in S[(m, "heldout1")][0]]
        c2 = [F.counts(gold["heldout2"], x) for x in S[(m, "heldout2")][0]]
        assert cn and c1 and len(c1) == len(c2), f"missing runs for {m}"
        pooled = [F.add(x, y) for x, y in zip(c1, c2)]
        res[name] = {}
        for key, cs in (("novel", cn), ("heldout_pooled", pooled)):
            ms = [cm_metrics(c["TP"], c["FP"], c["FN"], c["TN"]) for c in cs]
            res[name][key] = {"runs": len(cs), **run_mean(ms), "per_run": ms,
                              "per_run_counts": [{k: c[k] for k in ("TP", "FP", "FN", "TN")} for c in cs]}
            # agreement with score_scen_f1's own F1 / precision / recall / BA (same counts, same run means)
            old = [F.metrics(c) for c in cs]
            for k_new, k_old in (("f1_help", "f1"), ("recall", "recall"), ("ba", "ba"), ("precision", "precision")):
                o = [x[k_old] for x in old]
                if any(v is None for v in o):
                    continue
                checks.append((f"{key} {name} {k_new} equals score_scen_f1 ({statistics.mean(o):.4f})",
                               math.isclose(statistics.mean(o), res[name][key][k_new], abs_tol=1e-12)))
    # trivial references, built from the gold labels
    vis0 = sorted(F.VISIBLE)[0]

    def pol(s, p):
        if p == "right":
            ans = {cid: (g["acceptable"][0] if g["kind"] == "help" else vis0) for cid, g in gold[s].items()}
        else:
            ans = {cid: p for cid in gold[s]}
        return F.counts(gold[s], ans)

    refs = {}
    for key, ss in (("novel", ("novel",)), ("heldout_pooled", ("heldout1", "heldout2"))):
        tot = lambda p: pol(ss[0], p) if len(ss) == 1 else F.add(pol(ss[0], p), pol(ss[1], p))
        best = max(sorted(F.VISIBLE), key=lambda v: (lambda c: cm_metrics(c["TP"], c["FP"], c["FN"], c["TN"])
                                                     ["macro_f1"] or -1)(tot(v)))
        for pname, p in (("never intervene (always none)", "none"), ("always intervene, right support", "right"),
                         (f"always {best} (best single support by macro-F1)", best)):
            c = tot(p)
            refs[(key, pname)] = ({k: c[k] for k in ("TP", "FP", "FN", "TN")}, cm_metrics(c["TP"], c["FP"], c["FN"], c["TN"]))
    md = render(res, refs, checks)
    if a.json_out:
        a.json_out.write_text(json.dumps({"results": res, "refs": {f"{k[0]} | {k[1]}": v for k, v in refs.items()},
                                          "checks": [{"check": c, "ok": ok} for c, ok in checks]},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    if a.md_out:
        a.md_out.write_text(md, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(md)
    return 0 if all(ok for _, ok in checks) else 1


def render(res, refs, checks) -> str:
    L = ["#### Scenario sets: checks (computed)\n"]
    L.append(f"- {sum(ok for _, ok in checks)} of {len(checks)} OK: F1 (help), precision, recall and balanced accuracy equal"
             " score_scen_f1.py's values for every row and set" + ("" if all(ok for _, ok in checks) else
                                                                    "; FAILED: " + "; ".join(c for c, ok in checks if not ok)))
    for key, title in (("novel", "규칙 밖 패턴 (60: help 28, wait 32)"),
                       ("heldout_pooled", "평가 시나리오 (pooled 112: help 60, wait 52)")):
        L.append(f"\n#### 표 5 candidates, {title}: all metrics (mean of per-run values)\n")
        L.append("| 판단 모델 | Runs | TP | FP | FN | TN | " + " | ".join(LABEL[m] for m in METRICS) + " |")
        L.append("|---|---|---|---|---|---|" + "---|" * len(METRICS))
        for name, r in res.items():
            rr = r[key]
            mc = {k: statistics.mean(c[k] for c in rr["per_run_counts"]) for k in ("TP", "FP", "FN", "TN")}
            L.append(f"| {name} | {rr['runs']} | " + " | ".join(F.g(mc[k]) for k in ("TP", "FP", "FN", "TN")) + " | "
                     + " | ".join(f3(rr[m]) for m in METRICS) + " |")
    L.append("\n#### 표 5 paper-ready (three decimals)\n")
    L.append("| 판단 모델 | 규칙 밖 패턴 F1 | 규칙 밖 패턴 macro-F1 | 규칙 밖 패턴 특이도 | 평가 시나리오 F1 | 평가 시나리오 macro-F1 |"
             " 평가 시나리오 특이도 |")
    L.append("|---|---|---|---|---|---|---|")
    for name, r in res.items():
        a, b = r["novel"], r["heldout_pooled"]
        L.append(f"| {name} | {f3(a['f1_help'])} | {f3(a['macro_f1'])} | {f3(a['specificity'])} | {f3(b['f1_help'])} | "
                 f"{f3(b['macro_f1'])} | {f3(b['specificity'])} |")
    L.append("\n#### Scenario sets: trivial references (built from the gold labels)\n")
    L.append("| Set | Policy | TP | FP | FN | TN | " + " | ".join(LABEL[m] for m in METRICS) + " |")
    L.append("|---|---|---|---|---|---|" + "---|" * len(METRICS))
    for (key, pname), (c, mt) in refs.items():
        L.append(f"| {'규칙 밖 패턴' if key == 'novel' else '평가 시나리오 (pooled)'} | {pname} | {c['TP']} | {c['FP']} | "
                 f"{c['FN']} | {c['TN']} | " + " | ".join(f3(mt[m]) for m in METRICS) + " |")
    L.append("\n#### Scenario sets: orders\n")
    for key, title in (("novel", "규칙 밖 패턴"), ("heldout_pooled", "평가 시나리오")):
        order_report(L, title, {n: r[key] for n, r in res.items()})
    L.append("\n#### Scenario sets: check (c)\n")
    rule = "규칙 기반 판단"
    for key, title in (("novel", "규칙 밖 패턴"), ("heldout_pooled", "평가 시나리오")):
        rv = res[rule][key]["macro_f1"]
        for n in ("Jev", "gpt-6.1-sol", "Sonnet 5.5", "gpt-5.4-mini"):
            v = res[n][key]["macro_f1"]
            L.append(f"- {title}: {n} macro-F1 {f3(v)} {'>' if v > rv else '<=' } rule {f3(rv)}")
        rk = ranks({n: r[key]["macro_f1"] for n, r in res.items()})
        L.append(f"- {title}: gpt-5.4-mini macro-F1 rank {rk['gpt-5.4-mini']} of {len(rk)}")
        floor = refs[(key, "never intervene (always none)")][1]["macro_f1"]
        ceil = refs[(key, "always intervene, right support")][1]["macro_f1"]
        L.append(f"- {title}: rows with macro-F1 below the never-intervene reference ({f3(floor)}): "
                 + (", ".join(f"{n} {f3(r[key]['macro_f1'])}" for n, r in res.items() if r[key]["macro_f1"] < floor) or "none")
                 + f"; below the always-intervene ceiling ({f3(ceil)}): "
                 + (", ".join(n for n, r in res.items() if r[key]["macro_f1"] < ceil) or "none"))
    L.append("\n#### Scenario sets: cells at 0.000 or 1.000 (three decimals; 'rounded' = not exactly 0 or 1)\n")
    for key, title in (("novel", "규칙 밖 패턴"), ("heldout_pooled", "평가 시나리오")):
        extremes(L, title, {n: r[key] for n, r in res.items()})
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
