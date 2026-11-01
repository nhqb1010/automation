# LEARN: YOU ARE HERE
#   DailyCommitTool asks "which repo + token?" ▶ THIS FILE answers from .env (dev)
#   or the macOS Keychain (installed app) ▶ GitHubClient uses them
#   read next → app/tools/daily_commit/streak_stats.py
"""
Where the Daily Commit tool's GitHub token lives.

LEARN: two copies of the app, two places for the secret

                  make start_app (dev)          installed .app
  read from       .env (you fill it in)         macOS Keychain
  [ Connect ]     ✗ (edit .env instead)         ✓ saves to Keychain
  [ Disconnect ]  ✗                             ✓ removes it from Keychain
  Keychain        NEVER touched                 one item, see below

  → the dev copy can't change or read the installed app's secret

LEARN: Keychain = macOS's encrypted password store (Keychain Access app)
  one item: service "Bao Internal Apps Streak", account "github"
  its password = {"repository": "me/notes", "token": "github_pat_…"} as JSON
    → one item → one "Always Allow" question after each reinstall
  the service name must NEVER change: a new name = a new, empty item

LEARN: keyring = a Python package that talks to each OS's password store
  keyring.backends.macOS.Keyring → the Mac one, chosen directly
  (no auto-detection → also works inside the built .app)
"""

import json
import logging
from collections.abc import Callable
from typing import Protocol

from keyring.backends import macOS
from pydantic import BaseModel, SecretStr, ValidationError

from app.tools.daily_commit.github_client import REPOSITORY_PATTERN
from app.tools.daily_commit.models import ConnectionInfo

logger = logging.getLogger(__name__)

# NEVER rename these two (see above); the tool was first called "Streak",
# and the saved item keeps that name
KEYCHAIN_SERVICE = "Bao Internal Apps Streak"
KEYCHAIN_ACCOUNT = "github"


class ConnectionNotEditableError(RuntimeError):
    """The dev copy's connection comes from .env; it can't be changed here."""


class DailyCommitConnection(BaseModel):
    """
    LEARN: the notes repo + the token that may write to it

    SecretStr → prints as "**********"; the real text only via
      .get_secret_value() → only GitHubClient asks for it
    """

    repository: str
    token: SecretStr


class SecretStorage(Protocol):
    """
    LEARN: Protocol = "anything with these methods will do"
      the real Keychain and the tests' fake dict both fit
      industry term: "structural typing" / "duck typing"
      ≈ an interface, without having to inherit from it
    """

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def open_macos_keychain() -> SecretStorage:
    """
    LEARN: the real Keychain, opened only when first needed

    called by → DailyCommitConnectionStore, installed app only
    loading the keyring package touches nothing; only its calls do
      → the dev copy never calls this function
    """
    return macOS.Keyring()


def check_repository_name(repository: str) -> str:
    """
    LEARN: "  me/notes " → "me/notes"; anything not owner/name → ValueError

    called by → DailyCommitConnectionStore.save_daily_commit_connection
    also accepts a pasted web address: https://github.com/me/notes → me/notes
    """
    cleaned = repository.strip().removeprefix("https://github.com/").strip("/")
    cleaned = cleaned.removesuffix(".git")
    if not REPOSITORY_PATTERN.match(cleaned):
        raise ValueError("Repository must look like owner/name, e.g. me/notes")

    return cleaned


class DailyCommitConnectionStore:
    """
    LEARN: the one place that knows where the connection lives

    made by → DailyCommitTool (daily_commit/__init__.py), once at startup
    is_installed → True: Keychain · False: the .env values passed in
    open_keychain → how to open the Keychain (tests pass a fake)
    """

    def __init__(
        self,
        is_installed: bool,
        dev_repository: str | None,
        dev_token: SecretStr | None,
        open_keychain: Callable[[], SecretStorage] = open_macos_keychain,
    ) -> None:
        self._is_installed = is_installed
        self._dev_repository = dev_repository
        self._dev_token = dev_token
        self._open_keychain = open_keychain

    def read_daily_commit_connection(self) -> DailyCommitConnection | None:
        """
        LEARN: repo + token, or None when not connected

        called by → DailyCommitTool, before every GitHub call
        a broken / unreadable Keychain item → logged, treated as None
        """
        if not self._is_installed:
            if not self._dev_repository or self._dev_token is None:
                return None

            return DailyCommitConnection(
                repository=self._dev_repository.strip(), token=self._dev_token
            )

        try:
            saved = self._open_keychain().get_password(
                KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT
            )
        except Exception:
            logger.exception("Could not read the Daily Commit item from the Keychain")
            return None

        if not saved:
            return None

        try:
            return DailyCommitConnection.model_validate(json.loads(saved))
        except ValueError, ValidationError:
            logger.warning("The Keychain's Daily Commit item is unreadable, skipped")
            return None

    def describe_daily_commit_connection(self) -> ConnectionInfo:
        """called by → DailyCommitTool overview ▶ the Connection card (no token)."""
        connection = self.read_daily_commit_connection()
        if connection is None:
            source = "none"
        elif self._is_installed:
            source = "keychain"
        else:
            source = "dev_env"

        return ConnectionInfo(
            source=source,
            repository=connection.repository if connection else None,
            can_edit=self._is_installed,
        )

    def save_daily_commit_connection(
        self, repository: str, token: str
    ) -> DailyCommitConnection:
        """
        LEARN: [ Connect ] in the installed app → one Keychain item

        called by → DailyCommitTool.connect_daily_commit_repository
        the dev copy → ConnectionNotEditableError (edit .env instead)
        """
        if not self._is_installed:
            raise ConnectionNotEditableError("The dev copy reads its token from .env")

        connection = DailyCommitConnection(
            repository=check_repository_name(repository), token=SecretStr(token.strip())
        )
        if not connection.token.get_secret_value():
            raise ValueError("The token is empty")

        secret = json.dumps(
            {
                "repository": connection.repository,
                "token": connection.token.get_secret_value(),
            }
        )
        self._open_keychain().set_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, secret)
        logger.info(f"Daily Commit connected {connection.repository=}")
        return connection

    def forget_daily_commit_connection(self) -> None:
        """
        LEARN: [ Disconnect ] → remove the Keychain item

        the notes repo and its workflow are NOT touched: GitHub keeps
        posting daily; only this app forgets how to reach it
        """
        if not self._is_installed:
            raise ConnectionNotEditableError("The dev copy reads its token from .env")

        try:
            self._open_keychain().delete_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        except Exception:
            # nothing saved → nothing to remove; that's fine
            logger.info("No Daily Commit connection in the Keychain to remove")
            return

        logger.info("Daily Commit disconnected")
