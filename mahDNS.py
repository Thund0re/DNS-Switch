"""
DNS Changer Pro — Optimized Edition
Fully async, responsive, modern UI
"""

from __future__ import annotations
import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import re
import threading
import time
import sys
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

# ── Async executor for I/O tasks ─────────────────────────────────────────────
_executor = ThreadPoolExecutor(max_workers=6)

# ── Theme ─────────────────────────────────────────────────────────────────────
T = {
    "bg":          "#0D0D0F",
    "surface":     "#141418",
    "surface2":    "#1C1C22",
    "border":      "#2A2A35",
    "accent":      "#00E5FF",
    "accent2":     "#7C3AED",
    "green":       "#00C853",
    "red":         "#FF1744",
    "blue":        "#2979FF",
    "yellow":      "#FFD600",
    "fg":          "#E8E8F0",
    "fg2":         "#8888A0",
    "mono":        ("Consolas", 9),
    "ui":          ("Segoe UI", 9),
    "ui_bold":     ("Segoe UI", 9, "bold"),
    "title":       ("Segoe UI", 18, "bold"),
    "subtitle":    ("Segoe UI", 10),
}

# ── DNS Providers ─────────────────────────────────────────────────────────────
DNS_PROVIDERS: dict[str, tuple[str, str]] = {
    "Cloudflare — Privacy":          ("1.1.1.1",        "1.0.0.1"),
    "Google Public DNS":             ("8.8.8.8",        "8.8.4.4"),
    "Quad9 — Malware Block":         ("9.9.9.9",        "149.112.112.112"),
    "OpenDNS":                       ("208.67.222.222", "208.67.220.220"),
    "AdGuard DNS":                   ("94.140.14.14",   "94.140.15.15"),
    "CleanBrowsing":                 ("185.228.168.168","185.228.169.168"),
    "Control D":                     ("76.76.2.0",      "76.76.10.0"),
    "NextDNS":                       ("45.90.28.0",     "45.90.30.0"),
    "DNS.WATCH":                     ("84.200.69.80",   "84.200.70.40"),
    "Comodo Secure DNS":             ("8.26.56.26",     "8.20.247.20"),
}

# ── State ─────────────────────────────────────────────────────────────────────
@dataclass
class AppState:
    active_interface:  Optional[str]  = None
    previous_dns:      list           = field(default_factory=list)
    previous_mode:     Optional[str]  = None
    test_running:      bool           = False
    ready:             bool           = False

state = AppState()

# ══════════════════════════════════════════════════════════════════════════════
#  ASYNC SYSTEM LAYER
# ══════════════════════════════════════════════════════════════════════════════

def _run(cmd: str, timeout: int = 10) -> str:
    """Blocking subprocess helper — run in executor."""
    result = subprocess.check_output(
        cmd, shell=True, text=True, stderr=subprocess.DEVNULL, timeout=timeout
    )
    return result

async def async_run(cmd: str, timeout: int = 10) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, lambda: _run(cmd, timeout))

async def get_active_interface() -> Optional[str]:
    try:
        out = await async_run("netsh interface show interface", timeout=4)
        for line in out.splitlines():
            if "Connected" in line and ("Ethernet" in line or "Wi-Fi" in line):
                return line.split()[-1]
    except Exception:
        pass
    return None

async def get_current_dns(interface: str) -> tuple[str, list[str]]:
    try:
        out = await async_run(f'netsh interface ip show dns name="{interface}"')
        if "DHCP enabled" in out:
            return "dhcp", []
        return "static", re.findall(r"\d+\.\d+\.\d+\.\d+", out)
    except Exception:
        return "unknown", []

async def apply_dns(primary: str, secondary: str) -> bool:
    try:
        await async_run(
            f'netsh interface ip set dns name="{state.active_interface}" static {primary}'
        )
        await async_run(
            f'netsh interface ip add dns name="{state.active_interface}" addr={secondary} index=2'
        )
        return True
    except Exception:
        return False

async def reset_to_dhcp() -> bool:
    try:
        await async_run(
            f'netsh interface ip set dns name="{state.active_interface}" source=dhcp'
        )
        return True
    except Exception:
        return False

async def ping_ms(ip: str) -> Optional[float]:
    t = time.perf_counter()
    try:
        await async_run(f"ping -n 1 -w 700 {ip}", timeout=3)
        return (time.perf_counter() - t) * 1000
    except Exception:
        return None

