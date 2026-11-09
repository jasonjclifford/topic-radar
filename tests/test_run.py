import csv
import io
import re
from datetime import datetime, timezone
from functools import partial

import pytest
from typer.testing import CliRunner

from topic_radar import cli, pipeline, rank
from topic_radar.model.ollama import PreflightError
from topic_radar.model.scripted import ScriptedModel
from topic_radar.report.render import render_report
from topic_radar.state import (DECISIONS, Article, Claim, FailedSource, Item, QuickHit, RunState, Story, Written,
                               WrittenStory)

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
FEED = "https://e.test/feed"
BOM = b"\xef\xbb\xbf"
LINK = re.compile(r"(?<!\\)\[(?:\\.|[^\]\\])*\]\(<([^>]*)>\)")  # [text](<address>); escaped brackets aren't links
SCHEME_LINK = re.compile(r"\]\(\s*<?\s*([a-z][a-z0-9+.-]*):", re.IGNORECASE)
QUOTE = "Cedar 3.0 ships a new scheduler that starts jobs 40 percent faster than version 2."


class FakeOllama:
    """Stands in for the Ollama client: a scripted model, plus the preflight and unload the CLI calls."""

    def __init__(self, scripted, preflight_error=None):
        self.scripted = scripted
        self.preflight_error = preflight_error
        self.preflights, self.unloads = [], 0

    async def call(self, step, system, user, schema):
        return await self.scripted.call(step, system, user, schema)

    async def preflight(self, model):
        self.preflights.append(model)
        if self.preflight_error:
            raise PreflightError(self.preflight_error)

    async def unload(self):
        self.unloads += 1


def scripted(cedar=True):
    verdicts = [(3, "release"), (2, "news"), (2, "news"), (0, "other"), (0, "other"), (0, "other"), (0, "other")]
    model = ScriptedModel().on("triage", "", {"items": [
        {"item": n, "relevance": r, "reason": "fits" if r else "unrelated", "kind": k}
        for n, (r, k) in enumerate(verdicts, 1)]})
    model.on("read", "Cedar 3.0 announced", {"claims": [
        {"claim": "Cedar 3.0 starts jobs 40 percent faster.", "quote": QUOTE}]})
    model.on("write", "Cedar 3.0 announced", {
        "headline": "Cedar 3.0 ships a faster scheduler", "what_happened": "A new scheduler starts jobs faster.",
        "why_it_matters": "You follow build tooling.", "read_if": "You run builds.", "takeaway": "Cedar 3.0 is faster."})
    return model.on("summary", "", {"bullets": ["Cedar 3.0 is out."]})


class Harness:
    def __init__(self, folder, site, monkeypatch):
        self.folder, self.site, self.monkeypatch = folder, site, monkeypatch
        self.fake = FakeOllama(scripted())
        (folder / "watches").mkdir(parents=True)
        (folder / "settings.yaml").write_text("request_delay_seconds: 0\ntimeout_seconds: 2\n")
        self.write_watch("ai", [site.url("/run/feed.xml")])

    def write_watch(self, slug, seeds, text=None):
        (self.folder / "watches" / f"{slug}.yaml").write_text(text or (
            "name: Build tooling\ninterests: |\n  Build tools and schedulers.\nseeds:\n"
            + "".join(f"  - {s}\n" for s in seeds)))

    def run(self, watch="ai", *extra, relative=False):
        self.monkeypatch.setattr(cli, "run_watch", partial(
            pipeline.run_watch, model_client=self.fake, allow_loopback=True, clock=lambda: NOW))
        folder = str(self.folder)
        if relative:  # as typed from inside the folder's parent
            self.monkeypatch.chdir(self.folder.parent)
            folder = self.folder.name
        return CliRunner().invoke(cli.app, ["run", watch, "--folder", folder, "--read-cap", "1", *extra])

    @property
    def run_dir(self):
        (path,) = (self.folder / "runs").iterdir()
        return path

    def report(self):
        return (self.run_dir / "report.md").read_text(encoding="utf-8")

    def rows(self):
        text = (self.run_dir / "items.csv").read_bytes().decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))


@pytest.fixture
def h(tmp_path, site, monkeypatch):
    return Harness(tmp_path / "Topic Radar", site, monkeypatch)


# --- end to end through the CLI ---------------------------------------------------------------

