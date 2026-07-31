"""
borkDNS  v0.2  — Network Utility Suite
────────────────────────────────────────────────────────────────────────────────
What's new vs v0.1
  • Current active DNS shown in BIG text at the top — always visible
  • UAC / admin prompt is LAZY — only fires when a privileged action is triggered
    (apply / undo / DHCP reset / flush cache). Read-only features work without it.
  • Ping Tool  — dedicated tabbed dialog: live table of per-host results,
    sparkline mini-chart, packet-loss %, min/avg/max summary, Stop/Export
  • DNS Search filter  — type to narrow the provider dropdown in real time
  • Custom DNS entry  — type any primary+secondary IPs, apply directly
  • DNS History  — last 10 applied profiles, one-click re-apply
  • Copy IPs button  — clipboard-copies the currently selected provider's IPs
  • Hosts-file inline edit  — edit & save from the viewer (still needs admin)
  • DNS benchmark table  — speed-test results open in a sortable Toplevel table
  • Tooltip helper  — hover any button to see what it does
────────────────────────────────────────────────────────────────────────────────
stdlib only (tkinter + subprocess + socket + asyncio)
"""
from __future__ import annotations
import asyncio, json, os, re, socket, subprocess, sys, threading, time, ctypes
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Hide console on Windows ───────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

_SW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ─────────────────────────────────────────────────────────────────────────────
#  ELEVATION  — lazy: only called when a privileged action is needed
# ─────────────────────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def relaunch_as_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        " ".join(f'"{a}"' for a in sys.argv), None, 1)
    sys.exit(0)

def _demand_admin() -> bool:
    """
    Called just before any privileged action.
    If already admin → True.
    If not → ask the user once; relaunch or return False (limited mode).
    """
    if S.admin:
        return True
    from tkinter import messagebox
    ans = messagebox.askyesno(
        "Administrator Required",
        "This action requires Administrator privileges.\n\n"
        "Relaunch as Administrator now?\n\n"
        "Choose 'No' to stay in limited (read-only) mode.",
        icon="warning",
    )
    if ans:
        relaunch_as_admin()
    return False

# ─────────────────────────────────────────────────────────────────────────────
#  PREFS
# ─────────────────────────────────────────────────────────────────────────────

PREFS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "borkDNS" / "prefs.json"

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

T = dict(THEMES["dark"])

# ─────────────────────────────────────────────────────────────────────────────
#  DNS PROVIDERS
# ─────────────────────────────────────────────────────────────────────────────

DNS_PROVIDERS: dict[str, tuple[str, str]] = {
    "Cloudflare — Privacy":          ("1.1.1.1",          "1.0.0.1"),
    "Cloudflare — Malware Block":    ("1.1.1.2",          "1.0.0.2"),
    "Cloudflare — Family Safe":      ("1.1.1.3",          "1.0.0.3"),
    "Google Public DNS":             ("8.8.8.8",          "8.8.4.4"),
    "Quad9 — Malware Block":         ("9.9.9.9",          "149.112.112.112"),
    "Quad9 — Unsecured":             ("9.9.9.10",         "149.112.112.10"),
    "OpenDNS Home":                  ("208.67.222.222",   "208.67.220.220"),
    "OpenDNS FamilyShield":          ("208.67.222.123",   "208.67.220.123"),
    "AdGuard DNS — Default":         ("94.140.14.14",     "94.140.15.15"),
    "AdGuard DNS — Family":          ("94.140.14.15",     "94.140.15.16"),
    "AdGuard DNS — Non-filtering":   ("94.140.14.140",    "94.140.14.141"),
    "Mullvad DNS":                   ("194.242.2.2",      "194.242.2.3"),
    "Mullvad DNS — Ad-block":        ("194.242.2.4",      "194.242.2.5"),
    "dns0.eu — Zero":                ("193.110.81.0",     "185.253.5.0"),
    "dns0.eu — Kids":                ("193.110.81.1",     "185.253.5.1"),
    "CleanBrowsing — Security":      ("185.228.168.9",    "185.228.169.9"),
    "CleanBrowsing — Family":        ("185.228.168.168",  "185.228.169.168"),
    "CleanBrowsing — Adult":         ("185.228.168.10",   "185.228.169.11"),
    "Control D — Unfiltered":        ("76.76.2.0",        "76.76.10.0"),
    "NextDNS":                       ("45.90.28.0",       "45.90.30.0"),
    "Alternate DNS":                 ("76.76.19.19",      "76.223.122.150"),
    "DNS.WATCH":                     ("84.200.69.80",     "84.200.70.40"),
    "Comodo Secure DNS":             ("8.26.56.26",       "8.20.247.20"),
    "Verisign Public DNS":           ("64.6.64.6",        "64.6.65.6"),
    "FreeDNS":                       ("37.235.1.174",     "37.235.1.177"),
    "Yandex DNS — Basic":            ("77.88.8.8",        "77.88.8.1"),
    "Yandex DNS — Safe":             ("77.88.8.88",       "77.88.8.2"),
    "Level3 / CenturyLink":          ("4.2.2.1",          "4.2.2.2"),
    "Hurricane Electric":            ("74.82.42.42",      "74.82.42.42"),
}

# ─────────────────────────────────────────────────────────────────────────────
#  APP STATE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AppState:
    active_interface:   Optional[str] = None
    current_dns_mode:   str           = "unknown"
    current_dns_list:   list          = field(default_factory=list)
    previous_dns:       list          = field(default_factory=list)
    previous_mode:      Optional[str] = None
    test_running:       bool          = False
    ping_running:       bool          = False
    ping_history:       list          = field(default_factory=list)
    ready:              bool          = False
    admin:              bool          = False
    current_theme:      str           = "dark"
    wan_ip:             str           = "…"
    dns_apply_history:  list          = field(default_factory=list)  # [(name, p, s), …]

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

# ─────────────────────────────────────────────────────────────────────────────
#  SUBPROCESS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: str, timeout: int = 12) -> str:
    return subprocess.check_output(
        cmd, shell=True, text=True, stderr=subprocess.DEVNULL,
        timeout=timeout, creationflags=_SW,
    )

async def arun(cmd: str, timeout: int = 12) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, lambda: _run(cmd, timeout))

# ─────────────────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────────────────

_log_history: list[tuple[str, str, str]] = []

def log(msg: str, kind: str = "info"):
    ts = time.strftime("%H:%M:%S")
    _log_history.append((ts, msg, kind))
    if len(_log_history) > 500:
        _log_history.pop(0)
    def _w():
        if not (log_box and log_box.winfo_exists()):
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
        out = await arun(f"ping -n 1 -w 2000 {ip}", 4)
        # Parse ms from ping output for accuracy
        m = re.search(r"time[=<](\d+)ms", out, re.IGNORECASE)
        if m:
            return float(m.group(1))
        if "TTL=" in out:
            return (time.perf_counter() - t) * 1000
        return None
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
    loop = asyncio.get_running_loop()
    def _check():
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False
    return await loop.run_in_executor(_executor, _check)

async def get_public_ip() -> str:
    loop = asyncio.get_running_loop()
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
    iface_task = asyncio.ensure_future(get_active_interface())
    wan_task   = asyncio.ensure_future(get_public_ip())

    iface = await iface_task
    if not iface:
        set_status("No interface found", T["err"])
        log("Could not detect active network interface", "err")
    else:
        S.active_interface = iface
        log(f"Interface: {iface}", "ok")

        mode, dns_list = await get_current_dns(iface)
        S.current_dns_mode = mode
        S.current_dns_list = dns_list

        # ── Update the big current-DNS banner ────────────────────────────────
        _update_current_dns_banner(mode, dns_list)

        admin_str = "  ·  ADMIN ✓" if S.admin else "  ·  limited (no admin)"
        set_status(f"Ready{admin_str}", T["ok"] if S.admin else T["warn"])
        S.ready = True

    wan = await wan_task
    S.wan_ip = wan
    log(f"WAN IP: {wan}", "ok")
    def _upd_wan():
        if wan_ip_lbl and wan_ip_lbl.winfo_exists():
            wan_ip_lbl.config(
                text=f"WAN  {wan}",
                fg=T["ok"] if wan not in ("unavailable", "unknown") else T["err"])
    ui(_upd_wan)

