import os
from pathlib import Path

# Force Argos to use your local model directory
PROJECT_ROOT = Path(__file__).resolve().parent
os.environ["ARGOS_PACKAGES_DIR"] = str(PROJECT_ROOT / "argos-data")

import argostranslate.package as argos_pkg
import argostranslate.translate as argos_tx

argos_tx.load_installed_languages()
for pkg in argos_pkg.get_installed_packages():
    print (pkg.from_code, " -> ", pkg.to_code)