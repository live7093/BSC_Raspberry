#!/usr/bin/env python3
"""
focus_test.py
-------------
One-shot macro focus test — uses the exact same code path as the main loop.
Runs cameras.py: LEDs on → capture → LEDs off.

Usage:
    python3 focus_test.py
Output:
    focus_test.jpg  (in current directory)
"""

from cameras import capture_frame, FOCUS_MODE, AUTOFOCUS_RANGE, MANUAL_LENS_POSITION

OUT = "focus_test.jpg"

print(f"Focus mode : {FOCUS_MODE}"
      + (f"  range={AUTOFOCUS_RANGE}" if FOCUS_MODE in ("auto", "autofocus")
         else f"  lens_position={MANUAL_LENS_POSITION}"))
print(f"Capturing  → {OUT} …")

ok = capture_frame(0, OUT)
print("✅ Done — check focus_test.jpg" if ok else "❌ Capture failed")
