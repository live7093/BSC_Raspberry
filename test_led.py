#!/usr/bin/env python3
"""
test_led.py
-----------
Quick NeoPixel SPI LED test.
Runs: white ON 3s → off 1s → colour cycle → off

Install once:
    pip3 install adafruit-circuitpython-neopixel-spi --break-system-packages
"""

import time

LED_COUNT      = 56
LED_BRIGHTNESS = 0.5

print("Initialising NeoPixel SPI strip...")
try:
    import board
    import neopixel_spi as neospi
    spi    = board.SPI()
    pixels = neospi.NeoPixel_SPI(
        spi,
        LED_COUNT,
        brightness=LED_BRIGHTNESS,
        auto_write=False,
        pixel_order=neospi.GRB,
    )
    print(f"✅ NeoPixel init OK  ({LED_COUNT} LEDs, brightness={LED_BRIGHTNESS})")
except Exception as e:
    print(f"❌ NeoPixel init FAILED: {e}")
    print("   Check: SPI enabled? (raspi-config → Interfaces → SPI)")
    print("   Check: library installed? pip3 install adafruit-circuitpython-neopixel-spi")
    raise SystemExit(1)

def show(colour, label, seconds=2):
    pixels.fill(colour)
    pixels.show()
    print(f"  {label} for {seconds}s...")
    time.sleep(seconds)

def off():
    pixels.fill((0, 0, 0))
    pixels.show()

print("\n--- Test sequence ---")

# 1. Full white — main use case for illumination
show((255, 255, 255), "💡 Full WHITE (capture colour)", seconds=3)
off(); time.sleep(0.5)

# 2. Colour check — confirms GRB order is correct
show((255, 0, 0), "🔴 RED",   seconds=1)
show((0, 255, 0), "🟢 GREEN", seconds=1)
show((0, 0, 255), "🔵 BLUE",  seconds=1)
off(); time.sleep(0.5)

# 3. Dim white — lower brightness
pixels.brightness = 0.2
show((255, 255, 255), "🔅 Dim white (brightness=0.2)", seconds=2)
pixels.brightness = LED_BRIGHTNESS
off()

print("\n✅ Test complete.")
print("   If LEDs did not light up:")
print("   1. Check SPI is enabled: sudo raspi-config → Interfaces → SPI")
print("   2. Check common GND between RPi and LED power supply")
print("   3. Check DATA wire is on RPi SPI MOSI pin (GPIO 10 / Pin 19)")