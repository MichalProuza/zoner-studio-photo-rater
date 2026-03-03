# ZPS X Photo Rater — automatické hodnocení fotek pomocí AI

Python nástroj pro automatizovaný workflow:
1. **Extrakce** JPEG náhledů z RAW souborů
2. **AI hodnocení** náhledů (1–5 hvězd) pomocí připraveného promptu
3. **Zápis** hvězdiček do katalogu Zoner Photo Studio X

---

## Obsah

- [Požadavky](#požadavky)
- [Instalace](#instalace)
- [Struktura projektu](#struktura-projektu)
- [Rychlý start](#rychlý-start)
- [Workflow krok za krokem](#workflow-krok-za-krokem)
  - [1. Extrakce náhledů](#1-extrakce-náhledů)
  - [2. Hodnocení náhledů](#2-hodnocení-náhledů)
  - [3. Zápis do katalogu](#3-zápis-do-katalogu)
- [PowerShell orchestrace](#powershell-orchestrace)
- [Formát ratings.json](#formát-ratingsjson)
- [Podporované RAW formáty](#podporované-raw-formáty)
- [ZPS X SQLite schéma](#zps-x-sqlite-schéma)
- [Důležité poznámky](#důležité-poznámky)

---

## Požadavky

- **Python 3.10+**
- **Windows** (výchozí cesty jsou Windows; skripty fungují i na Linuxu s explicitními cestami)
- **Zoner Photo Studio X** s vytvořeným katalogem

---

## Instalace

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# nebo
.venv\Scripts\activate          # Windows PowerShell

pip install -U pip
pip install -e .
```

Alternativa bez editable instalace:

```bash
pip install rawpy Pillow
```

---

## Struktura projektu

```text
zoner-studio-photo-rater/
├── pyproject.toml                 # Konfigurace Python projektu
├── README.md                      # Tato dokumentace
├── ratings.json                   # Hodnocení fotek (výstup AI, vstup apply_ratings.py)
├── prompts/
│   └── RATING_PROMPT_V2.md       # Prompt pro AI hodnocení fotografií
└── scripts/
    ├── extract_previews.py        # Extrakce JPEG náhledů z RAW souborů
    ├── apply_ratings.py           # Zápis hodnocení do ZPS X katalogu
    └── run_zps_workflow.ps1       # PowerShell orchestrace celého workflow
```

---

## Rychlý start

```powershell
# 1. Aktivace prostředí a instalace
python -m venv .venv
.venv\Scripts\activate
pip install -U pip && pip install -e .

# 2. Extrakce náhledů
python scripts/extract_previews.py "C:\Users\michal.prouza\Pictures\2025-12-21" `
    --output "C:\Users\michal.prouza\Pictures\2025-12-21\_previews"

# 3. Ohodnoť náhledy (ručně nebo pomocí AI promptu) → ulož ratings.json

# 4. Dry-run — zkontroluj, co se zapíše
python scripts/apply_ratings.py "C:\Users\michal.prouza\Pictures\2025-12-21\ratings.json" `
    --catalog "C:\Users\michal.prouza\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps" `
    --dry-run

# 5. Ostrý zápis
python scripts/apply_ratings.py "C:\Users\michal.prouza\Pictures\2025-12-21\ratings.json" `
    --catalog "C:\Users\michal.prouza\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps"
```

---

## Workflow krok za krokem

```
RAW soubory
    │
    ▼
extract_previews.py ──► JPEG náhledy (max 800 px)
    │
    ▼
AI hodnocení (RATING_PROMPT_V2.md) ──► ratings.json
    │
    ▼
apply_ratings.py ──► ZPS X katalog (SQLite)
    │
    ▼
Hvězdičky v Zoner Photo Studio X
```

### 1. Extrakce náhledů

**Skript:** `scripts/extract_previews.py`

Extrahuje embedded JPEG náhledy z RAW souborů bez nutnosti plného renderování.
Výstupní náhledy jsou zmenšeny na maximální rozměr delší strany (výchozí 800 px).

#### Použití

```bash
python scripts/extract_previews.py <source> [volitelné argumenty]
```

#### Argumenty

| Argument | Zkratka | Výchozí | Popis |
|---|---|---|---|
| `source` | — | (povinné) | Adresář s RAW soubory |
| `--output` | `-o` | `/tmp/zps_previews` | Výstupní adresář pro náhledy |
| `--max-size` | `-s` | `800` | Maximální rozměr delší strany v pixelech |
| `--recursive` | `-r` | vypnuto | Prohledávat i podadresáře |

#### Příklady

```bash
# Základní použití
python scripts/extract_previews.py /cesta/k/raw --output /tmp/zps_previews

# Větší náhledy
python scripts/extract_previews.py /cesta/k/raw --output ./previews --max-size 1600

# Rekurzivní zpracování
python scripts/extract_previews.py /cesta/k/raw --output ./previews --recursive
```

#### Výstup

```
Nalezeno 47 RAW souborů
Výstup: C:\Pictures\2025-12-21\_previews
Max rozměr: 800px

  ✓ [1/47] DSCF3987.RAF
  ✓ [2/47] DSCF3988.RAF
  ⚠ Žádný náhled: DSCF3990.RAF
  ✓ [4/47] DSCF3991.RAF
  ...

Hotovo za 12.3s
  ✓ Extrahováno: 46
  ✗ Selhalo: 1
  Náhledy uloženy v: C:\Pictures\2025-12-21\_previews
```

---

### 2. Hodnocení náhledů

**Prompt:** `prompts/RATING_PROMPT_V2.md`

Prompt pro AI (nebo manuální) hodnocení fotografií. Definuje filosofii hodnocení,
stupnici, kritéria a formát výstupu.

#### Stupnice hodnocení

| Hvězdičky | Označení | Popis |
|---|---|---|
| ⭐⭐⭐⭐⭐ | Výjimečný | Zastaví vás. Silná emoce, dokonalé načasování. |
| ⭐⭐⭐⭐ | Silný | Výborná kompozice i výraz. Stojí za publikaci. |
| ⭐⭐⭐ | Dobrý | Solidní snímek, funguje, ale ničím nevyniká. |
| ⭐⭐ | Slabý | Technicky OK, ale nevýrazný. |
| ⭐ | Odpad | Zavřené oči (neúmyslně), výrazné rozmazání, katastrofální kompozice. |

#### Kritéria hodnocení

- **Kompozice** — vedoucí linie, rámování, negativní prostor, umístění subjektu
- **Emoce a výraz** — přirozenost, intenzita výrazu, oční kontakt
- **Umělecký záměr** — pohybové rozmazání, nekonvenční kompozice jako záměr

#### Co ignorovat

- Expozice, vyvážení bílé, barevné podání (opravitelné v postprodukci)
- Šum a zrnitost
- Mírné chromatické aberace

#### Formát výstupu AI

```
SOUBOR: DSCF3987
HODNOCENÍ: 4
DŮVOD: Přirozený výraz, výborné světlo. Drobná nerovnováha kompozice.

SOUBOR: DSCF3988
HODNOCENÍ: 2
DŮVOD: Subjekt mimo zaostření, výraz bez výrazu.
```

Na konci každé dávky AI přidá JSON souhrn, který zkopíruješ do `ratings.json`.

---

### 3. Zápis do katalogu

**Skript:** `scripts/apply_ratings.py`

Načte `ratings.json` a zapíše hodnocení do SQLite katalogu Zoner Photo Studio X.

#### Použití

```bash
python scripts/apply_ratings.py <ratings> [volitelné argumenty]
```

#### Argumenty

| Argument | Zkratka | Výchozí | Popis |
|---|---|---|---|
| `ratings` | — | (povinné) | Cesta k `ratings.json` |
| `--catalog` | `-c` | `%LOCALAPPDATA%\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps` | Cesta ke katalogu ZPS X |
| `--dry-run` | `-n` | vypnuto | Jen zobrazit změny, nic nezapisovat |
| `--no-backup` | — | záloha ON | Nevytvářet zálohu katalogu před zápisem |

#### Příklady

```bash
# Dry-run (bezpečné testování)
python scripts/apply_ratings.py ratings.json --dry-run

# Zápis s explicitní cestou ke katalogu
python scripts/apply_ratings.py ratings.json \
    --catalog "C:\Users\michal.prouza\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps"

# Zápis bez zálohy
python scripts/apply_ratings.py ratings.json --no-backup
```

#### Výstup

```
Hodnocení k aplikaci: 47 fotek

  5⭐   3 ( 6.4%)  ███
  4⭐  18 (38.3%)  ██████████████████
  3⭐  15 (31.9%)  ███████████████
  2⭐  10 (21.3%)  ██████████
  1⭐   1 ( 2.1%)  █

Záloha: index.catalogue-zps.bak

⚠️  Ujisti se, že Zoner Photo Studio X je ZAVŘENÝ!

  ✓ DSCF3987.RAF: bez hodnocení → 4⭐
  ✓ DSCF3988.RAF: 3⭐ → 4⭐
  – DSCF3989.RAF již má 5⭐, přeskakuji
  ⚠ Nenalezeno: DSCF3990

Výsledek:
  ✓ Aktualizováno: 45
  – Beze změny:    1
  ⚠ Nenalezeno:    1
```

#### Párování souborů

Skript páruje záznamy v `ratings.json` se soubory v katalogu podle názvu bez přípony:

| Klíč v ratings.json | Hledaný vzor v katalogu |
|---|---|
| `DSCF3987` | `DSCF3987.%` (jakákoliv přípona) |
| `DSCF3987.RAF` | `DSCF3987.RAF` (přesná shoda) |

---

## PowerShell orchestrace

**Skript:** `scripts/run_zps_workflow.ps1`

Automatizuje celý workflow v jednom spuštění: extrakce → čekání na hodnocení → zápis.

#### Parametry

| Parametr | Výchozí | Popis |
|---|---|---|
| `-SourceDir` | `C:\Users\michal.prouza\Pictures\2025-12 Sousedské setkání\2025-12-21` | Složka s RAW soubory |
| `-PreviewDir` | `<SourceDir>\_previews` | Výstupní složka pro náhledy |
| `-RatingsPath` | `<SourceDir>\ratings.json` | Cesta k souboru s hodnoceními |
| `-CatalogPath` | `%LOCALAPPDATA%\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps` | Cesta ke katalogu ZPS X |
| `-Recursive` | vypnuto | Prohledávat i podadresáře |
| `-DryRun` | vypnuto | Simulovat zápis bez skutečných změn |
| `-MaxSize` | `800` | Max rozměr náhledů v pixelech |

#### Použití

```powershell
# Základní spuštění (dry-run pro kontrolu)
powershell -ExecutionPolicy Bypass -File scripts/run_zps_workflow.ps1 -DryRun

# Ostrý zápis
powershell -ExecutionPolicy Bypass -File scripts/run_zps_workflow.ps1

# S vlastní složkou
powershell -ExecutionPolicy Bypass -File scripts/run_zps_workflow.ps1 `
    -SourceDir "C:\Fotky\2025-03-Akce" `
    -PreviewDir "C:\Fotky\2025-03-Akce\_previews" `
    -RatingsPath "C:\Fotky\2025-03-Akce\ratings.json" `
    -MaxSize 1200
```

#### Průběh

```
== ZPS X Photo Rater workflow ==
SourceDir:   C:\Users\michal.prouza\Pictures\2025-12-21
PreviewDir:  C:\Users\michal.prouza\Pictures\2025-12-21\_previews
RatingsPath: C:\Users\michal.prouza\Pictures\2025-12-21\ratings.json
CatalogPath: C:\Users\...\ZPSCatalog\index.catalogue-zps

[1/2] Extrakce náhledů...
  ✓ [1/47] DSCF3987.RAF
  ...

Nyní ohodnoť náhledy dle prompts/RATING_PROMPT_V2.md a ulož výsledky do: ...
Až bude ratings.json připravený, stiskni Enter pro pokračování k zápisu hodnocení:

[2/2] Aplikace hodnocení do katalogu...
  ✓ DSCF3987.RAF: bez hodnocení → 4⭐
  ...

Hotovo.
```

---

## Formát ratings.json

Jednoduchý JSON objekt: klíč = název souboru bez přípony, hodnota = hvězdičky (1–5).

```json
{
  "DSCF3987": 4,
  "DSCF3988": 3,
  "DSCF3989": 5,
  "DSCF3990": 2,
  "DSCF3991": 1
}
```

**Poznámky:**
- Klíče lze zadat i s příponou: `"DSCF3987.RAF": 4`
- Klíče začínající `_` jsou ignorovány (lze použít pro komentáře: `"_poznamka": "..."`)
- Soubor uložený PowerShellem může obsahovat UTF-8 BOM — skript to automaticky zpracuje
- Prázdný soubor (`{}`) způsobí chybu (ochrana před tichým no-op zápisem)

---

## Podporované RAW formáty

| Přípona | Výrobce |
|---|---|
| `.raf` | Fujifilm |
| `.cr2`, `.cr3` | Canon |
| `.nef`, `.nrw` | Nikon |
| `.arw`, `.srf`, `.sr2` | Sony |
| `.dng` | Adobe DNG (universální) |
| `.orf` | Olympus |
| `.rw2` | Panasonic |
| `.pef` | Pentax |
| `.srw` | Samsung |
| `.x3f` | Sigma |
| `.3fr` | Hasselblad |
| `.iiq` | Phase One |
| `.rwl` | Leica |
| `.erf` | Epson |

---

## ZPS X SQLite schéma

Katalog Zoner Photo Studio X je SQLite databáze uložená jako `index.catalogue-zps`.

**Výchozí umístění (Windows):**
```
C:\Users\<uživatel>\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps
```

**Použité tabulky:**

### CatItemMetadata

| Sloupec | Typ | Popis |
|---|---|---|
| `CUID` | TEXT (PK) | Unikátní identifikátor záznamu |
| `CIM_DisplayNameWithExt` | TEXT | Název souboru s příponou (např. `DSCF3987.RAF`) |
| `CIM_DataRating` | INTEGER | Hodnocení 1–5 hvězd (**sem se zapisuje**) |

### CatItemBasic

| Sloupec | Typ | Popis |
|---|---|---|
| `CUID` | TEXT (PK/FK) | Unikátní identifikátor záznamu |
| `CIB_OriginalUniPath` | TEXT | Plná cesta k souboru |
| `CIB_NormalizedUniPath` | TEXT | Normalizovaná cesta |

Skript `apply_ratings.py` zapisuje hodnoty výhradně do `CatItemMetadata.CIM_DataRating`.

---

## Důležité poznámky

- **Zavři Zoner Photo Studio X** před zápisem do katalogu — otevřená aplikace katalog uzamkne.
- **Záloha** — skript automaticky vytváří zálohu `*.catalogue-zps.bak` před každým zápisem.
  Zálohu lze přeskočit pomocí `--no-backup`.
- **Dry-run** — vždy doporučujeme nejdřív spustit s `--dry-run`, zkontrolovat výstup
  a teprve pak provést ostrý zápis.
- **Párování souborů** — pokud skript hlásí „Nenalezeno", zkontroluj, zda jsou soubory
  importovány v ZPS X a katalog je aktuální.
