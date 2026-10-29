# LEARN: YOU ARE HERE
#   main.py at startup ▶ THIS FILE: is the app already running?
#   yes → that copy comes forward, this one quits
#   no  → listen for future launches while the app runs
#   read next → app/state.py
"""
Only one copy of the app runs at a time.

LEARN: how the two copies talk (industry term: "single instance lock")

  launch 2 ── connect ──▶ .instance.sock ──▶ launch 1 brings its window forward
     │
     └── nobody answers ──▶ launch 2 becomes the running app

  socket = a two-way "phone line" between programs
  Unix socket = one that only works on this Mac, and looks like a file
"""

# LEARN: contextlib.suppress(Err) = "ignore Err inside this with-block"
#   a short form of try: … except Err: pass
import contextlib
import logging
import socket
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# b"…" = bytes (sockets send raw bytes, not text)
FOCUS_MESSAGE = b"focus"
CONNECT_TIMEOUT_SECONDS = 1.0


class SingleInstanceGuard:
    """
    LEARN: makes sure only one copy of the app runs

    made by → main.py, once at startup
    """

    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path
        # the listening socket; None until we start listening
        self._server: socket.socket | None = None

    def ask_running_instance_to_focus(self) -> bool:
        """
        LEARN: try to reach an already running copy

        called by → main.py, first thing after logging is set up
        gives back → True = another copy answered → this launch should quit
        """
        # AF_UNIX = local (file-style) socket; SOCK_STREAM = a steady
        #   two-way connection (like a phone call, not a postcard)
        # "with … as client" → the socket is closed automatically after
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(CONNECT_TIMEOUT_SECONDS)
            try:
                client.connect(str(self._socket_path))
                client.sendall(FOCUS_MESSAGE)
            # nobody listening (or no socket file) → we're the only copy
            except OSError:
                return False

        return True

    def start_listening_for_focus_requests(self, on_focus: Callable[[], None]) -> None:
        """
        LEARN: wait for future launches, in the background

        called by → main.py, once the window exists
        on_focus = the function to run when a 2nd launch calls
          (main.py passes "bring the window to the front")
          Callable[[], None] = a function with no inputs that returns nothing
        """
        # a socket file left by a crash would block bind(), and nobody is
        # listening on it (the connect attempt above just failed)
        self._socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # bind = claim the address (creates the .instance.sock file)
        # listen = start accepting calls
        server.bind(str(self._socket_path))
        server.listen()
        self._server = server
        # background thread so waiting for calls never freezes the window
        # daemon=True → it won't keep the app alive at exit
        threading.Thread(
            target=self._accept_focus_requests,
            args=(server, on_focus),
            name="single-instance",
            daemon=True,
        ).start()

    def stop_listening_for_focus_requests(self) -> None:
        # called by → main.py, after the window closes
        if self._server is not None:
            self._server.close()
            self._server = None

        # remove the socket file → the next launch starts fresh
        self._socket_path.unlink(missing_ok=True)

    def _accept_focus_requests(
        self, server: socket.socket, on_focus: Callable[[], None]
    ) -> None:
        # runs on the background thread for as long as the app is open
        while True:
            try:
                # accept() waits until someone connects; gives back
                # (connection, their address) → address not needed: _
                connection, _ = server.accept()
            except OSError:
                # the socket was closed on shutdown → stop the loop
                return

            # two context managers in one with: close the connection after,
            # and ignore errors from a caller that hung up early
            with connection, contextlib.suppress(OSError):
                if connection.recv(len(FOCUS_MESSAGE)) == FOCUS_MESSAGE:
                    logger.info("Second launch detected, bringing window forward")
                    on_focus()
