import time

import httpx
from pydantic import BaseModel

from .answers import parse_answer
from .client import Answer

NOT_RUNNING = "Ollama isn't running. Start it with: ollama serve"


class PreflightError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _http(timeout: float) -> httpx.AsyncClient:
    # trust_env off: a proxy setting must never intercept calls to the local service
    return httpx.AsyncClient(timeout=timeout, trust_env=False)


class OllamaClient:
    def __init__(self, address: str, model: str, timeout_seconds: float, context: int):
        self.address = address.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.context = context

    async def call(self, step: str, system: str, user: str, schema: type[BaseModel]) -> Answer:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": schema.model_json_schema(),
            "think": False,
            "options": {"temperature": 0, "num_ctx": self.context},
        }
        started = time.monotonic()
        try:
            async with _http(self.timeout_seconds) as http:
                response = await http.post(f"{self.address}/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
            text = data["message"]["content"]
        except httpx.TimeoutException:
            return Answer(kind="timeout", seconds=time.monotonic() - started,
                          error=f"The model didn't answer within {self.timeout_seconds:g} seconds.")
        except httpx.ConnectError:
            return Answer(kind="unreachable", seconds=time.monotonic() - started, error=NOT_RUNNING)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return Answer(kind="http", seconds=time.monotonic() - started,
                          error="Ollama gave an answer that couldn't be read.")
        return parse_answer(schema, text, seconds=time.monotonic() - started,
                            prompt_tokens=data.get("prompt_eval_count", 0),
                            answer_tokens=data.get("eval_count", 0))

    async def preflight(self, model: str) -> None:
        try:
            async with _http(self.timeout_seconds) as http:
                response = await http.get(f"{self.address}/api/tags")
            response.raise_for_status()
            installed = response.json()["models"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise PreflightError(NOT_RUNNING) from None
        names = set()
        for m in installed:
            for key in ("name", "model"):
                if isinstance(m.get(key), str):
                    names.add(m[key])
        wanted = model if ":" in model else model + ":latest"
        if wanted not in names:
            raise PreflightError(f"The model {model} isn't installed. Install it with: ollama pull {model}")

    async def unload(self) -> None:
        try:
            async with _http(self.timeout_seconds) as http:
                await http.post(f"{self.address}/api/chat", json={"model": self.model, "keep_alive": 0})
        except httpx.HTTPError:
            pass  # best effort at the end of a run
