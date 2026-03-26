"""
DNS Changer Pro — Complete Network Utility
Async, multi-theme, persistent prefs, elevation-aware
stdlib only (tkinter + subprocess + socket + asyncio)
"""
from __future__ import annotations
import asyncio, json, os, re, socket, subprocess, sys, threading, time, ctypes
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
#  ELEVATION  (Windows UAC re-launch)
# ─────────────────────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def relaunch_as_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1
    )
    sys.exit(0)

# ─────────────────────────────────────────────────────────────────────────────
#  PREFS  (window geometry + theme)
# ─────────────────────────────────────────────────────────────────────────────

PREFS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "DNSChangerPro" / "prefs.json"

def load_prefs() -> dict:
    try:
        return json.loads(PREFS_PATH.read_text())
    except Exception:
        return {}

def save_prefs(data: dict):
    try:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
#  THEMES
# ─────────────────────────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        "name":     "Dark",
        "bg":       "#0D0D0F",
        "surface":  "#141418",
        "surface2": "#1C1C24",
        "border":   "#2A2A38",
        "accent":   "#00E5FF",
        "accent2":  "#7C3AED",
        "ok":       "#00C853",
        "err":      "#FF1744",
        "warn":     "#FFD600",
        "blue":     "#2979FF",
        "fg":       "#E4E4EE",
        "fg2":      "#6E6E88",
        "log_bg":   "#0A0A0C",
        "mono":     ("Consolas", 9),
    },
    "light": {
        "name":     "Light",
        "bg":       "#F0F0F5",
        "surface":  "#FFFFFF",
        "surface2": "#E8E8F0",
        "border":   "#CCCCDD",
        "accent":   "#0055CC",
        "accent2":  "#6D28D9",
        "ok":       "#15803D",
        "err":      "#DC2626",
        "warn":     "#B45309",
        "blue":     "#1D4ED8",
        "fg":       "#111128",
        "fg2":      "#555570",
        "log_bg":   "#FAFAFA",
        "mono":     ("Consolas", 9),
    },
    "tinted": {
        "name":     "Amber",
        "bg":       "#1A1208",
        "surface":  "#221A0A",
        "surface2": "#2C2210",
        "border":   "#3D3018",
        "accent":   "#FFB300",
        "accent2":  "#E65100",
        "ok":       "#8BC34A",
        "err":      "#FF5722",
        "warn":     "#FFC107",
        "blue":     "#29B6F6",
        "fg":       "#F5E6C8",
        "fg2":      "#8A7A58",
        "log_bg":   "#140F04",
        "mono":     ("Consolas", 9),
    },
}

# Active theme (mutable reference)
T = dict(THEMES["dark"])

# ─────────────────────────────────────────────────────────────────────────────
#  DNS PROVIDERS
# ─────────────────────────────────────────────────────────────────────────────

DNS_PROVIDERS: dict[str, tuple[str, str]] = {
    "Cloudflare — Privacy":   ("1.1.1.1",         "1.0.0.1"),
    "Google Public DNS":      ("8.8.8.8",          "8.8.4.4"),
    "Quad9 — Malware Block":  ("9.9.9.9",          "149.112.112.112"),
    "OpenDNS":                ("208.67.222.222",   "208.67.220.220"),
    "AdGuard DNS":            ("94.140.14.14",     "94.140.15.15"),
    "CleanBrowsing":          ("185.228.168.168",  "185.228.169.168"),
    "Control D":              ("76.76.2.0",        "76.76.10.0"),
    "NextDNS":                ("45.90.28.0",       "45.90.30.0"),
    "DNS.WATCH":              ("84.200.69.80",     "84.200.70.40"),
    "Comodo Secure DNS":      ("8.26.56.26",       "8.20.247.20"),
}

# ─────────────────────────────────────────────────────────────────────────────
#  APP STATE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AppState:
    active_interface:   Optional[str] = None
    previous_dns:       list          = field(default_factory=list)
    previous_mode:      Optional[str] = None
    test_running:       bool          = False
    ping_running:       bool          = False
    ping_history:       list          = field(default_factory=list)   # last 30 pings ms
    ready:              bool          = False
    admin:              bool          = False
    current_theme:      str           = "dark"

S = AppState()

# ─────────────────────────────────────────────────────────────────────────────
#  ASYNC ENGINE
# ─────────────────────────────────────────────────────────────────────────────

_executor = ThreadPoolExecutor(max_workers=8)
_loop: asyncio.AbstractEventLoop = None  # type: ignore

def _start_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()

def submit(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop)

def ui(fn, *a, **kw):
    root.after(0, lambda: fn(*a, **kw))

def _run(cmd: str, timeout: int = 12) -> str:
    return subprocess.check_output(
        cmd, shell=True, text=True, stderr=subprocess.DEVNULL, timeout=timeout
    )

async def arun(cmd: str, timeout: int = 12) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, lambda: _run(cmd, timeout))

# ─────────────────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def log(msg: str, kind: str = "info"):
    ts = time.strftime("%H:%M:%S")
    def _w():
        if not log_box.winfo_exists():
            return
        log_box.config(state="normal")
        log_box.insert("end", f"[{ts}] ", "ts")
        log_box.insert("end", f"{msg}\n", kind)
        log_box.see("end")
        log_box.config(state="disabled")
    ui(_w)