def test_a_run_leaves_the_report_notes_csv_articles_and_details(h):
    result = h.run()
    assert result.exit_code == 0, result.output
    run = h.run_dir
    assert (run / "report.md").is_file() and (run / "items.csv").is_file()
    assert (run / "notes.md").read_text(encoding="utf-8").rstrip().endswith("Done.")
    assert [p.name for p in (run / "articles").iterdir()] == ["1-cedar-3-0-announced.md"]
    assert (run / "details" / "events.jsonl").is_file()
    assert "Cedar 3.0 ships a faster scheduler" in h.report()


def test_the_first_line_says_stopping_with_ctrl_c_is_safe(h):
    h.run()
    first = (h.run_dir / "notes.md").read_text(encoding="utf-8").splitlines()[0]
    assert "Ctrl-C" in first and "safe" in first


def test_every_link_in_the_report_is_an_item_address_and_a_javascript_feed_link_is_not_linked(h):
    h.run()
    report = h.report()
    targets = LINK.findall(report)
    item_addresses = {r["address"] for r in h.rows()}
    assert h.site.url("/articles/quoted.html") in targets  # not vacuous: the report does link its items
    assert set(targets) <= item_addresses
    assert all(t.startswith(("http://", "https://")) for t in targets)
    assert {m.lower() for m in SCHEME_LINK.findall(report)} <= {"http", "https"}
    assert "Plugin loader notes" in report  # the javascript: item is in the report, as words
    assert "javascript:alert" not in " ".join(targets)


def test_untrusted_titles_cannot_inject_links_or_headings(h):
    h.run()
    report = h.report()
    assert "Click me" in report
    assert "evil.example" not in " ".join(LINK.findall(report))
    assert not re.search(r"^#+ Heading", report, re.MULTILINE)
    assert "<b>" not in report
    assert "evil.example/pwn" in report and "https://evil.example" not in report  # shown as words; a bare address can't autolink


def test_items_csv_has_a_bom_and_one_row_per_item_with_one_decision_each(h):
    h.run()
    raw = (h.run_dir / "items.csv").read_bytes()
    assert raw.startswith(BOM)
    rows = h.rows()
    assert len(rows) == 7
    assert list(rows[0]) == ["watch", "source", "title", "address", "published", "new_or_update", "relevance",
                             "kind", "reason", "decision", "report_id", "article"]
    assert {r["decision"] for r in rows} <= set(DECISIONS)
    cedar = next(r for r in rows if r["title"] == "Cedar 3.0 announced")
    assert (cedar["decision"], cedar["report_id"], cedar["relevance"], cedar["source"], cedar["watch"]) == (
        "top story", "S1", "3", "Build Weekly", "ai")
    assert cedar["article"] == "articles/1-cedar-3-0-announced.md"
    over_cap = next(r for r in rows if r["title"] == "Plugin loader notes")
    assert (over_cap["decision"], over_cap["reason"], over_cap["report_id"]) == ("quick hit", "over read cap", "Q1")


def test_cells_starting_with_a_formula_character_get_a_leading_apostrophe(h):
    h.run()
    titles = {r["title"] for r in h.rows()}
    assert {"'=SUM(1+1)", "'+1 plan", "'-5 percent off sale", "'@handle moved on"} <= titles
    assert "Cedar 3.0 announced" in titles  # an ordinary cell is left as it was


def test_a_failed_source_shows_the_banner_a_notes_line_and_run_health_and_the_run_still_succeeds(h):
    bad = h.site.url("/status/503")
    h.write_watch("ai", [h.site.url("/run/feed.xml"), bad])
    result = h.run()
    assert result.exit_code == 0, result.output
    report = h.report()
    banner = report.index("1 of 2 sources couldn't be read")
    assert banner < report.index("## In 30 seconds")
    health = report[report.index("## Run health"):]
    assert bad in health and "503" in health
    notes = (h.run_dir / "notes.md").read_text(encoding="utf-8")
    assert any(bad in line and "ouldn't read" in line for line in notes.splitlines())


