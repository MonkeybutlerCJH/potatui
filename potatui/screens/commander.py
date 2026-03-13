# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Commander modal — fire and configure CAT and console command slots."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static, TabbedContent, TabPane

from potatui.commands import (
    NUM_SLOTS,
    RESERVED_KEYS,
    CommandConfig,
    CommandSlot,
    save_commands,
)

if TYPE_CHECKING:
    from potatui.flrig import FlrigClient


class CommanderModal(ModalScreen[None]):
    """Two-tab modal for firing and configuring CAT and console command slots."""

    CSS = """
    CommanderModal { align: center middle; }

    #cmd-box {
        width: 100;
        height: auto;
        max-height: 90%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #cmd-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .slot-row {
        height: 3;
    }

    .slot-num {
        width: 3;
        padding-top: 1;
        color: $text-muted;
    }

    .slot-label-input {
        width: 18;
        margin-right: 1;
    }

    .slot-cmd-input {
        width: 1fr;
        margin-right: 1;
    }

    .slot-key-display {
        width: 10;
        padding-top: 1;
        color: $accent;
        text-align: center;
    }

    .slot-set-btn {
        width: 6;
        margin-left: 1;
    }

    .slot-fire-btn {
        width: 5;
        margin-left: 1;
    }

    .tab-hint {
        color: $text-muted;
        text-style: italic;
        height: 1;
        margin-top: 1;
    }

    #capture-sink {
        display: none;
    }

    #cmd-hint {
        height: 1;
        color: $warning;
        text-style: italic;
        margin-top: 1;
    }

    #cmd-status {
        height: 1;
        margin-top: 0;
    }

    #cmd-btn-row {
        height: auto;
        align: right middle;
        margin-top: 1;
    }

    #cmd-btn-nosave {
        margin-right: 1;
    }
    """

    def __init__(self, cmd_config: CommandConfig, flrig: "FlrigClient") -> None:
        super().__init__()
        self._cmd_config = cmd_config
        self._flrig = flrig
        self._capture_state: tuple[str, int] | None = None  # ("cat"|"console", 1–5)
        # Mirror shortcut values so edits are tracked separately from saved config
        self._shortcuts: dict[tuple[str, int], str] = {}
        for i, s in enumerate(cmd_config.cat_slots, 1):
            self._shortcuts[("cat", i)] = s.shortcut
        for i, s in enumerate(cmd_config.console_slots, 1):
            self._shortcuts[("console", i)] = s.shortcut

    def compose(self) -> ComposeResult:
        with Container(id="cmd-box"):
            yield Static("Commander", id="cmd-title")
            with TabbedContent():
                with TabPane("CAT Commands", id="pane-cat"):
                    yield from self._compose_slots("cat", self._cmd_config.cat_slots)
                    yield Static(
                        "Sent via flrig send_cat_string(). Check your rig manual for command codes.",
                        classes="tab-hint",
                    )
                with TabPane("Console Commands", id="pane-console"):
                    yield from self._compose_slots("console", self._cmd_config.console_slots)
                    yield Static(
                        "Shell commands run in the background. You are responsible for cross-platform compatibility.",
                        classes="tab-hint",
                    )
            # Hidden focus sink — receives focus during key-capture mode so
            # key events aren't swallowed by Input widgets.
            yield Button("", id="capture-sink")
            yield Static("", id="cmd-hint")
            yield Static("", id="cmd-status")
            with Horizontal(id="cmd-btn-row"):
                yield Button("Close without saving", id="cmd-btn-nosave")
                yield Button("Save & Close", variant="primary", id="cmd-btn-save")

    def _compose_slots(self, slot_type: str, slots: list[CommandSlot]) -> ComposeResult:
        for i, s in enumerate(slots, 1):
            shortcut_text = s.shortcut or "—"
            with Horizontal(classes="slot-row"):
                yield Static(f"{i}.", classes="slot-num")
                yield Input(
                    value=s.label,
                    placeholder=f"Label {i}",
                    id=f"slot-label-{slot_type}-{i}",
                    classes="slot-label-input",
                    select_on_focus=False,
                )
                yield Input(
                    value=s.command,
                    placeholder="command…",
                    id=f"slot-cmd-{slot_type}-{i}",
                    classes="slot-cmd-input",
                    select_on_focus=False,
                )
                yield Static(
                    shortcut_text,
                    id=f"slot-key-{slot_type}-{i}",
                    classes="slot-key-display",
                )
                yield Button("Set", id=f"slot-set-{slot_type}-{i}", classes="slot-set-btn")
                yield Button("▶", id=f"slot-fire-{slot_type}-{i}", classes="slot-fire-btn")

    def on_key(self, event) -> None:
        if self._capture_state is None:
            if event.key == "escape":
                self.dismiss(None)
            return

        # In capture mode — absorb all keys before anything else handles them.
        event.stop()
        key = event.key
        slot_type, idx = self._capture_state
        self._capture_state = None
        self.query_one("#cmd-hint", Static).update("")

        if key == "escape":
            # Restore previous display without changing the shortcut.
            prev = self._shortcuts.get((slot_type, idx), "") or "—"
            self.query_one(f"#slot-key-{slot_type}-{idx}", Static).update(prev)
            return

        error = self._validate_shortcut(key, slot_type, idx)
        if error:
            prev = self._shortcuts.get((slot_type, idx), "") or "—"
            self.query_one(f"#slot-key-{slot_type}-{idx}", Static).update(prev)
            self._set_status(error, error=True)
        else:
            self._shortcuts[(slot_type, idx)] = key
            self.query_one(f"#slot-key-{slot_type}-{idx}", Static).update(key)
            self._set_status("Assigned — click 'Save & Close' to keep it.", error=False)

    def _validate_shortcut(self, key: str, slot_type: str, idx: int) -> str | None:
        """Return an error string, or None if the key is valid."""
        key_lower = key.lower()
        if key_lower in RESERVED_KEYS:
            return f"'{key}' is reserved by the logger"
        for (stype, sidx), skey in self._shortcuts.items():
            if skey and skey.lower() == key_lower and (stype != slot_type or sidx != idx):
                desc = self._get_label(stype, sidx) or f"{stype.upper()} {sidx}"
                return f"'{key}' is already assigned to {desc}"
        return None

    def _get_label(self, slot_type: str, idx: int) -> str:
        try:
            return self.query_one(f"#slot-label-{slot_type}-{idx}", Input).value.strip()
        except Exception:
            return ""

    @on(Button.Pressed)
    def _on_btn(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""

        if btn_id == "cmd-btn-save":
            self._save()
            return

        if btn_id == "cmd-btn-nosave":
            self.dismiss(None)
            return

        if btn_id.startswith("slot-set-"):
            # id format: slot-set-{type}-{idx}
            parts = btn_id.split("-")
            slot_type = parts[2]   # "cat" or "console"
            idx = int(parts[3])
            self._enter_capture(slot_type, idx)
            return

        if btn_id.startswith("slot-fire-"):
            # id format: slot-fire-{type}-{idx}
            parts = btn_id.split("-")
            slot_type = parts[2]
            idx = int(parts[3])
            self._fire(slot_type, idx)

    def _enter_capture(self, slot_type: str, idx: int) -> None:
        label = self._get_label(slot_type, idx) or f"slot {idx}"
        self._capture_state = (slot_type, idx)
        self.query_one(f"#slot-key-{slot_type}-{idx}", Static).update("◉ …")
        self.query_one("#cmd-hint", Static).update(
            f"Press a key for '{label}'… (Esc to cancel)"
        )
        self._set_status("", error=False)
        # Defocus all inputs so key events reach on_key instead of being typed.
        self.query_one("#capture-sink", Button).focus()

    def _fire(self, slot_type: str, idx: int) -> None:
        cmd = self.query_one(f"#slot-cmd-{slot_type}-{idx}", Input).value.strip()
        if not cmd:
            self._set_status(f"Slot {idx} has no command configured", error=True)
            return
        label = self._get_label(slot_type, idx) or f"{slot_type.upper()} {idx}"
        if slot_type == "cat":
            ok = self._flrig.send_cat_string(cmd)
            if ok:
                self._set_status(f"Fired: {label}  ({cmd})", error=False)
            else:
                self._set_status("flrig not connected", error=True)
        else:
            self._set_status(f"Running: {label}…", error=False)
            self._run_console(label, cmd)

    @work(thread=True)
    def _run_console(self, label: str, cmd: str) -> None:
        try:
            result = subprocess.run(  # noqa: S602
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                self.app.call_from_thread(self._set_status, f"'{label}' completed OK", False)
            else:
                err = (result.stderr or "").strip() or f"exit {result.returncode}"
                self.app.call_from_thread(self._set_status, f"'{label}' failed: {err[:40]}", True)
        except subprocess.TimeoutExpired:
            self.app.call_from_thread(self._set_status, f"'{label}' timed out after 30 s", True)
        except Exception as e:
            self.app.call_from_thread(self._set_status, f"Error: {e}", True)

    def _save(self) -> None:
        """Collect all inputs, validate, persist, and dismiss."""
        cat_slots: list[CommandSlot] = []
        console_slots: list[CommandSlot] = []
        all_keys: dict[str, str] = {}  # normalised key → owner description

        def collect(slot_type: str, out: list[CommandSlot]) -> str | None:
            for i in range(1, NUM_SLOTS + 1):
                label = self.query_one(f"#slot-label-{slot_type}-{i}", Input).value.strip()
                cmd = self.query_one(f"#slot-cmd-{slot_type}-{i}", Input).value.strip()
                key = self._shortcuts.get((slot_type, i), "")
                if key:
                    nk = key.lower()
                    if nk in all_keys:
                        return (
                            f"Shortcut '{key}' used by both {all_keys[nk]} "
                            f"and {slot_type.upper()} {i}"
                        )
                    all_keys[nk] = f"{slot_type.upper()} {i}"
                out.append(CommandSlot(label=label, command=cmd, shortcut=key))
            return None

        err = collect("cat", cat_slots)
        if err:
            self._set_status(err, error=True)
            return
        err = collect("console", console_slots)
        if err:
            self._set_status(err, error=True)
            return

        self._cmd_config.cat_slots = cat_slots
        self._cmd_config.console_slots = console_slots
        save_commands(self._cmd_config)
        self.dismiss(None)

    def _set_status(self, msg: str, error: bool = False) -> None:
        try:
            status = self.query_one("#cmd-status", Static)
            status.update(msg)
            status.styles.color = "red" if error else "green"
        except Exception:
            pass
