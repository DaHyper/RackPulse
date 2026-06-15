from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from rackpulse.models import DeviceReading, PollSnapshot, VmReading


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    rack TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    host TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS power_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name TEXT NOT NULL,
                    rack TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    watts REAL
                );

                CREATE INDEX IF NOT EXISTS idx_power_samples_device_time
                    ON power_samples (device_name, timestamp);

                CREATE TABLE IF NOT EXISTS device_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name TEXT NOT NULL,
                    rack TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    cpu_percent REAL,
                    ram_percent REAL,
                    temperature_c REAL,
                    extra_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_device_metrics_device_time
                    ON device_metrics (device_name, timestamp);

                CREATE TABLE IF NOT EXISTS vm_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vmid INTEGER NOT NULL,
                    vm_name TEXT NOT NULL,
                    host_device TEXT NOT NULL,
                    rack TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    cpu_percent REAL,
                    ram_percent REAL,
                    status TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_vm_metrics_host_time
                    ON vm_metrics (host_device, timestamp);

                CREATE TABLE IF NOT EXISTS power_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name TEXT NOT NULL,
                    rack TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    watts REAL,
                    volts REAL,
                    amps REAL
                );

                CREATE INDEX IF NOT EXISTS idx_power_metrics_device_time
                    ON power_metrics (device_name, timestamp);
                """
            )

    def upsert_devices_from_snapshot(self, snapshot: PollSnapshot) -> None:
        with self._connect() as conn:
            for rack in snapshot.racks:
                for device in rack.devices:
                    conn.execute(
                        """
                        INSERT INTO devices (name, rack, device_type, host, active)
                        VALUES (?, ?, ?, ?, 1)
                        ON CONFLICT(name) DO UPDATE SET
                            rack = excluded.rack,
                            device_type = excluded.device_type,
                            host = excluded.host,
                            active = 1
                        """,
                        (device.name, rack.name, device.device_type, device.host),
                    )

    def save_snapshot(self, snapshot: PollSnapshot) -> None:
        if snapshot.last_poll is None:
            return

        ts = snapshot.last_poll.isoformat()
        self.upsert_devices_from_snapshot(snapshot)

        with self._connect() as conn:
            for rack in snapshot.racks:
                for device in rack.devices:
                    if device.status.value not in ("ok", "stale"):
                        continue

                    watts = device.power_watts
                    if watts is not None:
                        conn.execute(
                            """
                            INSERT INTO power_samples (device_name, rack, timestamp, watts)
                            VALUES (?, ?, ?, ?)
                            """,
                            (device.name, rack.name, ts, watts),
                        )
                        if metrics.volts is not None or metrics.amps is not None:
                            conn.execute(
                                """
                                INSERT INTO power_metrics
                                    (device_name, rack, timestamp, watts, volts, amps)
                                VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    device.name,
                                    rack.name,
                                    ts,
                                    watts,
                                    metrics.volts,
                                    metrics.amps,
                                ),
                            )

                    metrics = device.metrics
                    if any(
                        v is not None
                        for v in (
                            metrics.cpu_percent,
                            metrics.ram_percent,
                            metrics.temperature_c,
                        )
                    ):
                        conn.execute(
                            """
                            INSERT INTO device_metrics
                                (device_name, rack, timestamp, cpu_percent, ram_percent, temperature_c, extra_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                device.name,
                                rack.name,
                                ts,
                                metrics.cpu_percent,
                                metrics.ram_percent,
                                metrics.temperature_c,
                                None,
                            ),
                        )

                    for vm in device.vms:
                        conn.execute(
                            """
                            INSERT INTO vm_metrics
                                (vmid, vm_name, host_device, rack, timestamp, cpu_percent, ram_percent, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                vm.vmid,
                                vm.name,
                                device.name,
                                rack.name,
                                ts,
                                vm.cpu_percent,
                                vm.ram_percent,
                                vm.status,
                            ),
                        )

    def prune_old_data(self, retain_days: int) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).isoformat()
        with self._connect() as conn:
            for table in ("power_samples", "device_metrics", "vm_metrics", "power_metrics"):
                conn.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,))

    def recent_power_by_rack(self, rack: str, hours: float = 24) -> list[tuple[str, float]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, SUM(watts) AS total_watts
                FROM power_samples
                WHERE rack = ? AND timestamp >= ?
                GROUP BY timestamp
                ORDER BY timestamp
                """,
                (rack, cutoff),
            ).fetchall()
        return [(row["timestamp"], row["total_watts"]) for row in rows]

    def top_power_devices(self, limit: int = 10) -> list[tuple[str, str, float]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT device_name, rack, watts
                FROM power_samples p
                INNER JOIN (
                    SELECT device_name, MAX(timestamp) AS max_ts
                    FROM power_samples
                    GROUP BY device_name
                ) latest ON p.device_name = latest.device_name AND p.timestamp = latest.max_ts
                ORDER BY watts DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [(row["device_name"], row["rack"], row["watts"]) for row in rows]

    def device_power_history(
        self,
        device_name: str,
        hours: float = 24,
    ) -> list[dict[str, float | str | None]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, watts, volts, amps
                FROM power_metrics
                WHERE device_name = ? AND timestamp >= ?
                ORDER BY timestamp
                """,
                (device_name, cutoff),
            ).fetchall()
        if rows:
            return [
                {
                    "timestamp": row["timestamp"],
                    "watts": row["watts"],
                    "volts": row["volts"],
                    "amps": row["amps"],
                }
                for row in rows
            ]

        rows = conn.execute(
            """
            SELECT timestamp, watts
            FROM power_samples
            WHERE device_name = ? AND timestamp >= ?
            ORDER BY timestamp
            """,
            (device_name, cutoff),
        ).fetchall()
        return [{"timestamp": row["timestamp"], "watts": row["watts"], "volts": None, "amps": None} for row in rows]

    def latest_power_metric(self, device_name: str) -> dict[str, float | str | None] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT timestamp, watts, volts, amps
                FROM power_metrics
                WHERE device_name = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (device_name,),
            ).fetchone()
        if row:
            return {
                "timestamp": row["timestamp"],
                "watts": row["watts"],
                "volts": row["volts"],
                "amps": row["amps"],
            }
        row = conn.execute(
            """
            SELECT timestamp, watts
            FROM power_samples
            WHERE device_name = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (device_name,),
        ).fetchone()
        if not row:
            return None
        return {"timestamp": row["timestamp"], "watts": row["watts"], "volts": None, "amps": None}
