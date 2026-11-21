"""The window output in the shape the backend's decision layer reads (contract_view.decision_situation and
observations) and the local touch entry of the live runner (touch_entry.py).

Inputs are made here (synthetic rows, fake perception, fake frames with a fake wall clock), as in
test_vision_chain.py, whose helpers are reused. No camera, no picture, no window. The backend cross-check runs the
backend's own rule table in a separate interpreter, so its `app` package does not mix with ai-engine's.
Every number below is made for these synthetic inputs and is not a proposal for a pilot value.
"""

import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the helpers also load as tests.test_vision_links
from test_vision_chain import (AI_ENGINE_DIR, DT, FULL, HAS_CV2, HAS_NUMPY, NAN, NOT_SEEN, SKIP,  # noqa: E402
                               FakeDirection, FakeHeads, FakeModels, bundle, facing, fake_inference, rows_of, sweep,
                               yaw_schedule)

EPOCH0 = 1_800_000_000.0          # the fake wall clock of the fake camera: frame k is captured at EPOCH0 + t_s
LIVE = {**FULL, "tap_count": None, "miss_tap_count": None}   # live rows: no touch columns at frame time
ORIGIN = "http://127.0.0.1:8080"  # an order screen origin for the CORS tests (the Compose frontend's address)

BACKEND_DIR = os.path.join(os.path.dirname(AI_ENGINE_DIR), "backend")
BACKEND_RULE_TABLE = os.path.join(BACKEND_DIR, "app", "modules", "decision", "rule_table.py")

# Runs one window through backend/app/modules/decision (rule_table.decide on a fresh session state) and prints what
# the decision layer read: whether the situation is known, the evidence counts, the decision and the Jev state.
BACKEND_SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from app.modules.decision.rule_table import decide, evidence_counts, jev_state, situation_known
from app.modules.decision.schemas import PILOT_PARAMS, SessionState, WindowInput
inp = WindowInput(**json.load(sys.stdin))
d = decide(inp, SessionState(), PILOT_PARAMS)
print(json.dumps({"known": situation_known(inp.situation), "evidence": evidence_counts(inp.situation),
                  "transition": d.transition, "support": d.support,
                  "jev_situation": (d.jev_request or {}).get("state", {}).get("situation")}))
