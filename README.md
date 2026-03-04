# Zoner Studio Photo Rater — automatické hodnocení fotek pomocí AI

Python nástroj pro automatizovaný workflow:
1. **Extrakce** JPEG náhledů z RAW souborů
2. **AI hodnocení** náhledů (1–5 hvězd) pomocí připraveného promptu
3. **Zápis** hvězdiček do XMP metadat

> **Nejjednodušší způsob:** spusť `python scripts/run_gui.py`, vyber složku s fotkami a klikni na Spustit. Vše ostatní se provede automaticky.

---

## Obsah

- [Požadavky](#požadavky)
- [Instalace](#instalace)
- [Struktura projektu](#struktura-projektu)
- [Rychlý start — grafické rozhraní (GUI)](#rychlý-start--grafické-rozhraní-gui)
- [Workflow krok za krokem](#workflow-krok-za-krokem)
  - [1. Extrakce náhledů](#1-extrakce-náhledů)
  - [2. Hodnocení náhledů](#2-hodnocení-náhledů)
  - [2b. Automatické AI hodnocení](#2b-automatické-ai-hodnocení)
  - [3. Zápis do XMP metadat](#3-zápis-do-xmp-metadat)
- [PowerShell orchestrace](#powershell-orchestrace)
- [Formát ratings.json](#formát-ratingsjson)
- [Podporované RAW formáty](#podporované-raw-formáty)
- [Důležité poznámky](#důležité-poznámky)

---

## Požadavky

- **Python 3.10+**
- **Windows** (výchozí cesty jsou Windows; skripty fungují i na Linuxu s explicitními cestami)
- **Zoner Photo Studio X**

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
    ├── run_gui.py                 # ★ Grafické rozhraní — výběr složky + celý workflow
    ├── extract_previews.py        # Extrakce JPEG náhledů z RAW souborů
    ├── rate_with_ai.py            # Automatické AI hodnocení (Anthropic API)
    ├── apply_ratings.py           # Zápis hodnocení do XMP metadat
    ├── run_zps_workflow.ps1       # PowerShell orchestrace celého workflow
    └── run_zps_workflow.cmd       # CMD wrapper (obchází ExecutionPolicy)
```

---

## Rychlý start — grafické rozhraní (GUI)

Nejjednodušší způsob použití — žádné příkazy v terminálu:

```powershell
# 1. Instalace závislostí (jen jednou)
pip install -e .

# 2. Spuštění GUI
python scripts/run_gui.py
```

**Postup v GUI:**

1. Klikni na **Vybrat…** a vyber složku s RAW fotkami
2. Zadej svůj **Anthropic API klíč** (nebo ho nastav jako env proměnnou `ANTHROPIC_API_KEY`)
3. Klikni na **▶ Spustit celý workflow**

GUI automaticky provede všechny tři kroky:

```
[1/3] Extrakce náhledů ze RAW souborů  →  <složka>/_previews/
[2/3] Hodnocení pomocí Claude AI        →  <složka>/ratings.json
[3/3] Zápis hodnocení do XMP souborů   →  <složka>/*.xmp
```

Průběh každého kroku se zobrazuje v logu v reálném čase.

Po dokončení otevři v Zoner Studio **Aktualizaci metadat** (`Ctrl+Shift+M`), aby se hvězdičky z XMP souborů načetly do Zoner Studio.

**Volitelné přepínače:**

| Přepínač | Popis |
|---|---|
| Procházet podsložky | Zpracuje i RAW soubory ve vnořených složkách |
| Dry run | Simuluje zápis do XMP bez skutečné změny souborů |

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
apply_ratings.py ──► XMP sidecar soubory
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

### 2b. Automatické AI hodnocení

**Skript:** `scripts/rate_with_ai.py`

Automaticky odesílá náhledy na Anthropic API (Claude) a ukládá hodnocení do `ratings.json`.
Náhledy jsou odesílány po dávkách, výsledky se průběžně ukládají — přerušení nevadí.

#### Předpoklady

```bash
pip install anthropic
```

```powershell
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# Linux/macOS
export ANTHROPIC_API_KEY=sk-ant-...
```

API klíč získáš na [console.anthropic.com](https://console.anthropic.com/).

#### Použití

```bash
python scripts/rate_with_ai.py <previews_dir> [volitelné argumenty]
```

#### Argumenty

| Argument | Zkratka | Výchozí | Popis |
|---|---|---|---|
| `previews_dir` | — | (povinné) | Složka s JPEG náhledy |
| `--output` | `-o` | `ratings.json` | Výstupní soubor |
| `--batch-size` | `-b` | `20` | Počet fotek v jedné API žádosti |
| `--model` | `-m` | `claude-sonnet-4-6` | ID modelu Claude |
| `--resume` | — | vypnuto | Přeskočit již ohodnocené fotky |

#### Příklady

```powershell
# Základní hodnocení
python scripts/rate_with_ai.py "C:\Pictures\2025-12-21\_previews" `
    --output "C:\Pictures\2025-12-21\ratings.json"

# Menší dávky (při problémech s timeoutem)
python scripts/rate_with_ai.py ./previews --batch-size 10 --output ratings.json

# Pokračovat po přerušení
python scripts/rate_with_ai.py ./previews --output ratings.json --resume
```

#### Výstup

```
Celkem fotek:  252
Počet dávek:   13 × max 20
Model:         claude-sonnet-4-6
Výstup:        ratings.json

[1/13] Hodnotím fotky 1–20...
  ✓ 20 hodnocení uloženo (20 celkem)
[2/13] Hodnotím fotky 21–40...
  ✓ 20 hodnocení uloženo (40 celkem)
...
[13/13] Hodnotím fotky 241–252...
  ✓ 12 hodnocení uloženo (252 celkem)

Hotovo! Ohodnoceno: 252 fotek
Výsledek uložen: ratings.json

Distribuce hodnocení:
  5⭐    8 ( 3.2%)  █
  4⭐   62 (24.6%)  ████████████
  3⭐   98 (38.9%)  ███████████████████
  2⭐   71 (28.2%)  ██████████████
  1⭐   13 ( 5.2%)  ██
```

---

### 3. Zápis do XMP metadat

**Skript:** `scripts/apply_ratings.py`

Načte `ratings.json` a zapíše hodnocení do **XMP sidecar souborů** vedle originálních fotek (`xmp:Rating`).
Skript hledá fotky přímo na disku v `--source-dir` a vytváří/aktualizuje soubory jako `DSCF3987.xmp` vedle `DSCF3987.RAF`.

Po zápisu spusť v Zoner Studio **Aktualizaci metadat** (`Ctrl+Shift+M`) pro načtení hodnocení z XMP.

#### Použití

```bash
python scripts/apply_ratings.py <ratings> [volitelné argumenty]
```

#### Argumenty

| Argument | Zkratka | Výchozí | Popis |
|---|---|---|---|
| `ratings` | — | (povinné) | Cesta k `ratings.json` |
| `--source-dir` | `-s` | `None` | Složka s RAW fotkami, kde se vytvoří XMP soubory |
| `--dry-run` | `-n` | vypnuto | Jen zobrazit změny, nic nezapisovat |

#### Příklady

```bash
# Dry-run (kontrola před zápisem)
python scripts/apply_ratings.py ratings.json --source-dir "C:\Fotky\2025-03" --dry-run

# Ostrý zápis
python scripts/apply_ratings.py ratings.json --source-dir "C:\Fotky\2025-03"

# Rekurzivně i v podsložkách
python scripts/apply_ratings.py ratings.json --source-dir "C:\Fotky"
```

#### Výstup

```
Hodnocení k aplikaci: 47 fotek

  5⭐   3 ( 6.4%)  ███
  4⭐  18 (38.3%)  ██████████████████
  3⭐  15 (31.9%)  ███████████████
  2⭐  10 (21.3%)  ██████████
  1⭐   1 ( 2.1%)  █

  ✓ DSCF3987.RAF: bez hodnocení → 4⭐
    XMP → C:\Pictures\2025-12-21\DSCF3987.xmp
  ✓ DSCF3988.RAF: 3⭐ → 4⭐
    XMP → C:\Pictures\2025-12-21\DSCF3988.xmp
  – DSCF3989.RAF již má 5⭐, přeskakuji
  ⚠ Nenalezeno: DSCF3990

Výsledek:
  ✓ Aktualizováno: 45
  – Beze změny:    1
  ⚠ Nenalezeno:    1
  XMP zapsáno:     44

💡 V Zoner Studio spusť Aktualizaci metadat (Ctrl+Shift+M) pro načtení hodnocení z XMP souborů.
```

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
| `-Recursive` | vypnuto | Prohledávat i podadresáře |
| `-DryRun` | vypnuto | Simulovat zápis bez skutečných změn |
| `-MaxSize` | `800` | Max rozměr náhledů v pixelech |

#### Použití

Nejjednodušší způsob — přes `.cmd` wrapper (nevyžaduje změnu ExecutionPolicy):

```powershell
# Základní spuštění (dry-run pro kontrolu)
scripts\run_zps_workflow.cmd -DryRun

# Ostrý zápis
scripts\run_zps_workflow.cmd

# S vlastní složkou
scripts\run_zps_workflow.cmd -SourceDir "C:\Fotky\2025-03-Akce" -PreviewDir "C:\Fotky\2025-03-Akce\_previews" -RatingsPath "C:\Fotky\2025-03-Akce\ratings.json" -MaxSize 1200
```

Alternativně přímo přes PowerShell (vyžaduje `-ExecutionPolicy Bypass`):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_zps_workflow.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File scripts/run_zps_workflow.ps1
```

#### Průběh

```
== Zoner Studio Photo Rater workflow ==
SourceDir:   C:\Users\michal.prouza\Pictures\2025-12-21
PreviewDir:  C:\Users\michal.prouza\Pictures\2025-12-21\_previews
RatingsPath: C:\Users\michal.prouza\Pictures\2025-12-21\ratings.json

[1/2] Extrakce náhledů...
  ✓ [1/47] DSCF3987.RAF
  ...

Nyní ohodnoť náhledy dle prompts/RATING_PROMPT_V2.md a ulož výsledky do: ...
Až bude ratings.json připravený, stiskni Enter pro pokračování k zápisu hodnocení:

[2/2] Aplikace hodnocení do XMP metadat...
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

## Důležité poznámky

- **XMP sidecar soubory** — skript vytváří/aktualizuje `.xmp` soubory vedle originálních
  RAW fotek s hodnocením (`xmp:Rating`). Zoner Studio čte hodnocení z těchto souborů.
- **Aktualizace metadat** — po zápisu otevři Zoner Studio a spusť `Ctrl+Shift+M` (Aktualizace metadat),
  aby se hodnocení z XMP souborů načetla do Zoner Studio.
- **Dry-run** — vždy doporučujeme nejdřív spustit s `--dry-run`, zkontrolovat výstup
  a teprve pak provést ostrý zápis.
- **Párování souborů** — pokud skript hlásí „Nenalezeno", zkontroluj, zda jsou soubory
  přítomny v zadané složce `--source-dir`.
