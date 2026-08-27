from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from rackpulse.secrets import (
    SECRET_REF,
    SecretsStore,
    auth_secret_key,
    device_secret_key,
    resolve_secret_value,
    smtp_secret_key,
    snmp_v3_secret_key,
)


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


ApcSnmpConfig = PduSnmpConfig


@dataclass
class StorageConfig:
    path: str = "./data/rackpulse.db"
    retain_days: int = 90


@dataclass
class SecretsConfig:
    path: str = "./data/secrets.db"


@dataclass
class AuthConfig:
    enabled: bool = False
    api_key: str = ""


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080


@dataclass
class SmtpConfig:
    host: str = ""
    port: int = 587
    security: str = "tls"
    username: str = ""
    password: str = ""
    from_address: str = ""
    recipients: list[str] = field(default_factory=list)


@dataclass
class WebhookConfig:
    name: str = ""
    url: str = ""
    format: str = "generic"
    enabled: bool = True


@dataclass
class AlertsConfig:
    cooldown_minutes: int = 15
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    webhooks: list[WebhookConfig] = field(default_factory=list)


@dataclass
class MaintenanceConfig:
    enabled: bool = False
    silence_alerts: bool = True
    message: str = ""
    until: str = ""


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
class PollConfig:
    """Controls how aggressively RackPulse polls devices in parallel."""

    device_concurrency: int = 12
    bmc_concurrency: int = 4


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
    poll: PollConfig = field(default_factory=PollConfig)
    snmp: SnmpDefaults = field(default_factory=SnmpDefaults)
    pdu: PduSnmpConfig = field(default_factory=PduSnmpConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    maintenance: MaintenanceConfig = field(default_factory=MaintenanceConfig)
    racks: list[RackConfig] = field(default_factory=list)


def default_secrets_path(storage_path: str) -> str:
    return str(Path(storage_path).parent / "secrets.db")


def open_secrets_store(config: AppConfig) -> SecretsStore:
    path = config.secrets.path or default_secrets_path(config.storage.path)
    return SecretsStore(path)


def _parse_smtp(data: dict[str, Any] | None) -> SmtpConfig:
    data = data or {}
    recipients = data.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]
    return SmtpConfig(
        host=data.get("host", ""),
        port=int(data.get("port", 587)),
        security=data.get("security", "tls"),
        username=data.get("username", ""),
        password=data.get("password", ""),
        from_address=data.get("from_address", ""),
        recipients=list(recipients),
    )


def _parse_webhook(data: dict[str, Any]) -> WebhookConfig:
    return WebhookConfig(
        name=data.get("name", ""),
        url=data.get("url", ""),
        format=data.get("format", "generic"),
        enabled=bool(data.get("enabled", True)),
    )


def _parse_alerts(raw: dict[str, Any]) -> AlertsConfig:
    alerts_raw = raw.get("alerts", {}) or {}
    cooldown = alerts_raw.get("cooldown_minutes", raw.get("alert_cooldown_minutes", 15))
    smtp_raw = alerts_raw.get("smtp", raw.get("smtp", {})) or {}
    webhooks_raw = alerts_raw.get("webhooks", raw.get("webhooks", [])) or []
    return AlertsConfig(
        cooldown_minutes=int(cooldown),
        smtp=_parse_smtp(smtp_raw),
        webhooks=[_parse_webhook(w) for w in webhooks_raw],
    )


