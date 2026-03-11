#!/usr/bin/env python3
"""
Extrakce embedded JPEG náhledů z RAW souborů.
"""

import argparse
import os
import sys
import time
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

def extract_thumbnail(raw_path: Path, output_dir: Path, max_size: int = 800) -> bool:
    try:
        with rawpy.imread(str(raw_path)) as raw:
            try:
                thumb = raw.extract_thumb()
            except rawpy.LibRawNoThumbnailError:
                return False
            except Exception:
                return False

            if thumb.format == rawpy.ThumbFormat.JPEG:
                target_path = output_dir / f"{raw_path.stem}.jpg"
                with open(target_path, "wb") as f:
                    f.write(thumb.data)
                
                # Zmenšení pro AI
                if max_size:
                    with Image.open(target_path) as img:
                        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                        img.save(target_path, "JPEG", quality=85)
                return True
            return False
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Složka s RAW soubory")
    parser.add_argument("--output", "-o", required=True, help="Výstupní složka")
    parser.add_argument("--max-size", type=int, default=800)
    parser.add_argument("--recursive", "-r", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Hledám fotky v: {input_dir}")
    
    if args.recursive:
        files = []
        for ext in SUPPORTED_RAW:
            files.extend(input_dir.rglob(f"*{ext}"))
            files.extend(input_dir.rglob(f"*{ext.upper()}"))
    else:
        files = [p for p in input_dir.iterdir() if p.suffix.lower() in SUPPORTED_RAW]

    if not files:
        print("Nenalezeny žádné podporované RAW soubory.")
        return

    print(f"Nalezeno {len(files)} RAW souborů. Extrahuji náhledy...")
    
    success = 0
    for i, f in enumerate(files, 1):
        if extract_thumbnail(f, output_dir, args.max_size):
            success += 1
        if i % 10 == 0:
            print(f"  Zpracováno {i}/{len(files)}...")

    print(f"Hotovo. Extrahováno {success} náhledů do {output_dir}")

if __name__ == "__main__":
    main()
