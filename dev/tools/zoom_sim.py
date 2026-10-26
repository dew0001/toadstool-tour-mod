"""Check the zoom view camera without a Dolphin: run the assembled cave 7 code on a tiny PowerPC interpreter
for sample shots and compare with the intended formula (ZOOM_TUNING). Usage: python -I zoom_sim.py
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import build_mod as b  # noqa: E402


def f32(x):
    return struct.unpack(">f", struct.pack(">f", x))[0]


class CPU:
    def __init__(self, mem):
        self.r = [0] * 32
        self.f = [0.0] * 32
        self.mem = mem  # dict addr -> 4 bytes
        self.cr0 = 0  # 'lt', 'gt', 'eq'
        self.lr = 0xDEAD0000

    def rd(self, a):
        return self.mem.get(a & 0xFFFFFFFF, b"\0\0\0\0")

    def wr(self, a, v):
        self.mem[a & 0xFFFFFFFF] = v

    def run(self, pc, code_base, code):
        steps = 0
        while pc != self.lr:
            steps += 1
            assert steps < 10000
            w = struct.unpack_from(">I", code, pc - code_base)[0]
            op = w >> 26
            rd, ra, rb = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
            simm = w & 0xFFFF
            simm = simm - 0x10000 if simm & 0x8000 else simm
            nxt = pc + 4
            if op == 14:
                self.r[rd] = ((self.r[ra] if ra else 0) + simm) & 0xFFFFFFFF
            elif op == 15:
                self.r[rd] = ((self.r[ra] if ra else 0) + (simm << 16)) & 0xFFFFFFFF
            elif op == 32:
                self.r[rd] = struct.unpack(">I", self.rd((self.r[ra] if ra else 0) + simm))[0]
            elif op == 48:
                self.f[rd] = struct.unpack(">f", self.rd((self.r[ra] if ra else 0) + simm))[0]
            elif op == 52:
                self.wr((self.r[ra] if ra else 0) + simm, struct.pack(">f", self.f[rd]))
            elif op == 11:
                v = self.r[ra] - (1 << 32) if self.r[ra] & 0x80000000 else self.r[ra]
                self.cr0 = "lt" if v < simm else "gt" if v > simm else "eq"
            elif op == 16:
                bo, bi = rd, ra
                bd = w & 0xFFFC
                bd = bd - 0x10000 if bd & 0x8000 else bd
                bit = ["lt", "gt", "eq"][bi & 3] if (bi & 3) < 3 else None
                cond = self.cr0 == bit
                if (bo & 0x1C) == 0x0C and cond or (bo & 0x1C) == 0x04 and not cond:
                    nxt = pc + bd
            elif op == 18:
                li = w & 0x03FFFFFC
                li = li - 0x04000000 if li & 0x02000000 else li
                nxt = pc + li
            elif w == 0x4E800020:
                nxt = self.lr
            elif op == 59:
                xo = (w >> 1) & 31
                rc = (w >> 6) & 31
                fa, fb, fc = self.f[ra], self.f[rb], self.f[rc]
                self.f[rd] = f32({18: lambda: fa / fb, 20: lambda: fa - fb, 21: lambda: fa + fb,
                                  25: lambda: fa * fc, 29: lambda: fa * fc + fb}[xo]())
            elif op == 63:
                xo10 = (w >> 1) & 0x3FF
                xo5 = (w >> 1) & 31
                if xo10 == 0:
                    a_, b_ = self.f[ra], self.f[rb]
                    self.cr0 = "lt" if a_ < b_ else "gt" if a_ > b_ else "eq"
                elif xo10 == 72:
                    self.f[rd] = self.f[rb]
                elif xo5 == 26:
                    self.f[rd] = 1 / math.sqrt(self.f[rb])
                else:
                    raise SystemExit(f"op63 {w:08X}")
            else:
                raise SystemExit(f"unknown {w:08X} at {pc:08X}")
            pc = nxt


def mem_with(blob, base, mem):
    for i in range(0, len(blob), 4):
        mem[base + i] = blob[i:i + 4]


def intended(ball, target, z):
    """Where the camera should end up (eye + look) for a zoom amount, once it has glided there."""
    T = b.ZOOM_TUNING
    dx, dz = target[0] - ball[0], target[2] - ball[2]
    D = math.hypot(dx, dz)
    dx, dz = dx / D, dz / D
    t = min(1, z / T["full"])
    along, up = t * t * (3 - 2 * t), t * (2 - t)
    b1 = min(T["end_back"], T["end_back_share"] * D)
    u1 = min(T["end_up"], max(T["end_up_min"], T["end_up_share"] * D))
    s = -T["start_back"] + along * (D - b1 + T["start_back"])
    e0y = ball[1] + T["start_up"]
    return [ball[0] + dx * s, e0y + up * (target[1] + u1 - e0y), ball[2] + dz * s] + list(target)


def run_case(ball, target, z, game_cam, frames):
    """One frame in the normal view (the code remembers the game's camera), then `frames` zoomed frames."""
    cave7, v7 = b.cave7_code()
    cave2, _ = b.cave2_code(0x8003B000)
    mem = {}
    mem_with(cave7, b.CAVE7, mem)
    mem_with(cave2, b.CAVE2, mem)
    setup, cam = 0x81000000, 0x81100000
    put = lambda a, v: mem.__setitem__(a, struct.pack(">f", v))
    for i, v in enumerate(target):
        put(setup + b.SETUP_TARGET + 4 * i, v)
    for i, v in enumerate(ball):
        put(b.AIM_BALL + 4 * i, v)
    mem[b.CAMERA_PTR] = struct.pack(">I", cam)
    put(setup + b.SETUP_ZOOM, z)
    history = []
    for frame in range(frames + 1):
        mem[setup + b.SETUP_VIEW] = struct.pack(">I", 5 if frame == 0 else b.VIEW_ZOOM)
        for i, v in enumerate(game_cam):  # the game writes its own camera every frame
            put(cam + 4 * i, v)
        cpu = CPU(mem)
        cpu.r[3] = setup
        cpu.run(v7["zoom"], b.CAVE7, cave7)
        history.append([struct.unpack(">f", mem[cam + 4 * i])[0] for i in range(6)])
    return history


def show(label, cam, ball):
    print(f"{label}: eye {cam[0]:7.1f} {cam[1]:6.1f} {cam[2]:7.1f}  look {cam[3]:6.1f} {cam[4]:5.1f} {cam[5]:7.1f}  "
          f"({math.hypot(cam[0] - ball[0], cam[2] - ball[2]):4.0f} ft from the ball, {cam[1] - ball[1]:5.1f} up)")


ball, target = (-64.5, 51.6, 510.8), (-81.7, 1.9, -123.0)
normal_view = (-62.0, 62.0, 535.0, -63.0, 55.0, 500.0)
first = run_case(ball, target, 0.13, normal_view, 1)  # the first press jumps the amount to about 0.13
show("normal view    ", first[0], ball)
show("first zoom frame", first[1], ball)
for z in (0.13, 0.3, 0.6, 0.9, 1.2, 2.5):
    settled = run_case(ball, target, z, normal_view, 90)[-1]
    err = max(abs(g - w) for g, w in zip(settled, intended(ball, target, z)))
    show(f"z {z:4} settled ", settled, ball)
    assert err < 0.05, f"z {z}: off by {err}"
chip = run_case((0.0, 0.0, 0.0), (0.0, 0.0, -30.0), 1.5, normal_view, 90)[-1]
assert max(abs(g - w) for g, w in zip(chip, intended((0.0, 0.0, 0.0), (0.0, 0.0, -30.0), 1.5))) < 0.05
print("short chip, full zoom:", [round(v, 1) for v in chip])
print("all match the intended path")
