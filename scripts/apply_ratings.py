#!/usr/bin/env python3
"""
Aplikace hodnocení z ratings.json do ZPS X katalogu a XMP sidecar souborů.

Schéma ZPS X katalogu (index.catalogue-zps = SQLite):
  - CatItemBasic: CUID (PK), CIB_OriginalUniPath, CIB_NormalizedUniPath
  - CatItemMetadata: CUID (PK/FK), CIM_DisplayNameWithExt, CIM_DataRating (hvězdičky)

Hodnocení se zapisuje do:
  1. CatItemMetadata.CIM_DataRating (katalog ZPS X)
  2. XMP sidecar souborů vedle originálních fotek (xmp:Rating)

ZPS X čte hodnocení primárně z metadat souborů (XMP), katalog slouží jen jako cache.
Proto je zápis do XMP sidecar souborů nezbytný, aby se hvězdičky zobrazily.

Použití:
    python scripts/apply_ratings.py ratings.json
    python scripts/apply_ratings.py ratings.json --catalog "C:\\Users\\...\\ZPSCatalog\\index.catalogue-zps"
    python scripts/apply_ratings.py ratings.json --dry-run
"""

import argparse
import json
import re
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

# Výchozí cesta ke katalogu
DEFAULT_CATALOG = (
    Path.home()
    / "AppData" / "Local" / "Zoner" / "ZPS X" / "ZPSCatalog"
    / "index.catalogue-zps"
)


def load_ratings(path: Path) -> dict[str, int]:
    """Načte ratings.json, vrátí {filename_bez_přípony: hodnocení}."""
    try:
        # utf-8-sig toleruje BOM, který často přidá Windows PowerShell
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"✗ Neplatný JSON v souboru {path}: {e}")
        sys.exit(1)

    # Odfiltrovat komentáře
    ratings = {k: v for k, v in data.items() if not k.startswith("_")}

    for filename, rating in ratings.items():
        if not isinstance(rating, int) or not 1 <= rating <= 5:
            print(f"✗ Neplatné hodnocení: {filename} = {rating} (musí být 1–5)")
            sys.exit(1)

    return ratings


def print_summary(ratings: dict[str, int]):
    """Zobrazí přehled hodnocení."""
    counts = Counter(ratings.values())
    total = len(ratings)

    print(f"Hodnocení k aplikaci: {total} fotek\n")
    for stars in range(5, 0, -1):
        count = counts.get(stars, 0)
        bar = "█" * count
        pct = (count / total * 100) if total else 0
        print(f"  {stars}⭐  {count:3d} ({pct:4.1f}%)  {bar}")
    print()


XMP_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:xmp="http://ns.adobe.com/xap/1.0/"
      xmp:Rating="{rating}"/>
  </rdf:RDF>
