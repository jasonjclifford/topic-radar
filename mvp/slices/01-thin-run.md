# Slice 1 — one thin run, start to finish, on real feeds

**Status:** in-progress
**Spec:** [`../spec.md`](../spec.md)

**Value claim:** You will be able to run `topic-radar run ai-engineering` against the real watch and get a plain `report.md` (top stories, quick hits, filtered counts) and a run folder showing every prompt, answer, article and decision, so report quality can be judged before the rest is built. Try it: run with a read cap of 3, open `runs/<time>/report.md`, and check each top story against its `articles/*.md` and `items.csv`; `uv run pytest -m real_model` says how many of T1–T12 the default model gets right.

**Covers:** AC12, AC13, AC14, AC15, AC16, AC17, AC22, AC28, AC44, AC46, AC50, AC51

**Partially covers:** AC1, AC5, AC9, AC18, AC19, AC20, AC23, AC25, AC26, AC27, AC37, AC38, AC39, AC40, AC43, AC47, AC48, AC49

## What the run does

1. Load one watch from `<folder>/watches/<watch>.yaml` (AC1; invalid file → message naming the file, line and missing field; `searches` and `mode` noted as skipped).
2. Read every seed directly as a feed over HTTP (no `init`, no `sources/`). A seed that fails or isn't a feed is a failed source in `notes.md`; the run continues (AC9 in part).
3. Keep items published within `first_run_lookback` before the run started (AC5 in part; no history, so every run is a first run). Normalize addresses for in-run duplicates only.
4. Combine one project's releases in one feed into one item (AC46).
5. Triage in batches of up to 10 with known ideas numbered (AC12, AC44); known ideas come from `already_know` bullets split by code, plus `known/<watch>.md` if present, read only (AC43 in part).
6. Group near-identical titles first (AC17; grouping runs before reading, so one story is read once), then read stories scored 2–3 in ranking order up to `read_cap`: fetch, extract, chunk, claims with quotes, quote check, article files (AC13–AC16). Tune the read prompt (the probe kept 3 of about 8 claims).
7. Rank and cap (AC19 in part: no update ordering).
8. Write top stories from kept claims and the watch's interests and not_interested (AC23 in part: no profile file yet), the 30-second summary from the stories; number check (AC50).
9. Write `report.md` (AC18, AC20 in part), `notes.md`, `items.csv` (AC25–AC27 in part), `articles/`, `details/` with `events.jsonl` (AC28). Last model call unloads the model (AC39 in part). Exit 0 when a report was written (AC40 in part).

Web text goes inside delimiters (with literal delimiter tags neutralized) and only schema-matching answers are used; fetches are guarded: http/https only, each redirect hop checked, private addresses refused, 5 MB and content-type limits (AC49 in part: refusals go to notes.md, not sources.csv). Before collecting, a preflight checks that Ollama answers and the model is installed, and exits 2 with the fixing command (AC37 in part). The report opens with a banner when anything failed (AC47 in part), and the first progress line says Ctrl-C is safe (AC48 in part).

## Decisions

- In the T1–T12 real-model test, "top story" passes when the item is scored 2–3 and read with at least one kept claim (top-story eligible), not when it lands in the final picks: the 3-per-watch cap would make T1, T3, T5 and T7 compete for slots and the test would measure the cap, not the prompts. The report itself still applies the cap.
- Whether "Read if" names the right section (T1, T12) is judged by eye in the run folder.
- No visual surface: command line and a Markdown file.

## Scenario outcomes (T1–T12)

Written before the real model first ran over the scenario feeds (`tests/sites/scenarios/`), and not changed after. Each scenario's pass rule is evaluated on the run state after the whole pipeline, from the scenario's own item(s). The scenario watch is `tests/scenario_support.py`'s own fresh watch (interests, not-interested and nine known ideas), not a copy of the example watch. The scripted-model test passes every row with a model that answers as the table expects; the real-model test needs 10 of 12 rows to pass with `gemma4:e4b-mlx`.

Terms: **eligible** = the item's story has an item that was scored 2–3, read, and has at least one kept claim. **Quick-hit candidate** = an item of the story was scored 2–3 and read without failing, and the story ends as `top story` or `quick hit` (not `filtered`, not `failed`). **Repeat filter** = decision `filtered` and reason starting `repeats: `.

