from rapidfuzz.fuzz import token_sort_ratio

from ..state import RunState, Story


async def group(ctx, state: RunState) -> RunState:
    """Items whose titles are near-identical become one story listing every source (AC17)."""
    threshold = ctx.settings.same_story_similarity
    stories: list[Story] = []
    for item in state.items:
        for story in stories:
            if any(token_sort_ratio(item.title, other.title) >= threshold for other in story.items):
                story.items.append(item)
                break
        else:
            stories.append(Story([item]))
    state.stories = stories
    return state
