# Potatui — Claude Code Instructions

> **Maintenance**: When making significant code changes — new files, renamed/removed modules, new fields, changed behaviours — update the relevant section(s) of this file in the same commit.

> **Before every commit**: update `_LAST_UPDATED` in `potatui/screens/logger_modals.py` to today's date (`YYYY-MM-DD`).

## Project

Python TUI application for logging POTA (Parks on the Air) activations.
Built with Textual 8, httpx, xmlrpc.client.

**License headers**: every `.py` file must start with:
```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)
```
Add this to any new file you create.

## Environment

- Virtual environment at `.venv/` — always use `.venv/bin/python` / `.venv/bin/pip`
- User runs fish shell — activation is `source .venv/bin/activate.fish`
- Run the app with `.venv/bin/potatui` or `potatui` when venv is active

## Key Constraints

- **Cross-platform**: All code must run on Windows, macOS, and Linux. No hardcoded Unix paths (e.g. `~/.config`). Use `platformdirs` for platform-appropriate config/data directories (`user_config_dir`, `user_data_dir`). Use `pathlib.Path` for all file paths — never string concatenation with `/` or `\`. No subprocess/shell commands that are OS-specific.
- **Textual render rate**: `MAX_REFRESH_RATE` is **not** a valid Textual `App` class variable — it is silently ignored. To cap the frame rate use the `TEXTUAL_FPS` environment variable (maps to `textual.constants.MAX_FPS`). On Windows this is set to `10` in `run()` to avoid hammering ConPTY.
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
  _ssl_ctx.py      Shared SSL context — `ssl_ctx: ssl.SSLContext` singleton created once via
                   `ssl.create_default_context(cafile=certifi.where())`. On Windows, OpenSSL
                   reads certifi's cacert.pem (~272 KB) byte-by-byte through ReadFile(), so
                   constructing a new context per-client generates ~272K I/O ops. All httpx
                   clients (qrz, hamdb, pota_api, space_weather, park_db, wawa) import and
                   pass `ssl_ctx` as `verify=ssl_ctx`. Never construct a bare httpx client
                   without this — especially in code paths reached via `asyncio.gather`, where
                   multiple clients would be constructed synchronously in the same event loop tick.
  mode_map.py      ModeTranslations dataclass + load/save/auto_map helpers.
                   Stored at `~/.config/potatui/mode_translations.json`.
                   `rig_to_canonical` — what flrig reports → potatui canonical (inbound).
                   `canonical_to_rig` — potatui mode → rig mode string (outbound).
                   SSB outbound: empty string = auto USB/LSB-by-freq (existing logic).
                   Two load functions — **must not be swapped**:
                     `load_translations()` — for FlrigClient runtime use; merges built-in
                       defaults on top of saved data so unmapped modes still resolve.
                     `load_user_translations()` — for the UI editor; returns ONLY what is
                       literally in the JSON file (empty inbound if no file exists). Using
                       `load_translations()` in the UI re-injects all built-in defaults and
                       shows modes the rig doesn't have (FT8, FT4, etc.).
  flrig.py         FlrigClient — xmlrpc.client, all methods return None/False on failure
                   Accepts optional `mode_translations: ModeTranslations` in constructor.
                   `get_modes()` — fetches all rig mode strings via `rig.get_modes()`.
                   `update_translations(t)` — hot-swap translations at runtime (thread-safe).
  wsjtx.py         WsjtxClient — UDP listener (default port 2237), Qt QDataStream binary protocol
                   Thread-based, daemon thread; is_online() true if message received within 20s
                   drain_qsos() returns and clears pending Type 5 (QSO Logged) messages
                   Parsed QSO dict keys: datetime_off, dx_call, dx_grid, tx_freq_hz, mode,
                   rst_sent, rst_rcvd, name, comments
  pota_api.py      async httpx: lookup_park(), fetch_spots(), self_spot()
                   fetch_location_pins() — fetches /locations, returns abbrev→(lat,lon), cached for process lifetime
                   ParkInfo has state field (2-letter abbrev) populated via _US_STATE_ABBREV
                   Spot has location (2-letter abbrev) and grid fields
                   Module-level persistent AsyncClient via lazy `_client()` — uses shared ssl_ctx
  qrz.py           QRZClient, QRZInfo, grid/distance/bearing utilities
  hamdb.py         HamDbClient — no-auth fallback callsign lookup via hamdb.org REST API
  commands.py      RESERVED_KEYS set + command slot config (CAT/console shortcuts)
  space_weather.py NOAA Kp index + geomagnetic alert fetching; fetch_muf() for prop info;
                   fetch_kp_forecast() parses 3-day-forecast.txt into KpForecastData
                   Module-level persistent AsyncClient via lazy `_client()` — uses shared ssl_ctx
                   **prop.kc2g.com rate limit**: per the API owner's request, fetch_muf()
                   must not be called more than once every 15 minutes per location.
                   Enforced via _muf_cache keyed on (lat, lon) with monotonic timestamp.
                   fetch_alerts() returns all alerts from the past 8h (no prefix filter);
                   NOAA message preamble ("Space Weather Message Code:", "Serial Number:",
                   "Issue Time:") is stripped from message bodies at parse time.
                   **NOAA API formats**: noaa-planetary-k-index.json is an array of dicts
                   with "time_tag" and "Kp" keys (not the old array-of-arrays with header row).
                   10cm-flux.json is an array of dicts with a "flux" key (not a single
                   {"Flux": N} dict). Use these formats; do not revert to the old structure.
  propagation.py   Propagation scoring for spot contact likelihood.
                   PropProfile dataclass — holds per-band QSO distances + fof2/MUF.
                   PropScore enum — HIGH / MEDIUM / LOW / UNKNOWN.
                   score_spot(profile, freq_khz, dist_km) — hybrid scoring:
                     empirical (≥10 QSOs on band) takes priority; falls back to
                     theoretical skip-zone calculation using fof2 from MUF data.
  park_db.py       ParkDb singleton — offline CSV park database, search_parks()
  wawa.py          Easter egg — nearest Wawa via Overpass API (brand="Wawa" filter);
                   Nominatim reverse-geocode fallback for nodes missing address tags;
                   session-level result cache; respects offline_mode flag
  screens/
    settings.py    Settings editor — shown on first run (empty callsign) and via F8
    resume.py      Session picker — shown on launch if saved sessions exist
    setup.py       Activation setup form — live park lookup, navigates to LoggerScreen
    logger.py      Main logging screen (all the action)
    logger_modals.py  All modal dialogs used by the logger: ModePickerModal,
                   EditQSOModal, SessionSummaryModal, ConfirmModal, QrzLogModal,
                   FlrigStatusModal, SelfSpotModal, SetFreqModal,
                   ChangeOperatorModal, WawaModal, SolarWeatherModal
    spots.py       Live POTA spots browser
    commander.py   CommanderModal — fire and configure CAT/console/CW command slots (F7)
                   Module-level helpers: `_apply_cut(rst)` (9→N cut numbers, first digit preserved),
                   `resolve_cw_macros(text, context)` (substitutes {VARIABLE} placeholders).
                   Accepts optional `get_cw_context: Callable[[], dict[str, str]]` from LoggerScreen.
    park_update.py ParkDbModal — download/refresh local park database prompt
    mode_translations.py  ModeTranslationsScreen — edit rig↔potatui mode maps (via Settings → flrig section)
                   Two sections: Inbound (rig mode → canonical, dynamic rows) and Outbound
                   (canonical → rig mode, fixed rows per MODES). "Fetch from flrig" button
                   calls `flrig.get_modes()` + `auto_map()` and replaces inbound rows
                   (awaits `remove_children()` before mounting to avoid duplicate-ID errors).
                   On first open (no saved file), inbound is empty — user fetches or adds manually.
                   Save calls `save_translations()` + `flrig_client.update_translations()` (hot-reload).
```

