"""Демо-оценщик по простым правилам: для тестов и запуска без внешнего оценщика.

Правила нарочно простые и прозрачные:
балл = 5 + по 1 за каждое слово ниши (не больше 3) + 1, если бюджет ≥ 3 000 ₽,
− 2, если откликов больше 20; итог в пределах 0–10.
"""

from order_scout.config import Config, PortfolioItem
from order_scout.filters import has_word, normalize
from order_scout.models import Evaluation, Order

MIN_PRICE_KOP = 200000          # не дешевле 2 000 ₽
DEFAULT_PRICE_KOP = 300000      # бюджет не указан → 3 000 ₽
DEFAULT_DAYS = 3


def _text(order: Order) -> str:
    return normalize(f"{order.title}\n{order.description}")


def pick_portfolio(order: Order, items: list[PortfolioItem]) -> PortfolioItem | None:
    """Проект портфолио с наибольшим числом совпавших тегов."""
    text = _text(order)
    best, best_hits = None, 0
    for item in items:
        hits = sum(has_word(text, tag) for tag in item.tags)
        if hits > best_hits:
            best, best_hits = item, hits
    return best


def evaluate_by_rules(order: Order, cfg: Config) -> Evaluation:
    text = _text(order)
    score = 5 + min(3, sum(has_word(text, word) for word in cfg.niches))
    if order.budget_kop is not None and order.budget_kop >= 300000:
        score += 1
    if order.offers_count is not None and order.offers_count > 20:
        score -= 2
    score = max(0, min(10, score))

    if order.budget_kop is None:
        price_kop = DEFAULT_PRICE_KOP
    else:
        # 80 % бюджета: отзывов пока нет, поэтому цена ниже рынка
        price_kop = max(MIN_PRICE_KOP, order.budget_kop * 8 // 10)

    decision = "take" if score >= cfg.score_threshold else "skip"
    portfolio = pick_portfolio(order, cfg.portfolio)
    reply = (
        f"Здравствуйте! Сделаю: «{order.title}».\n"
        f"Срок — {DEFAULT_DAYS} дня, цена — {price_kop // 100} ₽.\n"
        "На площадке я недавно, поэтому цена ниже рынка. "
        "Готов ответить на вопросы и уточнить детали."
    ) if decision == "take" else ""
    return Evaluation(
        decision=decision,
        score=score,
        days=DEFAULT_DAYS,
        price_kop=price_kop,
        risks="демо-оценка по правилам",
        reply=reply,
        portfolio_url=portfolio.url if portfolio else None,
    )
