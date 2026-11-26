"""선택 열 (optional columns) of events.py, made from one frame's perception outputs.

Layers: 추론 (app/inference/vision.py MediaPipe; app/inference/head.py H1 · head_direction.py P1) -> 관측값
(features.py) + this file -> 사건 (events.py) -> 상황 (situation.py). numpy only (no OpenCV, MediaPipe or ONNX Runtime
here), so it is tested on arrays.

Columns (names = the ones events.py reads, then observation-only columns no rule reads yet):
  people_behind_count   heads standing behind the main user: the boxes of this frame whose track is decided 'behind'
                        (below). 0 when no head other than the main user's is found; None (blank, the cue is missing)
                        when another head's role cannot be told. 'Standing, not passing' is the events layer's job
                        (stay_min_s). Absent (column missing) when the head detector did not run.
  companion_box         (x0, y0, x1, y1) as fractions of the frame: the largest box of this frame whose track is decided
                        'companion'; None when every other head is decided not to be one. The key is left out of the
                        row when no companion is found and another head's role cannot be told (events.py: a row
                        without the column = the companion cannot be told there, not 'no companion').
  shoulder_cx, shoulder_cy  midpoint of pose points 11 and 12 (left / right shoulder [D3]) as fractions of the frame;
                        None when the body is not seen.
  mouth_motion          largest absolute change of a mouth / jaw blendshape (params.mouth_dials) from that dial's
                        baseline = the median of the same dial over the previous mouth_baseline_s seconds of the same
                        unbroken face run (decision list 2026-10-10 §16: the person's baseline subtracted, change
                        only). None while the face is not seen, while the run is shorter than mouth_baseline_s, and
                        when blendshapes are off.
  aid_owner, aid_top_class, aid_any_score, aid_wheelchair_score, aid_kind, aid_class_scores, aid_box, aid_count   the
                        walking-aid detector's person boxes for the main user (aid_columns; app/inference/aid.py, an
                        optional input that runs only when its ONNX file is given; absent otherwise). The detector's
                        classes are person-level (a person with a crutch, cane, walker or wheelchair, or none): it gives
                        no position of the aid itself, so the shoulder line is used to find the main user's person box,
                        not to judge how the aid is held. The anchor is the main user's head-box centre when the
                        head detector ran (no box in the frame: no anchor), else the pose's two shoulder points. The
                        user's box = among the person boxes holding the anchor, the one whose top edge is nearest the
                        head box's top edge (the box that starts at this person's head; the smallest without a head
                        box). Its class scores (aid_class_scores, {class: objectness x
                        class score}), its best class (aid_top_class), aid_any_score = the largest of its crutch,
                        cane, walker and wheelchair scores ('uses an assistive device', the owner's decision),
                        aid_wheelchair_score, aid_kind ('wheelchair' when the wheelchair score is above the largest of
                        the crutch, cane and walker scores, else 'standing': which scene the judgment layer routes to,
                        1-2 or 1-1) and aid_box come from that one box. aid_owner: 'yes' = its best class is one of the
                        four aids;
                        'no' = the anchor is known and its best class is another one, or no box holds the anchor (an
                        aid seen on someone else is 'no'); 'unknown' = no anchor. aid_count = person boxes in the frame
                        at or above params.aid_score_min (the recording floor); aid_person_count = those above
                        params.aid_person_min (the detector's person operating point), the only ones that count as a
                        person seen and that can be the main user's box (None without the value). No threshold of
                        'uses an aid' is applied here: that yes / no is the tag aid_use (situation.py).
  aid_head_score, aid_head_class, aid_head_box   the walking-aid detector under the head_centre reading
                        (params.aid_rule; aid_head_columns, 2026-11-26), for the kiosk-view detector files, where an
                        aid user is one aid-class box around the user and the aid: for every class except pedestrian
                        the highest score among that class's kept boxes (app/inference/aid.py Aids.class_boxes: the
                        class's channel on every anchor, floor aid_score_min, NMS aid_nms_iou inside the class) that
                        contain the centre of the main user's head box, and of those the highest, with the class and
                        the box it came from (equal scores: the class first in the model's order). 0.0 with no class
                        and no box when the head box is there and no kept box contains its centre; None (all three)
                        when the frame has no main-user head box (the head detector off: on every row). Present only
                        when the detector runs with this reading; the aid_columns are written then too. No threshold
                        here: aid_use compares the window median with params.aid_head_min (situation.py).
                        Under the head_centre_carry reading (AidCarry, 2026-11-26) the three columns are the same on
                        every row with the main user's head box, and a frame without that box follows the aid-class
                        box of the latest head row with the head tracker's association rule (params.track_iou_min,
                        track_max_gap_s; 'Tracks' below): the kept box of any aid class with the highest IoU against
                        it, when that IoU is at least track_iou_min, gives its score, class and box and becomes the box
                        followed; no box matched for longer than track_max_gap_s ends the carry. A head row whose value
                        is 0.0 clears the box, a head row with a value replaces it, and nothing is carried before a
                        head row. The carry does not end with the head track (the user's head can be lost for long
                        stretches while the aid box stays).
  aid_head_from         under the head_centre_carry reading only: 'head' (the value of a row with the main user's head
                        box, as head_centre), 'carried' (a value followed from the latest head row), None (no value).
  iod_ratio_user        the main user's inter-ocular distance (iod_px) over a reference of the same user's face rows
                        before this one (FaceSizeRef; tree table 3-가 2-1 '시작 대비 눈 사이 거리 비'). Anchor = the
                        start of the current main-user track (primary_track changes) and of the touch-log session.
                        The person may still be walking up after either anchor (a first press can come while the user
                        is stepping in), so the reference is the median of the upper half of the rows so far (the
                        smaller walk-up sizes drop out). With a touch log the reference collects only from the
                        session's first press and leaves out the rows whose ratio is above params.approach_ratio_min,
                        so a user who leans in and stays close keeps the ratio. Without a touch log (live.py today,
                        replays of recordings without one) the lean enters the reference and a long lean fades.
                        A user already close at the anchor has that close size as the reference. None while the face is
                        not the main user's (its iod_px is blank), before the reference has a row, and before the first
                        press. Without the head detector the reference starts again when nobody has been seen for
                        longer than params.track_max_gap_s.
  head_ratio_user       the main user's head-box height over the same user's reference (HeadSizeRef): the anchors and
                        rules of iod_ratio_user, with params.head_approach_ratio_min as the keep-out. None without the
                        main user's box, before the reference has a row and before the first press. Absent when the
                        head detector did not run.
  dpitch_user_deg       the main user's head pitch (pitch_deg, + = down) minus the pitch of the same user's first face
                        row after the anchor (PitchRef): the anchors of iod_ratio_user (a new main-user track that is
                        not a reacquisition in the same place, the touch-log session and its first press, and without
                        the head detector nobody seen for longer than params.track_max_gap_s), except that a stitched
                        track break (main_user_stitched) keeps this reference (PitchRef). None while the face is
                        not the main user's, without a pitch and before the first press. The session-start
                        dpitch_start_deg of features.py stays as an observation column; this is the one face_approach's
                        head-down gate reads.
  main_user_prev_track, main_user_gap_s, main_user_body_kept   on the first row of a new main-user track that follows
                        an earlier main-user track of the same touch-log session (MainUserChange; tree table 3-가 2-2
                        '앞 사람 추적이 끊긴 뒤'): the earlier track's id, the seconds since its last head box, and whether
                        the body was seen on every row from then to this one (2-2 '기다리는 동안 몸이 계속 보였는지';
                        someone's body, not necessarily the same person's). None on every other row. Absent when the
                        head detector did not run.
  main_user_reacquired  on the same row: True when the new main-user box overlaps the ended track's last box by at
                        least params.track_iou_min (the SORT association value the tracker uses) - the same place, so
                        the head detector lost and found the same person (a cap, a deep bow, a camera stall) - and the
                        place did not stand empty: with body_unseen_s on the rows, nothing of the user (that head box
                        or a body) was unseen for longer than params.track_max_gap_s at a stretch (the gap a head track
                        survives; main_user_body_gap_s), else the body was seen on every row (main_user_body_kept);
                        False otherwise; None when a box is missing. The tag user_changed does not count a
                        reacquisition as a change.
  main_user_body_gap_s  on the same row: the longest stretch since the ended track's last box, up to and including this
                        row, with neither that box nor a body (body_unseen_s, at most the time since the last box); None
                        when a row lacks body_unseen_s.
  main_user_prev_settled  on the same row: whether the earlier main user had settled at the kiosk - its head-box
                        height had stopped growing (Settle: the first params.segment_s bin whose median height is not
                        above the bin before it). False: the track changed during the first approach (a walk-up, or the
                        head detector passing the main user on before anyone stood at the kiosk); the tag user_changed
                        does not count that as a change. A reacquisition or a stitch keeps the earlier track's state.
  main_user_new_start_s, main_user_start_shift, main_user_start_size, main_user_stitched   on the same row, the track
                        break measured without appearance (StrongSORT's AFLink idea, Du et al. IEEE TMM 2023: link
                        tracklets from time and position only): the seconds from the earlier track's last head box to the
                        new track's first box (the new track may have started as another head while the earlier one
                        still lived; <= 0 = both were seen at once, so two people), the shift of the first box's centre
                        from that last box (horizontal difference over the last box's width and vertical difference over
                        its height, as a Euclidean distance: the R-CNN box deltas tx, ty, Girshick et al. CVPR 2014
                        appendix C) and the size step |ln(first height / last height)| (R-CNN th). main_user_stitched =
                        True when the new track began after the last box and within params.track_max_gap_s (the gap
                        a track survives) with shift <= params.stitch_shift_max and size <= params.stitch_size_max: the
                        same user whose track broke in place (a cap, a deep bow); False otherwise; None when a boundary
                        has no value or a box is missing. The tag user_changed does not count a stitch as a change;
                        the size references (iod_ratio_user, head_ratio_user) still start again there (FaceSizeRef);
                        the pitch reference (dpitch_user_deg) goes on (PitchRef).
  main_user_prev_h, main_user_new_h, main_user_h_ratio, main_user_new_was_role, main_user_new_rel_dist,
  main_user_new_growth  size evidence on the same row, observation only (no threshold): the head-box height (fraction
                        of the frame) of the earlier main user's last box and of the new main user's box, new / earlier;
                        and when the new main-user track was already seen as another head before the change, its last
                        role then (head_boxes 'role': behind, companion, other or unknown), its last rel_dist_med then
                        (the earlier main user's height / its height: > 1 = smaller, i.e. farther), and its growth = its
                        height now / the median of its heights while it was not the main user. A person behind becomes
                        the next user by stepping forward, so a growth near 1 with rel_dist above 1 means the head that
                        took over is still at a behind size. None when not known.
  head_count, primary_box, primary_score, primary_from   all kept head boxes; the main user's box, its H1 score and how
                        it was chosen ('track' = the main user's track from earlier frames, 'face' | 'largest' = chosen
                        anew at this frame); observation only. primary_box is None while the main user's track is alive
                        but has no box in this frame.
  primary_track         track id of the main user (also while its track has no box in this frame); observation only
  face_in_primary       whether the centre of the face the Face Landmarker tracks lies inside the main user's box: True,
                        False, or None when the face or the main user is not there. While the main user's track is
                        alive but has no box in this frame: False when the face centre lies in another track's box,
                        None when it lies in no head box (the head detector may have missed the main user). False =
                        the face is someone else's: the chain (chain.FrameChain) then blanks the face values of the
                        row (FACE_VALUE_COLUMNS) and mouth_motion, so the events layer reads them as missing, not as
                        the main user's
  face_track            track id of the largest head box around the face centre (the box choose_primary takes by the
                        face), or None; observation only (whose face the landmarker follows)
  head_boxes            every head box of the frame in H1 order, one dict each: track (id), cx, cy, w, h (fractions of
                        the frame), score (H1), role ('primary' | 'companion' | 'behind' | 'other' | 'unknown') and the
                        cues against the main user - rel_dist, lateral of this frame and rel_dist_med, lateral_med of
                        the trailing window (None for the main user's box and where a cue cannot be computed). Written
                        as one JSON cell in rows.csv ("[]" = no head); observation only, so later analyses need no rerun
  head_dir_middle, head_dir_up, head_dir_left, head_dir_right, head_dir_back   P1 probabilities of the main user's
                        head (classes 중간 · 위 · 좌 · 우 · 뒤, AI Hub 70 '촬영방향'); None without a main-user head or
                        without the P1 model. Observation only: no rule reads them yet.

Tracks (HeadTracker; params track_iou_min, track_max_gap_s): frame by frame, each head box joins the live track whose
last box overlaps it most, highest IoU first, when that IoU is at least track_iou_min (the association step of SORT,
Bewley et al. 2016, without its Kalman prediction and with a greedy instead of a Hungarian assignment); a box that joins
none starts a new track. A track ends when it has had no box for more than track_max_gap_s seconds.

Main user (HeadPeople; params.primary_rule, [파일럿] rule). The main user is a track: while its track is alive it
stays the main user, and only after it ended is a new one chosen among the boxes of the frame (choose_primary):
'face_then_largest' = the largest head box that contains the centre of the face the Face Landmarker tracks (face_cx,
face_cy), so the yaw, the mouth and the head box belong to the same person at the moment of choice; without such a box
(face not seen, or no box around it) the largest box, ties broken by the distance of the box centre to the frame's
vertical centre line. 'largest' = always the largest box. The Face Landmarker follows one face on its own, so after the
choice a face centre outside the main user's box (primary_box), or inside another track's box while the main user's
track has no box in the frame, means the face and the main user are two people; that frame's face values are not the
main user's (face_in_primary). A new touch-log session (chain.FrameChain) starts the tracks, the main user and the cue
history again (HeadPeople.reset; tree section 4 ①: a new session is judged from the start); track ids keep counting, so
an id names one track in a run.

Cues of every other track against the main user (relative_cues), in frames where both have a box: rel_dist = h_primary /
h_box (box heights; a pinhole camera images a head at a size inversely proportional to its distance, so with heads of
similar size this is the distance from the camera relative to the main user's, research 56 section 4 [유도]; the height
is less cut than the width at the left and right frame edges) and lateral = (cx_box - cx_primary) / h_primary in pixels
(signed, + = right in the image; in main-user head heights). Each track keeps its cues of the last role_window_s
seconds; their medians (rel_dist_med, the signed lateral_med) decide its role (decide_role):
  companion   rel_dist_med <= companion_rel_dist_max ('비슷한 크기') and |lateral_med| >= companion_lateral_min ('옆')
  behind      rel_dist_med > 1 (decision table 3: '주 사용자보다 작은 상자', SMALLER_THAN_USER) and rel_dist_med >=
              behind_rel_dist_min ('뒤쪽') and not a companion
  other       neither; unknown = cannot tell (a boundary without a value, or no cue in the window)
The three boundaries have no value (params.UNDECIDED): until a value bundle gives one, the roles they decide are
'unknown' and the cues are still written (head_boxes). The tracks' cue history starts again when the main user changes.
"""
from __future__ import annotations

