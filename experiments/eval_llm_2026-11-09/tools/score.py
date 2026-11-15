"""Score one arm's answers of the LLM evaluation kit in the columns of the judgment table
(experiments/eval_jev_raw_2026-11-08/results/judgment_E12.csv).

  python score.py --kit <kit> --data <kit>/data/E5_J.jsonl --answers my_answers.jsonl [--name "my model"]
                  [--cells-out cells.csv]
  python score.py --kit <kit> --rule-table     # the rule table's own row (no answers needed)
  python score.py --kit <kit> --check          # rescore reference_answers/ and compare with the recorded rows

<kit> = the evaluation kit folder (data/, labels/, reference_answers/).

Answers file: JSON lines {"window_id": "...", "choice": "<one option of that window>" | null}; other keys are
ignored, and the last line of a window counts. Python 3.8+, standard library only.

The scoring is the one of E5 / E12 (E5 tools/metrics.py segment_outcomes with E3 tools/help_rule.py, labels v5):
  cell      = a label segment (one turn of a clip) x one synthetic touch condition; windows of clip 20261028_165108
              are left out (recorded at 1x zoom, out of every evaluation), and so are cells the labels mark
              contradictory;
  selection = per window: the answer when the window was asked and the answer is one of its options; the rule
              table's own decision when an asked window has no valid answer (E5: failed call) or the window was not
              measurable (E5: not asked; the rule table opens nothing there); 'none' when a measurable window is not
              in the data file (E5_C0 / E5_C: no rule-table candidate, E5: support_choice skipped);
  display   = a visible support chosen at a window starts a display (not at the window ending at the turn start);
              it lasts while the rule table keeps that same support (shadow flow: the choice does not change later
              states), otherwise one window;
  TP / FN   = help-expected cell (designated, with a rule-table v0 row) with / without a display shown at or after
              the cell's onset whose form is admissible then; FP / TN = wait-only cell with / without any window
              whose selection is visible; designated delivery = the same as TP for the designated supports only;
  C4 false alarms = FP among the wait-only cells of condition C4 (long no-input).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent   # the kit folder: set by --kit (use_kit)
LABELS = HERE / "labels"
EXCLUDED_CLIPS = {"20261028_165108"}   # recorded at 1x zoom, out of every evaluation
EPS = 1e-9
# support -> action: rule table v0 (metrics.py ACTION_OF); showing nothing is 'wait'
ACTION_OF = {"wait_hold_timer": "wait", "remaining_steps_notice": "apply", "delay_responsibility_notice": "apply",
             "large_button": "propose", "highlight_next_action": "apply", "defer_big_button_question": "wait",
             "call_staff": "call_staff", "general_help_ask": "propose", "none": "wait"}
VISIBLE = {"propose", "apply", "call_staff"}     # 'wait' shows nothing
FORM = {"wait": "기다림", "propose": "묻기", "apply": "바로 적용", "call_staff": "직원 호출"}   # forms in admissible_v5.csv

# Recorded rows: TP, FP, FN, TN, accuracy, precision, recall, F1, designated-support recall, C4 false alarms.
# experiments/eval_jev_raw_2026-11-08/results/judgment_E12.csv has the rule table, E5_C, E5_J and E12 rows; the
# E5_C0 row (Jev) and the 'all none' row are in the judgment tables of experiments/eval_llm_2026-11-09/README.md.
REFERENCE = {
    "rule table": ("Rule table (evaluated implementation)", "43 5 24 65 0.788 0.896 0.642 0.748 0.582 3/9"),
    "E5_C": ("Jev: score, then choose", "42 5 25 65 0.781 0.894 0.627 0.737 0.567 3/9"),
    "E5_C0": ("Jev: choose only", "42 5 25 65 0.781 0.894 0.627 0.737 0.567 3/9"),
    "E5_J": ("Jev: unconstrained choice", "49 52 18 18 0.489 0.485 0.731 0.583 0.612 9/9"),
    "E12_RAW-1": ("RAW-1: camera numbers + touch, choose", "48 51 19 19 0.489 0.485 0.716 0.578 0.567 9/9"),
    "E12_RAW-2": ("RAW-2: camera numbers + touch, score then choose",
                  "58 55 9 15 0.533 0.513 0.866 0.644 0.776 9/9"),
    "all none": ("No help (every asked window answered 'none')", "0 0 67 70 0.511 — 0.000 0.000 0.000 0/9"),
}
COLS = ["Condition", "TP", "FP", "FN", "TN", "Accuracy", "Precision", "Recall", "F1", "Designated-support recall",
        "False alarms under long no-input (C4)"]


def use_kit(path) -> None:
    """Score with the kit in `path`: data/ and reference_answers/ under HERE, labels under LABELS."""
    global HERE, LABELS
    HERE = Path(path).resolve()
    LABELS = HERE / "labels"


def read_csv(p: Path) -> list:
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_jsonl(p: Path) -> list:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def load_labels():
    """Windows (with their cell and the rule table's own flow), cells (admissible rows) and turn starts."""
    wins = [w for w in read_csv(LABELS / "window_cells.csv") if w["clip"] not in EXCLUDED_CLIPS]
    for w in wins:
        w["t"] = float(w["t"])
        w["measurable"] = w["measurable"] == "1"
        w["scored"] = w["scored"] == "1"
    f = lambda x: float(x) if x else None
    cells = {}
    for r in read_csv(LABELS / "admissible_v5.csv"):
        sets = lambda k: {x for x in r[k].split(";") if x}
        cells[f"{r['segment_id']}|{r['condition']}|{r['variant']}"] = {
            "segment_id": r["segment_id"], "condition": r["condition"], "cls": r["eff_class"],
            "base": sets("base_admissible"), "addon": sets("addon_admissible"), "addon_onset": f(r["addon_onset_s"]),
            "onset": f(r["onset_s"]), "designated": r["designated"], "v0_row": r["designated_v0_row"],
            "rules": r["rules"]}
    tstart = {r["segment_id"]: float(r["t_start"]) for r in read_csv(LABELS / "judgment_labels_v5.csv")}
    return wins, cells, tstart


def rule_choice(w: dict) -> str:
    return w["rule_support"] if w["rule_transition"] in ("open", "replace") else "none"


def visible(x) -> bool:
    return ACTION_OF.get(x or "none", "wait") in VISIBLE


def selections(wins: list, asked: dict, answers: dict) -> tuple[dict, Counter]:
    """asked: window_id -> options of the window's last stage (the data file); answers: window_id -> choice."""
    sel, status = {}, Counter()
    for w in wins:
        k = w["window_id"]
        if k in asked:
            x = answers.get(k)
            if x is not None and x in asked[k]:
                sel[k] = x
                status["answered"] += 1
            else:
                sel[k] = rule_choice(w)
                status["asked, no valid answer -> rule table's decision"] += 1
        elif not w["measurable"]:
            sel[k] = rule_choice(w)
            status["not measurable -> rule table's decision (opens nothing)"] += 1
        else:
            sel[k] = "none"
            status["measurable, not in the data file -> none"] += 1
    return sel, status


def displays(ws: list, sel: dict, t_start: float) -> list:
    """help_rule.displays over policy_records: an open = the selection; else the rule table's keep; else nothing."""
    out, cur = [], None
    for w in ws:                                    # ws sorted by t
        x, t = sel[w["window_id"]], w["t"]
        if x not in (None, "none"):
            tr, sp, act = "open", x, ACTION_OF.get(x, "wait")
        elif w["rule_transition"] == "keep":
            sp = w["rule_support"] or None
            tr, act = "keep", ACTION_OF.get(sp or "none", "wait")
        else:
            tr, sp, act = "none", None, None
        if cur is not None:
            if tr == "keep" and sp == cur["support"]:
                continue
            cur["t_end"] = t
            out.append(cur)
            cur = None
        if tr == "open" and act in VISIBLE and t > t_start + EPS:
            cur = {"support": sp, "form": FORM.get(act), "t_open": t, "t_end": math.inf}
    if cur is not None:
        out.append(cur)
    return out


def help_after_onset(ds: list, a: dict, supports=None):
    """The first display shown at or after the onset whose form is admissible then (help_rule.help_after_onset)."""
    onset = a["onset"]
    for d in ds:
        if supports is not None and d["support"] not in supports:
            continue
        if onset is not None and not (d["t_open"] >= onset - EPS or d["t_end"] > onset + EPS):
            continue
        if d["form"] in a["base"] or (d["form"] in a["addon"] and a["addon_onset"] is not None
                                      and a["addon_onset"] < d["t_end"] - EPS):
            return d
    return None


def designated_names(a: dict) -> set:
    return {d.split("(")[0] for d, _ in zip(a["designated"].split(";"), a["v0_row"].split(";")) if d}


def score(wins: list, cells: dict, tstart: dict, sel: dict) -> dict:
    by_cell = defaultdict(list)
    for w in wins:
        if w["scored"]:
            by_cell[w["cell_id"]].append(w)
    c = Counter()
    per_cell = []
    for cid in sorted(by_cell):
        ws, a = sorted(by_cell[cid], key=lambda w: w["t"]), cells[cid]
        row = {"cell_id": cid, "condition": a["condition"], "class": a["cls"], "origin": "", "outcome": a["cls"],
               "help_support": "", "help_t_open": "", "designated_delivered": ""}
        if a["cls"] == "wait_only":
            hit = any(visible(sel[w["window_id"]]) for w in ws)
            c["FP" if hit else "TN"] += 1
            row["outcome"] = "FP" if hit else "TN"
            if a["condition"] == "C4":
                c["C4_n"] += 1
                c["C4_FP"] += hit
        elif a["cls"] == "designated":
            ds = displays(ws, sel, tstart[a["segment_id"]])
            h, hd = help_after_onset(ds, a), help_after_onset(ds, a, designated_names(a))
            if "true" in a["v0_row"].split(";"):     # only designations with a rule-table v0 row enter the 2x2
                origin = "touch" if ("S3-C2" in a["rules"] or "S3-C3" in a["rules"]) else "camera"
                c["TP" if h else "FN"] += 1
                c["delivered"] += hd is not None
                c[f"{origin}_n"] += 1
                c[f"{origin}_TP"] += h is not None
                row.update(origin=origin, outcome="TP" if h else "FN", designated_delivered=int(hd is not None))
                if h:
                    row.update(help_support=h["support"], help_t_open=h["t_open"])
            else:
                row["outcome"] = "designated_no_v0_row (outside the 2x2)"
        per_cell.append(row)
    tp, fp, fn, tn = c["TP"], c["FP"], c["FN"], c["TN"]
    p, n = tp + fn, fp + tn
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn, "P": p, "N": n,
            "accuracy": (tp + tn) / (p + n), "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / p, "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
            "dsr": c["delivered"] / p, "delivered": c["delivered"], "c4": f"{c['C4_FP']}/{c['C4_n']}",
            "origin": {k: (c[f"{k}_TP"], c[f"{k}_n"]) for k in ("camera", "touch")},
            "windows_scored": sum(len(v) for v in by_cell.values()), "cells": per_cell}


