# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Entry point — Textual app class."""

from __future__ import annotations

import asyncio
import os
import socket
import sys

from textual.app import App

from potatui.config import load_config, save_config

# Arbitrary port used as a single-instance lock (loopback only).
_LOCK_PORT = 47832
_lock_socket: socket.socket | None = None


def _acquire_instance_lock() -> bool:
    """Try to bind a loopback socket to enforce single-instance.

    Returns True if this is the only running instance, False otherwise.
    The bound socket is kept in _lock_socket for the process lifetime.
    """
    global _lock_socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", _LOCK_PORT))
        sock.listen(1)
        _lock_socket = sock
        return True
    except OSError:
        sock.close()
        return False


class PotaLogApp(App):
    """POTA activation logging TUI."""

    TITLE = "Potatui"
    SUB_TITLE = "Parks on the Air Logger"

    def on_mount(self) -> None:
        self._config = load_config()
        self._config.log_dir_path.mkdir(parents=True, exist_ok=True)

        from potatui.log import setup_logging
        setup_logging(self._config.log_dir_path, enabled=self._config.debug_logging)

        if self._config.theme:
            self.theme = self._config.theme

        # Load the local park database from disk (fast, synchronous).
        from potatui.park_db import park_db
        park_db.load()

        if not self._config.callsign:
            # First run — show settings before anything else.
            from potatui.screens.settings import SettingsScreen
            self.push_screen(
                SettingsScreen(self._config, first_run=True),
                callback=self._after_settings,
            )
        else:
            self._check_park_db()

    def _after_settings(self, _result: object = None) -> None:
        """Called when the settings screen is dismissed on first run."""
        self._check_park_db()

    def _check_park_db(self) -> None:
        """Show the park DB download/refresh modal if needed, else proceed."""
        if self._config.offline_mode:
            self._continue_to_start()
            return

        from potatui.park_db import park_db
        from potatui.screens.park_update import ParkDbModal

        if park_db.needs_download():
            self.push_screen(ParkDbModal(is_refresh=False), callback=self._after_park_db)
        elif park_db.needs_refresh():
            self.push_screen(ParkDbModal(is_refresh=True), callback=self._after_park_db)
        else:
            self._continue_to_start()

    def _after_park_db(self, downloaded: bool | None) -> None:
        """Called after the park DB modal is dismissed."""
        if downloaded:
            from potatui.park_db import park_db
            park_db.load()
        self._continue_to_start()

    def _continue_to_start(self) -> None:
        from potatui.screens.resume import find_saved_sessions
        sessions = find_saved_sessions(self._config.log_dir_path)

        if sessions:
            from potatui.screens.resume import ResumeScreen
            self.push_screen(ResumeScreen(self._config, sessions))
        else:
            from potatui.screens.setup import SetupScreen
            self.push_screen(SetupScreen(self._config))


    def watch_theme(self, theme: str) -> None:
        """Persist theme changes to config immediately."""
        if hasattr(self, "_config"):
            self._config.theme = theme
            save_config(self._config)


def run() -> None:
    if sys.platform == "win32":
        # Reduce ConPTY encoding overhead.
        os.environ.setdefault("PYTHONUTF8", "1")
        # Cap render rate — 60fps default hammers ConPTY on Windows.
        # Controlled via TEXTUAL_FPS (textual.constants.MAX_FPS).
        os.environ.setdefault("TEXTUAL_FPS", "10")
        # Textual animations add render work with no value on ConPTY.
        os.environ.setdefault("TEXTUAL_ANIMATIONS", "none")
        # SelectorEventLoop has lower overhead than the default ProactorEventLoop
        # (IOCP) for the short, frequent socket reads that Textual and the QRZ/
        # HamDB thread-pool pattern produce.  Trade-off: ProactorEventLoop is
        # required for asyncio subprocess pipes; any subprocess interaction here
        # (Commander) uses subprocess.run in a thread, not asyncio subprocesses,
        # so this is safe for the current codebase.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    if not _acquire_instance_lock():
        print("Potatui is already running.", file=sys.stderr)
        sys.exit(1)
    app = PotaLogApp()
    app.run()


if __name__ == "__main__":
    run()
