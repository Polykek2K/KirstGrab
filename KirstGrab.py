import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, font as tkfont  # Добавляем импорт font
import subprocess
import os
import threading
from PIL import Image, ImageTk, ImageFont

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

def handle_age_restriction():
    cookies = simpledialog.askstring(
        "Требуется аутентификация",
        "Введите cookies для обхода возрастного ограничения (в формате Netscape):",
        parent=root
    )
    if cookies:
        with open("cookies.txt", "w", encoding="utf-8") as f:
            f.write(cookies)
        return True
    return False

def download_thread():
    url = entry.get().strip()
    if not url:
        messagebox.showerror("Ошибка", "Введите URL видео!")
        return

    download_path = filedialog.askdirectory()
    if not download_path:
        return

    format_choice = format_var.get()

    if not os.path.exists("cookies.txt"):
        with open("cookies.txt", "w") as f:
            pass
        
    command = [
        'yt-dlp',
        '-f', 'bv*+ba/b' if format_choice == "Video+Audio (MP4)" else 'ba',
        '--cookies', 'cookies.txt',
        url,
        "-P", download_path
    ]

    if format_choice == "Audio only (MP3)":
        command.extend([
            '-x',
            '--audio-format', 'mp3',
            '--audio-quality', '0'
        ])

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        output_text.delete(1.0, tk.END)
        output_text.insert(tk.END, f"Загрузка: {url}\n")
        
        def read_output():
            age_restriction_detected = False
            while True:
                err_line = process.stderr.readline()
                if err_line:
                    if "Sign in to confirm your age" in err_line and not age_restriction_detected:
                        age_restriction_detected = True
                        root.after(0, lambda: handle_age_restriction_and_restart(url, download_path))
                        break
                    output_text.insert(tk.END, f"Ошибка: {err_line}")
                    output_text.see(tk.END)

                out_line = process.stdout.readline()
                if out_line:
                    output_text.insert(tk.END, out_line)
                    output_text.see(tk.END)

                if process.poll() is not None:
                    if process.returncode == 0:
                        root.after(0, lambda: output_text.insert(tk.END, "\n✅ COMPLETED!"))
                    else:
                        root.after(0, lambda: output_text.insert(tk.END, "\n❌ ERROR"))
                    break

        threading.Thread(target=read_output, daemon=True).start()
        
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось запустить yt-dlp: {e}")
        output_text.insert(tk.END, "\n❌ Ошибка: " + str(e))

def handle_age_restriction_and_restart(url, download_path):
    if handle_age_restriction():
        output_text.insert(tk.END, "\nПовторная попытка загрузки с новыми cookies...\n")
        download_thread()

def download_video():
    threading.Thread(target=download_thread, daemon=True).start()

# Создаем окно
root = tk.Tk()
root.title("KirstGrab")
co_p = resource_path("icon.ico")
if os.path.exists(ico_p):
    try:
        root.iconbitmap(ico_p)
    except Exception:
        pass
root.geometry("500x350")

# Устанавливаем цвет фона по умолчанию
default_bg = '#2c3e50'
root.config(bg=default_bg)

# Инициализация шрифта
try:
    # Сначала пробуем загрузить кастомный шрифт
    font_path = None
    for ext in ['.ttf', '.otf']:
        test_path = os.path.join('fonts', f'm6x11plus{ext}')
        if os.path.exists(test_path):
            font_path = test_path
            break
    
    if font_path:
        # Создаем объект шрифта для tkinter
        tk_custom_font = tkfont.Font(family="m6x11plus", size=10)
        # Регистрируем шрифт в tkinter
        root.tk.call('font', 'create', 'm6x11plus', '-family', 'm6x11plus', '-size', 10)
    else:
        raise FileNotFoundError("Font file not found")
except Exception as e:
    print(f"Не удалось загрузить кастомный шрифт: {e}")
    # Используем стандартный шрифт
    tk_custom_font = ("Arial", 10)

try:
    # Пытаемся загрузить фоновое изображение
    bg_image = Image.open(os.path.join("images", "background.png"))
    bg_photo = ImageTk.PhotoImage(bg_image)
    bg_label = tk.Label(root, image=bg_photo)
    bg_label.place(x=0, y=0, relwidth=1, relheight=1)
    frame_bg = ''
except Exception as e:
    print(f"Не удалось загрузить фоновое изображение: {e}")
    # Если изображение не загружено, используем цвет
    frame_bg = default_bg

# Верхняя панель с настройками
settings_frame = tk.Frame(root, bg=frame_bg if frame_bg else default_bg, bd=0)  # Исправлено условие для frame_bg
settings_frame.pack(pady=5)

# Выпадающий список для формата
format_var = tk.StringVar(value="Video+Audio (MP4)")
format_label = tk.Label(settings_frame, text="Format:", bg=frame_bg if frame_bg else default_bg, fg='white', font=tk_custom_font)
format_label.pack(side=tk.LEFT, padx=5)

format_menu = tk.OptionMenu(settings_frame, format_var, "Video+Audio (MP4)", "Audio only (MP3)")
format_menu.config(bg='#2c3e50', fg='white', highlightthickness=0, font=tk_custom_font)
format_menu["menu"].config(bg='#2c3e50', fg='white', font=tk_custom_font)
format_menu.pack(side=tk.LEFT)

# Поле ввода URL
entry = tk.Entry(root, width=60, font=tk_custom_font, bd=2, relief="flat")
entry.pack(pady=5)

# Текстовое поле для вывода
output_text = tk.Text(root, height=10, width=60, bg='#34495e', fg='white', 
                     insertbackground='white', bd=2, relief="flat", font=tk_custom_font)
output_text.pack(pady=5)

# Пытаемся загрузить кастомные изображения для кнопки
try:
    btn_normal = ImageTk.PhotoImage(file=os.path.join("images", "button_normal.png"))
    btn_pressed = ImageTk.PhotoImage(file=os.path.join("images", "button_pressed.png"))
    button = ImageButton(root, normal_img=btn_normal, pressed_img=btn_pressed, 
                        command=download_video)
    button.pack(pady=10)
except Exception as e:
    print(f"Не удалось загрузить изображения кнопки: {e}")
    button = tk.Button(
        root,
        text="Download",
        font=tk_custom_font,
        padx=3, pady=3,
        command=download_video,
        height=1, width=7,
        bg='#e74c3c',
        fg='white',
        activebackground='#c0392b',
        bd=0
    )
    button.pack(pady=10)

root.mainloop()
