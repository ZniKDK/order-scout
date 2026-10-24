"""Тесты карточки заказа и действий по кнопкам."""

import pytest

from order_scout.bot.cards import TG_LIMIT, apply_action, format_card, format_stats
from order_scout.models import Evaluation
from order_scout.storage import Storage
from tests.test_storage import make_order

EV = Evaluation(
    decision="take", score=8, days=3, price_kop=400000, risks="нужен доступ к API",
    reply="Здравствуйте! Сделаю.", portfolio_url="https://github.com/ZniKDK/tg-lead-bot",
)


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "orders.db")


def stored_with(storage, **kwargs):
    [order_id] = storage.add_orders([make_order("1", **kwargs)])
    storage.save_evaluation(order_id, EV)
    return storage.get(order_id)


def test_card_main_fields(storage):
    card = format_card(stored_with(storage, title="Нужен бот"), EV)
    for part in ("Нужен бот", "5 000 ₽", "откликов: 3", "8/10", "берём", "4 000 ₽", "3 дн.",
                 "нужен доступ к API", "tg-lead-bot"):
        assert part in card.text
    labels = [label for label, _ in card.buttons]
    assert labels == ["Открыть заказ", "Пропустить", "Отправил"]
    assert card.buttons[0][1] == "https://example.com/1"


def test_card_escapes_html(storage):
    card = format_card(stored_with(storage, title="Бот <b>&</b>"), EV)
    assert "Бот &lt;b&gt;&amp;&lt;/b&gt;" in card.text


def test_card_unknown_budget(storage):
    card = format_card(stored_with(storage, budget_kop=None), EV)
    assert "бюджет не указан" in card.text


def test_long_reply_truncated(storage):
    long_ev = Evaluation("take", 8, 3, 400000, "", "а" * 5000, None)
    card = format_card(stored_with(storage), long_ev)
    assert len(card.reply_text) <= TG_LIMIT
    assert "обрезано" in card.reply_text
    assert card.reply_text.startswith("<pre>") and card.reply_text.endswith("</pre>")


def test_reply_escaped_in_pre(storage):
    ev = Evaluation("take", 8, 3, 400000, "", "Цена < 5000 & срок", None)
    card = format_card(stored_with(storage), ev)
    assert card.reply_text == "<pre>Цена &lt; 5000 &amp; срок</pre>"


def test_skip_action(storage):
    stored = stored_with(storage)
    storage.set_status(stored.id, "carded")
    assert apply_action(storage, stored.id, "skip") == "Пропущено"
    assert storage.get(stored.id).status == "skipped"
    assert [a for a, _ in storage.actions(stored.id)] == ["skip"]
    assert apply_action(storage, stored.id, "skip") == "Уже отмечено"


def test_sent_action(storage):
    stored = stored_with(storage)
    storage.set_status(stored.id, "carded")
    apply_action(storage, stored.id, "sent")
    assert storage.get(stored.id).status == "replied"


def test_unknown_action(storage):
    stored = stored_with(storage)
    with pytest.raises(ValueError):
        apply_action(storage, stored.id, "delete")


def test_stats(storage):
    stored = stored_with(storage)
    storage.log_action(stored.id, "carded")
    storage.set_status(stored.id, "carded")
    apply_action(storage, stored.id, "sent")
    text = format_stats(storage)
    assert "карточек: 1" in text
    assert "откликов отправлено: 1" in text
