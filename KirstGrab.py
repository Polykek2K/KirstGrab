import os
import sys
import ctypes
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont
import urllib.request
import urllib.parse
import json
import tempfile
import shutil
import zipfile
import re

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
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def ensure_cookies_file(path):
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8").close()

def clear_cookies_file():
    """Clear the cookies.txt file on startup"""
    cookies_path = resource_path("cookies.txt")
    try:
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write("")  # Clear the file
    except Exception as e:
        print(f"Warning: Could not clear cookies file: {e}")

def edit_cookies_file():
    """Open cookies.txt file in notepad for editing"""
    cookies_path = resource_path("cookies.txt")
    ensure_cookies_file(cookies_path)
    
    try:
        if sys.platform.startswith("win"):
            os.system(f'notepad.exe "{cookies_path}"')
        elif sys.platform.startswith("darwin"):  # macOS
            os.system(f'open -e "{cookies_path}"')
        else:  # Linux
            os.system(f'xdg-open "{cookies_path}"')
    except Exception as e:
        messagebox.showerror("Error", f"Could not open cookies file: {e}")

def paste_cookies():
    """Paste clipboard content to cookies.txt file"""
    cookies_path = resource_path("cookies.txt")
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
CURRENT_VERSION = "1.5.2"
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
                    progress_width = int(300 * (percent / 100))
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

    def cleanup_temp_files(temp_zip, extract_dir, batch_script=None):
        if temp_zip and os.path.exists(temp_zip):
            try:
                os.remove(temp_zip)
            except OSError:
                pass
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
        if batch_script and os.path.exists(batch_script):
            try:
                os.remove(batch_script)
            except OSError:
                pass

    def batch_escape(value):
        return str(value).replace("%", "%%")

    def write_windows_updater(batch_script, current_pid, current_exe, temp_exe, temp_zip, extract_dir, backup_path):
        log_path = os.path.join(tempfile.gettempdir(), "KirstGrab_update.log")
        script = f'''@echo off
setlocal
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
timeout /t 1 /nobreak >nul

if not exist "%SOURCE%" (
    echo ERROR: New executable not found: %SOURCE% >> "%LOG%"
    exit /b 1
)

if exist "%BACKUP%" del /f /q "%BACKUP%" >> "%LOG%" 2>&1

if exist "%DEST%" (
    echo Backing up current executable... >> "%LOG%"
    move /Y "%DEST%" "%BACKUP%" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo ERROR: Could not create backup. >> "%LOG%"
        exit /b 1
    )
)

echo Installing new executable... >> "%LOG%"
copy /Y "%SOURCE%" "%DEST%" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo ERROR: Copy failed. Restoring backup if possible. >> "%LOG%"
    if exist "%BACKUP%" move /Y "%BACKUP%" "%DEST%" >> "%LOG%" 2>&1
    exit /b 1
)

if exist "%BACKUP%" del /f /q "%BACKUP%" >> "%LOG%" 2>&1
if exist "%TEMPZIP%" del /f /q "%TEMPZIP%" >> "%LOG%" 2>&1
if exist "%EXTRACTDIR%" rmdir /s /q "%EXTRACTDIR%" >> "%LOG%" 2>&1

for %%I in ("%DEST%") do set "DESTDIR=%%~dpI"
echo Starting updated KirstGrab... >> "%LOG%"
start "" /D "%DESTDIR%" "%DEST%"

echo Update completed successfully. >> "%LOG%"
del /f /q "%~f0" >nul 2>&1
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

                subprocess.Popen(
                    ["cmd.exe", "/c", batch_script],
                    close_fds=True,
                    creationflags=creationflags
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

    def update_progress(percent):
        set_progress(f"Downloading update... {percent:.1f}%", percent)
    
    def download_and_replace():
        temp_zip = None
        extract_dir = None
        updater_handoff = False
        try:
            # Find the ZIP asset (release package)
            assets = latest_info.get('assets', [])
            zip_asset = None
            
            for asset in assets:
                if asset['name'].endswith('.zip') and 'release' in asset['name']:
                    zip_asset = asset
                    break
            
            if not zip_asset:
                show_update_error("Could not find release package in assets!", "Error")
                return

            if not getattr(sys, 'frozen', False):
                show_update_error("Automatic replacement is available only in the packaged application.")
                return
            
            # Download ZIP to temporary file
            temp_dir = tempfile.gettempdir()
            asset_name = os.path.basename(zip_asset.get('name', 'release.zip'))
            temp_zip = os.path.join(temp_dir, f"KirstGrab_update_{os.getpid()}_{asset_name}")
            
            set_progress("Downloading update...", 0)
            
            if not download_file(zip_asset['browser_download_url'], temp_zip, update_progress):
                show_update_error("Failed to download update!", "Error")
                return
            
            set_progress("Extracting update...", 100)
            
            # Extract the ZIP file
            extract_dir = tempfile.mkdtemp(prefix="KirstGrab_extract_")
            
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find the executable in the extracted files
            exe_files = []
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    if file.endswith('.exe') and 'KirstGrab' in file:
                        exe_files.append(os.path.join(root, file))
            
            if not exe_files:
                show_update_error("Could not find executable in release package!", "Error")
                return
            
            # Use the first (and likely only) executable found
            temp_exe = exe_files[0]
            
            set_progress("Preparing restart...", 100)
            
            # Running as compiled executable
            current_exe = sys.executable
            
            backup_path = current_exe + ".backup"
            
            # On Windows, we need to use a different approach to replace the running executable
            if sys.platform.startswith("win"):
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
            else:
                # For non-Windows systems, try direct replacement
                try:
                    shutil.copy2(temp_exe, current_exe)
                    
                    # Clean up temporary files
                    os.remove(temp_zip)
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    
                    def restart_non_windows():
                        messagebox.showinfo(
                            "Update Complete",
                            "Update completed successfully!\nThe application will now restart."
                        )
                        os.execv(current_exe, [current_exe] + sys.argv[1:])
                    set_progress("Update completed! Restarting application...", 100)
                    run_on_ui(restart_non_windows)
                except PermissionError:
                    # If permission denied, show error and clean up
                    show_update_error("Permission denied! Please run the application as administrator to update.")
                
        except Exception as e:
            show_update_error(f"Failed to update: {str(e)}")
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

def find_embedded_exe(name):
    p = resource_path(os.path.join("bin", name))
    return p if os.path.exists(p) else name

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
    yt = find_embedded_exe("yt-dlp.exe")
    ffmpeg_path = resource_path(os.path.join("bin", "ffmpeg.exe"))
    ffprobe_path = resource_path(os.path.join("bin", "ffprobe.exe"))
    deno_path = resource_path(os.path.join("bin", "deno", "deno.exe"))
    ffmpeg_dir = os.path.dirname(ffmpeg_path)
    
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
    if os.path.exists(deno_path):
        cmd.extend(["--js-runtimes", f"deno:{deno_path}"])
    # Handle cookies - only use cookies.txt file
    cookies_path = resource_path("cookies.txt")
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
    if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
        cmd.extend(["--ffmpeg-location", ffmpeg_dir])
        # Debug: Add ffmpeg path to output
        output_text.config(state=tk.NORMAL)
        output_text.insert(tk.END, f"Using ffmpeg: {ffmpeg_path}\n")
        output_text.insert(tk.END, f"Using ffprobe: {ffprobe_path}\n")
        output_text.config(state=tk.DISABLED)
    else:
        output_text.config(state=tk.NORMAL)
        if not os.path.exists(ffmpeg_path):
            output_text.insert(tk.END, f"Warning: ffmpeg not found at {ffmpeg_path}\n")
        if not os.path.exists(ffprobe_path):
            output_text.insert(tk.END, f"Warning: ffprobe not found at {ffprobe_path}\n")
        output_text.config(state=tk.DISABLED)
    return cmd

def start_download(url, download_path, format_choice, filename=None, clip_section=None):
    cmd = build_command(url, download_path, format_choice, filename, clip_section)
    
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
            bufsize=1,
            startupinfo=startupinfo
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

root = tk.Tk()
root.title("KirstGrab")

# Set icon before configuring the window
ico_p = resource_path("icon.ico")
if os.path.exists(ico_p):
    try:
        root.iconbitmap(ico_p)
    except Exception:
        # Try alternative method
        try:
            root.tk.call('wm', 'iconbitmap', root._w, ico_p)
        except Exception:
            pass
# Increase GUI size by 50% to accommodate all controls
default_width = int(500 * 1.5)  # 750
default_height = int(350 * 1.25)  # 437
expanded_height = default_height + 45
root.geometry(f"{default_width}x{default_height}")
root.resizable(False, False)  # Disable window resizing
default_bg = "#2c3e50"
root.config(bg=default_bg)

# Clear cookies file on startup
clear_cookies_file()

tk_custom_font = ("Arial", 12)
font_file = resource_path(os.path.join("fonts", "m6x11plus.ttf"))
if os.path.exists(font_file) and PIL_AVAILABLE:
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
        tk_custom_font = ("Arial", 12)

bg_photo = None
bg_label = None
bg_image_original = None
frame_bg = default_bg
bg_path = resource_path(os.path.join("images", "background.png"))
if os.path.exists(bg_path) and PIL_AVAILABLE:
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
    root.geometry(f"{default_width}x{height}")
    if bg_label is not None and bg_image_original is not None and PIL_AVAILABLE:
        try:
            resized_bg = bg_image_original.resize((default_width, height), Image.Resampling.LANCZOS)
            bg_photo = ImageTk.PhotoImage(resized_bg)
            bg_label.config(image=bg_photo)
            bg_label.image = bg_photo
        except Exception:
            pass

settings_frame = tk.Frame(root, bg=frame_bg if frame_bg else default_bg, bd=0)
settings_frame.pack(pady=5)

format_var = tk.StringVar(value="Best Quality (MP4)")
format_label = tk.Label(settings_frame, text="Format:", bg=frame_bg if frame_bg else default_bg, fg="white", font=tk_custom_font)
format_label.pack(side=tk.LEFT, padx=5)

format_options = [
    "Best Quality (MP4)",
    "Audio only (MP3)"
]

format_menu = tk.OptionMenu(settings_frame, format_var, *format_options)
format_menu.config(bg="#2c3e50", fg="white", highlightthickness=0, font=tk_custom_font)
format_menu["menu"].config(bg="#2c3e50", fg="white", font=tk_custom_font)
format_menu.pack(side=tk.LEFT)

# Add cookies management
cookies_label = tk.Label(settings_frame, text="Cookies:", bg=frame_bg if frame_bg else default_bg, fg="white", font=tk_custom_font)
cookies_label.pack(side=tk.LEFT, padx=(20, 5))

# Add edit cookies button
edit_cookies_btn = tk.Button(settings_frame, text="📝 Edit Cookies", command=edit_cookies_file,
                            font=tk_custom_font, bg="#e67e22", fg="white", 
                            activebackground="#d35400", bd=0, padx=8)
edit_cookies_btn.pack(side=tk.LEFT, padx=(10, 0))

# Add paste cookies button
paste_cookies_btn = tk.Button(settings_frame, text="📋 Paste Cookies", command=paste_cookies,
                             font=tk_custom_font, bg="#9b59b6", fg="white", 
                             activebackground="#8e44ad", bd=0, padx=8)
paste_cookies_btn.pack(side=tk.LEFT, padx=(10, 0))


# Add manual update check button
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

update_check_btn = tk.Button(settings_frame, text="🔄 Check Updates", command=manual_update_check,
                            font=tk_custom_font, bg="#27ae60", fg="white", 
                            activebackground="#229954", bd=0, padx=8)
update_check_btn.pack(side=tk.LEFT, padx=(10, 0))

# Create entry frame with paste button
entry_frame = tk.Frame(root, bg=default_bg)
entry_frame.pack(pady=5)

entry = tk.Entry(entry_frame, width=55, font=tk_custom_font, bd=2, relief="flat")
entry.pack(side=tk.LEFT, padx=(0, 5))

# Add a paste button as backup
paste_button = tk.Button(entry_frame, text="📋 Paste", command=lambda: handle_paste(None), 
                        font=tk_custom_font, bg="#3498db", fg="white", 
                        activebackground="#2980b9", bd=0, padx=10)
paste_button.pack(side=tk.LEFT)

clip_var = tk.BooleanVar(value=False)
clip_start_var = tk.StringVar()
clip_end_var = tk.StringVar()

def toggle_clip_controls():
    if clip_var.get():
        clip_controls_frame.pack(pady=(0, 5), before=help_label)
        set_window_height(expanded_height)
        clip_start_entry.focus_set()
    else:
        clip_controls_frame.pack_forget()
        set_window_height(default_height)

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
    highlightthickness=0
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

# Add help text
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
        context_menu = tk.Menu(root, tearoff=0, bg="#2c3e50", fg="white", font=tk_custom_font,
                              activebackground="#3498db", activeforeground="white")
        context_menu.add_command(label="📋 Paste (Ctrl+V)", command=lambda: handle_paste(None))
        context_menu.add_separator()
        context_menu.add_command(label="✂️ Cut", command=lambda: entry.event_generate("<<Cut>>"))
        context_menu.add_command(label="📄 Copy", command=lambda: entry.event_generate("<<Copy>>"))
        context_menu.add_separator()
        context_menu.add_command(label="🔍 Select All (Ctrl+A)", command=lambda: handle_ctrl_a(None))
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

output_text = tk.Text(root, height=12, width=60, bg="#34495e", fg="white", insertbackground="white", bd=2, relief="flat", font=tk_custom_font, state=tk.DISABLED)
output_text.pack(pady=5)

btn_normal = None
btn_pressed = None
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
