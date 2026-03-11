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

# Zajištění, aby Python viděl kořenový adresář pro importy
SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Importy pro "router" v EXE režimu (nyní relativní/absolutní vůči sys.path)
try:
    import scripts.extract_previews as extract_previews
    import scripts.rate_with_ai as rate_with_ai
    import scripts.apply_ratings as apply_ratings
except ImportError:
    # Fallback pro přímé spuštění ze složky scripts
    import extract_previews as extract_previews
    import rate_with_ai as rate_with_ai
    import apply_ratings as apply_ratings

_FROZEN = getattr(sys, "frozen", False)

MODELS = {
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
    "gemini": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-3.1-flash-lite-preview", "gemini-1.5-flash", "gemini-2.0-flash-lite"]
}

def ensure_dependencies():
    if _FROZEN: return
    required = {"rawpy": "rawpy", "PIL": "Pillow", "anthropic": "anthropic", "google.genai": "google-genai"}
    missing = []
    for module, package in required.items():
        try:
            if module == "google.genai": from google import genai
            else: __import__(module)
        except ImportError: missing.append(package)
    if missing:
        try:
            if "google-genai" in missing: subprocess.call([sys.executable, "-m", "pip", "uninstall", "-y", "google-generativeai"], stdout=subprocess.DEVNULL)
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        except: pass

def _config_path() -> Path:
    if sys.platform == "win32": base = Path(os.environ.get("APPDATA", Path.home()))
    else: base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "zps-rater" / "config.ini"

def load_config() -> dict:
    config_file = _config_path()
    data = {"provider": "anthropic", "anthropic_key": "", "gemini_key": "", "anthropic_model": MODELS["anthropic"][0], "gemini_model": MODELS["gemini"][0]}
    if config_file.exists():
        cfg = configparser.ConfigParser()
        cfg.read(config_file, encoding="utf-8")
        data["provider"] = cfg.get("settings", "provider", fallback="anthropic")
        data["anthropic_key"] = cfg.get("anthropic", "api_key", fallback="")
        data["gemini_key"] = cfg.get("gemini", "api_key", fallback="")
        data["anthropic_model"] = cfg.get("anthropic", "model", fallback=MODELS["anthropic"][0])
        data["gemini_model"] = cfg.get("gemini", "model", fallback=MODELS["gemini"][0])
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
        self.pr_var = tk.StringVar()
        ttk.Label(self, textvariable=self.pr_var, foreground="#0066cc").pack()
        
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
        self.cb.config(values=MODELS[prov])
        self.cb.set(self.anthropic_model_var.get() if is_ant else self.gemini_model_var.get())

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
        self.after(0, lambda: (self.log.config(state="normal"), self.log.insert("end", t + "\n", tag), self.log.see("end"), self.log.config(state="disabled")))

    def _start(self):
        fol, prov, mod = self.folder_var.get().strip(), self.provider_var.get(), self.cb.get()
        key = self.anthropic_key_var.get() if prov == "anthropic" else self.gemini_key_var.get()
        if not fol or not key: return
        self.btn.config(state="disabled")
        threading.Thread(target=self._run_workflow, args=(fol, prov, key, mod), daemon=True).start()

    def _run_step(self, lbl, cmd, env, cwd):
        self._log(f"\n=== {lbl} ===", "hdr")
        try:
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=cwd, env=env, startupinfo=startupinfo)
            for line in proc.stdout: self._log(line.rstrip())
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            self._log(f"Chyba: {e}", "err")
            return False

    def _run_workflow(self, fol, prov, key, mod):
        src, env = Path(fol), os.environ.copy()
        env["ANTHROPIC_API_KEY" if prov == "anthropic" else "GEMINI_API_KEY"] = key
        cwd = Path(sys.executable).parent if _FROZEN else PROJECT_ROOT
        exe_path = [sys.executable]
        
        c1 = [*exe_path, "--_mode=extract_previews", str(src), "-o", str(src/"_previews")]
        if self.recursive_var.get(): c1.append("-r")
        if not self._run_step("Extrakce", c1, env, cwd): return self.btn.config(state="normal")
        
        c2 = [*exe_path, "--_mode=rate_with_ai", str(src/"_previews"), "-o", str(src/"ratings.json"), "--provider", prov, "--model", mod, "--resume"]
        if not self._run_step("Hodnocení", c2, env, cwd): return self.btn.config(state="normal")
        
        c3 = [*exe_path, "--_mode=apply_ratings", str(src/"ratings.json"), "-s", str(src)]
        if self.dry_run_var.get(): c3.append("-n")
        self._run_step("Zápis XMP", c3, env, cwd)
        self._log("\n✔ Hotovo!", "ok")
        self.btn.config(state="normal")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--_mode="):
        mode = sys.argv[1].split("=")[1]
        target_mode = mode
        sys.argv.pop(1)
        if target_mode == "extract_previews": extract_previews.main()
        elif target_mode == "rate_with_ai": rate_with_ai.main()
        elif target_mode == "apply_ratings": apply_ratings.main()
        sys.exit(0)
    
    ensure_dependencies()
    App().mainloop()
