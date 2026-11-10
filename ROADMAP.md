# Topic radar — roadmap

From the MVP ([`mvp/spec.md`](mvp/spec.md)) to the full design ([`DESIGN.md`](DESIGN.md)). Each stage is useful on its own, and each plugs into a seam the MVP already has ([`mvp/architecture.md`](mvp/architecture.md), "Seams"), so no stage rewrites an earlier one. Stages 1b–4 can be reordered; each gets its own spec before it's built.

| Stage | Adds | Seam | Design section |
|---|---|---|---|
| **1. MVP** | Feeds, cursors, history, triage, read with quote check, near-identical grouping, combined releases, a known-ideas list so the same advice isn't shown again, the 5-minute report, feedback in words with a rebuilt profile, the run folder, `find`, `doctor`, macOS and Windows | — | `mvp/` |
| **1b. Pages without feeds, no browser** | Two more readers over plain HTTP, through the MVP's fetch guard: **sitemaps** (found from `robots.txt` or `/sitemap.xml`, limited to the seed's path, such as `/news/`; the cursor is each address's last-modified date; a new address's title and summary come from fetching that one page) and **static listing pages** (items found by code as the repeated link pattern under the page's main content; the cursor is the addresses already seen). `init` tries a feed, then a sitemap, then a listing, and says which it found. No model call to find items, no JavaScript | `Reader` kinds | 5 |
| **2. Beyond feeds** | Playwright on the installed Chrome or Edge; listing pages that need JavaScript, living documents (section fingerprints), PDFs; web search in the browser; **wide watches** that start from a topic; source discovery and the report's Candidate sources; `add source` feedback | `Reader` kinds; `discover_sources` step; feedback kinds | 4.3, 5, 7 |
| **3. Hands-off** | `schedule` (launchd on Mac, Task Scheduler on Windows); notifications; keep awake while running; battery rule; read cap set from the last run's times; install scripts for both systems and the launcher; `new` (write a watch from plain questions) | `platform.py`; `cli.py` | 8.1, 8.3, 8.6 |
| **4. Console** | The local web page for everything after install: home (latest report, Run now), watches, sources (confirm, mute, sample, a wide watch's searches), runs, find, feedback buttons, schedule, **health** (the `doctor` checks with fixes and Try again), **settings**, quick check and tidy buttons; stops by itself after about 30 minutes with no page open | `store/`; `report/` structure | 8.3 |
| **5. Better judgment** | Embedding prefilter; liked/disliked examples from feedback; source weights; clustering with embeddings; zoom reading for long documents; Dates to know; Trends; an optional larger writing model on 24 GB+ machines | step list; `ModelClient` | 6, 7, 8.1, 9 |
| **6. Extras** | Hosted model APIs as an option behind the same model client, for a larger context when small chunks aren't enough; replay of good runs as test cases; an Ask box in the console; an agent-harness add-on (for example pi) for exploring and feedback | run folder; `cli.py` | 9.4, 13 |

## Gaps in the full design these stages close

The full design's console left some things to the command line. Stage 4 closes them: a health page in place of `doctor`, a settings page, a wide watch's searches shown on the Sources page, quick check and tidy as buttons, and a rule for when the console's local server stops.

## Why stage 1b comes before stage 2

Three of the six coding-agent seeds in the primary case (Anthropic news, Anthropic engineering, the Devin blog) have no feed, so a pricing or plan change reaches the MVP only second-hand, a day or two late ([`mvp/primary-case.md`](mvp/primary-case.md), Sources). All three publish a `sitemap.xml` with a last-modified date on every page (checked 2026-11-10), so a sitemap reader closes that gap with no browser. Stage 2's Playwright costs a browser download on some machines, a second process in memory beside the model, and slower, flakier reads; stage 1b costs none of that, and leaves stage 2 for the pages that really need a browser (JavaScript listings, search, wide watches).
