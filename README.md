# Potatui
A terminal user interface (TUI) for logging Parks on the Air (POTA) activations.

> **Vibe coded.** This project was built entirely with AI assistance (Claude Code). It works well for my use case but comes with no guarantees. Use at your own risk, and always verify your log files before uploading to pota.app.

![Potatui logger screen](interface.png)

---

## Features

- **Live radio integration** — polls flrig every 2 seconds for frequency and mode. Band is derived automatically from frequency. flrig is required for radio integration; without it, frequency and mode are entered manually.
- **Resume activations** — on launch, pick any previous session to continue from where you left off.
- **Offline park database** — a local copy of the full POTA parks list is downloaded on first launch and refreshed every 30 days. Park lookups work even without internet.
- **Live park lookup** — park name and location shown as you type the park ref at setup.
- **P2P park lookup** — dedicated P2P field does a live lookup, displays the park name, and auto-fills the State field with the state abbreviation.
- **QRZ callsign lookup** — name, location, distance, and direction from your park shown automatically as you type a callsign. First name and state auto-fill. QRZ backfill runs on session resume to fill in any missing names/states. Requires a QRZ XML subscription.
- **POTA spots browser** — live spot list with band/mode/sort filters, auto-refreshes every 60 seconds. QSY directly to a spot with one keypress (tunes flrig, pre-fills callsign and P2P park). Distance from your park shown per spot. Worked activators shown in green.
- **Self-spotting** — post yourself to the POTA network from within the app.
- **Voice keyer** — fire rig voice keyer messages via CAT commands. Quick-fire with Ctrl+1–5, or open the full panel with F7.
- **ADIF export** — every QSO is appended to an ADIF file immediately. Full rewrite on edit, delete, or session end. Ready to upload to pota.app.
- **Multi-park support** — enter multiple park refs at setup (e.g. `US-1234,US-5678`).

---

## Installation

### Requirements

- Python 3.11 or newer
- `git` (to clone the repo)

---

### Linux / macOS

```bash
# 1. Clone the repository
git clone https://github.com/MonkeybutlerCJH/potatui.git potatui
cd potatui

# 2. Create a virtual environment
python3 -m venv .venv

# 3. Activate it
source .venv/bin/activate        # bash/zsh
# source .venv/bin/activate.fish  # fish shell

# 4. Install Potatui and its dependencies
pip install -e .

# 5. Run it
potatui
```

To run again in a future session:

```bash
cd potatui
source .venv/bin/activate   # or activate.fish
potatui
```

---

### Windows

```powershell
# 1. Clone the repository
git clone https://github.com/MonkeybutlerCJH/potatui.git potatui
cd potatui

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
.venv\Scripts\Activate.ps1

# If you get a script execution error, run this first (once):
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 4. Install Potatui and its dependencies
pip install -e .

# 5. Run it
potatui
```

To run again in a future session:

```powershell
cd potatui
.venv\Scripts\Activate.ps1
potatui
```

> **Windows terminal note:** Potatui works best in **Windows Terminal** (the modern one from the Microsoft Store). The legacy `cmd.exe` console has limited colour and Unicode support and is not recommended.

> **Config location on Windows:** the config file is stored at `%APPDATA%\potatui\config.toml` (e.g. `C:\Users\YourName\AppData\Roaming\potatui\config.toml`). Log files go to `%USERPROFILE%\potatui-logs\` by default.

---

## Configuration

The config file is created automatically on first launch. Its location is platform-specific:

| Platform | Path |
|----------|------|
| Linux    | `~/.config/potatui/config.toml` |
| macOS    | `~/Library/Application Support/potatui/config.toml` |
| Windows  | `%APPDATA%\potatui\config.toml` |

You can edit it by hand at any time, or press **F8** from the setup or logger screen to open the in-app settings editor.

**QRZ credentials (optional):** To keep usernames and passwords out of the config file, create a `.env` file in the same directory as `config.toml` (e.g. `~/.config/potatui/.env` on Linux) with:

```
POTATUI_QRZ_USERNAME=your_qrz_username
POTATUI_QRZ_PASSWORD=your_qrz_password
```

If these are set, they override any `[qrz]` username/password in `config.toml` and are not written back when you save settings. Existing TOML-based credentials still work unchanged.

```toml
[operator]
callsign       = "W1AW"
grid           = "EN34"
distance_unit  = "mi"    # "mi" or "km"

[logs]
dir = "~/potatui-logs"

[rig]
name     = "Yaesu FT-710"
antenna  = "EFHW"
power_w  = 100

