from __future__ import annotations

import asyncio
import csv
import io
import shlex
import subprocess

from rackpulse.collectors.base import Collector
from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.models import DeviceStatus, MetricReading


class NvidiaGpuCollector(Collector):
    """Collect GPU metrics via nvidia-smi locally or over SSH."""

    device_type = "gpu"

    async def collect(
        self,
        device: DeviceConfig,
        rack: str,
        config: AppConfig,
    ):
        try:
            output = await self._run_nvidia_smi(device)
        except FileNotFoundError:
            return self._base_reading(
                device,
                rack,
                DeviceStatus.ERROR,
                error="nvidia-smi not found on this machine",
            )
        except Exception as exc:  # noqa: BLE001
            return self._base_reading(device, rack, DeviceStatus.UNREACHABLE, error=str(exc))

        metrics = self._parse_output(output)
        if metrics.gpu_power_watts is None and metrics.gpu_util_percent is None:
            return self._base_reading(
                device,
                rack,
                DeviceStatus.ERROR,
                error="nvidia-smi returned no GPU metrics",
            )

        return self._base_reading(device, rack, DeviceStatus.OK, metrics)

    async def _run_nvidia_smi(self, device: DeviceConfig) -> str:
        query = (
            "index,name,power.draw,utilization.gpu,temperature.gpu,memory.used,memory.total"
        )
        smi_cmd = f"nvidia-smi --query-gpu={query} --format=csv,noheader,nounits"

        host = device.host.lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return await asyncio.to_thread(self._run_local, smi_cmd)

        ssh_user = device.ssh_user or device.username or "root"
        remote_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout=10 {ssh_user}@{device.host} {shlex.quote(smi_cmd)}"
        return await asyncio.to_thread(self._run_local, remote_cmd)

    @staticmethod
    def _run_local(command: str) -> str:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(stderr or f"command failed with code {result.returncode}")
        return result.stdout

    @staticmethod
    def _parse_output(output: str) -> MetricReading:
        reader = csv.reader(io.StringIO(output.strip()))
        total_power = 0.0
        max_util = 0.0
        max_temp: float | None = None
        gpu_count = 0
        gpu_details: list[dict] = []

        for row in reader:
            if len(row) < 7:
                continue
            gpu_count += 1
            index, name, power, util, temp, mem_used, mem_total = [c.strip() for c in row[:7]]
            power_f = float(power) if power and power != "[N/A]" else 0.0
            util_f = float(util) if util and util != "[N/A]" else 0.0
            temp_f = float(temp) if temp and temp != "[N/A]" else None

            total_power += power_f
            max_util = max(max_util, util_f)
            if temp_f is not None:
                max_temp = max(max_temp or temp_f, temp_f)

            gpu_details.append(
                {
                    "index": index,
                    "name": name,
                    "power_watts": power_f,
                    "util_percent": util_f,
                    "temperature_c": temp_f,
                    "memory_used_mb": mem_used,
                    "memory_total_mb": mem_total,
                }
            )

        return MetricReading(
            gpu_power_watts=round(total_power, 1) if gpu_count else None,
            gpu_util_percent=round(max_util, 1) if gpu_count else None,
            temperature_c=max_temp,
            extra={"gpus": gpu_details, "gpu_count": gpu_count},
        )
