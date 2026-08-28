import os
import sys
import ctypes
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont, ttk
import urllib.request
import urllib.parse
import json
import tempfile
import shutil
import zipfile
import re
import hashlib
import shlex
import plistlib

from kirstgrab_platform import (
    bundled_binary_paths,
    clean_subprocess_environment,
    cookies_file_path,
    find_macos_app_bundle,
    find_macos_app_in_tree,
    release_platform_key,
    select_release_asset,
)

MACOS_BUNDLE_IDENTIFIER = "com.polykek2k.kirstgrab"

try:
    from PIL import Image, ImageTk, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Windows API constants for clipboard access
if sys.platform.startswith("win"):
    try:
        import win32clipboard
        WIN32_AVAILABLE = True
    except ImportError:
        WIN32_AVAILABLE = False
else:
    WIN32_AVAILABLE = False

def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def macos_codesign_team_identifier(app_path):
    """Return the signing team for an app, or None for an ad-hoc signature."""
    result = subprocess.run(
        ["/usr/bin/codesign", "-dv", "--verbose=4", app_path],
        check=True,
        capture_output=True,
        text=True,
    )
    details = "\n".join((result.stdout, result.stderr))
    match = re.search(r"^TeamIdentifier=(.+)$", details, flags=re.MULTILINE)
    if not match:
        return None
    team_identifier = match.group(1).strip()
    return None if team_identifier.lower() in {"", "not set"} else team_identifier

def ensure_cookies_file(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8"):
            pass

def clear_cookies_file():
    """Clear the cookies.txt file on startup"""
    cookies_path = cookies_file_path()
    try:
        ensure_cookies_file(cookies_path)
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write("")  # Clear the file
    except Exception as e:
        print(f"Warning: Could not clear cookies file: {e}")

def edit_cookies_file():
    """Open the writable cookies file in the platform's text editor."""
    cookies_path = cookies_file_path()
    ensure_cookies_file(cookies_path)

    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["notepad.exe", cookies_path])
        elif sys.platform.startswith("darwin"):  # macOS
            subprocess.Popen(["/usr/bin/open", "-e", cookies_path])
        else:  # Linux
            subprocess.Popen(["xdg-open", cookies_path])
    except Exception as e:
        messagebox.showerror("Error", f"Could not open cookies file: {e}")

def paste_cookies():
    """Paste clipboard content to cookies.txt file"""
    cookies_path = cookies_file_path()
    ensure_cookies_file(cookies_path)
    clipboard_content = None
    
    # Try Windows API first (more reliable)
    if WIN32_AVAILABLE:
        try:
            win32clipboard.OpenClipboard()
            clipboard_content = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
            win32clipboard.CloseClipboard()
            # Convert bytes to string if necessary
            if isinstance(clipboard_content, bytes):
                clipboard_content = clipboard_content.decode('utf-8', errors='ignore')
        except Exception:
            pass
    
    # Fallback to Tkinter clipboard
    if not clipboard_content:
        try:
            clipboard_content = root.clipboard_get()
        except tk.TclError:
            pass
    
    if clipboard_content:
        try:
            with open(cookies_path, "w", encoding="utf-8") as f:
                f.write(clipboard_content)
            messagebox.showinfo("Success", "Cookies pasted successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Could not write cookies file: {e}")
    else:
        messagebox.showwarning("Warning", "No content found in clipboard!")


# Current version - update this when releasing new versions
CURRENT_VERSION = "1.6.2"
GITHUB_REPO = "Polykek2K/KirstGrab"


def get_latest_release_info():
    """Get latest release information from GitHub API"""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            return {
                'tag_name': data.get('tag_name', ''),
                'name': data.get('name', ''),
                'body': data.get('body', ''),
                'html_url': data.get('html_url', ''),
                'assets': data.get('assets', [])
            }
    except Exception as e:
        print(f"Error checking for updates: {e}")
        return None

def compare_versions(current, latest):
    """Compare version strings (simple numeric comparison)"""
    try:
        # Remove 'v' prefix if present
        current = current.replace('v', '')
        latest = latest.replace('v', '')
        
        # Split by dots and convert to integers
        current_parts = [int(x) for x in current.split('.')]
        latest_parts = [int(x) for x in latest.split('.')]
        
        # Pad shorter version with zeros
        max_len = max(len(current_parts), len(latest_parts))
        current_parts.extend([0] * (max_len - len(current_parts)))
        latest_parts.extend([0] * (max_len - len(latest_parts)))
        
        # Compare parts
        for i in range(max_len):
            if latest_parts[i] > current_parts[i]:
                return True  # Latest is newer
            elif latest_parts[i] < current_parts[i]:
                return False  # Current is newer
        
        return False  # Versions are equal
    except Exception:
        return False

def download_file(url, filepath, progress_callback=None):
    """Download a file with progress callback"""
    try:
        def download_progress(block_num, block_size, total_size):
            if progress_callback and total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, (downloaded / total_size) * 100)
                progress_callback(percent)
        
        urllib.request.urlretrieve(url, filepath, reporthook=download_progress)
        return True
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False

def show_update_dialog(latest_info):
    """Show update dialog with latest version information"""
    dialog = tk.Toplevel(root)
    dialog.title("Update Available")
    dialog.geometry("450x350")
    dialog.resizable(False, False)
    dialog.configure(bg="#2c3e50")
    
    # Center the dialog
    dialog.transient(root)
    dialog.grab_set()
    
    # Make dialog modal
    dialog.focus_set()
    
    # Update info
    latest_version = latest_info.get('tag_name', 'Unknown')
    release_name = latest_info.get('name', 'Latest Release')
    release_notes = latest_info.get('body', 'No release notes available.')

    if sys.platform == "darwin":
        dialog.geometry("480x340")
        dialog.configure(bg="#1c1c1e")

        update_content = ttk.Frame(
            dialog, style="MacRoot.TFrame", padding=(28, 24, 28, 24)
        )
        update_content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            update_content, text="Update available", style="MacTitle.TLabel"
        ).pack(anchor=tk.W)
        ttk.Label(
            update_content,
            text="A newer version of KirstGrab is ready to install.",
            style="MacSubtitle.TLabel",
        ).pack(anchor=tk.W, pady=(4, 18))

        version_frame = ttk.Frame(update_content, style="MacCard.TFrame", padding=14)
        version_frame.pack(fill=tk.X)
        ttk.Label(
            version_frame,
            text=f"Current version   {CURRENT_VERSION}",
            style="MacHint.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            version_frame,
            text=f"New version       {latest_version}",
            style="MacLabel.TLabel",
        ).pack(anchor=tk.W, pady=(5, 0))

        progress_frame = ttk.Frame(update_content, style="MacRoot.TFrame")
        progress_frame.pack(fill=tk.X, pady=(18, 0))
        progress_label = ttk.Label(progress_frame, text="", style="MacSubtitle.TLabel")
        progress_label.pack(anchor=tk.W)
        progress_track = tk.Frame(
            progress_frame, bg="#3a3a3c", height=8, width=300, bd=0
        )
        progress_track.pack(anchor=tk.W, fill=tk.X, pady=(7, 0))
        progress_track.pack_propagate(False)
        progress_bar = tk.Frame(progress_track, bg="#0a84ff", height=8, width=0, bd=0)
        progress_bar.pack(side=tk.LEFT)

        button_frame = ttk.Frame(update_content, style="MacRoot.TFrame")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))
        ttk.Button(
            button_frame,
            text="Update now",
            style="MacAccent.TButton",
            command=lambda: start_update(
                dialog, latest_info, progress_label, progress_bar, progress_frame
            ),
        ).pack(side=tk.RIGHT)
        ttk.Button(
            button_frame,
            text="Not now",
            style="Mac.TButton",
            command=dialog.destroy,
        ).pack(side=tk.RIGHT, padx=(0, 10))
        return
    
    # Title
    title_label = tk.Label(dialog, text=f"🔄 Update Available!", 
                          font=("Arial", 16, "bold"), 
                          fg="#3498db", bg="#2c3e50")
    title_label.pack(pady=20)
    
    # Version info
    version_frame = tk.Frame(dialog, bg="#2c3e50")
    version_frame.pack(pady=10)
    
    tk.Label(version_frame, text=f"Current Version: {CURRENT_VERSION}", 
             font=("Arial", 12), fg="white", bg="#2c3e50").pack()
    tk.Label(version_frame, text=f"Latest Version: {latest_version}", 
             font=("Arial", 12, "bold"), fg="#2ecc71", bg="#2c3e50").pack()
    
    # Simple update message
    message_label = tk.Label(dialog, text="A new version is available for download!", 
                           font=("Arial", 12), fg="#ecf0f1", bg="#2c3e50")
    message_label.pack(pady=20)
    
    # Progress bar (initially visible)
    progress_frame = tk.Frame(dialog, bg="#2c3e50")
    progress_frame.pack(pady=10)
    
    progress_label = tk.Label(progress_frame, text="", 
                             font=("Arial", 10), fg="#f39c12", bg="#2c3e50")
    progress_label.pack()
    
    progress_bar = tk.Frame(progress_frame, bg="#e74c3c", height=20, width=300)
    progress_bar.pack(pady=5)
    
    # Buttons
    button_frame = tk.Frame(dialog, bg="#2c3e50")
    button_frame.pack(pady=20)
    
    update_button = tk.Button(button_frame, text="🔄 Update Now", 
                             font=("Arial", 12, "bold"), 
                             bg="#e74c3c", fg="white",
                             activebackground="#c0392b",
                             bd=0, padx=25, pady=12,
                             width=12,
                             command=lambda: start_update(dialog, latest_info, progress_label, progress_bar, progress_frame))
    update_button.pack(side="left", padx=8)
    
    later_button = tk.Button(button_frame, text="⏰ Later", 
                            font=("Arial", 12), 
                            bg="#95a5a6", fg="white",
                            activebackground="#7f8c8d",
                            bd=0, padx=25, pady=12,
                            width=8,
                            command=dialog.destroy)
    later_button.pack(side="left", padx=8)
    
    skip_button = tk.Button(button_frame, text="❌ Skip", 
                           font=("Arial", 12), 
                           bg="#95a5a6", fg="white",
                           activebackground="#7f8c8d",
                           bd=0, padx=25, pady=12,
                           width=8,
                           command=dialog.destroy)
    skip_button.pack(side="left", padx=8)

