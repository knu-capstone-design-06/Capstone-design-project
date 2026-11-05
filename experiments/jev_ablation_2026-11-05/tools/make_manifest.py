"""Write or update the versioned manifest of an E5 result set (Codex 206 #3): results/real_<date>/manifest.json.

It records what every number of the set depends on: PR #77 file hashes, the E5 tool hashes, the input file hashes
(aligned, aligned_touch_none, windows_<bundle>.csv, labels v1/v2, admissible v1/v2, the verified window labels, the
vision-only windows), the exclusions, the cache policy and which results came from the cache, the model version and
question texts, and the superseded figures. Each update bumps "version"; manifest_id = <set>-v<version>-<content hash>.
metrics.py stamps the id and the label version into every metrics.md header.

  <backend venv python> -B make_manifest.py [--set results/real_2026-11-04] [--note "..."]

Record: this script wrote results/manifest.json in the author's workspace layout (4_vision/eval_jev_2026-11-04 next
to 4_vision/eval_ab_2026-11-04, hash_inputs.py groups, results/settings.json); it does not run inside this package.
"""

import argparse
import csv
import hashlib
import os
import json
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
E5 = HERE.parent
WS = E5.parents[1]
KST = timezone(timedelta(hours=9))
DEFAULT_SET = E5 / "results" / "real_2026-11-04"
# PR #77 worktrees <E5_WORKTREES>/wt_pr77_<first 7 hex of the commit>/ (the set's runs name the commit); the author's
# machine kept them in a temporary folder
SCRATCH = Path(os.environ.get("E5_WORKTREES", "."))
PR_FILES = ("app/modules/decision/schemas.py", "app/modules/decision/rule_table.py", "app/modules/decision/jev_questions.py",
            "app/modules/decision/service.py", "app/modules/decision/repository.py",
            "app/infrastructure/external/jev_client.py", "app/infrastructure/external/jev_schemas.py",
            "app/common/config/settings.py")
SUPERSEDED = [
    {"figure": "stage 1 order consistency 158/158 and every 'both orders agree' figure",
     "where": "stage1_aligned_b0_r0/metrics.md", "why": "the reversed-order requests were served by an order-blind "
     "cache key (dict keys sorted; singleton candidate lists); Codex 205 #1, red team E5 stage 1 #1",
     "replaced_by": "stage2_1_swap_C_C0 (order-aware cache key, live reversed calls)"},
    {"figure": "every stage-1 score on labels v1", "where": "stage1_aligned_b0_r0/metrics.md, labels_v1/",
     "why": "later label versions exist; v1 scorings stay for comparison only",
     "replaced_by": "the newest labels_v<N>/ rescoring (windows with identical inputs only)"},
    {"figure": "stage-1 forecast against persistence", "where": "stage1_aligned_b0_r0/metrics.md",
     "why": "persistence reads the current label (oracle); red team #7", "replaced_by": "B-top carry-forward and "
     "constant baselines on the same windows"},
    {"figure": "stage-1 permutation table", "where": "stage1_aligned_b0_r0/metrics.md",
     "why": "different population (121 incl. 6 excluded windows vs 115); Codex 205 #4, red team #6",
     "replaced_by": "nulls on the scored population, fixed Brier population, answers shuffled within option sets"},
    {"figure": "labels_v3 scorings before 2026-11-05 04:0x (no-row coverage by admissible form, J 16/20 and A 4/20; help as a new offer at or after the onset only; options from allowed_candidates; segment truth tag in the attribution; time-mode labels without onset)",
     "where": "labels_v3/ as of manifest v4, stage2_summary_v3.txt as of v4", "why": "Codex 209 #1-#7 and labels red team round 3 findings 1, 3, 4, 9 (main 2026-11-05)",
     "replaced_by": "labels_v3/ rescored with metrics.SCORING_VERSION; the old help rule stays in each metrics.json segments.old_definition"},
]


def _set_ref(p: Path) -> dict:
    m = json.loads((p / "manifest.json").read_text(encoding="utf-8")) if (p / "manifest.json").is_file() else {}
    return {"set": p.name, "path": str(p), "manifest_id": m.get("manifest_id"), "pr_commit": (m.get("pr77") or {}).get("commit"),
            "why": "PR #77 approved at 3c936ae (2026-11-05); 0114ed1 sent looking_around=false without a known situation, "
                   "its candidate lists differ in 46 / 59 / 42 tagged / GT windows and wait-only windows got a none-only "
                   "question (main's decision 2026-11-05)"}


WINDOW_COLS = ("situation", "gaze", "measurable", "session_reset", "transition", "support")   # what load_aligned reads


