"""Auto-shutdown manager for idle servers."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any


class AutoShutdownManager:
    """
    Manages automatic server shutdown when no players are online.

    Starts a countdown when player count drops to zero.
    Cancels countdown if a player joins.
    """

    def __init__(
        self,
        empty_minutes: int = 30,
        on_shutdown: Callable[[], Any] | None = None,
        on_warning: Callable[[int], Any] | None = None,
    ):
        """
        Initialize auto-shutdown manager.

        Args:
            empty_minutes: Minutes to wait before shutdown (0 = disabled)
            on_shutdown: Callback when shutdown triggers
            on_warning: Callback for warnings (receives minutes remaining)
        """
        self.empty_minutes = empty_minutes
        self._on_shutdown = on_shutdown
        self._on_warning = on_warning

        self._countdown_task: asyncio.Task | None = None
        self._empty_since: datetime | None = None
        self._enabled = empty_minutes > 0
        self._warning_intervals = [10, 5, 1]  # Minutes before shutdown to warn

    @property
    def is_enabled(self) -> bool:
        """Check if auto-shutdown is enabled."""
        return self._enabled

    @property
    def is_counting_down(self) -> bool:
        """Check if countdown is active."""
        return self._countdown_task is not None and not self._countdown_task.done()

    @property
    def time_remaining(self) -> timedelta | None:
        """Get time remaining until shutdown."""
        if not self._empty_since or not self._enabled:
            return None
        elapsed = datetime.now() - self._empty_since
        remaining = timedelta(minutes=self.empty_minutes) - elapsed
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    def enable(self, empty_minutes: int | None = None) -> None:
        """Enable auto-shutdown."""
        if empty_minutes is not None:
            self.empty_minutes = empty_minutes
        self._enabled = self.empty_minutes > 0

    def disable(self) -> None:
        """Disable auto-shutdown and cancel any pending countdown."""
        self._enabled = False
        self.cancel()

    def on_player_count_changed(self, count: int) -> None:
        """
        Handle player count change.

        Args:
            count: Current number of online players
        """
        if not self._enabled:
            return

        if count == 0:
            self._start_countdown()
        else:
            self.cancel()

    def _start_countdown(self) -> None:
        """Start the shutdown countdown."""
        if self.is_counting_down:
            return  # Already counting

        self._empty_since = datetime.now()
        self._countdown_task = asyncio.create_task(self._countdown_loop())

    async def _countdown_loop(self) -> None:
        """Run the countdown with warnings."""
        try:
            remaining_minutes = self.empty_minutes
            warned = set()

            while remaining_minutes > 0:
                # Check if we should warn
                for warn_minutes in self._warning_intervals:
                    if remaining_minutes <= warn_minutes and warn_minutes not in warned:
                        warned.add(warn_minutes)
                        if self._on_warning:
                            try:
                                result = self._on_warning(remaining_minutes)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception:
                                pass

                # Wait one minute
                await asyncio.sleep(60)
                remaining_minutes -= 1

            # Time's up - trigger shutdown
            if self._on_shutdown:
                try:
                    result = self._on_shutdown()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass

        except asyncio.CancelledError:
            pass  # Countdown was cancelled
        finally:
            self._empty_since = None

    def cancel(self) -> None:
        """Cancel the current countdown."""
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        self._countdown_task = None
        self._empty_since = None

    def reset(self) -> None:
        """Reset state (e.g., when server stops)."""
        self.cancel()
