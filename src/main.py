#!/usr/bin/env python3
"""
Minecraft Server Manager - Telegram bot for managing Minecraft servers.

Usage:
    python -m src.main

Or using poetry:
    poetry run mcmanager
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bot.bot import run_bot
from src.utils.config import load_config
from src.utils.java import check_java


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noise from libraries
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


async def check_requirements(java_path: str = "java") -> bool:
    """Check that all requirements are met."""
    logger = logging.getLogger(__name__)

    # Check Java
    logger.info("Checking Java installation...")
    java_info = await check_java(java_path)

    if not java_info.is_valid:
        logger.error(f"Java check failed: {java_info.error}")
        logger.error("Please install Java 17 or higher.")
        return False

    logger.info(f"Found Java {java_info.version} at {java_info.path}")

    if java_info.major_version < 17:
        logger.warning(
            f"Java {java_info.major_version} detected. " f"Minecraft 1.18+ requires Java 17+."
        )

    return True


async def async_main() -> None:
    """Async entry point."""
    logger = logging.getLogger(__name__)

    # Load configuration
    logger.info("Loading configuration...")
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        logger.info("Make sure config.yaml exists. You can copy config.example.yaml")
        sys.exit(1)

    # Validate token
    if not config.telegram.bot_token:
        logger.error(
            "Bot token not configured!\n"
            "Set BOT_TOKEN environment variable or configure in config.yaml"
        )
        sys.exit(1)

    # Check requirements
    if not await check_requirements(config.defaults.java_path):
        sys.exit(1)

    # Ensure directories exist
    config.paths.servers_dir.mkdir(parents=True, exist_ok=True)
    config.paths.backups_dir.mkdir(parents=True, exist_ok=True)
    config.paths.database.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Starting Minecraft Server Manager...")
    logger.info(f"Servers directory: {config.paths.servers_dir}")
    logger.info(f"Backups directory: {config.paths.backups_dir}")

    # Run the bot
    try:
        await run_bot(config)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    setup_logging()

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
