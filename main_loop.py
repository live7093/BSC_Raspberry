#!/usr/bin/env python3
"""
main_loop.py
------------
Kombucha Fermentation – Main Data Collection Loop
BSC project – Ruben Schmid

Wires together:
  • fermentation_sim  → pre-computed recipe curve + deviation checks
  • ph_reader         → Pico USB (JSON pH readings from pico_main.py)
  • htu21d_reader     → Raspberry Pi I2C temperature / humidity
  • cameras           → single camera, LED-illuminated capture (GPIO 10)

Run:
    python3 main_loop.py

All readings and deviations are appended to sensor_log.csv so you can
compare measured data against the simulation curve at any time.

Camera indices: currently [0]. Add 1 when second camera arrives — the
CAMERA_INDICES list below is the only thing that needs changing.
"""

import csv
import os
import time
from datetime import datetime

# ── Local modules ─────────────────────────────────────────────
from fermentation_sim import FermentationSim, SimConfig
from htu21d_reader    import HTU21D
from ph_reader        import PicoReader, find_pico_port
from cameras          import setup_gpio, cleanup_gpio, capture_frame

# ════════════════════════════════════════════════════════════
#  CONFIGURATION  –  edit to match your batch
# ════════════════════════════════════════════════════════════

PROJECT_DIR = "/home/schmiru/Kombucha_Fermentation"

# ── Recipe ───────────────────────────────────────────────────
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

# ── Timing ───────────────────────────────────────────────────
MEASURE_INTERVAL_S = 60 * 30   # sensor reading every 30 min
CAMERA_INTERVAL_S  = 60 * 60   # photo every 60 min

# ── Cameras  ─────────────────────────────────────────────────
# Currently one camera (index 0).
# To add a second camera later: change to [0, 1] — nothing else changes.
CAMERA_INDICES = [0]

# ── File paths ───────────────────────────────────────────────
SIM_CURVE_CSV   = os.path.join(PROJECT_DIR, "simulation_curve.csv")
SENSOR_LOG_CSV  = os.path.join(PROJECT_DIR, "sensor_log.csv")
IMAGE_DIR       = os.path.join(PROJECT_DIR, "images")
START_TIME_FILE = os.path.join(PROJECT_DIR, ".start_time")

# ════════════════════════════════════════════════════════════
#  CSV log schema
# ════════════════════════════════════════════════════════════

LOG_FIELDS = [
    "timestamp", "day",
    "ph_measured", "ph_voltage", "ph_expected", "ph_deviation", "ph_status",
    "ph_source",           # "auto" or "manual" (triggered from Pico LCD)
    "temp_measured", "temp_expected", "temp_deviation", "temp_status",
    "humidity",
    "image_cam0",          # filename or "" if capture failed
    "image_cam1",          # reserved for second camera
]

# ════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════

def get_or_set_start_time() -> datetime:
    if os.path.exists(START_TIME_FILE):
        with open(START_TIME_FILE) as f:
            return datetime.fromisoformat(f.read().strip())
    now = datetime.now()
    os.makedirs(PROJECT_DIR, exist_ok=True)
    with open(START_TIME_FILE, "w") as f:
        f.write(now.isoformat())
    print(f"[main] Fermentation start recorded: {now.isoformat()}")
    return now


def current_day(start: datetime) -> float:
    return (datetime.now() - start).total_seconds() / 86400.0


