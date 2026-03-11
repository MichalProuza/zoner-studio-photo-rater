#!/usr/bin/env python3
"""
rate_with_ai.py – automatické hodnocení náhledů pomocí AI (Anthropic nebo Gemini)
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
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_BATCH_SIZE = 30  # Zvětšeno pro snížení počtu požadavků
RETRY_ATTEMPTS = 5
RETRY_DELAY = 10


def load_prompt(prompt_path: Path) -> str:
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Chyba při načítání promptu: {e}", file=sys.stderr)
        sys.exit(1)


def encode_image(image_path: Path) -> str:
    return base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")


def parse_json_from_response(text: str) -> dict[str, int]:
    match = re.search(r"```json\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError("Nepodařilo se najít platný JSON blok v odpovědi modelu.")


def validate_ratings(ratings: dict) -> dict[str, int]:
    if isinstance(ratings, list):
        normalized = {}
        for item in ratings:
            if isinstance(item, dict) and "SOUBOR" in item and "HODNOCENI" in item:
                normalized[item["SOUBOR"]] = item["HODNOCENI"]
        ratings = normalized
    validated = {}
    for key, value in ratings.items():
        try:
            clean_key = Path(key).stem
            rating = int(value)
            if 1 <= rating <= 5:
                validated[clean_key] = rating
        except:
            pass
    return validated


class AnthropicProvider:
    def __init__(self, api_key: str, model: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def rate_batch(self, prompt: str, images: list[Path]) -> dict[str, int]:
        content = [{"type": "text", "text": prompt}]
        for image_path in images:
            content.append({"type": "text", "text": f"\nSoubor: {image_path.stem}"})
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": encode_image(image_path),
                },
            })
        content.append({"type": "text", "text": "\nOhodnoť fotky. JSON výstup: ```json\n{\"NAZEV\": hodnoceni, ...}\n```"})
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        return parse_json_from_response(response.content[0].text)


class GeminiProvider:
    def __init__(self, api_key: str, model: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model if model.startswith("models/") else f"models/{model}"

    def rate_batch(self, prompt: str, images: list[Path]) -> dict[str, int]:
        from google.genai import types
        content_parts = [prompt]
        for image_path in images:
            content_parts.append(f"\nSoubor: {image_path.stem}")
            image_part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/jpeg")
            content_parts.append(image_part)
        content_parts.append("\nOhodnoť fotky podle instrukcí. JSON výstup v ```json bloku.")
        
        response = self.client.models.generate_content(model=self.model, contents=content_parts)
        return parse_json_from_response(response.text)


def rate_batch_with_retry(provider, prompt: str, images: list[Path]) -> dict[str, int]:
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return validate_ratings(provider.rate_batch(prompt, images))
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                # Pokusíme se z chyby vytáhnout doporučenou dobu čekání
                wait_match = re.search(r"retry in ([\d\.]+)s", err_msg)
                wait_time = float(wait_match.group(1)) + 2 if wait_match else 70
                print(f"  ⚠ Dosažen limit API (429). Čekám {int(wait_time)} sekund...")
                time.sleep(wait_time)
                # Po čekání zkusíme znovu v rámci stejného pokusu
                try:
                    return validate_ratings(provider.rate_batch(prompt, images))
                except:
                    pass
            
            if attempt == RETRY_ATTEMPTS: raise
            wait = RETRY_DELAY * (2 ** (attempt - 1))
            print(f"  ✖ Pokus {attempt} selhal. Čekám {wait}s...")
            time.sleep(wait)
    return {}


def print_distribution(ratings: dict[str, int]) -> None:
    counts = {i: 0 for i in range(1, 6)}
    for v in ratings.values():
        if v in counts: counts[v] += 1
    total = len(ratings)
    print("\nDistribuce hodnocení:")
    for stars in range(5, 0, -1):
        count = counts[stars]
        pct = count / total * 100 if total else 0
        print(f"  {stars}⭐  {count:3d} ({pct:5.1f}%)  {'█' * int(pct / 2)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("previews_dir")
    parser.add_argument("--output", "-o", default="ratings.json")
    parser.add_argument("--provider", choices=["anthropic", "gemini"], default="anthropic")
    parser.add_argument("--model")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--gemini-api-key")
    parser.add_argument("--anthropic-api-key")
    args = parser.parse_args()

    if args.provider == "anthropic":
        api_key = args.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        model_id = args.model or DEFAULT_ANTHROPIC_MODEL
    else:
        api_key = args.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        model_id = args.model or DEFAULT_GEMINI_MODEL

    previews_dir = Path(args.previews_dir)
    if getattr(sys, "frozen", False): _base = Path(sys._MEIPASS)
    else: _base = Path(__file__).parent.parent
    prompt = load_prompt(_base / "prompts" / "RATING_PROMPT_V2.md")
    images = sorted([p for p in previews_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS])
    
    output_path = Path(args.output)
    ratings = {}
    if args.resume and output_path.exists():
        try:
            with open(output_path, encoding="utf-8-sig") as f: ratings = json.load(f)
            images = [img for img in images if img.stem not in ratings]
        except: pass

    if not images:
        if ratings: print_distribution(ratings)
        return

    provider = AnthropicProvider(api_key, model_id) if args.provider == "anthropic" else GeminiProvider(api_key, model_id)
    batches = [images[i:i + args.batch_size] for i in range(0, len(images), args.batch_size)]

    for i, batch in enumerate(batches, 1):
        print(f"[{i}/{len(batches)}] Hodnotím dávku {len(batch)} fotek...")
        try:
            batch_ratings = rate_batch_with_retry(provider, prompt, batch)
            ratings.update(batch_ratings)
            with open(output_path, "w", encoding="utf-8") as f: json.dump(ratings, f, ensure_ascii=False, indent=2)
            print(f"  ✔ {len(batch_ratings)} hodnocení uloženo")
        except Exception as e:
            print(f"  ✖ Chyba: {e}")

        if i < len(batches):
            time.sleep(10) # Bezpečnostní pauza mezi dávkami

    print_distribution(ratings)

if __name__ == "__main__":
    main()
