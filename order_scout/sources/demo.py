"""Демо-источник: вымышленные заказы из demo/orders.json (без сети)."""

import json
from pathlib import Path

from order_scout.models import Order

DEMO_FILE = Path(__file__).resolve().parent.parent.parent / "demo" / "orders.json"


class DemoSource:
    name = "demo"
    url = "demo://orders.json"

    def __init__(self, path: Path = DEMO_FILE) -> None:
        # Сборщик читает этот файл вместо запроса в сеть
        self.local_path = Path(path)

    def parse(self, payload: str) -> list[Order]:
        return [
            Order(
                source=self.name,
                external_id=item["id"],
                url=f"https://example.com/orders/{item['id']}",
                title=item["title"],
                description=item["description"],
                budget_kop=item["budget_rub"] * 100 if item["budget_rub"] is not None else None,
                budget_max_kop=None,
                offers_count=item["offers_count"],
                created_at=None,
            )
            for item in json.loads(payload)
        ]
