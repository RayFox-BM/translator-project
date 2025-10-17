# --- Offline recorder + STT (Vosk) + offline language detect (lingua) + offline translate (Argos) ---
# Raspberry Pi friendly; records while holding LEFT mouse, quits on RIGHT/Esc.

import os
import io
import json
import time
import threading
from pathlib import Path
from typing import Optional
import re
from statistics import mean

# -------------------- Argos Translate setup --------------------
BASE_DIR = Path(__file__).resolve().parent
PACK_DIR = BASE_DIR / "argos-data"
PACK_DIR.mkdir(parents=True, exist_ok=True)
os.environ["ARGOS_PACKAGES_DIR"] = str(PACK_DIR)

import argostranslate.package as argos_pkg
import argostranslate.translate as argos_tx

# -------------------- Audio & input deps --------------------
import speech_recognition as sr

try:
    from pynput import mouse as pynput_mouse
    from pynput import keyboard as pynput_keyboard
except Exception:
    pynput_mouse = None
    pynput_keyboard = None

# -------------------- Offline language detect (lingua) --------------------
try:
    from lingua import LanguageDetectorBuilder
    _LINGUA_AVAILABLE = True
except Exception:
    _LINGUA_AVAILABLE = False

_DETECTOR = None  # lazy init


def _init_detector():
    global _DETECTOR
    if not _LINGUA_AVAILABLE:
        return None
    if _DETECTOR is None:
        _DETECTOR = (
            LanguageDetectorBuilder
            .from_all_languages()
            .with_preloaded_language_models()
            .build()
        )
    return _DETECTOR


