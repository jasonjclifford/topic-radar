import re
from pathlib import Path
from typing import NamedTuple

from ...text import strip_controls

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


def clean(text: str) -> str:
    """Text for one line of a prompt: delimiter tags neutralized, whitespace collapsed."""
    return re.sub(r"\s+", " ", neutralize(strip_controls(text))).strip()


def profile(watch) -> str:
    """The profile in prompts: the watch's interests, then what it is not interested in when it says."""
    text = clean(watch.interests)
    if watch.not_interested.strip():
        text += "\nNot interested in: " + clean(watch.not_interested)
    return text


def known_ideas(ctx) -> list[str]:
    """The watch's known ideas, cleaned. Ideas from `already_know` and the hand-added file are never dropped
    (AC43); the `known_ideas_max` cap is for learned ideas, which don't exist yet."""
    return [clean(idea) for idea in ctx.watch.known_ideas]


def numbered(ideas: list[str]) -> str:
    """The known ideas as a numbered list (1-based, as the model refers to them), or "(none)"."""
    return "\n".join(f"{n}. {idea}" for n, idea in enumerate(ideas, 1)) or "(none)"


def idea_numbered(ideas: list[str], number: int | None) -> str | None:
    """The idea a model's 1-based number points at in `numbered(ideas)`; None for no number or one out of range."""
    return ideas[number - 1] if number and 1 <= number <= len(ideas) else None
