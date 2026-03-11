#!/usr/bin/env python3
"""
rate_with_ai.py – automatické hodnocení náhledů pomocí AI (Anthropic nebo Gemini)

Použití:
    python scripts/rate_with_ai.py <previews_dir> [volitelné argumenty]

Příklady:
    python scripts/rate_with_ai.py ./previews --provider gemini --gemini-api-key YOUR_KEY
    python scripts/rate_with_ai.py ./previews --provider anthropic --batch-size 15
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
DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
DEFAULT_BATCH_SIZE = 10
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # sekundy


def load_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8")


def encode_image(image_path: Path) -> str:
    return base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")


def parse_json_from_response(text: str) -> dict[str, int]:
    """Extrahuje JSON blok s hodnoceními z odpovědi modelu."""
    # Hledá JSON blok ohraničený ```json ... ```
    match = re.search(r"```json\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: hledá JSON objekt přímo v textu
    match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("Nepodařilo se najít platný JSON blok v odpovědi modelu.")


def validate_ratings(ratings: dict) -> dict[str, int]:
    """Ověří a normalizuje hodnocení – hodnoty musí být celá čísla 1–5."""
    if isinstance(ratings, list):
        # Převod z listu objektů na dict, pokud by model vrátil list
        normalized = {}
        for item in ratings:
            if isinstance(item, dict) and "SOUBOR" in item and "HODNOCENI" in item:
                normalized[item["SOUBOR"]] = item["HODNOCENI"]
        ratings = normalized

    validated = {}
    for key, value in ratings.items():
        try:
            # Klíče mohou být s příponou i bez, my chceme bez
            clean_key = Path(key).stem
            rating = int(value)
            if 1 <= rating <= 5:
                validated[clean_key] = rating
            else:
                print(f"  ⚠ Přeskakuji '{key}': hodnocení {rating} je mimo rozsah 1–5")
        except (TypeError, ValueError):
            print(f"  ⚠ Přeskakuji '{key}': hodnota '{value}' není číslo")
    return validated


class AnthropicProvider:
    def __init__(self, api_key: str, model: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def rate_batch(self, prompt: str, images: list[Path]) -> dict[str, int]:
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
                "```json\n{\"NAZEV_SOUBORU\": hodnoceni, ...}\n```"
            ),
        })

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        return parse_json_from_response(response.content[0].text)


class GeminiProvider:
    def __init__(self, api_key: str, model: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def rate_batch(self, prompt: str, images: list[Path]) -> dict[str, int]:
        content = [prompt]

        for image_path in images:
            content.append(f"\nSoubor: {image_path.stem}")
            # Gemini SDK umí pracovat přímo s daty
            img_data = {
                "mime_type": "image/jpeg",
                "data": image_path.read_bytes()
            }
            content.append(img_data)

        content.append(
            "\nOhodnoť všechny výše zobrazené fotky podle instrukcí. "
            "Výsledek vrať VÝHRADNĚ jako JSON objekt ve formátu: "
            "{\"NAZEV_SOUBORU\": hodnoceni, ...} zabalený v markdown bloku ```json."
        )

        response = self.model.generate_content(content)
        return parse_json_from_response(response.text)


def rate_batch_with_retry(provider, prompt: str, images: list[Path]) -> dict[str, int]:
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            raw_ratings = provider.rate_batch(prompt, images)
            return validate_ratings(raw_ratings)
        except Exception as e:
            if attempt == RETRY_ATTEMPTS:
                raise
            wait = RETRY_DELAY * (2 ** (attempt - 1))
            print(f"  ✖ Pokus {attempt}/{RETRY_ATTEMPTS} selhal: {e}")
            print(f"  Čekám {wait}s před dalším pokusem...")
            time.sleep(wait)
    return {}


def print_distribution(ratings: dict[str, int]) -> None:
    counts = {i: 0 for i in range(1, 6)}
    for v in ratings.values():
        if v in counts:
            counts[v] += 1
    total = len(ratings)
    print("\nDistribuce hodnocení:")
    for stars in range(5, 0, -1):
        count = counts[stars]
        pct = count / total * 100 if total else 0
        bar = "█" * int(pct / 2)
        print(f"  {stars}⭐  {count:3d} ({pct:5.1f}%)  {bar}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automatické hodnocení náhledů pomocí AI (Anthropic nebo Gemini)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("previews_dir", help="Složka s JPEG náhledy")
    parser.add_argument("--output", "-o", default="ratings.json", help="Výstupní soubor")
    parser.add_argument("--provider", choices=["anthropic", "gemini"], default="anthropic", help="Poskytovatel AI")
    parser.add_argument("--model", "-m", help="ID modelu (pokud není výchozí)")
    parser.add_argument("--batch-size", "-b", type=int, default=DEFAULT_BATCH_SIZE, help="Počet fotek v jedné dávce")
    parser.add_argument("--resume", action="store_true", help="Pokračovat v existujícím hodnocení")
    parser.add_argument("--gemini-api-key", help="API klíč pro Gemini (lze i přes GEMINI_API_KEY)")
    parser.add_argument("--anthropic-api-key", help="API klíč pro Anthropic (lze i přes ANTHROPIC_API_KEY)")

    args = parser.parse_args()

    # Kontrola API klíčů
    api_key = None
    if args.provider == "anthropic":
        api_key = args.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("Chybí Anthropic API klíč. Nastavte --anthropic-api-key nebo ANTHROPIC_API_KEY.", file=sys.stderr)
            sys.exit(1)
        model_id = args.model or DEFAULT_ANTHROPIC_MODEL
    else:
        api_key = args.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("Chybí Gemini API klíč. Nastavte --gemini-api-key nebo GEMINI_API_KEY.", file=sys.stderr)
            sys.exit(1)
        model_id = args.model or DEFAULT_GEMINI_MODEL

    previews_dir = Path(args.previews_dir)
    if not previews_dir.is_dir():
        print(f"Složka neexistuje: {previews_dir}", file=sys.stderr)
        sys.exit(1)

    # Načtení promptu
    if getattr(sys, "frozen", False):
        _base = Path(sys._MEIPASS)
    else:
        _base = Path(__file__).parent.parent
    prompt_path = _base / "prompts" / "RATING_PROMPT_V2.md"
    if not prompt_path.exists():
        print(f"Prompt nenalezen: {prompt_path}", file=sys.stderr)
        sys.exit(1)
    prompt = load_prompt(prompt_path)

    # Nalezení náhledů
    images = sorted([p for p in previews_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS])
    if not images:
        print(f"Žádné JPEG soubory v {previews_dir}", file=sys.stderr)
        sys.exit(1)

    # Resume logika
    output_path = Path(args.output)
    ratings = {}
    if args.resume and output_path.exists():
        with open(output_path, encoding="utf-8-sig") as f:
            ratings = json.load(f)
        print(f"Načteno {len(ratings)} existujících hodnocení.")
        images = [img for img in images if img.stem not in ratings]
        if not images:
            print("Všechny fotky jsou již ohodnoceny.")
            print_distribution(ratings)
            return
        print(f"Zbývá ohodnotit: {len(images)} fotek")

    # Inicializace poskytovatele
    try:
        if args.provider == "anthropic":
            provider = AnthropicProvider(api_key, model_id)
        else:
            provider = GeminiProvider(api_key, model_id)
    except ImportError:
        print(f"Chybí knihovna pro {args.provider}. Nainstalujte ji pomocí: pip install {args.provider}", file=sys.stderr)
        if args.provider == "gemini":
            print("  (pro Gemini: pip install google-generativeai)", file=sys.stderr)
        sys.exit(1)

    total = len(images)
    batches = [images[i:i + args.batch_size] for i in range(0, total, args.batch_size)]

    print(f"Celkem k hodnocení: {total}")
    print(f"Poskytovatel:      {args.provider} ({model_id})")
    print(f"Velikost dávky:    {args.batch_size}")
    print()

    for i, batch in enumerate(batches, 1):
        start_idx = (i - 1) * args.batch_size + 1
        end_idx = min(i * args.batch_size, total)
        print(f"[{i}/{len(batches)}] Hodnotím fotky {start_idx}–{end_idx}...")

        try:
            batch_ratings = rate_batch_with_retry(provider, prompt, batch)
            ratings.update(batch_ratings)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(ratings, f, ensure_ascii=False, indent=2)

            print(f"  ✔ {len(batch_ratings)} hodnocení uloženo ({len(ratings)} celkem)")
        except Exception as e:
            print(f"  ✖ Dávka {i} selhala: {e}", file=sys.stderr)
            print("  Pokračuji další dávkou...")

        if i < len(batches):
            time.sleep(1)  # Krátká pauza proti rate limitům

    print(f"\nHotovo! Ohodnoceno: {len(ratings)} fotek")
    print_distribution(ratings)


if __name__ == "__main__":
    main()
