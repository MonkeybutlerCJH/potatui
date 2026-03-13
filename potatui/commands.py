# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Command slot configuration — CAT and console command shortcuts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

_CONFIG_DIR = Path(user_config_dir("potatui", appauthor=False))
COMMANDS_PATH = _CONFIG_DIR / "commands.json"

NUM_SLOTS = 5

# Keys reserved by LoggerScreen that users cannot assign as command shortcuts.
RESERVED_KEYS: frozenset[str] = frozenset({
    "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10",
    "ctrl+s", "ctrl+d", "ctrl+o", "escape",
    "enter", "space", "tab", "backspace",
})


@dataclass
class CommandSlot:
    label: str = ""
    command: str = ""
    shortcut: str = ""  # Textual key name, e.g. "ctrl+1"


@dataclass
class CommandConfig:
    cat_slots: list[CommandSlot] = field(
        default_factory=lambda: [CommandSlot() for _ in range(NUM_SLOTS)]
    )
    console_slots: list[CommandSlot] = field(
        default_factory=lambda: [CommandSlot() for _ in range(NUM_SLOTS)]
    )


def load_commands(legacy_vk: list[str] | None = None) -> CommandConfig:
    """Load commands.json, initialising from legacy vk config on first run."""
    if COMMANDS_PATH.exists():
        try:
            data = json.loads(COMMANDS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

        def _parse(raw: list) -> list[CommandSlot]:
            slots: list[CommandSlot] = []
            for item in raw:
                try:
                    slots.append(CommandSlot(
                        label=str(item.get("label", "")),
                        command=str(item.get("command", "")),
                        shortcut=str(item.get("shortcut", "")),
                    ))
                except Exception:
                    slots.append(CommandSlot())
            while len(slots) < NUM_SLOTS:
                slots.append(CommandSlot())
            return slots[:NUM_SLOTS]

        return CommandConfig(
            cat_slots=_parse(data.get("cat_slots", [])),
            console_slots=_parse(data.get("console_slots", [])),
        )

    # First launch — migrate from legacy vk1–vk5 config fields.
    cat_slots: list[CommandSlot] = []
    for i, cmd in enumerate((legacy_vk or [])[:NUM_SLOTS], start=1):
        cat_slots.append(CommandSlot(label=f"VK{i}", command=cmd or ""))
    while len(cat_slots) < NUM_SLOTS:
        n = len(cat_slots) + 1
        cat_slots.append(CommandSlot(label=f"VK{n}"))

    cfg = CommandConfig(cat_slots=cat_slots)
    save_commands(cfg)
    return cfg


def save_commands(cfg: CommandConfig) -> None:
    """Persist command config to disk."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "cat_slots": [
            {"label": s.label, "command": s.command, "shortcut": s.shortcut}
            for s in cfg.cat_slots
        ],
        "console_slots": [
            {"label": s.label, "command": s.command, "shortcut": s.shortcut}
            for s in cfg.console_slots
        ],
    }
    COMMANDS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
