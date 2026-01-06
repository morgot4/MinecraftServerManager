"""Forge Minecraft server engine."""

import asyncio
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from src.engines.base import BaseEngine, DownloadProgress, VersionInfo


class ForgeEngine(BaseEngine):
    """
    Forge modded server engine.

    Downloads and installs Forge server using the official installer.
    """

    # Forge Maven repository
    FORGE_MAVEN_URL = "https://maven.minecraftforge.net"
    FORGE_PROMOTIONS_URL = f"{FORGE_MAVEN_URL}/promotions_slim.json"
    FORGE_VERSIONS_URL = f"{FORGE_MAVEN_URL}/net/minecraftforge/forge/maven-metadata.xml"

    def __init__(self):
        self._promotions_cache: dict | None = None
        self._versions_cache: list[str] | None = None

    @property
    def name(self) -> str:
        return "forge"

    @property
    def display_name(self) -> str:
        return "Forge"

    async def _fetch_promotions(self) -> dict:
        """Fetch Forge promotions (recommended/latest versions)."""
        if self._promotions_cache:
            return self._promotions_cache

        async with httpx.AsyncClient() as client:
            response = await client.get(self.FORGE_PROMOTIONS_URL, timeout=30.0)
            response.raise_for_status()
            self._promotions_cache = response.json()
            return self._promotions_cache

    async def _fetch_forge_versions(self) -> list[str]:
        """Fetch all available Forge versions from Maven."""
        if self._versions_cache:
            return self._versions_cache

        async with httpx.AsyncClient() as client:
            response = await client.get(self.FORGE_VERSIONS_URL, timeout=30.0)
            response.raise_for_status()

            # Parse XML to get versions
            # Format: <version>1.21.1-52.0.3</version>
            content = response.text
            versions = re.findall(r"<version>([^<]+)</version>", content)
            self._versions_cache = versions
            return versions

    def _parse_forge_version(self, forge_version: str) -> tuple[str, str]:
        """
        Parse Forge version string into MC version and Forge version.

        Example: "1.21.1-52.0.3" -> ("1.21.1", "52.0.3")
        """
        parts = forge_version.split("-", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return forge_version, ""

    async def get_versions(
        self,
        include_snapshots: bool = False,
    ) -> list[VersionInfo]:
        """Get available Forge versions."""
        forge_versions = await self._fetch_forge_versions()
        promotions = await self._fetch_promotions()
        promos = promotions.get("promos", {})

        # Group by MC version and get the latest Forge for each
        mc_versions: dict[str, str] = {}
        for fv in forge_versions:
            mc_ver, forge_ver = self._parse_forge_version(fv)
            # Skip old versions and snapshots (if not requested)
            if not include_snapshots:
                # Skip pre-1.12 and snapshot versions
                if mc_ver.startswith("1.") and mc_ver.split(".")[1].isdigit():
                    minor = int(mc_ver.split(".")[1])
                    if minor < 12:
                        continue

            if mc_ver not in mc_versions:
                mc_versions[mc_ver] = fv

        # Convert to VersionInfo
        versions = []
        for mc_ver, forge_full in mc_versions.items():
            # Check if this is a recommended version
            recommended_key = f"{mc_ver}-recommended"
            latest_key = f"{mc_ver}-latest"

            release_type = "release"
            if recommended_key in promos:
                release_type = "release"
            elif latest_key in promos:
                release_type = "snapshot"

            versions.append(
                VersionInfo(
                    version=forge_full,
                    release_type=release_type,
                    release_date=datetime.now(),  # Forge doesn't provide dates
                    url=None,
                )
            )

        # Sort by version (newest first)
        versions.sort(key=lambda v: v.version, reverse=True)
        return versions

    async def get_latest_version(self, stable_only: bool = True) -> VersionInfo | None:
        """Get the latest Forge version."""
        versions = await self.get_versions()
        if versions:
            if stable_only:
                # Find first release version
                for v in versions:
                    if v.release_type == "release":
                        return v
            return versions[0]
        return None

    async def get_recommended_for_mc(self, mc_version: str) -> str | None:
        """
        Get recommended Forge version for a specific MC version.

        Args:
            mc_version: Minecraft version (e.g., "1.21.1")

        Returns:
            Full Forge version string or None
        """
        promotions = await self._fetch_promotions()
        promos = promotions.get("promos", {})

        # Try recommended first, then latest
        for suffix in ["recommended", "latest"]:
            key = f"{mc_version}-{suffix}"
            if key in promos:
                forge_ver = promos[key]
                return f"{mc_version}-{forge_ver}"

        return None

    def _get_installer_url(self, forge_version: str) -> str:
        """Get URL for Forge installer JAR."""
        return (
            f"{self.FORGE_MAVEN_URL}/net/minecraftforge/forge/"
            f"{forge_version}/forge-{forge_version}-installer.jar"
        )

    async def download_server(
        self,
        version: str,
        destination: Path,
        on_progress: Callable[[Any], Any] | None = None,
    ) -> Path:
        """
        Download Forge installer and run it to create server.

        Note: Forge requires running the installer JAR to generate
        the actual server files. This needs Java to be installed.
        """
        destination.mkdir(parents=True, exist_ok=True)

        installer_url = self._get_installer_url(version)
        installer_path = destination / f"forge-{version}-installer.jar"

        # Download installer
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", installer_url, timeout=300.0) as response:
                if response.status_code == 404:
                    raise ValueError(f"Forge version not found: {version}")
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(installer_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)

                        if on_progress:
                            on_progress(
                                DownloadProgress(
                                    total_bytes=total_size,
                                    downloaded_bytes=downloaded,
                                    filename="forge-installer.jar",
                                )
                            )

        # Run installer to generate server files
        await self._run_installer(installer_path, destination)

        # Find the generated server JAR or run script
        server_jar = self._find_server_jar(destination, version)

        # Clean up installer
        installer_path.unlink(missing_ok=True)

        return server_jar

    async def _run_installer(self, installer_path: Path, destination: Path) -> None:
        """Run Forge installer in server mode."""
        process = await asyncio.create_subprocess_exec(
            "java",
            "-jar",
            str(installer_path),
            "--installServer",
            cwd=destination,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=300.0,  # 5 minutes max
        )

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Forge installer failed: {error_msg}")

    def _find_server_jar(self, destination: Path, version: str) -> Path:
        """Find the server JAR after installation."""
        # Modern Forge (1.17+) uses run scripts and libraries
        # Check for various possible server JARs

        possible_names = [
            f"forge-{version}-server.jar",
            f"forge-{version}.jar",
            "server.jar",
            "minecraft_server.*.jar",
        ]

        for name in possible_names:
            matches = list(destination.glob(name))
            if matches:
                # Rename to server.jar for consistency
                target = destination / "server.jar"
                if matches[0] != target:
                    matches[0].rename(target)
                return target

        # Check for run.sh (modern Forge)
        run_sh = destination / "run.sh"
        if run_sh.exists():
            # Modern Forge uses libraries, create a wrapper
            return run_sh

        raise RuntimeError("Could not find server JAR after Forge installation")

    async def setup_server(
        self,
        version: str,
        server_path: Path,
        on_progress: Callable[[Any], Any] | None = None,
    ) -> None:
        """Set up a new Forge server."""
        server_path.mkdir(parents=True, exist_ok=True)

        # Download and install Forge
        await self.download_server(version, server_path, on_progress)

        # Accept EULA
        await self.accept_eula(server_path)

        # Create mods folder
        mods_path = server_path / "mods"
        mods_path.mkdir(exist_ok=True)
