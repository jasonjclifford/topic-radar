from pydantic import BaseModel

from ..store.runfolder import RunFolder
from .client import Answer, ModelClient


class RecordingClient:
    """Wraps any ModelClient. One prompt/answer pair per call, numbered per step; a parse
    failure is retried once, and the pair holds the last attempt. A retried call also leaves the first
    attempt's raw answer as `<step>-<NNN>-answer-1.txt`."""

    def __init__(self, inner: ModelClient, run_folder: RunFolder):
        self.inner = inner
        self.run_folder = run_folder
        self._numbers: dict[str, int] = {}

    async def call(self, step: str, system: str, user: str, schema: type[BaseModel]) -> Answer:
        number = self._numbers[step] = self._numbers.get(step, 0) + 1
        attempts = 1
        first_text = None
        answer = await self.inner.call(step, system, user, schema)
        if answer.kind == "parse":
            attempts = 2
            first = answer
            first_text = first.text or first.error
            answer = await self.inner.call(step, system, user, schema)
            answer.seconds += first.seconds
            answer.prompt_tokens += first.prompt_tokens
            answer.answer_tokens += first.answer_tokens
        name = f"{step}-{number:03d}"
        details = self.run_folder.details
        (details / f"{name}-prompt.txt").write_text(f"=== system ===\n{system}\n\n=== user ===\n{user}\n", encoding="utf-8")
        if first_text is not None:
            (details / f"{name}-answer-1.txt").write_text(first_text, encoding="utf-8")
        (details / f"{name}-answer.txt").write_text(answer.text or answer.error, encoding="utf-8")
        self.run_folder.event("model_call", step=step, number=number, attempts=attempts,
                              seconds=round(answer.seconds, 3), prompt_tokens=answer.prompt_tokens,
                              answer_tokens=answer.answer_tokens, error=answer.error, kind=answer.kind)
        return answer
