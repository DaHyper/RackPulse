from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from rich.console import Console

from rackpulse import __version__
from rackpulse.config import load_config, resolve_config_path
from rackpulse.display.terminal import print_snapshot, render_device_detail
from rackpulse.engine.poller import Poller

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def cmd_poll(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        console.print("Copy config.example.yaml to config.yaml and edit it.")
        return 1

    poller = Poller(str(config_path))
    snapshot = asyncio.run(poller.poll_once())

    if args.json:
        payload = {
            "last_poll": snapshot.last_poll.isoformat() if snapshot.last_poll else None,
            "total_power_watts": snapshot.total_power_watts,
            "racks": [
                {
                    "name": r.name,
                    "location": r.location,
                    "power_watts": r.power_watts,
                    "status": r.status.value,
                    "devices": [
                        {
                            "name": d.name,
                            "type": d.device_type,
                            "host": d.host,
                            "status": d.status.value,
                            "power_watts": d.power_watts,
                            "volts": d.metrics.volts,
                            "amps": d.metrics.amps,
                            "cpu_percent": d.metrics.cpu_percent,
                            "ram_percent": d.metrics.ram_percent,
                            "temperature_c": d.metrics.temperature_c,
                            "error": d.error,
                            "vms": [
                                {
                                    "vmid": v.vmid,
                                    "name": v.name,
                                    "cpu_percent": v.cpu_percent,
                                    "ram_percent": v.ram_percent,
                                    "status": v.status,
                                }
                                for v in d.vms
                            ],
                        }
                        for d in r.devices
                    ],
                }
                for r in snapshot.racks
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print_snapshot(console, snapshot)

    return 0


async def _watch_loop(poller: Poller, interval: int | None) -> None:
    while True:
        snapshot = await poller.poll_once()
        print_snapshot(console, snapshot)
        wait = interval if interval is not None else poller.config.poll_interval_seconds
        await asyncio.sleep(wait)


def cmd_watch(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        return 1

    poller = Poller(str(config_path))
    try:
        asyncio.run(_watch_loop(poller, args.interval))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        return 1

    poller = Poller(str(config_path))
    try:
        reading = asyncio.run(poller.poll_device_by_name(args.device))
    except KeyError:
        console.print(f"[red]Device not found in config:[/red] {args.device}")
        return 1

    console.print(render_device_detail(reading))
    return 0 if reading.status.value in ("ok", "stale") else 2


def cmd_list_devices(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        return 1

    config = load_config(config_path)
    for rack in config.racks:
        console.print(f"[bold cyan]{rack.name}[/bold cyan] — {rack.location or 'no location'}")
        for device in rack.devices:
            console.print(f"  • {device.name} ({device.type}) @ {device.host}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        return 1

    poller = Poller(str(config_path))
    hours = args.hours
    history = poller.storage.device_power_history(args.device, hours=hours)

    if args.json:
        print(json.dumps({"device": args.device, "hours": hours, "samples": history}, indent=2))
        return 0

    if not history:
        console.print(f"[yellow]No power history for {args.device} in the last {hours}h.[/yellow]")
        return 0

    latest = history[-1]
    console.print(f"[bold]{args.device}[/bold] — last {hours}h ({len(history)} samples)")
    if latest.get("watts") is not None:
        console.print(f"Current: [cyan]{latest['watts']:.0f} W[/cyan]", end="")
        if latest.get("volts") is not None and latest.get("amps") is not None:
            console.print(f"  ({latest['volts']:.1f} V × {latest['amps']:.2f} A)")
        else:
            console.print()

    from rich.table import Table

    table = Table(show_header=True, header_style="bold")
    table.add_column("Timestamp")
    table.add_column("Watts", justify="right")
    table.add_column("Volts", justify="right")
    table.add_column("Amps", justify="right")
    for row in history[-20:]:
        table.add_row(
            str(row["timestamp"]),
            f"{row['watts']:.1f}" if row.get("watts") is not None else "—",
            f"{row['volts']:.1f}" if row.get("volts") is not None else "—",
            f"{row['amps']:.2f}" if row.get("amps") is not None else "—",
        )
    console.print(table)
    if len(history) > 20:
        console.print(f"[dim]… showing last 20 of {len(history)} samples[/dim]")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from rackpulse.api.app import run_server
    except ImportError:
        console.print(
            "[red]API dependencies not installed.[/red] Run: pip install -e '.[api]'"
        )
        return 1

    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        return 1

    run_server(str(config_path), host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rackpulse",
        description="Multi-rack power and infrastructure monitoring",
    )
    parser.add_argument("--version", action="version", version=f"rackpulse {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "-c",
        "--config",
        help="Path to config.yaml (default: ./config.yaml or config.example.yaml)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    poll = sub.add_parser("poll", help="Poll all devices once and print results")
    poll.add_argument("--json", action="store_true", help="Output JSON instead of dashboard")
    poll.set_defaults(func=cmd_poll)

    watch = sub.add_parser("watch", help="Continuously poll and refresh terminal dashboard")
    watch.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Override poll interval in seconds",
    )
    watch.set_defaults(func=cmd_watch)

    test = sub.add_parser("test", help="Test a single device by name")
    test.add_argument("device", help="Device name from config.yaml")
    test.set_defaults(func=cmd_test)

    ls = sub.add_parser("list", help="List configured racks and devices")
    ls.set_defaults(func=cmd_list_devices)

    history = sub.add_parser("history", help="Show stored power history for a device")
    history.add_argument("device", help="Device name from config.yaml")
    history.add_argument(
        "--hours",
        type=float,
        default=24,
        help="History window in hours (default: 24; use 168 for 7d, 720 for 30d)",
    )
    history.add_argument("--json", action="store_true", help="Output JSON")
    history.set_defaults(func=cmd_history)

    serve = sub.add_parser("serve", help="Start optional HTTP API (requires [api] extras)")
    serve.add_argument("--host", default=None, help="Bind host (default from config)")
    serve.add_argument("--port", type=int, default=None, help="Bind port (default from config)")
    serve.set_defaults(func=cmd_serve)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _setup_logging(args.verbose)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
