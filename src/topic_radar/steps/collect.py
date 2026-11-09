from ..readers import feed
from ..state import FailedSource, RunState
from ..web import FetchError


async def collect(ctx, state: RunState) -> RunState:
    """Read each seed as a feed. A seed that fails is recorded with a plain reason; the rest go on."""
    for seed in ctx.watch.seeds:
        try:
            result = await feed.collect(ctx, seed)
        except FetchError as err:
            state.failed_sources.append(FailedSource(seed, err.reason))
            continue
        state.items.extend(result.items)
        state.feed_titles[seed] = result.title
    return state
