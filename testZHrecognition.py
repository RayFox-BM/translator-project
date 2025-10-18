#!/usr/bin/env python3
# tts_test_zh.py
# Tests Chinese TTS via espeak-ng, pyttsx3, and Piper (if present)
# Plays "早安，你好吗？" and prints which backend/voice was used.

import os
import subprocess
import sys
import platform

TEXT = "早安，你好吗？"

def say(msg): print(msg, flush=True)

def have(cmd):
    try:
        subprocess.run([cmd, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def ensure_utf8_locale():
    # Warn if not UTF-8 (can cause garbled Hanzi)
    lang = os.environ.get("LANG", "")
    if "UTF-8" not in lang.upper():
        say(f"[WARN] LANG is '{lang}'. UTF-8 is recommended (e.g., en_AU.UTF-8).")

def pick_espeak_zh_tag():
    """Return a usable zh tag, pref zh+f* / zh / mb-zh*; else None."""
    try:
        out = subprocess.check_output(["espeak-ng", "--voices"], text=True)
        lines = out.splitlines()
        tags = []
        for ln in lines:
            parts = ln.split()
            if len(parts) >= 2:
                tag = parts[1]
                if tag.lower().startswith("zh") or tag.lower().startswith("mb-zh"):
                    tags.append(tag)
        for pref in ["zh+f3","zh+f2","zh+f1","zh","mb-zh1","mb-zh2","mb-zh3"]:
            if pref in tags:
                return pref
        return tags[0] if tags else None
    except Exception:
        return None

def test_espeak():
    if platform.system() != "Linux":
        say("[espeak-ng] skip (not Linux).")
        return False
    if not have("espeak-ng"):
        say("[espeak-ng] not installed.")
        return False
    tag = pick_espeak_zh_tag()
    if not tag:
        say("[espeak-ng] no Chinese voice found. Try:\n  sudo apt update && sudo apt install espeak-ng-data mbrola mbrola-zh1 mbrola-zh2 mbrola-zh3")
        return False
    say(f"[espeak-ng] Using voice '{tag}' ...")
    try:
        subprocess.run(["espeak-ng", "-v", tag, TEXT], check=True)
        return True
    except Exception as e:
        say(f"[espeak-ng] error: {e}")
        return False

def test_pyttsx3():
    try:
        import pyttsx3
    except Exception as e:
        say(f"[pyttsx3] not installed: {e}")
        return False
    try:
        eng = pyttsx3.init()
        voices = eng.getProperty("voices")
        zh_id = None
        for v in voices:
            blob = (v.id + " " + v.name + " " + " ".join([str(x) for x in getattr(v, "languages", [])])).lower()
            if "zh" in blob or "mandarin" in blob or "chinese" in blob:
                zh_id = v.id
                break
        if not zh_id:
            say("[pyttsx3] no zh-capable voice found (engine would fall back to default English).")
            return False
        eng.setProperty("voice", zh_id)
        say(f"[pyttsx3] Using voice id='{zh_id}' ...")
        eng.say(TEXT)
        eng.runAndWait()
        return True
    except Exception as e:
        say(f"[pyttsx3] error: {e}")
        return False

def find_piper_model():
    # If env var set, prefer that; else pick first zh model from list
    model = os.environ.get("PIPER_ZH_MODEL")
    if model:
        return model
    try:
        out = subprocess.check_output(["piper", "--list-voices"], text=True)
        for ln in out.splitlines():
            if "zh" in ln.lower():
                # last column usually model id
                parts = ln.split()
                return parts[-1]
    except Exception:
        pass
    return None

def test_piper():
    if platform.system() != "Linux":
        say("[piper] skip (not Linux).")
        return False
    if not have("piper"):
        say("[piper] not installed. Install: sudo apt install piper")
        return False
    model = find_piper_model() or "zh_CN-huayan-medium"
    say(f"[piper] Using model '{model}' ...")
    try:
        wav = "tts_zh_test.wav"
        subprocess.run(
            ["piper", "--model", model, "--output_file", wav],
            input=TEXT.encode("utf-8"),
            check=True
        )
        # Play via ALSA
        subprocess.run(["aplay", wav], check=True)
        return True
    except Exception as e:
        say(f"[piper] error: {e}")
        return False

def main():
    say(f"Testing Chinese TTS with text: {TEXT}")
    ensure_utf8_locale()
    ok = False

    # Prefer pyttsx3 if a zh voice exists; else Piper; else espeak-ng
    if test_pyttsx3():
        ok = True
    elif test_piper():
        ok = True
    elif test_espeak():
        ok = True

    if not ok:
        say("\nResult: No working Chinese TTS yet.")
        say("Try installing voices:\n"
            "  sudo apt update\n"
            "  sudo apt install espeak-ng espeak-ng-data mbrola mbrola-zh1 mbrola-zh2 mbrola-zh3 piper\n"
            "Then rerun this test.")

if __name__ == "__main__":
    main()