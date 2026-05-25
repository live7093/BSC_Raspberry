import time
from htu21d_reader import HTU21D
 
print("HTU21D Sensor Test")
print("=" * 40)
 
try:
    sensor = HTU21D()
    print("Sensor detected ✅\n")
except Exception as e:
    print(f"❌ Could not connect: {e}")
    print("\nCheck:")
    print("  1. i2cdetect -y 1  (should show 0x40)")
    print("  2. I2C enabled via raspi-config")
    print("  3. Wiring: SDA=Pin3, SCL=Pin5, VCC=3.3V, GND=Pin6")
    raise SystemExit(1)
 
print(f"{'Time':<10} {'Temp (°C)':<14} {'Humidity (%)':<14} {'Status'}")
print("─" * 48)
 
try:
    for i in range(10):
        temp, hum = sensor.read_both()
        ts = time.strftime("%H:%M:%S")
 
        if temp < 0 or temp > 50:
            status = "⚠ temp out of range"
        elif hum < 10 or hum > 95:
            status = "⚠ hum out of range"
        else:
            status = "ok"
 
        print(f"{ts:<10} {temp:<14.2f} {hum:<14.2f} {status}")
        time.sleep(2)
 
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    sensor.close()
    print("Done.")