def set_status(text: str, col: str = None):
    col = col or T["fg2"]
    ui(status_val.config, text=text, fg=col)

def set_dns_info(text: str):
    ui(dns_info_lbl.config, text=text)

def pulse(on: bool):
    ui(indicator.config, fg=T["accent"] if on else T["border"])

# ─────────────────────────────────────────────────────────────────────────────
#  NETWORK HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def get_active_interface() -> Optional[str]:
    try:
        out = await arun("netsh interface show interface", 4)
        for line in out.splitlines():
            if "Connected" in line and ("Ethernet" in line or "Wi-Fi" in line):
                return line.split()[-1]
    except Exception:
        pass
    return None

async def get_current_dns(iface: str) -> tuple[str, list[str]]:
    try:
        out = await arun(f'netsh interface ip show dns name="{iface}"')
        if "DHCP enabled" in out:
            return "dhcp", []
        return "static", re.findall(r"\d+\.\d+\.\d+\.\d+", out)
    except Exception:
        return "unknown", []

async def apply_dns(primary: str, secondary: str) -> bool:
    try:
        await arun(f'netsh interface ip set dns name="{S.active_interface}" static {primary}')
        await arun(f'netsh interface ip add dns name="{S.active_interface}" addr={secondary} index=2')
        return True
    except Exception:
        return False

async def reset_to_dhcp() -> bool:
    try:
        await arun(f'netsh interface ip set dns name="{S.active_interface}" source=dhcp')
        return True
    except Exception:
        return False

async def single_ping_ms(ip: str) -> Optional[float]:
    t = time.perf_counter()
    try:
        await arun(f"ping -n 1 -w 1000 {ip}", 3)
        return (time.perf_counter() - t) * 1000
    except Exception:
        return None

async def dns_lookup_ms(ip: str) -> Optional[float]:
    t = time.perf_counter()
    try:
        await arun(f"nslookup example.com {ip}", 3)
        return (time.perf_counter() - t) * 1000
    except Exception:
        return None

async def port_check(host: str, port: int, timeout: float = 3.0) -> bool:
    loop = asyncio.get_event_loop()
    def _check():
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False
    return await loop.run_in_executor(_executor, _check)

async def get_public_ip() -> str:
    """Pure socket HTTP GET — no requests lib."""
    loop = asyncio.get_event_loop()
    def _fetch():
        try:
            s = socket.create_connection(("api.ipify.org", 80), timeout=5)
            s.sendall(b"GET /?format=text HTTP/1.0\r\nHost: api.ipify.org\r\n\r\n")
            data = b""
            while True:
                chunk = s.recv(512)
                if not chunk:
                    break
                data += chunk
            s.close()
            body = data.decode(errors="ignore").split("\r\n\r\n", 1)
            return body[1].strip() if len(body) > 1 else "unknown"
        except Exception:
            return "unavailable"
    return await loop.run_in_executor(_executor, _fetch)

# ─────────────────────────────────────────────────────────────────────────────
#  STARTUP PROBE
# ─────────────────────────────────────────────────────────────────────────────

async def startup_probe():
    set_status("Detecting interface…", T["warn"])
    iface = await get_active_interface()
    if not iface:
        set_status("No interface found", T["err"])
        log("Could not detect active interface", "err")
        return
    S.active_interface = iface
    log(f"Interface: {iface}", "ok")

    mode, dns_list = await get_current_dns(iface)
    if dns_list:
        label = dns_list[0]
        if len(dns_list) > 1:
            label += f"  /  {dns_list[1]}"
    else:
        label = mode.upper()
    set_dns_info(f"Current DNS: {label}")

    admin_str = "  ·  ADMIN ✓" if S.admin else "  ·  limited (no admin)"
    set_status(f"Ready{admin_str}", T["ok"] if S.admin else T["warn"])
    S.ready = True

# ─────────────────────────────────────────────────────────────────────────────
#  DNS ACTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _guard() -> bool:
    if not S.active_interface:
        from tkinter import messagebox
        messagebox.showwarning("Not Ready", "No active network interface detected.")
        return False
    return True

def _no_admin_warn():
    from tkinter import messagebox
    messagebox.showerror("Elevation Required",
        "This action requires Administrator privileges.\n\n"
        "Restart the application as Admin (right-click → Run as administrator).")

async def _do_apply(primary: str, secondary: str):
    if not S.admin:
        ui(_no_admin_warn); return
    pulse(True)
    set_status("Saving previous…", T["warn"])
    S.previous_mode, S.previous_dns = await get_current_dns(S.active_interface)
    set_status("Applying DNS…", T["accent"])
    log(f"Applying  {primary}  /  {secondary}", "act")
    ok = await apply_dns(primary, secondary)
    pulse(False)
    if ok:
        set_status("Applied ✓", T["ok"])
        log(f"DNS → {primary} / {secondary}", "ok")
        set_dns_info(f"Current DNS: {primary}  /  {secondary}")
        ui(_msginfo, "Success", f"DNS applied.\n{primary}  /  {secondary}")
    else:
        set_status("Failed", T["err"])
        log("Failed to apply DNS", "err")
        ui(_msgerr, "Error", "Operation failed. Run as Administrator.")

