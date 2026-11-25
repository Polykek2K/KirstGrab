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
import re
import webbrowser
from pathlib import Path

from kirstgrab_platform import (
    bundled_binary_paths,
    clean_subprocess_environment,
    cookies_file_path,
    directory_is_writable,
    find_macos_app_bundle,
    macos_app_requires_manual_replacement,
    release_platform_key,
    select_release_asset,
)

from kirstgrab_updater import (
    download_release_archive,
    extract_release_archive,
    find_update_payload,
    launch_update_helper,
    release_sha256,
)

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
CURRENT_VERSION = "1.6.9"
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

update_dialog = None


def show_update_dialog(latest_info):
    """Show the available update or focus the existing dialog."""
    global update_dialog
    if update_dialog is not None and update_dialog.winfo_exists():
        update_dialog.lift()
        return
    dialog = update_dialog = tk.Toplevel(root)
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
        update_button = ttk.Button(
            button_frame,
            text="Update now",
            style="MacAccent.TButton",
            command=lambda: start_update(
                dialog, latest_info, progress_label, progress_bar, (update_button, later_button)
            ),
        )
        update_button.pack(side=tk.RIGHT)
        later_button = ttk.Button(
            button_frame,
            text="Not now",
            style="Mac.TButton",
            command=dialog.destroy,
        )
        later_button.pack(side=tk.RIGHT, padx=(0, 10))
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
                             command=lambda: start_update(
                                 dialog, latest_info, progress_label, progress_bar,
                                 (update_button, later_button, skip_button)
                             ))
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

def start_update(dialog, latest_info, progress_label, progress_bar, buttons):
    """Download and prepare an update while the application is still running."""
    for button in buttons:
        button.configure(state=tk.DISABLED)
    dialog.protocol("WM_DELETE_WINDOW", lambda: None)

    def set_progress(text, percent):
        def apply_progress():
            if not dialog.winfo_exists():
                return
            progress_label.configure(text=text)
            width = progress_bar.master.winfo_width() if sys.platform == "darwin" else 300
            progress_bar.configure(width=int(width * percent / 100))
        root.after(0, apply_progress)

    def show_failure(message, manual=False):
        def show_message():
            if not dialog.winfo_exists():
                return
            for button in buttons:
                button.configure(state=tk.NORMAL)
            dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
            if manual:
                messagebox.showinfo("Manual Update Required", message, parent=dialog)
                release_url = latest_info.get("html_url")
                if release_url:
                    webbrowser.open(release_url)
            else:
                messagebox.showerror("Update Error", message, parent=dialog)
        set_progress("Manual update required" if manual else "Update failed", 0)
        root.after(0, show_message)

    def download_and_replace():
        work_dir = None
        try:
            if not getattr(sys, "frozen", False) or sys.platform not in ("win32", "darwin"):
                show_failure("Open the release page to install the packaged application.", manual=True)
                return

            asset = select_release_asset(latest_info.get("assets") or [])
            if not asset:
                show_failure(f"This release has no package for {release_platform_key()}.", manual=True)
                return
            digest = release_sha256(asset)
            if not digest:
                show_failure("This release package has no valid SHA-256 checksum.", manual=True)
                return

            destination = Path(sys.executable).resolve()
            if sys.platform == "darwin":
                bundle = find_macos_app_bundle(str(destination))
                if not bundle or macos_app_requires_manual_replacement(bundle):
                    show_failure(
                        "Move KirstGrab.app to Applications and launch it there, or install the update manually.",
                        manual=True,
                    )
                    return
                destination = Path(bundle)
            if not directory_is_writable(destination.parent):
                show_failure("Install the update manually to replace KirstGrab in this folder.", manual=True)
                return

            url = asset.get("browser_download_url")
            if not url:
                raise ValueError("The release package has no download URL")
            work_dir = Path(tempfile.mkdtemp(prefix="KirstGrab_update_"))
            archive = work_dir / "release.zip"
            extracted = work_dir / "extracted"

            set_progress("Downloading update...", 0)
            download_release_archive(
                url, archive, digest,
                lambda percent: set_progress(f"Downloading update... {percent:.1f}%", percent),
            )
            set_progress("Verifying release package...", 100)
            extract_release_archive(archive, extracted)
            source = find_update_payload(extracted, destination, latest_info.get("tag_name", ""))
            set_progress("Preparing restart...", 100)
            launch_update_helper(work_dir, source, destination)
            work_dir = None  # The helper now owns the temporary files.
            root.after(0, root.destroy)
        except Exception as error:
            show_failure(f"Failed to prepare the update: {error}")
        finally:
            if work_dir is not None:
                shutil.rmtree(work_dir, ignore_errors=True)

    threading.Thread(target=download_and_replace, daemon=True).start()


