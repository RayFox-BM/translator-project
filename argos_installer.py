# argos_installer.py
from __future__ import annotations

def ensure_pair(src_code: str, dst_code: str) -> bool:
    """
    Ensure Argos Translate pair src->dst is installed.
    Returns True if available after this call (already or newly installed), False otherwise.
    """
    try:
        import argostranslate.package as pkg
        import argostranslate.translate as tx
    except Exception:
        return False

    # already installed?
    try:
        langs = tx.get_installed_languages()
        s = next((l for l in langs if l.code == src_code), None)
        d = next((l for l in langs if l.code == dst_code), None)
        if s and d:
            try:
                s.get_translation(d)  # raises if not found
                return True
            except Exception:
                pass
    except Exception:
        pass

    # try install (needs internet)
    try:
        pkg.update_package_index()
        available = pkg.get_available_packages()
        to_install = next((p for p in available if p.from_code == src_code and p.to_code == dst_code), None)
        if not to_install:
            return False
        pkg.install_from_path(to_install.download())
        return True
    except Exception:
        # offline or other failure
        return False