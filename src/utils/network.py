"""Network utilities for port checking."""

import asyncio
import socket


async def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check
        host: Host address to bind to

    Returns:
        True if port is available, False otherwise
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _check_port_sync, port, host)


def _check_port_sync(port: int, host: str) -> bool:
    """Synchronous port check."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False


async def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """
    Check if something is listening on a port.

    Args:
        port: Port number to check
        host: Host address to connect to

    Returns:
        True if port is in use (something listening), False otherwise
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=2.0,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (TimeoutError, OSError):
        return False


async def find_available_port(start_port: int = 25565, max_attempts: int = 100) -> int | None:
    """
    Find an available port starting from start_port.

    Args:
        start_port: Port to start searching from
        max_attempts: Maximum number of ports to try

    Returns:
        Available port number or None if not found
    """
    for port in range(start_port, start_port + max_attempts):
        if await is_port_available(port):
            return port
    return None


def get_local_ip() -> str:
    """
    Get the local IP address of this machine.

    Returns:
        Local IP address string
    """
    try:
        # Create a socket and connect to an external address
        # This doesn't actually send any data
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
