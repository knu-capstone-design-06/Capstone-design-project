"""Export the two perception checkpoints to ONNX for the CPU runtime (perception/head.py, perception/head_direction.py).

Runs in a separate environment with CPU torch, torchvision and YOLOX (commit 6ddff48) - not in the runtime one, which
needs only onnxruntime. From ai-engine/:

  python -m app.modules.vision.tools.export_onnx --h1-ckpt <best_ckpt.pth> --p1-ckpt <model_final.pt> [--out-dir DIR]

H1 head detector (YOLOX-Nano, 1 class 'head'): the steps of YOLOX tools/export_onnx.py (6ddff48) with its defaults -
exp.get_model() + checkpoint['model'] (strict), eval mode, nn.SiLU replaced by YOLOX's export SiLU, raw head output
(decode_in_inference False), dummy input 1 x 3 x 416 x 416 (exp.test_size), input 'images', output 'output', opset 11,
then onnxsim.simplify with its validity check - plus --dynamic (batch axis 'batch'). Differences, as in the Run 1 tool:
YOLOX calls the private torch.onnx._export that torch 2.7.1 no longer has, so the public torch.onnx.export is called
with the same arguments (TorchScript exporter, dynamo=False); onnxsim is the current release instead of the pinned
onnx-simplifier 0.4.10 (no wheel for this Python). The architecture comes from YOLOX's own exps/default/yolox_nano.py
with num_classes = 1, which equals H1's config (exps/example/custom/nano.py + num_classes 1); --h1-exp loads the
exact exp file instead. The strict state-dict load fails if the two differ.

P1 head direction (torchvision ResNet-18, 5 classes): resnet18(weights=None, num_classes=5) + checkpoint['model'],
input 'crops' N x 3 x 56 x 56 (normalised, p1_data.transforms(False)), output 'logits', dynamic batch, opset 11.

Checkpoints are loaded with torch.load(weights_only=True); YOLOX checkpoints hold numpy scalars, which are allowed
explicitly (torch.serialization.safe_globals) instead of switching weights_only off.

Checks written to <out-dir>/onnx_export.json and printed:
- ONNX Runtime vs PyTorch on the same inputs: max |difference| of the raw outputs (H1: a random 0-255 input as the
  Run 1 tool did, and a letterboxed synthetic frame; P1: a random normalised batch);
- H1 boxes after this module's decode + NMS (perception/head.py) from both outputs at the YOLOX evaluation floor 0.01;
- P1 input: this module's numpy crop transform (head_direction.to_input) vs the torchvision v2 transforms of
  p1_data.transforms(False) (Resize 64, CenterCrop 56, ToDtype scale, Normalize) on random crops;
- sizes and SHA-256 of the checkpoints and the ONNX files, package versions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(os.path.dirname(HERE), "models")
H1_ONNX = "h1_head_yolox_nano_416.onnx"
P1_ONNX = "p1_head_direction_resnet18_56.onnx"
YOLOX_COMMIT = "6ddff48"
OPSET = 11                       # YOLOX tools/export_onnx.py default (-o / --opset 11)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_info(path: str) -> dict:
    return {"file": os.path.basename(path), "bytes": os.path.getsize(path), "sha256": sha256(path)}


def _safe_load(path: str):
    """torch.load with weights_only=True; YOLOX checkpoints need numpy scalars and dtypes allowed."""
    import torch
    allow = [np._core.multiarray.scalar, np.dtype] + [getattr(np.dtypes, n) for n in dir(np.dtypes)
                                                       if n.endswith("DType")]
    with torch.serialization.safe_globals(allow):
        return torch.load(path, map_location="cpu", weights_only=True)


def _set_metadata(path: str, meta: dict, simplify: bool) -> dict:
    """Simplify (YOLOX's step) when asked, add metadata_props, check the model; returns the simplify outcome."""
    import onnx
    model = onnx.load(path)
    outcome = {"onnxsim": "not run (--no-onnxsim)"}
    if simplify:
        try:
            from onnxsim import simplify as onnxsim_simplify
            import onnxsim
            simplified, ok = onnxsim_simplify(model)
            if not ok:
                raise RuntimeError("Simplified ONNX model could not be validated")
            model = simplified
            outcome = {"onnxsim": f"applied (onnxsim {onnxsim.__version__}, check passed)"}
        except Exception as e:   # keep the plain export and say why
            outcome = {"onnxsim": f"not applied: {type(e).__name__}: {e}"}
    del model.metadata_props[:]
    for k, v in meta.items():
        entry = model.metadata_props.add()
        entry.key, entry.value = k, str(v)
    onnx.checker.check_model(model)
    onnx.save(model, path)
    return outcome


def _session(path: str):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    return ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])


