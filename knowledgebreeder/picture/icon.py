"""kb's app icon, drawn here as a PNG so nothing is fetched or shipped as a binary: a pale plate and a red bar,
slanted like the boxes on the pages, on the dark ink of the page. A phone needs it to put kb on its home screen and
in its Share menu."""

from __future__ import annotations

import struct
import zlib
from functools import lru_cache

INK = (29, 36, 48)
PLATE = (232, 223, 200)
RED = (192, 38, 45)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


@lru_cache(maxsize=4)
def png(size: int) -> bytes:
    """A square RGB icon, size pixels a side. Everything that matters sits in the middle 80%, so a round mask
    keeps it."""
    rows = bytearray()
    for y in range(size):
        v = (y + 0.5) / size
        rows.append(0)                                    # no filter on this row
        for x in range(size):
            u = (x + 0.5) / size
            s = u - 0.22 * (v - 0.5)                      # the slant of the boxes on the pages
            if 0.28 <= v <= 0.58 and 0.20 <= s <= 0.78:
                rows += bytes(PLATE)
            elif 0.64 <= v <= 0.72 and 0.20 <= s <= 0.62:
                rows += bytes(RED)
            else:
                rows += bytes(INK)
    head = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", head) + _chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + _chunk(b"IEND", b""))
