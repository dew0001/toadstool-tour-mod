"""Build the modded Toadstool Tour tree from a clean extracted disc.

Usage: python -I build_mod.py <clean disc dir> <build dir> [--version N] [--no-unlock] [--no-aspect-write] [--keep-id]
The build dir must already hold a copy of the clean tree (robocopy); this script only rewrites
the files it changes, reading every original from <clean disc dir>.

Changes (v1):
  - Widescreen built in (port of the gamemasterplc 16:9 Gecko code, without Gecko):
      * 3D aspect constant 1.218 -> 1.624 (x4/3), and the main camera's aspect re-asserted each frame
      * every 2D ortho projection widened by 4/3 so HUD art keeps its shape at 16:9
      * full-screen 2D layers at six call sites scaled back to full width
  - All courses and characters unlocked (the two Action Replay unlock codes, built in)
  - Own game ID GFTEMD and banner title, so it sits beside the original in Dolphin's list

Patch code lives over FUN_8006eab4, an SDK torus-drawing helper nothing on the disc references
(checked with find_dead_code.py). Low memory at 0x80001800 does NOT work: the code there is gone
by the time the game first draws.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402
import ppc  # noqa: E402

CAVE = 0x8006EAB4          # dead SDK function (GXDrawTorus-style helper)
CAVE_SIZE = 736
K_4_3 = 0x3FAAAAAB         # 4/3
K_ASPECT = 0x3FCFDF3B      # 1.624 = 1.218 * 4/3
ASPECT_CONST = 0x8015D940  # main.dol constant the camera setup reads (0x3F9BE76D = 1.218)
CAMERA_ASPECT = 0x8026C7F8  # main camera struct (0x8026C7C0) + 0x38
UNLOCK_FLAGS = 0x8022A3CC  # halfwords: players (A3CC) and tours/courses (A3CE)
ORTHO_HOOK = 0x8003E698    # inside C_MTXOrtho: fdivs f10,f9,f8 = 1/(right-left)
GX_SET_PROJECTION = 0x8006FCC0
LI_R4_1 = 0x38800001

DOL_MATRIX_HOOKS = [0x8000FAA8, 0x800255F4]
OVERLAY_MATRIX_HOOKS = {
    "C/L/V": [0x804303F8, 0x8043E2BC],  # golf overlay, loads at 0x80400000
    "B/U/C": [0x804017F0, 0x80401464],  # second overlay, same load address
}
OVERLAY_BASE = 0x80400000
GAME_ID = b"GFTEMD"
VERSION = sys.argv[sys.argv.index("--version") + 1] if "--version" in sys.argv else "1"
BANNER_TITLE = f"Mario Golf: Toadstool Tour (Mod v{VERSION})".encode("ascii")

UNLOCK = "--no-unlock" not in sys.argv
ASPECT_WRITE = "--no-aspect-write" not in sys.argv


def load_const(fr, addr):
    hi, lo = ppc.hi_lo(addr)
    return [ppc.lis(4, hi), ppc.lfs(fr, lo, 4)]


def ortho_stub(at):
    code = []
    if ASPECT_WRITE:
        hi, lo = ppc.hi_lo(CAMERA_ASPECT)
        code += load_const(12, CAVE + 4) + [ppc.lis(4, hi), ppc.stfs(12, lo, 4)]  # camera aspect = 1.624
    if UNLOCK:
        hi, lo = ppc.hi_lo(UNLOCK_FLAGS)
        code += [ppc.lis(4, hi), ppc.li(0, -1), 0x90040000 | (lo & 0xFFFF)]       # stw r0: both flags = FFFF
    code += load_const(12, CAVE)                                                  # f12 = 4/3
    code += [ppc.fmuls(8, 12, 8),                                                 # (right-left) *= 4/3
             ppc.fdivs(10, 9, 8)]                                                 # original instruction
    code.append(ppc.b(at + 4 * len(code), ORTHO_HOOK + 4))
    return code


def matrix_stub(at, hook):
    code = load_const(13, CAVE) + [                                               # f13 = 4/3
        ppc.lfs(12, 0x0, 3), ppc.fmuls(12, 13, 12), ppc.stfs(12, 0x0, 3),          # m[0][0] *= 4/3
        ppc.lfs(12, 0xC, 3), ppc.fmuls(12, 13, 12), ppc.stfs(12, 0xC, 3),          # m[0][3] *= 4/3
        LI_R4_1,                                                                  # original instruction
    ]
    code.append(ppc.b(at + 4 * len(code), hook + 4))
    return code


def build_cave():
    """Return (cave bytes, {hook address: stub address})."""
    words = [K_4_3, K_ASPECT]
    stubs = {}
    at = CAVE + 8
    hooks = [ORTHO_HOOK] + DOL_MATRIX_HOOKS + sum(OVERLAY_MATRIX_HOOKS.values(), [])
    for hook in hooks:
        code = ortho_stub(at) if hook == ORTHO_HOOK else matrix_stub(at, hook)
        stubs[hook] = at
        words += code
        at += 4 * len(code)
    blob = b"".join(struct.pack(">I", w) for w in words)
    if len(blob) > CAVE_SIZE:
        raise SystemExit(f"cave code is {len(blob)} bytes; only {CAVE_SIZE} available")
    return blob, stubs


def word(buf, base, addr):
    return struct.unpack_from(">I", buf, addr - base)[0]


def put(buf, base, addr, value, expect):
    old = word(buf, base, addr)
    if old != expect:
        raise SystemExit(f"0x{addr:08X}: expected {expect:08X}, found {old:08X} (not a clean GFTE01 file?)")
    struct.pack_into(">I", buf, addr - base, value)


def check_matrix_site(buf, base, hook):
    """The stub assumes r3 = matrix just built by C_MTXOrtho and a GXSetProjection call right after."""
    following = [word(buf, base, hook + 4 * i) for i in (1, 2)]
    targets = [hook + 4 * i + ((w & 0x03FFFFFC) - (0x04000000 if w & 0x02000000 else 0))
               for i, w in zip((1, 2), following) if w & 0xFC000003 == 0x48000001]
    if GX_SET_PROJECTION not in targets:
        raise SystemExit(f"0x{hook:08X}: no GXSetProjection call right after the hook")


def patch_dol(src, dst, cave, stubs):
    data = bytearray(open(src, "rb").read())
    t0_off = struct.unpack_from(">I", data, 0x00)[0]
    t0_addr = struct.unpack_from(">I", data, 0x48)[0]
    base = t0_addr - t0_off  # address of file offset 0, for word()/put()

    if word(data, base, CAVE) & 0xFFFF0000 != 0x94210000:  # stwu r1,-N(r1): still the original function
        raise SystemExit(f"0x{CAVE:08X}: not the expected function prologue")
    data[CAVE - base:CAVE - base + len(cave)] = cave
    put(data, base, ASPECT_CONST, K_ASPECT, 0x3F9BE76D)
    put(data, base, ORTHO_HOOK, ppc.b(ORTHO_HOOK, stubs[ORTHO_HOOK]), ppc.fdivs(10, 9, 8))
    for hook in DOL_MATRIX_HOOKS:
        check_matrix_site(data, base, hook)
        put(data, base, hook, ppc.b(hook, stubs[hook]), LI_R4_1)
    open(dst, "wb").write(data)
    print(f"main.dol: aspect 1.624, {1 + len(DOL_MATRIX_HOOKS)} hooks, {len(cave)}-byte cave at 0x{CAVE:08X}"
          f" (aspect write {'on' if ASPECT_WRITE else 'off'}, unlock {'on' if UNLOCK else 'off'})")


def patch_overlay(clean_files, build_files, rel, stubs):
    raw = open(os.path.join(clean_files, *rel.split("/")), "rb").read()
    kind, _ = lz.header(raw)
    blob, _ = lz.decompress(raw)
    buf = bytearray(blob)
    for hook in OVERLAY_MATRIX_HOOKS[rel]:
        check_matrix_site(buf, OVERLAY_BASE, hook)
        put(buf, OVERLAY_BASE, hook, ppc.b(hook, stubs[hook]), LI_R4_1)
    out = lz.pack(kind, bytes(buf))
    if lz.decompress(out)[0] != bytes(buf):
        raise SystemExit(f"{rel}: repack check failed")
    open(os.path.join(build_files, *rel.split("/")), "wb").write(out)
    print(f"{rel}: {len(OVERLAY_MATRIX_HOOKS[rel])} hooks, repacked {len(raw):,} -> {len(out):,} bytes")


def patch_ids(clean_sys, build_sys, clean_files, build_files):
    boot = bytearray(open(os.path.join(clean_sys, "boot.bin"), "rb").read())
    if boot[:6] != b"GFTE01":
        raise SystemExit(f"boot.bin: expected GFTE01, found {boot[:6]!r}")
    if "--keep-id" not in sys.argv:
        boot[:6] = GAME_ID
    open(os.path.join(build_sys, "boot.bin"), "wb").write(boot)
    bnr = bytearray(open(os.path.join(clean_files, "opening.bnr"), "rb").read())
    if bnr[:4] != b"BNR1":
        raise SystemExit("opening.bnr: not a BNR1 banner")
    long_name = 0x1820 + 0x20 + 0x20  # after short name and short maker
    bnr[long_name:long_name + 0x40] = BANNER_TITLE.ljust(0x40, b"\x00")
    open(os.path.join(build_files, "opening.bnr"), "wb").write(bnr)
    print(f"game ID {boot[:6].decode()}, banner title {BANNER_TITLE.decode()!r}")


def main():
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--version"]
    clean, build = args[:2]
    ppc.selftest()
    cave, stubs = build_cave()
    patch_dol(os.path.join(clean, "sys", "main.dol"), os.path.join(build, "sys", "main.dol"), cave, stubs)
    for rel in OVERLAY_MATRIX_HOOKS:
        patch_overlay(os.path.join(clean, "files"), os.path.join(build, "files"), rel, stubs)
    patch_ids(os.path.join(clean, "sys"), os.path.join(build, "sys"),
              os.path.join(clean, "files"), os.path.join(build, "files"))


if __name__ == "__main__":
    main()
