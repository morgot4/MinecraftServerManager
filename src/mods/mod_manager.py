"""Mod manager for installing and managing mods."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.mods.modrinth_api import ModInfo, ModrinthAPI, ModVersion
from src.storage.models import EngineType


@dataclass
class InstalledMod:
    """Information about an installed mod."""

    slug: str
    title: str
    filename: str
    version: str
    modrinth_id: str
    installed_at: datetime = field(default_factory=datetime.now)


class ModManager:
    """
    Manages mod installation and removal for a server.

    Only works with modded server engines (Forge, Fabric).
    """

    INSTALLED_MODS_FILE = "installed_mods.json"

    def __init__(self, server_path: Path, engine: EngineType):
        """
        Initialize mod manager.

        Args:
            server_path: Path to server directory
            engine: Server engine type
        """
        self.server_path = server_path
        self.engine = engine
        self.mods_path = server_path / "mods"
        self._api = ModrinthAPI()
        self._installed: list[InstalledMod] | None = None

    @property
    def loader(self) -> str:
        """Get loader name for API queries."""
        if self.engine == EngineType.FORGE:
            return "forge"
        # Add more mappings as engines are added
        return "forge"

    @property
    def is_modded_server(self) -> bool:
        """Check if server supports mods."""
        return self.engine in (EngineType.FORGE,)

    def _installed_mods_path(self) -> Path:
        """Get path to installed mods tracking file."""
        return self.server_path / self.INSTALLED_MODS_FILE

    def load_installed_mods(self) -> list[InstalledMod]:
        """Load list of installed mods from tracking file."""
        if self._installed is not None:
            return self._installed

        path = self._installed_mods_path()
        if not path.exists():
            self._installed = []
            return self._installed

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                self._installed = [
                    InstalledMod(
                        slug=m["slug"],
                        title=m["title"],
                        filename=m["filename"],
                        version=m["version"],
                        modrinth_id=m["modrinth_id"],
                        installed_at=datetime.fromisoformat(m["installed_at"]),
                    )
                    for m in data
                ]
        except (json.JSONDecodeError, KeyError):
            self._installed = []

        return self._installed

    def save_installed_mods(self) -> None:
        """Save installed mods tracking file."""
        if self._installed is None:
            return

        data = [
            {
                "slug": m.slug,
                "title": m.title,
                "filename": m.filename,
                "version": m.version,
                "modrinth_id": m.modrinth_id,
                "installed_at": m.installed_at.isoformat(),
            }
            for m in self._installed
        ]

        with open(self._installed_mods_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    async def search_mods(
        self,
        query: str,
        game_version: str,
        limit: int = 10,
    ) -> list[ModInfo]:
        """
        Search for mods compatible with this server.

        Args:
            query: Search query
            game_version: Minecraft version
            limit: Max results

        Returns:
            List of matching mods
        """
        return await self._api.search_mods(
            query=query,
            loader=self.loader,
            game_version=game_version,
            limit=limit,
        )

    async def install_mod(
        self,
        mod_id_or_slug: str,
        game_version: str,
        on_progress: Callable[[Any], Any] | None = None,
    ) -> InstalledMod:
        """
        Install a mod from Modrinth.

        Args:
            mod_id_or_slug: Mod ID or slug
            game_version: Minecraft version
            on_progress: Optional progress callback

        Returns:
            InstalledMod record

        Raises:
            ValueError: If mod not found or not compatible
            RuntimeError: If download fails
        """
        if not self.is_modded_server:
            raise RuntimeError("This server type doesn't support mods")

        # Ensure mods directory exists
        self.mods_path.mkdir(parents=True, exist_ok=True)

        # Get mod info
        mod_info = await self._api.get_mod(mod_id_or_slug)
        if not mod_info:
            raise ValueError(f"Mod not found: {mod_id_or_slug}")

        # Get compatible version
        version = await self._api.get_compatible_version(
            mod_id_or_slug,
            loader=self.loader,
            game_version=game_version,
        )
        if not version:
            raise ValueError(
                f"No compatible version of {mod_info.title} for " f"{self.loader} {game_version}"
            )

        # Check if already installed
        installed = self.load_installed_mods()
        existing = next((m for m in installed if m.slug == mod_info.slug), None)
        if existing:
            # Remove old version first
            old_path = self.mods_path / existing.filename
            if old_path.exists():
                old_path.unlink()
            installed.remove(existing)

        # Download mod
        await self._api.download_mod(version, self.mods_path, on_progress)

        # Track installation
        installed_mod = InstalledMod(
            slug=mod_info.slug,
            title=mod_info.title,
            filename=version.filename,
            version=version.version_number,
            modrinth_id=mod_info.id,
        )
        installed.append(installed_mod)
        self._installed = installed
        self.save_installed_mods()

        return installed_mod

    async def remove_mod(self, slug_or_title: str) -> bool:
        """
        Remove an installed mod.

        Args:
            slug_or_title: Mod slug or title

        Returns:
            True if removed, False if not found
        """
        installed = self.load_installed_mods()

        # Find mod by slug or title (case-insensitive)
        search = slug_or_title.lower()
        mod = next(
            (m for m in installed if m.slug.lower() == search or m.title.lower() == search),
            None,
        )

        if not mod:
            return False

        # Delete file
        mod_path = self.mods_path / mod.filename
        if mod_path.exists():
            mod_path.unlink()

        # Update tracking
        installed.remove(mod)
        self._installed = installed
        self.save_installed_mods()

        return True

    def get_installed_mods(self) -> list[InstalledMod]:
        """Get list of installed mods."""
        return self.load_installed_mods()

    def is_mod_installed(self, slug: str) -> bool:
        """Check if a mod is installed."""
        installed = self.load_installed_mods()
        return any(m.slug.lower() == slug.lower() for m in installed)

    async def check_updates(
        self,
        game_version: str,
    ) -> list[tuple[InstalledMod, ModVersion]]:
        """
        Check for mod updates.

        Args:
            game_version: Current Minecraft version

        Returns:
            List of (installed_mod, new_version) tuples
        """
        updates = []
        installed = self.load_installed_mods()

        for mod in installed:
            try:
                latest = await self._api.get_compatible_version(
                    mod.modrinth_id,
                    loader=self.loader,
                    game_version=game_version,
                )
                if latest and latest.version_number != mod.version:
                    updates.append((mod, latest))
            except Exception:
                continue

        return updates

    async def close(self) -> None:
        """Close API client."""
        await self._api.close()

    async def __aenter__(self) -> "ModManager":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
