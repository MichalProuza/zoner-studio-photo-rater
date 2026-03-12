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
import io
from pathlib import Path

# Vynucení UTF-8 pro konzoli na Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg"}
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_BATCH_SIZE = 30  # Zvětšeno pro snížení počtu požadavků
RETRY_ATTEMPTS = 5
RETRY_DELAY = 10


class QuotaExhaustedError(Exception):
    """Denní kvóta API je vyčerpána a není možné pokračovat."""
    pass


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
        self.total_input_tokens = 0
        self.total_output_tokens = 0

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
        if hasattr(response, "usage") and response.usage:
            self.total_input_tokens += getattr(response.usage, "input_tokens", 0)
            self.total_output_tokens += getattr(response.usage, "output_tokens", 0)
        return parse_json_from_response(response.content[0].text)


class GeminiProvider:
    def __init__(self, api_key: str, model: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _track_usage(self, response):
        meta = getattr(response, "usage_metadata", None)
        if meta:
            self.total_input_tokens += getattr(meta, "prompt_token_count", 0) or 0
            self.total_output_tokens += getattr(meta, "candidates_token_count", 0) or 0

    def rate_batch(self, prompt: str, images: list[Path]) -> dict[str, int]:
        from google.genai import types
        content_parts = [prompt]
        for image_path in images:
            content_parts.append(f"\nSoubor: {image_path.stem}")
            image_part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/jpeg")
            content_parts.append(image_part)
        content_parts.append("\nOhodnoť fotky podle instrukcí. JSON výstup v ```json bloku.")

        # Seznam variant názvu modelu k vyzkoušení
        model_variants = [self.model]
        if self.model.startswith("models/"): model_variants.append(self.model.replace("models/", ""))
        else: model_variants.append(f"models/{self.model}")

        last_exception = None
        for m in model_variants:
            try:
                response = self.client.models.generate_content(model=m, contents=content_parts)
                self._track_usage(response)
                return parse_json_from_response(response.text)
            except Exception as e:
                last_exception = e
                if "404" not in str(e): raise # Pokud to není 404, vyhodíme chybu (např. 429)

        # Pokud jsme se dostali sem, všechny varianty selhaly s 404
        print(f"  [!] Model '{self.model}' nebyl nalezen ani v jedné variantě.")
        try:
            models = [m.name for m in self.client.models.list()]
            print(f"  [!] Dostupné modely pro váš klíč: {', '.join(models[:10])}...")
        except: pass
        raise last_exception


def rate_batch_with_retry(provider, prompt: str, images: list[Path]) -> dict[str, int]:
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return validate_ratings(provider.rate_batch(prompt, images))
        except Exception as e:
            err_msg = str(e)
            
            # Extrakce podrobných informací o kvótách (pro Gemini)
            quota_info = []
            if "quotaMetric" in err_msg:
                # Pokusíme se najít názvy metrik a ID kvót
                metrics = re.findall(r"quotaMetric': '([^']+)'", err_msg)
                quota_ids = re.findall(r"quotaId': '([^']+)'", err_msg)
                for m, q in zip(metrics, quota_ids):
                    quota_info.append(f"    - Metrika: {m}\n    - ID kvóty: {q}")

            # Detekce vyčerpání denní kvóty (limit 0)
            if "limit: 0" in err_msg and "quota" in err_msg.lower():
                print(f"\n  [!!!] KRITICKÁ CHYBA: Vyčerpána denní kvóta pro tento model (limit 0).")
                if quota_info:
                    print("\n".join(quota_info))
                print(f"  [!] Tip: Pokud máte nastavený Billing, API vás stále identifikuje jako Free Tier.")
                print(f"  [!] Zkuste vygenerovat nový API klíč nebo počkejte na propagaci změn v Google Cloud.")
                raise QuotaExhaustedError(
                    "Denní kvóta Gemini API (Free Tier) je vyčerpána. "
                    "Počkejte do zítřka, nebo aktivujte placený plán a vygenerujte nový API klíč."
                )

            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                if quota_info:
                    print(f"  [!] Detaily omezení:\n" + "\n".join(quota_info))
                
                # Pokusíme se vytáhnout doporučenou dobu čekání
                wait_match = re.search(r"retry in ([\d\.]+)s", err_msg)
                if wait_match:
                    wait_time = float(wait_match.group(1)) + 2
                else:
                    wait_time = 65 + (attempt * 20) 
                
                print(f"  [!] Dosažen limit API (429). Čekám {int(wait_time)} sekund...")
                time.sleep(wait_time)
                
                if attempt < RETRY_ATTEMPTS:
                    try:
                        print(f"  [i] Opakuji pokus po čekání...")
                        return validate_ratings(provider.rate_batch(prompt, images))
                    except Exception as e2:
                        err_msg = str(e2)
                else:
                    raise
            
            if attempt == RETRY_ATTEMPTS:
                raise
            
            wait = RETRY_DELAY * (2 ** (attempt - 1))
            print(f"  [X] Pokus {attempt} selhal ({err_msg[:100]}...). Čekám {wait}s před dalším pokusem...")
            time.sleep(wait)
    return {}


# Cena za milion tokenů (input, output) v USD
MODEL_PRICING = {
    "claude-sonnet-4-6":          (3.0,  15.0),
    "claude-opus-4-6":            (15.0, 75.0),
    "claude-haiku-4-5-20251001":  (0.80,  4.0),
    "claude-3-7-sonnet-20250219": (3.0,  15.0),
    "gemini-2.5-flash":           (0.15,  0.60),
    "gemini-2.5-pro":             (1.25,  10.0),
    "gemini-2.0-flash-001":       (0.10,  0.40),
    "gemini-2.0-flash-lite":      (0.075, 0.30),
}


def print_usage_summary(provider, model_id: str) -> None:
    inp = provider.total_input_tokens
    out = provider.total_output_tokens
    total = inp + out
    if total == 0:
        return
    print(f"\nSpotřeba tokenů:")
    print(f"  Vstupní:  {inp:>10,} tokenů")
    print(f"  Výstupní: {out:>10,} tokenů")
    print(f"  Celkem:   {total:>10,} tokenů")

    pricing = MODEL_PRICING.get(model_id)
    if pricing:
        cost_input = inp / 1_000_000 * pricing[0]
        cost_output = out / 1_000_000 * pricing[1]
        cost_total = cost_input + cost_output
        print(f"\nOdhadovaná cena ({model_id}):")
        print(f"  Vstup:  ${cost_input:.4f}")
        print(f"  Výstup: ${cost_output:.4f}")
        print(f"  Celkem: ${cost_total:.4f}")


def print_distribution(ratings: dict[str, int]) -> None:
    counts = {i: 0 for i in range(1, 6)}
    for v in ratings.values():
        if v in counts: counts[v] += 1
    total = len(ratings)
    print("\nDistribuce hodnocení:")
    for stars in range(5, 0, -1):
        count = counts[stars]
        pct = count / total * 100 if total else 0
        bar = "#" * int(pct / 2)
        print(f"  {stars}*  {count:3d} ({pct:5.1f}%)  {bar}")


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

    total_photos = len(images)
    done_count = len(ratings)  # již hotové z resume

    for i, batch in enumerate(batches, 1):
        print(f"\n[{i}/{len(batches)}] Hodnotím dávku {len(batch)} fotek...")
        try:
            batch_ratings = rate_batch_with_retry(provider, prompt, batch)
            for name, stars in batch_ratings.items():
                done_count += 1
                print(f"  [{done_count}/{total_photos}] {name}: {'*' * stars} ({stars}/5)")
            ratings.update(batch_ratings)
            with open(output_path, "w", encoding="utf-8") as f: json.dump(ratings, f, ensure_ascii=False, indent=2)
            print(f"  [OK] {len(batch_ratings)} hodnocení uloženo")
        except QuotaExhaustedError as e:
            print(f"  [X] {e}")
            print("  [!] Zpracování přerušeno – nelze pokračovat bez platné kvóty.")
            break
        except Exception as e:
            print(f"  [X] Chyba: {e}")

        if i < len(batches):
            time.sleep(10) # Bezpečnostní pauza mezi dávkami

    print_distribution(ratings)
    print_usage_summary(provider, model_id)

if __name__ == "__main__":
    main()
