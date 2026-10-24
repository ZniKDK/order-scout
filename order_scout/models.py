"""Модель заказа и вспомогательные функции для сумм."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Order:
    """Заказ с биржи в едином для всех источников виде.

    Суммы хранятся в копейках; None — сумма неизвестна (не путать с нулём).
    """

    source: str                  # "flru" | "kwork" | "demo"
    external_id: str             # id заказа на бирже
    url: str
    title: str
    description: str
    budget_kop: int | None       # желаемый бюджет
    budget_max_kop: int | None   # допустимый бюджет (есть только на Kwork)
    offers_count: int | None     # сколько откликов уже есть
    created_at: datetime | None  # когда заказ опубликован (с часовым поясом)


# Решение по заказу: берём, берём этапами, не рекомендую
DECISIONS = ("take", "stages", "skip")


@dataclass(frozen=True)
class Evaluation:
    """Оценка заказа и готовый отклик."""

    decision: str               # take | stages | skip
    score: int                  # 0–10
    days: int                   # срок, дней
    price_kop: int              # наша цена
    risks: str                  # риски одной строкой
    reply: str                  # текст отклика (пустой допустим только при skip)
    portfolio_url: str | None   # похожий проект — для себя, не для отклика


# Число: цифры с пробелами-разделителями тысяч и необязательной дробной частью
_NUMBER_RE = re.compile(r"\d[\d\s ]*(?:[.,]\d{1,2})?")


def parse_rub(text: str) -> int | None:
    """Переводит сумму в рублях из текста в копейки.

    "1 500 ₽" -> 150000, "1500.50" -> 150050, "по договорённости" -> None.
    """
    match = _NUMBER_RE.search(text or "")
    if not match:
        return None
    # Убираем обычные и неразрывные пробелы, запятую считаем десятичной точкой
    raw = re.sub(r"[\s ]", "", match.group()).replace(",", ".")
    try:
        return int(Decimal(raw) * 100)
    except InvalidOperation:
        return None
