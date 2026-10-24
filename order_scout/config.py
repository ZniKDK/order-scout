"""Загрузка и проверка настроек из config.yaml."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Ошибка в файле настроек: текст ошибки понятен пользователю."""


@dataclass(frozen=True)
class PortfolioItem:
    """Проект из портфолио, на который можно сослаться в отклике."""

    name: str
    url: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    """Настройки сбора и отбора заказов."""

    # По умолчанию — только биржи с бесплатными откликами (на FL.ru отклик платный)
    sources: list[str] = field(default_factory=lambda: ["kwork"])
    niches: list[str] = field(default_factory=list)
    stop_words: list[str] = field(default_factory=list)
    min_budget_rub: int = 1000
    max_offers: int = 50
    score_threshold: int = 6
    collect_interval_min: int = 15
    portfolio: list[PortfolioItem] = field(default_factory=list)


def load_config(path: Path) -> Config:
    """Читает YAML, подставляет значения по умолчанию и проверяет границы."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Файл настроек не найден: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ConfigError(f"Ошибка в YAML: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError("Файл настроек должен быть словарём «ключ: значение»")

    portfolio = [
        PortfolioItem(name=item["name"], url=item["url"], tags=item.get("tags", []))
        for item in data.pop("portfolio", None) or []
    ]
    known = set(Config.__dataclass_fields__) - {"portfolio"}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"Неизвестные параметры: {', '.join(sorted(unknown))}")

    cfg = Config(**data, portfolio=portfolio)
    if cfg.collect_interval_min < 10:
        raise ConfigError("collect_interval_min должен быть не меньше 10 минут")
    if not 0 <= cfg.score_threshold <= 10:
        raise ConfigError("score_threshold должен быть от 0 до 10")
    if cfg.min_budget_rub < 0 or cfg.max_offers < 0:
        raise ConfigError("min_budget_rub и max_offers не могут быть отрицательными")
    return cfg
