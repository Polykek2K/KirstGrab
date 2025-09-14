import os
import sys
import ctypes
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont

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

def get_available_browsers():
    """Get list of available browsers for yt-dlp"""
    return [
        "cookies.txt (file)",
        "chrome",
        "chromium", 
        "edge",
        "firefox",
        "opera",
        "safari",
        "vivaldi"
    ]

def find_embedded_exe(name):
    p = resource_path(os.path.join("bin", name))
    return p if os.path.exists(p) else name

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

def build_command(url, download_path, format_choice, cookies_source):
    yt = find_embedded_exe("yt-dlp.exe")
    ffmpeg_path = resource_path(os.path.join("bin", "ffmpeg.exe"))
    ffprobe_path = resource_path(os.path.join("bin", "ffprobe.exe"))
    ffmpeg_dir = os.path.dirname(ffmpeg_path)
    
    cmd = [
        yt,
        "--no-check-certificates",  # Skip SSL certificate verification
        "--prefer-free-formats",    # Prefer free formats when available
        "--merge-output-format", "mp4",  # Merge to MP4 when possible
        url,
        "-P", download_path,
        "--progress-template", "%(progress._percent_str)s %(progress._eta_str)s",
    ]
    
    # Handle cookies source
    if cookies_source == "cookies.txt (file)":
        cookies_path = resource_path("cookies.txt")
        ensure_cookies_file(cookies_path)
        # Only use cookies if the file is not empty
        if os.path.getsize(cookies_path) > 0:
            cmd.extend(["--cookies", cookies_path])
    else:
        # Use browser cookies
        cmd.extend(["--cookies-from-browser", cookies_source])
    
    # Set format based on choice
    if format_choice == "Best Quality (MP4)":
        # Download best video+audio, prefer MP4, fallback to best available
        cmd.extend(["-f", "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"])
    elif format_choice == "Best Quality (Any Format)":
        # Download best available quality in any format
        cmd.extend(["-f", "bestvideo+bestaudio/best"])
    elif format_choice == "1080p (MP4)":
        # Download 1080p video, fallback to best available
        cmd.extend(["-f", "best[height<=1080][ext=mp4]/bestvideo[height<=1080]+bestaudio[ext=m4a]/best[height<=1080]/best"])
    elif format_choice == "720p (MP4)":
        # Download 720p video, fallback to best available
        cmd.extend(["-f", "best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]/best"])
    elif format_choice == "480p (MP4)":
        # Download 480p video, fallback to best available
        cmd.extend(["-f", "best[height<=480][ext=mp4]/bestvideo[height<=480]+bestaudio[ext=m4a]/best[height<=480]/best"])
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
        output_text.insert(tk.END, f"Using ffmpeg: {ffmpeg_path}\n")
        output_text.insert(tk.END, f"Using ffprobe: {ffprobe_path}\n")
    else:
        if not os.path.exists(ffmpeg_path):
            output_text.insert(tk.END, f"Warning: ffmpeg not found at {ffmpeg_path}\n")
        if not os.path.exists(ffprobe_path):
            output_text.insert(tk.END, f"Warning: ffprobe not found at {ffprobe_path}\n")
    return cmd

