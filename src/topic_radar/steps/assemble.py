import csv

from ..report.render import render_report, source_name
from ..state import RunState

COLUMNS = ["watch", "source", "title", "address", "published", "new_or_update", "relevance", "kind", "reason",
           "decision", "report_id", "article"]
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    """A spreadsheet reads a cell starting with = + - @ as a formula; a leading apostrophe makes it text."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def _report_ids(state: RunState) -> dict[int, str]:
    ids: dict[int, str] = {}
    if state.written:
        for w in state.written.top:
            ids.update({id(i): w.id for i in w.story.items})
        for q in state.written.quick:
            ids.update({id(i): q.id for i in q.story.items})
    return ids


def _rows(state: RunState):
    ids = _report_ids(state)
    for item in state.items:
        yield [item.watch, source_name(state, item), item.title, item.address, item.published.isoformat() if item.published else "",
               "new", "" if item.relevance is None else item.relevance, item.kind, item.reason, item.decision,
               ids.get(id(item), ""), item.article]


async def assemble(ctx, state: RunState) -> RunState:
    """Write items.csv and report.md, then the closing line of notes.md."""
    run = ctx.run_folder
    with open(run.path / "items.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows([safe_cell(c) for c in row] for row in _rows(state))
    (run.path / "report.md").write_text(render_report(ctx, state), encoding="utf-8")
    run.note("Done.")
    return state