import bisect
import json
import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from app.inference.head_direction import DIR_KEYS

from .events import SEEN

SHOULDERS = (11, 12)   # left / right shoulder in the 33-point pose map [D3]; = features.SHOULDERS
DIR_COLUMNS = tuple(f"head_dir_{k}" for k in DIR_KEYS)
HEAD_COLUMNS = ("people_behind_count", "companion_box", "head_count", "primary_box", "primary_score",
                "primary_from", "primary_track", "face_in_primary", "face_track") + DIR_COLUMNS + ("head_boxes",)
AID_COLUMNS = ("aid_owner", "aid_top_class", "aid_any_score", "aid_wheelchair_score", "aid_kind", "aid_class_scores",
               "aid_box", "aid_count", "aid_person_count")
AID_HEAD_COLUMNS = ("aid_head_score", "aid_head_class", "aid_head_box")   # the head_centre reading (aid_head_columns)
AID_CARRY_COLUMNS = ("aid_head_from",)   # the head_centre_carry reading (AidCarry): where the row's value came from
AID_FROM_HEAD, AID_FROM_CARRIED = "head", "carried"   # the values of aid_head_from
CHANGE_COLUMNS = ("main_user_prev_track", "main_user_gap_s", "main_user_body_kept", "main_user_prev_h",
                  "main_user_new_h", "main_user_h_ratio", "main_user_new_was_role", "main_user_new_rel_dist",
                  "main_user_new_growth", "main_user_reacquired", "main_user_prev_settled", "main_user_new_start_s",
                  "main_user_start_shift", "main_user_start_size", "main_user_stitched", "main_user_body_gap_s")
