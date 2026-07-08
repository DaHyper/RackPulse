from __future__ import annotations

import argparse
import copy
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from rackpulse.config import default_secrets_path
from rackpulse.config_io import migrate_plaintext_secrets, save_config


@dataclass
class MigrationResult:
    source_format: str
    input_path: Path
    output_path: Path
    backup_path: Path | None = None
    changes: list[str] = field(default_factory=list)
    secrets_migrated: bool = False
    dry_run: bool = False


def detect_source_format(raw: dict[str, Any]) -> str:
    racks = raw.get("racks") or []
    has_pdus = any(isinstance(r, dict) and r.get("pdus") for r in racks)
    has_devices = any(isinstance(r, dict) and r.get("devices") for r in racks)
    has_alerts = isinstance(raw.get("alerts"), dict)
    has_pdu_section = bool(raw.get("pdu") or raw.get("apc"))
    snmp = raw.get("snmp") or {}
    snmp_has_oids = any(k in snmp for k in ("power_oid", "power_divisor", "energy_oid", "energy_divisor"))

    if has_pdus:
        return "pdu-power-monitor"
    if has_alerts and has_pdu_section and has_devices and not snmp_has_oids:
        return "rackpulse-v2"
    if has_devices or snmp_has_oids or raw.get("smtp") or raw.get("webhooks"):
        return "rackpulse-v1"
    return "unknown"


def _migrate_device(device: dict[str, Any], default_community: str) -> dict[str, Any]:
    result = copy.deepcopy(device)
    if "type" not in result:
        result["type"] = "pdu"
    if result["type"] in ("pdu", "nas", "arista_switch", "cisco_switch", "dell_switch"):
        result.setdefault("community", default_community)
    return result


def _migrate_rack(rack: dict[str, Any], default_community: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": rack.get("name", "rack-1"),
        "location": rack.get("location") or rack.get("description") or "",
    }
    if rack.get("warning_kw") is not None:
        result["warning_kw"] = rack["warning_kw"]
    if rack.get("critical_kw") is not None:
        result["critical_kw"] = rack["critical_kw"]
    if rack.get("power_cap_kw") is not None:
        result["power_cap_kw"] = rack["power_cap_kw"]

    devices: list[dict[str, Any]] = []
    for pdu in rack.get("pdus") or []:
        devices.append(
            _migrate_device(
                {
                    "name": pdu["name"],
                    "type": "pdu",
                    "host": pdu["host"],
                    "community": pdu.get("community", default_community),
                    **({"snmp_version": pdu["snmp_version"]} if pdu.get("snmp_version") else {}),
                },
                default_community,
            )
        )
    for device in rack.get("devices") or []:
        devices.append(_migrate_device(device, default_community))
    result["devices"] = devices
    return result