## Config File

Location: `~/.config/potatui/config.toml`
Created automatically on first launch. Sectioned TOML format:
`[operator]`, `[qrz]`, `[logs]`, `[rig]`, `[flrig]`, `[voice_keyer]`, `[pota]`, `[app]`

`Config` dataclass is kept **flat** — `_SECTION_MAP` in config.py maps `(section, key)` tuples to field names. Legacy flat-format loading has a guard: `not isinstance(data[flat_key], dict)` to avoid section names (e.g. `"rig"`) overwriting string fields with a dict.

`save_config(cfg)` writes the full sectioned TOML back to disk, preserving structure.

## Config Fields (flat Config dataclass)

`callsign`, `grid`, `distance_unit` ("mi"/"km"), `rig`, `antenna`, `power_w`, `log_dir`,
`flrig_host`, `flrig_port`, `wsjtx_host` (default `"127.0.0.1"`), `wsjtx_port` (default `2237`),
`pota_api_base`, `p2p_prefix` (default `"US-"`, used to pre-fill the P2P field),
`theme`, `qrz_username`, `qrz_password`, `qrz_api_url`, `offline_mode` (bool),
`vk1`–`vk5` (legacy — kept only for migration into `commands.json` on first launch; not shown in Settings)

## Data Flow

- Each QSO is appended to `.adi` immediately on log
- Full ADIF rewrite on QSO edit or delete
- Session JSON is overwritten on every change
- Files saved to `config.log_dir_path / YYYYMMDD-CALL-PARKREF.{adi,json}`. Default log dir is `~/Documents/potatui-logs` (Windows/macOS) or `~/potatui-logs` (Linux). User-configurable via `log_dir` in config.

