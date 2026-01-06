"""Log watcher for parsing Minecraft server events."""

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of server events that can be detected."""

    SERVER_STARTING = "server_starting"
    SERVER_STARTED = "server_started"
    SERVER_STOPPING = "server_stopping"
    SERVER_STOPPED = "server_stopped"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_CHAT = "player_chat"
    PLAYER_DIED = "player_died"
    PLAYER_ACHIEVEMENT = "player_achievement"
    RCON_STARTED = "rcon_started"
    WORLD_SAVED = "world_saved"
    ERROR = "error"
    WARNING = "warning"


@dataclass
class ServerEvent:
    """Parsed server event from log."""

    event_type: EventType
    timestamp: datetime
    player: str | None = None
    message: str | None = None
    raw_line: str = ""


class LogWatcher:
    """
    Watches and parses Minecraft server log output.

    Detects events like player joins/leaves, server start/stop, etc.
    """

    # Log line patterns
    # Example: [12:34:56] [Server thread/INFO]: Done (2.5s)! For help, type "help"
    LOG_PATTERN = re.compile(r"\[(\d{2}:\d{2}:\d{2})\]\s*\[([^\]]+)/(\w+)\]:\s*(.*)")

    # Event patterns
    PATTERNS = {
        EventType.SERVER_STARTED: re.compile(r'Done \([^)]+\)! For help, type "help"'),
        EventType.SERVER_STOPPING: re.compile(r"Stopping the server"),
        EventType.SERVER_STOPPED: re.compile(r"Closing Server"),
        EventType.PLAYER_JOINED: re.compile(r"(\w+)\[/[\d.:]+\] logged in with entity id"),
        EventType.PLAYER_LEFT: re.compile(r"(\w+) left the game"),
        EventType.PLAYER_CHAT: re.compile(r"<(\w+)>\s+(.+)"),
        EventType.PLAYER_DIED: re.compile(
            r"(\w+) (was |died|fell|drowned|burned|blew up|hit the ground|suffocated|starved|withered|experienced kinetic energy)"
        ),
        EventType.PLAYER_ACHIEVEMENT: re.compile(
            r"(\w+) has (made the advancement|completed the challenge|reached the goal) \[(.+)\]"
        ),
        EventType.RCON_STARTED: re.compile(r"RCON running on [\d.:]+"),
        EventType.WORLD_SAVED: re.compile(r"Saved the (game|world)"),
    }

    def __init__(self):
        self._callbacks: dict[EventType | None, list[Callable[[ServerEvent], Any]]] = {}
        self._online_players: set[str] = set()

    @property
    def online_players(self) -> list[str]:
        """Get list of currently online players."""
        return sorted(self._online_players)

    @property
    def player_count(self) -> int:
        """Get number of online players."""
        return len(self._online_players)

    def on_event(
        self,
        callback: Callable[[ServerEvent], Any],
        event_type: EventType | None = None,
    ) -> None:
        """
        Register callback for events.

        Args:
            callback: Function to call when event occurs
            event_type: Specific event type, or None for all events
        """
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        self._callbacks[event_type].append(callback)

    def on_player_join(self, callback: Callable[[str], Any]) -> None:
        """Register callback for player joins."""
        self.on_event(
            lambda e: callback(e.player) if e.player else None,
            EventType.PLAYER_JOINED,
        )

    def on_player_leave(self, callback: Callable[[str], Any]) -> None:
        """Register callback for player leaves."""
        self.on_event(
            lambda e: callback(e.player) if e.player else None,
            EventType.PLAYER_LEFT,
        )

    def on_server_ready(self, callback: Callable[[], Any]) -> None:
        """Register callback for when server is fully started."""
        self.on_event(lambda _: callback(), EventType.SERVER_STARTED)

    def parse_line(self, line: str) -> ServerEvent | None:
        """
        Parse a log line and return event if detected.

        Args:
            line: Raw log line from server stdout

        Returns:
            ServerEvent if event detected, None otherwise
        """
        if not line.strip():
            return None

        # Try to parse standard log format
        match = self.LOG_PATTERN.match(line)
        if match:
            time_str, thread, level, message = match.groups()

            # Parse time
            try:
                now = datetime.now()
                time_parts = time_str.split(":")
                timestamp = now.replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=int(time_parts[2]),
                    microsecond=0,
                )
            except (ValueError, IndexError):
                timestamp = datetime.now()
        else:
            # Non-standard format, still try to parse
            message = line
            timestamp = datetime.now()

        # Check each event pattern
        for event_type, pattern in self.PATTERNS.items():
            event_match = pattern.search(message if match else line)
            if event_match:
                event = self._create_event(event_type, event_match, timestamp, line)
                if event:
                    self._update_state(event)
                    return event

        return None

    def _create_event(
        self,
        event_type: EventType,
        match: re.Match,
        timestamp: datetime,
        raw_line: str,
    ) -> ServerEvent | None:
        """Create event object from pattern match."""
        player = None
        message = None

        if event_type == EventType.PLAYER_JOINED:
            player = match.group(1)
        elif event_type == EventType.PLAYER_LEFT:
            player = match.group(1)
        elif event_type == EventType.PLAYER_CHAT:
            player = match.group(1)
            message = match.group(2)
        elif event_type == EventType.PLAYER_DIED:
            player = match.group(1)
            message = match.group(0)  # Full death message
        elif event_type == EventType.PLAYER_ACHIEVEMENT:
            player = match.group(1)
            message = match.group(3)  # Achievement name

        return ServerEvent(
            event_type=event_type,
            timestamp=timestamp,
            player=player,
            message=message,
            raw_line=raw_line,
        )

    def _update_state(self, event: ServerEvent) -> None:
        """Update internal state based on event."""
        if event.event_type == EventType.PLAYER_JOINED and event.player:
            self._online_players.add(event.player)
        elif event.event_type == EventType.PLAYER_LEFT and event.player:
            self._online_players.discard(event.player)
        elif event.event_type == EventType.SERVER_STOPPING:
            self._online_players.clear()

    async def process_line(self, line: str) -> None:
        """
        Process a log line and trigger callbacks.

        Args:
            line: Raw log line from server
        """
        event = self.parse_line(line)
        if event:
            logger.info(
                "[EVENT] %s | player=%s | message=%s",
                event.event_type.value,
                event.player or "-",
                event.message or "-",
            )
            await self._trigger_callbacks(event)

    async def _trigger_callbacks(self, event: ServerEvent) -> None:
        """Trigger registered callbacks for an event."""
        # Specific event callbacks
        for callback in self._callbacks.get(event.event_type, []):
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Don't let callback errors propagate

        # Global callbacks (event_type=None)
        for callback in self._callbacks.get(None, []):
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def reset(self) -> None:
        """Reset internal state (e.g., when server stops)."""
        self._online_players.clear()
