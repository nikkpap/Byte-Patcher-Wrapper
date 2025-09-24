import os
import sys
import importlib.util
import hashlib
import tkinter as tk
import subprocess, time, platform, tempfile, shutil, stat
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from types import ModuleType
from typing import Dict, Optional, Tuple, List

APP_NAME = "Byte Patcher Wrapper"
APP_VER  = "1.3"

# ---------- helpers ----------
def _import_from_path(path: str, module_name: str) -> Optional[ModuleType]:
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        return mod
    except Exception as e:
        messagebox.showerror("Import error", f"Failed to import core module:\n{path}\n\n{e}")
        return None

def _auto_load_core() -> Tuple[Optional[ModuleType], str]:
    here = os.path.abspath(os.path.dirname(__file__))
    candidate = os.path.join(here, "patch.py")
    if os.path.isfile(candidate):
        mod = _import_from_path(candidate, "patch_core")
        if mod:
            return mod, candidate
    return None, ""

def _extract_mapping(mod: ModuleType) -> Optional[Dict[int, int]]:
    if not hasattr(mod, "offsets_and_values"):
        return None
    raw = getattr(mod, "offsets_and_values")
    if not isinstance(raw, dict):
        return None
    m: Dict[int, int] = {}
    for k, v in raw.items():
        off = int(k, 16) if isinstance(k, str) and k.lower().startswith("0x") else int(k)
        val = int(v)
        if not (0 <= val <= 255):
            raise ValueError(f"Byte out of range at 0x{off:X}: {val}")
        m[off] = val
    return m

def _safe_backup(filepath: str) -> str:
    folder = os.path.dirname(filepath)
    base   = os.path.basename(filepath)
    bak    = os.path.join(folder, base + ".bak")
    if not os.path.exists(bak):
        with open(filepath, "rb") as fi, open(bak, "wb") as fo:
            fo.write(fi.read())
        return bak
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_ts = os.path.join(folder, f"{base}.bak.{ts}")
    with open(filepath, "rb") as fi, open(bak_ts, "wb") as fo:
        fo.write(fi.read())
    return bak_ts

def _apply_local_patch(original: bytes, mapping: Dict[int, int]) -> Tuple[bytes, int]:
    ba = bytearray(original)
    changed = 0
    for off, val in mapping.items():
        if off < len(ba) and ba[off] != val:
            ba[off] = val
            changed += 1
    return bytes(ba), changed

def _sha256_hex(data: bytes) -> str:
    import hashlib as _hh
    h = _hh.sha256(); h.update(data); return h.hexdigest()

def _preview_regions(data: bytes, mapping: Dict[int,int], context: int = 8) -> List[str]:
    lines: List[str] = []
    shown = 0
    for off in sorted(mapping.keys()):
        if shown >= 50: break
        if off < len(data):
            before = data[off]
            after  = mapping[off]
            start  = max(0, off - context)
            end    = min(len(data), off + context + 1)
            ctx    = " ".join(f"{b:02X}" for b in data[start:end])
            lines.append(f"0x{off:08X} : {before:02X} -> {after:02X}   ctx: {ctx[:90]}")
        else:
            lines.append(f"0x{off:08X} : OUT OF RANGE -> {mapping[off]:02X}")
        shown += 1
    return lines

# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VER}")
        self.geometry("820x520")
        self.minsize(680, 420)
        self._center()

        self.core_mod: Optional[ModuleType] = None
        self.core_path: str = ""
        self.mapping: Optional[Dict[int,int]] = None

        self._build_ui()
        self._auto_core_load()

    def _center(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        pad = 10
        main = ttk.Frame(self, padding=pad)
        main.pack(fill="both", expand=True)

        # Core row (auto)
        core_row = ttk.Frame(main)
        core_row.pack(fill="x")
        ttk.Label(core_row, text="Core script (auto):").grid(row=0, column=0, sticky="w")
        self.core_entry = ttk.Entry(core_row)
        self.core_entry.grid(row=0, column=1, sticky="ew", padx=6)
        core_row.columnconfigure(1, weight=1)

        # Green tick / red cross
        self.core_tick = ttk.Label(core_row, text="✗", foreground="#C62828")
        self.core_tick.grid(row=0, column=2, sticky="e", padx=(6,0))

        # Input row (.exe only)
        in_row = ttk.Frame(main)
        in_row.pack(fill="x", pady=(8,0))
        ttk.Label(in_row, text="Input .exe:").grid(row=0, column=0, sticky="w")
        self.in_entry = ttk.Entry(in_row)
        self.in_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(in_row, text="Browse...", command=self._browse_input).grid(row=0, column=2, sticky="e")
        in_row.columnconfigure(1, weight=1)

        # Middle: preview + info
        mid = ttk.Frame(main)
        mid.pack(fill="both", expand=True, pady=(8,8))

        left = ttk.Frame(mid)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Preview of first offsets (before → after):").pack(anchor="w")
        self.preview = tk.Listbox(left, font=("Consolas", 10))
        self.preview.pack(fill="both", expand=True, padx=(0,6), pady=(4,0))

        right = ttk.Frame(mid, width=320)
        right.pack(side="right", fill="y")
        ttk.Label(right, text="Checksums / details:").pack(anchor="w")
        self.info = tk.Text(right, height=16, wrap="word")
        self.info.pack(fill="both", expand=True)
        self.info.configure(state="disabled")

        # Bottom buttons
        bot = ttk.Frame(main)
        bot.pack(fill="x")
        self.btn_preview = ttk.Button(bot, text="Refresh Preview", command=self._refresh_preview, state="disabled")
        self.btn_preview.pack(side="left")
        self.btn_apply = ttk.Button(bot, text="Apply Patch", command=self._apply, state="disabled")
        self.btn_apply.pack(side="left", padx=6)
        ttk.Button(bot, text="Open Output Folder", command=self._open_out_folder).pack(side="right")

        # Log
        ttk.Label(main, text="Log:").pack(anchor="w")
        self.log = tk.Text(main, height=6, wrap="none")
        self.log.pack(fill="both", expand=False, pady=(4,0))
        self.log.configure(state="disabled", font=("Consolas", 10))

        # Menu (Help/About)
        m = tk.Menu(self)
        helpm = tk.Menu(m, tearoff=0)
        helpm.add_command(label="Instructions\tF1", accelerator="F1", command=self._show_help)
        helpm.add_separator()
        helpm.add_command(label="About", command=self._show_about)
        m.add_cascade(label="Help", menu=helpm)
        self.config(menu=m)
        self.bind("<F1>", lambda e: self._show_help())

    # ----- UI helpers -----
    def _set_tick(self, ok: bool):
        if ok:
            self.core_tick.configure(text="✓", foreground="#2E7D32")  # green
        else:
            self.core_tick.configure(text="✗", foreground="#C62828")  # red

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_info(self, txt: str):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("end", txt)
        self.info.configure(state="disabled")

    def _kill_sublime_processes(self, timeout=10):
        """
        Cross-platform force-kill for Sublime processes.
        Windows: taskkill /F /IM ...
        macOS/Linux: pkill / killall (best-effort), then wait until gone.
        """
        self._log("Closing Sublime processes...")

        names_win = ["sublime_text.exe", "plugin_host.exe", "sublime_crash_handler.exe"]
        names_posix = ["sublime_text", "plugin_host"]

        is_windows = platform.system().lower().startswith("win")
        creationflags = 0
        if is_windows and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            if is_windows:
                # Try explicit image names
                for nm in names_win:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/IM", nm],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=creationflags, check=False
                        )
                    except Exception:
                        pass
                # Wildcard sweep via PowerShell
                try:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                         "Get-Process sublime* -ErrorAction SilentlyContinue | Stop-Process -Force"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=creationflags, check=False
                    )
                except Exception:
                    pass

                def any_running():
                    try:
                        out = subprocess.check_output(["tasklist"], creationflags=creationflags)\
                                        .decode(errors="ignore").lower()
                        return any(nm in out for nm in [n.lower() for n in names_win])
                    except Exception:
                        return False

            else:
                # macOS/Linux
                # Try pkill by exact names
                for nm in names_posix:
                    try:
                        subprocess.run(["pkill", "-f", nm],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                    except Exception:
                        pass
                # Fallback to killall
                for nm in names_posix:
                    try:
                        subprocess.run(["killall", "-9", nm],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                    except Exception:
                        pass

                def any_running():
                    try:
                        out = subprocess.check_output(["ps", "aux"]).decode(errors="ignore").lower()
                        return any(nm in out for nm in names_posix)
                    except Exception:
                        return False

            # Wait until gone or timeout
            start = time.time()
            while time.time() - start < timeout:
                if not any_running():
                    self._log("Sublime processes terminated.")
                    return
                time.sleep(0.3)

            self._log("Warning: some Sublime processes may still be running (timeout reached).")

        except Exception as e:
            self._log(f"Process-kill error (continuing anyway): {e}")

    # ----- core loading -----
    def _auto_core_load(self):
        mod, path = _auto_load_core()
        if not mod:
            self.core_entry.delete(0, "end")
            self.core_entry.insert(0, "<patch.py not found in this folder>")
            self._set_tick(False)
            self._log("patch.py not found. Place subpatcher_gui.pyw and patch.py in the same folder.")
            return

        self.core_mod = mod
        self.core_path = path
        self.core_entry.delete(0, "end")
        self.core_entry.insert(0, path)
        self._set_tick(True)
        self._log(f"Loaded core: {path}")

        try:
            self.mapping = _extract_mapping(mod)
            self._log(f"Mapping entries: {len(self.mapping) if self.mapping else 0}")
        except Exception as e:
            self.mapping = None
            self._log(f"Error reading offsets_and_values: {e}")

        # enable preview/apply when core is ready
        self.btn_preview.configure(state="normal")
        # Apply stays disabled until a valid input .exe is chosen

    # ----- input / preview -----
    def _browse_input(self):
        p = filedialog.askopenfilename(
            title="Select input .exe",
            filetypes=[("Executable", "*.exe")]
        )
        if not p:
            return
        if not p.lower().endswith(".exe"):
            messagebox.showwarning("Invalid file", "Please select a .exe file.")
            return

        self.in_entry.delete(0, "end")
        self.in_entry.insert(0, p)
        self.btn_apply.configure(state="normal")
        self._refresh_preview()

    def _refresh_preview(self):
        if not self.core_mod:
            messagebox.showwarning("No core", "Place patch.py in the same folder.")
            return
        if not self.mapping:
            messagebox.showwarning("No mapping", "Core has no usable offsets_and_values.")
            return

        inp = self.in_entry.get().strip()
        if not inp or not os.path.isfile(inp):
            messagebox.showwarning("No input", "Choose a valid input .exe first.")
            return

        try:
            with open(inp, "rb") as f:
                data = f.read()
        except Exception as e:
            messagebox.showerror("Read error", f"Failed to read input:\n{e}")
            return

        self.preview.delete(0, "end")
        for line in _preview_regions(data, self.mapping, context=8):
            self.preview.insert("end", line)

        patched_preview, changed = _apply_local_patch(data, self.mapping)
        info = [
            f"Input: {inp}",
            f"Size: {len(data)} bytes",
            f"SHA256 original: {_sha256_hex(data)}",
            f"SHA256 (after patch preview): {_sha256_hex(patched_preview)}",
            "",
            f"Mapping entries: {len(self.mapping)}",
            f"Offsets that would change: {changed}",
        ]
        self._set_info("\n".join(info))
        self._log(f"Preview refreshed. Would change {changed} byte(s).")

    # ----- apply -----

    def _apply(self):
        if not self.core_mod:
            messagebox.showwarning("No core", "patch.py not loaded.")
            return

        inp = self.in_entry.get().strip()
        if not inp or not os.path.isfile(inp):
            messagebox.showwarning("No input", "Choose a valid executable file.")
            return

        # 1) Ensure target app is not locking the file
        try:
            self._kill_sublime_processes(timeout=10)
        except Exception as e:
            self._log(f"Kill warning: {e}")

        # 2) Backup original (same behavior)
        try:
            bak = _safe_backup(inp)
            self._log(f"Backup created: {bak}")
        except Exception as e:
            messagebox.showerror("Backup error", f"Failed to create backup:\n{e}")
            return

        # 3) Prepare temp output alongside the original (same filesystem for atomic replace)
        folder = os.path.dirname(inp)
        base, ext = os.path.splitext(os.path.basename(inp))
        # Keep original extension even on macOS/Linux; we are replacing the original file path.
        fd, out_temp = tempfile.mkstemp(prefix=f"{base}_patched_", suffix=ext or "", dir=folder)
        os.close(fd)  # We'll reopen normally
        try:
            # make writable just in case
            os.chmod(out_temp, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        except Exception:
            pass

        used_core = False
        core_failed = None

        # 4) Try core patch_exe() to write directly to temp file
        if hasattr(self.core_mod, "patch_exe") and callable(getattr(self.core_mod, "patch_exe")):
            try:
                self.core_mod.patch_exe(os.path.normpath(inp), os.path.normpath(out_temp))
                self._log(f"core patch_exe() wrote: {out_temp}")
                used_core = True
            except Exception as e:
                core_failed = e
                self._log(f"core patch_exe() failed, will fallback: {e!r}")

        # 5) Fallback: apply mapping in-memory and write temp
        if not used_core:
            if not self.mapping:
                messagebox.showerror("No mapping", "No offsets_and_values found to apply.")
                # Clean temp
                try:
                    os.remove(out_temp)
                except Exception:
                    pass
                return
            try:
                with open(inp, "rb") as f:
                    original = f.read()
                patched_bytes, changed = _apply_local_patch(original, self.mapping)
                with open(out_temp, "wb") as f:
                    f.write(patched_bytes)
                self._log(f"Patched (fallback) to temp. Bytes modified: {changed}")
            except Exception as e:
                msg = f"Failed to prepare/write temp output:\n{e}"
                if core_failed:
                    msg += f"\n\n(Original core error: {core_failed})"
                messagebox.showerror("Patch error", msg)
                try:
                    os.remove(out_temp)
                except Exception:
                    pass
                return

        # 6) Preserve original permissions where possible, then atomic replace
        try:
            try:
                st = os.stat(inp)
                os.chmod(out_temp, stat.S_IMODE(st.st_mode))
            except Exception:
                pass

            # Atomic-ish replace on same filesystem
            os.replace(out_temp, inp)
            self._log(f"Replaced original file: {inp}")

            # On Unix, ensure executable bit remains (especially if mapping fallback wrote without it)
            if platform.system() != "Windows":
                try:
                    os.chmod(inp, (st.st_mode if 'st' in locals() else (stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR)))
                except Exception:
                    pass

        except PermissionError as pe:
            messagebox.showerror(
                "Replace error",
                "Failed to replace the original binary.\n\n"
                f"{pe}\n\n"
                "Tips:\n"
                "• Ensure the app is fully closed (the wrapper tried to kill it).\n"
                "• On Windows/macOS/Linux, you may need elevated permissions for system locations "
                "(e.g., 'C:\\Program Files', '/Applications', '/usr/bin').\n"
                "• Copy the file to a writable folder, patch it, then move it back with admin rights."
            )
            # Clean temp if still present
            try:
                if os.path.exists(out_temp):
                    os.remove(out_temp)
            except Exception:
                pass
            return
        except Exception as e:
            messagebox.showerror("Replace error", f"Failed to replace original with patched temp:\n{e}")
            try:
                if os.path.exists(out_temp):
                    os.remove(out_temp)
            except Exception:
                pass
            return

        # 7) Final checksum & info
        try:
            with open(inp, "rb") as f:
                newb = f.read()
            details = (
                "Patched and replaced successfully.\n"
                f"File: {inp}\n"
                f"SHA256 (new): {_sha256_hex(newb)}"
            )
            messagebox.showinfo("Done", details)
            self._set_info(details)
        except Exception:
            pass

    def _open_out_folder(self):
        inp = self.in_entry.get().strip()
        if not inp:
            return
        base, ext = os.path.splitext(os.path.abspath(inp))
        folder = os.path.dirname(base)
        if os.name == "nt":
            os.startfile(folder)
        elif sys.platform == "darwin":
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')

    # ----- help/about -----
    def _show_help(self):
        dlg = tk.Toplevel(self)
        dlg.title("Instructions")
        dlg.transient(self); dlg.grab_set()
        w,h = 680, 420
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        wrap = ttk.Frame(dlg, padding=10); wrap.pack(fill="both", expand=True)
        txt = tk.Text(wrap, wrap="word"); vs = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vs.set)
        txt.pack(side="left", fill="both", expand=True); vs.pack(side="right", fill="y")
        content = (
            f"{APP_NAME} - Instructions\n\n"
            "• Place this file (subpatcher_gui.pyw) and patch.py in the SAME folder.\n"
            "• When opened, the app auto-loads patch.py and shows a green tick if successful.\n"
            "• Click 'Browse...' to select an input .exe.\n"
            "• Output is written automatically next to the input as <name>_patched.exe.\n"
            "• A backup of the original is created next to the input (.bak; timestamped if it already exists).\n"
            "• If patch.py exposes patch_exe(input, output), it will be called as-is. Otherwise, the wrapper falls back to applying offsets_and_values.\n"
            "\nUse only on files you are authorized to modify."
        )
        txt.insert("end", content); txt.configure(state="disabled")
        ttk.Button(wrap, text="Close (Esc)", command=dlg.destroy).pack(pady=(6,0))
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    def _show_about(self):
        dlg = tk.Toplevel(self); dlg.title("About"); dlg.transient(self); dlg.grab_set()
        w,h = 380, 200
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        wrap = ttk.Frame(dlg, padding=12); wrap.pack(fill="both", expand=True)
        ttk.Label(wrap, text=f"{APP_NAME} {APP_VER}", font=("Segoe UI", 12, "bold")).pack()
        ttk.Label(wrap, text="Minimal GUI wrapper for an external patch.py\n(use responsibly).", justify="center").pack(pady=(10,6))
        ttk.Button(wrap, text="OK", command=dlg.destroy).pack(pady=(6,0))

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
