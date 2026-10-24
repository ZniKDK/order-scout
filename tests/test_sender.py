"""Тесты отправки карточек (без сети) и проверки владельца чата."""

import pytest

from order_scout.bot.app import is_owner
from order_scout.bot.sender import send_new_cards
from order_scout.config import Config
from order_scout.models import Evaluation
from order_scout.storage import Storage
from tests.test_storage import make_order

CFG = Config(score_threshold=6)


class FakeSender:
    """Запоминает отправленные карточки; может падать на заданных номерах."""

    def __init__(self, fail_on=()):
        self.sent = []
        self.calls = 0
        self.fail_on = set(fail_on)

    async def send_card(self, card):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("Telegram не ответил")
        self.sent.append(card)


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "orders.db")


def evaluated(storage, external_id, decision, score):
    [order_id] = storage.add_orders([make_order(external_id)])
    storage.save_evaluation(order_id, Evaluation(decision, score, 3, 300000, "", "Сделаю.", None))
    return order_id


async def test_only_good_cards_sent(storage):
    good = evaluated(storage, "1", "take", 8)
    low = evaluated(storage, "2", "take", 4)
    bad = evaluated(storage, "3", "skip", 9)
    sender = FakeSender()
    assert await send_new_cards(storage, CFG, sender) == 1
    assert storage.get(good).status == "carded"
    assert [a for a, _ in storage.actions(good)] == ["carded"]
    assert storage.get(low).status == "skipped"
    assert storage.get(low).reason == "балл 4 < 6"
    assert storage.get(bad).status == "skipped"
    assert storage.get(bad).reason == "оценка: не берём"


async def test_send_error_keeps_evaluated(storage):
    first = evaluated(storage, "1", "take", 8)
    second = evaluated(storage, "2", "stages", 7)
    sender = FakeSender(fail_on={1})
    assert await send_new_cards(storage, CFG, sender) == 1
    assert storage.get(first).status == "evaluated"
    assert storage.get(second).status == "carded"


async def test_paused_sends_nothing(storage):
    order_id = evaluated(storage, "1", "take", 8)
    storage.set_flag("paused", True)
    assert await send_new_cards(storage, CFG, FakeSender()) == 0
    assert storage.get(order_id).status == "evaluated"


def test_is_owner():
    assert is_owner(42, 42)
    assert not is_owner(7, 42)
    assert not is_owner(None, 42)