## QSO Dataclass Fields

`qso_id`, `timestamp_utc`, `callsign`, `rst_sent`, `rst_rcvd`, `freq_khz`, `band`, `mode`,
`name`, `state`, `notes`, `is_p2p`, `p2p_ref`, `operator`,
`contact_grid` (Maidenhead grid from QRZ/HamDB lookup, default `""`),
`distance_km` (km from park to contact, computed at log time, default `None`)

`QSO.from_dict` uses `setdefault` for `state`, `operator`, `contact_grid`, `distance_km` for backwards compatibility with old session files.
`contact_grid` is emitted as `GRIDSQUARE` in ADIF output when non-empty.

## Park References

POTA USA parks use `US-XXXX` format (not `K-XXXX`). The regex `[A-Z]{1,4}-\d{1,6}` handles all international refs.

## Band Handling

Band is always derived from frequency via `freq_to_band(freq_khz)` in `adif.py`. There is no manual band picker — removed intentionally. ADIF output uses uppercase band names (`20M`, `40M`).

## Duplicate Detection

`Session.is_duplicate(callsign, band)` — a contact is only a duplicate if the same callsign has been worked **on the same band**. Working the same station on a different band is not a duplicate. Duplicate shown as `"DUPE!"` label below the callsign field (only in single-callsign mode).

## Setup Screen

Fields: Callsign, Park Ref(s), Grid Square, Power (W), Rig, Antenna, Your State (conditional).
- No band or mode field — both are set inside the logger.
- Live park lookup fires on `Input.Changed` for `#park_refs` via `@work(exclusive=True) _lookup_parks()`. Results cached in `self._park_names` (ref → name) and `self._park_infos` (ref → ParkInfo | None, for multi-state detection).
- `_validate_and_launch` reuses cached names; fetches any missed refs before launching.
- **Park name search**: typing a non-ref string (≥2 chars) in `#park_refs` triggers `@work(exclusive=True) _search_parks()` via `asyncio.to_thread(park_db.search_parks, ...)`. Results shown in `OptionList(id="park-suggestions")`. Selecting a suggestion replaces the active segment (after last comma) — supports 2fer/3fer.
- **Your State dropdown** (`#state-row`, `Select(id="my_state")`): hidden by default, shown when any looked-up park has `ParkInfo.locations` with >1 entry (multi-state park). Populated by `_update_state_field()`. Selection is required before launch when visible; stored as `Session.my_state`. Positioned between Park Ref(s) and Grid Square fields.
- `SetupScreen(config, dismissable=False)` — `dismissable=True` passed from ResumeScreen; Escape returns to session picker.
- **Grid auto-fill**: grid auto-filled from first park's `ParkInfo.grid` unless `_user_edited_grid` is True. Uses `_auto_fill_pending: int` counter (not a bool flag) because `Input.value =` posts `Input.Changed` asynchronously — a synchronous flag is always reset before the handler fires.

## Logger Screen Key Bindings

