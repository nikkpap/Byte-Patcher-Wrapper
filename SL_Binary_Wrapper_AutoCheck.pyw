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
from datetime import datetime

# Tkinter is checked/loaded by the startup dependency bootstrap below.
tk = None
ttk = None
filedialog = None
messagebox = None

APP_NAME = "Modern Binary Wrapper"
APP_VERSION = "3.3"
SUBLIME_DEFAULT_PATH = r"C:\\Program Files\\Sublime Text\\sublime_text.exe"

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def platform_name() -> str:
    if IS_WINDOWS:
        return "Windows"
    if IS_MACOS:
        return "macOS"
    if IS_LINUX:
        return "Linux"
    return sys.platform


# ------------------------------------------------------------
# STARTUP DEPENDENCY CHECK
# ------------------------------------------------------------
def _native_yes_no(title: str, message: str) -> bool:
    """Ask a Yes/No question without requiring Tkinter."""
    if IS_WINDOWS:
        try:
            MB_YESNO = 0x00000004
            MB_ICONQUESTION = 0x00000020
            MB_SETFOREGROUND = 0x00010000
            IDYES = 6
            result = ctypes.windll.user32.MessageBoxW(
                None, message, title,
                MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND,
            )
            return result == IDYES
        except Exception:
            pass

    if IS_MACOS:
        try:
            script = (
                'display dialog ' + json.dumps(message) +
                ' with title ' + json.dumps(title) +
                ' buttons {"No", "Yes"} default button "Yes"'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True,
            )
            return result.returncode == 0 and "button returned:Yes" in result.stdout
        except Exception:
            pass

    if IS_LINUX:
        # Prefer a graphical question when available.
        for cmd in (
            ["zenity", "--question", "--title", title, "--text", message],
            ["kdialog", "--yesno", message, "--title", title],
        ):
            if shutil.which(cmd[0]):
                try:
                    return subprocess.run(cmd).returncode == 0
                except Exception:
                    pass

    # Last-resort console prompt.
    try:
        ans = input(f"{title}\n{message}\nInstall now? [Y/n]: ").strip().lower()
        return ans in ("", "y", "yes")
    except Exception:
        return False


def _native_info(title: str, message: str, error: bool = False) -> None:
    """Show startup information without requiring Tkinter."""
    if IS_WINDOWS:
        try:
            flags = 0x10 if error else 0x40
            ctypes.windll.user32.MessageBoxW(None, message, title, flags)
            return
        except Exception:
            pass

    if IS_MACOS:
        try:
            script = (
                'display dialog ' + json.dumps(message) +
                ' with title ' + json.dumps(title) +
                ' buttons {"OK"} default button "OK"'
            )
            subprocess.run(["osascript", "-e", script], capture_output=True)
            return
        except Exception:
            pass

    if IS_LINUX:
        exe = "zenity" if shutil.which("zenity") else None
        if exe:
            kind = "--error" if error else "--info"
            try:
                subprocess.run([exe, kind, "--title", title, "--text", message])
                return
            except Exception:
                pass

    print(f"{title}: {message}")


def _tkinter_available() -> bool:
    try:
        import tkinter as _tk
        import tkinter.ttk as _ttk
        return True
    except Exception:
        return False


def _linux_tk_install_command():
    """Return a suitable package-manager command for Tkinter, when detectable."""
    managers = [
        ("apt-get", ["sudo", "apt-get", "install", "-y", "python3-tk"]),
        ("apt", ["sudo", "apt", "install", "-y", "python3-tk"]),
        ("dnf", ["sudo", "dnf", "install", "-y", "python3-tkinter"]),
        ("yum", ["sudo", "yum", "install", "-y", "python3-tkinter"]),
        ("zypper", ["sudo", "zypper", "--non-interactive", "install", "python3-tk"]),
        ("pacman", ["sudo", "pacman", "-S", "--noconfirm", "tk"]),
        ("apk", ["sudo", "apk", "add", "tk"]),
    ]
    for manager, command in managers:
        if shutil.which(manager):
            # If already root, don't depend on sudo.
            if hasattr(os, "geteuid") and os.geteuid() == 0 and command[0] == "sudo":
                command = command[1:]
            elif command[0] == "sudo" and not shutil.which("sudo"):
                command = command[1:]
            return command
    return None


