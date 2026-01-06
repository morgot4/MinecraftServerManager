"""Inline keyboard builders for the bot."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.i18n import t
from src.storage.models import Server, User, UserRole


def main_menu_keyboard(
    lang: str = "ru",
    is_running: bool = False,
    user: User | None = None,
) -> InlineKeyboardMarkup:
    """
    Build main menu keyboard based on user role.

    - PLAYER: status, players (view only)
    - OPERATOR: + start/stop/restart
    - ADMIN: + backup, settings
    - OWNER: + servers management
    """
    builder = InlineKeyboardBuilder()

    # Server control (OPERATOR+)
    can_control = user.can_control_server() if user else False
    if can_control:
        if is_running:
            builder.row(
                InlineKeyboardButton(text=t("button.stop", lang), callback_data="server:stop"),
                InlineKeyboardButton(text=t("button.restart", lang), callback_data="server:restart"),
            )
        else:
            builder.row(
                InlineKeyboardButton(text=t("button.start", lang), callback_data="server:start"),
            )

    # Status and players (everyone)
    builder.row(
        InlineKeyboardButton(text=t("button.status", lang), callback_data="server:status"),
        InlineKeyboardButton(text=t("button.players", lang), callback_data="players:list"),
    )

    # Backup and settings (ADMIN+)
    can_manage = user.can_manage_server() if user else False
    if can_manage:
        builder.row(
            InlineKeyboardButton(text=t("button.backup", lang), callback_data="backup:create"),
            InlineKeyboardButton(text=t("button.settings", lang), callback_data="config:menu"),
        )

    # Server management (OWNER only)
    can_create = user.can_create_servers() if user else False
    if can_create:
        builder.row(
            InlineKeyboardButton(text=t("button.servers", lang), callback_data="servers:list"),
        )

    return builder.as_markup()


def server_control_keyboard(
    lang: str = "ru",
    is_running: bool = False,
    user: User | None = None,
) -> InlineKeyboardMarkup:
    """Build server control keyboard."""
    builder = InlineKeyboardBuilder()

    can_control = user.can_control_server() if user else False
    if can_control:
        if is_running:
            builder.row(
                InlineKeyboardButton(text=t("button.stop", lang), callback_data="server:stop"),
                InlineKeyboardButton(text=t("button.restart", lang), callback_data="server:restart"),
            )
        else:
            builder.row(
                InlineKeyboardButton(text=t("button.start", lang), callback_data="server:start"),
            )

    builder.row(
        InlineKeyboardButton(text=t("button.back", lang), callback_data="menu:main"),
    )

    return builder.as_markup()


def confirm_keyboard(
    lang: str = "ru",
    confirm_data: str = "confirm",
    cancel_data: str = "cancel",
) -> InlineKeyboardMarkup:
    """Build confirmation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("button.confirm", lang), callback_data=confirm_data),
        InlineKeyboardButton(text=t("button.cancel", lang), callback_data=cancel_data),
    )
    return builder.as_markup()


def servers_list_keyboard(
    servers: list[Server],
    lang: str = "ru",
    can_create: bool = False,
    discovered_count: int = 0,
) -> InlineKeyboardMarkup:
    """Build servers list keyboard."""
    builder = InlineKeyboardBuilder()

    for server in servers:
        status = "✅" if server.is_active else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {server.name} ({server.mc_version})",
                callback_data=f"servers:select:{server.id}",
            )
        )

    if can_create:
        builder.row(
            InlineKeyboardButton(text="➕ " + t("button.create_server", lang), callback_data="servers:create"),
        )
        # Show import button if there are discovered servers
        if discovered_count > 0:
            builder.row(
                InlineKeyboardButton(
                    text=f"📥 {t('button.import_server', lang)} ({discovered_count})",
                    callback_data="servers:scan",
                ),
            )
        else:
            builder.row(
                InlineKeyboardButton(text="🔍 " + t("button.scan_servers", lang), callback_data="servers:scan"),
            )

    builder.row(
        InlineKeyboardButton(text=t("button.back", lang), callback_data="menu:main"),
    )

    return builder.as_markup()


def language_keyboard() -> InlineKeyboardMarkup:
    """Build language selection keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
    )
    return builder.as_markup()


def back_keyboard(lang: str = "ru", callback_data: str = "menu:main") -> InlineKeyboardMarkup:
    """Build simple back button keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("button.back", lang), callback_data=callback_data),
    )
    return builder.as_markup()


def whitelist_keyboard(
    players: list[str],
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Build whitelist management keyboard."""
    builder = InlineKeyboardBuilder()

    for player in players[:10]:  # Limit to 10
        builder.row(
            InlineKeyboardButton(
                text=f"❌ {player}",
                callback_data=f"whitelist:remove:{player}",
            )
        )

    builder.row(
        InlineKeyboardButton(text="➕ " + t("button.add_player", lang), callback_data="whitelist:add"),
    )
    builder.row(
        InlineKeyboardButton(text=t("button.back", lang), callback_data="menu:main"),
    )

    return builder.as_markup()


def mods_list_keyboard(
    mods: list[dict],
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Build mods list keyboard."""
    builder = InlineKeyboardBuilder()

    for mod in mods[:10]:  # Limit to 10
        builder.row(
            InlineKeyboardButton(
                text=f"🧩 {mod['title']} ({mod['version']})",
                callback_data=f"mods:info:{mod['slug']}",
            )
        )

    builder.row(
        InlineKeyboardButton(text="🔍 " + t("button.search_mods", lang), callback_data="mods:search"),
    )
    builder.row(
        InlineKeyboardButton(text=t("button.back", lang), callback_data="menu:main"),
    )

    return builder.as_markup()


def backups_list_keyboard(
    backups: list[dict],
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Build backups list keyboard."""
    builder = InlineKeyboardBuilder()

    for backup in backups[:10]:
        builder.row(
            InlineKeyboardButton(
                text=f"📦 {backup['filename']} ({backup['size']})",
                callback_data=f"backup:restore:{backup['id']}",
            )
        )

    builder.row(
        InlineKeyboardButton(text="📦 " + t("button.create_backup", lang), callback_data="backup:create"),
    )
    builder.row(
        InlineKeyboardButton(text=t("button.back", lang), callback_data="menu:main"),
    )

    return builder.as_markup()


def role_keyboard(user_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Build role selection keyboard for user management."""
    builder = InlineKeyboardBuilder()

    # Can't set OWNER via keyboard (only via config)
    builder.row(
        InlineKeyboardButton(
            text="👑 " + t("roles.admin", lang),
            callback_data=f"role:set:{user_id}:admin",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔧 " + t("roles.operator", lang),
            callback_data=f"role:set:{user_id}:operator",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="👤 " + t("roles.player", lang),
            callback_data=f"role:set:{user_id}:player",
        ),
    )
    builder.row(
        InlineKeyboardButton(text=t("button.cancel", lang), callback_data="menu:main"),
    )

    return builder.as_markup()


def users_list_keyboard(
    users: list[User],
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Build users list keyboard for role management."""
    builder = InlineKeyboardBuilder()

    role_icons = {
        UserRole.OWNER: "👑",
        UserRole.ADMIN: "⚙️",
        UserRole.OPERATOR: "🔧",
        UserRole.PLAYER: "👤",
    }

    for user in users[:15]:  # Limit to 15
        icon = role_icons.get(user.role, "👤")
        name = user.username or str(user.telegram_id)
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} {name}",
                callback_data=f"role:user:{user.telegram_id}",
            )
        )

    builder.row(
        InlineKeyboardButton(text=t("button.back", lang), callback_data="menu:main"),
    )

    return builder.as_markup()