[flrig]
host = "localhost"
port = 12345

[voice_keyer]
vk1 = "PB01;"
vk2 = "PB02;"
vk3 = "PB03;"
vk4 = "PB04;"
vk5 = "PB05;"

[qrz]
username = ""
password = ""

[pota]
api_base = "https://api.pota.app"

[app]
theme = "textual-dark"
```

Fields you fill in here will pre-populate the activation setup screen so you don't have to retype them each time.

---

## First Run

On first launch, if your callsign is not set, the **Settings** screen opens automatically so you can fill in your station details. Press **Ctrl+S** or click **Save Settings** to save and continue.

On first launch (or when the local park database is missing or outdated), Potatui will offer to download the full POTA parks list. This is a ~5 MB CSV file from pota.app and takes a few seconds. After that, park lookups work offline.

---

## Setup Screen

Fill in your callsign and park reference(s). Park refs use the POTA format: `US-1234`. For multi-park activations separate refs with a comma: `US-1234,US-5678`.

The app looks up each park in the local database as you type and shows the park name inline. If needed it will fall back to the POTA API.

If saved sessions exist, you'll see a resume screen first — select a session to pick up where you left off, or press `n` to start a new activation.

Press **F8** from the setup screen to open the Settings editor.

---

## Logger Screen

### Entry form fields (tab order)

| Field      | Notes                                                                              |
|------------|------------------------------------------------------------------------------------|
| Callsign   | Auto-focus after each logged QSO. Shows DUP if duplicate on same band.             |
| RST Sent   | Pre-filled with `5` — type the signal digits (e.g. `9` → `59`).                   |
| RST Rcvd   | Same.                                                                              |
| P2P Park   | Pre-filled with `US-`. Type digits. Live park name lookup. Auto-fills State.       |
| Name       | Optional. Auto-filled from QRZ if credentials are configured.                      |
| State/Loc  | Optional. Auto-filled from QRZ (2-letter state) or P2P park location.             |
| Notes      | Optional.                                                                          |
| Freq (kHz) | Pre-filled from flrig or last known. Edit to override. Band updates automatically. |

Press **Enter** from any field to log the QSO. UTC timestamp is stamped at log time.

### Header bar

```
W1AW | US-1234 Gifford Pinchot NF | 14:32z | 14225.0 kHz  20M  SSB | QSOs: 4 | 00:23:11     ◉ net  ● flrig
```

- Band is derived live from the frequency field — no separate band picker needed.
- Internet status indicator (net) shows whether the POTA API is reachable.
- flrig status indicator is green (online) or red (offline), right-justified.
- QSO count turns green and shows `✓ VALID` once you reach 10 contacts.

### Key bindings

| Key        | Action                                                         |
|------------|----------------------------------------------------------------|
| F2         | Set run/CQ frequency — tunes flrig if connected                |
| F3         | Mode picker popup (SSB / CW / FT8 / FT4 / AM / FM)            |
| F4         | Toggle between QSO table and entry form                        |
| F5         | Open live POTA spots screen                                    |
| F6         | Self-spot dialog                                               |
| F7         | Voice keyer panel (fire slots 1–5 via CAT command)             |
| F8         | Settings editor                                                |
| F10        | End session — rewrites full ADIF and exits                     |
| Ctrl+1–5   | Quick-fire voice keyer slots 1–5 (shows notification)          |
| Ctrl+D     | Delete highlighted QSO (confirmation required)                 |
| Enter      | Log QSO (from entry form) / Edit QSO (from table)              |
| Escape     | Return focus to Callsign field from QSO table                  |

### Changing frequency mid-activation

Press **F2** to open the Set Run Frequency dialog. Type the new frequency in kHz and press Enter. The header, entry form, and flrig (if connected) all update immediately.

### Editing QSOs

Press **F4** to move focus into the QSO log table. Use arrow keys to select any QSO, then press **Enter** to open the edit dialog. Press **F4** or **Escape** to return to the entry form.

---

## Spots Screen (F5)

- Pulls live activator spots from the POTA API, refreshes every 60 seconds.
- Filter by band or mode using the dropdowns at the top. Sort by distance from your park or spot age.
- Distance is measured from your **park's location** (looked up on startup).
- Activators you've already worked this session are shown in **bold green**.
- Filter, mode, and sort selections are remembered when you return to the screen.
- Press `r` to manually refresh.
- Highlight a spot and press **Enter** to QSY: tunes flrig if connected, pre-fills the callsign and P2P park fields back on the logger screen.
- Press `q` or **F5** to return to the logger.

---

## Self-Spot (F6)

Opens a dialog pre-filled with your current frequency, mode, park, and callsign. Add optional comments (e.g. `CQ POTA 20m SSB`) and submit. Shows a toast notification on success or failure.

Set your frequency accurately with F2 before spotting.

---

## Voice Keyer (F7 / Ctrl+1–5)

- **Ctrl+1 through Ctrl+5** — quick-fire directly from the logger screen.
- **F7** — opens the full VK Panel with all five slots visible.

Each slot sends a CAT command string to the rig via flrig's `rig.cat_string` method.

| Rig              | Command format      |
|------------------|---------------------|
| Yaesu FT-710     | `PB01;` – `PB05;`   |
| Yaesu FT-991A    | `PB01;` – `PB05;`   |
| Other rigs       | Check your manual   |

Configure commands in **Settings (F8)** or directly in the config file under `[voice_keyer]`. Leave a slot blank to disable it.

---

## QRZ Callsign Lookup

When a callsign is entered in the logger, Potatui queries QRZ for the operator's name, location, and grid (after a 1-second debounce). A strip below the entry form shows:

```
  W6ABC  ·  Fred Smith  ·  Los Angeles, CA  ·  Grid: DM04  ·  NE 1,247 mi