async def _do_reset():
    if not S.admin:
        ui(_no_admin_warn); return
    pulse(True)
    S.previous_mode, S.previous_dns = await get_current_dns(S.active_interface)
    set_status("Resetting to DHCP…", T["accent"])
    log("Resetting DNS → DHCP", "act")
    ok = await reset_to_dhcp()
    pulse(False)
    if ok:
        set_status("Reset ✓", T["ok"])
        log("DNS reset to DHCP", "ok")
        set_dns_info("Current DNS: DHCP (Automatic)")
        ui(_msginfo, "Done", "DNS reset to automatic.")
    else:
        set_status("Failed", T["err"])
        ui(_msgerr, "Error", "Run as Administrator.")

async def _do_undo():
    if not S.admin:
        ui(_no_admin_warn); return
    if not S.previous_mode:
        log("Nothing to undo", "warn")
        ui(_msgwarn, "Undo", "Nothing to restore."); return
    pulse(True)
    set_status("Restoring…", T["accent"])
    log("Restoring previous DNS", "act")
    if S.previous_mode == "dhcp":
        ok = await reset_to_dhcp()
    else:
        p = S.previous_dns[0]
        s = S.previous_dns[1] if len(S.previous_dns) > 1 else p
        ok = await apply_dns(p, s)
    pulse(False)
    if ok:
        set_status("Restored ✓", T["ok"])
        log("Previous DNS restored", "ok")
        ui(_msginfo, "Undo", "Previous DNS restored.")
    else:
        set_status("Failed", T["err"])
        ui(_msgerr, "Error", "Run as Administrator.")

async def _do_flush():
    if not S.admin:
        ui(_no_admin_warn); return
    pulse(True)
    set_status("Flushing DNS cache…", T["accent"])
    log("Flushing DNS resolver cache", "act")
    try:
        await arun("ipconfig /flushdns")
        set_status("Flushed ✓", T["ok"])
        log("DNS cache flushed", "ok")
        ui(_msginfo, "Done", "DNS resolver cache flushed.")
    except Exception as e:
        set_status("Failed", T["err"])
        log(f"Flush failed: {e}", "err")
    pulse(False)

# ─────────────────────────────────────────────────────────────────────────────
#  SPEED TEST  (parallel)
# ─────────────────────────────────────────────────────────────────────────────

async def _do_speed_test():
    if S.test_running:
        return
    S.test_running = True
    ui(btn_test.config, state="disabled", text="Testing…")
    set_status("Speed test running…", T["warn"])
    log("Parallel DNS speed test — all providers simultaneously", "act")

    async def test_one(name: str, ip: str):
        p, d = await asyncio.gather(single_ping_ms(ip), dns_lookup_ms(ip))
        return name, p, d

    tasks = [test_one(n, ips[0]) for n, ips in DNS_PROVIDERS.items()]
    raw = await asyncio.gather(*tasks)

    results = []
    for name, p, d in raw:
        if p is not None and d is not None:
            score = p * 0.6 + d * 0.4
            results.append((name, round(p), round(d), round(score)))
            log(f"  {name:<32} ping {p:>5.0f}ms  resolve {d:>5.0f}ms", "info")
        else:
            log(f"  {name} — unreachable", "warn")

    S.test_running = False
    ui(btn_test.config, state="normal", text="⚡ Speed Test")

    if not results:
        set_status("No response", T["err"])
        ui(_msgerr, "Error", "No DNS servers responded."); return

    results.sort(key=lambda x: x[3])
    fastest = results[0]
    set_status("Test complete ✓", T["ok"])

    medals = ["🥇", "🥈", "🥉"]
    report = "DNS Speed Test  (milliseconds)\n" + "─" * 46 + "\n"
    for i, r in enumerate(results):
        m = medals[i] if i < 3 else "  "
        report += f"{m}  {r[0]}\n     Ping {r[1]:>4}  Resolve {r[2]:>4}  Score {r[3]:>4}\n"
    report += f"\nFastest: {fastest[0]}\nApply it now?"

    log(f"Fastest: {fastest[0]}", "ok")
    ev = threading.Event()
    answer = [False]
    def ask():
        from tkinter import messagebox
        answer[0] = messagebox.askyesno("Fastest DNS Found", report)
        ev.set()
    ui(ask)
    ev.wait()
    if answer[0]:
        ui(combo.set, fastest[0])
        _refresh_info_card()

# ─────────────────────────────────────────────────────────────────────────────
#  PING MONITOR  (live sparkline)
# ─────────────────────────────────────────────────────────────────────────────

_ping_stop = threading.Event()