PHONE_COLUMNS = ("phone_owner", "phone_at", "phone_score", "phone_box", "phone_count")
OPTIONAL_COLUMNS = HEAD_COLUMNS + CHANGE_COLUMNS + AID_COLUMNS + AID_HEAD_COLUMNS + AID_CARRY_COLUMNS + PHONE_COLUMNS \
    + ("shoulder_cx", "shoulder_cy", "mouth_motion", "iod_ratio_user", "head_ratio_user", "dpitch_user_deg")
# features.COLUMNS that the Face Landmarker's face gives (its position, size, angles and the face box's image
# statistics): blanked where that face is not the main user's (face_in_primary False). face_state, the face detector's
# columns (face_count, face_det_score, det_box_w_frac) and the run counters stay.
FACE_VALUE_COLUMNS = ("iod_px", "iod_frac_w", "iod_ratio_start", "yaw_deg", "pitch_deg", "roll_deg", "dyaw_start_deg",
                      "dpitch_start_deg", "face_cx", "face_cy", "face_y_max", "face_shift", "iod_step", "bright_face",
                      "lapvar_face")
SMALLER_THAN_USER = 1.0   # decision table 3 '주 사용자보다 작은 상자': rel_dist > 1 = a head box smaller than the user's
ROLES = ("primary", "companion", "behind", "other", "unknown")


@dataclass(frozen=True)
class HeadRoles:
    """Who is who among the head boxes of one frame (indices into the boxes)."""
    primary: int | None            # the main user's box; None when the main user's track has no box in this frame
    companion: int | None          # the largest box of a track decided 'companion', or None
    behind: tuple                  # the boxes of tracks decided 'behind'
    primary_from: str | None       # 'track' | 'face' | 'largest' | None (no box of the main user in this frame)
    tracks: tuple = ()             # track id per box
    roles: tuple = ()              # role per box (ROLES)
    cues: tuple = ()               # per box (rel_dist, lateral, rel_dist_med, lateral_med); None for the main user's
    primary_track: int | None = None
    behind_known: bool = True      # every other box is decided behind or not
    companion_known: bool = True   # a companion was found, or every other box is decided not to be one


def _finite(v) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _areas(boxes: np.ndarray) -> np.ndarray:
    return (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])          # fraction units: ratios = pixel ratios


def _order(boxes: np.ndarray) -> list:
    """Box indices largest first; ties by distance to the vertical centre line, then index (stable)."""
    areas = _areas(boxes)
    centre_x = (boxes[:, 0] + boxes[:, 2]) / 2.0
    return sorted(range(len(boxes)), key=lambda i: (-areas[i], abs(centre_x[i] - 0.5), i))


def inside(face_xy, box) -> bool:
    """Whether the point (x, y) lies inside the box (x0, y0, x1, y1), edges included."""
    return bool(box[0] <= face_xy[0] <= box[2] and box[1] <= face_xy[1] <= box[3])


def face_box(boxes, face_xy):
    """Index of the largest head box around the face centre (ordered as choose_primary), or None."""
    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    if face_xy is None or not len(boxes):
        return None
    return next((i for i in _order(boxes) if inside(face_xy, boxes[i])), None)


def choose_primary(boxes, face_xy, rule: str) -> tuple:
    """(index, how) of the main user among one frame's head boxes (fractions x0, y0, x1, y1) by primary_rule (module
    docstring), how = 'face' | 'largest'; (None, None) without boxes. face_xy = (face_cx, face_cy) of the tracked face,
    or None when the face is not seen."""
    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    if not len(boxes):
        return None, None
    if rule == "face_then_largest":
        k = face_box(boxes, face_xy)
        if k is not None:
            return k, "face"
    return _order(boxes)[0], "largest"


def box_iou(a, b) -> float:
    """Intersection over union of two boxes (x0, y0, x1, y1); 0 when the union is empty."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0


class HeadTracker:
    """Head boxes linked into tracks with persistent ids (module docstring 'Tracks')."""

    def __init__(self, iou_min: float, max_gap_s: float):
        self.iou_min, self.max_gap_s = float(iou_min), float(max_gap_s)
        self.live = {}          # track id -> (last box, time of the last box)
        self.next_id = 1

    def update(self, t: float, boxes) -> list:
        """Track ids of this frame's boxes (same order). Tracks unseen for more than max_gap_s end first."""
        boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
        self.live = {k: v for k, v in self.live.items() if t - v[1] <= self.max_gap_s}
        pairs = sorted(((box_iou(boxes[i], last), i, k) for i in range(len(boxes))
                        for k, (last, _) in self.live.items()), key=lambda x: (-x[0], x[1], x[2]))
        ids, used = [None] * len(boxes), set()
        for value, i, k in pairs:
            if value < self.iou_min:
                break
            if ids[i] is None and k not in used:
                ids[i] = k
                used.add(k)
        for i in range(len(boxes)):
            if ids[i] is None:
                ids[i], self.next_id = self.next_id, self.next_id + 1
            self.live[ids[i]] = (boxes[i].copy(), t)
        return ids


def relative_cues(box, primary_box, frame_wh) -> tuple:
    """(rel_dist, lateral) of a head box against the main user's box (both fractions x0, y0, x1, y1; module
    docstring); (None, None) when a box has no height."""
    W, H = frame_wh
    hp, hb = primary_box[3] - primary_box[1], box[3] - box[1]
    if hp <= 0 or hb <= 0 or H <= 0:
        return None, None
    lateral = ((box[0] + box[2]) / 2.0 - (primary_box[0] + primary_box[2]) / 2.0) * W / (hp * H)
    return float(hp / hb), float(lateral)


def _and3(*conditions):
    """Three-valued AND (as situation._all): False if any is False, else None if any is None, else True."""
    if any(c is False for c in conditions):
        return False
    return None if any(c is None for c in conditions) else True


def _at_most(value, bound):
    return None if value is None or bound is None else value <= bound


def _at_least(value, bound):
    return None if value is None or bound is None else value >= bound


def decide_role(rel_dist_med, lateral_med, params) -> tuple:
    """(role, companion, behind) of one other track from its window medians (module docstring): companion and behind
    are True, False or None (cannot tell: a boundary without a value, or no cue in the window)."""
    companion = _and3(_at_most(rel_dist_med, params.companion_rel_dist_max),
                      _at_least(None if lateral_med is None else abs(lateral_med), params.companion_lateral_min))
    smaller = None if rel_dist_med is None else rel_dist_med > SMALLER_THAN_USER
    behind = _and3(smaller, _at_least(rel_dist_med, params.behind_rel_dist_min),
                   None if companion is None else not companion)
    if companion is True:
        role = "companion"
    elif behind is True:
        role = "behind"
    elif companion is False and behind is False:
        role = "other"
    else:
        role = "unknown"
    return role, companion, behind