def _update_current_dns_banner(mode: str, dns_list: list):
    """Refresh the big current-DNS display in the header."""
    def _do():
        if not (current_dns_primary_lbl and current_dns_primary_lbl.winfo_exists()):
            return
        if mode == "dhcp":
            current_dns_primary_lbl.config(text="DHCP (Auto)", fg=T["ok"])
            current_dns_secondary_lbl.config(text="Automatic", fg=T["fg2"])
            current_dns_name_lbl.config(text="Source: ISP / Router")
        elif dns_list:
            p = dns_list[0]
            s = dns_list[1] if len(dns_list) > 1 else "—"
            current_dns_primary_lbl.config(text=p, fg=T["accent"])
            current_dns_secondary_lbl.config(text=s, fg=T["fg2"])
            # Try to match to a known provider
            name = _identify_dns(p, s)
            current_dns_name_lbl.config(text=name)
        else:
            current_dns_primary_lbl.config(text="Unknown", fg=T["warn"])
            current_dns_secondary_lbl.config(text="—", fg=T["fg2"])
            current_dns_name_lbl.config(text="")
    ui(_do)

def _identify_dns(primary: str, secondary: str) -> str:
    """Try to reverse-match IPs to a known provider name."""
    for name, (p, s) in DNS_PROVIDERS.items():
        if p == primary:
            return f"↳ {name}"
    return "↳ Custom / Unknown"

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
    messagebox.showerror(
        "Elevation Required",
        "This action requires Administrator privileges.\n\n"
        "Restart as Administrator (right-click → Run as administrator).")

async def _do_apply(primary: str, secondary: str, name: str = "Custom"):
    if not _demand_admin():
        return
    pulse(True)
    set_status("Saving previous…", T["warn"])
    S.previous_mode, S.previous_dns = await get_current_dns(S.active_interface)
    set_status("Applying DNS…", T["accent"])
    log(f"Applying  {primary}  /  {secondary}", "act")
    ok = await apply_dns(primary, secondary)
    pulse(False)
    if ok:
        S.current_dns_mode = "static"
        S.current_dns_list = [primary, secondary]
        _update_current_dns_banner("static", [primary, secondary])
        set_status("Applied ✓", T["ok"])
        log(f"DNS → {primary} / {secondary}  [{name}]", "ok")
        # History
        _add_to_history(name, primary, secondary)
        prefs = load_prefs()
        prefs["last_provider"] = combo.get() if combo and combo.winfo_exists() else ""
        save_prefs(prefs)
        ui(_msginfo, "Success", f"DNS applied.\n{primary}  /  {secondary}")
    else:
        set_status("Failed", T["err"])
        log("Failed to apply DNS", "err")
        ui(_msgerr, "Error", "Operation failed. Run as Administrator.")

async def _do_reset():
    if not _demand_admin():
        return
    pulse(True)
    S.previous_mode, S.previous_dns = await get_current_dns(S.active_interface)
    set_status("Resetting to DHCP…", T["accent"])
    log("Resetting DNS → DHCP", "act")
    ok = await reset_to_dhcp()
    pulse(False)
    if ok:
        S.current_dns_mode = "dhcp"
        S.current_dns_list = []
        _update_current_dns_banner("dhcp", [])
        set_status("Reset ✓", T["ok"])
        log("DNS reset to DHCP", "ok")
        ui(_msginfo, "Done", "DNS reset to automatic (DHCP).")
    else:
        set_status("Failed", T["err"])
        ui(_msgerr, "Error", "Run as Administrator.")

async def _do_undo():
    if not _demand_admin():
        return
    if not S.previous_mode:
        log("Nothing to undo", "warn")
        ui(_msgwarn, "Undo", "Nothing to restore."); return
    pulse(True)
    set_status("Restoring…", T["accent"])
    log("Restoring previous DNS", "act")
    if S.previous_mode == "dhcp":
        ok = await reset_to_dhcp()
        if ok:
            S.current_dns_mode = "dhcp"; S.current_dns_list = []
            _update_current_dns_banner("dhcp", [])
    else:
        p = S.previous_dns[0]
        s = S.previous_dns[1] if len(S.previous_dns) > 1 else p
        ok = await apply_dns(p, s)
        if ok:
            S.current_dns_mode = "static"; S.current_dns_list = [p, s]
            _update_current_dns_banner("static", [p, s])
    pulse(False)
    if ok:
        set_status("Restored ✓", T["ok"])
        log("Previous DNS restored", "ok")
        ui(_msginfo, "Undo", "Previous DNS restored.")
    else:
        set_status("Failed", T["err"])
        ui(_msgerr, "Error", "Run as Administrator.")

async def _do_flush():
    if not _demand_admin():
        return
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
#  DNS HISTORY
# ─────────────────────────────────────────────────────────────────────────────

def _add_to_history(name: str, primary: str, secondary: str):
    entry = {"name": name, "primary": primary, "secondary": secondary,
             "ts": time.strftime("%d %b %H:%M")}
    S.dns_apply_history = [e for e in S.dns_apply_history
                           if not (e["primary"] == primary and e["secondary"] == secondary)]
    S.dns_apply_history.insert(0, entry)
    S.dns_apply_history = S.dns_apply_history[:10]
    # Persist
    prefs = load_prefs()
    prefs["dns_history"] = S.dns_apply_history
    save_prefs(prefs)

def open_history_dialog():
    if not S.dns_apply_history:
        from tkinter import messagebox
        messagebox.showinfo("DNS History", "No DNS changes recorded yet.")
        return

    win = tk.Toplevel(root)
    win.title("DNS Apply History")
    win.configure(bg=T["bg"])
    win.geometry("520x340")
    win.resizable(True, True)
    win.grab_set()
    _center(win, 520, 340)

    tk.Label(win, text="RECENT DNS PROFILES",
             font=("Segoe UI", 8, "bold"), bg=T["bg"], fg=T["fg2"]).pack(
             anchor="w", padx=14, pady=(12, 4))

    frame = tk.Frame(win, bg=T["surface"],
                     highlightthickness=1, highlightbackground=T["border"])
    frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))

    cols = ("Time", "Name", "Primary", "Secondary")
    tv = ttk.Treeview(frame, columns=cols, show="headings",
                      style="History.Treeview", height=10)
    tv.heading("Time",      text="Applied")
    tv.heading("Name",      text="Profile")
    tv.heading("Primary",   text="Primary DNS")
    tv.heading("Secondary", text="Secondary DNS")
    tv.column("Time",      width=90,  anchor="w")
    tv.column("Name",      width=160, anchor="w")
    tv.column("Primary",   width=110, anchor="center")
    tv.column("Secondary", width=110, anchor="center")

    sc = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sc.set)
    sc.pack(side="right", fill="y")
    tv.pack(fill="both", expand=True)

    for e in S.dns_apply_history:
        tv.insert("", "end", values=(e["ts"], e["name"], e["primary"], e["secondary"]))

    style = ttk.Style()
    style.configure("History.Treeview",
        background=T["log_bg"], foreground=T["fg"],
        fieldbackground=T["log_bg"], rowheight=24,
        font=("Consolas", 9))
    style.configure("History.Treeview.Heading",
        background=T["surface2"], foreground=T["fg2"],
        font=("Segoe UI", 8, "bold"))

    btn_row = tk.Frame(win, bg=T["bg"])
    btn_row.pack(fill="x", padx=14, pady=(0, 10))

    def re_apply():
        sel = tv.selection()
        if not sel:
            return
        idx = tv.index(sel[0])
        e = S.dns_apply_history[idx]
        win.destroy()
        if _guard():
            submit(_do_apply(e["primary"], e["secondary"], e["name"]))

    flat_btn(btn_row, "⟶ Re-apply Selected", re_apply,
             T["accent2"], pady=7).pack(side="left")
    flat_btn(btn_row, "Close", win.destroy,
             T["surface2"], fg=T["fg2"], pady=7).pack(side="right")

