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

# -------------------- Detection helpers (Method 3 core) --------------------
def detect_with_prior(text: str, min_conf: float = 0.55) -> Tuple[str, float]:
    """
    Returns (best_lang_code, posterior_prob). Uses langdetect and multiplies by POPULARITY_PRIOR.
    Falls back to ('en', 1.0) if langdetect unavailable or text too short.
    """
    if not dl:
        return "en", 1.0
    text = (text or "").strip()
    if len(text) < 6:
        return "en", 0.6  # too short—assume English mildly

    try:
        candidates = dl(text)  # e.g. [en:0.64, fr:0.18, ...]
    except Exception:
        return "en", 0.6

    scored: List[Tuple[str, float]] = []
    for c in candidates:
        code = c.lang.split("-")[0]  # normalize
        prior = POPULARITY_PRIOR.get(code, DEFAULT_PRIOR)
        scored.append((code, c.prob * prior))

    if not scored:
        return "en", 0.6

    scored.sort(key=lambda x: x[1], reverse=True)
    best_code, best_score = scored[0]
    return (best_code if best_score >= min_conf else "en", max(best_score, 0.6))

# -------------------- STT helpers (now return audio when requested) --------------------
def recognize_with_language(recognizer: sr.Recognizer, audio: sr.AudioData, language: Optional[str] = None) -> str:
    try:
        if language:
            return recognizer.recognize_google(audio, language=language)
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        return f"Speech service error: {e}"

def stt_listen_auto(recognizer: sr.Recognizer, mic: sr.Microphone,
                    timeout: Optional[float] = None, phrase_time_limit: Optional[float] = None,
                    return_audio: bool = False) -> str | Tuple[str, sr.AudioData]:
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    text = recognize_with_language(recognizer, audio, None)
    return (text, audio) if return_audio else text

def stt_record_seconds(recognizer: sr.Recognizer, mic: sr.Microphone, seconds: int,
                       return_audio: bool = False) -> str | Tuple[str, sr.AudioData]:
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.record(source, duration=seconds)
    text = recognize_with_language(recognizer, audio, None)
    return (text, audio) if return_audio else text

def stt_hold_to_record(recognizer: sr.Recognizer, mic: sr.Microphone,
                       hold_key: str = "caps lock", quit_key: str = "esc",
                       max_seconds: Optional[float] = None,
                       return_audio: bool = False) -> str | None | Tuple[str, sr.AudioData]:
    if keyboard is None:
        print("Hold-to-record requires the 'keyboard' package and appropriate permissions.")
        return ""
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("Hold Caps Lock to record, press Esc to quit.")
        # wait for hold or quit
        while True:
            if keyboard.is_pressed(quit_key):
                return None
            if keyboard.is_pressed(hold_key):
                break
            time.sleep(0.01)

        print("Recording... release Caps Lock to stop.")
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
            return "" if not return_audio else ("", None)  # nothing recorded
        audio = sr.AudioData(raw, source.SAMPLE_RATE, source.SAMPLE_WIDTH)
    text = recognize_with_language(recognizer, audio, None)
    return (text, audio) if return_audio else text

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
    if dl is None:
        print("langdetect not installed. Run: pip install langdetect")
        return
    txt = args.text or ("" if sys.stdin.isatty() else sys.stdin.read())
    if not txt.strip():
        print("No input text to detect."); return
    print(dl(txt))

def _mic_capture(rec: sr.Recognizer, mic: sr.Microphone, args) -> Tuple[str, sr.AudioData | None]:
    """Capture audio/text per selected mode, returning (first_pass_text, audio)."""
    if args.mode == "auto":
        print("Listening (auto-stop on silence)...")
        text, audio = stt_listen_auto(rec, mic, timeout=None, phrase_time_limit=args.phrase_limit, return_audio=True)
    elif args.mode == "seconds":
        print(f"Recording {args.seconds} seconds...")
        text, audio = stt_record_seconds(rec, mic, seconds=args.seconds, return_audio=True)
    elif args.mode == "hold":
        result = stt_hold_to_record(rec, mic, hold_key="caps lock", quit_key="esc", max_seconds=args.max_seconds, return_audio=True)
        if result is None:
            return None, None
        text, audio = result
    else:
        raise ValueError("Unknown mode.")
    return text, audio

def is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except Exception:
        return False

def score_text_with_prior(text: str) -> tuple[str, float]:
    # uses your existing detect_with_prior()
    try:
        return detect_with_prior(text, min_conf=0.0)
    except Exception:
        return ("en", 0.0)

def try_locales_and_pick_best(rec: sr.Recognizer, audio: sr.AudioData,
                              locales: list[str], debug: bool = False
) -> tuple[str, str, str, float]:
    """
    Try STT with several locales. Returns (best_locale, transcript, detected_lang, posterior_score).
    Score = posterior * transcript length (longer, coherent text wins).
    """
    candidates = []
    for loc in locales:
        txt = recognize_with_language(rec, audio, loc)
        if not txt:
            continue
        lang, post = score_text_with_prior(txt)
        score = post * max(1, len(txt))
        candidates.append((loc, txt, lang, post, score))

    if not candidates:
        return ("", "", "en", 0.0)

    candidates.sort(key=lambda x: x[-1], reverse=True)
    best_loc, best_txt, best_lang, best_post, _ = candidates[0]

    if debug:
        print("\n[debug] multi-locale candidates:")
        for loc, txt, lang, post, sc in candidates:
            preview = (txt[:80] + "...") if len(txt) > 80 else txt
            print(f"  - {loc}: lang={lang} post={post:.2f} len={len(txt)} score={sc:.2f} :: {preview}")
        print(f"[debug] picked -> {best_loc} (lang={best_lang}, post={best_post:.2f})\n")

    return (best_loc, best_txt, best_lang, best_post)

