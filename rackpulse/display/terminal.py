from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from rackpulse.models import DeviceReading, DeviceStatus, PollSnapshot, RackStatus


STATUS_STYLE = {
    RackStatus.OK: "green",
    RackStatus.WARNING: "yellow",
    RackStatus.CRITICAL: "red bold",
    RackStatus.UNKNOWN: "dim",
}

DEVICE_STATUS_STYLE = {
    DeviceStatus.OK: "green",
    DeviceStatus.STALE: "yellow",
    DeviceStatus.UNREACHABLE: "red",
    DeviceStatus.ERROR: "red",
}


def _fmt_power(watts: float | None) -> str:
    if watts is None:
        return "—"
    if watts >= 1000:
        return f"{watts / 1000:.2f} kW"
    return f"{watts:.0f} W"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%"


def render_snapshot(snapshot: PollSnapshot) -> Group:
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("Total draw", _fmt_power(snapshot.total_power_watts))
    if snapshot.last_poll:
        summary.add_row("Last poll", snapshot.last_poll.strftime("%Y-%m-%d %H:%M:%S UTC"))

    parts: list = [Panel(summary, title="RackPulse", border_style="cyan")]

    for rack in snapshot.racks:
        parts.append(_render_rack_table(rack))

    return Group(*parts)


def _render_rack_table(rack) -> Panel:
    title = f"{rack.name}"
    if rack.location:
        title += f" — {rack.location}"

    subtitle = Text()
    subtitle.append(_fmt_power(rack.power_watts), style=STATUS_STYLE.get(rack.status, "white"))
    subtitle.append(f"  [{rack.status.value}]", style=STATUS_STYLE.get(rack.status, "dim"))

    table = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold")
    table.add_column("Device")
    table.add_column("Type")
    table.add_column("Host")
    table.add_column("Power", justify="right")
    table.add_column("CPU", justify="right")
    table.add_column("RAM", justify="right")
    table.add_column("Temp", justify="right")
    table.add_column("Status")

    for device in sorted(rack.devices, key=lambda d: d.power_watts or 0, reverse=True):
        status_text = Text(device.status.value, style=DEVICE_STATUS_STYLE.get(device.status, "white"))
        if device.error and device.status in (DeviceStatus.UNREACHABLE, DeviceStatus.ERROR):
            short = device.error if len(device.error) <= 36 else device.error[:33] + "..."
            status_text.append(f" ({short})", style="dim")

        table.add_row(
            device.name,
            device.device_type,
            device.host,
            _fmt_power(device.power_watts),
            _fmt_pct(device.metrics.cpu_percent or device.metrics.gpu_util_percent),
            _fmt_pct(device.metrics.ram_percent),
            f"{device.metrics.temperature_c:.0f}°C" if device.metrics.temperature_c else "—",
            status_text,
        )

    return Panel(table, title=title, subtitle=subtitle, border_style=STATUS_STYLE.get(rack.status, "white"))


def print_snapshot(console: Console, snapshot: PollSnapshot) -> None:
    console.clear()
    console.print(render_snapshot(snapshot))


def render_device_detail(device: DeviceReading) -> Panel:
    lines = [
        f"Type: {device.device_type}",
        f"Host: {device.host}",
        f"Rack: {device.rack}",
        f"Status: {device.status.value}",
        f"Power: {_fmt_power(device.power_watts)}",
        f"Voltage: {device.metrics.volts:.1f} V" if device.metrics.volts is not None else "Voltage: —",
        f"Current: {device.metrics.amps:.2f} A" if device.metrics.amps is not None else "Current: —",
        f"CPU: {_fmt_pct(device.metrics.cpu_percent)}",
        f"RAM: {_fmt_pct(device.metrics.ram_percent)}",
        f"GPU util: {_fmt_pct(device.metrics.gpu_util_percent)}",
    ]
    if device.error:
        lines.append(f"Error: {device.error}")
    if device.metrics.extra:
        lines.append(f"Extra: {device.metrics.extra}")
    return Panel("\n".join(lines), title=device.name, border_style="cyan")
