"""Decompress every type 01/02 file on the disc and write a manifest.

Usage:
  python -I unpack_all.py <disc/files dir> <output dir>            unpack everything
  python -I unpack_all.py <disc/files dir> <output dir> A/W/B ...  only these files

Outputs, mirroring the disc tree:
  <file>.bin  decoded bytes
  <file>.rel  type 2 only: raw relocation entries (8 bytes each, no terminator)
  manifest.tsv  one row per disc file
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402


def classify(blob):
    """Cheap content hints for a decoded file."""
    if len(blob) < 16:
        return "tiny"
    n = len(blob) // 4
    words = struct.unpack_from(f">{n}I", blob, 0)
    blr = sum(1 for w in words if w == 0x4E800020)
    if blr >= 8 and blr * 4096 >= len(blob):
        return "code?"
    return ""


def main():
    root, out_root = sys.argv[1], sys.argv[2]
    only = set(sys.argv[3:])
    os.makedirs(out_root, exist_ok=True)
    rows = []
    totals = collections.Counter()
    for dirpath, _, names in os.walk(root):
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if only and rel not in only:
                continue
            with open(path, "rb") as f:
                data = f.read()
            kind, size = lz.header(data) if len(data) >= 4 else (None, 0)
            row = {"file": rel, "type": f"{kind:02X}" if kind is not None else "", "packed": len(data),
                   "unpacked": "", "relocs": "", "reloc_kinds": "", "status": "", "hint": ""}
            if kind in (1, 2):
                try:
                    blob, end = lz.decompress(data)
                    row["unpacked"] = len(blob)
                    status = "ok" if len(blob) == size else f"size {len(blob)} != header {size}"
                    dest = os.path.join(out_root, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest + ".bin", "wb") as f:
                        f.write(blob)
                    if kind == 2:
                        entries, tend = lz.relocations(data, end)
                        row["relocs"] = len(entries)
                        kinds = collections.Counter(lz.RELOC_KINDS.get(k, hex(k)) + ("*" if e else "")
                                                    for k, e, _, _ in entries)
                        row["reloc_kinds"] = " ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
                        with open(dest + ".rel", "wb") as f:
                            for k, e, off, val in entries:
                                f.write(struct.pack(">II", ((k | (4 if e else 0)) << 24) | off, val))
                        if len(data) - tend > 32:
                            status += f" (+{len(data) - tend} trailing bytes)"
                    row["status"] = status
                    row["hint"] = classify(blob)
                    totals["ok" if status.startswith("ok") else "bad"] += 1
                except Exception as exc:  # keep going; record the failure
                    row["status"] = f"error: {exc}"
                    totals["error"] += 1
            else:
                row["status"] = "not LZ"
                totals["skipped"] += 1
            rows.append(row)
    cols = ["file", "type", "packed", "unpacked", "relocs", "reloc_kinds", "status", "hint"]
    with open(os.path.join(out_root, "manifest.tsv"), "w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    for r in rows if only else []:
        print("  ".join(f"{c}={r[c]}" for c in cols if r[c] != ""))
    print(dict(totals))


if __name__ == "__main__":
    main()
