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
    # Zápis do katalogu + XMP (normální)
    python scripts/apply_ratings.py ratings.json
    python scripts/apply_ratings.py ratings.json --catalog "C:\\Users\\...\\ZPSCatalog\\index.catalogue-zps"
    python scripts/apply_ratings.py ratings.json --dry-run

    # Zápis jen do XMP metadat (bez katalogu)
    python scripts/apply_ratings.py ratings.json --xmp-only --source-dir "C:\\path\\to\\photos"
    python scripts/apply_ratings.py ratings.json --xmp-only --source-dir "C:\\path\\to\\photos" --dry-run
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


def _read_xmp_rating(content: str) -> int | None:
    """Přečte existující xmp:Rating z obsahu XMP souboru. Vrátí None pokud neexistuje."""
    # Atribut: xmp:Rating="4"
    m = re.search(r'xmp:Rating="(\d+)"', content)
    if m:
        return int(m.group(1))
    # Element: <xmp:Rating>4</xmp:Rating>
    m = re.search(r"<xmp:Rating>(\d+)</xmp:Rating>", content)
    if m:
        return int(m.group(1))
    return None


def write_xmp_rating(file_path: Path, rating: int, dry_run: bool = False) -> tuple[bool, str]:
    """Zapíše nebo aktualizuje xmp:Rating v XMP sidecar souboru.

    Pokud XMP soubor existuje a již obsahuje hodnocení, přeskočí zápis
    (zachová ruční hodnocení uživatele). Pokud XMP existuje bez hodnocení,
    doplní jej. Pokud neexistuje, vytvoří nový.

    Returns:
        (success, mode) kde mode je "updated", "created", "skipped" nebo "error".
    """
    xmp_path = file_path.with_suffix(".xmp")

    try:
        if xmp_path.exists():
            # Načíst existující XMP – toleruje BOM
            content = xmp_path.read_text(encoding="utf-8-sig")

            # Pokud už XMP obsahuje hodnocení, nepřepisovat
            existing = _read_xmp_rating(content)
            if existing is not None:
                return True, "skipped"

            # Rating neexistuje — přidat do prvního rdf:Description
            new_content = content
            if "xmlns:xmp=" not in new_content:
                new_content = re.sub(
                    r"(<rdf:Description\b)",
                    r'\1 xmlns:xmp="http://ns.adobe.com/xap/1.0/"',
                    new_content,
                    count=1,
                )
            # Vložit xmp:Rating atribut do prvního rdf:Description tagu
            new_content, added = re.subn(
                r"(<rdf:Description\b[^/>]*)",
                rf'\1\n      xmp:Rating="{rating}"',
                new_content,
                count=1,
            )
            if added == 0:
                print(f"  ⚠ XMP soubor {xmp_path.name} nemá rdf:Description, nelze vložit Rating")
                return False, "error"

            if not dry_run:
                xmp_path.write_text(new_content, encoding="utf-8")
            return True, "updated"
        else:
            if not dry_run:
                xmp_path.write_text(
                    XMP_TEMPLATE.format(rating=rating), encoding="utf-8"
                )
            return True, "created"
    except OSError as e:
        print(f"  ⚠ XMP chyba pro {file_path.name}: {e}")
        return False, "error"


def apply_xmp_only(
    ratings: dict[str, int],
    source_dir: Path,
    dry_run: bool = False,
):
    """
    Zapíše hodnocení jen do XMP sidecar souborů (bez katalogu).

    Hledá fotky přímo na disku v source_dir a jejím poddirectories.
    """
    updated = 0
    not_found = 0
    skipped = 0
    xmp_written = 0
    xmp_failed = 0

    for filename, new_rating in ratings.items():
        # Vytvořit vyhledávací pattern
        if "." in filename:
            # Mám příponou — hledám přesný název
            search_pattern = filename
        else:
            # Bez přípony — hledám s libovolnou příponou
            search_pattern = f"{filename}.*"

        # Hledání na disku
        found = False
        for file_path in source_dir.rglob(search_pattern):
            if not file_path.is_file():
                continue

            found = True

            # Zapsat XMP
            ok, mode = write_xmp_rating(file_path, new_rating, dry_run)
            if mode == "skipped":
                print(f"  – {file_path.name}: XMP již má hodnocení, přeskakuji")
                skipped += 1
            elif ok:
                xmp_path = file_path.with_suffix(".xmp")
                mode_label = "(aktualizován)" if mode == "updated" else "(vytvořen)"
                print(f"  ✓ {file_path.name}: → {new_rating}⭐")
                if dry_run:
                    print(f"    [DRY] XMP {mode_label} → {xmp_path}")
                else:
                    print(f"    XMP {mode_label} → {xmp_path}")
                xmp_written += 1
            else:
                xmp_failed += 1

            updated += 1

        if not found:
            print(f"  ⚠ Nenalezeno: {filename}")
            not_found += 1

    print(f"\nVýsledek:")
    print(f"  ✓ Aktualizováno: {updated}")
    if skipped:
        print(f"  – Přeskočeno:    {skipped} (XMP již má hodnocení)")
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


