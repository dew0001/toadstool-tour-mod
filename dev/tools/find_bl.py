"""List `bl target` sites in an overlay image (loaded at 0x80400000) with the instructions before them."""
import struct
import sys

blob = open(sys.argv[1], "rb").read()
target = int(sys.argv[2], 16)
lo, hi = (int(sys.argv[3], 16), int(sys.argv[4], 16)) if len(sys.argv) > 4 else (0, 1 << 32)
base = 0x80400000
for i in range(0, len(blob) - 3, 4):
    w = struct.unpack_from(">I", blob, i)[0]
    if w >> 26 == 18 and w & 3 == 1:
        d = w & 0x3FFFFFC
        if d & 0x2000000:
            d -= 0x4000000
        at = base + i
        if at + d == target and lo <= at < hi:
            prev = [struct.unpack_from(">I", blob, i - 4 * k)[0] for k in (3, 2, 1)]
            print(f"{at:08X}: {w:08X}  before: " + " ".join(f"{p:08X}" for p in prev))
