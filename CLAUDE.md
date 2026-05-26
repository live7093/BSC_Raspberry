# Kombucha Fermentation Monitor — Project Documentation
**BSC Project — Ruben Schmid, ZHAW**

---

## Hardware Overview

### Raspberry Pi 5
- **Camera** (ribbon cable) → CSI port CAM 0
- **HTU21D** (temp/humidity) → I2C bus 1 (SDA=GPIO2 Pin3, SCL=GPIO3 Pin5)
- **56× NeoPixel LEDs** (WS2812B) → SPI MOSI GPIO10 (Pin19), powered by external PSU with shared GND
- **Pico** → USB-A port (appears as `/dev/ttyACM0` or `/dev/ttyACM1`)

### Raspberry Pi Pico (MicroPython)
Connected via **Grove Base Hat for Pico**:
- **Grove LCD 16×2** → I2C1 port (SDA=GP6, SCL=GP7), addr 0x3E, single backlight (no RGB)
- **pH probe** → ADC A0 (GP26)
- **Rotation angle sensor** → ADC A1 (GP27)
- **Button** → D16 (GP16), **active-HIGH**, PULL_DOWN
- **HX711 load cell** → D18/D20 (GP18=CLK, GP20=DAT)

---

## Project Directory Structure

```
/home/schmiru/BSC_Raspberry/          ← all RPi Python files
/home/schmiru/Kombucha_Fermentation/  ← data output directory
    simulation_curve.csv              ← generated on each run start
    sensor_log.csv                    ← continuous measurement log
    images/                           ← timestamped camera captures
    run_1/, run_2/, ...               ← archived previous runs
```

---

## File Reference

### Raspberry Pi Files

#### `main_loop.py`
Main data collection loop. Run this to start a fermentation run.
- Reads pH + weight from Pico every 30 min (via `ph_reader.py`)
- Reads temp/humidity from HTU21D every 30 min (via `htu21d_reader.py`)
- Takes photos every 60 min (via `cameras.py`, LEDs on during capture)
- Compares readings against simulation curve, logs deviations
- Saves all data to `sensor_log.csv`
- Contains **ESCALATION HOOK** comment for future alert pipeline

**Key config at top of file:**
```python
RECIPE = SimConfig(
    tea_g_l        = 8.0,
    inoculum_pct   = 10.0,
    sugar_g_l      = 100.0,
    temp_c         = 25.0,
    is_green_tea   = False,
    total_days     = 10.0,
    tol_ph         = 0.3,
    tol_temp_c     = 2.0,
)
MEASURE_INTERVAL_S = 60 * 15   # sensor reading interval
CAMERA_INTERVAL_S  = 60 * 60   # photo interval
CAMERA_INDICES     = [0]        # change to [0, 1] when second camera added
```

---

#### `fermentation_sim.py`
Fermentation simulation model. **Exact port of xsimulation.ch/kombucha regression model.**
- Uses `regression_models.json` coefficients directly (hardcoded)
- `predict_time_series()` is a direct Python port of `predict_time_series.js`
- Factor order: `[tea_g_l, inoculum_pct, sugar_g_l, temp_c, is_green_tea (0|1)]`
- Predicts: pH, Sucrose, Glucose, Fructose, Ethanol, Acetic acid, Yeasts, AAB

**Usage:**
```python
from fermentation_sim import FermentationSim, SimConfig
sim = FermentationSim(SimConfig(tea_g_l=8, sugar_g_l=100, inoculum_pct=10, temp_c=25))
sim.save_csv("simulation_curve.csv")
result = sim.check_deviation(day=3.0, measured_ph=3.8, measured_temp=24.5)
```

---

#### `ph_reader.py`
Reads pH + weight JSON from Pico over USB serial.
- Auto-detects Pico by USB vendor ID (no hardcoded port)
- Parses JSON: `{"ph", "voltage", "weight_g", "weight_delta_g", "v_ph7", "v_ph4", "source"}`
- Skips non-JSON lines (boot messages, errors)
- `PicoReader` class keeps persistent serial connection open

**Standalone monitor:**
```bash
python3 ph_reader.py
```

---

#### `cameras.py`
Camera capture with NeoPixel LED illumination.
- LEDs: 56× NeoPixels, brightness=0.1, SPI (GPIO10/MOSI)
- Uses `rpicam-still` for capture
- `capture_frame(camera_index, output_path)` — used by main_loop
- `CAMERA_INDICES = [0]` — add `1` when second camera arrives
- Lens position: `MANUAL_LENS_POSITION = 5.0` (~17.5 cm distance)
- Resolution: `WIDTH = HEIGHT = 1920` (square)

---

