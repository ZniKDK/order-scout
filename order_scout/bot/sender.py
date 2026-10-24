"""Отправка новых карточек: какие заказы показывать и что делать при ошибке."""

import logging
from typing import Protocol

from order_scout.bot.cards import Card, format_card
from order_scout.config import Config
from order_scout.storage import Storage

log = logging.getLogger(__name__)


class CardSender(Protocol):
    """Кто умеет доставить карточку (Telegram или подделка в тестах)."""

    async def send_card(self, card: Card) -> None: ...


async def send_new_cards(storage: Storage, cfg: Config, sender: CardSender) -> int:
    """Отправляет карточки по оценённым заказам. Возвращает число отправленных.

    Не берём или балл ниже порога → skipped с причиной.
    Ошибка доставки → заказ остаётся evaluated и уйдёт в следующий раз.
    """
    if storage.get_flag("paused"):
        return 0
    sent = 0
    for stored in storage.by_status("evaluated"):
        ev = storage.get_evaluation(stored.id)
        if ev is None:
            continue
        if ev.decision == "skip":
            storage.set_status(stored.id, "skipped", "оценка: не берём")
            continue
        if ev.score < cfg.score_threshold:
            storage.set_status(stored.id, "skipped", f"балл {ev.score} < {cfg.score_threshold}")
            continue
        try:
            await sender.send_card(format_card(stored, ev))
        except Exception:  # noqa: BLE001 — сеть или Telegram; повторим позже
            log.exception("Карточка заказа %s не отправлена", stored.id)
            continue
        storage.set_status(stored.id, "carded")
        storage.log_action(stored.id, "carded")
        sent += 1
    return sent
