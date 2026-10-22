"""
Only one copy of the app runs at a time.

LEARN: the first launch listens on a Unix socket. A second launch tries to
connect: if someone answers, it sends "focus" and quits.

  launch 2 ── connect ──▶ socket ──▶ launch 1 brings its window forward
     │
     └── nobody answers ──▶ launch 2 becomes the running app
"""

import contextlib
import logging
import socket
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

FOCUS_MESSAGE = b"focus"
CONNECT_TIMEOUT_SECONDS = 1.0


class SingleInstanceGuard:
    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path
        self._server: socket.socket | None = None

    def ask_running_instance_to_focus(self) -> bool:
        """
        Tell an already running app to come forward.

        Returns:
            bool: True when another instance answered, so this launch should quit.
        """
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(CONNECT_TIMEOUT_SECONDS)
            try:
                client.connect(str(self._socket_path))
                client.sendall(FOCUS_MESSAGE)
            except OSError:
                return False

        return True

    def start_listening_for_focus_requests(self, on_focus: Callable[[], None]) -> None:
        # a socket file left by a crash would block binding, and nobody is
        # listening on it (the connect attempt above just failed)
        self._socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self._socket_path))
        server.listen()
        self._server = server
        threading.Thread(
            target=self._accept_focus_requests,
            args=(server, on_focus),
            name="single-instance",
            daemon=True,
        ).start()

    def stop_listening_for_focus_requests(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None

        self._socket_path.unlink(missing_ok=True)

    def _accept_focus_requests(
        self, server: socket.socket, on_focus: Callable[[], None]
    ) -> None:
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                # the socket was closed on shutdown
                return

            with connection, contextlib.suppress(OSError):
                if connection.recv(len(FOCUS_MESSAGE)) == FOCUS_MESSAGE:
                    logger.info("Second launch detected, bringing window forward")
                    on_focus()
