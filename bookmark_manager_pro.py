
import sys
import os
import json
import uuid
import platform
import subprocess
import base64
import ctypes
from ctypes import wintypes
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, colorchooser, messagebox
    import tkinter.font as tkfont
except Exception:
    print("tkinter is required.")
    sys.exit(1)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

try:
    import tkinterdnd2 as tkdnd
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False


DEFAULT_FILE = "bookmarks_v2.json"
LAST_FILE_STATE = ".bookmark_last_v2.json"
DEFAULT_ICON_PNG = "default_icon.png"
DEFAULT_ICON_ICO = "default_icon.ico"

DEFAULT_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAACXBIWXMAAAsSAAALEgHS3X78AAA"
    "Gd0lEQVRYw+2XwW7cMBCGv1b5FzqS5g94yXg5Yj1Nw1w9k1Jw5i6qJ2o5F0fC3y0aB9Qy2JbK5b0b8"
    "Zk9C9b0c4jW3dQ7gk0n9E2Z7w0Wm8wqO6mQ2l8oW+v8cO4dH3yQq7Cw7dP0pC8q9J8k3jG1mG7kM6o"
    "u4RC0lI3pGJ7y2cYpGzR3b8d4x2o4aPz6y8pQmF7s2Rj9v0R3yEZD9W2TzYb4v8H3l2H8wGk7c0gk"
    "ZP6l4oV6eC3bB9w4oX4c3u0w8n1m1i0d3G8E8D6bQqKgiGmC8/fh9zM8y1aG8X3lJb0m0p7I2lqk2l"
    "CkAqJYj6Q8WJ1nq3mDkJcL2gk9QopG6yK2hlgQ4CkqXgqgqfY6i6C3d0QxP6cLwq8z7bB4suZ6iQG9"
    "bJg9Wb3kqSxvC8KkFjGJxkGxZJk2oQkQyPVbqZ9e2CwWkUj2mEw2mI4H0m6N0n1J8m3L5Yz7k3C8Jk"
    "R3G1mKf4P8v1r2+K8y2k4Q0n0B9V8f0l6a4aTg8b+o2DqBqD8kqBtH2cE2qC1A7FJf7gY6YFf4J3c/"
    "oC0k2m/9zJ8tQ7Y5aI9GJcCw3l6f3/XKx6p9K4z8mHfX7i6wZC9oC3C0s0B0P0g0g0g0g0g0g0g0g0"
    "g0g0g0g0g0g0g0g0g0g0+8AF3K6b3s3mJQAAAABJRU5ErkJggg=="
)


def ensure_default_icons():
    if not os.path.exists(DEFAULT_ICON_PNG):
        try:
            with open(DEFAULT_ICON_PNG, "wb") as f:
                f.write(base64.b64decode(DEFAULT_PNG_B64))
        except Exception:
            pass
    if not os.path.exists(DEFAULT_ICON_ICO) and PIL_AVAILABLE and os.path.exists(DEFAULT_ICON_PNG):
        try:
            img = Image.open(DEFAULT_ICON_PNG).convert("RGBA")
            img.save(DEFAULT_ICON_ICO, format="ICO", sizes=[(32, 32), (48, 48), (64, 64)])
        except Exception:
            pass


def rel_or_abs(path):
    try:
        cwd = os.path.abspath(os.getcwd())
        ap = os.path.abspath(path)
        if ap.startswith(cwd):
            return os.path.relpath(ap, cwd)
        return ap
    except Exception:
        return path


def open_local(path):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Open Failed", str(e))


def webbrowser_open(url):
    import webbrowser
    webbrowser.open(url)


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def set_windows_titlebar(hwnd, caption_rgb, text_rgb, dark=True):
    try:
        if platform.system() != "Windows":
            return
        dwm = ctypes.WinDLL("dwmapi")
        DwmSetWindowAttribute = dwm.DwmSetWindowAttribute
        DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPCVOID, wintypes.DWORD]
        DwmSetWindowAttribute.restype = wintypes.HRESULT

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR = 36

        val = wintypes.BOOL(1 if dark else 0)
        DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val))

        def rgb_to_bgra(c):
            r, g, b = c
            return ctypes.c_int((b << 16) | (g << 8) | r)

        caption = rgb_to_bgra(caption_rgb)
        text = rgb_to_bgra(text_rgb)
        DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption))
        DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text))
    except Exception:
        pass


