"""The one help rule of E3 / E4 from labels v4 on (main's decision on round-3 critical 1, 2026-11-05; JUDGMENT_PROTOCOL.md
§v4-1). Name: E3's existing "admissible help after onset" (시작 뒤 허용 도움), whose meaning changed on 2026-11-05 04:0x
from "a new admissible offer at or after the onset" to the rule below (round-3 finding 1); its absence is "no
admissible help after onset". E5 uses the same rule under the same name.

  A display = one visible support opened inside the segment (a new decision, open or replace, whose action is visible,
  at a window that ends after the segment start: t_start < t_open; the window ending at t_start holds only the time
  before the turn, so an offer opened there belongs to the previous turn: 171844#2 x C2, main's ruling) and kept by
  the following windows of the same support; it ends at the first later window of the segment that does
  not keep it (withdraw, none, another open or replace); a display still kept at the last window of the segment runs
  to the segment end. A display opened in an earlier segment (turn) never counts, even when it is still shown.
  Help = a display that is shown at some time at or after the segment onset (opened at or after the onset, or opened
  earlier in the same segment and not yet ended at the onset: t_end > onset) and whose form is admissible then (the
  base set, or the add-on set once the add-on onset has come before the display ends).
  Latency = max(0, open time - onset); a display opened before the onset is reported apart (opened_before_onset, with
  lead_s = onset - open time). The window-level admissibility (selective risk, false tags) stays per window: an offer
  opened when the label admits nothing is counted there at its own time, even when it later counts as help.
  Designated delivery = the same rule restricted to the designated supports themselves.
  Onset = the segment onset of admissible_v4.csv (onset_s: the minimum over the segment's designations, protocol §v4-6).
Records are window dicts with t, transition, support, action (pass-1 records, pass-2 records or rows read from the
windows CSV: values may be strings); they must be the records of ONE segment of one line.
"""
from __future__ import annotations

import math

import harness as H

EPS = 1e-9
_TSTART: dict | None = None
RULE_NAME = "admissible help after onset (visible at or after the onset, opened within the same turn)"


def _vis_open(r) -> bool:
    return r["transition"] in ("open", "replace") and (r.get("action") or None) in H.VISIBLE


def seg_start(sid: str):
    """t_start of a label segment (harness.load_labels, the current labels)."""
    global _TSTART
    if _TSTART is None:
        _TSTART = {s["segment_id"]: float(s["t_start"]) for v in H.load_labels().values() for s in v}
    return _TSTART.get(sid)


def displays(rs: list) -> list:
    """Display intervals of the visible supports opened inside these records (one segment), in time order; an open at
    the window ending at the segment start belongs to the previous turn and starts no display."""
    out, cur = [], None
    ts = seg_start(rs[0]["segment_id"]) if rs and rs[0].get("segment_id") else None
    for r in sorted(rs, key=lambda x: float(x["t"])):
        t = float(r["t"])
        if cur is not None:
            if r["transition"] == "keep" and (r.get("support") or None) == cur["support"]:
                continue
            cur["t_end"] = t
            out.append(cur)
            cur = None
        if _vis_open(r) and (ts is None or t > ts + EPS):
            cur = {"support": r.get("support") or None, "action": r.get("action"), "form": H.FORM.get(r.get("action")),
                   "t_open": t, "t_end": math.inf}
    if cur is not None:
        out.append(cur)
    return out


def _admissible_during(a: dict, d: dict) -> bool:
    if d["form"] in a["base_set"]:
        return True
    ao = a.get("addon_onset")
    return d["form"] in a["addon_set"] and ao is not None and ao < d["t_end"] - EPS


def help_after_onset(rs: list, a: dict, supports=None, ds: list | None = None) -> dict | None:
    """The first display (by open time) that counts as help under the rule above, or None. supports: restrict to these
    support names (designated delivery). a: the admissible row (admissible_v4.load())."""
    onset = a.get("onset")
    for d in (ds if ds is not None else displays(rs)):
        if supports is not None and d["support"] not in supports:
            continue
        if onset is not None and not (d["t_open"] >= onset - EPS or d["t_end"] > onset + EPS):
            continue
        if not _admissible_during(a, d):
            continue
        before = onset is not None and d["t_open"] < onset - EPS
        return {"t_open": d["t_open"], "support": d["support"], "form": d["form"],
                "latency_s": round(max(0.0, d["t_open"] - onset), 4) if onset is not None else None,
                "opened_before_onset": before, "lead_s": round(onset - d["t_open"], 4) if before else 0.0}
    return None


def old_rule_t(rs: list, a: dict):
    """v3 rule kept for the before / after report only: the first NEW visible decision at or after the onset whose form
    is admissible at its own time (run_eval / second_pass up to labels v3)."""
    onset = a.get("onset")
    for r in sorted(rs, key=lambda x: float(x["t"])):
        t = float(r["t"])
        if not _vis_open(r) or (onset is not None and t < onset - EPS):
            continue
        allowed = set(a["base_set"])
        if a.get("addon_onset") is not None and t >= a["addon_onset"] - EPS:
            allowed |= a["addon_set"]
        if H.FORM.get(r.get("action")) in allowed:
            return t
    return None


def designated_names(a: dict, v0_only: bool | None = None) -> set:
    """Designated support names of an admissible row; v0_only True = only those with a v0 row, False = only those
    without one, None = all."""
    out = set()
    for d, f in zip(a["designated"].split(";"), a["designated_v0_row"].split(";")):
        if not d:
            continue
        if v0_only is None or (f == "true") == v0_only:
            out.add(d.split("(")[0])
    return out


def help_source(a: dict) -> str:
    """'touch' when the segment's designation includes a touch add-on (S3: C2 large_button, C3 highlight), else
    'camera' (scene designations: S1b, S4); round-3 finding 3 split."""
    rules = a.get("rules", "")
    return "touch" if ("S3-C2" in rules or "S3-C3" in rules) else "camera"
