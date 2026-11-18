"""Time fields of run_llm.py over HTTP retries, a refused temperature and the stages of one window.

Standard library only and no network: urllib.request.urlopen, time.perf_counter and time.sleep are replaced.
From the repository root:
    python -m unittest discover -s experiments/eval_scenarios_2026-11-09/tests -v
"""
import io, json, sys, tempfile, unittest, urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import run_llm  # noqa: E402  (puts eval_llm_2026-11-09/tools on the path for call_time)
from call_time import whole_ms  # noqa: E402

CHOICE = {"support_choice": {"type": "choice", "criteria": {"none": "wait", "large_button": "bigger buttons"}}}
SCORES = {"hesitation": {"type": "noul", "criteria": "the customer hesitates"}}


class Clock:
    """A fake perf_counter (seconds) that the HTTP stand-in and sleep move forward."""

    def __init__(self):
        self.t = 1000.0

    def patch(self):
        return mock.patch.multiple("time", perf_counter=lambda: self.t, sleep=self.sleep)

    def sleep(self, seconds):
        self.t += seconds


def reply(answers):
    return json.dumps({"model": "m", "choices": [{"message": {"content": json.dumps(answers)}}],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 2}}).encode()


class Reply:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


class HTTPError(urllib.error.HTTPError):
    def read(self, *args):  # the runner reads the error body once; close it then
        body = self.fp.read(*args)
        self.close()
        return body


def http(clock, steps, sent=None):
    """urlopen stand-in; each step is (ms, reply bytes), (ms, (HTTP code, message)) or (ms, an exception)."""
    steps = list(steps)

    def urlopen(req, timeout=None):
        if sent is not None:
            sent.append(json.loads(req.data))
        ms, out = steps.pop(0)
        clock.t += ms / 1000
        if isinstance(out, tuple):
            raise HTTPError(req.full_url, out[0], "error", {}, io.BytesIO(out[1].encode()))
        if isinstance(out, Exception):
            raise out
        return Reply(out)

    return mock.patch("urllib.request.urlopen", urlopen)


