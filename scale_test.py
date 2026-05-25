import lgpio
import time

DAT = 5
CLK = 6

h = lgpio.gpiochip_open(4)
lgpio.gpio_claim_input(h, DAT)
lgpio.gpio_claim_output(h, CLK, 0)

# HX711 Reset — CLK für >60us HIGH halten
print("Reset HX711...")
lgpio.gpio_write(h, CLK, 1)
time.sleep(0.1)
lgpio.gpio_write(h, CLK, 0)
time.sleep(0.5)

print(f"DAT nach Reset: {lgpio.gpio_read(h, DAT)}")

# Warte bis DAT LOW wird (bereit)
print("Warte auf HX711 bereit...")
timeout = time.time() + 5
while lgpio.gpio_read(h, DAT) == 1:
    if time.time() > timeout:
        print("HX711 antwortet nicht — Verkabelung prüfen!")
        lgpio.gpiochip_close(h)
        exit()
    time.sleep(0.01)

print("HX711 bereit!")

def read_raw():
    count = 0
    for _ in range(24):
        lgpio.gpio_write(h, CLK, 1)
        time.sleep(0.00001)
        count = (count << 1) | lgpio.gpio_read(h, DAT)
        lgpio.gpio_write(h, CLK, 0)
        time.sleep(0.00001)
    lgpio.gpio_write(h, CLK, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, CLK, 0)
    if count & 0x800000:
        count -= 0x1000000
    return count

for _ in range(5):
    val = read_raw()
    print(f"RAW: {val}")
    time.sleep(0.5)

lgpio.gpiochip_close(h)
