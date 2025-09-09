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

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def ensure_cookies_file(path):
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8").close()

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

def build_command(url, download_path, format_choice, cookies_path):
    yt = find_embedded_exe("yt-dlp.exe")
    ffmpeg_path = resource_path(os.path.join("bin", "ffmpeg.exe"))
    cmd = [
        yt,
        "--cookies", cookies_path,
        "--no-check-certificates",  # Skip SSL certificate verification
        "--prefer-free-formats",    # Prefer free formats when available
        "--merge-output-format", "mp4",  # Merge to MP4 when possible
        url,
        "-P", download_path,
        "--progress-template", "%(progress._percent_str)s %(progress._eta_str)s",
    ]
    
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
    if os.path.exists(ffmpeg_path):
        cmd.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_path)])
        # Debug: Add ffmpeg path to output
        output_text.insert(tk.END, f"Using ffmpeg: {ffmpeg_path}\n")
    else:
        output_text.insert(tk.END, f"Warning: ffmpeg not found at {ffmpeg_path}\n")
    return cmd

def start_download(url, download_path, format_choice):
    cookies_path = os.path.abspath("cookies.txt")
    ensure_cookies_file(cookies_path)
    cmd = build_command(url, download_path, format_choice, cookies_path)
    
    # Debug: Show the command being executed
    output_text.insert(tk.END, f"Format: {format_choice}\n")
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
    start_download(url, download_path, format_var.get())

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

entry = tk.Entry(root, width=60, font=tk_custom_font, bd=2, relief="flat")
entry.pack(pady=5)

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
