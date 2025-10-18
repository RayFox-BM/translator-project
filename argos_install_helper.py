#!/usr/bin/env python3
"""
Install Argos Translate language pairs for both en->tgt and tgt->en.

Usage:
  python install_argos_pairs.py
  python install_argos_pairs.py --packages-dir "C:/path/to/translator-project/argos-data"

Notes:
- Requires internet access for downloads.
- Safe to re-run; already-installed pairs are skipped.
- You can point to a custom data folder via --packages-dir (ARGOS_PACKAGES_DIR).
"""

from __future__ import annotations
import os
import sys
import argparse
from typing import Dict, Tuple, List

# ---- Your numpad mapping (used to decide which target languages to install) ----
DIGIT_TO_LANG: Dict[str, str] = {
    "0": "en", "1": "zh", "2": "es", "3": "fr", "4": "de",
    "5": "ja", "6": "pt", "7": "it", "8": "ru", "9": "ko",
}

EN = "en"

def echo(msg: str) -> None:
    print(msg, flush=True)

def warn(msg: str) -> None:
    print(f"⚠️  {msg}", flush=True)

def ok(msg: str) -> None:
    print(f"✅ {msg}", flush=True)

def fail(msg: str) -> None:
    print(f"❌ {msg}", flush=True)

def pair_exists(tx, src: str, dst: str) -> bool:
    try:
        langs = tx.get_installed_languages()
        s = next((l for l in langs if getattr(l, "code", None) == src), None)
        d = next((l for l in langs if getattr(l, "code", None) == dst), None)
        if not s or not d:
            return False
        try:
            s.get_translation(d)  # raises if not available
            return True
        except Exception:
            return False
    except Exception:
        return False

def find_package(pkg, src: str, dst: str):
    try:
        for p in pkg.get_available_packages():
            if getattr(p, "from_code", None) == src and getattr(p, "to_code", None) == dst:
                return p
    except Exception:
        pass
    return None

def install_pair(pkg, src: str, dst: str) -> Tuple[bool, str]:
    """Download and install a single pair. Returns (success, message)."""
    p = find_package(pkg, src, dst)
    if not p:
        return (False, f"No package found for {src}->{dst} in the Argos index.")
    try:
        path = p.download()  # downloads .argosmodel
        pkg.install_from_path(path)
        return (True, f"Installed {src}->{dst}")
    except Exception as e:
        return (False, f"Install failed for {src}->{dst}: {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--packages-dir",
        help="Custom directory to store Argos models (sets ARGOS_PACKAGES_DIR).",
        default=None,
    )
    args = ap.parse_args()

    if args.packages_dir:
        os.environ["ARGOS_PACKAGES_DIR"] = args.packages_dir
        echo(f"📦 Using ARGOS_PACKAGES_DIR = {os.environ['ARGOS_PACKAGES_DIR']}")
    else:
        echo("📦 Using default Argos data directory. (Use --packages-dir to override)")

    # Import Argos
    try:
        import argostranslate.translate as tx
        import argostranslate.package as pkg
    except Exception as e:
        fail("Argos Translate is not installed.")
        echo("👉 Install it first:  pip install argostranslate")
        sys.exit(1)

    # Build set of target languages (exclude 'en' itself for tgt list)
    targets = sorted({code for code in DIGIT_TO_LANG.values() if code != EN})

    echo("\n🔧 Preparing to install the following pairs:")
    for tgt in targets:
        echo(f"   - {EN} → {tgt}")
        echo(f"   - {tgt} → {EN}")

    # Update package index
    echo("\n🌐 Updating Argos package index...")
    try:
        pkg.update_package_index()
        ok("Package index updated.")
    except Exception as e:
        warn(f"Could not update index: {e}\nWill proceed with whatever is cached.")

    # Walk through pairs and install if missing
    installed: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []

    def handle_pair(src: str, dst: str):
        pair_label = f"{src}->{dst}"
        if pair_exists(tx, src, dst):
            skipped.append(pair_label)
            ok(f"Already installed: {pair_label}")
            return
        echo(f"⬇️  Installing: {pair_label} ...")
        success, msg = install_pair(pkg, src, dst)
        if success:
            installed.append(pair_label)
            ok(msg)
        else:
            failed.append(pair_label)
            fail(msg)

    for tgt in targets:
        handle_pair(EN, tgt)
        handle_pair(tgt, EN)

    # Summary
    echo("\n==================== SUMMARY ====================")
    echo(f"✅ Installed: {len(installed)}")
    if installed:
        for p in installed:
            echo(f"   • {p}")

    echo(f"\n⏭  Skipped (already installed): {len(skipped)}")
    if skipped:
        for p in skipped:
            echo(f"   • {p}")

    echo(f"\n❌ Failed: {len(failed)}")
    if failed:
        for p in failed:
            echo(f"   • {p}")

    echo("\n🧪 Verify with:")
    echo("   argos-translate --list-installed")
    echo("   # or")
    echo("   python -m argostranslate.cli --list-installed")
    echo("\nIf you set a custom directory, keep it for your app:")
    echo("   os.environ['ARGOS_PACKAGES_DIR'] = '<your path>'")
    echo("=================================================\n")

if __name__ == "__main__":
    main()