def _macos_tk_install_command():
    """Best-effort Homebrew Tcl/Tk installation."""
    brew = shutil.which("brew")
    if not brew:
        return None

    # Homebrew provides versioned python-tk formulas matching Python versions.
    versioned = f"python-tk@{sys.version_info.major}.{sys.version_info.minor}"
    return [brew, "install", versioned]


def install_missing_dependencies() -> bool:
    """
    Check startup dependencies and ask before installing anything.

    This app intentionally uses the Python standard library only.
    The dependency most commonly missing on Linux/macOS Python builds is Tkinter.
    """
    if _tkinter_available():
        return True

    question = (
        "A required GUI dependency is missing:\n\n"
        "• Tkinter / Tcl-Tk\n\n"
        f"Platform: {platform_name()}\n"
        f"Python: {sys.version.split()[0]}\n\n"
        "Install it automatically now?"
    )
    if not _native_yes_no(f"{APP_NAME} - Dependencies", question):
        _native_info(
            f"{APP_NAME} - Missing dependency",
            "Tkinter is required to start the graphical interface.",
            error=True,
        )
        return False

    command = None

    if IS_LINUX:
        command = _linux_tk_install_command()
    elif IS_MACOS:
        command = _macos_tk_install_command()
    elif IS_WINDOWS:
        # Standard CPython for Windows normally includes Tcl/Tk. It cannot
        # reliably be added to an existing Python install through pip.
        _native_info(
            f"{APP_NAME} - Python component",
            "Tkinter is normally included with the official Python installer on Windows.\n\n"
            "Please run the Python installer, choose Modify, and enable Tcl/Tk and IDLE.",
            error=True,
        )
        return False

    if not command:
        _native_info(
            f"{APP_NAME} - Installer not found",
            "No supported automatic package manager was found.\n\n"
            "Install Tkinter/Tcl-Tk for your Python installation and run the app again.",
            error=True,
        )
        return False

    try:
        _native_info(
            f"{APP_NAME} - Installing",
            "The system package manager may ask for your administrator password.",
        )
        result = subprocess.run(command)
        if result.returncode != 0:
            raise RuntimeError(f"Installer exited with code {result.returncode}")

        if not _tkinter_available():
            _native_info(
                f"{APP_NAME} - Restart required",
                "Installation completed, but this Python process cannot load Tkinter yet.\n\n"
                "Close and reopen the app.",
            )
            return False

        return True

    except Exception as e:
        _native_info(
            f"{APP_NAME} - Dependency installation failed",
            f"Could not install Tkinter automatically.\n\n{e}",
            error=True,
        )
        return False


def load_gui_dependencies() -> bool:
    """Load Tkinter after dependency verification."""
    global tk, ttk, filedialog, messagebox

    if not install_missing_dependencies():
        return False

    try:
        import tkinter as _tk
        from tkinter import ttk as _ttk, filedialog as _filedialog, messagebox as _messagebox

        tk = _tk
        ttk = _ttk
        filedialog = _filedialog
        messagebox = _messagebox
        return True
    except Exception as e:
        _native_info(
            f"{APP_NAME} - GUI error",
            f"Tkinter is installed but could not be loaded.\n\n{e}",
            error=True,
        )
        return False

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
    """Best-effort stop of the target process on Windows, macOS, and Linux."""
    exe_name = os.path.basename(path)

    try:
        if IS_WINDOWS:
            if not exe_name.lower().endswith(".exe"):
                return True
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
            time.sleep(0.35)
            return True

        if IS_MACOS or IS_LINUX:
            # Try the exact executable path first, then the process basename.
            subprocess.run(
                ["pkill", "-f", path],
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["pkill", "-x", exe_name],
                capture_output=True,
                text=True,
            )
            if log_callback:
                log_callback(f"Process stop requested: {exe_name}")
            time.sleep(0.25)
            return True

        if log_callback:
            log_callback(f"Process stop skipped on unsupported platform: {sys.platform}")
        return True

    except FileNotFoundError:
        if log_callback:
            log_callback("Process stop utility was not available; continuing.")
        return False
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




def _norm_reg_path(value: str) -> str:
    """Normalize registry paths for tolerant comparisons."""
    value = os.path.expandvars(str(value or "")).strip().strip('"').strip()
    # Icon values are also commonly stored as "path.exe,0".
    if value.lower().endswith(",0"):
        value = value[:-2].rstrip()
    return os.path.normcase(os.path.normpath(value))