</x:xmpmeta>
"""


def write_xmp_rating(file_path: Path, rating: int, dry_run: bool = False) -> bool:
    """Zapíše nebo aktualizuje xmp:Rating v XMP sidecar souboru."""
    xmp_path = file_path.with_suffix(".xmp")

    try:
        if xmp_path.exists():
            content = xmp_path.read_text(encoding="utf-8")

            # Aktualizovat existující xmp:Rating
            new_content, count = re.subn(
                r'(xmp:Rating=")[^"]*(")',
                rf"\g<1>{rating}\2",
                content,
            )

            if count == 0:
                # Rating neexistuje — přidat do prvního rdf:Description
                if "xmlns:xmp=" not in content:
                    new_content = re.sub(
                        r"(<rdf:Description\b)",
                        r'\1 xmlns:xmp="http://ns.adobe.com/xap/1.0/"',
                        content,
                        count=1,
                    )
                else:
                    new_content = content
                new_content = re.sub(
                    r"(<rdf:Description\b[^/>]*)",
                    rf'\1\n      xmp:Rating="{rating}"',
                    new_content,
                    count=1,
                )

            if not dry_run:
                xmp_path.write_text(new_content, encoding="utf-8")
        else:
            if not dry_run:
                xmp_path.write_text(
                    XMP_TEMPLATE.format(rating=rating), encoding="utf-8"
                )

        return True
    except OSError as e:
        print(f"  ⚠ XMP chyba pro {file_path.name}: {e}")
        return False


def apply_ratings(
    ratings: dict[str, int],
    catalog_path: Path,
    dry_run: bool = False,
):
    """
    Zapíše hodnocení do ZPS X katalogu a XMP sidecar souborů.

    Párování: ratings.json obsahuje názvy bez přípony (např. "DSCF3987").
    V katalogu hledáme CIM_DisplayNameWithExt LIKE 'DSCF3987.%'
    """
    conn = sqlite3.connect(str(catalog_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ověření, že tabulky existují
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
        "('CatItemMetadata', 'CatItemBasic')"
    )
    tables = {row["name"] for row in cur.fetchall()}
    if "CatItemMetadata" not in tables:
        print("✗ Tabulka CatItemMetadata nenalezena — špatný katalog?")
        conn.close()
        sys.exit(1)

    has_basic = "CatItemBasic" in tables

    updated = 0
    not_found = 0
    unchanged = 0
    xmp_written = 0
    xmp_failed = 0

    for filename, new_rating in ratings.items():
        # Hledání fotky podle názvu (bez přípony → LIKE pattern)
        # Podporuje i zadání s příponou ("DSCF3987.RAF")
        if "." in filename:
            pattern = filename
        else:
            pattern = f"{filename}.%"

        if has_basic:
            cur.execute(
                """
                SELECT m.CUID, m.CIM_DisplayNameWithExt, m.CIM_DataRating,
                       b.CIB_OriginalUniPath
                FROM CatItemMetadata m
                LEFT JOIN CatItemBasic b ON m.CUID = b.CUID
                WHERE m.CIM_DisplayNameWithExt LIKE ?
                """,
                (pattern,),
            )
        else:
            cur.execute(
                """
                SELECT m.CUID, m.CIM_DisplayNameWithExt, m.CIM_DataRating,
                       NULL AS CIB_OriginalUniPath
                FROM CatItemMetadata m
                WHERE m.CIM_DisplayNameWithExt LIKE ?
                """,
                (pattern,),
            )
        rows = cur.fetchall()

        if not rows:
            print(f"  ⚠ Nenalezeno: {filename}")
            not_found += 1
            continue

        for row in rows:
            cuid = row["CUID"]
            current_name = row["CIM_DisplayNameWithExt"]
            current_rating = row["CIM_DataRating"]
            original_path = row["CIB_OriginalUniPath"]

            if current_rating == new_rating:
                print(f"  – {current_name} již má {new_rating}⭐, přeskakuji")
                unchanged += 1
                continue

            old_str = f"{current_rating}⭐" if current_rating else "bez hodnocení"

            if dry_run:
                print(f"  [DRY] {current_name}: {old_str} → {new_rating}⭐")
            else:
                cur.execute(
                    "UPDATE CatItemMetadata SET CIM_DataRating = ? WHERE CUID = ?",
                    (new_rating, cuid),
                )
                print(f"  ✓ {current_name}: {old_str} → {new_rating}⭐")

            # Zapsat XMP sidecar vedle originálního souboru
            if original_path:
                file_path = Path(original_path)
                if write_xmp_rating(file_path, new_rating, dry_run):
                    xmp_path = file_path.with_suffix(".xmp")
                    if dry_run:
                        print(f"    [DRY] XMP → {xmp_path}")
                    else:
                        print(f"    XMP → {xmp_path}")
                    xmp_written += 1
                else:
                    xmp_failed += 1
            else:
                print(f"    ⚠ Cesta k souboru nenalezena, XMP nevytvořen")
                xmp_failed += 1

            updated += 1

    if not dry_run:
        conn.commit()

    conn.close()

    print(f"\nVýsledek:")
    print(f"  ✓ Aktualizováno: {updated}")
    print(f"  – Beze změny:    {unchanged}")
    if not_found:
        print(f"  ⚠ Nenalezeno:    {not_found}")
    print(f"  XMP zapsáno:     {xmp_written}")
    if xmp_failed:
        print(f"  XMP selhalo:     {xmp_failed}")

    if xmp_written and not dry_run:
        print(
            "\n💡 V ZPS X spusť Aktualizaci metadat (Ctrl+Shift+M)"
            " pro načtení hodnocení z XMP souborů."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Aplikace AI hodnocení do ZPS X katalogu"
    )
    parser.add_argument("ratings", type=Path, help="Cesta k ratings.json")
    parser.add_argument(
        "--catalog", "-c",
        type=Path,
        default=DEFAULT_CATALOG,
        help=f"Cesta ke katalogu (výchozí: {DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Jen zobrazit změny, nic nezapisovat",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Nevytvářet zálohu katalogu",
    )

    args = parser.parse_args()

    if not args.ratings.exists():
        print(f"✗ Soubor neexistuje: {args.ratings}")
        sys.exit(1)

    if not args.catalog.exists():
        print(f"✗ Katalog neexistuje: {args.catalog}")
        print(f"  Zkus zadat cestu přes --catalog")
        sys.exit(1)

    # Načíst hodnocení
    ratings = load_ratings(args.ratings)
    print_summary(ratings)

    # Záloha
    if not args.no_backup and not args.dry_run:
        backup = args.catalog.with_suffix(".catalogue-zps.bak")
        shutil.copy2(args.catalog, backup)
        print(f"Záloha: {backup}\n")

    if args.dry_run:
        print("[DRY RUN — žádné změny nebudou provedeny]\n")

    # ⚠️ DŮLEŽITÉ: ZPS X musí být ZAVŘENÝ při zápisu do katalogu!
    if not args.dry_run:
        print("⚠️  Ujisti se, že Zoner Photo Studio X je ZAVŘENÝ!\n")

    apply_ratings(ratings, args.catalog, args.dry_run)


if __name__ == "__main__":
    main()
