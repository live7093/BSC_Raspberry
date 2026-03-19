#!/usr/bin/env python3
"""
init_cameras.py
---------------
Raspberry Pi Camera Initialization & Test Script
BSC project of Ruben Schmid 

Run this script once before starting autonomous capture to:
  - Verify each camera is detected and responsive
  - Set and test focus (manual lens position or autofocus)
  - Take a test shot per camera and save it to the output folder
  - Print a summary of what worked and what didn't

Usage:
    python3 init_cameras.py

Adjust the CONFIGURATION block below to match your setup.
"""

import os
import subprocess
from datetime import datetime
import sys

# ============================================================
#  CONFIGURATION  –  edit this block to match your setup
# ============================================================

PROJECT_DIR   = "/home/schmiru/Kombucha_Fermentation"
CAMERA_EXE    = "rpicam-still"

# Which camera indices to initialize (list of ints)
CAMERA_INDICES = [0, 1]

# Output folder for test shots
INIT_OUTPUT_DIR = os.path.join(PROJECT_DIR, "init_test_shots")

# --- Resolution ---
WIDTH  = 1920
HEIGHT = 1080

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
# Options: "auto", "incandescent", "tungsten", "fluorescent",
#          "indoor", "daylight", "cloudy", "custom"
AWB_MODE = "auto"

# --- Exposure / gain (leave as None to use camera defaults) ---
# SHUTTER_SPEED_US: shutter speed in microseconds, e.g. 20000 = 1/50 s
# ANALOGUE_GAIN:    ISO-like gain, e.g. 1.0 (low) to 8.0 (high)
SHUTTER_SPEED_US = None   # e.g. 20000
ANALOGUE_GAIN    = None   # e.g. 2.0

# --- Timeout for each capture command (milliseconds) ---
CAPTURE_TIMEOUT_MS = 5000

# ============================================================
#  END OF CONFIGURATION
# ============================================================


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

    # Focus
    if FOCUS_MODE == "manual":
        cmd += ["--autofocus-mode", "manual",
                "--lens-position",  str(MANUAL_LENS_POSITION)]
    elif FOCUS_MODE == "autofocus":
        cmd += ["--autofocus-mode", "auto"]

    # Shutter speed
    if SHUTTER_SPEED_US is not None:
        cmd += ["--shutter", str(SHUTTER_SPEED_US)]

    # Analogue gain
    if ANALOGUE_GAIN is not None:
        cmd += ["--analoggain", str(ANALOGUE_GAIN)]

    return cmd


def init_camera(camera_index: int) -> dict:
    """
    Run a test capture for one camera.
    Returns a result dict with keys: camera, ok, file, command, error
    """
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name  = f"init_cam{camera_index}_{timestamp}.jpg"
    full_path  = os.path.join(INIT_OUTPUT_DIR, file_name)
    command    = build_command(camera_index, full_path)
    cmd_str    = " ".join(command)

    print(f"\n  → Camera {camera_index}: running test capture…")
    print(f"     CMD: {cmd_str}")

    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,          # hard wall-clock timeout (seconds)
        )
        # Check the file was actually written
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
    print(f"  Test shots saved to   : {INIT_OUTPUT_DIR}")
    print("-" * 60)

    # Ensure output directory exists
    os.makedirs(INIT_OUTPUT_DIR, exist_ok=True)

    results = []
    for idx in CAMERA_INDICES:
        results.append(init_camera(idx))

    # ── Summary ──────────────────────────────────────────────
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