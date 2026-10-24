"""Отбор заказов по нишам, стоп-словам, бюджету и числу откликов."""

import re
from dataclasses import dataclass

from order_scout.config import Config
from order_scout.models import Order


@dataclass(frozen=True)
class FilterResult:
    """Итог проверки: прошёл ли заказ и почему отсеян."""

    passed: bool
    reason: str | None = None


def normalize(text: str) -> str:
    """Приводит текст к виду для сравнения: без регистра, «ё» как «е»."""
    return text.casefold().replace("ё", "е")


def _has_word(text: str, word: str) -> bool:
    """Ищет слово с начала слова: «бот» найдётся в «бота», но не в «работа»."""
    pattern = r"(?<!\w)" + re.escape(normalize(word))
    return re.search(pattern, text) is not None


def apply_filter(order: Order, cfg: Config) -> FilterResult:
    """Проверяет заказ; первая сработавшая проверка даёт причину отсева."""
    text = normalize(f"{order.title}\n{order.description}")

    for word in cfg.stop_words:
        if _has_word(text, word):
            return FilterResult(False, f"стоп-слово: {word}")

    # Неизвестный бюджет не отсеиваем: часто он «по договорённости»
    if order.budget_kop is not None and order.budget_kop < cfg.min_budget_rub * 100:
        return FilterResult(False, f"бюджет {order.budget_kop // 100} ₽ < {cfg.min_budget_rub} ₽")

    if order.offers_count is not None and order.offers_count > cfg.max_offers:
        return FilterResult(False, f"откликов {order.offers_count} > {cfg.max_offers}")

    if not any(_has_word(text, word) for word in cfg.niches):
        return FilterResult(False, "не наша ниша")

    return FilterResult(True)
