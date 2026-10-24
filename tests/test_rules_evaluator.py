"""Тесты демо-оценщика по правилам."""

from order_scout.config import Config, PortfolioItem
from order_scout.rules_evaluator import evaluate_by_rules, pick_portfolio
from tests.test_storage import make_order

CFG = Config(
    niches=["telegram-бот", "бот", "парсер", "лендинг"],
    portfolio=[
        PortfolioItem("Лендинг", "https://github.com/ZniKDK/landing-demo", ["лендинг"]),
        PortfolioItem("Бот", "https://github.com/ZniKDK/tg-lead-bot", ["бот", "telegram"]),
    ],
)


def test_good_order():
    order = make_order(title="Telegram-бот, парсер", budget_kop=800000, offers_count=3)
    ev = evaluate_by_rules(order, CFG)
    assert ev.decision == "take"
    assert ev.score == 9
    assert ev.price_kop == 640000
    assert ev.days == 3
    assert ev.portfolio_url == "https://github.com/ZniKDK/tg-lead-bot"
    assert "Сделаю" in ev.reply and "Telegram-бот, парсер" in ev.reply


def test_unknown_budget_price():
    ev = evaluate_by_rules(make_order(title="Нужен бот", budget_kop=None), CFG)
    assert ev.price_kop == 300000


def test_low_price_floor():
    ev = evaluate_by_rules(make_order(title="Нужен бот", budget_kop=200000), CFG)
    assert ev.price_kop == 200000


def test_score_in_range_and_skip():
    order = make_order(title="Что-то", description="", budget_kop=None, offers_count=40)
    ev = evaluate_by_rules(order, CFG)
    assert 0 <= ev.score <= 10
    assert ev.decision == "skip"


def test_no_portfolio_match():
    assert pick_portfolio(make_order(title="Монтаж видео", description=""), CFG.portfolio) is None