async def lookup_ms(ip: str) -> Optional[float]:
    t = time.perf_counter()
    try:
        await async_run(f"nslookup example.com {ip}", timeout=3)
        return (time.perf_counter() - t) * 1000
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════════════
#  ASYNCIO BRIDGE  (runs asyncio loop in a background thread)
# ══════════════════════════════════════════════════════════════════════════════

_loop: asyncio.AbstractEventLoop = None  # type: ignore

def _start_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()

def submit(coro):
    """Schedule a coroutine on the background event loop; return a Future."""
    return asyncio.run_coroutine_threadsafe(coro, _loop)

# ══════════════════════════════════════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def ui(fn, *a, **kw):
    """Thread-safe UI call."""
    root.after(0, lambda: fn(*a, **kw))

def log(msg: str, kind: str = "info"):
    ts = time.strftime("%H:%M:%S")
    colours = {"info": T["fg2"], "ok": T["green"], "err": T["red"],
               "warn": T["yellow"], "act": T["accent"]}
    colour = colours.get(kind, T["fg2"])
    def _write():
        if not log_box.winfo_exists():
            return
        log_box.config(state="normal")
        log_box.insert(tk.END, f"[{ts}] ", "ts")
        log_box.insert(tk.END, f"{msg}\n", kind)
        log_box.see(tk.END)
        log_box.config(state="disabled")
    ui(_write)

def set_status(text: str, colour: str = None):
    colour = colour or T["fg2"]
    ui(status_val.config, text=text, fg=colour)

def set_dns_info(text: str):
    ui(dns_info_lbl.config, text=text)

def pulse_indicator(on: bool):
    c = T["accent"] if on else T["border"]
    ui(indicator.config, bg=c)

# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP — parallel interface detection + DNS read
# ══════════════════════════════════════════════════════════════════════════════

async def startup_probe():
    set_status("Detecting interface…", T["yellow"])
    iface = await get_active_interface()
    if not iface:
        set_status("No interface found", T["red"])
        log("Could not detect active interface", "err")
        return
    state.active_interface = iface
    log(f"Interface: {iface}", "ok")

    mode, dns_list = await get_current_dns(iface)
    if dns_list:
        label = f"{dns_list[0]}"
        if len(dns_list) > 1:
            label += f"  /  {dns_list[1]}"
    else:
        label = mode.upper()
    set_dns_info(f"Current DNS: {label}")
    set_status("Ready", T["green"])
    state.ready = True

# ══════════════════════════════════════════════════════════════════════════════
#  ACTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def _do_apply(primary: str, secondary: str):
    pulse_indicator(True)
    set_status("Saving previous DNS…", T["yellow"])
    state.previous_mode, state.previous_dns = await get_current_dns(state.active_interface)

    set_status("Applying DNS…", T["accent"])
    log(f"Applying  {primary}  /  {secondary}", "act")
    ok = await apply_dns(primary, secondary)
    pulse_indicator(False)
    if ok:
        set_status("Applied ✓", T["green"])
        log(f"DNS set to {primary} / {secondary}", "ok")
        ui(messagebox.showinfo, "Success", f"DNS applied.\n{primary}  /  {secondary}")
        mode, lst = await get_current_dns(state.active_interface)
        if lst:
            set_dns_info(f"Current DNS: {lst[0]}  /  {lst[1] if len(lst)>1 else ''}")
    else:
        set_status("Error — run as Admin", T["red"])
        log("Failed to apply DNS. Elevate privileges.", "err")
        ui(messagebox.showerror, "Error", "Run as Administrator.")

async def _do_reset():
    pulse_indicator(True)
    set_status("Saving previous DNS…", T["yellow"])
    state.previous_mode, state.previous_dns = await get_current_dns(state.active_interface)

    set_status("Resetting to DHCP…", T["accent"])
    log("Resetting DNS to DHCP", "act")
    ok = await reset_to_dhcp()
    pulse_indicator(False)
    if ok:
        set_status("Reset ✓", T["green"])
        log("DNS reset to automatic (DHCP)", "ok")
        set_dns_info("Current DNS: DHCP (Automatic)")
        ui(messagebox.showinfo, "Done", "DNS reset to automatic.")
    else:
        set_status("Error — run as Admin", T["red"])
        log("Failed to reset DNS.", "err")
        ui(messagebox.showerror, "Error", "Run as Administrator.")

