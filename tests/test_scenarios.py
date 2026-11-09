"""T1-T12 over the synthetic feeds in tests/sites/scenarios/, with a scripted model that answers the way the
slice record's outcome table expects. These tests check the code's decisions (combining, grouping, filtering on
known ideas, eligibility); the real model's side of the same table is in test_scenarios_real.py."""
import json
import re
from dataclasses import dataclass

import pytest
from scenario_support import (KNOWN_IDEAS, T2_RELEASE_TITLES, T7_APART, T7_JOINS, TITLES, judge, run_scenarios,
                              story_of, write_folder)
from test_run import FakeOllama

from topic_radar.model.answers import parse_answer
from topic_radar.model.scripted import ScriptedModel, UnmatchedPrompt


@dataclass
class V:
    relevance: int
    kind: str = "news"
    reason: str = "fits"
    repeats: int | None = None  # a known idea's number, 1-based
    adds_new: bool = False


# what a model that agrees with the outcome table says about each item at triage
VERDICTS = {
    TITLES["T1"]: V(3, "release"),
    TITLES["T2"]: V(1, "release", "bug fixes only"),
    TITLES["T3"]: V(3, "news"),
    TITLES["T4"]: V(3, "guidance", "tips for Copilot", repeats=1),
    TITLES["T5"]: V(3, "other", "adds measurements to the subagent idea", repeats=2, adds_new=True),
    TITLES["T6"]: V(2, "release"),
    TITLES["T7"]: V(3, "release"),
    T7_JOINS[0]: V(2), T7_JOINS[1]: V(2),
    T7_APART[0]: V(1, "opinion"), T7_APART[1]: V(1),
    TITLES["T8"]: V(0, "news", "funding news"),
    TITLES["T9"]: V(0, "other", "image generation"),
    TITLES["T10"]: V(2, "other"),
    TITLES["T11"]: V(3, "guidance", "caching basics", repeats=6),
    TITLES["T12"]: V(3, "other"),
}

# one sentence copied from each page that can get read; the extra entries are read only when a wrong model, or a
# wrong decision in the code, sends that page to the reader
QUOTES = {
    TITLES["T1"]: "The new PreCompact hook runs a command just before Claude Code compacts the conversation.",
    TITLES["T3"]: "Cached input tokens now count at one tenth of their normal weight toward the weekly cap, so sessions that reuse a long instruction file stretch much further than before.",
    TITLES["T4"]: "Keep an instruction file in the repository with your project's rules, such as the test command and the code style.",
    TITLES["T5"]: "With subagents, the main session used 168,000 tokens and the subagents used 131,000 between them, 299,000 in total, which is 27 percent less.",
    TITLES["T6"]: "The new parallel helper runs up to 8 independent steps at the same time and waits for all of them before the flow continues.",
    TITLES["T7"]: "Meridian 2 accepts up to 1,000,000 tokens of input in a single request, five times the context of the first Meridian.",
    T7_JOINS[0]: "Meridian Labs released its second model today.",
    T7_JOINS[1]: "The second Meridian model takes a million tokens of input and is cheaper to call, the lab said.",
    TITLES["T8"]: "Lathe, a startup building an AI coding assistant, announced a 120 million dollar Series B led by two venture firms.",
    TITLES["T10"]: "Several commenters say they saw the same overhead when they moved work to subagents.",
    TITLES["T11"]: "Agents send the same instructions and files in every request.",
    TITLES["T12"]: "In the first month, 14 percent of sampled sessions failed without any error message, mostly because the agent stopped after a tool call returned an empty result.",
}


class TitleModel:
    """Triage is answered per item title (the batch holds whichever items it holds); every other step goes to a
    ScriptedModel. An item with no verdict scores 0 and is listed in `unknown`; a page with no scripted reading
    has no claims. So a wrong decision in the code shows up as a wrong decision, not as a crashed run."""

    def __init__(self, verdicts, scripted):
        self.verdicts, self.scripted = verdicts, scripted
        self.unknown: list[str] = []

    async def call(self, step, system, user, schema):
        if step == "read":
            try:
                return await self.scripted.call(step, system, user, schema)
            except UnmatchedPrompt:
                return parse_answer(schema, json.dumps({"claims": []}))
        if step != "triage":
            return await self.scripted.call(step, system, user, schema)
        items = []
        for number, title in re.findall(r"^\[(\d+)\] (.*)$", user, re.MULTILINE):
            if title not in self.verdicts:
                self.unknown.append(title)
            v = self.verdicts.get(title, V(0, "other", "no verdict scripted"))
            row = {"item": int(number), "relevance": v.relevance, "reason": v.reason, "kind": v.kind,
                   "adds_new": v.adds_new}
            if v.repeats:
                row["repeats_idea"] = v.repeats
            items.append(row)
        return parse_answer(schema, json.dumps({"items": items}))