def check_for_updates(interactive=False):
    """Check for updates in the background at startup or from the settings button."""
    def check_thread():
        latest_info = get_latest_release_info()
        if latest_info and compare_versions(CURRENT_VERSION, latest_info.get("tag_name", "")):
            root.after(0, show_update_dialog, latest_info)
        elif interactive:
            if latest_info:
                root.after(0, messagebox.showinfo, "No Updates",
                           f"You are running the latest version ({CURRENT_VERSION})!")
            else:
                root.after(0, messagebox.showerror, "Update Check Failed",
                           "Could not check for updates. Please check your internet connection.")

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
# Keep the same compact composition on both desktop platforms. macOS uses
# explicit themed controls below so Aqua cannot replace button colors.
if IS_MACOS:
    default_width = 750
    default_height = 437
    expanded_height = 482
    default_bg = "#2c3e50"
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
    check_for_updates(interactive=True)


clip_var = tk.BooleanVar(value=False)
clip_start_var = tk.StringVar()
clip_end_var = tk.StringVar()


def toggle_clip_controls():
    if clip_var.get():
        if IS_MACOS:
            clip_controls_frame.pack(
                fill=tk.X,
                padx=14,
                pady=(0, 5),
                before=help_label,
            )
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

    windows_surface = "#2c3e50"
    style.configure("MacWindows.TFrame", background=windows_surface)
    style.configure(
        "MacWindows.TLabel",
        background=windows_surface,
        foreground="white",
        font=(system_font_family, 11),
    )
    style.configure(
        "MacWindowsHint.TLabel",
        background=windows_surface,
        foreground="#bdc3c7",
        font=(system_font_family, 9),
    )
    style.configure(
        "MacWindows.TEntry",
        fieldbackground="#f5f5f7",
        foreground="#1c1c1e",
        insertcolor="#1c1c1e",
        bordercolor="#d1d1d6",
        lightcolor="#d1d1d6",
        darkcolor="#d1d1d6",
        padding=7,
        font=(system_font_family, 11),
    )
    style.map(
        "MacWindows.TEntry",
        fieldbackground=[("focus", "#ffffff"), ("!focus", "#f5f5f7")],
        bordercolor=[("focus", "#3498db"), ("!focus", "#d1d1d6")],
    )
    style.configure(
        "MacWindows.TCheckbutton",
        background=windows_surface,
        foreground="white",
        focuscolor=windows_surface,
        font=(system_font_family, 11),
    )
    style.map(
        "MacWindows.TCheckbutton",
        background=[("active", windows_surface), ("pressed", windows_surface)],
        foreground=[("disabled", "#8e8e93"), ("!disabled", "white")],
    )

    def configure_windows_button_style(name, color, active_color, pressed_color):
        style.configure(
            name,
            background=color,
            foreground="white",
            borderwidth=0,
            focusthickness=0,
            focuscolor=color,
            padding=(9, 7),
            font=(system_font_family, 10),
        )
        style.map(
            name,
            background=[
                ("disabled", "#636366"),
                ("pressed", pressed_color),
                ("active", active_color),
                ("!disabled", color),
            ],
            foreground=[("disabled", "#d1d1d6"), ("!disabled", "white")],
        )

    configure_windows_button_style(
        "MacWindowsOrange.TButton", "#e67e22", "#f39c3d", "#d35400"
    )
    configure_windows_button_style(
        "MacWindowsPurple.TButton", "#9b59b6", "#ad6dc5", "#8e44ad"
    )
    configure_windows_button_style(
        "MacWindowsGreen.TButton", "#27ae60", "#3bc474", "#229954"
    )
    configure_windows_button_style(
        "MacWindowsBlue.TButton", "#3498db", "#4aa8e8", "#2980b9"
    )
    configure_windows_button_style(
        "MacWindowsDownload.TButton", "#e74c3c", "#f05d4e", "#c0392b"
    )
    style.configure(
        "MacWindowsDownload.TButton",
        padding=(18, 10),
        font=(system_font_family, 12, "bold"),
    )

    settings_frame = ttk.Frame(root, style="MacWindows.TFrame", padding=(10, 7))
    settings_frame.pack(fill=tk.X, padx=14, pady=(10, 5))
    ttk.Label(settings_frame, text="Format:", style="MacWindows.TLabel").pack(
        side=tk.LEFT, padx=(0, 5)
    )
    format_menu = ttk.Combobox(
        settings_frame,
        textvariable=format_var,
        values=format_options,
        state="readonly",
        width=20,
        style="Mac.TCombobox",
    )
    format_menu.pack(side=tk.LEFT)
    ttk.Label(settings_frame, text="Cookies:", style="MacWindows.TLabel").pack(
        side=tk.LEFT, padx=(18, 5)
    )
    edit_cookies_btn = ttk.Button(
        settings_frame,
        text="📝 Edit Cookies",
        command=edit_cookies_file,
        style="MacWindowsOrange.TButton",
    )
    edit_cookies_btn.pack(side=tk.LEFT, padx=(5, 0))
    paste_cookies_btn = ttk.Button(
        settings_frame,
        text="📋 Paste Cookies",
        command=paste_cookies,
        style="MacWindowsPurple.TButton",
    )
    paste_cookies_btn.pack(side=tk.LEFT, padx=(7, 0))
    update_check_btn = ttk.Button(
        settings_frame,
        text="🔄 Check Updates",
        command=manual_update_check,
        style="MacWindowsGreen.TButton",
    )
    update_check_btn.pack(side=tk.LEFT, padx=(7, 0))

    entry_frame = ttk.Frame(root, style="MacWindows.TFrame", padding=(10, 6))
    entry_frame.pack(fill=tk.X, padx=14, pady=5)
    entry = ttk.Entry(entry_frame, style="MacWindows.TEntry")
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    paste_button = ttk.Button(
        entry_frame,
        text="📋 Paste",
        command=lambda: handle_paste(None),
        style="MacWindowsBlue.TButton",
    )
    paste_button.pack(side=tk.LEFT, padx=(7, 0))
    clip_check = ttk.Checkbutton(
        entry_frame,
        text="Clip",
        variable=clip_var,
        command=toggle_clip_controls,
        style="MacWindows.TCheckbutton",
    )
    clip_check.pack(side=tk.LEFT, padx=(10, 0))

    clip_controls_frame = ttk.Frame(
        root, style="MacWindows.TFrame", padding=(10, 5)
    )
    clip_start_label = ttk.Label(
        clip_controls_frame, text="From:", style="MacWindows.TLabel"
    )
    clip_start_label.pack(side=tk.LEFT)
    clip_start_entry = ttk.Entry(
        clip_controls_frame,
        width=12,
        textvariable=clip_start_var,
        style="MacWindows.TEntry",
    )
    clip_start_entry.pack(side=tk.LEFT, padx=(6, 14))
    clip_end_label = ttk.Label(
        clip_controls_frame, text="To:", style="MacWindows.TLabel"
    )
    clip_end_label.pack(side=tk.LEFT)
    clip_end_entry = ttk.Entry(
        clip_controls_frame,
        width=12,
        textvariable=clip_end_var,
        style="MacWindows.TEntry",
    )
    clip_end_entry.pack(side=tk.LEFT, padx=(6, 0))
    help_label = ttk.Label(
        root,
        text="💡 Tip: Right-click in the URL field for paste options",
        style="MacWindowsHint.TLabel",
        padding=(8, 3),
    )
    help_label.pack(pady=(0, 5))
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
    output_frame = ttk.Frame(root, style="MacWindows.TFrame", padding=2)
    output_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=5)
    output_text = tk.Text(
        output_frame,
        height=12,
        width=60,
        bg="#34495e",
        fg="white",
        insertbackground="white",
        selectbackground="#3498db",
        bd=0,
        relief="flat",
        padx=8,
        pady=7,
        wrap=tk.WORD,
        font=tk_custom_font,
        state=tk.DISABLED,
    )
    output_scrollbar = ttk.Scrollbar(output_frame, orient=tk.VERTICAL, command=output_text.yview)
    output_text.configure(yscrollcommand=output_scrollbar.set)
    output_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    button = ttk.Button(
        root,
        text="Download",
        command=on_download_clicked,
        style="MacWindowsDownload.TButton",
        width=18,
    )
    button.pack(pady=(5, 12))
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
