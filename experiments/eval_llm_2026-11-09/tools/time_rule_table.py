"""Response time of the rule table itself, per window, on this PC.

Rebuilds the E5 J run's windows exactly as the E5 runner does (4_vision/eval_jev_2026-11-04/tools/run_jev_ablation.py:
load_aligned -> build_windows, same arguments as results/real_2026-11-05_3c936ae/stage2_3_J_b0_r0/run_settings.json),
then repeats the runner's rule_pass (tick -> decide -> apply, session state carried) with time.perf_counter around
(1) rule_table.decide only and (2) the whole tick + allowed_supports + decide + apply step. The rule table is PR #77's
backend/app/modules/decision/rule_table.py at commit 3c936ae (extracted with git archive; never edited).
Each decision is checked against the run's rule_windows.jsonl. Reports the 1,589 E5_J table-cell windows.
Run with the E5 backend venv (Python 3.12):  python time_rule_table.py <backend dir> <cell window list> <out json>
"""
import copy, json, sys, time
from pathlib import Path

backend, cell_list, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
import os
WORKSPACE = Path(os.environ.get("KIOSK_WORKSPACE", "."))  # 실험 기록이 있는 작업 폴더
E5 = WORKSPACE / "4_vision" / "eval_jev_2026-11-04"
AB = WORKSPACE / "4_vision" / "eval_ab_2026-11-04"
sys.path.insert(0, str(E5 / "tools"))
import run_jev_ablation as E  # noqa: E402

pr = E.PR(backend)
takes_raw = E.load_aligned([AB / "aligned", AB / "aligned_touch_none"], "b0_r0", {f"C{i}" for i in range(7)},
                           "fit-medium", None, AB / "results" / "labels_v2", "replay")
ref = {}
for l in (E5 / "results/real_2026-11-05_3c936ae/stage2_3_J_b0_r0/rule_windows.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(l)
    ref[f"{r['take']}@{r['t']}"] = (r["rule"]["transition"], r["rule"]["support"])
cells = set(cell_list.read_text(encoding="utf-8").split())

R, p = pr.R, pr.params
decide_ms, step_ms, mismatch, seen = {}, {}, 0, 0
for take, records in takes_raw.items():
    windows = E.build_windows(pr, take, records)
    state, k = pr.S.SessionState(), None
    for w in windows:
        t0 = time.perf_counter()
        if w.session_k != k:
            state, k = pr.S.SessionState(), w.session_k
        state, w.expired_id = R.tick(state, w.t, p)
        before = copy.deepcopy(state)
        R.allowed_supports(w.inp, before, p)
        t1 = time.perf_counter()
        decision = R.decide(w.inp, before, p)
        t2 = time.perf_counter()
        state, rec = R.apply(state, decision)
        t3 = time.perf_counter()
        wid = f"{take}@{w.t}"
        if wid in cells:
            seen += 1
            decide_ms[wid] = (t2 - t1) * 1000
            step_ms[wid] = (t3 - t0) * 1000
            tr = getattr(rec, "transition", None)
            sp = getattr(rec, "support", None)
            tr = getattr(tr, "value", tr)
            if ref.get(wid) != (tr, sp):
                mismatch += 1


def stats(d):
    L = sorted(d.values())
    k = lambda q: L[max(0, -(-q * len(L) // 100) - 1)]
    return {"n": len(L), "p50_ms": round(k(50), 4), "p95_ms": round(k(95), 4), "max_ms": round(L[-1], 4),
            "share_le_1000ms": sum(x <= 1000 for x in L) / len(L)}


res = {"function": "app.modules.decision.rule_table.decide (PR #77 3c936ae), called as in run_jev_ablation.rule_pass",
       "python": sys.version.split()[0], "cell_windows_listed": len(cells), "cell_windows_timed": seen,
       "decision_mismatch_vs_rule_windows_jsonl": mismatch,
       "decide_only": stats(decide_ms), "tick_allowed_decide_apply": stats(step_ms)}
out.write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
