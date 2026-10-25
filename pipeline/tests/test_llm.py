import json
from types import SimpleNamespace

import httpx
import pytest

from metashift.core.errors import MetashiftError
from metashift.core.llm import (
    ClaudeClient,
    FakeLLM,
    OllamaClient,
    complete_with_retry,
    make_llm,
)
from metashift.core.models import ExtractDraft


def test_retry_feeds_validation_error_back():
    llm = FakeLLM(['{"changes": "x"}', '{"changes": []}'])
    result, retries, problems = complete_with_retry(llm, "P", ExtractDraft)
    assert result.changes == [] and retries == 1 and problems == []
    assert "Your previous answer was invalid" in llm.prompts[1]


def test_retry_gives_up_after_two():
    llm = FakeLLM(["nope"] * 3)
    with pytest.raises(MetashiftError, match="after 2 retries"):
        complete_with_retry(llm, "P", ExtractDraft)
    assert len(llm.prompts) == 3


def test_check_problems_returned_when_retries_run_out():
    llm = FakeLLM(['{"changes": []}'] * 3)
    _, retries, problems = complete_with_retry(
        llm, "P", ExtractDraft, check=lambda r: ["missing Ahri"]
    )
    assert retries == 2 and problems == ["missing Ahri"]
    assert "missing Ahri" in llm.prompts[1]


def test_malformed_retry_after_a_valid_result_keeps_the_valid_result():
    llm = FakeLLM(['{"changes": []}', "nope", "nope"])
    result, retries, problems = complete_with_retry(
        llm, "P", ExtractDraft, check=lambda r: ["missing Ahri"]
    )
    assert result == ExtractDraft(changes=[]) and retries == 2
    assert problems[0] == "missing Ahri"
    assert any("invalid JSON" in p for p in problems[1:])
    assert len(llm.prompts) == 3
    assert "missing Ahri" in llm.prompts[2]  # the rule problem is still named in the retry


def test_malformed_retry_can_still_recover_with_a_later_valid_result():
    llm = FakeLLM(['{"changes": []}', "nope", '{"changes": []}'])
    calls = iter([["missing Ahri"], []])
    result, retries, problems = complete_with_retry(
        llm, "P", ExtractDraft, check=lambda r: next(calls)
    )
    assert result == ExtractDraft(changes=[]) and retries == 2 and problems == []


def test_no_valid_result_ever_still_raises():
    llm = FakeLLM(["nope"] * 3)
    with pytest.raises(MetashiftError, match="invalid JSON after 2 retries"):
        complete_with_retry(llm, "P", ExtractDraft, check=lambda r: ["x"])


def test_ollama_unreachable_says_ollama_serve():
    def boom(request):
        raise httpx.ConnectError("refused")

    llm = OllamaClient(
        model="m", host="http://localhost:11434", transport=httpx.MockTransport(boom)
    )
    with pytest.raises(MetashiftError, match="ollama serve"):
        llm.complete_json("P", ExtractDraft)


def test_ollama_sends_schema_and_parses_content():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        body = json.loads(request.content)
        seen["body"] = body
        return httpx.Response(200, json={"message": {"content": '{"changes": []}'}})

    llm = OllamaClient(model="m", host="http://x", transport=httpx.MockTransport(handler))
    result = llm.complete_json("P", ExtractDraft)
    assert result == ExtractDraft(changes=[])
    assert llm.name == "ollama:m"
    assert seen["url"] == "http://x/api/chat"
    body = seen["body"]
    assert body["format"] == ExtractDraft.model_json_schema()
    assert body["model"] == "m"
    assert body["messages"] == [{"role": "user", "content": "P"}]
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0, "num_ctx": 32768}
    assert body["think"] is False


def test_ollama_timeout_becomes_a_clear_error_with_the_env_hint(monkeypatch):
    monkeypatch.setenv("METASHIFT_OLLAMA_TIMEOUT", "5")
    seen = {}

    def slow(request: httpx.Request) -> httpx.Response:
        seen["timeout"] = request.extensions["timeout"]
        raise httpx.ReadTimeout("slow", request=request)

    llm = OllamaClient(model="m", host="http://x", transport=httpx.MockTransport(slow))
    with pytest.raises(MetashiftError) as err:
        llm.complete_json("P", ExtractDraft)
    assert str(err.value) == (
        "Ollama timed out after 5s on m. Raise METASHIFT_OLLAMA_TIMEOUT or use a smaller model"
    )
    assert seen["timeout"]["read"] == 5


def test_ollama_timeout_defaults_to_600_and_rejects_bad_env(monkeypatch):
    monkeypatch.delenv("METASHIFT_OLLAMA_TIMEOUT", raising=False)
    assert OllamaClient().timeout == 600
    monkeypatch.setenv("METASHIFT_OLLAMA_TIMEOUT", "soon")
    with pytest.raises(MetashiftError, match="METASHIFT_OLLAMA_TIMEOUT"):
        OllamaClient()


