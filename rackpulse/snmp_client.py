from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
    usmAesCfb128Protocol,
    usmAesCfb192Protocol,
    usmAesCfb256Protocol,
    usmDESPrivProtocol,
    usmHMAC128SHA224AuthProtocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMAC256SHA384AuthProtocol,
    usmHMAC384SHA512AuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
    usmNoAuthProtocol,
    usmNoPrivProtocol,
)

from rackpulse.config import DeviceConfig, SnmpDefaults, SnmpV3Config

_engine = SnmpEngine()

_AUTH_PROTOCOLS = {
    "MD5": usmHMACMD5AuthProtocol,
    "SHA": usmHMACSHAAuthProtocol,
    "SHA224": usmHMAC128SHA224AuthProtocol,
    "SHA256": usmHMAC192SHA256AuthProtocol,
    "SHA384": usmHMAC256SHA384AuthProtocol,
    "SHA512": usmHMAC384SHA512AuthProtocol,
    "NONE": usmNoAuthProtocol,
    "none": usmNoAuthProtocol,
}

_PRIV_PROTOCOLS = {
    "DES": usmDESPrivProtocol,
    "AES": usmAesCfb128Protocol,
    "AES192": usmAesCfb192Protocol,
    "AES256": usmAesCfb256Protocol,
    "NONE": usmNoPrivProtocol,
    "none": usmNoPrivProtocol,
}


@dataclass
class SnmpResult:
    success: bool
    value: float | None = None
    error: str | None = None


def _normalize_oid(oid: str) -> str:
    return oid.lstrip(".")


def _device_snmp_version(device: DeviceConfig, snmp: SnmpDefaults) -> str:
    return str(device.snmp_version or snmp.version)


def _build_usm_user(v3: SnmpV3Config) -> UsmUserData:
    level = v3.security_level
    auth_proto = _AUTH_PROTOCOLS.get(v3.auth_protocol, usmHMACSHAAuthProtocol)
    priv_proto = _PRIV_PROTOCOLS.get(v3.priv_protocol, usmAesCfb128Protocol)

    if level == "noAuthNoPriv":
        return UsmUserData(v3.username)
    if level == "authNoPriv":
        return UsmUserData(v3.username, v3.auth_password, authProtocol=auth_proto)
    return UsmUserData(
        v3.username,
        v3.auth_password,
        v3.priv_password,
        authProtocol=auth_proto,
        privProtocol=priv_proto,
    )


def _build_auth_data(device: DeviceConfig, snmp: SnmpDefaults):
    version = _device_snmp_version(device, snmp)
    if version == "3":
        return _build_usm_user(snmp.v3)
    mp_model = 1 if version == "2c" else 0
    community = device.community or snmp.community
    return CommunityData(community, mpModel=mp_model)


async def snmp_get(device: DeviceConfig, oid: str, snmp: SnmpDefaults) -> SnmpResult:
    oid = _normalize_oid(oid)
    try:
        transport = await UdpTransportTarget.create(
            (device.host, 161),
            timeout=snmp.timeout_seconds,
            retries=snmp.retries,
        )
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            _engine,
            _build_auth_data(device, snmp),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
    except Exception as exc:  # noqa: BLE001
        return SnmpResult(success=False, error=str(exc))

    if error_indication:
        return SnmpResult(success=False, error=str(error_indication))
    if error_status:
        return SnmpResult(success=False, error=str(error_status.prettyPrint()))

    for _name, val in var_binds:
        try:
            numeric = float(val)
        except (TypeError, ValueError):
            return SnmpResult(success=False, error=f"Non-numeric SNMP value: {val!r}")
        return SnmpResult(success=True, value=numeric)

    return SnmpResult(success=False, error="Empty SNMP response")
