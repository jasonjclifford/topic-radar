"""The real model over the scenario feeds. Run with: uv run pytest -m real_model tests/test_scenarios_real.py -s
Needs Ollama running with the default model installed; deselected by default."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from scenario_support import KNOWN_IDEAS, TITLES, WATCH, judge, run_scenarios, write_folder

from topic_radar.model.ollama import OllamaClient
from topic_radar.state import Item
from topic_radar.steps.read import ReadAnswer, _prompt
from topic_radar.text import extract_text, normalize_quote, quote_found
from topic_radar.watch import Watch

pytestmark = pytest.mark.real_model

MODEL = "gemma4:e4b-mlx"
REQUIRED = 10
SITE_PAGE = Path(__file__).parent / "sites/scenarios/pages/t1-precompact-hook.html"
# what a reader of the fixed chunk would want from it: a phrase that a kept claim's quote must contain
EXPECTED_CLAIMS = {
    "PreCompact hook runs before compaction": "precompact hook runs a command",
    "hook notes up to 2,000 characters": "2,000 characters",
    "subagent stops at 30 tool calls": "30 tool calls",
    "subagents default to the small model": "small model by default",
    "hook timeout now 60 seconds": "60 seconds",
    "hooks.json support ends in 2.6": "ends in 2.6",
    "/context shows tokens per subagent": "/context command",
    "crash with two hooks fixed": "crash",
}


async def test_the_real_model_matches_at_least_10_of_12_scenario_outcomes(site, tmp_path, monkeypatch):
    folder = tmp_path / "Topic Radar"
    write_folder(folder, site)
    outcome, state = await run_scenarios(folder, monkeypatch, model=MODEL)
    assert outcome.code == 0, outcome.message
    results = judge(state)
    matched = sum(ok for ok, _ in results.values())
    print(f"\n{MODEL}: {matched} of {len(results)} scenarios match")
    for name, (ok, why) in results.items():
        print(f"  {name:<4}{'match' if ok else 'MISS ':<6}{TITLES[name][:60]:<62}{why}")
    assert len(results) == 12
    assert matched >= REQUIRED


async def test_read_prompt_recall_on_the_fixed_chunk():
    """A probe, not a pass/fail test: one read call over the T1 page's text, printing how many of the expected
    claims came back with a quote that the quote check keeps."""
    chunk = extract_text(SITE_PAGE.read_text(encoding="utf-8"))
    watch = Watch(name="Scenario watch", slug="scenarios", interests=_section("interests"),
                  not_interested=_section("not_interested"), known_ideas=KNOWN_IDEAS)
    prompt = _prompt(SimpleNamespace(watch=watch), Item(TITLES["T1"], "", ""), KNOWN_IDEAS, chunk)
    answer = await OllamaClient("http://127.0.0.1:11434", MODEL, 300, 8192).call(
        "read", prompt.system, prompt.user, ReadAnswer)
    assert answer.parsed is not None, answer.error
    claims = answer.parsed.claims
    kept = [c for c in claims if quote_found(c.quote, chunk)]
    covered = {label for label, needle in EXPECTED_CLAIMS.items()
               if any(needle in normalize_quote(c.quote) for c in kept)}
    print(f"\nread prompt recall: kept {len(covered)} of {len(EXPECTED_CLAIMS)} expected claims "
          f"({len(claims)} returned, {len(kept)} with a quote found, {answer.seconds:.1f}s)")
    for label in EXPECTED_CLAIMS:
        print(f"  {'kept   ' if label in covered else 'missing'} {label}")
    assert claims  # the answer parsed and the model returned something


def _section(key: str) -> str:
    from ruamel.yaml import YAML
    text = WATCH.format(known="", seeds="")
    return str(YAML(typ="safe").load(text)[key])
