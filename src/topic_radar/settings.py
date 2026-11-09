from dataclasses import dataclass, fields, replace
from pathlib import Path

from ruamel.yaml import YAML


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


def load_settings(folder: Path) -> Settings:
    path = Path(folder) / "settings.yaml"
    if not path.exists():
        return Settings()
    data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    known = {f.name for f in fields(Settings)}
    return replace(Settings(), **{k: v for k, v in data.items() if k in known})
