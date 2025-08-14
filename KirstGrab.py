import os
import sys
import ctypes
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, font as tkfont
from PIL import Image, ImageTk, ImageFont

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
        "-f", "bv*+ba/b" if format_choice == "Video+Audio (MP4)" else "ba",
        "--cookies", cookies_path,
        url,
        "-P", download_path,
        "--progress"
    ]
    if format_choice == "Audio only (MP3)":
        cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    if os.path.exists(ffmpeg_path):
        cmd.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_path)])
    return cmd

def start_download(url, download_path, format_choice):
    cookies_path = os.path.abspath("cookies.txt")
    ensure_cookies_file(cookies_path)
    cmd = build_command(url, download_path, format_choice, cookies_path)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
        while True:
            try:
                err_line = proc.stderr.readline()
            except Exception:
                err_line = ""
            if err_line:
                def append_err(line=err_line):
                    output_text.insert(tk.END, f"Ошибка: {line}")
                    output_text.see(tk.END)
                root.after(0, append_err)
                if "Sign in to confirm your age" in err_line:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    def prompt_and_restart():
                        cookies = simpledialog.askstring(
                            "Требуется аутентификация",
                            "Введите cookies для обхода возрастного ограничения (в формате Netscape):",
                            parent=root
                        )
                        if cookies:
                            with open(os.path.abspath("cookies.txt"), "w", encoding="utf-8") as f:
                                f.write(cookies)
                            start_download(url, download_path, format_choice)
                        else:
                            output_text.insert(tk.END, "\nОтмена ввода cookies. Прервано.\n")
                    root.after(0, prompt_and_restart)
                    break
            try:
                out_line = proc.stdout.readline()
            except Exception:
                out_line = ""
            if out_line:
                def append_out(line=out_line):
                    output_text.insert(tk.END, line)
                    output_text.see(tk.END)
                root.after(0, append_out)
            if proc.poll() is not None:
                code = proc.returncode
                if code == 0:
                    root.after(0, lambda: output_text.insert(tk.END, "\n✅ COMPLETED!"))
                else:
                    root.after(0, lambda: output_text.insert(tk.END, f"\n❌ ERROR (code {code})"))
                break

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
ico_p = resource_path("icon.ico")
if os.path.exists(ico_p):
    try:
        root.iconbitmap(ico_p)
    except Exception:
        pass
root.geometry("500x350")
default_bg = "#2c3e50"
root.config(bg=default_bg)

tk_custom_font = ("Arial", 10)
font_file = resource_path(os.path.join("fonts", "m6x11plus.ttf"))
if os.path.exists(font_file):
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
            tk_custom_font = tkfont.Font(family=family_name, size=10)
        except Exception:
            tk_custom_font = (family_name, 10)
    except Exception:
        tk_custom_font = ("Arial", 10)

bg_photo = None
frame_bg = default_bg
bg_path = resource_path(os.path.join("images", "background.png"))
if os.path.exists(bg_path):
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

format_var = tk.StringVar(value="Video+Audio (MP4)")
format_label = tk.Label(settings_frame, text="Format:", bg=frame_bg if frame_bg else default_bg, fg="white", font=tk_custom_font)
format_label.pack(side=tk.LEFT, padx=5)

format_menu = tk.OptionMenu(settings_frame, format_var, "Video+Audio (MP4)", "Audio only (MP3)")
format_menu.config(bg="#2c3e50", fg="white", highlightthickness=0, font=tk_custom_font)
format_menu["menu"].config(bg="#2c3e50", fg="white", font=tk_custom_font)
format_menu.pack(side=tk.LEFT)

entry = tk.Entry(root, width=60, font=tk_custom_font, bd=2, relief="flat")
entry.pack(pady=5)

output_text = tk.Text(root, height=10, width=60, bg="#34495e", fg="white", insertbackground="white", bd=2, relief="flat", font=tk_custom_font)
output_text.pack(pady=5)

btn_normal = None
btn_pressed = None
btn_normal_path = resource_path(os.path.join("images", "button_normal.png"))
btn_pressed_path = resource_path(os.path.join("images", "button_pressed.png"))
if os.path.exists(btn_normal_path) and os.path.exists(btn_pressed_path):
    try:
        btn_normal = ImageTk.PhotoImage(file=btn_normal_path)
        btn_pressed = ImageTk.PhotoImage(file=btn_pressed_path)
        button = ImageButton(root, normal_img=btn_normal, pressed_img=btn_pressed, command=on_download_clicked)
        button.pack(pady=10)
    except Exception:
        button = tk.Button(root, text="Download", font=tk_custom_font, padx=3, pady=3, command=on_download_clicked, height=1, width=7, bg="#e74c3c", fg="white", activebackground="#c0392b", bd=0)
        button.pack(pady=10)
else:
    button = tk.Button(root, text="Download", font=tk_custom_font, padx=3, pady=3, command=on_download_clicked, height=1, width=7, bg="#e74c3c", fg="white", activebackground="#c0392b", bd=0)
    button.pack(pady=10)

root.mainloop()
