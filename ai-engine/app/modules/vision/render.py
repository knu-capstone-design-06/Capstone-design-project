"""Outputs of one run: overlay frames, contact sheet, time-series plots, timing table.

Output only - nothing here feeds back into the observations. Korean labels use the first Korean-capable font
found in KOREAN_FONTS (Malgun Gothic on Windows; Nanum Gothic or Noto Sans CJK on Linux); without one the
default font is used and one line is logged.
Chart colours: a fixed categorical palette (slot order blue, orange, aqua, yellow, magenta, green, violet, red;
a layout choice), solid hairline grid, one y-axis per panel.
"""
from __future__ import annotations

import math
import os
import sys

import cv2
import matplotlib
matplotlib.use("Agg")   # headless: never open a window
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.ticker import MaxNLocator
from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections
from mediapipe.tasks.python.vision.pose_landmarker import PoseLandmarksConnections
from PIL import Image, ImageDraw, ImageFont

from app.modules.vision.features import NOT_SEEN, SEEN, STAGES

KOREAN_FONTS = [   # (regular, bold or None); the first regular file that exists is used
    (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"),                    # Windows: Malgun Gothic
    (r"C:\Windows\Fonts\gulim.ttc", None),                                                   # Windows: Gulim
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",                                      # Debian / Ubuntu
     "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),                                 #   package fonts-nanum
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",                               # Debian / Ubuntu
     "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),                                 #   package fonts-noto-cjk
    ("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",                             # Fedora
     "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc"),                               #   google-noto-sans-cjk
]


def _find_korean_font():
    for reg, bold in KOREAN_FONTS:
        if os.path.isfile(reg):
            return reg, (bold if bold and os.path.isfile(bold) else reg)
    print("render: no Korean-capable font found (tried KOREAN_FONTS in render.py); drawing with the default font, "
          "Korean text may not show - install e.g. fonts-nanum on Linux", file=sys.stderr)
    return None, None


FONT_REG, FONT_BOLD = _find_korean_font()
SERIES =["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
PANEL_BG = (25, 26, 26)          # dark panel behind the overlay text (BGR)


def _hex_bgr(h):
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


C_FACE = _hex_bgr(SERIES[2])     # face contour
C_EYE = _hex_bgr(SERIES[3])      # eye centres and the eye-distance line
C_BOX = _hex_bgr(SERIES[0])      # landmark box and centre
C_DIR = _hex_bgr(SERIES[4])      # head direction arrow
C_DET = _hex_bgr(SERIES[1])      # face detector boxes
C_POSE = _hex_bgr(SERIES[6])     # pose skeleton


def _font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REG
    if path is None:                       # no Korean-capable font on this machine (logged once at import)
        try:
            return ImageFont.load_default(size)   # scalable default font (Pillow >= 10.1)
        except TypeError:
            return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def _fmt(v, spec="{:.2f}", missing="-"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return missing
    return spec.format(v)


def annotate(img: np.ndarray, draw: dict) -> np.ndarray:
    """Landmarks and measured geometry drawn on a copy of the frame (no text panel)."""
    out = img.copy()
    W, H = draw["W"], draw["H"]
    lw = max(1, int(round(W / 640)))
    if "pose_px" in draw:
        P, vis = draw["pose_px"], draw["pose_vis"]
        for c in PoseLandmarksConnections.POSE_LANDMARKS:
            a, b = P[c.start], P[c.end]
            cv2.line(out, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), C_POSE, lw, cv2.LINE_AA)
        grey = np.array([137, 135, 129], dtype=np.float64)   # muted ink: colour runs grey -> violet with visibility
        for (x, y), v in zip(P, vis):
            v = float(min(max(v, 0.0), 1.0))
            col = tuple(int(c) for c in grey * (1 - v) + np.array(C_POSE) * v)
            cv2.circle(out, (int(x), int(y)), 2 + lw, col, -1, cv2.LINE_AA)
    for (x, y, w, h, s) in draw.get("det_boxes", []):
        cv2.rectangle(out, (int(x), int(y)), (int(x + w), int(y + h)), C_DET, lw, cv2.LINE_AA)
        cv2.putText(out, f"{s:.2f}", (int(x), max(12, int(y) - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, C_DET, 1,
                    cv2.LINE_AA)
    if "face_px" in draw:
        F = draw["face_px"]
        for c in FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS:
            a, b = F[c.start], F[c.end]
            cv2.line(out, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), C_FACE, 1, cv2.LINE_AA)
        x0, y0, x1, y1 = draw["face_box_px"]
        cv2.rectangle(out, (int(x0), int(y0)), (int(x1), int(y1)), C_BOX, 1, cv2.LINE_AA)
        ea, eb = draw["eye_a"], draw["eye_b"]
        cv2.line(out, (int(ea[0]), int(ea[1])), (int(eb[0]), int(eb[1])), C_EYE, lw + 1, cv2.LINE_AA)
        for e in (ea, eb):
            cv2.circle(out, (int(e[0]), int(e[1])), 3 + lw, C_EYE, -1, cv2.LINE_AA)
        cx, cy = draw["face_center_px"]
        cv2.drawMarker(out, (int(cx), int(cy)), C_BOX, cv2.MARKER_CROSS, 10, 1, cv2.LINE_AA)
        if "rot" in draw:
            # Head direction: the face model's forward axis (3rd rotation column) projected on the image;
            # camera y points up in the face-geometry space, image y points down -> flip y. Length = box width.
            fwd = draw["rot"][:, 2]
            L = 0.8 * (x1 - x0)
            tip = (int(cx + fwd[0] * L), int(cy - fwd[1] * L))
            cv2.arrowedLine(out, (int(cx), int(cy)), tip, C_DIR, lw + 1, cv2.LINE_AA, tipLength=0.25)
    return out


PANEL_W = 340   # width of the value panel right of the frame (px); layout choice


def panel_lines(row: dict, header: str, phase_label: str) -> tuple[list, list]:
    """(compact, details): (style, text) lines of the value panel.

    compact = the block to read at a glance (larger font): 얼굴 / 몸 보임 · 못 봄, 눈 사이 거리 비율, 고개 각도,
    얼굴 연속, 이 프레임의 처리 ms. details = the other values (smaller font)."""
    face_seen = row["face_state"] == SEEN
    body_seen = row["body_state"] == SEEN
    compact = [("title", header),
               ("muted", f"t {row['t_s']:.2f} s · 프레임 {row['frame_idx']}" + (f" · {phase_label}" if phase_label else "")),
               ("state", f"얼굴 {row['face_state']}|몸 {row['body_state']}|{int(face_seen)}{int(body_seen)}")]
    if face_seen:
        compact += [("big", f"눈 사이 비율 ×{_fmt(row['iod_ratio_start'], '{:.2f}')}"),
                    ("big", f"고개 좌우 {_fmt(row['yaw_deg'], '{:+.0f}')}° 상하 {_fmt(row['pitch_deg'], '{:+.0f}')}°"
                            f" 기울기 {_fmt(row['roll_deg'], '{:+.0f}')}°"),
                    ("big", f"얼굴 연속 {row['face_run_s']:.1f} s (구간 {int(row['face_run_id'])})")]
    else:
        compact += [("bigmuted", "눈 사이 비율 · 고개: 얼굴 못 봄"),
                    ("big", f"얼굴 못 본 지 {row['face_unseen_s']:.1f} s")]
    compact += [("big", f"처리 {row['ms_total']:.1f} ms")]
    details = [("text", f"얼굴 수(검출기) {row['face_count']} · 검출 점수 {_fmt(row['face_det_score'])}")]
    if face_seen:
        details += [("text", f"눈 사이 {_fmt(row['iod_frac_w'], '{:.3f}')} × 화면 폭"),
                    ("text", f"위치 x {_fmt(row['face_cx'])} y {_fmt(row['face_cy'])} · 아래 끝 {_fmt(row['face_y_max'])}")]
    if body_seen:
        details += [("text", f"몸 연속 {row['body_run_s']:.1f} s · 가시도 {_fmt(row['pose_vis_mean'])}"
                             f" · 어깨 {_fmt(row['pose_vis_shoulders'])}")]
    else:
        details += [("text", f"몸 못 본 지 {row['body_unseen_s']:.1f} s")]
    details += [("text", f"밝기 화면 {_fmt(row['bright_frame'], '{:.0f}')} · 얼굴 {_fmt(row['bright_face'], '{:.0f}')}"),
                ("text", f"선명도 화면 {_fmt(row['lapvar_frame'], '{:.0f}')} · 얼굴 {_fmt(row['lapvar_face'], '{:.0f}')}"),
                ("muted", f"얼굴 {row['ms_face_lm']:.1f} · 검출 {row['ms_face_det']:.1f} · 몸 {row['ms_pose']:.1f} ms")]
    return compact, details


def _fitted_font(d, text: str, size: int, bold: bool, max_w: int):
    """The largest font not bigger than `size` with which `text` fits into max_w pixels (down to 10 px)."""
    while size > 10:
        f = _font(size, bold)
        if d.textlength(text, font=f) <= max_w:
            return f
        size -= 1
    return _font(size, bold)


def _panel(height: int, row: dict, header: str, phase_label: str, panel_w: int = PANEL_W) -> np.ndarray:
    """The value panel (BGR) for one frame."""
    fs = int(max(12, min(16, height // 25)))
    big = int(round(fs * 1.2))
    panel = Image.new("RGB", (panel_w, height), PANEL_BG[::-1])
    d = ImageDraw.Draw(panel)
    max_w = panel_w - 20
    compact, details = panel_lines(row, header, phase_label)
    y = 6
    for style, text in compact:
        if style == "state":
            lh = int(round(big * 1.35))
            a, b, flags = text.split("|")
            f = _font(big, bold=True)
            x = 10
            for label, seen in ((a, flags[0] == "1"), (b, flags[1] == "1")):
                r = big // 3
                col = SERIES[0] if seen else MUTED
                d.ellipse([x, y + lh // 2 - r, x + 2 * r, y + lh // 2 + r], fill=col if seen else None, outline=col,
                          width=2)
                d.text((x + 2 * r + 6, y), label, font=f, fill="#ffffff" if seen else "#a9a8a2")
                x += int(d.textlength(label, font=f)) + 2 * r + 26
        else:
            size = big if style.startswith("big") else fs
            lh = int(round(size * 1.35))
            f = _fitted_font(d, text, size, style in ("title", "big"), max_w)
            fill = {"title": "#ffffff", "big": "#ffffff", "bigmuted": "#a9a8a2", "muted": "#a9a8a2"}[style]
            d.text((10, y), text, font=f, fill=fill)
        y += lh
    y += 4
    d.line([(10, y), (panel_w - 10, y)], fill="#4a4a46", width=1)   # separates the compact block from the details
    y += 6
    small = fs - 1
    for style, text in details:
        f = _fitted_font(d, text, small, False, max_w)
        d.text((10, y), text, font=f, fill={"text": "#d8d7d0", "muted": "#a9a8a2"}[style])
        y += int(round(small * 1.38))
    return cv2.cvtColor(np.asarray(panel), cv2.COLOR_RGB2BGR)


def compose_frame(img: np.ndarray, draw: dict, row: dict, header: str, phase_label: str = ""):
    """The one frame composition used by both overlay.mp4 and the live window (run.py --show):
    landmarks and geometry drawn on a copy of the frame, plus the value panel on the right (the panel never
    covers the image). Returns (annotated frame, composed frame)."""
    annotated = annotate(img, draw)
    return annotated, np.hstack([annotated, _panel(annotated.shape[0], row, header, phase_label)])


def contact_sheet(items: list, title: str, out_path: str, phase_labels: dict, cols: int = 4, tile_w: int = 320):
    """items = [(annotated_image, row)]. Each tile gets a 3-line caption underneath."""
    if not items:
        return
    fs, lh = 14, 20
    cap_h = 3 * lh + 10
    tiles = []
    for img, row in items:
        h = int(round(img.shape[0] * tile_w / img.shape[1]))
        im = cv2.resize(img, (tile_w, h), interpolation=cv2.INTER_AREA)
        tile = Image.new("RGB", (tile_w, h + cap_h), SURFACE)
        tile.paste(Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)), (0, 0))
        d = ImageDraw.Draw(tile)
        phase = phase_labels.get(row.get("syn_phase") or "", "")
        l1 = f"t {row['t_s']:.1f} s" + (f" · {phase}" if phase else "")
        l2 = f"얼굴 {row['face_state']} · 몸 {row['body_state']} · 얼굴 수 {row['face_count']}"
        if row["face_state"] == SEEN:
            l3 = (f"시작 대비 ×{_fmt(row['iod_ratio_start'])} · 좌우 {_fmt(row['yaw_deg'], '{:+.0f}')}°"
                  f" · 상하 {_fmt(row['pitch_deg'], '{:+.0f}')}°")
        else:
            l3 = f"얼굴 못 본 지 {row['face_unseen_s']:.1f} s"
        for k, (txt, bold) in enumerate(((l1, True), (l2, False), (l3, False))):
            d.text((6, h + 4 + k * lh), txt, font=_font(fs, bold), fill=INK if k < 2 else INK2)
        tiles.append(tile)
    th = max(t.height for t in tiles)
    rows_n = int(math.ceil(len(tiles) / cols))
    gap, top = 8, 44
    sheet = Image.new("RGB", (cols * tile_w + (cols + 1) * gap, top + rows_n * (th + gap) + gap), "#f0efec")
    d = ImageDraw.Draw(sheet)
    d.text((gap, 10), title, font=_font(18, True), fill=INK)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet.paste(t, (gap + c * (tile_w + gap), top + r * (th + gap)))
    sheet.save(out_path)


# ---------------------------------------------------------------------------------------------- plots
def _setup_mpl():
    family = plt.rcParams["font.family"]          # matplotlib default when no Korean-capable font was found
    if FONT_REG is not None:
        for path in {FONT_REG, FONT_BOLD}:
            font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=FONT_REG).get_name()
    plt.rcParams.update({
        "font.family": family, "axes.unicode_minus": False, "font.size": 10,
        "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
        "axes.facecolor": SURFACE, "figure.facecolor": SURFACE, "legend.frameon": False,
        "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.5,
    })


def _col(rows, key):
    out = []
    for r in rows:
        v = r.get(key)
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(float("nan"))
    return np.array(out)


def _phase_spans(rows):
    spans, start, cur = [], 0, rows[0].get("syn_phase") or ""
    for i, r in enumerate(rows[1:], 1):
        p = r.get("syn_phase") or ""
        if p != cur:
            spans.append((cur, start, i - 1))
            start, cur = i, p
    spans.append((cur, start, len(rows) - 1))
    return spans


def _make_axes(rows, n, ratios, height):
    """Figure with n data panels; synthetic runs get an extra thin strip on top that names the phases."""
    synthetic = bool(rows[0].get("syn_phase"))
    if synthetic:
        fig, axs = plt.subplots(n + 1, 1, figsize=(12, height + 0.6), sharex=True,
                                gridspec_kw={"height_ratios": [0.32] + list(ratios)})
        return fig, axs[0], list(axs[1:])
    fig, axs = plt.subplots(n, 1, figsize=(12, height), sharex=True, gridspec_kw={"height_ratios": list(ratios)})
    return fig, None, list(axs)


def _shade_phases(strip, axes, rows, t, phase_labels):
    """Alternate light bands per synthetic phase on every panel; phase names in the top strip."""
    if strip is None:
        return
    spans = _phase_spans(rows)
    dt = (t[1] - t[0]) if len(t) > 1 else 0.0
    for k, (p, a, b) in enumerate(spans):
        x0, x1 = t[a] - dt / 2, t[b] + dt / 2
        for ax in axes + [strip]:
            if k % 2 == 1:
                ax.axvspan(x0, x1, color="#efeee9", zorder=0, lw=0)
        strip.text((x0 + x1) / 2, 0.5, phase_labels.get(p, p), ha="center", va="center", fontsize=8.5, color=INK2,
                   transform=strip.get_xaxis_transform())
    strip.set_yticks([])
    strip.grid(False)
    for side in ("left", "bottom"):
        strip.spines[side].set_visible(False)
    strip.tick_params(axis="x", length=0)
    strip.set_title("합성 입력의 단계 (사진을 키우고·옮기고·돌리고·지운 구간)", loc="left", fontsize=9.5, color=INK2)


def _seen_bars(ax, rows, t):
    dt = (t[1] - t[0]) if len(t) > 1 else 1.0
    for y, key, name, col in ((1, "face_state", "얼굴", SERIES[0]), (0, "body_state", "몸", SERIES[1])):
        seen = np.array([r[key] == SEEN for r in rows])
        for flag, color in ((True, col), (False, "#d3d2cc")):
            idx = np.where(seen == flag)[0]
            if len(idx):
                # merge consecutive frames into spans
                breaks = np.where(np.diff(idx) > 1)[0]
                starts = np.r_[idx[0], idx[breaks + 1]]
                ends = np.r_[idx[breaks], idx[-1]]
                ax.broken_barh([(t[s] - dt / 2, t[e] - t[s] + dt) for s, e in zip(starts, ends)], (y - 0.35, 0.7),
                               facecolors=color, linewidth=0)
    ax.set_yticks([0, 1], ["몸", "얼굴"])
    ax.set_ylim(-0.6, 1.6)
    ax.grid(False)
    ax.set_title("보임 (색) / 못 봄 (회색) — 결과가 비면 '못 봄'이며 '사람 없음'이 아님", loc="left", fontsize=10, color=INK)


def _lines(ax, t, series, title, logy=False):
    """One panel, one y-axis; units are in the title. Legend outside on the right when >= 2 series."""
    for k, (y, name) in enumerate(series):
        ax.plot(t, y, color=SERIES[k], label=name, marker="o" if np.isfinite(y).sum() < 40 else None, markersize=3)
    ax.set_title(title, loc="left", fontsize=10, color=INK)
    if logy:
        ax.set_yscale("log")
    if len(series) >= 2:
        ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=9)


def plot_observations(rows, title, out_path, phase_labels):
    _setup_mpl()
    t = _col(rows, "t_s")
    fig, strip, axes = _make_axes(rows, 7, [0.8, 0.8, 1, 1, 1.2, 1.2, 1.1], 17)
    _seen_bars(axes[0], rows, t)
    counts = _col(rows, "face_count")
    axes[1].step(t, counts, where="mid", color=SERIES[0])
    axes[1].set_title("얼굴 수 (Face Detector 결과 개수)", loc="left", fontsize=10, color=INK)
    axes[1].set_ylim(-0.3, max(1.0, float(np.nanmax(counts))) + 0.3)
    axes[1].yaxis.set_major_locator(MaxNLocator(integer=True))
    _lines(axes[2], t, [(_col(rows, "iod_frac_w"), "눈 사이 거리 ÷ 화면 폭")], "눈 사이 거리 ÷ 화면 폭 (얼굴 못 본 프레임은 빈칸)")
    _lines(axes[3], t, [(_col(rows, "iod_ratio_start"), "시작 대비")],
           "눈 사이 거리: 세션 시작(첫 얼굴 프레임) 대비 비율 — 1 = 시작 때와 같음")
    axes[3].axhline(1.0, color="#c3c2b7", lw=0.8, zorder=1)
    _lines(axes[4], t, [(_col(rows, "yaw_deg"), "좌우 (yaw)"), (_col(rows, "pitch_deg"), "상하 (pitch)"),
                        (_col(rows, "roll_deg"), "기울기 (roll)")], "고개 방향 (변환 행렬에서 꺼낸 각도, 도)")
    _lines(axes[5], t, [(_col(rows, "face_cx"), "가로 위치 x"), (_col(rows, "face_cy"), "세로 위치 y"),
                        (_col(rows, "face_y_max"), "얼굴 아래 끝 y")],
           "영상 안 얼굴 위치 (0 = 왼쪽·위, 1 = 오른쪽·아래)")
    _lines(axes[6], t, [(_col(rows, "face_run_s"), "얼굴 연속 시간"), (_col(rows, "face_unseen_s"), "얼굴 못 본 시간"),
                        (_col(rows, "body_run_s"), "몸 연속 시간")], "추적 연속 (초)")
    axes[6].set_xlabel("프레임 시각 (초)")
    _shade_phases(strip, axes, rows, t, phase_labels)
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, color=INK, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(out_path, dpi=100)
    plt.close(fig)


def plot_quality_timing(rows, title, out_path, phase_labels):
    _setup_mpl()
    t = _col(rows, "t_s")
    fig, strip, axes = _make_axes(rows, 4, [1.1, 1, 1, 1.3], 11.5)
    _lines(axes[0], t, [(_col(rows, "pose_vis_mean"), "몸 점 가시도 평균(33점)"),
                        (_col(rows, "pose_vis_shoulders"), "어깨 가시도(11·12)"),
                        (_col(rows, "pose_pres_mean"), "몸 점 존재 평균(33점)"),
                        (_col(rows, "face_det_score"), "얼굴 검출 점수")], "측정 신뢰도 재료 (0~1, 라이브러리 출력 그대로)")
    _lines(axes[1], t, [(_col(rows, "bright_frame"), "화면 전체"), (_col(rows, "bright_face"), "얼굴 영역")],
           "밝기 (회색조 평균, 0~255)")
    _lines(axes[2], t, [(_col(rows, "lapvar_frame"), "화면 전체"), (_col(rows, "lapvar_face"), "얼굴 영역")],
           "선명도 (라플라시안 분산, 로그 눈금 — 작을수록 흐림)", logy=True)
    stage_names = {"ms_face_lm": "얼굴 점(Face Landmarker)", "ms_face_det": "얼굴 검출(Face Detector)",
                   "ms_pose": "몸 점(Pose lite)", "ms_quality": "밝기·선명도(OpenCV)",
                   "ms_prep": "입력 준비", "ms_features": "기하 계산", "ms_total": "합계(파일 읽기 제외)"}
    _lines(axes[3], t, [(_col(rows, k), v) for k, v in stage_names.items()], "처리 시간 (ms, 프레임마다)")
    axes[3].set_xlabel("프레임 시각 (초)")
    _shade_phases(strip, axes, rows, t, phase_labels)
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, color=INK, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out_path, dpi=100)
    plt.close(fig)


# ---------------------------------------------------------------------------------------------- timing
def timing_stats(rows) -> list[dict]:
    """p50 / p95 per stage. p50 = median (half of the frames were faster); p95 = 95th percentile (95 % of the
    frames were faster - the slow tail). numpy.percentile with its default linear interpolation.
    The first processed frame carries one-time start-up work, so it is left out of p50 / p95 and reported
    on its own (first_frame_ms); every other frame counts, re-detections included."""
    out = []
    for k in STAGES:
        v = _col(rows, k)
        first = float(v[0]) if v.size else float("nan")
        v = v[1:]
        v = v[np.isfinite(v)]
        out.append({"stage": k, "n": int(v.size), "p50_ms": float(np.percentile(v, 50)) if v.size else float("nan"),
                    "p95_ms": float(np.percentile(v, 95)) if v.size else float("nan"),
                    "max_ms": float(v.max()) if v.size else float("nan"), "first_frame_ms": first})
    return out
