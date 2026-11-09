from datetime import timedelta
from urllib.parse import quote

import pytest

from topic_radar.state import Item, RunState
from topic_radar.steps.collect import collect
from topic_radar.steps.normalize import normalize, resolve_address
from conftest import NOW


async def run_both(ctx):
    return await normalize(ctx, await collect(ctx, RunState()))


def titles(state):
    return sorted(i.title for i in state.items)


async def test_items_older_than_the_lookback_are_dropped_and_newer_ones_kept(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/feeds/blog.xml")], lookback=timedelta(days=7))
    state = await run_both(ctx)
    assert titles(state) == ["Fresh post", "Just inside the window", "Undated note"]


async def test_the_lookback_comes_from_the_watch_and_the_context_clock(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/feeds/blog.xml")], lookback=timedelta(days=60))
    state = await run_both(ctx)
    assert "Long ago" in titles(state) and "Just outside the window" in titles(state)
    ctx = make_ctx(seeds=[site.url("/feeds/blog.xml")], lookback=timedelta(hours=48))
    state = await run_both(ctx)
    assert titles(state) == ["Fresh post", "Undated note"]
    assert NOW.isoformat() == "2026-11-09T12:00:00+00:00"


async def test_two_items_with_the_same_normalized_address_are_one(site, make_ctx):
    a = site.url("/posts/a")
    ctx = make_ctx()
    state = RunState(items=[
        Item("First", a + "/?utm_source=x", site.url("/f1"), NOW),
        Item("Second", a + "?fbclid=9", site.url("/f2"), NOW),
        Item("Other", site.url("/posts/b"), site.url("/f1"), NOW),
    ])
    assert state.items[0].address != state.items[1].address
    state = await normalize(ctx, state)
    assert [(i.title, i.address) for i in state.items] == [("First", a), ("Other", site.url("/posts/b"))]


async def test_a_redirect_resolves_to_its_final_address(site, make_ctx):
    final = site.url("/posts/final.html")
    ctx = make_ctx()
    state = RunState(items=[Item("Via redirect", site.url(f"/redirect?to={quote(final)}&code=301"),
                                 site.url("/f"), NOW)])
    state = await normalize(ctx, state)
    assert state.items[0].address == final


async def test_a_failed_head_falls_back_to_get(site, make_ctx):
    final = site.url("/posts/final.html")
    start = site.url(f"/head-fails?to={quote(final)}")
    assert await resolve_address(make_ctx(), start) == final
    assert site.requests == [("HEAD", start.removeprefix(site.base)), ("GET", start.removeprefix(site.base)),
                             ("GET", "/posts/final.html")]


async def test_a_head_that_works_needs_no_get(site, make_ctx):
    final = site.url("/posts/final.html")
    start = site.url(f"/redirect?to={quote(final)}")
    assert await resolve_address(make_ctx(), start) == final
    assert [m for m, p in site.requests] == ["HEAD", "HEAD"]


@pytest.mark.parametrize("path", ["/status/500", "/posts/missing.html", "/bytes/20?type=image/png"])
async def test_a_failed_resolve_keeps_the_feeds_address_and_the_item(site, make_ctx, path):
    original = site.url(path)
    ctx = make_ctx()
    state = RunState(items=[Item("Keeps", original, site.url("/f"), NOW)])
    state = await normalize(ctx, state)
    assert [(i.title, i.address) for i in state.items] == [("Keeps", original)]
    assert len(site.requests) >= 2  # HEAD then GET were both tried


async def test_a_resolve_that_the_guard_refuses_keeps_the_feeds_address(site, make_ctx):
    start = site.url(f"/redirect?to={quote('http://10.0.0.1/x')}")
    ctx = make_ctx()
    state = await normalize(ctx, RunState(items=[Item("Keeps", start, site.url("/f"), NOW)]))
    assert state.items[0].address == start


WIDGET = "/gh/acme/widget/releases.atom"


async def test_five_versioned_entries_become_one_combined_item(site, make_ctx):
    ctx = make_ctx(seeds=[site.url(WIDGET)])
    state = await run_both(ctx)
    assert len(state.items) == 1
    item = state.items[0]
    assert item.title == "widget: 5 releases since the last run"
    assert item.source == site.url(WIDGET)
    assert item.published.isoformat() == "2026-11-08T10:00:00+00:00"
    tags = ["v0.2.1", "v0.9.0", "v0.10.0-rc1", "v0.10.0", "v0.10.1"]
    assert item.links == [site.url(f"/gh/acme/widget/releases/tag/{t}") for t in tags]
    marks = ["NOTES-0.2.1", "NOTES-0.9.0", "NOTES-0.10.0-rc1", "NOTES-0.10.0 ", "NOTES-0.10.1"]
    at = [item.notes.index(m) for m in marks]
    assert at == sorted(at)
    assert "<" not in item.notes and "href" not in item.notes and "docs.example.test" not in item.notes
    assert "the cache guide" in item.notes  # the link's words stay
    assert "Ten" in item.notes


async def test_a_combined_item_is_addressed_by_its_newest_release_and_labels_each_link_by_version(site, make_ctx):
    state = await run_both(make_ctx(seeds=[site.url(WIDGET)]))
    (item,) = state.items
    assert item.address == site.url("/gh/acme/widget/releases/tag/v0.10.1")
    assert item.link_labels == ["v0.2.1", "v0.9.0", "v0.10.0-rc1", "v0.10.0", "v0.10.1"]


async def test_a_single_release_stays_an_ordinary_item(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/gh/acme/solo/releases.atom")])
    state = await run_both(ctx)
    assert [i.title for i in state.items] == ["v1.0.0"]
    assert state.items[0].links == []


async def test_a_feed_whose_titles_are_all_versions_is_combined_under_the_feed_title(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/changelog/feed.xml")])
    state = await run_both(ctx)
    assert [i.title for i in state.items] == ["Widget changelog: 3 releases since the last run"]
    assert [l.rsplit("/", 1)[1] for l in state.items[0].links] == ["1.2.0", "1.3.0", "1.3.1"]


async def test_a_blog_with_version_like_words_in_titles_is_not_combined(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/feeds/thoughts.xml")])
    state = await run_both(ctx)
    assert titles(state) == ["2.0 thoughts", "3.1 notes from the road"]


async def test_release_feeds_do_not_swallow_other_sources(site, make_ctx):
    ctx = make_ctx(seeds=[site.url(WIDGET), site.url("/feeds/news.atom")])
    state = await run_both(ctx)
    assert titles(state) == ["Dock repairs finish", "New ferry timetable", "widget: 5 releases since the last run"]


async def test_only_releases_inside_the_lookback_are_combined(site, make_ctx):
    # v0.9.0 (Nov 3) and v0.2.1 (Nov 4) fall out of a 4-day lookback; three releases remain
    ctx = make_ctx(seeds=[site.url(WIDGET)], lookback=timedelta(days=4))
    state = await run_both(ctx)
    assert [i.title for i in state.items] == ["widget: 3 releases since the last run"]


@pytest.mark.parametrize("lookback, said", [
    (timedelta(hours=12), "from the last 12 hours"),
    (timedelta(hours=1), "from the last 1 hour "),
    (timedelta(hours=36), "from the last 36 hours"),
    (timedelta(days=1), "from the last 1 day "),
    (timedelta(days=14), "from the last 14 days"),
])
async def test_the_kept_note_states_the_lookback_in_the_unit_that_reads_naturally(site, make_ctx, lookback, said):
    ctx = make_ctx(seeds=[site.url("/feeds/blog.xml")], lookback=lookback)
    await run_both(ctx)
    note = next(l for l in (ctx.run_folder.path / "notes.md").read_text(encoding="utf-8").splitlines() if "Kept " in l)
    assert said in note


async def test_a_standalone_item_at_a_release_address_never_drops_the_combined_item(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/feeds/widget-news.atom"), site.url(WIDGET)])
    state = await run_both(ctx)
    assert titles(state) == ["widget: 5 releases since the last run"]
    (item,) = state.items
    assert len(item.links) == 5 and "NOTES-0.2.1" in item.notes