def test_collecting_notes_one_line_per_source_in_seed_order_and_a_failure_when_it_happens(h):
    good1, bad, good2 = h.site.url("/run/feed.xml"), h.site.url("/status/500"), h.site.url("/feeds/news.atom")
    h.write_watch("ai", [good1, bad, good2])
    result = h.run()
    assert result.exit_code == 0, result.output
    for text in ((h.run_dir / "notes.md").read_text(encoding="utf-8"), result.output):
        lines = text.splitlines()
        reading = [line for line in lines if "Reading feed" in line]
        assert [line.split("] ", 1)[1] for line in reading] == [
            f"Reading feed 1 of 3: {good1}", f"Reading feed 2 of 3: {bad}", f"Reading feed 3 of 3: {good2}"]
        failures = [n for n, line in enumerate(lines) if "Couldn't read" in line]
        assert len(failures) == 1 and bad in lines[failures[0]] and "500" in lines[failures[0]]
        first_triage = next(n for n, line in enumerate(lines) if "Triage:" in line)
        assert lines.index(reading[1]) < failures[0] < lines.index(reading[2]) < first_triage


def test_a_not_a_feed_failure_in_run_health_carries_one_remedy(h):
    page = h.site.url("/feeds/page.html")
    h.write_watch("ai", [h.site.url("/run/feed.xml"), page])
    h.run()
    health = h.report().split("## Run health")[1]
    line = next(x for x in health.splitlines() if page in x)
    assert line.count("remove it from") == 1


def test_a_500_failure_in_run_health_still_gets_a_remedy(h):
    bad = h.site.url("/status/500")
    h.write_watch("ai", [h.site.url("/run/feed.xml"), bad])
    h.run()
    health = h.report().split("## Run health")[1]
    line = next(x for x in health.splitlines() if bad in x)
    assert "remove it from the watch's seeds" in line


def test_a_clean_run_has_no_banner(h):
    h.run()
    assert "couldn't be read" not in h.report().split("## In 30 seconds")[0]


def test_a_missing_watch_exits_2_naming_the_folder_and_the_watches_found(h):
    h.write_watch("other", [])
    result = h.run("nope")
    assert result.exit_code == 2
    assert str(h.folder / "watches") in result.output
    assert "nope" in result.output and "ai" in result.output and "other" in result.output
    assert h.site.requests == [] and not (h.folder / "runs").exists()


def test_a_bad_watch_file_exits_2_with_the_loaders_message(h):
    h.write_watch("broken", [], text="name: Broken\n")
    result = h.run("broken")
    assert result.exit_code == 2
    assert "broken.yaml: the field 'interests' is missing" in result.output
    assert h.site.requests == [] and not (h.folder / "runs").exists()


def test_a_watch_file_that_is_not_utf8_exits_2_naming_the_file(h):
    (h.folder / "watches" / "latin.yaml").write_bytes("name: Caf\xe9\ninterests: x\n".encode("latin-1"))
    result = h.run("latin")
    assert result.exit_code == 2
    assert "latin.yaml" in result.output and "UTF-8" in result.output and "Traceback" not in result.output
    assert h.site.requests == [] and not (h.folder / "runs").exists()


def test_a_settings_value_of_the_wrong_type_exits_2_naming_the_field_and_type(site, tmp_path, monkeypatch):
    h = Harness(tmp_path / "radar", site, monkeypatch)
    (h.folder / "settings.yaml").write_text("read_cap: \"5\"\n")
    result = h.run()
    assert result.exit_code == 2
    assert "read_cap" in result.output and "whole number" in result.output and "Traceback" not in result.output
    assert not (h.folder / "runs").exists()


def test_a_watch_name_cannot_reach_outside_the_watches_folder(h):
    (h.folder / "outside.yaml").write_text("name: X\ninterests: y\n")
    result = h.run("../outside")
    assert result.exit_code == 2 and h.site.requests == []


def test_a_failed_preflight_exits_2_with_its_message_and_collects_nothing(h):
    h.fake.preflight_error = "The model gemma4:e4b-mlx isn't installed. Install it with: ollama pull gemma4:e4b-mlx"
    result = h.run()
    assert result.exit_code == 2
    assert "ollama pull gemma4:e4b-mlx" in result.output
    assert h.fake.preflights == ["gemma4:e4b-mlx"]
    assert h.site.requests == []
    assert not (h.folder / "runs").exists()


def test_the_model_flag_names_the_model_preflight_checks(h):
    h.run("ai", "--model", "tiny:1b")
    assert h.fake.preflights == ["tiny:1b"]


async def boom(ctx, state):
    raise RuntimeError("kaboom in the middle")


