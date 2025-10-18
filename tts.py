# tts.py
from __future__ import annotations
import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# -----------------------------
# Configurable voice preferences
# -----------------------------

try:
    from fugashi import Tagger
    _JA_TAGGER = Tagger()  # uses unidic-lite bundled dict
except Exception:
    _JA_TAGGER = None

def _ja_to_kana_mecab(text: str) -> str:
    if _JA_TAGGER is None:
        return text
    kana_chunks = []
    for token in _JA_TAGGER(text):
        # unidic-lite exposes .feature.kana or .feature.pron depending version
        kana = getattr(token.feature, "pron", None) or getattr(token.feature, "kana", None)
        kana_chunks.append(kana or token.surface)
    return "".join(kana_chunks)

try:
    from pykakasi import kakasi as _kakasi_cls
    _KAKASI = _kakasi_cls()
    _KAKASI.setMode("J", "H")  # Kanji -> Hiragana
    _KAKASI.setMode("K", "H")  # Katakana -> Hiragana (normalize)
    _KAKASI.setMode("H", "H")  # Hiragana stays Hiragana
    _JA_CONVERTER = _KAKASI.getConverter()
except Exception:
    _JA_CONVERTER = None

def _ja_to_kana(text: str) -> str:
    if _JA_TAGGER is not None:
        return _ja_to_kana_mecab(text)
    if _JA_CONVERTER is not None:
        return _JA_CONVERTER.do(text)
    return text

VOICE_HINTS: Dict[str, Dict[str, str]] = {
    "en": {"win": "Microsoft Zira",   "mac": "Samantha",  "lin": "en"},
    "zh": {"win": "Microsift Huihui", "mac": "Ting-Ting", "lin": "sit/cmn"},
    "es": {"win": "Helena",           "mac": "Monica",    "lin": "es"},
    "fr": {"win": "Hortense",         "mac": "Amelie",    "lin": "fr"},
    "de": {"win": "Hedda",            "mac": "Anna",      "lin": "de"},
    "ja": {"win": "Haruka",           "mac": "Kyoko",     "lin": "ja"},
    "pt": {"win": "Maria",            "mac": "Joana",     "lin": "pt"},
    "it": {"win": "Elsa",             "mac": "Alice",     "lin": "it"},
    "ru": {"win": "Irina",            "mac": "Milena",    "lin": "ru"},
    "ko": {"win": "Heami",            "mac": "Yuna",      "lin": "ko"},
}

SAMPLE_TEXT = {
    "en": "Hello, this is a test.",
    "zh": "你好，这是测试。",
    "es": "Hola, esto es una prueba.",
    "fr": "Bonjour, ceci est un test.",
    "de": "Hallo, dies ist ein Test.",
    "ja": "こんにちは、これはテストです。",
    "pt": "Olá, isto é um teste.",
    "it": "Ciao, questo è un test.",
    "ru": "Здравствуйте, это тест.",
    "ko": "안녕하세요, 이것은 테스트입니다.",
}

# -----------------------------
# pyttsx3 helpers
# -----------------------------
_engine = None  # lazy-initialized pyttsx3 engine

@dataclass
class VoiceInfo:
    id: str
    name: str
    languages: List[str]

def _init_engine():
    global _engine
    if _engine is None:
        import pyttsx3
        _engine = pyttsx3.init()
    return _engine

def list_pyttsx3_voices() -> List[VoiceInfo]:
    """Return all pyttsx3 voices (id, name, languages)."""
    try:
        eng = _init_engine()
        res: List[VoiceInfo] = []
        for v in eng.getProperty("voices"):
            # v.languages may be bytes like [b'\x05en_US'] or empty
            langs = []
            try:
                raw = getattr(v, "languages", []) or []
                for item in raw:
                    try:
                        s = item.decode("utf-8", errors="ignore") if isinstance(item, (bytes, bytearray)) else str(item)
                        if s:
                            langs.append(s)
                    except Exception:
                        pass
            except Exception:
                pass
            res.append(VoiceInfo(id=v.id, name=(v.name or ""), languages=langs))
        return res
    except Exception:
        return []

