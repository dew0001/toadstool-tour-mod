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

Changes (v2):
  - Hold A after the hit: the shooter's update runs up to 3 times a frame (same result, faster)
  - Follow camera: cuts to behind and above the ball at launch, then glides after it
  - Putts: aimed (normal view and swing meter), stroked and followed from behind the ball, down the line;
    any other view, camera turn or side view shows the game's camera instead
  - No opening movie (boot or title idle), no shattered-glass transition during the flight

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

# ---- v2: hold A to fast-forward the shot, chase cam behind the ball (shots and putts)
CAVE2 = 0x8003E86C          # dead SDK C_MTX44Concat (4x4 matrices; the game only uses 3x4)
CAVE2_SIZE = 1104
PLAYERS = 0x804ECE70        # 4 player records, 0x5204 bytes each
PLAYER_STRIDE = 0x5204
CUR_PLAYER = 0x804E68FB     # byte: index of the player whose shot it is (bit 0x80 = none)
CAMERA_PTR = 0x802D7E64     # current camera: eye xyz at +0, look-at xyz at +0xC
PLAYER_UPDATE = 0x80423BBC  # one player's per-frame update (ball physics, shot camera, animation)
SHOT_CAMERA = 0x80456D1C    # shot camera, called from PLAYER_UPDATE while a shot plays out
HOOK_SHOOTER_UPDATE = 0x80405620  # golf scene: bl PLAYER_UPDATE for the shooter
HOOK_SHOT_CAMERA = 0x80425BB0     # PLAYER_UPDATE: bl SHOT_CAMERA
AIM_CAMERA = 0x80410838     # aim camera (r3 = shot setup), called from PLAYER_UPDATE while aiming
HOOK_AIM_CAMERA = 0x80424AF8      # PLAYER_UPDATE: bl AIM_CAMERA
SETUP_PTR = 0x5168          # player record: shot setup object
SETUP_CLUB = 0x1D4          # shot setup: club index
CLUB_PUTTER = 13
SETUP_VIEW = 0x1C4          # shot setup: aim view (5 normal, 0xB swing meter, 6 down the hole, 7 landing spot, ...)
SETUP_HELD = 0x100          # shot setup: held buttons (halfword)
PAD_Z = 0x10                # Z (the mod's Back button): side view while held
SETUP_ZOOM_IN = 0x12C       # shot setup: C-stick up/down (float; the mod's LT/RT switch views with it)
SETUP_TURN = 0x14C          # shot setup: camera turn from C-stick left/right (radians, springs back to 0)
SETUP_TARGET = 0x1EC        # shot setup: aim point xyz
AIM_BALL = 0x80502734       # golf overlay: ball position the aim camera works from
STATE_SWING, STATE_LAUNCHED = 5, 6  # player +0x24 during the swing / stroke animation
STATE_BALL_MOVING = 7       # player +0x24 while the ball flies/rolls
PAD_A = 0x100
FF_EXTRA_UPDATES = 2        # holding A runs this many extra updates per frame (3x speed)

# No opening movie: FUN_8000de5c plays the logos, then the opening movie (A/T/L) in a loop that runs until a
# button press or 0x2AE4 frames. The title screen reuses it as its idle movie. Skip straight past that loop.
MOVIE_LOOP = 0x8000E120       # loop head: cmpwi r29,0 (movie object made yet?), addi r28,r28,1
MOVIE_LOOP_EXIT = 0x8000E1D8  # after the loop: wait a frame, then `beq cr4` skips stopping a movie that never started

# Camera data block at CAVE2 (offsets from its start); the stub keeps its state here.
D_LAST_STATE, D_MODE, D_DIRX, D_DIRZ, D_PREV = 0x00, 0x04, 0x08, 0x0C, 0x10  # D_PREV: eye xyz, look xyz
D_ZOOM2, D_EPS2, D_TINY, D_HALF, D_THREEHALF, D_SMOOTH = 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C
D_PARAMS = 0x40  # per mode (0 shot, 1 putt, 2 putt aim): back, up, ahead, look-up
D_ONE = 0x70
CAM_TUNING = {  # distances in game units, which are feet
    "zoom2": 0.01,      # zoom stick squared above this (0.1 of full tilt) = player is zooming: game camera
    "eps2": 0.0004,     # below this squared horizontal speed (per frame), keep the last direction
    "smooth": 0.18,     # fraction of the way the camera moves toward its spot each frame
    "shot": (24.0, 12.0, 10.0, 0.0),  # high behind the ball, looking down at it (~19 degrees)
    "putt": (14.0, 5.0, 10.0, 0.0),   # roll: same spot as the putt aim view, so the stroke doesn't cut
    "aim": (14.0, 5.0, 10.0, 0.0),    # putt aim: backed up behind the ball on the line, golfer in view
}