class HeadPeople:
    """Per frame: head tracks, the main user as a track, the cues of every other track and their roles (module
    docstring). One instance per input; replay and live share it through chain.FrameChain."""

    def __init__(self, params):
        self.p = params
        self.tracker = HeadTracker(params.track_iou_min, params.track_max_gap_s)
        self.primary_track = None
        self.history = {}        # track id -> deque of (t, rel_dist, lateral) against the current main user

    def reset(self):
        """Forget the tracks, the main user and the cue history (a new session); the next frame chooses the main user
        anew. Track ids keep counting."""
        self.tracker.live.clear()
        self.primary_track = None
        self.history.clear()

    def update(self, t: float, boxes, frame_wh: tuple, face_xy) -> HeadRoles:
        boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
        ids = self.tracker.update(t, boxes)
        how = None
        if self.primary_track is not None and self.primary_track not in self.tracker.live:
            self.primary_track = None                       # unseen for more than track_max_gap_s: ended
        if self.primary_track is None and len(boxes):
            k, how = choose_primary(boxes, face_xy, self.p.primary_rule)
            self.primary_track = ids[k]
            self.history.clear()                            # cues against the previous main user no longer apply
        primary = ids.index(self.primary_track) if self.primary_track in ids else None
        if primary is not None and how is None:
            how = "track"
        for k in [k for k in self.history if k not in self.tracker.live]:
            del self.history[k]
        cues, roles, companions, behind_status = [], [], [], []
        for i, k in enumerate(ids):
            if i == primary:
                cues.append(None)
                roles.append("primary")
                continue
            rel, lat = (None, None) if primary is None else relative_cues(boxes[i], boxes[primary], frame_wh)
            past = self.history.setdefault(k, deque())
            if rel is not None:
                past.append((t, rel, lat))
            while past and past[0][0] < t - self.p.role_window_s:
                past.popleft()
            rel_med = float(np.median([x[1] for x in past])) if past else None
            lat_med = float(np.median([x[2] for x in past])) if past else None
            role, companion, behind = decide_role(rel_med, lat_med, self.p)
            cues.append((rel, lat, rel_med, lat_med))
            roles.append(role)
            companions.append((i, companion))
            behind_status.append((i, behind))
        areas = _areas(boxes)
        found = sorted((i for i, c in companions if c is True), key=lambda i: (-areas[i], i))
        companion = found[0] if found else None
        return HeadRoles(primary, companion, tuple(i for i, b in behind_status if b is True), how, tuple(ids),
                         tuple(roles), tuple(cues), self.primary_track,
                         behind_known=all(b is not None for _, b in behind_status),
                         companion_known=companion is not None or all(c is False for _, c in companions))


def _r(v, digits):
    return None if v is None else round(float(v), digits)


def head_columns(heads, roles: HeadRoles, dir_probs) -> dict:
    """The head columns of one frame. heads = app.inference.head.Heads (or anything with .boxes and .scores);
    dir_probs = the P1 probabilities of the main user's head (5,), or None. companion_box is left out when the
    companion cannot be told (module docstring)."""
    boxes = np.asarray(heads.boxes, dtype=np.float64).reshape(-1, 4)
    out = {"people_behind_count": len(roles.behind) if roles.behind_known else None,
           "head_count": int(len(boxes)),
           "primary_box": None if roles.primary is None else tuple(float(v) for v in boxes[roles.primary]),
           "primary_score": None if roles.primary is None else float(heads.scores[roles.primary]),
           "primary_from": roles.primary_from, "primary_track": roles.primary_track}
    if roles.companion is not None:
        out["companion_box"] = tuple(float(v) for v in boxes[roles.companion])
    elif roles.companion_known:
        out["companion_box"] = None
    probs = None if dir_probs is None or roles.primary is None else np.asarray(dir_probs, dtype=np.float64).ravel()
    for k, col in enumerate(DIR_COLUMNS):
        out[col] = None if probs is None else float(probs[k])
    listed = []
    for i, b in enumerate(boxes):
        cue = roles.cues[i] if i < len(roles.cues) and roles.cues[i] is not None else (None,) * 4
        listed.append({"track": roles.tracks[i] if i < len(roles.tracks) else None,
                       "cx": _r((b[0] + b[2]) / 2.0, 6), "cy": _r((b[1] + b[3]) / 2.0, 6),
                       "w": _r(b[2] - b[0], 6), "h": _r(b[3] - b[1], 6), "score": _r(heads.scores[i], 4),
                       "role": roles.roles[i] if i < len(roles.roles) else None,
                       "rel_dist": _r(cue[0], 4), "lateral": _r(cue[1], 4),
                       "rel_dist_med": _r(cue[2], 4), "lateral_med": _r(cue[3], 4)})
    out["head_boxes"] = listed
    return out


def shoulder_columns(pose) -> dict:
    """Midpoint of pose points 11 and 12 (fractions); None when there is no pose or a coordinate is missing."""
    if pose is None:
        return {"shoulder_cx": None, "shoulder_cy": None}
    pose = np.asarray(pose, dtype=np.float64)
    xs = [_finite(pose[i, 0]) for i in SHOULDERS]
    ys = [_finite(pose[i, 1]) for i in SHOULDERS]
    return {"shoulder_cx": None if None in xs else (xs[0] + xs[1]) / 2.0,
            "shoulder_cy": None if None in ys else (ys[0] + ys[1]) / 2.0}


class MouthMotion:
    """mouth_motion per frame with the baseline of the current unbroken face run (module docstring)."""

    def __init__(self, dials, baseline_s: float):
        self.dials = tuple(dials)
        self.baseline_s = float(baseline_s)
        self.reset()

    def reset(self):
        self.buffer = deque()      # (t, dial vector) of the current face run within the last baseline_s seconds
        self.run_start = None

    def update(self, t: float, scores: dict | None) -> float | None:
        """scores = {blendshape name: score} of this frame's face, or None when the face is not seen / blendshapes are
        off (the run breaks). A dial missing from scores is an error: the model's names changed."""
        if scores is None:
            self.reset()
            return None
        missing = [d for d in self.dials if d not in scores]
        if missing:
            raise KeyError(f"blendshape dials missing from the model output: {missing}")
        vec = np.array([scores[d] for d in self.dials], dtype=np.float64)
        if self.run_start is None:
            self.run_start = t
        while self.buffer and self.buffer[0][0] < t - self.baseline_s:
            self.buffer.popleft()
        value = None
        if t - self.run_start >= self.baseline_s and self.buffer:
            baseline = np.median(np.stack([v for _, v in self.buffer]), axis=0)
            value = float(np.max(np.abs(vec - baseline)))
        self.buffer.append((t, vec))
        return value


def _track_id(value):
    """A track id as an int where it is one: rows.csv gives "2" where the head_boxes JSON cell gives 2. None for a
    blank cell (None, "", NaN)."""
    if value is None or value == "" or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if math.isfinite(number) and number.is_integer() else value


SIZE_STEP_PX = 0.1   # storage step of FaceSizeRef, not a decision value: sizes are counted per 0.1 px, so a median
                     # read from the counts is within half a step (0.05 px) of the exact one (test on a long run)


def blank_box(box) -> bool:
    """A primary_box cell without a box: None, or the empty cell of a rows.csv read back."""
    return box is None or box == ""


def main_user_face(row: dict) -> bool:
    """The row's face is the main user's: seen, and - when the head detector ran (the face_in_primary key is there) -
    matched to the main user's head box (face_in_primary True; also 'True' read back from rows.csv)."""
    if row.get("face_state") != SEEN:
        return False
    return "face_in_primary" not in row or row["face_in_primary"] is True or row["face_in_primary"] == "True"


class Settle:
    """Whether a size that grows while a person walks up has stopped growing (the person stands at the kiosk): the
    values are binned every segment_s seconds (params.segment_s, the runners' window step) and the size has settled at
    the first bin whose median is not above the median of the bin before it. No constant of its own; segment_s None:
    settled from the start. Once settled it stays so until reset."""

    def __init__(self, segment_s: float | None = None):
        self.segment_s = segment_s
        self.reset()

    def reset(self):
        self.settled = self.segment_s is None
        self.start, self.values, self.previous, self.last_bin = None, [], None, []

    def add(self, t: float, value: float) -> bool:
        """Add one value at time t; returns whether the size has settled (last_bin = the bin that settled it; the value
        given in the call that settles is not in it)."""
        if self.settled:
            return True
        if self.start is None:
            self.start = t
        elif t - self.start >= self.segment_s:
            median = float(np.median(self.values)) if self.values else None
            if median is not None and self.previous is not None and median <= self.previous:
                self.settled, self.last_bin = True, list(self.values)
                return True
            if median is not None:
                self.previous = median
            self.start, self.values = t, []
        self.values.append(value)
        return False

    def close(self) -> bool:
        """Whether the size had settled when the values end (a track that ends): the open bin is judged as it stands."""
        if not self.settled and self.values and self.previous is not None                 and float(np.median(self.values)) <= self.previous:
            self.settled, self.last_bin = True, list(self.values)
        return self.settled


