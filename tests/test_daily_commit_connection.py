# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks daily_commit/connection.py with a FAKE Keychain
#   (a dict) → the real Keychain is never touched by tests
#   read next → tests/test_daily_commit_streak_stats.py
import json

import pytest
from pydantic import SecretStr

from app.tools.daily_commit.connection import (
    KEYCHAIN_ACCOUNT,
    KEYCHAIN_SERVICE,
    ConnectionNotEditableError,
    SecretStorage,
    DailyCommitConnectionStore,
    check_repository_name,
)


class FakeKeychain:
    """LEARN: a dict that behaves like the Keychain's three calls."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.items.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.items[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        # the real one raises when there is nothing to delete
        del self.items[(service, username)]


def refuse_keychain() -> SecretStorage:
    # the dev copy must never get here
    raise AssertionError("The dev copy opened the Keychain")


@pytest.fixture
def keychain() -> FakeKeychain:
    return FakeKeychain()


def build_installed_store(keychain: FakeKeychain) -> DailyCommitConnectionStore:
    return DailyCommitConnectionStore(
        is_installed=True,
        dev_repository=None,
        dev_token=None,
        open_keychain=lambda: keychain,
    )


class TestDailyCommitConnectionDevCopy:
    def test_daily_commit_connection_dev_copy_reads_env_values(self) -> None:
        store = DailyCommitConnectionStore(
            is_installed=False,
            dev_repository=" me/notes ",
            dev_token=SecretStr("tok"),
            open_keychain=refuse_keychain,
        )

        connection = store.read_daily_commit_connection()

        assert connection is not None
        assert connection.repository == "me/notes"
        assert connection.token.get_secret_value() == "tok"
        assert store.describe_daily_commit_connection().source == "dev_env"

    def test_daily_commit_connection_dev_copy_missing_values_not_connected(
        self,
    ) -> None:
        store = DailyCommitConnectionStore(
            is_installed=False,
            dev_repository="me/notes",
            dev_token=None,
            open_keychain=refuse_keychain,
        )

        info = store.describe_daily_commit_connection()

        assert info.source == "none"
        assert info.can_edit is False

    def test_daily_commit_connection_dev_copy_cannot_save_or_forget(self) -> None:
        store = DailyCommitConnectionStore(
            is_installed=False,
            dev_repository=None,
            dev_token=None,
            open_keychain=refuse_keychain,
        )

        with pytest.raises(ConnectionNotEditableError):
            store.save_daily_commit_connection(repository="me/notes", token="t")
        with pytest.raises(ConnectionNotEditableError):
            store.forget_daily_commit_connection()


class TestDailyCommitConnectionKeychain:
    def test_daily_commit_connection_keychain_save_then_read(
        self, keychain: FakeKeychain
    ) -> None:
        store = build_installed_store(keychain)

        store.save_daily_commit_connection(repository="me/notes", token=" tok ")

        saved = json.loads(keychain.items[(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)])
        connection = store.read_daily_commit_connection()
        assert saved == {"repository": "me/notes", "token": "tok"}
        assert connection is not None
        assert connection.token.get_secret_value() == "tok"
        assert store.describe_daily_commit_connection().source == "keychain"

    def test_daily_commit_connection_keychain_forget_removes_item(
        self, keychain: FakeKeychain
    ) -> None:
        store = build_installed_store(keychain)
        store.save_daily_commit_connection(repository="me/notes", token="tok")

        store.forget_daily_commit_connection()

        assert store.read_daily_commit_connection() is None
        # forgetting again (nothing saved) is fine
        store.forget_daily_commit_connection()

    def test_daily_commit_connection_keychain_broken_item_is_ignored(
        self, keychain: FakeKeychain
    ) -> None:
        keychain.items[(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)] = "not json"

        assert build_installed_store(keychain).read_daily_commit_connection() is None

    def test_daily_commit_connection_keychain_empty_token_rejected(
        self, keychain: FakeKeychain
    ) -> None:
        with pytest.raises(ValueError, match="empty"):
            build_installed_store(keychain).save_daily_commit_connection(
                repository="me/notes", token="   "
            )

        assert keychain.items == {}


class TestDailyCommitConnectionCheckRepositoryName:
    @pytest.mark.parametrize(
        ("typed", "expected"),
        [
            ("me/notes", "me/notes"),
            ("  me/notes  ", "me/notes"),
            ("https://github.com/me/notes", "me/notes"),
            ("https://github.com/me/notes.git", "me/notes"),
        ],
    )
    def test_daily_commit_connection_check_repository_name_cleans_input(
        self, typed: str, expected: str
    ) -> None:
        assert check_repository_name(typed) == expected

    def test_daily_commit_connection_check_repository_name_rejects_junk(self) -> None:
        with pytest.raises(ValueError, match="owner/name"):
            check_repository_name("just-a-name")
