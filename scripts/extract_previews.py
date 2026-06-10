#!/usr/bin/env python3
"""
Extrakce embedded JPEG náhledů z RAW souborů.
"""

import argparse
import io
import sys
from pathlib import Path

# Pokus o import rawpy s jasnou chybou
try:
    import rawpy
except ImportError:
    print("CHYBA: Knihovna 'rawpy' není nainstalována. Spusťte: pip install rawpy", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("CHYBA: Knihovna 'Pillow' není nainstalována. Spusťte: pip install Pillow", file=sys.stderr)
    sys.exit(1)

SUPPORTED_RAW = {".raf", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".srw"}


def find_raw_files(input_dir: Path, recursive: bool, exclude_dir: Path) -> list[Path]:
    """Najde RAW soubory bez duplicit (přípony porovnává case-insensitive)."""
    candidates = input_dir.rglob("*") if recursive else input_dir.iterdir()
    files = []
    for p in candidates:
        if not p.is_file() or p.suffix.lower() not in SUPPORTED_RAW:
            continue
        # Nezanořovat se do výstupní složky s náhledy
        if exclude_dir == p.parent or exclude_dir in p.parents:
            continue
        files.append(p)
    return sorted(files)


def extract_thumbnail(raw_path: Path, output_dir: Path, max_size: int = 800) -> bool:
    target_path = output_dir / f"{raw_path.stem}.jpg"
    try:
        with rawpy.imread(str(raw_path)) as raw:
            try:
                thumb = raw.extract_thumb()
            except Exception:
                return False
            if thumb.format != rawpy.ThumbFormat.JPEG:
                return False
            data = thumb.data

        if max_size:
            # Zmenšení pro AI — rovnou z paměti, jediný zápis na disk
            with Image.open(io.BytesIO(data)) as img:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                img.save(target_path, "JPEG", quality=85)
        else:
            target_path.write_bytes(data)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Složka s RAW soubory")
    parser.add_argument("--output", "-o", required=True, help="Výstupní složka")
    parser.add_argument("--max-size", type=int, default=800)
    parser.add_argument("--recursive", "-r", action="store_true")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Extrahovat znovu i existující náhledy")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Hledám fotky v: {input_dir}")
    files = find_raw_files(input_dir, args.recursive, output_dir)

    if not files:
        print("Nenalezeny žádné podporované RAW soubory.")
        return

    print(f"Nalezeno {len(files)} RAW souborů. Extrahuji náhledy...")

    success = 0
    skipped = 0
    for i, f in enumerate(files, 1):
        if not args.force and (output_dir / f"{f.stem}.jpg").exists():
            skipped += 1
        elif extract_thumbnail(f, output_dir, args.max_size):
            success += 1
        if i % 10 == 0:
            print(f"  Zpracováno {i}/{len(files)}...")

    print(f"Hotovo. Extrahováno {success} náhledů do {output_dir}")
    if skipped:
        print(f"Přeskočeno {skipped} již existujících náhledů (vynutit lze pomocí --force).")


if __name__ == "__main__":
    main()
