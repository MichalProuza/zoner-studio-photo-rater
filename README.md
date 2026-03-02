# ZPS X Photo Rater — Automatické hodnocení fotek pomocí Claude

Varianta A: Offline workflow bez pluginu. Claude Code analyzuje náhledy
extrahované z RAW souborů a výsledná hodnocení se zapíší zpět do ZPS X.

## Požadavky

```bash
pip install rawpy Pillow
```

## Workflow

### 1. Extrakce náhledů

```bash
python scripts/extract_previews.py /cesta/k/raw/souborum --output /tmp/zps_previews --max-size 800
```

Extrahuje embedded JPEG z RAW souborů (RAF, CR2, NEF, ARW, DNG, ORF, RW2).
Výstup: JPEG soubory 800px (delší strana), cca 60–80 KB každý.

### 2. Hodnocení v Claude Code

V Claude Code (VS Code) otevři projekt a zadej:

```
Přečti prompt z prompts/RATING_PROMPT_V2.md.
Pak postupně procházej náhledy v /tmp/zps_previews/ po dávkách 5–10 fotek.
Pro každou fotku urči hodnocení 1–5 hvězd.
Výsledky průběžně zapisuj do ratings.json ve formátu:
{"DSCF3987": 4, "DSCF3988": 3, ...}
```

### 3. Aplikace hodnocení do ZPS X

```bash
python scripts/apply_ratings.py ratings.json --catalog /cesta/ke/katalogu
```

⚠️ **Tento skript vyžaduje úpravu podle formátu ZPS X katalogu.**
Viz komentáře v kódu — placeholder pro SQLite/XML/proprietární přístup.

## Struktura projektu

```
zps-photo-rater/
├── README.md
├── ratings.json              ← generuje Claude Code (krok 2)
├── prompts/
│   └── RATING_PROMPT_V2.md   ← prompt pro hodnocení
└── scripts/
    ├── extract_previews.py   ← extrakce náhledů z RAW
    └── apply_ratings.py      ← zápis hodnocení do ZPS X katalogu
```
