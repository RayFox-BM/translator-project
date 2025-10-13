# translator_cmd.py
# CMD translator: mic -> STT (Google) -> Argos Translate (offline) + text translation
from __future__ import annotations
import os, sys, io, time, argparse
from pathlib import Path
from typing import Optional
from language_popularity import detect_with_popularity

# -------------------- argos packages dir BEFORE importing argostranslate --------------------
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PACK_DIR = BASE_DIR / "argos-data"
PACK_DIR.mkdir(parents=True, exist_ok=True)
os.environ["ARGOS_PACKAGES_DIR"] = str(PACK_DIR)

# -------------------- deps --------------------
import speech_recognition as sr
import argostranslate.package as argos_pkg
import argostranslate.translate as argos_tx

# optional language detection from text
try:
    from langdetect import detect as lang_detect
except Exception:
    lang_detect = None

# optional key-hold recording
try:
    import keyboard   # requires admin on Windows
except Exception:
    keyboard = None


# -------------------- Argos helpers --------------------
def model_installed(src: str, tgt: str) -> bool:
    argos_tx.load_installed_languages()
    for pkg in argos_pkg.get_installed_packages():
        if pkg.from_code == src and pkg.to_code == tgt:
            return True
    return False

def ensure_model(src: str, tgt: str) -> str:
    argos_pkg.update_package_index()
    argos_tx.load_installed_languages()
    if model_installed(src, tgt):
        return "Model already installed."

    pkgs = argos_pkg.get_available_packages()
    pkg = next((p for p in pkgs if p.from_code == src and p.to_code == tgt), None)
    if not pkg:
        return f"No Argos package available for {src}->{tgt}."

    path = pkg.download()
    argos_pkg.install_from_path(path)
    argos_tx.load_installed_languages()
    return "Model installed." if model_installed(src, tgt) else "Installed, but not visible. Try running again."

def translate_text(src: str, tgt: str, text: str) -> str:
    argos_tx.load_installed_languages()
    langs = argos_tx.get_installed_languages()
    from_lang = next((l for l in langs if getattr(l, "code", None) == src), None)
    to_lang   = next((l for l in langs if getattr(l, "code", None) == tgt), None)
    if not (from_lang and to_lang):
        return "Selected model not available. Run install first."
    tr = from_lang.get_translation(to_lang)
    return tr.translate(text)

# -------------------- STT helpers --------------------
def stt_listen_auto(recognizer: sr.Recognizer, mic: sr.Microphone,
                    timeout: Optional[float] = None, phrase_time_limit: Optional[float] = None) -> str:
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        return f"Speech service error: {e}"

def stt_record_seconds(recognizer: sr.Recognizer, mic: sr.Microphone, seconds: int) -> str:
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.record(source, duration=seconds)
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        return f"Speech service error: {e}"

def stt_hold_to_record(recognizer: sr.Recognizer, mic: sr.Microphone,
                       hold_key: str = "enter", quit_key: str = "esc",
                       max_seconds: Optional[float] = None) -> str | None:
    if keyboard is None:
        print("Hold-to-record requires the 'keyboard' package and appropriate permissions.")
        return ""
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("Hold Enter to record, press Esc to quit.")
        # wait for hold or quit
        while True:
            if keyboard.is_pressed(quit_key):
                return None
            if keyboard.is_pressed(hold_key):
                break
            time.sleep(0.01)

        print("Recording... release Enter to stop.")
        stream = source.stream
        chunk = source.CHUNK
        buf = io.BytesIO()
        start = time.time()
        while keyboard.is_pressed(hold_key):
            if keyboard.is_pressed(quit_key):
                return None
            data = stream.read(chunk)
            if not data:
                break
            buf.write(data)
            if max_seconds is not None and (time.time() - start) >= max_seconds:
                break
        raw = buf.getvalue()
        if not raw:
            return ""
        audio = sr.AudioData(raw, source.SAMPLE_RATE, source.SAMPLE_WIDTH)
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        return f"Speech service error: {e}"

def list_microphones():
    names = sr.Microphone.list_microphone_names()
    if not names:
        print("No microphones found.")
    else:
        for idx, name in enumerate(names):
            print(f"[{idx}] {name}")

# -------------------- CLI command handlers --------------------
def cmd_install(args):
    msg = ensure_model(args.src, args.tgt)
    print(msg)

def cmd_translate(args):
    msg = ensure_model(args.src, args.tgt)
    if "No Argos package" in msg:
        print(msg); return
    if args.text is None and not sys.stdin.isatty():
        args.text = sys.stdin.read()
    if not args.text:
        print("No input text."); return
    out = translate_text(args.src, args.tgt, args.text)
    print(out)

def cmd_detect(args):
    if lang_detect is None:
        print("langdetect not installed. Run: pip install langdetect")
        return
    txt = args.text or ("" if sys.stdin.isatty() else sys.stdin.read())
    if not txt.strip():
        print("No input text to detect."); return
    print(detect_with_popularity(txt))

