#!/usr/bin/env python3
"""
run_gui.py – grafické rozhraní pro ZPS X Photo Rater
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
    """Vrátí cestu ke konfiguračnímu souboru."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "zps-rater" / "config.ini"


def load_config() -> dict:
    """Načte konfiguraci z ini souboru."""
    config_file = _config_path()
    data = {
        "provider": "anthropic",
        "anthropic_key": "",
        "gemini_key": ""
    }
    if config_file.exists():
        cfg = configparser.ConfigParser()
        cfg.read(config_file, encoding="utf-8")
        data["provider"] = cfg.get("settings", "provider", fallback="anthropic")
        data["anthropic_key"] = cfg.get("anthropic", "api_key", fallback="")
        data["gemini_key"] = cfg.get("gemini", "api_key", fallback="")

    # Fallback na env proměnné
    if not data["anthropic_key"]:
        data["anthropic_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    if not data["gemini_key"]:
        data["gemini_key"] = os.environ.get("GEMINI_API_KEY", "")

    return data


def save_config(provider: str, anthropic_key: str, gemini_key: str) -> None:
    """Uloží konfiguraci do ini souboru."""
    config_file = _config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    if config_file.exists():
        cfg.read(config_file, encoding="utf-8")

    if "settings" not in cfg: cfg["settings"] = {}
    if "anthropic" not in cfg: cfg["anthropic"] = {}
    if "gemini" not in cfg: cfg["gemini"] = {}

    cfg["settings"]["provider"] = provider
    cfg["anthropic"]["api_key"] = anthropic_key
    cfg["gemini"]["api_key"] = gemini_key

    with open(config_file, "w", encoding="utf-8") as f:
        cfg.write(f)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ZPS X Photo Rater")
        self.minsize(700, 600)
        self._apply_theme()

        config_data = load_config()

        self.provider_var = tk.StringVar(value=config_data["provider"])
        self.anthropic_key_var = tk.StringVar(value=config_data["anthropic_key"])
        self.gemini_key_var = tk.StringVar(value=config_data["gemini_key"])
        self.folder_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._toggle_provider_fields()
        self.running = False

    def _apply_theme(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Run.TButton", font=("", 11, "bold"), padding=6)

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        # --- Folder selection ---
        frm_folder = ttk.LabelFrame(self, text="Složka s fotkami (RAW soubory)")
        frm_folder.pack(fill="x", **pad)

        ttk.Entry(frm_folder, textvariable=self.folder_var, width=55).pack(
            side="left", fill="x", expand=True, padx=6, pady=6
        )
        ttk.Button(frm_folder, text="Vybrat...", command=self._pick_folder).pack(
            side="right", padx=(0, 6), pady=6
        )

        # --- AI Settings ---
        frm_ai = ttk.LabelFrame(self, text="Nastavení AI")
        frm_ai.pack(fill="x", **pad)

        # Provider selection
        ttk.Label(frm_ai, text="Poskytovatel:").grid(row=0, column=0, sticky="w", padx=6, pady=5)
        frm_radio = ttk.Frame(frm_ai)
        frm_radio.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(frm_radio, text="Anthropic (Claude)", variable=self.provider_var,
                        value="anthropic", command=self._toggle_provider_fields).pack(side="left", padx=5)
        ttk.Radiobutton(frm_radio, text="Google (Gemini)", variable=self.provider_var,
                        value="gemini", command=self._toggle_provider_fields).pack(side="left", padx=5)

        # Anthropic Key
        self.lbl_anthropic = ttk.Label(frm_ai, text="Anthropic API klíč:")
        self.lbl_anthropic.grid(row=1, column=0, sticky="w", padx=6, pady=2)
        self.ent_anthropic = ttk.Entry(frm_ai, textvariable=self.anthropic_key_var, width=50, show="●")
        self.ent_anthropic.grid(row=1, column=1, sticky="ew", padx=6, pady=2)

        # Gemini Key
        self.lbl_gemini = ttk.Label(frm_ai, text="Gemini API klíč:")
        self.lbl_gemini.grid(row=2, column=0, sticky="w", padx=6, pady=2)
        self.ent_gemini = ttk.Entry(frm_ai, textvariable=self.gemini_key_var, width=50, show="●")
        self.ent_gemini.grid(row=2, column=1, sticky="ew", padx=6, pady=2)

        frm_ai.columnconfigure(1, weight=1)

        ttk.Button(frm_ai, text="Uložit nastavení", command=self._save_settings).grid(
            row=3, column=1, sticky="e", padx=6, pady=5
        )
        self.status_label = ttk.Label(frm_ai, text="", foreground="gray")
        self.status_label.grid(row=4, column=1, sticky="e", padx=6)

        # --- Options ---
        frm_opts = ttk.Frame(self)
        frm_opts.pack(fill="x", **pad)

        ttk.Checkbutton(frm_opts, text="Procházet podsložky rekurzivně", variable=self.recursive_var).pack(side="left", padx=6)
        ttk.Checkbutton(frm_opts, text="Dry run (simulace zápisu)", variable=self.dry_run_var).pack(side="left", padx=6)

        # --- Run button ---
        self.btn_run = ttk.Button(self, text="▶  Spustit celý workflow", command=self._start, style="Run.TButton")
        self.btn_run.pack(pady=10)

        self.progress_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.progress_var, foreground="#0066cc").pack()

        # --- Log ---
        frm_log = ttk.LabelFrame(self, text="Průběh")
        frm_log.pack(fill="both", expand=True, **pad)

        self.log = scrolledtext.ScrolledText(frm_log, state="disabled", height=15, font=("Courier New", 9), wrap="word")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.tag_config("ok", foreground="#007700")
        self.log.tag_config("err", foreground="#cc0000")
        self.log.tag_config("hdr", foreground="#0044aa", font=("Courier New", 9, "bold"))

    def _toggle_provider_fields(self):
        if self.provider_var.get() == "anthropic":
            self.ent_anthropic.config(state="normal")
            self.ent_gemini.config(state="disabled")
        else:
            self.ent_anthropic.config(state="disabled")
            self.ent_gemini.config(state="normal")

    def _save_settings(self):
        save_config(self.provider_var.get(), self.anthropic_key_var.get(), self.gemini_key_var.get())
        self.status_label.config(text="✓ Nastavení uloženo", foreground="#007700")
        self.after(3000, lambda: self.status_label.config(text=""))

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Vyberte složku s fotkami")
        if folder:
            self.folder_var.set(folder)

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
        self.running = running
        self.btn_run.config(state="disabled" if running else "normal")

    def _start(self):
        folder = self.folder_var.get().strip()
        if not folder:
            self._log("⚠  Není vybrána složka!", "err")
            return

        provider = self.provider_var.get()
        api_key = self.anthropic_key_var.get().strip() if provider == "anthropic" else self.gemini_key_var.get().strip()

        if not api_key:
            self._log(f"⚠  Chybí API klíč pro {provider}!", "err")
            return

        self._set_running(True)
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

        thread = threading.Thread(target=self._run_workflow, args=(folder, provider, api_key), daemon=True)
        thread.start()

    def _run_step(self, label: str, cmd: list, env: dict, cwd: Path) -> bool:
        self._set_progress(label)
        self._log(f"\n{'=' * 50}", "hdr")
        self._log(f"  {label}", "hdr")
        self._log(f"{'=' * 50}", "hdr")

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", cwd=cwd, env=env
            )
            for line in proc.stdout:
                self._log(line.rstrip())
            proc.wait()
        except Exception as e:
            self._log(f"✖  Nepodařilo se spustit příkaz: {e}", "err")
            return False

        if proc.returncode == 0:
            self._log("✔  Hotovo", "ok")
            return True
        self._log(f"✖  Krok selhal (exit {proc.returncode})", "err")
        return False

    def _exe_cmd(self, script_name: str) -> list:
        if _FROZEN:
            return [sys.executable, f"--_mode={script_name}"]
        return [sys.executable, str(SCRIPTS_DIR / f"{script_name}.py")]

    def _run_workflow(self, folder: str, provider: str, api_key: str):
        source = Path(folder)
        previews = source / "_previews"
        ratings_file = source / "ratings.json"

        env = os.environ.copy()
        if provider == "anthropic":
            env["ANTHROPIC_API_KEY"] = api_key
        else:
            env["GEMINI_API_KEY"] = api_key
        env["PYTHONUTF8"] = "1"

        cwd = Path(sys.executable).parent if _FROZEN else PROJECT_ROOT

        # Step 1: Previews
        cmd1 = [*self._exe_cmd("extract_previews"), str(source), "--output", str(previews), "--max-size", "800"]
        if self.recursive_var.get(): cmd1.append("--recursive")

        if not self._run_step("[1/3] Extrakce náhledů", cmd1, env, cwd):
            self._set_progress("Chyba v kroku 1")
            self._set_running(False)
            return

        # Step 2: Rating
        cmd2 = [*self._exe_cmd("rate_with_ai"), str(previews), "--output", str(ratings_file),
                "--provider", provider, "--batch-size", "10", "--resume"]
        if not self._run_step(f"[2/3] Hodnocení pomocí {provider}", cmd2, env, cwd):
            self._set_progress("Chyba v kroku 2")
            self._set_running(False)
            return

        # Step 3: XMP
        cmd3 = [*self._exe_cmd("apply_ratings"), str(ratings_file), "--source-dir", str(source)]
        if self.dry_run_var.get(): cmd3.append("--dry-run")

        if not self._run_step("[3/3] Zápis do XMP", cmd3, env, cwd):
            self._set_progress("Chyba v kroku 3")
            self._set_running(False)
            return

        self._log("\n✔  Celý workflow dokončen úspěšně!", "ok")
        self._set_progress("✔ Hotovo!")
        self._set_running(False)


if __name__ == "__main__":
    app = App()
    app.mainloop()