class _UserAnchor:
    """The anchor shared by FaceSizeRef and PitchRef: a row whose primary_track differs from the track so far starts
    the reference again (reset), unless it carries one of the marks in KEEP (the same user: main_user_reacquired, a
    reacquisition in the same place; PitchRef also main_user_stitched); rows without that column (no head detector)
    start it again when neither face nor body has been seen for longer than max_gap_s. Subclasses define reset() and
    keep self.track and self.max_gap_s."""
    KEEP = ("main_user_reacquired",)   # MainUserChange marks on a new track's first row that keep the reference

    def _follow(self, row: dict):
        track = _track_id(row.get("primary_track"))
        if track is not None and track != self.track:
            if self.track is None or not any(row.get(k) in (True, "True") for k in self.KEEP):
                self.reset()                         # a new main user; the same person found again keeps it
            self.track = track
        elif "primary_track" not in row and self.max_gap_s is not None:
            unseen = [v for v in (_finite(row.get("face_unseen_s")), _finite(row.get("body_unseen_s"))) if v is not None]
            if len(unseen) == 2 and min(unseen) > self.max_gap_s:
                self.reset()                         # nobody seen longer than a track lives: the next person


class FaceSizeRef(_UserAnchor):
    """iod_ratio_user per frame (module docstring). The reference is the median of the upper half of the main user's
    iod_px rows since the anchor, so the smaller sizes of walking up drop out, whether the anchor came before or after
    the user arrived. With a press anchor (a touch log: the session's first press, which may come while the user is
    still stepping up) the rows whose ratio is above near_min (the face-approach boundary of the bundle) stay out of
    it, so the lean does not raise its own reference. Without a press anchor (no touch log: the anchor is the start of
    the main-user track) the lean enters the reference and a long lean fades. A row whose primary_track differs from
    the track so far starts the reference again, unless it marks a reacquisition in the same place
    (main_user_reacquired, MainUserChange: the same person found again after a cap or a camera stall), which keeps
    it. A stitched track break (main_user_stitched) starts it again: most stitches fall in the walk-up, whose smaller
    sizes would stay in the reference (company camera 150: 3 of the 4 stitched breaks came before the user settled).
    Rows without that column (no head detector) start it again when neither face nor body has been seen for
    longer than max_gap_s (params.track_max_gap_s, the gap after which a head track ends).

    Only the main user's face counts: with the head detector, a row whose face is not matched to the main user's box
    (face_in_primary not True) is no face here. The sizes are kept as counts per 0.1 px (SIZE_STEP_PX), so a session of
    any length keeps a bounded state; a median read from them is off by at most half a step."""

    def __init__(self, near_min: float | None = None, max_gap_s: float | None = None):
        self.near_min, self.max_gap_s = near_min, max_gap_s
        self.reset()

    def reset(self):
        self.counts = {}           # iod_px of the main user's face rows since the anchor, counted per SIZE_STEP_PX
        self.keys = []             # the counted sizes, sorted
        self.n = 0
        self.track = None

    def _add(self, value: float):
        key = round(value / SIZE_STEP_PX) * SIZE_STEP_PX
        if key <= 0:                                 # below half a step: no size to compare with
            return
        if key not in self.counts:
            bisect.insort(self.keys, key)
            self.counts[key] = 0
        self.counts[key] += 1
        self.n += 1

    def _kth(self, k: int) -> float:
        """The k-th smallest stored size (0-based)."""
        for key in self.keys:
            k -= self.counts[key]
            if k < 0:
                return key
        raise IndexError(k)

    def _median_from(self, start: int) -> float | None:
        """The median of the stored sizes from rank start on."""
        m = self.n - start
        if m <= 0:
            return None
        lo, hi = self._kth(start + (m - 1) // 2), self._kth(start + m // 2)
        return (lo + hi) / 2.0

    def median(self) -> float | None:
        return self._median_from(0)

    def reference(self) -> float | None:
        """The median of the upper half of the rows so far (the rows at or above their median): the smaller rows of
        walking up drop out of it, whichever anchor started it (the main-user track, or the session's first press,
        which may come while the user is still stepping up to the kiosk)."""
        median = self.median()
        if median is None:
            return None
        below = sum(self.counts[key] for key in self.keys if key < median)
        return self._median_from(below)

    def _value(self, row: dict) -> float | None:
        """The size this reference follows: the main user's iod_px."""
        return _finite(row.get("iod_px")) if main_user_face(row) else None

    def update(self, row: dict, collect: bool = True, press_anchor: bool = False) -> float | None:
        """iod_ratio_user of this row. collect False (a touch log without a press in this session yet): nothing is
        compared or collected. press_anchor True (a touch log: the reference starts at the session's first press):
        rows above near_min stay out of the reference, so the lean does not raise it; the reference itself is the
        same upper-half median with either anchor."""
        self._follow(row)
        iod = self._value(row)
        if not collect or iod is None or iod <= 0:
            return None
        reference = self.reference()
        ratio = None if reference is None else iod / reference
        if not (press_anchor and self.near_min is not None and ratio is not None and ratio > self.near_min):
            self._add(iod)
        return ratio


class HeadSizeRef(FaceSizeRef):
    """head_ratio_user per frame: the head-box analogue of iod_ratio_user - the main user's head-box height over the
    same user's reference, from the same anchor and with the same rules as FaceSizeRef (near_min =
    params.head_approach_ratio_min keeps a lean out of the reference after a press). Rows without the main user's box
    give None. A lean makes the head bigger; a seated user at operating distance does not."""

    def _value(self, row: dict) -> float | None:
        h = _box_height(row.get("primary_box"))
        return None if h is None else _finite(h * 1000.0)   # permille of the frame height: the 0.1 step is 1/10,000


class PitchRef(_UserAnchor):
    """dpitch_user_deg per frame (module docstring): the main user's pitch_deg minus the pitch of that user's first
    face row after the anchor - the session-start pitch change of features.py, taken per main user. The anchors are
    FaceSizeRef's (_UserAnchor; a touch-log session change is the chain's reset()), except that a stitched track break
    (main_user_stitched) keeps the reference: the stitch says the track of the same user broke in place, as in a deep
    bow, and the first face row of the new track can be that bowed pitch, which would then be the user's level for the
    rest of the session and hide later bowing from the head-down gate. The size references start again at a stitch
    because a median of sizes would keep the walk-up's smaller sizes; this reference is one row, so keeping it gives
    the value an unbroken track gives. collect False (a touch log without a press in this session yet): no reference
    is taken and the value is None, as for iod_ratio_user."""
    KEEP = ("main_user_reacquired", "main_user_stitched")

    def __init__(self, max_gap_s: float | None = None):
        self.max_gap_s = max_gap_s
        self.reset()

    def reset(self):
        self.ref = None            # pitch_deg of the main user's first face row since the anchor
        self.track = None

    def update(self, row: dict, collect: bool = True) -> float | None:
        self._follow(row)
        pitch = _finite(row.get("pitch_deg")) if main_user_face(row) else None
        if not collect or pitch is None:
            return None
        if self.ref is None:
            self.ref = pitch
        return pitch - self.ref


class MainUserChange:
    """The CHANGE_COLUMNS per row (module docstring) from primary_track and body_state, kept across rows so that a
    change after a long gap is still seen (the windows only hold a few seconds of rows).

    iou_min (params.track_iou_min): a new main-user box that overlaps the ended track's last box at least this much,
    with the place kept through the gap, is a reacquisition - the head detector lost the same person in the same place
    (a cap, a deep bow, a camera stall) - and is marked main_user_reacquired. The place is kept when nothing of the
    user (the head box or a body) was unseen for longer than max_gap_s at a stretch (main_user_body_gap_s, from
    body_unseen_s; the rule a head track lives by), or, on rows without body_unseen_s, when the body was seen on every
    row (main_user_body_kept). Otherwise (the place stood empty, as when the next customer steps in) it is a change. segment_s (params.segment_s) bins the
    main user's head-box height for Settle: a track that ends before its user settled is the first approach, and the
    next track is marked main_user_prev_settled False. max_gap_s (params.track_max_gap_s) and window_s (params.role_window_s) bound the
    history of the other heads: a head not seen for longer than max_gap_s is dropped (its track has ended), and only
    its heights of the last window_s seconds are kept (the role rule's window). None = no bound.
    shift_max, size_max (params.stitch_shift_max, stitch_size_max): a new main-user track whose first box (kept from
    the frames where it was another head) came after the ended track's last box, within max_gap_s, and lies within
    shift_max of it with a size step within size_max, is the same user whose track broke in place (main_user_stitched;
    module docstring). None: no stitch is decided (main_user_stitched None)."""

    def __init__(self, iou_min: float | None = None, max_gap_s: float | None = None, window_s: float | None = None,
                 segment_s: float | None = None, shift_max: float | None = None, size_max: float | None = None):
        self.iou_min, self.max_gap_s, self.window_s = iou_min, max_gap_s, window_s
        self.shift_max, self.size_max = shift_max, size_max
        self.settle = Settle(segment_s)
        self.reset()

    def reset(self):
        self.track = None          # the current main-user track
        self.last_t = None         # time of its last row with a head box (any row of it without the box column)
        self.last_h = None         # height of that last box
        self.last_box = None       # that last box
        self.body_kept = True      # the body seen on every row since that last row
        self.body_gap = 0.0        # the longest stretch since that last row with neither that box nor a body
        self.gap_known = True      # every row since then said how long the body had been unseen (body_unseen_s)
        self.others = {}           # track id -> {"role", "rel", "last_t", "hist": deque of (t, h), "first": (t, box)}
                                   # of the other heads (first = the track's first box seen here)
        self.settle.reset()        # whether the current main user has settled at the kiosk

    def update(self, row: dict) -> dict:
        t, track = float(row["t_s"]), _track_id(row.get("primary_track"))
        body = row.get("body_state") == SEEN
        out = dict.fromkeys(CHANGE_COLUMNS)
        boxes = _head_boxes(row)
        box = row.get("primary_box")
        h = _box_height(box)
        if track is None:
            self._gap_row(t, row, body)
        elif self.track is not None and track != self.track:
            seen = self.others.pop(track, None)
            ratio = None if h is None or not self.last_h else h / self.last_h
            heights = [v for _, v in seen["hist"]] if seen else []
            growth = h / float(np.median(heights)) if heights and h is not None else None
            reacquired = None
            self._gap_row(t, row, body)                  # the gap runs up to this row (its body counts too)
            body_gap = self.body_gap if self.gap_known else None
            kept = self.body_kept if body_gap is None or self.max_gap_s is None else body_gap <= self.max_gap_s
            if self.iou_min is not None and box is not None and self.last_box is not None:
                reacquired = bool(box_iou(box, self.last_box) >= self.iou_min and kept)
            first_t, first_box = seen["first"] if seen and seen.get("first") else (t, box)
            start_s, shift, size = _break(self.last_t, self.last_box, first_t, first_box)
            stitched = None
            if None not in (self.max_gap_s, self.shift_max, self.size_max, start_s, shift, size):
                stitched = bool(0 < start_s <= self.max_gap_s and shift <= self.shift_max and size <= self.size_max)
            out.update(main_user_prev_track=self.track, main_user_gap_s=t - self.last_t,
                       main_user_body_kept=self.body_kept, main_user_prev_h=self.last_h,
                       main_user_new_h=h, main_user_h_ratio=ratio,
                       main_user_new_was_role=seen["role"] if seen else None,
                       main_user_new_rel_dist=seen["rel"] if seen else None, main_user_new_growth=growth,
                       main_user_reacquired=reacquired, main_user_prev_settled=self.settle.close(),
                       main_user_new_start_s=start_s, main_user_start_shift=shift, main_user_start_size=size,
                       main_user_stitched=stitched, main_user_body_gap_s=body_gap)
            self.track, self.last_t, self.last_h, self.last_box, self.body_kept = track, t, h, box, True
            self.body_gap, self.gap_known = 0.0, True
            if not (reacquired or stitched):
                self.settle.reset()                  # a new main user: its own approach
            if h is not None:
                self.settle.add(t, h)
        elif box is None and "primary_box" in row:   # the track lives on without a box in this frame
            self._gap_row(t, row, body)
        else:
            self.track, self.last_t, self.body_kept = track, t, True
            self.body_gap, self.gap_known = 0.0, True
            if h is not None:
                self.last_h, self.last_box = h, box
                self.settle.add(t, h)
        for other in boxes:                          # the other heads, against the main user of this frame
            k = _track_id(other.get("track"))
            if other.get("role") == "primary" or k is None:
                continue
            seen = self.others.setdefault(k, {"role": None, "rel": None, "last_t": t, "hist": deque(), "first": None})
            seen["role"], seen["rel"], seen["last_t"] = other.get("role"), _finite(other.get("rel_dist_med")), t
            if seen["first"] is None:
                seen["first"] = (t, _listed_box(other))
            if _finite(other.get("h")) is not None:
                seen["hist"].append((t, float(other["h"])))
        for k in list(self.others):
            seen = self.others[k]
            if self.max_gap_s is not None and t - seen["last_t"] > self.max_gap_s:
                del self.others[k]
                continue
            while self.window_s is not None and seen["hist"] and seen["hist"][0][0] < t - self.window_s:
                seen["hist"].popleft()
        return out

    def _gap_row(self, t: float, row: dict, body: bool):
        """A row since the main user's last head box without that box (and the row that starts the next track):
        body_kept (the body on every row) and body_gap, the longest stretch with neither that box nor a body
        (body_unseen_s, at most the time since the last box)."""
        self.body_kept = self.body_kept and body
        unseen = 0.0 if body else _finite(row.get("body_unseen_s"))
        if unseen is None:
            self.gap_known = False
        elif self.last_t is not None:
            self.body_gap = max(self.body_gap, min(unseen, t - self.last_t))


def _listed_box(head: dict):
    """(x0, y0, x1, y1) of one head_boxes entry (cx, cy, w, h fractions), or None."""
    cx, cy, w, h = (_finite(head.get(k)) for k in ("cx", "cy", "w", "h"))
    return None if None in (cx, cy, w, h) else (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def _break(last_t, last_box, first_t, first_box) -> tuple:
    """(start_s, shift, size) of a track break (module docstring, main_user_new_start_s ...): the seconds from the
    ended track's last box to the new track's first box, the centre shift in last-box widths and heights (Euclidean, the
    R-CNN deltas tx, ty) and |ln(first height / last height)| (R-CNN th); None where a box or a time is missing, and
    shift and size None where a box coordinate is not finite (as _box_height)."""
    start_s = None if last_t is None or first_t is None else float(first_t) - float(last_t)
    try:
        w0, h0 = float(last_box[2]) - float(last_box[0]), float(last_box[3]) - float(last_box[1])
        h1 = float(first_box[3]) - float(first_box[1])
        dx = (float(first_box[0]) + float(first_box[2]) - float(last_box[0]) - float(last_box[2])) / 2.0
        dy = (float(first_box[1]) + float(first_box[3]) - float(last_box[1]) - float(last_box[3])) / 2.0
    except (TypeError, ValueError, IndexError):
        return start_s, None, None
    if not all(math.isfinite(v) for v in (w0, h0, h1, dx, dy)) or w0 <= 0 or h0 <= 0 or h1 <= 0:
        return start_s, None, None
    return start_s, math.hypot(dx / w0, dy / h0), abs(math.log(h1 / h0))


def _contains(box, points) -> bool:
    return all(box[0] <= x <= box[2] and box[1] <= y <= box[3] for x, y in points)


def aid_columns(aids, pose, primary_box, head_detector: bool = False, person_min: float | None = None) -> dict:
    """AID_COLUMNS of one frame (module docstring). aids = app.inference.aid.Aids; pose = the pose points (33 x 4:
    x, y as fractions, visibility, presence) or None; primary_box = the main user's head box or None; head_detector =
    the head detector ran on this frame. The pose follows one person, not always the main user: with the head
    detector the main user's head-box centre alone is the anchor, and a frame without that box has no anchor (aid_owner
    unknown). Without the head detector the pose's two shoulders are the anchor, as for the shoulder columns.
    person_min (params.aid_person_min): only boxes above it are people (aid_person_count, the user's box); None: every
    box."""
    from app.inference.aid import AID_CLASSES, STANDING_AIDS, WHEELCHAIR
    out = dict.fromkeys(AID_COLUMNS)
    out["aid_count"] = len(aids)
    people = [i for i in range(len(aids)) if person_min is None or float(aids.scores[i]) > person_min]
    out["aid_person_count"] = None if person_min is None else len(people)
    head = None if primary_box is None else tuple(float(v) for v in primary_box)
    head_centre = None if head is None else ((head[0] + head[2]) / 2.0, (head[1] + head[3]) / 2.0)
    shoulders = None
    if pose is not None and head is None and not head_detector:
        pts = np.asarray(pose, dtype=np.float64)[list(SHOULDERS), :2]
        if np.isfinite(pts).all():
            shoulders = [tuple(p) for p in pts]
    # with the main user's head box the box is chosen by the head alone: the one pose may be someone else's, and a
    # companion's shoulders around the user's head would push the user's own box out; without the head detector the
    # pose's person (its two shoulders) is the main user, as for the shoulder columns
    anchor = [head_centre] if head_centre is not None else (shoulders or [])
    if not anchor:
        out["aid_owner"] = "unknown"
        return out
    classes = list(aids.classes)
    aid_idx = [classes.index(c) for c in AID_CLASSES]
    around = [i for i in people if _contains(aids.boxes[i], anchor)]
    if not around:
        out["aid_owner"] = "no"
        return out
    if head is not None:                     # the box that starts at this person's head
        k = min(around, key=lambda i: (abs(float(aids.boxes[i][1]) - head[1]), _box_area(aids.boxes[i])))
    else:
        k = min(around, key=lambda i: _box_area(aids.boxes[i]))
    cs = aids.class_scores[k]
    top = classes[int(np.argmax(cs))]
    out.update(aid_owner="yes" if top in AID_CLASSES else "no", aid_top_class=top,
               aid_class_scores={c: float(cs[j]) for j, c in enumerate(classes)},
               aid_any_score=float(max(cs[j] for j in aid_idx)),
               aid_wheelchair_score=float(cs[classes.index(WHEELCHAIR)]),
               aid_kind="wheelchair" if cs[classes.index(WHEELCHAIR)] > max(cs[classes.index(c)] for c in STANDING_AIDS)
               else "standing",
               aid_box=tuple(float(v) for v in aids.boxes[k]))
    return out


def aid_head_columns(aids, primary_box) -> dict:
    """AID_HEAD_COLUMNS of one frame under the head_centre reading (module docstring). aids =
    app.inference.aid.Aids with class_boxes (AidDetector(per_class=True)); primary_box = the main user's head box or
    None. A class's value is the highest score of its kept boxes that contain the head-box centre (edges included),
    the frame's the highest of the classes' values; a score must be above the best so far, so 0.0 stays when no box
    contains the centre and the first class in the model's order wins a tie."""
    if aids.class_boxes is None:
        raise ValueError("the head_centre reading needs the per-class boxes (AidDetector(per_class=True))")
    out = dict.fromkeys(AID_HEAD_COLUMNS)
    if primary_box is None:
        return out
    head = tuple(float(v) for v in primary_box)
    centre = [((head[0] + head[2]) / 2.0, (head[1] + head[3]) / 2.0)]
    out["aid_head_score"] = 0.0
    for name in aids.classes:
        if name not in aids.class_boxes:
            continue
        boxes, scores = aids.class_boxes[name]
        for box, score in zip(boxes, scores):
            if float(score) > out["aid_head_score"] and _contains(box, centre):
                out.update(aid_head_score=float(score), aid_head_class=name,
                           aid_head_box=tuple(float(v) for v in box))
    return out


class AidCarry:
    """AID_HEAD_COLUMNS + AID_CARRY_COLUMNS per frame under the head_centre_carry reading (module docstring,
    aid_head_score ...). iou_min, max_gap_s = params.track_iou_min, track_max_gap_s: the values and the rule of
    HeadTracker (the highest IoU first, at least iou_min; ended when nothing matched for more than max_gap_s), applied
    to the main user's aid-class box. One instance per input (chain.FrameChain); reset() with the other per-user state
    when the touch-log session changes."""

    def __init__(self, iou_min: float, max_gap_s: float):
        self.iou_min, self.max_gap_s = float(iou_min), float(max_gap_s)
        self.reset()

    def reset(self):
        self.box = None            # the aid-class box followed: from the latest head row, or the latest match
        self.last_t = None         # the time of that row

    def update(self, t: float, aids, primary_box) -> dict:
        """The columns of one frame. aids = app.inference.aid.Aids with class_boxes; primary_box = the main user's head
        box or None. A row with the head box gives aid_head_columns' value; one without it the box followed, matched
        among the kept boxes of every aid class (a tie on IoU: the class first in the model's order, then the higher
        score, as aid_head_columns orders them)."""
        out = aid_head_columns(aids, primary_box)
        out["aid_head_from"] = None
        if primary_box is not None:
            out["aid_head_from"] = AID_FROM_HEAD
            if out["aid_head_box"] is None:        # 0.0: no aid box holds the head centre
                self.reset()
            else:
                self.box, self.last_t = out["aid_head_box"], float(t)
            return out
        if self.box is None:                       # no head row with an aid box yet: nothing to follow
            return out
        if float(t) - self.last_t > self.max_gap_s:
            self.reset()                           # nothing matched for longer than a head track lives: ended
            return out
        best = None
        for name in aids.classes:
            if name not in aids.class_boxes:
                continue
            boxes, scores = aids.class_boxes[name]
            for box, score in zip(boxes, scores):
                iou = box_iou(box, self.box)
                if iou >= self.iou_min and (best is None or iou > best[0]):
                    best = (iou, name, tuple(float(v) for v in box), float(score))
        if best is not None:
            _, name, box, score = best
            out.update(aid_head_score=score, aid_head_class=name, aid_head_box=box, aid_head_from=AID_FROM_CARRIED)
            self.box, self.last_t = box, float(t)
        return out


NOSE = 0                                         # pose point 0 (nose) in the 33-point map [D3]
HANDS = ((15, 17, 19, 21), (16, 18, 20, 22))     # left / right wrist, pinky, index, thumb [D3]


def _meet(a, b) -> bool:
    """Whether two boxes (x0, y0, x1, y1) share a point, edges included."""
    return bool(a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3])


def _hand_boxes(pose, head, vis_min: float | None = None) -> list | None:
    """The main user's hand boxes (the box spanned by each hand's points that count) when the pose is the main user's
    (its nose lies in the main user's head box); None when there is no pose, it is someone else's, no hand point of it
    counts, or vis_min is None (no hand could be checked). A hand point counts when its x, y are finite and its
    visibility (pose column 2) is at least vis_min (params.hand_vis_min): below it the landmarker reports the point as
    occluded or out of the frame, so its position is estimated, not seen. A point without a visibility (NaN, or a pose
    without that column) does not count: nothing confirms its position. vis_min None (no value): no point's position
    is confirmed, so no hand box is built and the hand path is held - the module's rule for a missing boundary value
    (no value -> cannot tell); the head path does not read the hands."""
    if pose is None or vis_min is None:
        return None
    pose = np.asarray(pose, dtype=np.float64)
    pts = pose[:, :2]
    if not np.isfinite(pts[NOSE]).all() or not inside(pts[NOSE], head):
        return None
    out = []
    for hand in HANDS:
        p = pts[list(hand)]
        vis = pose[list(hand), 2] if pose.shape[1] > 2 else np.full(len(hand), np.nan)
        keep = np.isfinite(p).all(axis=1) & np.isfinite(vis) & (vis >= vis_min)
        p = p[keep]
        if len(p):
            out.append((p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()))
    return out or None                           # no hand point counts: the hands cannot be checked


def phone_columns(phones, pose, primary_box, head_boxes=None, hand_vis_min: float | None = None) -> dict:
    """PHONE_COLUMNS of one frame. phones = app.inference.phone.Phones; pose = the pose points (33 x 4) or None;
    primary_box = the main user's head box or None; head_boxes = the frame's head_boxes entries (head_columns; None or
    [] = no other head); hand_vis_min = params.hand_vis_min (with a value only hand points seen at least that visibly
    span a hand box; None: no hand box, so a phone away from the heads is 'unknown', never the main user's by a hand;
    _hand_boxes). A phone at a head belongs to the
    head box that holds the larger share of the phone box (the
    intersection area over the phone box's area; a tie goes to the main user): it is the main user's ('head', at the
    ear or in front of the face) when its box meets the main user's head box and no other head box holds more of it,
    and another person's when another head box holds more of it, or holds some of it while it does not meet the main
    user's head box. A phone at no head is the main user's when it meets a box spanned by one hand's pose points of the
    main user ('hand'; the pose is the main user's when its nose lies in that head box). phone_owner 'yes' = such a phone; 'no' = the
    head box is there and no phone box is in the frame, or every phone box was checked against the heads and the hands
    ('no' also when the detector missed a phone it should have seen: it says 'no box at the main user', not that the
    user has no phone); 'unknown' = no head box, or a phone away from the heads while the hands are not the main user's
    or cannot be checked. phone_score / phone_box = the best such phone (the head first); phone_count = phone boxes in
    the frame."""
    out = dict.fromkeys(PHONE_COLUMNS)
    out["phone_count"] = len(phones)
    if primary_box is None:
        out["phone_owner"] = "unknown"
        return out
    head = tuple(float(v) for v in primary_box)
    others = [b for b in (_listed_box(h) for h in _head_boxes({"head_boxes": head_boxes}) if h.get("role") != "primary")
              if b is not None]
    at_head, away = [], []
    for i in range(len(phones)):
        box = tuple(float(v) for v in phones.boxes[i])
        meets_main = _meet(box, head)
        rival = max((_inter_area(box, o) for o in others), default=0.0)   # the same phone area divides every share
        if meets_main and rival <= _inter_area(box, head):
            at_head.append(i)                    # the main user's head holds the larger share (or ties)
        elif not meets_main and rival <= 0.0:
            away.append(i)                       # at no head: tried against the hands
        # otherwise another person's head holds more of it: not the main user's
    hands = _hand_boxes(pose, head, hand_vis_min)
    in_hand = [] if hands is None else [i for i in away if any(_meet(phones.boxes[i], h) for h in hands)]
    for where, chosen in (("head", at_head), ("hand", in_hand)):
        if chosen:
            k = max(chosen, key=lambda i: float(phones.scores[i]))
            out.update(phone_owner="yes", phone_at=where, phone_score=float(phones.scores[k]),
                       phone_box=tuple(float(v) for v in phones.boxes[k]))
            return out
    out["phone_owner"] = "no" if (not away or hands is not None) else "unknown"
    return out


def _inter_area(a, b) -> float:
    """The intersection area of two boxes (x0, y0, x1, y1); 0 when they share no area."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _box_area(box) -> float:
    return max(0.0, float(box[2]) - float(box[0])) * max(0.0, float(box[3]) - float(box[1]))


def _box_height(box) -> float | None:
    """y1 - y0 of an (x0, y0, x1, y1) box (a tuple, or 'x0;y0;x1;y1' from rows.csv, as events._box_cy reads it), or
    None (also for a coordinate that is not finite)."""
    if isinstance(box, str):
        box = box.split(";")
    try:
        return _finite(float(box[3]) - float(box[1]))
    except (TypeError, ValueError, IndexError):
        return None


def _head_boxes(row: dict) -> list:
    """The row's head_boxes as a list of dicts (a JSON cell read back from rows.csv is parsed); [] when absent."""
    boxes = row.get("head_boxes")
    if isinstance(boxes, str):
        boxes = json.loads(boxes) if boxes else []
    return [b for b in boxes or [] if isinstance(b, dict)]


def add_main_user_change(rows: list, params=None) -> list:
    """The CHANGE_COLUMNS written into recorded rows that carry primary_track (an earlier replay with the head detector),
    in time order; rows without that column are left as they are. params = params.PilotParams (default values when
    None). Returns the rows."""
    if params is None:
        from .params import PilotParams
        params = PilotParams()
    change = MainUserChange(params.track_iou_min, params.track_max_gap_s, params.role_window_s, params.segment_s,
                            params.stitch_shift_max, params.stitch_size_max)
    for row in sorted(rows, key=lambda r: float(r["t_s"])):
        if "primary_track" in row:
            row.update(change.update(row))
    return rows


def stitch_motion(rows: list, max_gap_s: float | None) -> list:
    """(shift, size) of the same head within max_gap_s (params.track_max_gap_s, the longest break the stitch bridges),
    from the rows of one recording (primary_track and primary_box, e.g. a replay with the head detector): every main-user
    box paired with the last box of the same track at most max_gap_s later, measured as a break is (_break: centre shift
    in box widths and heights, |ln height ratio|). The distribution stitch_shift_max and stitch_size_max are calibrated
    from (params.STITCH_METHOD). [] when max_gap_s is None.
    Most pairs therefore span about max_gap_s (only the last max_gap_s of a track gives shorter ones), so the bounds
    fit the longest break the stitch bridges and are looser for the short breaks it mostly meets (a box lost for 0.1 s).
    The pairing admits max_gap_s + 1e-9 so that a pair at exactly max_gap_s is kept whatever the float rounding of the
    times (1.6 - 0.6 = 1.0000000000000002); the stitch rule (MainUserChange) and HeadTracker compare with a plain <=,
    so a break whose float interval rounds above max_gap_s is not stitched."""
    if max_gap_s is None:
        return []
    tracks = {}
    for r in sorted(rows, key=lambda r: float(r["t_s"])):
        k, box = _track_id(r.get("primary_track")), r.get("primary_box")
        if isinstance(box, str):
            box = tuple(float(x) for x in box.split(";")) if box else None
        if k is not None and box is not None:
            tracks.setdefault(k, []).append((float(r["t_s"]), box))
    out = []
    for seq in tracks.values():
        j = 0
        for i, (t, box) in enumerate(seq):
            j = max(j, i)
            while j + 1 < len(seq) and seq[j + 1][0] - t <= max_gap_s + 1e-9:
                j += 1
            if j > i:
                _, shift, size = _break(t, box, seq[j][0], seq[j][1])
                if shift is not None:
                    out.append((shift, size))
    return out


def add_face_size_ratio(rows: list, params=None) -> list:
    """iod_ratio_user written into recorded rows (rows.csv of an earlier replay), in time order, with the anchor of a
    run without a touch log (the main-user track). params = params.PilotParams (default values when None): its
    approach_ratio_min keeps the lean out of the reference. Returns the rows."""
    if params is None:
        from .params import PilotParams
        params = PilotParams()
    ref = FaceSizeRef(params.approach_ratio_min, params.track_max_gap_s)
    for row in sorted(rows, key=lambda r: float(r["t_s"])):
        row["iod_ratio_user"] = ref.update(row)
    return rows


def add_head_size_ratio(rows: list, params=None) -> list:
    """head_ratio_user written into recorded rows that carry primary_box (an earlier replay with the head detector), in
    time order, as a run without a touch log writes it (HeadSizeRef). When no row carries primary_box, the rows are
    left as they are. Returns the rows."""
    if params is None:
        from .params import PilotParams
        params = PilotParams()
    if not any("primary_box" in r for r in rows):
        return rows
    ref = HeadSizeRef(params.head_approach_ratio_min, params.track_max_gap_s)
    for row in sorted(rows, key=lambda r: float(r["t_s"])):
        row["head_ratio_user"] = ref.update(row)
    return rows


def add_pitch_user(rows: list, params=None) -> list:
    """dpitch_user_deg written into recorded rows, in time order, as a run without a touch log writes it (PitchRef:
    the main-user track, or without the head detector the unseen gap, as the anchor). Returns the rows."""
    if params is None:
        from .params import PilotParams
        params = PilotParams()
    ref = PitchRef(params.track_max_gap_s)
    for row in sorted(rows, key=lambda r: float(r["t_s"])):
        row["dpitch_user_deg"] = ref.update(row)
    return rows


def face_xy(row: dict):
    """(face_cx, face_cy) of a features row when its face is seen and both values are finite, else None."""
    if row.get("face_state") != SEEN:
        return None
    x, y = _finite(row.get("face_cx")), _finite(row.get("face_cy"))
    return None if x is None or y is None else (x, y)
