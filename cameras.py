#!/usr/bin/env python3
"""
cameras.py
----------
Raspberry Pi Camera Initialization & Test Script
Kombucha Fermentation Monitor – BSC project Ruben Schmid

Features:
  - Turns on illumination LEDs (GPIO 10) before each capture
  - Turns LEDs off immediately after capture
  - Verifies each camera is detected and responsive
  - Sets focus, white balance, exposure
  - Takes a test shot per camera and saves it to the output folder
  - Prints a summary of what worked and what didn't

Usage:
    python3 cameras.py

Install dependency once:
    pip3 install RPi.GPIO    (usually pre-installed on RPi OS)
"""

import os
import subprocess
from datetime import datetime
import sys
import time

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("[cameras] WARNING: RPi.GPIO not available – LED control disabled.")

# ============================================================
#  CONFIGURATION  –  edit this block to match your setup
# ============================================================

PROJECT_DIR   = "/home/schmiru/Kombucha_Fermentation"
CAMERA_EXE    = "rpicam-still"

# Which camera indices to initialize (list of ints)
CAMERA_INDICES = [0, 1]

# Output folder for test shots
INIT_OUTPUT_DIR = os.path.join(PROJECT_DIR, "init_test_shots")

# --- LED illumination ---
# BCM pin number that drives the LED array
LED_PIN         = 10
# Settle time (seconds) after turning LEDs on before triggering capture
LED_WARMUP_S    = 0.3

# --- Resolution ---
WIDTH  = 1920
HEIGHT = 2400

# --- Focus mode ---
# "manual"    → fix lens to MANUAL_LENS_POSITION (0.0 = infinity, higher = closer)
# "autofocus" → trigger a one-shot autofocus before capturing
FOCUS_MODE = "manual"

# Lens position used when FOCUS_MODE == "manual"
# 0.0  = infinity  (far away subjects)
# 2.0  = ~50 cm
# 4.0  = ~25 cm
# 8.0  = ~12 cm
# 10.0 = very close macro
MANUAL_LENS_POSITION = 0.0

# --- White Balance ---
AWB_MODE = "auto"

# --- Exposure / gain (leave as None to use camera defaults) ---
SHUTTER_SPEED_US = None   # e.g. 20000 (= 1/50 s)
ANALOGUE_GAIN    = None   # e.g. 2.0

# --- Timeout for each capture command (milliseconds) ---
CAPTURE_TIMEOUT_MS = 5000

# ============================================================
#  END OF CONFIGURATION
# ============================================================


# ── GPIO / LED helpers ────────────────────────────────────────

def setup_gpio():
    """Configure GPIO for LED output. Safe to call multiple times."""
    if not GPIO_AVAILABLE:
        return
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(LED_PIN, GPIO.OUT, initial=GPIO.LOW)


def leds_on():
    if not GPIO_AVAILABLE:
        print("     [LED] GPIO not available – skipping LED on")
        return
    GPIO.output(LED_PIN, GPIO.HIGH)
    print(f"     💡 LEDs ON  (GPIO {LED_PIN})")
    time.sleep(LED_WARMUP_S)


def leds_off():
    if not GPIO_AVAILABLE:
        return
    GPIO.output(LED_PIN, GPIO.LOW)
    print(f"     🌑 LEDs OFF (GPIO {LED_PIN})")


def cleanup_gpio():
    if not GPIO_AVAILABLE:
        return
    leds_off()
    GPIO.cleanup()


# ── Camera helpers ────────────────────────────────────────────

def build_command(camera_index: int, output_path: str) -> list[str]:
    """Build the rpicam-still command list from the config above."""
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
    """
    Run a test capture for one camera, with LED illumination.
    Returns a result dict with keys: camera, ok, file, command, error
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"init_cam{camera_index}_{timestamp}.jpg"
    full_path = os.path.join(INIT_OUTPUT_DIR, file_name)
    command   = build_command(camera_index, full_path)
    cmd_str   = " ".join(command)

    print(f"\n  → Camera {camera_index}: running test capture…")
    print(f"     CMD: {cmd_str}")

    leds_on()

    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
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
        stderr_text = e.stderr.decode(errors="replace").strip()
        print(f"     ❌ Capture failed (exit {e.returncode})")
        print(f"        stderr: {stderr_text}")
        return {"camera": camera_index, "ok": False,
                "file": None, "command": cmd_str, "error": stderr_text}

    except subprocess.TimeoutExpired:
        msg = "Command timed out after 30 seconds."
        print(f"     ❌ {msg}")
        return {"camera": camera_index, "ok": False,
                "file": None, "command": cmd_str, "error": msg}

    except FileNotFoundError:
        msg = f"Camera executable '{CAMERA_EXE}' not found. Is rpicam-apps installed?"
        print(f"     ❌ {msg}")
        return {"camera": camera_index, "ok": False,
                "file": None, "command": cmd_str, "error": msg}

    finally:
        leds_off()


def capture_frame(camera_index: int, output_path: str) -> bool:
    """
    Convenience function for use by the main data-collection loop.
    Turns LEDs on, captures, turns LEDs off.
    Returns True on success.
    """
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
    print(f"  Cameras to initialize : {CAMERA_INDICES}")
    print(f"  Resolution            : {WIDTH}×{HEIGHT}")
    print(f"  Focus mode            : {FOCUS_MODE}" +
          (f"  (lens position {MANUAL_LENS_POSITION})" if FOCUS_MODE == "manual" else ""))
    print(f"  White balance         : {AWB_MODE}")
    print(f"  Shutter speed         : {SHUTTER_SPEED_US or 'auto'}")
    print(f"  Analogue gain         : {ANALOGUE_GAIN or 'auto'}")
    print(f"  LED pin               : GPIO {LED_PIN}  (warmup {LED_WARMUP_S}s)")
    print(f"  Test shots saved to   : {INIT_OUTPUT_DIR}")
    print("-" * 60)

    os.makedirs(INIT_OUTPUT_DIR, exist_ok=True)
    setup_gpio()

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
        status = "✅ OK " if r["ok"] else "❌ FAIL"
        print(f"  Camera {r['camera']}:  {status}")
        if r["ok"]:
            print(f"            File : {r['file']}")
        else:
            print(f"            Error: {r['error']}")
        if not r["ok"]:
            all_ok = False

    print("-" * 60)
    if all_ok:
        print("  All cameras initialized successfully.")
        print("  You can now start autonomous capture.")
    else:
        print("  ⚠️  One or more cameras failed. Check errors above.")
        print("  Tip: run  'rpicam-still --list-cameras'  to see what")
        print("       the system detects.")
    print("=" * 60)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
