#!/usr/bin/env python3
"""
run_gui.py — grafické rozhraní pro ZPS X Photo Rater

Stačí vybrat složku s fotkami a celý pipeline proběhne automaticky:
  1. Extrakce náhledů ze surových souborů (RAW → JPEG)
  2. Hodnocení pomocí Claude AI (1–5 hvězdiček)
  3. Zápis hodnocení do XMP sidecar souborů

Spuštění:
    python scripts/run_gui.py
"""

import os
import sys
import subprocess
import threading
import configparser
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent

# Detekce PyInstaller frozen módu
_FROZEN = getattr(sys, "frozen", False)


def _config_path() -> Path:
    """Vrátí cestu ke konfiguračnímu souboru (~/.config/zps-rater/config.ini)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "zps-rater" / "config.ini"


def load_saved_api_key() -> str:
    """Načte uložený API klíč z konfiguračního souboru, nebo z env proměnné."""
    config_file = _config_path()
    if config_file.exists():
        cfg = configparser.ConfigParser()
        cfg.read(config_file, encoding="utf-8")
        key = cfg.get("anthropic", "api_key", fallback="").strip()
        if key:
            return key
    return os.environ.get("ANTHROPIC_API_KEY", "")


def save_api_key(api_key: str) -> None:
    """Uloží API klíč do konfiguračního souboru."""
    config_file = _config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    if config_file.exists():
        cfg.read(config_file, encoding="utf-8")
    if "anthropic" not in cfg:
        cfg["anthropic"] = {}
    cfg["anthropic"]["api_key"] = api_key
    with open(config_file, "w", encoding="utf-8") as f:
        cfg.write(f)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ZPS X Photo Rater")
        self.minsize(600, 500)
        self.resizable(True, True)
        self._apply_theme()
        self._build_ui()
        self.running = False

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self):
        style = ttk.Style(self)
        available = style.theme_names()
        for preferred in ("vista", "aqua", "clam", "alt", "default"):
            if preferred in available:
                style.theme_use(preferred)
                break
        style.configure("Run.TButton", font=("", 11, "bold"), padding=6)

    # ------------------------------------------------------------------
    # UI layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        # ---------- Folder selection ----------
        frm_folder = ttk.LabelFrame(self, text="Složka s fotkami (RAW soubory)")
        frm_folder.pack(fill="x", **pad)

        self.folder_var = tk.StringVar()
        ttk.Entry(frm_folder, textvariable=self.folder_var, width=55).pack(
            side="left", fill="x", expand=True, padx=6, pady=6
        )
        ttk.Button(frm_folder, text="Vybrat…", command=self._pick_folder).pack(
            side="right", padx=(0, 6), pady=6
        )

        # ---------- Options ----------
        frm_opts = ttk.LabelFrame(self, text="Nastavení")
        frm_opts.pack(fill="x", **pad)
        frm_opts.columnconfigure(1, weight=1)

        ttk.Label(frm_opts, text="Anthropic API klíč:").grid(
            row=0, column=0, sticky="w", padx=6, pady=5
        )
        self.api_key_var = tk.StringVar(value=load_saved_api_key())
        self._api_entry = ttk.Entry(
            frm_opts, textvariable=self.api_key_var, width=44, show="•"
        )
        self._api_entry.grid(row=0, column=1, sticky="ew", padx=(6, 2), pady=5)

        self._btn_save_key = ttk.Button(
            frm_opts, text="Uložit klíč", command=self._save_api_key
        )
        self._btn_save_key.grid(row=0, column=2, padx=(0, 6), pady=5)

        self._save_key_label = ttk.Label(frm_opts, text="", foreground="gray")
        self._save_key_label.grid(row=1, column=1, columnspan=2, sticky="w", padx=6)

        self.recursive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frm_opts, text="Procházet podsložky rekurzivně", variable=self.recursive_var
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frm_opts,
            text="Dry run — simulace bez zápisu do XMP",
            variable=self.dry_run_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        # ---------- Run button ----------
        self.btn_run = ttk.Button(
            self, text="▶  Spustit celý workflow", command=self._start, style="Run.TButton"
        )
        self.btn_run.pack(pady=8)

        self.progress_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.progress_var, foreground="#0066cc").pack()

        # ---------- Log ----------
        frm_log = ttk.LabelFrame(self, text="Průběh")
        frm_log.pack(fill="both", expand=True, **pad)

        self.log = scrolledtext.ScrolledText(
            frm_log, state="disabled", height=18, font=("Courier New", 9), wrap="word"
        )
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.tag_config("ok", foreground="#007700")
        self.log.tag_config("err", foreground="#cc0000")
        self.log.tag_config("hdr", foreground="#0044aa", font=("Courier New", 9, "bold"))

    # ------------------------------------------------------------------
    # API key persistence
    # ------------------------------------------------------------------

    def _save_api_key(self):
        key = self.api_key_var.get().strip()
        if not key:
            self._save_key_label.config(text="⚠  Klíč je prázdný.", foreground="#cc0000")
            return
        save_api_key(key)
        cfg_path = _config_path()
        self._save_key_label.config(
            text=f"✓  Uloženo do {cfg_path}", foreground="#007700"
        )
        # Reset status after 4 seconds
        self.after(4000, lambda: self._save_key_label.config(text="", foreground="gray"))

    # ------------------------------------------------------------------
    # Folder picker
    # ------------------------------------------------------------------

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Vyberte složku s fotkami")
        if folder:
            self.folder_var.set(folder)

    # ------------------------------------------------------------------
    # Logging helpers (thread-safe)
    # ------------------------------------------------------------------

    def _log(self, text: str, tag: str = ""):
        def _update():
            self.log.config(state="normal")
            self.log.insert("end", text + "\n", tag)
            self.log.see("end")
            self.log.config(state="disabled")

        self.after(0, _update)

    def _set_progress(self, text: str):
        self.after(0, lambda: self.progress_var.set(text))

    def _set_running(self, running: bool):
        def _update():
            self.running = running
            self.btn_run.config(state="disabled" if running else "normal")

        self.after(0, _update)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def _start(self):
        folder = self.folder_var.get().strip()
        if not folder:
            self._log("⚠  Není vybrána složka!", "err")
            return
        api_key = self.api_key_var.get().strip()
        if not api_key:
            self._log("⚠  Chybí Anthropic API klíč!", "err")
            return

        self._set_running(True)
        # Clear log
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

        thread = threading.Thread(
            target=self._run_workflow, args=(folder, api_key), daemon=True
        )
        thread.start()

    def _run_step(self, label: str, cmd: list, env: dict, cwd: Path = PROJECT_ROOT) -> bool:
        """Run one subprocess and stream its output to the log.

        Returns True on success, False on failure.
        """
        self._set_progress(label)
        self._log(f"\n{'=' * 50}", "hdr")
        self._log(f"  {label}", "hdr")
        self._log(f"{'=' * 50}", "hdr")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
            )
            for line in proc.stdout:
                self._log(line.rstrip())
            proc.wait()
        except FileNotFoundError as exc:
            self._log(f"✗  Nepodařilo se spustit příkaz: {exc}", "err")
            return False

        if proc.returncode == 0:
            self._log(f"✓  Hotovo (exit 0)", "ok")
            return True

        self._log(f"✗  Krok selhal (exit {proc.returncode})", "err")
        return False

    # ------------------------------------------------------------------
    # Subprocess helper
    # ------------------------------------------------------------------

    @staticmethod
    def _exe_cmd(script_name: str) -> list:
        """Vrátí prefix příkazu pro spuštění dílčího skriptu.

        V normálním (nefrozen) módu: [python, cesta/ke/skriptu.py]
        Ve frozen (EXE) módu:        [exe, --_mode=script_name]
        """
        if _FROZEN:
            return [sys.executable, f"--_mode={script_name}"]
        return [sys.executable, str(SCRIPTS_DIR / f"{script_name}.py")]

    def _run_workflow(self, folder: str, api_key: str):
        source = Path(folder)
        previews = source / "_previews"
        ratings = source / "ratings.json"

        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = api_key
        env["PYTHONUTF8"] = "1"  # Windows: všechny subprocesy píší UTF-8 do stdout

        # Ve frozen módu běží subprocesy ve stejném adresáři jako exe;
        # jinak používáme kořen projektu jako cwd.
        cwd = Path(sys.executable).parent if _FROZEN else PROJECT_ROOT

        # ── Step 1: Extract previews ───────────────────────────────────
        cmd = [
            *self._exe_cmd("extract_previews"),
            str(source),
            "--output", str(previews),
            "--max-size", "800",
        ]
        if self.recursive_var.get():
            cmd.append("--recursive")

        if not self._run_step("[1/3] Extrakce náhledů ze RAW souborů", cmd, env, cwd):
            self._set_progress("Chyba v kroku 1")
            self._set_running(False)
            return

        # ── Step 2: Rate with AI ───────────────────────────────────────
        cmd = [
            *self._exe_cmd("rate_with_ai"),
            str(previews),
            "--output", str(ratings),
            "--batch-size", "5",
            "--resume",
        ]
        if not self._run_step("[2/3] Hodnocení pomocí Claude AI", cmd, env, cwd):
            self._set_progress("Chyba v kroku 2")
            self._set_running(False)
            return

        if not ratings.exists() or ratings.stat().st_size < 5:
            self._log("✗  ratings.json chybí nebo je prázdný — hodnocení se nezdařilo.", "err")
            self._set_progress("Chyba v kroku 2")
            self._set_running(False)
            return

        # ── Step 3: Apply ratings to XMP ──────────────────────────────
        cmd = [
            *self._exe_cmd("apply_ratings"),
            str(ratings),
            "--xmp-only",
            "--source-dir", str(source),
        ]
        if self.dry_run_var.get():
            cmd.append("--dry-run")

        if not self._run_step("[3/3] Zápis hodnocení do XMP souborů", cmd, env, cwd):
            self._set_progress("Chyba v kroku 3")
            self._set_running(False)
            return

        self._log("\n✓  Celý workflow dokončen úspěšně!", "ok")
        self._set_progress("✓ Hotovo!")
        self._set_running(False)


# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
