# Topic radar MVP — spec

**Status: draft, ready for review.** The case it's built and tested against first is [`primary-case.md`](primary-case.md) (AI engineering). The full design is [`../DESIGN.md`](../DESIGN.md); how the MVP grows into it is [`../ROADMAP.md`](../ROADMAP.md). How the MVP is built is [`architecture.md`](architecture.md); the files it reads and writes are [`files.md`](files.md).

## Problem

Keeping up with a technical field means checking the same sites every week, working out what's new since last time, and deciding what deserves real reading time. It's a chore of an hour or more, and it's easy to miss things or to read things that didn't matter.

## What the MVP is

The smallest version that does the weekly chore end to end, on a 16 GB laptop, on macOS or Windows, with a local model:

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
| O1 | A useful weekly report: new items from my sources, ranked by my interests, readable in under 5 minutes, with a clear pointer to what to read in full |
| O2 | Only new things: a repeat is never shown as new; a changed item is shown as an update |
| O3 | Nothing invented: no fact without a quote from its source, no link the model typed |
| O4 | I can see what it did, with only Finder or File Explorer, a text editor and a spreadsheet |
| O5 | Feedback in plain words changes the next run, with no config to maintain |
| O6 | Runs on a 16 GB laptop on macOS or Windows with a local model, and fails clearly when something it needs is missing |
| O7 | Not the same ideas again: an article that only repeats what I already know is filtered, even at a new address |

## Acceptance criteria

Each criterion is checked by running the tool (offline tests use a local test feed server and a scripted stand-in model; see `architecture.md`, "Testing"). Where a criterion needs the real model or a real machine, it says so.

### Watches and sources (O1, O4)

- **AC1** A watch file with `name`, `interests`, `not_interested`, `seeds`, and optional `already_know` and `interval` (default `7d`) is loaded from `watches/`. The later-stage fields `searches` and `mode` are accepted, and `notes.md` says they're skipped until a later version. A watch file that is not valid YAML, or lacks `name` or `interests`, is skipped with a message naming the file, the line where known, and the missing field; the other watches still run.
- **AC2** `topic-radar init <watch>` turns each seed into proposed feeds: a seed that is itself an RSS or Atom feed is proposed as is; a seed that is an HTML page is proposed as the feeds its `<link rel="alternate">` tags point to; a seed with neither is reported as "no feed found" and nothing is proposed for it.
- **AC3** `init` asks about each proposed feed (`y` / `n`), shows the feed's title and its newest item's title, and writes each answer to `sources/<watch>.yaml` as `active` or `muted`. Running `init` again only asks about feeds not already in the file.
- **AC4** A run reads only `active` sources.

### Knowing what's new (O2)

