import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import re
import threading
import time
import os
import json
from functools import lru_cache

# ---------------- THEME ---------------- #
THEME = {
    "bg": "#2C2C2C",
    "fg": "#FFFFFF",
    "btn_bg": "#4CAF50",
    "reset_bg": "#F44336",
    "undo_bg": "#2196F3",
    "exit_bg": "#616161",
    "test_bg": "#9C27B0",
    "entry_bg": "#404040",
    "log_bg": "#1E1E1E",
    "log_fg": "#CFCFCF"
}

# ---------------- DNS PROVIDERS ---------------- #
DNS_PROVIDERS = {
    "Cloudflare (Fastest, Privacy)": ("1.1.1.1", "1.0.0.1"),
    "Google Public DNS": ("8.8.8.8", "8.8.4.4"),
    "Quad9 (Malware Blocking)": ("9.9.9.9", "149.112.112.112"),
    "OpenDNS": ("208.67.222.222", "208.67.220.220"),
    "AdGuard DNS": ("94.140.14.14", "94.140.15.15"),
    "CleanBrowsing": ("185.228.168.168", "185.228.169.168"),
    "Control D": ("76.76.2.0", "76.76.10.0"),
    "NextDNS": ("45.90.28.0", "45.90.30.0"),
    "DNS.WATCH": ("84.200.69.80", "84.200.70.40"),
    "Comodo Secure DNS": ("8.26.56.26", "8.20.247.20")
}

previous_dns = None
previous_mode = None
active_interface = None
current_dns_display = None
interface_detecting = False

# ---------------- LOGGING ---------------- #

def log(msg):
    """Optimized logging - batch updates when possible"""
    timestamp = time.strftime("%H:%M:%S")
    def write():
        if log_box.winfo_exists():
            log_box.insert(tk.END, f"[{timestamp}] {msg}\n")
            log_box.see(tk.END)
    root.after(0, write)

def set_state(text):
    root.after(0, lambda: state_label.config(text=f"STATE: {text}"))

# ---------------- SYSTEM ---------------- #

def get_active_interface():
    """Get active interface with timeout"""
    try:
        out = subprocess.check_output("netsh interface show interface", shell=True, text=True, timeout=3)
        for line in out.splitlines():
            if "Connected" in line and ("Ethernet" in line or "Wi-Fi" in line):
                iface = line.split()[-1]
                log(f"Active interface: {iface}")
                return iface
    except subprocess.TimeoutExpired:
        log("Interface detection timeout")
    except Exception as e:
        log(f"Interface detection error: {e}")
    return None

def get_current_dns(interface):
    out = subprocess.check_output(
        f'netsh interface ip show dns name="{interface}"',
        shell=True, text=True
    )
    if "DHCP enabled" in out:
        return "dhcp", []
    return "static", re.findall(r"\d+\.\d+\.\d+\.\d+", out)

def set_dns(primary, secondary):
    global previous_dns, previous_mode
    """Apply DNS in background thread"""
    threading.Thread(target=_apply_dns_worker, args=(primary, secondary), daemon=True).start()

def _apply_dns_worker(primary, secondary):
    """Background DNS application"""
    global previous_dns, previous_mode
    set_state("APPLYING DNS")
    log(f"Preparing to apply DNS: {primary}, {secondary}")

    previous_mode, previous_dns = get_current_dns(active_interface)

    try:
        subprocess.check_call(
            f'netsh interface ip set dns name="{active_interface}" static {primary}',
            shell=True,
            timeout=10
        )
        log(f"Primary DNS set to {primary}")

        subprocess.check_call(
            f'netsh interface ip add dns name="{active_interface}" addr={secondary} index=2',
            shell=True,
            timeout=10
        )
        log(f"Secondary DNS set to {secondary}")

        root.after(0, lambda: messagebox.showinfo("Success", "DNS applied successfully."))
        set_state("DONE")
    except subprocess.TimeoutExpired:
        log("DNS operation timeout")
        root.after(0, lambda: messagebox.showerror("Error", "Operation timed out. Run as Administrator."))
        set_state("ERROR")
    except Exception as e:
        log(f"ERROR applying DNS: {e}")
        root.after(0, lambda: messagebox.showerror("Error", "Run as Administrator."))
        set_state("ERROR")

def reset_dns():
    """Reset DNS to DHCP in background"""
    threading.Thread(target=_reset_dns_worker, daemon=True).start()