async def _do_ping_monitor(host: str):
    S.ping_running = True
    S.ping_history.clear()
    _ping_stop.clear()
    ui(btn_ping.config, text="■ Stop Ping", command=stop_ping_monitor)
    log(f"Ping monitor → {host}  (Ctrl-stop via button)", "act")
    count = 0

    while not _ping_stop.is_set():
        ms = await single_ping_ms(host)
        count += 1
        if ms is not None:
            S.ping_history.append(ms)
            if len(S.ping_history) > 40:
                S.ping_history.pop(0)
            avg = sum(S.ping_history) / len(S.ping_history)
            peak = max(S.ping_history)
            bar = _sparkline(S.ping_history)
            log(f"  #{count:>3}  {host}  {ms:>6.1f}ms  avg {avg:.0f}ms  peak {peak:.0f}ms  {bar}", "info")
        else:
            S.ping_history.append(0)
            log(f"  #{count:>3}  {host}  TIMEOUT", "warn")

        await asyncio.sleep(1.0)

    S.ping_running = False
    ui(btn_ping.config, text="● Ping Monitor", command=open_ping_dialog)
    log("Ping monitor stopped", "warn")

def _sparkline(data: list) -> str:
    if not data:
        return ""
    mn, mx = min(data), max(data)
    rng = mx - mn or 1
    bars = "▁▂▃▄▅▆▇█"
    return "".join(bars[int((v - mn) / rng * 7)] for v in data[-20:])

def stop_ping_monitor():
    _ping_stop.set()

# ─────────────────────────────────────────────────────────────────────────────
#  TRACEROUTE
# ─────────────────────────────────────────────────────────────────────────────

async def _do_traceroute(host: str):
    set_status("Traceroute running…", T["warn"])
    log(f"Traceroute → {host}", "act")
    pulse(True)

    def _stream():
        try:
            proc = subprocess.Popen(
                f"tracert -d -w 500 -h 20 {host}",
                shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line.strip():
                    log(f"  {line}", "info")
            proc.wait()
        except Exception as e:
            log(f"Traceroute error: {e}", "err")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _stream)
    pulse(False)
    set_status("Traceroute done ✓", T["ok"])
    log("Traceroute complete", "ok")

# ─────────────────────────────────────────────────────────────────────────────
#  IP / INTERFACE INFO
# ─────────────────────────────────────────────────────────────────────────────

async def _do_show_info():
    set_status("Gathering info…", T["warn"])
    pulse(True)
    log("── Network Info ─────────────────────────────────", "act")

    # Local info via ipconfig
    try:
        out = await arun("ipconfig /all", 6)
        # Parse relevant block
        in_block = False
        for line in out.splitlines():
            if S.active_interface and S.active_interface.lower() in line.lower():
                in_block = True
            if in_block:
                l = line.strip()
                if l and any(k in l for k in ("IPv4", "IPv6", "Subnet", "Gateway",
                                               "Physical", "DHCP Server", "DNS Servers",
                                               "Lease Obtained", "Lease Expires")):
                    log(f"  {l}", "info")
                if in_block and line == "" and "IPv4" in out:
                    # end of block heuristic
                    pass
    except Exception as e:
        log(f"ipconfig error: {e}", "err")

    # Hostname
    try:
        hostname = socket.gethostname()
        log(f"  Hostname: {hostname}", "info")
    except Exception:
        pass

    # Public IP
    log("  Fetching public IP…", "info")
    pub = await get_public_ip()
    log(f"  Public IP: {pub}", "ok")

    pulse(False)
    set_status("Info loaded ✓", T["ok"])

# ─────────────────────────────────────────────────────────────────────────────
#  PORT CHECK
# ─────────────────────────────────────────────────────────────────────────────

async def _do_port_check(host: str, port: int):
    set_status(f"Checking {host}:{port}…", T["warn"])
    log(f"Port check → {host}:{port}", "act")
    pulse(True)
    ok = await port_check(host, port)
    pulse(False)
    if ok:
        set_status(f"{host}:{port} OPEN ✓", T["ok"])
        log(f"  {host}:{port}  →  OPEN ✓", "ok")
    else:
        set_status(f"{host}:{port} CLOSED", T["err"])
        log(f"  {host}:{port}  →  CLOSED / filtered", "err")

# ─────────────────────────────────────────────────────────────────────────────
#  HOSTS FILE VIEWER
# ─────────────────────────────────────────────────────────────────────────────

def open_hosts_viewer():
    import tkinter as tk
    hosts_path = Path(r"C:\Windows\System32\drivers\etc\hosts")
    win = tk.Toplevel(root)
    win.title("Hosts File")
    win.configure(bg=T["bg"])
    win.geometry("560x420")
    win.resizable(True, True)

    tk.Label(win, text=str(hosts_path), font=("Consolas", 8),
             bg=T["bg"], fg=T["fg2"]).pack(anchor="w", padx=10, pady=(8, 2))

    frame = tk.Frame(win, bg=T["surface"])
    frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))
    sc = tk.Scrollbar(frame)
    sc.pack(side="right", fill="y")
    txt = tk.Text(frame, bg=T["log_bg"], fg=T["fg"],
                  font=("Consolas", 9), relief="flat", bd=0,
                  yscrollcommand=sc.set, padx=8, pady=6)
    txt.pack(fill="both", expand=True)
    sc.config(command=txt.yview)

    try:
        content = hosts_path.read_text(encoding="utf-8", errors="ignore")
        txt.insert("1.0", content)
    except Exception as e:
        txt.insert("1.0", f"Cannot read: {e}")
    txt.config(state="disabled")

    def open_in_notepad():
        subprocess.Popen(f'notepad "{hosts_path}"', shell=True)

    tk.Button(win, text="Open in Notepad", command=open_in_notepad,
              bg=T["accent2"], fg="white", relief="flat", padx=12, pady=6,
              cursor="hand2").pack(pady=(0, 10))

