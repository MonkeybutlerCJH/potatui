# Potatui — Claude Code Instructions

## Project

Python TUI application for logging POTA (Parks on the Air) activations.
Built with Textual 8, httpx, xmlrpc.client.

## Environment

- Virtual environment at `.venv/` — always use `.venv/bin/python` / `.venv/bin/pip`
- User runs fish shell — activation is `source .venv/bin/activate.fish`
- Run the app with `.venv/bin/potatui` or `potatui` when venv is active

## Key Constraints

- **Textual 8**: `push_screen` / `pop_screen` are `App`-only. Always use `self.app.push_screen()` from inside a `Screen` subclass — never `self.push_screen()`.
- **Textual 8**: Use `self.dismiss()` (not `self.app.pop_screen()`) inside a `Screen` when a push_screen callback needs to fire.
- **Static width in Horizontal containers**: always set `width: auto` on Static widgets inside Horizontal layouts or they will consume all remaining space.
- **Input select_on_focus**: Textual defaults to `True` — use `select_on_focus=False` to preserve pre-filled prefix text (RST fields, P2P field).
- **DataTable**: no `insert_row_at` — rebuild entire table with `_rebuild_table()` to maintain newest-first ordering.
- `notify()` is available on both `App` and `Screen`.

## Architecture

```
potatui/
  main.py          PotaLogApp(App) — on mount: shows SettingsScreen if callsign empty,
                   then ResumeScreen if saved sessions exist, else SetupScreen.
                   watch_theme() saves theme changes to config automatically.
  config.py        Config dataclass (flat), load_config(), save_config()
                   Config file: ~/.config/potatui/config.toml (sectioned TOML)
  session.py       QSO + Session dataclasses, JSON serialization
  adif.py          ADIF write/append, freq_to_band(), session_file_stem()
  flrig.py         FlrigClient — xmlrpc.client, all methods return None/False on failure
  pota_api.py      async httpx: lookup_park(), fetch_spots(), self_spot()
                   ParkInfo has state field (2-letter abbrev) populated via _US_STATE_ABBREV
                   Spot has location (2-letter abbrev) and grid fields
  qrz.py           QRZClient, QRZInfo, grid/distance/bearing utilities
  screens/
    settings.py    Settings editor — shown on first run (empty callsign) and via F8
    resume.py      Session picker — shown on launch if saved sessions exist
    setup.py       Activation setup form — live park lookup, navigates to LoggerScreen
    logger.py      Main logging screen (all the action)
    spots.py       Live POTA spots browser
```

## Config File

Location: `~/.config/potatui/config.toml`
Created automatically on first launch. Sectioned TOML format:
`[operator]`, `[qrz]`, `[logs]`, `[rig]`, `[flrig]`, `[voice_keyer]`, `[pota]`, `[app]`

`Config` dataclass is kept **flat** — `_SECTION_MAP` in config.py maps `(section, key)` tuples to field names. Legacy flat-format loading has a guard: `not isinstance(data[flat_key], dict)` to avoid section names (e.g. `"rig"`) overwriting string fields with a dict.

`save_config(cfg)` writes the full sectioned TOML back to disk, preserving structure.

## Config Fields (flat Config dataclass)

`callsign`, `grid`, `distance_unit` ("mi"/"km"), `rig`, `antenna`, `power_w`, `log_dir`,
`flrig_host`, `flrig_port`, `pota_api_base`, `theme`, `qrz_username`, `qrz_password`,
`vk1`–`vk5`

## Data Flow

- Each QSO is appended to `.adi` immediately on log
- Full ADIF rewrite on QSO edit or delete
- Session JSON is overwritten on every change
- Files saved to `~/potatui-logs/YYYYMMDD-CALL-PARKREF.{adi,json}`

## QSO Dataclass Fields

`qso_id`, `timestamp_utc`, `callsign`, `rst_sent`, `rst_rcvd`, `freq_khz`, `band`, `mode`,
`name`, `state`, `notes`, `is_p2p`, `p2p_ref`

