from __future__ import annotations

from pathlib import Path

import yaml

from rackpulse.config import PollConfig, load_config


def test_poll_config_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("racks: []\n", encoding="utf-8")
    config = load_config(config_path, resolve_secrets=False)
    assert config.poll.device_concurrency == 12
    assert config.poll.bmc_concurrency == 4


def test_poll_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "poll": {
                    "device_concurrency": 20,
                    "bmc_concurrency": 6,
                },
                "racks": [],
            }
        ),
        encoding="utf-8",
    )
    config = load_config(config_path, resolve_secrets=False)
    assert config.poll == PollConfig(device_concurrency=20, bmc_concurrency=6)


def test_poll_config_minimum_one(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "poll:\n  device_concurrency: 0\n  bmc_concurrency: -3\nracks: []\n",
        encoding="utf-8",
    )
    config = load_config(config_path, resolve_secrets=False)
    assert config.poll.device_concurrency == 1
    assert config.poll.bmc_concurrency == 1