def append_log(row: dict) -> None:
    write_header = not os.path.exists(SENSOR_LOG_CSV)
    with open(SENSOR_LOG_CSV, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({f: row.get(f, "") for f in LOG_FIELDS})


# ════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════

def main():
    os.makedirs(PROJECT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)

    # ── 1. Simulation curve ───────────────────────────────────
    print("[main] Building fermentation simulation curve …")
    sim = FermentationSim(RECIPE)
    sim.save_csv(SIM_CURVE_CSV)
    sim.print_table()

    # ── 2. HTU21D (temperature / humidity on RPi I2C) ─────────
    try:
        htu = HTU21D()
        print("[main] HTU21D connected ✅")
    except Exception as e:
        htu = None
        print(f"[main] HTU21D not available: {e}")

    # ── 3. Pico pH reader (persistent connection) ─────────────
    pico_port = find_pico_port()
    if pico_port:
        pico = PicoReader(port=pico_port)
        pico.open()
        print(f"[main] Pico connected on {pico_port} ✅")
    else:
        pico = None
        print("[main] Pico not found — pH readings will be skipped")

    # ── 4. GPIO / LEDs ────────────────────────────────────────
    setup_gpio()

    # ── 5. Fermentation clock ─────────────────────────────────
    start = get_or_set_start_time()
    print(f"[main] Fermentation started : {start.isoformat()}")
    print(f"[main] Sensor interval      : {MEASURE_INTERVAL_S // 60} min")
    print(f"[main] Camera interval      : {CAMERA_INTERVAL_S  // 60} min")
    print(f"[main] Active cameras       : {CAMERA_INDICES}")
    print("[main] Starting loop — press Ctrl-C to stop\n")

    last_measure = 0.0
    last_camera  = 0.0

    try:
        while True:
            now = time.monotonic()
            day = current_day(start)
            ts  = datetime.now().isoformat(timespec="seconds")

            # ══ Sensor cycle ══════════════════════════════════
            if now - last_measure >= MEASURE_INTERVAL_S:
                last_measure = now
                row = {"timestamp": ts, "day": round(day, 4)}

                # ── pH from Pico ──────────────────────────────
                ph_reading = None
                if pico:
                    try:
                        ph_reading = pico.read_one(timeout_s=35)
                    except Exception as e:
                        print(f"[pH] Read error: {e}")

                # ── Temperature / humidity from HTU21D ────────
                temp, hum = None, None
                if htu:
                    try:
                        temp, hum = htu.read_both()
                    except Exception as e:
                        print(f"[htu] Read error: {e}")

                # ── Deviation check ───────────────────────────
                result = sim.check_deviation(
                    day           = day,
                    measured_ph   = ph_reading.ph   if ph_reading else None,
                    measured_temp = temp,
                )

                # ── Fill log row ──────────────────────────────
                if ph_reading:
                    row["ph_measured"] = ph_reading.ph
                    row["ph_voltage"]  = ph_reading.voltage
                    row["ph_source"]   = ph_reading.source

                if hum is not None:
                    row["humidity"] = hum

                for v in result.variables:
                    if v.name == "pH":
                        row["ph_expected"]  = v.expected
                        row["ph_deviation"] = v.deviation
                        row["ph_status"]    = v.status
                    elif v.name == "temp_c":
                        row["temp_measured"]  = v.measured
                        row["temp_expected"]  = v.expected
                        row["temp_deviation"] = v.deviation
                        row["temp_status"]    = v.status

                append_log(row)

                # ── Console print ─────────────────────────────
                ph_str   = f"{ph_reading.ph:.2f} ({ph_reading.source})" if ph_reading else "—"
                temp_str = f"{temp:.1f}°C" if temp is not None else "—"
                hum_str  = f"{hum:.1f}%" if hum is not None else "—"
                print(f"[{ts}]  day={day:.3f}  pH={ph_str}  temp={temp_str}  hum={hum_str}")

                # ── Deviation alerts ──────────────────────────
                if result.any_deviation:
                    for v in result.variables:
                        if v.status != "ok":
                            flag = "⚠️ " if v.status == "warn" else "❌"
                            print(f"  {flag} {v.name}: "
                                  f"measured={v.measured}  expected={v.expected}  "
                                  f"dev=±{v.deviation}  tol=±{v.tolerance}  "
                                  f"→ {v.status.upper()}")
                            # ╔══════════════════════════════════╗
                            # ║  ESCALATION HOOK                 ║
                            # ║  plug in: Telegram, email,       ║
                            # ║  write_alert_csv(v), etc.        ║
                            # ╚══════════════════════════════════╝

            # ══ Camera cycle ══════════════════════════════════
            if now - last_camera >= CAMERA_INTERVAL_S:
                last_camera = now
                ts_img      = datetime.now().strftime("%Y%m%d_%H%M%S")
                cam_row     = {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "day":       round(day, 4),
                }

                for cam_idx in CAMERA_INDICES:
                    fname    = f"cam{cam_idx}_{ts_img}_day{day:.2f}.jpg"
                    out_path = os.path.join(IMAGE_DIR, fname)
                    ok       = capture_frame(cam_idx, out_path)
                    status   = "✅" if ok else "❌"
                    print(f"  📷 cam{cam_idx}: {status}  {fname}")
                    cam_row[f"image_cam{cam_idx}"] = fname if ok else ""

                append_log(cam_row)

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[main] Stopped by user.")
    finally:
        cleanup_gpio()
        if htu:
            htu.close()
        if pico:
            pico.close()
        print("[main] All hardware released. Goodbye.")


if __name__ == "__main__":
    main()