# ─────────────────────────────────────────────────────────────────────────────
#  SPEED TEST  (parallel, results in sortable table)
# ─────────────────────────────────────────────────────────────────────────────

async def _do_speed_test():
    if S.test_running:
        return
    S.test_running = True
    ui(btn_test.config, state="disabled", text="Testing…")
    set_status("Speed test running…", T["warn"])
    log("── DNS Speed Test (parallel) ─────────────────────", "act")

    async def test_one(name: str, ip: str):
        if not ip or not ip.strip():
            return name, None, None
        p, d = await asyncio.gather(single_ping_ms(ip), dns_lookup_ms(ip))
        return name, p, d

    tasks = [test_one(n, ips[0]) for n, ips in DNS_PROVIDERS.items()]
    raw = await asyncio.gather(*tasks)

    results = []
    for name, p, d in raw:
        if p is not None and d is not None:
            score = p * 0.6 + d * 0.4
            results.append((name, round(p), round(d), round(score)))
        else:
            log(f"  ✗ {name:<34} unreachable", "warn")

    S.test_running = False
    ui(btn_test.config, state="normal", text="⚡ Speed Test")

    if not results:
        set_status("No response", T["err"])
        ui(_msgerr, "Error", "No DNS servers responded.")
        return

    results.sort(key=lambda x: x[3])
    fastest = results[0]
    set_status(f"Fastest: {fastest[0].split('—')[0].strip()} ✓", T["ok"])
    log(f"  → Fastest: {fastest[0]}  ({fastest[3]}ms score)", "ok")

    # Open sortable results table
    ui(_open_speed_results_table, results, fastest)

def _open_speed_results_table(results: list, fastest: tuple):
    win = tk.Toplevel(root)
    win.title("DNS Speed Test Results")
    win.configure(bg=T["bg"])
    win.geometry("620x480")
    win.resizable(True, True)
    _center(win, 620, 480)

    tk.Label(win, text="DNS SPEED TEST RESULTS",
             font=("Segoe UI", 8, "bold"), bg=T["bg"], fg=T["fg2"]).pack(
             anchor="w", padx=14, pady=(12, 2))
    tk.Label(win, text=f"  🥇 Fastest: {fastest[0]}  —  {fastest[3]}ms score",
             font=("Segoe UI", 9), bg=T["bg"], fg=T["ok"]).pack(anchor="w", padx=14, pady=(0, 6))

    frame = tk.Frame(win, bg=T["surface"],
                     highlightthickness=1, highlightbackground=T["border"])
    frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))

    cols = ("#", "Provider", "Ping (ms)", "Resolve (ms)", "Score (ms)")
    tv = ttk.Treeview(frame, columns=cols, show="headings",
                      style="Speed.Treeview", height=16)
    medals = ["🥇", "🥈", "🥉"]
    for c, w in zip(cols, (28, 240, 70, 90, 70)):
        tv.heading(c, text=c, command=lambda col=c: _sort_tree(tv, col, results_var))
        tv.column(c, width=w, anchor="center" if c != "Provider" else "w")

    results_var = [list(results)]  # mutable for sort callback

    sc = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sc.set)
    sc.pack(side="right", fill="y")
    tv.pack(fill="both", expand=True)

    style = ttk.Style()
    style.configure("Speed.Treeview",
        background=T["log_bg"], foreground=T["fg"],
        fieldbackground=T["log_bg"], rowheight=22,
        font=("Consolas", 9))
    style.configure("Speed.Treeview.Heading",
        background=T["surface2"], foreground=T["fg2"],
        font=("Segoe UI", 8, "bold"))
    style.map("Speed.Treeview", background=[("selected", T["accent2"])])

    def _populate(data):
        tv.delete(*tv.get_children())
        for i, r in enumerate(data):
            m = medals[i] if i < 3 else str(i + 1)
            tv.insert("", "end", values=(m, r[0], r[1], r[2], r[3]))

    _populate(results)

    def _sort_tree(tree, col, data_ref):
        col_map = {"#": None, "Provider": 0, "Ping (ms)": 1,
                   "Resolve (ms)": 2, "Score (ms)": 3}
        idx = col_map.get(col)
        if idx is None:
            return
        data_ref[0] = sorted(data_ref[0], key=lambda r: r[idx])
        _populate(data_ref[0])

    btn_row = tk.Frame(win, bg=T["bg"])
    btn_row.pack(fill="x", padx=14, pady=(0, 10))

    def apply_selected():
        sel = tv.selection()
        if not sel:
            return
        vals = tv.item(sel[0], "values")
        name = vals[1]
        if name in DNS_PROVIDERS:
            win.destroy()
            if _guard():
                p, s = DNS_PROVIDERS[name]
                ui(combo.set, name)
                _refresh_info_card()
                submit(_do_apply(p, s, name))

    flat_btn(btn_row, "⟶ Apply Selected", apply_selected,
             T["accent2"], pady=7).pack(side="left")
    flat_btn(btn_row, "Close", win.destroy,
             T["surface2"], fg=T["fg2"], pady=7).pack(side="right")

# ─────────────────────────────────────────────────────────────────────────────
#  PING TOOL  — dedicated dialog with live table + sparkline
# ─────────────────────────────────────────────────────────────────────────────

_ping_stop = threading.Event()
_ping_tasks: dict[str, asyncio.Task] = {}

class PingRow:
    """Mutable state for one host in the ping table."""
    def __init__(self, host: str):
        self.host = host
        self.sent = 0
        self.recv = 0
        self.history: list[float] = []
        self.last: Optional[float] = None
        self.min_ms: Optional[float] = None
        self.max_ms: Optional[float] = None

    @property
    def loss_pct(self) -> float:
        return 0.0 if self.sent == 0 else 100.0 * (self.sent - self.recv) / self.sent

    @property
    def avg_ms(self) -> Optional[float]:
        return (sum(self.history) / len(self.history)) if self.history else None

    def add(self, ms: Optional[float]):
        self.sent += 1
        if ms is not None:
            self.recv += 1
            self.history.append(ms)
            if len(self.history) > 60:
                self.history.pop(0)
            self.last = ms
            self.min_ms = min(self.history)
            self.max_ms = max(self.history)