| Key      | Action                                    |
|----------|-------------------------------------------|
| F1       | About screen                              |
| F2       | Set run/CQ frequency (tunes flrig)        |
| F3       | Mode picker                               |
| F4       | Toggle QSO table / entry form             |
| F5       | Spots screen                              |
| Ctrl+S   | Spots screen (alias for F5)               |
| F6       | Self-spot dialog                          |
| F7       | Commander (CAT / console command slots)   |
| F8       | Settings editor                           |
| F10      | End session                               |
| Ctrl+N   | Toggle offline mode                       |
| Ctrl+O   | Change operator                           |
| D        | Delete QSO (table mode)                   |
| L        | QRZ lookup selected QSO (table mode)      |
| B        | QRZ backfill all QSOs (table mode)        |
| Escape   | Clear entry form, return focus to callsign |

**Reserved keys**: whenever a new `LoggerScreen` binding is added, also add the key to `RESERVED_KEYS` in `potatui/commands.py` so the F7 commander cannot assign it as a CAT/console shortcut.

## Entry Form Tab Order

Callsign → RST Sent → RST Rcvd → P2P Park → Name → State/Loc → Notes → Freq (kHz) → Log button

- RST fields pre-fill with `"59"` (SSB/AM/FM) or `"599"` (CW); on focus, the signal digits after the first char are selected so the user can type to overwrite just that part (`select_on_focus=False`)
- P2P field pre-fills with `config.p2p_prefix` (default `"US-"`) (`select_on_focus=False`)
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

`@work(exclusive=True, group="flrig-poll")` runs every 2s via `asyncio.to_thread`. Updates freq/band/mode and the freq input field (unless focused). Sets `self._flrig_online` flag. All FlrigClient methods catch exceptions silently.

**TCP pre-check** (`FlrigClient._port_open()`): before every XML-RPC poll, a `socket.create_connection` with a 0.3s timeout tests reachability. A refused connection returns in <1 ms; only open ports proceed to the XML-RPC call. This prevents blocking a thread-pool thread for the full 1s XML-RPC timeout on every poll cycle when flrig is not running — critical on Windows where this was causing visible poll lag.

**Exponential back-off**: `_flrig_retry_delay` starts at 2s and doubles each failed poll (cap 30s). `_flrig_next_poll` (monotonic) gates whether `_poll_flrig` actually runs, even though `set_interval(2.0)` keeps firing. On reconnect, delay resets to 2s.

**CAT / CW timeout avoidance**: flrig's XML-RPC server blocks completely during CW keying or voice playback, causing poll calls to time out even though flrig is healthy. `FlrigClient` uses a separate `_cat_proxy` / `_cat_lock` for CAT commands (`send_cat_string`) and CW (`send_cw`) and sets `cat_in_flight = True` for the duration. The poll handler skips marking flrig offline when `flrig.cat_in_flight` is True — only transitions to offline when a poll fails *and* no CAT/CW command is in flight.

## WSJT-X Integration

`WsjtxClient(host, port)` — thread-based UDP listener (`wsjtx.py`). Started in `LoggerScreen.on_mount()`, stopped in `on_unmount()`. Polled every 2s via `_poll_wsjtx()` (`@work(exclusive=True, group="wsjtx-poll")`).

**Protocol**: WSJT-X broadcasts UDP datagrams (default port 2237) using Qt QDataStream binary format. Magic bytes `0xADBCCBDA` then schema (u32), message type (u32), ID (utf8). Relevant types: 0 = Heartbeat, 1 = Status (diagnostic only), 5 = QSO Logged.

**`is_online()`**: True if any message received within 20 seconds (heartbeats sent ~every 15s).

**`drain_qsos()`**: thread-safe pop of parsed Type 5 messages. Returned dicts have keys: `datetime_off`, `dx_call`, `dx_grid`, `tx_freq_hz`, `mode`, `rst_sent`, `rst_rcvd`, `name`, `comments`.

**`_ingest_wsjtx_qso(data)`**: async — does QRZ→HamDB lookup for name/state/grid/distance (skipped when `self._offline`), calls `session.add_qso()` with the original WSJT-X timestamp, appends to ADIF, rebuilds table, saves session.

**Freq/mode from WSJT-X Status messages are diagnostic-only** — not used to update the logger display (flrig owns that).

**FT8/FT4 modes**: added to `MODES` list in `logger_modals.py`. Default RST for digital modes is `"-10"`.

**NetworkStatusModal**: WSJT-X row appears after flrig. Clickable → opens `WsjtxStatusModal` with host:port, online/offline, combined state+detail log.

