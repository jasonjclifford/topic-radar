from dataclasses import dataclass, field
from typing import Protocol

from ..state import Item


@dataclass
class CollectResult:
    items: list[Item] = field(default_factory=list)
    title: str = ""


class Reader(Protocol):
    async def collect(self, ctx, source: str) -> CollectResult: ...
