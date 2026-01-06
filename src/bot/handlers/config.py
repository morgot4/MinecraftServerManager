"""Server configuration command handlers."""

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import back_keyboard
from src.bot.middlewares.auth import require_role
from src.i18n import t
from src.minecraft.server_properties import ServerProperties
from src.storage.models import UserRole

if TYPE_CHECKING:
    from src.bot.bot import BotContext

router = Router(name="config")


@router.message(Command("settings"))
@require_role(UserRole.ADMIN)
async def cmd_settings(
    message: Message,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /settings command."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    # Load server.properties
    props = ServerProperties(server.properties_path)
    props.load()

    # Show common settings
    settings_text = f"""
{t("settings.title", user_lang, name=server.name)}

**General:**
• max-players: `{props.get("max-players", 20)}`
• view-distance: `{props.get("view-distance", 10)}`
• gamemode: `{props.get("gamemode", "survival")}`
• difficulty: `{props.get("difficulty", "normal")}`
• hardcore: `{props.get("hardcore", False)}`

**Features:**
• pvp: `{props.get("pvp", True)}`
• spawn-monsters: `{props.get("spawn-monsters", True)}`
• spawn-animals: `{props.get("spawn-animals", True)}`
• allow-flight: `{props.get("allow-flight", False)}`
• allow-nether: `{props.get("allow-nether", True)}`

**Security:**
• white-list: `{props.get("white-list", False)}`
• online-mode: `{props.get("online-mode", True)}`

Use `/set <key> <value>` to change a setting.
"""

    await message.answer(settings_text.strip(), reply_markup=back_keyboard(user_lang))


@router.callback_query(lambda c: c.data == "config:menu")
@require_role(UserRole.ADMIN)
async def callback_settings(
    callback: CallbackQuery,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle settings button."""
    server = ctx.server_manager.active_server
    if not server:
        await callback.answer(t("server.no_active", user_lang), show_alert=True)
        return

    props = ServerProperties(server.properties_path)
    props.load()

    settings_text = f"""
{t("settings.title", user_lang, name=server.name)}

**General:**
• max-players: `{props.get("max-players", 20)}`
• view-distance: `{props.get("view-distance", 10)}`
• gamemode: `{props.get("gamemode", "survival")}`
• difficulty: `{props.get("difficulty", "normal")}`
• hardcore: `{props.get("hardcore", False)}`

**Features:**
• pvp: `{props.get("pvp", True)}`
• spawn-monsters: `{props.get("spawn-monsters", True)}`
• spawn-animals: `{props.get("spawn-animals", True)}`
• allow-flight: `{props.get("allow-flight", False)}`
• allow-nether: `{props.get("allow-nether", True)}`

**Security:**
• white-list: `{props.get("white-list", False)}`
• online-mode: `{props.get("online-mode", True)}`

Use `/set <key> <value>` to change a setting.
"""

    await callback.message.edit_text(  # type: ignore
        settings_text.strip(),
        reply_markup=back_keyboard(user_lang),
    )
    await callback.answer()


@router.message(Command("set"))
@require_role(UserRole.ADMIN)
async def cmd_set(
    message: Message,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /set command to change server settings."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: /set <key> <value>")
        return

    key = parts[1]
    value = parts[2]

    # Load and update properties
    props = ServerProperties(server.properties_path)
    props.load()

    if key not in ServerProperties.KNOWN_PROPERTIES:
        await message.answer(t("settings.invalid_key", user_lang, setting=key))
        return

    # Convert value based on type
    prop_type = ServerProperties.KNOWN_PROPERTIES[key][0]
    if prop_type == "bool":
        value = value.lower() in ("true", "1", "yes", "on")
    elif prop_type == "int":
        try:
            value = int(value)
        except ValueError:
            await message.answer(f"Invalid value for {key}: expected integer")
            return

    props.set(key, value)
    props.save()

    response = t("settings.updated", user_lang, setting=key, value=str(value))

    # Some settings require restart
    restart_required = [
        "server-port",
        "max-players",
        "view-distance",
        "level-name",
        "online-mode",
        "enable-rcon",
        "white-list",
    ]
    if key in restart_required:
        response += "\n" + t("settings.requires_restart", user_lang)

    await message.answer(response)
