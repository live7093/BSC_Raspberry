import lgpio
import time

DAT = 5
CLK = 6

h = lgpio.gpiochip_open(4)
lgpio.gpio_claim_input(h, DAT)
lgpio.gpio_claim_output(h, CLK, 0)

lgpio.gpio_write(h, CLK, 1)
time.sleep(0.5)
lgpio.gpio_write(h, CLK, 0)
time.sleep(1.0)

def read_raw():
    timeout = time.time() + 3
    while lgpio.gpio_read(h, DAT) != 0:
        if time.time() > timeout:
            return None
        time.sleep(0.001)

    count = 0
    for _ in range(24):
        lgpio.gpio_write(h, CLK, 1)
        time.sleep(0.002)
        lgpio.gpio_write(h, CLK, 0)
        time.sleep(0.002)
        bit = lgpio.gpio_read(h, DAT)  # lesen NACH fallender Flanke
        count = (count << 1) | bit

    lgpio.gpio_write(h, CLK, 1)
    time.sleep(0.002)
    lgpio.gpio_write(h, CLK, 0)

    if count & 0x800000:
        count -= 0x1000000
    return count

for _ in range(5):
    print(read_raw())
    time.sleep(0.5)

lgpio.gpiochip_close(h)
