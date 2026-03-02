#!/usr/bin/env python3
"""
Extrakce embedded JPEG náhledů z RAW souborů.

Používá rawpy k rychlé extrakci vloženého JPEG z RAW souborů
bez nutnosti renderování. Většina RAW formátů (RAF, CR2, NEF, ARW, DNG...)
obsahuje plnorozlišení JPEG náhled.

Použití:
    python extract_previews.py /cesta/k/raw --output /tmp/zps_previews
    python extract_previews.py /cesta/k/raw --max-size 1024 --output ./previews
"""

import argparse
import io
import os
import sys
import time
from pathlib import Path

try:
    import rawpy
except ImportError:
    print("Chyba: nainstaluj rawpy → pip install rawpy")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Chyba: nainstaluj Pillow → pip install Pillow")
    sys.exit(1)

# Podporované RAW formáty
RAW_EXTENSIONS = {
    ".raf",  # Fujifilm
    ".cr2", ".cr3",  # Canon
    ".nef", ".nrw",  # Nikon
    ".arw", ".srf", ".sr2",  # Sony
    ".dng",  # Adobe DNG
    ".orf",  # Olympus
    ".rw2",  # Panasonic
    ".pef",  # Pentax
    ".srw",  # Samsung
    ".x3f",  # Sigma
    ".3fr",  # Hasselblad
    ".iiq",  # Phase One
    ".rwl",  # Leica
    ".erf",  # Epson
}


def extract_preview(raw_path: Path, output_dir: Path, max_size: int = 800) -> bool:
    """
    Extrahuje embedded JPEG z RAW souboru a uloží zmenšený náhled.

    Args:
        raw_path: Cesta k RAW souboru
        output_dir: Cílový adresář pro náhledy
        max_size: Maximální rozměr (delší strana) v pixelech

    Returns:
        True pokud úspěšně extrahováno, False jinak
    """
    try:
        raw = rawpy.imread(str(raw_path))
        thumb = raw.extract_thumb()

        if thumb.format == rawpy.ThumbFormat.JPEG:
            img = Image.open(io.BytesIO(thumb.data))
        elif thumb.format == rawpy.ThumbFormat.BITMAP:
            # Některé formáty mají bitmap místo JPEG
            img = Image.fromarray(thumb.data)
        else:
            print(f"  ⚠ Neznámý formát náhledu: {raw_path.name}")
            return False

        # Zachovat poměr stran, omezit na max_size
        img.thumbnail((max_size, max_size), Image.LANCZOS)

        # Uložit jako JPEG
        output_path = output_dir / f"{raw_path.stem}.jpg"
        img.save(str(output_path), "JPEG", quality=85)

        raw.close()
        return True

    except rawpy.LibRawNoThumbnailError:
        print(f"  ⚠ Žádný náhled: {raw_path.name}")
        return False
    except rawpy.LibRawError as e:
        print(f"  ✗ Chyba rawpy: {raw_path.name} → {e}")
        return False
    except Exception as e:
        print(f"  ✗ Neočekávaná chyba: {raw_path.name} → {e}")
        return False


def find_raw_files(source_dir: Path) -> list[Path]:
    """Najde všechny RAW soubory v adresáři (nerekurzivně)."""
    files = []
    for f in sorted(source_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in RAW_EXTENSIONS:
            files.append(f)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Extrakce JPEG náhledů z RAW souborů pro AI hodnocení"
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Adresář s RAW soubory"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("/tmp/zps_previews"),
        help="Výstupní adresář pro náhledy (výchozí: /tmp/zps_previews)"
    )
    parser.add_argument(
        "--max-size", "-s",
        type=int,
        default=800,
        help="Max rozměr delší strany v px (výchozí: 800)"
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Hledat RAW soubory i v podadresářích"
    )

    args = parser.parse_args()

    if not args.source.is_dir():
        print(f"Chyba: '{args.source}' není adresář")
        sys.exit(1)

    # Najít RAW soubory
    if args.recursive:
        raw_files = sorted([
            f for f in args.source.rglob("*")
            if f.is_file() and f.suffix.lower() in RAW_EXTENSIONS
        ])
    else:
        raw_files = find_raw_files(args.source)

    if not raw_files:
        print(f"Žádné RAW soubory nenalezeny v '{args.source}'")
        sys.exit(0)

    print(f"Nalezeno {len(raw_files)} RAW souborů")
    print(f"Výstup: {args.output}")
    print(f"Max rozměr: {args.max_size}px")
    print()

    # Vytvořit výstupní adresář
    args.output.mkdir(parents=True, exist_ok=True)

    # Extrahovat náhledy
    success = 0
    failed = 0
    start = time.time()

    for i, raw_file in enumerate(raw_files, 1):
        status = f"[{i}/{len(raw_files)}]"
        if extract_preview(raw_file, args.output, args.max_size):
            print(f"  ✓ {status} {raw_file.name}")
            success += 1
        else:
            failed += 1

    elapsed = time.time() - start
    print()
    print(f"Hotovo za {elapsed:.1f}s")
    print(f"  ✓ Extrahováno: {success}")
    if failed:
        print(f"  ✗ Selhalo: {failed}")
    print(f"  Náhledy uloženy v: {args.output}")


if __name__ == "__main__":
    main()
