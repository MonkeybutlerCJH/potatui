# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Settings screen — edit and save pota-log configuration."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, Select, Static

from potatui.config import CONFIG_PATH, Config, save_config


class SettingsScreen(Screen):
    """Full-screen settings editor.  Ctrl+S saves, Escape cancels."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    SettingsScreen {
        align: center top;
    }

    #settings-outer {
        width: 80;
        height: 100%;
        background: $surface;
        border: solid $primary;
    }

    #settings-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1 0;
        border-bottom: solid $primary-darken-2;
    }

    #settings-scroll {
        height: 1fr;
        padding: 1 2;
    }

    .section-heading {
        text-style: bold;
        color: $accent;
        margin-top: 1;
        margin-bottom: 0;
    }

    .section-rule {
        color: $primary-darken-2;
        margin-bottom: 1;
    }

    .field-row {
        height: auto;
        margin-bottom: 1;
    }

    .field-label {
        width: 20;
        padding-top: 1;
        color: $text-muted;
    }

    .field-input {
        width: 1fr;
    }

    .field-hint {
        color: $text-muted;
        text-style: italic;
        padding-left: 20;
        height: auto;
    }

    #btn-row {
        height: auto;
        padding: 1 2;
        align: right middle;
        border-top: solid $primary-darken-2;
    }

    #btn-cancel {
        margin-right: 1;
    }

    #save-status {
        color: $success;
        padding: 0 1;
        height: auto;
        width: 1fr;
    }
    """

    def __init__(self, config: Config, first_run: bool = False) -> None:
        super().__init__()
        self.config = config
        self.first_run = first_run

    def compose(self) -> ComposeResult:
        with Container(id="settings-outer"):
            title = "Welcome to Potatui — Let's set up your station" if self.first_run else "Settings"
            yield Static(title, id="settings-title")

            with ScrollableContainer(id="settings-scroll"):

                # ── Operator ────────────────────────────────────────────
                yield Static("Operator", classes="section-heading")
                yield Static("─" * 60, classes="section-rule")

                with Horizontal(classes="field-row"):
                    yield Label("Callsign:", classes="field-label")
                    yield Input(value=self.config.callsign, placeholder="W1AW", id="s-callsign", classes="field-input")

                with Horizontal(classes="field-row"):
                    yield Label("Distance Units:", classes="field-label")
                    yield Select(
                        [("Miles (mi)", "mi"), ("Kilometres (km)", "km")],
                        value=self.config.distance_unit if self.config.distance_unit in ("mi", "km") else "mi",
                        id="s-distance-unit",
                        classes="field-input",
                    )

                # ── Log Files ───────────────────────────────────────────
                yield Static("Log Files", classes="section-heading")
                yield Static("─" * 60, classes="section-rule")

                with Horizontal(classes="field-row"):
                    yield Label("Log Directory:", classes="field-label")
                    yield Input(value=self.config.log_dir, placeholder="~/potatui-logs", id="s-log-dir", classes="field-input")
                yield Static("ADIF and session files are saved here. ~ is supported.", classes="field-hint")

                # ── Rig ─────────────────────────────────────────────────
                yield Static("Rig", classes="section-heading")
                yield Static("─" * 60, classes="section-rule")

                with Horizontal(classes="field-row"):
                    yield Label("Rig:", classes="field-label")
                    yield Input(value=self.config.rig, placeholder="Yaesu FT-710", id="s-rig", classes="field-input")

                with Horizontal(classes="field-row"):
                    yield Label("Antenna:", classes="field-label")
                    yield Input(value=self.config.antenna, placeholder="EFHW", id="s-antenna", classes="field-input")

                with Horizontal(classes="field-row"):
                    yield Label("Power (W):", classes="field-label")
                    yield Input(value=str(self.config.power_w), placeholder="100", id="s-power", classes="field-input")

                # ── flrig ───────────────────────────────────────────────
                yield Static("flrig Integration", classes="section-heading")
                yield Static("─" * 60, classes="section-rule")

                with Horizontal(classes="field-row"):
                    yield Label("Host:", classes="field-label")
                    yield Input(value=self.config.flrig_host, placeholder="localhost", id="s-flrig-host", classes="field-input")

                with Horizontal(classes="field-row"):
                    yield Label("Port:", classes="field-label")
                    yield Input(value=str(self.config.flrig_port), placeholder="12345", id="s-flrig-port", classes="field-input")
                yield Static("Start flrig before launching pota-log. Leave defaults if running locally.", classes="field-hint")

                # ── QRZ ─────────────────────────────────────────────────
                yield Static("QRZ (Optional)", classes="section-heading")
                yield Static("─" * 60, classes="section-rule")
                yield Static("Enables callsign info strip with name, location, and distance.", classes="field-hint")

                with Horizontal(classes="field-row"):
                    yield Label("Username:", classes="field-label")
                    yield Input(value=self.config.qrz_username, placeholder="W1AW", id="s-qrz-user", classes="field-input")

                with Horizontal(classes="field-row"):
                    yield Label("Password:", classes="field-label")
                    yield Input(value=self.config.qrz_password, password=True, id="s-qrz-pass", classes="field-input")

                with Horizontal(classes="field-row"):
                    yield Label("API URL:", classes="field-label")
                    yield Input(value=self.config.qrz_api_url, placeholder="https://xmldata.qrz.com/xml/current/", id="s-qrz-url", classes="field-input")
                yield Static("Leave as default unless using an alternative QRZ endpoint.", classes="field-hint")

                # ── Config path ─────────────────────────────────────────
                yield Static("─" * 60, classes="section-rule")
                yield Static(f"Config file: {CONFIG_PATH}", classes="field-hint", id="config-path-hint")

            with Horizontal(id="btn-row"):
                yield Static("", id="save-status")
                yield Button("Cancel", id="btn-cancel")
                yield Button("Save", variant="primary", id="btn-save")

        yield Footer()

    # ── helpers ────────────────────────────────────────────────────────

    def _collect(self) -> Config | str:
        """Read all fields and return an updated Config, or an error string."""
        def val(widget_id: str) -> str:
            return self.query_one(f"#{widget_id}", Input).value.strip()

        callsign = val("s-callsign").upper()
        dist_sel = self.query_one("#s-distance-unit", Select)
        distance_unit = str(dist_sel.value) if dist_sel.value != Select.BLANK else "mi"
        log_dir = val("s-log-dir") or "~/potatui-logs"
        rig = val("s-rig")
        antenna = val("s-antenna")
        flrig_host = val("s-flrig-host") or "localhost"
        qrz_user = val("s-qrz-user")
        qrz_pass = self.query_one("#s-qrz-pass", Input).value  # preserve as-is
        qrz_url = val("s-qrz-url") or "https://xmldata.qrz.com/xml/current/"

        try:
            power_w = int(val("s-power") or "100")
        except ValueError:
            return "Power must be a whole number (e.g. 100)."

        try:
            flrig_port = int(val("s-flrig-port") or "12345")
        except ValueError:
            return "flrig port must be a number (e.g. 12345)."

        cfg = Config(
            callsign=callsign,
            grid=self.config.grid,  # preserved from existing config, no longer editable in UI
            distance_unit=distance_unit,
            log_dir=log_dir,
            rig=rig,
            antenna=antenna,
            power_w=power_w,
            flrig_host=flrig_host,
            flrig_port=flrig_port,
            qrz_username=qrz_user,
            qrz_password=qrz_pass,
            qrz_api_url=qrz_url,
            # vk1–vk5 preserved as-is; commands are now managed via the Commander (F7).
            vk1=self.config.vk1, vk2=self.config.vk2, vk3=self.config.vk3,
            vk4=self.config.vk4, vk5=self.config.vk5,
            pota_api_base=self.config.pota_api_base,
        )
        return cfg

    def _do_save(self) -> None:
        result = self._collect()
        if isinstance(result, str):
            self.query_one("#save-status", Static).update(result)
            return

        # Update the shared config object in-place so callers see the changes.
        for field in result.__dataclass_fields__:
            setattr(self.config, field, getattr(result, field))

        save_config(self.config)
        self.config.log_dir_path.mkdir(parents=True, exist_ok=True)

        if self.first_run:
            # Continue to normal startup flow — dismiss triggers the callback.
            self.dismiss()
        else:
            self.query_one("#save-status", Static).update("Saved.")

    # ── actions / events ───────────────────────────────────────────────

    def action_cancel(self) -> None:
        self.dismiss()

    def action_save(self) -> None:
        self._do_save()

    @on(Button.Pressed, "#btn-save")
    def on_save(self) -> None:
        self._do_save()

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel(self) -> None:
        self.dismiss()
