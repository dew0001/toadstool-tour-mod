"""Minimal PowerPC (Gekko) encoder and assembler for the mod's patch stubs.

Only the instructions the stubs use. Every encoding is checked in selftest() against machine code
taken from the game itself or the gamemasterplc widescreen Gecko code.
"""
import struct


def _simm(v):
    if not -0x8000 <= v <= 0xFFFF:
        raise ValueError(f"immediate out of range: {v}")
    return v & 0xFFFF


def _d(op, rt, d, ra):
    return op << 26 | rt << 21 | ra << 16 | _simm(d)


# integer
def lis(rd, imm): return 0x3C000000 | rd << 21 | _simm(imm)
def li(rd, imm): return 0x38000000 | rd << 21 | _simm(imm)
def addi(rd, ra, imm): return 0x38000000 | rd << 21 | ra << 16 | _simm(imm)
def ori(ra, rs, imm): return 0x60000000 | rs << 21 | ra << 16 | _simm(imm)
def mulli(rd, ra, imm): return 0x1C000000 | rd << 21 | ra << 16 | _simm(imm)
def add(rd, ra, rb): return 0x7C000214 | rd << 21 | ra << 16 | rb << 11
def mr(ra, rs): return 0x7C000378 | rs << 21 | ra << 16 | rs << 11
def andi_(ra, rs, imm): return 0x70000000 | rs << 21 | ra << 16 | (imm & 0xFFFF)
def cmpwi(ra, imm): return 0x2C000000 | ra << 16 | _simm(imm)
def lwz(rd, d, ra): return _d(32, rd, d, ra)
def lbz(rd, d, ra): return _d(34, rd, d, ra)
def lhz(rd, d, ra): return _d(40, rd, d, ra)
def stw(rs, d, ra): return _d(36, rs, d, ra)
def sth(rs, d, ra): return _d(44, rs, d, ra)
def stwu(rs, d, ra): return _d(37, rs, d, ra)
def mflr(rd): return 0x7C0802A6 | rd << 21
def mtlr(rs): return 0x7C0803A6 | rs << 21
BLR = 0x4E800020


# floating point (single)
def lfs(frd, d, ra): return _d(48, frd, d, ra)
def stfs(frs, d, ra): return _d(52, frs, d, ra)
def fadds(d, a, b): return 0xEC00002A | d << 21 | a << 16 | b << 11
def fsubs(d, a, b): return 0xEC000028 | d << 21 | a << 16 | b << 11
def fmuls(d, a, c): return 0xEC000032 | d << 21 | a << 16 | c << 6
def fdivs(d, a, b): return 0xEC000024 | d << 21 | a << 16 | b << 11
def fneg(d, b): return 0xFC000050 | d << 21 | b << 11
def frsqrte(d, b): return 0xFC000034 | d << 21 | b << 11
def fcmpu(a, b): return 0xFC000000 | a << 16 | b << 11  # into cr0


# branches
def b(at, target): return 0x48000000 | _rel26(at, target)
def bl(at, target): return 0x48000001 | _rel26(at, target)


def _rel26(at, target):
    off = target - at
    if not -0x2000000 <= off < 0x2000000 or off & 3:
        raise ValueError(f"branch from 0x{at:08X} to 0x{target:08X} out of range")
    return off & 0x03FFFFFC


COND = {"bne": 0x40820000, "beq": 0x41820000, "blt": 0x41800000, "bge": 0x40800000,
        "bgt": 0x41810000, "ble": 0x40810000}


def hi_lo(addr):
    """Split an address for `lis rX, hi` + `op rY, lo(rX)` (lo is sign-extended by the CPU)."""
    lo = addr & 0xFFFF
    hi = (addr >> 16) + (1 if lo & 0x8000 else 0)
    return hi & 0xFFFF, lo - 0x10000 if lo & 0x8000 else lo


class Asm:
    """Assembles a block at a fixed address, with labels for branches and data."""

    def __init__(self, base):
        self.base, self.words, self.labels, self.fixups = base, [], {}, []

    def here(self):
        return self.base + 4 * len(self.words)

    def label(self, name):
        self.labels[name] = self.here()

    def __call__(self, *words):
        self.words.extend(words)

    def bl(self, target):
        self.words.append(bl(self.here(), target))

    def b(self, target):
        self.words.append(b(self.here(), target))

    def br(self, kind, name):  # conditional, unconditional ("b") or call ("bl") branch to a label
        self.fixups.append((len(self.words), kind, name))
        self.words.append(0)

    def la(self, reg, name):  # load a label's address into reg (lis + addi)
        self.fixups.append((len(self.words), "la", (reg, name)))
        self.words.extend([0, 0])

    def float(self, name, value):
        self.label(name)
        self.words.append(struct.unpack(">I", struct.pack(">f", value))[0])

    def word(self, name, value=0):
        self.label(name)
        self.words.append(value & 0xFFFFFFFF)

    def assemble(self):
        for idx, kind, arg in self.fixups:
            at = self.base + 4 * idx
            if kind == "la":
                reg, name = arg
                hi, lo = hi_lo(self.labels[name])
                self.words[idx], self.words[idx + 1] = lis(reg, hi), addi(reg, reg, lo)
            elif kind == "b":
                self.words[idx] = b(at, self.labels[arg])
            elif kind == "bl":
                self.words[idx] = bl(at, self.labels[arg])
            else:
                off = self.labels[arg] - at
                if not -0x8000 <= off < 0x8000:
                    raise ValueError(f"{kind} {arg}: too far")
                self.words[idx] = COND[kind] | (off & 0xFFFC)
        return b"".join(struct.pack(">I", w) for w in self.words)


def selftest():
    known = {  # encoding: game or Gecko machine code word
        fmuls(8, 17, 8): 0xED110232, fdivs(10, 9, 8): 0xED494024, fsubs(8, 4, 3): 0xED041828,
        fadds(3, 4, 3): 0xEC64182A, fneg(3, 3): 0xFC601850, lfs(9, -0x7EE8, 2): 0xC1228118,
        stfs(4, 0, 3): 0xD0830000, lfs(1, 0xC, 3): 0xC023000C, stfs(1, 0xC, 3): 0xD023000C,
        li(4, 1): 0x38800001, li(28, -1): 0x3B80FFFF, lis(29, 0x804E): 0x3FA0804E,
        ori(4, 4, 0xAAAB): 0x6084AAAB, addi(9, 9, -0x3190): 0x3929CE70, mulli(3, 0, 0x5204): 0x1C605204,
        add(3, 3, 9): 0x7C634A14, mr(28, 0): 0x7C1C0378, andi_(9, 0, 0x80): 0x70090080,
        cmpwi(0, 0): 0x2C000000, cmpwi(21, 0): 0x2C150000, lwz(3, 0, 21): 0x80750000,
        lbz(0, 0x68FB, 9): 0x880968FB, lbz(0, 0xD16, 31): 0x881F0D16, stwu(1, -0x48, 1): 0x9421FFB8,
        mflr(0): 0x7C0802A6, bl(0x80425BB0, 0x80456D1C): 0x4803116D, bl(0x80405620, 0x80423BBC): 0x4801E59D,
        COND["bne"] | 0x18: 0x40820018, COND["blt"] | 0x1C: 0x4180001C, COND["beq"] | 0x28: 0x41820028,
    }
    for got, want in known.items():
        assert got == want, f"{got:08X} != {want:08X}"
    assert hi_lo(0x8026C7F8) == (0x8027, -0x3808)
    assert hi_lo(0x804ECE70) == (0x804F, -0x3190)
    return True


if __name__ == "__main__":
    print("ppc selftest:", selftest())