async def _do_undo():
    if not state.previous_mode:
        log("Nothing to undo", "warn")
        ui(messagebox.showwarning, "Undo", "Nothing to restore.")
        return
    pulse_indicator(True)
    set_status("Restoring previous DNS…", T["accent"])
    log("Undoing last DNS change", "act")
    if state.previous_mode == "dhcp":
        ok = await reset_to_dhcp()
    else:
        ok = await apply_dns(state.previous_dns[0],
                             state.previous_dns[1] if len(state.previous_dns) > 1 else state.previous_dns[0])
    pulse_indicator(False)
    if ok:
        set_status("Restored ✓", T["green"])
        log("Previous DNS restored", "ok")
        ui(messagebox.showinfo, "Undo", "Previous DNS restored.")
    else:
        set_status("Error — run as Admin", T["red"])
        ui(messagebox.showerror, "Error", "Run as Administrator.")

async def _do_speed_test():
    if state.test_running:
        return
    state.test_running = True
    ui(btn_test.config, state="disabled", text="Testing…")
    set_status("Speed test running…", T["yellow"])
    log("Starting parallel DNS speed test", "act")

    # Test all providers in parallel
    async def test_one(name: str, ip: str):
        p, d = await asyncio.gather(ping_ms(ip), lookup_ms(ip))
        return name, p, d

    tasks = [test_one(name, ips[0]) for name, ips in DNS_PROVIDERS.items()]
    raw = await asyncio.gather(*tasks)

    results = []
    for name, p, d in raw:
        if p is not None and d is not None:
            score = p * 0.6 + d * 0.4
            results.append((name, round(p), round(d), round(score)))
            log(f"{name:30s}  ping {p:>5.0f}ms  resolve {d:>5.0f}ms", "info")
        else:
            log(f"{name} — unreachable", "warn")

    state.test_running = False
    ui(btn_test.config, state="normal", text="Find Fastest DNS")

    if not results:
        set_status("No response", T["red"])
        ui(messagebox.showerror, "Error", "No DNS servers responded.")
        return

    results.sort(key=lambda x: x[3])
    fastest = results[0]
    set_status("Test complete ✓", T["green"])

    report = "DNS Speed Test  (ms)\n" + "─" * 48 + "\n"
    for i, r in enumerate(results):
        medal = ("🥇 ", "🥈 ", "🥉 ")[i] if i < 3 else "    "
        report += f"{medal}{r[0]}\n    Ping {r[1]:>4}  Resolve {r[2]:>4}  Score {r[3]:>4}\n\n"
    report += f"Fastest: {fastest[0]}\n\nApply it now?"

    log(f"Fastest DNS: {fastest[0]}", "ok")
    if ui_ask_yes_no("Fastest DNS Found", report):
        ui(combo.set, fastest[0])

def ui_ask_yes_no(title: str, msg: str) -> bool:
    """Thread-safe yes/no dialog — blocks the calling coroutine via an event."""
    result = threading.Event()
    answer = [False]
    def ask():
        answer[0] = messagebox.askyesno(title, msg)
        result.set()
    ui(ask)
    result.wait()
    return answer[0]

# ── Button handlers (non-blocking) ───────────────────────────────────────────

def on_apply():
    if not _guard(): return
    p, s = DNS_PROVIDERS[combo.get()]
    submit(_do_apply(p, s))

def on_reset():
    if not _guard(): return
    submit(_do_reset())

def on_undo():
    if not _guard(): return
    submit(_do_undo())

def on_speed_test():
    if not _guard(): return
    submit(_do_speed_test())

def _guard() -> bool:
    if not state.active_interface:
        messagebox.showwarning("Not Ready", "No active network interface detected.")
        return False
    return True

# ══════════════════════════════════════════════════════════════════════════════
#  UI BUILD
# ══════════════════════════════════════════════════════════════════════════════

root = tk.Tk()
root.title("DNS Changer Pro")
root.configure(bg=T["bg"])
root.resizable(True, True)
root.minsize(640, 560)

# Responsive sizing
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
w = min(max(680, int(sw * 0.42)), 1100)
h = min(max(580, int(sh * 0.62)), 920)
root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

# ── Style ─────────────────────────────────────────────────────────────────────
style = ttk.Style()
style.theme_use("clam")
style.configure("DNS.TCombobox",
    fieldbackground=T["surface2"],
    background=T["surface2"],
    foreground=T["fg"],
    arrowcolor=T["accent"],
    bordercolor=T["border"],
    lightcolor=T["border"],
    darkcolor=T["border"],
    insertcolor=T["fg"],
    selectbackground=T["accent2"],
    selectforeground="#fff",
    padding=(10, 8),
    font=T["ui"],
)
style.map("DNS.TCombobox",
    fieldbackground=[("readonly", T["surface2"])],
    foreground=[("readonly", T["fg"])],
)

