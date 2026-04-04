# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Rig mode translation editor screen."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, Select, Static

from potatui.config import Config

if TYPE_CHECKING:
    from potatui.flrig import FlrigClient
from potatui.mode_map import (
    ModeTranslations,
    auto_map,
    load_user_translations,
    save_translations,
)
from potatui.screens.logger_modals import MODES

_CANONICAL_OPTIONS: list[tuple[str, str]] = [("—", "")] + [(m, m) for m in MODES]


class ModeTranslationsScreen(Screen):
    """Full-screen editor for rig ↔ potatui mode translation tables."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    ModeTranslationsScreen {
        align: center top;
    }

    #mt-outer {
        width: 90;
        height: 100%;
        background: $surface;
        border: solid $primary;
    }

    #mt-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1 0;
        border-bottom: solid $primary-darken-2;
    }

    #mt-scroll {
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

    .field-hint {
        color: $text-muted;
        text-style: italic;
        height: auto;
        margin-bottom: 1;
    }

    #fetch-row {
        height: auto;
        margin-bottom: 1;
    }

    #fetch-status {
        width: 1fr;
        padding-top: 1;
        padding-left: 1;
        color: $text-muted;
        height: auto;
    }

    .mode-row {
        height: auto;
        margin-bottom: 1;
    }

    .rig-mode-label {
        width: 20;
        padding-top: 1;
        color: $text;
    }

    .canonical-select {
        width: 20;
    }

    .delete-btn {
        width: 5;
        margin-left: 1;
    }

    #add-row {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }

    #new-mode-input {
        width: 20;
    }

    #btn-add-mode {
        width: 10;
        margin-left: 1;
    }

    .out-mode-label {
        width: 20;
        padding-top: 1;
        color: $text;
    }

    .out-rig-input {
        width: 20;
    }

    #btn-row {
        height: auto;
        padding: 1 2;
        align: right middle;
        border-top: solid $primary-darken-2;
    }

    #mt-save-status {
        color: $success;
        padding: 0 1;
        height: auto;
        width: 1fr;
    }

    #btn-cancel {
        margin-right: 1;
    }

    #inbound-rows {
        height: auto;
    }

    #outbound-rows {
        height: auto;
    }
    """

    def __init__(
        self,
        config: Config,
        flrig_client: FlrigClient | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self._flrig_client = flrig_client  # live client from logger, or None
        # load_user_translations() returns only what was explicitly saved — no built-in
        # defaults injected into the inbound table.  If no file exists yet, inbound
        # starts empty so the user fetches from flrig or adds rows manually.
        self._translations = load_user_translations()
        # Track inbound rows: rig_mode_str → widget id suffix (sanitised)
        self._inbound_rows: list[str] = []

    # ── compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Container(id="mt-outer"):
            yield Static("Rig Mode Translations", id="mt-title")

            with ScrollableContainer(id="mt-scroll"):

                # ── Fetch ───────────────────────────────────────────────
                yield Static("Fetch from rig", classes="section-heading")
                yield Static("─" * 70, classes="section-rule")
                yield Static(
                    "Click to query flrig for your rig's mode list and auto-populate the table below.",
                    classes="field-hint",
                )
                with Horizontal(id="fetch-row"):
                    yield Button("Fetch from flrig", id="btn-fetch", variant="primary")
                    yield Static("", id="fetch-status")

                # ── Inbound ─────────────────────────────────────────────
                yield Static("Inbound — Rig → Potatui", classes="section-heading")
                yield Static("─" * 70, classes="section-rule")
                yield Static(
                    "When flrig reports this rig mode, Potatui displays the mapped canonical mode.",
                    classes="field-hint",
                )

                with Vertical(id="inbound-rows"):
                    for rig_mode, canonical in sorted(self._translations.rig_to_canonical.items()):
                        yield self._make_inbound_row(rig_mode, canonical)

                with Horizontal(id="add-row"):
                    yield Input(placeholder="Rig mode (e.g. CW-N)", id="new-mode-input")
                    yield Button("+ Add", id="btn-add-mode")

                # ── Outbound ────────────────────────────────────────────
                yield Static("Outbound — Potatui → Rig", classes="section-heading")
                yield Static("─" * 70, classes="section-rule")
                yield Static(
                    "When Potatui selects a mode, flrig is told to use this rig mode.",
                    classes="field-hint",
                )
                yield Static(
                    "SSB: leave blank to automatically choose USB (≥10 MHz) or LSB (<10 MHz).",
                    classes="field-hint",
                )

                with Vertical(id="outbound-rows"):
                    for canonical in MODES:
                        rig_mode = self._translations.canonical_to_rig.get(canonical, "")
                        yield self._make_outbound_row(canonical, rig_mode)

            with Horizontal(id="btn-row"):
                yield Static("", id="mt-save-status")
                yield Button("Cancel", id="btn-cancel")
                yield Button("Save", variant="primary", id="btn-save")

        yield Footer()

    # ── widget factories ───────────────────────────────────────────────────

    def _row_id(self, rig_mode: str) -> str:
        """Stable widget-id suffix for a rig mode string."""
        return rig_mode.replace(" ", "_").replace("-", "_").replace("/", "_")

    def _make_inbound_row(self, rig_mode: str, canonical: str) -> Horizontal:
        rid = self._row_id(rig_mode)
        self._inbound_rows.append(rig_mode)
        cur_val = canonical if canonical in MODES else ""
        return Horizontal(
            Label(rig_mode, classes="rig-mode-label"),
            Select(
                _CANONICAL_OPTIONS,
                value=cur_val,
                id=f"in-{rid}",
                classes="canonical-select",
            ),
            Button("✕", id=f"del-{rid}", classes="delete-btn"),
            classes="mode-row",
            id=f"row-{rid}",
        )

    def _make_outbound_row(self, canonical: str, rig_mode: str) -> Horizontal:
        return Horizontal(
            Label(canonical, classes="out-mode-label"),
            Input(
                value=rig_mode,
                placeholder="(auto)" if canonical == "SSB" else "",
                id=f"out-{canonical.lower()}",
                classes="out-rig-input",
            ),
            classes="mode-row",
        )

    # ── fetch worker ───────────────────────────────────────────────────────

    @work(exclusive=True, group="fetch-modes")
    async def _fetch_modes(self) -> None:
        self.query_one("#fetch-status", Static).update("Fetching…")
        self.query_one("#btn-fetch", Button).disabled = True

        try:
            if self._flrig_client is not None:
                flrig = self._flrig_client
                modes = await asyncio.to_thread(flrig.get_modes)
            else:
                from potatui.flrig import FlrigClient
                flrig = FlrigClient(self.config.flrig_host, self.config.flrig_port)
                modes = await asyncio.to_thread(flrig.get_modes)

            if modes is None:
                self.query_one("#fetch-status", Static).update("Could not connect to flrig.")
                return

            new_t = auto_map(modes)
            await self._apply_fetched(new_t, len(modes))

        except Exception as exc:
            self.query_one("#fetch-status", Static).update(f"Error: {exc}")
        finally:
            self.query_one("#btn-fetch", Button).disabled = False

    async def _apply_fetched(self, t: ModeTranslations, count: int) -> None:
        """Replace all inbound rows with fetched auto-mapped translations."""
        inbound = self.query_one("#inbound-rows", Vertical)

        # Await removal so widget IDs are fully released before mounting new rows
        await inbound.remove_children()
        self._inbound_rows.clear()

        # Add fetched rows
        for rig_mode, canonical in sorted(t.rig_to_canonical.items()):
            await inbound.mount(self._make_inbound_row(rig_mode, canonical))

        # Update outbound from fetched defaults
        for canonical, rig_mode in t.canonical_to_rig.items():
            try:
                inp = self.query_one(f"#out-{canonical.lower()}", Input)
                inp.value = rig_mode
            except Exception:
                pass

        self.query_one("#fetch-status", Static).update(
            f"Fetched {count} mode(s) from rig — mappings auto-populated."
        )

    # ── event handlers ─────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-fetch")
    def on_fetch(self) -> None:
        self._fetch_modes()

    @on(Button.Pressed, "#btn-add-mode")
    def on_add_mode(self) -> None:
        new_mode = self.query_one("#new-mode-input", Input).value.strip()
        if not new_mode:
            return
        if new_mode in self._inbound_rows:
            self.notify(f"{new_mode!r} already in list", severity="warning")
            return
        row = self._make_inbound_row(new_mode, "")
        self.query_one("#inbound-rows", Vertical).mount(row)
        self.query_one("#new-mode-input", Input).value = ""

    @on(Button.Pressed)
    def on_delete_row(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if not bid.startswith("del-"):
            return
        rid = bid[4:]  # suffix after "del-"
        # Find the rig_mode that maps to this rid
        for rig_mode in list(self._inbound_rows):
            if self._row_id(rig_mode) == rid:
                self._inbound_rows.remove(rig_mode)
                break
        try:
            self.query_one(f"#row-{rid}").remove()
        except Exception:
            pass

    @on(Button.Pressed, "#btn-save")
    def on_save_btn(self) -> None:
        self.action_save()

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel_btn(self) -> None:
        self.action_cancel()

    # ── collect + save ──────────────────────────────────────────────────────

    def _collect(self) -> ModeTranslations:
        r2c: dict[str, str] = {}
        for rig_mode in self._inbound_rows:
            rid = self._row_id(rig_mode)
            try:
                sel = self.query_one(f"#in-{rid}", Select)
                val = sel.value
                if val and val != Select.BLANK:
                    r2c[rig_mode] = str(val)
            except Exception:
                pass

        c2r: dict[str, str] = {}
        for canonical in MODES:
            try:
                inp = self.query_one(f"#out-{canonical.lower()}", Input)
                c2r[canonical] = inp.value.strip()
            except Exception:
                pass

        return ModeTranslations(rig_to_canonical=r2c, canonical_to_rig=c2r)

    def action_save(self) -> None:
        t = self._collect()
        save_translations(t)
        if self._flrig_client is not None:
            self._flrig_client.update_translations(t)
        self.dismiss()

    def action_cancel(self) -> None:
        self.dismiss()
