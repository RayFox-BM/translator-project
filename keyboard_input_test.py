from pynput import keyboard as kb

print("🔢 Unified Keyboard Test")
print("Press digits on top row or NUMPAD (0–9) and NUMPAD '.'")
print("ESC to exit. NumLock presses are ignored.\n")

# Windows virtual-key codes for numpad
VK_TO_CHAR = {
    96: "0", 97: "1", 98: "2", 99: "3", 100: "4",
    101: "5", 102: "6", 103: "7", 104: "8", 105: "9",
    110: ".",   # numpad decimal with NumLock ON
}
VK_NUMLOCK = 144

def normalize_char(key):
    """Return a unified character ('0'..'9' or '.') for any digit/decimal key.
       Returns None for other keys. NumLock is handled by caller."""
    # 1) Numpad by virtual key
    vk = getattr(key, "vk", None)
    if isinstance(vk, int):
        if vk in VK_TO_CHAR:
            return VK_TO_CHAR[vk]

    # 2) Some keyboards send numpad '.' as Delete when NumLock is OFF
    if key == kb.Key.delete:
        return "."

    # 3) Normal character keys
    if isinstance(key, kb.KeyCode) and key.char is not None:
        ch = key.char
        # Treat locale decimal ',' as '.'
        if ch == ",":
            return "."
        if ch.isdigit() or ch == ".":
            return ch

    return None

def on_press(key):
    # Ignore NumLock entirely
    if key == kb.Key.num_lock or getattr(key, "vk", None) == VK_NUMLOCK:
        return

    ch = normalize_char(key)
    if ch is not None:
        print(f"🔘 Pressed: '{ch}'")
    else:
        # For visibility you can comment this out if you only want digits/ptt
        print(f"(other key down: {key})")

def on_release(key):
    # Ignore NumLock entirely
    if key == kb.Key.num_lock or getattr(key, "vk", None) == VK_NUMLOCK:
        return

    ch = normalize_char(key)
    if ch is not None:
        print(f"◽ Released: '{ch}'")
    else:
        # Comment out if not needed
        print(f"(other key up: {key})")

    if key == kb.Key.esc:
        print("\nESC → exit")
        return False

with kb.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()