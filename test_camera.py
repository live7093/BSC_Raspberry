#!/usr/bin/env python3
"""
test_cameras.py  –  Quick camera test
Takes one shot per camera and saves it to the current folder.
"""

from picamera2 import Picamera2
from libcamera import controls
import time

LENS_POSITION = 4.5  # 0.0 = infinity, 2.0 = ~50cm, 4.0 = ~25cm
WIDTH, HEIGHT = 1920, 1080  # e.g. 1920x1080, 2592x1944 (full), 640x480 (fast)


for idx in [0, 1]:
    print(f"Camera {idx}: capturing…")
    cam = Picamera2(idx)
    cam.configure(cam.create_still_configuration())
    cam.configure(cam.create_still_configuration(main={"size": (WIDTH, HEIGHT)}))
    cam.start()
    cam.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": LENS_POSITION})
    time.sleep(2)
    cam.capture_file(f"test_cam{idx}.jpg")
    cam.stop()
    cam.close()
    print(f"Camera {idx}: saved test_cam{idx}.jpg")

print("Done.")