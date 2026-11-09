# Slice 1 plan — one thin run, start to finish, on real feeds

**Slice:** [`01-thin-run.md`](01-thin-run.md) · **Spec:** [`../spec.md`](../spec.md) · **Status:** ready

## Goal

`topic-radar run <watch>` reads one watch's seeds as feeds over HTTP, triages the new items with the local model, reads the best few in chunks with the quote check, and writes `report.md` plus a run folder (`notes.md`, `items.csv`, `articles/`, `details/`). A real-model test over synthetic feeds scores T1–T12.

## Delta design

A greenfield `uv` package laid out as `architecture.md` says, built only as far as this slice needs: `watch`, `settings`, `web`, `readers/feed`, `text`, `model/` (protocol, Ollama, scripted, answers, prompts, a recording wrapper), `steps/` (collect, normalize, triage, group, read, write, assemble), `rank`, `store/runfolder`, `report/render` (Markdown only), `context`/`state`, `pipeline`, `cli`. Steps are async functions over a run context and a run state, called in a fixed list. Nothing writes state outside the run folder (no history, sources or known-idea writes in this slice), so AC11's ordering doesn't arise yet.

### Data flow

```
preflight (Ollama answers, model installed) ─► collect (each seed as a feed, guarded fetch)
  ─► normalize (lookback, address, in-run dedupe, combine releases)
  ─► triage (batches ≤10, known ideas numbered) ─► group (rapidfuzz ≥90)
  ─► read (rank.read_order, up to read_cap: fetch, trafilatura, chunk, claims, quote check)
  ─► write (rank.picks, story texts, 30-second summary, number check)
  ─► assemble (report.md, items.csv, notes "Done.")
```

**Group runs before read**, a change from `architecture.md`'s step order. Read order needs the number of sources (AC19's ranking), which only exists after grouping, and grouping first means one story is read once instead of once per near-identical copy. AC17 groups by titles, so nothing in it needs the read. `architecture.md` gets the same change.

Every step appends lines to `notes.md` (echoed to the terminal) and events to `details/events.jsonl`. Progress is per batch and per article: "Triage: batch 3 of 20", "Reading 2 of 3: <title>". The first line says that stopping with Ctrl-C is safe. A recording wrapper around any `ModelClient` writes each prompt and answer to `details/`, so the scripted and real clients share that path.

### Key decisions

- **The Topic Radar folder** is `--folder` (default: the current directory). `watches/`, `runs/` and an optional `settings.yaml` live in it. A missing watch names the folder searched and lists the watches it found.
- **Preflight** (AC37 in part): before collecting, `GET /api/tags`. If Ollama doesn't answer, the run exits 2 with "Ollama isn't running. Start it with: ollama serve". If the model is missing, it exits 2 with "The model <m> isn't installed. Install it with: ollama pull <m>". `doctor` comes later.
- **Seeds are read as feeds directly.** A seed whose body is a web page gives the failed source "this address is a web page, not a feed: replace it with the feed's address or remove it from seeds".
- **Fetch guard** (AC49 in part):
  - only `http`/`https`;
  - redirects followed by hand, each hop checked;
  - loopback, private and link-local addresses refused;
  - bodies over 5 MB refused (streamed);
  - only HTML, XML, RSS, Atom or plain text accepted.

  Tests allow loopback through a run-context flag that only tests set (never a setting).