def test_ollama_reads_defaults_from_env(monkeypatch):
    monkeypatch.setenv("METASHIFT_OLLAMA_MODEL", "envmodel")
    monkeypatch.setenv("OLLAMA_HOST", "http://envhost:1")
    llm = OllamaClient()
    assert llm.name == "ollama:envmodel"
    assert llm.host == "http://envhost:1"


def test_claude_without_key_names_the_variable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MetashiftError, match="ANTHROPIC_API_KEY is not set"):
        ClaudeClient()


def test_claude_forces_tool_use_and_validates_input():
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text="thinking"),
                    SimpleNamespace(type="tool_use", name="emit", input={"changes": []}),
                ]
            )

    client = SimpleNamespace(messages=FakeMessages())
    llm = ClaudeClient(model="claude-x", client=client)
    assert llm.name == "claude:claude-x"
    assert llm.complete_json("P", ExtractDraft) == ExtractDraft(changes=[])
    kw = calls[0]
    assert kw["model"] == "claude-x"
    assert kw["max_tokens"] == 16000
    assert kw["tool_choice"] == {"type": "tool", "name": "emit"}
    assert kw["tools"][0]["name"] == "emit"
    assert kw["tools"][0]["input_schema"] == ExtractDraft.model_json_schema()
    assert kw["messages"] == [{"role": "user", "content": "P"}]


def test_claude_truncated_output_fails_at_once_without_retry():
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                stop_reason="max_tokens",
                content=[SimpleNamespace(type="tool_use", name="emit", input={})],
            )

    llm = ClaudeClient(model="claude-x", client=SimpleNamespace(messages=FakeMessages()))
    with pytest.raises(MetashiftError, match=r"Claude output was cut off at max_tokens \(16000\)"):
        complete_with_retry(llm, "P", ExtractDraft)
    assert len(calls) == 1


def test_make_llm_selects_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert make_llm("ollama").name.startswith("ollama:")
    assert make_llm("claude").name.startswith("claude:")


def _capture_headers(seen: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        if status != 200:
            return httpx.Response(status, text="unauthorized")
        return httpx.Response(200, json={"message": {"content": '{"changes": []}'}})

    return httpx.MockTransport(handler)


def test_ollama_sends_api_key_as_bearer_token(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "secret-key")
    seen: dict = {}
    llm = OllamaClient(model="m", host="https://ollama.com", transport=_capture_headers(seen))
    llm.complete_json("P", ExtractDraft)
    assert seen["auth"] == "Bearer secret-key"


def test_ollama_sends_no_auth_header_without_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    seen: dict = {}
    llm = OllamaClient(model="m", host="http://x", transport=_capture_headers(seen))
    llm.complete_json("P", ExtractDraft)
    assert seen["auth"] is None


def test_ollama_rejected_key_names_the_variable_not_the_key(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "secret-key")
    llm = OllamaClient(model="m", host="https://ollama.com", transport=_capture_headers({}, 401))
    with pytest.raises(MetashiftError, match="OLLAMA_API_KEY") as err:
        llm.complete_json("P", ExtractDraft)
    assert "secret-key" not in str(err.value)


def test_ollama_unreachable_remote_host_does_not_suggest_ollama_serve():
    def boom(request):
        raise httpx.ConnectError("refused")

    llm = OllamaClient(model="m", host="https://ollama.com", transport=httpx.MockTransport(boom))
    with pytest.raises(MetashiftError) as err:
        llm.complete_json("P", ExtractDraft)
    assert "ollama serve" not in str(err.value)
    assert "https://ollama.com" in str(err.value)


def test_ollama_accepts_json_wrapped_in_a_code_fence():
    fenced = '```json\n{"changes": []}\n```'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": fenced}})

    llm = OllamaClient(model="m", host="http://x", transport=httpx.MockTransport(handler))
    assert llm.complete_json("P", ExtractDraft) == ExtractDraft(changes=[])


@pytest.mark.parametrize(
    "error", [httpx.ReadError("reset"), httpx.RemoteProtocolError("bad response")]
)
def test_ollama_transport_errors_become_metashift_errors(error):
    def boom(request):
        raise error

    llm = OllamaClient(model="m", host="https://ollama.com", transport=httpx.MockTransport(boom))
    with pytest.raises(MetashiftError, match="https://ollama.com"):
        llm.complete_json("P", ExtractDraft)


def test_ollama_host_without_scheme_is_a_clear_error():
    with pytest.raises(MetashiftError, match="OLLAMA_HOST must start with http:// or https://"):
        OllamaClient(model="m", host="0.0.0.0:11434")
