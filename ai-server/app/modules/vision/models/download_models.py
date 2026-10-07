"""Download the four MediaPipe model files the vision module uses into this folder. Model weights are not kept in
Git (AGENTS.md section 5); sources, sizes and licence are in README.md next to this file.

  python app/modules/vision/models/download_models.py        (from ai-server/)

Each file is checked against the SHA-256 of the file the skeleton was tested with; a file that differs is not kept.
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://storage.googleapis.com/mediapipe-models/"
# (file, path under BASE, bytes, SHA-256) - downloaded 2026-10-06 (full-range detector 2026-10-08)
MODELS = [
    ("face_landmarker.task", "face_landmarker/face_landmarker/float16/1/face_landmarker.task", 3758596,
     "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"),
    ("pose_landmarker_lite.task", "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task", 5777746,
     "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"),
    ("blaze_face_short_range.tflite", "face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
     229746, "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f"),
    ("blaze_face_full_range.tflite", "face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite",
     1083786, "3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b"),
]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ok = True
    for name, rel, size, digest in MODELS:
        dst = os.path.join(HERE, name)
        if os.path.isfile(dst) and sha256(dst) == digest:
            print(f"already here: {name}")
            continue
        tmp = dst + ".part"
        urllib.request.urlretrieve(BASE + rel, tmp)
        got = sha256(tmp)
        if got != digest:
            os.remove(tmp)
            print(f"SHA-256 differs for {name}: got {got[:12]}, expected {digest[:12]} - the published file may have "
                  f"changed; not kept", file=sys.stderr)
            ok = False
            continue
        os.replace(tmp, dst)
        print(f"downloaded: {name} ({size:,} bytes)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
