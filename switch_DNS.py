import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import re
import threading
import time

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

# ---------------- LOGGING ---------------- #

def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    def write():
        log_box.insert(tk.END, f"[{timestamp}] {msg}\n")
        log_box.see(tk.END)
    root.after(0, write)

def set_state(text):
    root.after(0, lambda: state_label.config(text=f"STATE: {text}"))

# ---------------- SYSTEM ---------------- #

def get_active_interface():
    log("Detecting active network interface...")
    out = subprocess.check_output("netsh interface show interface", shell=True, text=True)
    for line in out.splitlines():
        if "Connected" in line and ("Ethernet" in line or "Wi-Fi" in line):
            iface = line.split()[-1]
            log(f"Active interface: {iface}")
            return iface
    log("No active interface found")
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
    set_state("APPLYING DNS")
    log(f"Preparing to apply DNS: {primary}, {secondary}")

    previous_mode, previous_dns = get_current_dns(active_interface)

    try:
        subprocess.check_call(
            f'netsh interface ip set dns name="{active_interface}" static {primary}',
            shell=True
        )
        log(f"Primary DNS set to {primary}")

        subprocess.check_call(
            f'netsh interface ip add dns name="{active_interface}" addr={secondary} index=2',
            shell=True
        )
        log(f"Secondary DNS set to {secondary}")

        messagebox.showinfo("Success", "DNS applied successfully.")
        set_state("DONE")
    except Exception as e:
        log(f"ERROR applying DNS: {e}")
        set_state("ERROR")
        messagebox.showerror("Error", "Run as Administrator.")

def reset_dns():
    global previous_dns, previous_mode
    set_state("RESETTING DNS")
    log("Resetting DNS to DHCP")

    previous_mode, previous_dns = get_current_dns(active_interface)

    try:
        subprocess.check_call(
            f'netsh interface ip set dns name="{active_interface}" source=dhcp',
            shell=True
        )
        log("DNS reset to automatic (DHCP)")
        messagebox.showinfo("Success", "DNS reset to automatic.")
        set_state("DONE")
    except Exception as e:
        log(f"ERROR resetting DNS: {e}")
        set_state("ERROR")

def undo_dns():
    set_state("UNDOING DNS")
    log("Attempting to restore previous DNS")

    if not previous_mode:
        log("Nothing to undo")
        messagebox.showwarning("Undo", "Nothing to restore.")
        set_state("IDLE")
        return

    try:
        if previous_mode == "dhcp":
            reset_dns()
        else:
            subprocess.check_call(
                f'netsh interface ip set dns name="{active_interface}" static {previous_dns[0]}',
                shell=True
            )
            log(f"Restored primary DNS: {previous_dns[0]}")
            for i, dns in enumerate(previous_dns[1:], start=2):
                subprocess.check_call(
                    f'netsh interface ip add dns name="{active_interface}" addr={dns} index={i}',
                    shell=True
                )
                log(f"Restored secondary DNS: {dns}")
            messagebox.showinfo("Undo", "Previous DNS restored.")
            set_state("DONE")
    except Exception as e:
        log(f"ERROR undoing DNS: {e}")
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
    set_state("TESTING DNS")
    log("Starting DNS speed test")
    btn_test.config(state="disabled")

    def worker():
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

    threading.Thread(target=worker, daemon=True).start()

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

# ---------------- GUI ---------------- #

root = tk.Tk()
root.title("Windows DNS Changer")
root.geometry("700x650")
root.configure(bg=THEME["bg"])
root.resizable(False, False)

active_interface = get_active_interface()

style = ttk.Style()
style.theme_use("clam")
style.configure("TCombobox", fieldbackground=THEME["entry_bg"])

tk.Label(root, text="Windows DNS Changer",
         font=("Segoe UI", 16, "bold"),
         bg=THEME["bg"], fg=THEME["fg"]).pack(pady=10)

state_label = tk.Label(root, text="STATE: IDLE",
                       bg=THEME["bg"], fg="#90CAF9")
state_label.pack()

combo = ttk.Combobox(root, values=list(DNS_PROVIDERS.keys()),
                     state="readonly", width=65)
combo.pack(pady=8)
combo.current(0)

tk.Button(root, text="Apply Selected DNS",
          command=lambda: set_dns(*DNS_PROVIDERS[combo.get()]),
          bg=THEME["btn_bg"], fg="white",
          width=42).pack(pady=4)

btn_test = tk.Button(root, text="Find Fastest DNS (No Apply)",
                     command=start_speed_test,
                     bg=THEME["test_bg"], fg="white",
                     width=42)
btn_test.pack(pady=4)

tk.Button(root, text="Undo / Restore Previous DNS",
          command=undo_dns,
          bg=THEME["undo_bg"], fg="white",
          width=42).pack(pady=4)

tk.Button(root, text="Reset to Automatic (DHCP)",
          command=reset_dns,
          bg=THEME["reset_bg"], fg="white",
          width=42).pack(pady=4)

tk.Button(root, text="Exit Application",
          command=root.destroy,
          bg=THEME["exit_bg"], fg="white",
          width=42).pack(pady=6)

# ---------------- LOG CONSOLE ---------------- #

tk.Label(root, text="Activity Log",
         bg=THEME["bg"], fg="#B0B0B0").pack(pady=(10, 2))

log_frame = tk.Frame(root)
log_frame.pack(fill="both", expand=True, padx=10, pady=5)

scroll = tk.Scrollbar(log_frame)
scroll.pack(side="right", fill="y")

log_box = tk.Text(log_frame, height=12,
                  bg=THEME["log_bg"], fg=THEME["log_fg"],
                  yscrollcommand=scroll.set,
                  wrap="word")
log_box.pack(fill="both", expand=True)
scroll.config(command=log_box.yview)

log("Application started")
set_state("IDLE")

root.mainloop()
