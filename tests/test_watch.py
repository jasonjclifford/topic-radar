from datetime import timedelta
from pathlib import Path

from topic_radar.watch import Watch, load_watch

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "watches" / "ai-engineering.yaml"


def write(folder, name, text):
    d = folder / "watches"
    d.mkdir(exist_ok=True)
    p = d / f"{name}.yaml"
    p.write_text(text, encoding="utf-8")
    return p


MIN = "name: Demo\ninterests: |\n  things\nseeds:\n  - https://e.test/feed\n"


def test_valid_watch_loads_with_default_lookback(tmp_path):
    w = load_watch(write(tmp_path, "demo", MIN))
    assert isinstance(w, Watch)
    assert w.name == "Demo"
    assert w.slug == "demo"
    assert w.interests.strip() == "things"
    assert w.seeds == ["https://e.test/feed"]
    assert w.first_run_lookback == timedelta(days=7)
    assert w.notes == []


def test_lookback_14d_parses_to_14_days(tmp_path):
    w = load_watch(write(tmp_path, "demo", MIN + "first_run_lookback: 14d\n"))
    assert w.first_run_lookback == timedelta(days=14)


def test_real_example_watch_loads():
    w = load_watch(EXAMPLE)
    assert isinstance(w, Watch)
    assert w.name == "AI engineering"
    assert len(w.known_ideas) == 9
    assert len(w.seeds) > 5


def test_invalid_yaml_is_skipped_naming_file_and_line(tmp_path):
    p = write(tmp_path, "broken", "name: Demo\ninterests: x\nseeds: [a, b\nother: 1\n")
    msg = load_watch(p)
    assert isinstance(msg, str)
    assert "broken.yaml" in msg
    assert "line 4" in msg


def test_missing_name_names_the_field(tmp_path):
    msg = load_watch(write(tmp_path, "demo", "interests: x\n"))
    assert isinstance(msg, str)
    assert "demo.yaml" in msg and "name" in msg and "interests" not in msg


def test_missing_interests_names_the_field(tmp_path):
    msg = load_watch(write(tmp_path, "demo", "name: Demo\n"))
    assert isinstance(msg, str)
    assert "demo.yaml" in msg and "interests" in msg and "name" not in msg.replace("demo.yaml", "")


def test_bad_lookback_is_skipped_naming_the_field(tmp_path):
    msg = load_watch(write(tmp_path, "demo", MIN + "first_run_lookback: soon\n"))
    assert isinstance(msg, str) and "first_run_lookback" in msg


def test_searches_and_mode_produce_skipped_note(tmp_path):
    w = load_watch(write(tmp_path, "demo", MIN + "searches: [a thing]\nmode: wide\n"))
    assert isinstance(w, Watch)
    assert any("searches" in n and "skipped until a later version" in n for n in w.notes)
    assert any("mode" in n and "skipped until a later version" in n for n in w.notes)


def test_only_searches_gives_only_the_searches_note(tmp_path):
    w = load_watch(write(tmp_path, "demo", MIN + "searches: [a thing]\n"))
    assert len(w.notes) == 1 and "searches" in w.notes[0]


def test_already_know_bullets_split_into_known_ideas(tmp_path):
    text = MIN + "already_know: |\n  Things I know:\n  - First idea.\n  - Second idea.\n"
    w = load_watch(write(tmp_path, "demo", text))
    assert w.known_ideas == ["First idea.", "Second idea."]


def test_known_file_lines_are_added_to_already_know(tmp_path):
    text = MIN + "already_know: |\n  - First idea.\n"
    p = write(tmp_path, "demo", text)
    (tmp_path / "known").mkdir()
    (tmp_path / "known" / "demo.md").write_text(
        "<!-- comment -->\n- Learned idea.\n- Another one.\n", encoding="utf-8")
    w = load_watch(p)
    assert w.known_ideas == ["First idea.", "Learned idea.", "Another one."]


def test_known_file_alone_supplies_ideas_without_already_know(tmp_path):
    p = write(tmp_path, "demo", MIN)
    (tmp_path / "known").mkdir()
    (tmp_path / "known" / "demo.md").write_text("- Only learned.\n", encoding="utf-8")
    assert load_watch(p).known_ideas == ["Only learned."]


def test_a_watch_file_that_is_not_utf8_is_skipped_naming_the_file(tmp_path):
    p = write(tmp_path, "latin", "x")
    p.write_bytes("name: Caf\xe9\ninterests: x\n".encode("latin-1"))
    msg = load_watch(p)
    assert isinstance(msg, str) and "latin.yaml" in msg and "UTF-8" in msg


def test_a_known_ideas_file_that_is_not_utf8_is_skipped_naming_that_file(tmp_path):
    p = write(tmp_path, "demo", MIN)
    (tmp_path / "known").mkdir()
    (tmp_path / "known" / "demo.md").write_bytes("- caf\xe9\n".encode("latin-1"))
    msg = load_watch(p)
    assert isinstance(msg, str) and "demo.md" in msg and "UTF-8" in msg
