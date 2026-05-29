
import board, neopixel_spi as neospi, time, subprocess
spi    = board.SPI()
pixels = neospi.NeoPixel_SPI(spi, 56, brightness=0.1, auto_write=False)
print('Brightness test - 56 LEDs, lens-position 4.1')
for b in range(1, 6):
    brightness = round(b / 10, 1)
    pixels.brightness = brightness
    pixels.fill((255, 255, 255))
    pixels.show()
    time.sleep(0.5)
    fname = f'test_brightness_{brightness}.jpg'
    subprocess.run(['rpicam-still', '-o', fname, '--lens-position', '4.1',
                    '--timeout', '1000', '--width', '2400', '--height', '2400'])
    print(f'  Captured {fname}')
pixels.fill((0, 0, 0))
pixels.show()
print('Done - LEDs off')
