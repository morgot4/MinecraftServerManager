"""Data models using Pydantic."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """
    User role levels for access control.

    Hierarchy (higher = more permissions):
    - OWNER (100): Create servers, assign roles, full control
    - ADMIN (75): All server commands (whitelist, backup, mods, settings, RCON)
    - OPERATOR (50): Start/stop/restart server (for trusted friends)
    - PLAYER (10): View status only (default for everyone)
    """

    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    PLAYER = "player"

    @property
    def level(self) -> int:
        """Get numeric level for role comparison."""
        levels = {
            UserRole.OWNER: 100,
            UserRole.ADMIN: 75,
            UserRole.OPERATOR: 50,
            UserRole.PLAYER: 10,
        }
        return levels.get(self, 0)


class EngineType(str, Enum):
    """Supported Minecraft server engines."""

    VANILLA = "vanilla"
    FORGE = "forge"
    # Future: FABRIC = "fabric", PAPER = "paper"


class User(BaseModel):
    """Telegram user with role assignment."""

    telegram_id: int
    username: str | None = None
    role: UserRole = UserRole.PLAYER
    language: Literal["ru", "en"] = "ru"
    created_at: datetime = Field(default_factory=datetime.now)

    def has_role(self, min_role: UserRole) -> bool:
        """Check if user has at least the specified role level."""
        return self.role.level >= min_role.level

    def is_owner(self) -> bool:
        """Check if user has owner role."""
        return self.role == UserRole.OWNER

    def is_admin(self) -> bool:
        """Check if user has admin or higher role."""
        return self.has_role(UserRole.ADMIN)

    def is_operator(self) -> bool:
        """Check if user has operator or higher role."""
        return self.has_role(UserRole.OPERATOR)

    def can_view(self) -> bool:
        """Check if user can view server status (all users)."""
        return True

    def can_control_server(self) -> bool:
        """Check if user can start/stop/restart server."""
        return self.has_role(UserRole.OPERATOR)

    def can_manage_server(self) -> bool:
        """Check if user can manage whitelist, backups, mods, settings."""
        return self.has_role(UserRole.ADMIN)

    def can_create_servers(self) -> bool:
        """Check if user can create new servers and assign roles."""
        return self.has_role(UserRole.OWNER)


class Server(BaseModel):
    """Minecraft server configuration."""

    id: str  # UUID
    name: str
    engine: EngineType = EngineType.VANILLA
    mc_version: str
    path: Path
    port: int = 25565
    ram_min: str = "2G"
    ram_max: str = "8G"
    rcon_port: int = 25575
    rcon_password: str = ""
    is_active: bool = False  # Currently selected server
    created_at: datetime = Field(default_factory=datetime.now)
    last_started_at: datetime | None = None

    @property
    def jar_path(self) -> Path:
        """Get path to server JAR file."""
        return self.path / "server.jar"

    @property
    def world_path(self) -> Path:
        """Get path to world folder."""
        return self.path / "world"

    @property
    def properties_path(self) -> Path:
        """Get path to server.properties file."""
        return self.path / "server.properties"

    @property
    def logs_path(self) -> Path:
        """Get path to logs folder."""
        return self.path / "logs"

    @property
    def mods_path(self) -> Path:
        """Get path to mods folder (for Forge/Fabric)."""
        return self.path / "mods"


class ServerStatus(BaseModel):
    """Current status of a running server."""

    is_running: bool = False
    players_online: int = 0
    players_max: int = 20
    players_list: list[str] = Field(default_factory=list)
    uptime_seconds: int | None = None
    memory_used_mb: int | None = None
    tps: float | None = None  # Ticks per second (if available)
    mc_version: str | None = None


class BackupType(str, Enum):
    """Type of backup."""

    AUTO = "auto"
    MANUAL = "manual"
    PRE_SHUTDOWN = "pre_shutdown"


class Backup(BaseModel):
    """Backup record."""

    id: str  # UUID
    server_id: str
    filename: str
    size_bytes: int
    backup_type: BackupType
    created_at: datetime = Field(default_factory=datetime.now)


class PlayerEvent(BaseModel):
    """Player join/leave event from log parsing."""

    player_name: str
    event_type: Literal["join", "leave"]
    timestamp: datetime = Field(default_factory=datetime.now)


class ServerEvent(BaseModel):
    """Server event from log parsing."""

    event_type: Literal["started", "stopped", "crashed", "saved"]
    message: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
