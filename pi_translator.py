# will modify for raspberry pi in the future
# --- set env BEFORE importing argostranslate ---
import os
from pathlib import Path

# project-local dir
BASE_DIR = Path(__file__).resolve().parent
PACK_DIR = BASE_DIR / "argos-data"
PACK_DIR.mkdir(parents=True, exist_ok=True)

# IMPORTANT: must be set before any argostranslate import
os.environ["ARGOS_PACKAGES_DIR"] = str(PACK_DIR)

# now import argos
import argostranslate.package as argos_pkg
import argostranslate.translate as argos_tx

# importing microphone dependencies
import io, time, keyboard, speech_recognition as sr

def recognize_speech_hold(recognizer: sr.Recognizer,
                          mic: sr.Microphone,
                          hold_key: str = "enter",
                          quit_key: str = "esc",
                          max_seconds: float | None = None) -> str | None:
    """
    Returns:
      str  = recognized text
      ""   = capture/recognition failure
      None = quit_key pressed before recording starts
    """
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("Hold Enter to record, press Esc to quit.")

        # Wait for either hold_key press or quit_key press
        while True:
            if keyboard.is_pressed(quit_key):
                return None
            if keyboard.is_pressed(hold_key):
                break
            time.sleep(0.01)

        print("Recording... release Enter to stop.")
        audio_buf = io.BytesIO()
        start = time.time()

        stream = source.stream  # MicrophoneStream from SpeechRecognition
        chunk_size = source.CHUNK  # default: 1024 frames

        # Read raw chunks while key is held
        while keyboard.is_pressed(hold_key):
            if keyboard.is_pressed(quit_key):
                print("Quit requested.")
                return None
            data = stream.read(chunk_size)  # <-- FIXED: removed exception_on_overflow
            if not data:
                break
            audio_buf.write(data)
            if max_seconds is not None and (time.time() - start) >= max_seconds:
                break

        print("Stopped recording.")

        raw = audio_buf.getvalue()
        if not raw:
            print("No audio captured.")
            return ""

        audio = sr.AudioData(raw, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

    # Recognize speech (Google API)
    try:
        text = recognizer.recognize_google(audio)
        print("Heard:", text)
        return text
    except sr.UnknownValueError:
        print("Could not understand audio.")
        return ""
    except sr.RequestError as e:
        print("Speech service error:", e)
        return ""
    

def using_dir() -> Path:
    # helper to print which directory we're actually using
    # (argos doesn't expose a public getter; we trust the env var we set)
    return Path(os.environ.get("ARGOS_PACKAGES_DIR", ""))


def model_installed(src: str, tgt: str) -> bool:
    # Make sure Argos' in-memory registry is fresh
    argos_tx.load_installed_languages()
    # Package layer is authoritative for installed pairs
    for pkg in argos_pkg.get_installed_packages():
        if pkg.from_code == src and pkg.to_code == tgt:
            return True
    return False

def install(src="en", tgt="es"):
    print(f"Packages dir (intended): {using_dir()}")
    argos_pkg.update_package_index()

    if model_installed(src, tgt) and any(PACK_DIR.iterdir()):
        print("Model already installed in project-local folder.")
        return

    # Even if a model exists in AppData, we (re)install it here to local folder
    print(f"Installing {src}→{tgt} into {PACK_DIR} ...")
    pkgs = argos_pkg.get_available_packages()
    pkg = next((p for p in pkgs if p.from_code == src and p.to_code == tgt), None)
    if not pkg:
        raise RuntimeError(f"No matching Argos package for {src}->{tgt}")

    path = pkg.download()
    argos_pkg.install_from_path(path)

    if not any(PACK_DIR.iterdir()):
        raise RuntimeError(
            "Install reported success but folder is still empty. "
            "Double-check that this script is the one you're running."
        )
    print("Installed to:", PACK_DIR)

def quick_test(src="en", tgt="es"):
    langs = argos_tx.get_installed_languages()
    from_lang = next((l for l in langs if getattr(l, "code", None) == src), None)
    to_lang = next((l for l in langs if getattr(l, "code", None) == tgt), None)
    if not (from_lang and to_lang):
        print("Test skipped (languages not visible).")
        return
    tr = from_lang.get_translation(to_lang)
    text = input("Enter text to translate: ").strip()
    print(tr.translate(text))

def record_test():
    recognizer = sr.Recognizer()
    mic = sr.Microphone()  # optional: sr.Microphone(device_index=...) to choose a device

    print("Ready. Hold Enter to speak; press Esc to quit.")
    while True:
        # You can cap each recording with max_seconds, e.g., max_seconds=15
        result = recognize_speech_hold(recognizer, mic, hold_key="enter", quit_key="esc", max_seconds=None)

        if result is None:
            print("Exiting.")
            break

        if not result:
            # Either no audio or recognition failed; loop again
            continue

        # Do whatever you want with the text (e.g., translate, print, etc.)
        print("Text:", result)


if __name__ == "__main__":
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    src = input("Enter source language code (e.g. en): ").strip().lower()
    tgt = input("Enter target language code (e.g. zh): ").strip().lower()
    print(model_installed(src, tgt))
    install(src, tgt)
    quick_test(src, tgt)

    record_test()