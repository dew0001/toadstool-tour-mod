"""Print main.dol words in an address range, and find callers (bl) of a target."""
import os
import struct
import sys
ROOT = os.environ.get("TTMOD_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

dol = open(os.environ.get("TTMOD_DOL", os.path.join(ROOT, "disc", "sys", "main.dol")), "rb").read()
offs = struct.unpack_from(">18I", dol, 0)
addrs = struct.unpack_from(">18I", dol, 0x48)
sizes = struct.unpack_from(">18I", dol, 0x90)


def off_of(addr):
    for o, a, s in zip(offs, addrs, sizes):
        if s and a <= addr < a + s:
            return o + addr - a
    raise ValueError(hex(addr))


cmd = sys.argv[1]
if cmd == "dump":
    start, end = int(sys.argv[2], 16), int(sys.argv[3], 16)
    for a in range(start, end, 4):
        print(f"{a:08X} {struct.unpack_from('>I', dol, off_of(a))[0]:08X}")
elif cmd == "callers":
    target = int(sys.argv[2], 16)
    for o, a, s in zip(offs[:7], addrs[:7], sizes[:7]):
        for i in range(0, s, 4):
            w = struct.unpack_from(">I", dol, o + i)[0]
            if w >> 26 == 18 and w & 3 == 1:
                d = w & 0x3FFFFFC
                if d & 0x2000000:
                    d -= 0x4000000
                if a + i + d == target:
                    print(f"bl from {a + i:08X}")