class Ask(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.client = run_llm.Client("not-a-key", "gpt-4o-mini", 30)
        self.sent = []

    def ask(self, steps):
        with self.clock.patch(), http(self.clock, steps, self.sent):
            return self.client.ask({"touch": {}}, CHOICE)

    def test_no_retry_is_one_attempt(self):
        r = self.ask([(250, reply({"support_choice": "none"}))])
        self.assertEqual((r["answers"], r["latency_ms"], r["retries"], r["request_ms"]),
                         ({"support_choice": "none"}, 250, 0, 250.0))
        self.assertEqual(r["http_attempts"], [{"ms": 250.0, "result": "ok", "wait_ms": 0.0}])

    def test_http_retry_counts_the_failed_attempt_and_the_wait(self):
        r = self.ask([(900, (503, "busy")), (300, reply({"support_choice": "none"}))])
        self.assertEqual((r["latency_ms"], r["retries"]), (300, 1))  # existing fields keep their meaning
        self.assertEqual(r["http_attempts"][0], {"ms": 900.0, "result": "http 503", "wait_ms": 2000.0})
        self.assertEqual(r["request_ms"], 3200.0)

    def test_refused_temperature_is_counted_and_is_not_a_retry(self):
        r = self.ask([(400, (400, "Unsupported value: 'temperature'")), (600, reply({"support_choice": "none"}))])
        self.assertEqual((r["latency_ms"], r["retries"], r["request_ms"]), (600, 0, 1000.0))
        self.assertEqual(r["http_attempts"][0]["result"], "http 400, temperature refused")
        self.assertEqual(["temperature" in b for b in self.sent], [True, False])
        self.assertFalse(self.client.use_temperature)

    def test_timeout_is_retried_once_without_a_wait(self):
        r = self.ask([(30000, TimeoutError()), (400, reply({"support_choice": "none"}))])
        self.assertEqual((r["latency_ms"], r["retries"], r["request_ms"]), (400, 1, 30400.0))
        self.assertEqual(r["http_attempts"][0], {"ms": 30000.0, "result": "TimeoutError", "wait_ms": 0.0})

    def test_unreadable_answer_is_retried_once_and_counted(self):
        bad = json.dumps({"choices": [{"message": {"content": "not json"}}]}).encode()
        r = self.ask([(500, bad), (300, reply({"support_choice": "none"}))])
        self.assertEqual((r["latency_ms"], r["retries"], r["request_ms"]), (300, 1, 800.0))
        self.assertEqual([a["result"] for a in r["http_attempts"]], ["JSONDecodeError", "ok"])

    def test_failed_request_keeps_its_time(self):
        r = self.ask([(100, (429, "slow down"))] * 4)
        self.assertEqual((r["error"], r["retries"]), ("http 429", 3))
        self.assertNotIn("latency_ms", r)
        self.assertEqual(r["request_ms"], 4 * 100 + (2 + 4 + 8) * 1000)
        other = self.ask([(100, (400, "bad request")), ])
        self.assertEqual((other["error"], other["request_ms"]), ("http 400: bad request", 100.0))


class Window(unittest.TestCase):
    """cumulative_ms runs over the stages of one window; the 1-s tools read the last line with whole_ms."""

    QUESTIONS = {"scores": {"questions": SCORES}, "choice": {"questions": CHOICE}}
    ROW = {"window_id": "w1", "stages": [
        {"stage": "state_scores", "questions": "scores", "state": {"touch": {}}},
        {"stage": "support_choice", "questions": "choice", "options": ["none", "large_button"],
         "state": {"touch": {}, "jev": {"scores": run_llm.PLACEHOLDER}}}]}

    def setUp(self):
        self.clock = Clock()
        self.client = run_llm.Client("not-a-key", "gpt-4o-mini", 30)

    def run_window(self, steps, sent=None):
        with self.clock.patch(), http(self.clock, steps, sent):
            return run_llm.run_window(self.client, self.QUESTIONS, self.ROW)

    def test_two_stages_add_up_on_the_last_line(self):
        answer, logs = self.run_window([(400, reply({"hesitation": 0.9})), (450, reply({"support_choice": "large_button"}))])
        self.assertEqual(answer, {"window_id": "w1", "choice": "large_button"})
        self.assertEqual([l["cumulative_ms"] for l in logs], [400.0, 850.0])
        self.assertEqual(whole_ms(logs[-1]), 850.0)  # within 1 s

    def test_a_retry_in_the_first_stage_moves_the_window_past_one_second(self):
        sent = []
        answer, logs = self.run_window([(300, (503, "busy")), (300, reply({"hesitation": 0.9})),
                                        (300, reply({"support_choice": "none"}))], sent)
        self.assertEqual(sum(l["latency_ms"] for l in logs), 600)  # what the bundle's scorers summed: within 1 s
        self.assertEqual(whole_ms(logs[-1]), 2900.0)               # 300 + 2,000 wait + 300 + 300: not within 1 s
        self.assertEqual(json.loads(sent[-1]["messages"][1]["content"])["state"]["jev"], {"scores": {"hesitation": 0.9}})

    def test_failed_first_stage_is_still_counted(self):
        answer, logs = self.run_window([(200, (401, "no key")), (300, reply({"support_choice": "none"}))])
        self.assertEqual((logs[0]["error"], logs[0]["cumulative_ms"]), ("http 401", 200.0))
        self.assertEqual((answer["choice"], logs[1]["cumulative_ms"]), ("none", 500.0))


class Main(unittest.TestCase):
    def test_run_writes_the_time_fields_and_the_window_summary(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp:
            kit, out, env = Path(tmp) / "kit", Path(tmp) / "out", Path(tmp) / "env"
            (kit / "data").mkdir(parents=True)
            (kit / "data/questions.json").write_text(json.dumps(Window.QUESTIONS), encoding="utf-8")
            rows = [{**Window.ROW, "window_id": w} for w in ("w1", "w2")]
            (kit / "data/ARM.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            env.write_text("OPENAI_API_KEY=not-a-key\n", encoding="utf-8")
            steps = [(400, reply({"hesitation": 0.9})), (450, reply({"support_choice": "large_button"})),
                     (300, (503, "busy")), (300, reply({"hesitation": 0.1})), (300, reply({"support_choice": "none"}))]
            argv = ["run_llm.py", "--kit", str(kit), "--arm", "ARM", "--model", "gpt-4o-mini", "--env", str(env),
                    "--out", str(out), "--workers", "1"]
            with clock.patch(), http(clock, steps), mock.patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                self.assertEqual(run_llm.main(), 0)
            calls = [json.loads(l) for l in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([c["cumulative_ms"] for c in calls], [400.0, 850.0, 2600.0, 2900.0])
            self.assertNotIn("not-a-key", (out / "calls.jsonl").read_text(encoding="utf-8"))
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual((summary["windows"], summary["calls"], summary["errors"]), (2, 4, 0))
            self.assertEqual((summary["window_ms_p50"], summary["windows_within_1s"],
                              summary["calls_with_more_than_one_http_attempt"]), (1875.0, 1, 1))


if __name__ == "__main__":
    unittest.main()
