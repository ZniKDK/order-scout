"""Тесты разбора страницы заказов Kwork."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from order_scout.sources.kwork import KworkSource

PAYLOAD = (Path(__file__).parent / "fixtures" / "kwork_projects.html").read_text(encoding="utf-8")


def test_parses_three_orders():
    orders = KworkSource().parse(PAYLOAD)
    assert len(orders) == 3
    assert all(o.source == "kwork" for o in orders)


def test_first_order_fields():
    order = KworkSource().parse(PAYLOAD)[0]
    assert order.external_id == "3269206"
    assert order.url == "https://kwork.ru/projects/3269206"
    assert order.title == "Поиск и мониторинг открытых рекламных объявлений"
    assert order.budget_kop == 500000
    assert order.budget_max_kop == 1500000
    assert order.offers_count == 0
    # На странице московское время, в модели — UTC
    assert order.created_at == datetime(2026, 10, 24, 13, 45, 8, tzinfo=timezone.utc)


def test_description_cleaned():
    description = KworkSource().parse(PAYLOAD)[0].description
    assert "\r" not in description
    assert "&quot;" not in description
    assert '"Рабочие дома"' in description


def test_offers_count_as_string():
    page = '"wants":[{"id": 5, "name": "Бот", "kwork_count": "12"}]'
    assert KworkSource().parse(page)[0].offers_count == 12


def test_urls_for_category_and_pages():
    assert KworkSource(category=11, pages=2).urls == [
        "https://kwork.ru/projects?c=11&page=1",
        "https://kwork.ru/projects?c=11&page=2",
    ]
    assert KworkSource().urls == ["https://kwork.ru/projects"]


def test_page_without_wants(caplog):
    with caplog.at_level(logging.WARNING):
        assert KworkSource().parse("<html><body>Новая вёрстка</body></html>") == []
    assert "wants" in caplog.text
