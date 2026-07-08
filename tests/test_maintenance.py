from __future__ import annotations

from datetime import datetime, timedelta, timezone

from rackpulse.config import MaintenanceConfig
from rackpulse.maintenance import is_maintenance_active, should_silence_alerts


def test_maintenance_expires():
    until = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    maintenance = MaintenanceConfig(enabled=True, until=until)
    assert is_maintenance_active(maintenance) is False


def test_maintenance_silences_alerts():
    maintenance = MaintenanceConfig(enabled=True, silence_alerts=True, message="work")
    assert should_silence_alerts(maintenance) is True


def test_maintenance_without_silence():
    maintenance = MaintenanceConfig(enabled=True, silence_alerts=False)
    assert should_silence_alerts(maintenance) is False
