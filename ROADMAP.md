# Topic radar — roadmap

From the MVP ([`mvp/spec.md`](mvp/spec.md)) to the full design ([`DESIGN.md`](DESIGN.md)). Each stage is useful on its own, and each plugs into a seam the MVP already has ([`mvp/architecture.md`](mvp/architecture.md), "Seams"), so no stage rewrites an earlier one. Stages 2–4 can be reordered; each gets its own spec before it's built.

| Stage | Adds | Seam | Design section |
|---|---|---|---|
| **1. MVP** | Feeds, cursors, history, triage, read with quote check, near-identical grouping, combined releases, a known-ideas list so the same advice isn't shown again, the 5-minute report, feedback in words with a rebuilt profile, the run folder, `find`, `doctor`, macOS and Windows | — | `mvp/` |
| **2. Beyond feeds** | Playwright on the installed Chrome or Edge; listing pages, living documents (section fingerprints), sitemaps, PDFs; web search in the browser; **wide watches** that start from a topic; source discovery and the report's Candidate sources; `add source` feedback | `Reader` kinds; `discover_sources` step; feedback kinds | 4.3, 5, 7 |
| **3. Hands-off** | `schedule` (launchd on Mac, Task Scheduler on Windows); notifications; keep awake while running; battery rule; read cap set from the last run's times; install scripts for both systems and the launcher; `new` (write a watch from plain questions) | `platform.py`; `cli.py` | 8.1, 8.3, 8.6 |
| **4. Console** | The local web page for everything after install: home (latest report, Run now), watches, sources (confirm, mute, sample, a wide watch's searches), runs, find, feedback buttons, schedule, **health** (the `doctor` checks with fixes and Try again), **settings**, quick check and tidy buttons; stops by itself after about 30 minutes with no page open | `store/`; `report/` structure | 8.3 |
| **5. Better judgment** | Embedding prefilter; liked/disliked examples from feedback; source weights; clustering with embeddings; zoom reading for long documents; Dates to know; Trends; an optional larger writing model on 24 GB+ machines | step list; `ModelClient` | 6, 7, 8.1, 9 |
| **6. Extras** | Replay of good weeks as test cases; an Ask box in the console; an agent-harness add-on (for example pi) for exploring and feedback | run folder; `cli.py` | 9.4, 13 |

## Gaps in the full design these stages close

The full design's console left some things to the command line. Stage 4 closes them: a health page in place of `doctor`, a settings page, a wide watch's searches shown on the Sources page, quick check and tidy as buttons, and a rule for when the console's local server stops.
