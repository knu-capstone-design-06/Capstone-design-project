"""The recording camera (tools/recording_camera.py): a clip played in real time, stamped like a webcam frame.

The clip is made here (a small MJPG file in a temporary folder, frame k has the grey level 8 k); no team recording is
read. Every number below is made for this synthetic clip and is not a proposal for a pilot value.
"""

import os
import shutil
import tempfile
import threading
import time
import unittest

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:          # the vision extras are not installed
    HAS_CV2 = False

FPS = 40.0                   # the synthetic clip's frame rate
FRAMES = 24                  # 0.6 s of clip
SIZE = (64, 48)              # width, height


def make_clip(folder: str) -> str:
    path = os.path.join(folder, "clip.avi")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), FPS, SIZE)
    for k in range(FRAMES):
        writer.write(np.full((SIZE[1], SIZE[0], 3), 8 * k, np.uint8))
    writer.release()
    return path


@unittest.skipUnless(HAS_CV2, "OpenCV and numpy are needed")
class RecordingCameraTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.clip = make_clip(self.folder)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def camera(self, **kw):
        from app.modules.vision.tools.recording_camera import RecordingCamera
        return RecordingCamera(self.clip, **kw)

    def test_a_fast_reader_gets_the_frames_at_their_time_with_the_wall_clock(self):
        cam = self.camera()
        frames = list(cam)
        indices = [int(f.src_ref) for f in frames]
        self.assertEqual(indices, sorted(set(indices)))
        self.assertEqual(cam.counts["clip"] + cam.counts["skipped"], FRAMES)   # each frame handed out or skipped
        self.assertGreaterEqual(cam.counts["clip"], FRAMES - 3)               # a reader this fast misses few
        times = [f.t_s for f in frames]
        self.assertEqual(times, sorted(times))
        for f in frames:                       # never handed out before its time in the clip, within one tick of
            # the monotonic clock (time.get_clock_info: 15.6 ms on Windows with Python 3.12)
            k = int(f.src_ref)
            self.assertGreaterEqual(f.t_s - cam.clip_start_t_s, k / FPS - time.get_clock_info("monotonic").resolution - 0.002)
            self.assertAlmostEqual(float(f.image.mean()), 8 * k, delta=4)   # the clip's own frame k
        offsets = [f.epoch_s - f.t_s for f in frames]   # wall time and monotonic time move together
        self.assertLess(max(offsets) - min(offsets), 0.05)
        self.assertLess(abs(frames[-1].epoch_s - time.time()), 1.0)
        self.assertEqual((cam.counts["preroll"], cam.counts["tail"]), (0, 0))
        self.assertEqual(cam.end_reason, "end of the recording")
        self.assertEqual(cam.kind, "camera")

    def test_a_slow_reader_skips_frames_and_the_clip_keeps_its_real_time(self):
        cam = self.camera()
        frames = []
        for f in cam:
            frames.append(f)
            time.sleep(0.06)                   # slower than the clip's 25 ms per frame
        indices = [int(f.src_ref) for f in frames]
        self.assertLess(len(frames), FRAMES)
        self.assertGreater(cam.counts["skipped"], 0)
        self.assertEqual(cam.counts["clip"] + cam.counts["skipped"], FRAMES)   # each frame handed out or skipped
        for f, k in zip(frames, indices):      # the frame handed out is the newest one at that moment
            self.assertLessEqual(abs((f.t_s - cam.clip_start_t_s) * FPS - k), 2.5)

    def test_step_hands_out_every_step_th_frame_only(self):
        frames = list(self.camera(step=2))
        self.assertTrue(frames)
        self.assertTrue(all(int(f.src_ref) % 2 == 0 for f in frames))
        self.assertEqual(self.camera(step=2).fps, FPS / 2)

    def test_black_frames_until_the_start_file_then_the_clip_then_the_tail(self):
        start = os.path.join(self.folder, "start")
        timer = threading.Timer(0.2, lambda: open(start, "w").close())
        timer.start()
        try:
            cam = self.camera(start_file=start, tail_s=0.2)
            frames = list(cam)
        finally:
            timer.cancel()
        refs = [f.src_ref for f in frames]
        first_clip = refs.index("0")
        self.assertGreater(first_clip, 0)
        self.assertTrue(all(r == "preroll" for r in refs[:first_clip]))
        self.assertTrue(all(float(f.image.max()) == 0 for f in frames[:first_clip]))
        self.assertEqual(frames[0].image.shape, (SIZE[1], SIZE[0], 3))
        self.assertGreaterEqual(frames[first_clip].t_s, 0.15)   # the timer's 0.2 s, less the OS timer's granularity
        self.assertGreaterEqual(cam.clip_start_t_s, 0.15)
        self.assertEqual(refs[-1], "tail")
        last_clip = max(i for i, r in enumerate(refs) if r not in ("preroll", "tail"))
        self.assertTrue(all(r == "tail" for r in refs[last_clip + 1:]))
        self.assertGreaterEqual(frames[-1].t_s - frames[last_clip].t_s, 0.15)
        self.assertLessEqual(cam.counts["preroll"], int(0.2 * FPS) + 3)   # paced at the clip's rate
        self.assertIsNotNone(cam.clip_started_epoch)
        self.assertLess(cam.clip_started_epoch, cam.clip_ended_epoch)
        self.assertIn("black frames", cam.end_reason)

    def test_seconds_stops_the_preroll(self):
        cam = self.camera(start_file=os.path.join(self.folder, "never"), seconds=0.15)
        frames = list(cam)
        self.assertTrue(frames and all(f.src_ref == "preroll" for f in frames))
        self.assertEqual(cam.end_reason, "--seconds reached")

    def test_the_touch_entry_accepts_its_frames(self):
        from app.modules.vision.params import load_bundle
        from app.modules.vision.touch_entry import TouchEntry
        entry = TouchEntry(load_bundle(None))
        cam = self.camera()
        for f in cam:
            entry.add_row({"t_s": f.t_s}, f)   # raises for a frame without a wall-clock time
        self.assertEqual(entry.status()["frames"], cam.counts["clip"])

    def test_label_names_the_source_and_bad_arguments_are_refused(self):
        self.assertEqual(self.camera(label="take 1").name, "take 1")
        self.assertEqual(self.camera().name, "clip.avi")
        with self.assertRaises(ValueError):
            self.camera(step=0)
        with self.assertRaises(ValueError):
            self.camera(tail_s=-1)
        from app.modules.vision.tools.recording_camera import RecordingCamera
        with self.assertRaises(FileNotFoundError):
            RecordingCamera(os.path.join(self.folder, "missing.mp4"))


class RecordingCameraArgsTests(unittest.TestCase):
    def test_the_links_need_the_touch_entry_as_in_live(self):
        from app.modules.vision.tools.recording_camera import parse_args
        import contextlib
        import io
        for argv in (["--video", "x", "--allow-origin", "http://127.0.0.1:5173"],
                     ["--video", "x", "--backend-url", "http://127.0.0.1:8000"],
                     ["--video", "x", "--serve", "8765", "--backend-url", "ftp://x"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(argv)
        a = parse_args(["--video", "x", "--serve", "0", "--allow-origin", "http://127.0.0.1:5173",
                        "--backend-url", "http://127.0.0.1:8000", "--step", "3", "--width", "960"])
        self.assertEqual((a.serve, a.allow_origin, a.step, a.width), (0, ["http://127.0.0.1:5173"], 3, 960))


if __name__ == "__main__":
    unittest.main()
