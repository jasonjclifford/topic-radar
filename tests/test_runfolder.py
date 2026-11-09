import json
from datetime import datetime, timedelta, timezone

from topic_radar.store.runfolder import RunFolder

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def stamp(t):
    return t.astimezone().strftime("%Y-%m-%d-%H%M")


def test_folder_is_named_by_local_minute_with_articles_and_details(tmp_path):
    rf = RunFolder.create(tmp_path, lambda: NOW, echo=lambda l: None)
    assert rf.path == tmp_path / "runs" / stamp(NOW)
    assert rf.articles.is_dir() and rf.details.is_dir()
    assert rf.articles == rf.path / "articles" and rf.details == rf.path / "details"


def test_a_second_run_in_the_same_minute_gets_2_then_3(tmp_path):
    first = RunFolder.create(tmp_path, lambda: NOW, echo=lambda l: None)
    second = RunFolder.create(tmp_path, lambda: NOW + timedelta(seconds=30), echo=lambda l: None)
    third = RunFolder.create(tmp_path, lambda: NOW, echo=lambda l: None)
    assert first.path.name == stamp(NOW)
    assert second.path.name == stamp(NOW) + "-2"
    assert third.path.name == stamp(NOW) + "-3"
    assert first.path.is_dir()  # the first run's folder is untouched


def test_a_later_minute_gets_its_own_name_without_a_suffix(tmp_path):
    RunFolder.create(tmp_path, lambda: NOW, echo=lambda l: None)
    later = RunFolder.create(tmp_path, lambda: NOW + timedelta(minutes=1), echo=lambda l: None)
    assert later.path.name == stamp(NOW + timedelta(minutes=1))


def test_every_note_has_a_time_and_is_printed_to_the_terminal(tmp_path, capsys):
    times = iter([NOW, NOW, NOW + timedelta(seconds=5)])  # the first reading names the folder
    rf = RunFolder.create(tmp_path, lambda: next(times))  # default echo is the terminal
    rf.note("Stopping with Ctrl-C is safe.")
    rf.note("Triage: batch 3 of 20")
    lines = (rf.path / "notes.md").read_text().splitlines()
    assert len(lines) == 2
    local = NOW.astimezone()
    assert lines[0] == f"[{local:%H:%M:%S}] Stopping with Ctrl-C is safe."
    assert lines[1] == f"[{(NOW + timedelta(seconds=5)).astimezone():%H:%M:%S}] Triage: batch 3 of 20"
    assert capsys.readouterr().out.splitlines() == lines


def test_a_multi_line_note_gets_a_time_on_every_line(tmp_path, capsys):
    rf = RunFolder.create(tmp_path, lambda: NOW)
    rf.note("one\ntwo")
    lines = (rf.path / "notes.md").read_text().splitlines()
    assert len(lines) == 2 and all(l.startswith("[") for l in lines)
    assert capsys.readouterr().out.splitlines() == lines


def test_events_are_one_json_object_per_line_with_a_time(tmp_path):
    rf = RunFolder.create(tmp_path, lambda: NOW, echo=lambda l: None)
    rf.event("fetch", address="https://a.example/x", ok=True)
    rf.event("fetch", address="https://b.example/y", ok=False)
    rows = [json.loads(l) for l in (rf.details / "events.jsonl").read_text().splitlines()]
    assert [(r["event"], r["address"], r["ok"]) for r in rows] == [
        ("fetch", "https://a.example/x", True), ("fetch", "https://b.example/y", False)]
    assert rows[0]["time"] == NOW.isoformat()


def test_the_folder_works_as_a_path_for_the_run_context(tmp_path):
    rf = RunFolder.create(tmp_path, lambda: NOW, echo=lambda l: None)
    import os
    assert os.fspath(rf) == str(rf.path)
