"""Whitelist and operators management."""

import json
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class MinecraftPlayer:
    """Minecraft player information."""

    name: str
    uuid: str


@dataclass
class WhitelistEntry:
    """Entry in whitelist.json."""

    uuid: str
    name: str


@dataclass
class OpsEntry:
    """Entry in ops.json."""

    uuid: str
    name: str
    level: int = 4  # 1-4, 4 is highest
    bypassesPlayerLimit: bool = False


class WhitelistManager:
    """
    Manages whitelist.json and ops.json files.

    Also provides player UUID lookup via Mojang API.
    """

    MOJANG_API_URL = "https://api.mojang.com/users/profiles/minecraft/{username}"

    def __init__(self, server_path: Path):
        """
        Initialize whitelist manager.

        Args:
            server_path: Path to server directory
        """
        self.server_path = server_path
        self.whitelist_path = server_path / "whitelist.json"
        self.ops_path = server_path / "ops.json"
        self._uuid_cache: dict[str, str] = {}

    # === UUID Lookup ===

    async def get_player_uuid(self, username: str) -> str | None:
        """
        Get player UUID from Mojang API.

        Args:
            username: Minecraft username

        Returns:
            UUID string or None if not found
        """
        # Check cache first
        if username.lower() in self._uuid_cache:
            return self._uuid_cache[username.lower()]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.MOJANG_API_URL.format(username=username),
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    # Format UUID with dashes
                    raw_uuid = data["id"]
                    formatted_uuid = f"{raw_uuid[:8]}-{raw_uuid[8:12]}-{raw_uuid[12:16]}-{raw_uuid[16:20]}-{raw_uuid[20:]}"
                    self._uuid_cache[username.lower()] = formatted_uuid
                    return formatted_uuid

        except Exception:
            pass

        return None

    # === Whitelist Operations ===

    def load_whitelist(self) -> list[WhitelistEntry]:
        """Load whitelist from file."""
        if not self.whitelist_path.exists():
            return []

        try:
            with open(self.whitelist_path, encoding="utf-8") as f:
                data = json.load(f)
                return [WhitelistEntry(**entry) for entry in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def save_whitelist(self, entries: list[WhitelistEntry]) -> None:
        """Save whitelist to file."""
        data = [{"uuid": e.uuid, "name": e.name} for e in entries]
        with open(self.whitelist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    async def add_to_whitelist(self, username: str) -> bool:
        """
        Add player to whitelist.

        Args:
            username: Player username

        Returns:
            True if added, False if already exists or UUID not found
        """
        entries = self.load_whitelist()

        # Check if already exists
        if any(e.name.lower() == username.lower() for e in entries):
            return False

        # Get UUID
        player_uuid = await self.get_player_uuid(username)
        if not player_uuid:
            return False

        entries.append(WhitelistEntry(uuid=player_uuid, name=username))
        self.save_whitelist(entries)
        return True

    def remove_from_whitelist(self, username: str) -> bool:
        """
        Remove player from whitelist.

        Args:
            username: Player username

        Returns:
            True if removed, False if not found
        """
        entries = self.load_whitelist()
        original_len = len(entries)
        entries = [e for e in entries if e.name.lower() != username.lower()]

        if len(entries) == original_len:
            return False

        self.save_whitelist(entries)
        return True

    def is_whitelisted(self, username: str) -> bool:
        """Check if player is whitelisted."""
        entries = self.load_whitelist()
        return any(e.name.lower() == username.lower() for e in entries)

    def get_whitelist_names(self) -> list[str]:
        """Get list of whitelisted player names."""
        return [e.name for e in self.load_whitelist()]

    # === Operators Operations ===

    def load_ops(self) -> list[OpsEntry]:
        """Load operators from file."""
        if not self.ops_path.exists():
            return []

        try:
            with open(self.ops_path, encoding="utf-8") as f:
                data = json.load(f)
                return [
                    OpsEntry(
                        uuid=entry["uuid"],
                        name=entry["name"],
                        level=entry.get("level", 4),
                        bypassesPlayerLimit=entry.get("bypassesPlayerLimit", False),
                    )
                    for entry in data
                ]
        except (json.JSONDecodeError, KeyError):
            return []

    def save_ops(self, entries: list[OpsEntry]) -> None:
        """Save operators to file."""
        data = [
            {
                "uuid": e.uuid,
                "name": e.name,
                "level": e.level,
                "bypassesPlayerLimit": e.bypassesPlayerLimit,
            }
            for e in entries
        ]
        with open(self.ops_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    async def add_op(self, username: str, level: int = 4) -> bool:
        """
        Add player as operator.

        Args:
            username: Player username
            level: Op level (1-4)

        Returns:
            True if added, False if already op or UUID not found
        """
        entries = self.load_ops()

        # Check if already op
        if any(e.name.lower() == username.lower() for e in entries):
            return False

        # Get UUID
        player_uuid = await self.get_player_uuid(username)
        if not player_uuid:
            return False

        entries.append(OpsEntry(uuid=player_uuid, name=username, level=level))
        self.save_ops(entries)
        return True

    def remove_op(self, username: str) -> bool:
        """
        Remove operator status.

        Args:
            username: Player username

        Returns:
            True if removed, False if not found
        """
        entries = self.load_ops()
        original_len = len(entries)
        entries = [e for e in entries if e.name.lower() != username.lower()]

        if len(entries) == original_len:
            return False

        self.save_ops(entries)
        return True

    def is_op(self, username: str) -> bool:
        """Check if player is operator."""
        entries = self.load_ops()
        return any(e.name.lower() == username.lower() for e in entries)

    def get_ops_names(self) -> list[str]:
        """Get list of operator names."""
        return [e.name for e in self.load_ops()]