def values(s: dict) -> str:
    f = lambda x: "—" if x is None else f"{x:.3f}"
    return " ".join([str(s["TP"]), str(s["FP"]), str(s["FN"]), str(s["TN"]), f(s["accuracy"]), f(s["precision"]),
                     f(s["recall"]), f(s["f1"]), f(s["dsr"]), s["c4"]])


def md_row(name: str, s: dict) -> str:
    return "| " + " | ".join([name] + values(s).split(" ")) + " |"


def read_arm(data: Path, answers: Path | None):
    asked = {}
    for line in read_jsonl(data):
        asked[line["window_id"]] = line["stages"][-1]["options"]
    got = {}
    if answers is not None:
        for line in read_jsonl(answers):
            got[line["window_id"]] = line.get("choice")
    return asked, got


def run_one(name: str, data: Path, answers: Path | None, wins, cells, tstart, all_none: bool = False):
    asked, got = read_arm(data, answers)
    if all_none:
        got = {k: "none" for k in asked}
    known = {w["window_id"] for w in wins}
    unknown = [k for k in got if k not in asked]
    sel, status = selections(wins, asked, got)
    s = score(wins, cells, tstart, sel)
    return s, status, unknown, len(set(asked) - known)


def print_table(rows: list) -> None:
    print("| " + " | ".join(COLS) + " |")
    print("|" + "---|" * len(COLS))
    for r in rows:
        print(r)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kit", help="the evaluation kit folder (data/, labels/, reference_answers/)")
    ap.add_argument("--data", help="the kit data file that was asked (data/<arm>.jsonl)")
    ap.add_argument("--answers", help="answers JSONL: window_id, choice")
    ap.add_argument("--name", help="row name (default: the answers file name)")
    ap.add_argument("--cells-out", help="write the outcome of every scored cell to this CSV")
    ap.add_argument("--rule-table", action="store_true", help="score the rule table's own decisions")
    ap.add_argument("--check", action="store_true", help="rescore reference_answers/ against the recorded rows")
    args = ap.parse_args()
    if args.kit:
        use_kit(args.kit)
    elif not (LABELS / "window_cells.csv").is_file():
        ap.error(f"give --kit <kit folder> (no labels/window_cells.csv under {HERE})")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")      # the table prints '—' (cp949 consoles cannot encode it)
    wins, cells, tstart = load_labels()

    if args.check:
        rows, ok_all = [], True
        rule = {w["window_id"]: rule_choice(w) for w in wins}
        checks = [("rule table", None, None, False)]
        checks += [(arm, HERE / "data" / f"{arm}.jsonl", HERE / "reference_answers" / f"{arm}.jsonl", False)
                   for arm in ("E5_C", "E5_C0", "E5_J", "E12_RAW-1", "E12_RAW-2")]
        checks += [("all none", HERE / "data" / "E5_J.jsonl", None, True)]
        for key, data, answers, none in checks:
            if data is None:
                s = score(wins, cells, tstart, rule)
            else:
                s = run_one(key, data, answers, wins, cells, tstart, none)[0]
            label, want = REFERENCE[key]
            ok = values(s) == want
            ok_all &= ok
            rows.append(md_row(f"{label} [{key}]", s))
            print(f"{'OK  ' if ok else 'DIFF'} {key}: {values(s)}" + ("" if ok else f"  (recorded {want})"))
        print()
        print_table(rows)
        print("\nall rows equal the recorded rows" if ok_all else "\nsome rows differ from the recorded rows")
        return 0 if ok_all else 1

    if args.rule_table:
        s = score(wins, cells, tstart, {w["window_id"]: rule_choice(w) for w in wins})
        name = "Rule table (evaluated implementation)"
        status, unknown, outside = Counter({"rule table's own decision": len(wins)}), [], 0
    else:
        if not (args.data and args.answers):
            ap.error("give --data and --answers (or --rule-table / --check)")
        s, status, unknown, outside = run_one("", Path(args.data), Path(args.answers), wins, cells, tstart)
        name = args.name or Path(args.answers).stem
    print(f"windows: {len(wins)} (clip {', '.join(sorted(EXCLUDED_CLIPS))} left out); scored windows "
          f"{s['windows_scored']}; cells: {s['P']} help-expected, {s['N']} wait-only")
    for k, v in sorted(status.items()):
        print(f"  {k}: {v}")
    if unknown:
        print(f"  answers for windows not in the data file (ignored): {len(unknown)}")
    if outside:
        print(f"  data windows not in labels/window_cells.csv (ignored): {outside}")
    o = s["origin"]
    print(f"TP by designation origin: camera {o['camera'][0]}/{o['camera'][1]}, touch {o['touch'][0]}/{o['touch'][1]}; "
          f"designated support delivered {s['delivered']}/{s['P']}\n")
    print_table([md_row(name, s)])
    if args.cells_out:
        with open(args.cells_out, "w", encoding="utf-8-sig", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(s["cells"][0]))
            wr.writeheader()
            wr.writerows(s["cells"])
        print(f"\ncells -> {args.cells_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