"""


def backend_window(**fields) -> dict:
    run = subprocess.run([sys.executable, "-I", "-c", BACKEND_SCRIPT, BACKEND_DIR], input=json.dumps(fields),
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    if run.returncode != 0:
        raise AssertionError(f"backend script failed: {run.stderr}")
    return json.loads(run.stdout)


def looking_around_rows():
    """Two off-screen sweeps, no touch on any row, body still, nobody behind: looking_around at 2.7 s."""
    return rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(10))


@unittest.skipUnless(HAS_NUMPY, SKIP)
class DecisionViewTests(unittest.TestCase):
    def test_the_contract_view_adds_the_backend_shape_and_keeps_its_own_keys(self):
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.situation import SCENE_TAGS
        rows = looking_around_rows()
        rec = WindowJudge(bundle()).evaluate(rows, rows[-1]["t_s"])
        ext = rec["contract"]["extension"]
        sit = rec["situation"]
        self.assertEqual(ext["decision_situation"], {"name": sit["name"], "evidence": sit["evidence"],
                                                     "confidence": sit["confidence"]})
        self.assertEqual(ext["decision_situation"]["name"], "looking_around")
        self.assertEqual(ext["situation"]["tag"], "looking_around")               # the replay tools' keys stay
        self.assertEqual(ext["situation"]["evidence_ids"], sit["evidence_ids"])
        self.assertEqual(ext["observations"]["gaze"], rec["vision"]["facing_screen"])
        self.assertIs(ext["observations"]["face_seen"], True)
        self.assertEqual([t["name"] for t in ext["observations"]["scene_tags"]], list(SCENE_TAGS))
        self.assertEqual([(t["status"], t["unknown_reason"]) for t in ext["observations"]["scene_tags"]],
                         [(t["status"], t["unknown_reason"]) for t in sit["tags"]])

    def test_without_a_value_bundle_the_view_says_unknown_and_has_no_scene_tags(self):
        from app.modules.vision.chain import WindowJudge
        rows = looking_around_rows()
        ext = WindowJudge(bundle(situation=False)).evaluate(rows, rows[-1]["t_s"])["contract"]["extension"]
        self.assertEqual(ext["decision_situation"], {"name": "unknown", "evidence": [], "confidence": "unknown"})
        self.assertEqual(ext["observations"]["scene_tags"], [])
        self.assertIsNone(ext["observations"]["gaze"])                            # no values: gaze cannot be told

    def test_face_seen_is_false_on_a_segment_without_a_face(self):
        from app.modules.vision.chain import WindowJudge
        rows = rows_of([(30, {"face_state": "못 봄", "yaw_deg": float("nan"), "face_cx": float("nan")})])
        ext = WindowJudge(bundle()).evaluate(rows, rows[-1]["t_s"])["contract"]["extension"]
        self.assertIs(ext["observations"]["face_seen"], False)


@unittest.skipUnless(HAS_NUMPY and os.path.isfile(BACKEND_RULE_TABLE), "numpy or the backend's rule table missing")
class BackendReadsTheViewTests(unittest.TestCase):
    """The backend's rule table on origin/main reads the new view; the old keys (tag, evidence_ids) it reads as no
    situation. Scene 4-2: a pause of 4.5 s after choosing opens the highlight only with the lowered pause, which the
    looking_around tag gives (gaze left unknown so that only the tag can lower it)."""

    def setUp(self):
        from app.modules.vision.chain import WindowJudge
        rows = looking_around_rows()
        self.ext = WindowJudge(bundle()).evaluate(rows, rows[-1]["t_s"])["contract"]["extension"]
        self.window = {"t": 10.0, "measurable": True, "screen": "menu", "steps_left": 2, "gaze": None,
                       "pause_s": 4.5, "backs_recent": 0}

    def test_the_new_view_is_a_known_situation_and_lowers_the_pause(self):
        out = backend_window(**self.window, situation=self.ext["decision_situation"])
        self.assertTrue(out["known"])
        self.assertEqual(out["evidence"], {"dwell_no_touch": 1, "yaw_sweep_offscreen": 2})
        self.assertEqual((out["transition"], out["support"]), ("open", "highlight_next_action"))
        self.assertEqual(out["jev_situation"]["tag"], "looking_around")

    def test_the_old_keys_read_as_no_situation(self):
        out = backend_window(**self.window, situation=self.ext["situation"])
        self.assertFalse(out["known"])
        self.assertEqual(out["evidence"], {})
        self.assertEqual(out["transition"], "none")                       # 4.5 s is below the unlowered 8.0 s


# --- the touch entry ----------------------------------------------------------------------------------------------
# Keys of a vision value: none of them may appear in any answer of the touch entry (the order screen gets no vision).
VISION_KEYS = frozenset({"situation", "decision_situation", "tags", "scene_tags", "observations", "gaze",
                         "facing_screen", "face_seen", "vision", "measurable", "unknown_reason", "evidence"})


def vision_keys(value) -> set:
    """The vision keys anywhere in a JSON value."""
    if isinstance(value, dict):
        return (set(value) & VISION_KEYS).union(*(vision_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(vision_keys(v) for v in value))
    return set()


def iso_at(t: float) -> str:
    from app.modules.vision.touch_entry import iso
    return iso(EPOCH0 + t)


def window_body(t0, t1, tap=0, miss=0, back=0, **extra):
    """A touch window (t0, t1] of the fake clock, as the order screen sends it."""
    return {"window_start": iso_at(t0), "window_end": iso_at(t1), "screen_id": "menu",
            "touch": {"tap_count": tap, "miss_tap_count": miss, "repeat_tap_count": 0, "back_count": back,
                      "dwell_ms": 0}, **extra}


def camera_frame(row):
    """The frame behind a synthetic row: its camera time and its wall time on the fake clock."""
    return SimpleNamespace(t_s=row["t_s"], epoch_s=EPOCH0 + row["t_s"])


def timed_frames(n, size=(120, 160)):
    """Fake camera frames with a wall time (sources.Frame.epoch_s) on the fake clock."""
    import numpy as np
    from app.modules.vision.sources import Frame
    img = np.full((size[0], size[1], 3), 127, np.uint8)
    return [Frame(i, round(i * DT, 6), img, str(i), 0.0, EPOCH0 + i * DT) for i in range(n)]


def entry(rows=(), b=None):
    """A touch entry fed with the rows of a fake camera; its log lines in .lines."""
    from app.modules.vision.touch_entry import TouchEntry
    lines = []
    svc = TouchEntry(b or bundle(), log=lines.append)
    for row in rows:
        svc.add_row(row, camera_frame(row))
    svc.lines = lines
    return svc


def reporting(frames_, svc, at):
    """The frames, with the touch windows at[i] (a list of bodies) sent to the entry just before frame i is
    processed, as the order screen sends a window when it ends."""
    for frame in frames_:
        for body in at.get(frame.index, ()):
            code, _ = svc.receive(body)
            assert code == 202, (code, body)
        yield frame


@unittest.skipUnless(HAS_NUMPY, SKIP)
class ParseRequestTests(unittest.TestCase):
    def test_a_touch_window_is_read_and_checked(self):
        from app.modules.vision.touch_entry import parse_request
        req = parse_request(window_body(0.7, 2.7, tap=2, session_id="s1", wait_ms=150))   # other keys are ignored
        self.assertAlmostEqual(req.start, EPOCH0 + 0.7)
        self.assertAlmostEqual(req.end, EPOCH0 + 2.7)
        self.assertEqual(req.touch, {"tap_count": 2, "miss_tap_count": 0, "back_count": 0})
        self.assertEqual((req.session, req.screen), ("s1", "menu"))
        no_screen = {k: v for k, v in window_body(0.7, 2.7).items() if k != "screen_id"}
        self.assertEqual((parse_request(no_screen).session, parse_request(no_screen).screen), (None, None))
        bad = [[], {**window_body(0, 2), "window_end": "2027-01-15T08:00:02"},     # no zone
               window_body(2, 2), window_body(2, 1), {**window_body(0, 2), "touch": None},
               window_body(0, 2, tap=True), window_body(0, 2, tap=1.0), window_body(0, 2, miss=-1),
               {**window_body(0, 2), "touch": {"tap_count": 0, "miss_tap_count": 0}},   # no back_count
               window_body(0, 2, session_id=""), window_body(0, 2, session_id=3),
               {**window_body(0, 2), "screen_id": ""}, {**window_body(0, 2), "screen_id": 3}]
        for body in bad:
            with self.assertRaises(ValueError, msg=repr(body)):
                parse_request(body)


@unittest.skipUnless(HAS_NUMPY, SKIP)
class LiveTouchTests(unittest.TestCase):
    def test_sessions_presses_and_pruning(self):
        from app.modules.vision.touch_entry import LiveTouch
        tl = LiveTouch()
        zero = {"tap_count": 0, "miss_tap_count": 0, "back_count": 0}
        self.assertEqual((tl.session_at(5.0), tl.session_since(5.0), tl.last_press(5.0)), (None, None, None))
        self.assertIsNone(tl.counts(0.0, 1.0))                     # never known at frame time
        tl.report(0.0, 2.0, zero, "a")
        tl.report(2.0, 4.0, {**zero, "tap_count": 1}, "a")
        self.assertEqual((tl.session_at(1.0), tl.session_since(1.0)), ("a", 0.0))   # the first session is cut too
        self.assertEqual((tl.last_press(3.9), tl.last_press(4.0)), (None, 4.0))      # the window's end
        tl.report(2.0, 4.0, zero, "a")                             # a repeated window replaces its report
        self.assertEqual((len(tl.snapshot()), tl.presses, tl.last_press(5.0)), (2, [], None))   # and its press
        tl.report(6.0, 8.0, zero, "b")
        self.assertEqual((tl.session_at(6.0), tl.session_at(6.1), tl.session_since(7.0)), ("a", "b", 6.0))
        self.assertEqual(tl.session_since(6.0), 0.0)               # (6, 8] holds the times after 6.0: still a's
        tl.report(8.0, 10.0, {**zero, "tap_count": 2}, "b")
        tl.prune(9.0)
        self.assertEqual([(r.t0, r.t1) for r in tl.snapshot()], [(8.0, 10.0)])
        self.assertEqual((tl.presses, tl.sessions), ([10.0], [("b", 6.0)]))   # a ended before the kept rows
        tl.prune(11.0)
        self.assertEqual((tl.snapshot(), tl.presses), ([], [10.0]))   # the last press stays as the anchor

    def test_a_replaced_report_takes_its_press_with_it(self):
        from app.modules.vision.touch_entry import LiveTouch
        tl = LiveTouch()
        one, zero = {"tap_count": 1, "miss_tap_count": 0, "back_count": 0}, {"tap_count": 0, "miss_tap_count": 0,
                                                                             "back_count": 0}
        tl.report(0.0, 2.0, one, "a")
        tl.report(0.0, 2.0, one, "a")                              # the same window again: no second anchor
        self.assertEqual(tl.presses, [2.0])
        tl.report(0.0, 2.0, zero, "a")                             # corrected to no press: no stale anchor
        self.assertEqual((tl.presses, tl.last_press(9.0)), ([], None))
        tl.report(2.0, 4.0, one, "a")
        tl.prune(5.0)                                              # its rows left: the press stays as the anchor
        self.assertEqual((tl.presses, tl.last_press(9.0), tl.snapshot()), ([4.0], 4.0, []))
        tl.report(6.0, 8.0, one, "a")
        self.assertEqual(tl.presses, [4.0, 8.0])

    def test_a_day_of_orders_keeps_the_session_lists_bounded(self):
        """One session per 10 s, two 2 s windows each, the kept rows 7.5 s back (the test bundle's keep_s): the
        lists keep the session at the earliest kept time and the later ones, and the lookups stay right."""
        from app.modules.vision.touch_entry import LiveTouch
        tl = LiveTouch()
        zero = {"tap_count": 0, "miss_tap_count": 0, "back_count": 0}
        sizes = []
        for i in range(200):
            tl.report(10.0 * i, 10.0 * i + 2.0, zero, f"s{i}")
            tl.report(10.0 * i + 2.0, 10.0 * i + 4.0, zero, f"s{i}")
            tl.prune(10.0 * i + 4.0 - 7.5)
            sizes.append((len(tl.sessions), len(tl.until)))
            self.assertEqual((tl.session_at(10.0 * i + 3.0), tl.session_since(10.0 * i + 3.0), tl.touch_until(f"s{i}")),
                             (f"s{i}", 10.0 * i, 10.0 * i + 4.0))
        self.assertLessEqual(max(sizes), (2, 2))
        tl.report(1993.0, 1995.0, zero, "s198")                    # a late window of the previous order
        tl.prune(1990.0)
        self.assertIn("s198", dict(tl.sessions))                   # kept while a kept report names it
        tl.prune(2000.0)
        self.assertEqual([s for s, _ in tl.sessions], ["s199"])


@unittest.skipUnless(HAS_NUMPY, SKIP)
class PlaceTouchTests(unittest.TestCase):
    def setUp(self):
        from app.modules.vision.touch_entry import Report
        self.R = Report
        self.rows = rows_of(facing(60), extra=LIVE)               # 0.0 .. 5.9 s

    def place(self, reports, w0=1.0, w1=4.0):
        from app.modules.vision.touch_entry import place_touch
        out = place_touch(self.rows, reports, w0, w1)
        return {round(r["t_s"], 1): (r["tap_count"], r["miss_tap_count"]) for r in out}

    def test_zero_windows_give_zero_and_rows_outside_stay_blank(self):
        got = self.place([self.R(-2.0, 0.0, 0, 0, 0, None), self.R(0.0, 2.0, 0, 0, 0, None),
                          self.R(2.0, 4.0, 0, 0, 0, None)])
        self.assertTrue(all(got[t] == (0, 0) for t in got if 1.0 <= t <= 4.0))
        self.assertTrue(all(got[t] == (None, None) for t in got if t < 1.0 or t > 4.0))
        self.assertIsNone(self.rows[20]["tap_count"])              # rows are copied, not changed in place

    def test_a_window_with_presses_inside_puts_them_on_its_last_row(self):
        got = self.place([self.R(0.0, 2.0, 0, 0, 0, None), self.R(2.0, 4.0, 2, 1, 0, None)])
        self.assertEqual(got[4.0], (2, 1))
        self.assertTrue(all(got[t] == (None, None) for t in got if 2.0 < t < 4.0))
        self.assertTrue(all(got[t] == (0, 0) for t in got if 1.0 <= t <= 2.0))
        got = self.place([self.R(2.0, 4.0, 2, 0, 0, None)])
        self.assertEqual((got[4.0], got[3.0]), ((2, 0), (None, 0)))   # no miss anywhere: misses are 0

    def test_a_window_across_the_start_gaps_and_overlaps_stay_blank(self):
        got = self.place([self.R(0.0, 2.0, 1, 0, 0, None), self.R(2.0, 4.0, 0, 0, 0, None)])
        self.assertTrue(all(got[t] == (None, 0) for t in got if 1.0 <= t <= 2.0))   # where was the press?
        got = self.place([self.R(2.5, 4.0, 0, 0, 0, None)])
        self.assertTrue(all(got[t] == (None, None) for t in got if 1.0 <= t <= 2.5))   # no report: not measured
        got = self.place([self.R(1.0, 3.0, 0, 0, 0, None), self.R(2.0, 4.0, 0, 0, 0, None)])
        self.assertEqual((got[2.5], got[1.5], got[3.5]), ((None, None), (0, 0), (0, 0)))

    def test_the_no_touch_tags_need_reported_windows(self):
        from app.modules.vision.chain import unknown_reasons
        from app.modules.vision.situation import assess
        from app.modules.vision.touch_entry import place_touch
        sp = bundle().situation
        rows = rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(10), extra=LIVE)
        t = rows[-1]["t_s"]
        zero = [self.R(-3.5, -1.3, 0, 0, 0, None), self.R(-1.3, 0.7, 0, 0, 0, None), self.R(0.7, t, 0, 0, 0, None)]
        name = (lambda rs: assess(rs, t, sp, landmarker_num_faces=1)[0]["name"])
        self.assertEqual(name(place_touch(rows, zero, t - sp.window_s, t)), "looking_around")
        self.assertEqual(name(rows), "unknown")
        reasons = unknown_reasons(rows, t, sp)
        self.assertIn("column:tap_count", {m for r in reasons for m in r.get("missing", [])})
        pressed = zero[:2] + [self.R(0.7, t, 1, 0, 0, None)]
        self.assertNotEqual(name(place_touch(rows, pressed, t - sp.window_s, t)), "looking_around")

    def test_the_entry_places_the_windows_it_receives(self):
        """The bodies the order screen sends become the same reports the tests above place (fake clock: camera
        time = wall time - EPOCH0)."""
        rows = rows_of(facing(60), extra=LIVE)
        svc = entry(rows)
        for body in (window_body(0.0, 2.0), window_body(2.0, 4.0, tap=2, miss=1, session_id="s1")):
            self.assertEqual(svc.receive(body), (202, {"status": "accepted"}))
        self.assertEqual(svc.touch.snapshot(), [self.R(0.0, 2.0, 0, 0, 0, None, "menu"),
                                                self.R(2.0, 4.0, 2, 1, 0, "s1", "menu")])
        got = self.place(svc.touch.snapshot())
        self.assertEqual(got[4.0], (2, 1))
        self.assertTrue(all(got[t] == (0, 0) for t in got if 1.0 <= t <= 2.0))


@unittest.skipUnless(HAS_NUMPY, SKIP)
class TouchEntryTests(unittest.TestCase):
    def test_a_touch_window_is_accepted_and_kept(self):
        svc = entry(rows_of(facing(30), extra=LIVE))
        self.assertEqual(svc.receive(window_body(0.7, 2.7, tap=1, session_id="s1")), (202, {"status": "accepted"}))
        self.assertEqual([(r.t0, r.t1, r.tap, r.session, r.screen) for r in svc.touch.snapshot()],
                         [(0.7, 2.7, 1, "s1", "menu")])
        status = svc.status()
        self.assertEqual(status["touch"], {"windows": 1, "last": {"window_start": iso_at(0.7),
                                                                   "window_end": iso_at(2.7),
                                                                   "session_id": "s1", "screen_id": "menu"}})
        self.assertEqual((status["status"], status["frames"]), ("running", 30))
        self.assertEqual(len(svc.lines), 1)

    def test_before_the_first_frame_and_after_the_stop_a_window_is_refused(self):
        svc = entry()
        code, out = svc.receive(window_body(0.0, 2.0))
        self.assertEqual((code, out["status"]), (503, "refused"))
        self.assertIn("no camera frame yet", out["reason"])
        for row in rows_of(facing(30), extra=LIVE):
            svc.add_row(row, camera_frame(row))
        svc.stop("--seconds reached")
        code, out = svc.receive(window_body(1.0, 2.9))
        self.assertEqual((code, out["status"]), (503, "refused"))
        self.assertIn("--seconds reached", out["reason"])
        self.assertEqual((svc.touch.snapshot(), svc.status()["status"]), ([], "stopped"))

    def test_a_malformed_body_is_refused_with_its_reason(self):
        svc = entry(rows_of(facing(30), extra=LIVE))
        code, out = svc.receive({"window_start": "now"})
        self.assertEqual((code, out["status"]), (400, "refused"))
        self.assertIn("window_start", out["reason"])
        with self.assertRaises(ValueError):
            svc.add_row({"t_s": 0.0}, SimpleNamespace(t_s=0.0, epoch_s=None))

    def test_the_reports_are_kept_as_long_as_the_rows(self):
        rows = rows_of(facing(200), extra=LIVE)                     # to 19.9 s; keep_s = 6 + 0.5 + 1 = 7.5 s here
        svc = entry(rows[:50])
        svc.receive(window_body(3.0, 5.0))
        for row in rows[50:]:
            svc.add_row(row, camera_frame(row))
        self.assertEqual(svc.keep_s, 7.5)
        self.assertEqual(svc.touch.snapshot(), [])                  # ended before the kept rows
        self.assertEqual(svc.status()["camera"]["kept_from_at"], iso_at(12.4))

    def test_the_runners_window_reads_the_reported_touch_as_a_replay_reads_its_log(self):
        """The rows of the runner's window with the touch the entry received give the situation a replay gives on
        the same rows with zero touch on every row; without a reported window it cannot tell."""
        from app.modules.vision.chain import WindowJudge
        rows = rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(10), extra=LIVE)
        t = rows[-1]["t_s"]
        svc = entry(rows)
        unknown = WindowJudge(bundle()).evaluate(svc.window_rows(rows, t), t)["situation"]
        self.assertEqual(unknown["name"], "unknown")
        self.assertIn("column:tap_count", {m for r in unknown["unknown_reason"] for m in r.get("missing", [])})
        for t0, t1 in ((-3.5, -1.3), (-1.3, 0.7), (0.7, t)):
            svc.receive(window_body(t0, t1))
        live = WindowJudge(bundle()).evaluate(svc.window_rows(rows, t), t)
        replay = WindowJudge(bundle()).evaluate(rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(10)), t)
        self.assertEqual(live["situation"], replay["situation"])
        self.assertEqual(live["situation"]["name"], "looking_around")
        self.assertEqual(live["contract"]["extension"]["decision_situation"],
                         replay["contract"]["extension"]["decision_situation"])

    def test_a_new_session_reads_only_its_own_rows(self):
        """Two sweeps before 3.0 s, facing after: the window at 5.0 is looking_around in the first session and not in
        a session that starts at 3.0 s, whose window does not read the sweeps."""
        from app.modules.vision.chain import WindowJudge
        rows = rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(36), extra=LIVE)   # to 5.3 s
        names = {}
        for second in ("a", "b"):
            svc = entry(rows)
            for t0, t1 in ((-3.0, -1.0), (-1.0, 1.0), (1.0, 3.0)):
                svc.receive(window_body(t0, t1, session_id="a"))
            svc.receive(window_body(3.0, 5.0, session_id=second))
            read = svc.window_rows(rows, 5.0)
            names[second] = WindowJudge(bundle()).evaluate(read, 5.0)["situation"]["name"]
            self.assertEqual(min(r["t_s"] for r in read), 0.0 if second == "a" else 3.1)
        self.assertEqual((svc.touch.session_since(5.0), svc.touch.session_at(5.0)), (3.0, "b"))
        self.assertEqual(names["a"], "looking_around")
        self.assertNotEqual(names["b"], "looking_around")

    def test_the_first_session_after_the_start_is_cut_too(self):
        """The runner saw the two sweeps before any session; the first session starts at 3.0 s, so its window at 5.0
        reads only its own rows, and every one of them has its touch (no rows from before the session)."""
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.events import window_any_tap
        rows = rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(36), extra=LIVE)   # to 5.3 s
        svc = entry(rows)
        svc.receive(window_body(3.0, 5.0, session_id="s1"))           # the first touch window after the start
        read = svc.window_rows(rows, 5.0)
        self.assertEqual((svc.touch.session_since(5.0), min(r["t_s"] for r in read)), (3.0, 3.1))
        self.assertIs(window_any_tap(read, (5.0 - bundle().situation.window_s, 5.0)), False)   # touch known
        self.assertNotEqual(WindowJudge(bundle()).evaluate(read, 5.0)["situation"]["name"], "looking_around")
        self.assertIsNone(svc.touch.session_since(3.0))              # (3, 5] holds the times after 3.0

    def test_no_answer_carries_a_vision_value(self):
        svc = entry()
        answers = [svc.receive(window_body(0.0, 2.0))[1], svc.status()]          # before the first frame
        for row in rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(10), extra=LIVE):
            svc.add_row(row, camera_frame(row))
        answers += [svc.receive(window_body(0.7, 2.7, tap=1, session_id="s1"))[1], svc.receive([])[1],
                    svc.status()]
        svc.stop("input ended")
        answers += [svc.receive(window_body(2.7, 4.7))[1], svc.status()]
        for out in answers:
            self.assertEqual(vision_keys(out), set(), out)


@unittest.skipUnless(HAS_CV2, SKIP)
class LiveEntryTests(unittest.TestCase):
    def test_the_press_anchor_and_a_new_session_reach_the_face_size_reference(self):
        from app.modules.vision.chain import FrameChain
        frames_ = timed_frames(30)
        svc = entry()
        chain = FrameChain(FakeModels([fake_inference() for _ in frames_]), bundle().chain, timeline=svc.touch)
        ratios = []
        for frame in frames_:
            if frame.index == 10:                    # the screen reports a press in (-1.0, 0.9]
                svc.receive(window_body(-1.0, 0.9, tap=1, session_id="s1"))
            if frame.index == 20:                    # a new session, no press yet
                svc.receive(window_body(1.5, 1.9, session_id="s2"))
            row = chain.process(frame)
            svc.add_row(row, frame)
            ratios.append(row["iod_ratio_user"])
        self.assertTrue(all(r is None for r in ratios[:10]))        # no press reported: nothing collected
        self.assertTrue(all(r is not None for r in ratios[11:20]))  # the first collected row only starts it
        self.assertTrue(all(r is None for r in ratios[20:]))        # the new session waits for its own press
        plain = FrameChain(FakeModels([fake_inference() for _ in frames_]), bundle().chain)
        self.assertIsNotNone([plain.process(f)["iod_ratio_user"] for f in frames_[:2]][1])   # without it: as before

    def test_the_first_session_resets_the_tracking_from_before_it(self):
        """The head tracker chose a main user before any order session; when the first session arrives the live
        runner's chain starts its per-session state again (a new main-user track), as at every later change. A
        timeline without the FIRST_SESSION_RESETS mark (a replay's touch log) keeps the state at its first session."""
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.touch_entry import LiveTouch

        class LogLike(LiveTouch):            # the same lookups, without the live entry's mark
            FIRST_SESSION_RESETS = False
        zero = {"tap_count": 0, "miss_tap_count": 0, "back_count": 0}
        frames_ = timed_frames(40)

        def tracks(timeline):
            chain = FrameChain(FakeModels([fake_inference() for _ in frames_]), bundle().chain, FakeHeads(),
                               FakeDirection(), timeline=timeline)
            out = []
            for frame in frames_:
                if frame.index == 10:
                    timeline.report(-1.0, 0.9, zero, "s1")           # the first order session
                if frame.index == 25:
                    timeline.report(2.0, 2.4, zero, "s2")            # the next one
                out.append(chain.process(frame)["primary_track"])
            return out
        live, log = tracks(LiveTouch()), tracks(LogLike())
        self.assertEqual((set(live[:10]), set(live[10:25]), set(live[25:])), ({1}, {2}, {3}))
        self.assertEqual((set(log[:25]), set(log[25:])), ({1}, {2}))   # as before: only the change resets
        plain = FrameChain(FakeModels([fake_inference() for _ in frames_]), bundle().chain, FakeHeads(), FakeDirection())
        self.assertEqual({plain.process(f)["primary_track"] for f in frames_}, {1})   # no timeline: as before

    def test_run_live_reads_the_touch_windows_and_stops_the_entry(self):
        from app.modules.vision.live import run_live
        sched = [fake_inference(y) for y in yaw_schedule()]

        def run(service, at):
            lines = []
            src = timed_frames(len(sched)) if service is None else reporting(timed_frames(len(sched)), service, at)
            meta = run_live(src, bundle(), models=FakeModels(sched), detector=FakeHeads(), direction=FakeDirection(),
                            print_fn=lines.append, entry=service)
            return meta, {line.split("초]")[0].strip("[ "): line for line in lines}

        _, plain = run(None, {})
        svc = entry()                    # the screen sends each 2 s window when it ends (frame 20 = 2.0 s, ...)
        meta, lines = run(svc, {1: [window_body(-2.0, 0.0)], 20: [window_body(0.0, 2.0)], 40: [window_body(2.0, 4.0)]})
        self.assertEqual((svc.frames, svc.stopped), (meta["frames"], "input ended"))
        self.assertIn("column:tap_count", plain["4.0"])            # no touch input: the no-touch cue is unknown
        self.assertIn("상황 looking_around", lines["4.0"])          # every row of the window covered by a report
        self.assertIn("column:tap_count", lines["3.0"])            # (2, 3] not reported yet at 3.0: blank
        self.assertIn("column:tap_count", lines["5.0"])            # nor (4, 5] at 5.0 (no later window came)
        self.assertEqual(svc.receive(window_body(6.0, 8.0))[0], 503)
        with self.assertRaises(ValueError):                         # frames without a wall time
            from test_vision_chain import frames
            run_live(frames(3), bundle(), models=FakeModels(sched), entry=entry(), print_fn=[].append)

    def test_an_unbounded_run_keeps_no_per_frame_or_per_window_rows(self):
        from app.modules.vision.live import RunTiming, UnloggedJev, keeps_timing, parse_args, run_live
        n = 300                                                     # 30 s of the fake camera
        runs = {}
        for keep in (False, True):
            timing = RunTiming(keep)
            meta = run_live(timed_frames(n), bundle(), models=FakeModels([fake_inference()] * n), detector=FakeHeads(),
                            direction=FakeDirection(), print_fn=[].append, entry=entry(), timing=timing)
            runs[keep] = (len(timing.rows), len(timing.windows), meta["frames"], meta["windows"], meta["timing_ms"])
        self.assertEqual(runs[False], (0, 0, n, 30, None))          # counted, nothing kept
        self.assertEqual(runs[True][:4], (n, 30, n, 30))            # bounded or --out: kept for the summary
        self.assertIsNotNone(runs[True][4]["ms_chain"])
        jev = UnloggedJev()
        self.assertEqual((jev.ask("fit", {"q": 1})["kind"], jev.log), ("fit", []))   # the record keeps the question
        base = ["--camera", "0", "--no-window"]
        with redirect_stderr(io.StringIO()):
            self.assertEqual([keeps_timing(parse_args(base + extra)) for extra in ([], ["--seconds", "5"], ["--out", "o"])],
                             [False, True, True])

    def test_the_unbounded_run_line_is_printed_only_with_serve(self):
        from app.modules.vision.live import parse_args, unbounded_note
        base = ["--camera", "0", "--no-window"]
        with redirect_stderr(io.StringIO()):
            notes = {tuple(extra): unbounded_note(parse_args(base + extra))
                     for extra in ([], ["--serve", "0"], ["--serve", "0", "--seconds", "5"], ["--serve", "0", "--out", "o"])}
        self.assertIsNone(notes[()])                                 # every new option unset: no new console line
        self.assertIn("--seconds", notes[("--serve", "0")])
        self.assertEqual([notes[("--serve", "0", "--seconds", "5")], notes[("--serve", "0", "--out", "o")]], [None, None])

    def test_the_command_line_switches(self):
        from app.modules.vision.live import parse_args
        a = parse_args(["--camera", "0", "--no-window", "--seconds", "1", "--serve", "0", "--allow-origin", ORIGIN])
        self.assertEqual((a.serve, a.allow_origin), (0, [ORIGIN]))
        self.assertIsNone(parse_args(["--camera", "0", "--no-window", "--seconds", "1"]).serve)
        for argv in (["--allow-origin", ORIGIN], ["--serve", "70000"], ["--serve", "-1"]):
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                parse_args(["--camera", "0", "--no-window", "--seconds", "1", *argv])


@unittest.skipUnless(HAS_NUMPY, SKIP)
class HttpTests(unittest.TestCase):
    def setUp(self):
        from app.modules.vision.touch_entry import start_server
        self.svc = entry(rows_of(facing(30), extra=LIVE))
        self.server = start_server(self.svc, 0, [ORIGIN])
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None, headers=None):
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 127.0.0.1 directly, no proxy
        try:
            with opener.open(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_a_touch_window_over_http_with_cors_for_the_order_screen(self):
        code, headers, data = self.call("POST", "/touch-windows", window_body(0.9, 2.9), {"Origin": ORIGIN})
        self.assertEqual((code, json.loads(data)), (202, {"status": "accepted"}))
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), ORIGIN)
        self.assertTrue(headers.get("Content-Type", "").startswith("application/json"))
        code, headers, data = self.refused("POST", "/touch-windows", {"Origin": "http://elsewhere.test"})
        self.assertEqual((code, json.loads(data)["status"]), (403, "refused"))   # another page may not post
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.call("POST", "/touch-windows", window_body(2.9, 4.9))[0], 202)   # a local tool
        self.assertEqual([r.t0 for r in self.svc.touch.snapshot()], [0.9, 2.9])

    def test_preflight_status_and_errors(self):
        code, headers, _ = self.call("OPTIONS", "/touch-windows", headers={
            "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true"})
        self.assertEqual(code, 204)
        self.assertIn("POST", headers.get("Access-Control-Allow-Methods", ""))
        self.assertEqual(headers.get("Access-Control-Allow-Private-Network"), "true")
        code, _, data = self.call("GET", "/status")
        status = json.loads(data)
        self.assertEqual((code, status["status"], status["frames"]), (200, "running", 30))
        self.assertEqual(status["camera"]["latest_frame_at"], iso_at(2.9))
        self.assertEqual(self.call("GET", "/other")[0], 404)
        self.assertEqual(self.refused("POST", "/window")[0], 404)                    # one path, no alias
        self.assertEqual(self.call("POST", "/touch-windows", b"{not json")[0], 400)
        code, _, data = self.call("POST", "/touch-windows", {"window_start": 1})
        self.assertEqual((code, json.loads(data)["status"]), (400, "refused"))

    def refused(self, method, path, headers=None):
        """A request its headers alone get refused: this entry's Host and a Content-Length are sent, the body never is
        (the entry answers without reading it; were it to read, the answer would not come before the timeout)."""
        port = self.server.server_address[1]
        return self.raw(method, path, {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json",
                                       "Content-Length": "1000", **(headers or {})})

    def raw(self, method, path, headers, body=None):
        """A request with exactly these headers (http.client, no Host or length added): the cases urllib does not
        send."""
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for key, value in headers.items():
                conn.putheader(key, value)
            conn.endheaders(body)
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def test_only_this_entrys_host_is_served(self):
        port = self.server.server_address[1]
        data = json.dumps(window_body(0.9, 2.9)).encode("utf-8")
        for host, code in ((f"127.0.0.1:{port}", 200), (f"localhost:{port}", 200), (f"LOCALHOST:{port}", 200),
                           (f"rebind.example:{port}", 403), (f"127.0.0.1:{port + 1}", 403), ("127.0.0.1", 403)):
            self.assertEqual(self.raw("GET", "/status", {"Host": host})[0], code, host)
        self.assertEqual(self.raw("GET", "/status", {})[0], 403)                       # no Host at all
        code, _, out = self.raw("POST", "/touch-windows", {"Host": f"192.168.0.5:{port}",
                                                           "Content-Length": str(len(data))})   # body never sent
        self.assertEqual((code, json.loads(out)["status"]), (403, "refused"))
        self.assertEqual(self.raw("OPTIONS", "/touch-windows", {"Host": f"rebind.example:{port}", "Origin": ORIGIN})[0],
                         403)
        self.assertEqual(self.svc.touch.snapshot(), [])                                 # nothing was taken
        refused = [line for line in self.svc.lines if line.startswith("[터치 입구] Host")]
        self.assertEqual(len(refused), 5)                            # once per Host value: rebind.example twice

    def test_status_has_no_cors_header_and_a_bad_length_is_refused(self):
        port = self.server.server_address[1]
        code, headers, _ = self.call("GET", "/status", headers={"Origin": ORIGIN})
        self.assertEqual(code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)       # pages cannot read it
        code, headers, _ = self.call("OPTIONS", "/status", headers={"Origin": ORIGIN,
                                                                     "Access-Control-Request-Method": "GET"})
        self.assertEqual(code, 204)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        host = {"Host": f"127.0.0.1:{port}"}
        for length in ("-1", "abc", "+5", "1_0"):
            code, _, out = self.raw("POST", "/touch-windows", {**host, "Content-Length": length})
            self.assertEqual((code, json.loads(out)["status"]), (400, "refused"), length)
        self.assertEqual(self.raw("POST", "/touch-windows", host)[0], 411)

    def test_a_refused_origin_is_logged_once_with_the_hint(self):
        from app.modules.vision.touch_entry import ORIGIN_HINT_KO
        other = "http://localhost:5173"                               # the same screen under the other name
        for _ in range(2):
            self.assertEqual(self.refused("POST", "/touch-windows", {"Origin": other})[0], 403)
        code, headers, _ = self.call("OPTIONS", "/touch-windows", headers={"Origin": "http://elsewhere.test",
                                                                            "Access-Control-Request-Method": "POST"})
        self.assertEqual(code, 204)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        refused = [line for line in self.svc.lines if line.startswith("[터치 입구] 허용하지 않은 출처")]
        self.assertEqual(len(refused), 2)                            # one per origin, not one per request
        self.assertIn(other, refused[0])
        self.assertTrue(all(ORIGIN_HINT_KO in line for line in refused))
        self.assertIn("--allow-origin", json.loads(self.refused("POST", "/touch-windows", {"Origin": other})[2])["reason"])

    def test_the_start_lines_name_the_order_screens_variable(self):
        from app.modules.vision.live import entry_lines
        lines = entry_lines(8765, [ORIGIN])
        self.assertIn("VITE_AI_ENGINE_URL=http://127.0.0.1:8765", lines)   # the exact line, alone
        self.assertTrue(any("AI_ENGINE_URL" in line and "ai-engine" in line and line.startswith("↑") for line in lines))
        self.assertIn("http://127.0.0.1:8765/touch-windows", lines[0])

    def test_a_fault_in_taking_the_window_is_a_500_answer(self):
        lines = []
        self.svc.log = lines.append

        def broken(body):
            raise KeyError("t_s")
        self.svc.receive = broken
        code, _, data = self.call("POST", "/touch-windows", window_body(0.9, 2.9))
        self.assertEqual((code, json.loads(data)), (500, {"status": "error", "reason": "KeyError: 't_s'"}))
        self.assertEqual(len(lines), 1)

    def test_no_http_answer_carries_a_vision_value(self):
        calls = [("POST", "/touch-windows", window_body(0.9, 2.9, tap=1, session_id="s1"), {"Origin": ORIGIN}),
                 ("POST", "/touch-windows", b"{not json", None), ("POST", "/touch-windows", {"touch": {}}, None),
                 ("GET", "/status", None, None), ("GET", "/other", None, None)]
        answers = [(m, p, self.call(m, p, b, h)) for m, p, b, h in calls]
        answers += [(m, p, self.refused(m, p, h)) for m, p, h in (("POST", "/touch-windows",
                                                                    {"Origin": "http://elsewhere.test"}),
                                                                   ("POST", "/other", None))]
        for method, path, (code, _, data) in answers:
            self.assertEqual(vision_keys(json.loads(data)), set(), (method, path, code))

    def test_a_refused_request_is_answered_without_reading_its_body_and_closed(self):
        import socket
        port = self.server.server_address[1]
        heads = (f"POST /touch-windows HTTP/1.1\r\nHost: rebind.example:{port}\r\n",                     # Host
                 f"POST /other HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n",                                    # path
                 f"POST /touch-windows HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: http://elsewhere.test\r\n")
        for head, code in zip(heads, (b"403", b"404", b"403")):
            with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                s.sendall((head + "Content-Type: application/json\r\nContent-Length: 1000\r\n\r\n").encode("ascii"))
                got = b""
                while chunk := s.recv(4096):                # ends only when the entry closes the connection
                    got += chunk
            self.assertEqual(got.split(b"\r\n", 1)[0].split()[1], code, head)   # answered with no body sent
            self.assertIn(b"Connection: close", got)
        self.assertEqual(self.svc.touch.snapshot(), [])