**Config fields**: `wsjtx_host` (default `"127.0.0.1"`), `wsjtx_port` (default `2237`). Editable in Settings (F8) under "WSJT-X Integration" section. Saved to `[wsjtx]` section in config.toml.

## Solar Weather Alerts

`_poll_space_weather()` runs on mount and every 10 minutes. On the **first poll**, all current alerts are silently seeded into `_seen_alert_keys` — no toasts are shown. The Kp pill flashes if any alerts are present and `_solar_alerts_acknowledged` is False.

Also fetches MUF (via `fetch_muf(lat, lon)`, respecting its 15-min cache) when `_park_latlon` is available, and updates `_prop_profile.fof2_mhz` / `.muf_mhz`. A second trigger fires at the end of `_fetch_park_location()` in case `_park_latlon` wasn't set yet during the on-mount poll.

Opening the `SolarWeatherModal` sets `_solar_alerts_acknowledged = True` and stops the flash. Subsequent polls only toast and reflash for genuinely new alerts (new `alert_key` values), which also clears `_solar_alerts_acknowledged`.

The pill flashes for **any** active alerts (not just storm-level Kp).

## Set Run Frequency (F2)

`SetFreqModal` pre-fills with `self.freq_khz`. On confirm: updates `self.freq_khz`, `self.band`, calls `_update_radio_display()`, sets `#f-freq` input value, calls `flrig.set_frequency(freq * 1000)` if online.

## Callsign Lookup (QRZ + HamDB fallback)

**QRZ** (`potatui/qrz.py`) — `QRZClient` uses the QRZ XML data API (`https://xmldata.qrz.com/xml/current/`).
- Login: GET with `username=`, `password=`, `agent=Potatui/1.0` → returns session `<Key>`
- Lookup: GET with `s=SESSION_KEY`, `callsign=CALL` → returns `<Callsign>` element
- Session key cached in memory; auto-relogin on expiry (no Key in response)
- Callsign results cached per-session in `_cache` dict — no duplicate API calls
- XML namespace: `http://xmldata.qrz.com` — `_find()` tries with and without namespace
- `QRZInfo` fields: `callsign`, `fname`, `name`, `city`, `state`, `country`, `grid`, `lat`, `lon`
  - `fname` = full first name field from QRZ (includes nickname in parens if present)
  - `state` = 2-letter US state abbreviation from QRZ

