from datetime import datetime, timezone

import pytest

from topic_radar.state import DECISIONS, Item


def make_item(**kw):
    base = dict(title="T", address="https://e.test/a", source="https://e.test/feed",
                published=datetime(2026, 11, 1, tzinfo=timezone.utc))
    base.update(kw)
    return Item(**base)


@pytest.mark.parametrize("decision", ["top story", "quick hit", "filtered", "repeat", "not scored", "failed"])
def test_item_accepts_each_vocabulary_decision(decision):
    item = make_item()
    item.decision = decision
    assert item.decision == decision
    assert decision in DECISIONS


def test_item_refuses_a_decision_outside_the_vocabulary():
    item = make_item()
    with pytest.raises(ValueError, match="maybe"):
        item.decision = "maybe"
    assert item.decision == "not scored"


def test_item_refuses_a_bad_decision_at_construction():
    with pytest.raises(ValueError, match="maybe"):
        make_item(decision="maybe")
