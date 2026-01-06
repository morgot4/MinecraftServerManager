"""SQLite database operations using aiosqlite."""

from datetime import datetime
from pathlib import Path

import aiosqlite

from src.storage.models import Backup, BackupType, EngineType, Server, User, UserRole


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and initialize tables."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._init_tables()

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Get the active connection."""
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def _init_tables(self) -> None:
        """Create database tables if they don't exist."""
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS servers (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                engine TEXT NOT NULL DEFAULT 'vanilla',
                mc_version TEXT NOT NULL,
                path TEXT NOT NULL,
                port INTEGER DEFAULT 25565,
                ram_min TEXT DEFAULT '2G',
                ram_max TEXT DEFAULT '8G',
                rcon_port INTEGER DEFAULT 25575,
                rcon_password TEXT DEFAULT '',
                is_active INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_started_at TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                role TEXT DEFAULT 'player',
                language TEXT DEFAULT 'ru',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backups (
                id TEXT PRIMARY KEY,
                server_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                backup_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_backups_server ON backups(server_id);
            CREATE INDEX IF NOT EXISTS idx_backups_created ON backups(created_at);
        """)
        await self.conn.commit()

    # ============== Server Operations ==============

    async def create_server(self, server: Server) -> Server:
        """Insert a new server into database."""
        await self.conn.execute(
            """
            INSERT INTO servers (
                id, name, engine, mc_version, path, port,
                ram_min, ram_max, rcon_port, rcon_password,
                is_active, created_at, last_started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                server.id,
                server.name,
                server.engine.value,
                server.mc_version,
                str(server.path),
                server.port,
                server.ram_min,
                server.ram_max,
                server.rcon_port,
                server.rcon_password,
                1 if server.is_active else 0,
                server.created_at.isoformat(),
                server.last_started_at.isoformat() if server.last_started_at else None,
            ),
        )
        await self.conn.commit()
        return server

    async def get_server(self, server_id: str) -> Server | None:
        """Get server by ID."""
        async with self.conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)) as cursor:
            row = await cursor.fetchone()
            return self._row_to_server(row) if row else None

    async def get_server_by_name(self, name: str) -> Server | None:
        """Get server by name."""
        async with self.conn.execute("SELECT * FROM servers WHERE name = ?", (name,)) as cursor:
            row = await cursor.fetchone()
            return self._row_to_server(row) if row else None

    async def get_active_server(self) -> Server | None:
        """Get the currently active server."""
        async with self.conn.execute("SELECT * FROM servers WHERE is_active = 1 LIMIT 1") as cursor:
            row = await cursor.fetchone()
            return self._row_to_server(row) if row else None

    async def get_all_servers(self) -> list[Server]:
        """Get all servers."""
        async with self.conn.execute("SELECT * FROM servers ORDER BY name") as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_server(row) for row in rows]

    async def update_server(self, server: Server) -> None:
        """Update server in database."""
        await self.conn.execute(
            """
            UPDATE servers SET
                name = ?, engine = ?, mc_version = ?, path = ?,
                port = ?, ram_min = ?, ram_max = ?, rcon_port = ?,
                rcon_password = ?, is_active = ?, last_started_at = ?
            WHERE id = ?
            """,
            (
                server.name,
                server.engine.value,
                server.mc_version,
                str(server.path),
                server.port,
                server.ram_min,
                server.ram_max,
                server.rcon_port,
                server.rcon_password,
                1 if server.is_active else 0,
                server.last_started_at.isoformat() if server.last_started_at else None,
                server.id,
            ),
        )
        await self.conn.commit()

    async def set_active_server(self, server_id: str) -> None:
        """Set a server as active, deactivating others."""
        await self.conn.execute("UPDATE servers SET is_active = 0")
        await self.conn.execute("UPDATE servers SET is_active = 1 WHERE id = ?", (server_id,))
        await self.conn.commit()

    async def delete_server(self, server_id: str) -> None:
        """Delete a server from database."""
        await self.conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        await self.conn.commit()

    def _row_to_server(self, row: aiosqlite.Row) -> Server:
        """Convert database row to Server model."""
        return Server(
            id=row["id"],
            name=row["name"],
            engine=EngineType(row["engine"]),
            mc_version=row["mc_version"],
            path=Path(row["path"]),
            port=row["port"],
            ram_min=row["ram_min"],
            ram_max=row["ram_max"],
            rcon_port=row["rcon_port"],
            rcon_password=row["rcon_password"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_started_at=(
                datetime.fromisoformat(row["last_started_at"]) if row["last_started_at"] else None
            ),
        )

    # ============== User Operations ==============

    async def get_or_create_user(self, telegram_id: int, username: str | None = None) -> User:
        """Get user by Telegram ID or create new one."""
        async with self.conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_user(row)

        # Create new user
        user = User(
            telegram_id=telegram_id,
            username=username,
            role=UserRole.PLAYER,
            created_at=datetime.now(),
        )
        await self.conn.execute(
            """
            INSERT INTO users (telegram_id, username, role, language, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user.telegram_id,
                user.username,
                user.role.value,
                user.language,
                user.created_at.isoformat(),
            ),
        )
        await self.conn.commit()
        return user

    async def get_user(self, telegram_id: int) -> User | None:
        """Get user by Telegram ID."""
        async with self.conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_user(row) if row else None

    async def update_user(self, user: User) -> None:
        """Update user in database."""
        await self.conn.execute(
            """
            UPDATE users SET username = ?, role = ?, language = ?
            WHERE telegram_id = ?
            """,
            (user.username, user.role.value, user.language, user.telegram_id),
        )
        await self.conn.commit()

    async def set_user_role(self, telegram_id: int, role: UserRole) -> None:
        """Set user role."""
        await self.conn.execute(
            "UPDATE users SET role = ? WHERE telegram_id = ?",
            (role.value, telegram_id),
        )
        await self.conn.commit()

    async def get_all_users(self) -> list[User]:
        """Get all registered users ordered by role level (highest first)."""
        async with self.conn.execute(
            """
            SELECT * FROM users
            ORDER BY
                CASE role
                    WHEN 'owner' THEN 1
                    WHEN 'admin' THEN 2
                    WHEN 'operator' THEN 3
                    ELSE 4
                END,
                username
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_user(row) for row in rows]

    async def get_users_by_role(self, role: UserRole) -> list[User]:
        """Get all users with a specific role."""
        async with self.conn.execute(
            "SELECT * FROM users WHERE role = ? ORDER BY username",
            (role.value,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_user(row) for row in rows]

    def _row_to_user(self, row: aiosqlite.Row) -> User:
        """Convert database row to User model."""
        return User(
            telegram_id=row["telegram_id"],
            username=row["username"],
            role=UserRole(row["role"]),
            language=row["language"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ============== Backup Operations ==============

    async def create_backup(self, backup: Backup) -> Backup:
        """Insert a new backup record."""
        await self.conn.execute(
            """
            INSERT INTO backups (id, server_id, filename, size_bytes, backup_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                backup.id,
                backup.server_id,
                backup.filename,
                backup.size_bytes,
                backup.backup_type.value,
                backup.created_at.isoformat(),
            ),
        )
        await self.conn.commit()
        return backup

    async def get_backups_for_server(
        self, server_id: str, limit: int | None = None
    ) -> list[Backup]:
        """Get backups for a server, ordered by creation date (newest first)."""
        query = """
            SELECT * FROM backups WHERE server_id = ?
            ORDER BY created_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"

        async with self.conn.execute(query, (server_id,)) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_backup(row) for row in rows]

    async def get_auto_backups_for_server(self, server_id: str) -> list[Backup]:
        """Get only automatic backups for a server."""
        async with self.conn.execute(
            """
            SELECT * FROM backups
            WHERE server_id = ? AND backup_type = 'auto'
            ORDER BY created_at DESC
            """,
            (server_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_backup(row) for row in rows]

    async def delete_backup(self, backup_id: str) -> None:
        """Delete a backup record."""
        await self.conn.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
        await self.conn.commit()

    def _row_to_backup(self, row: aiosqlite.Row) -> Backup:
        """Convert database row to Backup model."""
        return Backup(
            id=row["id"],
            server_id=row["server_id"],
            filename=row["filename"],
            size_bytes=row["size_bytes"],
            backup_type=BackupType(row["backup_type"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


# Global database instance
_database: Database | None = None


async def get_database() -> Database:
    """Get or create the global database instance."""
    global _database
    if _database is None:
        from src.utils.config import get_config

        config = get_config()
        _database = Database(config.paths.database)
        await _database.connect()
    return _database
