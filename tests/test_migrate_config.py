from __future__ import annotations

from pathlib import Path

import yaml

from rackpulse.migrate_config import detect_source_format, migrate_config_file, transform_to_v2
from rackpulse.secrets import SECRET_REF, auth_secret_key


LEGACY_PDU_YAML = """
poll_interval_seconds: 60
alert_cooldown_minutes: 15
snmp:
  version: "2c"
  community: public
  power_oid: "1.3.6.1.4.1.318.1.1.26.4.3.1.5.1"
  power_divisor: 100
  energy_oid: "1.3.6.1.4.1.318.1.1.26.4.3.1.9.1"
  energy_divisor: 10
racks:
  - name: Rack A
    description: Row 1
    warning_kw: 2.5
    critical_kw: 3.0
    pdus:
      - name: PDU A1
        host: 10.0.1.11
        community: public
smtp:
  host: smtp.example.com
  password: mail-secret
  recipients: [ops@example.com]
webhooks:
  - name: Slack
    url: https://hooks.slack.com/test
    format: slack
    enabled: true
server:
  host: 0.0.0.0
  port: 8080
  config_path: config.yaml
auth:
  enabled: true
  api_key: test-api-key
"""


def test_detect_pdu_power_monitor():
    raw = yaml.safe_load(LEGACY_PDU_YAML)
    assert detect_source_format(raw) == "pdu-power-monitor"


def test_transform_legacy_to_v2():
    raw = yaml.safe_load(LEGACY_PDU_YAML)
    transformed, changes = transform_to_v2(raw)

    assert "pdu-power-monitor" in changes[0].lower() or "PDU-Power-Monitor" in changes[0]
    assert transformed["pdu"]["power_oid"] == "1.3.6.1.4.1.318.1.1.26.4.3.1.5.1"
    assert "power_oid" not in transformed["snmp"]
    assert transformed["alerts"]["smtp"]["host"] == "smtp.example.com"
    assert transformed["alerts"]["cooldown_minutes"] == 15
    assert transformed["racks"][0]["location"] == "Row 1"
    assert transformed["racks"][0]["devices"][0]["type"] == "pdu"
    assert "config_path" not in transformed["server"]


def test_migrate_config_file_writes_and_secrets(tmp_path: Path, monkeypatch):
    import os

    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "legacy.yaml"
    output_path = tmp_path / "config.yaml"
    input_path.write_text(LEGACY_PDU_YAML, encoding="utf-8")

    result = migrate_config_file(
        input_path,
        output_path,
        backup=False,
        migrate_secrets=True,
    )

    assert result.source_format == "pdu-power-monitor"
    assert result.secrets_migrated is True
    raw = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert raw["auth"]["api_key"] == SECRET_REF
    assert raw["alerts"]["smtp"]["password"] == SECRET_REF

    from rackpulse.config import load_config, open_secrets_store

    config = load_config(output_path)
    store = open_secrets_store(config)
    assert store.get(auth_secret_key()) == "test-api-key"
