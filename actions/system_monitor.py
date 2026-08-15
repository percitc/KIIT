# system_monitor.py — KITT System Intelligence
# Real-time system awareness: CPU, RAM, disk, network, battery, processes
# Dependencies: psutil (already in requirements)

import os
import sys
import time
import platform
import subprocess
from datetime import datetime, timedelta

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


_OS = platform.system()  # Windows | Darwin | Linux


def _fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"

def _fmt_seconds(s: float) -> str:
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


# ════════════════════════════════════════════════════════════════════════════
#  STATUS REPORT
# ════════════════════════════════════════════════════════════════════════════

def _status(params: dict) -> str:
    if not _PSUTIL:
        return "psutil not installed."

    parts = []

    # CPU
    cpu_pct  = psutil.cpu_percent(interval=0.5)
    cpu_freq = psutil.cpu_freq()
    cpu_cores = psutil.cpu_count(logical=False)
    cpu_threads = psutil.cpu_count(logical=True)
    freq_str = f" @ {cpu_freq.current:.0f} MHz" if cpu_freq else ""
    parts.append(f"CPU: {cpu_pct}%{freq_str} ({cpu_cores} cores / {cpu_threads} threads)")

    # RAM
    ram = psutil.virtual_memory()
    parts.append(f"RAM: {ram.percent}% used ({_fmt_bytes(ram.used)} / {_fmt_bytes(ram.total)})")

    # Disk
    try:
        disk = psutil.disk_usage("/")
        parts.append(f"Disk: {disk.percent}% used ({_fmt_bytes(disk.free)} free of {_fmt_bytes(disk.total)})")
    except Exception:
        pass

    # Battery
    try:
        batt = psutil.sensors_battery()
        if batt:
            charge  = f"{batt.percent:.0f}%"
            status  = "charging" if batt.power_plugged else "on battery"
            secs_left = batt.secsleft
            eta     = f", ~{_fmt_seconds(secs_left)} remaining" if secs_left > 0 and not batt.power_plugged else ""
            parts.append(f"Battery: {charge} ({status}{eta})")
    except Exception:
        pass

    # Uptime
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime    = datetime.now() - boot_time
    h, rem    = divmod(int(uptime.total_seconds()), 3600)
    m         = rem // 60
    parts.append(f"Uptime: {h}h {m}m")

    # Temperature (if available)
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        avg_t = sum(e.current for e in entries) / len(entries)
                        parts.append(f"Temperature ({name}): {avg_t:.1f}°C")
                        break
    except Exception:
        pass

    return " | ".join(parts)


# ════════════════════════════════════════════════════════════════════════════
#  PROCESS MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

def _top_processes(params: dict) -> str:
    if not _PSUTIL:
        return "psutil not installed."

    sort_by = params.get("sort_by", "cpu")   # cpu | ram | name
    limit   = int(params.get("limit", 8))

    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = p.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Second pass for accurate CPU
    time.sleep(0.3)
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            for stored in procs:
                if stored["pid"] == p.pid:
                    stored["cpu_percent"] = p.cpu_percent()
        except Exception:
            pass

    if sort_by == "ram":
        procs.sort(key=lambda x: x.get("memory_percent") or 0, reverse=True)
    elif sort_by == "name":
        procs.sort(key=lambda x: (x.get("name") or "").lower())
    else:
        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)

    lines = []
    for p in procs[:limit]:
        name = (p.get("name") or "unknown")[:28]
        cpu  = p.get("cpu_percent") or 0
        mem  = p.get("memory_percent") or 0
        lines.append(f"{name:<28} CPU:{cpu:5.1f}%  RAM:{mem:4.1f}%")

    return "Top processes:\n" + "\n".join(lines)


