# ZPS X Photo Rater — automatické hodnocení fotek pomocí AI

Python projekt pro workflow:
1. extrakce JPEG náhledů z RAW,
2. AI hodnocení náhledů,
3. zápis hvězdiček do katalogu Zoner Photo Studio X.

## Instalace

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e .
```

Alternativa bez editable instalace:

```bash
pip install rawpy Pillow
```

## Struktura projektu

```text
zoner-studio-photo-rater/
├── pyproject.toml
├── README.md
├── ratings.json                 # generuje AI hodnocení
├── prompts/
│   └── RATING_PROMPT_V2.md
└── scripts/
    ├── extract_previews.py
    └── apply_ratings.py
```


## Rychlý start pro tvoji konkrétní složku

Pokud chceš pracovat **jen** se složkou:

```text
C:\Users\michal.prouza\Pictures\2025-12 Sousedské setkání\2025-12-21
```

použij tento postup v PowerShellu:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -U pip
pip install -e .

python scripts/extract_previews.py "C:\Users\michal.prouza\Pictures\2025-12 Sousedské setkání\2025-12-21" --output "C:\Users\michal.prouza\Pictures\2025-12 Sousedské setkání\2025-12-21\_previews" --max-size 800
```

Pak ohodnoť náhledy z `_previews` podle `prompts/RATING_PROMPT_V2.md` a ulož `ratings.json` do stejné složky.

Kontrola bez zápisu:

```powershell
python scripts/apply_ratings.py "C:\Users\michal.prouza\Pictures\2025-12 Sousedské setkání\2025-12-21\ratings.json" --catalog "C:\Users\michal.prouza\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps" --dry-run
```

Ostrý zápis:

```powershell
python scripts/apply_ratings.py "C:\Users\michal.prouza\Pictures\2025-12 Sousedské setkání\2025-12-21\ratings.json" --catalog "C:\Users\michal.prouza\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps"
```

Nebo můžeš spustit připravený skript:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_zps_workflow.ps1 -DryRun
# po kontrole bez --DryRun
```

## Workflow

### 1) Extrakce náhledů z RAW

```bash
python scripts/extract_previews.py /cesta/k/raw/souborum --output /tmp/zps_previews --max-size 800
```

Skript extrahuje embedded JPEG náhledy z RAW formátů (RAF, CR2/CR3, NEF, ARW, DNG, ORF, RW2…).

### 2) Hodnocení náhledů

Použij prompt ze souboru:

```text
prompts/RATING_PROMPT_V2.md
```

Výstup ukládej do `ratings.json` ve formátu:

```json
{
  "DSCF3987": 4,
  "DSCF3988": 3,
  "DSCF3989": 5
}
```

### 3) Zápis hodnocení do ZPS X katalogu

```bash
python scripts/apply_ratings.py ratings.json
```

Výchozí katalog (Windows):

```text
C:\Users\michal.prouza\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps
```

Případně explicitně:

```bash
python scripts/apply_ratings.py ratings.json --catalog "C:\Users\michal.prouza\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps"
```

Bez zápisu (kontrola změn):

```bash
python scripts/apply_ratings.py ratings.json --dry-run
```

## ZPS X SQLite schéma (použité tabulky)

- `CatItemMetadata`
  - `CUID` (PK)
  - `CIM_DisplayNameWithExt` (název souboru)
  - `CIM_DataRating` (hodnocení 1–5)
- `CatItemBasic`
  - `CUID` (PK)
  - `CIB_OriginalUniPath` (plná cesta k souboru)

Skript `apply_ratings.py` zapisuje hodnoty do `CatItemMetadata.CIM_DataRating`.

## Důležité

- Před zápisem do katalogu zavři Zoner Photo Studio X.
- Skript vytváří zálohu katalogu (`*.bak`), pokud nepoužiješ `--no-backup`.