def start_update(dialog, latest_info, progress_label, progress_bar, progress_frame):
    """Start the update process"""
    def run_on_ui(callback):
        try:
            root.after(0, callback)
        except tk.TclError:
            pass

    def set_progress(text=None, percent=None):
        def apply_progress():
            try:
                if not dialog.winfo_exists():
                    return
                if text is not None:
                    progress_label.config(text=text)
                if percent is not None:
                    progress_total_width = 300
                    if sys.platform == "darwin":
                        progress_total_width = max(progress_bar.master.winfo_width(), 300)
                    progress_width = int(progress_total_width * (percent / 100))
                    progress_bar.config(width=progress_width)
            except tk.TclError:
                pass
        run_on_ui(apply_progress)

    def show_update_error(message, title="Update Error"):
        def show_error():
            try:
                messagebox.showerror(title, message)
            except tk.TclError:
                pass
        set_progress("Update failed!")
        run_on_ui(show_error)

    def close_application():
        try:
            root.quit()
            root.destroy()
        except tk.TclError:
            pass

    def cleanup_temp_files(temp_zip, extract_dir, helper_script=None):
        if temp_zip and os.path.exists(temp_zip):
            try:
                os.remove(temp_zip)
            except OSError:
                pass
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
        if helper_script and os.path.exists(helper_script):
            try:
                os.remove(helper_script)
            except OSError:
                pass

    def batch_escape(value):
        return str(value).replace("%", "%%")

    def write_windows_updater(batch_script, current_pid, current_exe, temp_exe, temp_zip, extract_dir, backup_path):
        log_path = os.path.join(tempfile.gettempdir(), "KirstGrab_update.log")
        script = f'''@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PID={current_pid}"
set "SOURCE={batch_escape(temp_exe)}"
set "DEST={batch_escape(current_exe)}"
set "BACKUP={batch_escape(backup_path)}"
set "TEMPZIP={batch_escape(temp_zip)}"
set "EXTRACTDIR={batch_escape(extract_dir)}"
set "LOG={batch_escape(log_path)}"

echo KirstGrab update started > "%LOG%"
echo Waiting for process %PID% to exit... >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Wait-Process -Id %PID% -ErrorAction SilentlyContinue" >> "%LOG%" 2>&1

if not exist "%SOURCE%" (
    echo ERROR: New executable not found: %SOURCE% >> "%LOG%"
    goto update_failed
)

if exist "%BACKUP%" del /f /q "%BACKUP%" >> "%LOG%" 2>&1

for /L %%A in (1,1,30) do (
    if not exist "%DEST%" goto install_update
    echo Backing up current executable (attempt %%A)... >> "%LOG%"
    move /Y "%DEST%" "%BACKUP%" >> "%LOG%" 2>&1
    if not errorlevel 1 goto install_update
    timeout /t 1 /nobreak >nul
)
echo ERROR: Current executable stayed locked for 30 seconds. >> "%LOG%"
goto update_failed

:install_update
echo Installing new executable... >> "%LOG%"
copy /Y "%SOURCE%" "%DEST%" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo ERROR: Copy failed. Restoring backup if possible. >> "%LOG%"
    if exist "%BACKUP%" move /Y "%BACKUP%" "%DEST%" >> "%LOG%" 2>&1
    goto update_failed
)

if exist "%BACKUP%" del /f /q "%BACKUP%" >> "%LOG%" 2>&1
if exist "%TEMPZIP%" del /f /q "%TEMPZIP%" >> "%LOG%" 2>&1
if exist "%EXTRACTDIR%" rmdir /s /q "%EXTRACTDIR%" >> "%LOG%" 2>&1

for %%I in ("%DEST%") do set "DESTDIR=%%~dpI"
echo Starting updated KirstGrab... >> "%LOG%"
for /F "tokens=1 delims==" %%V in ('set _PYI_ 2^>nul') do set "%%V="
set "_MEIPASS2="
set "PYINSTALLER_RESET_ENVIRONMENT=1"
start "" /D "%DESTDIR%" "%DEST%"

echo Update completed successfully. >> "%LOG%"
del /f /q "%~f0" >nul 2>&1
exit /b 0

:update_failed
if not exist "%DEST%" if exist "%BACKUP%" move /Y "%BACKUP%" "%DEST%" >> "%LOG%" 2>&1
if not exist "%DEST%" goto cleanup_failed_update
for %%I in ("%DEST%") do set "DESTDIR=%%~dpI"
for /F "tokens=1 delims==" %%V in ('set _PYI_ 2^>nul') do set "%%V="
set "_MEIPASS2="
set "PYINSTALLER_RESET_ENVIRONMENT=1"
start "" /D "%DESTDIR%" "%DEST%"
:cleanup_failed_update
if exist "%TEMPZIP%" del /f /q "%TEMPZIP%" >> "%LOG%" 2>&1
if exist "%EXTRACTDIR%" rmdir /s /q "%EXTRACTDIR%" >> "%LOG%" 2>&1
del /f /q "%~f0" >nul 2>&1
exit /b 1
'''
        with open(batch_script, "w", encoding="utf-8") as f:
            f.write(script)

    def launch_windows_updater(batch_script, temp_zip, extract_dir):
        def launch_and_close():
            try:
                messagebox.showinfo(
                    "Update Ready",
                    "Update downloaded successfully.\nKirstGrab will close now and restart after the file is replaced."
                )

                creationflags = 0
                if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                    creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
                if hasattr(subprocess, "DETACHED_PROCESS"):
                    creationflags |= subprocess.DETACHED_PROCESS
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    creationflags |= subprocess.CREATE_NO_WINDOW

                child_env = clean_subprocess_environment()
                child_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
                subprocess.Popen(
                    ["cmd.exe", "/c", batch_script],
                    close_fds=True,
                    creationflags=creationflags,
                    env=child_env,
                )

                try:
                    dialog.grab_release()
                    dialog.destroy()
                except tk.TclError:
                    pass
                root.after(100, close_application)
            except Exception as e:
                cleanup_temp_files(temp_zip, extract_dir, batch_script)
                messagebox.showerror("Update Error", f"Failed to start updater: {e}")
                set_progress("Update failed!")
        run_on_ui(launch_and_close)

    def write_macos_updater(helper_script, current_pid, source_app, destination_app, temp_zip, extract_dir):
        log_path = os.path.join(tempfile.gettempdir(), "KirstGrab_update.log")
        quoted = {
            "source": shlex.quote(source_app),
            "destination": shlex.quote(destination_app),
            "backup": shlex.quote(destination_app + ".backup"),
            "staged": shlex.quote(destination_app + ".new"),
            "temp_zip": shlex.quote(temp_zip),
            "extract_dir": shlex.quote(extract_dir),
            "log": shlex.quote(log_path),
            "script": shlex.quote(helper_script),
        }
        script = f'''#!/bin/sh
set -u
PID={current_pid}
SOURCE={quoted["source"]}
DEST={quoted["destination"]}
BACKUP={quoted["backup"]}
STAGED={quoted["staged"]}
TEMPZIP={quoted["temp_zip"]}
EXTRACTDIR={quoted["extract_dir"]}
LOG={quoted["log"]}
SCRIPT={quoted["script"]}

log() {{
    /bin/echo "$(/bin/date -u +%Y-%m-%dT%H:%M:%SZ) $1" >> "$LOG"
}}

fail() {{
    log "ERROR: $1"
    /bin/rm -rf "$STAGED"
    if [ ! -d "$DEST" ] && [ -d "$BACKUP" ]; then
        /bin/mv "$BACKUP" "$DEST" || log "ERROR: Could not restore the previous app bundle"
    fi
    if [ -d "$DEST" ]; then
        PYINSTALLER_RESET_ENVIRONMENT=1 /usr/bin/open -n "$DEST" >> "$LOG" 2>&1 || \
            log "ERROR: Could not reopen KirstGrab after the failed update"
    fi
    /bin/rm -f "$TEMPZIP"
    /bin/rm -rf "$EXTRACTDIR"
    /bin/rm -f "$SCRIPT"
    exit 1
}}

: > "$LOG"
log "KirstGrab macOS update started"
while /bin/kill -0 "$PID" 2>/dev/null; do
    /bin/sleep 0.2
done

/bin/rm -rf "$STAGED"
/usr/bin/ditto "$SOURCE" "$STAGED" || fail "Could not stage the new app bundle"
if [ ! -x "$STAGED/Contents/MacOS/KirstGrab" ]; then
    fail "Staged app bundle has no executable"
fi

/bin/rm -rf "$BACKUP"
if [ -d "$DEST" ]; then
    /bin/mv "$DEST" "$BACKUP" || fail "Could not back up the current app bundle"
fi

if ! /bin/mv "$STAGED" "$DEST"; then
    fail "Could not install the new app bundle"
fi

if ! /usr/bin/codesign --verify --deep --strict "$DEST" >> "$LOG" 2>&1; then
    /bin/rm -rf "$DEST"
    if [ -d "$BACKUP" ]; then
        /bin/mv "$BACKUP" "$DEST" || true
    fi
    fail "Installed app bundle failed code-signature verification"
fi

if ! PYINSTALLER_RESET_ENVIRONMENT=1 /usr/bin/open -n "$DEST"; then
    /bin/rm -rf "$DEST"
    if [ -d "$BACKUP" ]; then
        /bin/mv "$BACKUP" "$DEST" || true
    fi
    fail "Could not restart KirstGrab"
fi
log "Update completed; backup retained at $BACKUP"
/bin/rm -f "$TEMPZIP"
/bin/rm -rf "$EXTRACTDIR"
/bin/rm -f "$SCRIPT"
'''
        with open(helper_script, "w", encoding="utf-8", newline="\n") as file:
            file.write(script)
        os.chmod(helper_script, 0o700)

    def launch_macos_updater(helper_script, temp_zip, extract_dir):
        def launch_and_close():
            try:
                messagebox.showinfo(
                    "Update Ready",
                    "Update downloaded successfully.\nKirstGrab will close and restart after the app bundle is replaced."
                )
                child_env = clean_subprocess_environment()
                child_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
                subprocess.Popen(
                    ["/bin/sh", helper_script],
                    close_fds=True,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=child_env,
                )
                try:
                    dialog.grab_release()
                    dialog.destroy()
                except tk.TclError:
                    pass
                root.after(100, close_application)
            except Exception as error:
                cleanup_temp_files(temp_zip, extract_dir, helper_script)
                messagebox.showerror("Update Error", f"Failed to start updater: {error}")
                set_progress("Update failed!")
        run_on_ui(launch_and_close)

    def show_manual_update(message):
        release_url = latest_info.get("html_url", "")

        def show_instructions():
            messagebox.showinfo("Manual Update Required", message)
            if release_url and sys.platform == "darwin":
                subprocess.Popen(["/usr/bin/open", release_url])

        set_progress("Manual update required")
        run_on_ui(show_instructions)

    def verify_download_digest(filepath, asset):
        raw_digest = asset.get("digest")
        if not raw_digest:
            raise ValueError("Release asset has no SHA-256 digest; use a manual update")
        digest = str(raw_digest)
        algorithm, separator, expected = digest.partition(":")
        if separator != ":" or algorithm.lower() != "sha256" or not expected:
            raise ValueError(f"Unsupported release digest: {digest}")

        hasher = hashlib.sha256()
        with open(filepath, "rb") as downloaded_file:
            for chunk in iter(lambda: downloaded_file.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest().lower() != expected.lower():
            raise ValueError("Downloaded update failed SHA-256 verification")

    def extract_update_archive(filepath, destination):
        destination_root = os.path.abspath(destination)
        with zipfile.ZipFile(filepath, "r") as archive:
            for member in archive.infolist():
                target = os.path.abspath(os.path.join(destination_root, member.filename))
                if os.path.commonpath([destination_root, target]) != destination_root:
                    raise ValueError(f"Unsafe path in update archive: {member.filename}")

        if sys.platform == "darwin":
            subprocess.run(
                ["/usr/bin/ditto", "-x", "-k", filepath, destination],
                check=True,
                capture_output=True,
                text=True,
            )
            return

        with zipfile.ZipFile(filepath, "r") as archive:
            archive.extractall(destination_root)

    def update_progress(percent):
        set_progress(f"Downloading update... {percent:.1f}%", percent)
    
    def download_and_replace():
        temp_zip = None
        extract_dir = None
        updater_handoff = False
        try:
            assets = latest_info.get('assets', [])
            zip_asset = select_release_asset(assets)

            if not zip_asset:
                platform_key = release_platform_key()
                show_update_error(f"Could not find a release package for {platform_key}.", "Error")
                return

            if not getattr(sys, 'frozen', False):
                show_update_error("Automatic replacement is available only in the packaged application.")
                return

            temp_dir = tempfile.gettempdir()
            asset_name = os.path.basename(zip_asset.get('name', 'release.zip'))
            temp_zip = os.path.join(temp_dir, f"KirstGrab_update_{os.getpid()}_{asset_name}")

            set_progress("Downloading update...", 0)

            download_url = zip_asset.get('browser_download_url', '')
            if not download_url or not download_file(download_url, temp_zip, update_progress):
                show_update_error("Failed to download update!", "Error")
                return

            verify_download_digest(temp_zip, zip_asset)
            set_progress("Extracting update...", 100)
            extract_dir = tempfile.mkdtemp(prefix="KirstGrab_extract_")
            extract_update_archive(temp_zip, extract_dir)
            set_progress("Preparing restart...", 100)

            if sys.platform.startswith("win"):
                exe_files = []
                for current_root, _directories, files in os.walk(extract_dir):
                    for filename in files:
                        if filename.lower().endswith('.exe') and 'kirstgrab' in filename.lower():
                            exe_files.append(os.path.join(current_root, filename))

                if not exe_files:
                    show_update_error("Could not find KirstGrab.exe in the release package!", "Error")
                    return

                temp_exe = sorted(exe_files)[0]
                current_exe = sys.executable
                backup_path = current_exe + ".backup"
                batch_script = os.path.join(temp_dir, f"update_kirstgrab_{os.getpid()}.bat")
                write_windows_updater(
                    batch_script,
                    os.getpid(),
                    current_exe,
                    temp_exe,
                    temp_zip,
                    extract_dir,
                    backup_path
                )
                set_progress("Update ready. Restarting application...", 100)
                updater_handoff = True
                launch_windows_updater(batch_script, temp_zip, extract_dir)
            elif sys.platform == "darwin":
                source_app = find_macos_app_in_tree(extract_dir)
                destination_app = find_macos_app_bundle(sys.executable)
                if not source_app:
                    show_update_error("Could not find KirstGrab.app in the release package!", "Error")
                    return
                subprocess.run(
                    ["/usr/bin/codesign", "--verify", "--deep", "--strict", source_app],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                source_info_plist = os.path.join(source_app, "Contents", "Info.plist")
                with open(source_info_plist, "rb") as plist_file:
                    source_info = plistlib.load(plist_file)
                source_bundle_identifier = source_info.get("CFBundleIdentifier")
                if source_bundle_identifier != MACOS_BUNDLE_IDENTIFIER:
                    raise ValueError(
                        f"Unexpected update bundle identifier: {source_bundle_identifier!r}"
                    )
                expected_version = str(latest_info.get("tag_name", "")).lstrip("v")
                source_version = str(source_info.get("CFBundleShortVersionString", "")).lstrip("v")
                if source_version != expected_version:
                    raise ValueError(
                        f"Update bundle version {source_version!r} does not match release {expected_version!r}"
                    )
                if not destination_app:
                    show_manual_update(
                        "KirstGrab could not locate its current .app bundle. "
                        "Download the matching macOS archive and replace KirstGrab.app manually."
                    )
                    return

                subprocess.run(
                    ["/usr/bin/codesign", "--verify", "--deep", "--strict", destination_app],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                current_team_identifier = macos_codesign_team_identifier(destination_app)
                update_team_identifier = macos_codesign_team_identifier(source_app)
                if current_team_identifier and update_team_identifier != current_team_identifier:
                    raise ValueError(
                        "The update is not signed by the same Apple Developer team as the installed app"
                    )

                destination_parent = os.path.dirname(destination_app)
                if not os.access(destination_parent, os.W_OK):
                    show_manual_update(
                        "The folder containing KirstGrab.app is not writable. "
                        "Download the matching archive and replace KirstGrab.app in Applications manually."
                    )
                    return

                helper_script = os.path.join(temp_dir, f"update_kirstgrab_{os.getpid()}.sh")
                write_macos_updater(
                    helper_script,
                    os.getpid(),
                    source_app,
                    destination_app,
                    temp_zip,
                    extract_dir,
                )
                set_progress("Update ready. Restarting application...", 100)
                updater_handoff = True
                launch_macos_updater(helper_script, temp_zip, extract_dir)
            else:
                show_update_error("Automatic updates are not supported on this platform.")

        except Exception as error:
            show_update_error(f"Failed to update: {error}")
        finally:
            if not updater_handoff:
                cleanup_temp_files(temp_zip, extract_dir)
    
    # Start download in separate thread
    threading.Thread(target=download_and_replace, daemon=True).start()

def check_for_updates():
    """Check for updates on startup"""
    def check_thread():
        try:
            latest_info = get_latest_release_info()
            if latest_info:
                latest_version = latest_info.get('tag_name', '')
                if compare_versions(CURRENT_VERSION, latest_version):
                    # Update available - show dialog in main thread
                    root.after(0, lambda: show_update_dialog(latest_info))
        except Exception as e:
            print(f"Update check failed: {e}")
    
    # Check for updates in background thread
    threading.Thread(target=check_thread, daemon=True).start()

def find_helper_executable(relative_path, development_candidates=()):
    executable = resource_path(relative_path)
    candidates = [executable]
    source_root = os.path.dirname(os.path.abspath(__file__))
    candidates.extend(os.path.join(source_root, candidate) for candidate in development_candidates)

    for candidate in candidates:
        if os.path.isfile(candidate) and (sys.platform.startswith("win") or os.access(candidate, os.X_OK)):
            return candidate

    discovered = shutil.which(os.path.basename(relative_path))
    return discovered

def resolve_helper_executables():
    binary_paths = bundled_binary_paths()
    yt_name = os.path.basename(binary_paths["yt_dlp"])
    ffmpeg_name = os.path.basename(binary_paths["ffmpeg"])
    ffprobe_name = os.path.basename(binary_paths["ffprobe"])
    deno_name = os.path.basename(binary_paths["deno"])

    yt_development_candidates = [yt_name]
    deno_development_candidates = [os.path.join("deno", deno_name), deno_name]
    if sys.platform == "darwin":
        architecture = release_platform_key().rsplit("-", 1)[-1]
        yt_development_candidates.append(os.path.join("macos-inputs", architecture, "yt-dlp"))
        deno_development_candidates.append(os.path.join("macos-inputs", architecture, "deno"))

    return {
        "yt_dlp": find_helper_executable(
            binary_paths["yt_dlp"],
            tuple(yt_development_candidates),
        ),
        "ffmpeg": find_helper_executable(
            binary_paths["ffmpeg"],
            (os.path.join("ffmpeg", ffmpeg_name), ffmpeg_name),
        ),
        "ffprobe": find_helper_executable(
            binary_paths["ffprobe"],
            (os.path.join("ffmpeg", ffprobe_name), ffprobe_name),
        ),
        "deno": find_helper_executable(
            binary_paths["deno"],
            tuple(deno_development_candidates),
        ),
    }

def normalize_clip_time(value):
    value = value.strip().replace(",", ".")
    if not value:
        return ""
    if value.lower() == "inf":
        return "inf"
    if not re.fullmatch(r"-?(?:\d+(?::\d{1,2}){0,2}(?:\.\d+)?|\d*\.\d+)", value):
        raise ValueError("Use time like 90, 1:30, 00:01:30, or leave one side empty.")
    return value

def build_clip_section(start_value, end_value):
    start = normalize_clip_time(start_value)
    end = normalize_clip_time(end_value)

    if not start and not end:
        raise ValueError("Set at least one clip time.")

    if not start:
        start = "0"
    if not end:
        end = "inf"

    return f"*{start}-{end}"

class ImageButton(tk.Canvas):
    def __init__(self, master=None, normal_img=None, pressed_img=None, command=None, **kwargs):
        super().__init__(master, highlightthickness=0, bd=0, **kwargs)
        self.command = command
        self.normal_img = normal_img
        self.pressed_img = pressed_img if pressed_img else normal_img
        width = self.normal_img.width()
        height = self.normal_img.height()
        self.config(width=width, height=height)
        self.image_item = self.create_image(0, 0, image=self.normal_img, anchor="nw")
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<ButtonRelease-1>", self.on_release)
    def on_press(self, event):
        self.itemconfig(self.image_item, image=self.pressed_img)
    def on_release(self, event):
        self.itemconfig(self.image_item, image=self.normal_img)
        if self.command and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.command()

def build_command(url, download_path, format_choice, filename=None, clip_section=None):
    helpers = resolve_helper_executables()
    yt = helpers["yt_dlp"]
    ffmpeg_path = helpers["ffmpeg"]
    ffprobe_path = helpers["ffprobe"]
    deno_path = helpers["deno"]

    if not yt:
        expected_path = resource_path(bundled_binary_paths()["yt_dlp"])
        raise FileNotFoundError(f"Bundled yt-dlp was not found at {expected_path}")

    ffmpeg_dir = os.path.dirname(ffmpeg_path) if ffmpeg_path else None
    
    cmd = [
        yt,
        "--no-check-certificates",  # Skip SSL certificate verification
        "--prefer-free-formats",    # Prefer free formats when available
        "--merge-output-format", "mp4",  # Merge to MP4 when possible
        "--no-js-runtimes",
        url,
        "-P", download_path,
        "--progress-template", "%(progress._percent_str)s %(progress._eta_str)s",
        "-o", os.path.join(download_path, "%(title)s.%(ext)s"),
    ]

    # # Add YouTube extractor arguments
    cmd.extend(["--extractor-args", "youtube:player_client=default,-tv_downgraded"])
    
    # Проверка наличия JS
    if deno_path:
        cmd.extend(["--js-runtimes", f"deno:{deno_path}"])
    # Handle cookies - only use cookies.txt file
    cookies_path = cookies_file_path()
    ensure_cookies_file(cookies_path)
    # Only use cookies if the file is not empty
    if os.path.getsize(cookies_path) > 0:
        cmd.extend(["--cookies", cookies_path])
    
    # Handle custom filename if provided and not empty
    if filename and filename.strip():
        # Remove extension from filename if present, yt-dlp will add the appropriate extension
        name_without_ext = os.path.splitext(filename)[0]
        # Only use custom filename if the name (without extension) is not empty
        if name_without_ext.strip():
            output_template = os.path.join(download_path, name_without_ext + ".%(ext)s")
            cmd.extend(["-o", output_template])

    if clip_section:
        cmd.extend(["--download-sections", clip_section])
    
    # Set format based on choice
    if format_choice == "Best Quality (MP4)":
        cmd.extend(["-t", "mp4"])
    # elif format_choice == "1080p (MP4)":
    #     cmd.extend(["-f", "best[height<=1080][ext=mp4]/bestvideo[height<=1080]+bestaudio[ext=m4a]/best[height<=1080]/best"])
    # elif format_choice == "720p (MP4)":
    #     cmd.extend(["-f", "best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]/best"])
    # elif format_choice == "480p (MP4)":
    #     cmd.extend(["-f", "best[height<=480][ext=mp4]/bestvideo[height<=480]+bestaudio[ext=m4a]/best[height<=480]/best"])
    elif format_choice == "Audio only (MP3)":
        # Download best audio and convert to MP3
        cmd.extend(["-f", "bestaudio", "-x", "--audio-format", "mp3", "--audio-quality", "0"])
    else:
        # Fallback to best available
        cmd.extend(["-f", "best"])
    
    # Check for ffmpeg and ffprobe
    if ffmpeg_path and ffprobe_path:
        cmd.extend(["--ffmpeg-location", ffmpeg_dir])
        # Debug: Add ffmpeg path to output
        output_text.config(state=tk.NORMAL)
        output_text.insert(tk.END, f"Using ffmpeg: {ffmpeg_path}\n")
        output_text.insert(tk.END, f"Using ffprobe: {ffprobe_path}\n")
        output_text.config(state=tk.DISABLED)
    else:
        output_text.config(state=tk.NORMAL)
        if not ffmpeg_path:
            output_text.insert(tk.END, "Warning: ffmpeg was not found\n")
        if not ffprobe_path:
            output_text.insert(tk.END, "Warning: ffprobe was not found\n")
        output_text.config(state=tk.DISABLED)
    return cmd

def start_download(url, download_path, format_choice, filename=None, clip_section=None):
    try:
        cmd = build_command(url, download_path, format_choice, filename, clip_section)
    except Exception as error:
        messagebox.showerror("Ошибка", f"Не удалось подготовить загрузку: {error}")
        return
    
    # Debug: Show the command being executed
    output_text.config(state=tk.NORMAL)
    output_text.insert(tk.END, f"Format: {format_choice}\n")
    if clip_section:
        output_text.insert(tk.END, f"Clip: {clip_section}\n")
    output_text.insert(tk.END, f"Command: {' '.join(cmd)}\n")
    output_text.config(state=tk.DISABLED)
    
    try:
        # Create startup info to hide console window on Windows
        startupinfo = None
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            startupinfo=startupinfo,
            env=clean_subprocess_environment(),
        )
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось запустить yt-dlp: {e}")
        output_text.config(state=tk.NORMAL)
        output_text.insert(tk.END, "\n❌ Ошибка: " + str(e))
        output_text.config(state=tk.DISABLED)
        return

    output_text.config(state=tk.NORMAL)
    output_text.delete(1.0, tk.END)
    output_text.insert(tk.END, f"Загрузка: {url}\n")
    output_text.config(state=tk.DISABLED)

    def read_output():
        buffer_line = ""
        progress_line_created = [False]  # Track if progress line exists
        
        while True:
            try:
                ch = proc.stdout.read(1)
            except Exception:
                ch = ""
            if not ch:
                if proc.poll() is not None:
                    code = proc.returncode
                    def show_completion():
                        output_text.config(state=tk.NORMAL)
                        output_text.insert(tk.END, "\n✅ COMPLETED!" if code == 0 else f"\n❌ ERROR (code {code})")
                        output_text.config(state=tk.DISABLED)
                    root.after(0, show_completion)
                    break
                continue

            if ch == "\r":
                # перезаписываем последнюю строку (для прогресса)
                def replace_line(line=buffer_line):
                    output_text.config(state=tk.NORMAL)
                    if progress_line_created[0]:
                        # Удаляем последнюю строку и заменяем её
                        last_line = output_text.index(tk.END + "-1l")
                        output_text.delete(last_line, tk.END)
                        output_text.insert(tk.END, line)
                    else:
                        # Создаем новую строку прогресса
                        output_text.insert(tk.END, line)
                        progress_line_created[0] = True
                    output_text.see(tk.END)
                    output_text.config(state=tk.DISABLED)
                root.after(0, replace_line)
                buffer_line = ""
            elif ch == "\n":
                def append_line(line=buffer_line):
                    output_text.config(state=tk.NORMAL)
                    output_text.insert(tk.END, line + "\n")
                    # Сбрасываем флаг строки прогресса при добавлении новой строки
                    progress_line_created[0] = False
                    output_text.see(tk.END)
                    output_text.config(state=tk.DISABLED)
                root.after(0, append_line)
                buffer_line = ""
            else:
                buffer_line += ch

    threading.Thread(target=read_output, daemon=True).start()

def on_download_clicked():
    url = entry.get().strip()
    if not url:
        messagebox.showerror("Ошибка", "Введите URL видео!")
        return
    
    clip_section = None
    if clip_var.get():
        try:
            clip_section = build_clip_section(clip_start_var.get(), clip_end_var.get())
        except ValueError as e:
            messagebox.showerror("Invalid Clip", str(e))
            return

    # Ask user to choose save location and filename
    # Use a simple default filename since this is YouTube-specific
    default_filename = "youtube_video.mp4"
    
    file_path = filedialog.asksaveasfilename(
        title="Choose download location and filename (leave blank for auto-naming)",
        defaultextension=".mp4",
        initialfile=default_filename,
        filetypes=[
            ("MP4 files", "*.mp4"),
            ("All files", "*.*")
        ]
    )
    if not file_path:
        return
    
    # Extract directory and filename
    download_path = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    
    # Only use custom filename if it's not empty, just whitespace, or the default suggested name
    if not filename or not filename.strip() or filename == default_filename:
        filename = None

    start_download(url, download_path, format_var.get(), filename, clip_section)

def run_self_test():
    """Validate packaged helper discovery without starting the GUI."""
    commands = {
        "yt_dlp": ["--version"],
        "ffmpeg": ["-version"],
        "ffprobe": ["-version"],
        "deno": ["eval", "console.log(1 + 1)"],
    }
    helpers = resolve_helper_executables()
    for helper_name, relative_path in bundled_binary_paths().items():
        executable = helpers[helper_name]
        if not executable:
            raise FileNotFoundError(f"Bundled helper was not found: {relative_path}")
        subprocess.run(
            [executable, *commands[helper_name]],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=clean_subprocess_environment(),
        )
    return 0

if "--self-test" in sys.argv:
    try:
        raise SystemExit(run_self_test())
    except Exception as error:
        print(f"KirstGrab self-test failed: {error}", file=sys.stderr)
        raise SystemExit(1)

root = tk.Tk()
root.title("KirstGrab")
IS_MACOS = sys.platform == "darwin"

# Windows uses the embedded ICO here; macOS gets its Dock/Finder icon from the app bundle.
ico_p = resource_path("icon.ico")
if sys.platform.startswith("win") and os.path.exists(ico_p):
    try:
        root.iconbitmap(ico_p)
    except Exception:
        # Try alternative method
        try:
            root.tk.call('wm', 'iconbitmap', root._w, ico_p)
        except Exception:
            pass
# Windows keeps its established geometry and visual treatment. macOS uses a
# separate layout below, sized for native spacing instead of image dimensions.
if IS_MACOS:
    default_width = 760
    default_height = 610
    expanded_height = 660
    default_bg = "#1c1c1e"
else:
    default_width = int(500 * 1.5)  # 750
    default_height = int(350 * 1.25)  # 437
    expanded_height = default_height + 45
    default_bg = "#2c3e50"
root.geometry(f"{default_width}x{default_height}")
root.minsize(default_width, default_height)
root.resizable(True, True)
root.config(bg=default_bg)

# Clear cookies file on startup
clear_cookies_file()

system_font_family = "Helvetica Neue" if IS_MACOS else "Arial"
tk_custom_font = (system_font_family, 12)
font_file = resource_path(os.path.join("fonts", "m6x11plus.ttf"))
if not IS_MACOS and os.path.exists(font_file) and PIL_AVAILABLE:
    try:
        pil_font = ImageFont.truetype(font_file, size=12)
        family_name = pil_font.getname()[0]
        if sys.platform.startswith("win"):
            FR_PRIVATE = 0x10
            try:
                ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(font_file), FR_PRIVATE, None)
            except Exception:
                pass
        try:
            tk_custom_font = tkfont.Font(family=family_name, size=12)
        except Exception:
            tk_custom_font = (family_name, 12)
    except Exception:
        tk_custom_font = (system_font_family, 12)

bg_photo = None
bg_label = None
bg_image_original = None
frame_bg = default_bg
bg_path = resource_path(os.path.join("images", "background.png"))
if not IS_MACOS and os.path.exists(bg_path) and PIL_AVAILABLE:
    try:
        bg_image_original = Image.open(bg_path)
        # Resize background to match the increased window size (50% wider)
        resized_bg = bg_image_original.resize((default_width, default_height), Image.Resampling.LANCZOS)
        bg_photo = ImageTk.PhotoImage(resized_bg)
        bg_label = tk.Label(root, image=bg_photo)
        bg_label.image = bg_photo
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        frame_bg = ""
    except Exception:
        frame_bg = default_bg

def set_window_height(height):
    global bg_photo
    window_width = max(root.winfo_width(), default_width) if IS_MACOS else default_width
    root.geometry(f"{window_width}x{height}")
    if bg_label is not None and bg_image_original is not None and PIL_AVAILABLE:
        try:
            resized_bg = bg_image_original.resize((default_width, height), Image.Resampling.LANCZOS)
            bg_photo = ImageTk.PhotoImage(resized_bg)
            bg_label.config(image=bg_photo)
            bg_label.image = bg_photo
        except Exception:
            pass

format_var = tk.StringVar(value="Best Quality (MP4)")
format_options = [
    "Best Quality (MP4)",
    "Audio only (MP3)"
]

def manual_update_check():
    """Manually check for updates"""
    try:
        latest_info = get_latest_release_info()
        if latest_info:
            latest_version = latest_info.get('tag_name', '')
            if compare_versions(CURRENT_VERSION, latest_version):
                # Update available - show dialog
                show_update_dialog(latest_info)
            else:
                messagebox.showinfo("No Updates", f"You are running the latest version ({CURRENT_VERSION})!")
        else:
            messagebox.showerror("Update Check Failed", "Could not check for updates. Please check your internet connection.")
    except Exception as e:
        messagebox.showerror("Update Check Error", f"Error checking for updates: {str(e)}")

clip_var = tk.BooleanVar(value=False)
clip_start_var = tk.StringVar()
clip_end_var = tk.StringVar()

def toggle_clip_controls():
    if clip_var.get():
        if IS_MACOS:
            clip_controls_frame.pack(fill=tk.X, pady=(12, 0), before=help_label)
        else:
            clip_controls_frame.pack(pady=(0, 5), before=help_label)
        set_window_height(expanded_height)
        clip_start_entry.focus_set()
    else:
        clip_controls_frame.pack_forget()
        set_window_height(default_height)

mac_content = None
if IS_MACOS:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("MacRoot.TFrame", background="#1c1c1e")
    style.configure("MacCard.TFrame", background="#2c2c2e")
    style.configure(
        "MacTitle.TLabel",
        background="#1c1c1e",
        foreground="#f5f5f7",
        font=(system_font_family, 24, "bold"),
    )
    style.configure(
        "MacSubtitle.TLabel",
        background="#1c1c1e",
        foreground="#98989d",
        font=(system_font_family, 11),
    )
    style.configure(
        "MacLabel.TLabel",
        background="#2c2c2e",
        foreground="#f5f5f7",
        font=(system_font_family, 11, "bold"),
    )
    style.configure(
        "MacHint.TLabel",
        background="#2c2c2e",
        foreground="#98989d",
        font=(system_font_family, 10),
    )
    style.configure(
        "Mac.TButton",
        background="#3a3a3c",
        foreground="#f5f5f7",
        borderwidth=0,
        padding=(12, 8),
        font=(system_font_family, 10),
    )
    style.map(
        "Mac.TButton",
        background=[("pressed", "#48484a"), ("active", "#48484a")],
    )
    style.configure(
        "MacAccent.TButton",
        background="#0a84ff",
        foreground="white",
        borderwidth=0,
        padding=(16, 11),
        font=(system_font_family, 12, "bold"),
    )
    style.map(
        "MacAccent.TButton",
        background=[("pressed", "#0060df"), ("active", "#409cff")],
    )
    style.configure(
        "Mac.TCheckbutton",
        background="#2c2c2e",
        foreground="#f5f5f7",
        font=(system_font_family, 11),
    )
    style.map(
        "Mac.TCheckbutton",
        background=[("active", "#2c2c2e")],
        foreground=[("disabled", "#636366")],
    )
    style.configure(
        "Mac.TEntry",
        fieldbackground="#111113",
        foreground="#f5f5f7",
        bordercolor="#48484a",
        lightcolor="#48484a",
        darkcolor="#48484a",
        padding=9,
        font=(system_font_family, 12),
    )
    style.configure(
        "Mac.TCombobox",
        fieldbackground="#3a3a3c",
        background="#3a3a3c",
        foreground="#f5f5f7",
        arrowcolor="#f5f5f7",
        bordercolor="#48484a",
        padding=6,
        font=(system_font_family, 11),
    )
    style.map(
        "Mac.TCombobox",
        fieldbackground=[("readonly", "#3a3a3c")],
        foreground=[("readonly", "#f5f5f7")],
        selectbackground=[("readonly", "#3a3a3c")],
        selectforeground=[("readonly", "#f5f5f7")],
    )
    root.option_add("*TCombobox*Listbox.background", "#2c2c2e")
    root.option_add("*TCombobox*Listbox.foreground", "#f5f5f7")
    root.option_add("*TCombobox*Listbox.selectBackground", "#0a84ff")

    mac_content = ttk.Frame(root, style="MacRoot.TFrame", padding=(28, 20, 28, 26))
    mac_content.pack(fill=tk.BOTH, expand=True)

    header_frame = ttk.Frame(mac_content, style="MacRoot.TFrame")
    header_frame.pack(fill=tk.X)
    ttk.Label(header_frame, text="KirstGrab", style="MacTitle.TLabel").pack(anchor=tk.W)
    ttk.Label(
        header_frame,
        text="Download video and audio without leaving your Mac",
        style="MacSubtitle.TLabel",
    ).pack(anchor=tk.W, pady=(2, 0))

    settings_frame = ttk.Frame(mac_content, style="MacCard.TFrame", padding=14)
    settings_frame.pack(fill=tk.X, pady=(18, 12))
    ttk.Label(settings_frame, text="Format", style="MacLabel.TLabel").pack(side=tk.LEFT)
    format_menu = ttk.Combobox(
        settings_frame,
        textvariable=format_var,
        values=format_options,
        state="readonly",
        width=20,
        style="Mac.TCombobox",
    )
    format_menu.pack(side=tk.LEFT, padx=(10, 18))
    update_check_btn = ttk.Button(
        settings_frame, text="Updates", command=manual_update_check, style="Mac.TButton"
    )
    update_check_btn.pack(side=tk.RIGHT)
    paste_cookies_btn = ttk.Button(
        settings_frame, text="Paste cookies", command=paste_cookies, style="Mac.TButton"
    )
    paste_cookies_btn.pack(side=tk.RIGHT, padx=(0, 8))
    edit_cookies_btn = ttk.Button(
        settings_frame, text="Edit cookies", command=edit_cookies_file, style="Mac.TButton"
    )
    edit_cookies_btn.pack(side=tk.RIGHT, padx=(0, 8))

    url_card = ttk.Frame(mac_content, style="MacCard.TFrame", padding=14)
    url_card.pack(fill=tk.X, pady=(0, 12))
    ttk.Label(url_card, text="Video URL", style="MacLabel.TLabel").pack(anchor=tk.W)
    entry_frame = ttk.Frame(url_card, style="MacCard.TFrame")
    entry_frame.pack(fill=tk.X, pady=(9, 0))
    entry = ttk.Entry(entry_frame, style="Mac.TEntry")
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    clip_check = ttk.Checkbutton(
        entry_frame,
        text="Clip",
        variable=clip_var,
        command=toggle_clip_controls,
        style="Mac.TCheckbutton",
    )
    clip_check.pack(side=tk.RIGHT, padx=(12, 0))
    paste_button = ttk.Button(
        entry_frame, text="Paste", command=lambda: handle_paste(None), style="Mac.TButton"
    )
    paste_button.pack(side=tk.RIGHT, padx=(8, 0))

    clip_controls_frame = ttk.Frame(url_card, style="MacCard.TFrame")
    clip_start_label = ttk.Label(clip_controls_frame, text="From", style="MacLabel.TLabel")
    clip_start_label.pack(side=tk.LEFT)
    clip_start_entry = ttk.Entry(
        clip_controls_frame, width=12, textvariable=clip_start_var, style="Mac.TEntry"
    )
    clip_start_entry.pack(side=tk.LEFT, padx=(8, 18))
    clip_end_label = ttk.Label(clip_controls_frame, text="To", style="MacLabel.TLabel")
    clip_end_label.pack(side=tk.LEFT)
    clip_end_entry = ttk.Entry(
        clip_controls_frame, width=12, textvariable=clip_end_var, style="Mac.TEntry"
    )
    clip_end_entry.pack(side=tk.LEFT, padx=(8, 0))
    help_label = ttk.Label(
        url_card,
        text="Paste a link, choose a format, then select where to save the file.",
        style="MacHint.TLabel",
    )
    help_label.pack(anchor=tk.W, pady=(10, 0))
else:
    settings_frame = tk.Frame(root, bg=frame_bg if frame_bg else default_bg, bd=0)
    settings_frame.pack(pady=5)

    format_label = tk.Label(settings_frame, text="Format:", bg=frame_bg if frame_bg else default_bg, fg="white", font=tk_custom_font)
    format_label.pack(side=tk.LEFT, padx=5)
    format_menu = tk.OptionMenu(settings_frame, format_var, *format_options)
    format_menu.config(bg="#2c3e50", fg="white", highlightthickness=0, font=tk_custom_font)
    format_menu["menu"].config(bg="#2c3e50", fg="white", font=tk_custom_font)
    format_menu.pack(side=tk.LEFT)

    cookies_label = tk.Label(settings_frame, text="Cookies:", bg=frame_bg if frame_bg else default_bg, fg="white", font=tk_custom_font)
    cookies_label.pack(side=tk.LEFT, padx=(20, 5))
    edit_cookies_btn = tk.Button(settings_frame, text="📝 Edit Cookies", command=edit_cookies_file,
                                font=tk_custom_font, bg="#e67e22", fg="white",
                                activebackground="#d35400", bd=0, padx=8)
    edit_cookies_btn.pack(side=tk.LEFT, padx=(10, 0))
    paste_cookies_btn = tk.Button(settings_frame, text="📋 Paste Cookies", command=paste_cookies,
                                 font=tk_custom_font, bg="#9b59b6", fg="white",
                                 activebackground="#8e44ad", bd=0, padx=8)
    paste_cookies_btn.pack(side=tk.LEFT, padx=(10, 0))
    update_check_btn = tk.Button(settings_frame, text="🔄 Check Updates", command=manual_update_check,
                                font=tk_custom_font, bg="#27ae60", fg="white",
                                activebackground="#229954", bd=0, padx=8)
    update_check_btn.pack(side=tk.LEFT, padx=(10, 0))

    entry_frame = tk.Frame(root, bg=default_bg)
    entry_frame.pack(pady=5)
    entry = tk.Entry(entry_frame, width=55, font=tk_custom_font, bd=2, relief="flat")
    entry.pack(side=tk.LEFT, padx=(0, 5))
    paste_button = tk.Button(entry_frame, text="📋 Paste", command=lambda: handle_paste(None),
                            font=tk_custom_font, bg="#3498db", fg="white",
                            activebackground="#2980b9", bd=0, padx=10)
    paste_button.pack(side=tk.LEFT)
    clip_check = tk.Checkbutton(
        entry_frame,
        text="Clip",
        variable=clip_var,
        command=toggle_clip_controls,
        font=tk_custom_font,
        bg=default_bg,
        fg="white",
        activebackground=default_bg,
        activeforeground="white",
        selectcolor="#34495e",
        bd=0,
        highlightthickness=0,
    )
    clip_check.pack(side=tk.LEFT, padx=(10, 0))

    clip_controls_frame = tk.Frame(root, bg=default_bg)
    clip_start_label = tk.Label(clip_controls_frame, text="From:", bg=default_bg, fg="white", font=tk_custom_font)
    clip_start_label.pack(side=tk.LEFT, padx=(0, 4))
    clip_start_entry = tk.Entry(clip_controls_frame, width=10, font=tk_custom_font, bd=2, relief="flat", textvariable=clip_start_var)
    clip_start_entry.pack(side=tk.LEFT, padx=(0, 10))
    clip_end_label = tk.Label(clip_controls_frame, text="To:", bg=default_bg, fg="white", font=tk_custom_font)
    clip_end_label.pack(side=tk.LEFT, padx=(0, 4))
    clip_end_entry = tk.Entry(clip_controls_frame, width=10, font=tk_custom_font, bd=2, relief="flat", textvariable=clip_end_var)
    clip_end_entry.pack(side=tk.LEFT)
    help_label = tk.Label(root, text="💡 Tip: Right-click in the URL field for paste options",
                         font=("Arial", 9), fg="#bdc3c7", bg=default_bg)
    help_label.pack(pady=(0, 5))

# Add keyboard shortcuts for better compatibility with non-English layouts
def handle_paste(event):
    """Handle paste operation with better keyboard layout support"""
    clipboard_content = None
    
    # Try Windows API first (more reliable)
    if WIN32_AVAILABLE:
        try:
            win32clipboard.OpenClipboard()
            clipboard_content = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
            win32clipboard.CloseClipboard()
        except Exception:
            pass
    
    # Fallback to Tkinter clipboard
    if not clipboard_content:
        try:
            clipboard_content = root.clipboard_get()
        except tk.TclError:
            pass
    
    if clipboard_content:
        # Clear current selection and insert clipboard content
        entry.delete(0, tk.END)
        entry.insert(0, clipboard_content)
        return "break"  # Prevent default behavior
    
    return None

def handle_ctrl_v(event):
    """Handle Ctrl+V specifically"""
    return handle_paste(event)

def handle_enter(event):
    """Handle Enter key to start download"""
    on_download_clicked()
    return "break"

def handle_escape(event):
    """Handle Escape key to clear entry"""
    entry.delete(0, tk.END)
    return "break"

def handle_ctrl_a(event):
    """Handle Ctrl+A to select all"""
    entry.select_range(0, tk.END)
    return "break"

# Add context menu for better paste support
def show_context_menu(event):
    """Show context menu with paste option"""
    try:
        primary_modifier = "⌘" if sys.platform == "darwin" else "Ctrl+"
        context_menu = tk.Menu(root, tearoff=0, bg="#2c3e50", fg="white", font=tk_custom_font,
                              activebackground="#3498db", activeforeground="white")
        context_menu.add_command(label=f"📋 Paste ({primary_modifier}V)", command=lambda: handle_paste(None))
        context_menu.add_separator()
        context_menu.add_command(label="✂️ Cut", command=lambda: entry.event_generate("<<Cut>>"))
        context_menu.add_command(label="📄 Copy", command=lambda: entry.event_generate("<<Copy>>"))
        context_menu.add_separator()
        context_menu.add_command(label=f"🔍 Select All ({primary_modifier}A)", command=lambda: handle_ctrl_a(None))
        context_menu.add_command(label="🗑️ Clear", command=lambda: entry.delete(0, tk.END))
        
        # Show context menu at cursor position
        context_menu.tk_popup(event.x_root, event.y_root)
    except Exception:
        pass

# Bind keyboard events - multiple approaches for different layouts
def handle_key_press(event):
    """Handle key press events for better layout compatibility"""
    # Debug: Print key information (remove in production)
    # print(f"Key: {event.keysym}, State: {event.state}, Char: {event.char}")
    
    # Check for Ctrl+V using multiple methods
    if (event.state & 0x4 and  # Ctrl is pressed
        (event.keysym.lower() == 'v' or  # V key
         event.char == '\x16' or  # Ctrl+V character code
         event.keycode == 86)):  # V key code
        return handle_paste(event)
    
    # Check for Ctrl+A using multiple methods
    elif (event.state & 0x4 and  # Ctrl is pressed
          (event.keysym.lower() == 'a' or  # A key
           event.char == '\x01' or  # Ctrl+A character code
           event.keycode == 65)):  # A key code
        return handle_ctrl_a(event)
    
    # Check for Enter
    elif event.keysym in ['Return', 'KP_Enter']:
        return handle_enter(event)
    
    # Check for Escape
    elif event.keysym == 'Escape':
        return handle_escape(event)
    
    return None

# Bind events using multiple methods for maximum compatibility
entry.bind("<KeyPress>", handle_key_press)  # Main key handler
entry.bind("<Control-v>", handle_ctrl_v)    # Standard Ctrl+V
entry.bind("<Control-V>", handle_ctrl_v)    # Capital V
entry.bind("<Control-a>", handle_ctrl_a)    # Standard Ctrl+A
entry.bind("<Control-A>", handle_ctrl_a)    # Capital A
if sys.platform == "darwin":
    entry.bind("<Command-v>", handle_ctrl_v)
    entry.bind("<Command-V>", handle_ctrl_v)
    entry.bind("<Command-a>", handle_ctrl_a)
    entry.bind("<Command-A>", handle_ctrl_a)
    entry.bind("<Control-Button-1>", show_context_menu)  # macOS trackpad context click
entry.bind("<Escape>", handle_escape)       # Escape to clear
entry.bind("<Button-2>", show_context_menu)    # Middle mouse button context menu
entry.bind("<Button-3>", show_context_menu)    # Right mouse button context menu
entry.bind("<Return>", handle_enter)        # Enter key to download
entry.bind("<KP_Enter>", handle_enter)      # Numpad Enter

# Additional bindings for Russian layout compatibility
entry.bind("<Control-KeyPress>", handle_key_press)  # Ctrl+Key combinations
entry.bind("<Key>", handle_key_press)               # All key events

# Focus the entry widget by default
entry.focus_set()

btn_normal = None
btn_pressed = None
if IS_MACOS:
    ttk.Label(mac_content, text="Activity", style="MacSubtitle.TLabel").pack(anchor=tk.W)
    output_frame = ttk.Frame(mac_content, style="MacCard.TFrame", padding=2)
    output_frame.pack(fill=tk.BOTH, expand=True, pady=(7, 12))
    output_text = tk.Text(
        output_frame,
        height=10,
        bg="#111113",
        fg="#e5e5ea",
        insertbackground="#f5f5f7",
        selectbackground="#0a84ff",
        bd=0,
        relief="flat",
        padx=12,
        pady=10,
        wrap=tk.WORD,
        font=("Menlo", 10),
        state=tk.DISABLED,
    )
    output_scrollbar = ttk.Scrollbar(output_frame, orient=tk.VERTICAL, command=output_text.yview)
    output_text.configure(yscrollcommand=output_scrollbar.set)
    output_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    button = ttk.Button(
        mac_content,
        text="Download",
        command=on_download_clicked,
        style="MacAccent.TButton",
    )
    button.pack(fill=tk.X)
else:
    output_text = tk.Text(root, height=12, width=60, bg="#34495e", fg="white", insertbackground="white", bd=2, relief="flat", font=tk_custom_font, state=tk.DISABLED)
    output_text.pack(pady=5)

    btn_normal_path = resource_path(os.path.join("images", "button_normal.png"))
    btn_pressed_path = resource_path(os.path.join("images", "button_pressed.png"))
    if os.path.exists(btn_normal_path) and os.path.exists(btn_pressed_path) and PIL_AVAILABLE:
        try:
            btn_normal = ImageTk.PhotoImage(file=btn_normal_path)
            btn_pressed = ImageTk.PhotoImage(file=btn_pressed_path)
            button = ImageButton(root, normal_img=btn_normal, pressed_img=btn_pressed, command=on_download_clicked)
            button.pack(pady=12)
        except Exception:
            button = tk.Button(root, text="Download", font=tk_custom_font, padx=6, pady=6, command=on_download_clicked, height=2, width=14, bg="#e74c3c", fg="white", activebackground="#c0392b", bd=0)
            button.pack(pady=12)
    else:
        button = tk.Button(root, text="Download", font=tk_custom_font, padx=6, pady=6, command=on_download_clicked, height=2, width=14, bg="#e74c3c", fg="white", activebackground="#c0392b", bd=0)
        button.pack(pady=12)

# Check for updates on startup
check_for_updates()

root.mainloop()
