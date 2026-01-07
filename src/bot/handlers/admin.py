"""Admin command handlers for server management."""

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import back_keyboard, confirm_keyboard, servers_list_keyboard
from src.bot.middlewares.auth import check_role, require_role
from src.core.server_manager import ServerManager
from src.engines.forge import ForgeEngine
from src.engines.vanilla import VanillaEngine
from src.i18n import t
from src.minecraft.server_properties import ServerProperties
from src.storage.models import EngineType, User, UserRole

if TYPE_CHECKING:
    from src.bot.bot import BotContext

router = Router(name="admin")


class CreateServerStates(StatesGroup):
    """States for server creation wizard."""

    waiting_for_name = State()
    waiting_for_engine = State()
    waiting_for_version = State()


# ============== Server List and Switch (OWNER) ==============


@router.message(Command("servers"))
@require_role(UserRole.OWNER)
async def cmd_servers(
    message: Message,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /servers command to list all servers (OWNER only)."""
    servers = await ctx.database.get_all_servers()

    # Don't scan here - it slows down the response
    # User can click "Scan" button to discover new servers

    if not servers:
        await message.answer(
            t("server.list.empty", user_lang),
            reply_markup=servers_list_keyboard([], user_lang, can_create=True, discovered_count=0),
        )
        return

    await message.answer(
        t("server.list.title", user_lang),
        reply_markup=servers_list_keyboard(servers, user_lang, can_create=True, discovered_count=0),
    )


@router.callback_query(lambda c: c.data == "servers:list")
async def callback_servers_list(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle servers list button (OWNER only)."""
    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return

    servers = await ctx.database.get_all_servers()

    # Don't scan here - user can click "Scan" button

    if not servers:
        await callback.message.edit_text(  # type: ignore
            t("server.list.empty", user_lang),
            reply_markup=servers_list_keyboard([], user_lang, can_create=True, discovered_count=0),
        )
    else:
        await callback.message.edit_text(  # type: ignore
            t("server.list.title", user_lang),
            reply_markup=servers_list_keyboard(servers, user_lang, can_create=True, discovered_count=0),
        )


@router.callback_query(lambda c: c.data and c.data.startswith("servers:select:"))
async def callback_server_select(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle server selection (OWNER only)."""
    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return

    server_id = callback.data.split(":")[2]  # type: ignore

    # Check if server is running
    if ctx.server_manager.is_running:
        await callback.answer(
            "Stop the current server before switching!",
            show_alert=True,
        )
        return

    # Get server
    server = await ctx.database.get_server(server_id)
    if not server:
        await callback.answer("Server not found", show_alert=True)
        return

    # Set as active
    await ctx.database.set_active_server(server_id)
    server.is_active = True
    ctx.server_manager.set_active_server(server)

    await callback.message.edit_text(  # type: ignore
        t("server.switched", user_lang, name=server.name),
        reply_markup=back_keyboard(user_lang),
    )
    await callback.answer()


@router.message(Command("switch"))
@require_role(UserRole.OWNER)
async def cmd_switch(
    message: Message,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /switch command to change active server (OWNER only)."""
    if ctx.server_manager.is_running:
        await message.answer("⚠️ Stop the current server before switching!")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /switch <server_name>")
        return

    server_name = parts[1]
    server = await ctx.database.get_server_by_name(server_name)

    if not server:
        await message.answer(f"Server '{server_name}' not found. Use /servers to see available.")
        return

    await ctx.database.set_active_server(server.id)
    server.is_active = True
    ctx.server_manager.set_active_server(server)

    await message.answer(t("server.switched", user_lang, name=server.name))


# ============== Server Creation (OWNER) ==============


@router.message(Command("create"))
@require_role(UserRole.OWNER)
async def cmd_create(
    message: Message,
    state: FSMContext,
    user_lang: str,
) -> None:
    """Handle /create command to start server creation wizard (OWNER only)."""
    await message.answer(
        "📝 **Create New Server**\n\n"
        "Enter a name for the server (letters, numbers, underscores only):"
    )
    await state.set_state(CreateServerStates.waiting_for_name)


@router.message(CreateServerStates.waiting_for_name)
async def process_server_name(
    message: Message,
    state: FSMContext,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Process server name input."""
    name = message.text.strip().replace(" ", "_")

    # Validate name
    if not name.replace("_", "").isalnum():
        await message.answer("❌ Invalid name. Use only letters, numbers, and underscores.")
        return

    # Check if exists
    existing = await ctx.database.get_server_by_name(name)
    if existing:
        await message.answer(t("error.server_exists", user_lang, name=name))
        return

    await state.update_data(name=name)
    await message.answer(
        "⚙️ **Select Engine:**\n\n"
        "1️⃣ `vanilla` - Official Minecraft server\n"
        "2️⃣ `forge` - For mods\n\n"
        "Enter `vanilla` or `forge`:"
    )
    await state.set_state(CreateServerStates.waiting_for_engine)


@router.message(CreateServerStates.waiting_for_engine)
async def process_server_engine(
    message: Message,
    state: FSMContext,
    user_lang: str,
) -> None:
    """Process engine selection."""
    engine_str = message.text.strip().lower()

    if engine_str not in ("vanilla", "forge"):
        await message.answer("❌ Invalid engine. Enter `vanilla` or `forge`.")
        return

    await state.update_data(engine=engine_str)

    # Get latest versions
    if engine_str == "vanilla":
        engine = VanillaEngine()
        latest = await engine.get_latest_version()
    else:
        engine = ForgeEngine()
        latest = await engine.get_latest_version()

    latest_str = latest.version if latest else "1.21.1"

    await message.answer(
        f"🎮 **Select Version:**\n\n"
        f"Latest: `{latest_str}`\n\n"
        f"Enter version (e.g., `{latest_str}`) or `latest`:"
    )
    await state.set_state(CreateServerStates.waiting_for_version)


@router.message(CreateServerStates.waiting_for_version)
async def process_server_version(
    message: Message,
    state: FSMContext,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Process version selection and create server."""
    version = message.text.strip()
    data = await state.get_data()
    await state.clear()

    name = data["name"]
    engine_str = data["engine"]
    engine_type = EngineType.VANILLA if engine_str == "vanilla" else EngineType.FORGE

    # Get engine and resolve version
    if engine_str == "vanilla":
        engine = VanillaEngine()
    else:
        engine = ForgeEngine()

    if version.lower() == "latest":
        latest = await engine.get_latest_version()
        if not latest:
            await message.answer("❌ Could not get latest version")
            return
        version = latest.version

    await message.answer(f"📦 Creating server **{name}** ({engine_str} {version})...")

    try:
        # Create server config
        server = ServerManager.create_server_config(
            name=name,
            mc_version=version.split("-")[0] if "-" in version else version,
            engine=engine_type,
            servers_dir=ctx.config.paths.servers_dir,
            ram_min=ctx.config.defaults.ram_min,
            ram_max=ctx.config.defaults.ram_max,
        )

        # Download and setup
        await message.answer(t("version.downloading", user_lang, version=version))
        await engine.setup_server(version, server.path)

        # Configure server.properties
        ServerProperties.create_default(
            path=server.properties_path,
            server_port=server.port,
            rcon_port=server.rcon_port,
            rcon_password=server.rcon_password,
            motd=f"Minecraft Server - {name}",
        )

        # Save to database
        server.is_active = True
        await ctx.database.create_server(server)

        # Deactivate other servers
        await ctx.database.set_active_server(server.id)

        # Set as active
        ctx.server_manager.set_active_server(server)

        await message.answer(
            t("server.created", user_lang, name=name),
            reply_markup=back_keyboard(user_lang),
        )

    except Exception as e:
        await message.answer(t("error.unknown", user_lang, message=str(e)))


@router.callback_query(lambda c: c.data == "servers:create")
async def callback_servers_create(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    user_lang: str,
) -> None:
    """Handle create server button (OWNER only)."""
    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return

    await callback.message.edit_text(  # type: ignore
        "📝 **Create New Server**\n\n" "Enter a name for the server:"
    )
    await state.set_state(CreateServerStates.waiting_for_name)
    await callback.answer()


# ============== Server Deletion (OWNER) ==============


@router.message(Command("delete"))
@require_role(UserRole.OWNER)
async def cmd_delete(
    message: Message,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /delete command (OWNER only)."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /delete <server_name>")
        return

    server_name = parts[1]
    server = await ctx.database.get_server_by_name(server_name)

    if not server:
        await message.answer(f"Server '{server_name}' not found.")
        return

    if (
        ctx.server_manager.is_running
        and ctx.server_manager.active_server
        and ctx.server_manager.active_server.id == server.id
    ):
        await message.answer("⚠️ Stop the server before deleting!")
        return

    await message.answer(
        f"⚠️ **Delete server '{server_name}'?**\n\n"
        "This will delete all server files including worlds!",
        reply_markup=confirm_keyboard(
            user_lang,
            confirm_data=f"server:confirm_delete:{server.id}",
            cancel_data="menu:main",
        ),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("server:confirm_delete:"))
async def callback_confirm_delete(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle delete confirmation (OWNER only)."""
    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return

    import shutil

    server_id = callback.data.split(":")[2]  # type: ignore
    server = await ctx.database.get_server(server_id)

    if not server:
        await callback.answer("Server not found", show_alert=True)
        return

    try:
        # Delete files
        if server.path.exists():
            shutil.rmtree(server.path)

        # Delete from database
        await ctx.database.delete_server(server_id)

        # Clear active if this was active
        if ctx.server_manager.active_server and ctx.server_manager.active_server.id == server_id:
            ctx.server_manager._active_server = None

        await callback.message.edit_text(  # type: ignore
            t("server.deleted", user_lang, name=server.name),
            reply_markup=back_keyboard(user_lang),
        )
    except Exception as e:
        await callback.message.edit_text(  # type: ignore
            t("error.unknown", user_lang, message=str(e)),
            reply_markup=back_keyboard(user_lang),
        )

    await callback.answer()


# ============== Version Change (OWNER) ==============


@router.message(Command("version"))
@require_role(UserRole.OWNER)
async def cmd_version(
    message: Message,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /version command to change server version (OWNER only)."""
    server = ctx.server_manager.active_server
    if not server:
        await message.answer(t("server.no_active", user_lang))
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            f"{t('version.current', user_lang, version=server.mc_version)}\n\n"
            "Usage: /version <new_version>"
        )
        return

    if ctx.server_manager.is_running:
        await message.answer("⚠️ Stop the server before changing version!")
        return

    new_version = parts[1]
    await message.answer(t("version.changing", user_lang, version=new_version))

    try:
        # Get appropriate engine
        if server.engine == EngineType.FORGE:
            engine = ForgeEngine()
        else:
            engine = VanillaEngine()

        # Download new version
        await message.answer(t("version.downloading", user_lang, version=new_version))
        await engine.download_server(new_version, server.path)

        # Update server config
        server.mc_version = new_version.split("-")[0] if "-" in new_version else new_version
        await ctx.database.update_server(server)

        await message.answer(t("version.changed", user_lang, version=new_version))

    except Exception as e:
        await message.answer(t("error.unknown", user_lang, message=str(e)))


# ============== Server Import (OWNER) ==============


@router.message(Command("import", "scan"))
@require_role(UserRole.OWNER)
async def cmd_import(
    message: Message,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle /import command to scan and import existing servers (OWNER only)."""
    from src.utils.server_scanner import ServerScanner, format_discovered_server

    await message.answer(t("server.import.scanning", user_lang))

    # Get known server names
    servers = await ctx.database.get_all_servers()
    known_names = [s.name for s in servers]

    # Scan for new servers
    scanner = ServerScanner(ctx.config.paths.servers_dir)
    discovered = scanner.scan_for_servers(known_names)

    if not discovered:
        await message.answer(t("server.import.none_found", user_lang))
        return

    # Show discovered servers
    text = t("server.import.title", user_lang) + "\n\n"
    for srv in discovered:
        text += format_discovered_server(srv, user_lang) + "\n\n"

    text += t("server.import.select", user_lang)

    # Build keyboard
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    for srv in discovered:
        engine_icon = "🔧" if srv.engine.value == "forge" else "📦"
        builder.row(
            InlineKeyboardButton(
                text=f"{engine_icon} {srv.name} ({srv.mc_version})",
                callback_data=f"import:server:{srv.name}",
            )
        )
    builder.row(
        InlineKeyboardButton(text=t("button.back", user_lang), callback_data="servers:list"),
    )

    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data == "servers:scan")
async def callback_scan_servers(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle scan servers button (OWNER only)."""
    import asyncio
    import logging

    from src.utils.server_scanner import ServerScanner, format_discovered_server

    logger = logging.getLogger(__name__)

    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return

    try:
        await callback.message.edit_text(t("server.import.scanning", user_lang))  # type: ignore

        # Get known server names
        servers = await ctx.database.get_all_servers()
        known_names = [s.name for s in servers]

        # Scan for new servers in executor to not block event loop
        scanner = ServerScanner(ctx.config.paths.servers_dir)
        loop = asyncio.get_event_loop()
        discovered = await loop.run_in_executor(None, scanner.scan_for_servers, known_names)

        logger.info(f"Scan completed: found {len(discovered)} servers")

        if not discovered:
            await callback.message.edit_text(  # type: ignore
                t("server.import.none_found", user_lang),
                reply_markup=back_keyboard(user_lang, "servers:list"),
            )
            return

        # Show discovered servers
        text = t("server.import.title", user_lang) + "\n\n"
        for srv in discovered:
            text += format_discovered_server(srv, user_lang) + "\n\n"

        text += t("server.import.select", user_lang)

        # Build keyboard
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        for srv in discovered:
            engine_icon = "🔧" if srv.engine.value == "forge" else "📦"
            builder.row(
                InlineKeyboardButton(
                    text=f"{engine_icon} {srv.name} ({srv.mc_version})",
                    callback_data=f"import:server:{srv.name}",
                )
            )
        builder.row(
            InlineKeyboardButton(text=t("button.back", user_lang), callback_data="servers:list"),
        )

        await callback.message.edit_text(text, reply_markup=builder.as_markup())  # type: ignore

    except Exception as e:
        logger.exception("Error scanning servers")
        await callback.message.edit_text(  # type: ignore
            t("error.unknown", user_lang, message=str(e)),
            reply_markup=back_keyboard(user_lang, "servers:list"),
        )


@router.callback_query(lambda c: c.data and c.data.startswith("import:server:"))
async def callback_import_server(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle server import selection (OWNER only)."""
    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return

    from src.utils.server_scanner import ServerScanner

    server_name = callback.data.split(":")[2]  # type: ignore

    # Get known server names and scan again
    servers = await ctx.database.get_all_servers()
    known_names = [s.name for s in servers]

    scanner = ServerScanner(ctx.config.paths.servers_dir)
    discovered = scanner.scan_for_servers(known_names)

    # Find the selected server
    selected = None
    for srv in discovered:
        if srv.name == server_name:
            selected = srv
            break

    if not selected:
        await callback.answer("Server not found", show_alert=True)
        return

    # Show confirmation
    await callback.message.edit_text(  # type: ignore
        t(
            "server.import.confirm",
            user_lang,
            name=selected.name,
            version=selected.mc_version,
            engine=selected.engine.value,
            port=selected.port,
        ),
        reply_markup=confirm_keyboard(
            user_lang,
            confirm_data=f"import:confirm:{selected.name}",
            cancel_data="servers:scan",
        ),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("import:confirm:"))
async def callback_import_confirm(
    callback: CallbackQuery,
    user: User,
    user_lang: str,
    ctx: "BotContext",  # type: ignore
) -> None:
    """Handle server import confirmation (OWNER only)."""
    if not await check_role(user, UserRole.OWNER, callback, user_lang):
        return

    from src.utils.server_scanner import ServerScanner

    server_name = callback.data.split(":")[2]  # type: ignore

    # Scan again to get fresh data
    servers = await ctx.database.get_all_servers()
    known_names = [s.name for s in servers]

    scanner = ServerScanner(ctx.config.paths.servers_dir)
    discovered = scanner.scan_for_servers(known_names)

    # Find the selected server
    selected = None
    for srv in discovered:
        if srv.name == server_name:
            selected = srv
            break

    if not selected:
        await callback.answer("Server not found", show_alert=True)
        return

    try:
        # Import the server
        server = scanner.import_server(
            selected,
            ram_min=ctx.config.defaults.ram_min,
            ram_max=ctx.config.defaults.ram_max,
        )

        # Save to database
        await ctx.database.create_server(server)

        # Build response
        response = t("server.import.success", user_lang, name=server.name)
        if selected.needs_rcon_setup:
            response += "\n" + t("server.import.rcon_configured", user_lang)

        await callback.message.edit_text(  # type: ignore
            response,
            reply_markup=back_keyboard(user_lang, "servers:list"),
        )

    except Exception as e:
        await callback.message.edit_text(  # type: ignore
            t("error.unknown", user_lang, message=str(e)),
            reply_markup=back_keyboard(user_lang),
        )

    await callback.answer()
