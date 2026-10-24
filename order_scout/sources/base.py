"""Общий интерфейс источника заказов."""

from typing import Protocol

from order_scout.models import Order


class Source(Protocol):
    """Источник: адрес ленты и разбор её содержимого в заказы.

    parse — чистая функция без сети, поэтому её легко проверять на образцах.
    """

    name: str
    url: str

    def parse(self, payload: str) -> list[Order]: ...
