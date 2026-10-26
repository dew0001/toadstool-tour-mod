"""Debug patches for a BUILT main.dol (run after build_mod.py). Never ship a build with these in it.

  draws:    log every distinct (caller, model instance) passed to the model draw MODEL_DRAW, with live
            "skip this model / this caller" switches, so you can hide a model and see what disappears.
            Read and switch with drawlog.ps1. (v4 found the golfer this way: player +0x518C.)
  messages: log every distinct (caller, message id) looked up with LO <= id <= HI. Read with msglog.ps1.
            The caller is the message formatter's caller's caller (two frames up), i.e. the code that
            put the text on screen. (v4 found the pause menu this way.)

Both chain to whatever the build already hooked there, so the mod still works.

Usage: python -I debug_patch.py <build>/sys/main.dol draws
       python -I debug_patch.py <build>/sys/main.dol messages [lo hi]   (ids in hex, default 10D 11F)
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ppc  # noqa: E402

MODEL_DRAW = 0x800072C8      # model draw entry (r3 = model instance)
MSG_LOOKUP = 0x80022CD0      # message id -> string
DRAW_LOG = 0x80057A14        # dead FUN_80057a14 (712 bytes): table at +0, skip words, then code
MSG_LOG = 0x8005DAFC         # dead FUN_8005dafc (444 bytes)
DEAD_FIRST = 0x7C0802A6
DRAW_MAX, MSG_MAX = 63, 40

path, kind = sys.argv[1], sys.argv[2]
data = bytearray(open(path, "rb").read())
offs = struct.unpack_from(">18I", data, 0)
addrs = struct.unpack_from(">18I", data, 0x48)
sizes = struct.unpack_from(">18I", data, 0x90)


def off_of(addr):
    for o, ad, s in zip(offs, addrs, sizes):
        if s and ad <= addr < ad + s:
            return o + addr - ad
    raise ValueError(hex(addr))


def word(addr):
    return struct.unpack_from(">I", data, off_of(addr))[0]


def continue_original(a, site):
    """Go on as the instruction at site would: follow the build's own `b` hook, or run it and carry on."""
    first = word(site)
    if first >> 26 == 18 and first & 3 == 0:
        d = first & 0x03FFFFFC
        a.b(site + (d - 0x04000000 if d & 0x02000000 else d))
    else:
        a(first)
        a.b(site + 4)


def log_loop(a, key_reg, done):
    """Append (key_reg, r3) to the table at label 'count' unless already there. Uses r7-r11."""
    a.la(11, "count")
    a(ppc.lwz(10, 0, 11), ppc.addi(9, 11, 4), ppc.li(8, 0))
    a.label("loop")
    a(ppc.cmpw(8, 10))
    a.br("bge", "add")
    a(ppc.lwz(7, 0, 9), ppc.cmpw(7, key_reg))
    a.br("bne", "next")
    a(ppc.lwz(7, 4, 9), ppc.cmpw(7, 3))
    a.br("beq", done)
    a.label("next")
    a(ppc.addi(9, 9, 8), ppc.addi(8, 8, 1))
    a.br("b", "loop")
    a.label("add")
    a(ppc.cmpwi(10, MAX))
    a.br("bge", done)
    a(ppc.stw(key_reg, 0, 9), ppc.stw(3, 4, 9), ppc.addi(10, 10, 1), ppc.stw(10, 0, 11))


if kind == "draws":
    CAVE, SITE, MAX = DRAW_LOG, MODEL_DRAW, DRAW_MAX
    a = ppc.Asm(CAVE)
    a.word("count")
    for i in range(MAX):
        a.word(f"e{i}a")
        a.word(f"e{i}b")
    a.word("skip_model")   # live-settable: a model instance not to draw
    a.word("skip_caller")  # live-settable: a return address whose draws are skipped
    a.label("log")
    a(ppc.mflr(12))
    a.la(11, "skip_model")
    a(ppc.lwz(10, 0, 11), ppc.cmpw(10, 3))
    a.br("beq", "skip")
    a(ppc.lwz(10, 4, 11), ppc.cmpw(10, 12))
    a.br("beq", "skip")
    log_loop(a, 12, "done")
    a.label("done")
    continue_original(a, SITE)
    a.label("skip")
    a(ppc.BLR)
elif kind == "messages":
    CAVE, SITE, MAX = MSG_LOG, MSG_LOOKUP, MSG_MAX
    lo, hi = (int(x, 16) for x in sys.argv[3:5]) if len(sys.argv) > 4 else (0x10D, 0x11F)
    a = ppc.Asm(CAVE)
    a.word("count")
    for i in range(MAX):
        a.word(f"e{i}a")
        a.word(f"e{i}b")
    a.label("log")
    a(ppc.cmpwi(3, lo))
    a.br("blt", "done")
    a(ppc.cmpwi(3, hi))
    a.br("bgt", "done")
    a(ppc.lwz(12, 0, 1), ppc.lwz(12, 0, 12), ppc.lwz(12, 4, 12))  # two frames up: who asked for the text
    log_loop(a, 12, "done")
    a.label("done")
    continue_original(a, SITE)
else:
    raise SystemExit(__doc__)

blob = a.assemble()
size = {DRAW_LOG: 712, MSG_LOG: 444}[CAVE]
if len(blob) > size or word(CAVE) != DEAD_FIRST:
    raise SystemExit(f"0x{CAVE:08X}: {len(blob)} bytes for {size}, or the cave is already used")
data[off_of(CAVE):off_of(CAVE) + len(blob)] = blob
struct.pack_into(">I", data, off_of(SITE), ppc.b(SITE, a.labels["log"]))
open(path, "wb").write(data)
print(f"{kind} log: table at 0x{CAVE:08X} ({len(blob)} bytes), hook 0x{SITE:08X}")