def _reset_dns_worker():
    global previous_dns, previous_mode
    set_state("RESETTING DNS")
    log("Resetting DNS to DHCP")

    previous_mode, previous_dns = get_current_dns(active_interface)

    try:
        subprocess.check_call(
            f'netsh interface ip set dns name="{active_interface}" source=dhcp',
            shell=True,
            timeout=10
        )
        log("DNS reset to automatic (DHCP)")
        root.after(0, lambda: messagebox.showinfo("Success", "DNS reset to automatic."))
        set_state("DONE")
    except Exception as e:
        log(f"ERROR resetting DNS: {e}")
        root.after(0, lambda: messagebox.showerror("Error", "Run as Administrator."))
        set_state("ERROR")

def undo_dns():
    """Undo DNS changes in background"""
    threading.Thread(target=_undo_dns_worker, daemon=True).start()

def _undo_dns_worker():
    set_state("UNDOING DNS")
    log("Attempting to restore previous DNS")

    if not previous_mode:
        log("Nothing to undo")
        root.after(0, lambda: messagebox.showwarning("Undo", "Nothing to restore."))
        set_state("IDLE")
        return

    try:
        if previous_mode == "dhcp":
            _reset_dns_worker()
        else:
            subprocess.check_call(
                f'netsh interface ip set dns name="{active_interface}" static {previous_dns[0]}',
                shell=True,
                timeout=10
            )
            log(f"Restored primary DNS: {previous_dns[0]}")
            for i, dns in enumerate(previous_dns[1:], start=2):
                subprocess.check_call(
                    f'netsh interface ip add dns name="{active_interface}" addr={dns} index={i}',
                    shell=True,
                    timeout=10
                )
                log(f"Restored secondary DNS: {dns}")
            root.after(0, lambda: messagebox.showinfo("Undo", "Previous DNS restored."))
            set_state("DONE")
    except Exception as e:
        log(f"ERROR undoing DNS: {e}")
        root.after(0, lambda: messagebox.showerror("Error", "Run as Administrator."))
        set_state("ERROR")

# ---------------- SPEED TEST ---------------- #

def ping_time(ip):
    start = time.time()
    try:
        subprocess.check_output(f"ping -n 1 -w 700 {ip}", shell=True)
        return (time.time() - start) * 1000
    except:
        return None

def dns_lookup_time(ip):
    start = time.time()
    try:
        subprocess.check_output(
            f'nslookup example.com {ip}',
            shell=True,
            stderr=subprocess.DEVNULL
        )
        return (time.time() - start) * 1000
    except:
        return None

def start_speed_test():
    """Start speed test in background"""
    set_state("TESTING DNS")
    log("Starting DNS speed test")
    btn_test.config(state="disabled")
    threading.Thread(target=_speed_test_worker, daemon=True).start()

def _speed_test_worker():
    results = []
    for name, (ip, _) in DNS_PROVIDERS.items():
        log(f"Testing {name} ({ip})")
        p = ping_time(ip)
        d = dns_lookup_time(ip)
        if p and d:
            score = (p * 0.6) + (d * 0.4)
            results.append((name, round(p), round(d), round(score)))
            log(f"Result → Ping: {p:.0f} ms | Resolve: {d:.0f} ms")
        else:
            log(f"{name} unreachable")

    root.after(0, lambda: show_results(results))

def show_results(results):
    btn_test.config(state="normal")
    set_state("DONE")

    if not results:
        log("No DNS responded")
        messagebox.showerror("Error", "No DNS servers responded.")
        return

    results.sort(key=lambda x: x[3])
    fastest = results[0][0]

    report = "DNS Speed Test Results (ms)\n\n"
    for r in results:
        report += f"{r[0]}\n  Ping: {r[1]} | Resolve: {r[2]} | Score: {r[3]}\n\n"

    report += f"Fastest DNS:\n{fastest}\n\nSelect it?"

    log(f"Fastest DNS detected: {fastest}")

    if messagebox.askyesno("Fastest DNS Found", report):
        combo.set(fastest)
        log(f"User selected {fastest}")

# Detect interface in background during startup
def _detect_interface_async():
    global active_interface, interface_detecting
    interface_detecting = True
    active_interface = get_active_interface()
    interface_detecting = False
    if active_interface:
        root.after(0, lambda: load_current_dns_display())

def load_current_dns_display():
    """Display current DNS settings"""
    global current_dns_display
    if active_interface:
        mode, dns_list = get_current_dns(active_interface)
        if dns_list:
            dns_str = f"Current DNS: {dns_list[0]}"
            if len(dns_list) > 1:
                dns_str += f" | {dns_list[1]}"
        else:
            dns_str = f"Current DNS: {mode.upper()}"
        current_dns_display.config(text=dns_str)

def get_screen_size():
    """Get screen resolution for initial window size"""
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    # Use 65% of screen or minimum 700x650
    width = max(700, int(screen_width * 0.65))
    height = max(650, int(screen_height * 0.65))
    # Cap at reasonable max
    width = min(width, 1200)
    height = min(height, 1000)
    return width, height

