# Project: topic radar (brainstorm)

A local-only digest, run as often as the user likes, of what's new in topics the user follows. The design is `DESIGN.md`; nothing is built yet.

- **Independent project:** it stands on its own; files and commits refer to nothing outside this repository.
- **Local only:** Ollama models, Playwright and plain HTTP. No hosted LLM APIs, accounts, API keys or tokens.
- **macOS and Windows:** same code and files on both; platform differences live behind one small module (`DESIGN.md` 8.6).
- **Target machine:** 16 GB of RAM; one model and at most one browser tab in memory at a time.
- **Plain files, no database:** the user may have little dev experience and must be able to see what a run did in Finder or File Explorer, a text editor or a spreadsheet.
- Python 3.12 with `uv` once code exists. YAML for data examples, with inline comments and no shorthand.
