"""Server control command handlers."""

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import main_menu_keyboard, server_control_keyboard
from src.bot.middlewares.auth import check_role, require_role
from src.i18n import t
from src.storage.models import User, UserRole
from src.utils.network import get_local_ip

if TYPE_CHECKING:
    from src.bot.bot import BotContext

router = Router(name="server")


def format_uptime(seconds: int | None) -> str:
    """Format uptime in human-readable format."""
    if seconds is None:
        return "-"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


@router.message(Command("status"))
async def cmd_status(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /status command - available to everyone."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    status = ctx.server_manager.status
    state = (
        t("server.status.running", user_lang)
        if status.is_running
        else t("server.status.stopped", user_lang)
    )

    text = f"""
{t("server.status.title", user_lang)}

📛 {t("server.status.name", user_lang)}: **{server.name}**
🎮 {t("server.status.version", user_lang)}: {server.mc_version}
⚙️ {t("server.status.engine", user_lang)}: {server.engine.value.capitalize()}
📊 {t("server.status.state", user_lang)}: {state}
👥 {t("server.status.players", user_lang)}: {status.players_online}/{status.players_max}
⏱️ {t("server.status.uptime", user_lang)}: {format_uptime(status.uptime_seconds)}
🌐 {t("server.status.address", user_lang)}: `{get_local_ip()}:{server.port}`
"""

    await message.answer(
        text.strip(),
        reply_markup=server_control_keyboard(user_lang, status.is_running, user),
    )


@router.callback_query(lambda c: c.data == "server:status")
async def callback_status(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle status button press - available to everyone."""
    server = ctx.server_manager.active_server
    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    status = ctx.server_manager.status
    state = (
        t("server.status.running", user_lang)
        if status.is_running
        else t("server.status.stopped", user_lang)
    )

    text = f"""
{t("server.status.title", user_lang)}

📛 {t("server.status.name", user_lang)}: **{server.name}**
🎮 {t("server.status.version", user_lang)}: {server.mc_version}
⚙️ {t("server.status.engine", user_lang)}: {server.engine.value.capitalize()}
📊 {t("server.status.state", user_lang)}: {state}
👥 {t("server.status.players", user_lang)}: {status.players_online}/{status.players_max}
⏱️ {t("server.status.uptime", user_lang)}: {format_uptime(status.uptime_seconds)}
🌐 {t("server.status.address", user_lang)}: `{get_local_ip()}:{server.port}`
"""

    await callback.message.edit_text(  # type: ignore
        text.strip(),
        reply_markup=server_control_keyboard(user_lang, status.is_running, user),
    )
    await callback.answer()


# ============== Server Control (OPERATOR+) ==============


@router.message(Command("on", "start_server"))
@require_role(UserRole.OPERATOR)
async def cmd_start_server(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /on command to start server (OPERATOR+)."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    if ctx.server_manager.is_running:
        await message.answer(t("server.already_running", user_lang))
        return

    await message.answer(t("server.starting", user_lang, name=server.name))

    try:
        success = await ctx.server_manager.start()
        if success:
            # Wait for server to be fully ready (timeout 120 sec)
            ready = await ctx.server_manager.wait_until_ready(timeout=120.0)
            if ready:
                # Update database
                server.last_started_at = ctx.server_manager.active_server.last_started_at
                await ctx.database.update_server(server)

                await message.answer(
                    t("server.started", user_lang, name=server.name),
                    reply_markup=main_menu_keyboard(user_lang, is_running=True, user=user),
                )
            else:
                await message.answer(t("server.start_timeout", user_lang, name=server.name))
        else:
            await message.answer(t("server.already_running", user_lang))
    except Exception as e:
        await message.answer(t("error.unknown", user_lang, message=str(e)))


@router.callback_query(lambda c: c.data == "server:start")
async def callback_start_server(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle start button press (OPERATOR+)."""
    if not await check_role(user, UserRole.OPERATOR, callback, user_lang):
        return

    server = ctx.server_manager.active_server
    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    if ctx.server_manager.is_running:
        await callback.answer(t("server.already_running", user_lang), show_alert=True)
        return

    await callback.message.edit_text(t("server.starting", user_lang, name=server.name))  # type: ignore
    await callback.answer()

    try:
        success = await ctx.server_manager.start()
        if success:
            # Wait for server to be fully ready (timeout 120 sec)
            ready = await ctx.server_manager.wait_until_ready(timeout=120.0)
            if ready:
                server.last_started_at = ctx.server_manager.active_server.last_started_at
                await ctx.database.update_server(server)

                await callback.message.edit_text(  # type: ignore
                    t("server.started", user_lang, name=server.name),
                    reply_markup=main_menu_keyboard(user_lang, is_running=True, user=user),
                )
            else:
                await callback.message.edit_text(  # type: ignore
                    t("server.start_timeout", user_lang, name=server.name),
                    reply_markup=main_menu_keyboard(user_lang, is_running=True, user=user),
                )
    except Exception as e:
        await callback.message.edit_text(t("error.unknown", user_lang, message=str(e)))  # type: ignore


@router.message(Command("off", "stop_server"))
@require_role(UserRole.OPERATOR)
async def cmd_stop_server(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /off command to stop server (OPERATOR+)."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    if not ctx.server_manager.is_running:
        await message.answer(t("server.not_running", user_lang))
        return

    await message.answer(t("server.stopping", user_lang, name=server.name))

    try:
        await ctx.server_manager.stop()
        await message.answer(
            t("server.stopped", user_lang, name=server.name),
            reply_markup=main_menu_keyboard(user_lang, is_running=False, user=user),
        )
    except Exception as e:
        await message.answer(t("error.unknown", user_lang, message=str(e)))


@router.callback_query(lambda c: c.data == "server:stop")
async def callback_stop_server(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle stop button press (OPERATOR+)."""
    if not await check_role(user, UserRole.OPERATOR, callback, user_lang):
        return

    server = ctx.server_manager.active_server
    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    if not ctx.server_manager.is_running:
        await callback.answer(t("server.not_running", user_lang), show_alert=True)
        return

    await callback.message.edit_text(t("server.stopping", user_lang, name=server.name))  # type: ignore
    await callback.answer()

    try:
        await ctx.server_manager.stop()
        await callback.message.edit_text(  # type: ignore
            t("server.stopped", user_lang, name=server.name),
            reply_markup=main_menu_keyboard(user_lang, is_running=False, user=user),
        )
    except Exception as e:
        await callback.message.edit_text(t("error.unknown", user_lang, message=str(e)))  # type: ignore


@router.message(Command("restart"))
@require_role(UserRole.OPERATOR)
async def cmd_restart_server(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /restart command (OPERATOR+)."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    await message.answer(t("server.restarting", user_lang, name=server.name))

    try:
        await ctx.server_manager.restart()
        # Wait for server to be fully ready
        ready = await ctx.server_manager.wait_until_ready(timeout=120.0)
        if ready:
            await message.answer(
                t("server.started", user_lang, name=server.name),
                reply_markup=main_menu_keyboard(user_lang, is_running=True, user=user),
            )
        else:
            await message.answer(t("server.start_timeout", user_lang, name=server.name))
    except Exception as e:
        await message.answer(t("error.unknown", user_lang, message=str(e)))


@router.callback_query(lambda c: c.data == "server:restart")
async def callback_restart_server(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle restart button press (OPERATOR+)."""
    if not await check_role(user, UserRole.OPERATOR, callback, user_lang):
        return

    server = ctx.server_manager.active_server
    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    await callback.message.edit_text(t("server.restarting", user_lang, name=server.name))  # type: ignore
    await callback.answer()

    try:
        await ctx.server_manager.restart()
        # Wait for server to be fully ready
        ready = await ctx.server_manager.wait_until_ready(timeout=120.0)
        if ready:
            await callback.message.edit_text(  # type: ignore
                t("server.started", user_lang, name=server.name),
                reply_markup=main_menu_keyboard(user_lang, is_running=True, user=user),
            )
        else:
            await callback.message.edit_text(  # type: ignore
                t("server.start_timeout", user_lang, name=server.name),
                reply_markup=main_menu_keyboard(user_lang, is_running=True, user=user),
            )
    except Exception as e:
        await callback.message.edit_text(t("error.unknown", user_lang, message=str(e)))  # type: ignore


# ============== Console Commands (ADMIN+) ==============


@router.message(Command("say"))
@require_role(UserRole.ADMIN)
async def cmd_say(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /say command to send chat message (ADMIN+)."""
    if not ctx.server_manager.is_running:
        await message.answer(t("server.not_running", user_lang))
        return

    # Extract message text
    text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
    if not text:
        await message.answer("Usage: /say message", parse_mode=None)
        return

    success = await ctx.server_manager.say(text)
    if success:
        await message.answer(f"💬 {text}")
    else:
        await message.answer(t("error.unknown", user_lang, message="Failed to send message"))


@router.message(Command("console", "cmd"))
@require_role(UserRole.ADMIN)
async def cmd_console(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /console command to execute server command (ADMIN+)."""
    if not ctx.server_manager.is_running:
        await message.answer(t("server.not_running", user_lang))
        return

    # Extract command
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /console command", parse_mode=None)
        return

    command = parts[1]
    result = await ctx.server_manager.send_command(command)

    if result:
        await message.answer(f"```\n{result}\n```")
    else:
        await message.answer(f"✅ Command sent: `{command}`")
