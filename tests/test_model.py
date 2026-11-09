import json
import socket
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from topic_radar.model.answers import LenientModel, parse_answer
from topic_radar.model.client import Answer
from topic_radar.model.ollama import OllamaClient, PreflightError
from topic_radar.model.recording import RecordingClient
from topic_radar.model.scripted import ScriptedModel, UnmatchedPrompt
from topic_radar.store.runfolder import RunFolder

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


class Verdict(LenientModel):
    score: int
    reason: str = ""
    repeats: int | None = None


class FakeOllama:
    def __init__(self):
        self.models = ["gemma4:e4b-it-qat", "other:latest"]
        self.reply = {"message": {"content": '{"score": 2, "reason": "ok"}'},
                      "prompt_eval_count": 111, "eval_count": 22}
        self.delay = 0.0
        self.requests = []  # (method, path, parsed json body or None)
        self.address = ""


@pytest.fixture
def ollama():
    fake = FakeOllama()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

        def do_GET(self):
            fake.requests.append(("GET", self.path, None))
            if self.path == "/api/tags":
                self._send({"models": [{"name": m, "model": m} for m in fake.models]})
            else:
                self.send_error(404)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            fake.requests.append(("POST", self.path, json.loads(raw)))
            time.sleep(fake.delay)
            self._send(fake.reply)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    fake.address = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True).start()
    yield fake
    server.shutdown()
    server.server_close()


def client_for(fake, model="gemma4:e4b-it-qat", timeout=5, context=4096):
    return OllamaClient(fake.address, model, timeout, context)


async def test_client_sends_required_fields_and_parses_answer(ollama):
    answer = await client_for(ollama).call("triage", "SYS", "USER", Verdict)

    (method, path, body), = ollama.requests
    assert (method, path) == ("POST", "/api/chat")
    assert body["model"] == "gemma4:e4b-it-qat"
    assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert body["stream"] is False
    assert body["think"] is False
    assert body["format"] == Verdict.model_json_schema()
    assert body["options"] == {"temperature": 0, "num_ctx": 4096}
    assert answer.error == ""
    assert answer.parsed == Verdict(score=2, reason="ok")
    assert answer.text == '{"score": 2, "reason": "ok"}'
    assert (answer.prompt_tokens, answer.answer_tokens) == (111, 22)
    assert answer.seconds > 0


async def test_client_answer_follows_what_the_server_said(ollama):
    ollama.reply = {"message": {"content": '{"score": 0, "reason": "off topic"}'}}
    answer = await client_for(ollama, context=2048).call("triage", "s", "u", Verdict)
    assert answer.parsed == Verdict(score=0, reason="off topic")
    assert ollama.requests[0][2]["options"]["num_ctx"] == 2048


async def test_timeout_gives_an_answer_with_an_error(ollama):
    ollama.delay = 1.0
    answer = await client_for(ollama, timeout=0.2).call("read", "s", "u", Verdict)
    assert answer.parsed is None
    assert answer.kind == "timeout"
    assert "didn't answer" in answer.error
    assert "Timeout" not in answer.error and "Traceback" not in answer.error


async def test_nothing_listening_gives_an_answer_with_an_error():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    answer = await OllamaClient(f"http://127.0.0.1:{port}", "m", 1, 2048).call("read", "s", "u", Verdict)
    assert answer.parsed is None
    assert answer.kind == "unreachable"
    assert "ollama serve" in answer.error


async def test_unparseable_text_is_a_parse_failure_with_the_raw_text(ollama):
    ollama.reply = {"message": {"content": "I think it is relevant."}}
    answer = await client_for(ollama).call("triage", "s", "u", Verdict)
    assert answer.parsed is None
    assert answer.kind == "parse"
    assert answer.text == "I think it is relevant."
    assert answer.error


async def test_preflight_passes_when_the_model_is_installed(ollama):
    await client_for(ollama).preflight("gemma4:e4b-it-qat")
    assert ollama.requests == [("GET", "/api/tags", None)]