def flat_btn(parent, text, cmd, bg, fg="#FFFFFF", font=None, padx=14, pady=10):
    f = font or T["ui_bold"]
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                  font=f, relief=tk.FLAT, bd=0,
                  padx=padx, pady=pady, cursor="hand2",
                  highlightthickness=1, highlightbackground=T["border"],
                  highlightcolor=T["accent"])
    def _on(e): b.config(bg=_lighten(bg))
    def _off(e): b.config(bg=bg)
    b.bind("<Enter>", _on)
    b.bind("<Leave>", _off)
    return b

def _lighten(hex_colour: str, factor: float = 1.18) -> str:
    hex_colour = hex_colour.lstrip("#")
    r, g, b_ = (int(hex_colour[i:i+2], 16) for i in (0, 2, 4))
    r = min(255, int(r * factor))
    g = min(255, int(g * factor))
    b_ = min(255, int(b_ * factor))
    return f"#{r:02x}{g:02x}{b_:02x}"

def sep(parent):
    tk.Frame(parent, height=1, bg=T["border"]).pack(fill="x", padx=0, pady=0)

# ═══════════════════  HEADER  ═════════════════════════════════════════════════
header = tk.Frame(root, bg=T["surface"], pady=0)
header.pack(fill="x")

hinner = tk.Frame(header, bg=T["surface"])
hinner.pack(fill="x", padx=20, pady=16)

# Title row
title_row = tk.Frame(hinner, bg=T["surface"])
title_row.pack(fill="x")

tk.Label(title_row, text="DNS", font=("Segoe UI", 22, "bold"),
         bg=T["surface"], fg=T["accent"]).pack(side="left")
tk.Label(title_row, text=" Changer Pro", font=("Segoe UI", 22, "bold"),
         bg=T["surface"], fg=T["fg"]).pack(side="left")

# Pulsing indicator dot
indicator = tk.Label(title_row, text="  ●", font=("Segoe UI", 12),
                     bg=T["surface"], fg=T["border"])
indicator.pack(side="left", padx=(6, 0), pady=(4, 0))

# Status row
status_row = tk.Frame(hinner, bg=T["surface"])
status_row.pack(fill="x", pady=(4, 0))

tk.Label(status_row, text="STATUS", font=("Segoe UI", 7, "bold"),
         bg=T["surface"], fg=T["fg2"]).pack(side="left")
tk.Label(status_row, text="  │  ", bg=T["surface"], fg=T["border"]).pack(side="left")
status_val = tk.Label(status_row, text="Initialising…",
                      font=("Segoe UI", 9), bg=T["surface"], fg=T["yellow"])
status_val.pack(side="left")

dns_info_lbl = tk.Label(hinner, text="",
                        font=("Segoe UI", 8), bg=T["surface"], fg=T["fg2"])
dns_info_lbl.pack(anchor="w", pady=(3, 0))

sep(root)

# ═══════════════════  MAIN PANEL  ═════════════════════════════════════════════
main = tk.Frame(root, bg=T["bg"])
main.pack(fill="both", expand=True)

# Left column
left = tk.Frame(main, bg=T["bg"], width=300)
left.pack(side="left", fill="both", expand=True, padx=(20, 10), pady=20)
left.pack_propagate(False)

# Provider label
tk.Label(left, text="DNS PROVIDER", font=("Segoe UI", 7, "bold"),
         bg=T["bg"], fg=T["fg2"]).pack(anchor="w", pady=(0, 6))

combo = ttk.Combobox(left, values=list(DNS_PROVIDERS.keys()),
                     state="readonly", style="DNS.TCombobox")
combo.pack(fill="x")
combo.current(0)

# Primary action
tk.Frame(left, height=12, bg=T["bg"]).pack()
apply_btn = flat_btn(left, "⟶  Apply DNS", on_apply, T["accent2"],
                     font=("Segoe UI", 10, "bold"), pady=12)
apply_btn.pack(fill="x")

# Secondary row
tk.Frame(left, height=8, bg=T["bg"]).pack()
row2 = tk.Frame(left, bg=T["bg"])
row2.pack(fill="x")

btn_test = flat_btn(row2, "⚡ Fastest", on_speed_test, T["surface2"],
                    fg=T["accent"], pady=10)
btn_test.pack(side="left", fill="both", expand=True, padx=(0, 4))

flat_btn(row2, "↩ Undo", on_undo, T["surface2"],
         fg=T["yellow"], pady=10).pack(side="left", fill="both", expand=True, padx=(4, 0))

