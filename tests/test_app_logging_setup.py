# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks the error counter in app/logging_setup.py
#   (the number behind the red badge on Logs)
#   read next → tests/test_app_csp.py
import logging
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import AppSettings
from app.logging_setup import ErrorCountingHandler, configure_app_logging


@pytest.fixture
def counted_logger() -> Iterator[tuple[logging.Logger, ErrorCountingHandler]]:
    # LEARN: a fixture with "yield" → the code after yield runs after the test
    #   (here: unhook the counter so other tests aren't affected)
    logger = logging.getLogger("tests.error_counter")
    counter = ErrorCountingHandler()
    logger.addHandler(counter)
    # propagate False → these test lines don't reach the real log handlers
    logger.propagate = False
    yield logger, counter
    logger.removeHandler(counter)


class TestAppLoggingSetupErrorCountingHandler:
    def test_app_logging_setup_error_counting_handler_counts_errors_only(
        self, counted_logger: tuple[logging.Logger, ErrorCountingHandler]
    ) -> None:
        logger, counter = counted_logger

        logger.info("fine")
        logger.warning("odd")
        logger.error("broken")
        logger.critical("very broken")

        assert counter.count_unseen_errors() == 2

    def test_app_logging_setup_error_counting_handler_mark_seen(
        self, counted_logger: tuple[logging.Logger, ErrorCountingHandler]
    ) -> None:
        logger, counter = counted_logger
        logger.error("first")

        counter.mark_all_errors_seen()
        logger.error("second")

        assert counter.count_unseen_errors() == 1


class TestAppLoggingSetupLoggingSetup:
    def test_app_logging_setup_configure_returns_counter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BAO_LOG_DIR", str(tmp_path))
        root = logging.getLogger()
        saved_handlers = list(root.handlers)
        saved_level = root.level
        # configure_app_logging also replaces Python's crash hooks → put
        # them back afterwards too (monkeypatch restores them for us)
        monkeypatch.setattr(sys, "excepthook", sys.excepthook)
        monkeypatch.setattr(threading, "excepthook", threading.excepthook)

        try:
            setup = configure_app_logging(AppSettings(_env_file=None))
            logging.getLogger("tests.setup").error("counted")
            unseen = setup.error_counter.count_unseen_errors()
        finally:
            # put the root logger back the way pytest had it
            for handler in root.handlers:
                if handler not in saved_handlers:
                    handler.close()

            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)

        assert setup.log_file.name == "app.log"
        assert unseen == 1