def test_a_step_that_raises_exits_1_with_error_txt_and_no_report(h):
    from topic_radar.steps.collect import collect
    from topic_radar.steps.normalize import normalize
    h.monkeypatch.setattr(pipeline, "STEPS", [collect, normalize, boom])
    result = h.run()
    assert result.exit_code == 1
    run = h.run_dir
    assert h.site.requests  # the pipeline got as far as collecting before the failure
    assert not (run / "report.md").exists()
    notes = (run / "notes.md").read_text(encoding="utf-8")
    assert "Done." not in notes and "kaboom" not in notes
    assert "error.txt" in notes
    error = (run / "details" / "error.txt").read_text(encoding="utf-8")
    assert "RuntimeError: kaboom in the middle" in error and "Traceback" in error
    assert h.fake.unloads == 1
    assert "Traceback" not in result.output


def test_ctrl_c_unloads_the_model_and_exits_non_zero_without_a_traceback(h):
    async def interrupted(ctx, state):
        raise KeyboardInterrupt

    h.monkeypatch.setattr(pipeline, "STEPS", [interrupted])
    result = h.run()
    assert result.exit_code == 130
    assert not (h.run_dir / "report.md").exists()
    assert "Done." not in (h.run_dir / "notes.md").read_text(encoding="utf-8")
    assert h.fake.unloads == 1
    assert "Traceback" not in result.output


def test_the_model_is_unloaded_once_at_the_end_of_a_run(h):
    assert h.run().exit_code == 0
    assert h.fake.unloads == 1


def test_the_terminal_output_ends_with_the_reports_path(h):
    result = h.run()
    assert result.output.rstrip().splitlines()[-1] == str(h.run_dir / "report.md")
    assert "Done." in result.output


def test_the_path_printed_is_the_full_path_even_when_the_folder_was_given_relative(h):
    result = h.run("ai", relative=True)
    last = result.output.rstrip().splitlines()[-1]
    assert last == str(h.run_dir.resolve() / "report.md") and last.startswith("/")


# --- the report, rendered from a state we build -------------------------------------------------

def make_item(title="Cedar 3.0 announced", address="https://e.test/a", decision="quick hit", **kw):
    return Item(title=title, address=address, source=FEED, published=NOW, decision=decision, **kw)


def story_of(item, **kw):
    return WrittenStory(id="S1", story=Story([item]), headline="Cedar 3.0 ships", what_happened="It is faster.",
                        why_it_matters="You build.", read_if="You run builds.", takeaway="Faster.",
                        article="articles/1-cedar.md", **kw)


@pytest.fixture
def render(make_ctx):
    def build(state, **settings):
        ctx = make_ctx(**settings)
        ctx.watch.name = "Build tooling"
        return render_report(ctx, state)
    return build


def state_with(*items, written=None, articles=(), failed=()):
    return RunState(items=list(items), stories=[Story([i]) for i in items], articles=list(articles),
                    failed_sources=list(failed), feed_titles={FEED: "Build Weekly"}, written=written)


async def test_a_top_story_shows_its_id_fields_source_link_and_article_path(render):
    item = make_item(decision="top story")
    top = story_of(item)
    report = render(state_with(item, written=Written(top=[top], summary=["Cedar is out."])))
    assert "S1" in report and "Cedar 3.0 ships" in report and "It is faster." in report
    assert "[Build Weekly](<https://e.test/a>)" in report
    assert "articles/1-cedar.md" in report
    assert "Cedar is out." in report.split("## Top stories")[0].split("## In 30 seconds")[1]


async def test_the_empty_state_says_how_many_were_read(render):
    items = [make_item("One", "https://e.test/1"), make_item("Two", "https://e.test/2")]
    arts = [Article(item=i) for i in items]
    report = render(state_with(*items, written=Written(), articles=arts))
    assert "2 items were read; none had a claim backed by a quote" in report
    none = render(state_with(make_item(), written=Written()))
    assert "0 items were read; none had a claim backed by a quote" in none


async def test_a_fallback_story_shows_the_headline_and_its_quoted_claims(render):
    item = make_item(decision="top story")
    claim = Claim("Cedar is 40% faster.", "starts jobs 40 percent faster", True)
    top = WrittenStory(id="S1", story=Story([item]), headline="Cedar 3.0 announced", claims=[claim],
                       article="articles/1-x.md", fallback=True, fallback_reason="number check")
    report = render(state_with(item, written=Written(top=[top])))
    assert "Cedar is 40% faster." in report and '"starts jobs 40 percent faster"' in report
    assert "Why it matters" not in report


