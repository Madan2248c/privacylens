"""Session Vault backends for PrivacyLens.

Provides in-memory, Redis, and SQLite backends for storing token-to-value
mappings scoped by session ID.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from privacylens.core.models import Config

if TYPE_CHECKING:
    import sqlite3


@runtime_checkable
class SessionVault(Protocol):
    """Protocol for session-scoped token-value storage."""

    def store(self, session_id: str, token: str, value: str) -> None:
        """Store a token-value mapping for the given session."""
        ...

    def retrieve(self, session_id: str, token: str) -> str:
        """Retrieve the value for a token in the given session.

        Raises:
            KeyError: If the token does not exist in the session.
        """
        ...

    def clear(self, session_id: str) -> None:
        """Remove all token-value mappings for the given session."""
        ...


class MemoryVault:
    """In-memory session vault. Always available with no extra dependencies."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}  # session_id → {token → value}

    def store(self, session_id: str, token: str, value: str) -> None:
        """Store a token-value mapping for the given session."""
        if session_id not in self._data:
            self._data[session_id] = {}
        self._data[session_id][token] = value

    def retrieve(self, session_id: str, token: str) -> str:
        """Retrieve the value for a token in the given session.

        Raises:
            KeyError: If the token does not exist in the session.
        """
        session = self._data.get(session_id)
        if session is None or token not in session:
            raise KeyError(token)
        return session[token]

    def clear(self, session_id: str) -> None:
        """Remove all token-value mappings for the given session."""
        self._data.pop(session_id, None)


class RedisVault:
    """Redis-backed session vault. Requires `pip install privacylens[redis]`."""

    def __init__(self, url: str = "redis://localhost:6379") -> None:
        try:
            import redis  # type: ignore[import]
        except ImportError:
            raise ImportError("Install redis: pip install privacylens[redis]")
        self._client = redis.from_url(url)

    def _key(self, session_id: str, token: str) -> str:
        return f"privacylens:{session_id}:{token}"

    def store(self, session_id: str, token: str, value: str) -> None:
        """Store a token-value mapping in Redis."""
        self._client.set(self._key(session_id, token), value)

    def retrieve(self, session_id: str, token: str) -> str:
        """Retrieve the value for a token from Redis.

        Raises:
            KeyError: If the token does not exist in the session.
        """
        result = self._client.get(self._key(session_id, token))
        if result is None:
            raise KeyError(token)
        # Redis returns bytes; decode to str
        if isinstance(result, bytes):
            return result.decode("utf-8")
        return str(result)

    def clear(self, session_id: str) -> None:
        """Remove all token-value mappings for the given session from Redis."""
        pattern = f"privacylens:{session_id}:*"
        keys = self._client.keys(pattern)
        if keys:
            self._client.delete(*keys)


class SqliteVault:
    """SQLite-backed session vault. Uses stdlib sqlite3 (lazy import).

    For file-based databases, a new connection is opened per operation.
    For `:memory:` databases, a single persistent connection is kept because
    each ``sqlite3.connect(":memory:")`` call creates a separate, empty database.
    """

    def __init__(self, db_path: str = "privacylens.db") -> None:
        import sqlite3

        self._db_path = db_path
        self._sqlite3 = sqlite3
        # Keep a persistent connection for in-memory DBs; file DBs use per-op connections.
        self._conn: sqlite3.Connection | None = (
            sqlite3.connect(":memory:") if db_path == ":memory:" else None
        )
        self._init_table()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        return self._sqlite3.connect(self._db_path)

    def _close(self, conn: sqlite3.Connection) -> None:
        # Only close connections we opened ourselves (not the persistent one).
        if conn is not self._conn:
            conn.close()

    def _init_table(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vault (
                    session_id TEXT NOT NULL,
                    token      TEXT NOT NULL,
                    value      TEXT NOT NULL,
                    PRIMARY KEY (session_id, token)
                )
                """
            )
            conn.commit()
        finally:
            self._close(conn)

    def store(self, session_id: str, token: str, value: str) -> None:
        """Store a token-value mapping in SQLite."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO vault (session_id, token, value) VALUES (?, ?, ?)",
                (session_id, token, value),
            )
            conn.commit()
        finally:
            self._close(conn)

    def retrieve(self, session_id: str, token: str) -> str:
        """Retrieve the value for a token from SQLite.

        Raises:
            KeyError: If the token does not exist in the session.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT value FROM vault WHERE session_id = ? AND token = ?",
                (session_id, token),
            )
            row = cursor.fetchone()
        finally:
            self._close(conn)
        if row is None:
            raise KeyError(token)
        return row[0]

    def clear(self, session_id: str) -> None:
        """Remove all token-value mappings for the given session from SQLite."""
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM vault WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
        finally:
            self._close(conn)


def _build_vault(config: Config) -> MemoryVault | RedisVault | SqliteVault:
    """Factory that selects the vault backend based on config.

    Args:
        config: The PrivacyLens configuration dict.

    Returns:
        An appropriate SessionVault implementation.

    Raises:
        ValueError: If the vault backend name is not recognized.
        ImportError: If the required backend library is not installed.
    """
    backend = config.get("vault", "memory")

    if backend == "memory":
        return MemoryVault()
    elif backend == "redis":
        redis_url = config.get("redis_url", "redis://localhost:6379")  # type: ignore[typeddict-item]
        return RedisVault(url=str(redis_url))
    elif backend == "sqlite":
        db_path = config.get("sqlite_path", "privacylens.db")  # type: ignore[typeddict-item]
        return SqliteVault(db_path=str(db_path))
    else:
        raise ValueError(
            f"Unknown vault backend: {backend!r}. "
            "Supported backends: 'memory', 'redis', 'sqlite'."
        )
