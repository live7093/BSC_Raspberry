# Kombucha Fermentation Monitor

**BSC Project — Ruben Schmid, ZHAW**

Automated monitoring system for kombucha fermentation runs. A Raspberry Pi 5 collects sensor data every 15 minutes, compares it against a physics-based simulation model, and takes time-lapse photos every hour — all logged to CSV for later analysis.

> ** Work in Progress **  
> This repository is actively under development. Features may change, break, or be incomplete until the first stable release.
---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Hardware](#2-hardware)
3. [Repository Structure](#3-repository-structure)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [Running a Fermentation](#6-running-a-fermentation)
7. [Data Output](#7-data-output)
8. [Simulation Model](#8-simulation-model)
9. [Camera & LED Settings](#9-camera--led-settings)
10. [Testing & Calibration Tools](#10-testing--calibration-tools)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. System Overview

The system consists of two microcontrollers that work together:

```
┌─────────────────────────────────────────────────────┐
│                  Raspberry Pi 5                     │
│                                                     │
│  main_loop.py  runs continuously:                   │
│  ┌────────────┐  every 15 min  ┌─────────────────┐  │
│  │ HTU21D     │─────────────→  │                 │  │
│  │ temp + hum │                │  sensor_log.csv │  │
│  └────────────┘                │                 │  │
│  ┌────────────┐  every 15 min  │  (also compares │  │
│  │ Pico (USB) │─────────────→  │   to simulation │  │
│  │ pH + weight│                │   curve)        │  │
│  └────────────┘                └─────────────────┘  │
│  ┌────────────┐  every 60 min                        │
│  │ Camera     │─────────────→  images/               │
│  │ + LEDs     │                                     │
│  └────────────┘                                     │
└─────────────────────────────────────────────────────┘
              │ USB serial
              ▼
┌─────────────────────────────────────────────────────┐
│               Raspberry Pi Pico                     │
│                                                     │
│  pico_main.py  (uploaded as main.py on Pico):       │
│  - Reads pH probe via ADC                           │
│  - Reads weight via HX711 load cell                 │
│  - Shows live pH + weight on Grove LCD              │
│  - Sends JSON to RPi every 30 s over USB serial     │
│  - Guides through pH calibration via LCD            │
└─────────────────────────────────────────────────────┘
```

---

## 2. Hardware

### Raspberry Pi 5

| Component | Connection |
|---|---|
| Camera (Arducam/RPi) | Ribbon cable → CSI port **CAM 0** |
| HTU21D (temp/humidity) | I2C bus 1: SDA=**GPIO 2** (Pin 3), SCL=**GPIO 3** (Pin 5), VCC=3.3V (Pin 1), GND (Pin 6) |
| 56× NeoPixel LEDs (WS2812B) | SPI MOSI **GPIO 10** (Pin 19), powered by external 5V PSU with shared GND |
| Raspberry Pi Pico | USB-A port → appears as `/dev/ttyACM0` or `/dev/ttyACM1` |

### Raspberry Pi Pico — Grove Base Hat for Pico

| Component | Connection |
|---|---|
| Grove LCD 16×2 | I2C1 port: SDA=**GP6**, SCL=**GP7**, addr `0x3E` |
| pH probe | ADC **A0** (GP26) |
| Rotation angle sensor | ADC **A1** (GP27) — switches LCD pages / confirms calibration |
| Button | **D16** (GP16), active-HIGH, PULL_DOWN — pause/resume + calibration confirm |
| HX711 load cell | CLK=**GP18**, DAT=**GP20** |

### Wiring notes

- NeoPixel LEDs draw up to 0.95 A at full white — use an external 5V PSU, not the RPi's 5V pin. Share GND between RPi and PSU.
- The Pico's USB port handles both power and serial communication. Just plug it into one of the RPi's USB-A ports.
- pH probe: the glass electrode connects to the BNC adapter on the Grove pH board. Keep it submerged or capped when not in use.
- HX711 load cell: place the fermentation vessel on the scale **before** starting `main_loop.py`. The Pico zeros the weight delta (`weight_delta_g`) on the first reading after boot, so whatever is on the scale at that moment becomes the baseline. Mass lost during fermentation (CO₂ off-gassing) shows up as an increasingly negative `weight_delta_g`.
  - Calibration constants in `pico_main.py`: `TARE = -762518`, `SCALE = 396.4` — re-calibrate if the load cell or amplifier board is swapped.

---

## 3. Repository Structure

### Raspberry Pi files (this repo)

```
BSC_Raspberry/
│
├── main_loop.py          Main data collection loop — start this to run a fermentation
├── fermentation_sim.py   Regression-based simulation model (port of xsimulation.ch)
├── ph_reader.py          USB serial reader for Pico — parses pH/weight JSON
├── htu21d_reader.py      I2C driver for the HTU21D temperature/humidity sensor
├── cameras.py            Camera capture + NeoPixel LED control (all camera settings live here)
├── verify_ph.py          Pre-run pH probe verification script
│
├── new_run.sh            Archive previous run, optionally edit recipe, start new run
│
├── test.py               Full hardware test suite (all components)
├── test_led.py           Quick NeoPixel LED test — blink + colour sweep
├── test_htu21.py         Quick HTU21D sensor test — 10 readings, 2 s apart
├── focus_test.py         Manual lens sweep (positions 3.0–5.0) to find best focus distance
│
├── scale2.py             HX711 load cell test (development/debug use)
└── scale_test.py         HX711 load cell test with reset sequence (development/debug use)
```

> **Pico firmware** (`pico_main.py`) is a separate file that runs on the Pico itself. It is not part of this repository. Upload it to the Pico as `main.py` using Thonny or `mpremote`.

### Data directory on Raspberry Pi

```
/home/schmiru/Kombucha_Fermentation/
│
├── sensor_log.csv         Live measurement log (appended every 15 min)
├── simulation_curve.csv   Pre-computed expected curve for the current recipe
├── calibration.json       pH calibration voltages (written on first Pico reading)
├── ph_verification.json   Pre-run probe check result (written by new_run.sh / verify_ph.py)
├── images/                Timestamped camera captures (one per hour)
├── .start_time            ISO timestamp of when the current run started
│
├── run_1/                 ← archived by new_run.sh
│   ├── sensor_log.csv
│   ├── simulation_curve.csv
│   ├── calibration.json
│   ├── ph_verification.json
│   ├── images/
│   └── .start_time
└── run_2/ …
```

---

## 4. Installation

### Raspberry Pi

**Enable interfaces** (once, via `sudo raspi-config`):
- `Interfaces → I2C` → Enable
- `Interfaces → SPI` → Enable

**Install Python dependencies:**
```bash
pip3 install smbus2 pyserial \
             adafruit-circuitpython-neopixel-spi \
             --break-system-packages
```

**Clone the repo:**
```bash
cd /home/schmiru
git clone <repo-url> BSC_Raspberry
cd BSC_Raspberry
```

**Verify everything works:**
```bash
python3 test.py
```

### Pico

1. Open `pico_main.py` in **Thonny** (or use `mpremote`)
2. Connect Pico via USB
3. Save the file to the Pico as **`main.py`**
4. The Pico will auto-start on power-up

### Systemd service (optional — autostart on boot)

```bash
sudo nano /etc/systemd/system/kombucha.service
```

```ini
[Unit]
Description=Kombucha Fermentation Monitor
After=multi-user.target

[Service]
ExecStart=/usr/bin/python3 /home/schmiru/BSC_Raspberry/main_loop.py
WorkingDirectory=/home/schmiru/BSC_Raspberry
User=schmiru
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable kombucha
sudo systemctl start kombucha
```

---

## 5. Configuration

All configuration for a run lives at the top of **`main_loop.py`**:

```python
RECIPE = SimConfig(
    tea_g_l        = 10.0,    # Tea concentration [g/L]  (range: 1–10)
    inoculum_pct   = 10.0,    # Starter culture   [%]    (range: 1–10)
    sugar_g_l      = 40.0,    # Sugar             [g/L]  (range: 40–100)
    temp_c         = 22.0,    # Target temperature [°C]  (range: 20–30)
    is_green_tea   = True,    # True = green tea, False = black tea
    total_days     = 7.0,     # Expected fermentation duration [days]
    tol_ph         = 0.3,     # pH deviation tolerance before alert
    tol_temp_c     = 4.0,     # Temperature deviation tolerance before alert

    # Temperature mode:
    # "static"  → use temp_c for the whole run (simple)
    # "dynamic" → HTU21D readings continuously update the expected values
    temp_mode      = "dynamic",
)

MEASURE_INTERVAL_S = 60 * 15   # how often to read sensors (seconds)
CAMERA_INTERVAL_S  = 60 * 60   # how often to take a photo (seconds)
CAMERA_INDICES     = [0]        # list of camera indices; add 1 for second camera
```

Camera and LED settings are in **`cameras.py`**:

```python
FOCUS_MODE           = "manual"  # "manual" = fixed lens position (autofocus non-functional on this setup)
                                 # "auto"   = autofocus (kept as option; not used in production)
AUTOFOCUS_RANGE      = "macro"   # "normal" | "macro" | "full" — only used when FOCUS_MODE = "auto"
MANUAL_LENS_POSITION = 5.4       # only used when FOCUS_MODE = "manual"
                                 # 0.0 = infinity, ~5.0 = ~20 cm, ~10.0 = ~10 cm
                                 # use focus_test.py to determine the best value for your setup
WIDTH    = 2400
HEIGHT   = 2400
```

---

## 6. Running a Fermentation

### Pre-run checklist

1. **Calibrate the pH probe** on the Pico LCD:
   - Rotate the knob right → select `CALIBRATE`
   - Follow the on-screen prompts with pH 7 buffer, then pH 4 buffer
   - Calibration is saved to `cal.json` on the Pico (survives reboots)

2. **Verify the probe** reads correctly:
   ```bash
   python3 verify_ph.py
   ```
   This guides you through pH 7 → rinse → pH 4 and reports pass/warn/fail.
   > **Note:** `new_run.sh` runs this automatically and saves the result as `ph_verification.json`. If you are starting via `new_run.sh` you don't need to run it manually.

3. **Test all hardware:**
   ```bash
   python3 test.py
   ```

4. **Update the recipe** in `main_loop.py` if needed.

5. **Place the fermentation vessel on the scale** before starting `main_loop.py`. The Pico zeroes `weight_delta_g` on its first reading — anything added to the scale after that will show as drift.

### Starting a run

**Option A — screen session (recommended for development):**
```bash
screen -S kombucha
cd /home/schmiru/BSC_Raspberry
python3 main_loop.py
# Detach with:  Ctrl-A then D
# Reattach with: screen -r kombucha
```

**Option B — systemd:**
```bash
sudo systemctl start kombucha
journalctl -u kombucha -f    # follow live logs
```

**Option C — new_run.sh (recommended between runs):**
```bash
bash new_run.sh
```
This stops the current run, archives the data into a named folder, lets you edit the recipe, and starts fresh.

### What happens at startup

1. The simulation curve is computed from your recipe and saved to `simulation_curve.csv`
2. The curve is printed as a table in the console
3. `calibration.json` is written on the first successful Pico reading

### What happens every cycle

Every **15 minutes** (sensor cycle):
- pH, voltage, weight, and calibration voltages are read from the Pico
- Temperature and humidity are read from the HTU21D
- The measured temperature is fed into the dynamic simulation model (if `temp_mode = "dynamic"`)
- Measured values are compared to the simulation curve
- Any deviation outside tolerance prints an alert:
  - `⚠️ warn` if within 2× tolerance
  - `❌ alert` if beyond 2× tolerance
- Everything is appended to `sensor_log.csv`

Every **60 minutes** (camera cycle):
- LEDs turn on, warm up for 1 second
- Camera captures a 2400×2400 photo
- LEDs turn off
- Filename and result are logged to `sensor_log.csv`

### Monitoring

```bash
# If using screen:
screen -r kombucha

# If using systemd:
journalctl -u kombucha -f

# Watch the CSV live:
tail -f /home/schmiru/Kombucha_Fermentation/sensor_log.csv
```

### Archiving and starting a new run

```bash
bash new_run.sh
```
You will be prompted for a name (e.g. `run_1`). The script:
1. Stops the running process
2. Moves `sensor_log.csv`, `images/`, `.start_time`, `calibration.json`, `ph_verification.json` into `run_1/`
3. Copies `simulation_curve.csv` into `run_1/`
4. Offers to run `verify_ph.py` (guided probe check, result saved as `ph_verification.json`)
5. Shows the current recipe and offers to edit it
6. Starts the new run

---

## 7. Data Output

### `sensor_log.csv`

One row per sensor cycle (every 15 min) and one row per camera cycle (every 60 min):

| Column | Description |
|---|---|
| `timestamp` | ISO 8601 datetime |
| `day` | Fractional day since run start |
| `ph_measured` | Measured pH value |
| `ph_voltage` | Raw electrode voltage [V] |
| `ph_expected` | Model-predicted pH at this day |
| `ph_deviation` | \|measured − expected\| |
| `ph_status` | `ok` / `warn` / `alert` |
| `ph_source` | `auto` (periodic) or `manual` (triggered via Pico LCD) |
| `ph_v_ph7` | Calibration voltage at pH 7 [V] |
| `ph_v_ph4` | Calibration voltage at pH 4 [V] |
| `weight_g` | Absolute vessel weight [g] from HX711 load cell |
| `weight_delta_g` | Weight change since run start [g] — tracks CO₂ off-gassing (grows more negative as fermentation progresses) |
| `temp_measured` | Measured temperature [°C] |
| `temp_expected` | Target temperature from recipe [°C] |
| `temp_deviation` | \|measured − target\| |
| `temp_status` | `ok` / `warn` / `alert` |
| `sim_eff_temp` | Effective temperature used by the model: equals `temp_c` in static mode; running mean of all HTU21D readings so far in dynamic mode |
| `humidity` | Relative humidity [%] |
| `static_ph` | Recipe-as-planned pH (always uses `temp_c`, never changes) |
| `static_sucrose` | Static sucrose [g/L] |
| `static_glucose` | Static glucose [g/L] |
| `static_fructose` | Static fructose [g/L] |
| `static_ethanol` | Static ethanol [g/L] |
| `static_acetic_acid` | Static acetic acid [mg/L] |
| `static_yeasts` | Static yeast count [log₁₀ KBE/ml] |
| `static_aab` | Static AAB count [log₁₀ KBE/ml] |
| `dyn_ph` | Temperature-corrected pH (updates as room temp changes) |
| `dyn_sucrose` | Dynamic sucrose [g/L] |
| `dyn_glucose` | Dynamic glucose [g/L] |
| `dyn_fructose` | Dynamic fructose [g/L] |
| `dyn_ethanol` | Dynamic ethanol [g/L] |
| `dyn_acetic_acid` | Dynamic acetic acid [mg/L] |
| `dyn_yeasts` | Dynamic yeast count [log₁₀ KBE/ml] |
| `dyn_aab` | Dynamic AAB count [log₁₀ KBE/ml] |
| `image_cam0` | Filename of the photo, or empty if no photo this cycle |
| `image_cam1` | Reserved for second camera |

> In **static mode**, `static_*` and `dyn_*` columns are identical. In **dynamic mode** they diverge whenever the actual room temperature differs from `temp_c`.

### `calibration.json`

Written once at the start of each run, on the first successful Pico reading:

```json
{
  "saved_at": "2026-05-29T10:23:00",
  "v_ph7": 1.712,
  "v_ph4": 1.931,
  "source": "auto"
}
```

### `ph_verification.json`

Written by `verify_ph.py --save` (called automatically by `new_run.sh`). Records pre-run probe accuracy:

```json
{
  "timestamp": "2026-05-29T09:15:00",
  "ph7": { "average": 7.03, "spread": 0.01, "deviation": 0.03, "status": "pass" },
  "ph4": { "average": 4.11, "spread": 0.02, "deviation": 0.11, "status": "warn" },
  "overall": "warn"
}
```

`overall` is `"pass"` if both buffers pass (±0.10), `"warn"` if any is within ±0.20, or `"fail"` if outside ±0.20.

### `simulation_curve.csv`

Pre-computed expected values at 0.1-day resolution for the full run. Columns: `day`, `pH`, `sucrose_g_l`, `glucose_g_l`, `fructose_g_l`, `ethanol_g_l`, `acetic_acid_mg_l`, `yeasts_log10_kbe_ml`, `aab_log10_kbe_ml`.

### `images/`

Files named `cam0_YYYYMMDD_HHMMSS_dayX.XX.jpg`. Resolution: 2400×2400 px.

---

## 8. Simulation Model

`fermentation_sim.py` is a direct Python port of the regression model from [xsimulation.ch/kombucha](https://xsimulation.ch/kombucha).

**How it works:**
- Five recipe inputs are fed into polynomial regression coefficients: tea [g/L], inoculum [%], sugar [g/L], temperature [°C], tea type (0/1)
- Eight variables are predicted over time: pH, sucrose, glucose, fructose, ethanol, acetic acid, yeasts (log₁₀ KBE/ml), AAB (log₁₀ KBE/ml)
- The polynomial coefficients are linear combinations of the input factors — this is why changing one recipe parameter shifts the entire predicted curve

**Static vs dynamic temperature:**

| Mode | Behaviour |
|---|---|
| `"static"` | One curve is computed at startup using `temp_c`. Expected values never change. |
| `"dynamic"` | Each HTU21D reading is recorded. `at(day)` re-evaluates the model using the time-weighted mean of all readings so far. |

Dynamic mode is more accurate when room temperature fluctuates: if the batch spent 5 days at 20°C and 2 days at 24°C, the model uses ~21.1°C (arithmetic mean of equally-spaced readings, equivalent to a time-weighted average).

**What gets logged each cycle:**

| CSV columns | Source | Changes during run? |
|---|---|---|
| `static_ph` … `static_aab` | `at_static(day)` — recipe as planned, always `temp_c` | ❌ Never — pure recipe baseline |
| `dyn_ph` … `dyn_aab` | `at(day)` — uses `sim_eff_temp` (running mean of HTU21D readings) | ✅ Yes, as room temp evolves |
| `sim_eff_temp` | Arithmetic mean of all HTU21D readings up to this point | ✅ Yes, converges over time |

Comparing `static_*` against `dyn_*` in your CSV shows how much the actual room temperature deviated from the recipe target and how that shifted the predicted fermentation trajectory.

**Deviation classification:**

| Status | Condition |
|---|---|
| `ok` | deviation ≤ tolerance |
| `warn` | deviation ≤ 2× tolerance |
| `alert` | deviation > 2× tolerance |

---

## 9. Camera & LED Settings

All camera and LED settings are in `cameras.py`. The main loop and `focus_test.py` both import from there, so you only ever need to edit one file.

### Focus modes

**Manual focus (current default — autofocus is non-functional on this setup):**
```python
FOCUS_MODE           = "manual"
MANUAL_LENS_POSITION = 5.4   # higher = closer focus
                              # 0.0 = infinity  ~2.0 = 50 cm
                              # ~5.0 = 20 cm    ~10.0 = 10 cm
```
Set `MANUAL_LENS_POSITION` once in `cameras.py`; every capture (main loop + focus_test) will use it.

**Autofocus (kept as option, not used in production):**
```python
FOCUS_MODE      = "auto"
AUTOFOCUS_RANGE = "macro"   # "normal" | "macro" | "full"
```
> ⚠️ Autofocus does not work reliably on the camera used in this project. Keep `FOCUS_MODE = "manual"`.

### Finding the right lens position

```bash
python3 focus_test.py
```
Sweeps through lens positions **3.0 → 3.5 → 4.0 → 4.5 → 5.0**, saving one image per position as `focus_3.0.jpg`, `focus_3.5.jpg`, etc. LEDs are on during the sweep. Compare the results, then set `MANUAL_LENS_POSITION` in `cameras.py` to the sharpest value.

### LED brightness

Set in `cameras.py` at the NeoPixel initialisation:
```python
pixels = neospi.NeoPixel_SPI(..., brightness=0.5, ...)
```
Range 0.0–1.0. `0.5` is the current default.

---

## 10. Testing & Calibration Tools

| Script | What it does | When to run |
|---|---|---|
| `python3 test.py` | Full hardware test: simulation, HTU21D, Pico/pH, LEDs, camera | Before every run |
| `python3 test.py --sim` | Test simulation model only | After recipe changes |
| `python3 test.py --temp` | Test HTU21D only | If temp readings look wrong |
| `python3 test.py --ph` | Test Pico connection and pH reading | If pH fails in main loop |
| `python3 test.py --led` | Test all 56 LEDs, asks for visual confirmation | After LED hardware changes |
| `python3 test.py --camera` | Test camera capture with LEDs | After camera changes |
| `python3 verify_ph.py` | Guided pH 7 → pH 4 probe verification, reports pass/warn/fail. Runs automatically via `new_run.sh --save`; run manually if starting without the script. | Before every run |
| `python3 focus_test.py` | Lens position sweep (3.0 → 3.5 → 4.0 → 4.5 → 5.0) with LEDs on → compare `focus_*.jpg` to find best `MANUAL_LENS_POSITION` | After adjusting camera distance |
| `python3 test_led.py` | Blink test + colour sweep for 56 LEDs | LED hardware debug |
| `python3 test_htu21.py` | 10 temperature/humidity readings, 2 s apart | HTU21D debug |

---

## 11. Troubleshooting

### Pico not found
```
[main] Pico not found — pH readings will be skipped
```
- Check USB cable is connected
- Run `ls /dev/ttyACM*` — should show `/dev/ttyACM0` or `/dev/ttyACM1`
- Make sure `pico_main.py` is running on the Pico (the LCD should show pH/weight)
- The port alternates between ACM0 and ACM1 on reconnect — `ph_reader.py` handles this automatically via USB vendor ID

### HTU21D not found
```
[main] HTU21D not available
```
- Verify I2C is enabled: `sudo raspi-config → Interfaces → I2C`
- Check wiring: SDA=Pin3, SCL=Pin5, VCC=3.3V (Pin1), GND
- Confirm sensor is visible: `i2cdetect -y 1` should show `40`

### NeoPixel LEDs not lighting up
- SPI must be enabled: `sudo raspi-config → Interfaces → SPI`
- Data wire must be on GPIO 10 (Pin 19 / MOSI)
- External 5V PSU required — RPi 5V pin cannot supply enough current
- GND must be shared between RPi and the PSU
- If only the first ~16 LEDs light up: PSU is too weak

### Camera capture fails
- Check ribbon cable is seated properly in CAM 0
- Verify with: `rpicam-still --list-cameras`
- Camera must not be in use by another process

### pH readings look wrong after calibration
1. Run `python3 verify_ph.py` — if it fails, recalibrate on the Pico LCD
2. On the Pico LCD: rotate knob right → `CALIBRATE` → follow prompts
3. Use fresh pH 4 and pH 7 buffer solutions
4. Allow the probe 60+ seconds to stabilise in each buffer before confirming

### pH tolerance alerts at the start of a run
Normal behaviour. The inoculum immediately acidifies the broth, so the measured pH drops faster than the model predicts in the first 12–24 hours. Set `tol_ph = 2.0` in the recipe if alerts are unwanted during this phase.

---

## Dependencies

```bash
# Raspberry Pi
pip3 install smbus2 pyserial \
             adafruit-circuitpython-neopixel-spi \
             --break-system-packages

# Pico (MicroPython — all built-in)
# machine, time, ujson, sys
```
