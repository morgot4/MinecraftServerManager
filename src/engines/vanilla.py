"""Vanilla Minecraft server engine using Mojang API."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from src.engines.base import BaseEngine, DownloadProgress, VersionInfo


class VanillaEngine(BaseEngine):
    """
    Vanilla Minecraft server engine.

    Uses official Mojang API to fetch versions and download server JARs.
    """

    VERSION_MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest.json"

    def __init__(self):
        self._version_cache: list[VersionInfo] | None = None
        self._manifest_cache: dict | None = None

    @property
    def name(self) -> str:
        return "vanilla"

    @property
    def display_name(self) -> str:
        return "Vanilla"

    async def _fetch_manifest(self) -> dict:
        """Fetch version manifest from Mojang."""
        if self._manifest_cache:
            return self._manifest_cache

        async with httpx.AsyncClient() as client:
            response = await client.get(self.VERSION_MANIFEST_URL, timeout=30.0)
            response.raise_for_status()
            self._manifest_cache = response.json()
            return self._manifest_cache

    async def get_versions(
        self,
        include_snapshots: bool = False,
    ) -> list[VersionInfo]:
        """Get available Vanilla versions from Mojang API."""
        manifest = await self._fetch_manifest()

        versions = []
        for version_data in manifest.get("versions", []):
            release_type = version_data.get("type", "release")

            # Filter snapshots if not requested
            if not include_snapshots and release_type != "release":
                continue

            try:
                release_date = datetime.fromisoformat(
                    version_data["releaseTime"].replace("Z", "+00:00")
                )
            except (ValueError, KeyError):
                release_date = datetime.now()

            versions.append(
                VersionInfo(
                    version=version_data["id"],
                    release_type=release_type,
                    release_date=release_date,
                    url=version_data.get("url"),
                )
            )

        return versions

    async def get_latest_version(self, stable_only: bool = True) -> VersionInfo | None:
        """Get the latest Vanilla version."""
        manifest = await self._fetch_manifest()
        latest = manifest.get("latest", {})

        target = "release" if stable_only else "snapshot"
        version_id = latest.get(target)

        if not version_id:
            return None

        versions = await self.get_versions(include_snapshots=not stable_only)
        for version in versions:
            if version.version == version_id:
                return version

        return None

    async def _get_version_details(self, version: str) -> dict:
        """Get detailed version info including download URLs."""
        versions = await self.get_versions(include_snapshots=True)

        version_info = None
        for v in versions:
            if v.version == version:
                version_info = v
                break

        if not version_info or not version_info.url:
            raise ValueError(f"Version not found: {version}")

        async with httpx.AsyncClient() as client:
            response = await client.get(version_info.url, timeout=30.0)
            response.raise_for_status()
            return response.json()

    async def download_server(
        self,
        version: str,
        destination: Path,
        on_progress: Callable[[Any], Any] | None = None,
    ) -> Path:
        """Download Vanilla server JAR from Mojang."""
        # Get version details for download URL
        details = await self._get_version_details(version)

        server_info = details.get("downloads", {}).get("server")
        if not server_info:
            raise ValueError(f"No server download available for {version}")

        download_url = server_info["url"]
        expected_size = server_info.get("size", 0)

        # Prepare destination
        destination.mkdir(parents=True, exist_ok=True)
        jar_path = destination / "server.jar"

        # Download with progress
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", download_url, timeout=300.0) as response:
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", expected_size))
                downloaded = 0

                with open(jar_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)

                        if on_progress:
                            on_progress(
                                DownloadProgress(
                                    total_bytes=total_size,
                                    downloaded_bytes=downloaded,
                                    filename="server.jar",
                                )
                            )

        return jar_path

    async def setup_server(
        self,
        version: str,
        server_path: Path,
        on_progress: Callable[[Any], Any] | None = None,
    ) -> None:
        """Set up a new Vanilla server."""
        # Create directory
        server_path.mkdir(parents=True, exist_ok=True)

        # Download server JAR
        await self.download_server(version, server_path, on_progress)

        # Accept EULA
        await self.accept_eula(server_path)
