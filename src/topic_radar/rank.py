from dataclasses import dataclass, field

from .state import Story

TOP_MAX = 7
PER_WATCH_MAX = 3
QUICK_MAX = 15


@dataclass
class Picks:
    top: list[Story] = field(default_factory=list)
    quick: list[Story] = field(default_factory=list)


def read_order(stories: list[Story]) -> list[Story]:
    """Relevance, then number of sources, then date, best first. Returns a new list; the read step
    passes the stories with `to_read` and reads them in this order up to the read cap."""
    return sorted(stories, key=lambda s: (-s.relevance, -len(s.sources), -s.date.timestamp()))


def picks(stories: list[Story]) -> Picks:
    """Choose the report's stories after reading and set each item's decision (AC19).

    Candidates are stories with a read-marked item still at `top story` or `quick hit`. An `eligible`
    story takes a top place while fewer than TOP_MAX are taken and fewer than PER_WATCH_MAX are
    from its watch. The rest are quick hits up to QUICK_MAX; the remainder are `filtered`."""
    live = ("top story", "quick hit")
    candidates = read_order([s for s in stories if any(i.to_read and i.decision in live for i in s.items)])
    top: list[Story] = []
    quick: list[Story] = []
    dropped: list[Story] = []
    per_watch: dict[str, int] = {}
    for story in candidates:
        if story.eligible and len(top) < TOP_MAX and per_watch.get(story.watch, 0) < PER_WATCH_MAX:
            top.append(story)
            per_watch[story.watch] = per_watch.get(story.watch, 0) + 1
        elif len(quick) < QUICK_MAX:
            quick.append(story)
        else:
            dropped.append(story)
    for group_, decision in ((top, "top story"), (quick, "quick hit"), (dropped, "filtered")):
        for story in group_:
            for item in story.items:
                if item.to_read and item.decision in live:
                    item.decision = decision
                    if decision == "filtered":
                        item.reason = "not in the top picks"
    return Picks(top=top, quick=quick)