# ─────────────────────────────────────────────────────────────────────────────
#  DIALOG HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _ask_host_port(title: str, host_default="8.8.8.8", port_default="80",
                   show_port=True) -> tuple[Optional[str], Optional[int]]:
    import tkinter as tk
    result = [None, None]
    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=T["bg"])
    win.resizable(False, False)
    win.grab_set()

    pad = {"padx": 12, "pady": 5}

    tk.Label(win, text="Host / IP", bg=T["bg"], fg=T["fg"],
             font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", **pad)
    host_var = tk.StringVar(value=host_default)
    tk.Entry(win, textvariable=host_var, bg=T["surface2"], fg=T["fg"],
             insertbackground=T["fg"], relief="flat", font=("Consolas", 10),
             width=28).grid(row=0, column=1, **pad)

    if show_port:
        tk.Label(win, text="Port", bg=T["bg"], fg=T["fg"],
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", **pad)
        port_var = tk.StringVar(value=port_default)
        tk.Entry(win, textvariable=port_var, bg=T["surface2"], fg=T["fg"],
                 insertbackground=T["fg"], relief="flat", font=("Consolas", 10),
                 width=10).grid(row=1, column=1, sticky="w", **pad)

    def on_ok():
        h = host_var.get().strip()
        result[0] = h if h else None
        if show_port:
            try:
                result[1] = int(port_var.get().strip())
            except Exception:
                result[1] = None
        else:
            result[1] = 0
        win.destroy()

    tk.Button(win, text="Go", command=on_ok,
              bg=T["accent2"], fg="white", relief="flat",
              padx=16, pady=6, cursor="hand2").grid(
                  row=2, column=0, columnspan=2, pady=10)
    win.bind("<Return>", lambda e: on_ok())
    root.wait_window(win)
    return result[0], result[1]

def open_ping_dialog():
    host, _ = _ask_host_port("Ping Monitor", host_default="8.8.8.8", show_port=False)
    if host:
        submit(_do_ping_monitor(host))

def open_traceroute_dialog():
    host, _ = _ask_host_port("Traceroute", host_default="8.8.8.8", show_port=False)
    if host:
        submit(_do_traceroute(host))

def open_port_dialog():
    host, port = _ask_host_port("Port Check", host_default="google.com", port_default="443")
    if host and port:
        submit(_do_port_check(host, port))

# ─────────────────────────────────────────────────────────────────────────────
#  SMALL UI HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _msginfo(t, m):
    from tkinter import messagebox; messagebox.showinfo(t, m)
def _msgerr(t, m):
    from tkinter import messagebox; messagebox.showerror(t, m)
def _msgwarn(t, m):
    from tkinter import messagebox; messagebox.showwarning(t, m)

def _lighten(hex_colour: str, factor: float = 1.16) -> str:
    h = hex_colour.lstrip("#")
    r, g, b_ = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(
        min(255, int(r * factor)),
        min(255, int(g * factor)),
        min(255, int(b_ * factor)),
    )

def flat_btn(parent, text, cmd, bg, fg="#FFFFFF", font=None,
             padx=12, pady=9, width=None):
    kw = {}
    if width:
        kw["width"] = width
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg=fg, activebackground=_lighten(bg),
                  activeforeground=fg, font=font or ("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=padx, pady=pady,
                  cursor="hand2", **kw)
    b.bind("<Enter>", lambda e: b.config(bg=_lighten(bg)))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b

def sep(parent, pady=0):
    tk.Frame(parent, height=1, bg=T["border"]).pack(fill="x", pady=pady)

# ─────────────────────────────────────────────────────────────────────────────
#  THEME SWITCHING  (runtime re-colour)
# ─────────────────────────────────────────────────────────────────────────────

_all_widgets: list = []  # collected after build

def _recolour_widget(w):
    """Best-effort re-theme a single widget."""
    cls = w.winfo_class()
    try:
        if cls in ("Frame", "Toplevel", "Tk"):
            w.config(bg=T["bg"])
        elif cls == "Label":
            w.config(bg=w.master.cget("bg") if w.master else T["bg"])
        elif cls == "Button":
            pass  # buttons rebuilt; skip
        elif cls == "Text":
            w.config(bg=T["log_bg"], fg=T["fg"])
    except Exception:
        pass

def apply_theme(theme_key: str):
    T.clear()
    T.update(THEMES[theme_key])
    S.current_theme = theme_key
    _rebuild_ui()

def _rebuild_ui():
    """Destroy and recreate the entire UI in-place (fast, < 50 ms)."""
    # Save combo selection
    sel = combo.get() if combo.winfo_exists() else list(DNS_PROVIDERS.keys())[0]
    for widget in root.winfo_children():
        widget.destroy()
    _build_ui(restore_combo=sel)
    # Re-apply log tags
    for tag, col in (("ts", T["fg2"]), ("ok", T["ok"]), ("err", T["err"]),
                     ("warn", T["warn"]), ("act", T["accent"]), ("info", T["fg"])):
        log_box.tag_config(tag, foreground=col)
    log(f"Theme → {T['name']}", "act")

# ─────────────────────────────────────────────────────────────────────────────
#  UI BUILD
# ─────────────────────────────────────────────────────────────────────────────
# These are module-level widget refs, assigned during build
root = None   # type: ignore
combo = None  # type: ignore
status_val = None  # type: ignore
dns_info_lbl = None  # type: ignore
indicator = None  # type: ignore
log_box = None  # type: ignore
btn_test = None  # type: ignore
btn_ping = None  # type: ignore
primary_lbl = None  # type: ignore
secondary_lbl = None  # type: ignore

import tkinter as tk
from tkinter import ttk

def _build_ui(restore_combo: str = None):
    global combo, status_val, dns_info_lbl, indicator, log_box
    global btn_test, btn_ping, primary_lbl, secondary_lbl

    bg = T["bg"]
    root.configure(bg=bg)

    # ── ttk style ─────────────────────────────────────────────────────────────
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("DNS.TCombobox",
        fieldbackground=T["surface2"], background=T["surface2"],
        foreground=T["fg"], arrowcolor=T["accent"],
        bordercolor=T["border"], lightcolor=T["border"],
        darkcolor=T["border"], selectbackground=T["accent2"],
        selectforeground="#fff", padding=(10, 7), font=("Segoe UI", 9),
    )
    style.map("DNS.TCombobox",
        fieldbackground=[("readonly", T["surface2"])],
        foreground=[("readonly", T["fg"])],
    )

    # ═══ HEADER ══════════════════════════════════════════════════════════════
    hdr = tk.Frame(root, bg=T["surface"])
    hdr.pack(fill="x")

    hi = tk.Frame(hdr, bg=T["surface"])
    hi.pack(fill="x", padx=18, pady=14)

    tr = tk.Frame(hi, bg=T["surface"])
    tr.pack(fill="x")

    tk.Label(tr, text="DNS", font=("Segoe UI", 20, "bold"),
             bg=T["surface"], fg=T["accent"]).pack(side="left")
    tk.Label(tr, text=" Changer Pro", font=("Segoe UI", 20, "bold"),
             bg=T["surface"], fg=T["fg"]).pack(side="left")
    indicator = tk.Label(tr, text="  ●", font=("Segoe UI", 11),
                         bg=T["surface"], fg=T["border"])
    indicator.pack(side="left", pady=(3, 0))

    # Theme buttons — right side of header
    thm_fr = tk.Frame(tr, bg=T["surface"])
    thm_fr.pack(side="right")
    for key, sym, tip in (("dark", "◑", "Dark"), ("light", "○", "Light"), ("tinted", "◐", "Amber")):
        c = T["accent"] if key == S.current_theme else T["fg2"]
        b = tk.Label(thm_fr, text=sym, font=("Segoe UI", 13),
                     bg=T["surface"], fg=c, cursor="hand2")
        b.pack(side="left", padx=4)
        b.bind("<Button-1>", lambda e, k=key: apply_theme(k))
        b.bind("<Enter>", lambda e, w=b: w.config(fg=T["accent"]))
        b.bind("<Leave>", lambda e, w=b, k=key: w.config(
            fg=T["accent"] if k == S.current_theme else T["fg2"]))

    sr = tk.Frame(hi, bg=T["surface"])
    sr.pack(fill="x", pady=(3, 0))
    tk.Label(sr, text="STATUS", font=("Segoe UI", 7, "bold"),
             bg=T["surface"], fg=T["fg2"]).pack(side="left")
    tk.Label(sr, text="  │  ", bg=T["surface"], fg=T["border"]).pack(side="left")
    status_val = tk.Label(sr, text="Initialising…",
                          font=("Segoe UI", 9), bg=T["surface"], fg=T["warn"])
    status_val.pack(side="left")

    dns_info_lbl = tk.Label(hi, text="", font=("Segoe UI", 8),
                            bg=T["surface"], fg=T["fg2"])
    dns_info_lbl.pack(anchor="w", pady=(2, 0))

    tk.Frame(root, height=1, bg=T["border"]).pack(fill="x")

    # ═══ MAIN BODY ════════════════════════════════════════════════════════════
    body = tk.Frame(root, bg=bg)
    body.pack(fill="both", expand=True)

    # ── LEFT PANEL ────────────────────────────────────────────────────────────
    left = tk.Frame(body, bg=bg)
    left.pack(side="left", fill="both", padx=(16, 8), pady=14)

    # ·· DNS section ··
    _section_label(left, "DNS CONFIGURATION")

    combo = ttk.Combobox(left, values=list(DNS_PROVIDERS.keys()),
                         state="readonly", style="DNS.TCombobox", width=32)
    combo.pack(fill="x", pady=(4, 0))
    combo.current(0)
    if restore_combo and restore_combo in DNS_PROVIDERS:
        combo.set(restore_combo)
    combo.bind("<<ComboboxSelected>>", lambda e: _refresh_info_card())

    tk.Frame(left, height=6, bg=bg).pack()
    apply_b = flat_btn(left, "⟶  Apply Selected DNS",
                       lambda: _guard() and submit(_do_apply(*DNS_PROVIDERS[combo.get()])),
                       T["accent2"], pady=11, font=("Segoe UI", 10, "bold"))
    apply_b.pack(fill="x")

    # Info card
    tk.Frame(left, height=6, bg=bg).pack()
    ic = tk.Frame(left, bg=T["surface2"],
                  highlightthickness=1, highlightbackground=T["border"])
    ic.pack(fill="x")
    ic_inner = tk.Frame(ic, bg=T["surface2"])
    ic_inner.pack(fill="x", padx=10, pady=8)
    tk.Label(ic_inner, text="PRIMARY", font=("Segoe UI", 7, "bold"),
             bg=T["surface2"], fg=T["fg2"]).grid(row=0, column=0, sticky="w")
    primary_lbl = tk.Label(ic_inner, text="", font=("Consolas", 11, "bold"),
                           bg=T["surface2"], fg=T["accent"])
    primary_lbl.grid(row=1, column=0, sticky="w")
    tk.Frame(ic_inner, width=20, bg=T["surface2"]).grid(row=0, column=1, rowspan=2)
    tk.Label(ic_inner, text="SECONDARY", font=("Segoe UI", 7, "bold"),
             bg=T["surface2"], fg=T["fg2"]).grid(row=0, column=2, sticky="w")
    secondary_lbl = tk.Label(ic_inner, text="", font=("Consolas", 11, "bold"),
                              bg=T["surface2"], fg=T["fg2"])
    secondary_lbl.grid(row=1, column=2, sticky="w")

    # ·· DNS utility row ··
    tk.Frame(left, height=8, bg=bg).pack()
    row_dns = tk.Frame(left, bg=bg)
    row_dns.pack(fill="x")

    for text, cmd, fg in (
        ("↩ Undo",       lambda: _guard() and submit(_do_undo()),  T["warn"]),
        ("⟲ DHCP",       lambda: _guard() and submit(_do_reset()), T["err"]),
        ("🗑 Flush",      lambda: _guard() and submit(_do_flush()), T["blue"]),
    ):
        flat_btn(row_dns, text, cmd, T["surface2"], fg=fg, pady=8,
                 padx=6).pack(side="left", fill="both", expand=True, padx=2)

    # ·· Tools section ··
    tk.Frame(left, height=10, bg=bg).pack()
    _section_label(left, "NETWORK TOOLS")

    row_t1 = tk.Frame(left, bg=bg)
    row_t1.pack(fill="x")
    btn_test = flat_btn(row_t1, "⚡ Speed Test", lambda: submit(_do_speed_test()),
                        T["surface2"], fg=T["accent"], pady=8)
    btn_test.pack(side="left", fill="both", expand=True, padx=(0, 2))
    btn_ping = flat_btn(row_t1, "● Ping Monitor", open_ping_dialog,
                        T["surface2"], fg=T["ok"], pady=8)
    btn_ping.pack(side="left", fill="both", expand=True, padx=(2, 0))

    tk.Frame(left, height=4, bg=bg).pack()
    row_t2 = tk.Frame(left, bg=bg)
    row_t2.pack(fill="x")
    flat_btn(row_t2, "⇝ Traceroute", open_traceroute_dialog,
             T["surface2"], fg=T["blue"], pady=8).pack(
                 side="left", fill="both", expand=True, padx=(0, 2))
    flat_btn(row_t2, "⬡ Port Check", open_port_dialog,
             T["surface2"], fg=T["warn"], pady=8).pack(
                 side="left", fill="both", expand=True, padx=(2, 0))

    tk.Frame(left, height=4, bg=bg).pack()
    row_t3 = tk.Frame(left, bg=bg)
    row_t3.pack(fill="x")
    flat_btn(row_t3, "ℹ Interface Info", lambda: submit(_do_show_info()),
             T["surface2"], fg=T["fg2"], pady=8).pack(
                 side="left", fill="both", expand=True, padx=(0, 2))
    flat_btn(row_t3, "📄 Hosts File", open_hosts_viewer,
             T["surface2"], fg=T["fg2"], pady=8).pack(
                 side="left", fill="both", expand=True, padx=(2, 0))

    # ·· Exit ··
    tk.Frame(left, height=10, bg=bg).pack()
    flat_btn(left, "✕  Exit", root.destroy, T["surface2"],
             fg=T["fg2"], pady=7).pack(fill="x")

    # ── DIVIDER ───────────────────────────────────────────────────────────────
    tk.Frame(body, width=1, bg=T["border"]).pack(side="left", fill="y", pady=12)

    # ── RIGHT PANEL — LOG ─────────────────────────────────────────────────────
    right = tk.Frame(body, bg=bg)
    right.pack(side="left", fill="both", expand=True, padx=(8, 16), pady=14)

    lh = tk.Frame(right, bg=bg)
    lh.pack(fill="x", pady=(0, 6))
    tk.Label(lh, text="ACTIVITY LOG", font=("Segoe UI", 7, "bold"),
             bg=bg, fg=T["fg2"]).pack(side="left")
    flat_btn(lh, "clear", lambda: _clear_log(),
             bg, fg=T["fg2"], padx=6, pady=2,
             font=("Segoe UI", 7)).pack(side="right")

    lf = tk.Frame(right, bg=T["surface"],
                  highlightthickness=1, highlightbackground=T["border"])
    lf.pack(fill="both", expand=True)
    sc = tk.Scrollbar(lf, bg=T["surface2"], troughcolor=T["surface"],
                      relief="flat", bd=0)
    sc.pack(side="right", fill="y")
    log_box = tk.Text(lf, bg=T["log_bg"], fg=T["fg"],
                      font=T["mono"], relief="flat", bd=0,
                      padx=10, pady=8, wrap="word",
                      state="disabled", yscrollcommand=sc.set,
                      selectbackground=T["accent2"],
                      insertbackground=T["accent"],
                      spacing1=1, spacing3=1, cursor="arrow")
    log_box.pack(fill="both", expand=True)
    sc.config(command=log_box.yview)

    # Admin badge
    adm_fr = tk.Frame(right, bg=bg)
    adm_fr.pack(fill="x", pady=(6, 0))
    adm_text = "● ADMIN" if S.admin else "○ no admin  (some features limited)"
    adm_col  = T["ok"] if S.admin else T["warn"]
    tk.Label(adm_fr, text=adm_text, font=("Segoe UI", 7, "bold"),
             bg=bg, fg=adm_col).pack(side="left")

    _refresh_info_card()

def _section_label(parent, text: str):
    f = tk.Frame(parent, bg=T["bg"])
    f.pack(fill="x", pady=(0, 4))
    tk.Label(f, text=text, font=("Segoe UI", 7, "bold"),
             bg=T["bg"], fg=T["fg2"]).pack(side="left")
    tk.Frame(f, height=1, bg=T["border"]).pack(side="left", fill="x",
                                                expand=True, padx=(6, 0), pady=3)

def _refresh_info_card():
    if not combo or not combo.winfo_exists():
        return
    name = combo.get()
    p, s = DNS_PROVIDERS.get(name, ("—", "—"))
    primary_lbl.config(text=p)
    secondary_lbl.config(text=s)

def _clear_log():
    log_box.config(state="normal")
    log_box.delete("1.0", "end")
    log_box.config(state="disabled")

# ─────────────────────────────────────────────────────────────────────────────
#  WINDOW GEOMETRY PERSISTENCE
# ─────────────────────────────────────────────────────────────────────────────

def _restore_geometry(prefs: dict):
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    g = prefs.get("geometry")
    if g:
        # Validate it's on-screen
        try:
            parts = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", g)
            if parts:
                w, h, x, y = (int(p) for p in parts.groups())
                x = max(0, min(x, sw - 100))
                y = max(0, min(y, sh - 100))
                root.geometry(f"{w}x{h}+{x}+{y}")
                return
        except Exception:
            pass
    # Default: centred
    w = min(max(760, int(sw * 0.5)), 1200)
    h = min(max(560, int(sh * 0.6)), 900)
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

def _save_geometry_on_exit():
    prefs = load_prefs()
    prefs["geometry"] = root.geometry()
    prefs["theme"] = S.current_theme
    save_prefs(prefs)
    root.destroy()

# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global root

    # ── Elevation check ───────────────────────────────────────────────────────
    S.admin = is_admin()
    if not S.admin:
        # Ask once via a small Tk dialog instead of blocking UAC immediately
        import tkinter as _tk_pre
        from tkinter import messagebox as _mb
        _r = _tk_pre.Tk()
        _r.withdraw()
        ans = _mb.askyesno(
            "DNS Changer Pro — Elevation",
            "Some features (applying DNS, flushing cache) require Administrator privileges.\n\n"
            "Relaunch as Administrator now?\n\n"
            "Choose 'No' to continue in limited mode.",
            icon="warning"
        )
        _r.destroy()
        if ans:
            relaunch_as_admin()
            return   # exits current process

    # ── Load prefs ────────────────────────────────────────────────────────────
    prefs = load_prefs()
    theme_key = prefs.get("theme", "dark")
    if theme_key in THEMES:
        T.clear()
        T.update(THEMES[theme_key])
        S.current_theme = theme_key

    # ── Create root ───────────────────────────────────────────────────────────
    root = tk.Tk()
    root.title("DNS Changer Pro")
    root.configure(bg=T["bg"])
    root.resizable(True, True)
    root.minsize(660, 500)
    root.protocol("WM_DELETE_WINDOW", _save_geometry_on_exit)

    _restore_geometry(prefs)

    # ── Build UI ──────────────────────────────────────────────────────────────
    _build_ui()

    # ── Start async engine ────────────────────────────────────────────────────
    bg_thread = threading.Thread(target=_start_loop, daemon=True)
    bg_thread.start()
    time.sleep(0.04)  # let loop start

    submit(startup_probe())
    log("DNS Changer Pro started" + (" — ADMIN" if S.admin else " — limited mode"), "act")

    root.mainloop()

if __name__ == "__main__":
    # Fix the syntax error from inline import alias
    main()
