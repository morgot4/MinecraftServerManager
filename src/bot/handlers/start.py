"""Start and help command handlers."""

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import language_keyboard, main_menu_keyboard
from src.i18n import t
from src.storage.models import User

if TYPE_CHECKING:
    from src.bot.bot import BotContext

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /start command."""
    is_running = ctx.server_manager.is_running

    await message.answer(
        t("bot.welcome", user_lang),
        reply_markup=main_menu_keyboard(user_lang, is_running, user),
    )


@router.message(Command("help"))
async def cmd_help(
    message: Message,
    user: User,
    user_lang: str,
) -> None:
    """Handle /help command - show available commands based on user role."""
    # Start with player commands (everyone sees these)
    help_text = t("bot.help_player", user_lang)

    # Add operator commands if user is operator or higher
    if user.can_control_server():
        help_text += "\n" + t("bot.help_operator", user_lang)

    # Add admin commands if user is admin or higher
    if user.can_manage_server():
        help_text += "\n" + t("bot.help_admin", user_lang)

    # Add owner commands if user is owner
    if user.can_create_servers():
        help_text += "\n" + t("bot.help_owner", user_lang)

    await message.answer(help_text)


@router.message(Command("lang"))
async def cmd_lang(message: Message, user_lang: str) -> None:
    """Handle /lang command."""
    await message.answer(
        t("lang.select", user_lang),
        reply_markup=language_keyboard(),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("lang:"))
async def callback_lang(
    callback: CallbackQuery,
    user: User,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle language selection."""
    lang = callback.data.split(":")[1]  # type: ignore

    # Update user language
    user.language = lang
    await ctx.database.update_user(user)

    await callback.message.edit_text(t("lang.changed", lang))  # type: ignore
    await callback.answer()


@router.callback_query(lambda c: c.data == "menu:main")
async def callback_main_menu(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle return to main menu."""
    is_running = ctx.server_manager.is_running

    await callback.message.edit_text(  # type: ignore
        t("bot.welcome", user_lang),
        reply_markup=main_menu_keyboard(user_lang, is_running, user),
    )
    await callback.answer()
