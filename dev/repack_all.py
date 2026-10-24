"""Repack decoded files back into a build tree, verifying each one decodes exactly.

Usage:
  python -I repack_all.py <unpacked dir> <build/files dir>            every file unpack_all.py decoded
  python -I repack_all.py <unpacked dir> <build/files dir> C/L/V ...  only these files

Reads <file>.bin (+ <file>.rel for type 2) and the manifest type, writes <build/files>/<file>.
"""
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402


def main():
    unpacked, build = sys.argv[1], sys.argv[2]
    only = set(sys.argv[3:])
    with open(os.path.join(unpacked, "manifest.tsv"), encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t") if r["status"].startswith("ok")]
    if only:
        rows = [r for r in rows if r["file"] in only]
    t0 = time.time()
    packed_total = orig_total = 0
    for n, r in enumerate(rows, 1):
        rel = r["file"]
        kind = int(r["type"], 16)
        base = os.path.join(unpacked, *rel.split("/"))
        with open(base + ".bin", "rb") as f:
            blob = f.read()
        table = b""
        if kind == 2:
            with open(base + ".rel", "rb") as f:
                table = f.read()
        out = lz.pack(kind, blob, table)
        check, end = lz.decompress(out)
        if check != blob:
            raise SystemExit(f"{rel}: repacked file does not decode back exactly")
        dest = os.path.join(build, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, dest)
        packed_total += len(out)
        orig_total += int(r["packed"])
        if n % 100 == 0 or n == len(rows):
            print(f"{n}/{len(rows)} files, {time.time() - t0:.0f}s, size vs original {packed_total / orig_total:.3f}x",
                  flush=True)


if __name__ == "__main__":
    main()
