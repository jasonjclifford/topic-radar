# Topic radar MVP — architecture

How the MVP in [`spec.md`](spec.md) is built, and where each later stage of [`../ROADMAP.md`](../ROADMAP.md) plugs in. File formats are in [`files.md`](files.md).

## Stack

| Piece | Choice | Notes |
|---|---|---|
| Language | Python 3.12, managed with `uv` | Same on macOS and Windows |
| Command line | `typer` | |
| Web requests | `httpx` (async) | Conditional requests, redirects, timeouts |
| Feeds | `feedparser` | RSS and Atom |
| Article text | `trafilatura` | Main text with headings kept |
| Model | Ollama over its HTTP interface, via `httpx` | No SDK needed; structured output with a JSON schema |
| Answers | `pydantic` | Every model answer parsed into a typed structure or recorded as an error |
| Files | `ruamel.yaml` (keeps comments), standard `csv`, `markdown-it-py` + `jinja2` for HTML | |
| Similar titles | `rapidfuzz` | |
| Tests | `pytest`, `pytest-asyncio`, a local test feed server | |

Not in the MVP: Playwright, `starlette`, `wakepy`, `psutil`, `desktop-notifier`, `pypdf`. Each arrives with the stage that needs it.

## Package layout

```
src/topic_radar/
  cli.py                 # typer commands: init, run, open, feedback, find, doctor
  settings.py            # defaults + optional settings.yaml; the model choice (model: auto)
  watch.py               # load and check watch files
  pipeline.py            # the run: the fixed list of steps, the run context
  steps/
    feedback_in.py       # step 0: read the report's Feedback section; applied in memory, saved at the end
    collect.py           # step 1: each active source's reader, in turn
    normalize.py         # step 2: normalized addresses, repeats, updates, combined releases
    triage.py            # step 3: model, batches of titles
    group.py             # step 4: near-identical titles into stories (before read: one story is read once)
    read.py              # step 5: model, chunks, quote check, article files
    rank.py              # step 6: order, caps, picks
    write.py             # step 7: model, story texts and the 30-second summary
    assemble.py          # step 8: report, word budget, notes, CSVs, state update
  readers/
    base.py              # the Reader protocol, Item, CollectResult
    feed.py              # RSS/Atom: discovery from a seed, collection since a cursor
  web.py                 # the shared HTTP client: polite pacing, normalize_address
  text.py                # main text, headings, chunking
  model/
    client.py            # the ModelClient protocol
    ollama.py            # the real client
    scripted.py          # the stand-in for tests
    answers.py           # pydantic models for each kind of answer
    prompts/             # one Markdown file per prompt, with {placeholders}
  feedback.py            # interpret feedback lines; rebuild a profile
  store/
    atomic.py            # write to a temporary name, then rename
    sources.py           # sources/<watch>.yaml
    history.py           # history/<watch>.csv
    runfolder.py         # runs/<time>/ and everything in it; events.jsonl
    feedbackfiles.py     # feedback/<watch>.md, profile/<watch>.md
    known.py             # known/<watch>.md, the known-ideas list (O7)
  report/
    render.py            # markdown and HTML from the report structure
    templates/
  platform.py            # open a file; Apple silicon check
tests/
```

## The run

`pipeline.run(context)` calls the steps in a fixed order. Each step is an `async` function that takes the run context and the run state and returns the new run state. No step decides which step comes next.

```python
STEPS = [feedback_in, collect, normalize, triage, group, read, rank, write, assemble]
```

**Run context** (built once, read-only to steps): settings, the watches, the run folder, the model client, the HTTP client, the clock. The clock, model client and HTTP client are passed in, so tests give a fixed time, the scripted model and the test feed server.

**Run state** (a plain dataclass, replaced by each step): the items with their decisions, triage answers, articles and claims, stories, the picks, the written texts, and the pending state changes (new cursors, history rows, source statuses).

State files are never written during the run, step 0 included: feedback typed in the report is interpreted and applied in memory (profile, mutes, known ideas) and joins the **pending changes**. Each step adds to them; only `assemble`, after the report files are written, applies them through `store/`, each file written to a temporary name and renamed, in the order history, known ideas, feedback and profile, sources, then `reports/latest.*` (AC11). Duplicates are safer than losses, which is why history goes first and cursors last. `init` and the `feedback` command aren't runs and write their own files at once through the same `store/` functions. The run folder is written as the run goes (prompts, answers, articles, `notes.md`, `events.jsonl`), so an interrupted run still shows how far it got.

