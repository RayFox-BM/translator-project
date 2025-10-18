#!/usr/bin/env python3
from evdev import InputDevice, categorize, ecodes
import subprocess
import os
import signal

# === CONFIG ===
EVENT_PATH = "/dev/input/event2"   # change to your keyboard/numpad event path
LAUNCH_KEY = ecodes.KEY_KP0        # press to start translator
STOP_KEY   = ecodes.KEY_KPDOT      # press to stop translator
TRANSLATOR_CMD = "bash -c 'cd ~/translator-project && source venv/bin/activate && python3 main.py'"

# === STATE ===
process = None
dev = InputDevice(EVENT_PATH)
print(f"Listening for keys on {EVENT_PATH}…")
print("▶  Press NUMPAD0 to start translator")
print("■  Press NUMPAD. (dot) to stop translator")
print("Ctrl+C to quit listener.\n")

# === LOOP ===
for event in dev.read_loop():
    if event.type != ecodes.EV_KEY:
        continue
    key_event = categorize(event)
    key = key_event.scancode
    state = key_event.keystate  # 1 = pressed, 0 = released

    # --- start translator ---
    if key == LAUNCH_KEY and state == 1:
        if process is None or process.poll() is not None:
            print("▶ Launching translator…")
            process = subprocess.Popen(TRANSLATOR_CMD, shell=True,
                                       preexec_fn=os.setsid)
        else:
            print("⚠ Translator already running.")

    # --- stop translator ---
    elif key == STOP_KEY and state == 1:
        if process and process.poll() is None:
            print("■ Stopping translator…")
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process = None
        else:
            print("⚠ No translator process running.")