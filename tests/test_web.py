import time
from urllib.parse import quote

import pytest

from topic_radar.web import FetchError, fetch, normalize_address

MB5 = 5 * 1024 * 1024


@pytest.mark.parametrize("raw, expected", [
    ("https://e.test/a?utm_source=x&utm_medium=y", "https://e.test/a"),
    ("https://e.test/a?id=7&utm_campaign=z&page=2", "https://e.test/a?id=7&page=2"),
    ("https://e.test/a?fbclid=abc", "https://e.test/a"),
    ("https://e.test/a?gclid=1&mc_cid=2&mc_eid=3", "https://e.test/a"),
    ("HTTPS://News.Example.TEST/Path/Case", "https://news.example.test/Path/Case"),
    ("https://e.test/a/", "https://e.test/a"),
    ("https://e.test/a/?utm_source=x", "https://e.test/a"),
    ("https://e.test/", "https://e.test"),
    ("https://e.test/a?utmx=1", "https://e.test/a?utmx=1"),
])
def test_normalize_address(raw, expected):
    assert normalize_address(raw) == expected


async def test_fetch_returns_final_address_type_and_text(site, make_ctx):
    ctx = make_ctx()
    got = await fetch(ctx, site.url("/feeds/news.atom"))
    assert got.status == 200
    assert got.url == site.url("/feeds/news.atom")
    assert got.content_type == "application/atom+xml"
    assert "Harbor News" in got.text


@pytest.mark.parametrize("ctype", ["text/html", "application/xml", "text/xml", "application/rss+xml",
                                   "application/atom+xml", "text/plain"])
async def test_fetch_accepts_page_feed_and_text_types(site, make_ctx, ctype):
    got = await fetch(make_ctx(), site.url(f"/bytes/20?type={quote(ctype)}"))
    assert got.content_type == ctype
    assert len(got.body) == 20


async def test_fetch_follows_a_redirect_to_its_final_address(site, make_ctx):
    target = site.url("/posts/final.html")
    got = await fetch(make_ctx(), site.url(f"/redirect?to={quote(target)}&code=301"))
    assert got.url == target
    assert "The article." in got.text


async def test_head_returns_no_body(site, make_ctx):
    got = await fetch(make_ctx(), site.url("/posts/final.html"), method="HEAD")
    assert got.status == 200
    assert got.body == b""


async def test_a_500_is_an_error_naming_the_status(site, make_ctx):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(), site.url("/status/500"))
    assert "500" in err.value.reason
    assert err.value.refused is False


async def test_a_slow_answer_is_an_error_naming_the_wait(site, make_ctx):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(timeout_seconds=0.3), site.url("/slow"))
    assert "no answer within 0.3 seconds" in err.value.reason


async def test_a_file_address_is_refused_with_the_scheme_rule(make_ctx):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(), "file:///etc/hosts")
    assert err.value.refused is True
    assert "only http and https" in err.value.reason
    assert "file" in err.value.reason


async def test_a_redirect_to_a_private_address_is_refused_even_with_loopback_allowed(site, make_ctx):
    start = site.url(f"/redirect?to={quote('http://10.0.0.1/secret')}")
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(allow_loopback=True), start)
    assert err.value.refused is True
    assert "private or local network address" in err.value.reason
    assert "10.0.0.1" in err.value.reason
    assert [m for m, p in site.requests] == ["GET"]  # the redirect was served; nothing went on


@pytest.mark.parametrize("target", ["http://192.168.1.5/", "http://172.16.0.9/", "http://169.254.169.254/latest",
                                    "http://[fe80::1]/", "http://0.0.0.0/"])
async def test_other_non_public_targets_are_refused_with_loopback_allowed(site, make_ctx, target):
    start = site.url(f"/redirect?to={quote(target)}")
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(allow_loopback=True), start)
    assert "private or local network address" in err.value.reason


async def test_loopback_itself_is_refused_when_the_flag_is_off(site, make_ctx):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(allow_loopback=False), site.url("/feeds/news.atom"))
    assert err.value.refused is True
    assert "private or local network address" in err.value.reason
    assert site.requests == []


async def test_a_hostname_that_resolves_to_loopback_is_refused_when_the_flag_is_off(site, make_ctx):
    port = site.base.rsplit(":", 1)[1]
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(allow_loopback=False), f"http://localhost:{port}/feeds/news.atom")
    assert "private or local network address" in err.value.reason
    assert site.requests == []


async def test_a_body_over_5_mb_is_refused_by_its_declared_length(site, make_ctx):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(), site.url(f"/bytes/{MB5 + 1}"))
    assert err.value.refused is True
    assert "larger than 5 MB" in err.value.reason


async def test_a_declared_length_over_5_mb_is_refused_before_the_body_is_read(site, make_ctx):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(), site.url(f"/bytes/100?declare={MB5 + 1}"))
    assert err.value.refused is True
    assert "larger than 5 MB" in err.value.reason


async def test_a_body_over_5_mb_with_no_declared_length_is_refused_while_streaming(site, make_ctx):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(), site.url(f"/bytes/{MB5 + 1}?length=0"))
    assert err.value.refused is True
    assert "larger than 5 MB" in err.value.reason


async def test_a_body_of_exactly_5_mb_is_accepted(site, make_ctx):
    got = await fetch(make_ctx(), site.url(f"/bytes/{MB5}"))
    assert len(got.body) == MB5


async def test_an_image_body_is_refused_with_the_type_rule(site, make_ctx):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(), site.url("/bytes/50?type=image/png"))
    assert err.value.refused is True
    assert "image/png" in err.value.reason
    assert "not a page or feed" in err.value.reason


async def test_a_redirect_loop_stops_at_the_hop_limit(site, make_ctx):
    # a chain longer than the limit: each hop sends the client on to another redirect
    url = site.url("/status/200")
    for _ in range(12):
        url = site.url(f"/redirect?to={quote(url)}")
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(), url)
    assert "too many redirects" in err.value.reason
    assert err.value.refused is True


async def test_requests_to_one_host_are_paced(site, make_ctx):
    ctx = make_ctx(request_delay_seconds=0.3)
    start = time.monotonic()
    await fetch(ctx, site.url("/feeds/news.atom"))
    await fetch(ctx, site.url("/feeds/blog.xml"))
    assert time.monotonic() - start >= 0.28


@pytest.mark.parametrize("bad", ["http://x.example:99999/", "http://x.example:abc/", "http://[bad/", "http://"])
async def test_a_malformed_address_is_a_fetch_error_not_a_crash(make_ctx, bad):
    with pytest.raises(FetchError) as err:
        await fetch(make_ctx(), bad)
    assert "Error" not in err.value.reason and "httpx" not in err.value.reason


async def test_a_redirect_to_a_malformed_address_is_a_fetch_error(site, make_ctx):
    start = site.url(f"/redirect?to={quote('http://x.example:99999/')}")
    with pytest.raises(FetchError):
        await fetch(make_ctx(), start)