| # | Item (synthetic) | Expected code decision | Pass rule |
|---|---|---|---|
| T1 | A coding-agent release adding a new hook type and a per-subagent tool limit | eligible (top story candidate) | story eligible |
| T2 | Five patch releases of one coding agent in one `releases.atom`, bug fixes only | combined into one item "<project>: 5 releases since the last run"; filtered or at most a quick hit, never top | exactly one item from that feed, titled with "5 releases since the last run", none of the five release titles as items, and not eligible |
| T3 | A plan price and usage-limit change for a coding agent | eligible | story eligible |
| T4 | "10 ways to get more from GitHub Copilot", restating instruction files and model choice | `filtered`, reason "repeats: <known idea 1>" | repeat filter, with the reason naming the instruction-file idea |
| T5 | A first-hand post measuring token cost before and after moving work to subagents, with numbers | eligible; triage records it as adding to known idea 2 (subagents), so it is not filtered as a repeat | story eligible, and its decision is not the repeat filter |
| T6 | An agent-framework release (fictional "Relaywork 0.9") with a parallel-steps feature | eligible or quick-hit candidate | story eligible, or a quick-hit candidate |
| T7 | One model launch covered by the vendor, a first-hand writer and three news sites; three of the five titles are near-identical | the three near-identical titles are one story (grouping, code); the writer's and the fifth title's items stay separate stories; the grouped story is eligible | the vendor item's story holds at least 2 items and at most 3 (the near-identical ones), the other two items are in stories of their own, and the grouped story is eligible |
| T8 | A funding round for an AI coding startup | `filtered`, not read | decision `filtered`, not scored 2–3, no article |
| T9 | An image-generation model release | `filtered`, not read | decision `filtered`, not scored 2–3, no article |
| T10 | A discussion-site thread whose title is a near-copy of T5's post title | grouped with T5's story, not a separate story | the thread item and the T5 item are in the same story, which holds at least 2 items |
| T11 | An article on prompt caching basics (known idea 6), marked as already known, republished on another site | `filtered`, reason "repeats: <known idea 6>" | repeat filter, with the reason naming the prompt-caching idea |
| T12 | A first-hand post on evaluating agents in production, with a method and results | eligible or quick-hit candidate | story eligible, or a quick-hit candidate |

Not mechanical: whether "Read if" names the method section (T12) or the part of the release notes to read (T1) is judged by eye in the run folder.

## Real-model results (T1–T12, read prompt)

Run on 2026-11-09 with `gemma4:e4b-mlx` (`uv run pytest -m real_model tests/test_scenarios_real.py -s`), fixed clock, default settings (read cap 25, 4 chunks of 3000 characters), against the outcome table above, which was committed before the first real run and not changed after.

**Score: 12 of 12** (needs 10), with the first read prompt (v0) and with the tuned one (v3). A whole scenario run (about 20 model calls: 2 triage batches, 8 reads, 3 stories, 1 summary) takes 56 to 67 seconds; the recall probe is one call of 5 to 17 seconds.

| # | Result | What the model did |
|---|---|---|
| T1 | match | scored 3, read, kept claims: eligible |
| T2 | match | one combined item, scored 0 ("minor patch releases"): filtered |
| T3 | match | scored 2, eligible |
| T4 | match | scored 1, repeat filter naming the instruction-file idea |
| T5 | match | scored 2–3, "adds to a known idea (subagents)", eligible |
| T6 | match | scored 2, eligible |
| T7 | match | three near-identical titles in one story (the other two apart), eligible |
| T8 | match | scored 0, not read |
| T9 | match | scored 0, not read |
| T10 | match | thread grouped with T5's post (2 items) |
| T11 | match | repeat filter naming the prompt-caching idea (scored 2) |
| T12 | match | scored 2, eligible |

Code-side check that the test can fail: with the repeat filter disabled and the grouping threshold raised to 101 in the code, the same real run scores 9 of 12 (T4, T7, T10 miss) and the test goes red. The real model alone cannot tell whether the tolerance of two misses hides a weak prompt, so the per-scenario table is printed on every run.

**Read-prompt recall.** A fixed chunk (the T1 page, 1,167 characters, eight facts a reader would want: the new hook, its 2,000-character notes, the 30-tool-call stop, the small-model default, the 60-second hook timeout, the end of `hooks.json` support, the `/context` change, a crash fix). Recall is how many of the eight appear in the quote of a claim whose quote the quote check keeps. One call per version, temperature 0.

