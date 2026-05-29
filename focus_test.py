#!/usr/bin/env python3
"""
focus_test.py
-------------
Manual focus sweep — takes one shot per lens position so you can
compare sharpness and pick the best value for cameras.py.

Lens position guide:
  3.0 → farther   (~30–35 cm)
  4.0 → mid-range (~20–25 cm)
  5.0 → closer    (~15–18 cm)

Once you find the sharpest image, set MANUAL_LENS_POSITION in cameras.py
and switch FOCUS_MODE = "manual".

Usage:
    python3 focus_test.py
Output:
    focus_3.0.jpg, focus_3.5.jpg, focus_4.0.jpg, focus_4.5.jpg, focus_5.0.jpg
"""

import subprocess
import time

from cameras import leds_on, leds_off, WIDTH, HEIGHT, CAPTURE_TIMEOUT_MS

LENS_POSITIONS = [3.0, 3.5, 4.0, 4.5, 5.0]
CAMERA_INDEX   = 0

print("=" * 46)
print("  Manual focus sweep  —  lens 3.0 → 5.0")
print("=" * 46)
print(f"  {len(LENS_POSITIONS)} shots  ·  {WIDTH}×{HEIGHT}  ·  cam {CAMERA_INDEX}")
print()

leds_on()

for lp in LENS_POSITIONS:
    fname = f"focus_{lp:.1f}.jpg"
    cmd = [
        "rpicam-still",
        "--camera",          str(CAMERA_INDEX),
        "-o",                fname,
        "--width",           str(WIDTH),
        "--height",          str(HEIGHT),
        "--timeout",         str(CAPTURE_TIMEOUT_MS),
        "--awb",             "auto",
        "--autofocus-mode",  "manual",
        "--lens-position",   str(lp),
    ]
    print(f"  lens={lp:.1f} → {fname} …", end=" ", flush=True)
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode == 0:
        print("✅")
    else:
        err = r.stderr.decode(errors="replace").strip().splitlines()[-1]
        print(f"❌  {err}")
    time.sleep(0.3)

leds_off()

print()
print("Done. Compare the JPEGs — pick the sharpest lens value,")
print("then set in cameras.py:")
print("  FOCUS_MODE           = \"manual\"")
print("  MANUAL_LENS_POSITION = <best value>")
