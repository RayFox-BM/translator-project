# keyboard_input_evdev.py
from __future__ import annotations
import threading
from dataclasses import dataclass
from typing import Callable, Optional
from evdev import InputDevice, categorize, ecodes, KeyEvent, list_devices

@dataclass
class KeyboardCallbacks:
    on_digit: Callable[[str], None]
    on_ptt_down: Callable[[], None]
    on_ptt_up: Callable[[], None]
    on_toggle_mode: Callable[[], None]
    on_exit: Optional[Callable[[], None]] = None

# Map Linux keycodes to digits
KEYPAD_DIGITS = {
    ecodes.KEY_KP0: "0", ecodes.KEY_KP1: "1", ecodes.KEY_KP2: "2",
    ecodes.KEY_KP3: "3", ecodes.KEY_KP4: "4", ecodes.KEY_KP5: "5",
    ecodes.KEY_KP6: "6", ecodes.KEY_KP7: "7", ecodes.KEY_KP8: "8",
    ecodes.KEY_KP9: "9",
}
TOPROW_DIGITS = {
    ecodes.KEY_0: "0", ecodes.KEY_1: "1", ecodes.KEY_2: "2",
    ecodes.KEY_3: "3", ecodes.KEY_4: "4", ecodes.KEY_5: "5",
    ecodes.KEY_6: "6", ecodes.KEY_7: "7", ecodes.KEY_8: "8",
    ecodes.KEY_9: "9",
}

def _pick_keyboard_device(preferred: str | None = None) -> str:
    """Pick a likely keyboard/numpad input device path."""
    candidates = []
    for path in list_devices():
        dev = InputDevice(path)
        name = (dev.name or "").lower()
        # prefer external keypads / keyboards
        score = 0
        if "keyboard" in name: score += 2
        if "keypad" in name or "numpad" in name: score += 3
        if "usb" in name: score += 1
        candidates.append((score, path, name))
    if preferred:
        return preferred
    candidates.sort(reverse=True)
    return candidates[0][1] if candidates else "/dev/input/event0"

class KeyboardInput(threading.Thread):
    """
    Headless keyboard listener using evdev (Linux).
    Controls:
      • Digits 0..9 (top row or keypad) → on_digit(d)
      • Tap '.' ('.' or KP '.')        → on_toggle_mode()
      • Hold Backspace                 → on_ptt_down() / on_ptt_up()
      • ESC                            → exit
    """
    def __init__(self, callbacks: KeyboardCallbacks, device_path: str | None = None):
        super().__init__(daemon=True)
        self.cb = callbacks

        #change if keyboard is not event5
        self.device_path = "/dev/input/event5"
        self.dev = InputDevice(self.device_path)
        self._running = True
        self._ptt_active = False

    def run(self):
        print(f"[KEYBOARD] Listening on {self.device_path} ({self.dev.name})")
        for event in self.dev.read_loop():
            if not self._running:
                break
            if event.type != ecodes.EV_KEY:
                continue

            keyevent = categorize(event)  # KeyEvent
            if not isinstance(keyevent, KeyEvent):
                continue

            code = keyevent.scancode
            state = keyevent.keystate  # 0=up, 1=down, 2=hold

            # Ignore NumLock chatter
            if code == ecodes.KEY_NUMLOCK:
                continue

            # ESC to exit
            if code == ecodes.KEY_ESC and state == KeyEvent.key_up:
                print("[KEYBOARD] ESC — exiting")
                if self.cb.on_exit:
                    self.cb.on_exit()
                self.stop()
                break

            # Digits (top row or keypad) on key_down
            if state == KeyEvent.key_down:
                if code in KEYPAD_DIGITS:
                    self.cb.on_digit(KEYPAD_DIGITS[code]); continue
                if code in TOPROW_DIGITS:
                    self.cb.on_digit(TOPROW_DIGITS[code]); continue

                # PTT start on Backspace press
                if code == ecodes.KEY_BACKSPACE and not self._ptt_active:
                    self._ptt_active = True
                    self.cb.on_ptt_down(); continue

            # Key up events
            if state == KeyEvent.key_up:
                # Toggle mode on '.' release (period key or keypad dot)
                if code in (ecodes.KEY_DOT, ecodes.KEY_KPDOT, ecodes.KEY_DELETE):  # DELETE often maps to KP '.' with NumLock off
                    self.cb.on_toggle_mode(); continue

                # PTT stop on Backspace release
                if code == ecodes.KEY_BACKSPACE and self._ptt_active:
                    self._ptt_active = False
                    self.cb.on_ptt_up(); continue

    # lifecycle
    def start(self):
        super().start()

    def join(self):
        super().join()

    def stop(self):
        self._running = False
        try:
            self.dev.close()
        except Exception:
            pass