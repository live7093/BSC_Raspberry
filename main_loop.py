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
import json
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
    tea_g_l        = 10.0,
    inoculum_pct   = 10.0,
    sugar_g_l      = 40.0,
    temp_c         = 22.0,   # target / room-temp estimate
    is_green_tea   = True,
    total_days     = 7.0,
    tol_ph         = 0.3,
    tol_temp_c     = 4.0,
    #
    # "static"  → use temp_c for the whole run (simple, predictable)
    # "dynamic" → feed each HTU21D reading into the model so expected
    #             values track the real room temperature over time
    temp_mode      = "dynamic",
)

# ── Timing ───────────────────────────────────────────────────
MEASURE_INTERVAL_S = 60 * 15   # sensor reading every 30 min
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
    "ph_v_ph7",            # calibration voltage at pH 7 (from Pico cal.json)
    "ph_v_ph4",            # calibration voltage at pH 4 (from Pico cal.json)
    "weight_g",            # absolute vessel weight [g] from HX711
    "weight_delta_g",      # weight change since run start [g] (tracks CO₂ loss)
    "temp_measured", "temp_expected", "temp_deviation", "temp_status",
    "sim_eff_temp",        # effective temp used by model (= temp_c in static, running mean in dynamic)
    "humidity",
    # ── Static simulation: recipe as planned (always temp_c, never changes) ──
    "static_ph", "static_sucrose", "static_glucose", "static_fructose",
    "static_ethanol", "static_acetic_acid", "static_yeasts", "static_aab",
    # ── Dynamic simulation: updated each cycle with actual room temperature ──
    "dyn_ph", "dyn_sucrose", "dyn_glucose", "dyn_fructose",
    "dyn_ethanol", "dyn_acetic_acid", "dyn_yeasts", "dyn_aab",
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


CAL_FILE = os.path.join(PROJECT_DIR, "calibration.json")

def save_calibration(reading) -> None:
    """Write pH calibration voltages to calibration.json once per run.

    Called on the first successful Pico reading so the file is always
    present in the run folder when new_run.sh archives it.
    """
    if os.path.exists(CAL_FILE):
        return   # already written for this run
    data = {
        "saved_at":  datetime.now().isoformat(timespec="seconds"),
        "v_ph7":     reading.v_ph7,
        "v_ph4":     reading.v_ph4,
        "source":    reading.source,
    }
    with open(CAL_FILE, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"[cal]  Calibration saved → {CAL_FILE}  "
          f"(pH7={reading.v_ph7:.3f} V  pH4={reading.v_ph4:.3f} V)")


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
    print(f"[main] Temp mode            : {RECIPE.temp_mode}"
          + (f"  (target {RECIPE.temp_c}°C, updates from HTU21D each cycle)"
             if RECIPE.temp_mode == "dynamic" else f"  (fixed {RECIPE.temp_c}°C)"))
    print("[main] Starting loop — press Ctrl-C to stop\n")

    # Initialise to -interval so the very first loop iteration fires both
    # cycles immediately, regardless of how long the Pi has been running.
    last_measure = -MEASURE_INTERVAL_S
    last_camera  = -CAMERA_INTERVAL_S

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

                # Feed temperature into the dynamic model
                if temp is not None:
                    sim.update_temp(day, temp)

                # ── Deviation check ───────────────────────────
                result = sim.check_deviation(
                    day           = day,
                    measured_ph   = ph_reading.ph   if ph_reading else None,
                    measured_temp = temp,
                )

                # ── Fill log row ──────────────────────────────
                if ph_reading:
                    row["ph_measured"]    = ph_reading.ph
                    row["ph_voltage"]     = ph_reading.voltage
                    row["ph_source"]      = ph_reading.source
                    row["ph_v_ph7"]       = ph_reading.v_ph7
                    row["ph_v_ph4"]       = ph_reading.v_ph4
                    if ph_reading.weight_g is not None:
                        row["weight_g"]       = ph_reading.weight_g
                    if ph_reading.weight_delta_g is not None:
                        row["weight_delta_g"] = ph_reading.weight_delta_g
                    save_calibration(ph_reading)

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

                row["sim_eff_temp"] = sim.effective_temp(day)

                # ── Static vs dynamic simulation points ───────
                s = sim.at_static(day)
                row["static_ph"]          = s.pH
                row["static_sucrose"]     = s.sucrose
                row["static_glucose"]     = s.glucose
                row["static_fructose"]    = s.fructose
                row["static_ethanol"]     = s.ethanol
                row["static_acetic_acid"] = s.acetic_acid
                row["static_yeasts"]      = s.yeasts
                row["static_aab"]         = s.aab

                d = sim.at(day)
                row["dyn_ph"]          = d.pH
                row["dyn_sucrose"]     = d.sucrose
                row["dyn_glucose"]     = d.glucose
                row["dyn_fructose"]    = d.fructose
                row["dyn_ethanol"]     = d.ethanol
                row["dyn_acetic_acid"] = d.acetic_acid
                row["dyn_yeasts"]      = d.yeasts
                row["dyn_aab"]         = d.aab

                append_log(row)

                # ── Console print ─────────────────────────────
                ph_str  = f"{ph_reading.ph:.2f} ({ph_reading.source})" if ph_reading else "—"
                wt_str  = (f"{ph_reading.weight_g:.0f}g "
                           f"(Δ{ph_reading.weight_delta_g:+.1f}g)"
                           if ph_reading and ph_reading.weight_g is not None else "—")
                temp_str = f"{temp:.1f}°C" if temp is not None else "—"
                hum_str  = f"{hum:.1f}%" if hum is not None else "—"
                eff_str  = (f"  eff_temp={sim.effective_temp(day):.2f}°C"
                            if RECIPE.temp_mode == "dynamic" else "")
                print(f"[{ts}]  day={day:.3f}  pH={ph_str}  wt={wt_str}  temp={temp_str}  hum={hum_str}{eff_str}")

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
