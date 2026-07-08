from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from rackpulse.config import AppConfig, DeviceConfig, RackConfig, load_config, open_secrets_store
from rackpulse.secrets import SECRET_REF, SecretsStore, auth_secret_key, device_secret_key, is_secret_reference, mask_value, smtp_secret_key, snmp_v3_secret_key


def _mask_placeholder(value: str | None) -> bool:
    return value in (None, "", "********")


def _device_to_dict(device: DeviceConfig, *, mask_secrets: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": device.name,
        "type": device.type,
        "host": device.host,
    }
    if device.community is not None:
        data["community"] = device.community
    if device.snmp_version is not None:
        data["snmp_version"] = device.snmp_version
    if device.username is not None:
        data["username"] = device.username
    if device.password is not None:
        if mask_secrets and device.password and not is_secret_reference(device.password):
            data["password"] = mask_value(device.password)
        elif is_secret_reference(device.password) or not mask_secrets:
            data["password"] = device.password if is_secret_reference(device.password) else SECRET_REF
        else:
            data["password"] = device.password
    if device.verify_ssl:
        data["verify_ssl"] = device.verify_ssl
    if device.node is not None:
        data["node"] = device.node
    if device.token_id is not None:
        data["token_id"] = device.token_id
    if device.token_secret is not None:
        if mask_secrets and device.token_secret and not is_secret_reference(device.token_secret):
            data["token_secret"] = mask_value(device.token_secret)
        elif is_secret_reference(device.token_secret) or not mask_secrets:
            data["token_secret"] = (
                device.token_secret if is_secret_reference(device.token_secret) else SECRET_REF
            )
        else:
            data["token_secret"] = device.token_secret
    if device.port is not None:
        data["port"] = device.port
    if device.ssh_user is not None:
        data["ssh_user"] = device.ssh_user
    if device.collect_gpu_power:
        data["collect_gpu_power"] = device.collect_gpu_power
    if device.parent is not None:
        data["parent"] = device.parent
    data.update(device.extra)
    return data


def config_to_dict(config: AppConfig, *, mask_secrets: bool = True) -> dict[str, Any]:
    store = open_secrets_store(config)
    v3_auth = config.snmp.v3.auth_password
    v3_priv = config.snmp.v3.priv_password
    if mask_secrets:
        if v3_auth and not is_secret_reference(v3_auth):
            v3_auth = mask_value(v3_auth)
        elif store.has(snmp_v3_secret_key("auth_password")):
            v3_auth = SECRET_REF
        if v3_priv and not is_secret_reference(v3_priv):
            v3_priv = mask_value(v3_priv)
        elif store.has(snmp_v3_secret_key("priv_password")):
            v3_priv = SECRET_REF

    smtp_password = config.alerts.smtp.password
    if mask_secrets:
        if store.has(smtp_secret_key()):
            smtp_password = SECRET_REF
        elif smtp_password and not is_secret_reference(smtp_password):
            smtp_password = mask_value(smtp_password)

    api_key = config.auth.api_key
    if mask_secrets:
        if store.has(auth_secret_key()):
            api_key = SECRET_REF
        elif api_key and not is_secret_reference(api_key):
            api_key = mask_value(api_key)

    racks: list[dict[str, Any]] = []
    for rack in config.racks:
        rack_dict: dict[str, Any] = {
            "name": rack.name,
            "location": rack.location,
            "devices": [],
        }
        if rack.warning_kw is not None:
            rack_dict["warning_kw"] = rack.warning_kw
        if rack.critical_kw is not None:
            rack_dict["critical_kw"] = rack.critical_kw
        if rack.power_cap_kw is not None:
            rack_dict["power_cap_kw"] = rack.power_cap_kw
        for device in rack.devices:
            dev = _device_to_dict(device, mask_secrets=mask_secrets)
            if mask_secrets:
                if store.has(device_secret_key(device.name, "password")):
                    dev["password"] = SECRET_REF
                if store.has(device_secret_key(device.name, "token_secret")):
                    dev["token_secret"] = SECRET_REF
            rack_dict["devices"].append(dev)
        racks.append(rack_dict)

    return {
        "poll_interval_seconds": config.poll_interval_seconds,
        "storage": {
            "path": config.storage.path,
            "retain_days": config.storage.retain_days,
        },
        "secrets": {
            "path": config.secrets.path,
        },
        "auth": {
            "enabled": config.auth.enabled,
            "api_key": api_key,
        },
        "server": {
            "host": config.server.host,
            "port": config.server.port,
        },
        "snmp": {
            "version": config.snmp.version,
            "timeout_seconds": config.snmp.timeout_seconds,
            "retries": config.snmp.retries,
            "community": config.snmp.community,
            "v3": {
                "username": config.snmp.v3.username,
                "auth_password": v3_auth,
                "priv_password": v3_priv,
                "auth_protocol": config.snmp.v3.auth_protocol,
                "priv_protocol": config.snmp.v3.priv_protocol,
                "security_level": config.snmp.v3.security_level,
            },
        },
        "pdu": {
            "power_oid": config.pdu.power_oid,
            "power_divisor": config.pdu.power_divisor,
            "energy_oid": config.pdu.energy_oid,
            "energy_divisor": config.pdu.energy_divisor,
        },
        "alerts": {
            "cooldown_minutes": config.alerts.cooldown_minutes,
            "smtp": {
                "host": config.alerts.smtp.host,
                "port": config.alerts.smtp.port,
                "security": config.alerts.smtp.security,
                "username": config.alerts.smtp.username,
                "password": smtp_password,
                "from_address": config.alerts.smtp.from_address,
                "recipients": list(config.alerts.smtp.recipients),
            },
            "webhooks": [
                {
                    "name": wh.name,
                    "url": wh.url,
                    "format": wh.format,
                    "enabled": wh.enabled,
                }
                for wh in config.alerts.webhooks
            ],
        },
        "maintenance": {
            "enabled": config.maintenance.enabled,
            "silence_alerts": config.maintenance.silence_alerts,
            "message": config.maintenance.message,
            "until": config.maintenance.until or None,
        },
        "racks": racks,
    }


