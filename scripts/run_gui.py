#!/usr/bin/env python3
"""
run_gui.py – jednoduchý průvodce (wizard) pro ZPS X Photo Rater

Tři kroky:
  1. Výběr složky s RAW fotkami
  2. Nastavení AI (poskytovatel, model, API klíč)
  3. Souhrn, spuštění a průběh s logem

Nastavení se ukládá automaticky (APPDATA/zps-rater/config.ini,
na Linuxu ~/.config/zps-rater/config.ini).
"""

import configparser
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, scrolledtext, ttk

# Zajištění cest pro import scripts.* při spuštění jako skript
SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_FROZEN = getattr(sys, "frozen", False)

MODELS = {
    "anthropic": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001", "claude-3-7-sonnet-20250219"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash-001", "gemini-2.0-flash-lite"],
}
PROVIDER_LABELS = {"anthropic": "Anthropic (Claude)", "gemini": "Google (Gemini)"}
API_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
API_KEY_HINT = {
    "anthropic": "Klíč získáš na console.anthropic.com",
    "gemini": "Klíč získáš na aistudio.google.com",
}

# Průběh workflow: extrakce 0–15 %, hodnocení 15–90 %, XMP 90–100 %
PROGRESS_AFTER_EXTRACT = 15
PROGRESS_AFTER_RATE = 90


