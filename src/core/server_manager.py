"""Main server manager that orchestrates all components."""

import asyncio
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.auto_shutdown import AutoShutdownManager
from src.core.backup_manager import BackupManager
from src.core.log_watcher import EventType, LogWatcher
from src.core.process_handler import ProcessConfig, ProcessHandler
from src.core.rcon import RconClient
from src.storage.models import Backup, BackupType, EngineType, Server, ServerStatus
from src.utils.config import Config

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


class ServerManager:
    """
    Main manager for Minecraft server operations.

    Orchestrates process handling, log watching, backups,
    auto-shutdown, and RCON communication.
    """

    def __init__(self, config: Config):
        self.config = config
        self._active_server: Server | None = None
        self._process: ProcessHandler | None = None
        self._log_watcher: LogWatcher | None = None
        self._rcon: RconClient | None = None
        self._backup_manager: BackupManager | None = None
        self._auto_shutdown: AutoShutdownManager | None = None
        self._server_ready = asyncio.Event()

        # Callbacks for notifications
        self._on_server_start: list[Callable[[Server], Any]] = []
        self._on_server_stop: list[Callable[[Server, int], Any]] = []
        self._on_player_join: list[Callable[[Server, str], Any]] = []
        self._on_player_leave: list[Callable[[Server, str], Any]] = []
        self._on_server_crash: list[Callable[[Server], Any]] = []

    @property
    def active_server(self) -> Server | None:
        """Get currently active server."""
        return self._active_server

    @property
    def is_running(self) -> bool:
        """Check if server is currently running."""
        return self._process is not None and self._process.is_running

    @property
    def status(self) -> ServerStatus:
        """Get current server status."""
        if not self._active_server:
            return ServerStatus(is_running=False)

        return ServerStatus(
            is_running=self.is_running,
            players_online=self._log_watcher.player_count if self._log_watcher else 0,
            players_max=20,  # TODO: Parse from server.properties
            players_list=self._log_watcher.online_players if self._log_watcher else [],
            uptime_seconds=self._process.uptime_seconds if self._process else None,
            mc_version=self._active_server.mc_version,
        )

    def set_active_server(self, server: Server) -> None:
        """Set the active server."""
        if self.is_running:
            raise RuntimeError("Cannot switch servers while running. Stop the server first.")
        self._active_server = server
        self._init_components()

    def _init_components(self) -> None:
        """Initialize components for the active server."""
        if not self._active_server:
            return

        server = self._active_server

        # Backup manager
        self._backup_manager = BackupManager(
            backups_dir=self.config.paths.backups_dir,
            keep_count=self.config.backups.keep_count,
        )

        # Auto shutdown
        self._auto_shutdown = AutoShutdownManager(
            empty_minutes=self.config.auto_shutdown.empty_minutes
            if self.config.auto_shutdown.enabled
            else 0,
            on_shutdown=self._handle_auto_shutdown,
            on_warning=self._handle_shutdown_warning,
        )

        # Log watcher
        self._log_watcher = LogWatcher()
        self._setup_log_callbacks()

        # RCON client
        self._rcon = RconClient(
            host="localhost",
            port=server.rcon_port,
            password=server.rcon_password,
        )

    def _setup_log_callbacks(self) -> None:
        """Set up log watcher event callbacks."""
        if not self._log_watcher:
            return

        self._log_watcher.on_event(self._handle_server_ready, EventType.SERVER_STARTED)
        self._log_watcher.on_event(self._handle_player_joined, EventType.PLAYER_JOINED)
        self._log_watcher.on_event(self._handle_player_left, EventType.PLAYER_LEFT)

    async def _handle_server_ready(self, event) -> None:
        """Handle server ready event."""
        self._server_ready.set()

        # Notify on_server_start callbacks (server is now actually ready)
        if self._active_server:
            for callback in self._on_server_start:
                try:
                    result = callback(self._active_server)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass

        # Connect RCON after server is ready
        if self._rcon:
            await asyncio.sleep(2)  # Brief delay for RCON to be ready
            await self._rcon.connect()

    async def _handle_player_joined(self, event) -> None:
        """Handle player join event."""
        if not self._active_server or not event.player:
            return

        # Cancel auto-shutdown
        if self._auto_shutdown:
            self._auto_shutdown.on_player_count_changed(
                self._log_watcher.player_count if self._log_watcher else 1
            )

        # Notify callbacks
        for callback in self._on_player_join:
            try:
                result = callback(self._active_server, event.player)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    async def _handle_player_left(self, event) -> None:
        """Handle player leave event."""
        if not self._active_server or not event.player:
            return

        # Check for auto-shutdown
        if self._auto_shutdown and self._log_watcher:
            self._auto_shutdown.on_player_count_changed(self._log_watcher.player_count)

        # Notify callbacks
        for callback in self._on_player_leave:
            try:
                result = callback(self._active_server, event.player)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    async def _handle_auto_shutdown(self) -> None:
        """Handle auto-shutdown trigger."""
        if self._active_server:
            await self.stop()

    async def _handle_shutdown_warning(self, minutes_remaining: int) -> None:
        """Handle shutdown warning."""
        if self._rcon:
            await self._rcon.command(
                f"say Server will auto-shutdown in {minutes_remaining} minute(s) due to inactivity"
            )

    async def _handle_process_exit(self, exit_code: int) -> None:
        """Handle server process exit."""
        server = self._active_server
        if not server:
            return

        # Cleanup
        if self._rcon:
            await self._rcon.disconnect()
        if self._log_watcher:
            self._log_watcher.reset()
        if self._auto_shutdown:
            self._auto_shutdown.reset()
        self._server_ready.clear()

        # Determine if crash or normal exit
        is_crash = exit_code != 0

        if is_crash:
            for callback in self._on_server_crash:
                try:
                    result = callback(server)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass
        else:
            for callback in self._on_server_stop:
                try:
                    result = callback(server, exit_code)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass

    # === Event Registration ===

    def on_server_start(self, callback: "Callable[[Server], Any]") -> None:
        """Register callback for server start."""
        self._on_server_start.append(callback)

    def on_server_stop(self, callback: "Callable[[Server, int], Any]") -> None:
        """Register callback for server stop (receives exit code)."""
        self._on_server_stop.append(callback)

    def on_player_join(self, callback: "Callable[[Server, str], Any]") -> None:
        """Register callback for player join."""
        self._on_player_join.append(callback)

    def on_player_leave(self, callback: "Callable[[Server, str], Any]") -> None:
        """Register callback for player leave."""
        self._on_player_leave.append(callback)

    def on_server_crash(self, callback: "Callable[[Server], Any]") -> None:
        """Register callback for server crash."""
        self._on_server_crash.append(callback)

    # === Server Operations ===

    async def start(self) -> bool:
        """
        Start the active server.

        Returns:
            True if started, False if already running or no server
        """
        if not self._active_server:
            raise RuntimeError("No active server set")

        if self.is_running:
            return False

        server = self._active_server

        # Create process handler
        process_config = ProcessConfig(
            java_path=self.config.defaults.java_path,
            jar_path=server.jar_path,
            working_dir=server.path,
            ram_min=server.ram_min,
            ram_max=server.ram_max,
        )
        self._process = ProcessHandler(process_config)

        # Set up stdout callback for log watching
        if self._log_watcher:
            self._process.on_stdout(
                lambda line: asyncio.create_task(self._log_watcher.process_line(line))
            )

        # Set up exit callback
        self._process.on_exit(lambda code: asyncio.create_task(self._handle_process_exit(code)))

        # Start the process
        self._server_ready.clear()
        success = await self._process.start()

        if success:
            # Update last started time
            server.last_started_at = datetime.now()
            # Note: _on_server_start callbacks are called in _handle_server_ready
            # when the server is actually ready (after "Done!" message in logs)

        return success

    async def stop(self, timeout: float = 30.0) -> bool:
        """
        Stop the server gracefully.

        Args:
            timeout: Seconds to wait for graceful shutdown

        Returns:
            True if stopped, False if not running
        """
        if not self._process or not self.is_running:
            return False

        server = self._active_server

        # Create backup before stop if configured
        if self.config.backups.backup_on_stop and server and self._backup_manager:
            try:
                await self._backup_manager.create_backup(server, BackupType.PRE_SHUTDOWN)
            except Exception:
                pass  # Don't fail stop if backup fails

        # Stop the process
        return await self._process.stop(timeout)

    async def restart(self, timeout: float = 30.0) -> bool:
        """Stop and start the server."""
        await self.stop(timeout)
        await asyncio.sleep(2)
        return await self.start()

    async def kill(self) -> None:
        """Force kill the server process."""
        if self._process:
            await self._process.kill()

    async def send_command(self, command: str) -> str | None:
        """
        Send a command to the server.

        Prefers RCON if connected, falls back to stdin.

        Args:
            command: Command to send (without leading /)

        Returns:
            Command response (RCON only) or None
        """
        # Try RCON first
        if self._rcon and self._rcon.is_connected:
            return await self._rcon.command(command)

        # Fall back to stdin
        if self._process:
            await self._process.send_command(command)
            return None

        return None

    async def wait_until_ready(self, timeout: float = 120.0) -> bool:
        """
        Wait for server to be fully started.

        Args:
            timeout: Seconds to wait

        Returns:
            True if ready, False if timeout
        """
        try:
            await asyncio.wait_for(self._server_ready.wait(), timeout)
            return True
        except TimeoutError:
            return False

    # === Backup Operations ===

    async def create_backup(
        self,
        backup_type: BackupType = BackupType.MANUAL,
    ) -> Backup | None:
        """Create a backup of the current server."""
        if not self._active_server or not self._backup_manager:
            return None

        # Save world before backup if server is running
        if self.is_running:
            await self.send_command("save-all flush")
            await asyncio.sleep(3)  # Wait for save

        return await self._backup_manager.create_backup(
            self._active_server,
            backup_type,
        )

    async def restore_backup(self, backup: Backup) -> None:
        """
        Restore a backup to the current server.

        Server must be stopped first.
        """
        if self.is_running:
            raise RuntimeError("Stop the server before restoring a backup")

        if not self._active_server or not self._backup_manager:
            raise RuntimeError("No active server")

        await self._backup_manager.restore_backup(self._active_server, backup)

    # === Player Operations ===

    async def get_online_players(self) -> list[str]:
        """Get list of online players."""
        if self._log_watcher:
            return self._log_watcher.online_players
        return []

    async def kick_player(self, player: str, reason: str = "") -> bool:
        """Kick a player from the server."""
        cmd = f"kick {player}" + (f" {reason}" if reason else "")
        result = await self.send_command(cmd)
        return result is not None or self._process is not None

    async def say(self, message: str) -> bool:
        """Send a message to the server chat."""
        result = await self.send_command(f"say {message}")
        return result is not None or self._process is not None

    # === Server Creation ===

    @staticmethod
    def create_server_config(
        name: str,
        mc_version: str,
        engine: EngineType,
        servers_dir: Path,
        port: int = 25565,
        ram_min: str = "4G",
        ram_max: str = "10G",
    ) -> Server:
        """
        Create a new server configuration.

        Does not download files, just creates the config.

        Args:
            name: Server name (used as folder name)
            mc_version: Minecraft version
            engine: Server engine type
            servers_dir: Base directory for servers
            port: Server port
            ram_min: Minimum RAM allocation
            ram_max: Maximum RAM allocation

        Returns:
            Server configuration object
        """
        server_id = str(uuid.uuid4())
        server_path = servers_dir / name

        # Generate RCON password
        rcon_password = secrets.token_urlsafe(16)

        return Server(
            id=server_id,
            name=name,
            engine=engine,
            mc_version=mc_version,
            path=server_path,
            port=port,
            ram_min=ram_min,
            ram_max=ram_max,
            rcon_port=port + 10,  # RCON port = server port + 10
            rcon_password=rcon_password,
            is_active=False,
            created_at=datetime.now(),
        )