class ResponsiveToolbar(tk.Frame):
    def __init__(self, master, bg):
        super().__init__(master, bg=bg)
        self.bg = bg
        self.items = []
        self.bind("<Configure>", self._on_configure)

    def add_widget(self, widget, min_width=120, group="left", stretch=False):
        self.items.append({
            "widget": widget,
            "min_width": min_width,
            "group": group,
            "stretch": stretch,
        })

    def _on_configure(self, _event=None):
        self.reflow()

    def reflow(self):
        for child in self.winfo_children():
            child.grid_forget()

        if not self.items:
            return

        width = max(self.winfo_width(), 1)
        col = 0
        row = 0
        used = 0
        pad_x = 8
        pad_y = 8

        for i in range(40):
            self.grid_columnconfigure(i, weight=0, uniform="")

        for item in self.items:
            needed = item["min_width"] + pad_x
            if used and used + needed > width:
                row += 1
                col = 0
                used = 0

            item["widget"].grid(row=row, column=col, padx=(0, pad_x), pady=(0, pad_y), sticky="ew")
            if item["stretch"]:
                self.grid_columnconfigure(col, weight=1, uniform="")
            else:
                self.grid_columnconfigure(col, weight=0, uniform="")
            used += needed
            col += 1


class BookmarkManagerResponsive:
    def __init__(self, root):
        self.root = root
        ensure_default_icons()

        self.file_path = self.load_last_file() or DEFAULT_FILE
        self.data = self.load_data(self.file_path)
        self.path = []
        self.undo_stack = []
        self.redo_stack = []
        self.current_search_results = []
        self.last_window_width = 0

        self.theme_color = self.data.get("_theme_color", "#3b82f6")
        self.titlebar_color = self.data.get("_titlebar_color", self.theme_color)
        self.bg_color = self.data.get("_bg_color", "#111827")
        self.surface_color = self.data.get("_surface_color", "#1f2937")
        self.surface_alt = self.data.get("_surface_alt", "#0f172a")
        self.text_color = self.data.get("_text_color", "#f9fafb")
        self.muted_text = self.data.get("_muted_text", "#9ca3af")
        self.button_color = self.data.get("_button_color", "#374151")
        self.font_family = self.data.get("_font_family", "Segoe UI")
        self.font_size = int(self.data.get("_font_size", 10))
        self.icon_path = self.data.get("_icon_path", "")

        size = self.data.get("_window_size", {"width": 1280, "height": 820})
        self.root.geometry(f"{size['width']}x{size['height']}")
        self.root.minsize(840, 560)
        self.root.configure(bg=self.bg_color)
        self.root.title("Bookmark Manager Pro Responsive")
        self.apply_icon()

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.configure_styles()

        self.build_ui()
        self.refresh()
        self.root.after(150, self.apply_titlebar_color)

        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.root.bind("<F2>", lambda e: self.rename_selected())
        self.root.bind("<Delete>", lambda e: self.delete_selected())
        self.root.bind("<Configure>", self.on_root_resize)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if DND_AVAILABLE:
            try:
                self.tree.drop_target_register('*')
                self.tree.dnd_bind('<<Drop>>', self.on_drop)
            except Exception:
                pass

    def configure_styles(self):
        self.font_main = (self.font_family, self.font_size)
        self.font_small = (self.font_family, max(8, self.font_size - 1))
        self.font_bold = (self.font_family, self.font_size, "bold")
        self.font_title = (self.font_family, self.font_size + 13, "bold")
        self.font_section = (self.font_family, self.font_size + 2, "bold")

        self.style.configure(".", background=self.bg_color, foreground=self.text_color, fieldbackground=self.surface_color)
        self.style.configure("Treeview", background=self.surface_color, fieldbackground=self.surface_color,
                             foreground=self.text_color, rowheight=30, font=self.font_main, borderwidth=0)
        self.style.map("Treeview", background=[("selected", self.theme_color)], foreground=[("selected", "white")])

        self.style.configure("Treeview.Heading", background=self.surface_alt, foreground=self.text_color,
                             font=self.font_bold, relief="flat")
        self.style.map("Treeview.Heading", background=[("active", self.surface_alt)])

        self.style.configure("Primary.TButton", font=self.font_bold, padding=(12, 10),
                             foreground="white", background=self.theme_color, borderwidth=0)
        self.style.map("Primary.TButton",
                       background=[("active", self.lighten(self.theme_color, 0.10)),
                                   ("pressed", self.darken(self.theme_color, 0.12))])

        self.style.configure("Secondary.TButton", font=self.font_main, padding=(12, 10),
                             foreground="white", background=self.button_color, borderwidth=0)
        self.style.map("Secondary.TButton",
                       background=[("active", self.lighten(self.button_color, 0.08)),
                                   ("pressed", self.darken(self.button_color, 0.08))])

        self.style.configure("Toolbar.TEntry", fieldbackground=self.surface_alt, foreground=self.text_color, padding=8)
        self.style.configure("Modern.TCombobox", fieldbackground=self.surface_alt)

    def build_ui(self):
        self.build_menu()

        self.main = tk.Frame(self.root, bg=self.bg_color)
        self.main.pack(fill="both", expand=True)

        self.topbar = tk.Frame(self.main, bg=self.bg_color, padx=18, pady=16)
        self.topbar.pack(fill="x")

        title_block = tk.Frame(self.topbar, bg=self.bg_color)
        title_block.pack(side="left", fill="x", expand=True)

        self.title_label = tk.Label(title_block, text="Bookmark Manager Pro", font=self.font_title,
                                    fg=self.text_color, bg=self.bg_color)
        self.title_label.pack(anchor="w")

        self.subtitle_label = tk.Label(title_block, text="Responsive layout, measured controls, expandable workspace",
                                       font=self.font_small, fg=self.muted_text, bg=self.bg_color)
        self.subtitle_label.pack(anchor="w", pady=(3, 0))

        self.file_badge = tk.Label(self.topbar, text="", font=self.font_small, fg=self.text_color,
                                   bg=self.surface_alt, padx=12, pady=6)
        self.file_badge.pack(side="right", padx=(10, 0))

        self.toolbar_wrap = tk.Frame(self.main, bg=self.bg_color, padx=18, pady=4)
        self.toolbar_wrap.pack(fill="x")

        self.toolbar = ResponsiveToolbar(self.toolbar_wrap, self.bg_color)
        self.toolbar.pack(fill="x")

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh())

        # Buttons measured explicitly so they can wrap cleanly
        controls = [
            ("＋ Link", self.add_link, "Primary.TButton", 120),
            ("📁 Folder", self.new_folder, "Secondary.TButton", 128),
            ("📄 File", self.add_file, "Secondary.TButton", 108),
            ("🗀 Folder Shortcut", self.add_folder_shortcut, "Secondary.TButton", 170),
            ("✎ Rename", self.rename_selected, "Secondary.TButton", 120),
            ("🗑 Delete", self.delete_selected, "Secondary.TButton", 116),
            ("⟲ Back", self.go_back, "Secondary.TButton", 100),
            ("💾 Backup", self.create_backup_popup, "Primary.TButton", 126),
            ("📂 Load", self.load_backup, "Secondary.TButton", 108),
            ("⚙ Settings", self.open_settings, "Secondary.TButton", 124),
        ]
        for label, cmd, style, width in controls:
            btn = ttk.Button(self.toolbar, text=label, command=cmd, style=style)
            self.toolbar.add_widget(btn, min_width=width)

        self.search_entry = ttk.Entry(self.toolbar, textvariable=self.search_var, style="Toolbar.TEntry")
        self.toolbar.add_widget(self.search_entry, min_width=260, stretch=True)

        clear_btn = ttk.Button(self.toolbar, text="Clear Search", style="Secondary.TButton",
                               command=lambda: self.search_var.set(""))
        self.toolbar.add_widget(clear_btn, min_width=128)

        self.breadcrumb_wrap = tk.Frame(self.main, bg=self.bg_color, padx=18, pady=12)
        self.breadcrumb_wrap.pack(fill="x")

        self.breadcrumb = tk.Label(self.breadcrumb_wrap, text="", font=self.font_small,
                                   fg=self.muted_text, bg=self.bg_color)
        self.breadcrumb.pack(anchor="w")

        self.paned = tk.PanedWindow(self.main, orient="horizontal", sashwidth=8, sashrelief="flat",
                                    bg=self.bg_color, bd=0, opaqueresize=True)
        self.paned.pack(fill="both", expand=True, padx=18, pady=10)

        self.left_panel = tk.Frame(self.paned, bg=self.surface_color, highlightthickness=1,
                                   highlightbackground=self.surface_alt)
        self.right_panel = tk.Frame(self.paned, bg=self.surface_alt, width=320)
        self.paned.add(self.left_panel, stretch="always", minsize=420)
        self.paned.add(self.right_panel, minsize=220)

        tree_top = tk.Frame(self.left_panel, bg=self.surface_color)
        tree_top.pack(fill="both", expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(tree_top, columns=("type",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("#0", anchor="w", width=740)
        self.tree.column("type", anchor="center", width=140, stretch=False)

        yscroll = ttk.Scrollbar(tree_top, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_details())

        self.build_details_panel()

        self.statusbar = tk.Frame(self.main, bg=self.surface_alt, padx=18, pady=8)
        self.statusbar.pack(fill="x", side="bottom")

        self.status_left = tk.Label(self.statusbar, text="", bg=self.surface_alt, fg=self.muted_text, font=self.font_small)
        self.status_left.pack(side="left")

        self.status_right = tk.Label(self.statusbar, text="Ctrl+F Search • F2 Rename • Drag sash to resize panels",
                                     bg=self.surface_alt, fg=self.muted_text, font=self.font_small)
        self.status_right.pack(side="right")

        self.toolbar.reflow()

    def build_details_panel(self):
        inner = tk.Frame(self.right_panel, bg=self.surface_alt, padx=16, pady=16)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="Details", font=self.font_section,
                 fg=self.text_color, bg=self.surface_alt).pack(anchor="w")

        self.detail_name = tk.Label(inner, text="No selection", wraplength=280,
                                    font=(self.font_family, self.font_size + 3, "bold"),
                                    fg=self.text_color, bg=self.surface_alt, justify="left")
        self.detail_name.pack(anchor="w", pady=(14, 10))

        self.detail_type = tk.Label(inner, text="", font=self.font_main,
                                    fg=self.muted_text, bg=self.surface_alt, justify="left")
        self.detail_type.pack(anchor="w", pady=(0, 6))

        self.detail_path = tk.Label(inner, text="", wraplength=280,
                                    font=self.font_small, fg=self.text_color,
                                    bg=self.surface_alt, justify="left")
        self.detail_path.pack(anchor="w", pady=(0, 16))

        detail_btns = tk.Frame(inner, bg=self.surface_alt)
        detail_btns.pack(fill="x")

        ttk.Button(detail_btns, text="Open", style="Primary.TButton",
                   command=self.open_selected).pack(fill="x", pady=(0, 8))
        ttk.Button(detail_btns, text="Rename", style="Secondary.TButton",
                   command=self.rename_selected).pack(fill="x", pady=(0, 8))
        ttk.Button(detail_btns, text="Delete", style="Secondary.TButton",
                   command=self.delete_selected).pack(fill="x", pady=(0, 18))

        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=(0, 14))

        tk.Label(inner, text="Quick Stats", font=self.font_section,
                 fg=self.text_color, bg=self.surface_alt).pack(anchor="w")

        self.stat_folders = tk.Label(inner, text="", font=self.font_main, fg=self.muted_text, bg=self.surface_alt)
        self.stat_folders.pack(anchor="w", pady=(10, 4))

        self.stat_items = tk.Label(inner, text="", font=self.font_main, fg=self.muted_text, bg=self.surface_alt)
        self.stat_items.pack(anchor="w", pady=4)

        self.stat_search = tk.Label(inner, text="", font=self.font_main, fg=self.muted_text, bg=self.surface_alt)
        self.stat_search.pack(anchor="w", pady=4)

    def build_menu(self):
        menu = tk.Menu(self.root, tearoff=0)

        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="New Folder", command=self.new_folder)
        file_menu.add_command(label="Add Link", command=self.add_link)
        file_menu.add_command(label="Add File", command=self.add_file)
        file_menu.add_command(label="Add Folder Shortcut", command=self.add_folder_shortcut)
        file_menu.add_separator()
        file_menu.add_command(label="Create Backup", command=self.create_backup_popup)
        file_menu.add_command(label="Load Backup", command=self.load_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menu.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu, tearoff=0)
        edit_menu.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Rename", command=self.rename_selected, accelerator="F2")
        edit_menu.add_command(label="Delete", command=self.delete_selected, accelerator="Del")
        menu.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menu, tearoff=0)
        view_menu.add_command(label="Settings", command=self.open_settings)
        menu.add_cascade(label="View", menu=view_menu)

        self.root.config(menu=menu)

    def lighten(self, color, factor=0.10):
        r, g, b = hex_to_rgb(color)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def darken(self, color, factor=0.10):
        r, g, b = hex_to_rgb(color)
        r = max(0, int(r * (1 - factor)))
        g = max(0, int(g * (1 - factor)))
        b = max(0, int(b * (1 - factor)))
        return f"#{r:02x}{g:02x}{b:02x}"

    def apply_titlebar_color(self):
        if platform.system() == "Windows":
            r, g, b = hex_to_rgb(self.titlebar_color)
            lumin = 0.299 * r + 0.587 * g + 0.114 * b
            text = (255, 255, 255) if lumin < 160 else (32, 32, 32)
            set_windows_titlebar(self.root.winfo_id(), (r, g, b), text, dark=True)

    def apply_icon(self):
        ico_to_use = None
        if self.icon_path:
            ap = os.path.abspath(self.icon_path)
            if ap.lower().endswith(".ico") and os.path.exists(ap):
                ico_to_use = ap
            elif ap.lower().endswith(".png") and os.path.exists(ap) and PIL_AVAILABLE:
                maybe_ico = os.path.splitext(ap)[0] + ".ico"
                try:
                    Image.open(ap).convert("RGBA").save(maybe_ico, format="ICO", sizes=[(32, 32), (48, 48), (64, 64)])
                    ico_to_use = maybe_ico
                except Exception:
                    pass

        if not ico_to_use and os.path.exists(DEFAULT_ICON_ICO):
            ico_to_use = DEFAULT_ICON_ICO

        try:
            if ico_to_use and platform.system() == "Windows":
                self.root.iconbitmap(ico_to_use)
            elif os.path.exists(DEFAULT_ICON_PNG):
                img = tk.PhotoImage(file=DEFAULT_ICON_PNG)
                self.root.iconphoto(True, img)
                self._icon_ref = img
        except Exception:
            pass

    def current_dir(self):
        node = self.data
        for p in self.path:
            node = node["folders"][p]
        return node

    def validate_data(self, data):
        if not isinstance(data, dict):
            data = {}
        data.setdefault("folders", {})
        data.setdefault("links", [])
        data.setdefault("_window_size", {"width": 1280, "height": 820})
        data.setdefault("_theme_color", "#3b82f6")
        data.setdefault("_titlebar_color", data["_theme_color"])
        data.setdefault("_bg_color", "#111827")
        data.setdefault("_surface_color", "#1f2937")
        data.setdefault("_surface_alt", "#0f172a")
        data.setdefault("_text_color", "#f9fafb")
        data.setdefault("_muted_text", "#9ca3af")
        data.setdefault("_button_color", "#374151")
        data.setdefault("_font_family", "Segoe UI")
        data.setdefault("_font_size", 10)
        data.setdefault("_icon_path", "")
        for link in data["links"]:
            link.setdefault("id", str(uuid.uuid4()))
            link.setdefault("name", "Untitled")
            link.setdefault("url", "")
            link.setdefault("kind", "url")
        return data

    def load_data(self, path):
        if not os.path.exists(path):
            return self.validate_data({"folders": {}, "links": []})
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return self.validate_data(raw)
        except Exception:
            messagebox.showwarning("Data Warning", "Could not read the saved JSON file. A fresh file will be used.")
            return self.validate_data({"folders": {}, "links": []})

    def save(self):
        self.data.update({
            "_window_size": {"width": self.root.winfo_width(), "height": self.root.winfo_height()},
            "_theme_color": self.theme_color,
            "_titlebar_color": self.titlebar_color,
            "_bg_color": self.bg_color,
            "_surface_color": self.surface_color,
            "_surface_alt": self.surface_alt,
            "_text_color": self.text_color,
            "_muted_text": self.muted_text,
            "_button_color": self.button_color,
            "_font_family": self.font_family,
            "_font_size": self.font_size,
            "_icon_path": self.icon_path,
        })
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Save Failed", str(e))

    def load_last_file(self):
        try:
            if os.path.exists(LAST_FILE_STATE):
                with open(LAST_FILE_STATE, "r", encoding="utf-8") as f:
                    return json.load(f).get("last")
        except Exception:
            return None
        return None

    def save_last_file(self, path):
        try:
            with open(LAST_FILE_STATE, "w", encoding="utf-8") as f:
                json.dump({"last": rel_or_abs(path)}, f)
        except Exception:
            pass

    def push_state(self):
        self.undo_stack.append(json.loads(json.dumps(self.data)))
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(json.loads(json.dumps(self.data)))
        self.data = self.undo_stack.pop()
        self.refresh()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(json.loads(json.dumps(self.data)))
        self.data = self.redo_stack.pop()
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        node = self.current_dir()
        query = self.search_var.get().strip().lower()
        self.current_search_results = []

        for folder_name in sorted(node["folders"].keys(), key=str.lower):
            if query and query not in folder_name.lower():
                continue
            iid = f"folder::{folder_name}"
            self.tree.insert("", "end", iid=iid, text=f"📁  {folder_name}", values=("Folder",))
            self.current_search_results.append(iid)

        for bm in sorted(node["links"], key=lambda x: x.get("name", "").lower()):
            label = bm.get("name", "Untitled")
            url = bm.get("url", "")
            kind = bm.get("kind", "url")
            hay = f"{label} {url} {kind}".lower()
            if query and query not in hay:
                continue
            icon = "🔗" if kind == "url" else ("📄" if kind == "file" else "🗀")
            iid = f"link::{bm['id']}"
            kind_text = "Link" if kind == "url" else ("File" if kind == "file" else "Folder Shortcut")
            self.tree.insert("", "end", iid=iid, text=f"{icon}  {label}", values=(kind_text,))
            self.current_search_results.append(iid)

        self.file_badge.config(text=os.path.basename(self.file_path))
        trail = " / ".join(["Root"] + self.path) if self.path else "Root"
        self.breadcrumb.config(text=f"Path: {trail}")

        total_folders = len(node["folders"])
        total_items = len(node["links"])
        self.stat_folders.config(text=f"Folders here: {total_folders}")
        self.stat_items.config(text=f"Items here: {total_items}")
        self.stat_search.config(text=f"Visible after search: {len(self.current_search_results)}")
        self.status_left.config(text=f"{len(self.current_search_results)} visible • {total_folders} folders • {total_items} items")

        self.update_details()
        self.root.title(f"Bookmark Manager Pro Responsive — {os.path.splitext(os.path.basename(self.file_path))[0]}")

    def selected_payload(self):
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        node = self.current_dir()

        if iid.startswith("folder::"):
            name = iid.split("folder::", 1)[1]
            return {"type": "folder", "name": name}

        if iid.startswith("link::"):
            link_id = iid.split("link::", 1)[1]
            for bm in node["links"]:
                if bm.get("id") == link_id:
                    return {"type": "link", "data": bm}
        return None

    def update_details(self):
        info = self.selected_payload()
        if not info:
            self.detail_name.config(text="No selection")
            self.detail_type.config(text="Select a folder, link, file, or shortcut")
            self.detail_path.config(text="")
            return

        if info["type"] == "folder":
            self.detail_name.config(text=info["name"])
            self.detail_type.config(text="Folder")
            self.detail_path.config(text="Double-click to enter this folder.")
        else:
            bm = info["data"]
            kind = bm.get("kind", "url")
            kind_text = "Web Link" if kind == "url" else ("File" if kind == "file" else "Folder Shortcut")
            self.detail_name.config(text=bm.get("name", "Untitled"))
            self.detail_type.config(text=kind_text)
            self.detail_path.config(text=bm.get("url", ""))

    def new_folder(self):
        name = self.prompt_text("New Folder", "Folder name:")
        if not name:
            return
        node = self.current_dir()
        if name in node["folders"]:
            messagebox.showerror("Exists", f"Folder '{name}' already exists.")
            return
        self.push_state()
        node["folders"][name] = {"folders": {}, "links": []}
        self.save()
        self.refresh()

    def add_link(self):
        dialog = DualInputDialog(self.root, "Add Link", "Link Name:", "URL:")
        self.root.wait_window(dialog.top)
        if not dialog.result:
            return
        name, url = dialog.result
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.push_state()
        self.current_dir()["links"].append({
            "id": str(uuid.uuid4()),
            "name": name,
            "url": url,
            "kind": "url",
        })
        self.save()
        self.refresh()

    def add_file(self):
        path = filedialog.askopenfilename(title="Select a File")
        if not path:
            return
        self.push_state()
        self.current_dir()["links"].append({
            "id": str(uuid.uuid4()),
            "name": os.path.basename(path),
            "url": rel_or_abs(path),
            "kind": "file",
        })
        self.save()
        self.refresh()

    def add_folder_shortcut(self):
        path = filedialog.askdirectory(title="Select a Folder")
        if not path:
            return
        self.push_state()
        self.current_dir()["links"].append({
            "id": str(uuid.uuid4()),
            "name": os.path.basename(path.rstrip("/\\")),
            "url": rel_or_abs(path),
            "kind": "folder",
        })
        self.save()
        self.refresh()

    def go_back(self):
        if self.path:
            self.path.pop()
            self.refresh()

    def open_selected(self):
        info = self.selected_payload()
        if not info:
            return
        if info["type"] == "folder":
            self.path.append(info["name"])
            self.refresh()
            return

        bm = info["data"]
        kind = bm.get("kind", "url")
        url = bm.get("url", "")
        if kind == "url":
            webbrowser_open(url)
        else:
            open_local(url)

    def on_double_click(self, _event):
        self.open_selected()

    def delete_selected(self):
        info = self.selected_payload()
        if not info:
            return

        node = self.current_dir()
        self.push_state()

        if info["type"] == "folder":
            name = info["name"]
            if not messagebox.askyesno("Delete Folder", f"Delete folder '{name}' and everything inside it?"):
                self.undo_stack.pop()
                return
            del node["folders"][name]
        else:
            bm = info["data"]
            if not messagebox.askyesno("Delete Item", f"Delete '{bm['name']}'?"):
                self.undo_stack.pop()
                return
            node["links"] = [x for x in node["links"] if x.get("id") != bm.get("id")]

        self.save()
        self.refresh()

    def rename_selected(self):
        info = self.selected_payload()
        if not info:
            return

        node = self.current_dir()
        if info["type"] == "folder":
            old = info["name"]
            new = self.prompt_text("Rename Folder", "New folder name:", old)
            if not new or new == old:
                return
            if new in node["folders"]:
                messagebox.showerror("Exists", f"A folder named '{new}' already exists.")
                return
            self.push_state()
            node["folders"][new] = node["folders"].pop(old)
        else:
            bm = info["data"]
            new = self.prompt_text("Rename Item", "New item name:", bm.get("name", ""))
            if not new or new == bm.get("name"):
                return
            self.push_state()
            bm["name"] = new

        self.save()
        self.refresh()

    def prompt_text(self, title, prompt, initial=""):
        dialog = SimpleInputDialog(self.root, title, prompt, initial=initial, theme_bg=self.surface_alt,
                                   text_fg=self.text_color, font=self.font_main)
        self.root.wait_window(dialog.top)
        return dialog.result

    def create_backup_popup(self):
        default_name = f"bookmarks_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
        path = filedialog.asksaveasfilename(
            title="Create Backup",
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Backup Created", f"Saved backup to:\n{path}")
        except Exception as e:
            messagebox.showerror("Backup Failed", str(e))

    def load_backup(self):
        path = filedialog.askopenfilename(
            title="Load Backup",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        if not messagebox.askyesno("Load Backup", f"Open and start editing:\n{path}"):
            return
        self.data = self.load_data(path)
        self.file_path = path
        self.path = []
        self.save_last_file(self.file_path)
        self.refresh()

    def open_settings(self):
        dialog = SettingsDialog(self)
        self.root.wait_window(dialog.top)

    def apply_theme_refresh(self):
        self.root.configure(bg=self.bg_color)
        self.configure_styles()

        self.main.configure(bg=self.bg_color)
        self.topbar.configure(bg=self.bg_color)
        self.toolbar_wrap.configure(bg=self.bg_color)
        self.toolbar.configure(bg=self.bg_color)
        self.breadcrumb_wrap.configure(bg=self.bg_color)
        self.breadcrumb.configure(bg=self.bg_color, fg=self.muted_text)
        self.left_panel.configure(bg=self.surface_color, highlightbackground=self.surface_alt)
        self.right_panel.configure(bg=self.surface_alt)
        self.statusbar.configure(bg=self.surface_alt)
        self.status_left.configure(bg=self.surface_alt, fg=self.muted_text, font=self.font_small)
        self.status_right.configure(bg=self.surface_alt, fg=self.muted_text, font=self.font_small)
        self.title_label.configure(bg=self.bg_color, fg=self.text_color, font=self.font_title)
        self.subtitle_label.configure(bg=self.bg_color, fg=self.muted_text, font=self.font_small)
        self.file_badge.configure(bg=self.surface_alt, fg=self.text_color, font=self.font_small)
        self.detail_name.configure(bg=self.surface_alt, fg=self.text_color)
        self.detail_type.configure(bg=self.surface_alt, fg=self.muted_text)
        self.detail_path.configure(bg=self.surface_alt, fg=self.text_color)

        self.apply_icon()
        self.apply_titlebar_color()
        self.toolbar.reflow()
        self.refresh()

    def on_drop(self, event):
        data = event.data
        paths = []
        token = ""
        in_brace = False
        for ch in data:
            if ch == "{":
                in_brace = True
                token = ""
                continue
            if ch == "}":
                in_brace = False
                paths.append(token)
                token = ""
                continue
            if ch == " " and not in_brace:
                if token:
                    paths.append(token)
                    token = ""
                continue
            token += ch
        if token:
            paths.append(token)

        if not paths:
            return

        self.push_state()
        node = self.current_dir()
        for p in paths:
            if os.path.isdir(p):
                node["links"].append({
                    "id": str(uuid.uuid4()),
                    "name": os.path.basename(p.rstrip("/\\")),
                    "url": rel_or_abs(p),
                    "kind": "folder",
                })
            elif os.path.isfile(p):
                node["links"].append({
                    "id": str(uuid.uuid4()),
                    "name": os.path.basename(p),
                    "url": rel_or_abs(p),
                    "kind": "file",
                })

        self.save()
        self.refresh()

    def on_root_resize(self, event):
        if event.widget is not self.root:
            return
        if abs(event.width - self.last_window_width) >= 12:
            self.last_window_width = event.width
            self.toolbar.reflow()

    def on_close(self):
        self.save()
        self.save_last_file(self.file_path)
        self.root.destroy()


class SimpleInputDialog:
    def __init__(self, parent, title, prompt, initial="", theme_bg="#1f2937", text_fg="white",
                 font=("Segoe UI", 10)):
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.configure(bg=theme_bg, padx=18, pady=14)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)

        tk.Label(self.top, text=prompt, bg=theme_bg, fg=text_fg, font=font).pack(anchor="w", pady=(0, 8))
        self.entry = ttk.Entry(self.top, width=42)
        self.entry.pack(fill="x")
        self.entry.insert(0, initial)
        self.entry.selection_range(0, "end")
        self.entry.focus_set()

        btns = tk.Frame(self.top, bg=theme_bg)
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text="Cancel", command=self.top.destroy, style="Secondary.TButton").pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="OK", command=self.accept, style="Primary.TButton").pack(side="right")

        self.top.bind("<Return>", lambda e: self.accept())
        self.center(parent)

    def accept(self):
        value = self.entry.get().strip()
        if value:
            self.result = value
        self.top.destroy()

    def center(self, parent):
        self.top.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.top.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.top.winfo_height() // 2)
        self.top.geometry(f"+{x}+{y}")