def apply_ratings(
    ratings: dict[str, int],
    catalog_path: Path,
    dry_run: bool = False,
    source_dir: Path | None = None,
):
    """
    Zapíše hodnocení do ZPS X katalogu a XMP sidecar souborů.

    Párování: ratings.json obsahuje názvy bez přípony (např. "DSCF3987").
    V katalogu hledáme CIM_DisplayNameWithExt LIKE 'DSCF3987.%'
    Pokud je zadán source_dir, omezíme hledání na fotky z dané složky.
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

    # Připravit pattern pro filtrování podle složky (oba typy lomítek)
    dir_pattern = None
    dir_pattern_fwd = None
    if source_dir is not None:
        dir_pattern = str(source_dir).replace("/", "\\").rstrip("\\") + "\\"
        dir_pattern_fwd = str(source_dir).replace("\\", "/").rstrip("/") + "/"
        print(f"Filtrování podle složky: {source_dir}\n")

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

        if dir_pattern:
            cur.execute(
                """
                SELECT m.CUID, m.CIM_DisplayNameWithExt, m.CIM_DataRating,
                       b.CIB_OriginalUniPath
                FROM CatItemMetadata m
                JOIN CatItemBasic b ON b.CUID = m.CUID
                WHERE m.CIM_DisplayNameWithExt LIKE ?
                  AND (b.CIB_OriginalUniPath LIKE ? OR b.CIB_NormalizedUniPath LIKE ?
                    OR b.CIB_OriginalUniPath LIKE ? OR b.CIB_NormalizedUniPath LIKE ?)
                """,
                (pattern,
                 f"%{dir_pattern}%", f"%{dir_pattern}%",
                 f"%{dir_pattern_fwd}%", f"%{dir_pattern_fwd}%"),
            )
        else:
            cur.execute(
                """
                SELECT m.CUID, m.CIM_DisplayNameWithExt, m.CIM_DataRating,
                       b.CIB_OriginalUniPath
                FROM CatItemMetadata m
                LEFT JOIN CatItemBasic b ON b.CUID = m.CUID
                WHERE m.CIM_DisplayNameWithExt LIKE ?
                """,
                (pattern,),
            )
        rows = cur.fetchall()

        if not rows:
            if dir_pattern:
                # Diagnostika: zjistit, zda fotka vůbec existuje v katalogu
                cur.execute(
                    """
                    SELECT b.CIB_OriginalUniPath
                    FROM CatItemMetadata m
                    JOIN CatItemBasic b ON b.CUID = m.CUID
                    WHERE m.CIM_DisplayNameWithExt LIKE ?
                    LIMIT 1
                    """,
                    (pattern,),
                )
                diag = cur.fetchone()
                if diag:
                    print(f"  ⚠ Nenalezeno ve složce '{source_dir}': {filename}")
                    print(f"    Katalog má cestu: {diag['CIB_OriginalUniPath']}")
                    not_found += 1
                    continue
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
                ok, mode = write_xmp_rating(file_path, new_rating, dry_run)
                if mode == "skipped":
                    print(f"    – XMP již má hodnocení, přeskakuji")
                elif ok:
                    xmp_path = file_path.with_suffix(".xmp")
                    mode_label = "(aktualizován)" if mode == "updated" else "(vytvořen)"
                    if dry_run:
                        print(f"    [DRY] XMP {mode_label} → {xmp_path}")
                    else:
                        print(f"    XMP {mode_label} → {xmp_path}")
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
        "--source-dir", "-s",
        type=Path,
        default=None,
        help="Omezit párování na fotky z této složky (zabrání zápisu na stejně pojmenované fotky z jiných složek)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Nevytvářet zálohu katalogu",
    )
    parser.add_argument(
        "--xmp-only",
        action="store_true",
        help="Zapsat jen do XMP metadat, přeskočit katalog (nevyžaduje --catalog)",
    )

    args = parser.parse_args()

    if not args.ratings.exists():
        print(f"✗ Soubor neexistuje: {args.ratings}")
        sys.exit(1)

    if args.xmp_only:
        if not args.source_dir:
            print("✗ --xmp-only vyžaduje --source-dir")
            sys.exit(1)
        if not args.source_dir.exists():
            print(f"✗ Složka neexistuje: {args.source_dir}")
            sys.exit(1)
    else:
        if not args.catalog.exists():
            print(f"✗ Katalog neexistuje: {args.catalog}")
            print(f"  Zkus zadat cestu přes --catalog")
            sys.exit(1)

    # Načíst hodnocení
    ratings = load_ratings(args.ratings)
    print_summary(ratings)

    if args.xmp_only:
        # Režim jen XMP
        if args.dry_run:
            print("[DRY RUN — žádné změny nebudou provedeny]\n")

        apply_xmp_only(ratings, args.source_dir, args.dry_run)
    else:
        # Normální režim — katalog + XMP
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

        apply_ratings(ratings, args.catalog, args.dry_run, args.source_dir)


if __name__ == "__main__":
    main()
