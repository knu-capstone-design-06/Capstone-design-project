"""Write the sha256 of E5's current input files into results/settings.json ("inputs_sha256", with the time), so a
result can be tied to the exact E3 files, label versions and replay windows it was computed from.

  python hash_inputs.py [--settings results/settings.json]

Record: written for the author's workspace layout (4_vision/eval_ab_2026-11-04, datasets/); the package's own input
hashes are in inputs/SHA256SUMS.json and in every run's run_settings.json input_sha256.
"""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
E5 = HERE.parent
V4 = E5.parent
AB = V4 / "eval_ab_2026-11-04"
GROUPS = {
    "aligned": sorted((AB / "aligned").glob("*.jsonl")),
    "aligned_touch_none": sorted((AB / "aligned_touch_none").glob("*.jsonl")),
    "windows_rows": sorted(list((AB / "results").glob("windows_*.csv*")) + list((AB / "results").glob("labels_v*/windows_*.csv*"))),
    "labels": sorted(list(AB.glob("judgment_labels_v*.csv")) + list(AB.glob("admissible_v*.csv"))),
    "bundles": sorted((AB / "bundles").glob("*.json")),
    "verified_window_labels": [V4.parent / "datasets" / "team_recording_2026-10-28" / "labels" /
                               "window_labels_v1_verified.csv"],
    "round3_replay_windows_b0": sorted((V4 / "companion_behind_2026-11-04" / "round3_replay" / "team_2026-10-28")
                                       .glob("*/windows_b0.jsonl")),
}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--settings", default=str(E5 / "results" / "settings.json"))
    args = ap.parse_args()
    path = Path(args.settings)
    s = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    out = {"hashed": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"), "files": {}}
    for group, files in GROUPS.items():
        out["files"][group] = {str(f.relative_to(V4.parent)): sha(f) for f in files if f.is_file()}
        print(f"{group}: {len(out['files'][group])} files")
    s["inputs_sha256"] = out
    path.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {path} inputs_sha256 ({out['hashed']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
