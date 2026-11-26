"""Tag sender of the live runner: each evaluated window's situation tags go straight to the backend.

Path (the team paper's figure 1, project owner's decision 2026-11-25): AI engine -> backend, the situation tags, direct;
the order screen relays no vision value. After live.run_live has evaluated a window (once the order screen's touch
for its segment has arrived, live.py 'When a window is evaluated'; the situation and the scene tags from
chain.WindowJudge, as in a replay) and the window has a session (the session its touch windows name,
touch_entry.py), the window is offered here and POSTed to
  {backend}/api/v1/sessions/{session_id}/vision-windows
as one JSON object (vision_window):
  session_id                the session (also in the path; the backend-ai contract's AnalyzeRequest carries its
                            session_id in the body the same way)
  window_start, window_end  the window's segment (record segment_s) on the wall clock, ISO 8601 UTC with
                            milliseconds (the touch entry's clock mapping, touch_entry.TouchEntry.wall)
  situation                 contract_view.decision_situation: name, evidence, confidence (the keys the backend's
                            decision layer reads from WindowInput.situation)
  observations              contract_view.observations: gaze, face_seen, scene_tags
  model_version             the window record's contract version mark (contract_view.MODEL_VERSION)
The camera loop never waits for the backend: offer_release() only puts the windows one evaluation released together
(live.run_live's flush: the segments one touch window released, or a single window) into a one-slot mailbox as one
item, and one sender thread POSTs that release's windows in time order: the segments of one release are sent together,
none replaced by its neighbour. A newer release replaces an unsent one as a whole (each of its windows counted as
replaced); a release's size is bounded by the runner's own wait bound. A release may carry a done (offer_release): it is
called once that release and every release offered before it are finished (posted, failed, skipped, replaced unsent, or
the sender closing); live.run_live's flush settles its touch windows with it (touch_entry.TouchEntry.settle). A send
that fails (no answer within the timeout, a refused connection, an answer outside 2xx, RFC 9110 15.3) is counted and
dropped, never retried. The timeout is the window cadence (segment_s), so a send does not outlive its window; it bounds
each socket operation (connect, each read: socket.settimeout through urllib). Standard library only; the connection
goes direct (no proxy).
A 404 (the backend does not know the session, e.g. after its restart) or 410 (the session's order is completed) is
not a failed send: it is counted as ended_404 / ended_410, the first answer of each kind is printed once, and the
windows of that session are not offered (skipped_ended) until a window of another session id comes, the next order.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

from .replay import jsonable
from .touch_entry import iso, plain

PATH = "/api/v1/sessions/{session_id}/vision-windows"


def vision_window(record: dict, session_id: str, wall) -> dict:
    """The JSON object sent for one window record (module docstring). wall = camera s -> wall-clock s (the touch
    entry's TouchEntry.wall)."""
    ext = record["contract"]["extension"]
    s0, s1 = record["segment_s"]
    return {"session_id": session_id, "window_start": iso(wall(s0)), "window_end": iso(wall(s1)),
            "situation": ext["decision_situation"], "observations": ext["observations"],
            "model_version": ext["model_version"]}


def target(base_url: str, session_id: str) -> str:
    return base_url.rstrip("/") + PATH.format(session_id=urllib.parse.quote(session_id, safe=""))


def check_base_url(base_url: str) -> str:
    """The backend base address as given, or ValueError: an http(s) URL with a host and no query."""
    u = urllib.parse.urlsplit(base_url)
    if u.scheme not in ("http", "https") or not u.netloc or u.query or u.fragment:
        raise ValueError(f"not an http(s) base address: {base_url!r}")
    return base_url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an answer outside 2xx: not followed (urllib would repeat a POST as a GET without its body)."""

    def redirect_request(self, *args, **kwargs):
        return None


class TagSender:
    """One sender thread with a one-slot mailbox of releases (module docstring)."""

    def __init__(self, base_url: str, timeout_s: float, log=None):
        self.base_url = check_base_url(base_url)
        self.timeout_s = float(timeout_s)
        self.log = log
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        self.cond = threading.Condition()
        self.slot = None           # the latest unsent release: a list of windows in time order
        self.taken = []            # the rest of the release the thread is posting
        self.releases = 0          # offer_release calls so far: release k is the k-th
        self.slot_k = None         # k of the release in the slot
        self.posting_k = None      # k of the release the thread is posting (until its last send has ended)
        self.dones = []            # [(k, done)] of the releases whose done is not called yet, in k order
        self.closing = False
        self.abandoned = False     # close() gave up waiting: the thread stops after the send under way
        self.counts = {"offered": 0, "sent": 0, "failed": 0, "replaced": 0, "unsent_at_close": 0,
                       "ended_404": 0, "ended_410": 0, "skipped_ended": 0}
        self.last_error = None
        self.ended = None          # (session_id, code): the last session the backend answered 404 or 410 for
        self.told = set()          # the codes (404, 410) already printed once
        self.thread = threading.Thread(target=self._run, name="vision-tag-sender", daemon=True)
        self.thread.start()

    def _skip(self, payload: dict) -> bool:
        """With the lock held: True when the payload's session is the one the backend ended (counted); a window of
        another session id clears the mark (a new session has started)."""
        if self.ended is None:
            return False
        if payload["session_id"] == self.ended[0]:
            self.counts["skipped_ended"] += 1
            return True
        self.ended = None
        return False

    def offer(self, payload: dict):
        """One window released alone: a release of one (offer_release)."""
        self.offer_release([payload])

    def offer_release(self, payloads: list, done=None):
        """Called by the camera loop with the windows one evaluation released together (live.run_live's flush), in
        time order; never blocks on the network. The release is one mailbox item: a newer release replaces an unsent
        one as a whole (each of its windows counted as replaced), and the thread posts a release's windows in order.
        A window of a session the backend answered 404 (unknown) or 410 (order completed) for is not offered until a
        window of a new session id comes.
        done (optional, no argument) is called once, when this release and every release offered before it are
        finished: each of their windows posted, failed or skipped, or dropped (replaced unsent, or the sender closing).
        A release may be empty (payloads []) to carry a done alone; it replaces nothing. done runs in the thread that
        finishes the last of them (this one when they are finished already, or the sender is closing)."""
        with self.cond:
            if self.closing:
                ready = [] if done is None else [done]
            else:
                self.counts["offered"] += len(payloads)
                kept = [p for p in payloads if not self._skip(p)]
                self.releases += 1
                if kept:
                    if self.slot is not None:
                        self.counts["replaced"] += len(self.slot)
                    self.slot, self.slot_k = kept, self.releases
                    self.cond.notify()
                if done is not None:
                    self.dones.append((self.releases, done))
                ready = self._finished()
        for call in ready:
            call()

    def _finished(self) -> list:
        """With the lock held: takes the dones whose release and every earlier one are finished (no earlier or equal k
        is in the slot or being posted), in k order; the caller calls them after releasing the lock."""
        open_k = [k for k in (self.posting_k, self.slot_k) if k is not None]
        first_open = min(open_k) if open_k else None
        ready = [d for k, d in self.dones if first_open is None or k < first_open]
        self.dones = [(k, d) for k, d in self.dones if first_open is not None and k >= first_open]
        return ready

    def _run(self):
        while True:
            with self.cond:
                while self.slot is None and not self.closing:
                    self.cond.wait()
                if self.slot is None:
                    return
                self.taken, self.slot = self.slot, None
                self.posting_k, self.slot_k = self.slot_k, None
            while True:
                with self.cond:
                    if self.abandoned or not self.taken:
                        break
                    payload = self.taken.pop(0)
                    if self._skip(payload):        # its session ended while the release waited
                        continue
                self._post(payload)
            with self.cond:
                self.posting_k = None
                ready = self._finished()
                abandoned = self.abandoned
            for call in ready:
                call()
            if abandoned:
                return

    def _post(self, payload: dict):
        try:
            data = json.dumps(jsonable(payload), ensure_ascii=False, default=plain).encode("utf-8")
            req = urllib.request.Request(target(self.base_url, payload["session_id"]), data=data, method="POST",
                                         headers={"Content-Type": "application/json"})
            with self.opener.open(req, timeout=self.timeout_s) as resp:
                resp.read()
                code = resp.status
            if not 200 <= code < 300:
                raise OSError(f"HTTP {code}")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):     # the session is unknown or its order is completed: not a failed send
                self._ended(payload["session_id"], e.code)
                return
            self._failed(e)
            return
        except Exception as e:    # a dead or slow backend, or a fault here: counted and dropped, the loop goes on
            self._failed(e)
            return
        with self.cond:
            self.counts["sent"] += 1

    def _ended(self, session: str, code: int):
        with self.cond:
            self.counts[f"ended_{code}"] += 1
            self.ended = (session, code)
            first = code not in self.told
            self.told.add(code)
        if first and self.log:
            what = "모르는 세션(404)" if code == 404 else "주문을 마친 세션(410)"
            self.log(f"[태그 보내기] backend가 세션 {session}을 {what}이라고 답함: 새 세션 ID의 창이 올 때까지 이 "
                     f"세션의 창은 보내지 않음(같은 답은 이후 세기만 함)")

    def _failed(self, e: Exception):
        with self.cond:
            self.counts["failed"] += 1
            first = self.last_error is None
            self.last_error = f"{type(e).__name__}: {e}"
        if first and self.log:
            self.log(f"[태그 보내기] 실패(이후 실패는 세기만 함): {self.last_error}")

    def stats(self) -> dict:
        with self.cond:
            return {**self.counts, "open_at_close": self.closing and self.thread.is_alive(),
                    "last_error": self.last_error, "timeout_s": self.timeout_s,
                    "target": self.base_url.rstrip("/") + PATH}

    def close(self) -> dict:
        """After the camera loop: the release in the mailbox and the rest of the one under way still get their sends,
        within one more timeout (the same cadence). The windows not posted by then are counted as unsent_at_close and
        the thread stops after the send under way, which is open_at_close (its outcome is not counted). Every done not
        called by then is called here (the sender is closing)."""
        with self.cond:
            self.closing = True
            self.cond.notify()
        self.thread.join(self.timeout_s)
        with self.cond:
            if self.thread.is_alive():
                self.abandoned = True
                self.counts["unsent_at_close"] += len(self.taken)
                self.taken = []
            if self.slot is not None:
                self.counts["unsent_at_close"] += len(self.slot)
                self.slot = None
            self.slot_k = self.posting_k = None
            ready = self._finished()
        for call in ready:
            call()
        return self.stats()
