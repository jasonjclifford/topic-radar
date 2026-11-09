import json
import sys
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..text import strip_controls


def _terminal(line: str) -> None:
    print(line, file=sys.stdout, flush=True)


class RunFolder:
    """runs/<YYYY-MM-DD-HHMM>/ and what goes in it: notes.md (each line timed and echoed),
    details/events.jsonl, articles/ and details/."""

    def __init__(self, path: Path, clock: Callable[[], datetime], echo: Callable[[str], None]):
        self.path = path
        self.clock = clock
        self.echo = echo
        self.articles = path / "articles"
        self.details = path / "details"

    @classmethod
    def create(cls, root: Path, clock: Callable[[], datetime], echo: Callable[[str], None] = _terminal) -> "RunFolder":
        runs = Path(root) / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        base = clock().astimezone().strftime("%Y-%m-%d-%H%M")
        n = 1
        while True:
            path = runs / (base if n == 1 else f"{base}-{n}")
            try:
                path.mkdir()  # atomic: a clash raises instead of sharing the folder
                break
            except FileExistsError:
                n += 1
        folder = cls(path, clock, echo)
        folder.articles.mkdir()
        folder.details.mkdir()
        return folder

    def __fspath__(self) -> str:
        return str(self.path)

    def note(self, text: str) -> None:
        """Append plain words to notes.md, each line with its time, and echo each to the terminal."""
        stamp = self.clock().astimezone().strftime("%H:%M:%S")
        lines = [f"[{stamp}] {part}" for part in strip_controls(str(text)).splitlines() or [""]]
        with open(self.path / "notes.md", "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        for line in lines:
            self.echo(line)

    def record_exception(self, what: str) -> None:
        """Append the traceback of the exception being handled to details/error.txt, headed by what failed."""
        with open(self.details / "error.txt", "a", encoding="utf-8") as f:
            f.write(f"== {what} ==\n{traceback.format_exc()}\n")

    def event(self, name: str, /, **fields) -> None:
        row = {"time": self.clock().isoformat(), "event": name, **fields}
        with open(self.details / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
