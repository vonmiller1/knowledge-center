"""The config boundary for retention packs: the only place a pack file is parsed.

The packs themselves are policy and their validation is domain logic, so it lives in
:mod:`meeting_capture.domain.retention`. What lives HERE is everything that touches the world
outside the hexagon: where the shipped packs sit on disk, reading those bytes, and turning YAML
into plain Python mappings. Splitting it this way is what lets the core import nothing but the
standard library : the engine is handed data, and never a parser.

The split is also why a pack can arrive from somewhere other than a file. Anything that can
produce ``(source, mapping)`` pairs : a config map, a secret manager, a test fixture : feeds
:func:`~meeting_capture.domain.retention.build_pack_set` directly, with no YAML involved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .domain.retention import RetentionPack, build_pack_set

__all__ = ["default_packs_dir", "load_default_packs", "load_packs", "read_pack_documents"]


def default_packs_dir() -> Path:
    """The shipped retention-pack directory, resolved relative to the repository root."""
    return Path(__file__).resolve().parents[2] / "config" / "packs"


def read_pack_documents(directory: Path) -> list[tuple[str, Any]]:
    """Parse every ``*.yaml`` pack in ``directory`` into ``(source, parsed)`` pairs.

    Sorted, so the order a refusal reports is the order a reader sees on disk. Nothing is
    validated here: a document that is not a mapping is passed on as it was parsed, because
    deciding that is the core's job and this function must not grow a second opinion about it.
    """
    return [
        (str(path), yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.yaml"))
    ]


def load_packs(directory: Path) -> dict[str, RetentionPack]:
    """Read and validate every retention pack under ``directory``, keyed by market code."""
    return build_pack_set(read_pack_documents(directory), origin=str(directory))


def load_default_packs() -> dict[str, RetentionPack]:
    """Load the shipped per-market retention packs (used by the API, CLI, demo and eval)."""
    return load_packs(default_packs_dir())
