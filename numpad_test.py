from pynput import keyboard as pyn_kb
from numpad_normaliser import normalize_keypress

print("Numpad demo: press numpad 0–9 or numpad '.' (PTT). ESC to exit.\n")

def on_press(key):
    kind, payload = normalize_keypress(key)
    if kind == "digit":
        print(f"[TARGET] set by digit: {payload}")
    elif kind == "ptt":
        print("[PTT] DOWN")
    # 'ignore' -> do nothing

def on_release(key):
    kind, payload = normalize_keypress(key)
    if kind == "ptt":
        print("[PTT] UP")
    if key == pyn_kb.Key.esc:
        print("ESC -> exit")
        return False

with pyn_kb.Listener(on_press=on_press, on_release=on_release) as l:
    l.join()