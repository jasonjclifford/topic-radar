from ..readers import feed
from ..state import FailedSource, RunState
from ..web import FetchError


async def collect(ctx, state: RunState) -> RunState:
    """Read each seed as a feed. A seed that fails is recorded with a plain reason; the rest go on."""
    seeds = ctx.watch.seeds
    for number, seed in enumerate(seeds, 1):
        ctx.run_folder.note(f"Reading feed {number} of {len(seeds)}: {seed}")
        try:
            result = await feed.collect(ctx, seed)
        except FetchError as err:
            state.failed_sources.append(FailedSource(seed, err.reason))
            ctx.run_folder.note(f"Couldn't read {seed}: {err.reason}.")
            continue
        state.items.extend(result.items)
        state.feed_titles[seed] = result.title
    read = len(state.feed_titles)
    ctx.run_folder.note(f"Found {len(state.items)} items in {read} {'feed' if read == 1 else 'feeds'}.")
    return state