```

- Distance is measured from your **park's location**, not your home QTH.
- Direction is shown as a 16-point cardinal (N, NNE, NE … NW, NNW).
- The operator's **first name** is automatically filled into the Name field if empty.
- The operator's **state** is automatically filled into the State field if empty and no P2P park has been entered.
- **QRZ backfill** — when resuming a previous session, any QSOs missing a name or state are automatically filled in from QRZ in the background.
- Results are cached for the session — no duplicate API calls.
- The strip is hidden silently if QRZ credentials are not configured.

**Requirements:** a QRZ account with an active XML data subscription. Enter credentials in **Settings (F8)**, or use a `.env` file in the config directory (see [Configuration](#configuration)) so they are not stored in `config.toml`.

**Distance units:** miles by default. Change to kilometres in Settings or by editing `distance_unit` in the config file.

---

## Offline Park Database

On first launch, Potatui downloads `all_parks_ext.csv` from pota.app (~5 MB) and stores it locally. After that:

- Park name lookups at setup and in P2P fields work without internet.
- The database is automatically refreshed if it's more than 30 days old.
- The internet status indicator in the header tells you if the live POTA API (for spots, self-spot, etc.) is reachable.

The database is stored in the platform data directory:

| Platform | Path |
|----------|------|
| Linux    | `~/.local/share/potatui/parks.csv` |
| macOS    | `~/Library/Application Support/potatui/parks.csv` |
| Windows  | `%LOCALAPPDATA%\potatui\parks.csv` |

---

## Settings (F8)

Opens the in-app settings editor from the setup screen or the logger screen. All config fields are editable here:

- Callsign, grid square, and distance units (mi/km)
- Log file directory
- Rig name, antenna, power
- flrig host and port
- Voice keyer CAT commands (VK1–VK5)
- QRZ username and password

Press **Ctrl+S** or click **Save Settings** to save. Changes are written immediately to the config file.

---

## Log Files

Files are saved to `~/potatui-logs/` by default (configurable via `log_dir` in Settings):

```
~/potatui-logs/
  20260301-W1AW-US-1234.adi    ← ADIF, ready to upload to pota.app
  20260301-W1AW-US-1234.json   ← session state for resume
```

### Uploading to pota.app

1. Go to **pota.app → My Logs → Upload**
2. Upload the `.adi` file
3. For multi-park activations, upload the same file once per park reference

The ADIF includes `MY_SIG=POTA`, `MY_SIG_INFO=<park ref>`, `STATION_CALLSIGN`, `OPERATOR`, and `STATE` — all fields required by the POTA uploader.

---

## flrig Integration

Start flrig before launching Potatui. The app polls every 2 seconds and:

- Updates the frequency display in the header
- Updates the mode (F3 to override)
- Syncs the Freq field in the entry form (unless you're actively editing it)

If flrig is not running, everything works normally. The header shows `● flrig: offline` in red. Frequency and band are taken from whatever is in the Freq entry field.

When you QSY to a spot (F5) or set a run frequency (F2), Potatui calls flrig to tune the radio automatically. If flrig is offline a warning toast is shown but the frequency is still updated in the display.

---

## License

MIT