def open_ping_tool():
    """Open the full Ping Tool dialog."""
    win = tk.Toplevel(root)
    win.title("Ping Tool")
    win.configure(bg=T["bg"])
    win.geometry("700x480")
    win.resizable(True, True)
    _center(win, 700, 480)

    # ── host entry row ─────────────────────────────────────────────────────
    top = tk.Frame(win, bg=T["bg"])
    top.pack(fill="x", padx=14, pady=(12, 6))

    tk.Label(top, text="PING TOOL", font=("Segoe UI", 8, "bold"),
             bg=T["bg"], fg=T["fg2"]).pack(side="left")

    host_var = tk.StringVar(value="8.8.8.8")
    entry = tk.Entry(top, textvariable=host_var, bg=T["surface2"], fg=T["fg"],
                     insertbackground=T["fg"], relief="flat",
                     font=("Consolas", 10), width=20,
                     highlightthickness=1, highlightbackground=T["border"],
                     highlightcolor=T["accent"])
    entry.pack(side="left", padx=(12, 4))

    ping_rows: dict[str, PingRow] = {}
    running = [False]
    stop_ev = threading.Event()
    active_tasks: list = []

    # ── results table ──────────────────────────────────────────────────────
    tframe = tk.Frame(win, bg=T["surface"],
                      highlightthickness=1, highlightbackground=T["border"])
    tframe.pack(fill="both", expand=True, padx=14, pady=(0, 0))

    cols = ("Host", "Sent", "Recv", "Loss%", "Last ms", "Min", "Avg", "Max", "Sparkline")
    tv = ttk.Treeview(tframe, columns=cols, show="headings",
                      style="Ping.Treeview", height=12)
    for c, w in zip(cols, (130, 50, 50, 55, 70, 55, 55, 55, 220)):
        tv.heading(c, text=c)
        tv.column(c, width=w, anchor="center" if c != "Host" and c != "Sparkline" else "w")

    psc = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=psc.set)
    psc.pack(side="right", fill="y")
    tv.pack(fill="both", expand=True)

    style = ttk.Style()
    style.configure("Ping.Treeview",
        background=T["log_bg"], foreground=T["fg"],
        fieldbackground=T["log_bg"], rowheight=22,
        font=("Consolas", 9))
    style.configure("Ping.Treeview.Heading",
        background=T["surface2"], foreground=T["fg2"],
        font=("Segoe UI", 8, "bold"))
    style.map("Ping.Treeview",
        background=[("selected", T["accent2"])],
        foreground=[("selected", "#fff")])

    tv.tag_configure("good",    foreground=T["ok"])
    tv.tag_configure("warn",    foreground=T["warn"])
    tv.tag_configure("bad",     foreground=T["err"])
    tv.tag_configure("timeout", foreground=T["fg2"])

    # ── status bar ─────────────────────────────────────────────────────────
    sbar = tk.Frame(win, bg=T["surface2"])
    sbar.pack(fill="x")
    sbar_lbl = tk.Label(sbar, text="Idle", font=("Segoe UI", 8),
                        bg=T["surface2"], fg=T["fg2"])
    sbar_lbl.pack(side="left", padx=10, pady=4)

    # ── button row ─────────────────────────────────────────────────────────
    brow = tk.Frame(win, bg=T["bg"])
    brow.pack(fill="x", padx=14, pady=(6, 10))

    def _row_tag(row: PingRow) -> str:
        if row.last is None:
            return "timeout"
        if row.last < 80:
            return "good"
        if row.last < 200:
            return "warn"
        return "bad"

    def _refresh_table():
        for host, row in ping_rows.items():
            spark = _sparkline(row.history[-30:])
            vals = (
                row.host,
                row.sent,
                row.recv,
                f"{row.loss_pct:.0f}%",
                f"{row.last:.0f}" if row.last is not None else "—",
                f"{row.min_ms:.0f}" if row.min_ms is not None else "—",
                f"{row.avg_ms:.0f}" if row.avg_ms is not None else "—",
                f"{row.max_ms:.0f}" if row.max_ms is not None else "—",
                spark,
            )
            tag = _row_tag(row)
            if tv.exists(host):
                tv.item(host, values=vals, tags=(tag,))
            else:
                tv.insert("", "end", iid=host, values=vals, tags=(tag,))

    async def _ping_loop(host: str, row: PingRow):
        while not stop_ev.is_set():
            ms = await single_ping_ms(host)
            row.add(ms)
            ui(_refresh_table)
            if running[0]:
                n = sum(r.sent for r in ping_rows.values())
                ui(sbar_lbl.config, text=f"Pinging {len(ping_rows)} host(s) — {n} total sent")
            await asyncio.sleep(1.0)

    def start_ping():
        host = host_var.get().strip()
        if not host:
            return
        if host not in ping_rows:
            ping_rows[host] = PingRow(host)
        stop_ev.clear()
        running[0] = True
        t = submit(_ping_loop(host, ping_rows[host]))
        active_tasks.append(t)
        btn_start.config(state="disabled")
        btn_stop.config(state="normal")
        sbar_lbl.config(text=f"Pinging {host}…", fg=T["warn"])

    def stop_ping():
        stop_ev.set()
        running[0] = False
        btn_start.config(state="normal")
        btn_stop.config(state="disabled")
        sbar_lbl.config(text="Stopped", fg=T["fg2"])

    def clear_hosts():
        stop_ping()
        ping_rows.clear()
        tv.delete(*tv.get_children())
        sbar_lbl.config(text="Idle")

    def export_results():
        lines = ["Host,Sent,Recv,Loss%,Min,Avg,Max"]
        for row in ping_rows.values():
            lines.append(
                f"{row.host},{row.sent},{row.recv},{row.loss_pct:.1f},"
                f"{row.min_ms or ''},{row.avg_ms or ''},{row.max_ms or ''}")
        text = "\n".join(lines)
        win.clipboard_clear()
        win.clipboard_append(text)
        sbar_lbl.config(text="Results copied to clipboard ✓", fg=T["ok"])

    def remove_selected():
        sel = tv.selection()
        for iid in sel:
            tv.delete(iid)
            ping_rows.pop(iid, None)

    btn_start = flat_btn(brow, "▶ Add & Ping", start_ping,
                         T["ok"], fg="#000", pady=7)
    btn_start.pack(side="left", padx=(0, 4))
    btn_stop = flat_btn(brow, "■ Stop", stop_ping,
                        T["err"], pady=7)
    btn_stop.config(state="disabled")
    btn_stop.pack(side="left", padx=(0, 4))
    flat_btn(brow, "✕ Remove", remove_selected,
             T["surface2"], fg=T["warn"], pady=7).pack(side="left", padx=(0, 4))
    flat_btn(brow, "🗑 Clear All", clear_hosts,
             T["surface2"], fg=T["fg2"], pady=7).pack(side="left", padx=(0, 4))
    flat_btn(brow, "📋 Export CSV", export_results,
             T["surface2"], fg=T["blue"], pady=7).pack(side="left")
    flat_btn(brow, "Close", win.destroy,
             T["surface2"], fg=T["fg2"], pady=7).pack(side="right")

    entry.bind("<Return>", lambda e: start_ping())

    def _on_close():
        stop_ev.set()
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", _on_close)

# ─────────────────────────────────────────────────────────────────────────────
#  TRACEROUTE
# ─────────────────────────────────────────────────────────────────────────────

_traceroute_proc: Optional[subprocess.Popen] = None
_traceroute_btn_ref = None

async def _do_traceroute(host: str):
    global _traceroute_proc
    set_status("Traceroute running…", T["warn"])
    log(f"Traceroute → {host}", "act")
    pulse(True)

    def _set_stop():
        if _traceroute_btn_ref and _traceroute_btn_ref.winfo_exists():
            _traceroute_btn_ref.config(text="■ Stop Trace", command=_cancel_traceroute)
    ui(_set_stop)

    def _stream():
        global _traceroute_proc
        try:
            _traceroute_proc = subprocess.Popen(
                f"tracert -d -w 500 -h 20 {host}",
                shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, creationflags=_SW)
            for line in _traceroute_proc.stdout:
                line = line.rstrip()
                if line.strip():
                    log(f"  {line}", "info")
            _traceroute_proc.wait()
        except Exception as e:
            log(f"Traceroute error: {e}", "err")
        finally:
            _traceroute_proc = None

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _stream)
    pulse(False)

    def _set_start():
        if _traceroute_btn_ref and _traceroute_btn_ref.winfo_exists():
            _traceroute_btn_ref.config(text="⇝ Traceroute", command=open_traceroute_dialog)
    ui(_set_start)
    set_status("Traceroute done ✓", T["ok"])
    log("Traceroute complete", "ok")

