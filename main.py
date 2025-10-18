# main.py (debug + language-aware TTS)
from __future__ import annotations
import json, time

import os
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent
os.environ["ARGOS_PACKAGES_DIR"] = str(PROJECT_ROOT / "argos-data")


# ---- local modules ----
import platform
USE_X = bool(os.environ.get("DISPLAY"))

if platform.system() == "Linux" and not USE_X:
    # headless: use evdev backend
    from keyboard_input_evdev import KeyboardInput, KeyboardCallbacks
else:
    # desktop: use pynput backend
    from keyboard_input import KeyboardInput, KeyboardCallbacks

from microphone_record import MicrophoneRecorder, MicConfig
from argos_translator import translate_text
# If installing Argos packages manually, you can disable ensure_pair below.
from tts import speak  # language-aware TTS

# ---------- config ----------
PROJECT_ROOT = Path(__file__).resolve().parent

VOSK_MODELS = {
    "en": PROJECT_ROOT / "vosk-models" / "vosk-model-small-en-us-0.15",
    "zh": PROJECT_ROOT / "vosk-models" / "vosk-model-small-cn-0.22",
    "es": PROJECT_ROOT / "vosk-models" / "vosk-model-small-es-0.42",
    "fr": PROJECT_ROOT / "vosk-models" / "vosk-model-small-fr-0.22",
    "ru": PROJECT_ROOT / "vosk-models" / "vosk-model-ru-0.42",
    "de": PROJECT_ROOT / "vosk-models" / "vosk-model-small-de-0.15",
    "ja": PROJECT_ROOT / "vosk-models" / "vosk-model-small-ja-0.22",
    "it": PROJECT_ROOT / "vosk-models" / "vosk-model-small-it-0.22",
    "pt": PROJECT_ROOT / "vosk-models" / "vosk-model-small-pt-0.3",
    "ko": PROJECT_ROOT / "vosk-models" / "vosk-model-small-ko-0.22",
    # Add more as needed
}

DIGIT_TO_LANG = {
    "0": "en", "1": "zh", "2": "es", "3": "fr", "4": "de",
    "5": "ja", "6": "pt", "7": "it", "8": "ru", "9": "ko",
}

USE_ENSURE_ARGOS_PAIR = False

# ---------- optional deps ----------
try:
    import vosk
    _VOSK = True
except Exception:
    _VOSK = False

try:
    import speech_recognition as sr
    _SR = True
except Exception:
    _SR = False

try:
    from langdetect import detect as lang_detect
    _LANGDETECT = True
except Exception:
    _LANGDETECT = False

# ---------- STT engine ----------
class STT:
    def __init__(self):
        self.rate = 16000
        self._rec = None
        self._current_lang: str | None = None

    def _load_vosk(self, lang: str) -> bool:
        path = VOSK_MODELS.get(lang)
        if not path or not path.exists():
            self._rec = None
            self._current_lang = None
            print(f"[STT] No Vosk model for {lang}")
            return False
        try:
            model = vosk.Model(str(path))
            self._rec = vosk.KaldiRecognizer(model, self.rate)
            self._current_lang = lang
            print(f"[STT] Loaded Vosk model for {lang}")
            return True
        except Exception as e:
            print(f"[STT] Error loading Vosk model: {e}")
            self._rec = None
            self._current_lang = None
            return False

    def transcribe(self, audio_16k, source_lang: str | None) -> str:
        # Use Vosk when we have a model for selected source_lang
        if _VOSK and source_lang and self._current_lang != source_lang:
            self._load_vosk(source_lang)

        if self._rec is not None:
            self._rec.Reset()
            self._rec.AcceptWaveform(audio_16k.tobytes())
            try:
                res = json.loads(self._rec.Result())
                text = (res.get("text") or "").strip()
                print(f"[STT] Vosk transcription ({source_lang}): {text}")
                return text
            except Exception as e:
                print(f"[STT] Vosk parse error: {e}")

