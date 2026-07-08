from __future__ import annotations

from datetime import datetime, timezone

from rackpulse.config import MaintenanceConfig


def is_maintenance_active(maintenance: MaintenanceConfig) -> bool:
    if not maintenance.enabled:
        return False
    if maintenance.until:
        try:
            until = datetime.fromisoformat(maintenance.until.replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= until:
                return False
        except ValueError:
            pass
    return True


def should_silence_alerts(maintenance: MaintenanceConfig) -> bool:
    return is_maintenance_active(maintenance) and maintenance.silence_alerts
