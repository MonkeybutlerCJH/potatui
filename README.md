# Potatui

A terminal user interface (TUI) for logging Parks on the Air (POTA) activations.

## Features

- **Live radio integration** — polls flrig every 2 seconds for frequency and mode. Band is derived automatically from frequency. Works fully without flrig.
- **Quick QSY** — press F2 to set a new run/CQ frequency instantly. Tunes flrig if connected.
- **Manual frequency entry** — type any frequency directly in the entry form; band updates in the header as you type.
- **Resume activations** — on launch, pick any previous session to continue from where you left off.
- **Live park lookup** — park name and location shown as you type the park ref at setup.
- **P2P park lookup** — dedicated P2P field does a live POTA API lookup, displays the park name, and auto-fills the State field with the state abbreviation.
- **QRZ callsign lookup** — name, location, distance, and direction from your park shown automatically as you type a callsign. First name and state auto-fill. Requires a QRZ subscription.
- **Duplicate detection** — highlights "DUP" in yellow if a callsign has already been worked on the same band this session. Non-blocking.
- **POTA spots browser** — live spot list with band/mode/sort filters, auto-refreshes every 60 seconds. QSY directly to a spot with one keypress (tunes flrig, pre-fills callsign and P2P park). Distance from your park shown per spot.
- **Self-spotting** — post yourself to the POTA network from within the app.
- **Voice keyer** — fire rig voice keyer messages via CAT commands. Quick-fire with Ctrl+1–5, or open the full panel with F7.
- **ADIF export** — every QSO is appended to an ADIF file immediately. Full rewrite on edit, delete, or session end. Ready to upload to pota.app.
- **Multi-park support** — enter multiple park refs at setup (e.g. `US-1234,US-5678`).
- **Persistent theme** — theme changes via the command palette are saved automatically.

---

## Installation

### Requirements

- Python 3.11 or newer
- `git` (to clone the repo)

### Step-by-step

```bash
# 1. Clone the repository
git clone <repo-url> potatui
cd potatui

# 2. Create a virtual environment
python3 -m venv .venv

# 3. Activate it
#    bash/zsh:
source .venv/bin/activate
#    fish shell:
source .venv/bin/activate.fish

# 4. Install Potatui and its dependencies
pip install -e .

# 5. Run it
potatui
```

> **Note for fish shell users:** always use `source .venv/bin/activate.fish`, not `source .venv/bin/activate`.

To run it again in a future terminal session:

```bash
cd potatui
source .venv/bin/activate.fish   # or activate for bash/zsh
potatui
```

---

## Configuration

The config file is at **`~/.config/potatui/config.toml`**. It is created automatically on first launch with all defaults.

You can edit it by hand at any time, or press **F8** from the setup or logger screen to open the in-app settings editor.

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

On first launch, if your callsign is not set, the **Settings** screen opens automatically so you can fill in your station details before starting. Press **Ctrl+S** or click **Save Settings** to save and continue. After saving, the normal startup flow continues.

---

## Setup Screen

Fill in your callsign and park reference(s) on launch. Park refs use the current POTA format: `US-1234`. For multi-park activations separate refs with a comma: `US-1234,US-5678`.

The app looks up each park via the POTA API as you type and shows the park name inline. If the API is unreachable it warns and continues.

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
W1AW | US-1234 Gifford Pinchot NF | 14:32z | 14225.0 kHz  20M  SSB | QSOs: 4 | 00:23:11     ● flrig: online
```

- Band is derived live from the frequency field — no separate band picker needed.
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

Press **F2** to open the Set Run Frequency dialog. Type the new frequency in kHz and press Enter. The header, entry form, and flrig (if connected) all update immediately. Use this whenever you move bands or find a new CQ spot.

### Editing QSOs

Press **F4** to move focus into the QSO log table (press **F4** or **Escape** to return). Use arrow keys to select any QSO, then press **Enter** to open the edit dialog. You can edit callsign, RST, frequency, mode, name, state, P2P park, and notes.

---

## Spots Screen (F5)

- Pulls live activator spots from the POTA API, refreshes every 60 seconds.
- Filter by band or mode using the dropdowns at the top. Sort by distance from your park or spot age.
- Distance is measured from your **park's location** (looked up from the POTA API on startup).
- Filter, mode, and sort selections are remembered when you return to the screen.
- Press `r` to manually refresh.
- Highlight a spot and press **Enter** to QSY: confirms the frequency and mode, tunes flrig if connected, pre-fills the callsign and P2P park fields back on the logger screen.
- Press `q` or **F5** to return to the logger.

---

## Self-Spot (F6)

Opens a dialog pre-filled with your current frequency, mode, park, and callsign. Add optional comments (e.g. `CQ POTA 20m SSB`) and submit. Shows a toast notification on success or failure.

The frequency used in the spot is whatever is currently shown in the header — set it accurately with F2 before spotting.

---

## Voice Keyer (F7 / Ctrl+1–5)

Two ways to fire voice keyer slots:

- **Ctrl+1 through Ctrl+5** — quick-fire directly from the logger screen; shows a toast notification confirming which slot fired.
- **F7** — opens the full VK Panel for a visual overview of all five slots.

Each slot sends a CAT command string to the rig via flrig's `rig.cat_string` method.

Commands are rig-specific. Common examples:

| Rig              | Command format      |
|------------------|---------------------|
| Yaesu FT-710     | `PB01;` – `PB05;`   |
| Yaesu FT-991A    | `PB01;` – `PB05;`   |
| Other rigs       | Check your manual   |

Configure the commands in **Settings (F8)** or directly in `~/.config/potatui/config.toml` under `[voice_keyer]`. Leave a slot blank to disable that button.

---

## QRZ Callsign Lookup

When a callsign is entered in the logger, Potatui automatically queries QRZ for the operator's name, location, and grid (after a 1-second pause). A strip between the entry form and the QSO table shows:

```
  W6ABC  ·  Fred Smith  ·  Los Angeles, CA  ·  Grid: DM04  ·  NE 1,247 mi
```

- Distance is measured from your **park's location** (looked up from the POTA API on startup), not your home QTH.
- Direction is shown as a 16-point cardinal (N, NNE, NE … NW, NNW).
- The operator's **first name** is automatically filled into the Name field if it's empty.
- The operator's **state** (2-letter abbreviation) is automatically filled into the State field if it's empty and no P2P park has been entered.
- Results are cached for the session — no repeated API calls for the same callsign.
- The strip is hidden silently if QRZ credentials are not configured.

**Requirements:** a QRZ account with an active XML data subscription. Enter your credentials in **Settings (F8)**.

**Distance units:** set to miles (`mi`) by default. Change to kilometres in Settings or by editing `distance_unit` under `[operator]` in the config file.

---

## Settings (F8)

Opens the in-app settings editor from the setup screen or the logger screen. All fields from `~/.config/potatui/config.toml` are editable here:

- Callsign, grid square, and distance units (mi/km)
- Log file directory
- Rig name, antenna, power
- flrig host and port
- Voice keyer CAT commands (VK1–VK5)
- QRZ username and password

Press **Ctrl+S** or click **Save Settings** to save. Changes are written immediately to `~/.config/potatui/config.toml`.

---

## Log Files

Files are saved to `~/potatui-logs/` (configurable via `log_dir` in config or Settings):

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
