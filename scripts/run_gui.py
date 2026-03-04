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
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent


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
        self.api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self._api_entry = ttk.Entry(
            frm_opts, textvariable=self.api_key_var, width=48, show="•"
        )
        self._api_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=5)

        ttk.Label(frm_opts, text="(nebo nastav env ANTHROPIC_API_KEY)", foreground="gray").grid(
            row=1, column=1, sticky="w", padx=6
        )

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

    def _run_step(self, label: str, cmd: list, env: dict) -> bool:
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
                cwd=PROJECT_ROOT,
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

    def _run_workflow(self, folder: str, api_key: str):
        source = Path(folder)
        previews = source / "_previews"
        ratings = source / "ratings.json"
        python = sys.executable

        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = api_key
        env["PYTHONUTF8"] = "1"  # Windows: všechny subprocesy píší UTF-8 do stdout

        # ── Step 1: Extract previews ───────────────────────────────────
        cmd = [
            python, str(SCRIPTS_DIR / "extract_previews.py"),
            str(source),
            "--output", str(previews),
            "--max-size", "800",
        ]
        if self.recursive_var.get():
            cmd.append("--recursive")

        if not self._run_step("[1/3] Extrakce náhledů ze RAW souborů", cmd, env):
            self._set_progress("Chyba v kroku 1")
            self._set_running(False)
            return

        # ── Step 2: Rate with AI ───────────────────────────────────────
        cmd = [
            python, str(SCRIPTS_DIR / "rate_with_ai.py"),
            str(previews),
            "--output", str(ratings),
            "--batch-size", "20",
            "--resume",
        ]
        if not self._run_step("[2/3] Hodnocení pomocí Claude AI", cmd, env):
            self._set_progress("Chyba v kroku 2")
            self._set_running(False)
            return

        # ── Step 3: Apply ratings to XMP ──────────────────────────────
        cmd = [
            python, str(SCRIPTS_DIR / "apply_ratings.py"),
            str(ratings),
            "--xmp-only",
            "--source-dir", str(source),
        ]
        if self.dry_run_var.get():
            cmd.append("--dry-run")

        if not self._run_step("[3/3] Zápis hodnocení do XMP souborů", cmd, env):
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