class DualInputDialog:
    def __init__(self, parent, title, label1, label2):
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.configure(bg="#0f172a", padx=18, pady=14)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)

        tk.Label(self.top, text=label1, bg="#0f172a", fg="white").pack(anchor="w")
        self.e1 = ttk.Entry(self.top, width=46)
        self.e1.pack(fill="x", pady=(4, 10))

        tk.Label(self.top, text=label2, bg="#0f172a", fg="white").pack(anchor="w")
        self.e2 = ttk.Entry(self.top, width=46)
        self.e2.pack(fill="x", pady=(4, 12))

        btns = tk.Frame(self.top, bg="#0f172a")
        btns.pack(fill="x")
        ttk.Button(btns, text="Cancel", command=self.top.destroy, style="Secondary.TButton").pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="Add", command=self.accept, style="Primary.TButton").pack(side="right")

        self.e1.focus_set()
        self.top.bind("<Return>", lambda e: self.accept())
        self.center(parent)

    def accept(self):
        v1 = self.e1.get().strip()
        v2 = self.e2.get().strip()
        if v1 and v2:
            self.result = (v1, v2)
        self.top.destroy()

    def center(self, parent):
        self.top.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.top.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.top.winfo_height() // 2)
        self.top.geometry(f"+{x}+{y}")


