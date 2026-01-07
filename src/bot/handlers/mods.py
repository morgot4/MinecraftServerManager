"""Mod management command handlers."""

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import back_keyboard, mods_list_keyboard
from src.bot.middlewares.auth import check_role, require_role
from src.i18n import t
from src.mods.mod_manager import ModManager
from src.storage.models import EngineType, User, UserRole

if TYPE_CHECKING:
    from src.bot.bot import BotContext

router = Router(name="mods")


class ModSearchStates(StatesGroup):
    """States for mod search flow."""

    waiting_for_query = State()


@router.message(Command("mods"))
@require_role(UserRole.ADMIN)
async def cmd_mods(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /mods command to list installed mods."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    if server.engine != EngineType.FORGE:
        await message.answer(t("mods.not_forge", user_lang))
        return

    mod_manager = ModManager(server.path, server.engine)
    installed = mod_manager.get_installed_mods()

    if not installed:
        await message.answer(t("mods.list_empty", user_lang))
        return

    mods_data = [{"title": m.title, "version": m.version, "slug": m.slug} for m in installed]

    await message.answer(
        t("mods.list_title", user_lang, name=server.name),
        reply_markup=mods_list_keyboard(mods_data, user_lang),
    )


@router.message(Command("addmod"))
@require_role(UserRole.ADMIN)
async def cmd_addmod(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /addmod command to install a mod."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    if server.engine != EngineType.FORGE:
        await message.answer(t("mods.not_forge", user_lang))
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /addmod mod_name_or_slug", parse_mode=None)
        return

    query = parts[1]
    await message.answer(t("mods.searching", user_lang, query=query))

    mod_manager = ModManager(server.path, server.engine)

    try:
        # Search for the mod first
        results = await mod_manager.search_mods(query, server.mc_version, limit=1)

        if not results:
            await mod_manager.close()
            await message.answer(t("mods.not_found", user_lang, query=query))
            return

        mod_info = results[0]
        await message.answer(t("mods.installing", user_lang, name=mod_info.title))

        # Install the mod
        installed = await mod_manager.install_mod(
            mod_info.slug,
            server.mc_version,
        )
        await mod_manager.close()

        response = t("mods.installed", user_lang, name=installed.title)
        if ctx.server_manager.is_running:
            response += "\n" + t("mods.requires_restart", user_lang)

        await message.answer(response)

    except ValueError as e:
        await mod_manager.close()
        await message.answer(t("mods.not_found", user_lang, query=str(e)))
    except Exception as e:
        await mod_manager.close()
        await message.answer(t("error.unknown", user_lang, message=str(e)))


@router.message(Command("removemod"))
@require_role(UserRole.ADMIN)
async def cmd_removemod(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /removemod command to remove a mod."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    if server.engine != EngineType.FORGE:
        await message.answer(t("mods.not_forge", user_lang))
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /removemod mod_name", parse_mode=None)
        return

    mod_name = parts[1]
    mod_manager = ModManager(server.path, server.engine)

    success = await mod_manager.remove_mod(mod_name)
    await mod_manager.close()

    if success:
        response = t("mods.removed", user_lang, name=mod_name)
        if ctx.server_manager.is_running:
            response += "\n" + t("mods.requires_restart", user_lang)
        await message.answer(response)
    else:
        await message.answer(t("mods.not_found", user_lang, query=mod_name))


@router.callback_query(lambda c: c.data == "mods:search")
async def callback_mods_search(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    user_lang: str,
) -> None:
    """Handle mod search button."""
    if not await check_role(user, UserRole.ADMIN, callback, user_lang):
        return

    await callback.message.edit_text("🔍 Enter mod name to search:")  # type: ignore
    await state.set_state(ModSearchStates.waiting_for_query)
    await callback.answer()


@router.message(ModSearchStates.waiting_for_query)
@require_role(UserRole.ADMIN)
async def process_mod_search(
    message: Message,
    user: User,
    state: FSMContext,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Process mod search query."""
    await state.clear()

    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    query = message.text
    await message.answer(t("mods.searching", user_lang, query=query))

    mod_manager = ModManager(server.path, server.engine)

    try:
        results = await mod_manager.search_mods(query, server.mc_version, limit=5)
        await mod_manager.close()

        if not results:
            await message.answer(t("mods.not_found", user_lang, query=query))
            return

        text = "🔍 **Search Results:**\n\n"
        for mod in results:
            text += f"• **{mod.title}** (`{mod.slug}`)\n"
            text += f"  {mod.description[:80]}...\n"
            text += f"  Downloads: {mod.downloads:,}\n\n"

        text += "\nUse /addmod slug to install a mod."
        await message.answer(text)

    except Exception as e:
        await mod_manager.close()
        await message.answer(t("error.unknown", user_lang, message=str(e)))


@router.callback_query(lambda c: c.data and c.data.startswith("mods:info:"))
async def callback_mod_info(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle mod info button."""
    if not await check_role(user, UserRole.ADMIN, callback, user_lang):
        return

    mod_slug = callback.data.split(":")[2]  # type: ignore
    server = ctx.server_manager.active_server

    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    mod_manager = ModManager(server.path, server.engine)
    installed = mod_manager.get_installed_mods()
    mod = next((m for m in installed if m.slug == mod_slug), None)

    if not mod:
        await callback.answer("Mod not found", show_alert=True)
        return

    text = f"""
🧩 **{mod.title}**

Version: `{mod.version}`
File: `{mod.filename}`
Installed: {mod.installed_at.strftime("%Y-%m-%d %H:%M")}

Use `/removemod {mod.slug}` to remove.
"""

    await callback.message.edit_text(  # type: ignore
        text.strip(),
        reply_markup=back_keyboard(user_lang, "mods:list"),
    )
    await callback.answer()
