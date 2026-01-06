"""Notification manager for sending alerts to admins."""

import logging

from aiogram import Bot

from src.core.server_manager import ServerManager
from src.i18n import t
from src.storage.models import Server
from src.utils.config import Config

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Manages sending notifications to admin users.

    Hooks into ServerManager events and sends Telegram messages.
    """

    def __init__(
        self,
        bot: Bot,
        config: Config,
        server_manager: ServerManager,
    ):
        self.bot = bot
        self.config = config
        self.server_manager = server_manager
        self._setup_callbacks()

    def _setup_callbacks(self) -> None:
        """Register callbacks with server manager."""
        if self.config.notifications.server_start:
            self.server_manager.on_server_start(self._on_server_start)

        if self.config.notifications.server_stop:
            self.server_manager.on_server_stop(self._on_server_stop)

        if self.config.notifications.player_join:
            self.server_manager.on_player_join(self._on_player_join)

        if self.config.notifications.player_leave:
            self.server_manager.on_player_leave(self._on_player_leave)

        if self.config.notifications.crash:
            self.server_manager.on_server_crash(self._on_server_crash)

    async def _notify_admins(self, message: str) -> None:
        """Send message to all admin users."""
        for admin_id in self.config.telegram.admin_ids:
            try:
                await self.bot.send_message(admin_id, message)
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")

    async def _on_server_start(self, server: Server) -> None:
        """Handle server start notification."""
        message = t("notify.server_started", name=server.name)
        await self._notify_admins(message)

    async def _on_server_stop(self, server: Server, exit_code: int) -> None:
        """Handle server stop notification."""
        message = t("notify.server_stopped", name=server.name)
        await self._notify_admins(message)

    async def _on_player_join(self, server: Server, player: str) -> None:
        """Handle player join notification."""
        message = t("notify.player_joined", player=player, server=server.name)
        await self._notify_admins(message)

    async def _on_player_leave(self, server: Server, player: str) -> None:
        """Handle player leave notification."""
        message = t("notify.player_left", player=player, server=server.name)
        await self._notify_admins(message)

    async def _on_server_crash(self, server: Server) -> None:
        """Handle server crash notification."""
        message = t("notify.server_crashed", name=server.name)
        await self._notify_admins(message)

    async def notify_auto_shutdown(self, server: Server) -> None:
        """Notify about auto-shutdown."""
        message = t("notify.auto_shutdown", name=server.name)
        await self._notify_admins(message)

    async def notify_backup_created(self, filename: str) -> None:
        """Notify about automatic backup."""
        message = t("notify.backup_auto", filename=filename)
        await self._notify_admins(message)