def synthetic_frame(w: int = 640, h: int = 480) -> np.ndarray:
    """A drawn BGR test frame (grey background, three filled ellipses and rectangles): no photo, no person."""
    import cv2
    img = np.full((h, w, 3), 127, np.uint8)
    for (cx, cy, rx, ry, col) in ((320, 200, 70, 90, (60, 80, 120)), (130, 170, 35, 45, (40, 40, 40)),
                                  (520, 160, 30, 38, (90, 110, 150))):
        cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, col, -1)
    cv2.rectangle(img, (220, 290), (420, 480), (150, 60, 40), -1)
    return img


def export_h1(ckpt_path: str, out_path: str, exp_file: str | None, simplify: bool) -> dict:
    import torch
    from torch import nn
    from yolox.exp import get_exp
    from yolox.models.network_blocks import SiLU
    from yolox.utils import replace_module

    from app.modules.vision.perception.head import decode, grid_and_strides, letterbox, nms

    if exp_file:
        exp = get_exp(exp_file, None)
    else:
        exp = get_exp(None, "yolox-nano")      # exps/default/yolox_nano.py = custom nano.py architecture
        exp.num_classes = 1
    model = exp.get_model()
    ckpt = _safe_load(ckpt_path)
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt, strict=True)
    model.eval()
    model = replace_module(model, nn.SiLU, SiLU)
    model.head.decode_in_inference = False
    size = tuple(exp.test_size)
    dummy = torch.randn(1, 3, size[0], size[1])
    torch.onnx.export(model, dummy, out_path, input_names=["images"], output_names=["output"],
                      dynamic_axes={"images": {0: "batch"}, "output": {0: "batch"}}, opset_version=OPSET,
                      dynamo=False)
    strides = (8, 16, 32)
    meta = {"model": "H1 head detector, YOLOX-Nano (depth 0.33, width 0.25, depthwise), Open Images V7 'Human head'",
            "classes": json.dumps(["head"]), "input_size": f"{size[0]},{size[1]}", "input_layout": "NCHW BGR 0-255, "
            "letterbox top-left, pad 114, no normalisation", "decode_in_inference": "false",
            "strides": ",".join(map(str, strides)), "yolox_commit": YOLOX_COMMIT,
            "source_checkpoint_sha256": sha256(ckpt_path), "source_checkpoint_epoch": str(ckpt.get("start_epoch")),
            "exporter": "app.modules.vision.tools.export_onnx (YOLOX tools/export_onnx.py steps, --dynamic)"}
    outcome = _set_metadata(out_path, meta, simplify)

    sess = _session(out_path)
    checks = {}
    rng = np.random.default_rng(0)
    x_rand = (rng.random((1, 3, size[0], size[1])) * 255).astype(np.float32)
    x_frame, r = letterbox(synthetic_frame(), size)
    grid, st = grid_and_strides(size, strides)
    for name, x in (("random_0_255", x_rand), ("synthetic_frame_letterboxed", x_frame[None])):
        with torch.no_grad():
            ref = model(torch.from_numpy(x)).numpy()
        got = sess.run(None, {"images": x})[0]
        b_ref, s_ref = decode(ref[0], grid, st)
        b_got, s_got = decode(got[0], grid, st)
        k_ref = [i for i in np.flatnonzero(s_ref >= 0.01)]
        k_got = [i for i in np.flatnonzero(s_got >= 0.01)]
        keep_ref = [k_ref[i] for i in nms(b_ref[k_ref], s_ref[k_ref], 0.65)] if k_ref else []
        keep_got = [k_got[i] for i in nms(b_got[k_got], s_got[k_got], 0.65)] if k_got else []
        same = keep_ref == keep_got
        checks[name] = {"output_shape": list(got.shape), "max_abs_diff_raw": float(np.abs(got - ref).max()),
                        "boxes_after_nms_at_0.01": {"torch": len(keep_ref), "onnx": len(keep_got),
                                                    "same_anchors": same,
                                                    "max_abs_diff_box_px": float(np.abs(b_ref[keep_ref] - b_got[keep_got]).max())
                                                    if same and keep_ref else None,
                                                    "max_abs_diff_score": float(np.abs(s_ref[keep_ref] - s_got[keep_got]).max())
                                                    if same and keep_ref else None}}
    return {**file_info(out_path), **outcome, "opset": OPSET, "input": {"name": "images", "shape": ["batch", 3, *size]},
            "output": {"name": "output", "shape": ["batch", int(grid.shape[0]), 6]}, "checks": checks,
            "source_checkpoint": file_info(ckpt_path), "exp": exp_file or "yolox exps/default/yolox_nano.py, "
            "num_classes=1", "metadata": meta}


