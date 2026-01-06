"""Java utilities for checking Java installation and version."""

import asyncio
import re
import shutil
from dataclasses import dataclass


@dataclass
class JavaInfo:
    """Information about Java installation."""

    path: str
    version: str
    major_version: int
    is_valid: bool
    error: str | None = None


async def check_java(java_path: str = "java") -> JavaInfo:
    """
    Check if Java is installed and get version information.

    Args:
        java_path: Path to java executable or "java" to use PATH

    Returns:
        JavaInfo with version details or error information
    """
    # First check if java exists
    resolved_path = shutil.which(java_path)
    if resolved_path is None and java_path == "java":
        return JavaInfo(
            path=java_path,
            version="",
            major_version=0,
            is_valid=False,
            error="Java not found in PATH. Please install Java 17 or higher.",
        )

    actual_path = resolved_path or java_path

    try:
        process = await asyncio.create_subprocess_exec(
            actual_path,
            "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)

        # Java outputs version to stderr
        output = stderr.decode("utf-8", errors="replace")

        # Parse version from output like:
        # openjdk version "17.0.1" 2021-10-19
        # java version "1.8.0_301"
        version_match = re.search(r'version "([^"]+)"', output)
        if not version_match:
            return JavaInfo(
                path=actual_path,
                version="",
                major_version=0,
                is_valid=False,
                error=f"Could not parse Java version from output: {output[:100]}",
            )

        version_str = version_match.group(1)

        # Extract major version
        # "17.0.1" -> 17
        # "1.8.0_301" -> 8
        if version_str.startswith("1."):
            major_match = re.match(r"1\.(\d+)", version_str)
            major_version = int(major_match.group(1)) if major_match else 0
        else:
            major_match = re.match(r"(\d+)", version_str)
            major_version = int(major_match.group(1)) if major_match else 0

        return JavaInfo(
            path=actual_path,
            version=version_str,
            major_version=major_version,
            is_valid=True,
        )

    except TimeoutError:
        return JavaInfo(
            path=actual_path,
            version="",
            major_version=0,
            is_valid=False,
            error="Timeout while checking Java version",
        )
    except FileNotFoundError:
        return JavaInfo(
            path=java_path,
            version="",
            major_version=0,
            is_valid=False,
            error=f"Java executable not found at: {java_path}",
        )
    except Exception as e:
        return JavaInfo(
            path=java_path,
            version="",
            major_version=0,
            is_valid=False,
            error=f"Error checking Java: {e}",
        )


def get_min_java_version(mc_version: str) -> int:
    """
    Get minimum required Java version for a Minecraft version.

    Args:
        mc_version: Minecraft version string (e.g., "1.21.1", "1.16.5")

    Returns:
        Minimum Java major version required
    """
    # Parse major.minor from MC version
    match = re.match(r"(\d+)\.(\d+)", mc_version)
    if not match:
        return 17  # Default to Java 17

    major, minor = int(match.group(1)), int(match.group(2))

    # Minecraft version requirements:
    # 1.21+ requires Java 21
    # 1.18 - 1.20.x requires Java 17
    # 1.17.x requires Java 16
    # 1.12 - 1.16.x requires Java 8
    if major >= 1 and minor >= 21:
        return 21
    elif major >= 1 and minor >= 18:
        return 17
    elif major >= 1 and minor >= 17:
        return 16
    else:
        return 8