def transform_to_v2(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Convert legacy YAML dict to RackPulse v2 structure."""
    source = detect_source_format(raw)
    if source == "rackpulse-v2":
        return copy.deepcopy(raw), ["Already RackPulse v2 format — no structural changes needed"]

    changes: list[str] = []
    data = copy.deepcopy(raw)
    snmp = data.get("snmp") or {}

    if source == "pdu-power-monitor":
        changes.append("Detected PDU-Power-Monitor config")
    elif source == "rackpulse-v1":
        changes.append("Detected RackPulse v1 config")
    else:
        changes.append("Unknown format — applying best-effort v2 normalization")

    storage = data.get("storage") or {}
    if not storage.get("path"):
        storage["path"] = "./data/rackpulse.db"
        changes.append("Added storage.path")
    if "retain_days" not in storage:
        storage["retain_days"] = 90
    data["storage"] = storage

    secrets = data.get("secrets") or {}
    if not secrets.get("path"):
        secrets["path"] = default_secrets_path(storage["path"])
        changes.append("Added secrets.path")
    data["secrets"] = secrets

    pdu_raw = data.get("pdu") or data.get("apc") or {}
    if any(k in snmp for k in ("power_oid", "power_divisor", "energy_oid", "energy_divisor")):
        for key in ("power_oid", "power_divisor", "energy_oid", "energy_divisor"):
            if key in snmp:
                pdu_raw.setdefault(key, snmp.pop(key))
        changes.append("Moved PDU OIDs from snmp.* to pdu.*")
    if pdu_raw:
        data["pdu"] = pdu_raw
    data.pop("apc", None)

    snmp.setdefault("community", "public")
    data["snmp"] = snmp

    alerts = data.get("alerts") or {}
    if "alert_cooldown_minutes" in data:
        alerts.setdefault("cooldown_minutes", data.pop("alert_cooldown_minutes"))
        changes.append("Moved alert_cooldown_minutes to alerts.cooldown_minutes")
    if "smtp" in data:
        alerts["smtp"] = data.pop("smtp")
        changes.append("Moved smtp to alerts.smtp")
    if "webhooks" in data:
        alerts["webhooks"] = data.pop("webhooks")
        changes.append("Moved webhooks to alerts.webhooks")
    alerts.setdefault("cooldown_minutes", 15)
    alerts.setdefault("smtp", {})
    alerts.setdefault("webhooks", [])
    data["alerts"] = alerts

    data.setdefault("auth", {"enabled": False, "api_key": ""})
    data.setdefault(
        "maintenance",
        {"enabled": False, "silence_alerts": True, "message": "", "until": None},
    )

    server = data.get("server") or {}
    server.pop("config_path", None)
    server.setdefault("host", "127.0.0.1")
    server.setdefault("port", 8080)
    data["server"] = server

    default_community = snmp.get("community", "public")
    racks_in = data.get("racks") or []
    data["racks"] = [_migrate_rack(rack, default_community) for rack in racks_in]
    if any(isinstance(r, dict) and r.get("pdus") for r in racks_in):
        changes.append("Converted racks[].pdus[] to racks[].devices[] with type: pdu")
    if any(isinstance(r, dict) and r.get("description") for r in racks_in):
        changes.append("Mapped racks[].description to racks[].location")

    return data, changes


def migrate_config_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    backup: bool = True,
    dry_run: bool = False,
    migrate_secrets: bool = True,
) -> MigrationResult:
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Config file not found: {input_file}")

    output_file = Path(output_path) if output_path else input_file

    with input_file.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML mapping at the top level")

    source_format = detect_source_format(raw)
    transformed, changes = transform_to_v2(raw)
    backup_path: Path | None = None

    if dry_run:
        return MigrationResult(
            source_format=source_format,
            input_path=input_file,
            output_path=output_file,
            changes=changes,
            dry_run=True,
        )

    if backup and input_file.resolve() == output_file.resolve():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_path = input_file.with_name(f"{input_file.name}.bak.{stamp}")
        shutil.copy2(input_file, backup_path)
        changes.append(f"Backup saved to {backup_path.name}")

    save_config(output_file, transformed)
    changes.append(f"Wrote RackPulse v2 config to {output_file}")

    secrets_migrated = False
    if migrate_secrets:
        secrets_migrated = migrate_plaintext_secrets(output_file)
        if secrets_migrated:
            changes.append("Moved plaintext secrets to secrets.db ($secret in config.yaml)")

    return MigrationResult(
        source_format=source_format,
        input_path=input_file,
        output_path=output_file,
        backup_path=backup_path,
        changes=changes,
        secrets_migrated=secrets_migrated,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate-config",
        description="Migrate PDU-Power-Monitor or RackPulse v1 config.yaml to RackPulse v2",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="config.yaml",
        help="Input config file (default: config.yaml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output path (default: overwrite input file)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a .bak backup when overwriting the input file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    parser.add_argument(
        "--no-secrets",
        action="store_true",
        help="Skip moving plaintext passwords into secrets.db",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = migrate_config_file(
            args.input,
            args.output,
            backup=not args.no_backup,
            dry_run=args.dry_run,
            migrate_secrets=not args.no_secrets,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Source format: {result.source_format}")
    for line in result.changes:
        print(f"  • {line}")
    if result.dry_run:
        print("\nDry run — no files were modified.")
    elif result.backup_path:
        print(f"\nBackup: {result.backup_path}")
    print(f"Output: {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
