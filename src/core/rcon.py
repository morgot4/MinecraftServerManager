"""RCON (Remote Console) client for Minecraft server commands."""

import asyncio
import struct
from dataclasses import dataclass
from enum import IntEnum


class PacketType(IntEnum):
    """RCON packet types."""

    COMMAND = 2
    AUTH = 3
    RESPONSE = 0


@dataclass
class RconPacket:
    """RCON protocol packet."""

    request_id: int
    packet_type: int
    payload: str

    def encode(self) -> bytes:
        """Encode packet to bytes for sending."""
        payload_bytes = self.payload.encode("utf-8") + b"\x00\x00"
        length = 4 + 4 + len(payload_bytes)  # request_id + type + payload
        return struct.pack("<iii", length, self.request_id, self.packet_type) + payload_bytes

    @classmethod
    def decode(cls, data: bytes) -> "RconPacket":
        """Decode packet from received bytes."""
        if len(data) < 14:
            raise ValueError("Packet too short")

        length, request_id, packet_type = struct.unpack("<iii", data[:12])
        payload = data[12:-2].decode("utf-8", errors="replace")
        return cls(request_id=request_id, packet_type=packet_type, payload=payload)


class RconClient:
    """
    Async RCON client for sending commands to Minecraft server.

    RCON (Remote Console) is a protocol for remotely executing commands
    on a Minecraft server. It must be enabled in server.properties.
    """

    def __init__(self, host: str = "localhost", port: int = 25575, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0
        self._authenticated = False
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if connected to RCON."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self, timeout: float = 5.0) -> bool:
        """
        Connect to RCON server.

        Args:
            timeout: Connection timeout in seconds

        Returns:
            True if connected and authenticated
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=timeout,
            )
        except (TimeoutError, OSError):
            return False

        # Authenticate
        return await self._authenticate()

    async def _authenticate(self) -> bool:
        """Authenticate with RCON server."""
        self._request_id += 1
        packet = RconPacket(
            request_id=self._request_id,
            packet_type=PacketType.AUTH,
            payload=self.password,
        )

        try:
            response = await self._send_packet(packet)
            if response and response.request_id == self._request_id:
                self._authenticated = True
                return True
            else:
                # Auth failed (request_id will be -1)
                self._authenticated = False
                return False
        except Exception:
            self._authenticated = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from RCON server."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = None
        self._reader = None
        self._authenticated = False

    async def command(self, cmd: str, timeout: float = 10.0) -> str | None:
        """
        Execute a command on the server.

        Args:
            cmd: Command to execute (without leading /)
            timeout: Response timeout in seconds

        Returns:
            Command response or None if failed
        """
        if not self._authenticated:
            # Try to reconnect
            if not await self.connect():
                return None

        async with self._lock:
            self._request_id += 1
            packet = RconPacket(
                request_id=self._request_id,
                packet_type=PacketType.COMMAND,
                payload=cmd,
            )

            try:
                response = await asyncio.wait_for(
                    self._send_packet(packet),
                    timeout=timeout,
                )
                return response.payload if response else None
            except TimeoutError:
                return None
            except Exception:
                # Connection lost, mark as not authenticated
                self._authenticated = False
                return None

    async def _send_packet(self, packet: RconPacket) -> RconPacket | None:
        """Send packet and receive response."""
        if not self._writer or not self._reader:
            return None

        try:
            self._writer.write(packet.encode())
            await self._writer.drain()

            # Read response length
            length_data = await self._reader.readexactly(4)
            length = struct.unpack("<i", length_data)[0]

            # Read rest of packet
            data = length_data + await self._reader.readexactly(length)
            return RconPacket.decode(data)

        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            await self.disconnect()
            return None

    async def __aenter__(self) -> "RconClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        await self.disconnect()


# Common RCON commands as helper functions
async def rcon_list(client: RconClient) -> list[str]:
    """Get list of online players via RCON."""
    response = await client.command("list")
    if not response:
        return []

    # Parse response like "There are 2 of a max of 20 players online: Player1, Player2"
    if ":" in response:
        players_str = response.split(":", 1)[1].strip()
        if players_str:
            return [p.strip() for p in players_str.split(",")]
    return []


async def rcon_say(client: RconClient, message: str) -> bool:
    """Send a chat message via RCON."""
    response = await client.command(f"say {message}")
    return response is not None


async def rcon_kick(client: RconClient, player: str, reason: str = "") -> bool:
    """Kick a player via RCON."""
    cmd = f"kick {player}" + (f" {reason}" if reason else "")
    response = await client.command(cmd)
    return response is not None


async def rcon_whitelist_add(client: RconClient, player: str) -> str | None:
    """Add player to whitelist via RCON."""
    return await client.command(f"whitelist add {player}")


async def rcon_whitelist_remove(client: RconClient, player: str) -> str | None:
    """Remove player from whitelist via RCON."""
    return await client.command(f"whitelist remove {player}")


async def rcon_op(client: RconClient, player: str) -> str | None:
    """Make player an operator via RCON."""
    return await client.command(f"op {player}")


async def rcon_deop(client: RconClient, player: str) -> str | None:
    """Remove operator status via RCON."""
    return await client.command(f"deop {player}")


async def rcon_save(client: RconClient) -> bool:
    """Save the world via RCON."""
    response = await client.command("save-all")
    return response is not None
