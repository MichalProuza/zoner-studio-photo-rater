#!/usr/bin/env python3
"""
main.py — hlavní vstupní bod pro zabalený EXE (PyInstaller).

Bez argumentů spustí grafické rozhraní (GUI).

Interní přepínač ``--_mode=<name>`` slouží k tomu, aby GUI mohlo spouštět
dílčí skripty jako subprocesy pomocí stejného exe souboru (místo volání
``python skript.py``). Tento přepínač není určen pro přímé použití uživatelem.

Podporované režimy:
    extract_previews  — extrakce JPEG náhledů z RAW souborů
    rate_with_ai      — hodnocení pomocí Claude AI
    apply_ratings     — zápis hodnocení do XMP sidecar souborů
"""

import sys


def _dispatch_mode(mode: str) -> None:
    if mode == "extract_previews":
        from scripts.extract_previews import main
        main()
    elif mode == "rate_with_ai":
        from scripts.rate_with_ai import main
        main()
    elif mode == "apply_ratings":
        from scripts.apply_ratings import main
        main()
    else:
        print(f"Neznámý interní režim: {mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--_mode="):
        mode = sys.argv[1].split("=", 1)[1]
        # Odstraň přepínač --_mode ze sys.argv, aby argparse v dílčích
        # skriptech viděl jen své vlastní argumenty.
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        _dispatch_mode(mode)
    else:
        from scripts.run_gui import App
        app = App()
        app.mainloop()