def config_to_yaml(config: AppConfig, *, mask_secrets: bool = False) -> str:
    return yaml.safe_dump(
        config_to_dict(config, mask_secrets=mask_secrets),
        default_flow_style=False,
        sort_keys=False,
    )


def _store_secret_if_value(
    config: AppConfig,
    key: str,
    raw: str | None,
    actual: str | None,
) -> str | None:
    store = open_secrets_store(config)
    if actual and not _mask_placeholder(actual) and actual != SECRET_REF and not is_secret_reference(actual):
        store.set(key, actual)
        return SECRET_REF
    if raw == SECRET_REF or (raw and is_secret_reference(raw)):
        return raw
    if actual and _mask_placeholder(actual):
        return SECRET_REF if store.has(key) else None
    return actual


def _normalize_device_secrets(config: AppConfig, device_data: dict[str, Any]) -> dict[str, Any]:
    name = device_data["name"]
    result = dict(device_data)
    for field in ("password", "token_secret"):
        if field not in result:
            continue
        value = result[field]
        if _mask_placeholder(value):
            result.pop(field, None)
            if open_secrets_store(config).has(device_secret_key(name, field)):
                result[field] = SECRET_REF
            continue
        result[field] = _store_secret_if_value(
            config,
            device_secret_key(name, field),
            value if isinstance(value, str) else None,
            value if isinstance(value, str) else None,
        )
    return result


def normalize_secrets_in_raw(config: AppConfig, raw: dict[str, Any]) -> dict[str, Any]:
    """Move plaintext secret fields into the secrets DB; config stores $secret refs."""
    data = copy.deepcopy(raw)
    store = open_secrets_store(config)

    for rack in data.get("racks", []):
        devices = rack.get("devices", rack.get("pdus", []))
        normalized = []
        for device in devices:
            if "type" not in device:
                device = {**device, "type": "pdu"}
            normalized.append(_normalize_device_secrets(config, device))
        rack["devices"] = normalized
        rack.pop("pdus", None)

    alerts = data.setdefault("alerts", {})
    smtp = alerts.setdefault("smtp", data.pop("smtp", None) or {})
    if smtp.get("password") and not _mask_placeholder(smtp["password"]):
        smtp["password"] = _store_secret_if_value(
            config,
            smtp_secret_key(),
            smtp.get("password"),
            smtp.get("password"),
        )

    snmp = data.setdefault("snmp", {})
    v3 = snmp.setdefault("v3", {})
    for field in ("auth_password", "priv_password"):
        if field in v3 and not _mask_placeholder(v3[field]):
            v3[field] = _store_secret_if_value(
                config,
                snmp_v3_secret_key(field),
                v3.get(field),
                v3.get(field),
            )

    auth = data.setdefault("auth", {})
    if auth.get("api_key") and not _mask_placeholder(auth["api_key"]):
        auth["api_key"] = _store_secret_if_value(
            config,
            auth_secret_key(),
            auth.get("api_key"),
            auth.get("api_key"),
        )

    if "alert_cooldown_minutes" in data and "cooldown_minutes" not in alerts:
        alerts["cooldown_minutes"] = data.pop("alert_cooldown_minutes")

    return data


