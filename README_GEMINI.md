# Zoner Studio Photo Rater — Gemini API Extension

Tento dokument shrnuje novinky a vylepšení zaměřená na integraci **Google Gemini API** do workflow hodnocení fotografií.

## Hlavní novinky

### 1. Podpora Google Gemini API
Aplikace nyní umožňuje přepnout mezi Anthropic Claude a Google Gemini.
- **Moderní SDK**: Používáme nejnovější balíček `google-genai`.
- **Nejnovější modely**: Podpora pro Gemini 2.5 Flash, 2.5 Pro, 2.0 Flash a Flash Lite.
- **Výchozí volba**: `gemini-2.5-flash` — rychlý a cenově výhodný.

### 2. Vylepšené GUI (Grafické rozhraní)
V `scripts/run_gui.py` přibyly nové ovládací prvky:
- **Přepínač poskytovatelů**: Snadná volba mezi Anthropic a Google.
- **Výběr modelu**: Rozbalovací menu s aktuálně dostupnými modely pro každého poskytovatele.
- **Oddělené klíče**: Aplikace si pamatuje API klíče pro oba poskytovatele zvlášť.
- **Perzistence**: Všechna nastavení se ukládají do `%APPDATA%\zps-rater\config.ini`.

### 3. Automatická správa závislostí
Při spuštění přes Python skript (`run_gui.py`) aplikace automaticky zkontroluje, zda máte nainstalované potřebné knihovny (`rawpy`, `Pillow`, `anthropic`, `google-genai`). Pokud chybí, pokusí se je sama doinstalovat.

### 4. Ochrana proti limitům (Rate Limiting)
Bezplatné tarify Gemini mají přísné limity na počet požadavků. Workflow jsme proto optimalizovali:
- **Větší dávky**: Nyní se posílá **30 fotek v jednom požadavku** (místo původních 10), což šetří vaši kvótu.
- **Smart Retry**: Pokud narazíte na chybu `429 RESOURCE_EXHAUSTED`, skript automaticky přečte doporučenou dobu čekání z chybové hlášky, počká (obvykle ~65s) a pak automaticky pokračuje.
- **Detekce denní kvóty**: Pokud je denní kvóta vyčerpána (limit 0), skript to rozpozná a ukončí se s jasnou hláškou.
- **Bezpečnostní pauzy**: Mezi dávkami je vložena 10sekundová prodleva pro zvýšení stability.

### 5. Samostatný EXE soubor
Aplikaci lze sestavit do jednoho souboru `ZpsXPhotoRater.exe`, který nevyžaduje nainstalovaný Python na cílovém počítači.

```powershell
pip install pyinstaller
python -m PyInstaller zps_rater.spec
```

Výsledek: `dist/ZpsXPhotoRater.exe`

---

## Tipy pro používání Gemini

- **Free Tier**: Pokud používáte Gemini zdarma, používejte model **Gemini 2.5 Flash**. Je nejrychlejší a má nejrozumnější limity pro hromadné zpracování.
- **Náhledy**: Extrakce náhledů je nastavena na 800px, což je ideální kompromis mezi čitelností pro AI a spotřebou tokenů.
- **XMP Metadata**: Nezapomeňte v Zoner Studio X po skončení workflow použít `Ctrl+Shift+M` (Aktualizovat metadata ze souboru).
