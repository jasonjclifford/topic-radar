from datetime import datetime, timezone

from rapidfuzz.fuzz import token_sort_ratio

from topic_radar.state import Item, RunState
from topic_radar.steps.group import group

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
A = "Anthropic ships Claude Agent SDK update"
SAME = "Anthropic ships Claude Agent SDK update today"
OTHER = "Anthropic ships new Claude Agent SDK release notes"


def item(title, source):
    return Item(title=title, address=f"https://{source}/{abs(hash(title))}", source=f"https://{source}/feed", published=NOW)


def test_the_fixture_titles_really_sit_at_about_92_and_70():
    assert 91 <= token_sort_ratio(A, SAME) < 95
    assert 65 <= token_sort_ratio(A, OTHER) < 75


async def test_titles_at_92_group_into_one_story_listing_both_sources(make_ctx):
    a, b = item(A, "one.test"), item(SAME, "two.test")
    state = await group(make_ctx(), RunState(items=[a, b]))
    assert len(state.stories) == 1
    assert state.stories[0].items == [a, b]
    assert state.stories[0].sources == ["https://one.test/feed", "https://two.test/feed"]


async def test_titles_at_70_stay_separate_stories(make_ctx):
    a, b = item(A, "one.test"), item(OTHER, "two.test")
    state = await group(make_ctx(), RunState(items=[a, b]))
    assert [s.items for s in state.stories] == [[a], [b]]


async def test_the_threshold_is_the_setting_and_is_inclusive(make_ctx):
    a, b = item(A, "one.test"), item(SAME, "two.test")
    score = token_sort_ratio(A, SAME)
    at = await group(make_ctx(same_story_similarity=int(score)), RunState(items=[a, b]))
    above = await group(make_ctx(same_story_similarity=int(score) + 1), RunState(items=[a, b]))
    assert len(at.stories) == 1
    assert len(above.stories) == 2


async def test_a_score_exactly_at_the_threshold_groups(make_ctx):
    a, b = item(A, "one.test"), item(A, "two.test")
    assert token_sort_ratio(A, A) == 100
    state = await group(make_ctx(same_story_similarity=100), RunState(items=[a, b]))
    assert len(state.stories) == 1


async def test_word_order_does_not_matter(make_ctx):
    a, b = item("Claude Agent SDK update Anthropic ships", "one.test"), item(A, "two.test")
    state = await group(make_ctx(), RunState(items=[a, b]))
    assert len(state.stories) == 1


async def test_every_item_lands_in_exactly_one_story(make_ctx):
    items = [item(A, "one.test"), item(SAME, "two.test"), item(OTHER, "three.test"), item("Unrelated paper on retrieval", "four.test")]
    state = await group(make_ctx(), RunState(items=items))
    assert sorted(id(i) for s in state.stories for i in s.items) == sorted(id(i) for i in items)
