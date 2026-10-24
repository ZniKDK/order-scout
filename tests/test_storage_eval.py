"""Тесты хранения оценок, журнала действий и флагов."""

import pytest

from order_scout.models import Evaluation
from order_scout.storage import Storage
from tests.test_storage import make_order

EV = Evaluation(
    decision="take", score=8, days=3, price_kop=400000,
    risks="нужен доступ к API", reply="Здравствуйте! Сделаю.",
    portfolio_url="https://github.com/ZniKDK/tg-lead-bot",
)


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "orders.db")


def test_save_and_get_evaluation(storage):
    [order_id] = storage.add_orders([make_order("1")])
    storage.set_status(order_id, "pending")
    storage.save_evaluation(order_id, EV)
    assert storage.get_evaluation(order_id) == EV
    assert storage.get(order_id).status == "evaluated"


def test_evaluation_replaced(storage):
    [order_id] = storage.add_orders([make_order("1")])
    storage.save_evaluation(order_id, EV)
    other = Evaluation("skip", 2, 1, 0, "", "", None)
    storage.save_evaluation(order_id, other)
    assert storage.get_evaluation(order_id) == other


def test_no_evaluation(storage):
    [order_id] = storage.add_orders([make_order("1")])
    assert storage.get_evaluation(order_id) is None


def test_actions_in_order(storage):
    [order_id] = storage.add_orders([make_order("1")])
    storage.log_action(order_id, "carded")
    storage.log_action(order_id, "skip")
    assert [action for action, _ in storage.actions(order_id)] == ["carded", "skip"]


def test_flags(storage):
    assert storage.get_flag("paused") is False
    storage.set_flag("paused", True)
    assert storage.get_flag("paused") is True
    storage.set_flag("paused", False)
    assert storage.get_flag("paused") is False
