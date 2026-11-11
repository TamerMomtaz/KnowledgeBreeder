"""Reader registry. Add a reader by importing it here and listing it in READERS."""

from __future__ import annotations

from .base import Reader, ReaderResult
from .vector_geometry import VectorGeometryReader

READERS: dict[str, Reader] = {r.name: r for r in (VectorGeometryReader(),)}


def get(name: str) -> Reader:
    try:
        return READERS[name]
    except KeyError:
        raise SystemExit(f"unknown reader '{name}'. Known: {', '.join(sorted(READERS))}")


__all__ = ["READERS", "Reader", "ReaderResult", "get"]
