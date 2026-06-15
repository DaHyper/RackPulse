from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SnmpV3Config:
    username: str = ""
    auth_password: str = ""
    priv_password: str = ""
    auth_protocol: str = "SHA"
    priv_protocol: str = "AES"
    security_level: str = "authPriv"


@dataclass
class SnmpDefaults:
    version: str = "2c"
    timeout_seconds: int = 5
    retries: int = 2
    community: str = "public"
    v3: SnmpV3Config = field(default_factory=SnmpV3Config)


@dataclass
class PduSnmpConfig:
    power_oid: str = "1.3.6.1.4.1.318.1.1.26.4.3.1.5.1"
    power_divisor: float = 100.0
    energy_oid: str = "1.3.6.1.4.1.318.1.1.26.4.3.1.9.1"
    energy_divisor: float = 10.0


# Backward-compatible alias
ApcSnmpConfig = PduSnmpConfig


@dataclass
class StorageConfig:
    path: str = "./data/rackpulse.db"
    retain_days: int = 90


@dataclass
class AuthConfig:
    enabled: bool = False
    api_key: str = ""
    # Future: OAuth / SSO settings


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080


@dataclass
class DeviceConfig:
    name: str
    type: str
    host: str
    community: str | None = None
    snmp_version: str | None = None
    username: str | None = None
    password: str | None = None
    verify_ssl: bool = False
    node: str | None = None
    token_id: str | None = None
    token_secret: str | None = None
    port: int | None = None
    ssh_user: str | None = None
    collect_gpu_power: bool = False
    parent: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.extra:
            return self.extra[key]
        return getattr(self, key, default)


@dataclass
class RackConfig:
    name: str
    location: str = ""
    power_cap_kw: float | None = None
    warning_kw: float | None = None
    critical_kw: float | None = None
    devices: list[DeviceConfig] = field(default_factory=list)


@dataclass
class AppConfig:
    poll_interval_seconds: int = 60
    snmp: SnmpDefaults = field(default_factory=SnmpDefaults)
    pdu: PduSnmpConfig = field(default_factory=PduSnmpConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    racks: list[RackConfig] = field(default_factory=list)


def _parse_device(data: dict[str, Any], snmp_defaults: SnmpDefaults) -> DeviceConfig:
    known = {
        "name",
        "type",
        "host",
        "community",
        "snmp_version",
        "username",
        "password",
        "verify_ssl",
        "node",
        "token_id",
        "token_secret",
        "port",
        "ssh_user",
        "collect_gpu_power",
        "parent",
    }
    extra = {k: v for k, v in data.items() if k not in known}
    return DeviceConfig(
        name=data["name"],
        type=data["type"],
        host=data["host"],
        community=data.get("community", snmp_defaults.community),
        snmp_version=data.get("snmp_version"),
        username=data.get("username"),
        password=data.get("password"),
        verify_ssl=bool(data.get("verify_ssl", False)),
        node=data.get("node"),
        token_id=data.get("token_id"),
        token_secret=data.get("token_secret"),
        port=int(data["port"]) if data.get("port") is not None else None,
        ssh_user=data.get("ssh_user"),
        collect_gpu_power=bool(data.get("collect_gpu_power", False)),
        parent=data.get("parent"),
        extra=extra,
    )


def _parse_rack(data: dict[str, Any], snmp_defaults: SnmpDefaults) -> RackConfig:
    return RackConfig(
        name=data["name"],
        location=data.get("location", data.get("description", "")),
        power_cap_kw=float(data["power_cap_kw"]) if data.get("power_cap_kw") is not None else None,
        warning_kw=float(data["warning_kw"]) if data.get("warning_kw") is not None else None,
        critical_kw=float(data["critical_kw"]) if data.get("critical_kw") is not None else None,
        devices=[_parse_device(d, snmp_defaults) for d in data.get("devices", [])],
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    snmp_raw = raw.get("snmp", {}) or {}
    v3_raw = snmp_raw.get("v3", {}) or {}
    snmp = SnmpDefaults(
        version=str(snmp_raw.get("version", "2c")),
        timeout_seconds=int(snmp_raw.get("timeout_seconds", 5)),
        retries=int(snmp_raw.get("retries", 2)),
        community=snmp_raw.get("community", "public"),
        v3=SnmpV3Config(
            username=v3_raw.get("username", ""),
            auth_password=v3_raw.get("auth_password", ""),
            priv_password=v3_raw.get("priv_password", ""),
            auth_protocol=v3_raw.get("auth_protocol", "SHA"),
            priv_protocol=v3_raw.get("priv_protocol", "AES"),
            security_level=v3_raw.get("security_level", "authPriv"),
        ),
    )

    pdu_raw = raw.get("pdu") or raw.get("apc") or {}
    pdu = PduSnmpConfig(
        power_oid=pdu_raw.get("power_oid", "1.3.6.1.4.1.318.1.1.26.4.3.1.5.1"),
        power_divisor=float(pdu_raw.get("power_divisor", 100)),
        energy_oid=pdu_raw.get("energy_oid", "1.3.6.1.4.1.318.1.1.26.4.3.1.9.1"),
        energy_divisor=float(pdu_raw.get("energy_divisor", 10)),
    )

    storage_raw = raw.get("storage", {}) or {}
    storage = StorageConfig(
        path=storage_raw.get("path", "./data/rackpulse.db"),
        retain_days=int(storage_raw.get("retain_days", 90)),
    )

    auth_raw = raw.get("auth", {}) or {}
    auth = AuthConfig(
        enabled=bool(auth_raw.get("enabled", False)),
        api_key=auth_raw.get("api_key", ""),
    )

    server_raw = raw.get("server", {}) or {}
    server = ServerConfig(
        host=server_raw.get("host", "127.0.0.1"),
        port=int(server_raw.get("port", 8080)),
    )

    return AppConfig(
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 60)),
        snmp=snmp,
        pdu=pdu,
        storage=storage,
        auth=auth,
        server=server,
        racks=[_parse_rack(r, snmp) for r in raw.get("racks", [])],
    )


def resolve_config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env_path = Path.cwd() / "config.yaml"
    if env_path.exists():
        return env_path
    example = Path.cwd() / "config.example.yaml"
    if example.exists():
        return example
    return env_path
