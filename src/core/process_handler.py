"""Async process handler for Minecraft server Java process."""

import asyncio
import logging
from asyncio.subprocess import Process
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProcessState:
    """Current state of the server process."""

    is_running: bool = False
    pid: int | None = None
    started_at: datetime | None = None
    exit_code: int | None = None


@dataclass
class ProcessConfig:
    """Configuration for starting a server process."""

    java_path: str
    jar_path: Path
    working_dir: Path
    ram_min: str = "2G"
    ram_max: str = "8G"
    extra_args: list[str] = field(default_factory=list)


class ProcessHandler:
    """
    Handles the Minecraft server Java process.

    Provides async start/stop/restart operations and stdout/stderr streaming.
    """

    def __init__(self, config: ProcessConfig):
        self.config = config
        self._process: Process | None = None
        self._state = ProcessState()
        self._stdout_callbacks: list[Callable[[str], Any]] = []
        self._stderr_callbacks: list[Callable[[str], Any]] = []
        self._exit_callbacks: list[Callable[[int], Any]] = []
        self._reader_task: asyncio.Task | None = None

    @property
    def state(self) -> ProcessState:
        """Get current process state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if process is currently running."""
        return self._state.is_running and self._process is not None

    @property
    def uptime_seconds(self) -> int | None:
        """Get uptime in seconds if running."""
        if self._state.started_at and self._state.is_running:
            return int((datetime.now() - self._state.started_at).total_seconds())
        return None

    def on_stdout(self, callback: Callable[[str], Any]) -> None:
        """Register callback for stdout lines."""
        self._stdout_callbacks.append(callback)

    def on_stderr(self, callback: Callable[[str], Any]) -> None:
        """Register callback for stderr lines."""
        self._stderr_callbacks.append(callback)

    def on_exit(self, callback: Callable[[int], Any]) -> None:
        """Register callback for process exit."""
        self._exit_callbacks.append(callback)

    def _build_command(self) -> list[str]:
        """Build the Java command line."""
        cmd = [
            self.config.java_path,
            f"-Xms{self.config.ram_min}",
            f"-Xmx{self.config.ram_max}",
            # Recommended JVM flags for Minecraft
            "-XX:+UseG1GC",
            "-XX:+ParallelRefProcEnabled",
            "-XX:MaxGCPauseMillis=200",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+DisableExplicitGC",
            "-XX:+AlwaysPreTouch",
            "-XX:G1HeapWastePercent=5",
            "-XX:G1MixedGCCountTarget=4",
            "-XX:G1MixedGCLiveThresholdPercent=90",
            "-XX:G1RSetUpdatingPauseTimePercent=5",
            "-XX:SurvivorRatio=32",
            "-XX:+PerfDisableSharedMem",
            "-XX:MaxTenuringThreshold=1",
            "-Dusing.aikars.flags=https://mcflags.emc.gs",
            "-Daikars.new.flags=true",
            *self.config.extra_args,
            "-jar",
            str(self.config.jar_path.name),
            "nogui",
        ]
        return cmd

    async def start(self) -> bool:
        """
        Start the server process.

        Returns:
            True if started successfully, False if already running
        """
        if self.is_running:
            return False

        # Ensure working directory exists
        self.config.working_dir.mkdir(parents=True, exist_ok=True)

        cmd = self._build_command()
        logger.info("Starting process: %s", " ".join(cmd[:3]) + " ...")
        logger.info("Working directory: %s", self.config.working_dir)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.working_dir,
                # Start in new process group for clean shutdown
                start_new_session=True,
            )

            self._state = ProcessState(
                is_running=True,
                pid=self._process.pid,
                started_at=datetime.now(),
            )

            logger.info("Process started with PID: %s", self._process.pid)

            # Start reading stdout/stderr
            self._reader_task = asyncio.create_task(self._read_output())

            return True

        except Exception as e:
            logger.error("Failed to start process: %s", e)
            self._state = ProcessState(is_running=False)
            raise RuntimeError(f"Failed to start server: {e}") from e

    async def stop(self, timeout: float = 120.0) -> bool:
        """
        Stop the server gracefully.

        Sends 'stop' command first, then SIGTERM, then SIGKILL if needed.

        Args:
            timeout: Seconds to wait for graceful shutdown

        Returns:
            True if stopped, False if was not running
        """
        if not self.is_running or self._process is None:
            return False

        # First, try graceful shutdown via 'stop' command
        try:
            await self.send_command("stop")

            # Wait for process to exit
            try:
                await asyncio.wait_for(self._process.wait(), timeout=timeout)
                return True
            except TimeoutError:
                pass  # Continue to SIGTERM

        except Exception:
            pass  # Process might not be ready for commands

        # Try SIGTERM
        try:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
                return True
            except TimeoutError:
                pass  # Continue to SIGKILL
        except ProcessLookupError:
            return True  # Already dead

        # Force kill with SIGKILL
        try:
            self._process.kill()
            await self._process.wait()
        except ProcessLookupError:
            pass  # Already dead

        return True

    async def kill(self) -> None:
        """Force kill the process immediately."""
        if self._process:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
            finally:
                self._cleanup()

    async def restart(self, timeout: float = 30.0) -> bool:
        """Stop and start the server."""
        await self.stop(timeout)
        await asyncio.sleep(1)  # Brief pause
        return await self.start()

    async def send_command(self, command: str) -> bool:
        """
        Send a command to the server stdin.

        Args:
            command: Command to send (without newline)

        Returns:
            True if sent, False if not running
        """
        if not self.is_running or self._process is None or self._process.stdin is None:
            return False

        try:
            self._process.stdin.write(f"{command}\n".encode())
            await self._process.stdin.drain()
            return True
        except Exception:
            return False

    async def _read_output(self) -> None:
        """Read stdout and stderr, calling registered callbacks."""
        if self._process is None:
            return

        stderr_lines: list[str] = []

        async def read_stream(
            stream: asyncio.StreamReader | None,
            callbacks: list[Callable[[str], Any]],
            is_stderr: bool = False,
        ) -> None:
            if stream is None:
                return
            try:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    if is_stderr and decoded:
                        stderr_lines.append(decoded)
                        logger.warning("[STDERR] %s", decoded)
                    for callback in callbacks:
                        try:
                            result = callback(decoded)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            pass  # Don't let callback errors crash the reader
            except Exception:
                pass

        # Read both streams concurrently
        await asyncio.gather(
            read_stream(self._process.stdout, self._stdout_callbacks, is_stderr=False),
            read_stream(self._process.stderr, self._stderr_callbacks, is_stderr=True),
        )

        # Process has exited
        exit_code = await self._process.wait()
        self._state.exit_code = exit_code
        self._state.is_running = False

        logger.info("Process exited with code: %s", exit_code)
        if exit_code != 0 and stderr_lines:
            logger.error("Last stderr lines: %s", stderr_lines[-5:])

        # Call exit callbacks
        for callback in self._exit_callbacks:
            try:
                result = callback(exit_code)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up after process exit."""
        self._state.is_running = False
        self._process = None
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        self._reader_task = None
