#!/usr/bin/env python3
"""
test_led.py
-----------
Quick NeoPixel SPI LED test.
Blinks all 56 LEDs white 5 times, then holds ON for 5 seconds.

Install once:
    pip3 install adafruit-circuitpython-neopixel-spi --break-system-packages

SPI pin on RPi:  GPIO 10 (Pin 19) = MOSI  ->  LED data line
"""

import time

LED_COUNT      = 56
LED_BRIGHTNESS = 0.5   # 0.0 - 1.0  (keep low for bench testing)

try:
    import board
    import neopixel_spi as neospi
except ImportError:
    print("Missing library. Run:")
    print("    pip3 install adafruit-circuitpython-neopixel-spi --break-system-packages")
    raise SystemExit(1)

print(f"Initialising {LED_COUNT} NeoPixels over SPI (GPIO 10 / MOSI)...")
try:
    spi    = board.SPI()
    pixels = neospi.NeoPixel_SPI(
        spi,
        LED_COUNT,
        brightness=LED_BRIGHTNESS,
        auto_write=False,
        pixel_order=neospi.GRB,
    )
except Exception as e:
    print(f"SPI init failed: {e}")
    print("    Check that SPI is enabled:  sudo raspi-config -> Interfaces -> SPI")
    raise SystemExit(1)

print("SPI init OK\n")

# Blink 5 times
for i in range(5):
    print(f"  Blink {i+1}/5  ON ...")
    pixels.fill((255, 255, 255))
    pixels.show()
    time.sleep(0.4)
    print(f"  Blink {i+1}/5  OFF ...")
    pixels.fill((0, 0, 0))
    pixels.show()
    time.sleep(0.4)

# Hold ON for 5 s
print("\nHolding ON for 5 seconds - check your LEDs now...")
pixels.fill((255, 255, 255))
pixels.show()
time.sleep(5)

# Colour sweep R -> G -> B
print("Colour sweep  R -> G -> B ...")
for colour in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:
    pixels.fill(colour)
    pixels.show()
    time.sleep(1)

# Off
pixels.fill((0, 0, 0))
pixels.show()
print("\nDone - LEDs off.")
print("If nothing lit up, check:")
print("  1. Common GND between RPi and external supply")
print("  2. SPI enabled:  sudo raspi-config -> Interfaces -> SPI")
print("  3. Data wire on GPIO 10 (Pin 19 / MOSI)")
