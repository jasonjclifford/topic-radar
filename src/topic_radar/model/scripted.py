import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from .answers import parse_answer
from .client import Answer


class UnmatchedPrompt(Exception):
    pass


@dataclass
class _Rule:
    step: str
    marker: str
    answers: list
    repeat: bool  # a single answer repeats; a list is a sequence that runs out
    used: int = 0

    def available(self) -> bool:
        return self.repeat or self.used < len(self.answers)


@dataclass
class ScriptedModel:
    """A model client for tests. Rules match on the step name and a marker (text that
    must appear in the system or user prompt, such as an item's title), never on the
    prompt's wording."""

    rules: list[_Rule] = field(default_factory=list)
    calls: list[tuple[str, str, str]] = field(default_factory=list)  # (step, system, user)

    def on(self, step: str, marker: str, answer) -> "ScriptedModel":
        """answer: a dict (sent as JSON), a str (sent as the raw text), an Answer (returned as is),
        or a list of those, given one per matching call in order (then no rule matches)."""
        sequence = isinstance(answer, list)
        self.rules.append(_Rule(step, marker, list(answer) if sequence else [answer], repeat=not sequence))
        return self

    async def call(self, step: str, system: str, user: str, schema: type[BaseModel]) -> Answer:
        self.calls.append((step, system, user))
        for rule in self.rules:
            if rule.step == step and rule.marker in system + "\n" + user and rule.available():
                value = rule.answers[0 if rule.repeat else rule.used]
                rule.used += 1
                if isinstance(value, Answer):
                    return value
                text = value if isinstance(value, str) else json.dumps(value)
                return parse_answer(schema, text)
        known = [r.marker for r in self.rules if r.step == step]
        raise UnmatchedPrompt(f"No scripted answer for step {step!r}; markers registered for it: {known}")
