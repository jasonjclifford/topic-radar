from datetime import datetime, timedelta, timezone

from topic_radar.rank import picks, read_order
from topic_radar.state import Item, Story

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def story(name, relevance=2, sources=1, age_days=0, watch="w", eligible=False, decision="quick hit"):
    items = [Item(title=name, address=f"https://e.test/{name}-{n}", source=f"https://s{n}.test/feed",
                  published=NOW - timedelta(days=age_days), relevance=relevance, to_read=True,
                  eligible=eligible, watch=watch, decision=decision) for n in range(sources)]
    return Story(items)


def names(stories):
    return [s.items[0].title for s in stories]


def test_read_order_is_relevance_then_sources_then_date():
    stories = [
        story("old-two-src", relevance=3, sources=2, age_days=5),
        story("new-two-src", relevance=3, sources=2, age_days=1),
        story("one-src", relevance=3, sources=1, age_days=0),
        story("rel2-many", relevance=2, sources=4, age_days=0),
        story("rel3-lone-old", relevance=3, sources=1, age_days=9),
    ]
    assert names(read_order(stories)) == ["new-two-src", "old-two-src", "one-src", "rel3-lone-old", "rel2-many"]


def test_read_order_does_not_change_its_input():
    stories = [story("a", relevance=2), story("b", relevance=3)]
    read_order(stories)
    assert names(stories) == ["a", "b"]


def test_a_story_takes_the_best_relevance_and_the_newest_date_of_its_items():
    s = story("x", relevance=2, sources=2, age_days=4)
    s.items[1].relevance = 3
    s.items[1].published = NOW
    assert (s.relevance, s.date) == (3, NOW)


def test_at_most_7_top_stories():
    stories = [story(f"s{i}", relevance=3, watch=f"w{i % 3}", eligible=True, age_days=i) for i in range(9)]
    result = picks(stories)
    assert names(result.top) == [f"s{i}" for i in range(7)]
    assert names(result.quick) == ["s7", "s8"]


def test_at_most_3_top_stories_from_one_watch_and_the_rest_become_quick_hits():
    stories = [story(f"a{i}", relevance=3, watch="a", eligible=True, age_days=i) for i in range(5)]
    stories += [story(f"b{i}", relevance=2, watch="b", eligible=True, age_days=i) for i in range(2)]
    result = picks(stories)
    assert names(result.top) == ["a0", "a1", "a2", "b0", "b1"]
    assert names(result.quick) == ["a3", "a4"]
    assert [s.items[0].decision for s in result.top] == ["top story"] * 5
    assert [s.items[0].decision for s in result.quick] == ["quick hit"] * 2


def test_a_story_that_is_not_eligible_is_never_a_top_story():
    stories = [story("better", relevance=3, eligible=False), story("worse", relevance=2, eligible=True)]
    result = picks(stories)
    assert names(result.top) == ["worse"]
    assert names(result.quick) == ["better"]


def test_at_most_15_quick_hits_and_the_16th_is_filtered_as_not_in_the_top_picks():
    stories = [story(f"q{i:02d}", relevance=2, age_days=i) for i in range(17)]
    result = picks(stories)
    assert names(result.quick) == [f"q{i:02d}" for i in range(15)]
    for dropped in stories[15:]:
        assert dropped.items[0].decision == "filtered"
        assert dropped.items[0].reason == "not in the top picks"
    assert all(s.items[0].decision == "quick hit" for s in stories[:15])


def test_top_stories_do_not_use_up_the_quick_hit_cap():
    stories = [story(f"t{i}", relevance=3, watch=f"w{i}", eligible=True, age_days=i) for i in range(3)]
    stories += [story(f"q{i:02d}", relevance=2, age_days=i) for i in range(15)]
    result = picks(stories)
    assert len(result.top) == 3 and len(result.quick) == 15


def test_stories_that_were_filtered_or_failed_are_left_alone():
    done = story("failed", decision="failed")
    done.items[0].reason = "the page timed out"
    low = Story([Item(title="low", address="https://e.test/low", source="s", relevance=1, decision="filtered", reason="meh")])
    result = picks([done, low, story("keep")])
    assert names(result.quick) == ["keep"]
    assert (done.items[0].decision, done.items[0].reason) == ("failed", "the page timed out")
    assert (low.items[0].decision, low.items[0].reason) == ("filtered", "meh")