- **Delimiters:** web text placed inside `<items>`, `<chunk>` or `<article>` has any literal opening or closing tag of those names neutralized first.
- **Known ideas** are the `already_know` text's `- ` bullets, split by code, plus the lines of `known/<watch>.md` if present (read only). The spec's split by model (AC43) comes with the known-ideas slice.
- **The profile** in prompts is the watch's `interests` and `not_interested` text until profiles exist (AC35).
- **Combined releases** (AC46): a feed whose address ends in `/releases.atom`, or whose item titles all look like version numbers (`^v?\d+(\.\d+)+\b`), with two or more items in the run becomes one item. The project name comes from the feed address (`github.com/<owner>/<project>`) or the feed title. The notes come from each entry's feed content, joined in version order, and are read without a page fetch.
- **Top-story eligibility vs picks:** code records `eligible` (scored 2–3, read, with at least one kept claim); `rank.picks` applies the caps. The real-model test checks eligibility. T1–T12's expected outcomes are written into the slice record before that test (Task 8).
- **Model-call failures** after triage: a read call that times out or still fails to parse after one retry makes the item `failed` with the error, not a quick hit. A failed story call gives the headline and quoted claims, as the number check does. A failed summary call leaves out "In 30 seconds" and puts a line in Run health. All of them are counted in Run health.
- **A run that hits an error it didn't expect:** the traceback goes to `details/error.txt` and `notes.md` gets a plain line. No `report.md` is written and there's no "Done.". The model is unloaded and the exit code is 1.
- **The report** shows a banner before "In 30 seconds" when any source failed or any item was `not scored` or `failed` (AC47 in part). Each top story shows its id and the path of its article file. Top stories has an explicit empty state ("N items were read; none had a claim backed by a quote"). Run health gives the read cap and how many scored items went unread. Links are only `http`/`https`. At the end, the terminal prints the full path of `report.md` and how to open it.
- **File names** in `articles/` and `details/`: a number plus a slug of `[a-z0-9-]`, at most 80 characters.
- **The read prompt** asks for every claim the reader would care about (each new feature, number, date, change in behaviour), at most 12 per chunk, each with a quote of one or two sentences copied exactly. It also asks for `repeats_idea` and `adds_new` (AC44's after-reading rule). Tuning it is part of Task 8.
- **Prompts** live in `model/prompts/*.md` with `{placeholders}`. The scripted model matches on stable markers (the step name and an item's title), not prompt wording, and raises when no canned answer matches.
- **The clock** is on the run context, so tests use a fixed time.

## Given Axioms

- Ollama 0.40 on a 16 GB M4; `gemma4:e4b-mlx` is installed and is the default; `gemma4:e4b-it-qat` and `gemma4:e2b-mlx` are installed (user-stated, this session; `ollama list`).
- Structured output works with a JSON schema in `format`, `think: false`, `temperature: 0`; e4b scored 10/10 on a 10-item triage probe; the read prompt kept only 3 of about 8 claims (user-stated; `spec.md` "Spec review", model check).
- `trafilatura.extract(html, output_format="markdown", include_formatting=True)` keeps `#`/`##` headings (checked this session with trafilatura 2.3.1); feedparser 6.0.14.
- Stack and package layout: `architecture.md` "Stack" and "Package layout". Prompt/answer rules: `architecture.md` "Model calls". Quote check: `architecture.md` "The quote check".
- Early maturity, nothing to migrate (`CLAUDE.md`, "Project Maturity"): no migration or backfill tasks.
- Tests: offline with a local test feed server and a scripted model; real-model tests marked `real_model` and excluded by default (user-stated rule).

## Known Unknowns

- [ ] Whether `gemma4:e4b-mlx` reaches 10 of 12 on T1–T12 with these prompts (blocks: Task 8's pass; the code is done without it).
- [ ] How far the read prompt's claim recall can be raised (blocks: Task 8).
- [ ] Whether GitHub `releases.atom` entries carry the release notes in `content` that feedparser exposes (blocks: Task 2's real-feed check; offline tests use synthetic Atom).

## Tasks

Each task is test-first: write the tests, run them and show them failing for the stated reason, then implement, then run the task's tests plus the tests of the modules it calls.

### Task 1 — Project, settings, watch loading, run context and state

**Delivers:** `pyproject.toml` (Python 3.12, `uv`, the `topic-radar` script, pytest config with the `real_model` marker deselected by default), `settings.py` (defaults, plus an optional `settings.yaml` that overrides them), and `watch.py`. The watch loader returns a `Watch` or a skip message. It also delivers `context.py` (settings, watch, folder, clock, HTTP client, model client, run folder, the test-only loopback flag) and `state.py` (`Item`, `Story`, `Claim`, `Article`, the run state, the decision vocabulary), which every later step uses.
**Test contract:**
- A valid watch file loads, with `first_run_lookback` defaulting to 7 days, and `14d` parsing to 14 days.
- A file that isn't valid YAML is skipped with a message naming the file and the line.
- A missing `name`, or a missing `interests`, gives a message naming the field.
- `searches` and `mode` produce the note "skipped until a later version".
- `already_know` bullets split into known ideas, and the lines of `known/<watch>.md` are added to them.
- A `settings.yaml` value overrides its default.
- An item's decision outside the vocabulary is refused.
**Files:** `pyproject.toml`, `src/topic_radar/{__init__,settings,watch,context,state}.py`, `tests/test_watch.py`, `tests/test_settings.py`, `tests/test_state.py`

### Task 2 — Test feed server, guarded fetch, collect and normalize

**Delivers:**
- A pytest fixture that serves `tests/sites/` over local HTTP, with failure statuses, slow responses and redirects.
- `web.py`: the guarded httpx fetch, pacing, `normalize_address`.
- `readers/feed.py`: fetches and parses a feed into `Item`s.
- `steps/collect.py`.
- `steps/normalize.py`: the lookback against the context clock, in-run dedupe by normalized address, redirect resolution with HEAD falling back to GET, combined releases.

**Test contract:**
- Items older than the lookback are not new, and newer ones are.
- `utm_*`/`fbclid` are stripped, case and the trailing `/` are normalized, and two items with the same address are one item.
- A redirect resolves to its final address; a failed HEAD falls back to GET; a failed resolve keeps the feed's address.
- A 500, a timeout and an HTML page each give a failed source with a plain error, while the other sources still yield their items.
- The fetch guard refuses each of these with the reason recorded:
  - a `file:` address;
  - a redirect to a private address, when the loopback flag is off;
  - a body over 5 MB;
  - an `image/png` body.
- Five versioned entries in a `releases.atom` feed become one item titled `<project>: 5 releases since the last run`, with its notes in version order and a link to each release.
- A single release stays an ordinary item, and a blog feed with a title like "2.0 thoughts" is not combined.
**Files:** `src/topic_radar/web.py`, `readers/{base,feed}.py`, `steps/{collect,normalize}.py`, `tests/conftest.py`, `tests/sites/…`, `tests/test_web.py`, `tests/test_collect.py`, `tests/test_normalize.py`

### Task 3 — Model client, scripted model, recording wrapper, preflight, run folder

**Delivers:**
- `model/client.py`, the `ModelClient` protocol: `call(step, system, user, schema) -> Answer`.
- `model/ollama.py`: posts to `/api/chat` with `format`, `think: false`, `temperature: 0`, `num_ctx` and a timeout. It also has `unload()` (`keep_alive: 0`) and `preflight(model)` (`/api/tags`).
- `model/scripted.py`: matches on step and marker, and raises when nothing matches.
- `model/recording.py`: wraps any client and writes `details/<step>-<NNN>-prompt.txt` / `-answer.txt`, with one retry on a parse failure.
- `model/answers.py`: pydantic models with lenient parsing.
- `store/runfolder.py`: makes the run folder (`YYYY-MM-DD-HHMM`, `-2` on a clash, an atomic `mkdir`), appends to `notes.md`, which is echoed to the terminal with plain words only, and writes `events.jsonl`.

**Test contract:**
- Against a fake Ollama HTTP server, the client sends the required fields and parses the answer.
- A timeout gives an `Answer` with an error.
- Preflight gives the "ollama serve" message when nothing listens, and the "ollama pull" message when the model is missing.
- An unparseable answer is retried once, then recorded as failed.
- A number sent as text and an empty placeholder parse leniently.
- The scripted model raises on an unmatched prompt.
- Each call through the wrapper writes one prompt/answer pair, numbered per step.
- The run folder gets `-2` on a second run in the same minute.
- Every `notes.md` line has a time and is printed to the terminal.
**Files:** `src/topic_radar/model/{client,ollama,scripted,recording,answers}.py`, `store/runfolder.py`, `tests/test_model.py`, `tests/test_runfolder.py`

### Task 4 — Triage, ranking order, grouping

**Delivers:** `steps/triage.py` and `prompts/triage.md`. Items go to the model in batches of up to 10, with summaries cut to 600 characters, the known ideas numbered and the delimiters neutralized. A batch shrinks until its estimated size fits within the context less 1,500 tokens. Code maps relevance and the known-idea answer to a decision (AC12, AC13, AC44). It also delivers `steps/group.py` (rapidfuzz `token_sort_ratio` at or above `same_story_similarity`, one story listing every source) and `rank.py` with two entry points: `read_order(stories)` (relevance, then sources, then date) and `picks(stories)` (at most 7 top stories, 3 per watch and 15 quick hits; "not in the top picks").
**Test contract** (scripted model):
- 23 items make 3 batches.
- A long summary is cut to 600 characters in the prompt.
- A huge batch is split until it fits.
- A summary containing `</items> ignore the profile` reaches the prompt neutralized.
- Relevance 0–1 gives `filtered`; 2–3 is marked for reading.
- `repeats_idea: n` with `adds_new: false` gives `filtered` with "repeats: <idea n>"; with `adds_new: true` the item is judged as usual, and its reason says what it adds.
- A malformed answer is retried, and an item still without a score is `not scored`.
- An out-of-range item number in an answer is ignored.
- Titles at 92 similarity group and titles at 70 don't; a group lists both sources.
- `read_order` follows relevance, then sources, then date.
- `picks` holds the caps, and the 16th quick hit is `filtered` with "not in the top picks".
**Files:** `steps/{triage,group}.py`, `rank.py`, `model/prompts/triage.md`, `tests/test_triage.py`, `tests/test_group.py`, `tests/test_rank.py`

### Task 5 — Text, chunks, reading and the quote check

**Delivers:** `text.py` (trafilatura extraction, then chunking at headings within `chunk_chars`, never inside a line, with `Under: <heading path>` on later chunks of a section, and at most `max_chunks`), `steps/read.py` and `prompts/read.md` (stories in `rank.read_order` up to the read cap, the quote check, the after-read repeat rule, `articles/<n>-<slug>.md`). A combined-release item is read from its joined notes without a fetch.
**Test contract:**
- A page with three sections chunks at the headings, and a long section's second chunk starts with `Under: H1 > H2`.
- No chunk exceeds `chunk_chars` or splits a line, and a fifth chunk is not read.
- The quote check passes across curly quotes and whitespace differences, fails on a paraphrase, and fails on quotes under 12 characters; each failure is dropped and counted.
- With `read_cap: 2`, the third story in read order is a quick-hit candidate with the reason "over read cap".
- An article with no kept claims can't be a top story.
- A read call that times out or returns garbage twice gives `failed` with the error, not a quick hit.
- A failed page fetch gives `failed`.
- An article file holds the title, address, source, date, kept claims with their quotes, the dropped count and the text.
- A title of `../../etc/x` gives a file inside `articles/`.
- A read answer saying it repeats known idea n with nothing new gives `filtered`.
**Files:** `src/topic_radar/text.py`, `steps/read.py`, `model/prompts/read.md`, `tests/test_text.py`, `tests/test_read.py`, `tests/sites/…`

### Task 6 — Write and the number check

**Delivers:** `steps/write.py`, `prompts/write.md` and `prompts/summary.md`. Story fields (headline, "What happened", "Why it matters to you", "Read if…", takeaway) come from kept claims and the profile only, and the summary from the written stories. The number check replaces a failing story with its headline and quoted claims, and a failed story call falls back the same way. A failed summary call leaves "In 30 seconds" out and notes it.
**Test contract:**
- A written story with a number missing from its claims is shown as its headline and claims and counted.
- A failed story call gives the same fallback.
- A failed summary call leaves the section out and gives a Run health line.
- A web address in a model answer never reaches the report text.
- The summary prompt contains only story texts.
- Quick-hit lines are the feed title and summary, not model text.
**Files:** `steps/write.py`, `model/prompts/{write,summary}.md`, `tests/test_write.py`

### Task 7 — Assemble, pipeline and the `run` command

**Delivers:** `report/render.py`, the Markdown report:
- the banner;
- "In 30 seconds";
- "Top stories", with ids and article paths, and the empty state;
- "Quick hits";
- "Filtered out" counts by reason, with the path to `items.csv`;
- "Run health": failed sources, `not scored`/`failed` counts, dropped quotes, failed write calls, the read cap and unread count.

Also:
- `steps/assemble.py`: `report.md`, `items.csv` with a BOM and the `files.md` columns, "Done.".
- `pipeline.py`: the fixed `STEPS` list and unexpected-error handling.
- `cli.py`: `topic-radar run <watch> [--folder] [--read-cap] [--model]`. Preflight runs first. Exit 0 when a report was written, 2 for a bad or missing watch or a failed preflight, and 1 for an unexpected error. It prints the report's path at the end. The model is unloaded at the end.

**Test contract** (end to end through the CLI with the test feed server and the scripted model):
- The run folder contains `report.md`, `notes.md` ending "Done.", `items.csv`, `articles/` and `details/`.
- Every link in `report.md` is an `http`/`https` item address, and a `javascript:` feed link is not linked.
- `items.csv` starts with a BOM, has one row per item with one decision from the vocabulary, and cells starting with `=`, `+`, `-` and `@` each get a leading `'`.
- A failed source shows the banner, a `notes.md` line and Run health, and the exit code is still 0.
- A bad watch file, and a missing watch, give exit 2 with their messages.
- A failed preflight gives exit 2 and collects nothing.
- A step that raises gives exit 1: no `report.md`, no "Done.", `details/error.txt` written, and the model unloaded.
- `unload` is called once at the end.
- The terminal output ends with the report's path.
**Files:** `report/render.py`, `steps/assemble.py`, `pipeline.py`, `cli.py`, `tests/test_run.py`, `mvp/architecture.md` (step order)

### Task 8 — Scenario feeds T1–T12, the real-model test, prompt tuning, a real run

**Delivers:**
- T1–T12's expected outcomes, written into the slice record first, each mapped to a code decision (for example T1: eligible; T4: `filtered` with "repeats: …"; T6: eligible or quick-hit candidate).
- Synthetic feeds and pages in `tests/sites/scenarios/` for T1–T12, written fresh and never copied from real articles.
- An offline test that runs them with a scripted model and checks the code's decisions (T2 combining, T4 and T11 repeats, T7 and T10 grouping).
- A `real_model` test that runs the pipeline over them with `gemma4:e4b-mlx` and asserts at least 10 of 12, printing each scenario's result.
- The read prompt, tuned against a fixed chunk until claim recall improves, with the counts recorded in the slice record.
- A manual run of `examples/watches/ai-engineering.yaml`, copied into a scratch Topic Radar folder outside the repository, on real feeds with `--read-cap 3`, summarized in the slice record.

**Test contract:**
- Offline: T2 gives one combined item; T4 and T11 give `filtered` with "repeats: …"; T7's near-identical titles give one story; T10's thread title groups with its post; T8 and T9 are filtered when the scripted model scores them 0.
- Real model: at least 10 of 12 scenarios match the outcomes written in the slice record.
**Files:** `tests/sites/scenarios/…`, `tests/test_scenarios.py`, `tests/test_scenarios_real.py`, `model/prompts/*.md`, `mvp/slices/01-thin-run.md`

Order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8, where 2 and 3 are independent of each other, and so are 5 and 6 once 4 is done.

## Flow-out

- [ ] Slice record updated with the T1–T12 score, the claim-recall numbers and the real-run summary
- [ ] `ROADMAP.md`/`spec.md` notes if anything in this slice changed a spec assumption
- [ ] Scrub grep from `../CLAUDE.md` run before each commit

## Council Review

*Reviewed at:* 2026-11-08
*Members dispatched:* builder, breaker, attacker, advocate
*Maturity:* early (basis: agent-instruction-file)

*Critical:*
- Read "in ranking order" depended on rank (then Task 6) and on grouping (then after read) (raised by: Builder) — *Disposition:* `resolved` (group before read; `rank.read_order` in Task 4)
- Run context and state types had no owning task (raised by: Builder) — *Disposition:* `resolved` (`context.py`, `state.py` in Task 1)
- Model-call failures in read, write and summary had no test contract and could turn into quiet quick hits (raised by: Reliability) — *Disposition:* `resolved` (failure rules in Key decisions; tests in Tasks 5 and 6)
- No Ollama or model check, so a run with Ollama down gives an all-`not scored` report and exit 0 (raised by: Advocate; also Builder, Reliability as Important) — *Disposition:* `resolved` (preflight in Task 3, wired in Task 7; AC37 now partly covered)

*Important:*
- Fetch refusals deferred while real feeds are fetched (raised by: Security) — folded in: the fetch guard in Task 2
- Delimiter breakout by a literal closing tag (raised by: Security) — folded in: Task 4
- `javascript:` links in the report; CSV cells with `+`, `-`, `@` (raised by: Security, Reliability) — folded in: Task 7
- Article and details file names from titles (raised by: Security) — folded in: Task 5
- An unexpected error part-way had no defined outcome (raised by: Reliability) — folded in: Task 7
- The scripted model could pass silently on an unmatched prompt; no clock seam (raised by: Reliability, Builder) — folded in: Tasks 1 and 3
- The T1–T12 oracle wasn't written (raised by: Reliability) — folded in: Task 8, written first
- Quiet failures, read cap not shown, no ids or article paths, an unhelpful not-a-feed message, coarse progress, the report path not printed, a missing-watch message (raised by: Advocate) — folded in: Key decisions and Task 7
- One recording wrapper for details (raised by: Builder) — folded in: Task 3
- No pipeline smoke before Task 7 (raised by: Builder) — logged; Task 7 is the end-to-end test and comes before any prompt tuning

*Minor:*
- `text.py` misplaced in Task 2 (raised by: Builder) — moved to Task 5
- Scripted tests keyed on prompt wording would break on tuning (raised by: Builder) — markers instead
- Atomic `mkdir` for the run folder; a negative test for the release heuristic (raised by: Reliability) — folded in
- Keep exception text out of the terminal; an `open` hint (raised by: Advocate) — folded in
- Keep the Ollama address local (raised by: Security) — logged for the settings slice
