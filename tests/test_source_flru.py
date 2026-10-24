"""Тесты разбора RSS-ленты FL.ru."""

from datetime import datetime, timezone
from pathlib import Path

from order_scout.sources.flru import FlruSource

PAYLOAD = (Path(__file__).parent / "fixtures" / "flru_rss.xml").read_text(encoding="utf-8")


def test_parses_all_items():
    orders = FlruSource().parse(PAYLOAD)
    assert [o.external_id for o in orders] == ["5526446", "5526565", "5526566"]
    assert all(o.source == "flru" for o in orders)


def test_budget_from_title_and_title_cleaned():
    order = FlruSource().parse(PAYLOAD)[1]
    assert order.budget_kop == 1000000
    assert order.title == "Продать курс Skillbox за 120000 ваши 10000"
    assert order.budget_max_kop is None
    assert order.offers_count is None


def test_budget_for_all_and_unescaped():
    order = FlruSource().parse(PAYLOAD)[0]
    assert order.budget_kop == 50000
    assert "Бюджет" not in order.title
    assert "&#" not in order.title


def test_no_budget():
    assert FlruSource().parse(PAYLOAD)[2].budget_kop is None


def test_created_at_with_timezone():
    order = FlruSource().parse(PAYLOAD)[0]
    assert order.created_at == datetime(2026, 10, 24, 12, 16, 56, tzinfo=timezone.utc)
    assert order.url.startswith("https://www.fl.ru/projects/5526446/")


def test_for_all_tail_without_budget_removed():
    rss = (
        "<rss><channel><item><title>Бот для автоматизации (для всех)</title>"
        "<link>https://www.fl.ru/projects/1/bot.html</link></item></channel></rss>"
    )
    order = FlruSource().parse(rss)[0]
    assert order.title == "Бот для автоматизации"
    assert order.budget_kop is None


def test_broken_xml_returns_empty():
    assert FlruSource().parse("<rss><channel><item>") == []
