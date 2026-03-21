# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

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
    OptionList,
    Select,
    Static,
)
from textual.widgets.option_list import Option as OptionListOption

from potatui.config import Config
from potatui.pota_api import ParkInfo, is_valid_park_ref, lookup_park
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

    #state-row {
        display: none;
        height: auto;
        margin-bottom: 1;
    }

    #state-row.visible {
        display: block;
    }

    #park-suggestions {
        display: none;
        margin-left: 18;
        max-height: 10;
        border: solid $primary-darken-2;
    }

    #park-suggestions.visible {
        display: block;
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

    def __init__(self, config: Config, dismissable: bool = False) -> None:
        super().__init__()
        self.config = config
        self._dismissable = dismissable
        self._park_names: dict[str, str] = {}       # ref → name
        self._park_infos: dict[str, ParkInfo | None] = {}  # ref → ParkInfo (for multi-state detection)
        self._user_edited_grid: bool = False         # True once user types in grid field
        self._auto_fill_pending: int = 0             # counts in-flight programmatic grid fills

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
                    placeholder="Type to search, US-1234, or US-1234,US-6789",
                    id="park_refs",
                    classes="field-input",
                )
            yield OptionList(id="park-suggestions")
            yield Static("", id="park-lookup")

            with Horizontal(classes="field-row", id="state-row"):
                yield Label("Your State:", classes="field-label")
                yield Select(
                    [],
                    allow_blank=True,
                    id="my_state",
                    classes="field-input",
                )

            with Horizontal(classes="field-row"):
                yield Label("Grid Square:", classes="field-label")
                yield Input(
                    placeholder="auto-filled from park",
                    id="grid_sq",
                    classes="field-input",
                )

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

    @on(Input.Changed, "#grid_sq")
    def on_grid_sq_changed(self, event: Input.Changed) -> None:
        if self._auto_fill_pending > 0:
            self._auto_fill_pending -= 1
        else:
            self._user_edited_grid = True

    @staticmethod
    def _active_segment(value: str) -> str:
        """Return the segment currently being typed (text after the last comma)."""
        return value.split(",")[-1].strip()

    def _hide_suggestions(self) -> None:
        suggestions = self.query_one("#park-suggestions", OptionList)
        suggestions.remove_class("visible")
        suggestions.clear_options()

    @on(Input.Changed, "#park_refs")
    def on_park_refs_changed(self, event: Input.Changed) -> None:
        refs = [r.strip().upper() for r in event.value.split(",") if r.strip()]
        valid_refs = [r for r in refs if is_valid_park_ref(r)]
        if valid_refs:
            self._lookup_parks(valid_refs)
        else:
            self.query_one("#park-lookup", Static).update("")

        # Suggestion logic: search by name/ref when typing something that isn't a valid ref yet
        segment = self._active_segment(event.value)
        if len(segment) < 2 or is_valid_park_ref(segment):
            self._hide_suggestions()
            return
        from potatui.park_db import park_db
        if not park_db.loaded:
            self._hide_suggestions()
            return
        self._search_parks(segment)

    @work(exclusive=True)
    async def _lookup_parks(self, refs: list[str]) -> None:
        display = self.query_one("#park-lookup", Static)
        display.update("Looking up…")
        parts = []
        for ref in refs:
            if ref not in self._park_names:
                if self.config.offline_mode:
                    from potatui.park_db import park_db
                    info = park_db.lookup(ref) if park_db.loaded else None
                else:
                    info = await lookup_park(ref, self.config.pota_api_base)
                self._park_infos[ref] = info
                self._park_names[ref] = info.name if info else ("Unknown park (offline)" if self.config.offline_mode else "Unknown park")
            parts.append(f"{ref}: {self._park_names[ref]}")
        display.update("  |  ".join(parts))
        self._update_state_field(refs)
        # Auto-fill grid from first park if user hasn't overridden it
        if not self._user_edited_grid and refs:
            first_info = self._park_infos.get(refs[0])
            self._auto_fill_pending += 1
            self.query_one("#grid_sq", Input).value = first_info.grid if first_info else ""

    @work(exclusive=True)
    async def _search_parks(self, query: str) -> None:
        import asyncio

        from potatui.park_db import park_db
        results = await asyncio.to_thread(park_db.search_parks, query, 15)
        suggestions = self.query_one("#park-suggestions", OptionList)
        if not results:
            self._hide_suggestions()
            return
        suggestions.clear_options()
        for p in results:
            suggestions.add_option(OptionListOption(f"{p.name}  ({p.reference})", id=p.reference))
        suggestions.add_class("visible")

    @on(OptionList.OptionSelected, "#park-suggestions")
    def on_park_suggestion_selected(self, event: OptionList.OptionSelected) -> None:
        ref = event.option.id
        if not ref:
            return
        park_input = self.query_one("#park_refs", Input)
        current = park_input.value
        if "," in current:
            prefix = current.rsplit(",", 1)[0] + ","
            new_value = prefix + ref
        else:
            new_value = ref
        park_input.value = new_value
        self._hide_suggestions()
        park_input.focus()

    def on_key(self, event) -> None:
        focused = self.focused
        if focused is None:
            return
        suggestions = self.query_one("#park-suggestions", OptionList)
        visible = "visible" in suggestions.classes

        if getattr(focused, "id", None) == "park_refs":
            if event.key == "down" and visible:
                event.prevent_default()
                event.stop()
                suggestions.focus()
            elif event.key == "escape":
                event.prevent_default()
                event.stop()
                if visible:
                    self._hide_suggestions()
                elif self._dismissable:
                    self.dismiss()
        elif getattr(focused, "id", None) == "park-suggestions":
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._hide_suggestions()
                self.query_one("#park_refs", Input).focus()
        elif event.key == "escape" and self._dismissable and not visible:
            event.prevent_default()
            event.stop()
            self.dismiss()

    def _update_state_field(self, refs: list[str]) -> None:
        """Show the state dropdown if any looked-up park spans multiple states."""
        all_locations: list[str] = []
        is_multi = False
        for ref in refs:
            info = self._park_infos.get(ref)
            if info and info.locations:
                if len(info.locations) > 1:
                    is_multi = True
                for loc in info.locations:
                    if loc not in all_locations:
                        all_locations.append(loc)

        state_row = self.query_one("#state-row")
        state_sel = self.query_one("#my_state", Select)
        if is_multi:
            state_row.add_class("visible")
            state_sel.set_options([(s, s) for s in all_locations])
            if len(all_locations) == 1:
                state_sel.value = all_locations[0]
        else:
            state_row.remove_class("visible")
            state_sel.set_options([])

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
        grid_sq = self.query_one("#grid_sq", Input).value.strip().upper()
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

        self._validate_and_launch(callsign, refs, grid_sq, power_w, rig, antenna)

    @work(exclusive=True)
    async def _validate_and_launch(
        self,
        callsign: str,
        refs: list[str],
        grid_sq: str,
        power_w: int,
        rig: str,
        antenna: str,
    ) -> None:
        from datetime import datetime

        error = self.query_one("#error-msg", Static)

        # Fetch any refs that weren't already looked up live.
        park_names: dict[str, str] = {}
        newly_fetched = False
        for ref in refs:
            if ref in self._park_names:
                park_names[ref] = self._park_names[ref]
            else:
                if self.config.offline_mode:
                    from potatui.park_db import park_db
                    info = park_db.lookup(ref) if park_db.loaded else None
                else:
                    info = await lookup_park(ref, self.config.pota_api_base)
                self._park_infos[ref] = info
                self._park_names[ref] = info.name if info else "Unknown (offline)" if self.config.offline_mode else "Unknown (API unavailable)"
                park_names[ref] = self._park_names[ref]
                newly_fetched = True

        # If we just fetched new parks, update the state field now
        if newly_fetched:
            self._update_state_field(refs)

        state_row = self.query_one("#state-row")
        state_sel = self.query_one("#my_state", Select)
        if "visible" in state_row.classes:
            my_state = "" if state_sel.value is Select.BLANK else str(state_sel.value)
        else:
            my_state = ""

        # If the state row is visible a selection is required
        if "visible" in state_row.classes and not my_state:
            error.update("Select your state for this multi-state park.")
            return

        session = Session(
            operator=callsign,
            station_callsign=callsign,
            park_refs=refs,
            active_park_ref=refs[0],
            grid=grid_sq,
            rig=rig,
            antenna=antenna,
            power_w=power_w,
            start_time=datetime.utcnow(),
            my_state=my_state,
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
