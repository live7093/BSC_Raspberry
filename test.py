#!/usr/bin/env python3
"""
test.py
-------
Kombucha Fermentation Monitor – Hardware Connection Test
BSC project – Ruben Schmid

Tests each component independently and prints a clear pass/fail summary.
Safe to run at any time — does NOT start a fermentation run.

Usage:
    python3 test.py            # test everything
    python3 test.py --camera   # test only camera
    python3 test.py --ph       # test only pH / Pico
    python3 test.py --temp     # test only HTU21D
    python3 test.py --led      # test only LEDs
    python3 test.py --sim      # test only simulation model
"""

import argparse
import os
import sys
import time

# ── Output dir for test shots ─────────────────────────────────
TEST_SHOT_DIR = "/home/schmiru/Kombucha_Fermentation/test_shots"

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⏭  SKIP"
SEP  = "─" * 52


def header(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def result(label, ok, detail=""):
    status = PASS if ok else FAIL
    line   = f"  {status}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)
    return ok


# ════════════════════════════════════════════════════════════
#  1 – Simulation model
# ════════════════════════════════════════════════════════════

def test_sim():
    header("Simulation model")
    try:
        from fermentation_sim import FermentationSim, SimConfig
        cfg = SimConfig(tea_g_l=8, inoculum_pct=10, sugar_g_l=100,
                        temp_c=25, total_days=10)
        sim = FermentationSim(cfg)
        p   = sim.at(5.0)
        ok  = 2.0 < p.pH < 7.0 and p.sucrose >= 0
        result("Model computes", ok, f"pH at day 5 = {p.pH:.3f}")

        res = sim.check_deviation(day=3.0, measured_ph=3.8, measured_temp=24.5)
        result("Deviation check", True,
               f"pH status={res.variables[0].status}  "
               f"temp status={res.variables[1].status}")
        return ok
    except Exception as e:
        result("Simulation model", False, str(e))
        return False


# ════════════════════════════════════════════════════════════
#  2 – HTU21D temperature / humidity
# ════════════════════════════════════════════════════════════

def test_htu():
    header("HTU21D  (temperature / humidity  –  RPi I2C)")
    try:
        from htu21d_reader import HTU21D
        sensor = HTU21D()
        temp, hum = sensor.read_both()
        sensor.close()

        t_ok = -10 < temp < 60
        h_ok = 0   < hum  < 100
        result("Sensor detected",    True)
        result("Temperature reading", t_ok, f"{temp:.2f} °C")
        result("Humidity reading",    h_ok, f"{hum:.2f} %RH")
        return t_ok and h_ok
    except Exception as e:
        result("HTU21D", False, str(e))
        print("  Tip: check wiring (SDA=GPIO2, SCL=GPIO3) and that I2C")
        print("       is enabled via raspi-config → Interfaces → I2C")
        return False


# ════════════════════════════════════════════════════════════
#  3 – Pico / pH probe
# ════════════════════════════════════════════════════════════

def test_ph():
    header("Pico  (pH probe over USB serial)")
    try:
        from ph_reader import PicoReader, find_pico_port

        port = find_pico_port()
        if not result("Pico detected", port is not None,
                      port or "Not found — check USB cable"):
            print("  Tip: run  ls /dev/ttyACM*  to see connected serial devices")
            return False

        print(f"  → Waiting for JSON reading (up to 35 s) …")
        with PicoReader(port=port) as reader:
            reading = reader.read_one(timeout_s=35)

        if reading is None:
            result("pH reading received", False, "Timeout — is pico_main.py running?")
            return False

        ph_ok = 0 < reading.ph < 14
        v_ok  = 0 < reading.voltage < 3.3
        result("pH reading received", True)
        result("pH value plausible",   ph_ok,  f"pH = {reading.ph:.2f}")
        result("Voltage plausible",    v_ok,   f"{reading.voltage:.3f} V")
        result("Calibration present",  True,
               f"pH7={reading.v_ph7:.3f} V  pH4={reading.v_ph4:.3f} V  "
               f"source={reading.source}")
        return ph_ok and v_ok
    except Exception as e:
        result("Pico / pH", False, str(e))
        return False


# ════════════════════════════════════════════════════════════
#  4 – LEDs (NeoPixel SPI)
# ════════════════════════════════════════════════════════════

def test_led():
    header("LEDs  (NeoPixel SPI — 56 LEDs, brightness 0.1)")
    try:
        import board
        import neopixel_spi as neospi
        result("Library import", True)
    except ImportError as e:
        result("Library import", False, str(e))
        print("  Tip: pip3 install adafruit-circuitpython-neopixel-spi --break-system-packages")
        return False

    try:
        spi    = board.SPI()
        pixels = neospi.NeoPixel_SPI(spi, 56, brightness=0.1,
                                     auto_write=False, pixel_order=neospi.GRB)
        result("NeoPixel SPI init", True)
    except Exception as e:
        result("NeoPixel SPI init", False, str(e))
        print("  Tip: SPI enabled? raspi-config → Interfaces → SPI")
        return False

    print("  → Full white ON for 3 seconds — check all 56 LEDs …")
    pixels.fill((255, 255, 255))
    pixels.show()
    time.sleep(3)
    pixels.fill((0, 0, 0))
    pixels.show()
    print("  → LEDs OFF")

    ans = input("  Did all 56 LEDs light up? [y/n]: ").strip().lower()
    ok  = ans == "y"
    result("LED illumination", ok,
           "If only first 16 lit: power supply too weak (needs ~0.34A for 56 LEDs at 0.1)")
    return ok


# ════════════════════════════════════════════════════════════
#  5 – Camera + LED capture
# ════════════════════════════════════════════════════════════

def test_camera():
    header("Camera  (rpicam-still + LED capture)")
    os.makedirs(TEST_SHOT_DIR, exist_ok=True)

    try:
        from cameras import setup_gpio, cleanup_gpio, capture_frame, CAMERA_INDICES
    except Exception as e:
        result("Import cameras.py", False, str(e))
        return False

    setup_gpio()
    all_ok = True

    # Only test indices defined in cameras.py (currently [0])
    for idx in CAMERA_INDICES:
        ts       = time.strftime("%Y%m%d_%H%M%S")
        fname    = f"test_cam{idx}_{ts}.jpg"
        out_path = os.path.join(TEST_SHOT_DIR, fname)

        print(f"  → Capturing test shot on camera {idx} …")
        ok = capture_frame(idx, out_path)

        if ok:
            size_kb = os.path.getsize(out_path) // 1024
            result(f"Camera {idx} capture", True,
                   f"{fname}  ({size_kb} KB)  saved to {TEST_SHOT_DIR}")
        else:
            result(f"Camera {idx} capture", False,
                   "File missing or empty — check ribbon cable and camera index")
            all_ok = False

    cleanup_gpio()
    return all_ok


# ════════════════════════════════════════════════════════════
#  Summary
# ════════════════════════════════════════════════════════════

def print_summary(results: dict):
    print(f"\n{'═' * 52}")
    print("  SUMMARY")
    print(f"{'═' * 52}")
    all_pass = True
    for name, ok in results.items():
        if ok is None:
            print(f"  {SKIP}  {name}")
        else:
            print(f"  {'✅' if ok else '❌'}  {name}")
            if not ok:
                all_pass = False
    print(f"{'─' * 52}")
    if all_pass and None not in results.values():
        print("  All tests passed — ready to run main_loop.py")
    elif all_pass:
        print("  Tested components passed (some skipped)")
    else:
        print("  One or more tests failed — check errors above")
    print(f"{'═' * 52}\n")


# ════════════════════════════════════════════════════════════
#  Entry point
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Kombucha hardware test")
    parser.add_argument("--sim",    action="store_true", help="Test simulation only")
    parser.add_argument("--temp",   action="store_true", help="Test HTU21D only")
    parser.add_argument("--ph",     action="store_true", help="Test Pico/pH only")
    parser.add_argument("--led",    action="store_true", help="Test LEDs only")
    parser.add_argument("--camera", action="store_true", help="Test camera only")
    args = parser.parse_args()

    # If no flags given → run everything
    run_all = not any(vars(args).values())

    print("=" * 52)
    print("  Kombucha Monitor – Hardware Test")
    print("=" * 52)

    results = {}

    results["Simulation model"] = (
        test_sim()   if (run_all or args.sim)    else None
    )
    results["HTU21D (temp/hum)"] = (
        test_htu()   if (run_all or args.temp)   else None
    )
    results["Pico / pH probe"] = (
        test_ph()    if (run_all or args.ph)     else None
    )
    results["LEDs (NeoPixel SPI)"] = (
        test_led()   if (run_all or args.led)    else None
    )
    results["Camera + LEDs"] = (
        test_camera() if (run_all or args.camera) else None
    )

    print_summary(results)
    sys.exit(0 if all(v for v in results.values() if v is not None) else 1)


if __name__ == "__main__":
    main()
