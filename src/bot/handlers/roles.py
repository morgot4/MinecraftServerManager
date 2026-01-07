"""Role management handlers for Owner only."""

from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import back_keyboard, role_keyboard, users_list_keyboard
from src.bot.middlewares.auth import check_role, require_role
from src.i18n import t
from src.storage.models import User, UserRole

if TYPE_CHECKING:
    from src.bot.bot import BotContext

router = Router(name="roles")


@router.message(Command("role", "roles", "users"))
@require_role(UserRole.OWNER)
async def cmd_users(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Show list of users for role management."""
    users = await ctx.database.get_all_users()

    if not users:
        await message.answer(
            t("roles.list_empty", user_lang),
            reply_markup=back_keyboard(user_lang),
        )
        return

    await message.answer(
        t("roles.select_user", user_lang),
        reply_markup=users_list_keyboard(users, user_lang),
    )


@router.message(Command("myrole"))
async def cmd_my_role(
    message: Message,
    user: User,
    user_lang: str,
) -> None:
    """Show user's own role."""
    role_names = {
        UserRole.OWNER: t("roles.owner", user_lang),
        UserRole.ADMIN: t("roles.admin", user_lang),
        UserRole.OPERATOR: t("roles.operator", user_lang),
        UserRole.PLAYER: t("roles.player", user_lang),
    }
    role_name = role_names.get(user.role, str(user.role))

    await message.answer(t("roles.your_role", user_lang, role=role_name))


@router.callback_query(F.data.startswith("role:user:"))
async def callback_select_user(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle user selection for role change."""
    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return

    target_id = int(callback.data.split(":")[2])  # type: ignore

    target_user = await ctx.database.get_user(target_id)
    if not target_user:
        await callback.answer(t("error.unknown", user_lang, message="User not found"))
        return

    # Can't change owner role
    if target_user.role == UserRole.OWNER:
        await callback.answer(
            t("roles.cannot_change_owner", user_lang),
            show_alert=True,
        )
        return

    username = target_user.username or str(target_user.telegram_id)
    await callback.message.edit_text(  # type: ignore
        t("roles.select_role", user_lang, user=username),
        reply_markup=role_keyboard(target_id, user_lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("role:set:"))
async def callback_set_role(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return
    """Handle role assignment."""
    parts = callback.data.split(":")  # type: ignore
    target_id = int(parts[2])
    new_role_str = parts[3]

    # Map string to role
    role_map = {
        "admin": UserRole.ADMIN,
        "operator": UserRole.OPERATOR,
        "player": UserRole.PLAYER,
    }

    new_role = role_map.get(new_role_str)
    if not new_role:
        await callback.answer(t("error.unknown", user_lang, message="Invalid role"))
        return

    target_user = await ctx.database.get_user(target_id)
    if not target_user:
        await callback.answer(t("error.unknown", user_lang, message="User not found"))
        return

    # Can't change owner role
    if target_user.role == UserRole.OWNER:
        await callback.answer(
            t("roles.cannot_change_owner", user_lang),
            show_alert=True,
        )
        return

    # Update role
    await ctx.database.set_user_role(target_id, new_role)

    role_names = {
        UserRole.ADMIN: t("roles.admin", user_lang),
        UserRole.OPERATOR: t("roles.operator", user_lang),
        UserRole.PLAYER: t("roles.player", user_lang),
    }
    role_name = role_names.get(new_role, str(new_role))
    username = target_user.username or str(target_user.telegram_id)

    await callback.message.edit_text(  # type: ignore
        t("roles.updated", user_lang, user=username, role=role_name),
        reply_markup=back_keyboard(user_lang),
    )
    await callback.answer()

