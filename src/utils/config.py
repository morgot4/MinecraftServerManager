"""Configuration management using Pydantic Settings."""

import os
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""

    bot_token: str = ""
    admin_ids: list[int] = Field(default_factory=list)


class DefaultsConfig(BaseModel):
    """Default settings for new servers."""

    ram_min: str = "4G"
    ram_max: str = "10G"
    port: int = 25565
    java_path: str = "java"


class AutoShutdownConfig(BaseModel):
    """Auto-shutdown configuration."""

    enabled: bool = True
    empty_minutes: int = 30


class BackupsConfig(BaseModel):
    """Backup configuration."""

    auto_enabled: bool = True
    interval_hours: int = 3
    keep_count: int = 2
    backup_on_stop: bool = True


class NotificationsConfig(BaseModel):
    """Notification settings."""

    server_start: bool = True
    server_stop: bool = True
    player_join: bool = True
    player_leave: bool = True
    crash: bool = True


class PathsConfig(BaseModel):
    """File paths configuration."""

    servers_dir: Path = Path("./servers")
    backups_dir: Path = Path("./backups")
    database: Path = Path("./data/manager.db")

    @model_validator(mode="after")
    def resolve_paths(self) -> Self:
        """Convert relative paths to absolute."""
        base_dir = Path(__file__).parent.parent.parent
        if not self.servers_dir.is_absolute():
            self.servers_dir = (base_dir / self.servers_dir).resolve()
        if not self.backups_dir.is_absolute():
            self.backups_dir = (base_dir / self.backups_dir).resolve()
        if not self.database.is_absolute():
            self.database = (base_dir / self.database).resolve()
        return self


class Config(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    auto_shutdown: AutoShutdownConfig = Field(default_factory=AutoShutdownConfig)
    backups: BackupsConfig = Field(default_factory=BackupsConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    language: str = "ru"

    @model_validator(mode="after")
    def apply_env_token(self) -> Self:
        """Override bot_token from environment if set."""
        env_token = os.getenv("BOT_TOKEN")
        if env_token and not self.telegram.bot_token:
            self.telegram.bot_token = env_token
        return self


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file and environment."""
    if config_path is None:
        # Check environment variable first
        env_path = os.getenv("CONFIG_PATH")
        if env_path:
            config_path = Path(env_path)
        else:
            # Default to config.yaml in project root
            config_path = Path(__file__).parent.parent.parent / "config.yaml"

    config_data = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

        # Handle ${VAR} substitution in bot_token
        if "telegram" in config_data and "bot_token" in config_data["telegram"]:
            token = config_data["telegram"]["bot_token"]
            if isinstance(token, str) and token.startswith("${") and token.endswith("}"):
                env_var = token[2:-1]
                config_data["telegram"]["bot_token"] = os.getenv(env_var, "")

    return Config(**config_data)


_config: Config | None = None


def get_config() -> Config:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