| Version | Change | Kept of 8 expected | Claims returned / with a quote found |
|---|---|---|---|
| v0 | the Task 5 prompt ("every claim the reader would care about") | 4 | 4 / 3 |
| v1 | go paragraph by paragraph, one claim per fact, a quote of one sentence | 5 | 6 / 5 |
| v2 | sentence by sentence; the example answer shows two claims | 5 | 5 / 4 |
| v3 (kept) | look back over every heading and paragraph, including the last, before answering; one sentence per quote, with backslashes | 6 | 6 to 7 / 5 to 6 |
| v4, v5 | v3 plus "do not stop early; short sections near the end hold small fixes", and a paragraph count | 6 | 5 / 5 |

v3 is kept because v4 and v5 add words and no recall. The two facts still missed are a minor bug fix and a one-line `/context` change; the reader's not-interested list names small bug fixes, so leaving the fix out is defensible.

**Finding (fixed in the commit "quote check reads Markdown escapes as plain characters"):** `trafilatura`'s Markdown output escapes underscores (`max_tool_calls` arrives as `max\_tool\_calls`), the model copies the unescaped identifier, and the quote check then drops a correct claim. In the probe this costs one claim in every version. `text.normalize_quote` now treats a backslash escape of Markdown punctuation as the plain character.

## Real run (real feeds, read cap 3)

Run on 2026-11-09 at 07:32 local, `examples/watches/ai-engineering.yaml` copied into a scratch Topic Radar folder outside the repository, `topic-radar run ai-engineering --folder <scratch> --read-cap 3`, default model `gemma4:e4b-mlx`.

- **Outcome:** exit 0, `report.md`, `notes.md` ending "Done.", `items.csv`, `articles/` and `details/` (27 prompt/answer pairs: 17 triage, 7 read, 2 write, 1 summary; plus `events.jsonl`). Wall clock 6 min 18 s: collecting 2 min 23 s, triage 2 min 39 s (17 batches), reading 1 min 1 s, writing and summary 14 s.
- **Sources:** 13 of 17 seeds read. The 4 that failed are web pages, not feeds (two blog index pages, a changelog label page, a news page); the report opened with the banner and Run health named each one. The seeds need their feed addresses (or a later slice's discovery).
- **Items:** 169 new items: 2 top stories, 15 quick hits, 151 filtered (85 scored 0, 26 scored 1, 40 not in the top picks), 1 failed (the site answered 403 to the article fetch).
- **Top stories, checked against their article files:** S1 (agent-written PR descriptions hidden behind `<details>`) has 5 kept claims, 0 dropped, and its text matches them. S2 (a 284B model on 64 GB of RAM, no GPU) has 10 kept claims and 24 dropped; every number in its text is in its claims.
- **Quote drops:** the 24 dropped on S2 came from a README of HTML stat blocks and Markdown tables; the model stitched quotes across cells and tags (`56.56 GiB <sub>…</div>`, `name | value`) that aren't contiguous in the extracted text. The check did its job; the cost is recall on table-heavy pages.
- **What the report showed that the tests didn't:**
  - Collecting printed nothing for over 2 minutes, and failed sources were only noted at the end (fixed in "progress lines while collecting; one remedy per failed source").
  - Each failed-source Run health line repeated its remedy (fixed in the same commit).
  - Hacker News feed summaries are boilerplate ("Article URL: … Comments URL: … Points: …"), so those quick-hit lines say little, and the escaped addresses in them read as `https:\//…`.
  - Several quick hits are model launches or framework marketing that the watch's interests arguably don't want (judged by eye; tuning triage is outside this slice).

## Notes for the spec

Places where building this slice settled something the spec or plan leaves open. The spec's text is unchanged; each is a candidate edit.

- **AC14:** "at most `chunk_chars`" and "never inside a line" can't both hold for a single line longer than `chunk_chars`. The code keeps the line whole, as its own oversize chunk.
- **AC46:** the plan's version-title pattern `^v?\d+(\.\d+)+\b` matches a blog post titled "2.0 thoughts", so the code requires the version to be the whole title or to be followed by `:` (with an optional `-rc1`-style suffix).
- **AC44:** "repeats: <idea n>" is read as the idea's text, not its number.
- **AC15:** quotes are checked against the chunk they came from, as the AC says (`architecture.md` says "the text"). The check also reads Markdown backslash escapes as the plain character.
- **Primary case:** 4 of the AI engineering watch's 17 seeds are web pages, not feeds (see Real run).
- **AC50:** the 30-second summary's bullets aren't number-checked; the AC names top-story text only.

## Deferred

`init`, cursors, history, conditional requests, broken sources, end-of-run state writes, feedback, profiles, `find`, `doctor`, `open`, HTML report, `report.json`, `sources.csv`, `model: auto`.
