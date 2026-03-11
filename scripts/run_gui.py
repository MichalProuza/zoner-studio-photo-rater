#!/usr/bin/env python3
"""
run_gui.py – grafické rozhraní a hlavní vstupní bod pro ZPS X Photo Rater
"""

import os
import sys
import subprocess
import threading
import configparser
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from pathlib import Path

# Zajištění cest
SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_FROZEN = getattr(sys, "frozen", False)

def run_mode(mode_name):
    # Debug výpis do stdout (zachytí subproces)
    print(f"DEBUG: Vstupuji do režimu: {mode_name}")
    try:
        if mode_name == "extract_previews":
            from scripts import extract_previews as m
        elif mode_name == "rate_with_ai":
            from scripts import rate_with_ai as m
        elif mode_name == "apply_ratings":
            from scripts import apply_ratings as m
        else: return
        m.main()
    except Exception as e:
        print(f"CHYBA v režimu {mode_name}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

MODELS = {
    "anthropic": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001", "claude-3-7-sonnet-20250219"],
    "gemini": ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
}

def ensure_dependencies():
    if _FROZEN: return
    required = {"rawpy": "rawpy", "PIL": "Pillow", "anthropic": "anthropic", "google.genai": "google-genai"}
    for module, package in required.items():
        try:
            if module == "google.genai": from google import genai
            else: __import__(module)
        except ImportError:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            except: pass

def _config_path() -> Path:
    if sys.platform == "win32": base = Path(os.environ.get("APPDATA", Path.home()))
    else: base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "zps-rater" / "config.ini"

def load_config() -> dict:
    config_file = _config_path()
    data = {"provider": "anthropic", "anthropic_key": "", "gemini_key": "", "anthropic_model": MODELS["anthropic"][0], "gemini_model": MODELS["gemini"][0]}
    if config_file.exists():
        try:
            cfg = configparser.ConfigParser()
            cfg.read(config_file, encoding="utf-8")
            data["provider"] = cfg.get("settings", "provider", fallback="anthropic")
            data["anthropic_key"] = cfg.get("anthropic", "api_key", fallback="")
            data["gemini_key"] = cfg.get("gemini", "api_key", fallback="")
            data["anthropic_model"] = cfg.get("anthropic", "model", fallback=MODELS["anthropic"][0])
            data["gemini_model"] = cfg.get("gemini", "model", fallback=MODELS["gemini"][0])
        except: pass
    return data

def save_config(p, ak, gk, am, gm):
    f = _config_path()
    f.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    if f.exists(): cfg.read(f, encoding="utf-8")
    for s in ["settings", "anthropic", "gemini"]:
        if s not in cfg: cfg[s] = {}
    cfg["settings"]["provider"], cfg["anthropic"]["api_key"], cfg["anthropic"]["model"] = p, ak, am
    cfg["gemini"]["api_key"], cfg["gemini"]["model"] = gk, gm
    with open(f, "w", encoding="utf-8") as file: cfg.write(file)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ZPS X Photo Rater")
        self.minsize(720, 650)
        config = load_config()
        self.provider_var = tk.StringVar(value=config["provider"])
        self.anthropic_key_var = tk.StringVar(value=config["anthropic_key"])
        self.gemini_key_var = tk.StringVar(value=config["gemini_key"])
        self.anthropic_model_var = tk.StringVar(value=config["anthropic_model"])
        self.gemini_model_var = tk.StringVar(value=config["gemini_model"])
        self.folder_var, self.recursive_var, self.dry_run_var = tk.StringVar(), tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        self._build_ui()
        self._update_ui_state()
        self.running = False

    def _apply_theme(self):
        s = ttk.Style(self)
        if "vista" in s.theme_names(): s.theme_use("vista")
        s.configure("Run.TButton", font=("", 11, "bold"), padding=6)

    def _build_ui(self):
        self._apply_theme()
        p = {"padx": 12, "pady": 6}
        f_fol = ttk.LabelFrame(self, text="Složka s fotkami (RAW soubory)")
        f_fol.pack(fill="x", **p)
        ttk.Entry(f_fol, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(f_fol, text="Vybrat...", command=self._pick_folder).pack(side="right", padx=(0, 6), pady=6)
        
        f_ai = ttk.LabelFrame(self, text="Nastavení AI")
        f_ai.pack(fill="x", **p)
        ttk.Label(f_ai, text="Poskytovatel:").grid(row=0, column=0, sticky="w", padx=6, pady=5)
        fr = ttk.Frame(f_ai)
        fr.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(fr, text="Anthropic", variable=self.provider_var, value="anthropic", command=self._update_ui_state).pack(side="left", padx=5)
        ttk.Radiobutton(fr, text="Gemini", variable=self.provider_var, value="gemini", command=self._update_ui_state).pack(side="left", padx=5)
        
        ttk.Label(f_ai, text="Model AI:").grid(row=1, column=0, sticky="w", padx=6, pady=5)
        self.cb = ttk.Combobox(f_ai, state="readonly", width=47)
        self.cb.grid(row=1, column=1, sticky="w", padx=6, pady=5)
        
        self.l_ant = ttk.Label(f_ai, text="Anthropic Key:")
        self.l_ant.grid(row=2, column=0, sticky="w", padx=6)
        self.e_ant = ttk.Entry(f_ai, textvariable=self.anthropic_key_var, show="●")
        self.e_ant.grid(row=2, column=1, sticky="ew", padx=6)
        
        self.l_gem = ttk.Label(f_ai, text="Gemini Key:")
        self.l_gem.grid(row=3, column=0, sticky="w", padx=6)
        self.e_gem = ttk.Entry(f_ai, textvariable=self.gemini_key_var, show="●")
        self.e_gem.grid(row=3, column=1, sticky="ew", padx=6)
        
        ttk.Button(f_ai, text="Uložit", command=self._save_settings).grid(row=4, column=1, sticky="e", padx=6, pady=5)
        self.st = ttk.Label(f_ai, text="")
        self.st.grid(row=5, column=1, sticky="e")
        
        f_o = ttk.Frame(self)
        f_o.pack(fill="x", **p)
        ttk.Checkbutton(f_o, text="Rekurzivně", variable=self.recursive_var).pack(side="left", padx=6)
        ttk.Checkbutton(f_o, text="Dry run", variable=self.dry_run_var).pack(side="left", padx=6)
        
        self.btn = ttk.Button(self, text="▶ Spustit", command=self._start, style="Run.TButton")
        self.btn.pack(pady=10)
        
        f_l = ttk.LabelFrame(self, text="Log")
        f_l.pack(fill="both", expand=True, **p)
        self.log = scrolledtext.ScrolledText(f_l, state="disabled", height=15, font=("Courier New", 9))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        for t, c in [("ok", "#007700"), ("err", "#cc0000"), ("hdr", "#0044aa")]: self.log.tag_config(t, foreground=c)

    def _update_ui_state(self):
        prov = self.provider_var.get()
        is_ant = prov == "anthropic"
        self.e_ant.config(state="normal" if is_ant else "disabled")
        self.e_gem.config(state="disabled" if is_ant else "normal")
        models = MODELS[prov]
        self.cb.config(values=models)
        saved = self.anthropic_model_var.get() if is_ant else self.gemini_model_var.get()
        self.cb.set(saved if saved in models else models[0])

    def _save_settings(self):
        p, m = self.provider_var.get(), self.cb.get()
        if p == "anthropic": self.anthropic_model_var.set(m)
        else: self.gemini_model_var.set(m)
        save_config(p, self.anthropic_key_var.get(), self.gemini_key_var.get(), self.anthropic_model_var.get(), self.gemini_model_var.get())
        self.st.config(text="✓ Uloženo")
        self.after(2000, lambda: self.st.config(text=""))

    def _pick_folder(self):
        f = filedialog.askdirectory()
        if f: self.folder_var.set(f)

    def _log(self, t, tag=""):
        self.after(0, lambda: (self.log.config(state="normal"), self.log.insert("end", str(t) + "\n", tag), self.log.see("end"), self.log.config(state="disabled")))

    def _start(self):
        fol, prov, mod = self.folder_var.get().strip(), self.provider_var.get(), self.cb.get()
        key = self.anthropic_key_var.get() if prov == "anthropic" else self.gemini_key_var.get()
        if not fol or not key: return
        self.btn.config(state="disabled")
        threading.Thread(target=self._run_workflow, args=(fol, prov, key, mod), daemon=True).start()

    def _run_step(self, lbl, cmd, env, cwd):
        self._log(f"\n=== {lbl} ===", "hdr")
        try:
            # Na Windows v EXE musíme použít správné příznaky, aby se proces neskryl úplně,
            # pokud chceme vidět výstup v logu.
            proc = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                encoding="utf-8", 
                errors="replace", 
                cwd=cwd, 
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            for line in proc.stdout:
                self._log(line.rstrip())
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            self._log(f"CHYBA: {e}", "err")
            return False

    def _run_workflow(self, fol, prov, key, mod):
        src, env = Path(fol), os.environ.copy()
        env["ANTHROPIC_API_KEY" if prov == "anthropic" else "GEMINI_API_KEY"] = key
        env["PYTHONIOENCODING"] = "utf-8"
        
        if _FROZEN:
            exe_base = [sys.executable]
            cwd = Path(sys.executable).parent
        else:
            exe_base = [sys.executable, sys.argv[0]]
            cwd = PROJECT_ROOT
        
        # Step 1: Previews
        c1 = [*exe_base, "--_mode=extract_previews", str(src), "-o", str(src/"_previews")]
        if self.recursive_var.get(): c1.append("-r")
        if not self._run_step("Extrakce", c1, env, cwd): 
            self._log("\nKrok Extrakce selhal.", "err")
            return self.btn.config(state="normal")
        
        # Step 2: Rate
        c2 = [*exe_base, "--_mode=rate_with_ai", str(src/"_previews"), "-o", str(src/"ratings.json"), "--provider", prov, "--model", mod, "--resume"]
        if not self._run_step("Hodnocení", c2, env, cwd): 
            self._log("\nKrok Hodnocení selhal.", "err")
            return self.btn.config(state="normal")
        
        # Step 3: XMP
        c3 = [*exe_base, "--_mode=apply_ratings", str(src/"ratings.json"), "-s", str(src)]
        if self.dry_run_var.get(): c3.append("-n")
        self._run_step("Zápis XMP", c3, env, cwd)
        
        self._log("\n✔ Všechny kroky dokončeny!", "ok")
        self.btn.config(state="normal")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--_mode="):
        mode = sys.argv[1].split("=")[1]
        sys.argv.pop(1)
        run_mode(mode)
        sys.exit(0)
    
    try:
        ensure_dependencies()
        App().mainloop()
    except Exception as e:
        with open(os.path.join(os.path.expanduser("~"), "zps_rater_crash.txt"), "w") as f:
            import traceback
            traceback.print_exc(file=f)
        sys.exit(1)
