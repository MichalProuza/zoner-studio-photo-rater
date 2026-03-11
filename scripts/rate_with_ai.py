#!/usr/bin/env python3
"""
rate_with_ai.py — automatické hodnocení náhledů pomocí Anthropic API

Použití:
    python scripts/rate_with_ai.py <previews_dir> [volitelné argumenty]

Příklady:
    python scripts/rate_with_ai.py C:\\Pictures\\2025-12-21\\_previews
    python scripts/rate_with_ai.py ./previews --output ./ratings.json --batch-size 15
    python scripts/rate_with_ai.py ./previews --resume   # pokračovat po přerušení

Vyžaduje:
    pip install anthropic
    set ANTHROPIC_API_KEY=sk-ant-...
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg"}
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_BATCH_SIZE = 20
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # sekund


def load_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8")


def encode_image(image_path: Path) -> str:
    return base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")


def parse_json_from_response(text: str) -> dict[str, int]:
    """Extrahuje JSON blok s hodnoceními z odpovědi modelu."""
    # Hledá JSON blok ohraničený ```json ... ```
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Fallback: hledá JSON objekt přímo v textu
    match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("Nepodařilo se najít JSON blok v odpovědi modelu.")


def validate_ratings(ratings: dict) -> dict[str, int]:
    """Ověří a normalizuje hodnocení — hodnoty musí být celá čísla 1–5."""
    validated = {}
    for key, value in ratings.items():
        try:
            rating = int(value)
        except (TypeError, ValueError):
            print(f"  ⚠ Přeskakuji '{key}': hodnota '{value}' není číslo")
            continue
        if not 1 <= rating <= 5:
            print(f"  ⚠ Přeskakuji '{key}': hodnocení {rating} je mimo rozsah 1–5")
            continue
        validated[key] = rating
    return validated


def rate_batch(
    client,
    model: str,
    prompt: str,
    images: list[Path],
) -> dict[str, int]:
    """Odešle jednu dávku náhledů na API a vrátí hodnocení."""
    content = [{"type": "text", "text": prompt}]

    for image_path in images:
        content.append({
            "type": "text",
            "text": f"\nSoubor: {image_path.stem}",
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": encode_image(image_path),
            },
        })

    content.append({
        "type": "text",
        "text": (
            "\nOhodnoť všechny výše zobrazené fotky. "
            "Na konci přidej JSON souhrn ve formátu:\n"
            "```json\n{\"NAZEV\": hodnoceni, ...}\n```"
        ),
    })

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    text = response.content[0].text
    raw_ratings = parse_json_from_response(text)
    return validate_ratings(raw_ratings)


def rate_batch_with_retry(
    client,
    model: str,
    prompt: str,
    images: list[Path],
    batch_index: int,
) -> dict[str, int]:
    """Pokusí se ohodnotit dávku, při selhání opakuje s exponenciálním čekáním."""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return rate_batch(client, model, prompt, images)
        except Exception as e:
            if attempt == RETRY_ATTEMPTS:
                raise
            wait = RETRY_DELAY * (2 ** (attempt - 1))
            print(f"  ✗ Pokus {attempt}/{RETRY_ATTEMPTS} selhal: {e}")
            print(f"  Čekám {wait}s před dalším pokusem...")
            time.sleep(wait)
    return {}  # nedostupné, ale mypy to vyžaduje


def print_distribution(ratings: dict[str, int]) -> None:
    """Vypíše distribuci hodnocení jako jednoduchý sloupcový graf."""
    counts = {i: 0 for i in range(1, 6)}
    for v in ratings.values():
        if v in counts:
            counts[v] += 1
    total = len(ratings)
    print()
    print("Distribuce hodnocení:")
    for stars in range(5, 0, -1):
        count = counts[stars]
        pct = count / total * 100 if total else 0
        bar = "█" * int(pct / 2)
        print(f"  {stars}⭐  {count:3d} ({pct:5.1f}%)  {bar}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automatické hodnocení JPEG náhledů pomocí Claude API",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "previews_dir",
        help="Složka s JPEG náhledy (výstup extract_previews.py)",
    )
    parser.add_argument(
        "--output", "-o",
        default="ratings.json",
        help="Výstupní soubor s hodnoceními",
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Počet fotek odeslaných v jednom API volání",
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help="ID modelu Claude",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Načíst existující ratings.json a hodnotit jen chybějící fotky",
    )
    args = parser.parse_args()

    # Kontrola závislosti
    try:
        import anthropic
    except ImportError:
        print("Chybí závislost: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    # Kontrola API klíče
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Chybí API klíč. Nastav proměnnou prostředí:\n"
            "  Windows: set ANTHROPIC_API_KEY=sk-ant-...\n"
            "  Linux:   export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(1)

    # Kontrola složky s náhledy
    previews_dir = Path(args.previews_dir)
    if not previews_dir.is_dir():
        print(f"Složka neexistuje: {previews_dir}", file=sys.stderr)
        sys.exit(1)

    # Načtení promptu
    # Ve frozen (PyInstaller) módu jsou datové soubory v sys._MEIPASS,
    # jinak hledáme relativně k tomuto skriptu.
    if getattr(sys, "frozen", False):
        _base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        _base = Path(__file__).parent.parent
    prompt_path = _base / "prompts" / "RATING_PROMPT_V2.md"
    if not prompt_path.exists():
        print(f"Prompt nenalezen: {prompt_path}", file=sys.stderr)
        sys.exit(1)
    prompt = load_prompt(prompt_path)

    # Nalezení náhledů
    images = sorted(
        p for p in previews_dir.iterdir()
        if p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not images:
        print(f"Žádné JPEG soubory v {previews_dir}", file=sys.stderr)
        sys.exit(1)

    # Načtení existujících hodnocení při --resume
    output_path = Path(args.output)
    ratings: dict[str, int] = {}
    if args.resume and output_path.exists():
        with open(output_path, encoding="utf-8-sig") as f:
            ratings = json.load(f)
        print(f"Načteno {len(ratings)} existujících hodnocení z {output_path}")
        images = [img for img in images if img.stem not in ratings]
        if not images:
            print("Všechny fotky jsou již ohodnoceny.")
            print_distribution(ratings)
            return
        print(f"Zbývá ohodnotit: {len(images)} fotek")

    client = anthropic.Anthropic(api_key=api_key)

    total = len(images)
    batches = [
        images[i:i + args.batch_size]
        for i in range(0, total, args.batch_size)
    ]

    print(f"Celkem fotek:  {total}")
    print(f"Počet dávek:   {len(batches)} × max {args.batch_size}")
    print(f"Model:         {args.model}")
    print(f"Výstup:        {output_path}")
    print()

    for i, batch in enumerate(batches, 1):
        start = (i - 1) * args.batch_size + 1
        end = min(i * args.batch_size, total)
        print(f"[{i}/{len(batches)}] Hodnotím fotky {start}–{end}...")

        try:
            batch_ratings = rate_batch_with_retry(
                client, args.model, prompt, batch, i
            )
            ratings.update(batch_ratings)

            # Průběžné ukládání po každé dávce
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(ratings, f, ensure_ascii=False, indent=2)

            print(f"  ✓ {len(batch_ratings)} hodnocení uloženo ({len(ratings)} celkem)")

        except Exception as e:
            print(f"  ✗ Dávka {i} selhala po {RETRY_ATTEMPTS} pokusech: {e}", file=sys.stderr)
            print("  Pokračuji další dávkou...")

        # Krátká pauza mezi dávkami (ochrana před rate limiting)
        if i < len(batches):
            time.sleep(2)

    print()
    print(f"Hotovo! Ohodnoceno: {len(ratings)}/{total + len(ratings) - total} fotek")
    print(f"Výsledek uložen: {output_path}")
    print_distribution(ratings)

    if not ratings:
        print("✗ Žádné hodnocení nebylo uloženo — všechny dávky selhaly.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