async def test_preflight_matches_a_bare_name_to_latest(ollama):
    await client_for(ollama).preflight("other")


async def test_preflight_says_ollama_serve_when_nothing_listens():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(PreflightError) as e:
        await OllamaClient(f"http://127.0.0.1:{port}", "m", 1, 2048).preflight("m")
    assert e.value.message == "Ollama isn't running. Start it with: ollama serve"


async def test_preflight_says_ollama_pull_when_the_model_is_missing(ollama):
    with pytest.raises(PreflightError) as e:
        await client_for(ollama).preflight("gemma4:e4b-mlx")
    assert e.value.message == "The model gemma4:e4b-mlx isn't installed. Install it with: ollama pull gemma4:e4b-mlx"


async def test_unload_sends_keep_alive_zero(ollama):
    await client_for(ollama).unload()
    (method, path, body), = ollama.requests
    assert (method, path) == ("POST", "/api/chat")
    assert body == {"model": "gemma4:e4b-it-qat", "keep_alive": 0}


async def test_unload_with_nothing_listening_does_not_raise():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    await OllamaClient(f"http://127.0.0.1:{port}", "m", 1, 2048).unload()


# --- lenient parsing ---

def test_a_number_sent_as_text_parses():
    assert parse_answer(Verdict, '{"score": "3", "repeats": " 2 "}').parsed == Verdict(score=3, repeats=2)


def test_empty_placeholders_are_treated_as_missing():
    got = parse_answer(Verdict, '{"score": 1, "reason": "", "repeats": "n/a"}').parsed
    assert got == Verdict(score=1, reason="", repeats=None)
    assert parse_answer(Verdict, '{"score": 1, "repeats": null}').parsed.repeats is None


def test_an_empty_placeholder_for_a_required_field_is_a_parse_error():
    a = parse_answer(Verdict, '{"score": ""}')
    assert a.parsed is None and a.kind == "parse" and a.error


def test_a_fenced_answer_parses():
    assert parse_answer(Verdict, '```json\n{"score": 2}\n```').parsed.score == 2


def test_text_that_is_not_a_number_is_a_parse_error():
    assert parse_answer(Verdict, '{"score": "high"}').kind == "parse"


# --- scripted model ---

async def test_scripted_model_raises_on_an_unmatched_prompt():
    model = ScriptedModel().on("triage", "Alpha", {"score": 3})
    with pytest.raises(UnmatchedPrompt) as e:
        await model.call("triage", "sys", "an item titled Beta", Verdict)
    assert "triage" in str(e.value)
    with pytest.raises(UnmatchedPrompt):
        await model.call("read", "sys", "an item titled Alpha", Verdict)


async def test_scripted_model_matches_on_step_and_marker():
    model = (ScriptedModel().on("triage", "Alpha", {"score": 3})
             .on("triage", "Beta", {"score": 0}))
    assert (await model.call("triage", "s", "x Beta x", Verdict)).parsed.score == 0
    assert (await model.call("triage", "s", "x Alpha x", Verdict)).parsed.score == 3
    assert len(model.calls) == 2


async def test_scripted_sequence_gives_answers_in_order_then_runs_out():
    model = ScriptedModel().on("triage", "", ["not json", {"score": 1}])
    first = await model.call("triage", "s", "u", Verdict)
    second = await model.call("triage", "s", "u", Verdict)
    assert (first.kind, second.parsed.score) == ("parse", 1)
    with pytest.raises(UnmatchedPrompt):
        await model.call("triage", "s", "u", Verdict)


# --- recording wrapper ---

@pytest.fixture
def folder(tmp_path):
    return RunFolder.create(tmp_path, lambda: NOW, echo=lambda line: None)


