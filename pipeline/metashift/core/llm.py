import os
from collections.abc import Callable
from typing import Literal, Protocol, TypeVar

import anthropic
import httpx
from pydantic import BaseModel, ValidationError

from metashift.core.errors import MetashiftError

T = TypeVar("T", bound=BaseModel)

DEFAULT_OLLAMA_MODEL = "qwen3:14b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"
OLLAMA_TIMEOUT_S = 600
CLAUDE_MAX_TOKENS = 16000


class LLM(Protocol):
    name: str

    def complete_json(self, prompt: str, schema: type[T]) -> T:
        """Return a validated `schema` instance.

        Raises pydantic.ValidationError (or ValueError for non-JSON) on bad output.
        """
        ...


class FakeLLM:
    def __init__(self, responses: list[str], name: str = "fake") -> None:
        self.name = name
        self._responses = iter(responses)
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, schema: type[T]) -> T:
        self.prompts.append(prompt)
        return schema.model_validate_json(next(self._responses))


def _ollama_timeout() -> float:
    raw = os.environ.get("METASHIFT_OLLAMA_TIMEOUT")
    if not raw:
        return OLLAMA_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise MetashiftError(
            f"METASHIFT_OLLAMA_TIMEOUT must be a positive number of seconds, got '{raw}'"
        )
    return int(value) if value == int(value) else value


class OllamaClient:
    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float | None = None,
    ) -> None:
        self.timeout = timeout if timeout is not None else _ollama_timeout()
        self.model = model or os.environ.get("METASHIFT_OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")
        self.name = f"ollama:{self.model}"
        self._transport = transport
        api_key = os.environ.get("OLLAMA_API_KEY")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def _is_local(self) -> bool:
        return httpx.URL(self.host).host in {"localhost", "127.0.0.1", "::1"}

    def complete_json(self, prompt: str, schema: type[T]) -> T:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "format": schema.model_json_schema(),
            "options": {"temperature": 0, "num_ctx": 32768},
        }
        try:
            with httpx.Client(
                transport=self._transport, timeout=self.timeout, headers=self._headers
            ) as http:
                response = http.post(f"{self.host}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.ConnectError as err:
            hint = " Start it with: ollama serve" if self._is_local() else ""
            raise MetashiftError(f"Ollama is not reachable at {self.host}.{hint}") from err
        except httpx.HTTPStatusError as err:
            if err.response.status_code in (401, 403):
                raise MetashiftError(
                    f"Ollama at {self.host} rejected the request (HTTP "
                    f"{err.response.status_code}). Check OLLAMA_API_KEY"
                ) from err
            raise MetashiftError(
                f"Ollama returned HTTP {err.response.status_code}: {err.response.text[:200]}"
            ) from err
        except httpx.TimeoutException as err:
            raise MetashiftError(
                f"Ollama timed out after {self.timeout:g}s on {self.model}. "
                "Raise METASHIFT_OLLAMA_TIMEOUT or use a smaller model"
            ) from err
        content = response.json()["message"]["content"]
        return schema.model_validate_json(content)


class ClaudeClient:
    def __init__(
        self,
        model: str | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model or os.environ.get("METASHIFT_CLAUDE_MODEL") or DEFAULT_CLAUDE_MODEL
        self.name = f"claude:{self.model}"
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise MetashiftError("ANTHROPIC_API_KEY is not set")
            client = anthropic.Anthropic()
        self._client = client

    def complete_json(self, prompt: str, schema: type[T]) -> T:
        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=CLAUDE_MAX_TOKENS,
                tools=[
                    {
                        "name": "emit",
                        "description": "Return the result",
                        "input_schema": schema.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": "emit"},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as err:
            raise MetashiftError(f"Claude API error: {err}") from err
        if getattr(message, "stop_reason", None) == "max_tokens":
            raise MetashiftError(
                f"Claude output was cut off at max_tokens ({CLAUDE_MAX_TOKENS})"
            )
        for block in message.content:
            if block.type == "tool_use":
                return schema.model_validate(block.input)
        raise ValueError("Claude returned no tool_use block")


def make_llm(kind: Literal["ollama", "claude"]) -> LLM:
    if kind == "ollama":
        return OllamaClient()
    if kind == "claude":
        return ClaudeClient()
    raise MetashiftError(f"unknown LLM kind: {kind}")


def complete_with_retry(
    llm: LLM,
    prompt: str,
    schema: type[T],
    check: Callable[[T], list[str]] | None = None,
    max_retries: int = 2,
) -> tuple[T, int, list[str]]:
    """Ask for JSON, retry on bad JSON or rule problems.

    Once one schema-valid result exists, a later schema failure never raises: when the
    retries run out the last valid result is returned with its problems.
    """
    retries = 0
    current = prompt
    best: tuple[T, list[str]] | None = None
    while True:
        try:
            result = llm.complete_json(current, schema)
        except (ValidationError, ValueError) as err:
            if retries >= max_retries:
                if best is not None:
                    note = f"a retry returned invalid JSON, kept the last valid answer: {err}"
                    return best[0], retries, best[1] + [note.splitlines()[0]]
                raise MetashiftError(
                    f"{llm.name} returned invalid JSON after {max_retries} retries: {err}"
                ) from err
            retries += 1
            rules = ""
            if best is not None:
                rules = "\nThese rule problems of the last valid answer remain:\n" + "\n".join(
                    best[1]
                )
            current = (
                prompt
                + "\n\nYour previous answer was invalid:\n"
                + str(err)
                + rules
                + "\nReturn corrected JSON only."
            )
            continue
        problems = check(result) if check else []
        if not problems:
            return result, retries, []
        best = (result, problems)
        if retries >= max_retries:
            return result, retries, problems
        retries += 1
        current = (
            prompt
            + "\n\nYour previous answer was invalid:\n"
            + "\n".join(problems)
            + "\nReturn corrected JSON only."
        )
