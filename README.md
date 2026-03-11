# Zoner Studio Photo Rater — automatické hodnocení fotek pomocí AI

Python nástroj pro automatizovaný workflow:
1. **Extrakce** JPEG náhledů z RAW souborů
2. **AI hodnocení** náhledů (1–5 hvězd) pomocí Anthropic Claude nebo Google Gemini
3. **Zápis** hvězdiček do XMP metadata

> **Nejjednodušší způsob:** spusť `python scripts/run_gui.py`, vyber složku s fotkami, zvol AI poskytovatele a klikni na Spustit.

---

## Obsah

- [Požadavky](#požadavky)
- [Instalace](#instalace)
- [Struktura projektu](#struktura-projektu)
- [Rychlý start — grafické rozhraní (GUI)](#rychlý-start--grafické-rozhraní-gui)
- [Workflow krok za krokem](#workflow-krok-za-rokem)
  - [1. Extrakce náhledů](#1-extrakce-náhledů)
  - [2. AI hodnocení](#2-ai-hodnocení)
  - [3. Zápis do XMP metadata](#3-zápis-do-xmp-metadata)

---

## Požadavky

- **Python 3.10+**
- **Windows** (výchozí cesty jsou Windows; skripty fungují i na Linuxu)
- **Zoner Photo Studio X**
- **API Klíč** pro [Anthropic](https://console.anthropic.com/) nebo [Google Gemini](https://aistudio.google.com/)

---

## Instalace

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell

pip install -U pip
pip install -e .
```

*Poznámka: Pro Gemini je vyžadována knihovna `google-generativeai`, pro Anthropic `anthropic`.*

---

## Rychlý start — grafické rozhraní (GUI)

Nejjednodušší způsob použití — žádné příkazy v terminálu:

```powershell
python scripts/run_gui.py
```

**Postup v GUI:**

1. Klikni na **Vybrat…** a vyber složku s RAW fotkami
2. Vyber **Poskytovatele** (Anthropic nebo Google) a zadej svůj **API klíč**
3. Klikni na **▶ Spustit celý workflow**

GUI automaticky provede všechny tři kroky:
- `[1/3]` Extrakce náhledů ze RAW souborů → `<složka>/_previews/`
- `[2/3]` Hodnocení pomocí Claude nebo Gemini → `<složka>/ratings.json`
- `[3/3]` Zápis hodnocení do XMP souborů → `<složka>/*.xmp`

---

## Workflow krok za krokem

### 1. Extrakce náhledů
**Skript:** `scripts/extract_previews.py`
Extrahujeme vložené náhledy pro rychlou analýzu bez nutnosti plného vyvolání RAWu.

### 2. AI hodnocení
**Skript:** `scripts/rate_with_ai.py`
Podporuje přepínání mezi modely pomocí parametru `--provider`.

```bash
# Použití Gemini (výchozí model gemini-1.5-flash)
python scripts/rate_with_ai.py ./_previews --provider gemini --gemini-api-key VAŠ_KLÍČ

# Použití Anthropic (výchozí model claude-3-5-sonnet)
python scripts/rate_with_ai.py ./_previews --provider anthropic --anthropic-api-key VAŠ_KLÍČ
```

---

## Důležité poznámky

- **XMP sidecar soubor** — skript vytváří/aktualizuje `.xmp` soubory vedle originálních RAW fotek.
- **Aktualizace metadat** — po zápisu otevři v Zoner Studio **Aktualizaci metadat** (`Ctrl+Shift+M`), aby se hvězdičky načetly do katalogu.
- **Dry-run** — vždy doporučujeme nejdříve spustit s volbou "Dry run" pro kontrolu, co se bude zapisovat.
