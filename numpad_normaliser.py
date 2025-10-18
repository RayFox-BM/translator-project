# numpad_normalizer.py
from pynput import keyboard as pyn_kb

# Windows VK codes for the numpad:
VK_TO_DIGIT = {
    96: "0", 97: "1", 98: "2", 99: "3", 100: "4",
    101: "5", 102: "6", 103: "7", 104: "8", 105: "9",
}
VK_DECIMAL = 110  # numpad '.'

def normalize_keypress(key):
    """
    Returns one of:
      ("digit", "0".."9")
      ("ptt", None)           # numpad decimal '.' or Delete (common on some boards)
      ("ignore", None)
    Works with external numpads and laptop numpads.
    """
    # 1) Numpad by VK code
    vk = getattr(key, "vk", None)
    if isinstance(vk, int):
        if vk in VK_TO_DIGIT:
            return ("digit", VK_TO_DIGIT[vk])
        if vk == VK_DECIMAL:
            return ("ptt", None)

    # 2) Main-row digits / locale chars
    if isinstance(key, pyn_kb.KeyCode) and key.char:
        ch = key.char
        if ch.isdigit():
            return ("digit", ch)
        if ch in {".", ","}:
            # Some layouts send ',' for decimal
            return ("ptt", None)

    # 3) Some keyboards send numpad '.' as Delete when NumLock is off
    if key == pyn_kb.Key.delete:
        return ("ptt", None)

    # 4) Ignore num_lock and others
    if key == pyn_kb.Key.num_lock:
        return ("ignore", None)

    return ("ignore", None)