"""Time over HTTP retries and format re-calls (call_time.py and the runners) and the 1-s tools that read it.

Standard library only and no network: urllib.request.urlopen, time.perf_counter and time.sleep are replaced, and the
anthropic package is replaced by a small stand-in. From the repository root:
    python -m unittest discover -s experiments/eval_llm_2026-11-09/tests -v
"""
import ast, hashlib, io, json, runpy, sys, tempfile, types, unittest, urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


def stand_in_anthropic():
    m = types.ModuleType("anthropic")

    class APIStatusError(Exception):
        def __init__(self, status_code=400):
            super().__init__(f"status {status_code}")
            self.status_code = status_code

    class RateLimitError(APIStatusError):
        pass

    class InternalServerError(APIStatusError):
        pass

    class APIConnectionError(Exception):
        pass

    class Anthropic:
        def __init__(self, **kwargs):
            self.messages = types.SimpleNamespace(create=None)

    for c in (APIStatusError, RateLimitError, InternalServerError, APIConnectionError, Anthropic):
        setattr(m, c.__name__, c)
    return m


sys.modules["anthropic"] = stand_in_anthropic()
import call_time  # noqa: E402
import run_claude  # noqa: E402
import run_gemini  # noqa: E402
import run_gpt  # noqa: E402
import run_scenarios  # noqa: E402

MSGS = [{"role": "system", "content": "Pick one."}, {"role": "user", "content": "{}"}]
OPTIONS = ["a", "none"]


class Clock:
    """A fake perf_counter (seconds) that the HTTP stand-ins and sleep move forward."""

    def __init__(self):
        self.t = 1000.0

    def patch(self):
        return mock.patch.multiple("time", perf_counter=lambda: self.t, sleep=self.sleep)

    def sleep(self, seconds):
        self.t += seconds


