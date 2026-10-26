"""Dump NUL-terminated strings in a main.dol file range with their load addresses, and find pointer tables to them."""
import os
import re
import struct
import sys
ROOT = os.environ.get("TTMOD_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

dol = open(os.environ.get("TTMOD_DOL", os.path.join(ROOT, "disc", "sys", "main.dol")), "rb").read()
offs = struct.unpack_from(">18I", dol, 0)
addrs = struct.unpack_from(">18I", dol, 0x48)
sizes = struct.unpack_from(">18I", dol, 0x90)


def addr_of(off):
    for o, a, s in zip(offs, addrs, sizes):
        if s and o <= off < o + s:
            return a + off - o
    return None


def off_of(addr):
    for o, a, s in zip(offs, addrs, sizes):
        if s and a <= addr < a + s:
            return o + addr - a
    return None


cmd = sys.argv[1]
if cmd == "strings":
    lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
    for m in re.finditer(rb"[\x20-\x7E\n%]{2,}", dol[lo:hi]):
        o = lo + m.start()
        print(f"{addr_of(o):08X} {m.group().decode('latin-1')!r}")
elif cmd == "refs":  # words in the DOL equal to an address
    target = int(sys.argv[2], 16)
    for i in range(0, len(dol) - 3, 4):
        if struct.unpack_from(">I", dol, i)[0] == target:
            print(f"word at {addr_of(i):08X}")
elif cmd == "words":
    a = int(sys.argv[2], 16)
    n = int(sys.argv[3])
    o = off_of(a)
    for k in range(n):
        print(f"{a + 4 * k:08X} {struct.unpack_from('>I', dol, o + 4 * k)[0]:08X}")
