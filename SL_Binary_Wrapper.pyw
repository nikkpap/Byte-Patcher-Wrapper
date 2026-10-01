import os
import sys
import ctypes
import hashlib
import shutil
import json
import subprocess
import time

try:
    import winreg
except ImportError:
    winreg = None
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

APP_NAME = "Modern Binary Wrapper"
APP_VERSION = "2.9"
SUBLIME_DEFAULT_PATH = r"C:\\Program Files\\Sublime Text\\sublime_text.exe"

# ------------------------------------------------------------
# ADMIN / UAC
# ------------------------------------------------------------
def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ask_for_elevation() -> bool:
    """Ask once on Windows whether to relaunch with Administrator rights."""
    if os.name != "nt" or is_admin():
        return True

    MB_YESNO = 0x00000004
    MB_ICONQUESTION = 0x00000020
    MB_SETFOREGROUND = 0x00010000
    IDYES = 6

    result = ctypes.windll.user32.MessageBoxW(
        None,
        "Run this application as Administrator?\n\n"
        "Administrator rights may be required when working with files in protected folders.\n\n"
        "Choose No to continue normally.",
        f"{APP_NAME} - Administrator",
        MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND,
    )

    if result != IDYES:
        return True

    try:
        if getattr(sys, "frozen", False):
            executable = sys.executable
            args = sys.argv[1:]
        else:
            executable = sys.executable
            args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]

        params = " ".join(f'"{arg}"' for arg in args)
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, None, 1
        )
        return False if rc > 32 else True
    except Exception:
        return True


# ------------------------------------------------------------
# ROBUST / AUTHORIZED MAINTENANCE HELPERS
# ------------------------------------------------------------
STATE_SUFFIX = ".mbw_state.json"
BACKUP_SUFFIX = ".mbw_backup"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def state_path_for(path: str) -> str:
    return path + STATE_SUFFIX


def backup_path_for(path: str) -> str:
    return path + BACKUP_SUFFIX


def make_backup(path: str) -> str:
    backup = backup_path_for(path)
    if not os.path.isfile(backup):
        shutil.copy2(path, backup)
    return backup