def _match_voice(lang: str) -> Optional[str]:
    voices = list_pyttsx3_voices()
    want_name = None
    system = platform.system()
    if system == "Windows":
        want_name = VOICE_HINTS.get(lang, {}).get("win")
    elif system == "Darwin":
        want_name = VOICE_HINTS.get(lang, {}).get("mac")
    elif system == "Linux":
        # NEW: if we have an explicit Linux voice id (e.g., 'sit/cmn'), use it
        vtag = VOICE_HINTS.get(lang, {}).get("lin")
        if vtag:
            return vtag

    # 1) name substring match (Win/Mac)
    if want_name:
        for v in voices:
            if want_name.lower() in v.name.lower():
                return v.id

    # 2) metadata language match
    for v in voices:
        for meta in v.languages:
            m = meta.lower()
            if lang.lower() in m or m.endswith(lang.lower()) or m.startswith(lang.lower()):
                return v.id

    return None

# -----------------------------
# Backends
# -----------------------------
def _backend_pyttsx3(text: str, lang: str) -> Tuple[bool, str]:
    try:
        eng = _init_engine()
        voice_id = _match_voice(lang)
        if not voice_id:
            # IMPORTANT: do NOT speak with default voice; let caller try other backends
            return False, f"pyttsx3: no matching voice for '{lang}'"
        eng.setProperty("voice", voice_id)
        eng.setProperty("rate", 120) 
        detail = f"pyttsx3 voice='{voice_id}'"
        eng.say(text)
        eng.runAndWait()
        return True, detail
    except Exception as e:
        return False, f"pyttsx3 error: {e}"

def _backend_macos_say(text: str, lang: str) -> Tuple[bool, str]:
    if platform.system() != "Darwin":
        return False, "not macOS"
    voice = VOICE_HINTS.get(lang, {}).get("mac")
    try:
        if voice:
            subprocess.run(["say", "-v", voice, text], check=True)
            return True, f"mac 'say' voice='{voice}'"
        else:
            subprocess.run(["say", text], check=True)
            return True, "mac 'say' default"
    except Exception as e:
        return False, f"mac say error: {e}"

def _backend_espeak(text: str, lang: str) -> Tuple[bool, str]:
    if platform.system() != "Linux":
        return False, "not Linux"
    vtag = VOICE_HINTS.get(lang, {}).get("lin", lang)
    try:
        subprocess.run(
            ["espeak-ng", "-v", vtag, text],
            check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True, f"espeak-ng -v {vtag}"
    except Exception as e:
        return False, f"espeak-ng error: {e}"

# -----------------------------
# Public speak() + diagnostics
# -----------------------------
def speak(text: str, lang: str = "en", also_print: bool = True) -> None:
    """Speak text in the given language with robust fallbacks and diagnostics."""
    if not text:
        return
    if lang == "ja":
        text = _ja_to_kana(text)
    if also_print:
        print(f"[SPEAK:{lang}] {text}")

    # 1) pyttsx3 on all OS (preferred if voice exists)
    ok, detail = _backend_pyttsx3(text, lang)
    if ok:
        print(f"[TTS] {detail}")
        return
    print(f"[TTS] {detail}")

    # 2) macOS 'say'
    ok, detail = _backend_macos_say(text, lang)
    if ok:
        print(f"[TTS] {detail}")
        return
    if "not macOS" not in detail:
        print(f"[TTS] {detail}")

    # 3) Linux espeak-ng
    ok, detail = _backend_espeak(text, lang)
    if ok:
        print(f"[TTS] {detail}")
        return
    if "not Linux" not in detail:
        print(f"[TTS] {detail}")

    print("[TTS] All backends failed.")

def print_voice_table() -> None:
    """Pretty-print all pyttsx3 voices available on this machine."""
    voices = list_pyttsx3_voices()
    if not voices:
        print("No pyttsx3 voices found (pyttsx3 not installed or engine init failed).")
        return
    print("\n=== pyttsx3 Voices ===")
    for v in voices:
        langs = ", ".join(v.languages) if v.languages else "-"
        print(f"- {v.name} | id='{v.id}' | langs=[{langs}]")
    print("======================\n")

def test_all_languages(order: Optional[List[str]] = None) -> None:
    """Speak one short sample per language; print pass/fail + backend used."""
    langs = order or list(VOICE_HINTS.keys())
    print_voice_table()
    print("=== TTS Test (one sample per language) ===")
    for code in langs:
        text = SAMPLE_TEXT.get(code, "Test.")
        print(f"\n[{code}] {text}")
        speak(text, code, also_print=False)
    print("\n=== TTS Test Complete ===")