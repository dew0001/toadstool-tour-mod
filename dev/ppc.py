"""Minimal PowerPC (Gekko) instruction encoder for small patch stubs.

Only the handful of instructions the mod's stubs need. Encodings are checked in selftest()
against machine code from the gamemasterplc widescreen Gecko code and the game itself.
"""


def _simm(v):
    if not -0x8000 <= v <= 0xFFFF:
        raise ValueError(f"immediate out of range: {v}")
    return v & 0xFFFF


def lis(rd, imm):
    return 0x3C000000 | rd << 21 | _simm(imm)


def ori(ra, rs, imm):
    return 0x60000000 | rs << 21 | ra << 16 | _simm(imm)


def li(rd, imm):
    return 0x38000000 | rd << 21 | _simm(imm)


def lfs(frd, d, ra):
    return 0xC0000000 | frd << 21 | ra << 16 | _simm(d)


def stfs(frs, d, ra):
    return 0xD0000000 | frs << 21 | ra << 16 | _simm(d)


def sth(rs, d, ra):
    return 0xB0000000 | rs << 21 | ra << 16 | _simm(d)


def fmuls(frd, fra, frc):
    return 0xEC000032 | frd << 21 | fra << 16 | frc << 6


def fdivs(frd, fra, frb):
    return 0xEC000024 | frd << 21 | fra << 16 | frb << 11


def b(at, target):
    off = target - at
    if not -0x2000000 <= off < 0x2000000 or off & 3:
        raise ValueError(f"branch from 0x{at:08X} to 0x{target:08X} out of range")
    return 0x48000000 | (off & 0x03FFFFFC)


def hi_lo(addr):
    """Split an address for `lis rX, hi` + `op rY, lo(rX)` (lo is sign-extended by the CPU)."""
    lo = addr & 0xFFFF
    hi = (addr >> 16) + (1 if lo & 0x8000 else 0)
    return hi & 0xFFFF, lo - 0x10000 if lo & 0x8000 else lo


def selftest():
    assert fmuls(8, 17, 8) == 0xED110232
    assert fdivs(10, 9, 8) == 0xED494024
    assert lfs(17, 0, 2) == 0xC2220000
    assert lfs(1, 0xC, 3) == 0xC023000C
    assert stfs(1, 0xC, 3) == 0xD023000C
    assert fmuls(1, 17, 1) == 0xEC310072
    assert li(4, 1) == 0x38800001
    assert lis(4, 0x3FAA) == 0x3C803FAA
    assert ori(4, 4, 0xAAAB) == 0x6084AAAB
    assert lis(29, 0x804E) == 0x3FA0804E
    assert b(0x8000FAA4, 0x8003E684) == 0x4802EBE1 & ~1  # game's `bl` minus the link bit
    assert hi_lo(0x8026C7F8) == (0x8027, -0x3808)
    return True


if __name__ == "__main__":
    print("ppc selftest:", selftest())
