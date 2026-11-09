import re

from .. import rank
from ..model.answers import LenientModel
from ..model.prompts import load_prompt, neutralize
from ..state import Article, Claim, QuickHit, RunState, Story, Written, WrittenStory
from .triage import _clean

QUICK_SUMMARY_CHARS = 200
SUMMARY_BULLETS_MAX = 5
_NUMBER = re.compile(r"\d[\d,.]*%?")
_TLDS = "com|org|net|io|dev|ai|co|app|edu|gov|info|xyz|me|us|uk|de|fr|eu|ru|cn|in|sh|tech|cloud|news|blog|site|online"
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_ADDRESS = re.compile(
    r"<?(?:[a-z][a-z0-9+.-]*://|www\.)\S+"  # a scheme or www address, to the next space
    rf"|\b(?:[a-z0-9-]+\.)+(?:{_TLDS})\b(?:/\S*)?",  # a bare domain, with any path
    re.IGNORECASE,
)


class WriteAnswer(LenientModel):
    headline: str
    what_happened: str
    why_it_matters: str
    read_if: str
    takeaway: str


class SummaryAnswer(LenientModel):
    bullets: list[str]


def strip_addresses(text: str) -> str:
    """Remove every web address from model-written text (AC22): links come only from item addresses.
    A markdown link keeps its words; a scheme or `www.` address, and a bare domain from a common
    top-level domain, is removed along with its path."""
    text = _MD_LINK.sub(r"\1", text)
    text = _ADDRESS.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _numbers(text: str) -> set[str]:
    return {m.group().rstrip(".,") for m in _NUMBER.finditer(text)} - {""}


def _passes_number_check(texts: list[str], claims: list[Claim]) -> bool:
    allowed = _numbers("\n".join(f"{c.text}\n{c.quote}" for c in claims))
    return all(_numbers(t) <= allowed for t in texts)


def _article(state: RunState, story: Story) -> Article | None:
    return next((a for a in state.articles if any(a.item is i for i in story.items)), None)


def _profile(ctx) -> str:
    profile = _clean(ctx.watch.interests)
    if ctx.watch.not_interested.strip():
        profile += "\nNot interested in: " + _clean(ctx.watch.not_interested)
    return profile


def _claims_block(claims: list[Claim]) -> str:
    return "\n".join(f'{n}. {_clean(c.text)}\n   quote: "{_clean(c.quote)}"' for n, c in enumerate(claims, 1))


def _fallback(sid: str, story: Story, art: Article | None, claims: list[Claim], reason: str) -> WrittenStory:
    return WrittenStory(id=sid, story=story, headline=_clean(story.items[0].title), claims=claims,
                        article=art.item.article if art else "", fallback=True, fallback_reason=reason)


async def _write_story(ctx, state: RunState, out: Written, number: int, story: Story) -> WrittenStory:
    sid = f"S{number}"
    art = _article(state, story)
    claims = [c for c in art.claims if c.kept] if art else []
    read_item = art.item if art else story.items[0]
    title = _clean(read_item.title)
    ctx.run_folder.note(f"Writing {sid}: {title}")
    prompt = load_prompt("write", profile=_profile(ctx), title=title, claims=_claims_block(claims))
    answer = await ctx.model.call("write", prompt.system, prompt.user, WriteAnswer)
    if answer.parsed is None:
        out.failed_writes += 1
        line = f"The write call for {sid} ({title}) failed, so it shows its headline and quoted claims."
        out.health.append(line)
        ctx.run_folder.note(line)
        return _fallback(sid, story, art, claims, "write call failed")
    a = answer.parsed
    fields = {name: strip_addresses(getattr(a, name)) for name in WriteAnswer.model_fields}
    if not _passes_number_check(list(fields.values()), claims):
        out.number_check_failures += 1
        line = f"The number check failed for {sid} ({title}), so it shows its headline and quoted claims."
        out.health.append(line)
        ctx.run_folder.note(line)
        return _fallback(sid, story, art, claims, "number check")
    return WrittenStory(id=sid, story=story, headline=fields["headline"] or title, what_happened=fields["what_happened"],
                        why_it_matters=fields["why_it_matters"], read_if=fields["read_if"],
                        takeaway=fields["takeaway"], claims=claims, article=read_item.article)


def _story_text(w: WrittenStory) -> str:
    return "\n".join(t for t in (w.headline, w.what_happened, w.why_it_matters, w.takeaway) if t)


async def _summarize(ctx, out: Written) -> None:
    texts = [_story_text(w) for w in out.top if not w.fallback]
    if not texts:
        return
    block = neutralize("\n\n".join(texts), tags=("stories", "article", "items", "chunk"))
    prompt = load_prompt("summary", stories=block)
    answer = await ctx.model.call("summary", prompt.system, prompt.user, SummaryAnswer)
    bullets = []
    if answer.parsed is not None:
        bullets = [b for b in (strip_addresses(b) for b in answer.parsed.bullets) if b][:SUMMARY_BULLETS_MAX]
    if not bullets:
        out.summary_failed = True
        line = "The \"In 30 seconds\" summary could not be written, so that section is left out."
        out.health.append(line)
        ctx.run_folder.note(line)
        return
    out.summary = bullets


def _quick_hit(number: int, story: Story) -> QuickHit:
    item = story.items[0]
    summary = _clean(item.summary)
    if len(summary) > QUICK_SUMMARY_CHARS:
        summary = summary[:QUICK_SUMMARY_CHARS].rstrip() + "…"
    return QuickHit(id=f"Q{number}", story=story, title=_clean(item.title), summary=summary,
                    address=item.address, watch=story.watch)


async def write(ctx, state: RunState) -> RunState:
    """Choose the picks, then write each top story from its kept claims and the profile, check its numbers,
    write the "In 30 seconds" bullets from the written stories, and build the quick-hit lines from the feed
    (AC18-AC20, AC22, AC50). Sets `state.written`; the report is rendered from it.

    A failed story call or a story with a number its claims don't contain is shown as its headline (the
    feed title) and quoted claims. Web addresses are stripped from everything the model wrote. A failed
    summary leaves the section out and adds a health line."""
    picks = rank.picks(state.stories)
    out = Written()
    for number, story in enumerate(picks.top, 1):
        out.top.append(await _write_story(ctx, state, out, number, story))
    out.quick = [_quick_hit(n, s) for n, s in enumerate(picks.quick, 1)]
    await _summarize(ctx, out)
    state.written = out
    return state