async def test_quick_hits_are_listed_by_id_with_links_only_for_web_addresses(render):
    web, js = make_item("Web one", "https://e.test/w"), make_item("Script one", "javascript:alert(1)")
    quick = [QuickHit("Q1", Story([web]), "Web one", "a summary", web.address, "test"),
             QuickHit("Q2", Story([js]), "Script one", "", js.address, "test")]
    report = render(state_with(web, js, written=Written(quick=quick)))
    section = report.split("## Quick hits")[1].split("## Filtered out")[0]
    assert LINK.findall(section) == ["https://e.test/w"]
    assert "Q1" in section and "a summary" in section and "Q2" in section and "Script one" in section


async def test_filtered_out_counts_items_by_reason_and_names_items_csv(render):
    items = [make_item(f"N{n}", f"https://e.test/{n}", "filtered", relevance=0, reason="unrelated") for n in range(3)]
    items.append(make_item("Barely", "https://e.test/b", "filtered", relevance=1, reason="meh"))
    items.append(make_item("Rep", "https://e.test/r", "filtered", relevance=3, reason="repeats: Use subagents."))
    items.append(make_item("Late", "https://e.test/l", "filtered", relevance=3, reason="not in the top picks"))
    section = render(state_with(*items, written=Written())).split("## Filtered out")[1].split("## Run health")[0]
    assert re.search(r"\b3\b.*not related", section)
    assert re.search(r"\b1\b.*barely related", section)
    assert re.search(r"\b1\b.*already know", section)
    assert re.search(r"\b1\b.*top picks", section)
    assert "items.csv" in section


async def test_run_health_lists_every_kind_of_problem_with_counts(render):
    items = [make_item("A", "https://e.test/a", "not scored"), make_item("B", "https://e.test/b", "not scored"),
             make_item("C", "https://e.test/c", "failed", reason="no answer"),
             make_item("D", "https://e.test/d", "quick hit", reason="over read cap", relevance=2, unread_over_cap=True),
             make_item("E", "https://e.test/e", "quick hit", reason="over read cap", relevance=3, unread_over_cap=True)]
    arts = [Article(item=items[0], dropped=2), Article(item=items[1], dropped=1)]
    written = Written(failed_writes=1, health=["The write call for S2 (X) failed, so it shows its headline."])
    failed = [FailedSource("https://down.test/feed", "no answer within 30 seconds")]
    report = render(state_with(*items, written=written, articles=arts, failed=failed), read_cap=25)
    banner, health = report.split("## In 30 seconds")[0], report.split("## Run health")[1]
    assert "1 of 1 source couldn't be read" in banner
    assert "2 items weren't scored" in banner and "1 item couldn't be read" in banner
    assert "https://down.test/feed" in health and "no answer within 30 seconds" in health
    assert "2 items were not scored" in health and "1 item failed" in health
    assert "3 claims were dropped" in health
    assert "The write call for S2 (X) failed" in health
    assert "Read cap: 25" in health and "2 scored items were not read" in health


async def test_a_clean_state_has_no_banner_and_no_dropped_claim_line(render):
    item = make_item(decision="top story")
    report = render(state_with(item, written=Written(top=[story_of(item)]), articles=[Article(item=item)]))
    assert "couldn't be read" not in report and "weren't scored" not in report
    assert "dropped" not in report.split("## Run health")[1]
    assert "0 scored items were not read" in report.split("## Run health")[1]


async def test_the_summary_section_is_left_out_when_there_is_no_summary(render):
    item = make_item(decision="top story")
    report = render(state_with(item, written=Written(top=[story_of(item)], summary=None)))
    assert "## In 30 seconds" not in report and "## Top stories" in report


async def test_a_filter_reason_the_report_does_not_recognise_is_escaped_not_linked(render):
    item = make_item("Odd", "https://e.test/o", "filtered", relevance=3, reason="[x](javascript:alert(1))")
    section = render(state_with(item, written=Written())).split("## Filtered out")[1].split("## Run health")[0]
    assert LINK.findall(section) == []
    assert not re.search(r"(?<!\\)\]\(", section)  # no unescaped ]( that could open a link target
    assert "x" in section


