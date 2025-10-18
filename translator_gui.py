# translator_cmd.py
# CMD translator: mic -> STT (Google) -> Argos Translate (offline) + text translation
from __future__ import annotations
import os, sys, io, time, argparse
from pathlib import Path
from typing import Optional, Dict, List, Tuple

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
    from langdetect import detect_langs as dl
    from langdetect import DetectorFactory
    DetectorFactory.seed = 0
except Exception:
    dl = None

# optional key-hold recording
try:
    import keyboard   # requires admin on Windows
except Exception:
    keyboard = None


# ------------------- Popularity prior -----------------
POPULARITY_PRIOR: Dict[str, float] = {
    # very high
    "en": 1.00, "zh": 0.95, "es": 0.93, "hi": 0.90, "ar": 0.88, "fr": 0.86,
    "ru": 0.84, "pt": 0.83, "de": 0.82, "ja": 0.80, "id": 0.78, "bn": 0.76,
    # high
    "ur": 0.74, "it": 0.73, "tr": 0.72, "vi": 0.71, "ko": 0.70, "fa": 0.69,
    "pl": 0.67, "uk": 0.66, "nl": 0.65, "th": 0.64, "ro": 0.63, "el": 0.62,
    "sv": 0.61, "cs": 0.60, "hu": 0.59, "he": 0.58, "da": 0.57, "fi": 0.56,
    # medium
    "no": 0.55, "bg": 0.54, "sk": 0.53, "sr": 0.52, "hr": 0.51, "sl": 0.50,
    "lt": 0.49, "lv": 0.48, "et": 0.47, "ms": 0.46, "ta": 0.45, "te": 0.44,
    "mr": 0.43, "gu": 0.42, "kn": 0.41, "ml": 0.40, "ne": 0.39, "si": 0.38,
    "sw": 0.37, "az": 0.36, "ka": 0.35, "kk": 0.34, "mn": 0.33, "hy": 0.32,
    "mk": 0.31, "be": 0.30, "bs": 0.29, "af": 0.28, "is": 0.27, "ga": 0.26,
}
DEFAULT_PRIOR = 0.25

# Map ISO-639-1 -> preferred Google locale
GOOGLE_LOCALE: Dict[str, str] = {
    "en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE", "it": "it-IT",
    "pt": "pt-PT", "ru": "ru-RU", "ja": "ja-JP", "ko": "ko-KR", "zh": "zh-CN",
    "ar": "ar-SA", "hi": "hi-IN", "id": "id-ID", "nl": "nl-NL", "pl": "pl-PL",
    "tr": "tr-TR", "vi": "vi-VN", "uk": "uk-UA", "he": "he-IL", "cs": "cs-CZ",
    "sv": "sv-SE", "da": "da-DK", "fi": "fi-FI", "no": "no-NO", "ro": "ro-RO",
    "el": "el-GR", "th": "th-TH", "hu": "hu-HU", "bn": "bn-IN", "ur": "ur-PK",
    "fa": "fa-IR",
}
def to_google_locale(code: str) -> str:
    return GOOGLE_LOCALE.get(code, f"{code}-{code.upper()}")

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
            # capture
            class _Args: pass
            _a = _Args()
            _a.mode, _a.seconds, _a.phrase_limit, _a.max_seconds = mode, 10, None, None
            text, audio = _mic_capture(rec, mic, _a)
            if text is None and audio is None:
                print("Cancelled.")
                continue
            if not audio:
                print("No audio captured."); continue

            first_text = text or recognize_with_language(rec, audio, first_locale)
            if not first_text:
                print("No speech recognized.")
                continue

            if src_in == "auto":
                src_lang, score = detect_with_prior(first_text, 0.55)
                print(f"Detected language: {src_lang} (score={score:.2f})")
            else:
                src_lang = src_in

            detected_locale = to_google_locale(src_lang)
            if detected_locale.lower() != first_locale.lower():
                refined = recognize_with_language(rec, audio, detected_locale)
                text_to_translate = refined or first_text
            else:
                text_to_translate = first_text

            print(ensure_model(src_lang, tgt))
            print("Recognized:", text_to_translate)
            print("Translation:", translate_text(src_lang, tgt, text_to_translate))

        elif choice == "4":
            if dl is None:
                print("langdetect not installed. Run: pip install langdetect")
                continue
            text = input("Text to analyze: ").strip()
            if not text:
                print("No input.")
                continue
            print(dl(text))
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