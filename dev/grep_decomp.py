"""Grep decompiled C and label every hit with its function, optionally only in an address range.

Usage: python -I grep_decomp.py <decomp.c> <regex> [--min 0x80400000] [--max 0x804E3604] [--after N]
"""
import re
import sys


def main():
    path, pattern = sys.argv[1], re.compile(sys.argv[2])
    lo = int(sys.argv[sys.argv.index("--min") + 1], 16) if "--min" in sys.argv else 0
    hi = int(sys.argv[sys.argv.index("--max") + 1], 16) if "--max" in sys.argv else 0xFFFFFFFF
    after = int(sys.argv[sys.argv.index("--after") + 1]) if "--after" in sys.argv else 0
    func, addr = "?", 0
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("// ==== "):
            parts = line.split()
            addr, func = int(parts[2], 16), parts[3]
            continue
        if lo <= addr < hi and pattern.search(line):
            print(f"{addr:08x} {func} L{i + 1}: {line.strip()}")
            for extra in lines[i + 1:i + 1 + after]:
                print(f"{'':28}{extra.strip()}")


if __name__ == "__main__":
    main()