class SettingsDialog:
    def __init__(self, app):
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.title("Settings")
        self.top.configure(bg=app.surface_alt, padx=18, pady=18)
        self.top.transient(app.root)
        self.top.grab_set()
        self.top.resizable(False, False)

        fonts = sorted(set(tkfont.families()))
        if app.font_family not in fonts:
            fonts.insert(0, app.font_family)

        tk.Label(self.top, text="Appearance", bg=app.surface_alt, fg=app.text_color,
                 font=(app.font_family, app.font_size + 4, "bold")).pack(anchor="w", pady=(0, 12))

        for label, attr in [
            ("Accent", "theme_color"),
            ("Title Bar", "titlebar_color"),
            ("Background", "bg_color"),
            ("Surface", "surface_color"),
            ("Panel", "surface_alt"),
            ("Text", "text_color"),
            ("Muted Text", "muted_text"),
            ("Buttons", "button_color"),
        ]:
            row = tk.Frame(self.top, bg=app.surface_alt)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, width=14, anchor="w", bg=app.surface_alt, fg=app.text_color).pack(side="left")
            chip = tk.Label(row, text=getattr(app, attr), bg=getattr(app, attr), fg="white",
                            padx=12, pady=4, width=12)
            chip.pack(side="left", padx=(0, 8))
            ttk.Button(row, text="Pick", style="Secondary.TButton",
                       command=lambda a=attr, c=chip: self.pick_color(a, c)).pack(side="left")

        tk.Label(self.top, text="Font Family", bg=app.surface_alt, fg=app.text_color).pack(anchor="w", pady=(14, 4))
        self.font_box = ttk.Combobox(self.top, values=fonts, state="readonly", width=32, style="Modern.TCombobox")
        self.font_box.set(app.font_family)
        self.font_box.pack(fill="x")

        tk.Label(self.top, text="Font Size", bg=app.surface_alt, fg=app.text_color).pack(anchor="w", pady=(14, 4))
        size_row = tk.Frame(self.top, bg=app.surface_alt)
        size_row.pack(fill="x")
        self.size_var = tk.IntVar(value=app.font_size)
        self.size_label = tk.Label(size_row, text=str(app.font_size), width=4, bg=app.surface_alt, fg=app.text_color)
        self.size_label.pack(side="left")
        ttk.Button(size_row, text="−", style="Secondary.TButton", command=lambda: self.bump_size(-1)).pack(side="left", padx=(8, 6))
        ttk.Button(size_row, text="+", style="Primary.TButton", command=lambda: self.bump_size(1)).pack(side="left")

        icon_row = tk.Frame(self.top, bg=app.surface_alt)
        icon_row.pack(fill="x", pady=(16, 0))
        tk.Label(icon_row, text="App Icon", width=14, anchor="w", bg=app.surface_alt, fg=app.text_color).pack(side="left")
        self.icon_label = tk.Label(icon_row, text=os.path.basename(app.icon_path) if app.icon_path else "Default",
                                   bg=app.surface_alt, fg=app.text_color)
        self.icon_label.pack(side="left", padx=(0, 8))
        ttk.Button(icon_row, text="Choose", style="Secondary.TButton", command=self.choose_icon).pack(side="left")

        actions = tk.Frame(self.top, bg=app.surface_alt)
        actions.pack(fill="x", pady=(18, 0))
        ttk.Button(actions, text="Cancel", style="Secondary.TButton", command=self.top.destroy).pack(side="right")
        ttk.Button(actions, text="Apply", style="Primary.TButton", command=self.apply).pack(side="right", padx=(0, 8))

        self.center()

    def pick_color(self, attr, chip):
        color = colorchooser.askcolor(initialcolor=getattr(self.app, attr), title=f"Choose {attr}")
        if color and color[1]:
            setattr(self.app, attr, color[1])
            chip.config(text=color[1], bg=color[1])

    def bump_size(self, delta):
        value = max(8, min(24, self.size_var.get() + delta))
        self.size_var.set(value)
        self.size_label.config(text=str(value))

    def choose_icon(self):
        p = filedialog.askopenfilename(title="Choose App Icon", filetypes=[("Icon/PNG", "*.ico *.png"), ("All files", "*.*")])
        if p:
            self.app.icon_path = rel_or_abs(p)
            self.icon_label.config(text=os.path.basename(self.app.icon_path))

    def apply(self):
        self.app.font_family = self.font_box.get()
        self.app.font_size = self.size_var.get()
        self.app.save()
        self.app.apply_theme_refresh()
        self.top.destroy()

    def center(self):
        self.top.update_idletasks()
        x = self.app.root.winfo_rootx() + (self.app.root.winfo_width() // 2) - (self.top.winfo_width() // 2)
        y = self.app.root.winfo_rooty() + (self.app.root.winfo_height() // 2) - (self.top.winfo_height() // 2)
        self.top.geometry(f"+{x}+{y}")


def build_root():
    if DND_AVAILABLE:
        return tkdnd.TkinterDnD.Tk()
    return tk.Tk()


if __name__ == "__main__":
    root = build_root()
    app = BookmarkManagerResponsive(root)
    root.mainloop()
