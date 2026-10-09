"""입력 (sources) layer: frame sources for the vision skeleton.

Every source yields `Frame` objects in time order. The two offline sources read files only.
`LiveCameraSource` (webcam) is separate: it opens a camera only when someone constructs it, which no offline
command does.

`measured_times` tells whether frame times are measured capture times (camera, a recorded clip with its
sidecar) or derived from a stated rate (index / fps). Only measured times give an effective frame rate.
doc 28 = the vision design note kept outside this repository (see inference.py).
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp")


@dataclass
class Frame:
    index: int          # 0-based index among the frames this source yields
    t_s: float          # frame time in seconds from the start of the input
    image: np.ndarray   # BGR uint8 (OpenCV channel order)
    src_ref: str        # source frame number (video) or file name (image folder)
    read_ms: float      # time spent reading / decoding / resizing this frame (offline only)


def resize_keep_aspect(img: np.ndarray, width: int | None) -> np.ndarray:
    """Resize to `width` keeping the aspect ratio.

    The aspect ratio is always kept: stretching a portrait photo changed the old bench's hand
    results (doc 28 section 6, note 1)."""
    if not width or img.shape[1] == width:
        return img
    h = int(round(img.shape[0] * width / img.shape[1]))
    return cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)


TIMES_SUFFIX = ".times.csv"   # optional sidecar of a recorded clip: a header line, then "frame,t_s" per frame


def read_times(video_path: str) -> list[float] | None:
    """Frame times (s) from the sidecar of a recorded clip, or None when there is no sidecar.

    The sidecar is trusted only when it is complete: frame numbers 0, 1, 2, ... in order and finite, non-decreasing
    times. Anything else raises, because a time silently taken from the wrong frame would corrupt every
    continuity and frame-rate value downstream."""
    p = video_path + TIMES_SUFFIX
    if not os.path.isfile(p):
        return None
    times: list[float] = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for expected, row in enumerate(csv.DictReader(f)):
            try:
                frame, t_s = int(row["frame"]), float(row["t_s"])
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError(f"{p}: expected columns 'frame,t_s' with numbers (line {expected + 2})") from e
            if frame != expected:
                raise ValueError(f"{p}: frame numbers must run 0, 1, 2, ... (got {frame} at line {expected + 2})")
            if not math.isfinite(t_s):
                raise ValueError(f"{p}: time of frame {frame} is not a finite number")
            if times and t_s < times[-1]:
                raise ValueError(f"{p}: time of frame {frame} goes backwards ({t_s} < {times[-1]})")
            times.append(t_s)
    if not times:
        raise ValueError(f"{p}: the sidecar has no frame times")
    return times


def effective_fps(times) -> float | None:
    """Mean frame rate of measured frame times: (frames - 1) / (last - first time) = 1 / mean frame interval
    None for fewer than two frames or when no time passed."""
    if len(times) < 2:
        return None
    span = float(times[-1]) - float(times[0])
    return (len(times) - 1) / span if span > 0 else None


class VideoFileSource:
    """Reads a video file. `step` = use every step-th frame (1 = all frames).

    Frame time = source frame index / container frame rate (OpenCV CAP_PROP_FPS), which assumes a constant
    frame rate. A recorded clip may have a sidecar (<clip>.times.csv) with the measured capture times; those
    are used instead."""

    kind = "video"

    def __init__(self, path: str, step: int = 1, width: int | None = None):
        # Files only: an integer camera index is never accepted here (cameras: LiveCameraSource).
        if not isinstance(path, str) or not os.path.isfile(path):
            raise FileNotFoundError(f"not a video file: {path!r}")
        if step < 1:
            raise ValueError("step must be >= 1")
        self.path, self.step, self.width = path, step, width
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise IOError(f"OpenCV cannot open {path}")
        self.src_fps = float(cap.get(cv2.CAP_PROP_FPS))
        self.src_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))  # container value, may be approximate
        cap.release()
        if self.src_fps <= 0:
            raise ValueError("the video reports no frame rate")
        self.fps = self.src_fps / step
        self.times = read_times(path)
        self.time_source = "sidecar (<clip>.times.csv)" if self.times else "frame index / container fps"
        self.measured_times = bool(self.times)
        self.name = os.path.basename(path)
        self.synthetic = False
        self.manifest = None

    def _t(self, src_i: int) -> float:
        if self.times is None:
            return src_i / self.src_fps
        if src_i >= len(self.times):
            raise ValueError(f"{self.path + TIMES_SUFFIX}: no time for frame {src_i} ({len(self.times)} times listed)")
        return self.times[src_i]

    def expected_frames(self) -> int:
        return (self.src_frame_count + self.step - 1) // self.step

    def __iter__(self):
        cap = cv2.VideoCapture(self.path)
        src_i, out_i = 0, 0
        try:
            while True:
                if src_i % self.step != 0:
                    if not cap.grab():          # skipped frame: not timed (a camera would not deliver it)
                        self.end_reason = "end of file"
                        break
                    src_i += 1
                    continue
                t0 = time.perf_counter()
                ok, img = cap.read()
                if not ok:
                    self.end_reason = "end of file"
                    break
                img = resize_keep_aspect(img, self.width)
                read_ms = (time.perf_counter() - t0) * 1000.0
                yield Frame(out_i, self._t(src_i), img, str(src_i), read_ms)
                src_i += 1
                out_i += 1
        finally:
            cap.release()


class ImageFolderSource:
    """Reads the images of a folder in file-name order. Images carry no time, so the caller gives a
    nominal frame rate; frame time = index / fps. If the folder has a manifest.json (written by
    make_synthetic.py), its fps and labels are used."""

    kind = "folder"
    measured_times = False

    def __init__(self, folder: str, fps: float | None = None, width: int | None = None):
        if not os.path.isdir(folder):
            raise FileNotFoundError(f"not a folder: {folder!r}")
        self.folder, self.width = folder, width
        self.files = sorted(f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXTS))
        if not self.files:
            raise FileNotFoundError(f"no images in {folder}")
        self.manifest = None
        mpath = os.path.join(folder, "manifest.json")
        if os.path.isfile(mpath):
            with open(mpath, encoding="utf-8") as f:
                self.manifest = json.load(f)
        if fps is None and self.manifest is not None:
            fps = float(self.manifest["fps"])
        if not fps or fps <= 0:
            raise ValueError("an image folder needs a frame rate (--fps) or a manifest.json")
        self.fps = float(fps)
        self.name = os.path.basename(os.path.normpath(folder))
        self.synthetic = bool(self.manifest and self.manifest.get("synthetic"))
        self.time_source = "frame index / fps"

    def expected_frames(self) -> int:
        return len(self.files)

    def phase_of(self, file_name: str) -> str:
        if not self.manifest:
            return ""
        return self.manifest["frames"].get(file_name, {}).get("phase", "")

    def __iter__(self):
        for i, fn in enumerate(self.files):
            t0 = time.perf_counter()
            img = cv2.imread(os.path.join(self.folder, fn), cv2.IMREAD_COLOR)
            if img is None:
                raise IOError(f"cannot read {fn}")
            img = resize_keep_aspect(img, self.width)
            read_ms = (time.perf_counter() - t0) * 1000.0
            yield Frame(i, i / self.fps, img, fn, read_ms)
        self.end_reason = "end of the image folder"


BACKENDS = {"any": cv2.CAP_ANY, "msmf": cv2.CAP_MSMF, "dshow": cv2.CAP_DSHOW}


class LiveCameraSource:
    """Webcam through OpenCV VideoCapture (run.py --camera).

    device  = camera index; 0 = the default camera (OpenCV VideoCapture docs: "To open default camera using
              default backend just pass 0").
    width / height = requested capture size; None keeps the driver default. The driver may deliver another
              size; the delivered size is in `size_wh`.
    backend = "any" (OpenCV chooses by its own priority list; library default), "msmf" (Media Foundation) or
              "dshow" (DirectShow).
    fps     = frame rate written into output videos; None = the rate the driver reports (CAP_PROP_FPS).
    seconds = stop after this many seconds; None = until the camera stops delivering frames.

    Frame time comes from a monotonic clock (MediaPipe VIDEO mode needs increasing timestamps). read_ms is
    the wait for the next frame from the driver, not a decode cost. Frames are handed on in order; when the
    processing is slower than the camera, the driver's queue decides which frames are lost (not handled here;
    LIVE_STREAM mode is the asynchronous alternative, doc 28 section 6)."""

    kind = "camera"
    measured_times = True

    def __init__(self, device: int = 0, width: int | None = None, height: int | None = None,
                 backend: str = "any", fps: float | None = None, seconds: float | None = None):
        self.cap = cv2.VideoCapture(int(device), BACKENDS[backend])
        if not self.cap.isOpened():
            raise IOError(f"cannot open camera {device} (backend {backend})")
        if width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
        if height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
        self.size_wh = (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.reported_fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        self.fps = float(fps) if fps else self.reported_fps
        if self.fps <= 0:
            self.cap.release()
            raise ValueError("the camera reports no frame rate - give one with --fps")
        self.seconds = seconds
        self.name = f"camera{device}"
        self.synthetic, self.manifest = False, None
        self.time_source = "monotonic clock at capture"

    def expected_frames(self) -> int:
        return int(self.seconds * self.fps) if self.seconds else 0

    def __iter__(self):
        t0, i = None, 0
        try:
            while True:
                t_wait = time.perf_counter()
                ok, img = self.cap.read()
                if not ok:
                    self.end_reason = "camera stopped delivering frames"
                    break
                now = time.monotonic()
                if t0 is None:
                    t0 = now
                if self.seconds is not None and now - t0 > self.seconds:
                    self.end_reason = "--seconds reached"
                    break
                yield Frame(i, now - t0, img, str(i), (time.perf_counter() - t_wait) * 1000.0)
                i += 1
        finally:
            self.cap.release()


def open_source(path: str, fps: float | None = None, step: int = 1, width: int | None = None):
    """Pick the offline source for a path: a folder of images or a video file."""
    if os.path.isdir(path):
        return ImageFolderSource(path, fps=fps, width=width)
    return VideoFileSource(path, step=step, width=width)
