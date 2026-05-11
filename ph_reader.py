#!/usr/bin/env python3
"""
ph_reader.py
------------
Raspberry Pi side – reads pH data from the Pico over USB serial.

The Pico now sends one JSON line per reading:
    {"ph": 3.82, "voltage": 1.234, "v_ph7": 1.121, "v_ph4": 1.550, "source": "auto"}

Calibration lives on the Pico (cal.json) and is embedded in every
reading, so the RPi always knows what slope/offset was used.

Usage (standalone monitor):
    python3 ph_reader.py

As a module (used by main_loop.py):
    from ph_reader import PicoReader
    reader = PicoReader()
    reading = reader.read_one()   # blocks until a line arrives
    print(reading.ph, reading.source)

Install once:
    pip3 install pyserial
"""

from __future__ import annotations

import json
import time
import serial
import serial.tools.list_ports
from dataclasses import dataclass
from typing import Optional


# ════════════════════════════════════════════════════════════
#  Data class returned to callers
# ════════════════════════════════════════════════════════════

@dataclass
class PHReading:
    ph:      float
    voltage: float
    v_ph7:   float
    v_ph4:   float
    source:  str        # "auto" | "manual"
    raw_line: str = ""


# ════════════════════════════════════════════════════════════
#  Pico finder
# ════════════════════════════════════════════════════════════

def find_pico_port() -> Optional[str]:
    for port in serial.tools.list_ports.comports():
        if port.vid == 0x2E8A or \
           "MicroPython" in (port.description or "") or \
           "Pico" in (port.description or ""):
            return port.device
    return None


# ════════════════════════════════════════════════════════════
#  Reader class  (importable by main_loop.py)
# ════════════════════════════════════════════════════════════

class PicoReader:
    """
    Opens a persistent serial connection to the Pico and parses
    JSON pH readings.

    Usage:
        with PicoReader() as reader:
            reading = reader.read_one(timeout_s=35)
    """

    def __init__(self, port: Optional[str] = None, baudrate: int = 115200):
        self._port     = port or find_pico_port()
        self._baudrate = baudrate
        self._ser: Optional[serial.Serial] = None

        if not self._port:
            raise RuntimeError(
                "Pico not found. Is it connected via USB? "
                "Try manually: PicoReader(port='/dev/ttyACM0')"
            )

    def open(self):
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(
            port=self._port, baudrate=self._baudrate, timeout=2
        )
        time.sleep(0.5)
        self._ser.reset_input_buffer()

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def read_one(self, timeout_s: float = 40) -> Optional[PHReading]:
        """
        Block until a valid JSON pH line arrives or timeout.
        Returns None on timeout or parse error.
        """
        if not (self._ser and self._ser.is_open):
            self.open()

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                raw = self._ser.readline().decode("utf-8", errors="replace").strip()
            except serial.SerialException as e:
                print(f"[ph_reader] Serial error: {e}")
                return None

            if not raw:
                continue

            # Only parse lines that look like JSON objects
            if not raw.startswith("{"):
                # Could be a MicroPython exception or print — log and skip
                print(f"[ph_reader] Non-JSON from Pico: {raw}")
                continue

            try:
                data = json.loads(raw)
                return PHReading(
                    ph       = float(data["ph"]),
                    voltage  = float(data["voltage"]),
                    v_ph7    = float(data["v_ph7"]),
                    v_ph4    = float(data["v_ph4"]),
                    source   = str(data.get("source", "auto")),
                    raw_line = raw,
                )
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"[ph_reader] Parse error ({e}): {raw}")
                continue

        return None   # timeout


# ════════════════════════════════════════════════════════════
#  Standalone monitor  (python3 ph_reader.py)
# ════════════════════════════════════════════════════════════

def main():
    port = find_pico_port()
    if not port:
        print("❌  Pico not found. Try setting port manually.")
        return

    print(f"Connected on {port}  (waiting for JSON readings from Pico…)\n")
    print(f"{'Time':<10} {'pH':>6}  {'Voltage':>9}  {'Source':>8}  {'Quality'}")
    print("─" * 54)

    with PicoReader(port=port) as reader:
        try:
            while True:
                reading = reader.read_one(timeout_s=60)
                if reading is None:
                    print("[timeout – no reading in 60 s]")
                    continue

                ts = time.strftime("%H:%M:%S")

                if reading.ph < 1 or reading.ph > 13:
                    quality = "⚠ check sensor"
                elif reading.voltage < 0.2 or reading.voltage > 3.1:
                    quality = "⚠ check wiring"
                else:
                    quality = "ok"

                src_flag = "📌" if reading.source == "manual" else "  "
                print(f"{ts:<10} {reading.ph:>6.2f}  "
                      f"{reading.voltage:>9.3f}  "
                      f"{src_flag}{reading.source:>6}  {quality}")

        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
