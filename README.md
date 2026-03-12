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
- [Podporované modely](#podporované-modely)
- [Workflow krok za krokem](#workflow-krok-za-krokem)
- [Progres a spotřeba tokenů](#progres-a-spotřeba-tokenů)
- [XMP chování](#xmp-chování)
- [Sestavení EXE](#sestavení-exe)

---

## Požadavky

- **Python 3.10+**
- **Windows** (výchozí cesty jsou Windows; skripty fungují i na Linuxu)
- **Zoner Photo Studio X**
- **API Klíč** pro [Anthropic](https://console.anthropic.com/) nebo [Google Gemini](https://aistudio.google.com/)

---

## Instalace

Nejdříve si vytvořte virtuální prostředí a nainstalujte všechny potřebné knihovny:

```powershell
# 1. Vytvoření virtuálního prostředí
python -m venv .venv

# 2. Aktivace prostředí (Windows PowerShell)
.venv\Scripts\activate

# 3. Instalace všech závislostí (včetně rawpy, Pillow, anthropic a google-genai)
pip install -U pip
pip install -e .
```

Pokud preferujete ruční instalaci jednotlivých balíčků:
```bash
pip install rawpy Pillow anthropic google-genai
```

---

## Struktura projektu

```
├── main.py                    # Vstupní bod pro EXE (PyInstaller)
├── zps_rater.spec             # PyInstaller spec pro build EXE
├── prompts/
│   └── RATING_PROMPT_V2.md   # Hodnotící kritéria (286 řádků)
└── scripts/
    ├── run_gui.py             # GUI (Tkinter)
    ├── extract_previews.py    # Extrakce JPEG z RAW
    ├── rate_with_ai.py        # AI hodnocení + token tracking
    └── apply_ratings.py       # Zápis do XMP / ZPS katalogu
```

---

## Rychlý start — grafické rozhraní (GUI)

Spusťte GUI a postupujte podle instrukcí na obrazovce:

```powershell
python scripts/run_gui.py
```

**Postup v GUI:**
1. Klikni na **Vybrat…** a vyber složku s RAW fotkami
2. Vyber **Poskytovatele** (Anthropic nebo Google) a zadej svůj **API klíč**
3. Vyber **Model** z rozbalovacího menu
4. Klikni na **▶ Spustit**

---

## Podporované modely

### Anthropic
| Model | Popis |
|---|---|
| `claude-sonnet-4-6` | **Výchozí** — dobrý poměr cena/výkon |
| `claude-opus-4-6` | Nejkvalitnější, ale dražší |
| `claude-haiku-4-5-20251001` | Nejrychlejší a nejlevnější |
| `claude-3-7-sonnet-20250219` | Starší Sonnet |

### Google Gemini
| Model | Popis |
|---|---|
| `gemini-2.5-flash` | **Výchozí** — rychlý, levný |
| `gemini-2.5-pro` | Kvalitnější, dražší |
| `gemini-2.0-flash-001` | Starší Flash |
| `gemini-2.0-flash-lite` | Nejlevnější varianta |

> **Poznámka:** `gemini-2.0-flash` (bez `-001`) byl zrušen pro nové uživatele. Používejte `gemini-2.5-flash`.

---

## Workflow krok za krokem

### 1. Extrakce náhledů
```bash
python scripts/extract_previews.py /cesta/k/fotkam -o /cesta/k/fotkam/_previews
```
Extrahuje JPEG náhledy z RAW souborů (RAF, CR2, CR3, NEF, ARW, DNG, ORF, SRW) a zmenší je na 800px.

### 2. AI hodnocení
```bash
python scripts/rate_with_ai.py /cesta/k/fotkam/_previews -o ratings.json --provider gemini
```
Ohodnotí fotky 1–5 hvězdami. Výstup: `ratings.json`.

### 3. Zápis do XMP
```bash
python scripts/apply_ratings.py ratings.json --xmp-only --source-dir /cesta/k/fotkam
```
Zapíše hodnocení do XMP sidecar souborů.

---

## Progres a spotřeba tokenů

Během hodnocení se vypisuje **progres po jednotlivých fotkách**:

```
[1/3] Hodnotím dávku 30 fotek...
  [1/90] DSCF3987: **** (4/5)
  [2/90] DSCF3988: *** (3/5)
  [3/90] DSCF3989: ***** (5/5)
  ...
  [OK] 30 hodnocení uloženo
```

Na konci se zobrazí **spotřeba tokenů a odhadovaná cena**:

```
Spotřeba tokenů:
  Vstupní:     125,000 tokenů
  Výstupní:      3,200 tokenů
  Celkem:      128,200 tokenů

Odhadovaná cena (gemini-2.5-flash):
  Vstup:  $0.0188
  Výstup: $0.0019
  Celkem: $0.0207
```

---

## XMP chování

Zápis do XMP sidecar souborů je **bezpečný vůči existujícím datům**:

- **XMP neexistuje** → vytvoří nový soubor s hodnocením
- **XMP existuje bez hodnocení** → doplní `xmp:Rating` do existujícího souboru (ostatní metadata zachová)
- **XMP existuje s hodnocením 0** → přepíše na nové hodnocení (0 = bez hodnocení)
- **XMP existuje s hodnocením 1–5** → **přeskočí** (zachová ruční hodnocení uživatele)

V logu se zobrazuje, zda byl XMP **(vytvořen)**, **(aktualizován)** nebo **přeskočen**.

---

## Sestavení EXE

Pro vytvoření samostatného EXE souboru (nevyžaduje Python na cílovém PC):

```powershell
pip install pyinstaller
python -m PyInstaller zps_rater.spec
```

Výsledek: `dist/ZpsXPhotoRater.exe`

> **Poznámka:** EXE se musí buildovat na Windows. Složky `dist/` a `build/` nejsou součástí repozitáře.

---

## Důležité poznámky

- **XMP sidecar soubor** — skript vytváří/aktualizuje `.xmp` soubory vedle originálních RAW fotek.
- **Aktualizace metadat** — po zápisu otevři v Zoner Studio **Aktualizaci metadat** (`Ctrl+Shift+M`), aby se hvězdičky načetly do katalogu.
- **Dry-run** — vždy doporučujeme nejdříve spustit s volbou "Dry run" pro kontrolu, co se bude zapisovat.
- **Rate limiting** — Gemini Free Tier má přísné limity. Skript automaticky detekuje 429 chyby a čeká na uvolnění kvóty.
- **Resume** — pokud hodnocení selže uprostřed, spusť znovu s `--resume` a pokračuje tam, kde skončilo.
