# Topic radar — the primary case: AI engineering

The case topic radar is built and tested against first. The watch file is [`../examples/watches/ai-engineering.yaml`](../examples/watches/ai-engineering.yaml). The MVP spec is [`spec.md`](spec.md).

## Who and what

I use coding agents every day (Claude Code, GitHub Copilot in VS Code, Devin) and build tools that call models at runtime, topic radar itself among them. Each time I check in, I want to know:

1. **Coding agents:** what changed, and how to get more out of them — skills, subagents, instruction files, prompts, hooks, MCP servers, agent modes — **while managing cost**.
2. **Building with models:** agent frameworks, structured output, tool calling, evaluation, small and local models, and the model releases that matter to builders.
3. **Where it's heading:** the arguments and first-hand reports that show the direction of the field.

## What makes an item worth my time

| Worth it | Not worth it |
|---|---|
| A release that changes how I'd use a tool (a new kind of agent, a cheaper mode, a new extension point) | A patch release that only fixes bugs |
| First-hand experience with numbers ("we cut token spend 40% by …") | "10 tips for Claude Code" that repeat the basics |
| Primary sources: release notes, official engineering posts, papers | A news write-up of a release I'll already see from its notes |
| A clear argument about where the field is going, with evidence | Hot takes, funding news, benchmark tables with no method |
| A pattern for building with models that I haven't seen | The same advice again, in new words |

**The hardest requirement is the last row.** Most AI engineering writing repeats a small set of ideas (keep an instruction file, use subagents, use a cheaper model for simple tasks). Address-based repeat checks don't catch that: every rehash is a new article at a new address. So this case needs a check for **ideas I've already seen**, not just items I've already seen. The MVP spec adds it (O7, "Not the same ideas again", AC43–AC45): a known-ideas list per watch, seeded from the watch's `already_know` and grown from each report's top stories and my "I already know this" feedback, which triage checks every item against.

**Releases need combining.** Claude Code ships releases most days. Seven separate quick hits for one tool is noise, so the MVP combines a feed's releases from one run into one item ("Claude Code: 6 releases since the last run") and reads their notes together (spec, AC46).

## Sources

The seeds in the watch file are starting points. `topic-radar init` confirms which have feeds; those without a feed are reported as "no feed found" and wait for stage 2, which reads listing pages through the browser.

**Checked on 2026-11-09:** Anthropic news, Anthropic engineering and the Devin blog have no feed, so in the MVP 3 of the 6 coding-agent seeds are missing. The cost is real: a pricing or plan-limit change (T3) reaches the MVP only second-hand, through Simon Willison or Hacker News, usually a day or two later. The LangChain blog's feed exists but isn't linked from the blog page, so the watch seeds the feed's address directly. All other seeds return a feed.

| Group | Seeds | Expected new items per 7 days |
|---|---|---|
| Coding agents | Claude Code releases, Anthropic engineering and news, GitHub Copilot changelog, VS Code updates, Devin blog | ~15–25 items, several releases (fewer in the MVP: three of these have no feed) |
| Building with models | LangGraph releases, LangChain blog, Ollama releases, Hugging Face blog, OpenAI news | ~20–30 |
| First-hand writers | Simon Willison, Latent Space, Hamel Husain, Eugene Yan, Martin Fowler | ~40–60 (Simon Willison posts a lot) |
| Discussion | Hacker News stories with 300+ points | ~60–80 |
| **Total** | | **~150–200 new items**, of which the report should keep 7 top stories and up to 15 quick hits |

The Hacker News feed is also the first real check of the "may have missed items" rule (AC10): if more 300-point stories appear between runs than the feed lists, the run says so. Running more often avoids it.

Stage 2 adds the watch's `searches` and `mode: wide`, so new places (an engineering team's blog, a conference talk write-up) are found and proposed as sources.

## What a good report looks like for this case

These scenarios are the expected outcomes. Each becomes an offline test (a synthetic feed item and a scripted model answer, checking the code's decision) and a check on reference runs with the real model.

| # | Item | Expected |
|---|---|---|
| T1 | A Claude Code release that adds a new extension point (a new kind of hook, a new subagent setting) | Top story; "Read if" names the part of the release notes to read |
| T2 | Five Claude Code patch releases since the last run, bug fixes only | Combined into one item; quick hit or filtered, never five quick hits |
| T3 | A pricing or rate-limit change for a model or a coding agent plan | Top story: it's about cost, the part of the interests that's marked "above all" |
| T4 | "10 ways to get more from GitHub Copilot", restating instruction files and choosing models | Filtered, reason "repeats: keep an instruction file…" |
| T5 | A first-hand post measuring token cost before and after moving work to subagents, with numbers | Top story, even though "subagents" is a known idea: it adds measurements |
| T6 | A LangGraph release with a new feature for running steps in parallel | Top story or quick hit, depending on what else is new |
| T7 | The same model launch covered by the vendor's post, Simon Willison and three news sites | MVP: items with near-identical titles are one story, the rest stay separate items. Stage 5 (clustering): one story, the vendor's post first, Simon Willison's as the first-hand source, the news sites folded in |
| T8 | A funding round for an AI coding startup | Filtered, reason "funding news" |
| T9 | An image-generation model release | Filtered, reason "image generation" |
| T10 | A Hacker News thread about a post already in the report | Grouped with that post's story, not a separate item |
| T11 | An article I marked "I already know this" in an earlier report, republished on another site | Filtered as a repeat of a known idea |
| T12 | A post on evaluating agents in production with a method and results | Top story or quick hit; "Read if" names the method section |

## How this case is used for testing

| Kind of test | What it uses | Checks |
|---|---|---|
| Offline (every change) | Synthetic feeds in `tests/sites/` written for T1–T12, never copies of real articles; the scripted model | The code's decisions: combining releases, grouping, filtering on known ideas, ranking, caps, word budget, files written |
| Real model (`-m real_model`) | The same synthetic feeds; the real model | The prompts produce parseable answers and the expected decisions for T1–T12 |
| Reference runs (manual) | The real watch, real feeds, a real run | Run time and memory (AC41), a report readable in under 5 minutes whose stories check out against their articles (AC42); each run folder kept as a record |
| Over time | My feedback on real runs | Share of top stories marked useful; items pulled back from "Filtered out"; how often "I already know this" is needed (it should fall) |
