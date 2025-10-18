#!/usr/bin/env python3
# tts_list.py
# Lists voices from: espeak-ng, pyttsx3, and Piper (if installed)

import os
import platform
import subprocess

def print_header(t):
    print("\n" + "="*len(t))
    print(t)
    print("="*len(t))

def have(cmd):
    try:
        subprocess.run([cmd, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def list_locale():
    print_header("Locale")
    try:
        out = subprocess.check_output(["locale"], text=True)
        print(out.strip())
    except Exception as e:
        print(f"(locale error: {e})")

def list_espeak():
    print_header("espeak-ng voices")
    if not have("espeak-ng"):
        print("espeak-ng not found.")
        return
    try:
        out = subprocess.check_output(["espeak-ng", "--voices"], text=True)
        print(out.rstrip())
        # Highlight Chinese
        zh = subprocess.check_output(["bash", "-lc", "espeak-ng --voices | grep -i ' zh' || true"], text=True)
        if zh.strip():
            print("\n[Chinese-related voices]")
            print(zh.rstrip())
        else:
            print("\n[Chinese-related voices] none found")
    except Exception as e:
        print(f"(espeak-ng error: {e})")

def list_pyttsx3():
    print_header("pyttsx3 voices")
    try:
        import pyttsx3
        eng = pyttsx3.init()
        voices = eng.getProperty("voices")
        if not voices:
            print("No pyttsx3 voices found.")
            return
        for v in voices:
            langs = getattr(v, "languages", []) or []
            langs = [x.decode("utf-8", "ignore") if isinstance(x, (bytes, bytearray)) else str(x) for x in langs]
            print(f"- id='{v.id}' | name='{v.name}' | langs={langs}")
        # highlight zh
        zh_hits = [v for v in voices if "zh" in (v.id.lower()+v.name.lower()+" ".join([str(l).lower() for l in getattr(v,"languages",[]) ]))]
        if zh_hits:
            print("\n[pyttsx3 Chinese-capable voices]")
            for v in zh_hits:
                print(f"- id='{v.id}' | name='{v.name}' | langs={getattr(v,'languages',[])}")
        else:
            print("\n[pyttsx3 Chinese-capable voices] none detected")
    except Exception as e:
        print(f"(pyttsx3 error: {e})")

def list_piper():
    print_header("Piper voices")
    if not have("piper"):
        print("piper not found.")
        return
    try:
        out = subprocess.check_output(["piper", "--list-voices"], text=True)
        print(out.rstrip())
        zh = subprocess.check_output(["bash", "-lc", "piper --list-voices | grep -i zh || true"], text=True)
        if zh.strip():
            print("\n[Chinese-related Piper voices]")
            print(zh.rstrip())
        else:
            print("\n[Chinese-related Piper voices] none found")
    except Exception as e:
        print(f"(piper error: {e})")

def main():
    print(f"OS: {platform.system()} {platform.release()}")
    list_locale()
    list_espeak()
    list_pyttsx3()
    list_piper()

if __name__ == "__main__":
    main()