# Modern Binary Wrapper

A compact, cross-platform Python utility for running authorized binary maintenance workflows with a simple one-button interface.

Designed for Windows, macOS, and Linux, the application provides a clean GUI around common maintenance tasks such as file detection, process shutdown, backup creation, verification, rollback, dependency checks, and platform-specific integration.

> Intended only for software, binaries, and systems that you own or are authorized to modify.

---

## Features

- Modern compact GUI
- Single **Just Do It** action
- Windows, macOS, and Linux support
- Automatic Administrator elevation on Windows
- Automatic target detection
- Automatic dependency check on startup
- Optional dependency installation with user confirmation
- Automatic process shutdown before file operations
- Backup creation before modifications
- SHA-256 verification
- Post-operation validation
- Already-processed detection
- Automatic retry when a file is temporarily locked
- Rollback support
- Cross-platform process handling
- Windows Registry integration support
- Registry auto-detection and verification
- Registry operations automatically disabled on macOS and Linux
- Activity log and status messages
- No unnecessary third-party Python packages

---

## Supported Platforms

### Windows

- Windows 10
- Windows 11
- Automatic UAC elevation
- Windows Registry support
- Process termination with `taskkill`
- Locked-file retry handling

### macOS

- macOS with Python 3
- Native application-path detection
- Process handling using `pkill`
- Windows Registry functions automatically disabled

### Linux

Supports common Linux distributions using package managers such as:

- APT
- DNF
- YUM
- Zypper
- Pacman
- APK

Process handling is performed using standard Linux utilities.

---

## Requirements

### Python

Python 3.10 or newer is recommended.

The application mainly uses modules included with the Python standard library.

### Tkinter

Tkinter is required for the graphical interface.

The application checks for it automatically during startup.

If Tkinter is missing, the program asks:

> Missing dependencies found. Install now?

No dependency is installed without user confirmation.

---

## How It Works

The typical workflow is:

1. Start the application.
2. Required dependencies are checked.
3. Windows Administrator privileges are requested when necessary.
4. The target application or binary is detected.
5. The existing state is checked.
6. If maintenance is required:
   - the target process is stopped;
   - the original file is backed up;
   - the authorized transformation is performed;
   - SHA-256 hashes are calculated;
   - the result is verified.
7. A state receipt is created.
8. Platform-specific integration is applied where supported.

If everything has already been completed, the program displays:

> **No need to cure — vaccine already done...!**

---

## Backup and Recovery

Before modifying a target file, the wrapper can automatically create a rollback copy.

Typical backup:

```text
application.exe.mbw_backup