def _kill_process(params: dict) -> str:
    if not _PSUTIL:
        return "psutil not installed."

    name = params.get("process_name", "").lower()
    pid  = params.get("pid")
    killed = []

    if pid:
        try:
            p = psutil.Process(int(pid))
            p.terminate()
            killed.append(f"PID {pid}")
        except Exception as e:
            return f"Could not kill PID {pid}: {e}"
    elif name:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if name in (p.info["name"] or "").lower():
                    p.terminate()
                    killed.append(p.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    if killed:
        return f"Terminated: {', '.join(killed)}"
    return f"No process found matching '{name or pid}'."


# ════════════════════════════════════════════════════════════════════════════
#  NETWORK
# ════════════════════════════════════════════════════════════════════════════

def _network_status(params: dict) -> str:
    if not _PSUTIL:
        return "psutil not installed."

    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    counters = psutil.net_io_counters()

    lines = []
    for iface, addr_list in addrs.items():
        st = stats.get(iface)
        if not st or not st.isup:
            continue
        for addr in addr_list:
            if addr.family == 2:   # AF_INET = IPv4
                speed = f"{st.speed} Mbps" if st.speed else "?"
                lines.append(f"{iface}: {addr.address} ({speed})")

    total = (f"Total sent: {_fmt_bytes(counters.bytes_sent)} | "
             f"Received: {_fmt_bytes(counters.bytes_recv)}")
    lines.append(total)
    return " | ".join(lines) if lines else "No active network interfaces found."


# ════════════════════════════════════════════════════════════════════════════
#  DISK DETAILS
# ════════════════════════════════════════════════════════════════════════════

def _disk_info(params: dict) -> str:
    if not _PSUTIL:
        return "psutil not installed."

    lines = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            lines.append(
                f"{part.device} ({part.fstype}): "
                f"{_fmt_bytes(usage.free)} free / {_fmt_bytes(usage.total)} total "
                f"({usage.percent}% used)"
            )
        except PermissionError:
            pass
    return " | ".join(lines) if lines else "No disk info available."


# ════════════════════════════════════════════════════════════════════════════
#  STARTUP APPS (Windows only)
# ════════════════════════════════════════════════════════════════════════════

def _startup_apps(params: dict) -> str:
    if _OS != "Windows":
        return "Startup app management is Windows-only."
    try:
        result = subprocess.run(
            ["wmic", "startup", "get", "Caption,Command,Location"],
            capture_output=True, text=True, timeout=10
        )
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip() and l.strip() != "Caption  Command  Location"]
        return f"Startup items: {len(lines)}\n" + "\n".join(lines[:10])
    except Exception as e:
        return f"Could not get startup apps: {e}"


# ════════════════════════════════════════════════════════════════════════════
#  PROACTIVE ALERT (call periodically from main if desired)
# ════════════════════════════════════════════════════════════════════════════

def get_proactive_alert() -> str | None:
    """Returns a warning string if system is stressed, else None."""
    if not _PSUTIL:
        return None
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory().percent
    try:
        batt = psutil.sensors_battery()
        if batt and not batt.power_plugged and batt.percent < 15:
            return f"Battery at {batt.percent:.0f}%. Connect charger soon."
    except Exception:
        pass
    if cpu > 90:
        return f"CPU at {cpu}%. Something is hammering the processor."
    if ram > 90:
        return f"RAM at {ram}%. Consider closing some apps."
    return None


# ════════════════════════════════════════════════════════════════════════════
#  MAIN DISPATCHER
# ════════════════════════════════════════════════════════════════════════════

def system_monitor(parameters: dict, player=None, speak=None) -> str:
    action = parameters.get("action", "status").lower()

    try:
        if action in ("status", "report", "health", "check"):
            return _status(parameters)
        elif action in ("processes", "top", "tasks"):
            return _top_processes(parameters)
        elif action in ("kill", "terminate", "close_process"):
            return _kill_process(parameters)
        elif action in ("network", "wifi", "internet"):
            return _network_status(parameters)
        elif action in ("disk", "storage", "drives"):
            return _disk_info(parameters)
        elif action in ("startup", "boot_apps"):
            return _startup_apps(parameters)
        elif action == "alert":
            return get_proactive_alert() or "All systems normal."
        else:
            return _status(parameters)
    except Exception as e:
        return f"system_monitor error: {e}"
