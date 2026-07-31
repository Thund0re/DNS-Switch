# DNS Changer (GUI)

# borkDNS Changelog

## v0.3
- DPI-aware auto-scaling — window, fonts, and padding scale from system DPI automatically
- Speed test streams per-host results live as they arrive with a running counter (`[3/29]…`)
- All actions (apply, reset, undo, flush, startup) log numbered steps as they execute

## v0.2
- Active DNS shown in large text in the header — always visible
- Lazy UAC — admin prompt only fires when a privileged action is triggered, not on startup
- Ping Tool — dedicated dialog with live multi-host table, sparkline, loss%, min/avg/max, CSV export
- DNS search filter — type to narrow the provider list in real time
- Custom DNS entry — apply any primary/secondary IP directly
- DNS history — last 10 applied profiles, one-click re-apply
- Copy IPs button — copies selected provider IPs to clipboard
- Hosts file inline edit — edit and save from the viewer (admin required)
- Speed test results open in a sortable table instead of dumping to the log
- Tooltips on all buttons

## v0.1
- Initial release
- 28 built-in DNS providers
- Apply, undo, DHCP reset, cache flush
- Parallel DNS speed test
- Ping monitor with sparkline
- Traceroute, port check, interface info, hosts viewer
- Dark / Light / Amber themes with persistence
- Async engine, no third-party dependencies

---

## License

MIT License

You are free to use, modify, and distribute this software.

