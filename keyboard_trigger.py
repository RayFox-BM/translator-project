#!/usr/bin/env python3
from evdev import InputDevice, categorize, ecodes
import subprocess

# === CONFIG ===
EVENT_PATH = "/dev/input/event5"   # change this to match your numpad device
LAUNCH_KEY = ecodes.KEY_KPPLUS     # Numpad "+" key

# === Command to run ===
CMD = "bash -c 'cd ~/translator-project && source venv/bin/activate && python3 main.py'"

# === Setup device ===
dev = InputDevice(EVENT_PATH)
print(f"Listening for '+' key on {dev.path} ({dev.name})")

for event in dev.read_loop():
    if event.type == ecodes.EV_KEY:
        key = categorize(event)
        if key.keycode == 'KEY_KPPLUS' and key.keystate == 1:  # key down
            print("Launching translator...")
            subprocess.Popen(CMD, shell=True)