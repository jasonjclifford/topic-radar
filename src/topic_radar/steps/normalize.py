from datetime import timedelta
import re
from urllib.parse import urlsplit

from ..state import Item, RunState
from ..web import FetchError, fetch, normalize_address

_VERSION_TITLE = re.compile(r"^v?(\d+(?:\.\d+)+)(?:([-+][0-9A-Za-z.]+))?(?::|$)")


def _version_key(title: str):
    m = _VERSION_TITLE.match(title)
    numbers = tuple(int(n) for n in m.group(1).split("."))
    suffix = m.group(2) or ""
    return numbers, 0 if suffix.startswith("-") else 1, suffix  # -rc1 sorts before the release itself


def _is_release_feed(source: str, items: list[Item]) -> bool:
    if len(items) < 2:
        return False
    if urlsplit(source).path.endswith("/releases.atom"):
        return True
    return all(_VERSION_TITLE.match(i.title) for i in items)


def _project(source: str, feed_title: str) -> str:
    segments = [s for s in urlsplit(source).path.split("/") if s]
    if len(segments) >= 2 and segments[-1] == "releases.atom":
        return segments[-2]
    return feed_title or urlsplit(source).netloc


def _combine(source: str, feed_title: str, items: list[Item]) -> Item:
    def order(item: Item):
        m = _VERSION_TITLE.match(item.title)
        return _version_key(item.title) if m else ((), 0, item.title)

    ordered = sorted(items, key=order)
    notes = "\n\n".join(f"{i.title}\n{i.notes or i.summary}".strip() for i in ordered)
    labels = []
    for i in ordered:
        m = _VERSION_TITLE.match(i.title)
        labels.append(m.group(0).rstrip(":") if m else "release")
    dates = [i.published for i in items if i.published]
    return Item(
        title=f"{_project(source, feed_title)}: {len(items)} releases since the last run",
        address=ordered[-1].address,  # a collected release address, never one built from the feed's own
        source=source,
        published=max(dates) if dates else None,
        summary="Releases: " + ", ".join(i.title for i in ordered),
        notes=notes,
        links=[i.address for i in ordered],
        link_labels=labels,
    )


async def resolve_address(ctx, address: str) -> str:
    """The address after redirects: HEAD first, GET if that fails, the given address if both fail."""
    for method in ("HEAD", "GET"):
        try:
            return (await fetch(ctx, address, method=method)).url
        except FetchError:
            continue
    return address


def _span(span: timedelta) -> str:
    """A lookback in whole days when it is one, else in hours: 14 days, 1 day, 12 hours."""
    seconds = int(span.total_seconds())
    if seconds % 86400 == 0:
        n, unit = seconds // 86400, "day"
    else:
        n, unit = seconds // 3600, "hour"
    return f"{n} {unit}" if n == 1 else f"{n} {unit}s"


async def normalize(ctx, state: RunState) -> RunState:
    cutoff = ctx.clock() - ctx.watch.first_run_lookback
    fresh = [i for i in state.items if i.published is None or i.published >= cutoff]

    by_source: dict[str, list[Item]] = {}
    for item in fresh:
        by_source.setdefault(item.source, []).append(item)
    combined = {s: _combine(s, state.feed_titles.get(s, ""), items)
                for s, items in by_source.items() if _is_release_feed(s, items)}

    out: list[Item] = []
    seen: set[str] = set()
    placed: set[str] = set()
    for item in fresh:
        if item.source in combined:
            if item.source in placed:
                continue
            placed.add(item.source)
            item = combined[item.source]
            item.address = normalize_address(item.address)
            item.links = [normalize_address(link) for link in item.links]
        else:
            item.address = normalize_address(await resolve_address(ctx, item.address))
        if item.address in seen:
            continue
        seen.add(item.address)
        out.append(item)
    state.items = out
    ctx.run_folder.note(f"Kept {len(out)} items from the last {_span(ctx.watch.first_run_lookback)} "
                        "after removing duplicates.")
    return state
