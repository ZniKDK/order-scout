"""Постоянный процесс: сбор по расписанию, отправка карточек и бот."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from order_scout.bot.app import TelegramSender, build_dispatcher, create_bot
from order_scout.bot.sender import CardSender, send_new_cards
from order_scout.collector import collect_once
from order_scout.config import Config
from order_scout.rules_evaluator import evaluate_by_rules
from order_scout.sources.base import Source
from order_scout.storage import Storage

log = logging.getLogger(__name__)

TICK_SEC = 60   # раз в минуту проверяем, не появились ли новые оценки


async def tick(
    storage: Storage,
    cfg: Config,
    sources: list[Source],
    client: httpx.AsyncClient,
    sender: CardSender,
    now: datetime,
    last_collect: datetime | None,
    evaluate_rules: bool = False,
) -> datetime | None:
    """Один шаг. Возвращает время последнего сбора.

    evaluate_rules — демо-режим: заказы сразу оцениваются правилами,
    без внешнего оценщика.
    """
    interval = timedelta(minutes=cfg.collect_interval_min)
    if last_collect is None or now - last_collect >= interval:
        # Время сбора запоминаем и при ошибке: иначе упавшую биржу дёргали бы каждую минуту
        last_collect = now
        try:
            report = await collect_once(storage, cfg, sources, client)
            log.info("Сбор: новых %s, к оценке %s, отсеяно %s, ошибок %s",
                     report.new, report.pending, report.filtered, len(report.errors))
        except Exception:  # noqa: BLE001 — процесс должен жить дальше
            log.exception("Сбор заказов упал")

    if evaluate_rules:
        for stored in storage.by_status("pending"):
            storage.save_evaluation(stored.id, evaluate_by_rules(stored.order, cfg))

    try:
        sent = await send_new_cards(storage, cfg, sender)
        if sent:
            log.info("Отправлено карточек: %s", sent)
    except Exception:  # noqa: BLE001
        log.exception("Отправка карточек упала")
    return last_collect


async def run_forever(
    storage: Storage,
    cfg: Config,
    sources: list[Source],
    token: str,
    chat_id: int,
    evaluate_rules: bool = False,
) -> None:
    """Бот слушает кнопки и команды, рядом раз в минуту идёт tick."""
    bot = create_bot(token)
    dispatcher = build_dispatcher(storage, chat_id)
    sender = TelegramSender(bot, chat_id)
    polling = asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False))
    last_collect = None
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            while True:
                last_collect = await tick(
                    storage, cfg, sources, client, sender,
                    datetime.now(timezone.utc), last_collect, evaluate_rules,
                )
                await asyncio.sleep(TICK_SEC)
    finally:
        polling.cancel()
        await bot.session.close()
