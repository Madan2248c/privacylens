"""Tests for the Session Vault module (Properties 14, 15, 16 and unit tests)."""

from __future__ import annotations

import sys
import unittest.mock as mock
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from privacylens.core.vault import MemoryVault, SqliteVault, _build_vault


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_session_id = st.text(min_size=1, max_size=50)
_token = st.text(min_size=1, max_size=50)
_value = st.text(min_size=0, max_size=200)

# Two distinct session IDs
_two_distinct_sessions = st.tuples(_session_id, _session_id).filter(
    lambda pair: pair[0] != pair[1]
)


# ---------------------------------------------------------------------------
# Property 14: Session vault isolation across distinct session IDs
# ---------------------------------------------------------------------------


@given(sessions=_two_distinct_sessions, token=_token, value=_value)
@settings(max_examples=300)
def test_vault_session_isolation(
    sessions: tuple[str, str], token: str, value: str
) -> None:
    """Property 14: token stored under s1 SHALL NOT be retrievable under s2.

    **Validates: Requirements 7.1**
    """
    s1, s2 = sessions
    vault = MemoryVault()
    vault.store(s1, token, value)

    with pytest.raises(KeyError):
        vault.retrieve(s2, token)


# ---------------------------------------------------------------------------
# Property 15: Session vault store-retrieve round-trip
# ---------------------------------------------------------------------------


@given(session_id=_session_id, token=_token, value=_value)
@settings(max_examples=300)
def test_vault_store_retrieve_roundtrip(
    session_id: str, token: str, value: str
) -> None:
    """Property 15: storing then retrieving with same session_id and token returns original value.

    **Validates: Requirements 7.2**
    """
    vault = MemoryVault()
    vault.store(session_id, token, value)
    assert vault.retrieve(session_id, token) == value


# ---------------------------------------------------------------------------
# Property 16: Vault clear removes all mappings
# ---------------------------------------------------------------------------


@given(
    session_id=_session_id,
    entries=st.lists(
        st.tuples(_token, _value),
        min_size=1,
        max_size=10,
        unique_by=lambda pair: pair[0],  # unique tokens
    ),
)
@settings(max_examples=200)
def test_vault_clear_removes_all_mappings(
    session_id: str, entries: list[tuple[str, str]]
) -> None:
    """Property 16: after clear(session_id), all previously stored tokens raise KeyError.

    **Validates: Requirements 7.7**
    """
    vault = MemoryVault()
    for token, value in entries:
        vault.store(session_id, token, value)

    vault.clear(session_id)

    for token, _ in entries:
        with pytest.raises(KeyError):
            vault.retrieve(session_id, token)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestMemoryVaultKeyError:
    def test_retrieve_missing_token_raises_key_error(self) -> None:
        """Requirement 7.3: retrieve on missing token raises KeyError."""
        vault = MemoryVault()
        with pytest.raises(KeyError):
            vault.retrieve("session-1", "[EMAIL_1]")

    def test_retrieve_wrong_session_raises_key_error(self) -> None:
        vault = MemoryVault()
        vault.store("session-1", "[EMAIL_1]", "alice@example.com")
        with pytest.raises(KeyError):
            vault.retrieve("session-2", "[EMAIL_1]")

    def test_retrieve_after_clear_raises_key_error(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[PHONE_1]", "555-1234")
        vault.clear("s1")
        with pytest.raises(KeyError):
            vault.retrieve("s1", "[PHONE_1]")

    def test_clear_nonexistent_session_is_noop(self) -> None:
        vault = MemoryVault()
        # Should not raise
        vault.clear("nonexistent-session")

    def test_overwrite_token_returns_latest_value(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_1]", "old@example.com")
        vault.store("s1", "[EMAIL_1]", "new@example.com")
        assert vault.retrieve("s1", "[EMAIL_1]") == "new@example.com"

    def test_multiple_sessions_independent(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        vault.store("s2", "[EMAIL_1]", "bob@example.com")
        assert vault.retrieve("s1", "[EMAIL_1]") == "alice@example.com"
        assert vault.retrieve("s2", "[EMAIL_1]") == "bob@example.com"

    def test_clear_only_affects_target_session(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        vault.store("s2", "[EMAIL_1]", "bob@example.com")
        vault.clear("s1")
        with pytest.raises(KeyError):
            vault.retrieve("s1", "[EMAIL_1]")
        # s2 should be unaffected
        assert vault.retrieve("s2", "[EMAIL_1]") == "bob@example.com"


class TestRedisImportError:
    def test_redis_import_error_when_not_installed(self) -> None:
        """Requirement 7.5: RedisVault raises ImportError with correct message when redis not installed."""
        # Temporarily hide redis from sys.modules
        with patch.dict(sys.modules, {"redis": None}):
            from privacylens.core.vault import RedisVault

            with pytest.raises(ImportError, match="Install redis: pip install privacylens\\[redis\\]"):
                RedisVault(url="redis://localhost:6379")


class TestSqliteVault:
    def test_store_and_retrieve(self) -> None:
        """Requirement 7.6: SQLite backend stores and retrieves values."""
        vault = SqliteVault(db_path=":memory:")
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        assert vault.retrieve("s1", "[EMAIL_1]") == "alice@example.com"

    def test_retrieve_missing_raises_key_error(self) -> None:
        vault = SqliteVault(db_path=":memory:")
        with pytest.raises(KeyError):
            vault.retrieve("s1", "[EMAIL_1]")

    def test_clear_removes_all_session_entries(self) -> None:
        vault = SqliteVault(db_path=":memory:")
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        vault.store("s1", "[PHONE_1]", "555-1234")
        vault.clear("s1")
        with pytest.raises(KeyError):
            vault.retrieve("s1", "[EMAIL_1]")
        with pytest.raises(KeyError):
            vault.retrieve("s1", "[PHONE_1]")

    def test_clear_does_not_affect_other_sessions(self) -> None:
        vault = SqliteVault(db_path=":memory:")
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        vault.store("s2", "[EMAIL_1]", "bob@example.com")
        vault.clear("s1")
        assert vault.retrieve("s2", "[EMAIL_1]") == "bob@example.com"

    def test_overwrite_token(self) -> None:
        vault = SqliteVault(db_path=":memory:")
        vault.store("s1", "[EMAIL_1]", "old@example.com")
        vault.store("s1", "[EMAIL_1]", "new@example.com")
        assert vault.retrieve("s1", "[EMAIL_1]") == "new@example.com"

    def test_session_isolation(self) -> None:
        vault = SqliteVault(db_path=":memory:")
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        with pytest.raises(KeyError):
            vault.retrieve("s2", "[EMAIL_1]")


class TestBuildVault:
    def test_build_memory_vault(self) -> None:
        config = {"vault": "memory"}
        vault = _build_vault(config)  # type: ignore[arg-type]
        assert isinstance(vault, MemoryVault)

    def test_build_sqlite_vault(self) -> None:
        config = {"vault": "sqlite", "sqlite_path": ":memory:"}
        vault = _build_vault(config)  # type: ignore[arg-type]
        assert isinstance(vault, SqliteVault)

    def test_build_default_is_memory(self) -> None:
        config = {}
        vault = _build_vault(config)  # type: ignore[arg-type]
        assert isinstance(vault, MemoryVault)

    def test_build_unknown_backend_raises_value_error(self) -> None:
        config = {"vault": "unknown"}
        with pytest.raises(ValueError, match="Unknown vault backend"):
            _build_vault(config)  # type: ignore[arg-type]
