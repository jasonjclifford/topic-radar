"""The T1-T12 scenario watch, how to run it over tests/sites/scenarios/, and the oracle that judges a run.

The oracle mirrors the table in mvp/slices/01-thin-run.md ("Scenario outcomes"): each rule is
evaluated on the run state after the whole pipeline, from the scenario's own item(s)."""
from datetime import datetime, timezone

from topic_radar import pipeline
from topic_radar.state import Item, RunState, Story

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

SEED_PATHS = [
    "/scenarios/feeds/changelog.xml",
    "/scenarios/gh/claude-code/releases.atom",
    "/scenarios/gh/relaywork/releases.atom",
    "/scenarios/feeds/copilot.xml",
    "/scenarios/feeds/vendor.xml",
    "/scenarios/feeds/writers.xml",  # before hn.xml, so a story's first item is the post and not its thread
    "/scenarios/feeds/news.xml",
    "/scenarios/feeds/repost.xml",
    "/scenarios/feeds/hn.xml",
]

KNOWN_IDEAS = [
    "Keep an instruction file with the project's rules for the agent.",
    "Subagents keep the main context small and let searches run side by side.",
    "Use a smaller or cheaper model for simple tasks.",
    "Give the agent tests to run so it can check its own work.",
    "Plan before the agent edits code.",
    "Prompt caching lowers the cost of repeated context.",
    "MCP lets agents call outside tools.",
    "For small models, build each prompt fresh instead of extending a conversation.",
    "Ask small models for structured output and validate it in code.",
]

WATCH = """name: Scenario watch

interests: |
  Where AI engineering is heading, for a developer who works with coding agents all day and builds
  software that calls models while it runs.

  Coding agents such as Claude Code and GitHub Copilot: new capabilities and ways to get more out of
  them (hooks, subagents, skills, instruction files, prompt files, MCP servers, plan mode, background
  agents). Above all, keeping cost and usage down, including pricing, plan changes and usage limits,
  without losing quality.

  Building with models: agent frameworks, structured output, tool calling, testing and evaluating
  model-driven code, small local models, reliability patterns, and what changed in model releases
  that matters to builders (context length, price, speed, tool use).

  Worth reading: first-hand experience with real numbers, official release notes and engineering
  posts, and clear arguments about where the field is going.

not_interested: |
  Listicles and "top 10 tips" that repeat the basics. Funding rounds, valuations, executive moves,
  lawsuits. AI art and image or video generation. Benchmarks with no method. Vendor marketing with
  no technical detail. Hot takes. Patch releases that only fix small bugs.

already_know: |
  Things I already know:
{known}

seeds:
{seeds}
first_run_lookback: 7d
"""

SETTINGS = "request_delay_seconds: 0\ntimeout_seconds: 5\n"

# the title each scenario's item has in its feed (T2's is made by combining the releases)
TITLES = {
    "T1": "Claude Code 2.4 adds a PreCompact hook and per-subagent tool limits",
    "T2": "claude-code: 5 releases since the last run",
    "T3": "Claude Code Max plans move to weekly usage limits with new per-model caps",
    "T4": "10 ways to get more from GitHub Copilot",
    "T5": "Measuring token cost before and after moving work to subagents",
    "T6": "Relaywork 0.9 adds parallel steps",
    "T7": "Meridian 2 launches with a one million token context window and lower prices",
    "T8": "Startup Lathe raises 120 million dollars to build an AI coding assistant",
    "T9": "Prism 5 turns text prompts into photorealistic images in two seconds",
    "T10": "Measuring token cost before and after moving our work to subagents",
    "T11": "How prompt caching cuts the bill on long agent sessions",
    "T12": "Evaluating coding agents in production: a sampling method and what it found",
}
# T7's other items: two near-identical titles that join the story, and two different ones that stay apart
T7_JOINS = ["Meridian 2 launches with a one million token context window, and lower prices",
            "Meridian 2 launches with one million token context window and lower prices"]
T7_APART = ["First impressions of Meridian 2 after a week of long-context testing",
            "Meridian 2 is here: what developers need to know"]
T2_RELEASE_TITLES = [f"v2.3.{n}" for n in range(1, 6)]


