"""Activation setup screen."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Static,
)

from potatui.config import Config
from potatui.pota_api import is_valid_park_ref, lookup_park
from potatui.session import Session


class SetupScreen(Screen):
    """Initial activation setup form."""

    BINDINGS = [
        Binding("f8", "settings", "Settings"),
    ]

    CSS = """
    SetupScreen {
        align: center middle;
    }

    #setup-container {
        width: 70;
        height: auto;
        border: solid $primary;
        padding: 1 2;
        background: $surface;
    }

    #setup-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .field-row {
        height: auto;
        margin-bottom: 1;
    }

    .field-label {
        width: 18;
        padding-top: 1;
        color: $text-muted;
    }

    .field-input {
        width: 1fr;
    }

    #park-lookup {
        height: auto;
        margin-bottom: 1;
        padding-left: 18;
        color: $success;
        text-style: italic;
    }

    #error-msg {
        color: $error;
        height: auto;
        margin-bottom: 1;
    }

    #btn-row {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    """

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._park_names: dict[str, str] = {}  # ref → name, populated by live lookup

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="setup-container"):
            yield Static("POTA Activation Setup", id="setup-title")

            with Horizontal(classes="field-row"):
                yield Label("Callsign:", classes="field-label")
                yield Input(
                    value=self.config.callsign,
                    placeholder="W1AW",
                    id="callsign",
                    classes="field-input",
                )

            with Horizontal(classes="field-row"):
                yield Label("Park Ref(s):", classes="field-label")
                yield Input(
                    placeholder="US-1234 or US-1234,US-5678",
                    id="park_refs",
                    classes="field-input",
                )
            yield Static("", id="park-lookup")

            with Horizontal(classes="field-row"):
                yield Label("Power (W):", classes="field-label")
                yield Input(
                    value=str(self.config.power_w),
                    placeholder="100",
                    id="power_w",
                    classes="field-input",
                )

            with Horizontal(classes="field-row"):
                yield Label("Rig:", classes="field-label")
                yield Input(
                    value=self.config.rig,
                    placeholder="IC-7300",
                    id="rig",
                    classes="field-input",
                )

            with Horizontal(classes="field-row"):
                yield Label("Antenna:", classes="field-label")
                yield Input(
                    value=self.config.antenna,
                    placeholder="EFHW",
                    id="antenna",
                    classes="field-input",
                )

            yield Static("", id="error-msg")

            with Horizontal(id="btn-row"):
                yield Button("Start Activation", variant="primary", id="btn-start")

        yield Footer()

    @on(Input.Changed, "#park_refs")
    def on_park_refs_changed(self, event: Input.Changed) -> None:
        refs = [r.strip().upper() for r in event.value.split(",") if r.strip()]
        valid_refs = [r for r in refs if is_valid_park_ref(r)]
        if valid_refs:
            self._lookup_parks(valid_refs)
        else:
            self.query_one("#park-lookup", Static).update("")

    @work(exclusive=True)
    async def _lookup_parks(self, refs: list[str]) -> None:
        display = self.query_one("#park-lookup", Static)
        display.update("Looking up…")
        parts = []
        for ref in refs:
            if ref not in self._park_names:
                info = await lookup_park(ref, self.config.pota_api_base)
                self._park_names[ref] = info.name if info else "Unknown park"
            parts.append(f"{ref}: {self._park_names[ref]}")
        display.update("  |  ".join(parts))

    @on(Button.Pressed, "#btn-start")
    def on_start(self) -> None:
        self._submit()

    @on(Input.Submitted)
    def on_input_submitted(self) -> None:
        self._submit()

    def _submit(self) -> None:
        error = self.query_one("#error-msg", Static)
        error.update("")

        callsign = self.query_one("#callsign", Input).value.strip().upper()
        park_refs_raw = self.query_one("#park_refs", Input).value.strip()
        power_str = self.query_one("#power_w", Input).value.strip()
        rig = self.query_one("#rig", Input).value.strip()
        antenna = self.query_one("#antenna", Input).value.strip()

        if not callsign:
            error.update("Callsign is required.")
            return
        if not park_refs_raw:
            error.update("At least one park reference is required.")
            return

        refs = [r.strip().upper() for r in park_refs_raw.split(",") if r.strip()]
        for ref in refs:
            if not is_valid_park_ref(ref):
                error.update(f"Invalid park reference: {ref}  (expected format: US-1234)")
                return

        try:
            power_w = int(power_str) if power_str else self.config.power_w
        except ValueError:
            power_w = self.config.power_w

        self._validate_and_launch(callsign, refs, power_w, rig, antenna)

    @work(exclusive=True)
    async def _validate_and_launch(
        self,
        callsign: str,
        refs: list[str],
        power_w: int,
        rig: str,
        antenna: str,
    ) -> None:
        from datetime import datetime

        error = self.query_one("#error-msg", Static)

        # Fetch any refs that weren't already looked up live.
        park_names: dict[str, str] = {}
        for ref in refs:
            if ref in self._park_names:
                park_names[ref] = self._park_names[ref]
            else:
                info = await lookup_park(ref, self.config.pota_api_base)
                park_names[ref] = info.name if info else "Unknown (API unavailable)"

        session = Session(
            operator=callsign,
            park_refs=refs,
            active_park_ref=refs[0],
            grid=self.config.grid,
            rig=rig,
            antenna=antenna,
            power_w=power_w,
            start_time=datetime.utcnow(),
        )

        from potatui.screens.logger import LoggerScreen

        self.app.push_screen(
            LoggerScreen(
                session=session,
                config=self.config,
                park_names=park_names,
            )
        )

    def action_settings(self) -> None:
        from potatui.screens.settings import SettingsScreen
        self.app.push_screen(SettingsScreen(self.config))
