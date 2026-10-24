"""Тесты хранилища заказов."""

from datetime import datetime, timezone

import pytest

from order_scout.models import Order
from order_scout.storage import Storage


def make_order(external_id="1", **kwargs):
    data = dict(
        source="demo",
        external_id=external_id,
        url=f"https://example.com/{external_id}",
        title="Нужен бот",
        description="Описание",
        budget_kop=500000,
        budget_max_kop=None,
        offers_count=3,
        created_at=datetime(2026, 10, 24, 9, 30, tzinfo=timezone.utc),
    )
    data.update(kwargs)
    return Order(**data)


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "orders.db")


def test_add_new_orders(storage):
    ids = storage.add_orders([make_order("1"), make_order("2")])
    assert len(ids) == 2
    stored = storage.get(ids[0])
    assert stored.status == "new"
    assert stored.order == make_order("1")


def test_duplicate_keeps_status(storage):
    [order_id] = storage.add_orders([make_order("1")])
    storage.set_status(order_id, "pending")
    assert storage.add_orders([make_order("1")]) == []
    assert storage.get(order_id).status == "pending"


def test_unknown_status(storage):
    [order_id] = storage.add_orders([make_order("1")])
    with pytest.raises(ValueError):
        storage.set_status(order_id, "lol")


def test_by_status_and_counts(storage):
    first, second = storage.add_orders([make_order("1"), make_order("2")])
    storage.set_status(first, "pending")
    storage.set_status(second, "filtered_out", "не наша ниша")
    assert [s.id for s in storage.by_status("pending")] == [first]
    assert storage.get(second).reason == "не наша ниша"
    assert storage.counts() == {"pending": 1, "filtered_out": 1}


def test_none_values_roundtrip(storage):
    order = make_order("1", budget_kop=None, offers_count=None, created_at=None)
    [order_id] = storage.add_orders([order])
    assert storage.get(order_id).order == order
