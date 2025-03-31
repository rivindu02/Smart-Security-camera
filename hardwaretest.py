#!/usr/bin/env python3
from gpiozero import MotionSensor, Buzzer
import time

# Initialize components
pir = MotionSensor(17)
buzzer = Buzzer(18)

print("Testing PIR and buzzer together - CTRL+C to exit")
print("Waiting for PIR to settle...")
pir.wait_for_no_motion()
print("Ready!")

try:
    while True:
        if pir.motion_detected:
            print("Motion detected - sounding alarm!")
            buzzer.on()
            time.sleep(0.5)  # Beep for 0.5 seconds
            buzzer.off()
        time.sleep(0.1)
except KeyboardInterrupt:
    buzzer.off()
    print("\nTest ended")
