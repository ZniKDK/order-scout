"""Источник Kwork: страница биржи с JSON-массивом "wants" внутри HTML.

Поля заказа в JSON (проверено 24.10.2026):
id, name — заголовок, description — текст с HTML-сущностями,
priceLimit — желаемый бюджет ("5000.00"), possiblePriceLimit — допустимый,
kwork_count — сколько предложений уже есть, date_create — московское время.
На странице только первые 12 заказов.
"""

import html
import json
import logging
from datetime import datetime, timedelta, timezone

from order_scout.models import Order, parse_rub

log = logging.getLogger(__name__)

# Москва без перехода на летнее время: UTC+3
MSK = timezone(timedelta(hours=3))
_MARKER = '"wants":'


def _rub(value) -> int | None:
    return parse_rub(str(value)) if value not in (None, "") else None


class KworkSource:
    name = "kwork"
    url = "https://kwork.ru/projects"

    def parse(self, payload: str) -> list[Order]:
        start = payload.find(_MARKER)
        if start == -1:
            log.warning("Kwork: на странице нет \"wants\" — вероятно, сменилась вёрстка")
            return []
        try:
            wants, _ = json.JSONDecoder().raw_decode(payload, start + len(_MARKER))
        except json.JSONDecodeError as error:
            log.warning("Kwork: не удалось прочитать \"wants\": %s", error)
            return []

        orders = []
        for want in wants:
            created = want.get("date_create")
            orders.append(Order(
                source=self.name,
                external_id=str(want["id"]),
                url=f"https://kwork.ru/projects/{want['id']}",
                title=html.unescape(want.get("name", "")).strip(),
                description=html.unescape(want.get("description", "")).replace("\r", "").strip(),
                budget_kop=_rub(want.get("priceLimit")),
                budget_max_kop=_rub(want.get("possiblePriceLimit")),
                offers_count=want.get("kwork_count"),
                created_at=(
                    datetime.fromisoformat(created).replace(tzinfo=MSK).astimezone(timezone.utc)
                    if created else None
                ),
            ))
        return orders
