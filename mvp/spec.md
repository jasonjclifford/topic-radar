# Topic radar MVP — spec

**Status: ready to slice and build** (after the spec review of 2026-11-09, recorded at the end). The case it's built and tested against first is [`primary-case.md`](primary-case.md) (AI engineering). The full design is [`../DESIGN.md`](../DESIGN.md); how the MVP grows into it is [`../ROADMAP.md`](../ROADMAP.md). How the MVP is built is [`architecture.md`](architecture.md); the files it reads and writes are [`files.md`](files.md).

## Problem

Keeping up with a technical field means checking the same sites again and again, working out what's new since last time, and deciding what deserves real reading time. It's a chore of an hour or more, and it's easy to miss things or to read things that didn't matter.

## What the MVP is

The smallest version that does the chore end to end, on a 16 GB laptop, on macOS or Windows, with a local model:

- reads **RSS/Atom feeds** found from the sites I name,
- keeps a **cursor per feed** and a **history** so only new things count,
- has the local model **score, read and summarize** the new items,
- writes **one report I can read in under 5 minutes**,
- lets me give **feedback in plain words** that changes the next report,
- and leaves **plain files** showing everything it did.

It runs from the command line, by hand. Everything else in the full design (web console, browser-based reading and search, wide watches, scheduling, installers, embeddings, trends) comes in later stages, each added behind a seam the MVP already has (`architecture.md`, "Seams").

## Objectives

| # | Objective |
|---|---|
| O1 | A useful report each run: new items from my sources, ranked by my interests, readable in under 5 minutes, with a clear pointer to what to read in full |
| O2 | Only new things: a repeat is never shown as new; a changed item is shown as an update |
| O3 | Nothing invented: every claim in a top story is backed by a word-for-word quote from its source, every number in a story's text appears in those claims, quick hits use their feed's own words, and no link is typed by the model |
| O4 | I can see what it did, with only Finder or File Explorer, a text editor and a spreadsheet |
| O5 | Feedback in plain words changes the next run, with no config to maintain |
| O6 | Runs on a 16 GB laptop on macOS or Windows with a local model, and fails clearly when something it needs is missing; a run that failed never looks like a quiet one |
| O7 | Not the same ideas again: an article that only repeats what I already know is filtered, even at a new address |

## Acceptance Criteria

Each criterion is checked by running the tool (offline tests use a local test feed server and a scripted stand-in model; see `architecture.md`, "Testing"). Where a criterion needs the real model or a real machine, it says so.

### Watches and sources (O1, O4)

- **AC1.** A watch file with `name`, `interests`, `not_interested`, `seeds`, and optional `already_know` and `first_run_lookback` (default `7d`) is loaded from `watches/`. The later-stage fields `searches` and `mode` are accepted, and `notes.md` says they're skipped until a later version. A watch file that is not valid YAML, or lacks `name` or `interests`, is skipped with a message naming the file, the line where known, and the missing field; the other watches still run.
- **AC2.** `topic-radar init <watch>` turns each seed into proposed feeds: a seed that is itself an RSS or Atom feed is proposed as is; a seed that is an HTML page is proposed as the feeds its `<link rel="alternate">` tags point to; a seed with neither is reported as "no feed found" and nothing is proposed for it.
- **AC3.** `init` asks about each proposed feed (`y` / `n`), shows the feed's title and its newest item's title, and writes each answer to `sources/<watch>.yaml` as `active` or `muted`. Running `init` again only asks about feeds not already in the file.
- **AC4.** A run reads `active` and `broken` sources and skips `muted` ones. Run health lists each `broken` source with its last error and what to do ("check the address, or mute it").

### Knowing what's new (O2)