def center_window(w, h):
    """Center window on screen"""
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - w) // 2
    y = (screen_height - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

# Create window early for fast startup
root = tk.Tk()
root.title("DNS Changer Pro")
root.configure(bg=THEME["bg"])
root.resizable(True, True)
root.minsize(600, 500)

# Determine window size based on screen
win_w, win_h = get_screen_size()
center_window(win_w, win_h)

# Start interface detection in background
threading.Thread(target=_detect_interface_async, daemon=True).start()

style = ttk.Style()
style.theme_use("clam")
style.configure("TCombobox", fieldbackground=THEME["entry_bg"])

# Header
header_frame = tk.Frame(root, bg=THEME["bg"])
header_frame.pack(fill="x", padx=15, pady=10)

tk.Label(header_frame, text="DNS Changer Pro",
         font=("Segoe UI", 16, "bold"),
         bg=THEME["bg"], fg=THEME["fg"]).pack(anchor="w")

state_label = tk.Label(header_frame, text="STATE: IDLE",
                       bg=THEME["bg"], fg="#00BCD4")
state_label.pack(anchor="w", pady=(5, 0))

current_dns_display = tk.Label(header_frame, text="Detecting interface...",
                               bg=THEME["bg"], fg="#90CAF9", font=("Segoe UI", 9))
current_dns_display.pack(anchor="w", pady=(2, 0))

# DNS Provider Selection
select_frame = tk.Frame(root, bg=THEME["bg"])
select_frame.pack(fill="x", padx=15, pady=10)

tk.Label(select_frame, text="Select DNS Provider:",
         font=("Segoe UI", 10),
         bg=THEME["bg"], fg=THEME["fg"]).pack(anchor="w", pady=(0, 5))

combo = ttk.Combobox(select_frame, values=list(DNS_PROVIDERS.keys()),
                     state="readonly")
combo.pack(fill="x", pady=5)
combo.current(0)

# Main buttons
btn_frame = tk.Frame(root, bg=THEME["bg"])
btn_frame.pack(fill="x", padx=15, pady=10)

tk.Button(btn_frame, text="Apply Selected DNS",
          command=lambda: set_dns(*DNS_PROVIDERS[combo.get()]),
          bg=THEME["btn_bg"], fg="white",
          font=("Segoe UI", 10),
          relief=tk.FLAT, padx=10, pady=8).pack(fill="x", pady=4)

# Secondary buttons
btn_row = tk.Frame(root, bg=THEME["bg"])
btn_row.pack(fill="x", padx=15, pady=5)

btn_test = tk.Button(btn_row, text="Find Fastest DNS",
                     command=start_speed_test,
                     bg=THEME["test_bg"], fg="white",
                     font=("Segoe UI", 9),
                     relief=tk.FLAT, padx=10, pady=8)
btn_test.pack(side="left", fill="both", expand=True, padx=2)

tk.Button(btn_row, text="Undo",
          command=undo_dns,
          bg=THEME["undo_bg"], fg="white",
          font=("Segoe UI", 9),
          relief=tk.FLAT, padx=10, pady=8).pack(side="left", fill="both", expand=True, padx=2)

# Tertiary buttons
btn_row2 = tk.Frame(root, bg=THEME["bg"])
btn_row2.pack(fill="x", padx=15, pady=5)

tk.Button(btn_row2, text="Reset (DHCP)",
          command=reset_dns,
          bg=THEME["reset_bg"], fg="white",
          font=("Segoe UI", 9),
          relief=tk.FLAT, padx=10, pady=8).pack(side="left", fill="both", expand=True, padx=2)

tk.Button(btn_row2, text="Exit",
          command=root.destroy,
          bg=THEME["exit_bg"], fg="white",
          font=("Segoe UI", 9),
          relief=tk.FLAT, padx=10, pady=8).pack(side="left", fill="both", expand=True, padx=2)

# Activity Log
tk.Label(root, text="Activity Log",
         font=("Segoe UI", 10, "bold"),
         bg=THEME["bg"], fg=THEME["fg"]).pack(anchor="w", padx=15, pady=(10, 5))

log_frame = tk.Frame(root, bg=THEME["entry_bg"])
log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

scroll = tk.Scrollbar(log_frame)
scroll.pack(side="right", fill="y")

log_box = tk.Text(log_frame, height=8,
                  bg=THEME["log_bg"], fg=THEME["log_fg"],
                  yscrollcommand=scroll.set,
                  wrap="word",
                  font=("Courier New", 9),
                  relief=tk.FLAT)
log_box.pack(fill="both", expand=True)
scroll.config(command=log_box.yview)

log("Application started")
set_state("READY")

root.mainloop()