def run_mode(mode_name):
    """Spustí dílčí skript (interní režim pro subprocesy GUI)."""
    modes = {
        "extract_previews": "scripts.extract_previews",
        "rate_with_ai": "scripts.rate_with_ai",
        "apply_ratings": "scripts.apply_ratings",
    }
    module_name = modes.get(mode_name)
    if not module_name:
        print(f"Neznámý interní režim: {mode_name}", file=sys.stderr)
        sys.exit(1)
    try:
        import importlib
        importlib.import_module(module_name).main()
    except Exception as e:
        print(f"CHYBA v režimu {mode_name}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def ensure_dependencies():
    """Při spuštění ze zdrojáků doinstaluje chybějící knihovny."""
    if _FROZEN:
        return
    required = {"rawpy": "rawpy", "PIL": "Pillow", "anthropic": "anthropic", "google.genai": "google-genai"}
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            except subprocess.CalledProcessError:
                print(f"Nepodařilo se nainstalovat {package}", file=sys.stderr)


def _config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "zps-rater" / "config.ini"


def load_config() -> dict:
    data = {
        "provider": "anthropic",
        "anthropic_key": "", "gemini_key": "",
        "anthropic_model": MODELS["anthropic"][0],
        "gemini_model": MODELS["gemini"][0],
    }
    config_file = _config_path()
    if config_file.exists():
        try:
            cfg = configparser.ConfigParser()
            cfg.read(config_file, encoding="utf-8")
            data["provider"] = cfg.get("settings", "provider", fallback=data["provider"])
            data["anthropic_key"] = cfg.get("anthropic", "api_key", fallback="")
            data["gemini_key"] = cfg.get("gemini", "api_key", fallback="")
            data["anthropic_model"] = cfg.get("anthropic", "model", fallback=data["anthropic_model"])
            data["gemini_model"] = cfg.get("gemini", "model", fallback=data["gemini_model"])
        except (configparser.Error, OSError):
            pass
    if data["provider"] not in MODELS:
        data["provider"] = "anthropic"
    return data


def save_config(data: dict) -> None:
    config_file = _config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    if config_file.exists():
        cfg.read(config_file, encoding="utf-8")
    for section in ("settings", "anthropic", "gemini"):
        if section not in cfg:
            cfg[section] = {}
    cfg["settings"]["provider"] = data["provider"]
    cfg["anthropic"]["api_key"] = data["anthropic_key"]
    cfg["anthropic"]["model"] = data["anthropic_model"]
    cfg["gemini"]["api_key"] = data["gemini_key"]
    cfg["gemini"]["model"] = data["gemini_model"]
    with open(config_file, "w", encoding="utf-8") as f:
        cfg.write(f)


class App(tk.Tk):
    """Třístupňový průvodce: složka → AI → spuštění."""

    STEP_TITLES = ["Složka s fotkami", "Nastavení AI", "Spuštění"]

    def __init__(self):
        super().__init__()
        self.title("ZPS X Photo Rater")
        self.minsize(640, 560)
        self.running = False
        self.step = 0

        cfg = load_config()
        self.provider_var = tk.StringVar(value=cfg["provider"])
        self.key_vars = {
            "anthropic": tk.StringVar(value=cfg["anthropic_key"]),
            "gemini": tk.StringVar(value=cfg["gemini_key"]),
        }
        self.model_vars = {
            "anthropic": tk.StringVar(value=cfg["anthropic_model"]),
            "gemini": tk.StringVar(value=cfg["gemini_model"]),
        }
        self.folder_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.progress_var = tk.DoubleVar(value=0)

        self._apply_theme()
        self._build_layout()
        self.step_frames = [
            self._build_step_folder(),
            self._build_step_ai(),
            self._build_step_run(),
        ]
        self._show_step(0)

    # ------------------------------------------------------------- vzhled

    def _apply_theme(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("", 13, "bold"))
        style.configure("Step.TLabel", foreground="#666666")
        style.configure("Error.TLabel", foreground="#cc0000")
        style.configure("Next.TButton", font=("", 10, "bold"), padding=6)

    def _build_layout(self):
        header = ttk.Frame(self, padding=(14, 12, 14, 4))
        header.pack(fill="x")
        self.step_label = ttk.Label(header, text="", style="Step.TLabel")
        self.step_label.pack(anchor="w")
        self.title_label = ttk.Label(header, text="", style="Title.TLabel")
        self.title_label.pack(anchor="w")
        ttk.Separator(self).pack(fill="x", padx=14, pady=(6, 0))

        self.container = ttk.Frame(self, padding=14)
        self.container.pack(fill="both", expand=True)

        footer = ttk.Frame(self, padding=(14, 4, 14, 12))
        footer.pack(fill="x", side="bottom")
        self.error_label = ttk.Label(footer, text="", style="Error.TLabel")
        self.error_label.pack(side="left")
        self.next_btn = ttk.Button(footer, text="Pokračovat ›", command=self._next, style="Next.TButton")
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(footer, text="‹ Zpět", command=self._back)
        self.back_btn.pack(side="right", padx=(0, 8))

    # ----------------------------------------------------------- kroky UI

    def _build_step_folder(self) -> ttk.Frame:
        frame = ttk.Frame(self.container)
        ttk.Label(frame, text="Vyber složku, ve které jsou RAW fotky k ohodnocení.").pack(anchor="w", pady=(0, 10))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Vybrat…", command=self._pick_folder).pack(side="right", padx=(8, 0))
        ttk.Checkbutton(frame, text="Včetně podsložek (rekurzivně)", variable=self.recursive_var).pack(anchor="w", pady=(10, 0))
        ttk.Label(
            frame,
            text="Podporované formáty: RAF, CR2, CR3, NEF, ARW, DNG, ORF, SRW",
            style="Step.TLabel",
        ).pack(anchor="w", pady=(14, 0))
        return frame

    def _build_step_ai(self) -> ttk.Frame:
        frame = ttk.Frame(self.container)
        ttk.Label(frame, text="Vyber AI poskytovatele a zadej svůj API klíč.").pack(anchor="w", pady=(0, 10))

        row = ttk.Frame(frame)
        row.pack(anchor="w")
        for value, label in PROVIDER_LABELS.items():
            ttk.Radiobutton(row, text=label, variable=self.provider_var, value=value,
                            command=self._on_provider_change).pack(side="left", padx=(0, 14))

        grid = ttk.Frame(frame)
        grid.pack(fill="x", pady=(14, 0))
        grid.columnconfigure(1, weight=1)

        ttk.Label(grid, text="Model:").grid(row=0, column=0, sticky="w", pady=4)
        self.model_cb = ttk.Combobox(grid, state="readonly")
        self.model_cb.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(grid, text="API klíč:").grid(row=1, column=0, sticky="w", pady=4)
        self.key_entry = ttk.Entry(grid, show="●")
        self.key_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=4)

        self.key_hint = ttk.Label(frame, text="", style="Step.TLabel")
        self.key_hint.pack(anchor="w", pady=(8, 0))

        self._on_provider_change()
        return frame

    def _build_step_run(self) -> ttk.Frame:
        frame = ttk.Frame(self.container)

        summary = ttk.LabelFrame(frame, text="Souhrn", padding=8)
        summary.pack(fill="x")
        self.summary_label = ttk.Label(summary, text="", justify="left")
        self.summary_label.pack(anchor="w")

        ttk.Checkbutton(frame, text="Dry run (jen zobrazit, nic nezapisovat)",
                        variable=self.dry_run_var).pack(anchor="w", pady=(8, 0))

        self.status_label = ttk.Label(frame, text="Připraveno ke spuštění.")
        self.status_label.pack(anchor="w", pady=(10, 2))
        ttk.Progressbar(frame, variable=self.progress_var, maximum=100).pack(fill="x")

        log_frame = ttk.LabelFrame(frame, text="Log", padding=4)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.log = scrolledtext.ScrolledText(log_frame, state="disabled", height=12, font=("Courier New", 9))
        self.log.pack(fill="both", expand=True)
        for tag, color in [("ok", "#007700"), ("err", "#cc0000"), ("hdr", "#0044aa")]:
            self.log.tag_config(tag, foreground=color)
        return frame

    # ---------------------------------------------------------- navigace

    def _show_step(self, index: int):
        self.step_frames[self.step].pack_forget()
        self.step = index
        self.step_frames[index].pack(fill="both", expand=True)
        self.step_label.config(text=f"Krok {index + 1} z {len(self.STEP_TITLES)}")
        self.title_label.config(text=self.STEP_TITLES[index])
        self.error_label.config(text="")
        self.back_btn.config(state="normal" if index > 0 and not self.running else "disabled")
        self.next_btn.config(text="▶ Spustit" if index == len(self.STEP_TITLES) - 1 else "Pokračovat ›")
        if index == 2:
            self._refresh_summary()

    def _back(self):
        if not self.running and self.step > 0:
            self._show_step(self.step - 1)

    def _next(self):
        if self.step == 0:
            folder = self.folder_var.get().strip()
            if not folder or not Path(folder).is_dir():
                self._show_error("Vyber existující složku s fotkami.")
                return
            self._show_step(1)
        elif self.step == 1:
            prov = self.provider_var.get()
            self.model_vars[prov].set(self.model_cb.get())
            if not self.key_vars[prov].get().strip():
                self._show_error("Zadej API klíč.")
                return
            self._save_settings()
            self._show_step(2)
        else:
            self._start()

    def _show_error(self, message: str):
        self.error_label.config(text=message)

    def _pick_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)

    def _on_provider_change(self):
        prov = self.provider_var.get()
        models = MODELS[prov]
        if self.model_vars[prov].get() not in models:
            self.model_vars[prov].set(models[0])
        self.model_cb.config(values=models, textvariable=self.model_vars[prov])
        self.key_entry.config(textvariable=self.key_vars[prov])
        self.key_hint.config(text=API_KEY_HINT[prov])

    def _save_settings(self):
        save_config({
            "provider": self.provider_var.get(),
            "anthropic_key": self.key_vars["anthropic"].get(),
            "gemini_key": self.key_vars["gemini"].get(),
            "anthropic_model": self.model_vars["anthropic"].get(),
            "gemini_model": self.model_vars["gemini"].get(),
        })

    def _refresh_summary(self):
        prov = self.provider_var.get()
        lines = [
            f"Složka:        {self.folder_var.get()}",
            f"Poskytovatel:  {PROVIDER_LABELS[prov]}",
            f"Model:         {self.model_vars[prov].get()}",
            f"Podsložky:     {'ano' if self.recursive_var.get() else 'ne'}",
        ]
        self.summary_label.config(text="\n".join(lines))

    # ---------------------------------------------------------- spuštění

    def _log(self, text, tag=""):
        def append():
            self.log.config(state="normal")
            self.log.insert("end", str(text) + "\n", tag)
            self.log.see("end")
            self.log.config(state="disabled")
        self.after(0, append)

    def _set_status(self, text: str, progress: float | None = None):
        def update():
            self.status_label.config(text=text)
            if progress is not None:
                self.progress_var.set(progress)
        self.after(0, update)

    def _start(self):
        if self.running:
            return
        self.running = True
        self.back_btn.config(state="disabled")
        self.next_btn.config(state="disabled")
        self.progress_var.set(0)
        prov = self.provider_var.get()
        threading.Thread(
            target=self._run_workflow,
            args=(self.folder_var.get().strip(), prov, self.key_vars[prov].get().strip(), self.model_vars[prov].get()),
            daemon=True,
        ).start()

    def _finish(self, success: bool):
        def update():
            self.running = False
            self.back_btn.config(state="normal")
            self.next_btn.config(state="normal")
        self.after(0, update)
        if success:
            self._set_status("✔ Hotovo!", 100)
            self._log("\n✔ Všechny kroky dokončeny!", "ok")
        else:
            self._set_status("Workflow selhal — viz log.")

    def _run_step(self, label, cmd, env, cwd, on_line=None) -> bool:
        self._log(f"\n=== {label} ===", "hdr")
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
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for line in proc.stdout:
                line = line.rstrip()
                self._log(line)
                if on_line:
                    on_line(line)
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            self._log(f"CHYBA: {e}", "err")
            return False

    def _run_workflow(self, folder, prov, key, model):
        src = Path(folder)
        env = os.environ.copy()
        env[API_KEY_ENV[prov]] = key
        env["PYTHONIOENCODING"] = "utf-8"

        if _FROZEN:
            exe_base = [sys.executable]
            cwd = Path(sys.executable).parent
        else:
            exe_base = [sys.executable, sys.argv[0]]
            cwd = PROJECT_ROOT

        previews = src / "_previews"
        ratings = src / "ratings.json"

        # 1/3 — extrakce náhledů
        self._set_status("Krok 1/3: Extrakce náhledů…", 2)
        cmd = [*exe_base, "--_mode=extract_previews", str(src), "-o", str(previews)]
        if self.recursive_var.get():
            cmd.append("-r")
        if not self._run_step("Extrakce náhledů", cmd, env, cwd):
            self._log("\nKrok Extrakce selhal.", "err")
            return self._finish(False)

        # 2/3 — AI hodnocení (průběh podle řádků "[n/m] …")
        self._set_status("Krok 2/3: AI hodnocení…", PROGRESS_AFTER_EXTRACT)

        def rating_progress(line):
            m = re.search(r"\[(\d+)/(\d+)\]", line)
            if m and int(m.group(2)) > 0:
                done, total = int(m.group(1)), int(m.group(2))
                span = PROGRESS_AFTER_RATE - PROGRESS_AFTER_EXTRACT
                self._set_status(
                    f"Krok 2/3: AI hodnocení… ({done}/{total})",
                    PROGRESS_AFTER_EXTRACT + span * done / total,
                )

        cmd = [*exe_base, "--_mode=rate_with_ai", str(previews), "-o", str(ratings),
               "--provider", prov, "--model", model, "--resume"]
        if not self._run_step("AI hodnocení", cmd, env, cwd, on_line=rating_progress):
            self._log("\nKrok Hodnocení selhal.", "err")
            return self._finish(False)

        # 3/3 — zápis XMP
        self._set_status("Krok 3/3: Zápis hodnocení do XMP…", PROGRESS_AFTER_RATE)
        cmd = [*exe_base, "--_mode=apply_ratings", str(ratings), "--xmp-only", "--source-dir", str(src)]
        if self.dry_run_var.get():
            cmd.append("-n")
        if not self._run_step("Zápis XMP", cmd, env, cwd):
            self._log("\nKrok Zápis XMP selhal.", "err")
            return self._finish(False)

        self._finish(True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--_mode="):
        mode = sys.argv[1].split("=", 1)[1]
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        run_mode(mode)
        sys.exit(0)

    try:
        ensure_dependencies()
        App().mainloop()
    except Exception:
        import traceback
        with open(os.path.join(os.path.expanduser("~"), "zps_rater_crash.txt"), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        sys.exit(1)
