import asyncio
import traceback
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .context import RunContext
from .model.ollama import OllamaClient, PreflightError
from .model.recording import RecordingClient
from .settings import SettingsError, load_settings
from .state import RunState
from .steps.assemble import assemble
from .steps.collect import collect
from .steps.group import group
from .steps.normalize import normalize
from .steps.read import read
from .steps.triage import triage
from .steps.write import write
from .store.runfolder import RunFolder
from .watch import load_watch

STEPS = [collect, normalize, triage, group, read, write, assemble]
AUTO_MODEL = "gemma4:e4b-mlx"  # what `model: auto` means until the resolver exists
INTERRUPTED = 130


@dataclass
class Outcome:
    code: int  # 0 a report was written, 1 an unexpected error, 2 the run could not start, 130 stopped with Ctrl-C
    report: Path | None = None
    message: str = ""  # for code 2: what to tell the user; for code 1: where the details went, if it wasn't in the run folder


def _find_watch(folder: Path, name: str) -> Path | str:
    watches = folder / "watches"
    path = watches / f"{name}.yaml"
    if path.is_file() and path.resolve().parent == watches.resolve():
        return path
    found = sorted(p.stem for p in watches.glob("*.yaml")) if watches.is_dir() else []
    listing = f"Watches found there: {', '.join(found)}." if found else "There are no watch files there yet."
    return f"There is no watch called {name} in {watches}. {listing}"


async def run_watch(watch: str, folder: Path, *, read_cap: int | None = None, model: str | None = None,
                    model_client=None, allow_loopback: bool = False,
                    clock: Callable[[], datetime] | None = None) -> Outcome:
    """Run one watch (see `_run_watch`); anything unexpected before or around the pipeline ends as code 1 with
    a plain message, never a traceback on the terminal."""
    held: dict = {}
    try:
        return await _run_watch(watch, folder, held, read_cap=read_cap, model=model, model_client=model_client,
                                allow_loopback=allow_loopback, clock=clock)
    except (KeyboardInterrupt, asyncio.CancelledError):
        raise
    except Exception:
        details = traceback.format_exc()
        run_folder = held.get("run_folder")
        if run_folder:
            (run_folder.details / "error.txt").write_text(details, encoding="utf-8")
            where = "The technical details are in details/error.txt in the run folder."
        else:
            where = "No run folder was created, so nothing was saved."
        if held.get("http"):
            await held["http"].aclose()
        if held.get("raw"):
            try:
                await held["raw"].unload()
            except Exception:
                pass
        return Outcome(1, message=f"The run stopped because something unexpected went wrong, so there is no report. {where}")


async def _run_watch(watch: str, folder: Path, held: dict, *, read_cap: int | None, model: str | None,
                     model_client, allow_loopback: bool, clock: Callable[[], datetime] | None) -> Outcome:
    """Run one watch from the Topic Radar `folder` and return how it ended.

    `model_client` (anything with call, preflight and unload) and `allow_loopback` exist so tests can
    run the whole pipeline against a scripted model and the local test feed server; the command line
    never sets them. Nothing is created in `folder` until the watch has loaded and the preflight passed."""
    folder = Path(folder)
    clock = clock or (lambda: datetime.now(timezone.utc))
    try:
        settings = load_settings(folder)
    except SettingsError as e:
        return Outcome(2, message=e.message)
    found = _find_watch(folder, watch)
    if isinstance(found, str):
        return Outcome(2, message=found)
    loaded = load_watch(found)
    if isinstance(loaded, str):
        return Outcome(2, message=loaded)
    model_name = model or settings.model
    if model_name == "auto":
        model_name = AUTO_MODEL
    settings = replace(settings, model=model_name, **({"read_cap": read_cap} if read_cap is not None else {}))
    raw = held["raw"] = model_client or OllamaClient(settings.ollama, model_name, settings.model_timeout_seconds,
                                                      settings.context)
    try:
        await raw.preflight(model_name)
    except PreflightError as e:
        return Outcome(2, message=e.message)

    # trust_env off: a proxy setting must not route around the fetch guard's address check
    run_folder = held["run_folder"] = RunFolder.create(folder, clock)
    http = held["http"] = httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=settings.timeout_seconds)
    ctx = RunContext(settings=settings, watch=loaded, folder=folder, clock=clock, http=http,
                     model=RecordingClient(raw, run_folder), run_folder=run_folder, allow_loopback=allow_loopback)
    outcome = Outcome(0, report=run_folder.path / "report.md")
    try:
        run_folder.note("Starting. You can stop at any time with Ctrl-C; it is safe, and nothing already saved is lost.")
        for line in loaded.notes:
            run_folder.note(line)
        state = RunState()
        for step in STEPS:
            state = await step(ctx, state)
    except (KeyboardInterrupt, asyncio.CancelledError):
        run_folder.note("Stopped because you pressed Ctrl-C. No report was written.")
        outcome = Outcome(INTERRUPTED)
    except Exception:
        (run_folder.details / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        run_folder.note("The run stopped because something unexpected went wrong, so there is no report. "
                        "The technical details are in details/error.txt.")
        outcome = Outcome(1)
    finally:
        await http.aclose()
        await raw.unload()
    return outcome