def write_state(path: str, before_hash: str, after_hash: str, backup: str) -> None:
    payload = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "target": os.path.abspath(path),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "backup": backup,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    with open(state_path_for(path), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def read_state(path: str):
    sp = state_path_for(path)
    if not os.path.isfile(sp):
        return None
    try:
        with open(sp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_already_processed(input_path: str, output_path: str = "") -> bool:
    if not input_path or not os.path.isfile(input_path):
        return False
    state = read_state(input_path)
    if not state:
        return False
    try:
        return state.get("after_sha256") == sha256_file(input_path)
    except Exception:
        return False


def default_output_path(input_path: str) -> str:
    return input_path


def stop_target_process(path: str, log_callback=None) -> bool:
    """Force-stop the target process tree and give Windows time to release handles."""
    if os.name != "nt":
        return True

    exe_name = os.path.basename(path)
    if not exe_name.lower().endswith(".exe"):
        return True

    try:
        completed = subprocess.run(
            ["taskkill", "/IM", exe_name, "/T", "/F"],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if completed.returncode == 0:
            if log_callback:
                log_callback(f"Force-stopped process tree: {exe_name}")
        else:
            if log_callback:
                log_callback(f"Process check complete: {exe_name} is not running.")

        # Windows may hold the executable briefly after taskkill returns.
        time.sleep(0.35)
        return True
    except Exception as e:
        if log_callback:
            log_callback(f"Process stop warning: {e}")
        return False


def wait_for_file_release(path: str, timeout: float = 6.0, log_callback=None) -> bool:
    """Wait until the target can be opened for update, retrying Windows lock errors."""
    deadline = time.monotonic() + timeout
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        try:
            with open(path, "r+b"):
                pass
            if attempt > 1 and log_callback:
                log_callback(f"File lock released after {attempt} checks.")
            return True
        except (PermissionError, OSError) as e:
            winerr = getattr(e, "winerror", None)
            if winerr not in (5, 32, 33) and not isinstance(e, PermissionError):
                raise
            time.sleep(0.25)

    if log_callback:
        log_callback("File is still locked after waiting; forcing process stop again...")
    stop_target_process(path, log_callback)
    time.sleep(0.5)

    try:
        with open(path, "r+b"):
            pass
        return True
    except (PermissionError, OSError):
        return False


def find_pattern(data: bytes, pattern: bytes) -> int:
    if not pattern:
        return -1
    return data.find(pattern)


def apply_authorized_patch(input_path: str, output_path: str = "", log_callback=None):
    """
    Authorized transformation hook.

    The surrounding app provides:
      * admin/UAC startup
      * target auto-detection
      * process shutdown
      * backup before write
      * generic signature-search helper
      * post-write verification
      * state-based already-done detection
      * rollback

    The distributed template does not include a product-specific binary patch.
    """
    if log_callback:
        log_callback("Authorized transformation hook reached.")
        log_callback("No product-specific binary modification is configured.")

    with open(input_path, "rb") as f:
        data = f.read()

    with open(input_path, "wb") as f:
        f.write(data)

    return 0




def has_sublime_context_menu(sublime_path: str) -> bool:
    """Return True only when both Sublime Explorer registry values are present and correct."""
    if os.name != "nt" or winreg is None or not sublime_path:
        return False

    shell_key = r"*\shell\Open with Sublime Text"
    command_key = shell_key + r"\command"
    expected_command = f'"{sublime_path}" "%1"'

    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            shell_key,
            0,
            winreg.KEY_READ,
        ) as key:
            icon, _ = winreg.QueryValueEx(key, "Icon")

        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            command_key,
            0,
            winreg.KEY_READ,
        ) as key:
            command, _ = winreg.QueryValueEx(key, None)

        return (
            os.path.normcase(str(icon).strip()) == os.path.normcase(sublime_path.strip())
            and str(command).strip() == expected_command
        )
    except (FileNotFoundError, OSError):
        return False



def add_sublime_context_menu(sublime_path: str, log_callback=None) -> bool:
    """Silently add an Explorer 'Open with Sublime Text' context-menu entry."""
    if os.name != "nt" or winreg is None:
        if log_callback:
            log_callback("Registry integration skipped: Windows registry unavailable.")
        return False

    if not sublime_path or not os.path.isfile(sublime_path):
        raise FileNotFoundError(f"Sublime Text executable not found: {sublime_path}")

    shell_key = r"*\shell\Open with Sublime Text"
    command_key = shell_key + r"\command"

    with winreg.CreateKeyEx(
        winreg.HKEY_CLASSES_ROOT,
        shell_key,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, sublime_path)

    command = f'"{sublime_path}" "%1"'
    with winreg.CreateKeyEx(
        winreg.HKEY_CLASSES_ROOT,
        command_key,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, command)

    if log_callback:
        log_callback('Registry: "Open with Sublime Text" added silently.')

    return True


def rollback_target(path: str, log_callback=None) -> bool:
    backup = backup_path_for(path)
    if not os.path.isfile(backup):
        return False

    if log_callback:
        log_callback("Preparing rollback...")

    stop_target_process(path, log_callback)

    if not wait_for_file_release(path, timeout=6.0, log_callback=log_callback):
        raise PermissionError(
            "The target executable is still locked after force-closing its process tree."
        )

    # Retry the actual restore too, because AV/indexers can briefly reopen executables.
    last_error = None
    for attempt in range(1, 9):
        try:
            shutil.copy2(backup, path)
            last_error = None
            if attempt > 1 and log_callback:
                log_callback(f"Rollback restore succeeded on retry {attempt}.")
            break
        except (PermissionError, OSError) as e:
            last_error = e
            winerr = getattr(e, "winerror", None)
            if winerr not in (5, 32, 33) and not isinstance(e, PermissionError):
                raise
            if log_callback:
                log_callback(f"Target still busy — retrying restore ({attempt}/8)...")
            stop_target_process(path, log_callback)
            time.sleep(0.35)

    if last_error is not None:
        raise last_error

    try:
        os.remove(state_path_for(path))
    except FileNotFoundError:
        pass

    if log_callback:
        log_callback(f"Rollback restored: {backup}")
    return True


# ------------------------------------------------------------
# GUI
# ------------------------------------------------------------
class ModernApp(tk.Tk):
    BG = "#0f172a"
    PANEL = "#111827"
    PANEL_2 = "#172033"
    TEXT = "#e5e7eb"
    MUTED = "#94a3b8"
    ACCENT = "#38bdf8"
    SUCCESS = "#22c55e"
    WARNING = "#f59e0b"
    DANGER = "#ef4444"

    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("540x360")
        self.minsize(500, 330)
        self.configure(bg=self.BG)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.backup_var = tk.BooleanVar(value=True)

        self._configure_style()
        self._build_ui()
        self._center()
        self._update_admin_badge()
        self.after(150, self._auto_find_sublime)

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 2)
        self.geometry(f"+{x}+{y}")

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("Card.TFrame", background=self.PANEL_2)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.BG, foreground="white", font=("Segoe UI Semibold", 16))
        style.configure("Sub.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.PANEL_2, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Muted.Card.TLabel", background=self.PANEL_2, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(18, 10))
        style.map("Accent.TButton", background=[("active", "#0ea5e9"), ("!disabled", self.ACCENT)], foreground=[("!disabled", "#06121d")])
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("TCheckbutton", background=self.PANEL_2, foreground=self.TEXT, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", self.PANEL_2)])

    def _build_ui(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")

        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Sublime Text utility", style="Sub.TLabel").pack(anchor="w", pady=(4, 0))

        self.admin_badge = tk.Label(
            header, text="", bg=self.PANEL_2, fg=self.TEXT, padx=12, pady=7,
            font=("Segoe UI Semibold", 9), bd=0,
        )
        self.admin_badge.pack(side="right")

        card = ttk.Frame(outer, style="Card.TFrame", padding=14)
        card.pack(fill="both", expand=True, pady=(12, 8))

        self.target_label = ttk.Label(
            card, text="Searching for Sublime Text...", style="Card.TLabel",
            font=("Segoe UI Semibold", 9)
        )
        self.target_label.pack(anchor="center", pady=(2, 8))

        self.just_do_it_btn = tk.Button(
            card,
            text="Just Do It",
            command=self.run_patch,
            bg=self.ACCENT,
            fg="#06121d",
            activebackground="#0ea5e9",
            activeforeground="#06121d",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 16),
            padx=28,
            pady=10,
        )
        self.just_do_it_btn.pack(anchor="center", pady=(4, 6))
        self.just_do_it_btn.bind("<Button-3>", self._rollback_from_context)

        self.rollback_hint = ttk.Label(
            card,
            text="Right-click “Just Do It” for rollback",
            style="Muted.Card.TLabel",
        )
        self.rollback_hint.pack(anchor="center", pady=(0, 6))

        self.log_text = tk.Text(
            card, height=7, bg="#0b1220", fg=self.TEXT, insertbackground="white",
            relief="flat", wrap="word", font=("Cascadia Mono", 8),
        )
        self.log_text.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text.configure(state="disabled")

        # Hidden compatibility widgets/state for existing helper methods.
        self.info_text = tk.Text(self)
        self.info_text.withdraw() if hasattr(self.info_text, "withdraw") else None

        footer = ttk.Frame(outer)
        footer.pack(fill="x")
        self.status_dot = tk.Label(footer, text="●", bg=self.BG, fg=self.SUCCESS, font=("Segoe UI", 10))
        self.status_dot.pack(side="left")
        ttk.Label(footer, textvariable=self.status_var, style="Sub.TLabel").pack(side="left", padx=(6, 0))

    def _auto_find_sublime(self):
        """Auto-detect the standard Sublime Text executable location on Windows."""
        if os.name != "nt":
            return

        candidates = [
            SUBLIME_DEFAULT_PATH,
            r"C:\Program Files (x86)\Sublime Text\sublime_text.exe",
        ]

        for path in candidates:
            if os.path.isfile(path):
                self.input_var.set(path)
                self.output_var.set(path)
                self.target_label.configure(text=f"Found: {path}")
                self._log(f"Auto-detected Sublime Text: {path}")
                try:
                    self.inspect_file()
                    self._refresh_already_done_state()
                except Exception as e:
                    self._log(f"Auto-inspection failed: {e}")
                return

        self.target_label.configure(text="Sublime Text not found")
        self._log("Sublime Text was not found in the standard Program Files locations.")
        self._set_status("Sublime Text not auto-detected", self.WARNING)

    def _refresh_already_done_state(self):
        src = self.input_var.get().strip()
        patched = is_already_processed(src)
        regs_ok = has_sublime_context_menu(src) if patched else False

        if patched and regs_ok:
            msg = "No need to cure — vaccine already done...!"
            self._set_status(msg, self.SUCCESS)
            self._log(msg)
            self.just_do_it_btn.configure(text="Already Done ✓", state="disabled")
            return True

        if patched and not regs_ok:
            msg = "Patch already done — registry entry missing"
            self._set_status(msg, self.WARNING)
            self._log(msg)
            self.just_do_it_btn.configure(text="Just Do It", state="normal")
            return False

        self.just_do_it_btn.configure(text="Just Do It", state="normal")
        return False

    def _rollback_from_context(self, event=None):
        src = self.input_var.get().strip()
        if not src or not os.path.isfile(src):
            return

        backup = backup_path_for(src)
        if not os.path.isfile(backup):
            messagebox.showinfo(APP_NAME, "No rollback backup exists yet.")
            return

        if not messagebox.askyesno(
            APP_NAME,
            "Restore the original file from the rollback backup?"
        ):
            return

        try:
            if rollback_target(src, self._log):
                self.just_do_it_btn.configure(text="Just Do It", state="normal")
                self._set_status("Rollback completed", self.SUCCESS)
                self._log("Original file restored successfully.")
                messagebox.showinfo(APP_NAME, "Rollback completed successfully.")
        except Exception as e:
            self._set_status("Rollback failed", self.DANGER)
            self._log(f"Rollback error: {e}")
            messagebox.showerror(APP_NAME, f"Rollback failed:\n\n{e}")

    def _update_admin_badge(self):
        if os.name == "nt" and is_admin():
            self.admin_badge.configure(text="ADMINISTRATOR", fg=self.SUCCESS)
        elif os.name == "nt":
            self.admin_badge.configure(text="STANDARD USER", fg=self.WARNING)
        else:
            self.admin_badge.configure(text="DESKTOP MODE", fg=self.ACCENT)

    def _set_status(self, text, color=None):
        self.status_var.set(text)
        self.status_dot.configure(fg=color or self.SUCCESS)
        self.update_idletasks()

    def _log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.update_idletasks()

    def _set_info(self, text):
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("end", text)
        self.info_text.configure(state="disabled")

    def browse_input(self):
        path = filedialog.askopenfilename(
            title="Select executable or binary",
            filetypes=[("Executables", "*.exe"), ("Binary files", "*.bin *.dll"), ("All files", "*.*")],
        )
        if not path:
            return
        self.input_var.set(path)
        self.output_var.set(path)
        self._log(f"Selected: {path}")
        self.inspect_file()

    def browse_output(self):
        initial = self.output_var.get().strip() or "modified.exe"
        path = filedialog.asksaveasfilename(
            title="Choose output file",
            initialfile=os.path.basename(initial),
            initialdir=os.path.dirname(initial) if os.path.dirname(initial) else None,
            defaultextension=os.path.splitext(initial)[1] or ".bin",
            filetypes=[("All files", "*.*")],
        )
        if path:
            self.output_var.set(path)

    def inspect_file(self):
        path = self.input_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning(APP_NAME, "Choose a valid input file first.")
            return

        try:
            size = os.path.getsize(path)
            digest = sha256_file(path)
            stat = os.stat(path)
            info = (
                f"File: {path}\n\n"
                f"Size: {size:,} bytes\n"
                f"Modified: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"SHA-256:\n{digest}\n\n"
                f"Admin: {'Yes' if is_admin() else 'No'}"
            )
            self._set_info(info)
            self._set_status("File inspected", self.SUCCESS)
        except Exception as e:
            self._set_status("Inspection failed", self.DANGER)
            messagebox.showerror(APP_NAME, str(e))

    def run_patch(self):
        src = self.input_var.get().strip()

        if not src or not os.path.isfile(src):
            messagebox.showwarning(APP_NAME, "Target executable was not found.")
            return

        try:
            patched = is_already_processed(src)
            regs_ok = has_sublime_context_menu(src)

            # Patch is already done, but Explorer integration is missing:
            # do ONLY the registry step. No process kill, backup, or binary work.
            if patched and not regs_ok:
                self._set_status("Adding registry entry...", self.ACCENT)
                self._log("Patch already done; applying registry integration only...")
                add_sublime_context_menu(src, self._log)

                if not has_sublime_context_menu(src):
                    raise RuntimeError("Registry verification failed.")

                self._set_status("Registry applied", self.SUCCESS)
                self._log("Registry integration verified successfully.")
                self._refresh_already_done_state()
                messagebox.showinfo(
                    APP_NAME,
                    "Patch was already done.\n\nOnly the Explorer registry entry was applied."
                )
                return

            # Both are already present: nothing to do.
            if patched and regs_ok:
                self._refresh_already_done_state()
                return

            self._set_status("Working...", self.ACCENT)
            self._log("Starting authorized maintenance workflow...")

            stop_target_process(src, self._log)

            before_hash = sha256_file(src)
            backup = make_backup(src)
            self._log(f"Rollback backup: {backup}")
            self._log(f"Before SHA-256: {before_hash}")

            changed = apply_authorized_patch(src, src, self._log)

            after_hash = sha256_file(src)
            self._log(f"Reported bytes changed: {changed}")
            self._log(f"After SHA-256: {after_hash}")

            write_state(src, before_hash, after_hash, backup)

            # Silent Explorer context-menu integration after the workflow succeeds.
            add_sublime_context_menu(src, self._log)

            if not os.path.isfile(src) or not is_already_processed(src):
                raise RuntimeError("Post-write verification failed.")
            if not has_sublime_context_menu(src):
                raise RuntimeError("Registry verification failed.")

            self._set_status("Completed", self.SUCCESS)
            self._refresh_already_done_state()
            messagebox.showinfo(
                APP_NAME,
                "Completed successfully.\n\nBackup, verification receipt, and the Sublime Text context-menu entry were created."
            )

        except PermissionError as e:
            self._set_status("Permission denied", self.DANGER)
            self._log(f"Permission error: {e}")
            messagebox.showerror(
                APP_NAME,
                "Permission denied. Restart with Administrator rights."
            )
        except Exception as e:
            self._set_status("Failed", self.DANGER)
            self._log(f"Error: {e}")
            messagebox.showerror(APP_NAME, f"Operation failed:\n\n{e}")

    def open_folder(self):
        path = self.output_var.get().strip() or self.input_var.get().strip()
        if not path:
            return
        folder = os.path.dirname(os.path.abspath(path))
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", folder])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))


def main():
    if not ask_for_elevation():
        return
    app = ModernApp()
    app.mainloop()


if __name__ == "__main__":
    main()
