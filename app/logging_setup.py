"""Log file setup: one rotating file plus the terminal."""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from app.config import AppSettings

LOG_FILE_NAME = "app.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3
LOG_FORMAT = "{asctime} {levelname:<7} [{name}] {message}"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger(__name__)


def configure_app_logging(settings: AppSettings) -> Path:
    """
    Send every logger in the app to logs/app.log and the terminal.

    LEARN: rotation in one picture. At 1 MB the file is renamed and a fresh
    one starts; only three old files are kept.

      app.log (full) ──▶ app.log.1 ──▶ app.log.2 ──▶ app.log.3 ──▶ deleted

    Args:
        settings (AppSettings): provides the log level and folder.
    Returns:
        Path: the log file path.
    """
    log_dir = settings.resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, style="{")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    terminal_handler = logging.StreamHandler()
    terminal_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level)
    root.addHandler(file_handler)
    root.addHandler(terminal_handler)
    # pywebview's own debug chatter is only useful when debugging pywebview
    logging.getLogger("pywebview").setLevel(logging.WARNING)

    install_crash_logging()
    return log_file


def install_crash_logging() -> None:
    # LEARN: an excepthook runs for any error nobody caught. Logging the full
    # traceback there means a crash always leaves its reason in the log file.
    sys.excepthook = log_uncaught_main_thread_error
    threading.excepthook = log_uncaught_thread_error


def log_uncaught_main_thread_error(
    error_type: type[BaseException],
    error: BaseException,
    error_traceback: TracebackType | None,
) -> None:
    logger.critical(
        "App crashed with an uncaught error",
        exc_info=(error_type, error, error_traceback),
    )


def log_uncaught_thread_error(args: threading.ExceptHookArgs) -> None:
    if args.exc_value is None:
        return

    thread_name = args.thread.name if args.thread else "unknown"
    logger.error(
        f"Uncaught error in thread {thread_name}",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
