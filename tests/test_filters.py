"""Тесты фильтра заказов."""

from order_scout.config import Config
from order_scout.filters import apply_filter, normalize
from order_scout.models import Order

CFG = Config(
    niches=["телеграм-бот", "telegram-бот", "бот", "парсер", "отчёт"],
    stop_words=["1С", "Битрикс"],
    min_budget_rub=1000,
    max_offers=50,
)


def make_order(title, description="", budget_kop=None, offers_count=None):
    return Order(
        source="demo", external_id="1", url="https://example.com/1",
        title=title, description=description, budget_kop=budget_kop,
        budget_max_kop=None, offers_count=offers_count, created_at=None,
    )


def test_niche_order_passes():
    result = apply_filter(make_order("Нужен Telegram-бот для записи"), CFG)
    assert result.passed and result.reason is None


def test_stop_word():
    result = apply_filter(make_order("Доработать Битрикс-сайт"), CFG)
    assert not result.passed
    assert result.reason == "стоп-слово: Битрикс"


def test_stop_word_lowercase():
    result = apply_filter(make_order("Бот", "обмен с 1с"), CFG)
    assert result.reason == "стоп-слово: 1С"


def test_low_budget():
    result = apply_filter(make_order("Парсер цен", budget_kop=50000), CFG)
    assert result.reason == "бюджет 500 ₽ < 1000 ₽"


def test_unknown_budget_passes():
    assert apply_filter(make_order("Парсер цен", budget_kop=None), CFG).passed


def test_too_many_offers():
    result = apply_filter(make_order("Парсер цен", offers_count=80), CFG)
    assert result.reason == "откликов 80 > 50"


def test_not_our_niche():
    result = apply_filter(make_order("Нарисовать баннер"), CFG)
    assert result.reason == "не наша ниша"


def test_niche_word_with_yo():
    assert apply_filter(make_order("Ежедневный отчет по продажам"), CFG).passed


def test_niche_word_not_inside_other_word():
    # «бот» не должен находиться внутри «обработка»
    result = apply_filter(make_order("Обработка фото"), CFG)
    assert result.reason == "не наша ниша"


def test_normalize():
    assert normalize("ЁЛКА") == "елка"
