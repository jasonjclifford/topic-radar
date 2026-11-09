import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError, model_validator

from .client import Answer

_PLACEHOLDERS = {"", "n/a", "na", "none", "null", "-", "—"}
_FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)


class LenientModel(BaseModel):
    """Base for every step's answer model.

    A number sent as text ("3") is accepted by pydantic's lax mode; an empty placeholder
    ("", "n/a", null) is dropped before validation, so the field takes its default or,
    when it has none, the answer is a parse failure.
    """

    @model_validator(mode="before")
    @classmethod
    def _drop_placeholders(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items()
                if not (v is None or (isinstance(v, str) and v.strip().lower() in _PLACEHOLDERS))}


def parse_answer(schema: type[BaseModel], text: str, **timing) -> Answer:
    """Parse the model's raw text against the step's schema; never raises."""
    body = text.strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        data = json.loads(body)
        parsed = schema.model_validate(data)
    except (ValueError, ValidationError) as e:
        why = "the answer wasn't valid JSON" if isinstance(e, json.JSONDecodeError) else (
            "the answer didn't match the expected shape")
        return Answer(text=text, error=f"The model's answer couldn't be used: {why}.", kind="parse", **timing)
    return Answer(text=text, parsed=parsed, **timing)
