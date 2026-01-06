"""Scanner for discovering existing Minecraft servers."""

import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.minecraft.server_properties import ServerProperties
from src.storage.models import EngineType, Server

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredServer:
    """Information about a discovered server."""

    name: str
    path: Path
    engine: EngineType
    mc_version: str
    port: int
    rcon_port: int
    rcon_password: str
    has_world: bool
    needs_rcon_setup: bool


class ServerScanner:
    """
    Scanner for discovering existing Minecraft servers.

    Scans the servers directory for folders containing server.jar
    that are not yet registered in the database.
    """

    def __init__(self, servers_dir: Path):
        self.servers_dir = servers_dir

    def scan_for_servers(self, known_names: list[str]) -> list[DiscoveredServer]:
        """
        Scan for servers not in the known list.

        Args:
            known_names: List of server names already in database

        Returns:
            List of discovered servers
        """
        discovered = []

        if not self.servers_dir.exists():
            return discovered

        for folder in self.servers_dir.iterdir():
            if not folder.is_dir():
                continue

            if folder.name in known_names:
                continue

            # Check for server.jar
            server_jar = folder / "server.jar"
            if not server_jar.exists():
                # Also check for forge-style jars
                forge_jars = list(folder.glob("forge-*.jar")) + list(folder.glob("*-forge-*.jar"))
                if not forge_jars:
                    continue

            server = self._analyze_server(folder)
            if server:
                discovered.append(server)
                logger.info(f"Discovered server: {server.name} ({server.engine.value} {server.mc_version})")

        return discovered

    def _analyze_server(self, path: Path) -> DiscoveredServer | None:
        """
        Analyze a server folder to extract configuration.

        Args:
            path: Path to server folder

        Returns:
            DiscoveredServer or None if analysis failed
        """
        name = path.name

        # Determine engine type
        engine = self._detect_engine(path)

        # Get Minecraft version
        mc_version = self._detect_version(path)

        # Load server.properties
        props_path = path / "server.properties"
        port = 25565
        rcon_port = 25575
        rcon_password = ""
        needs_rcon_setup = True

        if props_path.exists():
            props = ServerProperties(props_path)
            props.load()

            port = props.get("server-port", 25565)
            rcon_port = props.get("rcon.port", 25575)
            rcon_password = props.get_raw("rcon.password") or ""

            # Check if RCON is properly configured
            rcon_enabled = props.get("enable-rcon", False)
            if rcon_enabled and rcon_password:
                needs_rcon_setup = False

        # Check if world exists
        has_world = (path / "world").exists()

        return DiscoveredServer(
            name=name,
            path=path,
            engine=engine,
            mc_version=mc_version,
            port=port,
            rcon_port=rcon_port,
            rcon_password=rcon_password,
            has_world=has_world,
            needs_rcon_setup=needs_rcon_setup,
        )

    def _detect_engine(self, path: Path) -> EngineType:
        """Detect which engine the server uses."""
        # Check for Forge indicators
        forge_indicators = [
            path / "mods",
            path / "config",
            path / "libraries" / "net" / "minecraftforge",
        ]

        for indicator in forge_indicators:
            if indicator.exists():
                # Also check for forge jar
                forge_jars = list(path.glob("forge-*.jar")) + list(path.glob("*-forge-*.jar"))
                if forge_jars or (path / "mods").exists():
                    return EngineType.FORGE

        return EngineType.VANILLA

    def _detect_version(self, path: Path) -> str:
        """Detect Minecraft version from server files."""
        # Try version.json (vanilla)
        version_json = path / "version.json"
        if version_json.exists():
            try:
                with open(version_json, encoding="utf-8") as f:
                    data = json.load(f)
                    if "id" in data:
                        return data["id"]
            except (json.JSONDecodeError, KeyError):
                pass

        # Try to parse from forge jar name
        for jar in path.glob("forge-*.jar"):
            # Format: forge-<mc_version>-<forge_version>.jar
            try:
                name = jar.stem
                parts = name.split("-")
                if len(parts) >= 2:
                    return parts[1]
            except (IndexError, ValueError):
                pass

        # Try server.jar manifest (less reliable)
        # For now, return unknown
        return "unknown"

    def import_server(
        self,
        discovered: DiscoveredServer,
        ram_min: str = "2G",
        ram_max: str = "8G",
    ) -> Server:
        """
        Import a discovered server into the database format.

        Args:
            discovered: Discovered server info
            ram_min: Minimum RAM allocation
            ram_max: Maximum RAM allocation

        Returns:
            Server model ready to save to database
        """
        # Generate RCON password if needed
        rcon_password = discovered.rcon_password
        if discovered.needs_rcon_setup:
            rcon_password = secrets.token_urlsafe(16)

            # Update server.properties with RCON settings
            props_path = discovered.path / "server.properties"
            props = ServerProperties(props_path)
            if props_path.exists():
                props.load()

            props.update_for_manager(
                rcon_port=discovered.rcon_port,
                rcon_password=rcon_password,
                server_port=discovered.port,
            )
            props.save()
            logger.info(f"Updated server.properties with RCON settings for {discovered.name}")

        return Server(
            id=str(uuid.uuid4()),
            name=discovered.name,
            engine=discovered.engine,
            mc_version=discovered.mc_version,
            path=discovered.path,
            port=discovered.port,
            ram_min=ram_min,
            ram_max=ram_max,
            rcon_port=discovered.rcon_port,
            rcon_password=rcon_password,
            is_active=False,
            created_at=datetime.now(),
        )


def format_discovered_server(server: DiscoveredServer, lang: str = "ru") -> str:
    """Format discovered server info for display."""
    engine_icon = "🔧" if server.engine == EngineType.FORGE else "📦"
    world_icon = "🌍" if server.has_world else "🆕"
    rcon_icon = "✅" if not server.needs_rcon_setup else "⚠️"

    return (
        f"{engine_icon} **{server.name}**\n"
        f"   Версия: {server.mc_version}\n"
        f"   Движок: {server.engine.value}\n"
        f"   Порт: {server.port}\n"
        f"   {world_icon} Мир: {'есть' if server.has_world else 'новый'}\n"
        f"   {rcon_icon} RCON: {'настроен' if not server.needs_rcon_setup else 'будет настроен'}"
    )