def _parse_maintenance(data: dict[str, Any] | None) -> MaintenanceConfig:
    data = data or {}
    return MaintenanceConfig(
        enabled=bool(data.get("enabled", False)),
        silence_alerts=bool(data.get("silence_alerts", True)),
        message=data.get("message", ""),
        until=data.get("until") or "",
    )


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
    device_type = data.get("type", "pdu")
    return DeviceConfig(
        name=data["name"],
        type=device_type,
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
    devices_raw = data.get("devices")
    if devices_raw is None:
        devices_raw = [
            {**pdu, "type": "pdu"} for pdu in data.get("pdus", [])
        ]
    return RackConfig(
        name=data["name"],
        location=data.get("location", data.get("description", "")),
        power_cap_kw=float(data["power_cap_kw"]) if data.get("power_cap_kw") is not None else None,
        warning_kw=float(data["warning_kw"]) if data.get("warning_kw") is not None else None,
        critical_kw=float(data["critical_kw"]) if data.get("critical_kw") is not None else None,
        devices=[_parse_device(d, snmp_defaults) for d in devices_raw],
    )


def _resolve_device_secrets(device: DeviceConfig, store: SecretsStore | None) -> DeviceConfig:
    password = resolve_secret_value(
        device.password,
        device_secret_key(device.name, "password"),
        store,
    )
    token_secret = resolve_secret_value(
        device.token_secret,
        device_secret_key(device.name, "token_secret"),
        store,
    )
    return DeviceConfig(
        name=device.name,
        type=device.type,
        host=device.host,
        community=device.community,
        snmp_version=device.snmp_version,
        username=device.username,
        password=password,
        verify_ssl=device.verify_ssl,
        node=device.node,
        token_id=device.token_id,
        token_secret=token_secret,
        port=device.port,
        ssh_user=device.ssh_user,
        collect_gpu_power=device.collect_gpu_power,
        parent=device.parent,
        extra=device.extra,
    )


def _resolve_config_secrets(config: AppConfig, store: SecretsStore | None) -> AppConfig:
    v3 = config.snmp.v3
    resolved_v3 = SnmpV3Config(
        username=v3.username,
        auth_password=resolve_secret_value(
            v3.auth_password,
            snmp_v3_secret_key("auth_password"),
            store,
        )
        or "",
        priv_password=resolve_secret_value(
            v3.priv_password,
            snmp_v3_secret_key("priv_password"),
            store,
        )
        or "",
        auth_protocol=v3.auth_protocol,
        priv_protocol=v3.priv_protocol,
        security_level=v3.security_level,
    )
    snmp = SnmpDefaults(
        version=config.snmp.version,
        timeout_seconds=config.snmp.timeout_seconds,
        retries=config.snmp.retries,
        community=config.snmp.community,
        v3=resolved_v3,
    )
    smtp = config.alerts.smtp
    resolved_smtp = SmtpConfig(
        host=smtp.host,
        port=smtp.port,
        security=smtp.security,
        username=smtp.username,
        password=resolve_secret_value(smtp.password, smtp_secret_key(), store) or "",
        from_address=smtp.from_address,
        recipients=list(smtp.recipients),
    )
    auth = config.auth
    resolved_auth = AuthConfig(
        enabled=auth.enabled,
        api_key=resolve_secret_value(auth.api_key, auth_secret_key(), store) or "",
    )
    racks = [
        RackConfig(
            name=rack.name,
            location=rack.location,
            power_cap_kw=rack.power_cap_kw,
            warning_kw=rack.warning_kw,
            critical_kw=rack.critical_kw,
            devices=[_resolve_device_secrets(device, store) for device in rack.devices],
        )
        for rack in config.racks
    ]
    return AppConfig(
        poll_interval_seconds=config.poll_interval_seconds,
        poll=config.poll,
        snmp=snmp,
        pdu=config.pdu,
        storage=config.storage,
        secrets=config.secrets,
        auth=resolved_auth,
        server=config.server,
        alerts=AlertsConfig(
            cooldown_minutes=config.alerts.cooldown_minutes,
            smtp=resolved_smtp,
            webhooks=list(config.alerts.webhooks),
        ),
        maintenance=config.maintenance,
        racks=racks,
    )


def load_config(path: str | Path, *, resolve_secrets: bool = True) -> AppConfig:
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

    secrets_raw = raw.get("secrets", {}) or {}
    secrets = SecretsConfig(
        path=secrets_raw.get("path", default_secrets_path(storage.path)),
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

    poll_raw = raw.get("poll", {}) or {}
    poll = PollConfig(
        device_concurrency=max(1, int(poll_raw.get("device_concurrency", 12))),
        bmc_concurrency=max(1, int(poll_raw.get("bmc_concurrency", 4))),
    )

    config = AppConfig(
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 60)),
        poll=poll,
        snmp=snmp,
        pdu=pdu,
        storage=storage,
        secrets=secrets,
        auth=auth,
        server=server,
        alerts=_parse_alerts(raw),
        maintenance=_parse_maintenance(raw.get("maintenance")),
        racks=[_parse_rack(r, snmp) for r in raw.get("racks", [])],
    )

    if not resolve_secrets:
        return config

    store = open_secrets_store(config)
    return _resolve_config_secrets(config, store)


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
