# argos_translator.py
from __future__ import annotations
from functools import lru_cache
from typing import Optional, Tuple, List
import os
from pathlib import Path

# ----- FORCE ARGOS DATA DIR (your path) -----
# If you ever want to override at runtime, set the env var before import and
# this code will respect it:
#   $env:ARGOS_PACKAGES_DIR="C:\path\to\argos-data"   (PowerShell)
#   export ARGOS_PACKAGES_DIR="/path/to/argos-data"   (bash)
DEFAULT_ARGOS_DIR = Path(r"C:\Users\owobo\Documents\translator-project\argos-data")
if not os.environ.get("ARGOS_PACKAGES_DIR"):
    os.environ["ARGOS_PACKAGES_DIR"] = str(DEFAULT_ARGOS_DIR)

BRIDGE_LANG = "en"  # bridge language for 2-hop translation

def _debug(msg: str) -> None:
    print(f"[Argos] {msg}")

def _get_env_packages_dir() -> Optional[str]:
    return os.environ.get("ARGOS_PACKAGES_DIR")

def _load_modules():
    # Print where we're pointing *before* importing Argos
    argos_dir = _get_env_packages_dir()
    if argos_dir:
        _debug(f"ARGOS_PACKAGES_DIR = {argos_dir}")
        if not Path(argos_dir).exists():
            _debug("WARNING: directory does not exist.")
    try:
        import argostranslate.translate as tx
        import argostranslate.package as pkg
        return tx, pkg
    except Exception as e:
        _debug(f"Argos Translate not importable: {e}")
        return None, None

def _installed_langs(tx) -> List[str]:
    try:
        langs = tx.get_installed_languages()
        return sorted({l.code for l in langs})
    except Exception as e:
        _debug(f"Could not list installed languages: {e}")
        return []

def _get_lang_obj(tx, code: str):
    try:
        for l in tx.get_installed_languages():
            if getattr(l, "code", None) == code:
                return l
    except Exception:
        pass
    return None

def _pair_exists(tx, src: str, dst: str) -> bool:
    s = _get_lang_obj(tx, src)
    d = _get_lang_obj(tx, dst)
    if not s or not d:
        return False
    try:
        t = s.get_translation(d)  # raises if missing
        return t is not None
    except Exception:
        return False

@lru_cache(maxsize=256)
def _translate_direct_cached(src: str, dst: str, text: str) -> str:
    tx, _ = _load_modules()
    if not tx:
        return text
    s = _get_lang_obj(tx, src)
    d = _get_lang_obj(tx, dst)
    if not s or not d:
        return text
    try:
        t = s.get_translation(d)
    except Exception:
        return text
    try:
        return t.translate(text)
    except Exception:
        return text

def _translate_direct(src: str, dst: str, text: str) -> Tuple[bool, str]:
    out = _translate_direct_cached(src, dst, text)
    success = (out.strip() != "" and out != text) or (src == dst and out == text)
    return success, out

def _can_bridge(tx, src: str, dst: str) -> bool:
    return (
        src != BRIDGE_LANG and dst != BRIDGE_LANG
        and _pair_exists(tx, src, BRIDGE_LANG)
        and _pair_exists(tx, BRIDGE_LANG, dst)
    )

def translate_text(src_code: str, dst_code: str, text: str) -> str:
    """
    Translate text from src_code → dst_code using Argos Translate.
    - Tries direct src→dst if installed.
    - Falls back to src→en→dst if both legs exist.
    Returns the original text if translation isn't possible.
    """
    if not text or not text.strip():
        return text

    tx, _ = _load_modules()
    if not tx:
        return text

    # Show installed codes each call (helps diagnose)
    codes = _installed_langs(tx)
    _debug(f"Installed languages: {', '.join(codes) if codes else '(none)'}")

    # 1) Direct path
    if _pair_exists(tx, src_code, dst_code):
        _debug(f"Using direct pair {src_code}->{dst_code}")
        ok, out = _translate_direct(src_code, dst_code, text)
        if ok:
            return out
        _debug("Direct translation returned empty/unchanged; will try bridge if possible.")

    # 2) Bridge path (src→en→dst)
    if _can_bridge(tx, src_code, dst_code):
        _debug(f"Using bridge via {BRIDGE_LANG}: {src_code}->{BRIDGE_LANG}->{dst_code}")
        ok1, mid = _translate_direct(src_code, BRIDGE_LANG, text)
        if not ok1 or not mid.strip():
            _debug(f"Bridge step failed: {src_code}->{BRIDGE_LANG}")
            return text
        ok2, out = _translate_direct(BRIDGE_LANG, dst_code, mid)
        if ok2:
            return out
        _debug(f"Bridge step failed: {BRIDGE_LANG}->{dst_code}")
        return text

    # 3) Nothing available
    _debug(f"No available pair for {src_code}->{dst_code} and no valid bridge via {BRIDGE_LANG}.")
    return text

# ---------- Optional: quick CLI for testing ----------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: python argos_translator.py '<text>' <src_code> <dst_code>")
        print("Example: python argos_translator.py '你好世界' zh en")
        sys.exit(1)
    txt = sys.argv[1]
    src = sys.argv[2]
    dst = sys.argv[3]
    res = translate_text(src, dst, txt)
    print(f"\n[RESULT] {src}->{dst}: {res}")