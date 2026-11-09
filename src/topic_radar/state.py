from dataclasses import dataclass, field
from datetime import datetime

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


@dataclass
class RunState:
    items: list[Item] = field(default_factory=list)
    stories: list[Story] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
