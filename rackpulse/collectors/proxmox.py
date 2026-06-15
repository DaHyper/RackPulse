from __future__ import annotations

import httpx

from rackpulse.collectors.base import Collector
from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.models import DeviceStatus, MetricReading

# Resolved PVE node name per API endpoint (host:port).
_node_cache: dict[str, str] = {}


class ProxmoxCollector(Collector):
    device_type = "pve"
    default_port = 8006

    async def collect(
        self,
        device: DeviceConfig,
        rack: str,
        config: AppConfig,
    ):
        if not device.token_id or not device.token_secret:
            return self._base_reading(
                device,
                rack,
                DeviceStatus.ERROR,
                error="token_id and token_secret required for PVE API",
            )

        port = device.port or self.default_port
        base_url = f"https://{device.host}:{port}/api2/json"
        headers = {"Authorization": f"PVEAPIToken={device.token_id}={device.token_secret}"}
        cache_key = f"{device.host}:{port}"

        try:
            async with httpx.AsyncClient(
                verify=device.verify_ssl, timeout=20.0, follow_redirects=True
            ) as client:
                if device.node:
                    node = device.node
                elif cache_key in _node_cache:
                    node = _node_cache[cache_key]
                else:
                    node = await self._detect_node(client, base_url, headers, device.host)
                    _node_cache[cache_key] = node

                node_status = await self._get_json(
                    client, f"{base_url}/nodes/{node}/status", headers
                )
                cpu_percent, ram_percent = self._node_utilization(node_status)
                if cpu_percent is None or ram_percent is None:
                    nodes_payload = await self._get_json(client, f"{base_url}/nodes", headers)
                    for entry in nodes_payload.get("data", []):
                        if entry.get("node") != node:
                            continue
                        fb_cpu, fb_ram = self._node_utilization({"data": entry})
                        if cpu_percent is None:
                            cpu_percent = fb_cpu
                        if ram_percent is None:
                            ram_percent = fb_ram
                        break
        except httpx.HTTPError as exc:
            return self._base_reading(device, rack, DeviceStatus.UNREACHABLE, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._base_reading(device, rack, DeviceStatus.ERROR, error=str(exc))

        data = node_status.get("data", node_status)
        extra: dict = {"node": node, "uptime": data.get("uptime")}
        gpu_power_watts = None
        gpu_util_percent = None
        temperature_c = None

        if device.collect_gpu_power:
            from rackpulse.collectors.nvidia_gpu import NvidiaGpuCollector

            gpu_reading = await NvidiaGpuCollector().collect(device, rack, config)
            if gpu_reading.status == DeviceStatus.OK:
                gpu_power_watts = gpu_reading.metrics.gpu_power_watts
                gpu_util_percent = gpu_reading.metrics.gpu_util_percent
                temperature_c = gpu_reading.metrics.temperature_c
                extra["gpu_power_source"] = "nvidia-smi"
                if gpu_reading.metrics.extra.get("gpus"):
                    extra["gpus"] = gpu_reading.metrics.extra["gpus"]
            elif gpu_reading.error:
                extra["gpu_power_error"] = gpu_reading.error

        reading = self._base_reading(
            device,
            rack,
            DeviceStatus.OK,
            MetricReading(
                cpu_percent=cpu_percent,
                ram_percent=ram_percent,
                temperature_c=temperature_c,
                gpu_power_watts=gpu_power_watts,
                gpu_util_percent=gpu_util_percent,
                extra=extra,
            ),
        )
        return reading

    @staticmethod
    def _node_utilization(payload: dict) -> tuple[float | None, float | None]:
        data = payload.get("data", payload)
        cpu = data.get("cpu")
        mem = data.get("memory") if data.get("memory") is not None else data.get("mem")
        maxmem = data.get("maxmem")

        cpu_percent = round(float(cpu) * 100, 1) if cpu is not None else None
        ram_percent = None
        if mem is not None and maxmem:
            ram_percent = round(float(mem) / float(maxmem) * 100, 1)

        return cpu_percent, ram_percent

    async def _detect_node(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict[str, str],
        host: str,
    ) -> str:
        payload = await self._get_json(client, f"{base_url}/nodes", headers)
        nodes = payload.get("data", [])
        if not nodes:
            raise ValueError("No PVE nodes found")

        online = [n for n in nodes if n.get("status") == "online"]
        candidates = online or nodes

        if len(candidates) == 1:
            return candidates[0]["node"]

        matched = await self._find_node_by_host(client, base_url, headers, host, candidates)
        if matched:
            return matched

        names = ", ".join(n["node"] for n in candidates)
        raise ValueError(
            f"Could not match PVE node to host {host}. "
            f"Online nodes: {names}. Set node: in config to override."
        )

    async def _find_node_by_host(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict[str, str],
        host: str,
        candidates: list[dict],
    ) -> str | None:
        host = host.lower()
        for entry in candidates:
            node = entry["node"]
            payload = await self._get_json(client, f"{base_url}/nodes/{node}/network", headers)
            for iface in payload.get("data", []):
                for key in ("address", "cidr"):
                    value = iface.get(key)
                    if not value:
                        continue
                    address = value.split("/")[0].lower()
                    if address == host:
                        return node
        return None

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
    ) -> dict:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