def cmd_mic(args):
    rec = sr.Recognizer()
    rec.dynamic_energy_threshold = True
    rec.pause_threshold = 0.6
    rec.non_speaking_duration = 0.2

    mic = sr.Microphone(device_index=args.device)

    # 1) Capture audio + first-pass transcript (whatever the helpers gave us)
    first_locale = args.first_lang or "en-US"
    text, audio = _mic_capture(rec, mic, args)
    if text is None and audio is None:
        print("Exiting."); return
    if not audio:
        print("No audio captured."); return

    # Ensure we have a first transcript using the requested first locale
    first_text = text or recognize_with_language(rec, audio, first_locale)
    if args.debug:
        print(f"[debug] first pass locale={first_locale}")
        print(f"[debug] first pass text='{(first_text or '')[:100]}'")

    # 2) If user forced --src, skip auto detection (but re-run STT in that locale once)
    if args.src != "auto":
        src_lang = args.src
        detected_locale = to_google_locale(src_lang)
        text_to_translate = first_text or ""
        if detected_locale.lower() != first_locale.lower():
            refined = recognize_with_language(rec, audio, detected_locale)
            if refined:
                text_to_translate = refined
        if not text_to_translate:
            print("No speech recognized."); return
        msg = ensure_model(src_lang, args.tgt)
        if "No Argos package" in msg:
            print(msg); return
        print("Recognized:", text_to_translate)
        print("Translation:", translate_text(src_lang, args.tgt, text_to_translate))
        return

    # 3) AUTO path: detect from first text
    src_lang, score = detect_with_prior(first_text or "", min_conf=0.55)
    detected_locale = to_google_locale(src_lang)
    if args.debug:
        print(f"[debug] detection from first pass: src={src_lang} score={score:.2f} -> {detected_locale}")

    # Heuristics to decide if we MUST probe multiple locales:
    # - no text
    # - low score
    # - first locale is zh-* but transcript is ASCII (likely wrong)
    need_probe = (not first_text) or (score < 0.70) or (
        first_locale.lower().startswith("zh") and first_text and is_ascii(first_text)
    )

    if need_probe:
        probe_locales = [l.strip() for l in (args.auto_locales or "").split(",") if l.strip()]
        # Ensure both detected_locale and first_locale are included at front
        for loc in [detected_locale, first_locale]:
            if loc and loc not in probe_locales:
                probe_locales.insert(0, loc)

        best_loc, best_txt, best_lang, best_post = try_locales_and_pick_best(
            rec, audio, probe_locales, debug=args.debug
        )

        if best_txt:
            detected_locale = best_loc
            src_lang = best_lang
            text_to_translate = best_txt
            print(f"Detected language: {src_lang} (via {detected_locale}, post≈{best_post:.2f})")
        else:
            # fallback to first pass
            text_to_translate = first_text
            print(f"Detected language: {src_lang} (score={score:.2f})")
    else:
        text_to_translate = first_text
        print(f"Detected language: {src_lang} (score={score:.2f})")

    if not text_to_translate:
        print("No speech recognized."); return

    # 4) Translate
    msg = ensure_model(src_lang, args.tgt)
    if "No Argos package" in msg:
        print(msg); return
    print("Recognized:", text_to_translate)
    out = translate_text(src_lang, args.tgt, text_to_translate)
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
    mp.add_argument("--src", default="auto", help="source lang code or 'auto' (default auto)")
    mp.add_argument("--tgt", required=True, help="target lang code (Argos)")
    mp.add_argument("--mode", choices=["auto","seconds","hold"], default="auto")
    mp.add_argument("--seconds", type=int, default=10, help="seconds for --mode seconds")
    mp.add_argument("--phrase-limit", type=int, default=None, help="limit seconds for auto mode")
    mp.add_argument("--max-seconds", type=int, default=None, help="cap for hold mode")
    mp.add_argument("--device", type=int, default=None, help="microphone device_index (optional)")
    mp.add_argument("--first-lang", default="en-US", help="Assuming language (default en-US)")
    mp.add_argument("--debug", action="store_true", help="print debug info")
    mp.add_argument(
        "--auto-locales",
        default="en-US,zh-CN,zh-TW,es-ES,ja-JP,fr-FR",
        help="comma-separated STT locales to probe when --src auto"
    )
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
            src_in = input("Source language (or 'auto'): ").strip().lower() or "auto"
            tgt = input("Target language: ").strip().lower()
            mode = input("Mode [auto/seconds/hold] (default auto): ").strip().lower() or "auto"
            device = input("Mic device index (blank = default): ").strip()
            device = int(device) if device else None
            first_locale = input("First-pass STT locale (default en-US): ").strip() or "en-US"
            rec = sr.Recognizer()
            mic = sr.Microphone(device_index=device)

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