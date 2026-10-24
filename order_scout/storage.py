"""Хранилище заказов в SQLite."""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from order_scout.models import Evaluation, Order

# Жизненный цикл заказа:
# new → pending (прошёл фильтр) | filtered_out → evaluated → carded → skipped | replied
STATUSES = ("new", "pending", "filtered_out", "evaluated", "carded", "skipped", "replied")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    external_id    TEXT NOT NULL,
    url            TEXT NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT NOT NULL,
    budget_kop     INTEGER,
    budget_max_kop INTEGER,
    offers_count   INTEGER,
    created_at     TEXT,
    status         TEXT NOT NULL DEFAULT 'new',
    reason         TEXT,
    added_at       TEXT NOT NULL,
    UNIQUE (source, external_id)
);
CREATE TABLE IF NOT EXISTS evaluations (
    order_id      INTEGER PRIMARY KEY REFERENCES orders (id),
    decision      TEXT NOT NULL,
    score         INTEGER NOT NULL,
    days          INTEGER NOT NULL,
    price_kop     INTEGER NOT NULL,
    risks         TEXT NOT NULL,
    reply         TEXT NOT NULL,
    portfolio_url TEXT,
    evaluated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders (id),
    action   TEXT NOT NULL,
    at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class StoredOrder:
    """Заказ из базы вместе со служебными полями."""

    id: int
    order: Order
    status: str
    reason: str | None
    added_at: datetime


def _to_iso(value: datetime | None) -> str | None:
    """Время в базе храним строкой ISO в UTC."""
    return value.astimezone(timezone.utc).isoformat() if value else None


def _from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Storage:
    """Работа с таблицей заказов: добавление без дублей и смена статусов."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        # IF NOT EXISTS: база от прошлой версии открывается без миграций
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def add_orders(self, orders: Iterable[Order]) -> list[int]:
        """Добавляет заказы; уже известные пропускает. Возвращает id новых."""
        new_ids = []
        now = _to_iso(datetime.now(timezone.utc))
        for order in orders:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO orders (source, external_id, url, title,"
                " description, budget_kop, budget_max_kop, offers_count,"
                " created_at, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (order.source, order.external_id, order.url, order.title,
                 order.description, order.budget_kop, order.budget_max_kop,
                 order.offers_count, _to_iso(order.created_at), now),
            )
            # rowcount = 0, если такой заказ уже был (сработал UNIQUE)
            if cursor.rowcount:
                new_ids.append(cursor.lastrowid)
        self._db.commit()
        return new_ids

    def get(self, order_id: int) -> StoredOrder:
        row = self._db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise KeyError(f"Заказ {order_id} не найден")
        return self._row_to_stored(row)

    def by_status(self, status: str) -> list[StoredOrder]:
        """Заказы с указанным статусом, старые первыми."""
        self._check_status(status)
        rows = self._db.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
        return [self._row_to_stored(row) for row in rows]

    def set_status(self, order_id: int, status: str, reason: str | None = None) -> None:
        self._check_status(status)
        self._db.execute(
            "UPDATE orders SET status = ?, reason = ? WHERE id = ?",
            (status, reason, order_id),
        )
        self._db.commit()

    def counts(self) -> dict[str, int]:
        """Сколько заказов в каждом статусе (пустые статусы не выводятся)."""
        rows = self._db.execute("SELECT status, COUNT(*) FROM orders GROUP BY status")
        return {status: count for status, count in rows}

    def save_evaluation(self, order_id: int, ev: Evaluation) -> None:
        """Сохраняет (или заменяет) оценку и переводит заказ в evaluated."""
        self._db.execute(
            "INSERT OR REPLACE INTO evaluations (order_id, decision, score, days,"
            " price_kop, risks, reply, portfolio_url, evaluated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, ev.decision, ev.score, ev.days, ev.price_kop, ev.risks,
             ev.reply, ev.portfolio_url, _to_iso(datetime.now(timezone.utc))),
        )
        self._db.execute("UPDATE orders SET status = 'evaluated' WHERE id = ?", (order_id,))
        self._db.commit()

    def get_evaluation(self, order_id: int) -> Evaluation | None:
        row = self._db.execute(
            "SELECT * FROM evaluations WHERE order_id = ?", (order_id,)
        ).fetchone()
        if row is None:
            return None
        return Evaluation(
            decision=row["decision"], score=row["score"], days=row["days"],
            price_kop=row["price_kop"], risks=row["risks"], reply=row["reply"],
            portfolio_url=row["portfolio_url"],
        )

    def log_action(self, order_id: int, action: str) -> None:
        """Журнал: что и когда происходило с заказом (карточка, нажатия)."""
        self._db.execute(
            "INSERT INTO actions (order_id, action, at) VALUES (?, ?, ?)",
            (order_id, action, _to_iso(datetime.now(timezone.utc))),
        )
        self._db.commit()

    def actions(self, order_id: int) -> list[tuple[str, datetime]]:
        rows = self._db.execute(
            "SELECT action, at FROM actions WHERE order_id = ? ORDER BY id", (order_id,)
        )
        return [(action, _from_iso(at)) for action, at in rows]

    def count_actions_since(self, action: str, since: datetime) -> int:
        """Сколько раз было действие начиная с момента since (для /stats)."""
        row = self._db.execute(
            "SELECT COUNT(*) FROM actions WHERE action = ? AND at >= ?",
            (action, _to_iso(since)),
        ).fetchone()
        return row[0]

    def get_flag(self, name: str) -> bool:
        row = self._db.execute("SELECT value FROM meta WHERE name = ?", (name,)).fetchone()
        return row is not None and row[0] == "1"

    def set_flag(self, name: str, value: bool) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO meta (name, value) VALUES (?, ?)",
            (name, "1" if value else "0"),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _check_status(status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"Неизвестный статус: {status}")

    @staticmethod
    def _row_to_stored(row: sqlite3.Row) -> StoredOrder:
        order = Order(
            source=row["source"],
            external_id=row["external_id"],
            url=row["url"],
            title=row["title"],
            description=row["description"],
            budget_kop=row["budget_kop"],
            budget_max_kop=row["budget_max_kop"],
            offers_count=row["offers_count"],
            created_at=_from_iso(row["created_at"]),
        )
        return StoredOrder(
            id=row["id"],
            order=order,
            status=row["status"],
            reason=row["reason"],
            added_at=_from_iso(row["added_at"]),
        )
