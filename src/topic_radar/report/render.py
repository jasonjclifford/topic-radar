import re
from urllib.parse import urlsplit

from ..state import Item, QuickHit, RunState, WrittenStory

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>@]|(?<=:)(?=//)|(?<=www)(?=\.))")


def escape(text: str) -> str:
    """Untrusted text as one line of plain Markdown: nothing in it can start a link, a heading or a tag."""
    return _MD_SPECIAL.sub(lambda m: "\\" + m.group(), re.sub(r"\s+", " ", text or "")).strip()


def is_web_address(address: str) -> bool:
    parts = urlsplit(address)
    return parts.scheme in ("http", "https") and bool(parts.netloc) and not re.search(r"[\s<>]", address)


def link(text: str, address: str) -> str:
    """A Markdown link when the address is http or https; the escaped words alone otherwise."""
    return f"[{escape(text)}](<{address}>)" if is_web_address(address) else escape(text)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def source_name(state: RunState, item: Item) -> str:
    """The feed's own title for the item's source, else the source's host, else the source as given."""
    return state.feed_titles.get(item.source) or urlsplit(item.source).netloc or item.source


def _banner(state: RunState, seeds: int) -> str:
    parts = []
    if state.failed_sources:
        parts.append(f"{len(state.failed_sources)} of {_count(seeds, 'source')} couldn't be read")
    unscored = sum(i.decision == "not scored" for i in state.items)
    failed = sum(i.decision == "failed" for i in state.items)
    if unscored:
        parts.append(f"{_count(unscored, 'item')} weren't scored" if unscored > 1 else "1 item wasn't scored")
    if failed:
        parts.append(f"{_count(failed, 'item')} couldn't be read" if failed > 1 else "1 item couldn't be read")
    if not parts:
        return ""
    return f"> **This report is missing things.** {' and '.join(parts)}, so what follows may be incomplete. See Run health.\n"


def _releases(item: Item) -> str:
    """A combined release's own release addresses as links, labelled by version; web addresses only."""
    labels = item.link_labels + ["release"] * (len(item.links) - len(item.link_labels))
    parts = [link(label, address) for label, address in zip(labels, item.links) if is_web_address(address)]
    return "Releases: " + " · ".join(parts) if parts else ""


def _top_story(w: WrittenStory, state: RunState) -> list[str]:
    lines = [f"### {w.id}. {escape(w.headline)}", ""]
    if w.fallback:
        lines += ["The written summary of this story was left out, so these are the claims found in the article, each with its quote:", ""]
        for c in w.claims:
            lines += [f"- {escape(c.text)}", f"  > \"{escape(c.quote)}\""]
        lines.append("")
    else:
        for label, value in (("What happened", w.what_happened), ("Why it matters", w.why_it_matters),
                             ("Read it if", w.read_if), ("Takeaway", w.takeaway)):
            if value:
                lines.append(f"**{label}:** {escape(value)}  ")
        lines.append("")
    sources = [link(source_name(state, i), i.address) if is_web_address(i.address)
               else f"{escape(source_name(state, i))} (no link: the address isn't a web address)"
               for i in w.story.items]
    lines.append("Sources: " + " · ".join(sources) + "  ")
    releases = [r for r in (_releases(i) for i in w.story.items) if r]
    if releases:
        lines.append(" · ".join(releases) + "  ")
    if w.article:
        lines.append(f"Article: `{w.article}`")
    lines.append("")
    return lines


def _quick_hit(q: QuickHit) -> str:
    head = link(q.title, q.address)
    line = f"- **{q.id}** {head}" + (f": {escape(q.summary)}" if q.summary else "")
    releases = [r for r in (_releases(i) for i in q.story.items) if r]
    return line + (" (" + " · ".join(releases) + ")" if releases else "")


def filter_reason(item: Item) -> str:
    if item.reason.startswith("repeats:"):
        return "repeated an idea you already know"
    if item.reason == "not in the top picks":
        return "not in the top picks"
    if item.reason == "over word budget":
        return "over the word budget"
    if item.relevance == 0:
        return "not related to your interests (scored 0)"
    if item.relevance == 1:
        return "barely related to your interests (scored 1)"
    return escape(item.reason) or "no reason recorded"


def _filtered_counts(state: RunState) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for item in state.items:
        if item.decision in ("filtered", "repeat"):
            reason = filter_reason(item)
            counts[reason] = counts.get(reason, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _health(ctx, state: RunState) -> list[str]:
    lines = []
    for f in state.failed_sources:
        line = f"Couldn't read `{f.source.replace('`', chr(39))}`: {escape(f.reason)}."
        if "remove it from" not in f.reason:  # a reason that already says what to do needs no second remedy
            line += " Check the address, or remove it from the watch's seeds."
        lines.append(line)
    unscored = sum(i.decision == "not scored" for i in state.items)
    failed = sum(i.decision == "failed" for i in state.items)
    if unscored:
        lines.append(f"{_count(unscored, 'item')} were not scored because the model gave no usable answer; "
                     "items.csv says why for each." if unscored > 1 else
                     "1 item was not scored because the model gave no usable answer; items.csv says why.")
    if failed:
        lines.append(f"{_count(failed, 'item')} failed while being read; items.csv says why for each."
                     if failed > 1 else "1 item failed while being read; items.csv says why.")
    dropped = sum(a.dropped for a in state.articles)
    if dropped:
        lines.append(f"{_count(dropped, 'claim')} were dropped because their quote wasn't found in the article."
                     if dropped > 1 else "1 claim was dropped because its quote wasn't found in the article.")
    if state.written:
        lines += [escape(h) for h in state.written.health]
    unread = sum(i.unread_over_cap for i in state.items)
    lines.append(f"Read cap: {ctx.settings.read_cap}. {_count(len(state.articles), 'article')} "
                 f"{'was' if len(state.articles) == 1 else 'were'} read; "
                 f"{_count(unread, 'scored item')} {'was' if unread == 1 else 'were'} not read.")
    return lines


def _no_top_stories(state: RunState) -> str:
    """Why there is no top story, from the cause: nothing read, every read item a repeat, or no claim kept."""
    read = len(state.articles)
    if read == 0:
        if any(i.decision == "failed" for i in state.items):
            return "No article was read: the items that scored high enough couldn't be read. See Run health."
        if state.items and all(i.decision == "not scored" for i in state.items):
            return "No article was read because the items weren't scored. See Run health."
        return "No article was read because no item scored high enough to read."
    repeats = sum(a.item.decision == "filtered" and a.item.reason.startswith("repeats") for a in state.articles)
    if repeats == read:
        return f"{_count(read, 'article')} {'was' if read == 1 else 'were'} read; all repeated ideas you already know."
    if repeats:
        rest = read - repeats
        return (f"{_count(read, 'article')} {'was' if read == 1 else 'were'} read: {repeats} repeated "
                f"{'an idea' if repeats == 1 else 'ideas'} you already know and {rest} had no claim backed by a quote.")
    return f"{_count(read, 'item')} {'was' if read == 1 else 'were'} read; none had a claim backed by a quote."


def render_report(ctx, state: RunState) -> str:
    """The report as Markdown. Links come only from item addresses and only when they are http or https;
    everything from the web or the model is escaped so it cannot add a link, a heading or a tag."""
    now = ctx.clock().astimezone()
    written = state.written
    out = [f"# {escape(ctx.watch.name)}, {now.date().isoformat()}", "",
           f"_Written by topic-radar at {now.strftime('%H:%M')}. Safe to edit or delete; the run's other files show how it was made._", ""]
    banner = _banner(state, max(len(ctx.watch.seeds), len(state.failed_sources)))
    if banner:
        out += [banner]
    if written and written.summary:
        out += ["## In 30 seconds", ""] + [f"- {escape(b)}" for b in written.summary] + [""]
    out += ["## Top stories", ""]
    if written and written.top:
        for w in written.top:
            out += _top_story(w, state)
    else:
        out += [_no_top_stories(state), ""]
    out += ["## Quick hits", ""]
    if written and written.quick:
        names = {ctx.watch.slug: ctx.watch.name}
        for watch in dict.fromkeys(q.watch for q in written.quick):
            out += [f"**{escape(names.get(watch, watch))}**", ""]
            out += [_quick_hit(q) for q in written.quick if q.watch == watch] + [""]
    else:
        out += ["None.", ""]
    out += ["## Filtered out", ""]
    counts = _filtered_counts(state)
    out += [f"- {n} {reason}" for reason, n in counts] or ["Nothing was filtered out."]
    out += ["", "Every item and what was decided about it is in `items.csv`, in the same folder as this report.", "",
            "## Run health", ""]
    out += [f"- {line}" for line in _health(ctx, state)]
    return "\n".join(out) + "\n"