def _command_points_to_sublime(command: str, sublime_path: str) -> bool:
    """Accept normal quoted/unquoted Explorer command variants."""
    if not command:
        return False

    raw = os.path.expandvars(str(command)).strip()
    wanted = _norm_reg_path(sublime_path)

    # The command must pass the selected file to Sublime.
    if '%1' not in raw:
        return False

    # Accept both:
    #   "C:\\...\\sublime_text.exe" "%1"
    #   C:\\...\\sublime_text.exe "%1"
    # and harmless whitespace/case variations.
    cleaned = raw.replace('"%1"', '%1').replace("'%1'", '%1').strip()
    before_arg = cleaned.split('%1', 1)[0].strip().rstrip().strip('"').strip()
    return _norm_reg_path(before_arg) == wanted


def _read_context_menu_from_root(root, base_prefix: str, sublime_path: str, wow_flag: int = 0) -> bool:
    shell_rel = r"*\shell\Open with Sublime Text"
    command_rel = shell_rel + r"\command"
    shell_key = (base_prefix + "\\" + shell_rel) if base_prefix else shell_rel
    command_key = (base_prefix + "\\" + command_rel) if base_prefix else command_rel

    access = winreg.KEY_READ | wow_flag
    try:
        with winreg.OpenKey(root, shell_key, 0, access) as key:
            icon, _ = winreg.QueryValueEx(key, "Icon")
        with winreg.OpenKey(root, command_key, 0, access) as key:
            command, _ = winreg.QueryValueEx(key, None)

        return (
            _norm_reg_path(icon) == _norm_reg_path(sublime_path)
            and _command_points_to_sublime(command, sublime_path)
        )
    except (FileNotFoundError, OSError):
        return False