#### `htu21d_reader.py`
HTU21D temperature/humidity sensor driver.
- I2C bus 1, addr 0x40
- `read_both()` returns `(temp_celsius, humidity_percent)`
- Uses `smbus2` library

---

#### `verify_ph.py`
Pre-run pH probe verification script. Run before starting a new fermentation.
- Guides through pH7 → rinse → pH4 verification
- Tolerance: ±0.10 pass, ±0.20 warn, outside = fail
- Does NOT change calibration (use Pico LCD for that)

```bash
python3 verify_ph.py
```

---

#### `test.py`
Hardware connection test for all components. Safe to run anytime.
```bash
python3 test.py              # test everything
python3 test.py --sim        # simulation only
python3 test.py --temp       # HTU21D only
python3 test.py --ph         # Pico/pH only
python3 test.py --led        # LEDs only
python3 test.py --camera     # camera only
```

---

#### `test_led.py`
Quick NeoPixel LED test. Blinks 5×, holds ON 5s, colour sweep.
```bash
python3 test_led.py
```

---

#### `test_htu21d.py`
Quick HTU21D sensor test. Takes 10 readings, 2s apart.
```bash
python3 test_htu21d.py
```

---

#### `new_run.sh`
Shell script to archive previous run data and start a new run.
- Stops current run (systemctl or screen)
- Archives `sensor_log.csv`, `images/`, `.start_time` to named folder
- Shows current recipe, offers to edit `main_loop.py`
- Starts new run

```bash
bash new_run.sh           # interactive
bash new_run.sh run_1     # pass archive name directly
```

---

#### `kombucha_simulator.html`
Browser-based fermentation dashboard.
- Same regression model as `fermentation_sim.py`
- Recipe sliders on left, chart on right
- Live sensor overlay: enter measured pH/temp → shows deviation from recipe
- 5 chart views: pH, Sugars, Acids, Biomass, All
- Tolerance bands configurable

---

### Pico File

#### `pico_main.py` → uploaded to Pico as `main.py`
MicroPython firmware. Runs automatically on Pico boot.
- **2-page UI**: rotation knob switches pages, button confirms
  - **Page 0 (RUNNING)**: live pH + weight on LCD, emits JSON every 30s, button pauses/resumes
  - **Page 1 (CALIBRATE)**: guided pH7→pH4 calibration, saves to `cal.json`, rotate left to abort
- **HX711**: TARE=-762518, SCALE=396.4 (calibrated values)
- **pH calibration**: stored in `cal.json` on Pico filesystem, survives reboots
- **Weight delta**: zeroed on first reading after boot, tracks CO₂ loss over run
- **Serial output** every 30s:
```json
{"ph": 3.82, "voltage": 1.234, "weight_g": 1205.3,
 "weight_delta_g": -4.7, "v_ph7": 1.712, "v_ph4": 1.931, "source": "auto"}
```

---

## Running a Fermentation Run

### Pre-run checklist
1. Calibrate pH on Pico LCD (rotate right → CALIBRATE → follow prompts with pH4/pH7 buffers)
2. Verify probe: `python3 verify_ph.py`
3. Test all hardware: `python3 test.py`
4. Update recipe in `main_loop.py` if needed
5. Place vessel on scale

### Start run
```bash
screen -S kombucha
cd /home/schmiru/BSC_Raspberry
python3 main_loop.py
# Ctrl+A then D to detach
```

### Monitor
```bash
screen -r kombucha          # reattach
journalctl -u kombucha -f   # if using systemd
```

### Start new run / archive old data
```bash
bash new_run.sh
```

---

## Systemd Service (optional autostart)

```bash
# Enable
sudo systemctl enable kombucha
sudo systemctl start kombucha

# Disable
sudo systemctl stop kombucha
sudo systemctl disable kombucha

# Logs
journalctl -u kombucha -f
```

Service file: `/etc/systemd/system/kombucha.service`

---

## Dependencies

### Raspberry Pi
```bash
pip3 install RPi.GPIO smbus2 pyserial matplotlib \
             adafruit-circuitpython-neopixel-spi --break-system-packages
```

### Pico (MicroPython — built-in)
`machine`, `time`, `ujson`, `sys`

---

## Known Issues / Notes
- Pico serial port alternates between `/dev/ttyACM0` and `/dev/ttyACM1` on reconnect — `ph_reader.py` auto-detects by USB vendor ID so this is handled
- NeoPixel LEDs require **SPI enabled** on RPi (`raspi-config → Interfaces → SPI`)
- HTU21D requires **I2C enabled** on RPi (`raspi-config → Interfaces → I2C`)
- Second camera: change `CAMERA_INDICES = [0, 1]` in `cameras.py` and `main_loop.py`
- pH tolerance `tol_ph = 2.0` recommended (starter immediately acidifies broth, simulation starts at ~4.6)
