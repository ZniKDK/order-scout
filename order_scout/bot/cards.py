"""Карточка заказа для Telegram и действия по кнопкам.

Всё здесь — чистые функции без сети: их проверяют тесты,
а бот только отправляет готовый текст.
"""

import html
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from order_scout.models import Evaluation
from order_scout.storage import Storage, StoredOrder

TG_LIMIT = 4096                  # предел длины сообщения Telegram
DESCRIPTION_PREVIEW = 300        # сколько символов описания показывать в карточке
MSK = timezone(timedelta(hours=3))

SOURCE_LABELS = {"flru": "FL.ru", "kwork": "Kwork", "demo": "Демо"}
DECISION_LABELS = {"take": "берём", "stages": "берём этапами", "skip": "не рекомендую"}
TRUNCATED = "\n…(обрезано, полный текст в базе)"

# Кнопка → новый статус и ответ на нажатие
ACTIONS = {
    "skip": ("skipped", "Пропущено"),
    "sent": ("replied", "Отмечено: отклик отправлен"),
}


@dataclass(frozen=True)
class Card:
    """Готовые сообщения: карточка с кнопками и отдельно текст отклика."""

    text: str
    reply_text: str
    buttons: list[tuple[str, str]]   # (подпись, url или callback_data)


def _money(kop: int) -> str:
    return f"{kop // 100:,}".replace(",", " ") + " ₽"


def _budget(stored: StoredOrder) -> str:
    order = stored.order
    if order.budget_kop is None:
        return "бюджет не указан"
    text = f"бюджет {_money(order.budget_kop)}"
    if order.budget_max_kop:
        text += f" (до {_money(order.budget_max_kop)})"
    return text


def _reply_block(reply: str) -> str:
    """Отклик в <pre>: в Telegram такой блок копируется одним нажатием."""
    escaped = html.escape(reply)
    room = TG_LIMIT - len("<pre></pre>")
    if len(escaped) > room:
        cut = escaped[: room - len(TRUNCATED)]
        # Не оставляем обрубок HTML-сущности вроде «&am»
        amp = cut.rfind("&")
        if amp != -1 and ";" not in cut[amp:]:
            cut = cut[:amp]
        escaped = cut + TRUNCATED
    return f"<pre>{escaped}</pre>"


def format_card(stored: StoredOrder, ev: Evaluation) -> Card:
    order = stored.order
    offers = "нет данных" if order.offers_count is None else str(order.offers_count)
    description = order.description
    if len(description) > DESCRIPTION_PREVIEW:
        description = description[:DESCRIPTION_PREVIEW].rstrip() + "…"

    lines = [
        f"<b>{SOURCE_LABELS.get(order.source, order.source)}</b> · "
        f"{DECISION_LABELS[ev.decision]} · <b>{ev.score}/10</b>",
        f"<b>{html.escape(order.title)}</b>",
        f"{_budget(stored)} · откликов: {offers}",
        f"Наш вариант: {ev.days} дн. · {_money(ev.price_kop)}",
    ]
    if ev.risks:
        lines.append(f"Риски: {html.escape(ev.risks)}")
    if ev.portfolio_url:
        lines.append(f"Похожий проект: {html.escape(ev.portfolio_url)}")
    if description:
        lines.append("")
        lines.append(f"<i>{html.escape(description)}</i>")

    return Card(
        text="\n".join(lines),
        reply_text=_reply_block(ev.reply),
        buttons=[
            ("Открыть заказ", order.url),
            ("Пропустить", f"skip:{stored.id}"),
            ("Отправил", f"sent:{stored.id}"),
        ],
    )


def apply_action(storage: Storage, order_id: int, action: str) -> str:
    """Обрабатывает нажатие кнопки; повторное нажатие ничего не меняет."""
    if action not in ACTIONS:
        raise ValueError(f"Неизвестное действие: {action}")
    if storage.get(order_id).status in ("skipped", "replied"):
        return "Уже отмечено"
    status, answer = ACTIONS[action]
    storage.set_status(order_id, status)
    storage.log_action(order_id, action)
    return answer


def format_stats(storage: Storage, now: datetime | None = None) -> str:
    """Сводка для /stats: что сегодня (по Москве) и что лежит в базе."""
    now = now or datetime.now(timezone.utc)
    day_start = now.astimezone(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    lines = [
        "<b>Сегодня</b>",
        f"карточек: {storage.count_actions_since('carded', day_start)}",
        f"откликов отправлено: {storage.count_actions_since('sent', day_start)}",
        f"пропущено: {storage.count_actions_since('skip', day_start)}",
        "",
        "<b>В базе</b>",
    ]
    lines += [f"{status}: {count}" for status, count in storage.counts().items()]
    if storage.get_flag("paused"):
        lines.append("\n⏸ На паузе: /resume, чтобы продолжить")
    return "\n".join(lines)
