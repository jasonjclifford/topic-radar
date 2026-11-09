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
    links: list[str] = field(default_factory=list)  # a combined item's release addresses, in version order
    watch: str = ""  # the slug of the watch that found it (set by triage)
    relevance: int | None = None  # triage's 0-3, None until scored
    kind: str = ""  # triage's kind (paper, release, rule, guidance, news, opinion, marketing, other)
    to_read: bool = False  # triage scored it 2-3: the read step reads it, in rank.read_order
    eligible: bool = False  # the read step read it and kept at least one claim: it may be a top story
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
class RunState:
    items: list[Item] = field(default_factory=list)
    stories: list[Story] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    failed_sources: list[FailedSource] = field(default_factory=list)
    feed_titles: dict[str, str] = field(default_factory=dict)  # feed address -> the feed's own title