# Tertiary row
tk.Frame(left, height=8, bg=T["bg"]).pack()
row3 = tk.Frame(left, bg=T["bg"])
row3.pack(fill="x")

flat_btn(row3, "⟲ DHCP Reset", on_reset, T["surface2"],
         fg=T["red"], pady=10).pack(side="left", fill="both", expand=True, padx=(0, 4))
flat_btn(row3, "✕ Exit", root.destroy, T["surface2"],
         fg=T["fg2"], pady=10).pack(side="left", fill="both", expand=True, padx=(4, 0))

# Provider info card
tk.Frame(left, height=16, bg=T["bg"]).pack()
info_frame = tk.Frame(left, bg=T["surface"], highlightthickness=1,
                      highlightbackground=T["border"])
info_frame.pack(fill="x")

tk.Label(info_frame, text="SELECTED", font=("Segoe UI", 6, "bold"),
         bg=T["surface"], fg=T["fg2"]).pack(anchor="w", padx=12, pady=(10, 2))

def update_info_card(*_):
    name = combo.get()
    p, s = DNS_PROVIDERS.get(name, ("—", "—"))
    primary_lbl.config(text=p)
    secondary_lbl.config(text=s)

info_inner = tk.Frame(info_frame, bg=T["surface"])
info_inner.pack(fill="x", padx=12, pady=(0, 12))

tk.Label(info_inner, text="Primary", font=("Segoe UI", 8),
         bg=T["surface"], fg=T["fg2"]).grid(row=0, column=0, sticky="w")
primary_lbl = tk.Label(info_inner, text="1.1.1.1",
                       font=("Consolas", 11, "bold"), bg=T["surface"], fg=T["accent"])
primary_lbl.grid(row=1, column=0, sticky="w")

tk.Frame(info_inner, width=20, bg=T["surface"]).grid(row=0, column=1)

tk.Label(info_inner, text="Secondary", font=("Segoe UI", 8),
         bg=T["surface"], fg=T["fg2"]).grid(row=0, column=2, sticky="w")
secondary_lbl = tk.Label(info_inner, text="1.0.0.1",
                          font=("Consolas", 11, "bold"), bg=T["surface"], fg=T["fg2"])
secondary_lbl.grid(row=1, column=2, sticky="w")

combo.bind("<<ComboboxSelected>>", update_info_card)
update_info_card()

# ─── Vertical divider ────────────────────────────────────────────────────────
tk.Frame(main, width=1, bg=T["border"]).pack(side="left", fill="y", pady=20)

# Right column — log
right = tk.Frame(main, bg=T["bg"])
right.pack(side="left", fill="both", expand=True, padx=(10, 20), pady=20)

log_header = tk.Frame(right, bg=T["bg"])
log_header.pack(fill="x", pady=(0, 8))
tk.Label(log_header, text="ACTIVITY LOG", font=("Segoe UI", 7, "bold"),
         bg=T["bg"], fg=T["fg2"]).pack(side="left")

log_frame = tk.Frame(right, bg=T["surface"],
                     highlightthickness=1, highlightbackground=T["border"])
log_frame.pack(fill="both", expand=True)

scroll = tk.Scrollbar(log_frame, bg=T["surface2"], troughcolor=T["surface"],
                      relief=tk.FLAT, bd=0, highlightthickness=0)
scroll.pack(side="right", fill="y")

log_box = tk.Text(log_frame,
                  bg=T["surface"], fg=T["fg2"],
                  font=T["mono"],
                  relief=tk.FLAT, bd=0,
                  padx=12, pady=10,
                  wrap="word",
                  state="disabled",
                  yscrollcommand=scroll.set,
                  selectbackground=T["accent2"],
                  insertbackground=T["accent"],
                  spacing1=2, spacing3=2,
                  cursor="arrow")
log_box.pack(fill="both", expand=True)
scroll.config(command=log_box.yview)

# Tag colours
for tag, colour in (("ts", T["border"]), ("ok", T["green"]),
                    ("err", T["red"]), ("warn", T["yellow"]),
                    ("act", T["accent"]), ("info", T["fg2"])):
    log_box.tag_config(tag, foreground=colour)

# ════════════════════════════════════════════════════════════════════════════
#  BOOT
# ════════════════════════════════════════════════════════════════════════════

# Start asyncio event loop in background thread
_bg_thread = threading.Thread(target=_start_loop, daemon=True)
_bg_thread.start()
# Give loop a moment to start
time.sleep(0.05)

# Kick off async startup probe (non-blocking)
submit(startup_probe())
log("DNS Changer Pro — ready", "act")

root.mainloop()
