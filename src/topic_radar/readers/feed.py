import re
from calendar import timegm
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

import feedparser

from ..state import Item
from ..text import strip_controls
from ..web import FetchError, fetch, is_parseable_address
from .base import CollectResult

_BLOCKS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote",
           "tr", "table", "hr"}
MAX_ENTRIES = 200  # per feed; the newest by date
_OLDEST = datetime.min.replace(tzinfo=timezone.utc)
_PAGE_ERROR = ("this address is a web page, not a feed: replace it with the feed's address "
               "or remove it from seeds")


class _Plain(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def plain_text(markup: str) -> str:
    """HTML to plain text: tags and link targets dropped, link words kept, paragraphs on their own lines."""
    parser = _Plain()
    parser.feed(markup or "")
    parser.close()
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(parser.parts).split("\n"))
    return strip_controls("\n".join(line for line in lines if line))


def _published(entry) -> datetime | None:
    stamp = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(timegm(stamp), tz=timezone.utc) if stamp else None


async def collect(ctx, source: str) -> CollectResult:
    """Fetch a feed and parse it into items. Raises FetchError with a plain reason."""
    got = await fetch(ctx, source)
    parsed = feedparser.parse(got.body)
    if not parsed.version:
        head = got.text[:1024].lower()
        if got.content_type == "text/html" or "<html" in head or "<!doctype html" in head:
            raise FetchError(_PAGE_ERROR)
        raise FetchError("this address could not be read as a feed")
    items = []
    notes = []
    entries = parsed.entries
    if len(entries) > MAX_ENTRIES:
        entries = sorted(entries, key=lambda e: _published(e) or _OLDEST, reverse=True)[:MAX_ENTRIES]
        notes.append(f"{source} has {len(parsed.entries)} entries; only the {MAX_ENTRIES} newest are used.")
    for entry in entries:
        link = entry.get("link")
        if not link:
            continue
        try:
            address = strip_controls(urljoin(got.url, link))
        except ValueError:
            continue
        if not is_parseable_address(address):  # an entry whose link isn't an address is left out, like one with no link
            continue
        content = plain_text(entry.content[0].value) if entry.get("content") else ""
        items.append(Item(
            title=plain_text(entry.get("title", "")) or address,
            address=address,
            source=source,
            published=_published(entry),
            summary=plain_text(entry.get("summary", "")),
            notes=content,
        ))
    return CollectResult(items=items, title=plain_text(parsed.feed.get("title", "")), notes=notes)
