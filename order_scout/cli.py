"""Командная строка: python -m order_scout <команда>."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

from order_scout.collector import SOURCES, collect_once
from order_scout.config import ConfigError, load_config
from order_scout.exchange import export_pending, import_evaluations
from order_scout.rules_evaluator import evaluate_by_rules
from order_scout.storage import Storage

DEFAULT_CONFIG = Path("config.yaml")
DEFAULT_DB = Path("data") / "orders.db"
DEFAULT_PENDING = Path("data") / "pending.json"
DEFAULT_EVALUATIONS = Path("data") / "evaluations.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="order_scout", description="Сбор и отбор заказов с бирж")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="один проход по биржам")
    collect.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    collect.add_argument("--db", type=Path, default=DEFAULT_DB)
    collect.add_argument("--demo", action="store_true", help="вымышленные заказы вместо бирж")

    stats = commands.add_parser("stats", help="сколько заказов в каждом статусе")
    stats.add_argument("--db", type=Path, default=DEFAULT_DB)

    export = commands.add_parser("export", help="выгрузить заказы для внешнего оценщика")
    export.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    export.add_argument("--db", type=Path, default=DEFAULT_DB)
    export.add_argument("--out", type=Path, default=DEFAULT_PENDING)

    imp = commands.add_parser("import", help="принять оценки внешнего оценщика")
    imp.add_argument("--db", type=Path, default=DEFAULT_DB)
    imp.add_argument("--file", type=Path, default=DEFAULT_EVALUATIONS)

    evaluate = commands.add_parser("evaluate", help="оценить заказы встроенными правилами")
    evaluate.add_argument("--rules", action="store_true", required=True,
                          help="демо-оценка по простым правилам")
    evaluate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    evaluate.add_argument("--db", type=Path, default=DEFAULT_DB)
    return parser


def _load_config_or_exit(path: Path):
    """Конфиг или None с сообщением об ошибке (код выхода 2 решает вызывающий)."""
    try:
        return load_config(path)
    except ConfigError as error:
        print(f"Ошибка настроек: {error}", file=sys.stderr)
        return None


def _export(args: argparse.Namespace) -> int:
    cfg = _load_config_or_exit(args.config)
    if cfg is None:
        return 2
    storage = Storage(args.db)
    try:
        count = export_pending(storage, cfg, args.out)
    finally:
        storage.close()
    print(f"выгружено: {count}")
    return 0


def _import(args: argparse.Namespace) -> int:
    if not args.file.exists():
        print("новых оценок нет")
        return 0
    storage = Storage(args.db)
    try:
        report = import_evaluations(storage, args.file)
    finally:
        storage.close()
    print(f"принято: {report.imported}, отклонено: {len(report.invalid)}")
    for line in report.invalid:
        print(f"  {line}")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    cfg = _load_config_or_exit(args.config)
    if cfg is None:
        return 2
    storage = Storage(args.db)
    try:
        pending = storage.by_status("pending")
        for stored in pending:
            storage.save_evaluation(stored.id, evaluate_by_rules(stored.order, cfg))
    finally:
        storage.close()
    print(f"оценено: {len(pending)}")
    return 0


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
    cfg = _load_config_or_exit(args.config)
    if cfg is None:
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
    handlers = {"stats": _stats, "export": _export, "import": _import, "evaluate": _evaluate}
    return handlers[args.command](args)