# No glass-break transition: the shot camera asks the screen-transition manager (main.dol 0x80222988) for
# type 4, a shattered-glass wipe, when it cuts between flight views. Ask for -1 (none) instead, the value
# the game itself uses to cancel a transition.
GLASS_BREAK_SITES = [0x804570D0, 0x8045744C, 0x804574AC, 0x80457718]  # li r4,4 before bl FUN_8000f93c
LI_R4_4, LI_R4_NONE = 0x38800004, 0x3880FFFF


def normalize_xz(a, x, z, n2):
    """f{x}, f{z} /= sqrt(f{n2}), where f{n2} = x*x + z*z > 0. Uses f6-f9; r7 = data block."""
    a(ppc.frsqrte(6, n2), ppc.lfs(7, D_HALF, 7), ppc.lfs(8, D_THREEHALF, 7))
    for _ in range(2):  # Newton steps: y *= 1.5 - 0.5*x*y*y
        a(ppc.fmuls(9, 6, 6), ppc.fmuls(9, 9, n2), ppc.fmuls(9, 9, 7), ppc.fsubs(9, 8, 9), ppc.fmuls(6, 6, 9))
    a(ppc.fmuls(x, x, 6), ppc.fmuls(z, z, 6))


def place_camera(a, params):
    """f5-f7 = eye, f8-f10 = look-at, from ball f0-f2, unit direction f3/f4 and params at r12+params."""
    a(ppc.lfs(10, params, 12), ppc.lfs(11, params + 4, 12), ppc.lfs(12, params + 8, 12),
      ppc.lfs(13, params + 12, 12))
    a(ppc.fmuls(5, 3, 10), ppc.fsubs(5, 0, 5), ppc.fadds(6, 1, 11), ppc.fmuls(7, 4, 10), ppc.fsubs(7, 2, 7))
    a(ppc.fmuls(8, 3, 12), ppc.fadds(8, 0, 8), ppc.fadds(9, 1, 13), ppc.fmuls(10, 4, 12), ppc.fadds(10, 2, 10))


