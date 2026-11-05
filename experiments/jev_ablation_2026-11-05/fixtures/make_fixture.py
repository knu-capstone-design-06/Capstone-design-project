"""Hand-written fixture windows for the E5 harness (mechanics only; every value is a made-up test input).

Writes fixtures/windows/<take>.jsonl in the vision window-record shape the runner reads (situation view, segment
touch counts, screen, vision.facing_screen, measurable, session_reset) plus `expect` = the rule table's transition
and support this window should give (read off rule_table.py by hand), and fixtures/fixture_labels.csv (allowed
sets and states for the metrics' code paths, not judgments of any recording).
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUEUE, BUSY, AROUND = "looking_back_with_people_behind", "consulting_companion", "looking_around"
EVENT = {QUEUE: ("look_back", "people_behind"), BUSY: ("companion_present", "mouth_moving"),
         AROUND: ("yaw_sweep_offscreen", "dwell_no_touch")}


def situation(tag, t):
    if tag is None:
        return {"name": "unknown", "display_text": "", "evidence_ids": [], "evidence": [], "confidence": "unknown",
                "alternatives": [], "quality": None, "unknown_reason": [{"code": "fixture"}], "window_s": None,
                "source": None}
    ev = [{"event_id": f"{k}@{int(t * 10)}", "obs": k, "value": 1, "t": t - 0.5} for k in EVENT[tag]]
    return {"name": tag, "display_text": "", "evidence_ids": [e["event_id"] for e in ev], "evidence": ev,
            "confidence": {"events": len(ev), "quality_ok": True}, "alternatives": [],
            "quality": {"face_visible_ratio": 1.0, "track_conf": 1.0}, "unknown_reason": [], "window_s": [t - 2, t],
            "source": "rules_v1"}


def window(t, tag=None, screen="menu", steps_left=None, taps=0, misses=0, fixes=0, backs=0, gaze=None,
           pause=None, options=None, measurable=True, reset=False, five=False, touch=True, expect=None):
    tc = None
    if touch:
        tc = {"tap_count": taps, "miss_tap_count": misses, "near_miss_fix_count": fixes, "back_count": backs,
              "unknown_target_presses": 0, "repeat_tap_count": 0 if five else None, "dwell_ms": 1000 if five else None}
    return {"t": float(t), "segment_s": [float(t) - 1.0, float(t)], "situation": situation(tag, t), "touch": tc,
            "screen": {"name": screen, "steps_left": steps_left, "pause_s": pause, "options_open": options},
            "vision": {"facing_screen": gaze}, "measurable": measurable, "session_reset": reset,
            "expect": expect}


def e(transition, support=None):
    return {"transition": transition, "support": support}


N, KEEP_BIG = "remaining_steps_notice", e("keep", "large_button")
TAKES = {
    # 3-1: tag opens the notice (fit question), a screen forward withdraws it, the tag opens it again in a new scope
    "fx_queue": [
        window(1, QUEUE, "menu", 2, five=True, expect=e("open", N)),
        window(2, QUEUE, "menu", 2, five=True, expect=e("keep", N)),
        window(3, None, "review", 1, taps=1, five=True, expect=e("withdraw", N)),
        window(4, QUEUE, "review", 1, five=True, expect=e("open", N)),
        window(5, None, "complete", 0, taps=1, five=True, expect=e("withdraw", N)),
        window(6, QUEUE, "complete", 0, five=True, expect=e("none")),
    ],
    # 3-2: the wait opens and stays, touch withdraws it; a back opens 4-2 (unknown tag: no Jev question)
    "fx_companion": [
        window(1, BUSY, "menu", expect=e("open", "wait_hold_timer")),
        window(2, BUSY, "menu", expect=e("keep", "wait_hold_timer")),
        window(3, None, "menu", taps=2, expect=e("withdraw", "wait_hold_timer")),
        window(4, None, "menu", taps=1, backs=1, expect=e("open", "highlight_next_action")),
        window(5, None, "menu", expect=e("keep", "highlight_next_action")),
    ],
    # 4-1: two near-miss fixes in the recent span while facing the screen open the big-button ask (fit question);
    # unanswered for no_response_s (10 s) it is withdrawn by tick and not reopened on the same screen visit
    "fx_tremor": [window(1, AROUND, gaze=True, taps=1, misses=1, fixes=1, five=True, expect=e("none")),
                  window(2, AROUND, gaze=True, taps=1, misses=1, fixes=1, five=True, expect=e("open", "large_button"))]
                 + [window(t, AROUND, gaze=True, taps=1, five=True, expect=KEEP_BIG) for t in range(3, 12)]
                 + [window(12, AROUND, gaze=True, taps=1, five=True, expect=e("none"))],
    # 4-2 with vision: looking_around lowers the pause criterion to lost_pause_s_vision (4 s)
    "fx_lost": [
        window(1, AROUND, gaze=True, pause=2.0, options=True, expect=e("none")),
        window(2, AROUND, gaze=True, pause=3.0, options=True, expect=e("none")),
        window(3, AROUND, gaze=True, pause=4.5, options=True, expect=e("open", "highlight_next_action")),
        window(4, AROUND, "review", gaze=True, taps=1, expect=e("withdraw", "highlight_next_action")),
    ],
    # the same pauses without vision: lost_pause_s (8 s) applies, nothing opens
    "fx_lost_novision": [
        window(1, pause=2.0, options=True, expect=e("none")),
        window(2, pause=3.0, options=True, expect=e("none")),
        window(3, pause=4.5, options=True, expect=e("none")),
        window(4, None, "review", taps=1, expect=e("none")),
    ],
    # 3-1 choice: a tremor row behind the queue tag adds the defer option (queue_support question); the quiet
    # notice is then replaced by the big-button ask
    "fx_queue_tremor": [
        window(1, QUEUE, gaze=True, taps=2, misses=2, fixes=2, five=True, expect=e("open", N)),
        window(2, QUEUE, gaze=True, taps=1, five=True, expect=e("replace", "large_button")),
        window(3, QUEUE, gaze=True, taps=1, five=True, expect=KEEP_BIG),
    ],
    # not measurable (no press, no face), keep while not measurable, a new session starts the state again
    "fx_session": [
        window(1, measurable=False, expect=e("none")),
        window(2, taps=1, backs=1, expect=e("open", "highlight_next_action")),
        window(3, measurable=False, expect=e("keep", "highlight_next_action")),
        window(4, reset=True, expect=e("none")),
    ],
}
LABELS = [   # take, t_start, t_end, allowed, state
    ("fx_queue", 0, 6, "remaining_steps_notice;none", "normal"),
    ("fx_companion", 0, 3, "wait_hold_timer", "normal"),
    ("fx_companion", 3, 6, "highlight_next_action;none", "navigation_difficulty"),
    ("fx_tremor", 0, 13, "large_button", "touch_difficulty"),
    ("fx_lost", 0, 5, "highlight_next_action", "hesitation"),
    ("fx_lost_novision", 0, 5, "highlight_next_action", "hesitation"),
    ("fx_queue_tremor", 0, 4, "remaining_steps_notice;defer_big_button_question", "touch_difficulty"),
]

if __name__ == "__main__":
    out = HERE / "windows"
    out.mkdir(exist_ok=True)
    for take, rows in TAKES.items():
        with open(out / f"{take}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(HERE / "fixture_labels.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["take", "t_start", "t_end", "allowed", "state"])
        w.writerows(LABELS)
    print(f"{sum(len(r) for r in TAKES.values())} windows in {len(TAKES)} takes -> {out}")
