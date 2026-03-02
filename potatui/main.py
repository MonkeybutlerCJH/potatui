"""Entry point — Textual app class."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from potatui.config import load_config, save_config


class PotaLogApp(App):
    """POTA activation logging TUI."""

    TITLE = "Potatui"
    SUB_TITLE = "Parks on the Air Logger"

    def on_mount(self) -> None:
        self._config = load_config()
        self._config.log_dir_path.mkdir(parents=True, exist_ok=True)

        if self._config.theme:
            self.theme = self._config.theme

        if not self._config.callsign:
            # First run — show settings before anything else.
            from potatui.screens.settings import SettingsScreen
            self.push_screen(
                SettingsScreen(self._config, first_run=True),
                callback=self._after_settings,
            )
        else:
            self._go_to_start()

    def _after_settings(self, _result: object = None) -> None:
        """Called when the settings screen is dismissed on first run."""
        self._go_to_start()

    def _go_to_start(self) -> None:
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
    app = PotaLogApp()
    app.run()


if __name__ == "__main__":
    run()
