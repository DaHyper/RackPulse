from __future__ import annotations

import httpx

from rackpulse.collectors.base import Collector
from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.models import DeviceStatus, MetricReading, VmReading


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

        try:
            async with httpx.AsyncClient(verify=device.verify_ssl, timeout=20.0) as client:
                node = device.node or await self._detect_node(client, base_url, headers)
                node_status = await self._get_json(
                    client, f"{base_url}/nodes/{node}/status", headers
                )
                vms = await self._collect_vms(client, base_url, headers, node, device.name)
        except httpx.HTTPError as exc:
            return self._base_reading(device, rack, DeviceStatus.UNREACHABLE, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._base_reading(device, rack, DeviceStatus.ERROR, error=str(exc))

        data = node_status.get("data", node_status)
        cpu = data.get("cpu")
        mem = data.get("memory")
        maxmem = data.get("maxmem")

        cpu_percent = round(float(cpu) * 100, 1) if cpu is not None else None
        ram_percent = None
        if mem is not None and maxmem:
            ram_percent = round(float(mem) / float(maxmem) * 100, 1)

        reading = self._base_reading(
            device,
            rack,
            DeviceStatus.OK,
            MetricReading(
                cpu_percent=cpu_percent,
                ram_percent=ram_percent,
                extra={"node": node, "uptime": data.get("uptime")},
            ),
        )
        reading.vms = vms
        return reading

    async def _detect_node(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict[str, str],
    ) -> str:
        payload = await self._get_json(client, f"{base_url}/nodes", headers)
        nodes = payload.get("data", [])
        if not nodes:
            raise ValueError("No PVE nodes found")
        return nodes[0]["node"]

    async def _collect_vms(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict[str, str],
        node: str,
        host_device: str,
    ) -> list[VmReading]:
        payload = await self._get_json(
            client,
            f"{base_url}/nodes/{node}/qemu",
            headers,
        )
        vms: list[VmReading] = []
        for vm in payload.get("data", []):
            vmid = int(vm["vmid"])
            name = vm.get("name", f"vm-{vmid}")
            cpu_percent = None
            if vm.get("cpu") is not None:
                cpu_percent = round(float(vm["cpu"]) * 100, 1)

            ram_percent = None
            if vm.get("mem") is not None and vm.get("maxmem"):
                ram_percent = round(float(vm["mem"]) / float(vm["maxmem"]) * 100, 1)

            vms.append(
                VmReading(
                    vmid=vmid,
                    name=name,
                    host=host_device,
                    cpu_percent=cpu_percent,
                    ram_percent=ram_percent,
                    status=vm.get("status"),
                )
            )
        return vms

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
    ) -> dict:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
