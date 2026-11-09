from dataclasses import dataclass, field
from datetime import datetime, timezone

_NO_DATE = datetime.min.replace(tzinfo=timezone.utc)
DECISIONS = ("top story", "quick hit", "filtered", "repeat", "not scored", "failed")


@dataclass
class Item:
    title: str
    address: str
    source: str  # the feed address the item came from
    published: datetime | None = None  # timezone-aware
    summary: str = ""
    decision: str = "not scored"
    reason: str = ""
    notes: str = ""  # the feed's own full text for the entry (plain), when it carries one
    links: list[str] = field(default_factory=list)  # a combined item's release addresses, in version order; its `address` is the newest of them
    link_labels: list[str] = field(default_factory=list)  # a combined item's version names, parallel to `links`
    watch: str = ""  # the slug of the watch that found it (set by triage)
    relevance: int | None = None  # triage's 0-3, None until scored
    kind: str = ""  # triage's kind (paper, release, rule, guidance, news, opinion, marketing, other)
    to_read: bool = False  # triage scored it 2-3: the read step reads it, in rank.read_order
    eligible: bool = False  # the read step read it and kept at least one claim: it may be a top story
    unread_over_cap: bool = False  # scored 2-3 but over the read cap, so never read; stays set whatever the picks decide later
    article: str = ""  # path of its saved article, relative to the run folder; empty when it wasn't read

    def __setattr__(self, name, value):
        if name == "decision" and value not in DECISIONS:
            raise ValueError(f"decision {value!r} is not one of {', '.join(DECISIONS)}")
        super().__setattr__(name, value)


@dataclass
class Story:
    items: list[Item]

    @property
    def sources(self) -> list[str]:
        return list(dict.fromkeys(i.source for i in self.items))

    @property
    def relevance(self) -> int:
        return max((i.relevance or 0 for i in self.items), default=0)

    @property
    def date(self) -> datetime:
        return max((i.published for i in self.items if i.published), default=_NO_DATE)

    @property
    def to_read(self) -> bool:
        return any(i.to_read for i in self.items)

    @property
    def eligible(self) -> bool:
        return any(i.eligible for i in self.items)

    @property
    def watch(self) -> str:
        return next((i.watch for i in self.items if i.watch), "")


@dataclass
class Claim:
    text: str
    quote: str
    kept: bool = False


@dataclass
class Article:
    item: Item
    path: str = ""
    text: str = ""
    claims: list[Claim] = field(default_factory=list)
    dropped: int = 0  # claims whose quote wasn't found in the chunk


@dataclass
class FailedSource:
    source: str  # the seed address
    reason: str  # a plain sentence, no exception text


@dataclass
class WrittenStory:
    id: str  # S1, S2, ... in report order
    story: Story  # its items give the source links (item addresses only)
    headline: str
    what_happened: str = ""
    why_it_matters: str = ""
    read_if: str = ""
    takeaway: str = ""
    claims: list[Claim] = field(default_factory=list)  # the kept claims, shown when `fallback`
    unread_over_cap: bool = False  # scored 2-3 but over the read cap, so never read; stays set whatever the picks decide later
    article: str = ""  # path of the saved article, relative to the run folder
    fallback: bool = False  # headline (the feed title) and quoted claims only; the other fields are empty
    fallback_reason: str = ""  # "number check" or "write call failed"


@dataclass
class QuickHit:
    id: str  # Q1, Q2, ...
    story: Story
    title: str  # the feed title
    summary: str  # the feed summary, trimmed
    address: str
    watch: str

    @property
    def line(self) -> str:
        return f"{self.title}: {self.summary}" if self.summary else self.title


@dataclass
class Written:
    top: list[WrittenStory] = field(default_factory=list)
    quick: list[QuickHit] = field(default_factory=list)
    summary: list[str] | None = None  # "In 30 seconds" bullets; None leaves the section out
    failed_writes: int = 0  # story calls that failed (each gave the fallback)
    number_check_failures: int = 0  # written stories replaced by the fallback
    summary_failed: bool = False
    health: list[str] = field(default_factory=list)  # plain Run health lines from this step


@dataclass
class RunState:
    items: list[Item] = field(default_factory=list)
    stories: list[Story] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)
    failed_sources: list[FailedSource] = field(default_factory=list)
    feed_titles: dict[str, str] = field(default_factory=dict)  # feed address -> the feed's own title
    written: Written | None = None  # set by the write step