def has_sublime_context_menu(sublime_path: str) -> bool:
    """Auto-detect the actual Sublime Explorer registry integration on Windows."""
    if not IS_WINDOWS:
        return True
    if winreg is None or not sublime_path:
        return False

    # HKCR is a merged view. Also inspect the backing per-user/per-machine
    # Software\\Classes locations and both registry views where applicable.
    checks = [
        (winreg.HKEY_CLASSES_ROOT, "", 0),
        (winreg.HKEY_CURRENT_USER, r"Software\Classes", 0),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Classes", 0),
    ]

    if hasattr(winreg, "KEY_WOW64_64KEY"):
        checks.extend([
            (winreg.HKEY_CLASSES_ROOT, "", winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_CURRENT_USER, r"Software\Classes", winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Classes", winreg.KEY_WOW64_64KEY),
        ])
    if hasattr(winreg, "KEY_WOW64_32KEY"):
        checks.extend([
            (winreg.HKEY_CLASSES_ROOT, "", winreg.KEY_WOW64_32KEY),
            (winreg.HKEY_CURRENT_USER, r"Software\Classes", winreg.KEY_WOW64_32KEY),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Classes", winreg.KEY_WOW64_32KEY),
        ])

    seen = set()
    for root, prefix, view in checks:
        token = (int(root), prefix, view)
        if token in seen:
            continue
        seen.add(token)
        if _read_context_menu_from_root(root, prefix, sublime_path, view):
            return True

    return False

def registry_context_status(sublime_path: str) -> str:
    if not IS_WINDOWS:
        return f"Registry not applicable on {platform_name()}"
    return "Registry integration detected" if has_sublime_context_menu(sublime_path) else "Registry integration not detected"


def add_sublime_context_menu(sublime_path: str, log_callback=None) -> bool:
    """Silently add an Explorer 'Open with Sublime Text' context-menu entry."""
    if not IS_WINDOWS:
        if log_callback:
            log_callback(f"Registry integration skipped on {platform_name()}.")
        return True
    if winreg is None:
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
# Load GUI dependencies before defining any Tk-based classes.
if not load_gui_dependencies():
    sys.exit(1)

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
        ttk.Label(left, text=f"Sublime Text utility • {platform_name()}", style="Sub.TLabel").pack(anchor="w", pady=(4, 0))

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
        self.just_do_it_btn.bind("<Button-2>", self._rollback_from_context)
        if IS_MACOS:
            self.just_do_it_btn.bind("<Control-Button-1>", self._rollback_from_context)

        self.rollback_hint = ttk.Label(
            card,
            text=("Control-click “Just Do It” for rollback" if IS_MACOS else "Right-click “Just Do It” for rollback"),
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
        """Auto-detect Sublime Text using standard locations for the current OS."""
        if IS_WINDOWS:
            candidates = [
                SUBLIME_DEFAULT_PATH,
                r"C:\Program Files (x86)\Sublime Text\sublime_text.exe",
            ]
        elif IS_MACOS:
            candidates = [
                "/Applications/Sublime Text.app/Contents/MacOS/sublime_text",
                str(Path.home() / "Applications/Sublime Text.app/Contents/MacOS/sublime_text"),
            ]
        elif IS_LINUX:
            candidates = [
                "/opt/sublime_text/sublime_text",
                "/usr/lib/sublime-text/sublime_text",
                "/usr/lib/sublime_text/sublime_text",
                "/snap/sublime-text/current/opt/sublime_text/sublime_text",
                "/var/lib/flatpak/app/com.sublimetext.three/current/active/files/sublime_text/sublime_text",
            ]

            # Common launchers/symlinks are useful as a fallback.
            for launcher in ("sublime_text", "subl"):
                resolved = shutil.which(launcher)
                if resolved:
                    candidates.append(os.path.realpath(resolved))
        else:
            candidates = []

        seen = set()
        for path in candidates:
            if not path:
                continue
            path = os.path.realpath(os.path.expanduser(path))
            if path in seen:
                continue
            seen.add(path)

            if os.path.isfile(path):
                self.input_var.set(path)
                self.output_var.set(path)
                self.target_label.configure(text=f"Found: {path}")
                self._log(f"Auto-detected Sublime Text on {platform_name()}: {path}")
                try:
                    self.inspect_file()
                    self._refresh_already_done_state()
                except Exception as e:
                    self._log(f"Auto-inspection failed: {e}")
                return

        self.target_label.configure(text=f"Sublime Text not found on {platform_name()}")
        self._log(f"Sublime Text was not found in the standard {platform_name()} locations.")
        self._set_status("Sublime Text not auto-detected", self.WARNING)

    def _refresh_already_done_state(self):
        src = self.input_var.get().strip()
        patched = is_already_processed(src)
        regs_required = IS_WINDOWS
        regs_ok = has_sublime_context_menu(src) if (patched and regs_required) else True
        if patched and regs_required:
            self._log(registry_context_status(src))

        if patched and regs_ok:
            msg = "No need to cure — vaccine already done...!"
            self._set_status(msg, self.SUCCESS)
            self._log(msg)
            self.just_do_it_btn.configure(text="Already Done ✓", state="disabled")
            return True

        if patched and regs_required and not regs_ok:
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
            self.admin_badge.configure(text=platform_name().upper(), fg=self.ACCENT)

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
            filetypes=[
                ("Applications / executables", "*.exe *.bin *.dll *.so *.dylib"),
                ("All files", "*.*"),
            ],
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
            regs_required = IS_WINDOWS
            regs_ok = has_sublime_context_menu(src) if regs_required else True

            # Windows only: patch is already done, but Explorer integration is missing.
            # Do ONLY the registry step. No process kill, backup, or binary work.
            if patched and regs_required and not regs_ok:
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

            # Windows only: add Explorer context-menu integration.
            if IS_WINDOWS:
                add_sublime_context_menu(src, self._log)

            if not os.path.isfile(src) or not is_already_processed(src):
                raise RuntimeError("Post-write verification failed.")
            if IS_WINDOWS and not has_sublime_context_menu(src):
                raise RuntimeError("Registry verification failed.")

            self._set_status("Completed", self.SUCCESS)
            self._refresh_already_done_state()

            if IS_WINDOWS:
                done_message = (
                    "Completed successfully.\n\n"
                    "Backup, verification receipt, and the Sublime Text context-menu entry were created."
                )
            else:
                done_message = (
                    f"Completed successfully on {platform_name()}.\n\n"
                    "Backup and verification receipt were created. "
                    "Windows registry integration was skipped."
                )

            messagebox.showinfo(APP_NAME, done_message)

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
