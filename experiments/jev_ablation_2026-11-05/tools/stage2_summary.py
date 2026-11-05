"""Key numbers of the E5 stage-2 result set, read from the labels_<version>/<run>/metrics.json files (no API call):
allowed-action rate with chance, designated delivery, segment 2x2, the withdrawn-rule reproduction, J's out-of-filter
rate, GT-tag deltas (A_GT / C_GT against A / C on the same bundle), state AUROCs against raw-feature baselines.

  python -B stage2_summary.py [--set results] [--labels v4] > summary.txt

In this package --set results gives results/stage2_summary_v4.txt again, except one clause of the stage-1 line of the
version comparison (the held-history count), which needs the superseded 0114ed1 set's run files (not shipped).
"""

import argparse
import json
from pathlib import Path

E5 = Path(__file__).resolve().parent.parent      # the package folder (experiments/jev_ablation_2026-11-05)


def load(root: Path, ver: str, run: str):
    p = root / f"labels_{ver}" / run / "metrics.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def kn(d):
    if not d or not d.get("n"):
        return "-"
    ci = d.get("ci95")
    return f"{d['k']}/{d['n']}" + (f" [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "")


def kk(d):
    return "-" if not d or d.get("n") is None else f"{d['k']}/{d['n']}"


def seg(s):
    cov = f", no-row exact delivery {kk(s['designated_delivery_no_row'])}" if s.get("designated_delivery_no_row", {}).get("n")         else ""
    return f"TP/FN/FP/TN {s['TP']}/{s['FN']}/{s['FP']}/{s['TN']}, delivery {kn(s.get('designated_delivery_v0_row'))}{cov}"


TABLE = [   # Codex 209 #5 / main: the common segment population; (input, policy, run, arm, kind)
    ("b0_r0", "A", "stage2_1_swap_C_C0", "A", "a"),
    ("b0_r0", "A + withdrawn rule", "stage2_1_swap_C_C0", None, "withdrawn"),
    ("b0_r0", "C", "stage2_1_swap_C_C0", "C", "c"),
    ("b0_r0", "C0", "stage2_1_swap_C_C0", "C0", "c"),
    ("b0_r0", "C:nohistory", "stage2_2_C_nohistory", "C:nohistory", "c"),
    ("b0_r0", "J", "stage2_3_J_b0_r0", "J", "c"),
    ("b0_rA", "A", "stage2_4a_b0_rA", "A", "a"),
    ("b0_rA", "C", "stage2_4a_b0_rA", "C", "c"),
    ("b2_rA", "A", "stage2_4b_b2_rA", "A", "a"),
    ("b2_rA", "C", "stage2_4b_b2_rA", "C", "c"),
    ("reference tags, b0_r0", "A_GT", "stage2_5_GT_b0_r0", "A", "a"),
    ("reference tags, b0_r0", "C_GT", "stage2_5_GT_b0_r0", "C", "c"),
]


def segments_of(m, arm, kind):
    se = m.get("selection") or {}
    if kind == "a":
        return (se.get("A") or {}).get("segments")
    if kind == "withdrawn":
        return (m.get("baselines") or {}).get("segments_decline_if_withdrawn")
    return (se.get(arm) or {}).get("segments_with_rule_fallback")


def main_table(root, ver):
    rows = ["| Input | Policy | TP/FN | FP/TN | Exact designated delivery | Camera TP/n · delivery | Touch S3 TP/n · delivery "
            "| Opened before onset | Old rule TP/FN · delivery | No-row exact delivery |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for inp, pol, run, arm, kind in TABLE:
        m = load(root, ver, run)
        sg = segments_of(m, arm, kind) if m else None
        if not sg:
            rows.append(f"| {inp} | {pol} | - | - | - | - | - | - | - | - |")
            continue
        o = sg.get("by_origin") or {}
        org = lambda k: (f"{o[k]['TP']}/{o[k]['designated_v0_row']} · {o[k]['designated_delivery']['k']}/"
                         f"{o[k]['designated_delivery']['n']}") if k in o else "-"
        od = sg.get("old_definition") or {}
        rows.append(f"| {inp} | {pol} | {sg['TP']}/{sg['FN']} | {sg['FP']}/{sg['TN']} | {kk(sg['designated_delivery_v0_row'])} "
                    f"| {org('camera')} | {org('touch')} | {sg['help_opened_before_onset']['segments']} "
                    f"(lead {sg['help_opened_before_onset']['lead_s']}) | {od.get('TP')}/{od.get('FN')} · "
                    f"{od.get('designated_delivery_v0_row', {}).get('k')}/{od.get('designated_delivery_v0_row', {}).get('n')} "
                    f"| {kk(sg['designated_delivery_no_row'])} |")
    return rows


def selection_lines(name, m):
    out = []
    se = m.get("selection") or {}
    A = se.get("A")
    if A:
        out.append(f"{name} A: allowed {kn(A['allowed']['with_candidates'])} (chance {A['chance_allowed']['with_candidates']:.3f}"
                   f" on windows with candidates); {seg(A['segments'])}" if A['chance_allowed']['with_candidates'] is not None
                   else f"{name} A: {seg(A['segments'])}")
    bl = m.get("baselines") or {}
    if bl.get("windows"):
        out.append(f"{name} baselines (windows with candidates {bl['windows']}): always-none {kn(bl['always_none'])}, "
                   f"always-candidate {kn(bl['always_candidate'])}, decline-if-withdrawn {kn(bl['decline_if_withdrawn'])}")
    for arm, s in se.items():
        if arm in ("A", "windows_scored", "singleton_none_windows"):
            continue
        fo, oa = s["first_order"], s["order_agreed"]
        line = (f"{name} {arm}: answered allowed {kn(fo['allowed_answered'])} (chance {fo['chance_on_answered']}); "
                f"order-agreed {kn(oa['allowed_answered'])}; order consistency {kn(s['order_consistency'])}; "
                f"{seg(s['segments_with_rule_fallback'])}")
        dp = s.get("decline_profile") or {}
        if dp.get("windows"):
            line += (f"; declines {dp['declines']}/{dp['windows']}, withdrawn-rule reproduction "
                     f"{kn(dp['withdrawn_rule_reproduction'])}, declined when withdrawn {kn(dp['declined_when_withdrawn'])}, "
                     f"when fresh {kn(dp['declined_when_fresh'])}, admissible {dp['admissible_actual']} vs random-decline "
                     f"{dp['admissible_expected_random_decline']:.1f}")
        if "out_of_filter_choice" in s:
            line += f"; out-of-filter choices {kn(s['out_of_filter_choice'])}, reference absent {kn(s['reference_absent'])}"
        out.append(line)
    return out


def state_lines(name, m):
    out = []
    for arm, per in (m.get("state_estimation") or {}).items():
        parts = []
        for q, v in per.items():
            if not v.get("n"):
                continue
            raw = v.get("raw_feature_auroc") or {}
            best = max(((k, x["auroc"]) for k, x in raw.items() if x.get("auroc") is not None), key=lambda t: t[1],
                       default=(None, None))
            au = "undef" if v.get("auroc") is None else f"{v['auroc']:.3f}"
            sk = "-" if v.get("brier_skill") is None else f"{v['brier_skill']:+.2f}"
            paired = ", ".join(f"{k} {x['auroc']:.3f} vs Jev {x['jev_auroc_same_windows']:.3f} (n {x['n']})"
                               for k, x in raw.items() if x.get("auroc") is not None
                               and x.get("jev_auroc_same_windows") is not None)
            parts.append(f"{q} AUROC {au} (n {v['n']}/{v['positives']}+; paired on shared windows: {paired or '-'}), "
                         f"skill {sk}")
        if parts:
            out.append(f"{name} {arm}: " + "; ".join(parts))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", default=str(E5 / "results"), help="a folder with labels_<version>/<run>/metrics.json")
    ap.add_argument("--labels", default="v4")
    args = ap.parse_args()
    root = Path(args.set)
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8")) if (root / "manifest.json").is_file() else {}
    print(f"manifest {man.get('manifest_id')}, labels {args.labels}")
    first = load(root, args.labels, "stage2_1_swap_C_C0") or {}
    print(f"scoring {first.get('scoring_version')}")
    print("help rule: " + (((first.get("selection") or {}).get("A") or {}).get("segments") or {}).get("help_rule", "-"))
    print("== main table (common segment population; B / D and window-level diagnostics outside it)")
    for line in main_table(root, args.labels):
        print(line)
    runs = sorted(d.name for d in (root / f"labels_{args.labels}").iterdir() if (d / "metrics.json").is_file())
    for run in runs:
        m = load(root, args.labels, run)
        print(f"== {run} ({(m.get('scored_population') or {}).get('windows')} scored windows; order swap valid "
              f"{m['order_swap']['valid']})")
        for line in selection_lines(run, m) + state_lines(run, m):
            print(line)
    gt, base = load(root, args.labels, "stage2_5_GT_b0_r0"), load(root, args.labels, "stage2_1_swap_C_C0")
    if gt and base:
        print("== GT-tag deltas (verified tags minus replay tags, b0_r0)")
        for arm in ("A", "C"):
            g, b = gt["selection"].get(arm), base["selection"].get(arm)
            if not g or not b:
                continue
            gs = g["segments"] if arm == "A" else g["segments_with_rule_fallback"]
            bs = b["segments"] if arm == "A" else b["segments_with_rule_fallback"]
            print(f"{arm}_GT vs {arm}: TP {gs['TP']}-{bs['TP']}, FN {gs['FN']}-{bs['FN']}, FP {gs['FP']}-{bs['FP']}, "
                  f"TN {gs['TN']}-{bs['TN']}; delivery {kn(gs.get('designated_delivery_v0_row'))} vs "
                  f"{kn(bs.get('designated_delivery_v0_row'))}")
    for line in version_lines(root, man):
        print(line)
    return 0


def held_history(old_run: Path, new_run: Path) -> tuple[int, int]:
    """Same-input windows whose rule decision differs between the sets: how many, and how many of them carry another
    held support and follow an earlier window of the same take whose inputs differ (session history, not the code)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from compare_versions import read_jsonl, same_input
    ro = {(r["take"], r["i"]): r for r in read_jsonl(old_run / "rule_windows.jsonl")}
    rn = {(r["take"], r["i"]): r for r in read_jsonl(new_run / "rule_windows.jsonl")}
    n = hist = 0
    for (take, i), b in rn.items():
        a = ro.get((take, i))
        if a is None or not same_input(a, b):
            continue
        if (a["rule"]["transition"], a["rule"]["support"]) == (b["rule"]["transition"], b["rule"]["support"]):
            continue
        n += 1
        earlier = any((take, j) in ro and (take, j) in rn and not same_input(ro[(take, j)], rn[(take, j)]) for j in range(i))
        hist += earlier and a.get("held_before") != b.get("held_before")
    return n, hist


def version_lines(root: Path, man: dict) -> list:
    """The code-version comparison (version_comparison.json of compare_versions.py), so the numbers above carry it."""
    p = root / "version_comparison.json"
    if not p.is_file():
        return []
    vc = json.loads(p.read_text(encoding="utf-8"))
    old = Path((man.get("supersedes") or {}).get("path") or "")
    if not old.is_absolute():
        old = E5 / old
    commits = next(iter(vc.values())).get("commits") or ["?", "?"]
    out = [f"== version comparison ({p.name}, tools/compare_versions.py): PR #77 {commits[0][:7]} -> {commits[1][:7]}, "
           f"model {(man.get('model') or {}).get('setting_default')} in both; requests and answers are compared on windows "
           "whose rule inputs are identical in both sets"]
    for run, r in vc.items():
        line = (f"{run}: windows {r['windows_new']}, same inputs {r['windows_compared']}; rule decisions differ "
                f"{r['decisions_differ']}, allowed-candidate lists differ {r['candidate_lists_differ']}")
        if r["inputs_differ"]:
            line += (f"; NOT a clean version comparison: {r['inputs_differ']} windows have other rule inputs (input drift "
                     f"between the two runs' E3 inputs, not a code effect) and are left out")
            if r["decisions_differ"] and (old / run).is_dir():
                n, hist = held_history(old / run, root / run)
                line += (f"; of the {n} same-input windows with another decision, {hist} carry another held support "
                         f"after an earlier window of the same take with other inputs (session history)")
        out.append(line)
        for k, d in r["arms"].items():
            dup = d.get("identical_request_other_answer", 0)
            out.append(f"   {k}: asked in both {d.get('both', 0)}, identical requests {d.get('identical_request', 0)}"
                       + (f" (another answer {dup}: duplicate answers in the old cache)" if dup else "") +
                       f", changed requests {d.get('request_changed', 0)} (answer changed {d.get('answer_changed', 0)}), "
                       f"asked only in the old set {d.get('only_old', 0)}, only in the new set {d.get('only_new', 0)}")
    j = {run: (r["arms"].get("J / support_choice") or {}) for run, r in vc.items() if "J / support_choice" in r["arms"]}
    if j:
        out.append("J (code-version effect): requests changed " + ", ".join(
            f"{run} {d.get('request_changed', 0)}/{d.get('both', 0)}" for run, d in j.items()) + "; answers changed " +
            ", ".join(f"{run} {d.get('answer_changed', 0)}" for run, d in j.items()) +
            ". Every J request changed because its 3-2 wait option text now comes from the PR's rule_table.WHAT "
            "(run_jev_ablation.py supplied WAIT_WHAT while WHAT had no 3-2 line).")
    c = {run: (r["arms"].get("C / support_choice") or {}) for run, r in vc.items()
         if "C / support_choice" in r["arms"] and not r["inputs_differ"]}
    if c:
        out.append("C choices changed: " + ", ".join(f"{run} {d.get('answer_changed', 0)}/{d.get('both', 0)} (requests "
                   f"changed {d.get('request_changed', 0)}, no longer asked {d.get('only_old', 0)})" for run, d in c.items()))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