# --- the tag sender -----------------------------------------------------------------------------------------------
PAYLOAD_KEYS = {"session_id", "window_start", "window_end", "situation", "observations", "model_version"}


class StubBackend:
    """A backend stand-in on 127.0.0.1 that records every POST as (path, JSON body). code = the status it answers;
    hold = an Event the first request waits on before it is answered (a slow backend); delay = seconds every request
    takes before its answer (a slow backend that still answers within the sender's timeout)."""

    def __init__(self, code=201, hold=None, delay=0.0):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        self.received, self.arrived = [], threading.Event()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                stub.received.append((self.path, body))
                stub.arrived.set()
                if hold is not None and len(stub.received) == 1:
                    hold.wait(10)
                time.sleep(delay)
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{}")
                except OSError:                 # the sender gave up waiting (its timeout) and closed
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def closed_port_url() -> str:
    """A base address where nothing listens (a port the OS gave and that was released)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def payload(end, session="s1"):
    """A small window to send (the sender does not look inside)."""
    return {"session_id": session, "window_start": iso_at(end - 1.0), "window_end": iso_at(end),
            "situation": {"name": "unknown", "evidence": [], "confidence": "unknown"},
            "observations": {"gaze": None, "face_seen": False, "scene_tags": []}, "model_version": "test"}


@unittest.skipUnless(HAS_NUMPY, SKIP)
class TagSenderTests(unittest.TestCase):
    def setUp(self):
        self.stubs = []

    def tearDown(self):
        for stub in self.stubs:
            stub.close()

    def stub(self, **kw):
        self.stubs.append(StubBackend(**kw))
        return self.stubs[-1]

    def test_the_payload_of_a_window_and_its_target(self):
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.contract_view import MODEL_VERSION
        from app.modules.vision.tag_sender import TagSender, target, vision_window
        rows = looking_around_rows()
        t = rows[-1]["t_s"]
        rec = WindowJudge(bundle()).evaluate(rows, t)
        ext = rec["contract"]["extension"]
        body = vision_window(rec, "s1", lambda s: EPOCH0 + s)
        self.assertEqual(set(body), PAYLOAD_KEYS)
        self.assertEqual((body["session_id"], body["window_start"], body["window_end"]),
                         ("s1", iso_at(rec["segment_s"][0]), iso_at(t)))
        self.assertEqual(body["situation"], ext["decision_situation"])       # the decision layer's keys
        self.assertEqual(body["situation"]["name"], "looking_around")
        self.assertEqual(body["observations"], ext["observations"])
        self.assertEqual(body["model_version"], MODEL_VERSION)
        self.assertEqual(target("http://kiosk.test/", "a/b c"), "http://kiosk.test/api/v1/sessions/a%2Fb%20c/vision-windows")
        stub = self.stub()
        sender = TagSender(stub.url, 1.0)
        sender.offer(body)
        stats = sender.close()
        self.assertEqual((stats["sent"], stats["failed"], stats["offered"]), (1, 0, 1))
        self.assertEqual(stub.received, [("/api/v1/sessions/s1/vision-windows", json.loads(json.dumps(body)))])

    def test_a_newer_release_replaces_an_unsent_release_as_a_whole(self):
        """The mailbox item is a release (the windows one evaluation released together): a newer release replaces an
        unsent one with all its windows, and a release under way is posted to its end, in order."""
        from app.modules.vision.tag_sender import TagSender
        hold = threading.Event()
        stub = self.stub(hold=hold)
        sender = TagSender(stub.url, 10.0)
        sender.offer_release([payload(1.0), payload(2.0)])
        self.assertTrue(stub.arrived.wait(10))                     # the first send is under way, held
        sender.offer_release([payload(3.0), payload(4.0)])          # returns at once: the backend is still busy
        sender.offer_release([payload(5.0), payload(6.0)])          # replaces the unsent release, both windows
        self.assertEqual(sender.stats()["replaced"], 2)
        hold.set()
        stats = sender.close()
        self.assertEqual([b["window_end"] for _, b in stub.received], [iso_at(t) for t in (1.0, 2.0, 5.0, 6.0)])
        self.assertEqual({k: stats[k] for k in ("offered", "sent", "failed", "replaced", "unsent_at_close")},
                         {"offered": 6, "sent": 4, "failed": 0, "replaced": 2, "unsent_at_close": 0})

    def test_a_failed_send_is_counted_and_dropped(self):
        from app.modules.vision.tag_sender import TagSender
        stub = self.stub(code=500)
        lines = []
        sender = TagSender(stub.url, 1.0, log=lines.append)
        sender.offer(payload(1.0))
        stats = sender.close()
        self.assertEqual((stats["sent"], stats["failed"], len(stub.received)), (0, 1, 1))   # sent once, no retry
        self.assertIn("500", stats["last_error"])
        self.assertEqual(len(lines), 1)
        dead = TagSender(closed_port_url(), 1.0)
        dead.offer(payload(1.0))
        self.assertEqual(dead.close()["sent"], 0)

    def test_an_ended_session_is_not_offered_again_until_a_new_session_comes(self):
        from app.modules.vision.tag_sender import TagSender

        def wait_for(check):                     # the sends run on the sender's thread
            deadline = time.monotonic() + 10
            while not check() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(check())
        for code in (410, 404):
            stub = self.stub(code=code)
            lines = []
            sender = TagSender(stub.url, 1.0, log=lines.append)
            sender.offer(payload(1.0, "s1"))
            wait_for(lambda: sender.stats()[f"ended_{code}"] == 1)
            sender.offer(payload(2.0, "s1"))                         # the same session: not sent
            sender.offer(payload(3.0, "s2"))                         # a new session id: sent
            wait_for(lambda: sender.stats()[f"ended_{code}"] == 2)
            stats = sender.close()
            self.assertEqual([p.split("/")[4] for p, _ in stub.received], ["s1", "s2"])
            self.assertEqual({k: stats[k] for k in ("offered", "sent", "failed", "skipped_ended", f"ended_{code}")},
                             {"offered": 3, "sent": 0, "failed": 0, "skipped_ended": 1, f"ended_{code}": 2})
            self.assertEqual(len(lines), 1)                          # the first answer of its kind, printed once
            self.assertIn(f"({code})", lines[0])

    def test_the_base_address_is_checked(self):
        from app.modules.vision.tag_sender import check_base_url
        self.assertEqual(check_base_url("http://127.0.0.1:8000"), "http://127.0.0.1:8000")
        for bad in ("127.0.0.1:8000", "ftp://host", "http://", "http://host/?a=1"):
            with self.assertRaises(ValueError, msg=bad):
                check_base_url(bad)


@unittest.skipUnless(HAS_CV2, SKIP)
class LiveSenderTests(unittest.TestCase):
    def setUp(self):
        self.stubs = []

    def tearDown(self):
        for stub in self.stubs:
            stub.close()

    def run_with(self, url, at):
        """run_live on the fake camera with the touch entry and a sender to url; at = touch windows by frame."""
        from app.modules.vision.live import run_live
        from app.modules.vision.tag_sender import TagSender
        sched = [fake_inference(y) for y in yaw_schedule()]
        svc = entry()
        sender = TagSender(url, bundle().chain.segment_s)
        meta = run_live(reporting(timed_frames(len(sched)), svc, at), bundle(), models=FakeModels(sched),
                        detector=FakeHeads(), direction=FakeDirection(), print_fn=[].append, entry=svc,
                        sender=sender)
        return meta, len(sched)

    def test_windows_are_sent_only_in_a_session_the_touch_windows_named(self):
        stub = StubBackend()
        self.stubs.append(stub)
        meta, _ = self.run_with(stub.url, {})
        self.assertEqual((meta["tag_sender"]["offered"], stub.received), (0, []))   # no touch window: nothing sent
        meta, _ = self.run_with(stub.url, {20: [window_body(0.0, 2.0, session_id="s1")],
                                           40: [window_body(2.0, 4.0, session_id="s1")]})
        s = meta["tag_sender"]
        self.assertEqual(s["offered"], 5)                          # 2.0, 3.0, 4.0, 5.0 and the last 5.9; not 1.0
        self.assertEqual(len(stub.received) + s["replaced"] + s["unsent_at_close"], s["offered"])   # each offer once
        self.assertFalse(s["open_at_close"])
        self.assertTrue(stub.received)
        for path, body in stub.received:
            self.assertEqual((path, set(body), body["session_id"]), ("/api/v1/sessions/s1/vision-windows",
                                                                     PAYLOAD_KEYS, "s1"))
        self.assertEqual(stub.received[-1][1]["window_end"], iso_at(5.9))   # the last window is sent at the close
        ends = [b["window_end"] for _, b in stub.received]
        self.assertEqual(ends, sorted(ends))

    def test_a_dead_or_slow_backend_does_not_stop_the_loop(self):
        windows = {20: [window_body(0.0, 2.0, session_id="s1")], 40: [window_body(2.0, 4.0, session_id="s1")]}
        meta, n = self.run_with(closed_port_url(), windows)
        self.assertEqual((meta["frames"], meta["windows"], meta["tag_sender"]["sent"]), (n, 6, 0))
        self.assertGreaterEqual(meta["tag_sender"]["failed"], 1)
        hold = threading.Event()
        stub = StubBackend(hold=hold)
        self.stubs.append(stub)
        try:
            meta, n = self.run_with(stub.url, windows)              # the first send is never answered in time
        finally:
            hold.set()
        self.assertEqual((meta["frames"], meta["windows"], meta["tag_sender"]["offered"]), (n, 6, 5))

    def test_with_a_backend_the_console_labels_the_local_rule_table(self):
        from app.modules.vision.live import run_live
        from app.modules.vision.tag_sender import TagSender
        sched = [fake_inference(y) for y in yaw_schedule()]
        for sender in (None, TagSender(closed_port_url(), bundle().chain.segment_s)):
            lines = []
            run_live(timed_frames(len(sched)), bundle(), models=FakeModels(sched), detector=FakeHeads(),
                     direction=FakeDirection(), print_fn=lines.append, entry=entry(), sender=sender)
            windows = [line for line in lines if "초] 상황 " in line]
            self.assertEqual(len(windows), 6)
            label = " | 판단 " if sender is None else " | 로컬 규칙표 "
            self.assertTrue(all(label in line for line in windows), (label, windows[0]))

    def test_the_sender_needs_the_entry_and_its_switch_needs_serve(self):
        from app.modules.vision.live import parse_args, run_live
        from app.modules.vision.tag_sender import TagSender
        sender = TagSender(closed_port_url(), 1.0)
        with self.assertRaises(ValueError):
            run_live(timed_frames(3), bundle(), models=FakeModels([]), sender=sender, print_fn=[].append)
        sender.close()
        base = ["--camera", "0", "--no-window", "--seconds", "1"]
        a = parse_args(base + ["--serve", "0", "--backend-url", "http://127.0.0.1:8000"])
        self.assertEqual(a.backend_url, "http://127.0.0.1:8000")
        self.assertIsNone(parse_args(base).backend_url)
        for argv in (["--backend-url", "http://127.0.0.1:8000"], ["--serve", "0", "--backend-url", "127.0.0.1"]):
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                parse_args(base + argv)


# --- when a window is evaluated: after the touch for its stretch has arrived ---------------------------------------
RIGHT_BOX = (0.75, 0.25, 0.95, 0.95)   # a companion box right of the user's face (face_cx 0.5), as test_situation


def paced_run(at, sched=None, sender=None, watch=None):
    """run_live on the fake camera with the touch entry; at = touch windows by frame index (reporting). Returns
    (meta, entry, {t: record}, [(record, body)]). watch(svc) is called before each frame is processed."""
    from app.modules.vision.live import run_live
    sched = sched or [fake_inference(y) for y in yaw_schedule()]
    svc = entry()
    seen = []

    def frames_():
        for frame in reporting(timed_frames(len(sched)), svc, at):
            if watch is not None:
                watch(svc)
            yield frame
    meta = run_live(frames_(), bundle(), models=FakeModels(sched), detector=FakeHeads(), direction=FakeDirection(),
                    print_fn=[].append, entry=svc, sender=sender, on_window=lambda rec, body: seen.append((rec, body)))
    return meta, svc, {rec["t"]: rec for rec, _ in seen}, seen


def missing(rec) -> set:
    return {m for r in rec["situation"]["unknown_reason"] for m in r.get("missing", [r["code"]])}


@unittest.skipUnless(HAS_CV2, SKIP)
class TouchPacedEvaluationTests(unittest.TestCase):
    S1 = {1: [window_body(-2.0, 0.0, session_id="s1")], 20: [window_body(0.0, 2.0, session_id="s1")],
          40: [window_body(2.0, 4.0, session_id="s1")]}     # 2 s windows, each sent when it ends

    def test_with_a_session_each_segment_waits_for_its_touch_and_reads_it_complete(self):
        meta, _, recs, seen = paced_run(self.S1)
        ev = {t: (r["evaluated"]["how"], r["evaluated"]["at"], r["evaluated"]["touch_complete"]) for t, r in recs.items()}
        self.assertEqual({t: ev[t] for t in (1.0, 2.0, 3.0, 4.0)},
                         {1.0: ("touch", 2.0, True), 2.0: ("touch", 2.0, True),      # two segments per touch window,
                          3.0: ("touch", 4.0, True), 4.0: ("touch", 4.0, True)})     # at the frame after it came
        for t in (1.0, 2.0, 3.0, 4.0):
            self.assertNotIn("column:tap_count", missing(recs[t]))
        self.assertEqual((recs[3.0]["situation"]["name"], recs[4.0]["situation"]["name"]),
                         ("looking_around", "looking_around"))
        self.assertEqual([ev[5.0][0], ev[5.9][0], ev[5.0][2]], ["input_end", "input_end", False])   # no touch came
        self.assertEqual(list(recs), sorted(recs))                  # in time order
        self.assertEqual(meta["windows"], 6)
        self.assertTrue(all(body is None for _, body in seen))      # no sender: nothing offered

    def test_a_window_with_a_press_is_settled_by_the_press(self):
        """A press is placed on its report's last row and the report's other rows stay blank (touch_entry.place_touch);
        the rules then know the touch from the press (events.window_any_tap True), so the window counts as judged."""
        from app.modules.vision.events import window_any_tap
        pressed = {**self.S1, 20: [window_body(0.0, 2.0, tap=1, session_id="s1")]}
        _, _, recs, _ = paced_run(pressed)
        ev = {t: r["evaluated"]["touch_complete"] for t, r in recs.items()}
        self.assertEqual((ev[1.0], ev[2.0], ev[3.0], ev[4.0]), (False, True, True, True))   # 1.0: the press may lie
        self.assertNotIn("column:tap_count", missing(recs[2.0]))                             # in (0, 1]: not known
        rows = rows_of(facing(20), extra=LIVE)                       # 0.0 .. 1.9 s, no counts
        rows[5]["tap_count"] = 1
        self.assertIs(window_any_tap(rows, (0.0, 1.9)), True)        # one press settles it, blanks around it
        self.assertIsNone(window_any_tap(rows_of(facing(20), extra=LIVE), (0.0, 1.9)))
        self.assertIs(window_any_tap(rows_of(facing(20)), (0.0, 1.9)), False)   # a zero on every row

    def test_the_sent_windows_follow_each_touch_window(self):
        from app.modules.vision.tag_sender import TagSender
        stub = StubBackend()
        try:
            meta, _, recs, seen = paced_run(self.S1, sender=TagSender(stub.url, bundle().chain.segment_s))
        finally:
            stub.close()
        offered = [(rec["t"], rec["evaluated"]["at"]) for rec, body in seen if body is not None]
        self.assertEqual(offered, [(1.0, 2.0), (2.0, 2.0), (3.0, 4.0), (4.0, 4.0), (5.0, 5.9), (5.9, 5.9)])
        releases = {}                                               # one release per evaluation call (its frame)
        for t, at in offered:
            releases.setdefault(at, []).append(iso_at(t))
        ends = [b["window_end"] for _, b in stub.received]
        self.assertIn(iso_at(5.9), ends)                            # the last one is sent at the close
        sent = [r for r in releases.values() if any(e in ends for e in r)]
        self.assertEqual(sorted(ends), sorted(e for r in sent for e in r))   # every window of a sent release came
        self.assertEqual(ends, sorted(ends))                        # in time order
        self.assertEqual(len(ends) + meta["tag_sender"]["replaced"], len(offered))   # the rest: whole releases
        self.assertEqual({k for _, b in stub.received for k in b}, PAYLOAD_KEYS)   # no key added

    def test_a_window_arriving_during_a_release_does_not_change_it(self):
        """Session s2's first window (3.5, 4.0] is added, as an HTTP thread would, right after the release of frame 40
        took its copy of the touch state: segments 3.0 and 4.0 still read s1's rows and go out under s1's id, the same
        as without the new window; the next release reads s2."""
        from app.modules.vision.tag_sender import TagSender, target

        def run(inject):
            def watch(svc):
                if inject and not hasattr(svc, "real_state"):
                    svc.real_state = svc.touch.state

                    def state():
                        copy = svc.real_state()
                        if (svc.latest_t or 0.0) >= 4.0 and not hasattr(svc, "injected"):   # frame 40's flush
                            svc.injected = svc.receive(window_body(3.5, 4.0, session_id="s2"))
                        return copy
                    svc.touch.state = state
            _, svc, recs, seen = paced_run(self.S1, sender=TagSender(closed_port_url(), 1.0), watch=watch)
            return svc, recs, {rec["t"]: body for rec, body in seen}             # the bodies the releases offered
        _, plain, plain_bodies = run(False)
        svc, recs, bodies = run(True)
        self.assertEqual(svc.injected, (202, {"status": "accepted"}))
        for t in (3.0, 4.0):
            self.assertEqual((recs[t]["situation"], recs[t]["vision"], recs[t]["evaluated"]["session_id"]),
                             (plain[t]["situation"], plain[t]["vision"], "s1"))
            self.assertEqual(bodies[t], plain_bodies[t])                    # the same body, posted to s1's path
            self.assertEqual(target("http://b", bodies[t]["session_id"]), "http://b/api/v1/sessions/s1/vision-windows")
        self.assertEqual(recs[5.0]["evaluated"]["session_id"], "s2")          # the window was taken, later

    def test_the_segments_of_one_release_all_reach_a_slow_backend_in_order(self):
        """The touch window of frame 20 releases 1.0 and 2.0 together: both are posted, in order, although each answer
        takes longer than the rest of the fake run. The release of frame 40 (3.0, 4.0) waits unsent behind them and the
        input end's release (5.0, 5.9) replaces it as a whole."""
        from app.modules.vision.tag_sender import TagSender
        stub = StubBackend(delay=0.3)                     # test values: a slow answer, within the sender's timeout
        try:
            meta, _, _, _ = paced_run(self.S1, sender=TagSender(stub.url, 5.0))
        finally:
            stub.close()
        ends = [b["window_end"] for _, b in stub.received]
        self.assertEqual(ends, [iso_at(t) for t in (1.0, 2.0, 5.0, 5.9)])
        s = meta["tag_sender"]
        self.assertEqual((s["offered"], s["sent"], s["replaced"], s["unsent_at_close"], s["failed"]), (6, 4, 2, 0, 0))

    def test_a_zero_touch_window_lets_consulting_companion_be_judged(self):
        from app.modules.vision.chain import WindowJudge
        rows = rows_of(facing(5), sweep(+1), facing(10), extra={**LIVE, "companion_box": RIGHT_BOX})
        for r in rows[-8:-2]:
            r["mouth_motion"] = 0.3                                 # talking toward the companion at the end
        t = rows[-1]["t_s"]
        svc = entry(rows)
        before = WindowJudge(bundle()).evaluate(svc.window_rows(rows, t), t)["situation"]
        self.assertEqual((before["name"], missing({"situation": before})), ("unknown", {"column:tap_count"}))
        for t0, t1 in ((-6.0, -4.0), (-4.0, -2.0), (-2.0, 0.0), (0.0, t)):
            svc.receive(window_body(t0, t1, session_id="s1"))
        after = WindowJudge(bundle()).evaluate(svc.window_rows(rows, t), t)["situation"]
        self.assertEqual(after["name"], "consulting_companion")
        self.assertIn("dwell_no_touch@0", after["evidence_ids"])

    def test_touch_windows_that_stop_arriving_release_at_the_kept_history_and_the_runner_state_stays_bounded(self):
        """The waiting segments, the kept rows and the touch reports kept with them stay within the kept-history bound
        while no touch comes (the timing rows of an unbounded run: test_an_unbounded_run_keeps_no_..._rows)."""
        from app.modules.vision.chain import history_s
        keep_s, seg = history_s(bundle()) + bundle().chain.segment_s, bundle().chain.segment_s
        spans, reports = [], []

        def watch(svc):
            if svc.times:
                spans.append(svc.latest_t - svc.times[0])
                reports.append((svc.times[0], [r.t1 for r in svc.touch.snapshot()]))
        n = 150                                                     # 15 s; touch stops after 2.0 s
        meta, svc, recs, _ = paced_run({1: self.S1[1], 20: self.S1[20]}, sched=[fake_inference()] * n, watch=watch)
        self.assertEqual((meta["frames"], meta["windows"]), (n, 15))   # every frame, every segment and the last part
        held = {t: r["evaluated"] for t, r in recs.items() if r["evaluated"]["how"] == "kept_history"}
        self.assertEqual(sorted(held), [3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        for t, e in held.items():                                   # at the first frame past keep_s - segment_s
            self.assertAlmostEqual(e["at"], t + keep_s - seg)
            self.assertFalse(e["touch_complete"])                   # evaluated as it is: touch missing
        self.assertEqual({recs[t]["evaluated"]["how"] for t in recs if t > 8.0}, {"input_end"})
        self.assertLessEqual(max(spans), keep_s + keep_s - seg + 1e-9)   # the kept rows stay bounded
        self.assertGreater(max(spans), keep_s)                       # (longer than keep_s while a segment waits)
        frame_times = [round(i * DT, 6) for i in range(n)]           # segments due and not yet evaluated, per frame
        waiting = [sum(1 for t, r in recs.items() if t <= x < r["evaluated"]["at"]) for x in frame_times]
        self.assertLessEqual(max(waiting), (keep_s - seg) / seg + 1)    # at most keep_s - segment_s of segments wait
        self.assertGreaterEqual(max(waiting), 6)
        self.assertTrue(all(t1 >= kept_from for kept_from, ends in reports for t1 in ends))   # reports go with
        self.assertEqual(reports[-1][1], [2.0])                      # their rows: only the one whose rows are still kept

    def test_without_a_session_the_runner_keeps_its_own_cadence(self):
        no_session = {k: [{kk: vv for kk, vv in b.items() if kk != "session_id"} for b in v] for k, v in self.S1.items()}
        _, _, recs, seen = paced_run(no_session)
        self.assertEqual({t: (r["evaluated"]["how"], r["evaluated"]["at"]) for t, r in recs.items()},
                         {1.0: ("cadence", 1.0), 2.0: ("cadence", 2.0), 3.0: ("cadence", 3.0),
                          4.0: ("cadence", 4.0), 5.0: ("cadence", 5.0), 5.9: ("cadence", 5.9)})
        self.assertIn("column:tap_count", missing(recs[3.0]))       # (2, 3] not reported yet at 3.0, as before
        self.assertEqual(recs[4.0]["situation"]["name"], "looking_around")

    def test_an_older_sessions_windows_do_not_release_a_newer_sessions_segment(self):
        at = {1: [window_body(-2.0, 0.0, session_id="a")], 20: [window_body(0.0, 2.0, session_id="a")],
              30: [window_body(2.5, 3.0, session_id="b")],           # a new session from 2.5 s
              40: [window_body(2.0, 4.0, session_id="a")],           # a late window of the old one
              50: [window_body(3.0, 5.0, session_id="b")]}
        _, _, recs, _ = paced_run(at)
        e = {t: (r["evaluated"]["how"], r["evaluated"]["at"], r["evaluated"]["session_id"]) for t, r in recs.items()}
        self.assertEqual(e[3.0], ("touch", 3.0, "b"))
        self.assertEqual(e[4.0], ("touch", 5.0, "b"))               # a's window to 4.0 did not release it
        self.assertEqual(e[5.0], ("touch", 5.0, "b"))


CONTRACT_DIR = os.path.join(os.path.dirname(AI_ENGINE_DIR), "contract")


def contract_example(test, name: str, path: str, method: str = "post") -> dict:
    """The request example of one path in contract/<name>; skips the test when the file is absent (the engine side
    can be merged before the contract files)."""
    file = os.path.join(CONTRACT_DIR, name)
    if not os.path.isfile(file):
        test.skipTest(f"contract/{name} is absent (the engine side checked out without the contract files)")
    with open(file, encoding="utf-8") as f:
        spec = json.load(f)
    return spec["paths"][path][method]["requestBody"]["content"]["application/json"]["example"]


def key_tree(value):
    """The keys of a JSON value, nested: dict -> {key: tree}, list -> [the merged trees of its items], else None."""
    if isinstance(value, dict):
        return {k: key_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        merged = {}
        for item in value:
            tree = key_tree(item)
            if isinstance(tree, dict):
                merged.update(tree)
        return [merged] if merged else []
    return None


@unittest.skipUnless(HAS_NUMPY, SKIP)
class ContractExampleTests(unittest.TestCase):
    def test_the_touch_entry_takes_the_order_screens_example(self):
        from app.modules.vision.touch_entry import parse_request
        example = contract_example(self, "frontend-ai.openapi.json", "/touch-windows")
        req = parse_request(example)
        self.assertEqual(req.touch, {k: example["touch"][k] for k in ("tap_count", "miss_tap_count", "back_count")})
        self.assertEqual((req.session, req.screen, req.start_text, req.end_text),
                         (example["session_id"], example["screen_id"], example["window_start"], example["window_end"]))

    def test_the_sent_window_has_the_keys_of_the_backends_example(self):
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.tag_sender import vision_window
        example = contract_example(self, "ai-backend.openapi.json", "/api/v1/sessions/{session_id}/vision-windows")
        rows = looking_around_rows()
        body = vision_window(WindowJudge(bundle()).evaluate(rows, rows[-1]["t_s"]), "s1", lambda s: EPOCH0 + s)
        self.assertEqual(key_tree(json.loads(json.dumps(body))), key_tree(example))


VITE_DEFAULT = ("localhost", "5173")    # Vite's default server.host and server.port (Vite documentation)


class DocsTests(unittest.TestCase):   # plain Python: the documented command against this project's order screen
    def test_the_documented_origin_is_the_order_screens_dev_origin(self):
        import re
        pkg = os.path.join(os.path.dirname(AI_ENGINE_DIR), "frontend", "package.json")
        if not os.path.isfile(pkg):
            self.skipTest("frontend/package.json is absent (the engine side checked out without the order screen)")
        with open(pkg, encoding="utf-8") as f:
            dev = json.load(f)["scripts"]["dev"]
        host = re.search(r"--host[ =](\S+)", dev)
        port = re.search(r"--port[ =](\d+)", dev)
        origin = f"http://{host.group(1) if host else VITE_DEFAULT[0]}:{port.group(1) if port else VITE_DEFAULT[1]}"
        with open(os.path.join(AI_ENGINE_DIR, "app", "modules", "vision", "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn(f"--allow-origin {origin} ", readme)          # the two-links command
        from app.modules.vision import live
        self.assertIn(f"example {origin},", " ".join(live.__doc__.split()))


class SmokeToolTests(unittest.TestCase):   # the tool's helpers in plain Python, and one short run on fake perception
    def test_helpers_and_arguments(self):
        from app.modules.vision.tools import integration_smoke as smoke
        self.assertEqual(smoke.percentiles([4.0, 1.0, 3.0, 2.0, None]), {"p50": 2.5, "p95": 3.85, "max": 4.0, "n": 4})
        self.assertIsNone(smoke.percentiles([None]))
        self.assertEqual(smoke.epoch_of("2027-01-15T08:00:01.500Z"), EPOCH0 + 1.5)
        a = smoke.parse_args(["--seconds", "5"])
        self.assertEqual((a.threads, a.width, a.height, a.no_heads, a.params, a.out), (1, 640, 480, False, None, None))
        self.assertEqual((smoke.FEATURE_WINDOW_MS, smoke.SCREEN), (2000, "menu"))
        body = {"session_id": "s1", "window_start": "2027-01-15T08:00:01.000Z", "window_end": "2027-01-15T08:00:02.000Z",
                "situation": {"name": "none"}, "observations": {"gaze": True, "face_seen": True, "scene_tags": []},
                "model_version": "test"}
        self.assertIn("터치 단서 판정함(터치 창이 온 뒤)",
                      smoke.window_line(body, 10.0, {"how": "touch", "touch_complete": True}))
        self.assertIn("못 판정함", smoke.window_line(body, 10.0, {"how": "kept_history", "touch_complete": False}))

    @unittest.skipUnless(HAS_CV2, SKIP)
    def test_a_short_run_sends_the_named_sessions_windows_to_the_stub(self):
        import tempfile
        from app.modules.vision.tools import integration_smoke as smoke

        class PacedModels:                           # one fake inference per frame, at the tests' 10 frames a second
            inf = fake_inference()

            def infer(self, frame):
                time.sleep(DT)
                return self.inf

        cam = smoke.FakeCamera(6.5, 160, 120)
        self.assertEqual(cam.size_wh, (160, 120))
        lines = []
        with tempfile.TemporaryDirectory() as out:
            summary = smoke.run_smoke(cam, bundle(), models=PacedModels(), detector=FakeHeads(),
                                      direction=FakeDirection(), out_dir=out, print_fn=lines.append)
            self.assertEqual(sorted(os.listdir(os.path.join(out, "live"))), ["meta.json", "windows.jsonl"])
        r = summary["received"]
        self.assertGreaterEqual(summary["touch_windows"]["accepted"], 1)
        self.assertGreaterEqual(r["count"], 1)
        self.assertEqual(r["paths"], ["/api/v1/sessions/smoke/vision-windows"])
        self.assertTrue(all(set(item["body"]) == PAYLOAD_KEYS for item in summary["per_window"]))
        self.assertEqual(r["count"], summary["sender"]["sent"])
        self.assertEqual(summary["live"]["stop_reason"], "--seconds reached")
        self.assertTrue(any(line.startswith("[터치 창") for line in lines))
        got = [line for line in lines if line.startswith("[backend 받음]")]
        self.assertEqual(len(got), r["count"])
        self.assertTrue(all(" | 구간 " in line and " | 상황 " in line and "터치 단서 " in line for line in got))
        self.assertTrue(all(item["evaluated"] is not None for item in summary["per_window"]))   # each one found
        touch = [item for item in summary["per_window"] if item["evaluated"]["how"] == "touch"]
        self.assertTrue(touch)                                      # released by the stand-in's touch windows,
        self.assertTrue(all(item["evaluated"]["touch_complete"] for item in touch))   # reading only the session's rows
        self.assertIn("터치 단서 판정함(터치 창이 온 뒤)", "\n".join(got))
        self.assertGreaterEqual(r["touch_conditions"]["judged"], 1)


if __name__ == "__main__":
    unittest.main()