def scripted_rest():
    model = ScriptedModel()
    for title, quote in QUOTES.items():
        model.on("read", f"Article title: {title}", {"claims": [{"claim": "The page reports a change.", "quote": quote}]})
        model.on("write", f"Title: {title}", {
            "headline": "A change was reported", "what_happened": "A change was reported.",
            "why_it_matters": "You follow this topic.", "read_if": "You build with agents.", "takeaway": "Worth a look."})
    return model.on("summary", "", {"bullets": ["Several changes landed."]})


@pytest.fixture
def folder(tmp_path, site):
    path = tmp_path / "Topic Radar"
    write_folder(path, site)
    return path


async def run(folder, monkeypatch, **changed):
    verdicts = {**VERDICTS, **{TITLES[k]: v for k, v in changed.items()}}
    model = TitleModel(verdicts, scripted_rest())
    outcome, state = await run_scenarios(folder, monkeypatch, model="scripted", model_client=FakeOllama(model))
    assert outcome.code == 0, outcome.message
    state.unknown_titles = model.unknown  # for the test that no item outside the table appears
    return state


def item(state, title):
    found = next((i for i in state.items if i.title == title), None)
    assert found is not None, f"{title!r} never reached the run"
    return found


async def test_a_model_that_agrees_with_the_table_passes_all_twelve_scenarios(folder, monkeypatch):
    state = await run(folder, monkeypatch)
    assert state.unknown_titles == []  # every item that reached the run is one the table accounts for
    results = judge(state)
    assert list(results) == [f"T{n}" for n in range(1, 13)]
    assert {name: ok for name, (ok, _) in results.items() if not ok} == {}, results


async def test_five_patch_releases_become_one_item_that_is_not_five_quick_hits(folder, monkeypatch):
    state = await run(folder, monkeypatch)
    from_feed = [i for i in state.items if "/gh/claude-code/" in i.source]
    assert [i.title for i in from_feed] == [TITLES["T2"]]
    assert not any(i.title in T2_RELEASE_TITLES for i in state.items)
    assert from_feed[0].notes.count("Fixed") == 5  # all five releases' notes are in the one item
    assert from_feed[0].decision == "filtered"  # scored 1, so it is not read and not a quick hit


@pytest.mark.parametrize("name, idea", [("T4", 1), ("T11", 6)])
async def test_a_relevant_item_that_repeats_a_known_idea_is_filtered_with_the_idea_as_the_reason(
        folder, monkeypatch, name, idea):
    state = await run(folder, monkeypatch)
    found = item(state, TITLES[name])
    assert found.relevance == 3  # scored relevant, so the filter is the known idea and not low relevance
    assert (found.decision, found.reason) == ("filtered", f"repeats: {KNOWN_IDEAS[idea - 1]}")
    assert not found.article  # filtered before reading


async def test_near_identical_titles_of_one_launch_are_one_story_and_the_other_titles_are_not(folder, monkeypatch):
    state = await run(folder, monkeypatch)
    story = story_of(state, item(state, TITLES["T7"]))
    assert {i.title for i in story.items} == {TITLES["T7"], *T7_JOINS}
    assert len(story.sources) == 2  # the vendor's feed and the news feed
    for title in T7_APART:
        assert story_of(state, item(state, title)) is not story


async def test_a_thread_whose_title_is_a_near_copy_of_a_post_joins_the_posts_story(folder, monkeypatch):
    state = await run(folder, monkeypatch)
    post, thread = item(state, TITLES["T5"]), item(state, TITLES["T10"])
    assert post.title != thread.title
    story = story_of(state, post)
    assert story_of(state, thread) is story and len(story.items) == 2
    assert story.items[0] is post  # the post is read, not the thread


@pytest.mark.parametrize("name", ["T8", "T9"])
async def test_funding_and_image_generation_items_scored_0_are_filtered_and_not_read(folder, monkeypatch, name):
    state = await run(folder, monkeypatch)
    found = item(state, TITLES[name])
    assert found.relevance == 0
    assert (found.decision, found.to_read, found.article) == ("filtered", False, "")


@pytest.mark.parametrize("changed, failing", [
    ({"T1": V(0, "other", "unrelated")}, {"T1"}),
    ({"T4": V(3, "guidance", "tips")}, {"T4"}),  # relevant but no known idea named: not filtered as a repeat
    ({"T5": V(3, "other", "repeats", repeats=2)}, {"T5"}),  # repeats and adds nothing new: filtered
    ({"T8": V(2, "news", "startup news")}, {"T8"}),  # scored relevant: it would be read, so it isn't filtered
])
async def test_the_oracle_fails_exactly_the_scenario_a_wrong_model_gets_wrong(folder, monkeypatch, changed, failing):
    verdicts = {**VERDICTS, **{TITLES[k]: v for k, v in changed.items()}}
    outcome, state = await run_scenarios(folder, monkeypatch, model="scripted",
                                         model_client=FakeOllama(TitleModel(verdicts, scripted_rest())))
    assert outcome.code == 0, outcome.message
    results = judge(state)
    assert {n for n, (ok, _) in results.items() if not ok} == failing, results
