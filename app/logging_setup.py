# LEARN: YOU ARE HERE
#   main.py at startup ▶ THIS FILE sets up logging
#   ▶ every logger.info / .warning / .error in the app ▶ logs/app.log + terminal
#   read next → app/single_instance.py
"""Log file setup: one rotating file plus the terminal."""

# LEARN: logging = Python's built-in way to record what the app is doing
#   logger.info("…")    → normal milestone
#   logger.warning("…") → something's off, app copes
#   logger.error("…")   → something failed
#   each file does: logger = logging.getLogger(__name__)
#   → all of them feed the "root" logger set up here
import logging
import sys
import threading
from dataclasses import dataclass

# LEARN: handler = where log lines GO (a file, the terminal, …)
#   RotatingFileHandler = a file that rolls over when it gets big
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from app.config import AppSettings

LOG_FILE_NAME = "app.log"
# 1_000_000 = 1000000 (underscores are allowed in numbers, just for reading)
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3
# LEARN: the look of each line, with {} placeholders filled by logging:
#   2026-10-22 22:12:01 INFO    [app.main] Starting …
#   {levelname:<7} → level name, padded to 7 characters (lines stay aligned)
LOG_FORMAT = "{asctime} {levelname:<7} [{name}] {message}"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger(__name__)


class ErrorCountingHandler(logging.Handler):
    """
    LEARN: counts ERROR (and worse) log lines, for the red badge on Logs

    a handler normally writes lines somewhere; this one only counts them
    made by → configure_app_logging; read by → bridge (shell.js asks)

      errors logged:   ●●●●●
      seen so far:     ●●●        → unseen = 2 → badge shows 2
      open the Logs tool → mark_all_errors_seen() → badge gone

    lock → log lines arrive from many threads at once
    """

    def __init__(self) -> None:
        # level=ERROR → WARNING and INFO lines never reach emit
        super().__init__(level=logging.ERROR)
        self._count_lock = threading.Lock()
        self._error_count = 0
        self._seen_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        # called by → Python's logging, once per ERROR / CRITICAL line
        with self._count_lock:
            self._error_count += 1

    def count_unseen_errors(self) -> int:
        with self._count_lock:
            return self._error_count - self._seen_count

    def mark_all_errors_seen(self) -> None:
        with self._count_lock:
            self._seen_count = self._error_count


@dataclass(frozen=True)
class LoggingSetup:
    """LEARN: what configure_app_logging hands back to main.py."""

    log_file: Path
    error_counter: ErrorCountingHandler


def configure_app_logging(settings: AppSettings) -> LoggingSetup:
    """
    LEARN: send every log line to logs/app.log AND the terminal

    called by → main.py, once at startup
    gives back → the log file path + the error counter (for the Logs badge)

    rotation (industry term "log rotation") → the file never grows forever

      app.log reaches 1 MB
        app.log ──▶ app.log.1 ──▶ app.log.2 ──▶ app.log.3 ──▶ deleted ✗
        a fresh app.log starts
    """
    log_dir = settings.resolve_log_dir()
    # parents=True → make missing parent folders too
    # exist_ok=True → no error if it's already there
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME

    # style="{" → the format above uses {name} placeholders (not %(name)s)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, style="{")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    # StreamHandler() → prints to the terminal (where make start_app runs)
    terminal_handler = logging.StreamHandler()
    terminal_handler.setFormatter(formatter)

    # LEARN: the root logger = the top of the tree; every module's logger
    #   passes its lines up to it → set up handlers once, here
    root = logging.getLogger()
    root.handlers.clear()
    # level = the cutoff: INFO → shows INFO, WARNING, ERROR (not DEBUG)
    root.setLevel(settings.log_level)
    root.addHandler(file_handler)
    root.addHandler(terminal_handler)
    error_counter = ErrorCountingHandler()
    root.addHandler(error_counter)
    # pywebview's own debug chatter is only useful when debugging pywebview
    logging.getLogger("pywebview").setLevel(logging.WARNING)

    install_crash_logging()
    return LoggingSetup(log_file=log_file, error_counter=error_counter)


def install_crash_logging() -> None:
    """
    LEARN: make sure a crash always leaves its reason in the log

    excepthook = a function Python calls for any error NOBODY caught
      replacing it → we log the full traceback before the app dies
      traceback = the list of calls that led to the error (where it broke)
    """
    # LEARN: assigning a function WITHOUT () → "use this function later"
    #   (with () it would run right now)
    sys.excepthook = log_uncaught_main_thread_error
    # background threads have their own hook
    threading.excepthook = log_uncaught_thread_error


def log_uncaught_main_thread_error(
    error_type: type[BaseException],
    error: BaseException,
    error_traceback: TracebackType | None,
) -> None:
    # called by → Python, when the main thread crashes
    # exc_info=(…) → attach the full traceback to the log line
    logger.critical(
        "App crashed with an uncaught error",
        exc_info=(error_type, error, error_traceback),
    )


def log_uncaught_thread_error(args: threading.ExceptHookArgs) -> None:
    # called by → Python, when a background thread crashes
    if args.exc_value is None:
        return

    thread_name = args.thread.name if args.thread else "unknown"
    logger.error(
        f"Uncaught error in thread {thread_name}",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
