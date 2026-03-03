"""Modal for downloading / refreshing the local POTA park database."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ParkDbModal(ModalScreen[bool]):
    """Prompt to download (or refresh) the local POTA park database CSV."""

    CSS = """
    ParkDbModal {
        align: center middle;
    }

    #park-db-box {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #park-db-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #park-db-desc {
        height: auto;
        margin-bottom: 1;
    }

    #park-db-status {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
        text-style: italic;
    }

    #park-db-status.error {
        color: $error;
        text-style: none;
    }

    #park-db-status.success {
        color: $success;
        text-style: none;
    }

    #park-db-btn-row {
        height: auto;
        margin-top: 1;
        align: right middle;
    }

    #park-db-btn-row Button {
        margin-left: 1;
    }
    """

    def __init__(self, is_refresh: bool = False) -> None:
        super().__init__()
        self._is_refresh = is_refresh
        self._downloading = False
        self._download_done = False

    def compose(self) -> ComposeResult:
        if self._is_refresh:
            title = "Park Database Update"
            desc = (
                "Your local POTA park database is over 30 days old.\n\n"
                "Downloading a fresh copy ensures you have the latest\n"
                "park names and locations available offline."
            )
            yes_label = "Update (~4 MB)"
        else:
            title = "POTA Park Database"
            desc = (
                "Potatui can cache park information locally so lookups\n"
                "work without internet during activations.\n\n"
                "Download the POTA park database now? (~4 MB)"
            )
            yes_label = "Download"

        with Vertical(id="park-db-box"):
            yield Static(title, id="park-db-title")
            yield Static(desc, id="park-db-desc")
            yield Static("", id="park-db-status")
            with Horizontal(id="park-db-btn-row"):
                yield Button(yes_label, variant="primary", id="btn-yes")
                yield Button("Skip" if not self._is_refresh else "Not Now", id="btn-skip")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-skip":
            self.dismiss(False)
        elif event.button.id == "btn-yes":
            if self._download_done:
                self.dismiss(True)
            elif not self._downloading:
                self._start_download()

    @work
    async def _start_download(self) -> None:
        from potatui.park_db import download_parks

        self._downloading = True
        status = self.query_one("#park-db-status", Static)
        yes_btn = self.query_one("#btn-yes", Button)
        skip_btn = self.query_one("#btn-skip", Button)

        yes_btn.disabled = True
        skip_btn.disabled = True
        status.remove_class("error", "success")
        status.update("Downloading… (this may take a moment)")

        success, message = await download_parks()
        self._downloading = False

        if success:
            self._download_done = True
            status.add_class("success")
            status.update(f"Done! {message}")
            yes_btn.label = "Continue"
            yes_btn.disabled = False
        else:
            status.add_class("error")
            status.update(f"Failed: {message}")
            yes_btn.label = "Retry"
            yes_btn.disabled = False
            skip_btn.disabled = False
