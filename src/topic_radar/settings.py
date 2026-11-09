from dataclasses import dataclass, fields, replace
from pathlib import Path

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
    known = {f.name for f in fields(Settings)}
    return replace(Settings(), **{k: v for k, v in data.items() if k in known})
