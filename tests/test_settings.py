from topic_radar.settings import Settings, load_settings


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