def write_folder(folder, site) -> None:
    (folder / "watches").mkdir(parents=True)
    (folder / "settings.yaml").write_text(SETTINGS)
    (folder / "watches" / "scenarios.yaml").write_text(WATCH.format(
        known="".join(f"  - {idea}\n" for idea in KNOWN_IDEAS).rstrip("\n"),
        seeds="".join(f"  - {site.url(p)}\n" for p in SEED_PATHS)))


async def run_scenarios(folder, monkeypatch, *, model_client=None, model=None):
    """Run the scenario watch end to end; returns the Outcome and the run state after the last step."""
    captured: list[RunState] = []

    async def capture(ctx, state):
        captured.append(state)
        return state

    monkeypatch.setattr(pipeline, "STEPS", [*pipeline.STEPS, capture])
    outcome = await pipeline.run_watch("scenarios", folder, model=model, model_client=model_client,
                                       allow_loopback=True, clock=lambda: NOW)
    return outcome, (captured[0] if captured else None)


def story_of(state: RunState, item: Item) -> Story:
    return next(s for s in state.stories if any(i is item for i in s.items))


def _find(state: RunState, title: str) -> Item | None:
    return next((i for i in state.items if i.title == title), None)


def _candidate(story: Story) -> bool:
    return any(i.to_read and i.decision in ("top story", "quick hit") for i in story.items)


def _repeat(item: Item, idea: str) -> bool:
    return item.decision == "filtered" and item.reason == f"repeats: {idea}"


def _unscored_and_unread(item: Item) -> bool:
    return item.decision == "filtered" and not item.to_read and not item.article


def judge(state: RunState) -> dict[str, tuple[bool, str]]:
    """Per scenario: (passed, why). A scenario whose item never reached the run fails, so a missing
    item is never counted as a match."""
    out: dict[str, tuple[bool, str]] = {}

    def verdict(name, ok, why):
        out[name] = (bool(ok), why)

    def need(name):
        item = _find(state, TITLES[name])
        if item is None:
            verdict(name, False, "the item never reached the run")
        return item

    def describe(item):
        return f"decision {item.decision!r}, relevance {item.relevance}, reason {item.reason!r}, eligible {story_of(state, item).eligible}"

    for name in ("T1", "T3"):
        if item := need(name):
            verdict(name, story_of(state, item).eligible, describe(item))
    for name in ("T6", "T12"):
        if item := need(name):
            story = story_of(state, item)
            verdict(name, story.eligible or _candidate(story), describe(item))
    if item := need("T5"):
        verdict("T5", story_of(state, item).eligible and not item.reason.startswith("repeats:"), describe(item))

    combined = [i for i in state.items if "/gh/claude-code/" in i.source]
    if len(combined) == 1 and combined[0].title == TITLES["T2"] and not story_of(state, combined[0]).eligible:
        verdict("T2", True, describe(combined[0]))
    else:
        verdict("T2", False, "items from the releases feed: " + "; ".join(i.title for i in combined))

    if item := need("T4"):
        verdict("T4", _repeat(item, KNOWN_IDEAS[0]), describe(item))
    if item := need("T11"):
        verdict("T11", _repeat(item, KNOWN_IDEAS[5]), describe(item))
    for name in ("T8", "T9"):
        if item := need(name):
            verdict(name, _unscored_and_unread(item), describe(item))

    if item := need("T7"):
        story = story_of(state, item)
        titles = {i.title for i in story.items}
        apart = [_find(state, t) for t in T7_APART]
        ok = (2 <= len(story.items) <= 3 and titles <= {TITLES["T7"], *T7_JOINS}
              and all(a is not None and story_of(state, a) is not story for a in apart) and story.eligible)
        verdict("T7", ok, f"{len(story.items)} items in its story, eligible {story.eligible}")
    post, thread = _find(state, TITLES["T5"]), _find(state, TITLES["T10"])
    if post and thread:
        story = story_of(state, post)
        verdict("T10", story is story_of(state, thread) and len(story.items) >= 2,
                f"the thread's story holds {len(story_of(state, thread).items)} item(s)")
    else:
        verdict("T10", False, "the thread or its post never reached the run")
    return dict(sorted(out.items(), key=lambda kv: int(kv[0][1:])))
