from datetime import timezone

import pytest

from topic_radar.state import RunState
from topic_radar.steps.collect import collect

NEWS_TITLES = ["Dock repairs finish", "New ferry timetable"]


async def test_each_seed_is_read_as_a_feed_into_items(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/feeds/blog.xml"), site.url("/feeds/news.atom")])
    state = await collect(ctx, RunState())
    by_source = {}
    for item in state.items:
        by_source.setdefault(item.source, []).append(item.title)
    assert by_source[site.url("/feeds/news.atom")] == NEWS_TITLES
    assert len(by_source[site.url("/feeds/blog.xml")]) == 5
    assert state.failed_sources == []
    assert state.feed_titles == {site.url("/feeds/blog.xml"): "Garden Notes",
                                 site.url("/feeds/news.atom"): "Harbor News"}


async def test_items_carry_address_date_and_plain_text(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/feeds/news.atom"), site.url("/feeds/blog.xml")])
    state = await collect(ctx, RunState())
    dock = next(i for i in state.items if i.title == "Dock repairs finish")
    assert dock.address == site.url("/posts/dock.html")
    assert dock.published.tzinfo is not None
    assert dock.published.astimezone(timezone.utc).isoformat() == "2026-11-08T10:00:00+00:00"
    assert dock.summary == "The east dock reopens."
    ferry = next(i for i in state.items if i.title == "New ferry timetable")
    assert ferry.notes == "Ferries run hourly."  # entry content, tags removed
    fresh = next(i for i in state.items if i.title == "Fresh post")
    assert fresh.summary == "Soil tips."
    undated = next(i for i in state.items if i.title == "Undated note")
    assert undated.published is None


@pytest.mark.parametrize("path, reason_has", [
    ("/status/500", "500"),
    ("/slow", "no answer within 0.3 seconds"),
    ("/feeds/page.html", "a web page, not a feed"),
])
async def test_a_failing_source_is_recorded_and_the_others_still_yield(site, make_ctx, path, reason_has):
    bad = site.url(path)
    ctx = make_ctx(seeds=[bad, site.url("/feeds/news.atom")], timeout_seconds=0.3)
    state = await collect(ctx, RunState())
    assert [f.source for f in state.failed_sources] == [bad]
    reason = state.failed_sources[0].reason
    assert reason_has in reason
    assert "Traceback" not in reason and "httpx" not in reason and "Error" not in reason
    assert [i.title for i in state.items] == NEWS_TITLES


async def test_the_web_page_reason_tells_the_user_what_to_do(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/feeds/page.html")])
    state = await collect(ctx, RunState())
    assert state.failed_sources[0].reason == (
        "this address is a web page, not a feed: replace it with the feed's address or remove it from seeds")


async def test_a_text_body_that_is_not_a_feed_is_a_failed_source(site, make_ctx):
    ctx = make_ctx(seeds=[site.url("/bytes/40"), site.url("/feeds/news.atom")])
    state = await collect(ctx, RunState())
    assert [f.source for f in state.failed_sources] == [site.url("/bytes/40")]
    assert "could not be read as a feed" in state.failed_sources[0].reason
    assert len(state.items) == 2


async def test_a_refused_seed_records_the_guard_reason_and_the_rest_continue(site, make_ctx):
    ctx = make_ctx(seeds=["file:///etc/hosts", site.url("/bytes/20?type=image/png"), site.url("/feeds/news.atom")])
    state = await collect(ctx, RunState())
    reasons = {f.source: f.reason for f in state.failed_sources}
    assert "only http and https" in reasons["file:///etc/hosts"]
    assert "image/png" in reasons[site.url("/bytes/20?type=image/png")]
    assert [i.title for i in state.items] == NEWS_TITLES


async def test_a_feed_with_no_entries_is_a_source_with_no_items_not_a_failure(site, make_ctx, tmp_path):
    ctx = make_ctx(seeds=[site.url("/feeds/empty.xml")])
    state = await collect(ctx, RunState())
    assert state.failed_sources == []
    assert state.items == []


async def test_each_source_is_noted_as_it_is_read_and_a_failure_is_noted_when_it_happens(site, make_ctx):
    lines = []
    ctx = make_ctx(seeds=[site.url("/status/500"), site.url("/feeds/news.atom")])
    ctx.run_folder.echo = lines.append
    await collect(ctx, RunState())
    texts = [line.split("] ", 1)[1] for line in lines]
    assert texts[0] == f"Reading feed 1 of 2: {site.url('/status/500')}"
    assert texts[1].startswith(f"Couldn't read {site.url('/status/500')}: ") and texts[1].endswith(".")
    assert texts[2] == f"Reading feed 2 of 2: {site.url('/feeds/news.atom')}"
    assert texts[3] == "Found 2 items in 1 feed."
