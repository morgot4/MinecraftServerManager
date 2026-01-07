"""Player management command handlers."""

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import back_keyboard, whitelist_keyboard
from src.bot.middlewares.auth import check_role, require_role
from src.i18n import t
from src.minecraft.whitelist import WhitelistManager
from src.storage.models import User, UserRole

if TYPE_CHECKING:
    from src.bot.bot import BotContext

router = Router(name="players")


@router.message(Command("list"))
async def cmd_list(
    message: Message,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /list command to show online players."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    if not ctx.server_manager.is_running:
        await message.answer(t("server.not_running", user_lang))
        return

    status = ctx.server_manager.status
    players = status.players_list

    if players:
        players_text = "\n".join(f"• {p}" for p in players)
        text = f"{t('players.list_title', user_lang, count=status.players_online, max=status.players_max)}\n\n{players_text}"
    else:
        text = t("players.list_empty", user_lang)

    await message.answer(text)


@router.callback_query(lambda c: c.data == "players:list")
async def callback_players_list(
    callback: CallbackQuery,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle players list button."""
    server = ctx.server_manager.active_server
    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    if not ctx.server_manager.is_running:
        await callback.answer(t("server.not_running", user_lang), show_alert=True)
        return

    status = ctx.server_manager.status
    players = status.players_list

    if players:
        players_text = "\n".join(f"• {p}" for p in players)
        text = f"{t('players.list_title', user_lang, count=status.players_online, max=status.players_max)}\n\n{players_text}"
    else:
        text = t("players.list_empty", user_lang)

    await callback.message.edit_text(  # type: ignore
        text,
        reply_markup=back_keyboard(user_lang),
    )
    await callback.answer()


@router.message(Command("kick"))
@require_role(UserRole.ADMIN)
async def cmd_kick(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /kick command."""
    if not ctx.server_manager.is_running:
        await message.answer(t("server.not_running", user_lang))
        return

    # Parse command
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /kick player [reason]", parse_mode=None)
        return

    player = parts[1]
    reason = parts[2] if len(parts) > 2 else ""

    # Check if player is online
    status = ctx.server_manager.status
    if player not in status.players_list:
        await message.answer(t("players.not_online", user_lang, player=player))
        return

    success = await ctx.server_manager.kick_player(player, reason)
    if success:
        await message.answer(t("players.kicked", user_lang, player=player))
    else:
        await message.answer(t("error.unknown", user_lang, message="Failed to kick player"))


@router.message(Command("whitelist"))
@require_role(UserRole.ADMIN)
async def cmd_whitelist(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /whitelist command."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    # Parse subcommand
    parts = message.text.split()

    if len(parts) == 1:
        # Show whitelist
        wl_manager = WhitelistManager(server.path)
        players = wl_manager.get_whitelist_names()

        if players:
            await message.answer(
                t("whitelist.list_title", user_lang),
                reply_markup=whitelist_keyboard(players, user_lang),
            )
        else:
            await message.answer(t("whitelist.list_empty", user_lang))
        return

    action = parts[1].lower()
    if len(parts) < 3:
        await message.answer("Usage: /whitelist add|remove player", parse_mode=None)
        return

    player = parts[2]
    wl_manager = WhitelistManager(server.path)

    if action == "add":
        success = await wl_manager.add_to_whitelist(player)
        if success:
            # Also add via RCON if server is running
            if ctx.server_manager.is_running:
                await ctx.server_manager.send_command(f"whitelist add {player}")
            await message.answer(t("whitelist.added", user_lang, player=player))
        else:
            await message.answer(t("whitelist.already_added", user_lang, player=player))

    elif action == "remove":
        success = wl_manager.remove_from_whitelist(player)
        if success:
            if ctx.server_manager.is_running:
                await ctx.server_manager.send_command(f"whitelist remove {player}")
            await message.answer(t("whitelist.removed", user_lang, player=player))
        else:
            await message.answer(t("error.unknown", user_lang, message="Player not in whitelist"))


@router.callback_query(lambda c: c.data and c.data.startswith("whitelist:remove:"))
async def callback_whitelist_remove(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle whitelist remove button."""
    if not await check_role(user, UserRole.ADMIN, callback, user_lang):
        return

    player = callback.data.split(":")[2]  # type: ignore
    server = ctx.server_manager.active_server

    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    wl_manager = WhitelistManager(server.path)
    success = wl_manager.remove_from_whitelist(player)

    if success:
        if ctx.server_manager.is_running:
            await ctx.server_manager.send_command(f"whitelist remove {player}")

        # Refresh list
        players = wl_manager.get_whitelist_names()
        if players:
            await callback.message.edit_text(  # type: ignore
                t("whitelist.list_title", user_lang),
                reply_markup=whitelist_keyboard(players, user_lang),
            )
        else:
            await callback.message.edit_text(t("whitelist.list_empty", user_lang))  # type: ignore

    await callback.answer(t("whitelist.removed", user_lang, player=player))


@router.message(Command("op"))
@require_role(UserRole.ADMIN)
async def cmd_op(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /op command."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    parts = message.text.split()
    if len(parts) < 2:
        # Show ops list
        wl_manager = WhitelistManager(server.path)
        ops = wl_manager.get_ops_names()
        if ops:
            ops_text = "\n".join(f"👑 {op}" for op in ops)
            await message.answer(f"{t('ops.list_title', user_lang)}\n\n{ops_text}")
        else:
            await message.answer(t("ops.list_empty", user_lang))
        return

    action = parts[1].lower()
    if len(parts) < 3 and action in ("add", "remove"):
        await message.answer("Usage: /op add|remove player", parse_mode=None)
        return

    player = parts[2] if len(parts) > 2 else parts[1]
    wl_manager = WhitelistManager(server.path)

    if action == "add":
        success = await wl_manager.add_op(player)
        if success:
            if ctx.server_manager.is_running:
                await ctx.server_manager.send_command(f"op {player}")
            await message.answer(t("ops.added", user_lang, player=player))
        else:
            await message.answer(t("error.unknown", user_lang, message="Failed to add operator"))

    elif action == "remove":
        success = wl_manager.remove_op(player)
        if success:
            if ctx.server_manager.is_running:
                await ctx.server_manager.send_command(f"deop {player}")
            await message.answer(t("ops.removed", user_lang, player=player))
        else:
            await message.answer(t("error.unknown", user_lang, message="Player is not an operator"))

    else:
        # Assume it's a player name, add as op
        success = await wl_manager.add_op(action)
        if success:
            if ctx.server_manager.is_running:
                await ctx.server_manager.send_command(f"op {action}")
            await message.answer(t("ops.added", user_lang, player=action))
        else:
            await message.answer(t("error.unknown", user_lang, message="Failed to add operator"))