def detect_lang_code(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    det = _init_detector()
    if det is None:
        return None
    lang = det.detect_language_of(text)
    if lang is None:
        return None
    code = getattr(getattr(lang, "iso_code_639_1", None), "name", None)
    return code.lower() if code else None


# -------------------- Argos helpers --------------------
def using_dir() -> Path:
    return Path(os.environ.get("ARGOS_PACKAGES_DIR", ""))


def model_installed(src: str, tgt: str) -> bool:
    argos_tx.load_installed_languages()
    for pkg in argos_pkg.get_installed_packages():
        if pkg.from_code == src and pkg.to_code == tgt:
            return True
    return False


def install(src="en", tgt="es"):
    """Install Argos model for src→tgt into the project-local folder."""
    print(f"Packages dir (intended): {using_dir()}")
    argos_pkg.update_package_index()

    if model_installed(src, tgt) and any(PACK_DIR.iterdir()):
        print("Model already installed in project-local folder.")
        return

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


def ensure_model(src: str, tgt: str = "en") -> None:
    if src == tgt:
        return
    if not model_installed(src, tgt) or not any(PACK_DIR.iterdir()):
        install(src, tgt)


def translate_text(src: str, tgt: str, text: str) -> str:
    argos_tx.load_installed_languages()
    langs = argos_tx.get_installed_languages()
    from_lang = next((l for l in langs if getattr(l, "code", None) == src), None)
    to_lang   = next((l for l in langs if getattr(l, "code", None) == tgt), None)
    if not (from_lang and to_lang):
        ensure_model(src, tgt)
        argos_tx.load_installed_languages()
        langs = argos_tx.get_installed_languages()
        from_lang = next((l for l in langs if getattr(l, "code", None) == src), None)
        to_lang   = next((l for l in langs if getattr(l, "code", None) == tgt), None)
        if not (from_lang and to_lang):
            return text
    tr = from_lang.get_translation(to_lang)
    return tr.translate(text)


# -------------------- Vosk (offline STT) --------------------
try:
    from vosk import Model as VoskModel, KaldiRecognizer
    _VOSK_AVAILABLE = True
except Exception:
    _VOSK_AVAILABLE = False

_VOSK_MODELS: dict[str, VoskModel] = {}


def load_vosk_model(lang_code: str, model_dir_map: dict[str, str]) -> Optional[VoskModel]:
    """
    lang_code: 'zh', 'ja', 'en', etc.
    """
    if not _VOSK_AVAILABLE:
        return None
    if lang_code in _VOSK_MODELS:
        return _VOSK_MODELS[lang_code]
    path = model_dir_map.get(lang_code)
    if not path or not Path(path).exists():
        return None
    model = VoskModel(path)
    _VOSK_MODELS[lang_code] = model
    return model


# -------------------- CJK helpers (Kanji + Kana) --------------------
CJK_KANJI_RANGE = r"\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF"      # Han/Kanji
JPN_KANA_RANGE  = r"\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF"      # Hiragana/Katakana (+ ext)
CJK_RANGE       = CJK_KANJI_RANGE + JPN_KANA_RANGE

def _looks_cjk(text: str) -> bool:
    return bool(re.search(fr"[{CJK_RANGE}]", text))

def cjk_ratio(text: str) -> float:
    cjk = re.findall(fr"[{CJK_RANGE}]", text)
    return (len(cjk) / max(1, len(text))) if text else 0.0

def kana_ratio(text: str) -> float:
    kana = re.findall(fr"[{JPN_KANA_RANGE}]", text)
    return (len(kana) / max(1, len(text))) if text else 0.0

def compact_cjk(text: str) -> str:
    # remove spaces between consecutive CJK chars (Kanji + Kana)
    text = re.sub(fr"(?<=[{CJK_RANGE}])\s+(?=[{CJK_RANGE}])", "", text)
    # tidy spaces around common CJK punctuation and JP quotes
    text = re.sub(r"\s+([，。！？、“”‘’：；「」『』])", r"\1", text)
    text = re.sub(r"([，。！？、“”‘’：；「」『』])\s+", r"\1", text)
    return text


def _avg_conf_from_result_json(j: dict) -> float:
    words = j.get("result") or []
    confs = [w.get("conf") for w in words if isinstance(w.get("conf"), (float, int))]
    return mean(confs) if confs else 0.0


def _stream_decode_with_model(pcm16: bytes, model, sr_hz: int = 16000) -> tuple[str, float, dict]:
    rec = KaldiRecognizer(model, sr_hz)
    rec.SetWords(True)

    CHUNK_BYTES = 6400  # ~0.2s at 16kHz
    text_parts = []
    for i in range(0, len(pcm16), CHUNK_BYTES):
        chunk = pcm16[i:i+CHUNK_BYTES]
        if rec.AcceptWaveform(chunk):
            j = json.loads(rec.Result())
            seg = (j.get("text") or "").strip()
            if seg:
                text_parts.append(seg)
        else:
            _ = json.loads(rec.PartialResult())  # ignore partial text

    jfinal = json.loads(rec.FinalResult())
    final_text = (jfinal.get("text") or "").strip()
    if final_text:
        text_parts.append(final_text)

    full_text = " ".join(t for t in text_parts if t).strip()
    avg_conf = _avg_conf_from_result_json(jfinal)
    return full_text, avg_conf, jfinal


def stt_vosk_auto(audio: sr.AudioData,
                  model_map: dict[str, str],
                  debug: bool = False) -> tuple[str, str | None]:
    """
    Try all provided models and pick the best by confidence + language/script fit.
    Returns (text, lang_key) or ("", None).
    """
    if not _VOSK_AVAILABLE:
        return "", None

    pcm16 = audio.get_raw_data(convert_rate=16000, convert_width=2)

    candidates = []
    for lang_key, _ in model_map.items():
        model = load_vosk_model(lang_key, model_map)
        if not model:
            continue

        text, avg_conf, _ = _stream_decode_with_model(pcm16, model, 16000)
        if not text:
            continue

        guessed   = (detect_lang_code(text) or "")
        looks_cjk = _looks_cjk(text)
        ratio     = cjk_ratio(text)
        is_cjk_lang = lang_key in {"zh", "yue", "ja", "ko"}

        length_score = min(len(text), 200) / 200.0
        conf_score   = max(0.0, min(1.0, float(avg_conf)))

        # HARD GUARD: demote Chinese when decoded text isn't actually CJK-ish
        zh_penalty = 1.0 if (lang_key in {"zh", "yue"} and ratio < 0.20) else 0.0

        match_bonus  = 0.0
        if guessed:
            if lang_key.startswith(guessed):
                match_bonus += 0.9
            if guessed == "zh" and lang_key in {"zh", "yue"}:
                match_bonus += 0.2

        script_bonus = 0.4 if (looks_cjk and is_cjk_lang) or ((not looks_cjk) and (lang_key == "en")) else 0.0

        score = (0.6 * conf_score) + (0.15 * length_score) + match_bonus + script_bonus - zh_penalty

        candidates.append({
            "lang": lang_key,
            "text": text,
            "score": score,
            "conf": conf_score,
            "len": len(text),
            "looks_cjk": looks_cjk,
            "ratio_cjk": ratio,
            "guessed": guessed,
        })

    if not candidates:
        return "", None

    if debug:
        print("[stt_vosk_auto] candidates:")
        for c in candidates:
            print(f"  - {c['lang']}: score={c['score']:.3f} conf={c['conf']:.3f} len={c['len']} "
                  f"cjk={c['ratio_cjk']:.2f} looks_cjk={c['looks_cjk']} guessed={c['guessed']}")

    best = max(candidates, key=lambda c: c["score"])
    if debug:
        print(f"[stt_vosk_auto] picked: {best['lang']}")
    return best["text"], best["lang"]


def normalize_src_for_argos(code: str, picked_lang: Optional[str]) -> str:
    """
    Map guessed/picked language into Argos codes:
    - yue -> zh
    - zh* -> zh
    - ja  -> ja
    """
    code = (code or "").lower()
    picked = (picked_lang or "").lower()

    if picked in {"yue"} or code.startswith("yue"):
        return "zh"
    if code.startswith("zh") or picked in {"zh"}:
        return "zh"
    if code.startswith("ja") or picked in {"ja"}:
        return "ja"
    return code or "en"


# -------------------- Mouse/Keyboard controller (pynput) --------------------
class InputController:
    """
    Tracks mouse-left hold for recording, right-click or Esc to quit.
    Works via pynput listeners (X11/desktop session).
    """
    def __init__(self, use_mouse=True, use_keyboard=True):
        self.use_mouse = use_mouse and (pynput_mouse is not None)
        self.use_keyboard = use_keyboard and (pynput_keyboard is not None)

        self._holding = False
        self._quit = False

        self._mouse_listener = None
        self._key_listener = None
        self._lock = threading.Lock()

    def start(self):
        if self.use_mouse:
            self._mouse_listener = pynput_mouse.Listener(
                on_click=self._on_click
            )
            self._mouse_listener.start()
        if self.use_keyboard:
            self._key_listener = pynput_keyboard.Listener(
                on_press=self._on_key_press
            )
            self._key_listener.start()

    def stop(self):
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._key_listener:
            self._key_listener.stop()

    def _on_click(self, x, y, button, pressed):
        try:
            from pynput.mouse import Button
            if button == Button.left:
                with self._lock:
                    self._holding = bool(pressed)
            elif button == Button.right and pressed:
                with self._lock:
                    self._quit = True
        except Exception:
            pass

    def _on_key_press(self, key):
        try:
            from pynput.keyboard import Key
            if key == Key.esc:
                with self._lock:
                    self._quit = True
        except Exception:
            pass

    def is_holding(self) -> bool:
        with self._lock:
            return self._holding

    def should_quit(self) -> bool:
        with self._lock:
            return self._quit

    def clear_quit(self):
        with self._lock:
            self._quit = False


# -------------------- Recording (returns raw AudioData) --------------------
def recognize_speech_hold(
    recognizer: sr.Recognizer,
    mic: sr.Microphone,
    input_ctrl: InputController,
    max_seconds: Optional[float] = None
) -> Optional[sr.AudioData] | str:
    """
    Returns:
      AudioData = audio captured (for STT)
      ""        = capture failure / no audio
      None      = quit before recording (right-click or Esc)
    """
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("Hold LEFT mouse button to record; RIGHT mouse button or Esc to quit.")

        # Wait for hold or quit
        while True:
            if input_ctrl.should_quit():
                return None
            if input_ctrl.is_holding():
                break
            time.sleep(0.01)

        print("Recording... release LEFT button to stop.")
        audio_buf = io.BytesIO()
        start = time.time()

        stream = source.stream
        chunk_size = source.CHUNK

        while True:
            if input_ctrl.should_quit():
                print("Quit requested.")
                return None

            if not input_ctrl.is_holding():
                break

            data = stream.read(chunk_size)
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

    return audio


# -------------------- Main loop --------------------
def record_test():
    if pynput_mouse is None or pynput_keyboard is None:
        print("pynput not available; cannot capture mouse/keyboard via desktop hooks.")
        return
    if not _VOSK_AVAILABLE:
        print("Vosk not installed. pip install vosk")
        return

    recognizer = sr.Recognizer()
    mic = sr.Microphone()  # set device_index=... if needed

    input_ctrl = InputController(use_mouse=True, use_keyboard=True)
    input_ctrl.start()
    print("Ready.  (Hold LEFT mouse to speak; RIGHT/Esc to quit)")

    PROJECT_ROOT = Path(__file__).resolve().parent

    # Model folders relative to project root (adjust if your names differ)
    vosk_model_dirs = {
        "ja": str(PROJECT_ROOT / "vosk-models" / "vosk-model-small-ja-0.22"),
        "zh": str(PROJECT_ROOT / "vosk-models" / "vosk-model-small-cn-0.22"),
        "en": str(PROJECT_ROOT / "vosk-models" / "vosk-model-small-en-us-0.15"),
        # "yue": str(PROJECT_ROOT / "vosk-models" / "vosk-model-small-yue-<ver>"),  # optional Cantonese
    }

    # Sanity check: paths & load
    for key, p in vosk_model_dirs.items():
        print(f"[Vosk] Checking model for {key}: {p}")
        if not Path(p).exists():
            print(f"[Vosk][ERROR] Path does not exist: {p}")
        else:
            try:
                _ = load_vosk_model(key, vosk_model_dirs)
                print(f"[Vosk] Loaded model: {key}")
            except Exception as e:
                print(f"[Vosk][ERROR] Failed to load model {key}: {e}")

    try:
        while True:
            audio_or_none = recognize_speech_hold(
                recognizer, mic, input_ctrl, max_seconds=None
            )

            if audio_or_none is None:
                print("Exiting.")
                break
            if audio_or_none == "":
                continue

            audio: sr.AudioData = audio_or_none  # type: ignore

            # --- OFFLINE STT (Vosk auto-select best model) ---
            text, picked_lang = stt_vosk_auto(audio, vosk_model_dirs, debug=False)
            if not text:
                print("[Vosk] Could not transcribe with installed models.")
                continue

            print(f"Heard (picked={picked_lang or 'unknown'}): {text}")

            # --- OFFLINE language guess (Lingua) for routing translation ---
            code = detect_lang_code(text) or picked_lang or "en"
            print(f"[Detector] Language guess: {code}")

            # --- Compact CJK before translation for better results ---
            is_cjk_text = code.startswith("zh") or code.startswith("ja") or (picked_lang in {"zh", "yue", "ja"})
            text_for_tx = compact_cjk(text) if is_cjk_text else text

            # --- Normalize src for Argos & translate to English (offline) ---
            src_for_argos = normalize_src_for_argos(code, picked_lang)
            if src_for_argos != "en":
                try:
                    ensure_model(src_for_argos, "en")  # auto-install ja→en / zh→en if missing
                    translated = translate_text(src_for_argos, "en", text_for_tx)
                    print("→ English:", translated)
                except Exception as e:
                    print("Translate error:", e)
            else:
                print("→ English:", text_for_tx)

    finally:
        input_ctrl.stop()


# -------------------- Entry --------------------
if __name__ == "__main__":
    # Optional: preinstall common pairs once
    # install("zh", "en")
    # install("ja", "en")
    record_test()