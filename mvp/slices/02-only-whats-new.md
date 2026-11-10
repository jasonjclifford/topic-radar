# Slice 2 — a second run shows only what's new

**Status:** chosen, not yet planned
**Spec:** [`../spec.md`](../spec.md)

**Value claim:** You will be able to confirm a watch's feeds once with `topic-radar init`, then run the same watch every day and get a report holding only what appeared since the last run, with updated items labelled as updates. The run folder will say which sources had nothing new, which failed and which may have missed items. Try it: run `init` and `run` on the AI engineering watch, then `run` again the next morning. The second report should only list items published in between, `items.csv` should show every earlier item as `repeat`, and `sources.yaml` and `history/` should show where each source left off.

**Covers:** AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC19

**Partially covers:** AC11, AC24, AC25, AC26, AC27, AC47, AC49

**Also delivers (not yet in the spec):** a lockfile between a run and other commands, from the spec review's Important list. Before `init` or `run` writes anything, it takes `.topic-radar.lock` in the Topic Radar folder. A second command that finds the lock held by a live process stops with a plain message ("a run is already going, started 07:00"). A lock left by a process that has died is taken over, and `notes.md` says so. Candidate spec addition once built.

## Why this slice next

Slice 1 proved the reading pipeline: 12 of 12 scenarios right, and every claim in the real run's report traced to a kept quote. But every run is still a first run, so the tool can't do the job it exists for: running again shows the same items. This slice is the read and create phase for the tool's state (sources, cursors, history). Feedback, the profile and known ideas (AC30–AC35, AC43) write into the same end-of-run step, so they come next, on top of it. The rest of the MVP (HTML report, `find`, `doctor`, `model: auto`) doesn't depend on this order.

## What it adds

1. **`topic-radar init <watch>`.** Turns seeds into proposed feeds: a seed that is a feed as is, an HTML page by its `<link rel="alternate">` feeds, otherwise "no feed found" (AC2). Asks `y`/`n` per feed, showing the feed's title and its newest item's title. Writes `sources/<watch>.yaml` at once, through a temporary name and a rename. A second `init` asks only about feeds not already in the file (AC3). Fetches go through slice 1's fetch guard.
2. **The run reads `sources/<watch>.yaml`, not the seeds.** It reads `active` and `broken` sources and skips `muted` ones. A watch with no `active` or `broken` sources stops with exit code 2 and "No sources yet: run topic-radar init <watch>" (AC4, AC47 in part).
3. **Conditional requests.** The stored `ETag` and `Last-Modified` are sent on the next request; a `304` gives no items, and `notes.md` says "no change" (AC8).
4. **What counts as new.** A source's first read uses `first_run_lookback`, and older items go into the history as seen (AC5). After that, an item is new if its normalized address isn't in `history/<watch>.csv`. A later feed `updated` date makes it an **update**, reported once and labelled so. A feed whose every item moved its `updated` date on one fetch has its updates ignored for the run, and Run health says so (AC6). Ranking puts new items ahead of updates (AC19).
5. **Addresses after redirects.** Each item's address is resolved at collect time (HEAD, falling back to GET, every hop through the fetch guard). If that fails, the feed's address is kept and the item stays (AC7).
6. **Failing and broken sources.** A failure leaves the cursor unchanged and is written to `notes.md` and `sources.csv`. After 3 failed runs in a row the source becomes `broken`; it's still tried once per run, and a success sets it back to `active` (AC9). Run health lists each broken source with its last error and "check the address, or mute it" (AC4).
7. **Missed items.** When a feed's oldest listed item is newer than its cursor, `notes.md` and Run health say items may have been missed between the two dates (AC10).
8. **End-of-run state.** Only after `report.md` is written, in order: `history/`, then `sources/`, then `reports/latest.md`. Each is written to a temporary name and renamed. A run stopped before that leaves every state file byte-for-byte unchanged. A failed rename says "state not saved", names the file, marks the report incomplete and leaves `reports/latest.md` as it was. Items that are `not scored`, or `failed` from a model or network error, never enter the history (AC11 for history, sources and the latest copy; AC24 for the copy to `reports/latest.md`; AC26 for the incomplete mark).
9. **The run folder.** `sources.csv` (AC25 in part, AC9), fetch refusals in `sources.csv` as well as `notes.md` (AC49 in part), and `items.csv` gains the `repeat` decision and the `new_or_update` column (AC27 in part).

## Decisions

- No visual surface: command line, a Markdown report and plain files. `init`'s `y`/`n` prompt is a terminal question.
- One watch per `run`, as in slice 1. Running every watch in one combined report (AC1's "the other watches still run", AC19's cap across watches) is left for a later slice.
- AC11's state writes for `known/`, `feedback/` and `profile/` come with the feedback slice. This slice sets up the end-of-run step they slot into, in AC11's order.
- `reports/latest.html` and `topic-radar open` stay with the HTML report (AC24's rest).

## What's left of the spec once this slice is built

- Watches and sources: one of four left, loading every watch in one run (AC1).
- Knowing what's new: one of seven left, the end-of-run writes for known ideas, feedback and profile (AC11).
- Judging and reading: none of six.
- The report: five of seven left (sections, ids and takeaways in `report.json`, the word budget, the profile in prompts, the HTML copy and `open`). The word budget (AC21) looks built in slice 1's `assemble` step but neither slice claims it; check it when the report slice is planned.
- Seeing what it did: four of five left (`report.html` and `report.json`, the rest of `notes.md` and `items.csv`, `find`).
- Feedback: six of six left.
- Running on the laptop: seven of seven left.
- Not the same ideas again: two of four left (learning known ideas from reports, and counting repeats in Filtered out).
- Failed and empty runs: two of two left, though this slice adds the no-sources stop.
- Untrusted web content: one of one left, though this slice adds the refusals to `sources.csv`.
- Checking the result: none of two.

## Follow-ups carried from slice 1 that this slice touches

- DNS rebinding in the fetch guard (the name is checked, then looked up again to connect). This slice adds redirect resolution and `init` fetches, so more requests go through the gap. Fix it here, with a backend that connects to the checked address, or say in the plan why not.