`QSO.from_dict` uses `d.setdefault("state", "")` for backwards compatibility with old session files.

## Park References

POTA USA parks use `US-XXXX` format (not `K-XXXX`). The regex `[A-Z]{1,4}-\d{1,6}` handles all international refs.

## Band Handling

Band is always derived from frequency via `freq_to_band(freq_khz)` in `adif.py`. There is no manual band picker — removed intentionally. ADIF output uses uppercase band names (`20M`, `40M`).

## Duplicate Detection

`Session.is_duplicate(callsign, band)` — a contact is only a duplicate if the same callsign has been worked **on the same band**. Working the same station on a different band is not a duplicate.

## Setup Screen

Fields: Callsign, Park Ref(s), Power (W), Rig, Antenna.
- No band or mode field — both are set inside the logger.
- Live park lookup fires on `Input.Changed` for `#park_refs` via `@work(exclusive=True) _lookup_parks()`. Results cached in `self._park_names`.
- `_validate_and_launch` reuses cached names; fetches any missed refs before launching.

## Logger Screen Key Bindings

| Key      | Action                                    |
|----------|-------------------------------------------|
| F2       | Set run/CQ frequency (tunes flrig)        |
| F3       | Mode picker                               |
| F4       | Toggle QSO table / entry form             |
| F5       | Spots screen                              |
| F6       | Self-spot dialog                          |
| F7       | Voice keyer panel                         |
| F8       | Settings editor                           |
| F10      | End session                               |
| Ctrl+1–5 | Quick-fire voice keyer slots 1–5          |
| Ctrl+D   | Delete QSO                                |
| Escape   | Return focus to callsign from QSO table   |

## Entry Form Tab Order

Callsign → RST Sent → RST Rcvd → P2P Park → Name → State/Loc → Notes → Freq (kHz) → Log button

- RST fields pre-fill with `"5"` (`select_on_focus=False`) — user types signal digits
- P2P field pre-fills with `"US-"` (`select_on_focus=False`)
- Freq field updated by flrig poll (skipped if field has focus)

## QSO Table Columns

`#`, `UTC`, `Callsign`, `Sent`, `Rcvd`, `Freq`, `Mode`, `Name`, `State`, `P2P`, `Notes`
Band column removed — derived from freq. P2P column shows park ref only when `is_p2p=True`.

## LoggerScreen.__init__ Signature

```python
LoggerScreen(session, config, park_names, mode="SSB", freq_khz=14200.0)
```

`freq_khz` and `mode` are optional — resume.py passes last QSO's values; setup.py uses defaults.

## flrig Polling

`@work(exclusive=True)` runs every 2s. Updates freq/band/mode and the freq input field (unless focused). Sets `self._flrig_online` flag. All FlrigClient methods catch exceptions silently.

## Set Run Frequency (F2)

`SetFreqModal` pre-fills with `self.freq_khz`. On confirm: updates `self.freq_khz`, `self.band`, calls `_update_radio_display()`, sets `#f-freq` input value, calls `flrig.set_frequency(freq * 1000)` if online.

## QRZ Lookup

`potatui/qrz.py` — `QRZClient` uses the QRZ XML data API (`https://xmldata.qrz.com/xml/current/`).
- Login: GET with `username=`, `password=`, `agent=Potatui/1.0` → returns session `<Key>`
- Lookup: GET with `s=SESSION_KEY`, `callsign=CALL` → returns `<Callsign>` element
- Session key cached in memory; auto-relogin on expiry (no Key in response)
- Callsign results cached per-session in `_cache` dict — no duplicate API calls
- XML namespace: `http://xmldata.qrz.com` — `_find()` tries with and without namespace
- `QRZInfo` fields: `callsign`, `fname`, `name`, `city`, `state`, `country`, `grid`, `lat`, `lon`
  - `fname` = first word of first name field (strips middle initial)
  - `state` = 2-letter US state abbreviation from QRZ

