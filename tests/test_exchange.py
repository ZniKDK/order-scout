"""Тесты обмена с внешним оценщиком."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from order_scout.config import Config, PortfolioItem
from order_scout.exchange import EXPORT_LIMIT, export_pending, import_evaluations
from order_scout.storage import Storage
from tests.test_storage import make_order

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
CFG = Config(portfolio=[PortfolioItem("Бот", "https://github.com/ZniKDK/tg-lead-bot", ["бот"])])


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "orders.db")


def add_pending(storage, count, age=timedelta(hours=1)):
    """Добавляет заказы в pending с заданным «возрастом»."""
    ids = storage.add_orders([make_order(f"{age}-{n}") for n in range(count)])
    for order_id in ids:
        storage.set_status(order_id, "pending")
        storage._db.execute(
            "UPDATE orders SET added_at = ? WHERE id = ?",
            ((NOW - age + timedelta(seconds=order_id)).isoformat(), order_id),
        )
    storage._db.commit()
    return ids


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_export_only_fresh_pending(storage, tmp_path):
    ids = add_pending(storage, 2)
    [old_id] = add_pending(storage, 1, age=timedelta(hours=30))
    [other] = storage.add_orders([make_order("filtered")])
    storage.set_status(other, "filtered_out", "не наша ниша")

    path = tmp_path / "pending.json"
    assert export_pending(storage, CFG, path, now=NOW) == 2
    data = read(path)
    assert {o["id"] for o in data["orders"]} == set(ids)
    assert data["score_threshold"] == 6
    assert data["portfolio"][0]["url"] == "https://github.com/ZniKDK/tg-lead-bot"
    assert storage.get(old_id).status == "skipped"
    assert storage.get(old_id).reason == "устарел"


def test_export_limit_newest_first(storage, tmp_path):
    ids = add_pending(storage, EXPORT_LIMIT + 5)
    path = tmp_path / "pending.json"
    assert export_pending(storage, CFG, path, now=NOW) == EXPORT_LIMIT
    exported = [o["id"] for o in read(path)["orders"]]
    assert exported[0] == ids[-1]
    assert len(exported) == EXPORT_LIMIT


def test_export_money_in_rubles_and_utf8(storage, tmp_path):
    [order_id] = add_pending(storage, 1)
    storage._db.execute("UPDATE orders SET budget_max_kop = NULL WHERE id = ?", (order_id,))
    storage._db.commit()
    path = tmp_path / "pending.json"
    export_pending(storage, CFG, path, now=NOW)
    order = read(path)["orders"][0]
    assert order["budget_rub"] == 5000
    assert order["budget_max_rub"] is None
    assert "Нужен бот" in path.read_text(encoding="utf-8")


def good_record(order_id, **kwargs):
    record = dict(
        id=order_id, decision="take", score=8, days=3, price_rub=4000,
        risks="нет", reply="Здравствуйте! Сделаю.", portfolio_url=None,
    )
    record.update(kwargs)
    return record


def write_evaluations(tmp_path, records):
    path = tmp_path / "evaluations.json"
    path.write_text(json.dumps({"evaluations": records}, ensure_ascii=False), encoding="utf-8")
    return path


def test_import_good_record(storage, tmp_path):
    [order_id] = add_pending(storage, 1)
    path = write_evaluations(tmp_path, [good_record(order_id)])
    report = import_evaluations(storage, path)
    assert report.imported == 1 and report.invalid == []
    ev = storage.get_evaluation(order_id)
    assert ev.price_kop == 400000 and ev.decision == "take"
    assert not path.exists()
    assert (tmp_path / "evaluations.imported.json").exists()


def test_import_broken_json(storage, tmp_path):
    path = tmp_path / "evaluations.json"
    path.write_text("{не json", encoding="utf-8")
    report = import_evaluations(storage, path)
    assert report.imported == 0
    assert len(report.invalid) == 1


@pytest.mark.parametrize("changes", [
    {"id": 999},
    {"decision": "maybe"},
    {"score": 15},
    {"days": 0},
    {"price_rub": -1},
    {"reply": ""},
    {"extra": 1},
    {"score": "8"},
])
def test_import_invalid_record_stays_pending(storage, tmp_path, changes):
    [order_id] = add_pending(storage, 1)
    path = write_evaluations(tmp_path, [good_record(order_id, **changes)])
    report = import_evaluations(storage, path)
    assert report.imported == 0
    assert len(report.invalid) == 1
    assert storage.get(order_id).status == "pending"


def test_import_not_pending_order(storage, tmp_path):
    [order_id] = add_pending(storage, 1)
    storage.set_status(order_id, "skipped")
    report = import_evaluations(storage, write_evaluations(tmp_path, [good_record(order_id)]))
    assert report.imported == 0 and str(order_id) in report.invalid[0]


def test_import_skip_with_empty_reply_ok(storage, tmp_path):
    [order_id] = add_pending(storage, 1)
    record = good_record(order_id, decision="skip", reply="", price_rub=0)
    assert import_evaluations(storage, write_evaluations(tmp_path, [record])).imported == 1
