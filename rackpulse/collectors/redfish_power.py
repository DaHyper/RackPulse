from __future__ import annotations

import httpx

from rackpulse.collectors.base import Collector
from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.models import DeviceStatus, MetricReading


class RedfishPowerCollector(Collector):
    """Collect power and health from Redfish BMC endpoints."""

    device_type = "redfish"
    default_port = 443

    async def collect(
        self,
        device: DeviceConfig,
        rack: str,
        config: AppConfig,
    ):
        if not device.username or not device.password:
            return self._base_reading(
                device,
                rack,
                DeviceStatus.ERROR,
                error="username and password required for Redfish",
            )

        port = device.port or self.default_port
        base_url = f"https://{device.host}:{port}"
        auth = (device.username, device.password)

        try:
            async with httpx.AsyncClient(
                verify=device.verify_ssl, timeout=15.0, follow_redirects=True
            ) as client:
                power_watts, temperature_c, extra = await self._read_power(client, base_url, auth)
        except httpx.HTTPError as exc:
            return self._base_reading(device, rack, DeviceStatus.UNREACHABLE, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._base_reading(device, rack, DeviceStatus.ERROR, error=str(exc))

        return self._base_reading(
            device,
            rack,
            DeviceStatus.OK,
            MetricReading(
                power_watts=power_watts,
                temperature_c=temperature_c,
                extra=extra,
            ),
        )

    async def _read_power(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        auth: tuple[str, str],
    ) -> tuple[float | None, float | None, dict]:
        power_watts: float | None = None
        temperature_c: float | None = None
        extra: dict = {}

        # Common chassis power endpoint paths across BMC vendors
        power_paths = [
            "/redfish/v1/Chassis/1/Power",
            "/redfish/v1/Chassis/System.Embedded.1/Power",
        ]

        for path in power_paths:
            response = await client.get(f"{base_url}{path}", auth=auth)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            data = response.json()

            for control in data.get("PowerControl", []):
                consumed = control.get("PowerConsumedWatts")
                if consumed is not None:
                    power_watts = float(consumed)
                    break

            for psu in data.get("PowerSupplies", []):
                status = psu.get("Status", {})
                extra.setdefault("power_supplies", []).append(
                    {
                        "name": psu.get("Name"),
                        "health": status.get("Health"),
                        "state": status.get("State"),
                    }
                )

            break

        if power_watts is None:
            # Fallback: sum PowerSupplies LastPowerOutputWatts
            for path in power_paths:
                response = await client.get(f"{base_url}{path}", auth=auth)
                if response.status_code != 200:
                    continue
                data = response.json()
                outputs = [
                    float(psu["LastPowerOutputWatts"])
                    for psu in data.get("PowerSupplies", [])
                    if psu.get("LastPowerOutputWatts") is not None
                ]
                if outputs:
                    power_watts = round(sum(outputs), 1)
                    break

        # Temperature from thermal subsystem
        thermal_paths = [
            "/redfish/v1/Chassis/1/Thermal",
            "/redfish/v1/Chassis/System.Embedded.1/Thermal",
        ]
        for path in thermal_paths:
            response = await client.get(f"{base_url}{path}", auth=auth)
            if response.status_code == 404:
                continue
            if response.status_code == 200:
                data = response.json()
                temps = [
                    float(r["ReadingCelsius"])
                    for r in data.get("Temperatures", [])
                    if r.get("ReadingCelsius") is not None
                ]
                if temps:
                    temperature_c = round(max(temps), 1)
                break

        if power_watts is None:
            raise ValueError("Could not read power from Redfish endpoints")

        return power_watts, temperature_c, extra


class HpServerCollector(RedfishPowerCollector):
    device_type = "hp_server"


class DellServerCollector(RedfishPowerCollector):
    device_type = "dell_server"


class LenovoServerCollector(RedfishPowerCollector):
    device_type = "lenovo_server"


# Backward-compatible aliases
HpIloCollector = HpServerCollector
DellIdracCollector = DellServerCollector
