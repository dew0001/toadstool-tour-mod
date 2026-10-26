"""Check the v6 yardage box without a Dolphin: run cave 8's box_text on a tiny PowerPC interpreter for sample
labels and print where the digits start and the box outline it draws. Calls into the game are no-ops here.
Usage: python -I box_sim.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import build_mod as b  # noqa: E402

FIFO = 0xCC008000


class CPU:
    def __init__(self, mem):
        self.r, self.f, self.mem, self.cr0, self.lr = [0] * 32, [0.0] * 32, mem, "eq", 0xDEAD0000
        self.fifo = []

    def load(self, a, n):
        return bytes(self.mem.get(a + i, 0) for i in range(n))

    def store(self, a, data):
        if a == FIFO:
            self.fifo.append(data)
            return
        for i, x in enumerate(data):
            self.mem[a + i] = x

    def run(self, pc, code_base, code):
        end = self.lr
        for _ in range(100000):
            if pc == end:
                return
            if not code_base <= pc < code_base + len(code):  # a call into the game: pretend it returned
                pc = self.lr
                continue
            w = struct.unpack_from(">I", code, pc - code_base)[0]
            op, rd, ra, rb = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
            simm = (w & 0xFFFF) - (0x10000 if w & 0x8000 else 0)
            base = self.r[ra] if ra else 0
            ea = (base + simm) & 0xFFFFFFFF
            nxt = pc + 4
            s32 = lambda v: v - (1 << 32) if v & 0x80000000 else v
            if op == 14:
                self.r[rd] = (base + simm) & 0xFFFFFFFF
            elif op == 15:
                self.r[rd] = (base + (simm << 16)) & 0xFFFFFFFF
            elif op == 7:
                self.r[rd] = (s32(self.r[ra]) * simm) & 0xFFFFFFFF
            elif op == 24:
                self.r[ra] = self.r[rd] | (w & 0xFFFF)
            elif op == 21:
                sh, mb, me = rb, (w >> 6) & 31, (w >> 1) & 31
                v = ((self.r[rd] << sh) | (self.r[rd] >> (32 - sh))) & 0xFFFFFFFF if sh else self.r[rd]
                mask = 0
                for bit in range(32):
                    if (mb <= me and mb <= bit <= me) or (mb > me and (bit >= mb or bit <= me)):
                        mask |= 1 << (31 - bit)
                self.r[ra] = v & mask
            elif op in (32, 34, 48):
                data = self.load(ea, {32: 4, 34: 1, 48: 4}[op])
                if op == 48:
                    self.f[rd] = struct.unpack(">f", data)[0]
                else:
                    self.r[rd] = int.from_bytes(data, "big")
            elif op in (36, 37, 38, 44, 52):
                if op == 52:
                    data = struct.pack(">f", self.f[rd])
                else:
                    data = (self.r[rd] & 0xFFFFFFFF).to_bytes(4, "big")[{36: 0, 37: 0, 38: 3, 44: 2}[op]:]
                self.store(ea, data)
                if op == 37:
                    self.r[ra] = ea
            elif op == 11:
                v = s32(self.r[ra])
                self.cr0 = "lt" if v < simm else "gt" if v > simm else "eq"
            elif op == 31:
                xo = (w >> 1) & 0x3FF
                if xo == 0:
                    x, y = s32(self.r[ra]), s32(self.r[rb])
                    self.cr0 = "lt" if x < y else "gt" if x > y else "eq"
                elif xo == 266:
                    self.r[rd] = (self.r[ra] + self.r[rb]) & 0xFFFFFFFF
                elif xo == 235:
                    self.r[rd] = (s32(self.r[ra]) * s32(self.r[rb])) & 0xFFFFFFFF
                elif xo == 339:
                    self.r[rd] = self.lr
                elif xo == 467:
                    self.lr = self.r[rd]
                else:
                    raise SystemExit(f"op31 xo {xo} at {pc:08X}")
            elif op == 16:
                bo, bi = rd, ra
                bd = (w & 0xFFFC) - (0x10000 if w & 0x8000 else 0)
                cond = self.cr0 == ["lt", "gt", "eq"][bi & 3]
                if (bo & 0x1C) == 0x0C and cond or (bo & 0x1C) == 0x04 and not cond:
                    nxt = pc + bd
            elif op == 18:
                li = (w & 0x03FFFFFC) - (0x04000000 if w & 0x02000000 else 0)
                if w & 1:
                    self.lr = pc + 4
                nxt = pc + li
            elif w == 0x4E800020:
                nxt = self.lr
            else:
                raise SystemExit(f"unknown {w:08X} at {pc:08X}")
            pc = nxt
        raise SystemExit("ran too long")


def run(label):
    blob, v8 = b.cave8_code()
    mem = {}
    for i, x in enumerate(blob):
        mem[b.CAVE8 + i] = x
    cpu = CPU(mem)
    sp = 0x81000000
    for i, ch in enumerate(label.encode() + b"\0"):
        mem[sp + b.HUD_TEXT + i] = ch
    for i in range(4):
        mem[sp + b.HUD_PUTT + i] = 0
    cpu.r[1], cpu.r[29] = sp, 0
    cpu.run(v8["box_text"], b.CAVE8, blob)
    assert cpu.r[1] == sp and cpu.r[0] == label.encode()[0]
    verts = []
    for k in range(0, len(cpu.fifo), 4):
        x, y = (struct.unpack(">h", cpu.fifo[k + i])[0] for i in (0, 1))
        verts.append((x, y))
    shift = cpu.r[29] - (1 << 32) if cpu.r[29] & 0x80000000 else cpu.r[29]
    return shift, verts


for label in ("212y", " 95y", "  8y"):
    shift, verts = run(label)
    xs = [x for x, _ in verts]
    first = -32 + shift + 16 * (len(label) - len(label.lstrip()))
    last = -32 + shift + 16 * len(label)
    print(f"{label!r}: digits {first}..{last}, box {min(xs)}..{max(xs)} x {min(y for _, y in verts)}..{max(y for _, y in verts)},"
          f" {len(verts)} vertices: {verts[:6]} ...")