**HamDB fallback** (`potatui/hamdb.py`) — `HamDbClient` wraps the `http://api.hamdb.org/v1/CALL/json/potatui` REST API (note the `/v1/` prefix — the root URL 302-redirects but httpx doesn't follow redirects by default).
- No authentication required
- Returns a `QRZInfo` object (same dataclass reused) so the rest of the logger is source-agnostic
- Results cached per-session in `_cache` dict
- Used automatically when QRZ is not configured OR when QRZ returns None (not found / error)
- Info bar shows `QRZ:` or `HamDB:` prefix to indicate which source was used

Logger integration — `#qrz-info-container` (Vertical, `height: auto`) holds one `.qrz-info-bar` Static per callsign, above `#p2p-info-bar`:
- Triggered by `on_callsign_changed` via `_looks_like_callsign()` (len≥3, has digit+2 letters)
- **Multi-callsign mode**: one bar per callsign, looked up in parallel. `_trigger_qrz_lookup(callsign)` calls `self.run_worker(_do_qrz_lookup(callsign), exclusive=True, group=f"qrz-{callsign}")` — each callsign gets its own exclusive worker group so lookups don't cancel each other. Lookup only fires when the bar is still in `hidden` class (avoids re-querying already-resolved callsigns on each keystroke).
- `_qrz_bars: dict[str, Static]` tracks callsign → bar widget. Bars are added/removed as callsigns are typed or deleted.
- **1-second debounce** (`await asyncio.sleep(1.0)`) before hitting the API; stale-checked via `_qrz_bars` membership after debounce and after HTTP round-trip.
- Distance from **park location** (`self._park_latlon`), fetched via POTA API on mount
  - Falls back to `self.session.grid` (config grid) if park lookup hasn't completed
- Shows: `QRZ: Callsign  ·  Name  ·  City, State  ·  Grid: XX00  ·  NE 847 mi` (or `HamDB:` prefix)
- Unit controlled by `config.distance_unit` ("mi" or "km", default "mi"); converts km×0.621371
- Direction shown as 16-point cardinal before the distance value
- Auto-fills `#f-name` and `#f-state` **only in single-callsign mode** (when `len(_qrz_bars) == 1`)
- P2P park lookup overrides `#f-state` with `info.state` (2-letter abbrev from `_US_STATE_ABBREV`)
- CSS class `.qrz-info-bar` (not ID) — states: `hidden` (display:none), `pending` (italic), `notfound` (muted), no extra class = result shown
- Cleared on QSO log; name and state fields cleared when callsign field is emptied
- `L` (table mode) and `B` backfill both use QRZ→HamDB fallback chain; no longer blocked when QRZ unconfigured
- Both return early with a warning toast when `self._offline` is True (offline mode guard)
- **B concurrent backfill** (table mode): up to 5 lookups run concurrently via `asyncio.Semaphore(5)` + `asyncio.gather()`; `QRZClient` serialises its own login internally so concurrent callers are safe

Park location fetch (`_fetch_park_location`):
- `@work` on mount — sets `self._park_latlon` (used for QRZ distance calc) and `self._shift_lon` (used for shift window calc)
- `_park_latlon`: user's grid (session.grid) takes priority; falls back to park lat/lon from API/local DB
- `_shift_lon`: for multi-location parks (`session.my_state` set), uses the state/province admin pin from `fetch_location_pins()`; otherwise uses `_park_latlon[1]`

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

`SpotsScreen(config, flrig, park_latlon=None, session=None, prop_profile=None)` — park_latlon, session, and prop_profile passed from LoggerScreen.
- Columns: Activator, Park, Park Name, Freq, Band, Mode, State, Dist, [Prop,] Age, Comments
- Filter bar: Band select, Mode select, Sort select (Propagation / Distance / Age / Frequency)
- Distance computed via haversine from `park_latlon` to `spot.grid` (Maidenhead)
- Sort by Propagation (HIGH → MEDIUM → LOW → UNKNOWN, then by distance), distance, age, or frequency
- Filter/sort selections persist between visits via class-level `_saved_*` attributes including `_saved_prop_enabled`
- Auto-refreshes every 60 seconds; `r` to manual refresh
- Worked activators shown with bold green "✓ CALLSIGN" — matched by callsign against session QSOs
- **Propagation indicators**: press `p` to toggle on/off (default off). When on, a "Prop" column appears:
  - `●` green = HIGH likelihood (spot is in the current propagation window)
  - `◐` yellow = MEDIUM (near the skip zone edge or fringe range)
  - `○` red = LOW (in the skip zone or out of range)
  - `·` dim = UNKNOWN (no distance data or insufficient session data)
- Scoring uses `score_spot()` from `propagation.py` — see Propagation Scoring section below
- `_rebuild_table()` calls `table.clear(columns=True)` and re-adds columns on each rebuild (needed for dynamic Prop column)
- Park grid fetches use `asyncio.Semaphore(10)` + `asyncio.gather` — limits concurrent POTA API hits when many unique parks are in the spots list

## Commander (F7)

The voice keyer has been replaced by the Commander — a three-tab modal for CAT commands, console (shell) commands, and CW keyer macros.

**Data model** (`potatui/commands.py`):
- `CommandSlot(label, command, shortcut)` — one slot. `shortcut` is a Textual key name (e.g. `"ctrl+1"`).
- `CommandConfig(cat_slots, console_slots, cw_slots)` — 5 slots each.
- Persisted to `~/.config/potatui/commands.json` via `save_commands()` / `load_commands()`.
- On first launch, `load_commands(legacy_vk=[...])` migrates old `config.vk1`–`vk5` values into CAT slots.

**CommanderModal** (`potatui/screens/commander.py`):
- Three tabs: **CAT Commands** (sent via `flrig.send_cat_string()`), **Console Commands** (shell commands via `subprocess.run(..., shell=True, timeout=30)`), **CW Keyer** (sent via `flrig.send_cw()`).
- Each slot row has: label input, command/text input, shortcut display, **Set** button (enters key-capture mode), **▶** fire button.
- **Key capture**: clicking Set focuses a hidden `Button(id="capture-sink")` to absorb keypresses, then records the next key as the shortcut. Del/Backspace clears; Escape cancels.
- Shortcuts validated against `RESERVED_KEYS` and checked for duplicates within the modal before saving.
- **Save & Close** persists; **Close without saving** discards edits.
- CW tab accepts optional `get_cw_context: Callable[[], dict[str, str]]` from LoggerScreen for live macro resolution.

**CW macros** — variables substituted at send time:
- `{OP}` operator callsign, `{CALL}` station callsign, `{PARK}` active park ref(s)
- `{THEIRCALL}` callsign field, `{RST}` RST sent field, `{RSTCUT}` RST with 9→N cut (first digit preserved), `{STATE}` state field

**flrig CW send** (`flrig.py`): `send_cw(text)` calls `rig.cwio_text(text)` then `rig.cwio_send(1)` via the CAT proxy (5s timeout). Sets `cat_in_flight = True` for the duration.

**Logger shortcut dispatch** (`logger.py`):
- `on_key` scans `_cmd_config.cat_slots`, `_cmd_config.console_slots`, and `_cmd_config.cw_slots` on every keypress.
- Match → `_fire_cat_slot()`, `_fire_console_slot()`, or `_fire_cw_slot()` (all `@work(thread=True)`).
- `_fire_cw_slot()` calls `_get_cw_context()` to resolve macros before sending.
- `_get_cw_context()` reads live form fields (callsign, RST sent, state) and session data (operator, park refs, station callsign).
- `_cmd_config` loaded via `load_commands(legacy_vk)` in `__init__`.

**RESERVED_KEYS** (`commands.py`): `f1`–`f10`, `ctrl+s`, `ctrl+n`, `ctrl+o`, `escape`, `enter`, `space`, `tab`, `backspace` — users cannot assign these as shortcuts. (`d`, `l`, `b` are table-mode-only and not reserved since Commander shortcuts only apply in entry-form mode.)

## Settings Screen

`SettingsScreen(config, first_run=False)` — edits all Config fields.
- `first_run=True`: no Cancel button, `self.dismiss()` on save triggers `_after_settings` callback in `main.py`.
- `first_run=False`: Cancel button present, save shows "Saved." status message.
- **Ctrl+S** saves from anywhere on the screen (shown in footer).
- Updates `self.config` in-place (same object reference shared across screens).
- Calls `save_config(self.config)` to persist to disk.
- Distance unit selector uses `Select` widget with values `"mi"` / `"km"`.
- `action_settings()` passes `_on_settings_closed` callback to `push_screen` — syncs `_offline` / `_offline_manual` if the user toggled offline mode inside Settings. Without this, the offline flag change doesn't take effect until restart.

## Early/Late Shift Indicator

`#hdr-shift` Static in the logger header — shows 🌅 (Early Shift) or 🌙 (Late Shift) emoji when the current park is within a POTA shift window. Hidden (`shift-inactive`) when outside both windows or when coordinates are unavailable.

**Shift windows** (per POTA rules):
- Early Shift: 6-hour period starting at `round(2 − lon/15) % 24` UTC
- Late Shift: 8-hour period starting at `round(18 − lon/15) % 24` UTC

**Longitude source** (`_shift_lon`):
- Single-location park: park pin longitude
- Multi-location park (`session.my_state` set): state/province admin pin from `fetch_location_pins()` — this is the POTA-official pin per the award rules
- Falls back to park pin if offline or if the location lookup fails

**Interaction**: clicking the emoji shows a `notify()` toast with the shift name and UTC window (e.g. `Early Shift active: 22:00 – 04:00 UTC`).

`_shift_status(lon, utc_now)` — module-level helper in `logger.py`, handles midnight-wrapping windows.
`_update_shift_indicator()` — called from `_tick_clock()` (every second) and at the end of `_fetch_park_location()`.

## Windows Performance

Windows Terminal uses a ConPTY pseudo-terminal layer that processes ANSI escape sequences with significantly more overhead than a native Unix PTY. Several mitigations are applied in `run()` (before the app starts) and in `LoggerScreen._tick_clock()`:

**Startup env vars** (set via `os.environ.setdefault` in `run()` on `sys.platform == "win32"`):
- `PYTHONUTF8=1` — eliminates code-page conversion overhead in the Python I/O layer
- `TEXTUAL_FPS=10` — caps the Textual render rate at 10fps (default 60fps hammers ConPTY on every cycle)
- `TEXTUAL_ANIMATIONS=none` — skips animated widget transitions (extra render work with no value on ConPTY)

**Asyncio event loop** (`run()`, win32 only): `asyncio.WindowsSelectorEventLoopPolicy()` — `SelectorEventLoop` has lower overhead than the default `ProactorEventLoop` (IOCP) for TUI I/O patterns.

**`_tick_clock` throttle** (`logger.py`): `_update_last_spotted_bar()` and `_update_shift_indicator()` are called every second on non-Windows but only every 5 seconds on Windows (`_clock_tick_count % 5 == 0`). These widgets change slowly and each widget update is expensive on ConPTY.

**`_ssl_ctx.py` shared SSL context**: On Windows, `ssl.create_default_context()` reads certifi's cacert.pem (~272 KB) byte-by-byte via `ReadFile()` — ~272K syscalls per construction. All httpx clients share a single `ssl_ctx` instance imported from `_ssl_ctx.py`. Never construct a bare httpx client without passing `verify=ssl_ctx`, especially in `asyncio.gather` code paths where multiple clients would otherwise be built in the same event loop tick.

**`FlrigClient._port_open()` TCP pre-check**: without this, every poll when flrig is offline blocks a thread-pool thread for the full 1s XML-RPC timeout. The TCP pre-check returns in <1 ms on a refused connection, keeping the thread pool free and eliminating poll lag on Windows. Paired with exponential back-off so the poll interval grows to 30s when flrig stays offline.

**Rule**: when adding new per-second work to `_tick_clock` or other hot render paths, guard it with the same `sys.platform != "win32" or self._clock_tick_count % N == 0` pattern if the update is not time-critical.

## Theme Persistence

`PotaLogApp.watch_theme(theme)` fires whenever `app.theme` changes (e.g. via command palette). Saves the new theme name to `config.theme` and calls `save_config()`. On next launch, `on_mount` restores it with `self.theme = self._config.theme`.

## Propagation Scoring

`potatui/propagation.py` — `score_spot(profile, freq_khz, dist_km) → PropScore`

**`PropProfile`** (dataclass):
- `band_distances: dict[str, list[float]]` — per-band list of confirmed QSO distances (km) from the session
- `fof2_mhz: float | None` — ionospheric critical frequency from `fetch_muf()`
- `muf_mhz: float | None` — max usable frequency for the path
- `add_qso(band, distance_km)` — records a QSO distance into the profile

**Scoring algorithm** (hybrid — empirical takes priority):
1. If ≥10 QSOs with distance on the spot's band (empirical):
   - `min_d` to `max_d` = range of confirmed QSO distances
   - Single-hop core `[min_d×0.90, max_d×1.25]` → HIGH
   - Single-hop fringe `[min_d×0.60, min_d×0.90)` or `(max_d×1.25, max_d×1.50]` → MEDIUM
   - Double-skip window `[2×min_d×0.85, 2×max_d×1.20]` → MEDIUM
   - Triple-skip window `[3×min_d×0.80, 3×max_d×1.15]` → LOW; outside all windows → LOW
   - Empirical HIGH always wins; empirical LOW softened to MEDIUM if theoretical says HIGH
2. Else if `fof2_mhz` is known (theoretical skip zone):
   - `fof2 >= fo`: NVIS, no skip zone — ≤500km HIGH, ≤1200km MEDIUM, else LOW
   - `fof2 < fo`: skip zone exists — `MUA = arcsin(fof2/fo)`, `skip_km = 2 × 300km × tan(π/2 - MUA)`; below skip LOW/MEDIUM, in range HIGH, multi-hop MEDIUM
3. Else: UNKNOWN

**Logger integration** (`logger.py`):
- `self._prop_profile: PropProfile` built on mount (seeds from resumed session QSOs with `distance_km`)
- `self._qrz_contact_info: dict[str, tuple[str, float | None]]` — callsign → (grid, dist_km), populated in `_do_qrz_lookup`, cleared in `_clear_qrz_info`
- At log time, `_contact_location(callsign)` reads from `_qrz_contact_info` cache; `contact_grid` and `distance_km` saved to QSO; prop profile updated immediately
- `_poll_space_weather` updates `_prop_profile.fof2_mhz` / `.muf_mhz` after each MUF fetch
- `PropProfile` reference passed to `SpotsScreen` — live updates (new QSOs) are visible immediately on next table rebuild
