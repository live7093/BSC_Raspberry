#!/usr/bin/env python3
"""
focus_test.py
-------------
Focus & brightness calibration for the fermentation camera.
Mirrors the settings in cameras.py — keep them in sync.

Manual mode   – sweeps LENS_POSITIONS at fixed brightness to find the
                sharpest focus distance for your setup.
Auto mode     – sweeps LED_BRIGHTNESS_STEPS with macro autofocus active
                so the camera locks focus itself each shot.

Usage:
    python3 focus_test.py
Output files are saved in the current directory.
"""

import subprocess
import time

# ── Settings — keep in sync with cameras.py ──────────────────
CAMERA_INDEX    = 0

FOCUS_MODE      = "auto"    # "manual" | "auto"
AUTOFOCUS_RANGE = "macro"   # "normal" | "macro" | "full"  (auto mode only)

# Manual mode: which lens positions to sweep
LENS_POSITIONS  = [3.5, 4.1, 4.9, 5.4, 6.0]
MANUAL_BRIGHTNESS = 0.5     # fixed brightness during a manual sweep

# Auto mode: which brightness levels to sweep (camera focuses itself each shot)
LED_BRIGHTNESS_STEPS = [0.1, 0.2, 0.3, 0.4, 0.5]

WIDTH, HEIGHT      = 2400, 2400
LED_COUNT          = 56
LED_WARMUP_S       = 1.5   # seconds after LEDs on before capture
CAPTURE_TIMEOUT_MS = 5000

# ── LED setup ─────────────────────────────────────────────────
try:
    import board
    import neopixel_spi as neospi
    _spi   = board.SPI()
    pixels = neospi.NeoPixel_SPI(
        _spi, LED_COUNT, brightness=0.5, auto_write=False, pixel_order=neospi.GRB
    )
    LED_AVAILABLE = True
except Exception as e:
    pixels        = None
    LED_AVAILABLE = False
    print(f"[focus_test] WARNING: NeoPixel init failed – LEDs disabled. ({e})")


def leds_on(brightness: float = 0.5):
    if not LED_AVAILABLE:
        return
    pixels.brightness = brightness
    pixels.fill((255, 255, 255))
    pixels.show()
    time.sleep(LED_WARMUP_S)   # let LEDs warm up and exposure stabilise


def leds_off():
    if not LED_AVAILABLE:
        return
    pixels.fill((0, 0, 0))
    pixels.show()


# ── Camera helpers ────────────────────────────────────────────

def build_focus_args() -> list[str]:
    if FOCUS_MODE == "manual":
        return []   # lens position is per-shot in manual mode
    return ["--autofocus-mode", "auto", "--autofocus-range", AUTOFOCUS_RANGE]


def shoot(fname: str, extra_args: list[str]) -> bool:
    cmd = [
        "rpicam-still",
        "--camera",  str(CAMERA_INDEX),
        "-o",        fname,
        "--width",   str(WIDTH),
        "--height",  str(HEIGHT),
        "--timeout", str(CAPTURE_TIMEOUT_MS),
        "--awb",     "auto",
    ] + extra_args
    print(f"     CMD: {' '.join(cmd)}")
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ok = r.returncode == 0
    if not ok:
        err = r.stderr.decode(errors="replace").strip().splitlines()[-1]
        print(f"     ❌ {err}")
    else:
        print(f"     ✅ saved {fname}")
    return ok


# ── Main ──────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Kombucha – Focus & Brightness Test")
    print("=" * 60)
    print(f"  Focus mode   : {FOCUS_MODE}", end="")
    if FOCUS_MODE == "auto":
        print(f"  (range={AUTOFOCUS_RANGE})")
    else:
        print()
    print(f"  Resolution   : {WIDTH}×{HEIGHT}")
    print(f"  Camera index : {CAMERA_INDEX}")
    print(f"  LEDs         : {'OK' if LED_AVAILABLE else 'NOT AVAILABLE'}")
    print("-" * 60)

    try:
        if FOCUS_MODE == "auto":
            _run_auto_sweep()
        else:
            _run_manual_sweep()
    finally:
        leds_off()

    print("\n" + "=" * 60)
    print("  Done — compare the JPEGs to pick the best settings.")
    if FOCUS_MODE == "auto":
        print("  → Best: sharpest image at lowest acceptable brightness.")
        print("    Update cameras.py: AUTOFOCUS_RANGE and brightness.")
    else:
        print("  → Best: sharpest image at your working distance.")
        print("    Update cameras.py: MANUAL_LENS_POSITION.")
    print("=" * 60)


def _run_auto_sweep():
    """Sweep LED brightness; camera autofocuses (macro) for each shot."""
    focus_args = ["--autofocus-mode", "auto", "--autofocus-range", AUTOFOCUS_RANGE]
    print(f"\n  Sweeping {len(LED_BRIGHTNESS_STEPS)} brightness levels "
          f"(autofocus-range={AUTOFOCUS_RANGE} per shot)\n")

    for brightness in LED_BRIGHTNESS_STEPS:
        fname = f"focus_auto_{AUTOFOCUS_RANGE}_b{brightness:.1f}.jpg"
        print(f"  → brightness={brightness:.1f}")
        leds_on(brightness)
        shoot(fname, focus_args)
        leds_off()
        time.sleep(0.5)


def _run_manual_sweep():
    """Sweep lens positions at fixed brightness to find sharpest distance."""
    print(f"\n  Sweeping {len(LENS_POSITIONS)} lens positions "
          f"at brightness={MANUAL_BRIGHTNESS:.1f}\n")

    leds_on(MANUAL_BRIGHTNESS)
    for lp in LENS_POSITIONS:
        fname = f"focus_manual_lens{lp:.1f}.jpg"
        print(f"  → lens_position={lp:.1f}")
        manual_args = [
            "--autofocus-mode", "manual",
            "--lens-position",  str(lp),
        ]
        shoot(fname, manual_args)
        time.sleep(0.5)
    leds_off()


if __name__ == "__main__":
    main()