def openai_reply(choice, key="choice"):
    return json.dumps({"model": "m", "choices": [{"message": {"content": json.dumps({key: choice})},
                                                  "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 2}}).encode()


def gemini_reply(choice):
    return json.dumps({"modelVersion": "gemini-3.8-flash", "candidates": [
        {"content": {"parts": [{"text": json.dumps({"choice": choice})}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2}}).encode()


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
    def read(self, *args):  # the runners read the error body once; close it then
        body = self.fp.read(*args)
        self.close()
        return body


def http(clock, steps):
    """urlopen stand-in; each step is (ms, reply bytes) or (ms, (HTTP code, message))."""
    steps = list(steps)

    def urlopen(req, timeout=None):
        ms, out = steps.pop(0)
        clock.t += ms / 1000
        if isinstance(out, tuple):
            raise HTTPError(req.full_url, out[0], "error", {}, io.BytesIO(out[1].encode()))
        return Reply(out)

    return mock.patch("urllib.request.urlopen", urlopen)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()


class GptRunner(TempDir):
    def setUp(self):
        super().setUp()
        self.client = run_gpt.Client("not-a-key", "gpt-4o-mini-2024-07-18", 30, 256, self.dir / "cache")

    def ask(self, steps):
        with self.clock.patch(), http(self.clock, steps):
            return self.client.ask(MSGS, OPTIONS, 0)

    def test_no_retry_is_one_attempt(self):
        r = self.ask([(250, openai_reply("a"))])
        self.assertEqual((r["latency_ms"], r["retries"], r["request_ms"]), (250.0, 0, 250.0))
        self.assertEqual(r["http_attempts"], [{"ms": 250.0, "result": "ok", "wait_ms": 0.0}])

    def test_http_retry_counts_the_failed_attempt_and_the_wait(self):
        r = self.ask([(900, (503, "busy")), (300, openai_reply("a"))])
        self.assertEqual((r["latency_ms"], r["retries"]), (300.0, 1))  # existing fields keep their meaning
        self.assertEqual(r["http_attempts"][0], {"ms": 900.0, "result": "http 503", "wait_ms": 2000.0})
        self.assertEqual(r["request_ms"], 3200.0)
        with self.clock.patch(), http(self.clock, []):  # the same request again comes from the cache, with its time
            again = self.client.ask(MSGS, OPTIONS, 0)
        self.assertEqual((again["cached"], again["request_ms"]), (True, 3200.0))

    def test_request_refused_for_temperature_counts_into_the_call(self):
        refusal = (400, "Unsupported value: 'temperature' does not support 0")
        r = self.ask([(120, refusal), (300, openai_reply("a"))])
        self.assertEqual((r["latency_ms"], r["retries"], r["temperature_0"]), (300.0, 0, False))
        self.assertEqual([a["result"] for a in r["http_attempts"]], ["http 400, temperature refused", "ok"])
        self.assertEqual((r["request_ms"], r["accepted_ms"]), (420.0, 300.0))
        # the cache keeps the whole request that produced the answer, and the accepted body's own time apart
        stored = json.loads(next((self.dir / "cache").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual((stored["request_ms"], stored["accepted_ms"]), (420.0, 300.0))
        # the same client reuses the answer (no refusal any more) and still sees the producing request's time
        again = self.ask([])
        self.assertEqual((again["cached"], again["request_ms"]), (True, 420.0))
        self.assertNotIn("refused_now", again)
        # a new client (a rerun) is refused again before it reads the cache: recorded once, not added
        self.client = run_gpt.Client("not-a-key", "gpt-4o-mini-2024-07-18", 30, 256, self.dir / "cache")
        rerun = self.ask([(150, refusal)])
        self.assertEqual((rerun["cached"], rerun["request_ms"]), (True, 420.0))
        self.assertEqual(rerun["refused_now"], [{"ms": 150.0, "result": "http 400, temperature refused", "wait_ms": 0.0}])

    def test_cache_written_before_these_fields(self):
        # one cache file per attempt number: no HTTP retry (one attempt, latency_ms is the whole request) and
        # one retry (time unknown)
        for attempt, retries, expected in ((0, 0, 400.0), (1, 1, None)):
            b = self.client.body(MSGS, OPTIONS)
            ck = hashlib.sha256(json.dumps([self.client.model, b, attempt], sort_keys=True).encode()).hexdigest()
            (self.dir / "cache" / f"{ck}.json").write_text(json.dumps(
                {"latency_ms": 400.0, "model": "m", "content": '{"choice": "a"}', "finish_reason": "stop",
                 "retries": retries, "temperature_0": True, "schema": True, "error": None}), encoding="utf-8")
            with self.clock.patch(), http(self.clock, []):
                r = self.client.ask(MSGS, OPTIONS, attempt)
            self.assertEqual((r["cached"], r["request_ms"]), (True, expected))


class FailedCacheWrite(TempDir):
    """A response that succeeds but whose cache write fails: one HTTP attempt, its time counted once, no second
    request, and the answer is returned although it is not cached."""

    def test_failed_cache_write(self):
        clients = {"gpt": (run_gpt.Client("not-a-key", "gpt-4o-mini-2024-07-18", 30, 256, self.dir / "gpt"),
                           openai_reply("a")),
                   "gemini": (run_gemini.Client("not-a-key", "gemini-3.8-flash", 30, 256, self.dir / "gemini"),
                              gemini_reply("a"))}
        for name, (client, reply) in clients.items():
            with self.subTest(name):
                sent = []

                def urlopen(req, timeout=None, reply=reply):
                    sent.append(req)
                    self.clock.t += 0.25
                    return Reply(reply)

                with self.clock.patch(), mock.patch("urllib.request.urlopen", urlopen), \
                        mock.patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
                    r = client.ask(MSGS, OPTIONS, 0)
                self.assertEqual(len(sent), 1)
                self.assertEqual((r["error"], r["cached"], r["content"], r["request_ms"]),
                                 (None, False, '{"choice": "a"}', 250.0))
                self.assertEqual(r["http_attempts"], [{"ms": 250.0, "result": "ok", "wait_ms": 0.0}])
                self.assertEqual(list(client.cache_dir.glob("*.json")), [])


class ClaudeRunner(TempDir):
    def test_http_retry_counts_the_failed_attempt_and_the_wait(self):
        client = run_claude.Client("not-a-key", "claude-haiku-5-5", 30, 256, self.dir / "cache")
        steps = [(900, run_claude.anthropic.RateLimitError(429)), (300, None)]

        def create(**params):
            ms, err = steps.pop(0)
            self.clock.t += ms / 1000
            if err:
                raise err
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text='{"choice": "a"}')],
                                         model="claude-haiku-5-5", stop_reason="end_turn",
                                         usage=types.SimpleNamespace(input_tokens=10, output_tokens=2,
                                                                     cache_read_input_tokens=0))

        client.client.messages.create = create
        with self.clock.patch():
            r = client.ask(MSGS, OPTIONS, 0)
        self.assertEqual((r["latency_ms"], r["retries"], r["request_ms"]), (300.0, 1, 3200.0))
        self.assertEqual(r["http_attempts"][0], {"ms": 900.0, "result": "RateLimitError", "wait_ms": 2000.0})


class ScenarioRunner(TempDir):
    def test_refused_temperature_and_http_retry_count_into_the_case(self):
        cl = run_scenarios.OpenAI("not-a-key", "gpt-4o-mini-2024-07-18")
        b = cl.body("{}", {"support_choice": {"criteria": {"a": "A.", "none": "None."}}})
        steps = [(120, (400, "Unsupported value: 'temperature'")), (900, (503, "busy")),
                 (300, openai_reply("a", "support_choice"))]
        with self.clock.patch(), http(self.clock, steps):
            r = cl.call(b)
        self.assertEqual((r["latency_ms"], r["retries"]), (300.0, 1))
        self.assertEqual(r["request_ms"], 120.0 + 900.0 + 2000.0 + 300.0)


class StoredLineRule(unittest.TestCase):
    def test_whole_ms(self):
        self.assertEqual(call_time.whole_ms({"cumulative_ms": 1200.0, "latency_ms": 300.0}), 1200.0)
        self.assertEqual(call_time.whole_ms({"attempt": 0, "retries": 0, "latency_ms": 400.0}), 400.0)
        self.assertIsNone(call_time.whole_ms({"attempt": 0, "retries": 1, "latency_ms": 400.0}))
        self.assertIsNone(call_time.whole_ms({"attempt": 1, "retries": 0, "latency_ms": 300.0}))


class OneSecondTool(TempDir):
    """run_gpt.py writes the runs, one_second.py reads them (both run in this process)."""

    def make_kit(self, states=None):
        """Kit with windows w1..w3; states maps a window to its state (windows with the same state share a prompt)."""
        states = states or {w: {"window": w} for w in ("w1", "w2", "w3")}
        kit = self.dir / "kit"
        q = {"qs": {"questions": {"support_choice": {"instructions": "Pick one.",
                                                     "criteria": {"a": "Help.", "none": "Wait."}}}}}
        (kit / "data").mkdir(parents=True)
        (kit / "data/questions.json").write_text(json.dumps(q), encoding="utf-8")
        write_jsonl(kit / "data/E5_C0.jsonl", [
            {"window_id": w, "stages": [{"stage": "support_choice", "questions": "qs", "options": OPTIONS,
                                         "state": s}]} for w, s in states.items()])
        e5 = self.dir / "e5"
        for arm, d in (("E5_J", "stage2_3_J_b0_r0"), ("E5_C0", "stage2_1_swap_C_C0")):
            write_jsonl(kit / f"reference_answers/{arm}.jsonl", [{"window_id": "take@1.0", "choice": "a"}])
            write_jsonl(e5 / d / "jev_calls.jsonl", [
                {"arm": "J" if arm == "E5_J" else "C0", "take": "take", "t": 1.0,
                 "stages": [{"stage": "support_choice", "latency_ms": 200.0,
                             "answers": {"support_choice": {"choice": "a"}}}]}])
        return kit, e5

    def test_one_second(self):
        kit, e5 = self.make_kit()
        root = self.dir / "root"
        env = self.dir / "env"
        env.write_text("OPENAI_API_KEY=not-a-key\n", encoding="utf-8")
        steps = [(900, openai_reply("not-an-option")), (300, openai_reply("a")),  # w1: format error, then re-call
                 (250, openai_reply("a")),                                       # w2: no retry
                 (900, (503, "busy")), (300, openai_reply("a"))]                 # w3: HTTP retry after a wait
        argv = ["run_gpt.py", "--kit", str(kit), "--arm", "E5_C0", "--model", "gpt-4o-mini-2024-07-18",
                "--env", str(env), "--out", str(root / "runs/new_E5_C0"), "--cache", str(self.dir / "cache"),
                "--workers", "1"]
        with self.clock.patch(), http(self.clock, steps), mock.patch.object(sys, "argv", argv), \
                redirect_stdout(io.StringIO()):
            run_gpt.main()
        calls = read_jsonl(root / "runs/new_E5_C0/calls.jsonl")
        self.assertEqual([(c["window_id"], c["attempt"], c["latency_ms"], c["cumulative_ms"]) for c in calls],
                         [("w1", 0, 900.0, 900.0), ("w1", 1, 300.0, 1200.0), ("w2", 0, 250.0, 250.0),
                          ("w3", 0, 300.0, 3200.0)])

        # lines stored before the time fields: w1 no retry and no earlier attempt (used as it is),
        # w2 an HTTP retry, w3 an earlier attempt (both: time unknown)
        write_jsonl(root / "runs/stored_E5_C0/calls.jsonl", [
            {"window_id": "w1", "attempt": 0, "choice": "a", "latency_ms": 400.0, "retries": 0},
            {"window_id": "w2", "attempt": 0, "choice": "a", "latency_ms": 400.0, "retries": 1},
            {"window_id": "w3", "attempt": 0, "choice": None, "latency_ms": 600.0, "retries": 0},
            {"window_id": "w3", "attempt": 1, "choice": "a", "latency_ms": 300.0, "retries": 0}])
        write_jsonl(root / "runs/stored_E5_C0/answers.jsonl", [{"window_id": w, "choice": "a"} for w in ("w1", "w2", "w3")])

        report = self.run_one_second(root, kit, e5)

        def answers(run):
            return {r["window_id"]: r["choice"] for r in read_jsonl(root / f"runs/{run}/answers_1s.jsonl")}

        # w1 is the reviewers' case: 900 ms then 300 ms is not within 1 s although its answering request took 300 ms
        self.assertEqual(answers("new_E5_C0"), {"w1": None, "w2": "a", "w3": None})
        self.assertEqual(report["new_E5_C0"], {"windows": 3, "set_null_over_1s": 2, "set_null_time_unknown": 0})
        self.assertEqual(answers("stored_E5_C0"), {"w1": "a", "w2": None, "w3": None})
        self.assertEqual(report["stored_E5_C0"], {"windows": 3, "set_null_over_1s": 0, "set_null_time_unknown": 2})
        self.assertEqual(answers("jev_E5_C0_1s"), {"take@1.0": "a"})

    def run_one_second(self, root, kit, e5):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["one_second.py", str(root), str(kit), str(e5)]), redirect_stdout(out):
            runpy.run_path(str(TOOLS / "one_second.py"), run_name="__main__")
        return json.loads(out.getvalue())

    def test_cached_answer_keeps_the_time_of_the_request_that_produced_it(self):
        # w1 and w2 share a prompt; w1's request is refused for temperature 0 (900 ms) and answered in 300 ms,
        # w2 is answered from the cache by the same client; w3 has its own prompt, answered in 250 ms
        kit, e5 = self.make_kit({"w1": {"k": 1}, "w2": {"k": 1}, "w3": {"k": 3}})
        root, env = self.dir / "root", self.dir / "env"
        env.write_text("OPENAI_API_KEY=not-a-key\n", encoding="utf-8")
        steps = [(900, (400, "Unsupported value: 'temperature'")), (300, openai_reply("a")), (250, openai_reply("a"))]
        argv = ["run_gpt.py", "--kit", str(kit), "--arm", "E5_C0", "--model", "gpt-4o-mini-2024-07-18",
                "--env", str(env), "--out", str(root / "runs/new_E5_C0"), "--cache", str(self.dir / "cache"),
                "--workers", "1"]
        with self.clock.patch(), http(self.clock, steps), mock.patch.object(sys, "argv", argv), \
                redirect_stdout(io.StringIO()):
            run_gpt.main()
        calls = read_jsonl(root / "runs/new_E5_C0/calls.jsonl")
        self.assertEqual([(c["window_id"], c["cached"], c["latency_ms"], c["cumulative_ms"]) for c in calls],
                         [("w1", False, 300.0, 1200.0), ("w2", True, 300.0, 1200.0), ("w3", False, 250.0, 250.0)])
        report = self.run_one_second(root, kit, e5)
        answers = {r["window_id"]: r["choice"] for r in read_jsonl(root / "runs/new_E5_C0/answers_1s.jsonl")}
        self.assertEqual(answers, {"w1": None, "w2": None, "w3": "a"})
        self.assertEqual(report["new_E5_C0"], {"windows": 3, "set_null_over_1s": 2, "set_null_time_unknown": 0})

        # a rerun (new process) is refused once more before it reads the cache: the line records that refusal
        # and keeps the producing request's time, without adding the refusal a second time
        argv[argv.index("--out") + 1] = str(root / "runs/rerun_E5_C0")
        with self.clock.patch(), http(self.clock, [(100, (400, "Unsupported value: 'temperature'"))]), \
                mock.patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            run_gpt.main()
        rerun = read_jsonl(root / "runs/rerun_E5_C0/calls.jsonl")
        self.assertEqual([(c["window_id"], c["cached"], c["cumulative_ms"]) for c in rerun],
                         [("w1", True, 1200.0), ("w2", True, 1200.0), ("w3", True, 250.0)])
        self.assertEqual([len(c["refused_now"] or []) for c in rerun], [1, 0, 0])

    def test_gemini_refusal_and_retry_reach_the_one_second_judgment(self):
        # w1: thinking level refused (100 ms), then 503 (900 ms) and a 2 s wait, then the answer (300 ms);
        # w2 shares w1's prompt and is answered from the cache; w3 is answered in 250 ms
        kit, e5 = self.make_kit({"w1": {"k": 1}, "w2": {"k": 1}, "w3": {"k": 3}})
        root, env = self.dir / "root", self.dir / "env"
        env.write_text("GEMINI_API_KEY=not-a-key\n", encoding="utf-8")
        steps = [(100, (400, "Thinking level is not supported for this model.")), (900, (503, "busy")),
                 (300, gemini_reply("a")), (250, gemini_reply("a"))]
        argv = ["run_gemini.py", "--kit", str(kit), "--arm", "E5_C0", "--model", "gemini-3.8-flash",
                "--env", str(env), "--out", str(root / "runs/gemini_E5_C0"), "--cache", str(self.dir / "cache"),
                "--workers", "1"]
        with self.clock.patch(), http(self.clock, steps), mock.patch.object(sys, "argv", argv), \
                redirect_stdout(io.StringIO()):
            run_gemini.main()
        calls = read_jsonl(root / "runs/gemini_E5_C0/calls.jsonl")
        self.assertEqual([(c["window_id"], c["cached"], c["latency_ms"], c["cumulative_ms"]) for c in calls],
                         [("w1", False, 300.0, 3300.0), ("w2", True, 300.0, 3300.0), ("w3", False, 250.0, 250.0)])
        self.assertEqual([a["result"] for a in calls[0]["http_attempts"]],
                         ["http 400, thinking level refused", "http 503", "ok"])
        self.run_one_second(root, kit, e5)
        answers = {r["window_id"]: r["choice"] for r in read_jsonl(root / "runs/gemini_E5_C0/answers_1s.jsonl")}
        self.assertEqual(answers, {"w1": None, "w2": None, "w3": "a"})


class ScenarioOneSecondTool(TempDir):
    def make_inputs(self, root):
        for s in ("novel", "heldout1", "heldout2"):
            (root / "inputs").mkdir(parents=True, exist_ok=True)
            gold = {"c1": {"kind": "help", "acceptable": ["a"]}, "c2": {"kind": "wait", "acceptable": []}}
            (root / f"inputs/{s}_gold.json").write_text(json.dumps(gold), encoding="utf-8")
            write_jsonl(root / f"inputs/{s}_rule.jsonl", [{"window_id": "c1", "choice": "none"},
                                                          {"window_id": "c2", "choice": "none"}])

    def score(self, root):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["score_scen_1s.py", str(root)]), redirect_stdout(out):
            runpy.run_path(str(TOOLS / "score_scen_1s.py"), run_name="__main__")
        text = out.getvalue()
        return json.loads(text[:text.index("rule:")]), ast.literal_eval(text.rsplit("(cases per run): ", 1)[1].strip())

    def test_runner_re_call_reaches_the_one_second_judgment(self):
        # c1: an answer outside the options after 900 ms, the re-call answers in 300 ms; c2 answers in 250 ms
        root, env = self.dir / "scen", self.dir / "env"
        self.make_inputs(root)
        env.write_text("OPENAI_API_KEY=not-a-key\n", encoding="utf-8")
        q = {"support_choice": {"criteria": {"a": "Help.", "none": "Wait."}}}
        write_jsonl(root / "inputs/novel.jsonl", [{"case_id": c, "state": {"case": c}, "questions": q} for c in ("c1", "c2")])
        steps = [(900, openai_reply("not-an-option", "support_choice")), (300, openai_reply("a", "support_choice")),
                 (250, openai_reply("none", "support_choice"))]
        argv = ["run_scenarios.py", "--set", "novel", "--model", "gpt-4o-mini-2024-07-18", "--run", "1",
                "--root", str(root), "--cache", str(self.dir / "cache"), "--openai-env", str(env),
                "--anthropic-env", str(env), "--workers", "1"]
        with self.clock.patch(), http(self.clock, steps), mock.patch.object(sys, "argv", argv), \
                redirect_stdout(io.StringIO()):
            run_scenarios.main()
        calls = read_jsonl(root / "gpt-4o-mini-2024-07-18__novel__r1/calls.jsonl")
        self.assertEqual([(c["case_id"], c["attempt"], c["latency_ms"], c["cumulative_ms"]) for c in calls],
                         [("c1", 0, 900.0, 900.0), ("c1", 1, 300.0, 1200.0), ("c2", 0, 250.0, 250.0)])
        scores, unknown = self.score(root)
        # c1's answer took 1,200 ms from its first request: the rule table's answer is used (help missed)
        self.assertEqual(scores["gpt-4o-mini-2024-07-18 | novel"]["runs"], [0.5])
        self.assertEqual(unknown["gpt-4o-mini-2024-07-18 | novel"], [0])

    def test_score_scen_1s(self):
        root = self.dir / "scen"
        self.make_inputs(root)
        c2 = {"case_id": "c2", "attempt": 0, "choice": "none", "latency_ms": 300.0, "retries": 0, "cumulative_ms": 300.0}
        runs = {"r1": [{"case_id": "c1", "attempt": 0, "choice": "a", "latency_ms": 400.0, "retries": 0}, c2],
                "r2": [{"case_id": "c1", "attempt": 0, "choice": "a", "latency_ms": 400.0, "retries": 1}, c2],
                "r3": [{"case_id": "c1", "attempt": 0, "choice": None, "latency_ms": 900.0, "retries": 0,
                        "cumulative_ms": 900.0},
                       {"case_id": "c1", "attempt": 1, "choice": "a", "latency_ms": 300.0, "retries": 0,
                        "cumulative_ms": 1200.0}, c2]}
        for r, lines in runs.items():
            write_jsonl(root / f"m__novel__{r}/calls.jsonl", lines)
            write_jsonl(root / f"m__novel__{r}/answers.jsonl", [{"case_id": "c1", "choice": "a"},
                                                                {"case_id": "c2", "choice": "none"}])
        scores, unknown = self.score(root)
        # r1: stored line with no retry, used as it is; r2: stored line with a retry, time unknown;
        # r3: 900 ms then 300 ms after a format error, over 1 s
        self.assertEqual(scores["m | novel"]["runs"], [1.0, 0.5, 0.5])
        self.assertEqual(unknown["m | novel"], [0, 1, 0])


if __name__ == "__main__":
    unittest.main()