def _cancel_traceroute():
    global _traceroute_proc
    if _traceroute_proc:
        try:
            _traceroute_proc.kill()
        except Exception:
            pass
        log("Traceroute cancelled", "warn")

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
#  IP / INTERFACE INFO
# ─────────────────────────────────────────────────────────────────────────────

async def _do_show_info():
    set_status("Gathering info…", T["warn"])
    pulse(True)
    log("── Network Info ─────────────────────────────────", "act")
    try:
        hostname = socket.gethostname()
        log(f"  Hostname       : {hostname}", "info")
    except Exception:
        pass
    try:
        out = await arun("ipconfig /all", 6)
        blocks = re.split(r"\r?\n\r?\n", out)
        for block in blocks:
            if S.active_interface and S.active_interface.lower() in block.lower():
                for line in block.splitlines():
                    l = line.strip()
                    if l and any(k in l for k in (
                        "IPv4", "IPv6", "Subnet", "Default Gateway",
                        "Physical Address", "DHCP Server", "DNS Servers",
                        "Lease Obtained", "Lease Expires", "DHCP Enabled",
                    )):
                        log(f"  {l}", "info")
                break
    except Exception as e:
        log(f"  ipconfig error: {e}", "err")

    if S.wan_ip and S.wan_ip not in ("…", "unavailable", "unknown"):
        log(f"  Public (WAN) IP: {S.wan_ip}", "ok")
    else:
        pub = await get_public_ip()
        S.wan_ip = pub
        log(f"  Public (WAN) IP: {pub}", "ok")
        def _upd():
            if wan_ip_lbl and wan_ip_lbl.winfo_exists():
                wan_ip_lbl.config(
                    text=f"WAN  {pub}",
                    fg=T["ok"] if pub not in ("unavailable","unknown") else T["err"])
        ui(_upd)

    pulse(False)
    set_status("Info loaded ✓", T["ok"])

# ─────────────────────────────────────────────────────────────────────────────
#  HOSTS FILE VIEWER  (with inline edit + save)
# ─────────────────────────────────────────────────────────────────────────────

def open_hosts_viewer():
    hosts_path = Path(r"C:\Windows\System32\drivers\etc\hosts")
    win = tk.Toplevel(root)
    win.title("Hosts File")
    win.configure(bg=T["bg"])
    win.geometry("620x480")
    win.resizable(True, True)
    _center(win, 620, 480)

    hdr_row = tk.Frame(win, bg=T["bg"])
    hdr_row.pack(fill="x", padx=12, pady=(10, 3))
    tk.Label(hdr_row, text=str(hosts_path), font=("Consolas", 8),
             bg=T["bg"], fg=T["fg2"]).pack(side="left")

    frame = tk.Frame(win, bg=T["surface"],
                     highlightthickness=1, highlightbackground=T["border"])
    frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
    sc = tk.Scrollbar(frame, bg=T["surface2"], troughcolor=T["surface"],
                      relief="flat", bd=0)
    sc.pack(side="right", fill="y")
    txt = tk.Text(frame, bg=T["log_bg"], fg=T["fg"],
                  font=("Consolas", 9), relief="flat", bd=0,
                  yscrollcommand=sc.set, padx=10, pady=8,
                  selectbackground=T["accent2"])
    txt.pack(fill="both", expand=True)
    sc.config(command=txt.yview)

    txt.tag_config("comment", foreground=T["fg2"])
    txt.tag_config("entry",   foreground=T["accent"])

    try:
        content = hosts_path.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines(keepends=True):
            stripped = line.lstrip()
            if stripped.startswith("#") or not stripped.strip():
                txt.insert("end", line, "comment")
            elif stripped[0].isdigit():
                txt.insert("end", line, "entry")
            else:
                txt.insert("end", line)
    except Exception as e:
        txt.insert("end", f"Cannot read hosts file:\n{e}")

    txt.config(state="disabled")
    is_editing = [False]

    btn_row = tk.Frame(win, bg=T["bg"])
    btn_row.pack(fill="x", padx=12, pady=(0, 10))

    edit_btn = flat_btn(btn_row, "✏ Edit", None, T["surface2"], fg=T["warn"], pady=7)
    save_btn = flat_btn(btn_row, "💾 Save", None, T["ok"], fg="#000", pady=7)
    save_btn.pack_forget()  # hidden until editing

    def toggle_edit():
        if not _demand_admin():
            return
        txt.config(state="normal")
        is_editing[0] = True
        edit_btn.pack_forget()
        save_btn.pack(side="left", padx=(0, 6))

    def save_hosts():
        new_content = txt.get("1.0", "end-1c")
        try:
            hosts_path.write_text(new_content, encoding="utf-8")
            is_editing[0] = False
            txt.config(state="disabled")
            save_btn.pack_forget()
            edit_btn.pack(side="left", padx=(0, 6))
            from tkinter import messagebox
            messagebox.showinfo("Hosts File", "Hosts file saved successfully.")
        except PermissionError:
            from tkinter import messagebox
            messagebox.showerror("Permission Denied",
                "Could not save. Run the app as Administrator.")
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error", str(e))

    edit_btn.config(command=toggle_edit)
    save_btn.config(command=save_hosts)
    edit_btn.pack(side="left", padx=(0, 6))
    flat_btn(btn_row, "Open in Notepad", lambda: subprocess.Popen(
        f'notepad "{hosts_path}"', shell=True, creationflags=_SW),
        T["accent2"], pady=7).pack(side="left")
    flat_btn(btn_row, "Close", win.destroy,
             T["surface2"], fg=T["fg2"], pady=7).pack(side="right")

# ─────────────────────────────────────────────────────────────────────────────
#  DIALOG HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _center(win, w, h):
    root.update_idletasks()
    rx = root.winfo_x() + (root.winfo_width()  - w) // 2
    ry = root.winfo_y() + (root.winfo_height() - h) // 2
    win.geometry(f"{w}x{h}+{rx}+{ry}")

def _ask_host_port(title: str, host_default="8.8.8.8", port_default="80",
                   show_port=True) -> tuple[Optional[str], Optional[int]]:
    result = [None, None]
    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=T["bg"])
    win.resizable(False, False)
    win.grab_set()
    ww, wh = 320, 130 if show_port else 100
    _center(win, ww, wh)

    inner = tk.Frame(win, bg=T["bg"])
    inner.pack(fill="both", expand=True, padx=14, pady=12)

    tk.Label(inner, text="Host / IP", bg=T["bg"], fg=T["fg"],
             font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=3)
    host_var = tk.StringVar(value=host_default)
    host_entry = tk.Entry(inner, textvariable=host_var, bg=T["surface2"], fg=T["fg"],
                          insertbackground=T["fg"], relief="flat", font=("Consolas", 10),
                          width=24, highlightthickness=1,
                          highlightbackground=T["border"],
                          highlightcolor=T["accent"])
    host_entry.grid(row=0, column=1, padx=(8, 0), pady=3, sticky="ew")
    host_entry.focus_set()
    host_entry.select_range(0, "end")

    if show_port:
        tk.Label(inner, text="Port", bg=T["bg"], fg=T["fg"],
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=3)
        port_var = tk.StringVar(value=port_default)
        tk.Entry(inner, textvariable=port_var, bg=T["surface2"], fg=T["fg"],
                 insertbackground=T["fg"], relief="flat", font=("Consolas", 10),
                 width=10, highlightthickness=1,
                 highlightbackground=T["border"],
                 highlightcolor=T["accent"]).grid(row=1, column=1, padx=(8, 0),
                                                   pady=3, sticky="w")

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

    btn_r = 2 if show_port else 1
    flat_btn(inner, "Go", on_ok, T["accent2"], pady=6,
             font=("Segoe UI", 9, "bold")).grid(
                 row=btn_r, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    win.bind("<Return>", lambda e: on_ok())
    win.bind("<Escape>", lambda e: win.destroy())
    root.wait_window(win)
    return result[0], result[1]

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
        min(255, int(b_ * factor)))

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