def cave2_code():
    """Assemble the v2 stubs. Returns (bytes, {name: address})."""
    a = ppc.Asm(CAVE2)
    # data block first, so the stubs can use fixed offsets from r7
    for name in ("last_state", "mode", "dirx", "dirz", "ex", "ey", "ez", "tx", "ty", "tz"):
        a.word(name)
    a.float("zoom2", CAM_TUNING["zoom2"])
    a.float("eps2", CAM_TUNING["eps2"])
    a.float("tiny", 1e-12)
    a.float("half", 0.5)
    a.float("threehalf", 1.5)
    a.float("smooth", CAM_TUNING["smooth"])
    for mode in ("shot", "putt", "aim"):
        for i, v in enumerate(CAM_TUNING[mode]):
            a.float(f"{mode}{i}", v)
    a.float("one", 1.0)
    assert a.here() - CAVE2 == D_ONE + 4

    # Fast-forward: replaces `bl PLAYER_UPDATE` for the shooter. r3 = shooter's record.
    a.label("ff")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1), ppc.stw(31, 12, 1), ppc.stw(30, 8, 1))
    a(ppc.mr(31, 3), ppc.li(30, FF_EXTRA_UPDATES))
    a.bl(PLAYER_UPDATE)
    a.label("ff_loop")
    a(ppc.lwz(4, 0x24, 31), ppc.cmpwi(4, STATE_BALL_MOVING))
    a.br("bne", "ff_done")
    a(ppc.lwz(4, 0x4F14, 31), ppc.lhz(4, 0, 4), ppc.andi_(4, 4, PAD_A))  # shooter's pad: held buttons
    a.br("beq", "ff_done")
    a(ppc.mr(3, 31))
    a.bl(PLAYER_UPDATE)
    a(ppc.addi(30, 30, -1), ppc.cmpwi(30, 0))
    a.br("bne", "ff_loop")
    a.label("ff_done")
    a(ppc.lwz(30, 8, 1), ppc.lwz(31, 12, 1), ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    # Chase cam: replaces `bl SHOT_CAMERA`. Runs the game's camera, then while the ball moves puts the
    # camera behind and above it along its direction of travel (eased after a clean cut at launch). During a
    # putt's stroke it holds the putt aim view, instead of the game's face-on stroke view.
    a.label("cam")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1))
    a.bl(SHOT_CAMERA)
    hi, lo = ppc.hi_lo(CUR_PLAYER)
    a(ppc.lis(3, hi), ppc.lbz(4, lo, 3), ppc.mulli(4, 4, PLAYER_STRIDE))
    hi, lo = ppc.hi_lo(PLAYERS)
    a(ppc.lis(5, hi), ppc.addi(5, 5, lo), ppc.add(5, 5, 4))           # r5 = shooter
    a.la(7, "last_state")                                            # r7 = data block
    a(ppc.lwz(6, 0x24, 5), ppc.lwz(8, D_LAST_STATE, 7), ppc.stw(6, D_LAST_STATE, 7),
      ppc.cmpwi(6, STATE_BALL_MOVING))
    a.br("beq", "cam_moving")
    a(ppc.cmpwi(6, STATE_SWING))
    a.br("blt", "cam_done")
    a(ppc.cmpwi(6, STATE_LAUNCHED))
    a.br("bgt", "cam_done")
    a(ppc.lwz(3, SETUP_PTR, 5), ppc.lwz(4, SETUP_CLUB, 3), ppc.cmpwi(4, CLUB_PUTTER))
    a.br("bne", "cam_done")
    a.br("bl", "aim_place")
    a.br("b", "cam_done")
    a.label("cam_moving")
    hi, lo = ppc.hi_lo(CAMERA_PTR)
    a(ppc.lwz(9, 0x1C, 5), ppc.lis(10, hi), ppc.lwz(10, lo, 10))      # r9 = ball, r10 = camera
    a(ppc.cmpwi(8, STATE_BALL_MOVING))
    a.br("beq", "cam_steady")
    # first moving frame: putt if the shooter has the putter out; aim along the game's camera until moving
    a(ppc.lwz(11, SETUP_PTR, 5), ppc.lwz(11, SETUP_CLUB, 11), ppc.cmpwi(11, CLUB_PUTTER), ppc.li(11, 0))
    a.br("bne", "cam_mode")
    a(ppc.li(11, 1))
    a.label("cam_mode")
    a(ppc.stw(11, D_MODE, 7))
    a(ppc.lfs(1, 0xC, 10), ppc.lfs(2, 0x0, 10), ppc.fsubs(1, 1, 2), ppc.stfs(1, D_DIRX, 7),
      ppc.lfs(1, 0x14, 10), ppc.lfs(2, 0x8, 10), ppc.fsubs(1, 1, 2), ppc.stfs(1, D_DIRZ, 7))
    a.label("cam_steady")
    # direction: horizontal velocity, or the last direction when the ball has (nearly) stopped
    a(ppc.lfs(3, 0x50, 9), ppc.lfs(4, 0x58, 9), ppc.fmuls(5, 3, 3), ppc.fmuls(6, 4, 4), ppc.fadds(5, 5, 6),
      ppc.lfs(6, D_EPS2, 7), ppc.fcmpu(5, 6))
    a.br("bge", "cam_dir")
    a(ppc.lfs(3, D_DIRX, 7), ppc.lfs(4, D_DIRZ, 7), ppc.fmuls(5, 3, 3), ppc.fmuls(6, 4, 4), ppc.fadds(5, 5, 6),
      ppc.lfs(6, D_TINY, 7), ppc.fcmpu(5, 6))
    a.br("blt", "cam_done")
    a.label("cam_dir")
    normalize_xz(a, 3, 4, 5)
    a(ppc.stfs(3, D_DIRX, 7), ppc.stfs(4, D_DIRZ, 7))
    a(ppc.lwz(11, D_MODE, 7), ppc.mulli(11, 11, 16), ppc.add(12, 7, 11))
    a(ppc.lfs(0, 0x9C, 9), ppc.lfs(1, 0xA0, 9), ppc.lfs(2, 0xA4, 9))   # ball position
    place_camera(a, D_PARAMS)
    a(ppc.lfs(12, D_SMOOTH, 7), ppc.cmpwi(8, STATE_BALL_MOVING))
    a.br("beq", "cam_glide")
    a(ppc.lfs(12, D_ONE, 7))  # first moving frame: cut straight to the follow spot (gliding there folds the view)
    a.label("cam_glide")
    for i, f in enumerate((5, 6, 7)):  # eye glides: prev += (want - prev) * smooth; write camera
        a(ppc.lfs(11, D_PREV + 4 * i, 7), ppc.fsubs(f, f, 11), ppc.fmuls(f, f, 12), ppc.fadds(f, 11, f),
          ppc.stfs(f, D_PREV + 4 * i, 7), ppc.stfs(f, 4 * i, 10))
    for i, f in ((3, 8), (4, 9), (5, 10)):  # look-at stays on the ball, so a fast ball never drifts off screen
        a(ppc.stfs(f, 4 * i, 10))
    a.label("cam_done")
    a(ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    # Putt aim view: replaces `bl AIM_CAMERA` (r3 = shot setup, r4 passed through). Runs the game's aim
    # camera, then with the putter out in the normal view (or on the swing meter) puts the camera behind the
    # ball on the line to the aim point. Every way of looking around wins: another view (LT/RT, X/Y), turning
    # the camera (right stick) or the side view (Back) shows the game's camera until let go.
    a.label("aim")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1), ppc.stw(31, 12, 1), ppc.mr(31, 3))
    a.bl(AIM_CAMERA)
    a.la(7, "last_state")
    a(ppc.lwz(4, SETUP_CLUB, 31), ppc.cmpwi(4, CLUB_PUTTER))
    a.br("bne", "aim_done")
    a(ppc.lwz(4, SETUP_VIEW, 31), ppc.cmpwi(4, 5))
    a.br("beq", "aim_view")
    a(ppc.cmpwi(4, 0xB))
    a.br("bne", "aim_done")
    a.label("aim_view")
    a(ppc.lfs(1, SETUP_ZOOM_IN, 31), ppc.fmuls(1, 1, 1), ppc.lfs(2, D_ZOOM2, 7), ppc.fcmpu(1, 2))
    a.br("bgt", "aim_done")
    a(ppc.lfs(1, SETUP_TURN, 31), ppc.fmuls(1, 1, 1), ppc.fcmpu(1, 2))  # camera turned more than ~6 degrees
    a.br("bgt", "aim_done")
    a(ppc.lhz(4, SETUP_HELD, 31), ppc.andi_(4, 4, PAD_Z))                 # side view held
    a.br("bne", "aim_done")
    a(ppc.mr(3, 31))
    a.br("bl", "aim_place")
    a.label("aim_done")
    a(ppc.lwz(31, 12, 1), ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    # Leaf: camera behind the ball on the line to the aim point. r3 = shot setup, r7 = data block.
    a.label("aim_place")
    hi, lo = ppc.hi_lo(AIM_BALL)
    a(ppc.lis(8, hi), ppc.addi(8, 8, lo), ppc.lfs(0, 0, 8), ppc.lfs(1, 4, 8), ppc.lfs(2, 8, 8))   # ball
    a(ppc.lfs(3, SETUP_TARGET, 3), ppc.fsubs(3, 3, 0), ppc.lfs(4, SETUP_TARGET + 8, 3), ppc.fsubs(4, 4, 2))
    a(ppc.fmuls(5, 3, 3), ppc.fmuls(6, 4, 4), ppc.fadds(5, 5, 6), ppc.lfs(6, D_TINY, 7), ppc.fcmpu(5, 6))
    a.br("blt", "aim_place_done")
    normalize_xz(a, 3, 4, 5)
    a(ppc.mr(12, 7))
    place_camera(a, D_PARAMS + 0x20)
    hi, lo = ppc.hi_lo(CAMERA_PTR)
    a(ppc.lis(10, hi), ppc.lwz(10, lo, 10))
    for i, f in enumerate((5, 6, 7, 8, 9, 10)):
        a(ppc.stfs(f, 4 * i, 10))
    a.label("aim_place_done")
    a(ppc.BLR)

    blob = a.assemble()
    if len(blob) > CAVE2_SIZE:
        raise SystemExit(f"v2 code is {len(blob)} bytes; only {CAVE2_SIZE} available")
    return blob, {"ff": a.labels["ff"], "cam": a.labels["cam"], "aim": a.labels["aim"]}


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


def patch_dol(src, dst, cave, stubs, cave2):
    data = bytearray(open(src, "rb").read())
    t0_off = struct.unpack_from(">I", data, 0x00)[0]
    t0_addr = struct.unpack_from(">I", data, 0x48)[0]
    base = t0_addr - t0_off  # address of file offset 0, for word()/put()

    for addr, first, code in ((CAVE, 0x9421FF70, cave), (CAVE2, 0x7C0802A6, cave2)):
        if word(data, base, addr) != first:  # still the original (dead) function
            raise SystemExit(f"0x{addr:08X}: expected first instruction {first:08X}")
        data[addr - base:addr - base + len(code)] = code
    put(data, base, ASPECT_CONST, K_ASPECT, 0x3F9BE76D)
    put(data, base, ORTHO_HOOK, ppc.b(ORTHO_HOOK, stubs[ORTHO_HOOK]), ppc.fdivs(10, 9, 8))
    for hook in DOL_MATRIX_HOOKS:
        check_matrix_site(data, base, hook)
        put(data, base, hook, ppc.b(hook, stubs[hook]), LI_R4_1)
    if word(data, base, MOVIE_LOOP_EXIT + 8) != 0x41B20058:  # beq cr4, past the movie's stop/destroy calls
        raise SystemExit(f"0x{MOVIE_LOOP_EXIT + 8:08X}: not the expected movie loop exit")
    put(data, base, MOVIE_LOOP, 0x2E1D0000, 0x2C1D0000)  # cmpwi cr4,r29,0: r29 = 0 here, so cr4 = "no movie"
    put(data, base, MOVIE_LOOP + 4, ppc.b(MOVIE_LOOP + 4, MOVIE_LOOP_EXIT), 0x3B9C0001)
    open(dst, "wb").write(data)
    print(f"main.dol: aspect 1.624, {1 + len(DOL_MATRIX_HOOKS)} hooks, {len(cave)}-byte cave at 0x{CAVE:08X}"
          f" (aspect write {'on' if ASPECT_WRITE else 'off'}, unlock {'on' if UNLOCK else 'off'}), no opening movie")


def patch_overlay(clean_files, build_files, rel, stubs, v2):
    raw = open(os.path.join(clean_files, *rel.split("/")), "rb").read()
    kind, _ = lz.header(raw)
    blob, _ = lz.decompress(raw)
    buf = bytearray(blob)
    for hook in OVERLAY_MATRIX_HOOKS[rel]:
        check_matrix_site(buf, OVERLAY_BASE, hook)
        put(buf, OVERLAY_BASE, hook, ppc.b(hook, stubs[hook]), LI_R4_1)
    if rel == "C/L/V":  # v2 hooks live in the golf overlay
        put(buf, OVERLAY_BASE, HOOK_SHOOTER_UPDATE, ppc.bl(HOOK_SHOOTER_UPDATE, v2["ff"]),
            ppc.bl(HOOK_SHOOTER_UPDATE, PLAYER_UPDATE))
        put(buf, OVERLAY_BASE, HOOK_SHOT_CAMERA, ppc.bl(HOOK_SHOT_CAMERA, v2["cam"]),
            ppc.bl(HOOK_SHOT_CAMERA, SHOT_CAMERA))
        put(buf, OVERLAY_BASE, HOOK_AIM_CAMERA, ppc.bl(HOOK_AIM_CAMERA, v2["aim"]),
            ppc.bl(HOOK_AIM_CAMERA, AIM_CAMERA))
        for site in GLASS_BREAK_SITES:
            if word(buf, OVERLAY_BASE, site + 4) != 0x38632988:  # addi r3,r3,0x2988: the transition manager
                raise SystemExit(f"0x{site:08X}: not a glass-break transition request")
            put(buf, OVERLAY_BASE, site, LI_R4_NONE, LI_R4_4)
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
    cave2, v2 = cave2_code()
    print(f"v2 code: {len(cave2)} bytes at 0x{CAVE2:08X} (fast-forward 0x{v2['ff']:08X},"
          f" chase cam 0x{v2['cam']:08X}, putt aim 0x{v2['aim']:08X})")
    patch_dol(os.path.join(clean, "sys", "main.dol"), os.path.join(build, "sys", "main.dol"), cave, stubs, cave2)
    for rel in OVERLAY_MATRIX_HOOKS:
        patch_overlay(os.path.join(clean, "files"), os.path.join(build, "files"), rel, stubs, v2)
    patch_ids(os.path.join(clean, "sys"), os.path.join(build, "sys"),
              os.path.join(clean, "files"), os.path.join(build, "files"))


if __name__ == "__main__":
    main()
