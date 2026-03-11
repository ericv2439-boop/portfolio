import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np

# --- Functions ---
def plot_equations(event=None):  # event=None allows it to be called from a key press
    try:
        m = float(linear_m_var.get())
        b = float(linear_b_var.get())
        a = float(quad_a_var.get())
        bb = float(quad_b_var.get())
        c = float(quad_c_var.get())
    except ValueError:
        return  # ignore invalid input

    x = np.linspace(-10, 10, 400)
    y_linear = m * x + b
    y_quad = a * x**2 + bb * x + c

    ax.clear()
    ax.plot(x, y_linear, label=f"Linear: y={m}x+{b}", color='blue')
    ax.plot(x, y_quad, label=f"Quadratic: y={a}x²+{bb}x+{c}", color='red')
    ax.set_title("Equations Plot")
    ax.set_xlabel("X-axis")
    ax.set_ylabel("Y-axis")
    ax.grid(True)
    ax.legend()
    canvas.draw()

# --- Main Window ---
root = tk.Tk()
root.title("Equation Plotter")

# --- Input Variables ---
linear_m_var = tk.StringVar(value="1")
linear_b_var = tk.StringVar(value="0")
quad_a_var = tk.StringVar(value="1")
quad_b_var = tk.StringVar(value="0")
quad_c_var = tk.StringVar(value="0")

# --- Layout ---
frame_inputs = ttk.Frame(root)
frame_inputs.pack(side=tk.LEFT, padx=10, pady=10)

# Linear inputs
ttk.Label(frame_inputs, text="Linear y=mx+b").grid(row=0, column=0, columnspan=2, pady=(0,5))
ttk.Label(frame_inputs, text="m:").grid(row=1, column=0, sticky="e")
ttk.Entry(frame_inputs, textvariable=linear_m_var, width=10).grid(row=1, column=1)
ttk.Label(frame_inputs, text="b:").grid(row=2, column=0, sticky="e")
ttk.Entry(frame_inputs, textvariable=linear_b_var, width=10).grid(row=2, column=1)

# Quadratic inputs
ttk.Label(frame_inputs, text="Quadratic y=ax²+bx+c").grid(row=3, column=0, columnspan=2, pady=(10,5))
ttk.Label(frame_inputs, text="a:").grid(row=4, column=0, sticky="e")
ttk.Entry(frame_inputs, textvariable=quad_a_var, width=10).grid(row=4, column=1)
ttk.Label(frame_inputs, text="b:").grid(row=5, column=0, sticky="e")
ttk.Entry(frame_inputs, textvariable=quad_b_var, width=10).grid(row=5, column=1)
ttk.Label(frame_inputs, text="c:").grid(row=6, column=0, sticky="e")
ttk.Entry(frame_inputs, textvariable=quad_c_var, width=10).grid(row=6, column=1)

# Update Button
ttk.Button(frame_inputs, text="Update Plot", command=plot_equations).grid(row=7, column=0, columnspan=2, pady=10)

# --- Plot Area ---
fig = Figure(figsize=(5,4), dpi=100)
ax = fig.add_subplot(111)
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

# --- Initial Plot ---
plot_equations()

# --- Bind Enter Key ---
root.bind('<Return>', plot_equations)  # Press Enter anywhere in the window to update plot

root.mainloop()
