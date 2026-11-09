import pytest

from topic_radar.settings import Settings, SettingsError, load_settings


def test_defaults_apply_when_no_settings_file(tmp_path):
    s = load_settings(tmp_path)
    assert s.read_cap == 25
    assert s.model_timeout_seconds == 300


def test_settings_yaml_overrides_a_default_and_keeps_the_rest(tmp_path):
    (tmp_path / "settings.yaml").write_text("read_cap: 3\nmodel: gemma4:e2b-mlx\n", encoding="utf-8")
    s = load_settings(tmp_path)
    assert s.read_cap == 3
    assert s.model == "gemma4:e2b-mlx"
    assert s.chunk_chars == Settings().chunk_chars


@pytest.mark.parametrize("line, field, expected", [
    ('read_cap: "5"', "read_cap", "whole number"),
    ("read_cap: 2.5", "read_cap", "whole number"),
    ("read_cap: true", "read_cap", "whole number"),
    ("model:", "model", "text"),
    ("model: 7", "model", "text"),
    ('timeout_seconds: "fast"', "timeout_seconds", "number"),
    ("ollama: [a]", "ollama", "text"),
])
def test_a_value_of_the_wrong_type_is_an_error_naming_the_field_and_expected_type(tmp_path, line, field, expected):
    (tmp_path / "settings.yaml").write_text(line + "\n", encoding="utf-8")
    with pytest.raises(SettingsError) as e:
        load_settings(tmp_path)
    assert "settings.yaml" in e.value.message and field in e.value.message and expected in e.value.message


def test_right_types_load_including_a_whole_number_for_a_number_field(tmp_path):
    (tmp_path / "settings.yaml").write_text("request_delay_seconds: 2\ntimeout_seconds: 1.5\nmodel: m\n", encoding="utf-8")
    s = load_settings(tmp_path)
    assert (s.request_delay_seconds, s.timeout_seconds, s.model) == (2, 1.5, "m")