def windows_rows_provenance(runs: dict, ab: Path) -> dict | None:
    """Which E3 window-row files the set's runs read, where they come from, and whether the columns E5 reads equal
    E3's current rows (E3 results/windows_<bundle>.csv(.gz), named in E3's newest manifest_v<N>.json)."""
    import gzip
    named = {}
    for name, r in runs.items():
        w = (r.get("aligned") or {}).get("windows_rows")
        if w:
            named.setdefault(w, []).append(name)
    if not named:
        return None

    def read(p: Path) -> dict:
        out = {}
        with (gzip.open(p, "rt", encoding="utf-8-sig", newline="") if p.suffix == ".gz" else
              open(p, encoding="utf-8-sig", newline="")) as fh:
            for row in csv.DictReader(fh):
                if row["line"] == "AB0" and row["variant"] == "fit-medium":
                    out[(row["take"], row["condition"], round(float(row["t"]), 4))] = tuple(row[c] for c in WINDOW_COLS)
        return out

    def actual(p: Path) -> Path:
        return p if p.is_file() else p.with_name(p.name + ".gz")

    e3_manifests = sorted((ab / "results").glob("manifest_v*.json"), key=lambda f: int(f.stem.split("_v")[-1]))
    e3_now = json.loads(e3_manifests[-1].read_text(encoding="utf-8")) if e3_manifests else {}
    files = {}
    for w, names in sorted(named.items()):
        used = actual(Path(w))
        src_manifest = used.parent / f"manifest_{used.parent.name.split('_')[-1]}.json"
        src = json.loads(src_manifest.read_text(encoding="utf-8")) if src_manifest.is_file() else {}
        cur = actual(ab / "results" / Path(w).name)
        check = None
        if used.is_file() and cur.is_file():
            a, b = read(used), read(cur)
            check = {"e3_file": str(cur.relative_to(WS).as_posix()), "e3_file_sha256": sha(cur),
                     "rows_fit_medium_ab0": len(a), "rows_in_both": len(set(a) & set(b)),
                     "rows_with_other_values": sum(1 for k in a if k in b and a[k] != b[k])}
        files[str(used.relative_to(WS).as_posix()) if used.is_file() else w] = {
            "named_in_runs_as": w, "read": str(used.relative_to(WS).as_posix()) if used.is_file() else None,
            "sha256": sha(used), "runs": sorted(names),
            "made_by": {"e3_manifest": str(src_manifest.relative_to(WS).as_posix()) if src else None,
                        "made": src.get("made"), "vision_commit": (src.get("vision_code") or {}).get("commit"),
                        "e3_labels_then": src.get("label")},
            "equal_to_e3_current_rows": check}
    return {
        "what": "E3 AB0 window rows joined to the aligned windows by run_jev_ablation.load_aligned: line AB0, the run's "
                "variant (fit-medium), columns " + ", ".join(WINDOW_COLS) + " (situation, gaze, measurable and session "
                "reset are rule inputs; transition and support are AB0's decision for the parity check)",
        "path_note": "runs.<name>.aligned.windows_rows names windows_<bundle>.csv; when only windows_<bundle>.csv.gz "
                     "exists the runner reads that (load_aligned) and runs.<name>.input_sha256 holds its hash",
        "label_independence": "the columns read do not depend on E3's judgment labels (labels only score AB0), so rows "
                              "from an E3 pass on an older label version serve any label version, provided the vision "
                              "commit and the inputs are the same; equal_to_e3_current_rows checks this per file",
        "e3_current": {"manifest": str(e3_manifests[-1].relative_to(WS).as_posix()) if e3_manifests else None,
                       "vision_commit": (e3_now.get("vision_code") or {}).get("commit")},
        "checked": datetime.now(KST).isoformat(timespec="seconds"),
        "files": files}