### Model calls

All model calls go through `ModelClient.call(step, system, user, schema) -> Answer`, where `Answer` holds the raw text, the parsed result or the parse error, token counts and the time taken. The client writes the prompt and answer to `details/` (AC28). Rules that every step follows:

- Each prompt is built fresh from the run state for that one call: the watch profile, the item or chunk, the instructions. Never earlier messages.
- Web text goes inside `<items>`, `<chunk>` or `<article>` delimiters, and the system prompt says it's data, never instructions (AC49).
- `think: false` and `temperature: 0` on every call; a timeout per call (AC39).
- Answers are requested as JSON matching the step's pydantic schema (Ollama's structured output) and parsed leniently: a number sent as text is accepted, empty placeholder values are treated as missing.
- One retry on a parse failure, then the step records the failure and moves on.
- Links are never taken from answers. Triage and read refer to items by their number in the prompt; code maps numbers back to items (AC22).
- Prompt texts live in `model/prompts/*.md`, so tuning a prompt is editing a text file.

### The quote check (AC15)

```python
def quote_found(quote: str, text: str) -> bool:
    return normalize_quote(quote) in normalize_quote(text)

# normalize_quote: collapse all whitespace to one space; curly quotes and
# apostrophes to straight ones; dashes to "-"; lowercase; strip. Quotes under
# 12 characters never count as found.
```

### The word budget (AC21)

`write` produces the texts; `assemble` renders the report, counts words from the top through Quick hits, and while over budget removes the lowest-ranked quick hit, then the lowest-ranked top story, re-rendering each time. Removed items get the decision `filtered` with the reason `over word budget`, so `items.csv` stays true. If a top story was removed, `write` is called once more for the 30-second summary only.

### The number check (AC50)

After writing, code collects every number in a top story's text (`\d[\d,.]*%?`) and checks each appears in the story's kept claims or quotes. A story that fails is rendered as its headline and its quoted claims, and Run health counts it.

## Seams

Each later stage plugs in at one of these without changing the others:

| Seam | MVP | Later |
|---|---|---|
| `Reader` protocol (`discover(seed)`, `collect(source, cursor, since)`) | `feed` | `sitemap`, `listing`, `document`, `search` (Playwright), all returning the same `Item` and cursor |
| The step list | 9 steps | `prefilter` (embeddings) between `normalize` and `triage`; `discover_sources` after `read`; `dates` and `trends` before `rank` |
| `ModelClient` | Ollama, scripted | a separate writing model; the `embed` call for embeddings |
| `store/` | the only code that touches state files | the console reads and writes through it too, so its rules (atomic writes, end-of-run changes) hold for every interface |
| `report/` | Markdown + HTML from one report structure | sections added to the structure (Dates to know, Trends, Candidate sources); the console renders the same structure |
| Feedback kinds | seven kinds | `add source`, `source more/less` weights, liked/disliked examples, all through the same interpreter |
| Known ideas | a numbered list in the triage prompt | compared by embeddings in stage 5, so the list can grow past what fits in a prompt |
| `platform.py` | open a file, Apple silicon check | scheduler, launcher, keep awake, battery, notifications |
| `cli.py` | six commands | `schedule`, `console`, `tidy`, `new` |

## Testing

- **Offline (default):** a local test feed server started by a pytest fixture serves feed files and article pages from `tests/sites/`, including ETag and 304 handling, redirects, failures and slow responses. The scripted model returns canned answers keyed by step and by text in the prompt. The clock is fixed. Each acceptance criterion in `spec.md` that isn't marked manual has at least one test that runs the tool (a step, the pipeline, or a CLI command) and checks its output files or exit code.
- **Real model (`-m real_model`):** a few runs against the test sites with the real Ollama model, to check the prompts produce parseable answers. Not part of the default run.
- **Both systems:** the offline suite runs on macOS and Windows (GitHub Actions matrix: `macos-latest`, `windows-latest`).
- **Manual checks:** AC41 and AC42, on a real machine with real feeds, recorded in a run folder.