async def test_each_call_writes_one_prompt_answer_pair_numbered_per_step(folder):
    inner = ScriptedModel().on("triage", "", {"score": 1}).on("read", "", {"score": 2})
    client = RecordingClient(inner, folder)
    await client.call("triage", "SYS-A", "USER-A", Verdict)
    await client.call("triage", "SYS-B", "USER-B", Verdict)
    await client.call("read", "SYS-C", "USER-C", Verdict)

    names = sorted(p.name for p in folder.details.glob("*.txt"))
    assert names == ["read-001-answer.txt", "read-001-prompt.txt",
                     "triage-001-answer.txt", "triage-001-prompt.txt",
                     "triage-002-answer.txt", "triage-002-prompt.txt"]
    prompt = (folder.details / "triage-002-prompt.txt").read_text()
    assert "SYS-B" in prompt and "USER-B" in prompt and "SYS-A" not in prompt
    assert json.loads((folder.details / "triage-001-answer.txt").read_text()) == {"score": 1}
    events = [json.loads(l) for l in (folder.details / "events.jsonl").read_text().splitlines()]
    assert [(e["event"], e["step"], e["number"]) for e in events] == [
        ("model_call", "triage", 1), ("model_call", "triage", 2), ("model_call", "read", 1)]


async def test_an_unparseable_answer_is_retried_once_then_recorded_as_failed(folder):
    inner = ScriptedModel().on("triage", "", ["nonsense one", "nonsense two", {"score": 3}])
    answer = await RecordingClient(inner, folder).call("triage", "s", "u", Verdict)

    assert len(inner.calls) == 2  # one retry, not two
    assert answer.parsed is None and answer.kind == "parse" and answer.error
    assert answer.text == "nonsense two"
    assert (folder.details / "triage-001-answer.txt").read_text() == "nonsense two"
    events = [json.loads(l) for l in (folder.details / "events.jsonl").read_text().splitlines()]
    assert events[0]["attempts"] == 2 and events[0]["error"]


async def test_a_retry_that_parses_gives_the_good_answer(folder):
    inner = ScriptedModel().on("triage", "", ["nonsense", {"score": 3}])
    answer = await RecordingClient(inner, folder).call("triage", "s", "u", Verdict)
    assert len(inner.calls) == 2
    assert answer.parsed.score == 3 and answer.error == ""


async def test_a_retry_keeps_the_first_raw_answer_beside_the_final_one(folder):
    inner = ScriptedModel().on("triage", "", ["nonsense one", {"score": 3}])
    await RecordingClient(inner, folder).call("triage", "s", "u", Verdict)
    assert (folder.details / "triage-001-answer-1.txt").read_text() == "nonsense one"
    assert json.loads((folder.details / "triage-001-answer.txt").read_text()) == {"score": 3}


async def test_a_call_without_a_retry_writes_no_first_attempt_file(folder):
    inner = ScriptedModel().on("triage", "", {"score": 3})
    await RecordingClient(inner, folder).call("triage", "s", "u", Verdict)
    assert sorted(p.name for p in folder.details.glob("triage-001-*")) == ["triage-001-answer.txt", "triage-001-prompt.txt"]


async def test_a_good_first_answer_is_not_retried(folder):
    inner = ScriptedModel().on("triage", "", {"score": 3})
    await RecordingClient(inner, folder).call("triage", "s", "u", Verdict)
    assert len(inner.calls) == 1


async def test_a_timeout_is_recorded_without_a_retry(folder):
    timeout = Answer(error="The model didn't answer in time.", kind="timeout")
    inner = ScriptedModel().on("read", "", [timeout, {"score": 1}])
    answer = await RecordingClient(inner, folder).call("read", "s", "u", Verdict)
    assert len(inner.calls) == 1
    assert answer.kind == "timeout"
    assert (folder.details / "read-001-prompt.txt").exists()


def test_clean_removes_control_characters_but_keeps_words_and_spacing():
    from topic_radar.model.prompts import clean
    assert clean("a\x1b[31m red\x07\n  line\x9b") == "a[31m red line"