def test_a_malformed_settings_file_exits_2_naming_the_file_with_no_traceback_or_run_folder(site, tmp_path, monkeypatch):
    h = Harness(tmp_path / "radar", site, monkeypatch)
    (h.folder / "settings.yaml").write_text("model: [unclosed\n")
    result = h.run()
    assert result.exit_code == 2
    assert "settings.yaml" in result.output and "line" in result.output
    assert "Traceback" not in result.output
    assert not (h.folder / "runs").exists()


def test_an_error_before_the_run_folder_exists_exits_1_with_no_traceback(site, tmp_path, monkeypatch):
    h = Harness(tmp_path / "radar", site, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("disk exploded")
    monkeypatch.setattr(pipeline.RunFolder, "create", boom)
    result = h.run()
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "went wrong" in result.output
    assert h.fake.unloads == 1


def test_malformed_item_links_never_stop_the_run(h):
    h.write_watch("ai", [h.site.url("/run/badlinks.xml")])
    result = h.run()
    assert result.exit_code == 0, result.output
    assert "Cedar 3.0 ships a faster scheduler" in h.report()
    assert {r["title"] for r in h.rows()} == {"Cedar 3.0 announced", "Plain note"}


async def test_run_health_counts_every_scored_item_the_read_step_did_not_read_even_when_picks_filtered_it(make_ctx, site):
    from topic_radar.model.scripted import ScriptedModel
    from topic_radar.steps.read import read
    items = [make_item(f"Story {n}", site.url("/articles/quoted.html" if n == 0 else f"/never-read/{n}"),
                       "quick hit", relevance=2, to_read=True, watch="ai") for n in range(19)]
    ctx = make_ctx(read_cap=1)
    ctx.model = ScriptedModel().on("read", "Story 0", {"claims": [{"claim": "Cedar is faster.", "quote": QUOTE}]})
    state = state_with(*items)
    await read(ctx, state)
    rank.picks(state.stories)
    assert sum(i.reason == "not in the top picks" for i in items) == 3  # over-cap stories that missed the quick hits
    ctx.watch.name = "Build tooling"
    health = render_report(ctx, state).split("## Run health")[1]
    assert "1 article was read; 18 scored items were not read." in health


WIDGET_TAGS = ["v0.2.1", "v0.9.0", "v0.10.0-rc1", "v0.10.0", "v0.10.1"]  # version order


def release_run(h, read_quote):
    model = ScriptedModel().on("triage", "", {"items": [{"item": 1, "relevance": 2, "reason": "fits", "kind": "release"}]})
    model.on("read", "releases since the last run", {"claims": [{"claim": "Version 0.10.1 fixes a crash.", "quote": read_quote}]})
    model.on("write", "releases since the last run", {
        "headline": "Widget ships fixes", "what_happened": "Version 0.10.1 fixes a crash.", "why_it_matters": "x",
        "read_if": "y", "takeaway": "z"})
    model.on("summary", "", {"bullets": ["Widget 0.10.1 fixes a crash."]})
    h.fake = FakeOllama(model)
    h.write_watch("ai", [h.site.url("/gh/acme/widget/releases.atom")])
    result = h.run()
    assert result.exit_code == 0, result.output
    return [h.site.url(f"/gh/acme/widget/releases/tag/{t}") for t in WIDGET_TAGS]


def test_a_combined_release_in_quick_hits_links_each_release_and_nothing_synthesized(h):
    releases = release_run(h, "this quote is not in the notes at all, so the claim is dropped")
    report = h.report()
    quick = report.split("## Quick hits")[1].split("## Filtered out")[0]
    assert "releases since the last run" in quick
    targets = LINK.findall(quick)
    assert set(releases) <= set(targets)
    assert set(targets) == set(releases)  # no link built from the feed address
    labels = re.findall(r"(?<!\\)\[([^\]]*)\]\(<[^>]*/releases/tag/", quick)
    assert labels[0].startswith("widget: 5 releases")  # the title links to the newest release
    assert labels[1:] == ["v0.2.1", "v0.9.0", "v0.10.0-rc1", "v0.10.0", "v0.10.1"]
    assert {r["address"] for r in h.rows()} <= set(releases)
    assert h.site.url("/gh/acme/widget/releases.atom") not in " ".join(LINK.findall(report))


def test_a_combined_release_in_top_stories_links_each_release_in_its_sources(h):
    releases = release_run(h, "NOTES-0.10.1 fixes a crash.")
    top = h.report().split("## Top stories")[1].split("## Quick hits")[0]
    assert "Widget ships fixes" in top
    assert set(LINK.findall(top)) == set(releases)
