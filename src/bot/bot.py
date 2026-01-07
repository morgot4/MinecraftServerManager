"""Main Telegram bot setup and initialization."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.handlers import (
    admin,
    backup,
    mods,
    players,
    roles,
    server,
    start,
)
from src.bot.handlers import config as config_handlers
from src.bot.middlewares.auth import AuthMiddleware
from src.bot.notifications import NotificationManager
from src.core.server_manager import ServerManager
from src.storage.database import Database
from src.utils.config import Config

logger = logging.getLogger(__name__)


class BotContext:
    """Shared context for bot handlers."""

    def __init__(
        self,
        config: Config,
        server_manager: ServerManager,
        database: Database,
    ):
        self.config = config
        self.server_manager = server_manager
        self.database = database
        self.notification_manager: NotificationManager | None = None


async def create_bot(config: Config) -> tuple[Bot, Dispatcher, BotContext]:
    """
    Create and configure the Telegram bot.

    Args:
        config: Application configuration

    Returns:
        Tuple of (Bot, Dispatcher, BotContext)
    """
    # Validate token
    if not config.telegram.bot_token:
        raise ValueError(
            "Bot token not configured. Set BOT_TOKEN environment variable "
            "or telegram.bot_token in config.yaml"
        )

    # Create bot instance
    bot = Bot(
        token=config.telegram.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )

    # Create dispatcher with in-memory FSM storage
    dp = Dispatcher(storage=MemoryStorage())

    # Initialize database
    database = Database(config.paths.database)
    await database.connect()

    # Initialize server manager
    server_manager = ServerManager(config)

    # Load active server from database
    active_server = await database.get_active_server()
    if active_server:
        server_manager.set_active_server(active_server)
        logger.info(f"Loaded active server: {active_server.name}")

    # Create context
    ctx = BotContext(
        config=config,
        server_manager=server_manager,
        database=database,
    )

    # Set up notification manager
    ctx.notification_manager = NotificationManager(
        bot=bot,
        config=config,
        server_manager=server_manager,
    )

    # Create auth middleware instance
    auth_middleware = AuthMiddleware(config, database)

    # Register handlers
    all_routers = [
        start.router,
        server.router,
        players.router,
        config_handlers.router,
        backup.router,
        mods.router,
        roles.router,
        admin.router,
    ]

    for router in all_routers:
        # Register middleware on each router
        router.message.middleware(auth_middleware)
        router.callback_query.middleware(auth_middleware)
        dp.include_router(router)

    # Store context in dispatcher for handlers
    dp["ctx"] = ctx

    return bot, dp, ctx


async def run_bot(config: Config) -> None:
    """
    Run the Telegram bot.

    Args:
        config: Application configuration
    """
    bot, dp, ctx = await create_bot(config)

    logger.info("Starting Minecraft Server Manager bot...")

    try:
        # Get bot info
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot started successfully! @{bot_info.username}")
        logger.info("Waiting for messages... (Press Ctrl+C to stop)")

        # Start polling
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        # Cleanup
        logger.info("Shutting down...")

        # Stop server if running
        if ctx.server_manager.is_running:
            logger.info("Stopping Minecraft server...")
            await ctx.server_manager.stop()

        # Close database
        await ctx.database.close()

        # Close bot session
        await bot.session.close()
