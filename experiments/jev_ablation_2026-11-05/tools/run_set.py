"""Run the recorded E5 set (13 runs of results/labels_v4/) again from this package: from the answer cache (no call),
with the stub (no call) or against the Jev API with your own key; optionally rescore each run on labels v4 and compare
it with the recorded metrics. The package form of run_3c936ae.py: the inputs and arms of every run are written out
below (as recorded in results/manifest.json runs.<name>), with the package's inputs/ in place of the author's paths.

  python -B tools/run_set.py --jev cache|stub|real --backend <checkout>/backend [--items a,b] [--out-root runs/<name>]
      [--rescore [--null-perms 1000] [--compare]] [--concurrency N] [--cap N] [--max-failure-rate 0.01]

  cache  answers only from results/jev_cache.jsonl.gz (read-only) and results/answer_pins.json; nothing is sent, no
         key is read; a request the cache lacks is a 'cache miss' (none in the recorded set)
  stub   fake answers (tools/run_jev_ablation.py docstring) to check the mechanics; no key, no network
  real   the Jev API; the key from JEV_API_KEY or <backend>/.env (never printed); a fresh cache <out-root>/jev_cache.jsonl
         shared by the runs, so a request asked in an earlier run is not asked again; --cap stops asking after N calls
Outputs: <out-root>/<run>/ (run files, several hundred MB for the whole set), <out-root>/labels_v4/<run>/ (metrics),
<out-root>/run_log.json (calls, cache answers, cache misses, pins, time per run).
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
INPUTS = PKG / "inputs"
RESULTS = PKG / "results"
KST = timezone(timedelta(hours=9))
AL = ["--aligned", str(INPUTS / "aligned"), "--aligned", str(INPUTS / "aligned_touch_none"),
      "--windows-dir", str(INPUTS / "e3_windows")]
COND = ["--variant", "fit-medium", "--conditions", "C0", "C1", "C2", "C3", "C4", "C5", "C6"]
V3 = ["--input", str(INPUTS / "vision_round3")]
BASE14 = ["A", "B", "C", "C0", "D", "E", "B:novision", "B:notouch", "B:la_null", "B:sit_dict", "B:vision_summary",
          "B:wording_nocrit", "B:perm_vision", "B:perm_touch"]
# the recorded runs in the order they ran on 2026-11-05 (re-run of the 0114ed1 set, then stage 3)
RUNS = {
    "stage1_aligned_b0_r0": AL + ["--bundle", "b0_r0", *COND, "--tag-source", "replay", "--arms", *BASE14, "--repeats", "1"],
    "stage2_1_swap_C_C0": AL + ["--bundle", "b0_r0", *COND, "--tag-source", "replay", "--arms", "C", "C0", "--repeats", "1"],
    "stage2_2_C_nohistory": AL + ["--bundle", "b0_r0", *COND, "--tag-source", "replay", "--arms", "C", "C:nohistory",
                                  "--repeats", "1"],
    "stage2_3_J_b0_r0": AL + ["--bundle", "b0_r0", *COND, "--tag-source", "replay", "--arms", "J", "--repeats", "1"],
    "stage2_4a_b0_rA": AL + ["--bundle", "b0_rA", *COND, "--tag-source", "replay", "--arms", "A", "B", "C", "C0", "J",
                             "--repeats", "1"],
    "stage2_4b_b2_rA": AL + ["--bundle", "b2_rA", *COND, "--tag-source", "replay", "--arms", "A", "B", "C", "C0", "J",
                             "--repeats", "1"],
    "stage2_5_GT_b0_r0": AL + ["--bundle", "b0_r0", *COND, "--tag-source", "verified", "--arms", "A", "C", "--repeats", "1"],
    "stage2_6_vision_b0": V3 + ["--windows-name", "windows_b0.jsonl", "--arms", "A", "B", "B:vision_summary",
                                "--repeats", "1"],
    "vision_only_round3": V3 + ["--arms", *BASE14, "--repeats", "3"],
    "stage3_a1_repeats_C_C0": AL + ["--bundle", "b0_r0", "--arms", "C", "C0", "--repeats", "5",
                                    "--repeat-stages", "support_choice"],
    "stage3_a2_repeats_B10": AL + ["--bundle", "b0_r0", "--arms", "B", "--repeats", "5", "--repeat-fraction", "0.1",
                                   "--repeat-seed", "0"],
    "stage3_b_B_vt_b0_rA": AL + ["--bundle", "b0_rA", "--arms", "B", "B:novision", "B:notouch", "--repeats", "1"],
    "stage3_b_B_vt_b2_rA": AL + ["--bundle", "b2_rA", "--arms", "B", "B:novision", "B:notouch", "--repeats", "1"],
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jev", required=True, choices=("cache", "stub", "real"))
    ap.add_argument("--backend", default=os.environ.get("E5_BACKEND"),
                    help="PR #77 checkout's backend/ (default: the environment variable E5_BACKEND)")
    ap.add_argument("--items", help=f"comma-separated run names (default: all 13: {', '.join(RUNS)})")
    ap.add_argument("--out-root", help="output folder (default runs/<cache|stub|real_YYYY-MM-DD>)")
    ap.add_argument("--cache-file", help="cache mode: default results/jev_cache.jsonl.gz; real: <out-root>/jev_cache.jsonl")
    ap.add_argument("--concurrency", type=int, help="takes in flight within an arm (default 1; real runs used 2)")
    ap.add_argument("--cap", type=int, help="real mode: API calls allowed for the whole call of this script")
    ap.add_argument("--max-failure-rate", type=float, default=0.01, help="real mode: stop once failed calls exceed "
                    "this share (the recorded set used 0.01)")
    ap.add_argument("--rescore", action="store_true", help="rescore every run on labels v4 (no API call)")
    ap.add_argument("--null-perms", type=int, default=1000, help="permutations of the null controls (recorded: 1000)")
    ap.add_argument("--compare", action="store_true", help="cache mode with --rescore: compare each metrics.json with "
                                                           "results/labels_v4/<run>/metrics.json")
    args = ap.parse_args()
    if not args.backend:
        raise SystemExit("pass --backend <checkout>/backend or set E5_BACKEND")
    names = args.items.split(",") if args.items else list(RUNS)
    unknown = [n for n in names if n not in RUNS]
    if unknown:
        raise SystemExit(f"unknown run(s) {unknown}; known: {list(RUNS)}")
    today = datetime.now(KST).strftime("%Y-%m-%d")
    root = Path(args.out_root) if args.out_root else PKG / "runs" / (args.jev if args.jev != "real" else f"real_{today}")
    root.mkdir(parents=True, exist_ok=True)
    cache = args.cache_file or (str(RESULTS / "jev_cache.jsonl.gz") if args.jev == "cache" else
                                str(root / "jev_cache.jsonl") if args.jev == "real" else None)
    log_path = root / "run_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.is_file() else {"items": []}
    used, failed_any = 0, False
    for name in names:
        left = None if args.cap is None else args.cap - used
        if args.jev == "real" and left is not None and left <= 0:
            print(f"cap reached ({used} of {args.cap}); {name} not started")
            log["items"].append({"jev": args.jev, "run": name, "skipped": "cap reached"})
            break
        out = root / name
        cmd = [sys.executable, "-B", str(HERE / "run_jev_ablation.py"), "--jev", args.jev, "--backend", args.backend,
               "--no-labels", "--out", str(out), "--concurrency", str(args.concurrency or 1), *RUNS[name]]
        if cache:
            cmd += ["--cache-file", cache]
        if args.jev == "cache":
            cmd += ["--answer-pins", str(RESULTS / "answer_pins.json"), "--pin-run", name]
        if args.jev == "real":
            cmd += ["--max-failure-rate", str(args.max_failure_rate)]
            if left is not None:
                cmd += ["--max-calls", str(left)]
        started = datetime.now(KST)
        print(f"== {name} ({args.jev}) started {started.isoformat(timespec='seconds')}", flush=True)
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"{name} failed (exit {r.returncode})")
            log["items"].append({"jev": args.jev, "run": name, "error": r.returncode,
                                 "started": started.isoformat(timespec="seconds")})
            failed_any = True
            break
        s = json.loads((out / "run_settings.json").read_text(encoding="utf-8"))
        row = {"jev": args.jev, "run": name, "started": started.isoformat(timespec="seconds"),
               "ended": datetime.now(KST).isoformat(timespec="seconds"), "pr_commit": s.get("pr_commit"),
               "api_calls": s["calls_total"], "repeat_calls": s.get("repeat_calls"), "failed": s["calls_failed"],
               "answers_from_cache": s["answers_from_cache"], "cache_misses": s.get("cache_misses"),
               "answers_pinned": s.get("answers_pinned"), "backoff_retries": s.get("backoff_retries"),
               "key": s.get("key"), "model": s.get("model"), "wall_s": s.get("wall_s")}
        used += s["calls_total"]
        if args.rescore:
            rc = [sys.executable, "-B", str(HERE / "rescore_labels.py"), "--run", str(out), "--version", "v4",
                  "--dest", str(root), "--backend", args.backend, "--null-perms", str(args.null_perms)]
            if args.jev == "cache":
                rc += ["--manifest", str(RESULTS / "manifest.json")]   # the numbers are the recorded set's
            t0 = datetime.now(KST)
            subprocess.run(rc, check=True)
            row["rescored_s"] = round((datetime.now(KST) - t0).total_seconds(), 1)
            if args.compare and args.jev == "cache":
                cp = subprocess.run([sys.executable, "-B", str(HERE / "compare_metrics.py"),
                                     str(RESULTS / "labels_v4" / name / "metrics.json"),
                                     str(root / "labels_v4" / name / "metrics.json")], capture_output=True, text=True)
                print(cp.stdout.strip())
                row["compare"] = cp.stdout.strip().splitlines()[-1] if cp.stdout.strip() else None
                row["compare_exit"] = cp.returncode
        log["items"].append(row)
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if args.jev == "real" and s["calls_total"] and s["calls_failed"] > args.max_failure_rate * s["calls_total"]:
            print(f"failure rate {s['calls_failed']}/{s['calls_total']} above {args.max_failure_rate}; stopping")
            break
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.jev}: {used} API calls over {len(names)} run(s) -> {root}")
    return 1 if failed_any else 0


if __name__ == "__main__":
    raise SystemExit(main())