def save_config(path: str | Path, data: dict[str, Any]) -> AppConfig:
    config_path = Path(path)
    preview = load_config(config_path, resolve_secrets=False) if config_path.exists() else AppConfig()

    secrets_raw = data.get("secrets", {}) or {}
    if secrets_raw.get("path"):
        preview.secrets.path = secrets_raw["path"]
    storage_raw = data.get("storage", {}) or {}
    if storage_raw.get("path"):
        preview.storage.path = storage_raw["path"]
        if not secrets_raw.get("path"):
            from rackpulse.config import default_secrets_path

            preview.secrets.path = default_secrets_path(storage_raw["path"])

    normalized = normalize_secrets_in_raw(preview, data)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(normalized, handle, default_flow_style=False, sort_keys=False)
    return load_config(config_path)


def merge_config_update(current: AppConfig, update: dict[str, Any]) -> dict[str, Any]:
    merged = config_to_dict(current, mask_secrets=False)
    deep = copy.deepcopy(update)

    if "poll_interval_seconds" in deep:
        merged["poll_interval_seconds"] = deep["poll_interval_seconds"]

    alerts_update = deep.pop("alerts", None)
    if alerts_update:
        if "cooldown_minutes" in alerts_update:
            merged.setdefault("alerts", {})["cooldown_minutes"] = alerts_update["cooldown_minutes"]
        if "smtp" in alerts_update:
            smtp_update = alerts_update["smtp"]
            if _mask_placeholder(smtp_update.get("password")):
                smtp_update.pop("password", None)
            merged.setdefault("alerts", {}).setdefault("smtp", {}).update(smtp_update)
        if "webhooks" in alerts_update:
            merged.setdefault("alerts", {})["webhooks"] = alerts_update["webhooks"]

    for legacy_key, target in (
        ("alert_cooldown_minutes", ("alerts", "cooldown_minutes")),
        ("smtp", ("alerts", "smtp")),
        ("webhooks", ("alerts", "webhooks")),
    ):
        if legacy_key in deep:
            value = deep.pop(legacy_key)
            if legacy_key == "smtp" and isinstance(value, dict):
                if _mask_placeholder(value.get("password")):
                    value.pop("password", None)
            if legacy_key == "alert_cooldown_minutes":
                merged.setdefault("alerts", {})["cooldown_minutes"] = value
            elif legacy_key == "webhooks":
                merged.setdefault("alerts", {})["webhooks"] = value
            else:
                merged.setdefault("alerts", {}).setdefault("smtp", {}).update(value)

    if "snmp" in deep:
        snmp_update = deep["snmp"]
        if "v3" in snmp_update:
            v3_update = snmp_update["v3"]
            if _mask_placeholder(v3_update.get("auth_password")):
                v3_update.pop("auth_password", None)
            if _mask_placeholder(v3_update.get("priv_password")):
                v3_update.pop("priv_password", None)
            merged["snmp"].setdefault("v3", {}).update(v3_update)
            del snmp_update["v3"]
        merged["snmp"].update(snmp_update)

    if "pdu" in deep:
        merged["pdu"].update(deep["pdu"])

    if "storage" in deep:
        merged["storage"].update(deep["storage"])

    if "auth" in deep:
        auth_update = deep["auth"]
        if _mask_placeholder(auth_update.get("api_key")):
            auth_update.pop("api_key", None)
        merged["auth"].update(auth_update)

    if "maintenance" in deep:
        merged["maintenance"].update(deep["maintenance"])

    if "server" in deep:
        merged["server"].update(deep["server"])

    if "racks" in deep:
        merged["racks"] = deep["racks"]

    return merged
