import serial
import serial.tools.list_ports
import time

# ── 2-point calibration ───────────────────────────────────────
VREF    = 3.3
ADC_MAX = 65535

V_PH7 = 1.121   # measured with pH 7 buffer (raw 22250)
V_PH4 = 1.550   # measured with pH 4 buffer

SLOPE  = (V_PH4 - V_PH7) / (4.0 - 7.0)   # = -0.143 V/pH
OFFSET = 7.0 - (V_PH7 / SLOPE)            # derived intercept

def convert_to_ph(raw_value):
    voltage = (raw_value / ADC_MAX) * VREF
    ph = (voltage - V_PH7) / SLOPE + 7.0
    return round(voltage, 3), round(max(0.0, min(14.0, ph)), 2)

# ── Serial connection ─────────────────────────────────────────
def find_pico_port():
    for port in serial.tools.list_ports.comports():
        if port.vid == 0x2E8A or \
           'MicroPython' in (port.description or '') or \
           'Pico' in (port.description or ''):
            return port.device
    return None

def main():
    port = find_pico_port()
    if not port:
        print("Pico not found. Try manually setting port = '/dev/ttyACM0'")
        return

    ser = serial.Serial(port=port, baudrate=115200, timeout=2)
    print(f"Connected on {port}")
    print(f"Calibration: pH4={V_PH4}V  pH7={V_PH7}V  slope={SLOPE:.4f} V/pH\n")
    time.sleep(1)
    ser.reset_input_buffer()

    print(f"{'Time':<12} {'Raw ADC':<12} {'Voltage (V)':<14} {'pH':<8} {'Quality'}")
    print("─" * 56)

    try:
        while True:
            line = ser.readline().decode('utf-8').strip()
            if line:
                try:
                    raw = int(line)
                    voltage, ph = convert_to_ph(raw)
                    ts = time.strftime("%H:%M:%S")

                    # Simple quality flag
                    if ph < 1 or ph > 13:
                        quality = "⚠ check sensor"
                    elif voltage < 0.2 or voltage > 3.1:
                        quality = "⚠ check wiring"
                    else:
                        quality = "ok"

                    print(f"{ts:<12} {raw:<12} {voltage:<14.3f} {ph:<8} {quality}")
                except ValueError:
                    print(f"[Non-numeric]: {line}")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    main()