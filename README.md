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

# 3. Instalace všech závislostí (včetně rawpy, Pillow, anthropic a google-generativeai)
pip install -U pip
pip install -e .
```

Pokud preferujete ruční instalaci jednotlivých balíčků:
```bash
pip install rawpy Pillow anthropic google-generativeai
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
3. Klikni na **▶ Spustit celý workflow**

---

## Důležité poznámky

- **XMP sidecar soubor** — skript vytváří/aktualizuje `.xmp` soubory vedle originálních RAW fotek.
- **Aktualizace metadat** — po zápisu otevři v Zoner Studio **Aktualizaci metadat** (`Ctrl+Shift+M`), aby se hvězdičky načetly do katalogu.
- **Dry-run** — vždy doporučujeme nejdříve spustit s volbou "Dry run" pro kontrolu, co se bude zapisovat.
