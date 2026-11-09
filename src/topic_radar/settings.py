from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Callable, NamedTuple

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError


@dataclass(frozen=True)
class Settings:
    model: str = "auto"
    model_timeout_seconds: int = 300
    ollama: str = "http://127.0.0.1:11434"
    context: int = 8192
    read_cap: int = 25
    chunk_chars: int = 3000
    max_chunks: int = 4
    word_budget: int = 1200
    same_story_similarity: int = 90
    request_delay_seconds: float = 1
    timeout_seconds: float = 30
    known_ideas_max: int = 80


class _Type(NamedTuple):
    words: str
    accepts: Callable[[object], bool]


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_EXPECTED = {
    "str": _Type("text", lambda v: isinstance(v, str)),
    "int": _Type("a whole number", lambda v: isinstance(v, int) and not isinstance(v, bool)),
    "float": _Type("a number", _is_number),
}


class SettingsError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def load_settings(folder: Path) -> Settings:
    path = Path(folder) / "settings.yaml"
    if not path.exists():
        return Settings()
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    except MarkedYAMLError as e:
        mark = e.problem_mark or e.context_mark
        where = f"line {mark.line + 1}" if mark else "unknown line"
        raise SettingsError(f"{path.name}: not valid YAML, {where}: {e.problem}. Fix it or delete the file to use "
                            "the defaults.") from None
    except (OSError, UnicodeDecodeError) as e:
        raise SettingsError(f"{path.name}: can't be read ({e.__class__.__name__}). Fix it or delete the file to use "
                            "the defaults.") from None
    if not isinstance(data, dict):
        raise SettingsError(f"{path.name}: expected a list of fields such as model. Fix it or delete the file to "
                            "use the defaults.")
    known = {f.name: f for f in fields(Settings)}
    values = {k: v for k, v in data.items() if k in known}
    for name, value in values.items():
        expected = _EXPECTED[known[name].type if isinstance(known[name].type, str) else known[name].type.__name__]
        if not expected.accepts(value):
            raise SettingsError(f"{path.name}: {name} must be {expected.words}, not {value!r}. Fix it or delete the "
                                "line to use the default.")
    return replace(Settings(), **values)