def sha(p: Path) -> str | None:
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run_summary(run: Path) -> dict:
    s = json.loads((run / "run_settings.json").read_text(encoding="utf-8"))
    cached = Counter()
    models = Counter()
    swaps = Counter()
    calls = run / "jev_calls.jsonl"
    if calls.is_file():
        with open(calls, encoding="utf-8") as fh:
            for line in fh:
                c = json.loads(line)
                for st in c["stages"]:
                    if st.get("outcome") in ("answered", "no_answer"):
                        cached[(c["arm"], st["stage"], bool(st.get("cached")))] += 1
                        if st.get("response_model"):
                            models[st["response_model"]] += 1
                    if st.get("order_swap"):
                        swaps[(c["arm"], bool(st["order_swap"].get("cached")))] += 1
    return {"run_settings_sha256": sha(run / "run_settings.json"), "created": s.get("created"), "jev": s.get("jev"),
            "model_requested": s.get("model"), "response_models": dict(models), "arms": [a["arm"] for a in s["arms"]],
            "inputs": s.get("inputs"), "aligned": s.get("aligned"), "tag_source": s.get("tag_source"),
            "order_swap_cache": s.get("order_swap_cache") or ("order-blind (before 2026-11-05)" if s.get("order_swap")
                                                              else None),
            "api_calls": s.get("calls_total"), "failed": s.get("calls_failed"), "answers_from_cache":
                s.get("answers_from_cache"), "backoff_retries": s.get("backoff_retries"),
            "input_sha256": s.get("input_sha256"),
            "stage_answers": [{"arm": a, "stage": st, "from_cache": c, "n": n} for (a, st, c), n in sorted(cached.items())],
            "order_swaps": [{"arm": a, "from_cache": c, "n": n} for (a, c), n in sorted(swaps.items())],
            "questions_sha256": sha(run / "questions.json")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", default=str(DEFAULT_SET))
    ap.add_argument("--note", default="")
    ap.add_argument("--supersedes", help="an older result set this one replaces (its folder)")
    ap.add_argument("--superseded-by", help="the result set that replaces this one (its folder)")
    args = ap.parse_args()
    root = Path(args.set)
    path = root / "manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    import hash_inputs as HI
    ab = WS / "4_vision" / "eval_ab_2026-11-04"
    versions = sorted({f.stem.split("_")[-1] for f in ab.glob("admissible_v*.csv")
                       if (ab / f"judgment_labels_{f.stem.split('_')[-1]}.csv").is_file()}, key=lambda v: int(v[1:]))
    newest = versions[-1] if versions else None
    inputs = {g: {f.relative_to(WS).as_posix(): sha(f) for f in files if f.is_file()} for g, files in HI.GROUPS.items()}
    settings = json.loads((E5 / "results" / "settings.json").read_text(encoding="utf-8"))
    run_commits = {json.loads((d / "run_settings.json").read_text(encoding="utf-8")).get("pr_commit")
                   for d in root.iterdir() if (d / "run_settings.json").is_file()} - {None}
    if len(run_commits) != 1:
        raise SystemExit(f"the set's runs name {len(run_commits)} PR commits: {sorted(run_commits)}")
    PR_BACKEND = SCRATCH / f"wt_pr77_{next(iter(run_commits))[:7]}" / "backend"
    try:
        commit = subprocess.run(["git", "-C", str(PR_BACKEND), "rev-parse", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    runs = {d.name: run_summary(d) for d in sorted(root.iterdir()) if (d / "run_settings.json").is_file()
            and json.loads((d / "run_settings.json").read_text(encoding="utf-8")).get("arms")}
    if run_commits != {commit}:
        raise SystemExit(f"PR backend {PR_BACKEND} is at {commit}, the runs at {sorted(run_commits)}")
    import metrics as MX
    contradictory = {}
    with open(ab / f"admissible_{newest}.csv", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["contradictory"] == "True" and r["variant"] == "fit-medium":
                contradictory.setdefault(r["condition"], []).append(r["segment_id"])
    stage2_log = root / "stage2_log.json"
    cache_file = root / "jev_cache.jsonl"
    for d in sorted(root.iterdir()):          # a set may share another set's cache file (--cache-file of its runs)
        argv = json.loads((d / "run_settings.json").read_text(encoding="utf-8")).get("command") or []             if (d / "run_settings.json").is_file() else []
        if not cache_file.is_file() and "--cache-file" in argv:
            cache_file = Path(argv[argv.index("--cache-file") + 1])
    run_log = root / "run_log.json"
    body = {
        "set": root.name, "updated": datetime.now(KST).isoformat(timespec="seconds"), "note": args.note,
        "pr77": {"backend": str(PR_BACKEND), "commit": commit, "sha256": {f: sha(PR_BACKEND / f) for f in PR_FILES}},
        "tools": {str(f.relative_to(E5)): sha(f) for f in sorted(list(HERE.glob("*.py")) + list(HERE.glob("wording/*.json")))},
        "inputs": inputs,
        "windows_rows_provenance": windows_rows_provenance(runs, ab),
        "label_versions": {**{v: {k: inputs["labels"].get(f"4_vision/eval_ab_2026-11-04/{k}")
                                  for k in (f"judgment_labels_{v}.csv", f"admissible_{v}.csv")} for v in versions},
                           "scoring": f"{newest} (labels_{newest}/); older scorings kept under labels_v<N>/ for comparison",
                           "review": "labels v3 = decision 227 red team round 2 applied; labels v4 = labels red team "
                                     "round 3 (6_records/reviews/2026-11-05/redteam_judgment_labels_v3_opus_out.md) "
                                     "applied (eval_ab_2026-11-04/changes_v4.csv); labels red team round 4 "
                                     "(6_records/reviews/2026-11-05/redteam_judgment_labels_v4_fable_out.md) closed "
                                     "2026-11-05 06:2x with 0 critical, confirmed by Codex 212 (13:1x, "
                                     "codex_212_labels_round4_out.md); the labels stay stipulated admissible actions, "
                                     "so every number is provisional"},
        "scoring": {"metrics_version": MX.SCORING_VERSION, "help_rule": MX.HELP_RULE, "old_help_rule": MX.OLD_HELP_RULE,
                    "metrics_sha256": sha(HERE / "metrics.py"),
                    "help_rule_module": {"path": str(ab / "tools" / "help_rule.py"), "sha256": sha(ab / "tools" / "help_rule.py"),
                                         "how": "imported by metrics.py (one implementation for E3 / E5)"}},
        "supersedes": None if not args.supersedes else _set_ref(Path(args.supersedes)),
        "superseded_by": None if not args.superseded_by else _set_ref(Path(args.superseded_by)),
        "budget": {"cap_usd": 10, "source": "his words H124 (2026-11-05 01:5x): 'And the budget for the JEV is $10.' "
                                            "(was $3, H114 / H115)",
                   "rule": "staged (decision 249, decision 248 amended): expand only where a review shows value; "
                           "report usage from the actual call count at every stage (H125)",
                   "recorded_calls": sum(r.get("api_calls") or 0 for r in runs.values() if r.get("jev") == "real")
                   if not run_log.is_file() else sum(r.get("api_calls") or 0 for r in
                                                     json.loads(run_log.read_text(encoding="utf-8"))["items"]),
                   "recorded_calls_basis": "run_log.json (every chunk and the killed first attempt)" if run_log.is_file()
                   else "calls_total of the run folders"},
        "exclusions": {
            "segments": "windows of segments with eff_class 'excluded' leave every label-dependent score (selection, "
                        "state estimation, rule question, forecast, null controls)",
            "rescoring": "a recorded run is rescored only on windows whose rebuilt inputs equal the recorded ones "
                         f"(rescore_labels.py input_check.json, backend at the run's pr_commit); see labels_{newest}/",
            "contradictory": {"rule": "cells (segment x touch condition) whose touch condition contradicts the scene "
                                      "(eff_class contradictory) are not evaluable for E4 / E5 (NOT_EVALUABLE)",
                              "cells_fit_medium": {c: sorted(v) for c, v in sorted(contradictory.items())},
                              "count_fit_medium": sum(len(v) for v in contradictory.values())},
            "wait_only_candidate": "windows whose only allowed candidate is wait_hold_timer: PR 0114ed1 "
                                   "SupportChoiceStage offered only none there (its WHAT had no 3-2 line); PR 3c936ae's "
                                   "WHAT has the 3-2 line and no run of the 3c936ae set sent a none-only question; options "
                                   "and chance come from the question actually sent; singleton-none windows are counted "
                                   "apart (Codex 209 #7)",
        },
        "cache_policy": {
            "key": "sha256 of canonical JSON (sorted dict keys) of model, state and questions for ordinary requests; the "
                   "reversed-order support_choice request is keyed on its JSON in sent order ('o:' prefix) since "
                   "2026-11-05 (Codex 205 #1); failures are never cached; repeats bypass the cache",
            "file": str(cache_file), "file_sha256_now": sha(cache_file),
            "per_run": "runs.<name>.stage_answers / order_swaps list, per arm and stage, how many answers came from the "
                       "cache (an answer reused from an earlier arm or run is not an independent replication)"},
        "model": {"setting_default": settings.get("model", {}).get("setting_default"),
                  "questions": {"settings_json": str(E5 / "results" / "settings.json"),
                                "questions_section_sha256": hashlib.sha256(json.dumps(settings.get("questions"),
                                    sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()}},
        "runs": runs,
        "stage2_log": json.loads(stage2_log.read_text(encoding="utf-8")) if stage2_log.is_file() else None,
        "run_log": json.loads(run_log.read_text(encoding="utf-8")) if run_log.is_file() else None,
        "superseded": SUPERSEDED + [
            {"figure": f"every scoring on labels {v}", "where": f"labels_{v}/", "why": f"labels {newest} exist",
             "replaced_by": f"labels_{newest}/"} for v in versions if v not in ("v1", newest)
            and (root / f"labels_{v}").is_dir()],
    }
    content = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    version = int(old.get("version", 0)) + 1
    body = {"manifest_id": f"{root.name}-v{version}-{content}", "version": version, **body}
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"manifest {body['manifest_id']} -> {path} ({len(runs)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
