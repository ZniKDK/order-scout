"""Тесты загрузки config.yaml."""

from pathlib import Path

import pytest

from order_scout.config import ConfigError, load_config

EXAMPLE = Path(__file__).parent.parent / "config.example.yaml"


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_example_config_loads():
    cfg = load_config(EXAMPLE)
    assert "парсер" in cfg.niches
    assert "Битрикс" in cfg.stop_words
    assert cfg.portfolio and cfg.portfolio[0].url.startswith("https://")


def test_defaults_for_missing_fields(tmp_path):
    cfg = load_config(write(tmp_path, "niches: [бот]\n"))
    assert cfg.sources == ["kwork"]
    assert cfg.min_budget_rub == 1000
    assert cfg.max_offers == 50
    assert cfg.score_threshold == 6
    assert cfg.collect_interval_min == 15
    assert cfg.stop_words == []
    assert cfg.portfolio == []
    assert cfg.kwork_category == 11
    assert cfg.kwork_pages == 3


def test_kwork_pages_range(tmp_path):
    with pytest.raises(ConfigError, match="kwork_pages"):
        load_config(write(tmp_path, "kwork_pages: 0\n"))


def test_interval_too_small(tmp_path):
    with pytest.raises(ConfigError, match="не меньше 10 минут"):
        load_config(write(tmp_path, "collect_interval_min: 5\n"))


def test_threshold_out_of_range(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, "score_threshold: 11\n"))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="не найден"):
        load_config(tmp_path / "nope.yaml")
