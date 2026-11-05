"""Compare two metrics.json files of the same run (e.g. results/labels_v4/<run>/ against a cache reproduction).

Every value is compared exactly. Values that name files on a machine (run, labels, labels_segments, help_rule_module,
aligned.windows_rows) are left out; 'jev' (the answer source: real, or cache) is printed apart. The other differences
are reported in two groups: 'execution' (the execution and order_swap blocks: API calls against cache answers,
latencies of API calls; a reproduction from the cache makes no call, so these differ wherever the recorded run made
calls) and 'scores' (everything else). Exit 0 when the scores are identical.

  python -B tools/compare_metrics.py <recorded metrics.json> <new metrics.json>
"""

import json
import sys

PATH_KEYS = {("run",), ("labels",), ("labels_segments",), ("help_rule_module",), ("aligned", "windows_rows")}
EXECUTION = {"execution", "order_swap"}
PROVENANCE = {"jev"}      # the answer source of the run (real, or cache for a reproduction)


def walk(a, b, path, out):
    if path in PATH_KEYS:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append((path + (k,), "only in " + ("new" if k not in a else "recorded")))
            else:
                walk(a[k], b[k], path + (k,), out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, path + (i,), out)
    elif a != b:
        out.append((path, f"{json.dumps(a, ensure_ascii=False)[:80]} -> {json.dumps(b, ensure_ascii=False)[:80]}"))


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    a, b = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:3])
    diffs = []
    walk(a, b, (), diffs)
    execution = [d for d in diffs if d[0] and d[0][0] in EXECUTION]
    provenance = [d for d in diffs if d[0] and d[0][0] in PROVENANCE]
    scores = [d for d in diffs if not d[0] or d[0][0] not in EXECUTION | PROVENANCE]
    for title, group in (("answer source", provenance), ("execution", execution), ("scores", scores)):
        for p, what in group[:20]:
            print(f"  {title}: {'.'.join(map(str, p))}: {what}")
        if len(group) > 20:
            print(f"  {title}: ... {len(group) - 20} more")
    print(f"scores {'identical' if not scores else f'differ in {len(scores)} values'}; "
          f"execution values differing: {len(execution)} (paths ignored)")
    return 0 if not scores else 1


if __name__ == "__main__":
    raise SystemExit(main())
