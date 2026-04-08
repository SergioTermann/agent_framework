from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import List, Tuple


def _import_causal_core():
    try:
        return importlib.import_module("causal_core"), None
    except ImportError as exc:
        import_error = exc

    candidate_roots = []
    for parent in Path(__file__).resolve().parents:
        candidate_roots.append(parent)
        if len(candidate_roots) >= 5:
            break
    candidate_roots.append(Path.cwd())

    search_dirs = []
    for project_root in candidate_roots:
        search_dirs.extend([
            project_root / "rust_extensions" / "causal_core" / "target" / "release",
        project_root / "rust_extensions" / "causal_core" / "target" / "debug",
        ])
    patterns = ("causal_core*.pyd", "causal_core*.so", "causal_core*.dylib")

    for directory in search_dirs:
        if not directory.exists():
            continue
        if not any(directory.glob(pattern) for pattern in patterns):
            continue

        sys.path.insert(0, str(directory))
        try:
            return importlib.import_module("causal_core"), None
        except ImportError:
            sys.path.pop(0)

    return None, import_error


causal_core, _CAUSAL_CORE_IMPORT_ERROR = _import_causal_core()
RUST_CAUSAL_AVAILABLE = causal_core is not None

if not RUST_CAUSAL_AVAILABLE:
    print(f"Warning: Rust causal_core not available, falling back to Python ({_CAUSAL_CORE_IMPORT_ERROR})")


class CausalGraphOps:
    @staticmethod
    def find_paths(
        edges: List[Tuple[int, str, str]],
        start_id: str,
        end_id: str,
        max_depth: int,
    ) -> List[List[int]]:
        if RUST_CAUSAL_AVAILABLE:
            return causal_core.find_paths(edges, start_id, end_id, max_depth)
        return []

    @staticmethod
    def shortest_path(
        edges: List[Tuple[int, str, str]],
        start_id: str,
        end_id: str,
    ) -> List[int]:
        if RUST_CAUSAL_AVAILABLE:
            return causal_core.shortest_path(edges, start_id, end_id)
        return []

    @staticmethod
    def detect_cycles(edges: List[Tuple[int, str, str]]) -> List[List[str]]:
        if RUST_CAUSAL_AVAILABLE:
            return causal_core.detect_cycles(edges)
        return []