def export_p1(ckpt_path: str, out_path: str, simplify: bool) -> dict:
    import torch
    import torchvision
    from torchvision.transforms import v2

    from app.modules.vision.perception import head_direction as hd

    p = _safe_load(ckpt_path)
    classes = tuple(p["classes"])
    if classes != hd.DIR_CLASSES:
        raise SystemExit(f"P1 classes {classes} differ from {hd.DIR_CLASSES}")
    if (float(p.get("crop_scale", hd.CROP_SCALE)), int(p.get("crop_side", hd.CROP_SIDE))) != (hd.CROP_SCALE,
                                                                                            hd.CROP_SIDE):
        raise SystemExit("P1 checkpoint crop differs from head_direction.CROP_* (the input would not match)")
    model = torchvision.models.resnet18(weights=None, num_classes=len(classes))
    model.load_state_dict(p["model"], strict=True)
    model.eval()
    dummy = torch.randn(1, 3, hd.CROP_IN, hd.CROP_IN)
    torch.onnx.export(model, dummy, out_path, input_names=["crops"], output_names=["logits"],
                      dynamic_axes={"crops": {0: "batch"}, "logits": {0: "batch"}}, opset_version=OPSET, dynamo=False)
    meta = {"model": "P1 head direction, torchvision ResNet-18 from random initial weights, AI Hub 70 head crops",
            "classes": json.dumps(list(classes), ensure_ascii=False), "crop_scale": str(hd.CROP_SCALE),
            "crop_side": str(hd.CROP_SIDE), "crop_in": str(hd.CROP_IN), "grey": str(hd.GREY),
            "mean": ",".join(f"{v:g}" for v in hd.MEAN.tolist()), "std": ",".join(f"{v:g}" for v in hd.STD.tolist()),
            "input_layout": "NCHW RGB, CenterCrop 56 of the 64-px crop, /255, Normalize(mean, std)",
            "source_checkpoint_sha256": sha256(ckpt_path), "source_checkpoint_epoch": str(p.get("epoch")),
            "exporter": "app.modules.vision.tools.export_onnx"}
    outcome = _set_metadata(out_path, meta, simplify)

    sess = _session(out_path)
    rng = np.random.default_rng(0)
    x = rng.standard_normal((8, 3, hd.CROP_IN, hd.CROP_IN)).astype(np.float32)
    with torch.no_grad():
        ref = model(torch.from_numpy(x)).numpy()
    got = sess.run(None, {"crops": x})[0]
    # the input transform: p1_data.transforms(False) rebuilt here vs this module's numpy version
    tf = v2.Compose([v2.Resize(hd.CROP_SIDE, antialias=True), v2.CenterCrop(hd.CROP_IN),
                     v2.ToDtype(torch.float32, scale=True), v2.Normalize(mean=hd.MEAN.tolist(), std=hd.STD.tolist())])
    crops = rng.integers(0, 256, (16, hd.CROP_SIDE, hd.CROP_SIDE, 3), dtype=np.uint8)
    ref_in = tf(torch.from_numpy(crops).permute(0, 3, 1, 2)).numpy()
    got_in = hd.to_input(crops)
    return {**file_info(out_path), **outcome, "opset": OPSET,
            "input": {"name": "crops", "shape": ["batch", 3, hd.CROP_IN, hd.CROP_IN]},
            "output": {"name": "logits", "shape": ["batch", len(classes)]},
            "checks": {"random_normalised_batch8": {"max_abs_diff_logits": float(np.abs(got - ref).max()),
                                                    "same_argmax": bool((got.argmax(1) == ref.argmax(1)).all())},
                       "input_transform_vs_torchvision": {"max_abs_diff": float(np.abs(got_in - ref_in).max()),
                                                          "shape": list(got_in.shape)}},
            "source_checkpoint": file_info(ckpt_path), "classes": list(classes), "epoch": p.get("epoch"),
            "metadata": meta}


def versions() -> dict:
    import onnx
    import onnxruntime
    import torch
    import torchvision
    import yolox
    return {"python": platform.python_version(), "torch": torch.__version__, "torchvision": torchvision.__version__,
            "onnx": onnx.__version__, "onnxruntime": onnxruntime.__version__, "yolox": yolox.__version__,
            "numpy": np.__version__, "platform": platform.platform()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--h1-ckpt", required=True, help="H1 best_ckpt.pth (YOLOX checkpoint)")
    ap.add_argument("--p1-ckpt", required=True, help="P1 model_final.pt")
    ap.add_argument("--h1-exp", default=None, help="H1 exp file (default: YOLOX yolox-nano with num_classes=1)")
    ap.add_argument("--out-dir", default=MODELS_DIR)
    ap.add_argument("--no-onnxsim", action="store_true", help="skip onnxsim.simplify (YOLOX --no-onnxsim)")
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.time()
    record = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "versions": versions()}
    record["h1"] = export_h1(a.h1_ckpt, os.path.join(a.out_dir, H1_ONNX), a.h1_exp, not a.no_onnxsim)
    record["p1"] = export_p1(a.p1_ckpt, os.path.join(a.out_dir, P1_ONNX), not a.no_onnxsim)
    record["seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(a.out_dir, "onnx_export.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
