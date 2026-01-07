"""Backup command handlers."""

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import back_keyboard, backups_list_keyboard, confirm_keyboard
from src.bot.middlewares.auth import check_role, require_role
from src.core.backup_manager import BackupManager
from src.i18n import t
from src.storage.models import BackupType, User, UserRole

if TYPE_CHECKING:
    from src.bot.bot import BotContext

router = Router(name="backup")


@router.message(Command("backup"))
@require_role(UserRole.ADMIN)
async def cmd_backup(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /backup command to create manual backup."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    await message.answer(t("backup.creating", user_lang))

    try:
        backup = await ctx.server_manager.create_backup(BackupType.MANUAL)
        if backup:
            size = BackupManager.format_size(backup.size_bytes)
            await ctx.database.create_backup(backup)
            await message.answer(
                t("backup.created", user_lang, filename=backup.filename, size=size)
            )
        else:
            await message.answer(t("backup.failed", user_lang, error="No active server"))
    except Exception as e:
        await message.answer(t("backup.failed", user_lang, error=str(e)))


@router.callback_query(lambda c: c.data == "backup:create")
async def callback_backup_create(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle backup create button."""
    if not await check_role(user, UserRole.ADMIN, callback, user_lang):
        return

    server = ctx.server_manager.active_server
    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    await callback.message.edit_text(t("backup.creating", user_lang))  # type: ignore
    await callback.answer()

    try:
        backup = await ctx.server_manager.create_backup(BackupType.MANUAL)
        if backup:
            size = BackupManager.format_size(backup.size_bytes)
            await ctx.database.create_backup(backup)
            await callback.message.edit_text(  # type: ignore
                t("backup.created", user_lang, filename=backup.filename, size=size),
                reply_markup=back_keyboard(user_lang),
            )
    except Exception as e:
        await callback.message.edit_text(  # type: ignore
            t("backup.failed", user_lang, error=str(e)),
            reply_markup=back_keyboard(user_lang),
        )


@router.message(Command("backups"))
@require_role(UserRole.ADMIN)
async def cmd_backups(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /backups command to list backups."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    backups = await ctx.database.get_backups_for_server(server.id, limit=10)

    if not backups:
        await message.answer(t("backup.list_empty", user_lang))
        return

    backup_data = [
        {
            "id": b.id,
            "filename": b.filename,
            "size": BackupManager.format_size(b.size_bytes),
        }
        for b in backups
    ]

    await message.answer(
        t("backup.list_title", user_lang, name=server.name),
        reply_markup=backups_list_keyboard(backup_data, user_lang),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("backup:restore:"))
async def callback_backup_restore(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle backup restore button - show confirmation."""
    if not await check_role(user, UserRole.ADMIN, callback, user_lang):
        return

    backup_id = callback.data.split(":")[2]  # type: ignore

    # Store backup_id for confirmation
    await callback.message.edit_text(  # type: ignore
        "⚠️ **Warning!**\n\nRestoring a backup will:\n"
        "1. Stop the server if running\n"
        "2. Delete current world\n"
        "3. Restore world from backup\n\n"
        "Are you sure?",
        reply_markup=confirm_keyboard(
            user_lang,
            confirm_data=f"backup:confirm_restore:{backup_id}",
            cancel_data="menu:main",
        ),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("backup:confirm_restore:"))
async def callback_backup_confirm_restore(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle backup restore confirmation."""
    if not await check_role(user, UserRole.ADMIN, callback, user_lang):
        return

    backup_id = callback.data.split(":")[2]  # type: ignore
    server = ctx.server_manager.active_server

    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    # Find backup
    backups = await ctx.database.get_backups_for_server(server.id)
    backup = next((b for b in backups if b.id == backup_id), None)

    if not backup:
        await callback.answer(t("backup.not_found", user_lang), show_alert=True)
        return

    await callback.message.edit_text(t("backup.restoring", user_lang))  # type: ignore
    await callback.answer()

    try:
        # Stop server if running
        if ctx.server_manager.is_running:
            await ctx.server_manager.stop()

        # Restore backup
        await ctx.server_manager.restore_backup(backup)

        await callback.message.edit_text(  # type: ignore
            t("backup.restored", user_lang),
            reply_markup=back_keyboard(user_lang),
        )
    except Exception as e:
        await callback.message.edit_text(  # type: ignore
            t("error.unknown", user_lang, message=str(e)),
            reply_markup=back_keyboard(user_lang),
        )


@router.message(Command("restore"))
@require_role(UserRole.ADMIN)
async def cmd_restore(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /restore command."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /restore backup_id\nUse /backups to see available backups.", parse_mode=None)
        return

    backup_id = parts[1]
    backups = await ctx.database.get_backups_for_server(server.id)
    backup = next((b for b in backups if b.id == backup_id or b.filename == backup_id), None)

    if not backup:
        await message.answer(t("backup.not_found", user_lang))
        return

    await message.answer(
        f"⚠️ Restore `{backup.filename}`?\n\n" "This will delete the current world!",
        reply_markup=confirm_keyboard(
            user_lang,
            confirm_data=f"backup:confirm_restore:{backup.id}",
            cancel_data="menu:main",
        ),
    )
