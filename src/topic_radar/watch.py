import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

_LOOKBACK = re.compile(r"^(\d+)\s*([hdw])$")
_UNITS = {"h": "hours", "d": "days", "w": "weeks"}
_LATER = "skipped until a later version"


@dataclass
class Watch:
    name: str
    slug: str  # the file name without .yaml
    interests: str
    not_interested: str = ""
    seeds: list[str] = field(default_factory=list)
    known_ideas: list[str] = field(default_factory=list)
    first_run_lookback: timedelta = timedelta(days=7)
    notes: list[str] = field(default_factory=list)


def _bullets(text: str) -> list[str]:
    return [line.strip()[2:].strip() for line in text.splitlines() if line.strip().startswith("- ")]


def load_watch(path: Path) -> Watch | str:
    """Return the Watch, or a plain message saying why the file is skipped."""
    path = Path(path)
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return f"{path.name}: not saved as UTF-8 text, so it can't be read. Skipped."
    except MarkedYAMLError as e:
        mark = e.problem_mark or e.context_mark
        where = f"line {mark.line + 1}" if mark else "unknown line"
        return f"{path.name}: not valid YAML, {where}: {e.problem}. Skipped."
    if not isinstance(data, dict):
        return f"{path.name}: expected a list of fields such as name and interests. Skipped."
    for required in ("name", "interests"):
        if not data.get(required):
            return f"{path.name}: the field '{required}' is missing. Skipped."

    lookback = timedelta(days=7)
    if "first_run_lookback" in data:
        m = _LOOKBACK.match(str(data["first_run_lookback"]).strip())
        if not m:
            return (f"{path.name}: first_run_lookback must look like 7d, 2w or 12h, "
                    f"not {data['first_run_lookback']!r}. Skipped.")
        lookback = timedelta(**{_UNITS[m.group(2)]: int(m.group(1))})

    notes = [f"{path.name}: {key} is accepted but {_LATER}."
             for key in ("searches", "mode") if data.get(key)]

    known = _bullets(str(data.get("already_know") or ""))
    known_file = path.parent.parent / "known" / f"{path.stem}.md"
    if known_file.exists():
        try:
            known += _bullets(known_file.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            return f"{known_file.name}: not saved as UTF-8 text, so it can't be read (it belongs to {path.name}). Skipped."

    return Watch(
        name=str(data["name"]),
        slug=path.stem,
        interests=str(data["interests"]),
        not_interested=str(data.get("not_interested") or ""),
        seeds=[str(s) for s in data.get("seeds") or []],
        known_ideas=known,
        first_run_lookback=lookback,
        notes=notes,
    )
