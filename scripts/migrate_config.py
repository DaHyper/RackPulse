#!/usr/bin/env python3
"""Migrate PDU-Power-Monitor or RackPulse v1 config.yaml to RackPulse v2.

Usage:
  python scripts/migrate_config.py
  python scripts/migrate_config.py /path/to/old-config.yaml
  python scripts/migrate_config.py old.yaml -o config.yaml
  python scripts/migrate_config.py --dry-run config.yaml
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running without `pip install -e .`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rackpulse.migrate_config import main

if __name__ == "__main__":
    raise SystemExit(main())
