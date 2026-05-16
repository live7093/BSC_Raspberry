#!/usr/bin/env python3
"""
verify_ph.py
------------
Pre-run pH probe verification for Raspberry Pi
BSC project – Ruben Schmid

Run this BEFORE starting main_loop.py to confirm the pH probe
is reading correctly with your known pH 4 and pH 7 buffers.

Does NOT change calibration — use the CALIBRATION page on the
Pico LCD for that. This is just a sanity check.

Usage:
    python3 verify_ph.py
"""

from ph_reader import PicoReader, find_pico_port
import time

PASS = "✅"
WARN = "⚠️ "
FAIL = "❌"

# How close the reading needs to be to pass (pH units)
TOLERANCE_PASS = 0.10   # within ±0.10 = pass
TOLERANCE_WARN = 0.20   # within ±0.20 = warning, outside = fail


def check(measured, expected, label):
    diff = abs(measured - expected)
    if diff <= TOLERANCE_PASS:
        icon = PASS
        note = "within ±{:.2f}".format(TOLERANCE_PASS)
    elif diff <= TOLERANCE_WARN:
        icon = WARN
        note = "off by {:.2f} — acceptable but recalibrate soon".format(diff)
    else:
        icon = FAIL
        note = "off by {:.2f} — recalibrate before starting run!".format(diff)
    print(f"  {icon}  {label:<20} expected={expected:.2f}  "
          f"measured={measured:.2f}  {note}")
    return diff <= TOLERANCE_WARN


def get_stable_reading(reader, label, samples=5):
    """Take multiple readings and return the average."""
    print(f"  Reading {samples} samples", end="", flush=True)
    readings = []
    for _ in range(samples):
        r = reader.read_one(timeout_s=35)
        if r:
            readings.append(r.ph)
            print(".", end="", flush=True)
        else:
            print("x", end="", flush=True)
    print()

    if not readings:
        print(f"  {FAIL}  No readings received — is the Pico connected?")
        return None, None

    avg = round(sum(readings) / len(readings), 2)
    spread = round(max(readings) - min(readings), 3)
    print(f"  Readings: {[round(r,2) for r in readings]}")
    print(f"  Average : {avg}  (spread: {spread})")
    if spread > 0.2:
        print(f"  {WARN}  High spread ({spread}) — probe may need more time to stabilise")
    return avg, spread


def main():
    print("=" * 56)
    print("  Pre-run pH Probe Verification")
    print("=" * 56)
    print(f"  Pass tolerance : ±{TOLERANCE_PASS} pH")
    print(f"  Warn tolerance : ±{TOLERANCE_WARN} pH")
    print()

    # Connect to Pico
    port = find_pico_port()
    if not port:
        print(f"{FAIL}  Pico not found — check USB connection")
        return
    print(f"  Pico found on {port}\n")

    results = []

    with PicoReader(port=port) as reader:

        # ── Step 1: pH 7 buffer ───────────────────────────────
        print("─" * 56)
        print("  STEP 1 — Insert probe into pH 7 buffer")
        print("  Wait for reading to stabilise, then press Enter")
        input("  → Press Enter when ready: ")

        ph7, spread7 = get_stable_reading(reader, "pH 7 buffer")
        if ph7 is not None:
            ok = check(ph7, 7.0, "pH 7 buffer")
            results.append(ok)
        print()

        # ── Step 2: Rinse reminder ────────────────────────────
        print("─" * 56)
        print("  STEP 2 — Rinse probe with distilled water")
        input("  → Press Enter when rinsed: ")

        # ── Step 3: pH 4 buffer ───────────────────────────────
        print("─" * 56)
        print("  STEP 3 — Insert probe into pH 4 buffer")
        input("  → Press Enter when ready: ")

        ph4, spread4 = get_stable_reading(reader, "pH 4 buffer")
        if ph4 is not None:
            ok = check(ph4, 4.0, "pH 4 buffer")
            results.append(ok)
        print()

    # ── Summary ───────────────────────────────────────────────
    print("═" * 56)
    print("  RESULT")
    print("═" * 56)

    if not results:
        print(f"  {FAIL}  No readings received — check Pico connection")
        return

    if all(results):
        print(f"  {PASS}  Probe verified — ready to start the run")
        print()
        print("  Next step:  python3 main_loop.py")
    else:
        print(f"  {FAIL}  Probe out of tolerance — recalibrate first")
        print()
        print("  On the Pico LCD: rotate to CALIBRATION → press button")
        print("  Then re-run this script to verify again")
    print("═" * 56)


if __name__ == "__main__":
    main()