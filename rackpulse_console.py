"""Console entry point with editable-install path bootstrap."""
from __future__ import annotations

import re
import site
import sys
from pathlib import Path


def _ensure_rackpulse_on_path() -> None:
    try:
        import rackpulse  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    for site_dir in site.getsitepackages():
        base = Path(site_dir)

        root_pth = base / "rackpulse-root.pth"
        if root_pth.is_file():
            root = Path(root_pth.read_text(encoding="utf-8").strip())
            if (root / "rackpulse" / "__init__.py").is_file():
                sys.path.insert(0, str(root))
                return

        for finder in base.glob("__editable___rackpulse_*_finder.py"):
            match = re.search(r"'rackpulse': '([^']+)'", finder.read_text(encoding="utf-8"))
            if not match:
                continue
            root = Path(match.group(1)).parent
            if (root / "rackpulse" / "__init__.py").is_file():
                sys.path.insert(0, str(root))
                return

    cwd = Path.cwd()
    if (cwd / "rackpulse" / "__init__.py").is_file():
        sys.path.insert(0, str(cwd))


def main() -> None:
    _ensure_rackpulse_on_path()
    from rackpulse.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
