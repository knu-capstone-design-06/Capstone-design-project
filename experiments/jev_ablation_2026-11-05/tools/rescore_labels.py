"""Rescore a recorded E5 run on another label version without any API call (Codex 205 #2 / main's item 5).

1. Input check: the runner rebuilds the run's window inputs from today's input files with condition A only (stub, no
   API) and compares every window with the run's rule_windows.jsonl: WindowInput fields, the situation it used, the
   rule decision and the allowed candidates. Windows that differ are listed and left out of the rescoring, so only
   windows whose inputs are identical are rescored.
2. Metrics: tools/metrics.py on the recorded jev_calls / repeats with the chosen labels; for aligned runs the
   admissible table joined on segment x condition x variant, the segment of a window taken by time from the
   judgment-label file (v2 changed boundaries and added segments).
Outputs: <dest>/labels_<version>/<run name>/{input_check.json, metrics.json, metrics.md}.

  python -B rescore_labels.py --run <run folder> --version v4 --dest <folder> --backend <checkout>/backend
      [--admissible <csv>] [--judgment <csv>] [--null-perms N] [--manifest results/manifest.json]

Package defaults: labels from inputs/labels/, E3 window rows from inputs/e3_windows/, --backend from the environment
variable E5_BACKEND, metrics.py run with this interpreter (it needs only the standard library).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = HERE.parent / "inputs"
LABELS_DIR = INPUTS / "labels"
FIELDS = ("t", "measurable", "screen", "steps_left", "gaze", "misses_recent", "fixes_recent", "backs_recent", "pause_s",
          "taps_segment", "progress_segment", "options_open")


def read_jsonl(p: Path) -> list:
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--version", required=True, help="label version name, e.g. v4")
    ap.add_argument("--dest", required=True, help="folder that gets labels_<version>/<run name>/")
    ap.add_argument("--admissible", help="admissible table (default inputs/labels/admissible_<version>.csv)")
    ap.add_argument("--judgment", help="judgment labels (default inputs/labels/judgment_labels_<version>.csv)")
    ap.add_argument("--null-perms", type=int, default=1000)
    ap.add_argument("--backend", default=os.environ.get("E5_BACKEND"),
                    help="a backend/ folder at the run's PR commit (default: the environment variable E5_BACKEND); the "
                         "commit must equal run_settings pr_commit")
    ap.add_argument("--metrics-python", default=sys.executable, help="interpreter for metrics.py (default: this one)")
    ap.add_argument("--check-only", action="store_true", help="only the input check (light; no metrics)")
    ap.add_argument("--windows-dir", default=str(INPUTS / "e3_windows"),
                    help="folder of E3's windows_<bundle>.csv(.gz) (default inputs/e3_windows)")
    ap.add_argument("--manifest", help="manifest.json whose id goes into the metrics.md header (e.g. results/manifest.json "
                                       "when the run reproduces the recorded set)")
    args = ap.parse_args()
    if not args.backend:
        raise SystemExit("pass --backend <checkout>/backend (at the run's PR commit) or set E5_BACKEND")
    run = Path(args.run)
    s = json.loads((run / "run_settings.json").read_text(encoding="utf-8"))
    out = Path(args.dest) / f"labels_{args.version}" / run.name
    out.mkdir(parents=True, exist_ok=True)
    admissible = Path(args.admissible) if args.admissible else LABELS_DIR / f"admissible_{args.version}.csv"
    judgment = Path(args.judgment) if args.judgment else LABELS_DIR / f"judgment_labels_{args.version}.csv"

    # 1. input check
    tmp = out / "_inputs_now"
    cmd = [sys.executable, "-B", str(HERE / "run_jev_ablation.py"), "--jev", "stub", "--arms", "A", "--no-labels",
           "--out", str(tmp), "--backend", args.backend]
    if s.get("aligned"):
        for d in s["inputs"]:
            cmd += ["--aligned", d]
        a = s["aligned"]
        cmd += ["--bundle", a["bundle"], "--variant", a["variant"], "--conditions", *a["conditions"],
                "--tag-source", s.get("tag_source") or "replay", "--windows-dir", args.windows_dir]
    else:
        for d in s["inputs"]:
            cmd += ["--input", d]
        argv = s.get("command") or []
        if "--windows-name" in argv:                       # e.g. round3 windows_b0.jsonl
            cmd += ["--windows-name", argv[argv.index("--windows-name") + 1]]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    rebuilt = json.loads((tmp / "run_settings.json").read_text(encoding="utf-8"))
    if rebuilt.get("pr_commit") != s.get("pr_commit"):
        raise SystemExit(f"backend commit {rebuilt.get('pr_commit')} differs from the run's pr_commit {s.get('pr_commit')}; "
                         f"pass --backend <a backend/ at {s.get('pr_commit')}>")
    then = {(r["take"], r["i"]): r for r in read_jsonl(run / "rule_windows.jsonl")}
    now = {(r["take"], r["i"]): r for r in read_jsonl(tmp / "rule_windows.jsonl")}
    changed = []
    for k, r in then.items():
        x = now.get(k)
        same = x is not None and all(r["input"].get(f) == x["input"].get(f) for f in FIELDS) \
            and r.get("situation_used") == x.get("situation_used") \
            and (r["rule"]["transition"], r["rule"]["support"]) == (x["rule"]["transition"], x["rule"]["support"]) \
            and r["allowed_candidates"] == x["allowed_candidates"]
        if not same:
            changed.append(list(k))
    shutil.rmtree(tmp)
    check = {"run": str(run), "pr_commit": s.get("pr_commit"),
             "inputs_rebuilt_with": args.windows_dir if s.get("aligned") else None,
             "windows": len(then), "identical": len(then) - len(changed), "changed": len(changed),
             "changed_windows": changed[:50], "missing_now": sum(1 for k in then if k not in now)}
    (out / "input_check.json").write_text(json.dumps(check, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"input check: {check['identical']} of {check['windows']} windows identical, {check['changed']} changed")
    if args.check_only:
        return 0
    excl = out / "_exclude.json"
    excl.write_text(json.dumps(changed), encoding="utf-8")

    # 2. metrics on the chosen labels
    cmd = [args.metrics_python, "-B", str(HERE / "metrics.py"), "--run", str(run), "--out-dir", str(out),
           "--null-perms", str(args.null_perms), "--exclude-windows", str(excl)]
    if args.manifest:
        cmd += ["--manifest", args.manifest]
    if s.get("aligned"):
        cmd += ["--labels", str(admissible)]
        if args.version != "v1":     # v1: the segment_id the aligned record carries (as the run was scored)
            cmd += ["--segments", str(judgment)]
    else:
        cmd += ["--labels", str(judgment)]
    subprocess.run(cmd, check=True)
    excl.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