- **AC5** The first time a source is read, only items published within the watch's `interval` before the run started count as new; older items are recorded in the history as seen, not reported.
- **AC6** An item whose normalized address is already in the watch's history is not reported again, unless its feed `updated` date is later than the one recorded, in which case it's reported once as an **update** and labelled so in the report.
- **AC7** Addresses are normalized before comparing: tracking parameters (`utm_*`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`) are removed, the scheme and host are lowercased, a trailing `/` is dropped, and the address after redirects is used. Two items with the same normalized address in one run are one item.
- **AC8** Each source's `ETag` and `Last-Modified` are stored and sent on the next request. A `304 Not Modified` gives no items, and `notes.md` records "no change".
- **AC9** A source that fails (network error, timeout, an HTTP status other than 200 or 304, or a body that doesn't parse as a feed) doesn't stop the run: it's recorded in `notes.md` and `sources.csv`, and its cursor is unchanged. After 3 failed runs in a row its status becomes `broken`; a later success sets it back to `active`.
- **AC10** A feed only lists its latest items. When the oldest item a feed lists is newer than that source's cursor, items may have been missed between runs: `notes.md` and Run health say so for that source ("may have missed items between 2026-11-02 and 2026-11-06; this feed only keeps its latest 20"), and the run continues.
- **AC11** `sources/` and `history/` are changed only at the end of a run that wrote its report. If a run stops before that, those files are byte-for-byte unchanged, and the next run treats the same items as new.

### Judging and reading (O1, O3)

- **AC12** Every new item is triaged by the model (batches of up to 10 titles with their feed summaries) into a relevance of 0–3, a short reason, and a kind (`paper`, `release`, `rule`, `guidance`, `news`, `opinion`, `marketing`, `other`). An answer that doesn't parse is retried once; an item still without a score is recorded with the decision `not scored` and never silently dropped.
- **AC13** Items with relevance 2 or 3 are read in full, highest first, up to the read cap (setting `read_cap`, default 25 for the whole run). Items over the cap are recorded with the decision `over cap` and can still be quick hits from their triage answer.
- **AC14** Reading fetches the item's page, extracts its main text, and splits it into chunks of at most `chunk_chars` characters (default 3,000), breaking at headings where possible and never inside a line; at most `max_chunks` (default 4) chunks are read per article. A chunk after the first in a section starts with `Under: <heading path>`.
- **AC15** Each claim the model reports from a chunk carries a quote. A claim is kept only if its quote appears in the chunk's text after both are normalized for whitespace and quote characters; otherwise it's dropped and counted. An article with no kept claims becomes a quick hit at most.
- **AC16** Each article read is saved as `articles/<name>.md` in the run folder: title, address, source, date, the kept claims with their quotes, the dropped-claim count, then the extracted text.
- **AC17** Items in one run whose titles are near-identical (similarity at or above `same_story_similarity`, default 90 out of 100) are grouped as one story listing every source.

### The report (O1, O3)

- **AC18** The report has, in order: "This week in 30 seconds" (3–5 bullets), "Top stories", "Quick hits" (grouped by watch), "Filtered out" (counts by triage reason, with the path to `items.csv`), "What I think you want" (each watch's profile), "Run health", and an empty "Feedback" heading.
- **AC19** At most 7 top stories, at most 3 from any one watch; at most 15 quick hits. Ranking is relevance, then updates after new items, then the number of sources, then date.
- **AC20** Every top story has an id (`S1`…), a headline, "What happened", "Why it matters to you", "Read if…", and links to each of its sources. Every quick hit has an id (`Q1`…), one line, and a link.
- **AC21** The text from the top of the report through Quick hits is at most `word_budget` words (default 1,200). Code enforces it after writing, by removing the lowest-ranked quick hits, then the lowest-ranked top stories, until it fits.
- **AC22** Every link in the report is an address taken from a collected item. A web address that appears in a model answer is never put in the report.
- **AC23** The model writes each top story from that story's kept claims and quotes only, and the 30-second summary from the written stories only.
- **AC24** The report is written as `report.md` and `report.html` in the run folder and copied to `reports/latest.md` and `reports/latest.html`. `topic-radar open` opens `reports/latest.html` with the system's default program.

### Seeing what it did (O4)

- **AC25** Each run writes a folder `runs/<YYYY-MM-DD-HHMM>/` (local time; a second run in the same minute adds `-2`) containing `report.md`, `report.html`, `notes.md`, `items.csv`, `sources.csv`, `articles/` and `details/`.
- **AC26** `notes.md` has one plain-language line per source read and per step, with the time, and ends with "Done." only when the run finished. An unfinished run's report (if any) is marked "incomplete".
- **AC27** `items.csv` has one row per item the run considered, with the columns in `files.md`, and a decision from: `top story`, `quick hit`, `filtered`, `repeat`, `over cap`, `not scored`, `failed`. It's UTF-8 with a byte-order mark, so Excel on Windows shows non-English titles correctly.
- **AC28** `details/` holds every prompt sent and every raw answer received, one pair of files per call, named by step and number, and `events.jsonl` with one line per event.
- **AC29** `topic-radar find <text>` searches `history/`, every run's `items.csv`, `notes.md` and `articles/`, ignoring case, and prints one line per match with the run, the watch, the source, the title and the decision.

### Feedback (O5)

- **AC30** Text under the "Feedback" heading of `reports/latest.md`, if any, is read at the start of the next run, recorded in the feedback files (below), and removed from `reports/latest.md`.
- **AC31** `topic-radar feedback "<text>"` records the same way and prints what it understood before saving; `--yes` skips the confirmation.
- **AC32** Ids in feedback (`S2`, `Q7`) are resolved by code to the item's title, address and source from the run that wrote `reports/latest.md`. An id that doesn't exist in that run is reported as unknown and not recorded.
- **AC33** The model interprets each feedback line into one or more of: `more like this`, `less like this`, `wrong relevance`, `mute source`, `already know`, `style`, or `unclear`, each tied to a watch (or all watches when no watch can be told). Each is appended to `feedback/<watch>.md` with the date, my words, and what was understood. `unclear` changes nothing and is listed in the next report's Run health.
- **AC34** `mute source` sets that source's status to `muted` in the sources file; it isn't read in later runs.
- **AC35** After new feedback is recorded, the watch's profile (`profile/<watch>.md`) is rebuilt by the model from the watch file and the whole feedback file (never edited in place). The profile is part of the triage, read and write prompts, and is printed in the report. Deleting the profile is harmless: it's rebuilt before the next triage.

### Running on the laptop (O6)

- **AC36** The offline test suite passes on macOS and on Windows.
- **AC37** Before collecting anything, a run checks that Ollama answers and the chosen model is installed. If not, it stops with exit code 2 and a message naming the command that fixes it (`ollama serve`, `ollama pull <model>`). `topic-radar doctor` runs the same checks plus write access to the folder, and prints each as OK or as the problem with its fix.
- **AC38** With setting `model: auto`, the tool uses `gemma4:e4b-mlx` on Apple silicon when installed, otherwise `gemma4:e4b`. A model named in settings is used as is.
- **AC39** Model calls use the context size from settings (default 8,192), one call at a time, and the run's last call unloads the model (`keep_alive: 0`).
- **AC40** A run exits with code 0 when it wrote a report, even if some sources failed, and non-zero only when it didn't.
- **AC41** (Manual, real model.) On a 16 GB Apple silicon Mac, a run over a reference set of about 300 new items with the default settings finishes in 60 minutes or less, and the tool's memory (Ollama plus the tool) stays under 8 GB.
- **AC42** (Manual, real model.) For a reference week, the report can be read in under 5 minutes, and each of its top stories can be checked against its saved article.

### Not the same ideas again (O7)

- **AC43** Each watch has a known-ideas list (`known/<watch>.md`), one short idea per line. It's built from three places: the watch's `already_know` text (split into ideas by the model the first time it's seen or whenever it changes), each top story's one-line takeaway once its report is written, and `already know` feedback (the item's takeaway). It keeps the newest `known_ideas_max` ideas (default 80), and it's changed only at the end of a run, like the other state files (AC11).
- **AC44** Triage sees the watch's known ideas, numbered. When the model answers that an item's main point is known idea *n* and that it adds nothing new, code gives the item the decision `filtered` with the reason "repeats: <idea n>". When the model answers that it's known idea *n* but adds something new (numbers, a new method, a changed result), the item is judged as usual and its reason says what it adds.
- **AC45** "Filtered out" in the report shows how many items repeated known ideas, and Run health gives the path to `known/<watch>.md`.
- **AC46** A feed's items that are releases of one project in one run (a GitHub `releases.atom` feed, or a feed whose item titles are version numbers) are combined into one item titled "<project>: <n> releases this week", listing each version and linking each release. It's triaged and read as one item, with the release notes joined in version order.

## Non-goals for the MVP

Each is in the full design and placed on the roadmap:

- The web console; feedback buttons; notifications.
- Reading anything that isn't a feed: listing pages, living documents, sitemaps, PDFs, JavaScript-heavy pages. No Playwright in the MVP.
- Web search and wide watches that start from a topic.
- Source discovery and candidate sources.
- Scheduling commands, keep-awake and battery rules, install scripts, launchers.
- Embeddings, zoom reading, clustering beyond near-identical titles, trends, "Dates to know".
- Read cap tuned from past run times.
- Any agent harness add-on.

## UI direction

Command line only, with plain words throughout:

```bash
topic-radar init ai-research          # confirm feeds for a watch
topic-radar run                       # all watches; prints where the report is
topic-radar open                      # open the latest report
topic-radar feedback "S2 more like this; mute the vendor blog"
topic-radar find "nature.com"
topic-radar doctor
```

Every message a person sees names what happened and, for a problem, what to do next. Output a person reads is written for someone who isn't a developer.

## Open questions

None blocking. Defaults chosen here (read cap 25, 4 chunks per article, 1,200 words, similarity 90) are settings and can be tuned after the first real runs.