# ---------- controller state ----------
class State:
    def __init__(self):
        self.mode = "target"      # "target" or "source"
        self.target = "en"
        self.source: str | None = "en"  # None = auto-detect
        self._zero_times: list[float] = []

    def toggle_mode(self):
        self.mode = "source" if self.mode == "target" else "target"
        speak(f"{self.mode.capitalize()} selection mode.", "en")

    def feed_digit(self, d: str):
        now = time.time()
        if d == "0":
            self._zero_times = [t for t in self._zero_times if now - t < 1.0]
            self._zero_times.append(now)
            if len(self._zero_times) >= 3:
                self._zero_times.clear()
                self.source = None
                self.target = "en"
                speak("Quick profile: auto detect to English.", "en")
                print("[STATE] Quick profile reset (auto→en)")
                return
        else:
            self._zero_times.clear()

        lang = DIGIT_TO_LANG.get(d)
        if not lang:
            print(f"[STATE] Unknown digit {d}")
            return
        if self.mode == "target":
            self.target = lang
            speak(f"Target set to {lang}.", "en")
            print(f"[STATE] Target language = {lang}")
        else:
            self.source = lang
            speak(f"Microphone recognition set to {lang}.", "en")
            print(f"[STATE] Source language = {lang}")

# ---------- wire everything ----------
def main():
    stt = STT()
    mic = MicrophoneRecorder(MicConfig(device=4))
    state = State()

    def on_digit(d):
        print(f"[EVENT] Digit pressed: {d}")
        state.feed_digit(d)

    def on_toggle_mode():
        print("[EVENT] Toggle mode (dot tap)")
        state.toggle_mode()

    def on_ptt_down():
        print("[EVENT] PTT DOWN — starting mic")
        mic.start()
        speak("Listening.", "en")

    def on_ptt_up():
        print("[EVENT] PTT UP — stopping mic")
        audio = mic.stop()
        if audio.size == 0:
            speak("No audio captured.", "en")
            print("[DEBUG] No audio in buffer.")
            return

        # STT → text
        src_lang = state.source  # None => auto after STT
        print(f"[DEBUG] Source lang: {src_lang}, Target: {state.target}")
        text = stt.transcribe(audio, source_lang=src_lang or "en")
        if not text:
            speak("I did not catch that.", "en")
            print("[DEBUG] Empty transcription.")
            return

        # Auto-detect (text) if requested
        if src_lang is None:
            if _LANGDETECT:
                try:
                    src_lang = lang_detect(text) or "en"
                except Exception:
                    src_lang = "en"
            else:
                src_lang = "en"
            print(f"[DEBUG] Auto-detected source = {src_lang}")

        dst_lang = state.target

        # Ensure Argos pair (optional; you said you'll install manually)
        if USE_ENSURE_ARGOS_PAIR:
            print(f"[DEBUG] Ensuring Argos pair: {src_lang}->{dst_lang}")
            ensure_pair(src_lang, dst_lang)

        # Translate (or pass-through)
        out = text if src_lang == dst_lang else translate_text(src_lang, dst_lang, text)
        print(f"[TRANSLATION] {src_lang}->{dst_lang}: {out}")
        speak(out, dst_lang)  # speak with TARGET language voice

    def on_exit():
        print("[EVENT] ESC pressed — exiting")
        speak("Goodbye.", "en")

    kb_in = KeyboardInput(KeyboardCallbacks(
        on_digit=on_digit,
        on_ptt_down=on_ptt_down,
        on_ptt_up=on_ptt_up,
        on_toggle_mode=on_toggle_mode,
        on_exit=on_exit,
    ))

    speak("Translator ready. Tap dot to switch source or target. Hold backspace to speak. Digits choose language.", "en")
    print("[SYSTEM] Translator ready. Waiting for keyboard input...")

    kb_in.start()
    kb_in.join()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[SYSTEM] Interrupted by user.")