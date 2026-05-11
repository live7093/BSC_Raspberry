#!/usr/bin/env python3
"""
cameras.py
----------
Raspberry Pi Camera Initialization & Capture
Kombucha Fermentation Monitor – BSC project Ruben Schmid

LEDs are NeoPixels driven over SPI (neopixel_spi + board libraries).
Install once:
    pip3 install adafruit-circuitpython-neopixel-spi --break-system-packages

Camera ribbon connected to CAM 0 (CSI port).
"""

import os
import subprocess
from datetime import datetime
import sys
import time

# ── NeoPixel SPI LED setup ────────────────────────────────────
try:
    import board
    import neopixel_spi as neospi
    _spi   = board.SPI()
    pixels = neospi.NeoPixel_SPI(
        _spi,
        56,
        brightness=0.1,
        auto_write=False,
        pixel_order=neospi.GRB,
    )
    LED_AVAILABLE = True
except Exception as e:
    pixels        = None
    LED_AVAILABLE = False
    print(f"[cameras] WARNING: NeoPixel init failed – LEDs disabled. ({e})")

# ============================================================
#  CONFIGURATION
# ============================================================

PROJECT_DIR   = "/home/schmiru/Kombucha_Fermentation"
CAMERA_EXE    = "rpicam-still"

CAMERA_INDICES  = [0]        # add 1 when second camera arrives
INIT_OUTPUT_DIR = os.path.join(PROJECT_DIR, "init_test_shots")

LED_WARMUP_S    = 1.0        # seconds to wait after LEDs on before capture

WIDTH    = 1920
HEIGHT   = 1080
AWB_MODE = "auto"

FOCUS_MODE           = "manual"
MANUAL_LENS_POSITION = 0.0

SHUTTER_SPEED_US   = None
ANALOGUE_GAIN      = None
CAPTURE_TIMEOUT_MS = 5000

# ============================================================


# ── LED helpers ───────────────────────────────────────────────

def leds_on():
    if not LED_AVAILABLE:
        print("     [LED] NeoPixel not available – skipping")
        return
    pixels.fill((255, 255, 255))
    pixels.show()
    print("     💡 LEDs ON")
    time.sleep(LED_WARMUP_S)


def leds_off():
    if not LED_AVAILABLE:
        return
    pixels.fill((0, 0, 0))
    pixels.show()
    print("     🌑 LEDs OFF")


# Keep as no-ops so main_loop.py imports don't break
def setup_gpio():
    pass

def cleanup_gpio():
    leds_off()


# ── Camera helpers ────────────────────────────────────────────

def build_command(camera_index: int, output_path: str) -> list[str]:
    cmd = [
        CAMERA_EXE,
        "--camera",  str(camera_index),
        "-o",        output_path,
        "--timeout", str(CAPTURE_TIMEOUT_MS),
        "--width",   str(WIDTH),
        "--height",  str(HEIGHT),
        "--awb",     AWB_MODE,
    ]
    if FOCUS_MODE == "manual":
        cmd += ["--autofocus-mode", "manual",
                "--lens-position",  str(MANUAL_LENS_POSITION)]
    elif FOCUS_MODE == "autofocus":
        cmd += ["--autofocus-mode", "auto"]
    if SHUTTER_SPEED_US is not None:
        cmd += ["--shutter", str(SHUTTER_SPEED_US)]
    if ANALOGUE_GAIN is not None:
        cmd += ["--analoggain", str(ANALOGUE_GAIN)]
    return cmd


def init_camera(camera_index: int) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"init_cam{camera_index}_{timestamp}.jpg"
    full_path = os.path.join(INIT_OUTPUT_DIR, file_name)
    command   = build_command(camera_index, full_path)
    cmd_str   = " ".join(command)

    print(f"\n  → Camera {camera_index}: running test capture…")
    print(f"     CMD: {cmd_str}")

    leds_on()
    try:
        subprocess.run(command, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=30)
        if os.path.isfile(full_path) and os.path.getsize(full_path) > 0:
            print(f"     ✅ Image saved: {full_path}  ({os.path.getsize(full_path):,} bytes)")
            return {"camera": camera_index, "ok": True,
                    "file": full_path, "command": cmd_str, "error": None}
        else:
            msg = "Command succeeded but output file is missing or empty."
            print(f"     ⚠️  {msg}")
            return {"camera": camera_index, "ok": False,
                    "file": None, "command": cmd_str, "error": msg}
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace").strip()
        print(f"     ❌ Capture failed (exit {e.returncode}): {err}")
        return {"camera": camera_index, "ok": False,
                "file": None, "command": cmd_str, "error": err}
    except subprocess.TimeoutExpired:
        msg = "Command timed out after 30 s."
        print(f"     ❌ {msg}")
        return {"camera": camera_index, "ok": False,
                "file": None, "command": cmd_str, "error": msg}
    except FileNotFoundError:
        msg = f"'{CAMERA_EXE}' not found. Is rpicam-apps installed?"
        print(f"     ❌ {msg}")
        return {"camera": camera_index, "ok": False,
                "file": None, "command": cmd_str, "error": msg}
    finally:
        leds_off()


def capture_frame(camera_index: int, output_path: str) -> bool:
    """Used by main_loop.py — LEDs on, capture, LEDs off."""
    command = build_command(camera_index, output_path)
    leds_on()
    try:
        subprocess.run(command, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=30)
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        return False
    finally:
        leds_off()


def main():
    print("=" * 60)
    print("  Kombucha Fermentation – Camera Initialization")
    print("=" * 60)
    print(f"  Cameras      : {CAMERA_INDICES}")
    print(f"  Resolution   : {WIDTH}×{HEIGHT}")
    print(f"  LEDs         : {'OK (NeoPixel SPI)' if LED_AVAILABLE else 'NOT AVAILABLE'}")
    print(f"  Test shots → : {INIT_OUTPUT_DIR}")
    print("-" * 60)

    os.makedirs(INIT_OUTPUT_DIR, exist_ok=True)

    results = []
    try:
        for idx in CAMERA_INDICES:
            results.append(init_camera(idx))
    finally:
        cleanup_gpio()

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    all_ok = True
    for r in results:
        status = "✅ OK" if r["ok"] else "❌ FAIL"
        print(f"  Camera {r['camera']}: {status}")
        if r["ok"]:
            print(f"           File: {r['file']}")
        else:
            print(f"           Error: {r['error']}")
        if not r["ok"]:
            all_ok = False

    print("-" * 60)
    if all_ok:
        print("  All cameras OK. You can now start main_loop.py.")
    else:
        print("  ⚠️  One or more cameras failed.")
        print("  Tip: rpicam-still --list-cameras")
    print("=" * 60)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