def start_download(url, download_path, format_choice, cookies_source):
    cmd = build_command(url, download_path, format_choice, cookies_source)
    
    # Debug: Show the command being executed
    output_text.insert(tk.END, f"Format: {format_choice}\n")
    output_text.insert(tk.END, f"Cookies: {cookies_source}\n")
    output_text.insert(tk.END, f"Command: {' '.join(cmd)}\n")
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось запустить yt-dlp: {e}")
        output_text.insert(tk.END, "\n❌ Ошибка: " + str(e))
        return

    output_text.delete(1.0, tk.END)
    output_text.insert(tk.END, f"Загрузка: {url}\n")

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
                    root.after(0, lambda: output_text.insert(tk.END,
                        "\n✅ COMPLETED!" if code == 0 else f"\n❌ ERROR (code {code})"))
                    break
                continue

            if ch == "\r":
                # перезаписываем последнюю строку (для прогресса)
                def replace_line(line=buffer_line):
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
                root.after(0, replace_line)
                buffer_line = ""
            elif ch == "\n":
                def append_line(line=buffer_line):
                    output_text.insert(tk.END, line + "\n")
                    # Сбрасываем флаг строки прогресса при добавлении новой строки
                    progress_line_created[0] = False
                    output_text.see(tk.END)
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
    download_path = filedialog.askdirectory()
    if not download_path:
        return
    start_download(url, download_path, format_var.get(), cookies_var.get())

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
root.geometry("500x350")
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
frame_bg = default_bg
bg_path = resource_path(os.path.join("images", "background.png"))
if os.path.exists(bg_path) and PIL_AVAILABLE:
    try:
        bg_image = Image.open(bg_path)
        bg_photo = ImageTk.PhotoImage(bg_image)
        bg_label = tk.Label(root, image=bg_photo)
        bg_label.image = bg_photo
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        frame_bg = ""
    except Exception:
        frame_bg = default_bg

settings_frame = tk.Frame(root, bg=frame_bg if frame_bg else default_bg, bd=0)
settings_frame.pack(pady=5)

format_var = tk.StringVar(value="Best Quality (MP4)")
format_label = tk.Label(settings_frame, text="Format:", bg=frame_bg if frame_bg else default_bg, fg="white", font=tk_custom_font)
format_label.pack(side=tk.LEFT, padx=5)

format_options = [
    "Best Quality (MP4)",
    "Best Quality (Any Format)", 
    "1080p (MP4)",
    "720p (MP4)",
    "480p (MP4)",
    "Audio only (MP3)"
]

format_menu = tk.OptionMenu(settings_frame, format_var, *format_options)
format_menu.config(bg="#2c3e50", fg="white", highlightthickness=0, font=tk_custom_font)
format_menu["menu"].config(bg="#2c3e50", fg="white", font=tk_custom_font)
format_menu.pack(side=tk.LEFT)

# Add cookies management
cookies_var = tk.StringVar(value="cookies.txt (file)")
cookies_label = tk.Label(settings_frame, text="Cookies:", bg=frame_bg if frame_bg else default_bg, fg="white", font=tk_custom_font)
cookies_label.pack(side=tk.LEFT, padx=(20, 5))

cookies_menu = tk.OptionMenu(settings_frame, cookies_var, *get_available_browsers())
cookies_menu.config(bg="#2c3e50", fg="white", highlightthickness=0, font=tk_custom_font)
cookies_menu["menu"].config(bg="#2c3e50", fg="white", font=tk_custom_font)
cookies_menu.pack(side=tk.LEFT)

# Add edit cookies button
edit_cookies_btn = tk.Button(settings_frame, text="📝 Edit Cookies", command=edit_cookies_file,
                            font=tk_custom_font, bg="#e67e22", fg="white", 
                            activebackground="#d35400", bd=0, padx=8)
edit_cookies_btn.pack(side=tk.LEFT, padx=(10, 0))

# Function to toggle edit cookies button visibility
def toggle_edit_cookies_button(*args):
    """Show/hide edit cookies button based on cookies source selection"""
    if cookies_var.get() == "cookies.txt (file)":
        edit_cookies_btn.pack(side=tk.LEFT, padx=(10, 0))
    else:
        edit_cookies_btn.pack_forget()

# Bind the toggle function to cookies selection
cookies_var.trace('w', toggle_edit_cookies_button)

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

output_text = tk.Text(root, height=12, width=60, bg="#34495e", fg="white", insertbackground="white", bd=2, relief="flat", font=tk_custom_font)
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
        button = tk.Button(root, text="Download", font=tk_custom_font, padx=3, pady=3, command=on_download_clicked, height=1, width=7, bg="#e74c3c", fg="white", activebackground="#c0392b", bd=0)
        button.pack(pady=12)
else:
    button = tk.Button(root, text="Download", font=tk_custom_font, padx=3, pady=3, command=on_download_clicked, height=1, width=7, bg="#e74c3c", fg="white", activebackground="#c0392b", bd=0)
    button.pack(pady=12)

root.mainloop()