def _add_tooltip(widget, text: str):
    """Simple hover tooltip."""
    tip = [None]
    def show(e):
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        t = tk.Toplevel(widget)
        t.wm_overrideredirect(True)
        t.wm_geometry(f"+{x}+{y}")
        tk.Label(t, text=text, font=("Segoe UI", 8),
                 bg=T["surface2"], fg=T["fg"],
                 relief="flat", bd=0, padx=8, pady=4,
                 highlightthickness=1, highlightbackground=T["border"]).pack()
        tip[0] = t
    def hide(e):
        if tip[0]:
            tip[0].destroy()
            tip[0] = None
    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")

def _sparkline(data: list) -> str:
    if not data:
        return ""
    mn, mx = min(data), max(data)
    rng = mx - mn or 1
    bars = "▁▂▃▄▅▆▇█"
    return "".join(bars[int((v - mn) / rng * 7)] for v in data[-30:])

# ─────────────────────────────────────────────────────────────────────────────
#  THEME SWITCHING
# ─────────────────────────────────────────────────────────────────────────────

def apply_theme(theme_key: str):
    T.clear()
    T.update(THEMES[theme_key])
    S.current_theme = theme_key
    _rebuild_ui()

def _rebuild_ui():
    sel = combo.get() if (combo is not None and combo.winfo_exists()) else list(DNS_PROVIDERS.keys())[0]
    for widget in root.winfo_children():
        widget.destroy()
    _build_ui(restore_combo=sel)
    _restore_log_history()
    if wan_ip_lbl and wan_ip_lbl.winfo_exists() and S.wan_ip not in ("…",):
        ok_col = T["ok"] if S.wan_ip not in ("unavailable", "unknown") else T["err"]
        wan_ip_lbl.config(text=f"WAN  {S.wan_ip}", fg=ok_col)
    # Restore current DNS banner after rebuild
    _update_current_dns_banner(S.current_dns_mode, S.current_dns_list)
    log(f"Theme → {T['name']}", "act")

def _restore_log_history():
    for tag, col in (("ts", T["fg2"]), ("ok", T["ok"]), ("err", T["err"]),
                     ("warn", T["warn"]), ("act", T["accent"]), ("info", T["fg"])):
        log_box.tag_config(tag, foreground=col)
    if not _log_history:
        return
    log_box.config(state="normal")
    for ts, msg, kind in _log_history:
        log_box.insert("end", f"[{ts}] ", "ts")
        log_box.insert("end", f"{msg}\n", kind)
    log_box.see("end")
    log_box.config(state="disabled")

# ─────────────────────────────────────────────────────────────────────────────
#  CLIPBOARD HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _copy_selected_dns():
    name = combo.get() if combo and combo.winfo_exists() else ""
    if name not in DNS_PROVIDERS:
        return
    p, s = DNS_PROVIDERS[name]
    root.clipboard_clear()
    root.clipboard_append(f"{p}, {s}")
    log(f"Copied: {p}, {s}", "act")
    set_status("IPs copied to clipboard ✓", T["ok"])

# ─────────────────────────────────────────────────────────────────────────────
#  UI BUILD
# ─────────────────────────────────────────────────────────────────────────────

root = None           # type: ignore
combo = None          # type: ignore
status_val = None     # type: ignore
wan_ip_lbl = None     # type: ignore
indicator = None      # type: ignore
log_box = None        # type: ignore
btn_test = None       # type: ignore
btn_ping = None       # type: ignore
primary_lbl = None    # type: ignore
secondary_lbl = None  # type: ignore
_traceroute_btn_ref = None  # type: ignore

# Big current-DNS banner widget refs
current_dns_primary_lbl   = None  # type: ignore
current_dns_secondary_lbl = None  # type: ignore
current_dns_name_lbl      = None  # type: ignore

import tkinter as tk
from tkinter import ttk

def _section_label(parent, text: str):
    f = tk.Frame(parent, bg=T["bg"])
    f.pack(fill="x", pady=(0, 4))
    tk.Label(f, text=text, font=("Segoe UI", 7, "bold"),
             bg=T["bg"], fg=T["fg2"]).pack(side="left")
    tk.Frame(f, height=1, bg=T["border"]).pack(
        side="left", fill="x", expand=True, padx=(6, 0), pady=3)

def _refresh_info_card():
    if not combo or not combo.winfo_exists():
        return
    name = combo.get()
    p, s = DNS_PROVIDERS.get(name, ("—", "—"))
    primary_lbl.config(text=p)
    secondary_lbl.config(text=s)

def _clear_log():
    _log_history.clear()
    log_box.config(state="normal")
    log_box.delete("1.0", "end")
    log_box.config(state="disabled")

