"""Print the decompiled function containing each given address.

Usage: python -I find_func.py <ghidra_out dir> <addr> [<addr> ...] [--lines N]
"""
import bisect
import os
import re
import sys


def main():
    args = sys.argv[1:]
    max_lines = 60
    if "--lines" in args:
        i = args.index("--lines")
        max_lines = int(args[i + 1])
        del args[i:i + 2]
    out_dir, targets = args[0], [int(a, 16) for a in args[1:]]

    with open(os.path.join(out_dir, "decomp.c"), encoding="utf-8", errors="replace") as f:
        text = f.read()
    blocks = re.split(r"^// ==== ", text, flags=re.M)[1:]
    funcs = sorted((int(b.split(" ", 1)[0], 16), b) for b in blocks)
    starts = [a for a, _ in funcs]

    for t in targets:
        i = bisect.bisect_right(starts, t) - 1
        if i < 0:
            print(f"0x{t:08X}: no containing function")
            continue
        start, block = funcs[i]
        lines = block.splitlines()
        print(f"==== 0x{t:08X} is +0x{t - start:X} into {lines[0]}")
        print("\n".join(lines[1:max_lines + 1]))
        if len(lines) > max_lines + 1:
            print(f"   ... ({len(lines) - max_lines - 1} more lines)")


if __name__ == "__main__":
    main()
