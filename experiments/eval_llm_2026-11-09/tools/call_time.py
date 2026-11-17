"""Time of one model call from its first HTTP request to its valid answer, recorded by the runners and read by the 1-s
tools (one_second.py, score_scen_1s.py) through whole_ms().

A call is the question for one window (or one scenario case). It can take several HTTP attempts: a 429, a 5xx,
a timeout or an unreadable response is retried after a wait, and a request whose setting the model refuses
(temperature 0, json_schema, thinking level) is sent again without it. After an answer in a wrong format the
runner asks once more (calls.jsonl line with attempt 1). Each calls.jsonl line therefore carries
    latency_ms     the HTTP attempt that returned this line's response (meaning unchanged)
    retries        HTTP retries of the request body that answered (meaning unchanged)
    http_attempts  every HTTP attempt of this line's request, those of a refused body included:
                   {"ms", "result", "wait_ms" (wait before the next one)}
    request_ms     the sum of those attempts and waits
    accepted_ms    (run_gpt.py, run_gemini.py) the part of request_ms spent on the body that was accepted
    refused_now    (a line answered from the cache only) attempts the present call sent with a body that was then
                   refused, before the cache was read; recorded, not added (see attach)
    cumulative_ms  request_ms of this line plus that of the call's earlier lines: the time from the call's first
                   request to the end of this line's request; on the answering line, the time to the valid answer
Times are perf_counter around each HTTP exchange (request and reading the response) and around each wait.
The cache keeps a response with the whole time of the request that produced it (refused bodies included), and a
response read from the cache is judged on that time.
Standard library only.
"""
import time


def ms_since(t0):
    return (time.perf_counter() - t0) * 1000


class Attempts:
    """HTTP attempts of one request line and the waits between them."""

    def __init__(self):
        self.items = []

    def add(self, ms, result):
        self.items.append({"ms": round(ms, 1), "result": result, "wait_ms": 0.0})

    def wait(self, seconds):
        """Sleep before the next attempt; the time slept goes to the last attempt."""
        t0 = time.perf_counter()
        time.sleep(seconds)
        self.items[-1]["wait_ms"] = round(ms_since(t0), 1)

    def total(self, start=0):
        return total(self.items[start:])


def total(items):
    return round(sum(a["ms"] + a["wait_ms"] for a in items), 1)


def stored_request_ms(rec):
    """request_ms of one response record (cache file or runner result), or None when the record cannot give it.

    A record stored before request_ms existed counts as one attempt when it shows no HTTP retry (retries 0):
    its latency_ms is then the whole request. Any other such record has no known request time."""
    if "request_ms" in rec:
        return rec["request_ms"]
    if rec.get("retries") == 0 and rec.get("latency_ms") is not None:
        return rec["latency_ms"]
    return None


def attach(rec, refused_now=()):
    """Time fields of a response read from the cache. Returns rec.

    The answer is judged on the stored time of the request that produced it (http_attempts and request_ms, a refused
    body's attempts included). A record stored before these fields counts as one attempt when it shows no HTTP retry
    (retries 0); otherwise request_ms is None (unknown). Attempts the present call sent with a body that was refused
    before the cache was read go to refused_now and are not added: the stored time stands for the whole request that
    produced the answer, which may already hold a refusal of its own."""
    t = stored_request_ms(rec)
    if rec.get("http_attempts") is None and t is not None:  # stored before these fields, no retry: one attempt
        rec["http_attempts"] = [{"ms": rec["latency_ms"], "result": "ok", "wait_ms": 0.0}]
    rec["request_ms"] = t
    if refused_now:
        rec["refused_now"] = list(refused_now)
    return rec


def add_ms(so_far, ms):
    """Running cumulative time of a call; None once any part is unknown."""
    return None if so_far is None or ms is None else round(so_far + ms, 1)


def whole_ms(line):
    """Time from the call's first request to the answer on this calls.jsonl line, or None when the line cannot give it.

    A line with cumulative_ms carries it. A line stored before that field is used as it is only when it shows no
    HTTP retry (retries 0) and no earlier attempt (attempt 0): then the answering request's latency_ms is the whole
    time. For any other such line the time is unknown; the 1-s tools do not count it as within 1 s and report how
    many there were."""
    if "cumulative_ms" in line:
        return line["cumulative_ms"]
    if line.get("retries") == 0 and line.get("attempt") == 0:
        return line.get("latency_ms")
    return None
