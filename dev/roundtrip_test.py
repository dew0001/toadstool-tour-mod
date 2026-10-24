"""Repack decoded files and check the game's decoder reads them back exactly.

Usage: python -I roundtrip_test.py <disc/files dir> <file> [<file> ...]
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402


def main():
    root = sys.argv[1]
    failures = 0
    for rel in sys.argv[2:]:
        with open(os.path.join(root, rel), "rb") as f:
            orig = f.read()
        kind, _ = lz.header(orig)
        blob, end = lz.decompress(orig)
        table = b""
        entries = []
        if kind == 2:
            entries, _ = lz.relocations(orig, end)
            table = b"".join(struct.pack(">II", ((k | (4 if e else 0)) << 24) | off, val)
                             for k, e, off, val in entries)
        t0 = time.time()
        packed = lz.pack(kind, blob, table)
        took = time.time() - t0
        blob2, end2 = lz.decompress(packed)
        ok = blob2 == blob and end2 <= len(packed)
        if kind == 2:
            entries2, tend2 = lz.relocations(packed, end2)
            ok = ok and entries2 == entries and tend2 == len(packed)
        failures += not ok
        print(f"{rel}: type {kind:02X} unpacked {len(blob):,}  original {len(orig):,}  repacked {len(packed):,} "
              f"({len(packed) / len(orig):.2f}x)  {took:.1f}s  {'OK' if ok else 'FAIL'}")
    print("all round-trips OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
