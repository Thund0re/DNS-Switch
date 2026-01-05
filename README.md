# DNS Changer (GUI)

A lightweight and transparent Windows DNS Changer built using Python and Tkinter.
The application allows users to change, test, undo, and reset DNS settings with full visibility into what actions are being performed.

The tool is designed to be fast, safe, and user-controlled.
No background services, no silent changes, and no startup delays.

---

## Features

* Change DNS using well-known public DNS providers
* Test and identify the fastest DNS (latency + real DNS resolution)
* User confirmation before applying any DNS changes
* Undo and restore previous DNS settings (session-based)
* Reset DNS to automatic (DHCP)
* Live activity log showing commands and results
* Clear state indicator showing current operation
* Clean exit with no background processes

---

## Supported Platform

* Windows 10
* Windows 11
* Python 3.9 or newer
* Administrator privileges required for DNS changes

---

## Dependencies

Only standard Python libraries are used:

* tkinter
* subprocess
* threading
* re
* time

No third-party packages are required.

---

## How to Run

### Step 1: Download the Application

Clone the repository or download the Python file directly.

```bash
git clone https://github.com/your-repo/windows-dns-changer.git
cd windows-dns-changer
```

---

### Step 2: Run as Administrator

Changing DNS settings requires administrator privileges.

Option A: From an elevated command prompt

```bash
python dns_changer.py
```

Option B: From File Explorer

* Right-click the Python file
* Select "Run as administrator"

---

## How to Use

### Select a DNS Provider

Choose a DNS provider from the dropdown list.
Examples include Cloudflare, Google DNS, Quad9, and others.

---

### Apply Selected DNS

Click "Apply Selected DNS" to apply the chosen DNS to the currently active network interface.
The activity log will show which commands are executed and whether the operation succeeded.

---

### Find Fastest DNS (No Apply)

Click "Find Fastest DNS (No Apply)" to test DNS speed.

The application will:

* Ping each DNS server
* Perform a real DNS lookup using nslookup
* Rank DNS providers by performance

A popup will display the results and ask whether you want to select the fastest DNS.
DNS is not applied automatically.

---

### Undo / Restore Previous DNS

Restores the DNS configuration that was active before the last DNS change.

This works for:

* Static DNS configurations
* Automatic (DHCP) DNS

Undo is valid only during the current application session.

---

### Reset to Automatic (DHCP)

Resets DNS settings back to the system default configuration using DHCP.

---

### Exit Application

Closes the application cleanly.
No background processes remain running.

---

## Activity Log

The activity log displays real-time information about what the application is doing.

It includes:

* Timestamps
* Current tasks
* DNS test progress
* Command execution results
* Errors if they occur

Example log output:

```
[14:22:01] Detecting active network interface
[14:22:02] Active interface: Wi-Fi
[14:22:10] Testing Cloudflare (1.1.1.1)
[14:22:11] Result: Ping 18 ms, Resolve 22 ms
```

---

## Application States

The current state is displayed at the top of the application.

Possible states:

* IDLE: Waiting for user action
* TESTING DNS: DNS speed test in progress
* APPLYING DNS: DNS change in progress
* RESETTING DNS: Resetting DNS to DHCP
* DONE: Operation completed successfully
* ERROR: Operation failed

---

## Important Notes

* Administrator privileges are mandatory for applying or resetting DNS
* DNS speed testing does not modify system settings
* Undo works only while the application remains open
* DNS performance depends on network conditions and ISP routing

---

## Troubleshooting

### Permission Error

Ensure the application is started with administrator privileges.

---

### No DNS Servers Responded

Check internet connectivity or firewall rules blocking ICMP or DNS queries.

---

### Undo Not Available

No DNS changes were made during the current session.

---

## Internal Design Overview

* Uses netsh for DNS configuration
* Uses ping for network latency testing
* Uses nslookup for real DNS resolution timing
* Background threads prevent UI blocking
* UI updates are performed safely on the main thread

---

## License

MIT License

You are free to use, modify, and distribute this software.

