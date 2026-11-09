import re

from .. import rank
from ..model.answers import LenientModel
from ..model.prompts import clean, idea_numbered, known_ideas, load_prompt, neutralize, numbered, profile
from ..state import Article, Claim, Item, RunState, Story
from ..text import chunk_text, extract_text, quote_found, strip_controls
from ..web import FetchError, fetch

CLAIMS_PER_CHUNK = 12
NAME_MAX = 80
UNEXPECTED = "something unexpected went wrong while reading it (details/error.txt has the technical details)"


class ClaimIn(LenientModel):
    claim: str
    quote: str = ""


class ReadAnswer(LenientModel):
    claims: list[ClaimIn] = []
    repeats_idea: int | None = None
    adds_new: bool = False


class ReadFailed(Exception):
    """The article could not be read; the message is a plain sentence for the report."""


def _mark(story: Story, decision: str, reason: str, *, unread: bool = False) -> None:
    for item in story.items:
        if item.to_read:
            item.decision, item.reason = decision, reason
            item.unread_over_cap = unread


async def _page_text(ctx, item: Item) -> str:
    if item.links and item.notes:  # a combined release: the feed's own notes, no fetch
        return item.notes
    try:
        page = await fetch(ctx, item.address)
    except FetchError as e:
        raise ReadFailed(e.reason) from None
    text = strip_controls(page.text if page.content_type == "text/plain" else extract_text(page.text)).strip()
    if not text:
        raise ReadFailed("no readable text was found on the page")
    return text


def _prompt(ctx, item: Item, known: list[str], chunk: str):
    return load_prompt("read", profile=profile(ctx.watch), known_ideas=numbered(known), title=clean(item.title),
                       chunk=neutralize(chunk).strip())


def _file_name(number: int, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "article"
    stem = f"{number}-"
    room = NAME_MAX - len(stem) - len(".md")
    return f"{stem}{slug[:room].strip('-') or 'article'}.md"


def _article_markdown(art: Article) -> str:
    item = art.item
    title = re.sub(r"\s+", " ", item.title).strip()
    date = item.published.date().isoformat() if item.published else "unknown"
    kept = [c for c in art.claims if c.kept]
    lines = [f"# {title}", "", f"- Address: {item.address}", f"- Source: {item.source}", f"- Date: {date}",
             f"- Dropped claims: {art.dropped}", "", "## Claims", ""]
    lines += [f'- {c.text}\n  > "{c.quote}"' for c in kept] or ["(none kept)"]
    return "\n".join(lines) + f"\n\n## Text\n\n{art.text}\n"


async def _read_item(ctx, item: Item, known: list[str]) -> tuple[Article, str | None, bool]:
    """Fetch, extract, chunk and ask the model about each chunk. Returns the article, the known idea it
    repeats and whether any chunk said it adds something new. The article repeats an idea only when every
    chunk that said anything (claims or a repeat) names a repeated idea; one chunk with claims and no
    repeat means the article as a whole is not a repeat."""
    text = await _page_text(ctx, item)
    art = Article(item=item, text=text)
    idea: str | None = None
    all_repeat = True
    adds_new = False
    for chunk in chunk_text(text, ctx.settings.chunk_chars, ctx.settings.max_chunks):
        prompt = _prompt(ctx, item, known, chunk)
        answer = await ctx.model.call("read", prompt.system, prompt.user, ReadAnswer)
        if answer.parsed is None:
            raise ReadFailed(answer.error or "the model gave no answer")
        for c in answer.parsed.claims[:CLAIMS_PER_CHUNK]:
            if not c.claim.strip():
                continue
            kept = quote_found(c.quote, chunk)
            art.claims.append(Claim(text=c.claim.strip(), quote=c.quote.strip(), kept=kept))
            art.dropped += not kept
        repeated = idea_numbered(known, answer.parsed.repeats_idea)
        if repeated is None:
            all_repeat = all_repeat and not answer.parsed.claims
        elif idea is None:
            idea = repeated
        adds_new = adds_new or answer.parsed.adds_new
    return art, idea if all_repeat else None, adds_new


async def read(ctx, state: RunState) -> RunState:
    """Read the stories marked `to_read` in rank.read_order, up to `read_cap` (AC13-AC16, AC44).

    One item is read per story: its first item marked `to_read`. An over-cap story is a quick-hit
    candidate with the reason "over read cap". Each page is chunked; the model lists claims with quotes
    per chunk; a claim is kept only when its quote is found in that chunk. The read item is `eligible`
    with at least one kept claim, `filtered` when the model says it repeats a known idea and adds nothing,
    and `failed` when the page or the model failed. Every to_read item of the story takes a failure or
    filter decision; an article is saved for each story that was read."""
    known = known_ideas(ctx)
    ordered = rank.read_order([s for s in state.stories if s.to_read])
    cap = ctx.settings.read_cap
    for story in ordered[cap:]:
        _mark(story, "quick hit", "over read cap", unread=True)
    todo = ordered[:cap]
    for number, story in enumerate(todo, 1):
        item = next(i for i in story.items if i.to_read)
        ctx.run_folder.note(f"Reading {number} of {len(todo)}: {item.title}")
        try:
            art, idea, adds_new = await _read_item(ctx, item, known)
        except ReadFailed as e:
            _mark(story, "failed", str(e))
            continue
        except Exception:
            ctx.run_folder.record_exception(f"reading {item.title}")
            _mark(story, "failed", UNEXPECTED)
            ctx.run_folder.note(f"Couldn't read {item.title}: {UNEXPECTED}.")
            continue
        art.path = f"articles/{_file_name(number, item.title)}"
        (ctx.run_folder.path / art.path).write_text(_article_markdown(art), encoding="utf-8")
        item.article = art.path
        state.articles.append(art)
        if idea is not None and not adds_new:
            _mark(story, "filtered", f"repeats: {idea}")
        else:
            item.eligible = any(c.kept for c in art.claims)
    return state
