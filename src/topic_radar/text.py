import re

import trafilatura

MIN_QUOTE_CHARS = 12
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_CHARS = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "ʼ": "'",
                        "“": '"', "”": '"', "„": '"', "‟": '"',
                        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
                        "―": "-", "−": "-"})


def extract_text(html: str) -> str:
    """The page's main text as Markdown, headings kept as `#` lines; empty when there is none."""
    return trafilatura.extract(html, output_format="markdown", include_formatting=True) or ""


def _sections(text: str) -> list[tuple[list[str], list[str]]]:
    """(heading path, lines) per section; a section starts at its heading line."""
    sections: list[tuple[list[str], list[str]]] = []
    stack: list[tuple[int, str]] = []
    current = None
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2)))
            current = ([title for _, title in stack], [line])
            sections.append(current)
        else:
            if current is None:
                current = ([], [])
                sections.append(current)
            current[1].append(line)
    return sections


def _split(lines: list[str], path: list[str], limit: int) -> list[str]:
    """Pieces of a section too long for one chunk, cut between lines; every piece after the first
    starts with `Under: <heading path>` unless that would push it over the limit. A line longer than the
    limit becomes a piece of its own."""
    prefix = [f"Under: {' > '.join(path)}"] if path else []
    pieces: list[str] = []
    piece: list[str] = []
    size = 0
    lead = "\n".join(prefix)
    for line in lines:
        if piece and size + len(line) + 1 > limit:
            pieces.append("\n".join(piece).strip("\n"))
            piece, size = [], 0
        if not piece:
            if not line.strip():
                continue
            if pieces and prefix and len(lead) + 1 + len(line) <= limit:
                piece, size = list(prefix), len(lead)  # the prefix only goes on when it leaves the piece within the limit
        piece.append(line)
        size += len(line) + (1 if len(piece) > 1 else 0)
    if "\n".join(piece).strip():
        pieces.append("\n".join(piece).strip("\n"))
    return pieces


def chunk_text(text: str, chunk_chars: int, max_chunks: int | None) -> list[str]:
    """Chunks of at most `chunk_chars` characters, cut at headings where possible and never inside a
    line, the first `max_chunks` of them (all when None). A section too long for one chunk is cut
    between lines, and its later chunks start with `Under: <heading path>`."""
    chunks: list[str] = []
    current = ""
    for path, lines in _sections(text):
        section = "\n".join(lines).strip("\n")
        if not section.strip():
            continue
        if current and len(current) + 2 + len(section) <= chunk_chars:
            current += "\n\n" + section
            continue
        if len(section) > chunk_chars and current and all(_HEADING.match(l) or not l.strip() for l in current.splitlines()):
            lines = current.splitlines() + [""] + lines  # a title with nothing under it leads the long section that follows
            current = ""
        if current:
            chunks.append(current)
            current = ""
        if len(section) <= chunk_chars:
            current = section
        else:
            *whole, current = _split(lines, path, chunk_chars)
            chunks.extend(whole)
    if current:
        chunks.append(current)
    return chunks if max_chunks is None else chunks[:max_chunks]


def normalize_quote(text: str) -> str:
    """Whitespace collapsed to one space, curly quotes and dashes made plain, Markdown backslash escapes
    (`\\_`, `\\*`) read as the plain character, lowercase."""
    text = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", text)
    return re.sub(r"\s+", " ", text.translate(_CHARS)).strip().lower()


def quote_found(quote: str, text: str) -> bool:
    """Whether the quote appears in the text once both are normalized; one under 12 characters never does."""
    wanted = normalize_quote(quote)
    return len(wanted) >= MIN_QUOTE_CHARS and wanted in normalize_quote(text)
