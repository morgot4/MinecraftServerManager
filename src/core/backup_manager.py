"""Backup manager with rotation for Minecraft worlds."""

import asyncio
import shutil
import tarfile
import uuid
from datetime import datetime
from pathlib import Path

from src.storage.models import Backup, BackupType, Server


class BackupManager:
    """
    Manages world backups with automatic rotation.

    Creates compressed tar.gz archives of the world folder.
    Supports automatic cleanup of old backups.
    """

    def __init__(self, backups_dir: Path, keep_count: int = 2):
        """
        Initialize backup manager.

        Args:
            backups_dir: Directory to store backups
            keep_count: Number of auto backups to keep per server
        """
        self.backups_dir = backups_dir
        self.keep_count = keep_count
        self._lock = asyncio.Lock()

    async def create_backup(
        self,
        server: Server,
        backup_type: BackupType = BackupType.MANUAL,
    ) -> Backup:
        """
        Create a backup of the server's world.

        Args:
            server: Server to backup
            backup_type: Type of backup (auto, manual, pre_shutdown)

        Returns:
            Backup record

        Raises:
            FileNotFoundError: If world folder doesn't exist
            RuntimeError: If backup creation fails
        """
        world_path = server.world_path
        if not world_path.exists():
            raise FileNotFoundError(f"World folder not found: {world_path}")

        # Create backup directory for this server
        server_backup_dir = self.backups_dir / server.name
        server_backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"world_{timestamp}.tar.gz"
        backup_path = server_backup_dir / filename

        async with self._lock:
            # Run compression in thread pool to not block
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    self._create_archive,
                    world_path,
                    backup_path,
                )
            except Exception as e:
                raise RuntimeError(f"Failed to create backup: {e}") from e

        # Get file size
        size_bytes = backup_path.stat().st_size

        return Backup(
            id=str(uuid.uuid4()),
            server_id=server.id,
            filename=filename,
            size_bytes=size_bytes,
            backup_type=backup_type,
            created_at=datetime.now(),
        )

    def _create_archive(self, source_path: Path, dest_path: Path) -> None:
        """Create tar.gz archive of a directory."""
        with tarfile.open(dest_path, "w:gz") as tar:
            tar.add(source_path, arcname="world")

    async def restore_backup(self, server: Server, backup: Backup) -> None:
        """
        Restore a backup to the server's world folder.

        WARNING: This will delete the current world!

        Args:
            server: Server to restore to
            backup: Backup to restore

        Raises:
            FileNotFoundError: If backup file doesn't exist
            RuntimeError: If restoration fails
        """
        backup_path = self.backups_dir / server.name / backup.filename
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        world_path = server.world_path

        async with self._lock:
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    self._restore_archive,
                    backup_path,
                    world_path,
                )
            except Exception as e:
                raise RuntimeError(f"Failed to restore backup: {e}") from e

    def _restore_archive(self, archive_path: Path, world_path: Path) -> None:
        """Extract archive to world folder."""
        # Delete current world
        if world_path.exists():
            shutil.rmtree(world_path)

        # Extract backup
        world_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            # Extract to parent directory (archive contains "world" folder)
            tar.extractall(world_path.parent)

    async def rotate_auto_backups(
        self,
        server: Server,
        db_backups: list[Backup],
    ) -> list[Backup]:
        """
        Delete old auto backups beyond keep_count.

        Args:
            server: Server to rotate backups for
            db_backups: List of auto backups from database (newest first)

        Returns:
            List of deleted backups
        """
        # Filter to only auto backups
        auto_backups = [b for b in db_backups if b.backup_type == BackupType.AUTO]

        if len(auto_backups) <= self.keep_count:
            return []

        # Delete oldest backups beyond keep_count
        to_delete = auto_backups[self.keep_count :]
        deleted = []

        for backup in to_delete:
            try:
                await self.delete_backup_file(server, backup)
                deleted.append(backup)
            except Exception:
                pass  # Continue with others

        return deleted

    async def delete_backup_file(self, server: Server, backup: Backup) -> None:
        """Delete a backup file from disk."""
        backup_path = self.backups_dir / server.name / backup.filename
        if backup_path.exists():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, backup_path.unlink)

    def get_backup_path(self, server: Server, backup: Backup) -> Path:
        """Get full path to a backup file."""
        return self.backups_dir / server.name / backup.filename

    def list_backup_files(self, server: Server) -> list[Path]:
        """List all backup files for a server."""
        server_backup_dir = self.backups_dir / server.name
        if not server_backup_dir.exists():
            return []
        return sorted(server_backup_dir.glob("*.tar.gz"), reverse=True)

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format file size in human readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
