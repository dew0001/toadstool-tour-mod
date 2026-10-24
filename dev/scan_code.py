"""Rank disc files by how much they look like raw PowerPC code.

Counts word-aligned `stwu r1,-N(r1)` prologues and `blr` returns per KiB.
Compressed or media files score near zero; uncompressed code overlays don't.

Usage: python -I scan_code.py <disc/files dir> [top_n]
"""
import os
import struct
import sys


def score(data):
    n = len(data) // 4
    words = struct.unpack_from(f">{n}I", data, 0)
    prologues = sum(1 for w in words if (w & 0xFFFF8000) == 0x94218000)
    blrs = sum(1 for w in words if w == 0x4E800020)
    return prologues, blrs


def main():
    root = sys.argv[1]
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    rows = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                data = f.read()
            if len(data) < 1024:
                continue
            p, b = score(data)
            kib = len(data) / 1024
            rows.append((min(p, b) / kib, p, b, len(data), os.path.relpath(path, root), data[:8].hex()))
    rows.sort(reverse=True)
    print(f"{'per_kib':>8} {'stwu':>6} {'blr':>6} {'bytes':>11}  file  head")
    for density, p, b, size, rel, head in rows[:top_n]:
        print(f"{density:8.2f} {p:6} {b:6} {size:11,}  {rel}  {head}")


if __name__ == "__main__":
    main()
