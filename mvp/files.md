# Topic radar MVP — files

Every file the MVP reads or writes, in the Topic Radar folder. All text files are UTF-8; CSV files have a byte-order mark for Excel. Each file the tool writes starts with a line saying what it is and whether it's safe to edit.

```
Topic Radar/
  settings.yaml             # optional; defaults apply when absent
  watches/<watch>.yaml      # written by me
  sources/<watch>.yaml      # written by the tool; "status" safe to edit
  history/<watch>.csv       # written by the tool; don't edit
  feedback/<watch>.md       # written by the tool; my words and what it understood
  profile/<watch>.md        # written by the tool; safe to delete
  known/<watch>.md          # written by the tool; ideas I already know, one per line; safe to edit
  runs/<YYYY-MM-DD-HHMM>/   # one per run
  reports/latest.md         # copy of the newest report; I type feedback at its end
  reports/latest.html
```

`<watch>` is the watch file's name without `.yaml`: lowercase letters, digits and `-` only.

## settings.yaml

```yaml
model: auto                    # auto = gemma4:e4b-mlx on Apple silicon if installed, else gemma4:e4b-it-qat; gemma4:e2b-mlx is lighter
model_timeout_seconds: 300     # most seconds one model call may take; a timeout counts as a failed call
ollama: http://127.0.0.1:11434 # where Ollama listens
context: 8192                  # model context size in tokens
read_cap: 25                   # most articles read in full per run, all watches together
chunk_chars: 3000              # most characters per chunk
max_chunks: 4                  # most chunks read per article
word_budget: 1200              # most words from the top of the report through Quick hits
same_story_similarity: 90      # title similarity (0-100) at which items are one story
request_delay_seconds: 1       # pause between requests to the same site
timeout_seconds: 30            # per request
known_ideas_max: 80            # most ideas kept in each watch's known-ideas list
```

## watches/<watch>.yaml

```yaml
name: AI breakthroughs            # required; the report's section title
interests: |                      # required; free text
  New model architectures, small models that run locally, evaluation methods.
not_interested: |                 # optional; free text
  Funding rounds, executive moves, opinion threads.
seeds:                            # web addresses: feeds or pages that link to feeds
  - https://rss.arxiv.org/rss/cs.CL   # a feed address; a page with no feed link would get "no feed found"
  - https://ollama.com/blog
already_know: |                   # optional; things the report shouldn't keep telling me
  - Keep an instruction file with project rules.
first_run_lookback: 7d            # optional, default 7d; how far back a source's first run reaches; not a schedule
searches: []                      # accepted, used from stage 2
mode: normal                      # accepted, used from stage 2 (wide)
```

The primary case's full watch is `examples/watches/ai-engineering.yaml`.

## sources/<watch>.yaml

```yaml
# Written by topic-radar. You may change "status" (active or muted).
- name: arXiv cs.CL new submissions     # the feed's own title
  address: https://rss.arxiv.org/rss/cs.CL
  seed: https://rss.arxiv.org/rss/cs.CL   # the seed it came from
  kind: feed
  status: active                        # active | muted | broken
  added: 2026-11-09
  cursor:
    etag: '"5f2a-61c"'                  # sent as If-None-Match
    last_modified: Sun, 08 Nov 2026 23:00:00 GMT  # sent as If-Modified-Since
    newest_published: 2026-11-08T22:00:00Z
  last_run: 2026-11-09-0700
  last_result: 37 new items             # or the error, in words
  failures_in_a_row: 0
```

## history/<watch>.csv

One row per item ever seen.

| Column | Example |
|---|---|
| `address` | `https://arxiv.org/abs/2611.01234` (normalized) |
| `title` | `Two-bit KV caches without retraining` |
| `source` | `arXiv cs.CL new submissions` |
| `published` | `2026-11-07T18:00:00Z` |
| `updated` | `2026-11-07T18:00:00Z` (the feed's updated date, used for AC6) |
| `first_seen` | `2026-11-09-0700` (run folder) |
| `last_seen` | `2026-11-09-0700` |
| `last_decision` | `quick hit` |

## The run folder: runs/<YYYY-MM-DD-HHMM>/

| File | Content |
|---|---|
| `report.md`, `report.html` | The report |
| `report.json` | The report structure, with each id (`S1`, `Q3`) mapped to its items and its one-line takeaway; used to resolve feedback ids (AC32) and to learn known ideas (AC43) |
| `notes.md` | Plain-language log, ends with "Done." when finished |
| `items.csv` | One row per item considered (columns below) |
| `sources.csv` | One row per source read: `watch`, `source`, `address`, `result` (`ok`, `no change`, `failed`), `new_items`, `seconds`, `error` |
| `articles/<name>.md` | One per article read; `<name>` is the source's short name and the title's first words, letters, digits and `-` only, at most 80 characters |
| `details/events.jsonl` | One JSON object per event |
| `details/<step>-<NNN>-prompt.txt`, `details/<step>-<NNN>-answer.txt` | Each model call's prompt (system and user) and raw answer |

### items.csv

| Column | Meaning |
|---|---|
| `watch` | The watch |
| `source` | The source's name |
| `title` | The item's title |
| `address` | Normalized address |
| `published` | From the feed |
| `new_or_update` | `new` or `update` |
| `relevance` | 0–3, empty when not scored |
| `kind` | From triage |
| `reason` | Triage's reason, or why it was dropped |
| `decision` | `top story`, `quick hit`, `filtered`, `repeat`, `not scored`, `failed` (the reason column says why, for example "over read cap", "over word budget", "not in the top picks", "repeats: <idea>") |
| `report_id` | `S1`, `Q4`, or empty |
| `article` | Path of the saved article, or empty |

## feedback/<watch>.md

Newest first. Lines that applied to all watches are written into each watch's file.

```markdown
## 2026-11-09 — on the report of 2026-11-09-0700
You said: "S5 is marketing"
I understood: less like this — S5 "Law firm explains new guidance" (example-law-blog),
because it restates a rule without adding anything.
```

## profile/<watch>.md

```markdown
<!-- Written by topic-radar from the watch file and the feedback file. Safe to delete: it is rebuilt. -->
You follow AI research. You want new architectures, small local models and
evaluation methods, with numbers. You don't want funding news, executive moves,
or opinion threads. You prefer papers and release notes over news write-ups.
```

## known/<watch>.md

```markdown
<!-- Written by topic-radar: ideas you already know, one per line. Safe to edit: delete a line to see that idea again, add one to stop seeing it. Ideas marked (from already_know), (you said) or (added by hand) are never dropped; learned ones are capped at known_ideas_max. -->
- Keep an instruction file (CLAUDE.md, copilot-instructions.md, AGENTS.md) with project rules. (from already_know)
- Use subagents to keep the main context small. (from already_know)
- Prompt caching only pays off above a few thousand repeated tokens. (you said, on Q4 of 2026-11-09-0700)
- Claude Code hooks can block a tool call before it runs. (learned: top story S1, 2026-11-09-0700)
```

## reports/latest.md

A copy of the newest `report.md`. Its last section is:

```markdown
## Feedback

<!-- Type feedback below, in your own words, then save. It's read at the start of the next run. Example: S2 more like this. Q4 is marketing. Mute the example-vendor blog. -->
```
