import os
import sqlite3
import tkinter as tk
from tkinter import messagebox

# --- Database file path (in the same directory as script) ---
DB_FILE = os.path.join(os.getcwd(), "portfolio_users.db")

# --- SQL to create table and sample data ---
INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password TEXT NOT NULL
);

INSERT INTO users (username, password) 
SELECT 'alice', 'alice123' WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='alice');

INSERT INTO users (username, password) 
SELECT 'bob', 'qwerty' WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='bob');

INSERT INTO users (username, password) 
SELECT 'charlie', 'pass123' WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='charlie');
"""

# --- Create database file if it doesn't exist ---
first_run = not os.path.exists(DB_FILE)
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

if first_run:
    cursor.executescript(INIT_SQL)
    conn.commit()
    print(f"Database created at: {DB_FILE}")

# --- Tkinter GUI ---
root = tk.Tk()
root.title("Portfolio User Viewer")
root.geometry("400x300")

listbox = tk.Listbox(root, font=("Consolas", 12))
listbox.pack(fill="both", expand=True, padx=20, pady=20)

# Load usernames into the listbox
def load_users():
    listbox.delete(0, tk.END)
    cursor.execute("SELECT username FROM users")
    users = cursor.fetchall()
    for user in users:
        listbox.insert(tk.END, user[0])

# Show password when username is double-clicked
def show_password(event):
    selection = listbox.curselection()
    if selection:
        username = listbox.get(selection[0])
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        password = cursor.fetchone()[0]
        messagebox.showinfo("Password", f"Username: {username}\nPassword: {password}")

listbox.bind("<Double-Button-1>", show_password)

# Load Users button
load_button = tk.Button(root, text="Load Users", command=load_users, bg="green", fg="white")
load_button.pack(pady=10)

# --- Do NOT load users on startup anymore ---
# load_users()  <-- removed

root.mainloop()
conn.close()
