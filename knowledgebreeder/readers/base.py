"""The reader contract.

A reader looks at one page of a drawing set and writes what it found as JSON.
Readers compete: the scoreboard measures each one, and a reader only replaces
another when its score goes up. Every reader must:

* say which page classes it can handle (`applies_to`), using the seed's
  probe classes: vector_text, vector_outlined, raster, raster_with_text, hybrid;
* be deterministic for the same input and version, so scores are comparable;
* never invent: anything uncertain is reported as uncertain, not dropped or guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ReaderResult:
    reader: str
    version: str
    page: int
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"reader": self.reader, "version": self.version, "page": self.page,
                "warnings": self.warnings, **self.data}


class Reader(Protocol):
    name: str
    version: str
    applies_to: frozenset[str]

    def read(self, pdf_path: str, page_no: int, rotation: int = 0) -> ReaderResult:
        ...
