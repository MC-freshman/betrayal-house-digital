from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from game.ui import run_app
else:
    from .ui import run_app


def main() -> None:
    run_app()


if __name__ == "__main__":
    main()
