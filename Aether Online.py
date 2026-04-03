import json
import os
import queue
import socket
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

APP_TITLE = "Aetherium Client"
CONFIG_FILE = "aetherium_client_config.json"


class AetheriumClient:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1240x780")
        self.root.minsize(980, 620)

        self.sock = None
        self.connected = False
        self.inbox = queue.Queue()
        self.username_sent = False

        self.host_var = tk.StringVar(value="")
        self.port_var = tk.StringVar(value="5555")
        self.username_var = tk.StringVar(value="User")
        self.status_text_var = tk.StringVar(value="Offline")
        self.connection_mode_var = tk.StringVar(value="DISCONNECTED")
        self.room_var = tk.StringVar(value="general")
        self.online_count_var = tk.StringVar(value="0 online")
        self.window_title_var = tk.StringVar(value="Aetherium")

        self.show_users_var = tk.BooleanVar(value=True)
        self.show_commands_var = tk.BooleanVar(value=True)
        self.show_statusbar_var = tk.BooleanVar(value=True)
        self.show_node_status_var = tk.BooleanVar(value=False)

        self.node_window = None

        self.palette = {
            "bg": "#070b14",
            "bg2": "#0b1120",
            "panel": "#0f1728",
            "panel2": "#131f35",
            "panel3": "#182744",
            "chat": "#08101d",
            "input": "#0b1426",
            "line": "#223455",
            "text": "#dbe8ff",
            "muted": "#89a0c7",
            "cyan": "#62d4ff",
            "blue": "#5aa9ff",
            "violet": "#8878ff",
            "green": "#66f2c1",
            "yellow": "#ffd166",
            "red": "#ff6b7a",
            "orange": "#ffb454",
            "menu_bg": "#0e1627",
        }

        self.build_style()
        self.load_config()
        self.build_menu()
        self.build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(80, self.process_incoming)

    # ----------------------------
    # config
    # ----------------------------
    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.host_var.set(data.get("host", self.host_var.get()))
            self.port_var.set(str(data.get("port", self.port_var.get())))
            self.username_var.set(data.get("username", self.username_var.get()))
            self.show_users_var.set(bool(data.get("show_users", True)))
            self.show_commands_var.set(bool(data.get("show_commands", True)))
            self.show_statusbar_var.set(bool(data.get("show_statusbar", True)))
        except Exception:
            pass

    def save_config(self):
        try:
            data = {
                "host": self.host_var.get().strip(),
                "port": self.port_var.get().strip(),
                "username": self.username_var.get().strip(),
                "show_users": self.show_users_var.get(),
                "show_commands": self.show_commands_var.get(),
                "show_statusbar": self.show_statusbar_var.get(),
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ----------------------------
    # style
    # ----------------------------
    def build_style(self):
        p = self.palette
        self.root.configure(bg=p["bg"])

        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Main.TFrame", background=p["bg"])
        style.configure("Panel.TFrame", background=p["panel"])
        style.configure("Panel2.TFrame", background=p["panel2"])
        style.configure("Panel3.TFrame", background=p["panel3"])

        style.configure(
            "Title.TLabel",
            background=p["bg"],
            foreground=p["text"],
            font=("Segoe UI Semibold", 24),
        )
        style.configure(
            "SubTitle.TLabel",
            background=p["bg"],
            foreground=p["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Section.TLabel",
            background=p["panel"],
            foreground=p["text"],
            font=("Segoe UI Semibold", 11),
        )

        style.configure(
            "Accent.TButton",
            background=p["blue"],
            foreground="white",
            borderwidth=0,
            padding=9,
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", p["violet"]), ("disabled", "#33435f")],
            foreground=[("disabled", "#a7b7d3")],
        )

        style.configure(
            "Soft.TButton",
            background=p["panel3"],
            foreground=p["text"],
            borderwidth=0,
            padding=8,
            font=("Segoe UI", 10),
        )
        style.map(
            "Soft.TButton",
            background=[("active", "#23395f"), ("disabled", "#1a2741")],
            foreground=[("disabled", "#8ca1c6")],
        )

    # ----------------------------
    # menus
    # ----------------------------
    def build_menu(self):
        menubar = tk.Menu(self.root, tearoff=0)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save Settings", command=self.save_config)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        connection_menu = tk.Menu(menubar, tearoff=0)
        connection_menu.add_command(label="Connect", command=self.connect)
        connection_menu.add_command(label="Disconnect", command=self.disconnect)
        connection_menu.add_separator()
        connection_menu.add_command(label="Copy Host", command=self.copy_host)
        menubar.add_cascade(label="Connection", menu=connection_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Show Online Users", variable=self.show_users_var, command=self.refresh_layout)
        view_menu.add_checkbutton(label="Show Commands", variable=self.show_commands_var, command=self.refresh_layout)
        view_menu.add_checkbutton(label="Show Status Bar", variable=self.show_statusbar_var, command=self.refresh_layout)
        view_menu.add_separator()
        view_menu.add_checkbutton(label="Node Status Window", variable=self.show_node_status_var, command=self.toggle_node_window)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Commands", command=self.show_help_dialog)
        help_menu.add_command(label="About", command=self.show_about_dialog)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    # ----------------------------
    # ui
    # ----------------------------
    def build_ui(self):
        p = self.palette

        outer = ttk.Frame(self.root, style="Main.TFrame", padding=14)
        outer.pack(fill="both", expand=True)
        self.outer = outer

        header = ttk.Frame(outer, style="Main.TFrame")
        header.pack(fill="x", pady=(0, 12))
        self.header = header

        header_left = ttk.Frame(header, style="Main.TFrame")
        header_left.pack(side="left", fill="x", expand=True)

        ttk.Label(header_left, text="AETHERIUM", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header_left,
            text="Persistent communication node",
            style="SubTitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # Discreet host status
        header_right = tk.Frame(header, bg=p["bg"])
        header_right.pack(side="right", anchor="ne")

        self.header_status_dot = tk.Label(
            header_right,
            text="●",
            bg=p["bg"],
            fg=p["red"],
            font=("Segoe UI", 10, "bold"),
        )
        self.header_status_dot.pack(side="left", padx=(0, 6))

        self.header_status_text = tk.Label(
            header_right,
            textvariable=self.status_text_var,
            bg=p["bg"],
            fg=p["muted"],
            font=("Segoe UI", 9),
        )
        self.header_status_text.pack(side="left")

        content = ttk.Frame(outer, style="Main.TFrame")
        content.pack(fill="both", expand=True)
        self.content = content

        self.left = ttk.Frame(content, style="Panel.TFrame", padding=12)
        self.left.pack(side="left", fill="both", expand=True)

        self.right = ttk.Frame(content, style="Panel.TFrame", padding=12, width=300)
        self.right.pack(side="right", fill="y", padx=(12, 0))
        self.right.pack_propagate(False)

        self.build_topbar(self.left)
        self.build_chat_area(self.left)
        self.build_composer(self.left)
        self.build_sidebar(self.right)
        self.build_statusbar(outer)

        self.refresh_layout()

    def build_topbar(self, parent):
        p = self.palette

        box = tk.Frame(parent, bg=p["panel2"], highlightthickness=1, highlightbackground=p["line"])
        box.pack(fill="x", pady=(0, 12))
        self.topbar_box = box

        title = tk.Label(
            box,
            text="NETWORK LINK",
            bg=p["panel2"],
            fg=p["cyan"],
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=10,
            anchor="w",
        )
        title.grid(row=0, column=0, columnspan=10, sticky="ew")

        labels = [
            ("Host / Domain", 0),
            ("Port", 2),
            ("Username", 4),
        ]

        for text, col in labels:
            tk.Label(
                box,
                text=text,
                bg=p["panel2"],
                fg=p["muted"],
                font=("Segoe UI", 9),
            ).grid(row=1, column=col, sticky="w", padx=(12, 6), pady=(2, 8))

        self.host_entry = self.make_entry(box, self.host_var, width=26)
        self.host_entry.grid(row=2, column=0, sticky="ew", padx=(12, 12), pady=(0, 12))

        self.port_entry = self.make_entry(box, self.port_var, width=8)
        self.port_entry.grid(row=2, column=2, sticky="ew", padx=(0, 12), pady=(0, 12))

        self.username_entry = self.make_entry(box, self.username_var, width=18)
        self.username_entry.grid(row=2, column=4, sticky="ew", padx=(0, 12), pady=(0, 12))

        self.connect_btn = ttk.Button(box, text="Connect", style="Accent.TButton", command=self.connect)
        self.connect_btn.grid(row=2, column=6, padx=(0, 8), pady=(0, 12), sticky="ew")

        self.disconnect_btn = ttk.Button(box, text="Disconnect", style="Soft.TButton", command=self.disconnect)
        self.disconnect_btn.grid(row=2, column=7, padx=(0, 12), pady=(0, 12), sticky="ew")

        self.copy_host_btn = ttk.Button(box, text="Copy Host", style="Soft.TButton", command=self.copy_host)
        self.copy_host_btn.grid(row=2, column=8, padx=(0, 12), pady=(0, 12), sticky="ew")

        box.grid_columnconfigure(0, weight=3)
        box.grid_columnconfigure(2, weight=1)
        box.grid_columnconfigure(4, weight=2)

    def build_chat_area(self, parent):
        p = self.palette

        wrap = tk.Frame(parent, bg=p["panel2"], highlightthickness=1, highlightbackground=p["line"])
        wrap.pack(fill="both", expand=True)
        self.chat_wrap = wrap

        top = tk.Frame(wrap, bg=p["panel2"])
        top.pack(fill="x")

        tk.Label(
            top,
            text="GENERAL STREAM",
            bg=p["panel2"],
            fg=p["cyan"],
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=10,
        ).pack(side="left")

        self.room_badge = tk.Label(
            top,
            textvariable=self.room_var,
            bg=p["panel3"],
            fg=p["green"],
            font=("Consolas", 10, "bold"),
            padx=10,
            pady=4,
        )
        self.room_badge.pack(side="right", padx=12, pady=8)

        self.chat_text = tk.Text(
            wrap,
            bg=p["chat"],
            fg=p["text"],
            insertbackground=p["text"],
            relief="flat",
            bd=0,
            wrap="word",
            font=("Consolas", 11),
            padx=16,
            pady=16,
            state="disabled",
            selectbackground="#2a4f91",
        )
        self.chat_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.chat_text.yview)
        scroll.pack(side="right", fill="y")
        self.chat_text.configure(yscrollcommand=scroll.set)

        self.chat_text.tag_configure("system", foreground=p["blue"])
        self.chat_text.tag_configure("error", foreground=p["red"])
        self.chat_text.tag_configure("self", foreground=p["green"])
        self.chat_text.tag_configure("command", foreground=p["orange"])

    def build_composer(self, parent):
        p = self.palette

        box = tk.Frame(parent, bg=p["panel2"], highlightthickness=1, highlightbackground=p["line"])
        box.pack(fill="x", pady=(12, 0))
        self.composer_box = box

        tk.Label(
            box,
            text="MESSAGE COMPOSER",
            bg=p["panel2"],
            fg=p["cyan"],
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=10,
            anchor="w",
        ).pack(fill="x")

        row = tk.Frame(box, bg=p["panel2"])
        row.pack(fill="x", padx=12, pady=(0, 12))

        self.message_box = tk.Text(
            row,
            height=4,
            bg=self.palette["input"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            relief="flat",
            bd=0,
            wrap="word",
            font=("Segoe UI", 11),
            padx=12,
            pady=12,
        )
        self.message_box.pack(side="left", fill="x", expand=True)
        self.message_box.bind("<Return>", self.on_enter_send)
        self.message_box.bind("<Shift-Return>", lambda e: None)

        btns = tk.Frame(row, bg=p["panel2"])
        btns.pack(side="left", padx=(12, 0))

        ttk.Button(btns, text="Send", style="Accent.TButton", command=self.send_message).pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="/list", style="Soft.TButton", command=lambda: self.send_raw("/list")).pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="Clear", style="Soft.TButton", command=self.clear_message).pack(fill="x")

    def build_sidebar(self, parent):
        p = self.palette

        users_wrap = tk.Frame(parent, bg=p["panel2"], highlightthickness=1, highlightbackground=p["line"])
        users_wrap.pack(fill="both", expand=True)
        self.users_wrap = users_wrap

        head = tk.Frame(users_wrap, bg=p["panel2"])
        head.pack(fill="x")

        tk.Label(
            head,
            text="ONLINE USERS",
            bg=p["panel2"],
            fg=p["cyan"],
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=10,
            anchor="w",
        ).pack(side="left")

        tk.Label(
            head,
            textvariable=self.online_count_var,
            bg=p["panel2"],
            fg=p["muted"],
            font=("Segoe UI", 9),
            padx=12,
            pady=10,
        ).pack(side="right")

        self.users_list = tk.Listbox(
            users_wrap,
            bg=p["chat"],
            fg=p["text"],
            relief="flat",
            bd=0,
            activestyle="none",
            font=("Segoe UI", 10),
            selectbackground="#2a4f91",
            selectforeground=p["text"],
        )
        self.users_list.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        cmd_wrap = tk.Frame(parent, bg=p["panel2"], highlightthickness=1, highlightbackground=p["line"])
        cmd_wrap.pack(fill="x", pady=(12, 0))
        self.cmd_wrap = cmd_wrap

        tk.Label(
            cmd_wrap,
            text="COMMANDS",
            bg=p["panel2"],
            fg=p["cyan"],
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=10,
            anchor="w",
        ).pack(fill="x")

        cmd_text = tk.Text(
            cmd_wrap,
            height=7,
            bg=p["chat"],
            fg=p["muted"],
            relief="flat",
            bd=0,
            wrap="word",
            font=("Consolas", 10),
            padx=12,
            pady=12,
        )
        cmd_text.pack(fill="x", padx=12, pady=(0, 12))
        cmd_text.insert(
            "1.0",
            "/list\n"
            "/rename NewName\n"
            "/quit\n\n"
            "Enter = send\n"
            "Shift+Enter = newline"
        )
        cmd_text.configure(state="disabled")

    def build_statusbar(self, parent):
        p = self.palette

        bar = tk.Frame(parent, bg=p["panel"], highlightthickness=1, highlightbackground=p["line"])
        bar.pack(fill="x", pady=(12, 0))
        self.status_bar = bar

        self.status_dot = tk.Label(bar, text="●", bg=p["panel"], fg=p["red"], font=("Segoe UI", 12, "bold"))
        self.status_dot.pack(side="left", padx=(10, 6), pady=8)

        self.status_label = tk.Label(
            bar,
            textvariable=self.status_text_var,
            bg=p["panel"],
            fg=p["red"],
            font=("Segoe UI", 10),
        )
        self.status_label.pack(side="left", pady=8)

        self.clock_label = tk.Label(
            bar,
            text="",
            bg=p["panel"],
            fg=p["muted"],
            font=("Consolas", 10),
        )
        self.clock_label.pack(side="right", padx=10, pady=8)

        self.update_clock()

    def make_entry(self, parent, variable, width=16):
        p = self.palette
        return tk.Entry(
            parent,
            textvariable=variable,
            width=width,
            bg=p["input"],
            fg=p["text"],
            insertbackground=p["text"],
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
        )

    # ----------------------------
    # layout / windows
    # ----------------------------
    def refresh_layout(self):
        right_needed = self.show_users_var.get() or self.show_commands_var.get()

        if right_needed:
            if not self.right.winfo_manager():
                self.right.pack(side="right", fill="y", padx=(12, 0))
        else:
            if self.right.winfo_manager():
                self.right.pack_forget()

        if self.show_users_var.get():
            if not self.users_wrap.winfo_manager():
                self.users_wrap.pack(fill="both", expand=True)
        else:
            if self.users_wrap.winfo_manager():
                self.users_wrap.pack_forget()

        if self.show_commands_var.get():
            if not self.cmd_wrap.winfo_manager():
                self.cmd_wrap.pack(fill="x", pady=(12, 0))
        else:
            if self.cmd_wrap.winfo_manager():
                self.cmd_wrap.pack_forget()

        if self.show_statusbar_var.get():
            if not self.status_bar.winfo_manager():
                self.status_bar.pack(fill="x", pady=(12, 0))
        else:
            if self.status_bar.winfo_manager():
                self.status_bar.pack_forget()

        self.save_config()

    def toggle_node_window(self):
        if self.show_node_status_var.get():
            self.open_node_window()
        else:
            self.close_node_window()

    def open_node_window(self):
        if self.node_window and self.node_window.winfo_exists():
            self.node_window.lift()
            return

        p = self.palette
        self.node_window = tk.Toplevel(self.root)
        self.node_window.title("Node Status")
        self.node_window.geometry("360x220")
        self.node_window.configure(bg=p["bg"])
        self.node_window.resizable(False, False)

        wrap = tk.Frame(self.node_window, bg=p["panel2"], highlightthickness=1, highlightbackground=p["line"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            wrap,
            text="NODE STATUS",
            bg=p["panel2"],
            fg=p["cyan"],
            font=("Segoe UI Semibold", 11),
            pady=12
        ).pack()

        self.node_window_dot = tk.Label(
            wrap,
            text="●",
            bg=p["panel2"],
            fg=p["red"],
            font=("Segoe UI", 30, "bold"),
        )
        self.node_window_dot.pack(pady=(4, 0))

        self.node_window_status = tk.Label(
            wrap,
            textvariable=self.status_text_var,
            bg=p["panel2"],
            fg=p["red"],
            font=("Segoe UI Semibold", 12),
        )
        self.node_window_status.pack(pady=(4, 2))

        self.node_window_mode = tk.Label(
            wrap,
            textvariable=self.connection_mode_var,
            bg=p["panel2"],
            fg=p["muted"],
            font=("Consolas", 10),
        )
        self.node_window_mode.pack(pady=(0, 12))

        self.node_window_info = tk.Label(
            wrap,
            text="Host: -\nPort: -\nUser: -",
            bg=p["panel2"],
            fg=p["muted"],
            font=("Consolas", 10),
            justify="left",
        )
        self.node_window_info.pack()

        self.node_window.protocol("WM_DELETE_WINDOW", self.on_node_window_close)
        self.sync_node_window()

    def sync_node_window(self):
        if self.node_window and self.node_window.winfo_exists():
            host = self.host_var.get().strip() or "-"
            port = self.port_var.get().strip() or "-"
            user = self.username_var.get().strip() or "-"
            self.node_window_info.configure(text=f"Host: {host}\nPort: {port}\nUser: {user}")

    def close_node_window(self):
        if self.node_window and self.node_window.winfo_exists():
            self.node_window.destroy()
        self.node_window = None

    def on_node_window_close(self):
        self.show_node_status_var.set(False)
        self.close_node_window()

    # ----------------------------
    # dialogs
    # ----------------------------
    def show_help_dialog(self):
        messagebox.showinfo(
            "Commands",
            "/list\n/rename NewName\n/quit\n\nEnter = send\nShift+Enter = newline"
        )

    def show_about_dialog(self):
        messagebox.showinfo(
            "About Aetherium",
            "Aetherium Client\nPersistent communication node interface"
        )

    # ----------------------------
    # helpers
    # ----------------------------
    def update_clock(self):
        self.clock_label.configure(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.root.after(1000, self.update_clock)

    def set_status(self, state: str, text: str, mode: str = None):
        p = self.palette
        self.status_text_var.set(text)

        if mode is not None:
            self.connection_mode_var.set(mode)

        color = p["red"]
        label_color = p["muted"]

        if state == "online":
            color = p["green"]
            label_color = p["muted"]
        elif state == "warning":
            color = p["yellow"]
            label_color = p["muted"]
        elif state == "neutral":
            color = p["muted"]
            label_color = p["muted"]

        self.status_dot.configure(fg=color)
        self.header_status_dot.configure(fg=color)
        self.header_status_text.configure(fg=label_color)
        self.status_label.configure(fg=color)

        if self.node_window and self.node_window.winfo_exists():
            self.node_window_dot.configure(fg=color)
            self.node_window_status.configure(fg=color)
            self.sync_node_window()

    def append_chat(self, text: str, tag: str = None):
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {text}\n"

        self.chat_text.configure(state="normal")
        if tag:
            self.chat_text.insert("end", line, tag)
        else:
            self.chat_text.insert("end", line)
        self.chat_text.see("end")
        self.chat_text.configure(state="disabled")

    def clear_message(self):
        self.message_box.delete("1.0", "end")

    def copy_host(self):
        value = self.host_var.get().strip()
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.append_chat(f"[SYSTEM] Copied host '{value}' to clipboard.", "system")

    def update_users(self, users):
        self.users_list.delete(0, "end")
        for user in users:
            self.users_list.insert("end", user)
        self.online_count_var.set(f"{len(users)} online")

    # ----------------------------
    # networking
    # ----------------------------
    def connect(self):
        if self.connected:
            return

        host = self.host_var.get().strip()
        username = self.username_var.get().strip()
        port_text = self.port_var.get().strip()

        if not host or not username or not port_text:
            messagebox.showerror("Missing info", "Enter host, port, and username.")
            return

        try:
            port = int(port_text)
        except ValueError:
            messagebox.showerror("Invalid port", "Port must be numeric.")
            return

        self.save_config()
        self.sync_node_window()
        self.set_status("warning", "Connecting...", "HANDSHAKE")
        self.append_chat(f"[SYSTEM] Attempting connection to {host}:{port}", "system")

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(8)
            self.sock.connect((host, port))
            self.sock.settimeout(0.5)
        except Exception as e:
            self.sock = None
            self.set_status("neutral", "Offline", "DISCONNECTED")
            self.append_chat(f"Connection failed: {e}", "error")
            return

        self.connected = True
        self.username_sent = False
        self.set_status("online", "Online", "CONNECTED")
        self.append_chat(f"[SYSTEM] Connected to {host}:{port}", "system")

        threading.Thread(target=self.receive_loop, daemon=True).start()

    def disconnect(self):
        if not self.connected:
            return
        try:
            self.send_raw("/quit", local_echo=False)
        except Exception:
            pass

        self.safe_close()
        self.connected = False
        self.username_sent = False
        self.update_users([])
        self.set_status("neutral", "Offline", "DISCONNECTED")
        self.append_chat("[SYSTEM] Disconnected.", "system")

    def safe_close(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def receive_loop(self):
        while self.connected and self.sock:
            try:
                data = self.sock.recv(4096)
                if not data:
                    self.inbox.put(("disconnect", "Host closed the connection."))
                    break

                decoded = data.decode("utf-8", errors="replace")
                for line in decoded.splitlines():
                    clean = line.strip()
                    if not clean:
                        continue

                    if (not self.username_sent) and "Enter username:" in clean:
                        self.inbox.put(("send_username", self.username_var.get().strip()))
                        self.username_sent = True
                    else:
                        self.inbox.put(("message", clean))

            except socket.timeout:
                continue
            except Exception as e:
                self.inbox.put(("disconnect", f"Receive error: {e}"))
                break

    def process_incoming(self):
        try:
            while True:
                kind, payload = self.inbox.get_nowait()

                if kind == "send_username":
                    self.send_raw(payload, local_echo=False)

                elif kind == "message":
                    self.handle_message(payload)

                elif kind == "disconnect":
                    if self.connected:
                        self.append_chat(payload, "error")
                        self.safe_close()
                        self.connected = False
                        self.username_sent = False
                        self.update_users([])
                        self.set_status("neutral", "Offline", "DISCONNECTED")
        except queue.Empty:
            pass

        self.root.after(80, self.process_incoming)

    def handle_message(self, msg: str):
        if msg.startswith("[USERLIST] "):
            raw = msg[len("[USERLIST] "):].strip()
            users = [u.strip() for u in raw.split(",") if u.strip()]
            self.update_users(users)
            return

        if msg.startswith("[SYSTEM]"):
            self.append_chat(msg, "system")
            return

        if msg.startswith("ERROR"):
            self.append_chat(msg, "error")
            return

        if msg.startswith("[CHAT] "):
            own = self.username_var.get().strip()
            if f"{own}:" in msg:
                self.append_chat(msg, "self")
            else:
                self.append_chat(msg)
            return

        if msg.startswith("/"):
            self.append_chat(msg, "command")
            return

        self.append_chat(msg)

    def send_raw(self, text: str, local_echo=False):
        if not self.connected or not self.sock:
            self.append_chat("Not connected.", "error")
            return
        try:
            self.sock.sendall((text.strip() + "\n").encode("utf-8"))
            if local_echo:
                self.append_chat(text.strip(), "command" if text.startswith("/") else "self")
        except Exception as e:
            self.append_chat(f"Send failed: {e}", "error")
            self.safe_close()
            self.connected = False
            self.username_sent = False
            self.update_users([])
            self.set_status("neutral", "Offline", "DISCONNECTED")

    def send_message(self):
        text = self.message_box.get("1.0", "end").strip()
        if not text:
            return

        self.send_raw(text, local_echo=False)
        self.clear_message()

    # ----------------------------
    # events
    # ----------------------------
    def on_enter_send(self, event):
        if event.state & 0x0001:
            return None
        self.send_message()
        return "break"

    def on_close(self):
        self.save_config()
        self.close_node_window()
        self.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AetheriumClient(root)
    root.mainloop()