- **AC5.** The first time a source is read, only items published within the watch's `first_run_lookback` before the run started count as new; older items are recorded in the history as seen, not reported.
- **AC6.** After a source's first run, an item is new if and only if its normalized address is not in the watch's history; the cursor's newest date is used only for AC10, and an undated item counts as new. An item already in the history is not reported again, unless its feed `updated` date is later than the one recorded, in which case it's reported once as an **update** and labelled so. When every listed item of a feed shows a later `updated` date on the same fetch, that feed's updates are ignored for the run and Run health says so, so a feed that rewrites its dates doesn't re-report everything.
- **AC7.** Addresses are normalized before comparing: tracking parameters (`utm_*`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`) are removed, the scheme and host are lowercased, a trailing `/` is dropped, and the address after redirects is used: each collected item's address is resolved at collect time (a HEAD request, falling back to GET), and if that fails the feed's address is kept and the item is not dropped. Two items with the same normalized address in one run are one item.
- **AC8.** Each source's `ETag` and `Last-Modified` are stored and sent on the next request. A `304 Not Modified` gives no items, and `notes.md` records "no change".
- **AC9.** A source that fails (network error, timeout, an HTTP status other than 200 or 304, or a body that doesn't parse as a feed) doesn't stop the run: it's recorded in `notes.md` and `sources.csv`, and its cursor is unchanged. After 3 failed runs in a row its status becomes `broken`; it's still tried once each run (no retries within a run), and a success sets it back to `active`.
- **AC10.** A feed only lists its latest items. When the oldest item a feed lists is newer than that source's cursor, items may have been missed between runs: `notes.md` and Run health say so for that source ("may have missed items between 2026-11-02 and 2026-11-06; this feed only keeps its latest 20"), and the run continues.
- **AC11.** A run changes state files (`history/`, `known/`, `feedback/`, `profile/`, `sources/`, and clearing the Feedback section of `reports/latest.md`) only at its end, after its report is written, in this order: history, known ideas, feedback and profile, sources, then `reports/latest.*`. Each file is written to a temporary name and renamed. If a run stops before that, every state file is byte-for-byte unchanged and the next run does the same work again; if a rename fails part-way, the run says "state not saved" in plain words, names the file, marks the report incomplete and leaves `reports/latest.*` as they were. Items with the decision `not scored`, or `failed` because of a model or network error, are never written to the history, so the next run tries them again. `init` (AC3) and the `feedback` command (AC31) are not runs: they write their own files at once, with the same temporary-name-and-rename step.

### Judging and reading (O1, O3)

- **AC12.** Every new item is triaged by the model (batches of up to 10 titles with their feed summaries) into a relevance of 0–3, a short reason, and a kind (`paper`, `release`, `rule`, `guidance`, `news`, `opinion`, `marketing`, `other`). An answer that doesn't parse is retried once; an item still without a score is recorded with the decision `not scored` and never silently dropped. Each feed summary is cut to 600 characters for triage.
- **AC13.** Relevance decides what happens to an item: 0–1 is `filtered`; 2–3 items are read in full in ranking order (AC19) up to the read cap (setting `read_cap`, default 25 for the whole run). Only an item read with at least one kept claim can be a top story. Every other 2–3 item (over the cap, or read with no kept claims) is a quick-hit candidate; one over the cap is recorded with the reason "over read cap".
- **AC14.** Reading fetches the item's page, extracts its main text, and splits it into chunks of at most `chunk_chars` characters (default 3,000), breaking at headings where possible and never inside a line; at most `max_chunks` (default 4) chunks are read per article. A chunk after the first in a section starts with `Under: <heading path>`.
- **AC15.** Each claim the model reports from a chunk carries a quote. A claim is kept only if its quote appears in the chunk's text after both are normalized for whitespace and quote characters; otherwise it's dropped and counted. An article with no kept claims becomes a quick hit at most.
- **AC16.** Each article read is saved as `articles/<name>.md` in the run folder: title, address, source, date, the kept claims with their quotes, the dropped-claim count, then the extracted text.
- **AC17.** Items in one run whose titles are near-identical (similarity at or above `same_story_similarity`, default 90 out of 100) are grouped as one story listing every source.

### The report (O1, O3)

- **AC18.** The report has, in order: "In 30 seconds" (3–5 bullets), "Top stories", "Quick hits" (grouped by watch), "Filtered out" (counts by triage reason, with the path to `items.csv`), "What I think you want" (each watch's profile), "Run health", and an empty "Feedback" heading.
- **AC19.** At most 7 top stories, at most 3 from any one watch; at most 15 quick hits. Ranking is relevance, then updates after new items, then the number of sources, then date. A quick-hit candidate that doesn't make the 15 is `filtered` with the reason "not in the top picks".
- **AC20.** Every top story has an id (`S1`…), a headline, "What happened", "Why it matters to you", "Read if…", a one-line takeaway (stored in `report.json`, used by AC43), and links to each of its sources. Every quick hit has an id (`Q1`…), one line taken from its feed title and summary (not written by the model), and a link; its takeaway is that line.
- **AC21.** The text from the top of the report through Quick hits is at most `word_budget` words (default 1,200). Code enforces it after writing, by removing the lowest-ranked quick hits, then the lowest-ranked top stories, until it fits. A removed item gets the decision `filtered` with the reason "over word budget". If a top story is removed, the 30-second summary is written again once from the stories that remain. If the report still doesn't fit with no quick hits and one top story, it's kept as it is and Run health says it's over budget.
- **AC22.** Every link in the report is an address taken from a collected item. A web address that appears in a model answer is never put in the report.
- **AC23.** The model writes each top story from that story's kept claims and quotes and the watch profile only (the profile is what "Why it matters to you" is written from), and the 30-second summary from the written stories only.
- **AC24.** The report is written as `report.md` and `report.html` in the run folder and copied to `reports/latest.md` and `reports/latest.html`. `topic-radar open` opens `reports/latest.html` with the system's default program.

### Seeing what it did (O4)

- **AC25.** Each run writes a folder `runs/<YYYY-MM-DD-HHMM>/` (local time; a second run in the same minute adds `-2`) containing `report.md`, `report.html`, `report.json` (each report id mapped to its items and takeaway), `notes.md`, `items.csv`, `sources.csv`, `articles/` and `details/`.
- **AC26.** `notes.md` has one plain-language line per source read and per step, with the time, and ends with "Done." only when the run finished. A report is assembled only at the end of a run, never part-way; it's marked "incomplete" only when its state couldn't be saved (AC11).
- **AC27.** `items.csv` has one row per item the run considered, with the columns in `files.md`, and one decision from: `top story`, `quick hit`, `filtered`, `repeat` (same address seen before), `not scored`, `failed`, plus a reason. It's UTF-8 with a byte-order mark, so Excel on Windows shows non-English titles correctly.
- **AC28.** `details/` holds every prompt sent and every raw answer received, one pair of files per call, named by step and number, and `events.jsonl` with one line per event.
- **AC29.** `topic-radar find <text>` searches `history/`, every run's `items.csv`, `notes.md` and `articles/`, ignoring case, and prints one line per match with the run, the watch, the source, the title and the decision.

### Feedback (O5)

- **AC30.** Text under the "Feedback" heading of `reports/latest.md`, if any, is read at the start of the next run and applied to that run in memory (profile, mutes, known ideas). It's written to the feedback files, and removed from `reports/latest.md`, only with that run's other end-of-run changes (AC11), so an interrupted run never loses it.
- **AC31.** `topic-radar feedback "<text>"` records the same way and prints what it understood before saving; `--yes` skips the confirmation.
- **AC32.** Ids in feedback (`S2`, `Q7`) are resolved by code to the item's title, address and source from the run that wrote `reports/latest.md`. An id that doesn't exist in that run is reported as unknown and not recorded.
- **AC33.** The model interprets each feedback line into one or more of: `more like this`, `less like this`, `wrong relevance`, `mute source`, `already know`, `style`, or `unclear`, each tied to a watch (or all watches when no watch can be told). Each is appended to `feedback/<watch>.md` with the date, my words, and what was understood. `unclear` changes nothing and is listed in the next report's Run health.
- **AC34.** `mute source` sets that source's status to `muted` in the sources file (at once from the `feedback` command; at the end of the run for feedback typed in the report, while that run already skips the source); it isn't read in later runs.
- **AC35.** After new feedback is recorded, the watch's profile (`profile/<watch>.md`) is rebuilt by the model from the watch file and the whole feedback file (never edited in place). The profile is part of the triage, read and write prompts, and is printed in the report. Deleting the profile is harmless: it's rebuilt before the next triage.

### Running on the laptop (O6)

- **AC36.** The offline test suite passes on macOS and on Windows.
- **AC37.** Before collecting anything, a run checks that Ollama answers and the chosen model is installed. If not, it stops with exit code 2 and a message naming the command that fixes it (`ollama serve`, `ollama pull <model>`). `topic-radar doctor` runs the same checks plus write access to the folder, and prints each as OK or as the problem with its fix.
- **AC38.** With setting `model: auto`, the tool uses `gemma4:e4b-mlx` on Apple silicon when it's installed, otherwise `gemma4:e4b-it-qat`; `gemma4:e2b-mlx` is the documented lighter option. A model named in settings is used as is. "Thinking" is turned off on every call (`think: false`).
- **AC39.** Model calls use the context size from settings (default 8,192), one call at a time, each with a timeout (setting `model_timeout_seconds`, default 300; a timeout counts as a failed call), and the run's last call unloads the model (`keep_alive: 0`). Before each call, the prompt's size is estimated (characters ÷ 3.5); a triage batch shrinks until its estimate fits within the context size less 1,500 tokens for the answer.
- **AC40.** A run exits with code 0 when it wrote a report, even if some sources failed, and non-zero only when it didn't.
- **AC41.** (Manual, real model.) On a 16 GB Apple silicon Mac, a run over a reference set of about 300 new items with the default settings finishes in 60 minutes or less without the machine running out of memory, and Run health records the model's resident size as `ollama ps` reports it. (Measured on a 16 GB M4: `gemma4:e4b-mlx` 8.7–8.9 GB resident at 8K context; `gemma4:e2b-mlx` 6.4–6.5 GB; `gemma4:e4b-it-qat` runs on the llama.cpp runner, where `ollama ps` doesn't report its full size.)
- **AC42.** (Manual, real model.) For a reference run over about 7 days of new items, the report can be read in under 5 minutes, and each of its top stories can be checked against its saved article.

### Not the same ideas again (O7)

- **AC43.** Each watch has a known-ideas list (`known/<watch>.md`), one short idea per line. It's built from three places: the watch's `already_know` text (split into ideas by the model the first time it's seen or whenever it changes), each top story's one-line takeaway once its report is written, and `already know` feedback (the item's takeaway). Ideas from `already_know`, ideas from `already know` feedback, and lines I add by hand are never dropped; `known_ideas_max` (default 80) limits only the ideas learned from reports, keeping the newest. A learned idea is at most 200 characters and is listed in Run health when it's added. The list is changed only at the end of a run (AC11).
- **AC44.** Triage sees the watch's known ideas, numbered. When the model answers that an item's main point is known idea *n* and that it adds nothing new, code gives the item the decision `filtered` with the reason "repeats: <idea n>". When the model answers that it's known idea *n* but adds something new (numbers, a new method, a changed result), the item is judged as usual and its reason says what it adds. The model may also answer "repeats known idea *n*" after reading an article (AC15), and the same rule then applies to it.
- **AC45.** "Filtered out" in the report shows how many items repeated known ideas, and Run health gives the path to `known/<watch>.md`.
- **AC46.** A feed's items that are releases of one project in one run (a GitHub `releases.atom` feed, or a feed whose item titles are version numbers) are combined into one item titled "<project>: <n> releases since the last run", listing each version and linking each release. It's triaged and read as one item, with the release notes joined in version order and taken from the feed's own content (no page fetch). The combined item exists only in the run, `report.json` and `items.csv`; the history keeps one row per release address. A single release is an ordinary item.

### Failed and empty runs (O6)

- **AC47.** When any source failed, any item went `not scored` or `failed`, or state couldn't be saved, the report opens with a banner before "In 30 seconds", in plain words, for example: "3 of 17 sources couldn't be read and 40 items weren't scored, so this report is missing things; they'll be tried again next run. See Run health." When a run finds no new items at all, the report says "Nothing new since <date of the last run>" instead of empty sections. A run with no active or broken sources stops with exit code 2 and the message "No sources yet: run topic-radar init <watch>".
- **AC48.** While a run is going, the terminal shows each line as it's added to `notes.md`, and the first line says that stopping with Ctrl-C is safe (nothing is saved until the end).

### Untrusted web content (O3, O4)

- **AC49.** Feed text and page text are data, never instructions: every prompt puts them inside clearly marked delimiters, and only answers that match the step's schema are used. Fetching allows only `http` and `https`; each redirect hop is checked, and a loopback, private-network or link-local address is refused. Bodies over 5 MB, and content types other than HTML, XML, RSS, Atom or plain text, are refused. Each refusal is recorded in `notes.md` and `sources.csv`. Spreadsheet cells that start with `=`, `+`, `-` or `@` get a leading `'`. The HTML report escapes all text and only links `http`/`https` addresses.

### Checking the result (O1, O3)

- **AC50.** Every number in a top story's written text (digits, with or without `%`, `,` or `.`) must appear in that story's kept claims or quotes; if one doesn't, the story is shown as its headline and its quoted claims instead of the written text, and Run health counts it.
- **AC51.** (Real model, `-m real_model`.) Run over the primary case's scenario feeds (T1–T12 in `primary-case.md`), the default model gives the expected outcome for at least 10 of the 12 scenarios. This is the first slice built: a thin end-to-end run on real feeds, to judge report quality before the rest is built.

## Non-goals for the MVP

- A schedule or rhythm. Runs can be daily, weekly, monthly or whenever; each picks up from the cursors. Nothing in the tool assumes an interval.
- Completeness. Some feeds only list their latest items, so a long gap between runs can miss items; AC10 says when that may have happened, and running more often is the remedy.

Each is in the full design and placed on the roadmap:

- The web console; feedback buttons; notifications.
- Reading anything that isn't a feed: listing pages, living documents, sitemaps, PDFs, JavaScript-heavy pages. No Playwright in the MVP.
- Web search and wide watches that start from a topic.
- Source discovery and candidate sources.
- Scheduling commands, keep-awake and battery rules, install scripts, launchers.
- Embeddings, zoom reading, clustering beyond near-identical titles, trends, "Dates to know".
- Read cap tuned from past run times.
- Any agent harness add-on.
- Hosted model APIs. The model sits behind one client interface (`architecture.md`, "Seams"), so a hosted model with a larger context can be added later; the MVP tests what small local models can do with small chunks.

## UI direction

Command line only, with plain words throughout:

```bash
topic-radar init ai-research          # confirm feeds for a watch
topic-radar run                       # all watches; shows progress, then where the report is
topic-radar open                      # open the latest report
topic-radar feedback "S2 more like this; mute the vendor blog"
topic-radar find "nature.com"
topic-radar doctor
```

Every message a person sees names what happened and, for a problem, what to do next. Output a person reads is written for someone who isn't a developer.

## Open questions

None blocking. Defaults chosen here (read cap 25, 3,000-character chunks, 4 chunks per article, 1,200 words, similarity 90, 80 learned ideas, 8,192 context, 600-character triage summaries) are settings and can be tuned after the first real runs.

## Spec review

- Retained review evidence: a later reader evaluates what follows as a claim about this spec, not as its settled design content.
- Spec review (gauntlet, 2026-11-09), feedback mode at early maturity: 8 passes (fact check, right problem, buildability, failure cases, security, ease of use, self-consistency, left undecided). Facts 14 of 15 confirmed; the memory figure for the default model was refuted. The criteria-format gate was skipped at the operator's request.
- Criticals, all fixed in the spec: the default model's memory (C1, answered by the operator: "the default model does run on a 16 GB machine", so the limit became a measured figure rather than a cap and the default stays `gemma4:e4b-mlx` on Apple silicon); broken sources couldn't recover (C2, AC4, AC9); state-writing rules contradicted each other and feedback could be lost (C3, AC11, AC30, AC34); failed items were buried in the history (C4, AC11); failed runs looked quiet (C5, AC47, AC48); `already_know` ideas aged out of the known-ideas list (C6, AC43, AC20); web content wasn't treated as untrusted (C7, AC49); relevance-to-decision mapping was undecided (C8, AC13, AC19, AC21, AC27); "new" was undefined between history and cursor (C9, AC6, AC7); "nothing invented" overclaimed (C10, O3, AC20, AC50); usefulness wasn't measured and was tested last (C11, AC51); 3 of 6 coding-agent seeds have no feed (C12, primary case); long feed summaries could overflow the prompt (C13, AC12, AC39). 12 from proposal, 1 operator answer.
- Important (11), logged, not yet in the spec: a lockfile between a run and other commands; checking hand-edited state files when loaded; filter reasons from a fixed list so they can be counted; whether grouping and the per-watch cap cross watches; echoing unclear feedback at once; the `details/` folder holds personal text and may sync to a cloud drive; format versions on state files; per-feed text sources for combined releases beyond GitHub; and three covered above in part (progress output, timeouts, redirect timing).
- Minor (8): loose terms (cursor, read, feed, source, seed, story); 23 criteria bundle several checks and should be split when slicing; the 5-minute target isn't tied to the word budget; sync HTTP would do; DESIGN's old-feedback fading isn't in the spec; a warning when the Ollama address isn't local; file-name checks for `..` and reserved characters.
- Model check on a 16 GB M4 (2026-11-09, scratch probe of 10 triage items and one 1,700-character release-notes chunk, temperature 0, thinking off): `gemma4:e4b-mlx` 10/10 triage in 12.8 s, 8.7–8.9 GB resident; `gemma4:e4b-it-qat` 10/10 in 28.2 s (llama.cpp runner, about 2.2 times slower); `gemma4:e2b-mlx` 8/10 in 7.0 s, 6.4–6.5 GB resident. All three quoted every claim word for word, but the e4b models listed only 3 claims from a chunk holding about 8; the read prompt needs tuning in the first slice (AC51). Naming "pricing, plans and usage limits" in the interests fixed a missed rate-limit item for both e4b models.
