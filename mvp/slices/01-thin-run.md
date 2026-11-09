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

## Deferred

`init`, cursors, history, conditional requests, broken sources, end-of-run state writes, feedback, profiles, `find`, `doctor`, `open`, HTML report, `report.json`, `sources.csv`, `model: auto`.
