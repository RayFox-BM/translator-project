from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional
from pynput import keyboard as kb

# Map Windows virtual-key codes for NUMPAD (works cross-platform via vk + KeyCode)
VK_TO_CHAR = {
    96: "0", 97: "1", 98: "2", 99: "3", 100: "4",
    101: "5", 102: "6", 103: "7", 104: "8", 105: "9",
    110: ".",  # numpad decimal (NumLock ON)
}

def _normalize_char(key) -> Optional[str]:
    """Return '0'..'9' or '.' for numpad/row keys; ignore others."""
    # 1) Prefer virtual-key code (captures numpad reliably on Windows)
    vk = getattr(key, "vk", None)
    if isinstance(vk, int) and vk in VK_TO_CHAR:
        return VK_TO_CHAR[vk]

    # 2) Some keyboards send Delete for numpad '.' when NumLock OFF
    if key == kb.Key.delete:
        return "."

    # 3) Regular character keys
    if isinstance(key, kb.KeyCode) and key.char is not None:
        ch = key.char
        if ch == ",":
            ch = "."  # locale decimal → dot
        if ch.isdigit() or ch == ".":
            return ch

    return None

@dataclass
class KeyboardCallbacks:
    on_digit: Callable[[str], None]                 # '0'..'9'
    on_ptt_down: Callable[[], None]                 # hold Backspace -> start talk
    on_ptt_up: Callable[[], None]                   # release Backspace -> stop talk
    on_toggle_mode: Callable[[], None]              # tap '.' -> toggle source/target
    on_exit: Optional[Callable[[], None]] = None    # ESC to exit (optional)

class KeyboardInput:
    """
    Controls:
      • Digits '0'..'9'      → callbacks.on_digit(d)
      • Tap '.' (any dot)    → callbacks.on_toggle_mode()
      • HOLD Backspace       → callbacks.on_ptt_down() on press, on_ptt_up() on release
      • ESC                  → exit listener
    """
    def __init__(self, callbacks: KeyboardCallbacks):
        self.cb = callbacks
        self._ptt_active = False

    # -- Event handlers -------------------------------------------------------
    def _on_press(self, key):
        # Ignore NumLock spam entirely
        if key == kb.Key.num_lock:
            return

        # Digits / '.' (we handle '.' on release as a toggle)
        ch = _normalize_char(key)
        if ch and ch.isdigit():
            self.cb.on_digit(ch)
            return

        # PTT start on Backspace press (only once per hold)
        if key == kb.Key.backspace and not self._ptt_active:
            self._ptt_active = True
            self.cb.on_ptt_down()
            return

    def _on_release(self, key):
        # ESC to exit
        if key == kb.Key.esc:
            if self.cb.on_exit:
                self.cb.on_exit()
            return False

        # Ignore NumLock release noise
        if key == kb.Key.num_lock:
            return

        # Toggle mode on '.' release (tap behavior)
        ch = _normalize_char(key)
        if ch == ".":
            self.cb.on_toggle_mode()
            return

        # PTT stop on Backspace release
        if key == kb.Key.backspace and self._ptt_active:
            self._ptt_active = False
            self.cb.on_ptt_up()
            return

    # -- Lifecycle ------------------------------------------------------------
    def start(self):
        self._listener = kb.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    def join(self):
        if hasattr(self, "_listener") and self._listener:
            self._listener.join()

    def stop(self):
        if hasattr(self, "_listener") and self._listener:
            self._listener.stop()