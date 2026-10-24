"""Telegram-бот на aiogram: отправка карточек, кнопки и команды.

Бот отвечает только владельцу (CHAT_ID из .env), остальных молча игнорирует.
"""

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from order_scout.bot.cards import Card, apply_action, format_stats
from order_scout.storage import Storage

log = logging.getLogger(__name__)

HELP = (
    "Я присылаю подходящие заказы с бирж и готовые отклики.\n"
    "Отклик отправляете вы: «Открыть заказ» → вставить текст → «Отправил».\n\n"
    "/stats — сводка\n/pause — не присылать карточки\n/resume — продолжить"
)


def is_owner(chat_id: int | None, owner_id: int) -> bool:
    return chat_id is not None and chat_id == owner_id


def create_bot(token: str) -> Bot:
    return Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def _keyboard(card: Card) -> InlineKeyboardMarkup:
    """Первая кнопка — ссылка на заказ, остальные — действия в один ряд."""
    (open_label, url), *actions = card.buttons
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=open_label, url=url)],
        [InlineKeyboardButton(text=label, callback_data=data) for label, data in actions],
    ])


class TelegramSender:
    """Доставка карточки владельцу: сообщение с кнопками и отдельно отклик."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self.bot = bot
        self.chat_id = chat_id

    async def send_card(self, card: Card) -> None:
        await self.bot.send_message(
            self.chat_id, card.text, reply_markup=_keyboard(card),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await self.bot.send_message(self.chat_id, card.reply_text)


def build_dispatcher(storage: Storage, owner_id: int) -> Dispatcher:
    router = Router()
    # Фильтр на весь роутер: чужие сообщения и нажатия не обрабатываются
    router.message.filter(lambda message: is_owner(message.chat.id, owner_id))
    router.callback_query.filter(lambda callback: is_owner(callback.from_user.id, owner_id))

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(HELP)

    @router.message(Command("stats"))
    async def stats(message: Message) -> None:
        await message.answer(format_stats(storage))

    @router.message(Command("pause"))
    async def pause(message: Message) -> None:
        storage.set_flag("paused", True)
        await message.answer("⏸ Карточки не присылаю. /resume — продолжить")

    @router.message(Command("resume"))
    async def resume(message: Message) -> None:
        storage.set_flag("paused", False)
        await message.answer("▶️ Снова присылаю карточки")

    @router.callback_query(F.data.regexp(r"^(skip|sent):\d+$"))
    async def on_button(callback: CallbackQuery) -> None:
        action, order_id = callback.data.split(":")
        answer = apply_action(storage, int(order_id), action)
        await callback.answer(answer)
        # Помечаем карточку, чтобы в ленте было видно, что с ней сделано
        if callback.message and answer != "Уже отмечено":
            mark = "✅ Отклик отправлен" if action == "sent" else "⏭ Пропущено"
            await callback.message.edit_text(
                f"{callback.message.html_text}\n\n<b>{mark}</b>",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
