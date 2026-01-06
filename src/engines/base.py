"""Base engine interface for Minecraft server types."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


@dataclass
class VersionInfo:
    """Information about a Minecraft version."""

    version: str
    release_type: Literal["release", "snapshot", "old_beta", "old_alpha"]
    release_date: datetime
    url: str | None = None  # Download URL if available


@dataclass
class DownloadProgress:
    """Progress information for downloads."""

    total_bytes: int
    downloaded_bytes: int
    filename: str

    @property
    def percent(self) -> float:
        """Get download progress as percentage."""
        if self.total_bytes == 0:
            return 0
        return (self.downloaded_bytes / self.total_bytes) * 100


class BaseEngine(ABC):
    """
    Abstract base class for Minecraft server engines.

    Each engine type (Vanilla, Forge, Fabric, etc.) implements this interface
    to provide version listing and server downloading functionality.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine name (e.g., 'vanilla', 'forge')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable engine name."""
        ...

    @abstractmethod
    async def get_versions(
        self,
        include_snapshots: bool = False,
    ) -> list[VersionInfo]:
        """
        Get available versions for this engine.

        Args:
            include_snapshots: Include snapshot/development versions

        Returns:
            List of available versions (newest first)
        """
        ...

    @abstractmethod
    async def get_latest_version(self, stable_only: bool = True) -> VersionInfo | None:
        """
        Get the latest available version.

        Args:
            stable_only: Only consider stable releases

        Returns:
            Latest version info or None if unavailable
        """
        ...

    @abstractmethod
    async def download_server(
        self,
        version: str,
        destination: Path,
        on_progress: Callable[[Any], Any] | None = None,
    ) -> Path:
        """
        Download server JAR for specified version.

        Args:
            version: Version string (e.g., "1.21.1")
            destination: Directory to download to
            on_progress: Optional callback(DownloadProgress)

        Returns:
            Path to downloaded server.jar

        Raises:
            ValueError: If version not found
            RuntimeError: If download fails
        """
        ...

    @abstractmethod
    async def setup_server(
        self,
        version: str,
        server_path: Path,
        on_progress: Callable[[Any], Any] | None = None,
    ) -> None:
        """
        Full setup of a new server.

        Downloads server JAR, creates necessary files, accepts EULA.

        Args:
            version: Version string
            server_path: Directory for the server
            on_progress: Optional progress callback
        """
        ...

    async def accept_eula(self, server_path: Path) -> None:
        """Accept Minecraft EULA by creating eula.txt."""
        eula_path = server_path / "eula.txt"
        eula_path.write_text("eula=true\n", encoding="utf-8")

    def is_version_valid(self, version: str, versions: list[VersionInfo]) -> bool:
        """Check if a version string is valid."""
        return any(v.version == version for v in versions)
