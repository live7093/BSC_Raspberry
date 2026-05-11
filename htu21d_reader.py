#!/usr/bin/env python3
"""
htu21d_reader.py
----------------
HTU21D / HTU2x Temperature & Humidity Reader
Kombucha Fermentation Monitor – BSC project Ruben Schmid

Reads temperature and humidity from an HTU21D sensor connected
to the Raspberry Pi via I2C (SDA=GPIO2, SCL=GPIO3 by default).

Wiring:
  HTU21D VCC  → 3.3V (Pin 1)
  HTU21D GND  → GND  (Pin 6)
  HTU21D SDA  → GPIO 2 (Pin 3)
  HTU21D SCL  → GPIO 3 (Pin 5)

Install dependency once:
  pip3 install smbus2

Usage (standalone test):
  python3 htu21d_reader.py
"""

import time
import struct

try:
    import smbus2
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False
    print("[htu21d] WARNING: smbus2 not installed. Run: pip3 install smbus2")


# ============================================================
#  CONFIGURATION
# ============================================================

I2C_BUS     = 1          # /dev/i2c-1 on modern RPi
HTU21D_ADDR = 0x40       # fixed I2C address

# HTU21D command bytes
CMD_TEMP_HOLD    = 0xE3
CMD_HUM_HOLD     = 0xE5
CMD_TEMP_NOHOLD  = 0xF3
CMD_HUM_NOHOLD   = 0xF5
CMD_SOFT_RESET   = 0xFE

# ============================================================


class HTU21D:
    """Minimal driver for the HTU21D sensor over I2C."""

    def __init__(self, bus_num: int = I2C_BUS, address: int = HTU21D_ADDR):
        if not SMBUS_AVAILABLE:
            raise RuntimeError("smbus2 is not installed. Run: pip3 install smbus2")
        self._bus  = smbus2.SMBus(bus_num)
        self._addr = address
        self.soft_reset()
        time.sleep(0.05)   # 15 ms reset time per datasheet, 50 ms for safety

    def soft_reset(self):
        """Send soft reset command to restore default settings."""
        self._bus.write_byte(self._addr, CMD_SOFT_RESET)

    def _read_raw(self, command: int) -> int:
        """
        Send a measurement command, wait, then read 3 bytes (MSB, LSB, CRC).
        Returns the 16-bit raw value (CRC stripped).
        """
        self._bus.write_byte(self._addr, command)
        time.sleep(0.05)   # max conversion time: 44 ms for temp, 16 ms for hum
        data = self._bus.read_i2c_block_data(self._addr, command, 3)
        raw = (data[0] << 8) | data[1]
        raw &= 0xFFFC      # clear status bits (last 2 bits)
        return raw

    def read_temperature(self) -> float:
        """Return temperature in °C."""
        raw  = self._read_raw(CMD_TEMP_HOLD)
        temp = -46.85 + 175.72 * (raw / 65536.0)
        return round(temp, 2)

    def read_humidity(self) -> float:
        """Return relative humidity in %RH (clamped 0–100)."""
        raw = self._read_raw(CMD_HUM_HOLD)
        rh  = -6.0 + 125.0 * (raw / 65536.0)
        return round(max(0.0, min(100.0, rh)), 2)

    def read_both(self) -> tuple[float, float]:
        """Return (temperature_°C, humidity_%RH) in one call."""
        return self.read_temperature(), self.read_humidity()

    def close(self):
        self._bus.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Standalone test ───────────────────────────────────────────
def main():
    print("HTU21D Sensor Test")
    print("=" * 40)

    try:
        sensor = HTU21D()
    except Exception as e:
        print(f"❌ Could not open HTU21D: {e}")
        print("   Check wiring and that I2C is enabled (raspi-config).")
        return

    print(f"{'Time':<12} {'Temp (°C)':<14} {'Humidity (%RH)':<18} {'Status'}")
    print("─" * 54)

    try:
        while True:
            try:
                temp, hum = sensor.read_both()
                ts = time.strftime("%H:%M:%S")

                if temp < 0 or temp > 50:
                    status = "⚠ temp out of range"
                elif hum < 10 or hum > 95:
                    status = "⚠ hum out of range"
                else:
                    status = "ok"

                print(f"{ts:<12} {temp:<14.2f} {hum:<18.2f} {status}")

            except Exception as e:
                print(f"Read error: {e}")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sensor.close()


if __name__ == "__main__":
    main()
