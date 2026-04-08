from __future__ import annotations

import sys
from pathlib import Path


def add_src_to_path(repo_root: Path) -> None:
    src_path = repo_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    add_src_to_path(repo_root)

    from agent_framework.core.harness_doctor import main as doctor_main

    return doctor_main()


if __name__ == "__main__":
    raise SystemExit(main())
