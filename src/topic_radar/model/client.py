from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel


@dataclass
class Answer:
    text: str = ""
    parsed: Any = None
    error: str = ""
    kind: str = ""
    prompt_tokens: int = 0
    answer_tokens: int = 0
    seconds: float = 0.0


class ModelClient(Protocol):
    async def call(self, step: str, system: str, user: str, schema: type[BaseModel]) -> Answer: ...
