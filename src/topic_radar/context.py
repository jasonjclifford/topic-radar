from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .settings import Settings
from .watch import Watch


@dataclass
class RunContext:
    settings: Settings
    watch: Watch
    folder: Path
    clock: Callable[[], datetime]  # returns timezone-aware now
    http: Any  # httpx.AsyncClient
    model: Any  # ModelClient
    run_folder: Path
    allow_loopback: bool = False  # test-only; never read from settings
