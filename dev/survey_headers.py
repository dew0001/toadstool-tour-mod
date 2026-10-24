"""Survey the 4-byte headers of disc files: type byte + 24-bit size.

Usage: python -I survey_headers.py <disc/files dir>
"""
import collections
import os
import sys


def main():
    root = sys.argv[1]
    by_type = collections.Counter()
    rows = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                head = f.read(8)
            if len(head) < 4:
                continue
            kind = head[0]
            claimed = int.from_bytes(head[1:4], "big")
            by_type[kind] += 1
            rows.append((claimed, kind, size, rel, head.hex()))
    print("type byte counts:", {f"{k:02X}": v for k, v in by_type.most_common(12)})
    plausible = [r for r in rows if r[1] in (1, 2) and r[2] <= r[0] <= r[2] * 20]
    print(f"{len(plausible)} of {len(rows)} files look like type 01/02 + unpacked size >= packed size")
    print("\nlargest claimed unpacked sizes (type 01/02):")
    for claimed, kind, size, rel, head in sorted(plausible, reverse=True)[:20]:
        print(f"  {rel:10} type {kind:02X}  packed {size:>11,}  unpacked {claimed:>11,}  ratio {claimed / size:5.2f}  {head}")
    others = [r for r in rows if r not in plausible]
    print(f"\nother headers ({len(others)}), largest first:")
    for claimed, kind, size, rel, head in sorted(others, key=lambda r: -r[2])[:20]:
        print(f"  {rel:10} {size:>11,}  {head}")


if __name__ == "__main__":
    main()
