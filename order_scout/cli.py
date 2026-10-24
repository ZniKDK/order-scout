"""Командная строка: python -m order_scout <команда>."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

from order_scout.collector import SOURCES, collect_once
from order_scout.config import ConfigError, load_config
from order_scout.storage import Storage

DEFAULT_CONFIG = Path("config.yaml")
DEFAULT_DB = Path("data") / "orders.db"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="order_scout", description="Сбор и отбор заказов с бирж")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="один проход по биржам")
    collect.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    collect.add_argument("--db", type=Path, default=DEFAULT_DB)
    collect.add_argument("--demo", action="store_true", help="вымышленные заказы вместо бирж")

    stats = commands.add_parser("stats", help="сколько заказов в каждом статусе")
    stats.add_argument("--db", type=Path, default=DEFAULT_DB)
    return parser


def _setup_logging(db_path: Path) -> None:
    """Лог пишем рядом с базой, чтобы всё рабочее лежало в data/."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=db_path.parent / "order-scout.log",
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _collect(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
    except ConfigError as error:
        print(f"Ошибка настроек: {error}", file=sys.stderr)
        return 2
    names = ["demo"] if args.demo else cfg.sources
    sources = [SOURCES[name]() for name in names]
    storage = Storage(args.db)
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            report = await collect_once(storage, cfg, sources, client)
    finally:
        storage.close()
    print(f"новых: {report.new}, к оценке: {report.pending}, отсеяно: {report.filtered}")
    for error in report.errors:
        print(f"ошибка: {error}")
    return 0


def _stats(args: argparse.Namespace) -> int:
    storage = Storage(args.db)
    try:
        counts = storage.counts()
    finally:
        storage.close()
    if not counts:
        print("в базе пока нет заказов")
    for status, count in counts.items():
        print(f"{status}: {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Консоль Windows (cp1251) не знает часть символов — заменяем, а не падаем
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = _build_parser().parse_args(argv)
    _setup_logging(args.db)
    if args.command == "collect":
        return asyncio.run(_collect(args))
    return _stats(args)
