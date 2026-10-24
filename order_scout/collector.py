"""Сборщик: обходит источники, сохраняет новые заказы и прогоняет их через фильтр."""

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from order_scout.config import Config
from order_scout.filters import apply_filter
from order_scout.models import Order
from order_scout.sources.base import Source
from order_scout.sources.demo import DemoSource
from order_scout.sources.flru import FlruSource
from order_scout.sources.kwork import KworkSource
from order_scout.storage import Storage

log = logging.getLogger(__name__)

SOURCES: dict[str, type] = {
    "flru": FlruSource,
    "kwork": KworkSource,
    "demo": DemoSource,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
}
TIMEOUT_SEC = 20


@dataclass
class CollectReport:
    """Итог одного прохода сборщика."""

    new: int = 0
    pending: int = 0
    filtered: int = 0
    errors: list[str] = field(default_factory=list)


PAGE_PAUSE_SEC = 2   # пауза между страницами одной биржи — не частим


def make_sources(names: list[str], cfg: Config) -> list[Source]:
    """Создаёт источники по именам из конфига (Kwork — с разделом и числом страниц)."""
    sources = []
    for name in names:
        if name == "kwork":
            sources.append(KworkSource(category=cfg.kwork_category, pages=cfg.kwork_pages))
        else:
            sources.append(SOURCES[name]())
    return sources


async def fetch(source: Source, client: httpx.AsyncClient) -> list[Order]:
    """Скачивает ленту источника (одну или несколько страниц) и разбирает её. Ошибки сети пробрасывает."""
    local_path = getattr(source, "local_path", None)
    if local_path is not None:
        return source.parse(local_path.read_text(encoding="utf-8"))
    orders: dict[str, Order] = {}
    urls = getattr(source, "urls", [source.url])
    for number, url in enumerate(urls):
        if number:
            await asyncio.sleep(PAGE_PAUSE_SEC)
        response = await client.get(url, headers=HEADERS, timeout=TIMEOUT_SEC)
        response.raise_for_status()
        # Пока листаем, заказы сдвигаются: один и тот же может попасть на две страницы
        for order in source.parse(response.text):
            orders.setdefault(order.external_id, order)
    return list(orders.values())


async def collect_once(
    storage: Storage, cfg: Config, sources: list[Source], client: httpx.AsyncClient
) -> CollectReport:
    """Один проход: ошибка одного источника не мешает остальным."""
    report = CollectReport()
    for source in sources:
        try:
            orders = await fetch(source, client)
        except httpx.HTTPError as error:
            message = f"{source.name}: {type(error).__name__}: {error}"
            log.warning("Источник недоступен — %s", message)
            report.errors.append(message)
            continue
        except Exception as error:  # noqa: BLE001 — биржа прислала неожиданные данные
            message = f"{source.name}: ошибка разбора: {type(error).__name__}: {error}"
            log.exception("Источник не разобран — %s", message)
            report.errors.append(message)
            continue

        for order_id in storage.add_orders(orders):
            report.new += 1
            result = apply_filter(storage.get(order_id).order, cfg)
            if result.passed:
                storage.set_status(order_id, "pending")
                report.pending += 1
            else:
                storage.set_status(order_id, "filtered_out", result.reason)
                report.filtered += 1
    return report
