"""Обмен с внешним оценщиком через JSON-файлы.

export_pending пишет заказы к оценке в pending.json, внешний оценщик
отвечает файлом evaluations.json, import_evaluations строго проверяет
каждую запись. Неверная запись не принимается, заказ остаётся pending.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from order_scout.config import Config
from order_scout.models import DECISIONS, Evaluation
from order_scout.storage import Storage

log = logging.getLogger(__name__)

EXPORT_LIMIT = 30                 # больше за один раз не оцениваем
MAX_AGE = timedelta(hours=24)     # старые заказы уже разобраны другими

_FIELDS = {"id", "decision", "score", "days", "price_rub", "risks", "reply", "portfolio_url"}


@dataclass
class ImportReport:
    """Итог приёма оценок."""

    imported: int = 0
    invalid: list[str] = field(default_factory=list)


def _rub(kop: int | None) -> int | None:
    return kop // 100 if kop is not None else None


def export_pending(storage: Storage, cfg: Config, path: Path, now: datetime | None = None) -> int:
    """Выгружает свежие заказы pending; устаревшие помечает skipped. Возвращает число выгруженных."""
    now = now or datetime.now(timezone.utc)
    fresh = []
    for stored in storage.by_status("pending"):
        if now - stored.added_at > MAX_AGE:
            storage.set_status(stored.id, "skipped", "устарел")
        else:
            fresh.append(stored)
    # Свежие первыми: на новый заказ меньше конкурентов
    fresh.sort(key=lambda s: s.added_at, reverse=True)
    fresh = fresh[:EXPORT_LIMIT]

    data = {
        "generated_at": now.isoformat(),
        "score_threshold": cfg.score_threshold,
        "portfolio": [asdict(item) for item in cfg.portfolio],
        "orders": [
            {
                "id": s.id,
                "source": s.order.source,
                "url": s.order.url,
                "title": s.order.title,
                "description": s.order.description,
                "budget_rub": _rub(s.order.budget_kop),
                "budget_max_rub": _rub(s.order.budget_max_kop),
                "offers_count": s.order.offers_count,
            }
            for s in fresh
        ],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(fresh)


def _is_int(value) -> bool:
    # bool — тоже int в Python, но баллом быть не может
    return isinstance(value, int) and not isinstance(value, bool)


def _check_record(record, storage: Storage) -> str | None:
    """Возвращает причину отказа или None, если запись верна."""
    if not isinstance(record, dict):
        return "запись не является объектом"
    keys = set(record)
    if keys != _FIELDS:
        missing, extra = _FIELDS - keys, keys - _FIELDS
        parts = []
        if missing:
            parts.append(f"нет полей: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"лишние поля: {', '.join(sorted(extra))}")
        return "; ".join(parts)
    if not _is_int(record["id"]):
        return "id должен быть числом"
    try:
        stored = storage.get(record["id"])
    except KeyError:
        return "заказ не найден"
    if stored.status != "pending":
        return f"заказ не ждёт оценки (статус {stored.status})"
    if record["decision"] not in DECISIONS:
        return f"decision должен быть одним из: {', '.join(DECISIONS)}"
    if not _is_int(record["score"]) or not 0 <= record["score"] <= 10:
        return "score — целое от 0 до 10"
    if not _is_int(record["days"]) or record["days"] <= 0:
        return "days — целое больше 0"
    if not _is_int(record["price_rub"]) or record["price_rub"] < 0:
        return "price_rub — целое не меньше 0"
    if not isinstance(record["risks"], str) or not isinstance(record["reply"], str):
        return "risks и reply — строки"
    if record["decision"] != "skip" and not record["reply"].strip():
        return "пустой reply при решении «берём»"
    if record["portfolio_url"] is not None and not isinstance(record["portfolio_url"], str):
        return "portfolio_url — строка или null"
    return None


def import_evaluations(storage: Storage, path: Path) -> ImportReport:
    """Принимает оценки из файла; после приёма файл переименовывается."""
    path = Path(path)
    report = ImportReport()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data["evaluations"]
        if not isinstance(records, list):
            raise TypeError("evaluations должен быть списком")
    except (ValueError, KeyError, TypeError) as error:
        report.invalid.append(f"файл не прочитан: {error}")
        return report

    for number, record in enumerate(records, 1):
        reason = _check_record(record, storage)
        if reason:
            order = record.get("id", "?") if isinstance(record, dict) else "?"
            report.invalid.append(f"запись {number} (заказ {order}): {reason}")
            continue
        storage.save_evaluation(record["id"], Evaluation(
            decision=record["decision"],
            score=record["score"],
            days=record["days"],
            price_kop=record["price_rub"] * 100,
            risks=record["risks"].strip(),
            reply=record["reply"].strip(),
            portfolio_url=record["portfolio_url"],
        ))
        report.imported += 1

    for line in report.invalid:
        log.warning("Оценка отклонена — %s", line)
    # Принятый файл не удаляем, а откладываем: его можно посмотреть при разборе
    path.replace(path.with_name("evaluations.imported.json"))
    return report
