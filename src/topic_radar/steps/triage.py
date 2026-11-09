from ..model.answers import LenientModel
from ..model.prompts import clean, idea_numbered, known_ideas, load_prompt, numbered, profile
from ..state import Item, RunState

BATCH_SIZE = 10
SUMMARY_CHARS = 600
HEADROOM_TOKENS = 1500  # left free for the answer
CHARS_PER_TOKEN = 4  # the size estimate: no tokenizer, the prompt's characters divided by 4
KINDS = ("paper", "release", "rule", "guidance", "news", "opinion", "marketing", "other")


class Verdict(LenientModel):
    item: int
    relevance: int
    reason: str = ""
    kind: str = "other"
    repeats_idea: int | None = None
    adds_new: bool = False


class TriageAnswer(LenientModel):
    items: list[Verdict]


def _prompt(ctx, batch: list[Item], known: list[str]):
    rows = [f"[{n}] {clean(item.title)}\n    {clean(item.summary)[:SUMMARY_CHARS]}" for n, item in enumerate(batch, 1)]
    return load_prompt("triage", profile=profile(ctx.watch), known_ideas=numbered(known), items="\n".join(rows))


def _fits(ctx, prompt) -> bool:
    estimate = (len(prompt.system) + len(prompt.user)) / CHARS_PER_TOKEN
    return estimate <= ctx.settings.context - HEADROOM_TOKENS


def _batches(ctx, items: list[Item], known: list[str]) -> list[list[Item]]:
    """Batches of up to BATCH_SIZE; one whose estimated prompt exceeds the context less the
    headroom is halved until it fits (a single item is sent as it is)."""
    out: list[list[Item]] = []
    pending = [items[i:i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)][::-1]
    while pending:
        batch = pending.pop()
        if len(batch) > 1 and not _fits(ctx, _prompt(ctx, batch, known)):
            half = len(batch) // 2
            pending.extend([batch[half:], batch[:half]])
        else:
            out.append(batch)
    return out


def _judge(item: Item, v: Verdict, known: list[str]) -> None:
    item.relevance = max(0, min(3, v.relevance))
    item.kind = v.kind.strip().lower() if v.kind.strip().lower() in KINDS else "other"
    reason = v.reason.strip()
    idea = idea_numbered(known, v.repeats_idea)
    if idea and not v.adds_new:
        item.decision, item.reason, item.to_read = "filtered", f"repeats: {idea}", False
        return
    if idea:
        reason = f"adds to a known idea ({idea}): {reason}"
    item.reason = reason
    item.to_read = item.relevance >= 2
    item.decision = "quick hit" if item.to_read else "filtered"  # a read candidate stays a quick hit until read


async def triage(ctx, state: RunState) -> RunState:
    """Score every item with the model (AC12), then set decisions in code (AC13, AC44).

    An item scored 2-3 gets `to_read` and the decision `quick hit` (its fallback if never read);
    the read step reads the `to_read` stories in rank.read_order. Items without a score stay `not scored`."""
    known = known_ideas(ctx)
    for item in state.items:
        item.watch = item.watch or ctx.watch.slug
    batches = _batches(ctx, state.items, known)
    for number, batch in enumerate(batches, 1):
        ctx.run_folder.note(f"Triage: batch {number} of {len(batches)}")
        prompt = _prompt(ctx, batch, known)
        answer = await ctx.model.call("triage", prompt.system, prompt.user, TriageAnswer)
        if answer.parsed is None:
            for item in batch:
                item.reason = answer.error or "the model gave no answer"
            continue
        seen: set[int] = set()
        for v in answer.parsed.items:
            if 1 <= v.item <= len(batch) and v.item not in seen:
                seen.add(v.item)
                _judge(batch[v.item - 1], v, known)
        for n, item in enumerate(batch, 1):
            if n not in seen:
                item.reason = "the model gave no score for this item"
    return state
