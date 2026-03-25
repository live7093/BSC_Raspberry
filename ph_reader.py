import serial
import serial.tools.list_ports
import time

def find_pico_port():
    """Auto-detect the Pico's USB serial port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Pico shows up as MicroPython or with specific USB IDs
        if 'MicroPython' in (port.description or '') or \
           'Pico' in (port.description or '') or \
           (port.vid == 0x2E8A):  # Raspberry Pi vendor ID
            print(f"Found Pico on: {port.device}")
            return port.device
    return None

def convert_to_ph(raw_value, vref=3.3, adc_bits=16):
    """
    Convert raw ADC value to pH.
    Adjust the formula based on your specific pH sensor's datasheet.
    Typical Grove pH sensor: pH = 7 - ((voltage - 2.5) / 0.18)
    """
    voltage = (raw_value / 65535) * vref
    ph = 7.0 - ((voltage - 2.5) / 0.18)
    ph = max(0.0, min(14.0, ph))  # Clamp to valid pH range
    return voltage, ph

def main():
    # --- 1. Find the Pico port ---
    port = find_pico_port()
    if not port:
        print("Pico not found. Available ports:")
        for p in serial.tools.list_ports.comports():
            print(f"  {p.device} - {p.description} (VID:{p.vid})")
        print("\nSet port manually, e.g.: port = '/dev/ttyACM0'")
        return

    # --- 2. Open serial connection ---
    try:
        ser = serial.Serial(
            port=port,
            baudrate=115200,
            timeout=2
        )
        print(f"Connected to Pico on {port} at 115200 baud\n")
        time.sleep(1)  # Allow connection to stabilise
        ser.reset_input_buffer()

    except serial.SerialException as e:
        print(f"Failed to open port: {e}")
        print("Try: sudo chmod 666 /dev/ttyACM0  (or add user to 'dialout' group)")
        return

    # --- 3. Read and process data ---
    print(f"{'Time':<12} {'Raw ADC':<12} {'Voltage':<12} {'pH':<8}")
    print("-" * 44)

    try:
        while True:
            line = ser.readline().decode('utf-8').strip()

            if line:
                try:
                    raw_value = int(line)
                    voltage, ph = convert_to_ph(raw_value)
                    timestamp = time.strftime("%H:%M:%S")
                    print(f"{timestamp:<12} {raw_value:<12} {voltage:<12.3f} {ph:<8.2f}")

                except ValueError:
                    print(f"[Non-numeric data]: {line}")

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        ser.close()
        print("Serial connection closed.")

if __name__ == "__main__":
    main()