def cmd_mic(args):
    msg = ensure_model(args.src, args.tgt)
    if "No Argos package" in msg:
        print(msg); return

    rec = sr.Recognizer()
    mic = sr.Microphone(device_index=args.device)

    if args.mode == "auto":
        print("Listening (auto-stop on silence)...")
        text = stt_listen_auto(rec, mic, timeout=None, phrase_time_limit=args.phrase_limit)
    elif args.mode == "seconds":
        print(f"Recording {args.seconds} seconds...")
        text = stt_record_seconds(rec, mic, seconds=args.seconds)
    elif args.mode == "hold":
        text = stt_hold_to_record(rec, mic, hold_key="enter", quit_key="esc", max_seconds=args.max_seconds)
        if text is None:
            print("Exiting."); return
    else:
        print("Unknown mode."); return

    if not text:
        print("No speech recognized."); return

    print("Recognized:", text)
    out = translate_text(args.src, args.tgt, text)
    print("Translation:", out)

# -------------------- argparse --------------------
def build_parser():
    p = argparse.ArgumentParser(description="Argos offline translator (CLI).")
    sub = p.add_subparsers(dest="cmd", required=True)

    ip = sub.add_parser("install", help="Install a model pair into ./argos-data")
    ip.add_argument("--src", required=True, help="source lang code (e.g., en)")
    ip.add_argument("--tgt", required=True, help="target lang code (e.g., es)")
    ip.set_defaults(func=cmd_install)

    tp = sub.add_parser("translate", help="Translate text")
    tp.add_argument("--src", required=True)
    tp.add_argument("--tgt", required=True)
    tp.add_argument("--text", help="text to translate; if omitted, reads stdin")
    tp.set_defaults(func=cmd_translate)

    dp = sub.add_parser("detect", help="Detect language of text (requires langdetect)")
    dp.add_argument("--text", help="text to detect; if omitted, reads stdin")
    dp.set_defaults(func=cmd_detect)

    mp = sub.add_parser("mic", help="Record speech then translate")
    mp.add_argument("--src", required=True)
    mp.add_argument("--tgt", required=True)
    mp.add_argument("--mode", choices=["auto","seconds","hold"], default="auto")
    mp.add_argument("--seconds", type=int, default=10, help="seconds for --mode seconds")
    mp.add_argument("--phrase-limit", type=int, default=None, help="limit seconds for auto mode")
    mp.add_argument("--max-seconds", type=int, default=None, help="cap for hold mode")
    mp.add_argument("--device", type=int, default=None, help="microphone device_index (optional)")
    mp.set_defaults(func=cmd_mic)

    return p

# -------------------- Interactive menu --------------------
def interactive_menu():
    print("\nArgos Translator (interactive mode)")
    while True:
        print("\nChoose an action:")
        print(" 1) Install model")
        print(" 2) Translate typed text")
        print(" 3) Microphone → translate")
        print(" 4) Detect language of text")
        print(" 5) List microphones")
        print(" 6) Quit")

        choice = input("> ").strip()
        if choice == "1":
            src = input("Source language (e.g., en): ").strip().lower()
            tgt = input("Target language (e.g., ja): ").strip().lower()
            print(ensure_model(src, tgt))
        elif choice == "2":
            src = input("Source language: ").strip().lower()
            tgt = input("Target language: ").strip().lower()
            print(ensure_model(src, tgt))
            text = input("Text to translate: ").strip()
            print(translate_text(src, tgt, text))
        elif choice == "3":
            src = input("Source language: ").strip().lower()
            tgt = input("Target language: ").strip().lower()
            mode = input("Mode [auto/seconds/hold] (default auto): ").strip().lower() or "auto"
            device = input("Mic device index (blank = default): ").strip()
            device = int(device) if device else None
            rec = sr.Recognizer()
            mic = sr.Microphone(device_index=device)
            print(ensure_model(src, tgt))
            if mode == "seconds":
                sec = input("Seconds (default 10): ").strip()
                sec = int(sec) if sec else 10
                text = stt_record_seconds(rec, mic, seconds=sec)
            elif mode == "hold":
                text = stt_hold_to_record(rec, mic, hold_key="enter", quit_key="esc", max_seconds=None)
                if text is None:
                    print("Cancelled.")
                    continue
            else:
                text = stt_listen_auto(rec, mic, timeout=None, phrase_time_limit=None)
            if not text:
                print("No speech recognized.")
                continue
            print("Recognized:", text)
            print("Translation:", translate_text(src, tgt, text))
        elif choice == "4":
            if lang_detect is None:
                print("langdetect not installed. Run: pip install langdetect")
                continue
            text = input("Text to analyze: ").strip()
            if not text:
                print("No input.")
                continue
            print("Detected:", lang_detect(text))
        elif choice == "5":
            list_microphones()
        elif choice == "6":
            print("Goodbye.")
            break
        else:
            print("Invalid choice.")

# -------------------- entry point --------------------
def main():
    # If no arguments: interactive "user decide" mode
    if len(sys.argv) == 1:
        interactive_menu()
        return

    # Otherwise: normal argparse CLI
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()