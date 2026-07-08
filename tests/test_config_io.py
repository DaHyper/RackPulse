from __future__ import annotations

from pathlib import Path

import yaml

from rackpulse.config import load_config
from rackpulse.config_io import config_to_dict, merge_config_update, save_config
from rackpulse.secrets import SECRET_REF, SecretsStore, device_secret_key


def test_config_save_round_trip_stores_secrets(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    secrets_path = tmp_path / "secrets.db"
    config_path.write_text(
        yaml.safe_dump(
            {
                "storage": {"path": str(tmp_path / "rackpulse.db")},
                "secrets": {"path": str(secrets_path)},
                "racks": [
                    {
                        "name": "rack-1",
                        "warning_kw": 4.0,
                        "critical_kw": 5.0,
                        "devices": [
                            {
                                "name": "hp-server",
                                "type": "hp_server",
                                "host": "10.0.0.20",
                                "username": "admin",
                                "password": "super-secret",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(config_path)
    assert loaded.racks[0].devices[0].password == "super-secret"

    save_config(
        config_path,
        merge_config_update(
            loaded,
            {
                "racks": [
                    {
                        "name": "rack-1",
                        "location": "row 1",
                        "warning_kw": 4.0,
                        "critical_kw": 5.0,
                        "devices": [
                            {
                                "name": "hp-server",
                                "type": "hp_server",
                                "host": "10.0.0.20",
                                "username": "admin",
                                "password": "super-secret",
                            }
                        ],
                    }
                ]
            },
        ),
    )

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["racks"][0]["devices"][0]["password"] == SECRET_REF

    store = SecretsStore(secrets_path)
    assert store.get(device_secret_key("hp-server", "password")) == "super-secret"

    reloaded = load_config(config_path)
    assert reloaded.racks[0].devices[0].password == "super-secret"


def test_config_export_masks_secrets(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    secrets_path = tmp_path / "secrets.db"
    save_config(
        config_path,
        {
            "storage": {"path": str(tmp_path / "rackpulse.db")},
            "secrets": {"path": str(secrets_path)},
            "alerts": {
                "smtp": {
                    "host": "smtp.example.com",
                    "password": "mail-secret",
                    "recipients": ["ops@example.com"],
                }
            },
            "racks": [],
        },
    )
    config = load_config(config_path)
    exported = config_to_dict(config, mask_secrets=True)
    assert exported["alerts"]["smtp"]["password"] == SECRET_REF
