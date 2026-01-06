"""Modrinth API client for searching and downloading mods."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx


@dataclass
class ModVersion:
    """A specific version of a mod."""

    id: str
    version_number: str
    name: str
    game_versions: list[str]
    loaders: list[str]
    download_url: str
    filename: str
    size_bytes: int
    date_published: datetime


@dataclass
class ModInfo:
    """Information about a mod from Modrinth."""

    id: str
    slug: str
    title: str
    description: str
    author: str
    downloads: int
    icon_url: str | None
    categories: list[str]
    game_versions: list[str]
    loaders: list[str]
    updated: datetime
    versions: list[str]  # Version IDs


class ModrinthAPI:
    """
    Modrinth API client.

    Modrinth is a modern mod hosting platform with a free, open API.
    No API key required.
    """

    BASE_URL = "https://api.modrinth.com/v2"
    USER_AGENT = "MinecraftServerManager/1.0 (github.com/yourusername/mcmanager)"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={"User-Agent": self.USER_AGENT},
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search_mods(
        self,
        query: str,
        loader: Literal["forge", "fabric", "quilt", "neoforge"] = "forge",
        game_version: str | None = None,
        limit: int = 10,
    ) -> list[ModInfo]:
        """
        Search for mods on Modrinth.

        Args:
            query: Search query
            loader: Mod loader type
            game_version: Minecraft version (e.g., "1.21.1")
            limit: Maximum results to return

        Returns:
            List of matching mods
        """
        client = await self._get_client()

        # Build facets for filtering
        facets = [
            ["project_type:mod"],
            [f"categories:{loader}"],
        ]
        if game_version:
            facets.append([f"versions:{game_version}"])

        params = {
            "query": query,
            "facets": str(facets).replace("'", '"'),
            "limit": limit,
        }

        response = await client.get("/search", params=params)
        response.raise_for_status()
        data = response.json()

        mods = []
        for hit in data.get("hits", []):
            try:
                mods.append(
                    ModInfo(
                        id=hit["project_id"],
                        slug=hit["slug"],
                        title=hit["title"],
                        description=hit.get("description", ""),
                        author=hit.get("author", "Unknown"),
                        downloads=hit.get("downloads", 0),
                        icon_url=hit.get("icon_url"),
                        categories=hit.get("categories", []),
                        game_versions=hit.get("versions", []),
                        loaders=hit.get("loaders", []),
                        updated=datetime.fromisoformat(hit["date_modified"].replace("Z", "+00:00")),
                        versions=hit.get("versions", []),
                    )
                )
            except (KeyError, ValueError):
                continue

        return mods

    async def get_mod(self, mod_id_or_slug: str) -> ModInfo | None:
        """
        Get detailed information about a mod.

        Args:
            mod_id_or_slug: Mod ID or slug

        Returns:
            ModInfo or None if not found
        """
        client = await self._get_client()

        try:
            response = await client.get(f"/project/{mod_id_or_slug}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()

            return ModInfo(
                id=data["id"],
                slug=data["slug"],
                title=data["title"],
                description=data.get("description", ""),
                author=data.get("team", "Unknown"),
                downloads=data.get("downloads", 0),
                icon_url=data.get("icon_url"),
                categories=data.get("categories", []),
                game_versions=data.get("game_versions", []),
                loaders=data.get("loaders", []),
                updated=datetime.fromisoformat(data["updated"].replace("Z", "+00:00")),
                versions=data.get("versions", []),
            )
        except httpx.HTTPStatusError:
            return None

    async def get_mod_versions(
        self,
        mod_id_or_slug: str,
        loader: str | None = None,
        game_version: str | None = None,
    ) -> list[ModVersion]:
        """
        Get available versions of a mod.

        Args:
            mod_id_or_slug: Mod ID or slug
            loader: Filter by loader (forge, fabric, etc.)
            game_version: Filter by Minecraft version

        Returns:
            List of mod versions (newest first)
        """
        client = await self._get_client()

        params = {}
        if loader:
            params["loaders"] = f'["{loader}"]'
        if game_version:
            params["game_versions"] = f'["{game_version}"]'

        response = await client.get(
            f"/project/{mod_id_or_slug}/version",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        versions = []
        for v in data:
            try:
                # Get primary file
                files = v.get("files", [])
                primary_file = next(
                    (f for f in files if f.get("primary", False)),
                    files[0] if files else None,
                )
                if not primary_file:
                    continue

                versions.append(
                    ModVersion(
                        id=v["id"],
                        version_number=v["version_number"],
                        name=v.get("name", v["version_number"]),
                        game_versions=v.get("game_versions", []),
                        loaders=v.get("loaders", []),
                        download_url=primary_file["url"],
                        filename=primary_file["filename"],
                        size_bytes=primary_file.get("size", 0),
                        date_published=datetime.fromisoformat(
                            v["date_published"].replace("Z", "+00:00")
                        ),
                    )
                )
            except (KeyError, ValueError, StopIteration):
                continue

        return versions

    async def get_compatible_version(
        self,
        mod_id_or_slug: str,
        loader: str,
        game_version: str,
    ) -> ModVersion | None:
        """
        Get the latest compatible version of a mod.

        Args:
            mod_id_or_slug: Mod ID or slug
            loader: Mod loader (forge, fabric, etc.)
            game_version: Minecraft version

        Returns:
            Latest compatible ModVersion or None
        """
        versions = await self.get_mod_versions(
            mod_id_or_slug,
            loader=loader,
            game_version=game_version,
        )
        return versions[0] if versions else None

    async def download_mod(
        self,
        version: ModVersion,
        destination: Path,
        on_progress: Callable[[Any], Any] | None = None,
    ) -> Path:
        """
        Download a mod version.

        Args:
            version: ModVersion to download
            destination: Directory to save to
            on_progress: Optional progress callback

        Returns:
            Path to downloaded file
        """
        client = await self._get_client()
        destination.mkdir(parents=True, exist_ok=True)
        file_path = destination / version.filename

        async with client.stream("GET", version.download_url) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", version.size_bytes))
            downloaded = 0

            with open(file_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)

                    if on_progress:
                        on_progress(downloaded, total_size)

        return file_path

    async def __aenter__(self) -> "ModrinthAPI":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        await self.close()
