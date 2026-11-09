from dataclasses import dataclass, field
from typing import Protocol

from ..state import Item


@dataclass
class CollectResult:
    items: list[Item] = field(default_factory=list)
    title: str = ""
    notes: list[str] = field(default_factory=list)  # plain lines for the run's notes


class Reader(Protocol):
    async def collect(self, ctx, source: str) -> CollectResult: ...