Logger integration (`#qrz-info-bar` strip above `#p2p-info-bar`):
- Triggered by `on_callsign_changed` via `_looks_like_callsign()` (len≥3, has digit+2 letters)
- `@work(exclusive=True) _lookup_qrz()` — **1-second debounce** (`await asyncio.sleep(1.0)`) before hitting the API; cancels on each new keystroke
- Distance from **park location** (`self._park_latlon`), fetched via POTA API on mount
  - Falls back to `self.session.grid` (config grid) if park lookup hasn't completed
- Shows: `Callsign  ·  Name  ·  City, State  ·  Grid: XX00  ·  NE 847 mi`
- Unit controlled by `config.distance_unit` ("mi" or "km", default "mi"); converts km×0.621371
- Direction shown as 16-point cardinal before the distance value
- Auto-fills `#f-name` with `info.fname` if empty
- Auto-fills `#f-state` with `info.state` if empty **and** P2P field is still at default `"US-"`
- P2P park lookup overrides `#f-state` with `info.state` (2-letter abbrev from `_US_STATE_ABBREV`)
- Hidden when empty, `pending` class (italic) while fetching, `notfound` class if not found
- Cleared on QSO log; name and state fields cleared when callsign field is emptied
- If QRZ not configured (`_qrz.configured == False`), bar stays hidden silently

Park location fetch (`_fetch_park_location`):
- `@work` on mount — calls `lookup_park(session.active_park_ref, ...)` → converts `ParkInfo.grid` to lat/lon via `grid_to_latlon()` → stores in `self._park_latlon`

## P2P State Abbreviation

`pota_api.lookup_park()` populates `ParkInfo.state` by:
1. Checking `stateAbbrev` or `state` fields in the API response
2. Falling back to `_US_STATE_ABBREV` dict (full US state name → 2-letter code)

`_lookup_p2p_park` sets `#f-state` from `info.state` (abbreviation), not `info.location` (full name).

## Spots QSY

After confirming a QSY from the spots screen, the logger screen receives:
- `prefill_callsign(activator)` — sets `#f-callsign`
- `update_freq_mode(freq_khz, mode)` — updates freq/band/mode, sets `#f-freq`, refreshes header
- `prefill_p2p(park_ref)` — sets `#f-p2p`, triggers P2P lookup and state auto-fill

## Spots Screen

`SpotsScreen(config, flrig, park_latlon=None)` — park_latlon passed from LoggerScreen.
- Columns: Activator, Park, Park Name, Freq, Band, Mode, State, Dist, Age, Comments
- Filter bar: Band select, Mode select, Sort select (Distance / Age)
- Distance computed via haversine from `park_latlon` to `spot.grid` (Maidenhead)
- Sort by distance (ascending, unknowns last) or age (newest first)
- Filter/sort selections persist between visits via class-level `_saved_band`, `_saved_mode`, `_saved_sort`
- Auto-refreshes every 60 seconds; `r` to manual refresh

## Voice Keyer

- **Ctrl+1–5**: quick-fire slots directly from the logger, shows notify toast
- **F7**: opens `VoiceKeyerModal` with all 5 slots displayed
- Each slot fires `flrig.send_cat_string(cmd)` via `rig.cat_string` XML-RPC
- Commands configured in `config.vk1`–`vk5` (e.g. Yaesu: `PB01;`–`PB05;`)
- Blank command → slot silently skipped

## Settings Screen

`SettingsScreen(config, first_run=False)` — edits all Config fields.
- `first_run=True`: no Cancel button, `self.dismiss()` on save triggers `_after_settings` callback in `main.py`.
- `first_run=False`: Cancel button present, save shows "Saved." status message.
- **Ctrl+S** saves from anywhere on the screen (shown in footer).
- Updates `self.config` in-place (same object reference shared across screens).
- Calls `save_config(self.config)` to persist to disk.
- Distance unit selector uses `Select` widget with values `"mi"` / `"km"`.

## Theme Persistence

`PotaLogApp.watch_theme(theme)` fires whenever `app.theme` changes (e.g. via command palette). Saves the new theme name to `config.theme` and calls `save_config()`. On next launch, `on_mount` restores it with `self.theme = self._config.theme`.
