import re
from pathlib import Path
from typing import NamedTuple

_SPLIT = "=== user ==="
_TAGS = ("items", "chunk", "article")


class Prompt(NamedTuple):
    system: str
    user: str


def load_prompt(name: str, **values: str) -> Prompt:
    """Read prompts/<name>.md; the text before a `=== user ===` line is the system prompt, the rest the
    user prompt. `{key}` placeholders named in `values` are filled; any other brace is left alone."""
    text = (Path(__file__).parent / f"{name}.md").read_text(encoding="utf-8")
    text = re.sub(r"\{(\w+)\}", lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)
    system, _, user = text.partition(_SPLIT)
    return Prompt(system.strip(), user.strip())


def neutralize(text: str, tags: tuple[str, ...] = _TAGS) -> str:
    """Turn any literal opening or closing delimiter tag in web text into a square-bracket mark, so
    the text can't close the block it sits in."""
    pattern = re.compile(r"<\s*(/?)\s*(" + "|".join(map(re.escape, tags)) + r")\b[^>]*>", re.IGNORECASE)
    return pattern.sub(lambda m: f"[{m.group(1)}{m.group(2).lower()}]", text)