def _build_ui(restore_combo: str = None):
    global combo, status_val, wan_ip_lbl, indicator, log_box
    global btn_test, btn_ping, primary_lbl, secondary_lbl, _traceroute_btn_ref
    global current_dns_primary_lbl, current_dns_secondary_lbl, current_dns_name_lbl

    bg = T["bg"]
    root.configure(bg=bg)

    # ── ttk style ──────────────────────────────────────────────────────────
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("DNS.TCombobox",
        fieldbackground=T["surface2"], background=T["surface2"],
        foreground=T["fg"], arrowcolor=T["accent"],
        bordercolor=T["border"], lightcolor=T["border"],
        darkcolor=T["border"], selectbackground=T["accent2"],
        selectforeground="#fff", padding=(10, 7), font=("Segoe UI", 9))
    style.map("DNS.TCombobox",
        fieldbackground=[("readonly", T["surface2"])],
        foreground=[("readonly", T["fg"])])

    # ═══════════════════════════════════════════════════════════════════════
    #  HEADER
    # ═══════════════════════════════════════════════════════════════════════
    hdr = tk.Frame(root, bg=T["surface"])
    hdr.pack(fill="x")

    hi = tk.Frame(hdr, bg=T["surface"])
    hi.pack(fill="x", padx=18, pady=10)

    # ── Title row ──────────────────────────────────────────────────────────
    tr = tk.Frame(hi, bg=T["surface"])
    tr.pack(fill="x")
    tk.Label(tr, text="bork", font=("Segoe UI", 18, "bold"),
             bg=T["surface"], fg=T["accent"]).pack(side="left")
    tk.Label(tr, text="DNS", font=("Segoe UI", 18, "bold"),
             bg=T["surface"], fg=T["fg"]).pack(side="left")
    tk.Label(tr, text="  v0.2", font=("Segoe UI", 10),
             bg=T["surface"], fg=T["fg2"]).pack(side="left", pady=(4, 0))
    indicator = tk.Label(tr, text="  ●", font=("Segoe UI", 11),
                         bg=T["surface"], fg=T["border"])
    indicator.pack(side="left", pady=(3, 0))

    # Theme toggles
    thm_fr = tk.Frame(tr, bg=T["surface"])
    thm_fr.pack(side="right")
    for key, sym in (("dark", "◑"), ("light", "○"), ("tinted", "◐")):
        c = T["accent"] if key == S.current_theme else T["fg2"]
        b = tk.Label(thm_fr, text=sym, font=("Segoe UI", 13),
                     bg=T["surface"], fg=c, cursor="hand2")
        b.pack(side="left", padx=4)
        b.bind("<Button-1>", lambda e, k=key: apply_theme(k))
        b.bind("<Enter>", lambda e, w=b: w.config(fg=T["accent"]))
        b.bind("<Leave>", lambda e, w=b, k=key: w.config(
            fg=T["accent"] if k == S.current_theme else T["fg2"]))

    # ── Status row ─────────────────────────────────────────────────────────
    sr = tk.Frame(hi, bg=T["surface"])
    sr.pack(fill="x", pady=(2, 0))
    tk.Label(sr, text="STATUS", font=("Segoe UI", 7, "bold"),
             bg=T["surface"], fg=T["fg2"]).pack(side="left")
    tk.Label(sr, text="  │  ", bg=T["surface"], fg=T["border"]).pack(side="left")
    status_val = tk.Label(sr, text="Initialising…",
                          font=("Segoe UI", 9), bg=T["surface"], fg=T["warn"])
    status_val.pack(side="left")
    wan_ip_lbl = tk.Label(sr, text=f"WAN  {S.wan_ip}",
                          font=("Consolas", 9), bg=T["surface"], fg=T["accent"])
    wan_ip_lbl.pack(side="right", padx=(0, 2))

    # Admin badge
    adm_col  = T["ok"] if S.admin else T["warn"]
    adm_text = "● ADMIN" if S.admin else "○ limited mode"
    tk.Label(sr, text=f"  │  {adm_text}", font=("Segoe UI", 7, "bold"),
             bg=T["surface"], fg=adm_col).pack(side="right", padx=(0, 8))

    # ── BIG CURRENT DNS BANNER ─────────────────────────────────────────────
    dns_card = tk.Frame(hi, bg=T["surface2"],
                        highlightthickness=1, highlightbackground=T["border"])
    dns_card.pack(fill="x", pady=(8, 2))
    dns_inner = tk.Frame(dns_card, bg=T["surface2"])
    dns_inner.pack(fill="x", padx=14, pady=10)

    tk.Label(dns_inner, text="ACTIVE DNS", font=("Segoe UI", 7, "bold"),
             bg=T["surface2"], fg=T["fg2"]).pack(anchor="w")

    dns_ips = tk.Frame(dns_inner, bg=T["surface2"])
    dns_ips.pack(fill="x")

    # Primary — large
    current_dns_primary_lbl = tk.Label(
        dns_ips, text="…",
        font=("Consolas", 22, "bold"),
        bg=T["surface2"], fg=T["accent"])
    current_dns_primary_lbl.pack(side="left")

    tk.Label(dns_ips, text="  /  ", font=("Consolas", 16),
             bg=T["surface2"], fg=T["fg2"]).pack(side="left")

    # Secondary — slightly smaller
    current_dns_secondary_lbl = tk.Label(
        dns_ips, text="…",
        font=("Consolas", 16),
        bg=T["surface2"], fg=T["fg2"])
    current_dns_secondary_lbl.pack(side="left")

    current_dns_name_lbl = tk.Label(
        dns_inner, text="",
        font=("Segoe UI", 8),
        bg=T["surface2"], fg=T["fg2"])
    current_dns_name_lbl.pack(anchor="w", pady=(2, 0))

    tk.Frame(root, height=1, bg=T["border"]).pack(fill="x")

    # ═══════════════════════════════════════════════════════════════════════
    #  MAIN BODY
    # ═══════════════════════════════════════════════════════════════════════
    body = tk.Frame(root, bg=bg)
    body.pack(fill="both", expand=True)

    # ── LEFT PANEL ─────────────────────────────────────────────────────────
    left = tk.Frame(body, bg=bg)
    left.pack(side="left", fill="both", padx=(16, 8), pady=14)

    # ·· DNS Configuration ··
    _section_label(left, "DNS CONFIGURATION")

    # Search filter
    search_var = tk.StringVar()
    search_entry = tk.Entry(
        left, textvariable=search_var,
        bg=T["surface2"], fg=T["fg2"],
        insertbackground=T["fg"], relief="flat",
        font=("Segoe UI", 8), width=32,
        highlightthickness=1,
        highlightbackground=T["border"],
        highlightcolor=T["accent"])
    search_entry.insert(0, "Search providers…")
    search_entry.config(fg=T["fg2"])
    search_entry.pack(fill="x", pady=(0, 3))

    all_providers = list(DNS_PROVIDERS.keys())

    combo = ttk.Combobox(left, values=all_providers,
                         state="readonly", style="DNS.TCombobox", width=32)
    combo.pack(fill="x", pady=(0, 0))
    combo.current(0)

    _prefs_now = load_prefs()
    _saved_provider = _prefs_now.get("last_provider", "")
    if restore_combo and restore_combo in DNS_PROVIDERS:
        combo.set(restore_combo)
    elif _saved_provider and _saved_provider in DNS_PROVIDERS:
        combo.set(_saved_provider)
    combo.bind("<<ComboboxSelected>>", lambda e: _refresh_info_card())

    def _filter_providers(*args):
        q = search_var.get().lower()
        if q == "search providers…" or not q:
            combo.config(values=all_providers)
        else:
            filtered = [p for p in all_providers if q in p.lower()]
            combo.config(values=filtered)
            if filtered and combo.get() not in filtered:
                combo.set(filtered[0])
                _refresh_info_card()

    def _search_focus_in(e):
        if search_entry.get() == "Search providers…":
            search_entry.delete(0, "end")
            search_entry.config(fg=T["fg"])

    def _search_focus_out(e):
        if not search_entry.get():
            search_entry.insert(0, "Search providers…")
            search_entry.config(fg=T["fg2"])

    search_var.trace_add("write", _filter_providers)
    search_entry.bind("<FocusIn>",  _search_focus_in)
    search_entry.bind("<FocusOut>", _search_focus_out)

    # Info card
    tk.Frame(left, height=4, bg=bg).pack()
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

    _refresh_info_card()

    # Apply button + copy row
    tk.Frame(left, height=5, bg=bg).pack()
    apply_row = tk.Frame(left, bg=bg)
    apply_row.pack(fill="x")

    apply_b = flat_btn(apply_row, "⟶  Apply Selected DNS",
                       lambda: _guard() and submit(
                           _do_apply(*DNS_PROVIDERS[combo.get()], name=combo.get())),
                       T["accent2"], pady=10, font=("Segoe UI", 10, "bold"))
    apply_b.pack(side="left", fill="both", expand=True, padx=(0, 3))
    _add_tooltip(apply_b, "Apply the selected DNS provider to your active interface")

    copy_b = flat_btn(apply_row, "📋", _copy_selected_dns,
                      T["surface2"], fg=T["fg2"], padx=10, pady=10)
    copy_b.pack(side="left")
    _add_tooltip(copy_b, "Copy primary & secondary IPs to clipboard")

    # ── Custom DNS ─────────────────────────────────────────────────────────
    tk.Frame(left, height=6, bg=bg).pack()
    _section_label(left, "CUSTOM DNS")

    custom_fr = tk.Frame(left, bg=T["surface2"],
                         highlightthickness=1, highlightbackground=T["border"])
    custom_fr.pack(fill="x")
    cf_inner = tk.Frame(custom_fr, bg=T["surface2"])
    cf_inner.pack(fill="x", padx=10, pady=8)

    tk.Label(cf_inner, text="Primary", font=("Segoe UI", 7),
             bg=T["surface2"], fg=T["fg2"]).grid(row=0, column=0, sticky="w", pady=(0,2))
    custom_p_var = tk.StringVar()
    tk.Entry(cf_inner, textvariable=custom_p_var, bg=T["surface"], fg=T["fg"],
             insertbackground=T["fg"], relief="flat", font=("Consolas", 9), width=16,
             highlightthickness=1, highlightbackground=T["border"],
             highlightcolor=T["accent"]).grid(row=0, column=1, padx=(6,0), pady=(0,2), sticky="ew")

    tk.Label(cf_inner, text="Secondary", font=("Segoe UI", 7),
             bg=T["surface2"], fg=T["fg2"]).grid(row=1, column=0, sticky="w", pady=(2,0))
    custom_s_var = tk.StringVar()
    tk.Entry(cf_inner, textvariable=custom_s_var, bg=T["surface"], fg=T["fg"],
             insertbackground=T["fg"], relief="flat", font=("Consolas", 9), width=16,
             highlightthickness=1, highlightbackground=T["border"],
             highlightcolor=T["accent"]).grid(row=1, column=1, padx=(6,0), pady=(2,0), sticky="ew")

    def _apply_custom():
        p = custom_p_var.get().strip()
        s = custom_s_var.get().strip()
        if not p:
            _msgwarn("Custom DNS", "Enter a primary DNS IP."); return
        if not re.match(r"\d+\.\d+\.\d+\.\d+", p):
            _msgerr("Custom DNS", f"'{p}' does not look like a valid IP."); return
        if s and not re.match(r"\d+\.\d+\.\d+\.\d+", s):
            _msgerr("Custom DNS", f"'{s}' does not look like a valid IP."); return
        if not s:
            s = p
        if _guard():
            submit(_do_apply(p, s, "Custom"))

    flat_btn(cf_inner, "Apply Custom", _apply_custom,
             T["accent2"], pady=5, font=("Segoe UI", 8, "bold")).grid(
                 row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    # ── DNS Utilities ──────────────────────────────────────────────────────
    tk.Frame(left, height=8, bg=bg).pack()
    row_dns = tk.Frame(left, bg=bg)
    row_dns.pack(fill="x")

    for text, cmd, fg, tip in (
        ("↩ Undo",   lambda: _guard() and submit(_do_undo()),   T["warn"],  "Restore the previous DNS settings"),
        ("⟲ DHCP",   lambda: _guard() and submit(_do_reset()),  T["err"],   "Reset DNS to automatic (ISP DHCP)"),
        ("🗑 Flush",  lambda: _guard() and submit(_do_flush()),  T["blue"],  "Flush the Windows DNS resolver cache"),
    ):
        b = flat_btn(row_dns, text, cmd, T["surface2"], fg=fg, pady=8, padx=6)
        b.pack(side="left", fill="both", expand=True, padx=2)
        _add_tooltip(b, tip)

    tk.Frame(left, height=4, bg=bg).pack()
    hist_b = flat_btn(left, "🕐 DNS History", open_history_dialog,
                      T["surface2"], fg=T["fg2"], pady=7)
    hist_b.pack(fill="x")
    _add_tooltip(hist_b, "View and re-apply recently used DNS profiles")

    # ── Network Tools ──────────────────────────────────────────────────────
    tk.Frame(left, height=10, bg=bg).pack()
    _section_label(left, "NETWORK TOOLS")

    row_t1 = tk.Frame(left, bg=bg)
    row_t1.pack(fill="x")
    btn_test = flat_btn(row_t1, "⚡ Speed Test", lambda: submit(_do_speed_test()),
                        T["surface2"], fg=T["accent"], pady=8)
    btn_test.pack(side="left", fill="both", expand=True, padx=(0, 2))
    _add_tooltip(btn_test, "Benchmark all DNS providers — parallel ping + resolve")

    btn_ping = flat_btn(row_t1, "● Ping Tool", open_ping_tool,
                        T["surface2"], fg=T["ok"], pady=8)
    btn_ping.pack(side="left", fill="both", expand=True, padx=(2, 0))
    _add_tooltip(btn_ping, "Live ping monitor for multiple hosts with sparkline chart")

    tk.Frame(left, height=4, bg=bg).pack()
    row_t2 = tk.Frame(left, bg=bg)
    row_t2.pack(fill="x")
    _traceroute_btn_ref = flat_btn(row_t2, "⇝ Traceroute", open_traceroute_dialog,
                                   T["surface2"], fg=T["blue"], pady=8)
    if _traceroute_proc is not None:
        _traceroute_btn_ref.config(text="■ Stop Trace", command=_cancel_traceroute)
    _traceroute_btn_ref.pack(side="left", fill="both", expand=True, padx=(0, 2))
    _add_tooltip(_traceroute_btn_ref, "Run tracert to a host and stream hops to the log")

    port_b = flat_btn(row_t2, "⬡ Port Check", open_port_dialog,
                      T["surface2"], fg=T["warn"], pady=8)
    port_b.pack(side="left", fill="both", expand=True, padx=(2, 0))
    _add_tooltip(port_b, "Test if a TCP port is open on a remote host")

    tk.Frame(left, height=4, bg=bg).pack()
    row_t3 = tk.Frame(left, bg=bg)
    row_t3.pack(fill="x")
    info_b = flat_btn(row_t3, "ℹ Interface Info", lambda: submit(_do_show_info()),
                      T["surface2"], fg=T["fg2"], pady=8)
    info_b.pack(side="left", fill="both", expand=True, padx=(0, 2))
    _add_tooltip(info_b, "Show full network adapter info (IP, gateway, DHCP, etc.)")

    hosts_b = flat_btn(row_t3, "📄 Hosts File", open_hosts_viewer,
                       T["surface2"], fg=T["fg2"], pady=8)
    hosts_b.pack(side="left", fill="both", expand=True, padx=(2, 0))
    _add_tooltip(hosts_b, "View and optionally edit C:\\Windows\\System32\\drivers\\etc\\hosts")

    # ── Exit ───────────────────────────────────────────────────────────────
    tk.Frame(left, height=10, bg=bg).pack()
    flat_btn(left, "✕  Exit", _save_geometry_on_exit, T["surface2"],
             fg=T["fg2"], pady=7).pack(fill="x")

    # ── DIVIDER ────────────────────────────────────────────────────────────
    tk.Frame(body, width=1, bg=T["border"]).pack(side="left", fill="y", pady=12)

    # ── RIGHT PANEL — LOG ──────────────────────────────────────────────────
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

    # Colour tags
    for tag, col in (("ts", T["fg2"]), ("ok", T["ok"]), ("err", T["err"]),
                     ("warn", T["warn"]), ("act", T["accent"]), ("info", T["fg"])):
        log_box.tag_config(tag, foreground=col)

# ─────────────────────────────────────────────────────────────────────────────
#  GEOMETRY PERSISTENCE
# ─────────────────────────────────────────────────────────────────────────────

def _restore_geometry(prefs: dict):
    import re as _re
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    g = prefs.get("geometry")
    if g:
        try:
            parts = _re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", g)
            if parts:
                w, h, x, y = (int(p) for p in parts.groups())
                x = max(0, min(x, sw - 100))
                y = max(0, min(y, sh - 100))
                root.geometry(f"{w}x{h}+{x}+{y}")
                return
        except Exception:
            pass
    w = min(max(820, int(sw * 0.55)), 1280)
    h = min(max(620, int(sh * 0.65)), 960)
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

    # Admin is detected but NOT demanded at startup — lazy UAC
    S.admin = is_admin()

    prefs = load_prefs()
    theme_key = prefs.get("theme", "dark")
    if theme_key in THEMES:
        T.clear()
        T.update(THEMES[theme_key])
        S.current_theme = theme_key

    # Restore history
    S.dns_apply_history = prefs.get("dns_history", [])

    root = tk.Tk()
    root.title("borkDNS v0.2")
    root.configure(bg=T["bg"])
    root.resizable(True, True)
    root.minsize(700, 560)
    root.protocol("WM_DELETE_WINDOW", _save_geometry_on_exit)

    _restore_geometry(prefs)
    _build_ui()

    bg_thread = threading.Thread(target=_start_loop, daemon=True)
    bg_thread.start()
    time.sleep(0.04)

    submit(startup_probe())
    log("borkDNS v0.2 started" + ("  [ADMIN]" if S.admin else "  [limited — admin not requested yet]"), "act")

    root.mainloop()

if __name__ == "__main__":
    main()