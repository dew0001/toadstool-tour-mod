"""v27: Football, a Team Play game (Andrew 2026-10-30: "football mode. ... its a 2 person gamemode or 2v2. 1p is the QB
and 2p is the Receiver. qb starts on the box and has to throw it to the receiver to progress the hole which would be a
timed thing like the golf shot so power, impact etc. the receiver would be where the landing star would normally be and
attached to the aim of the qb at first ... as soon as the ball is thrown the camera would switch to the receiver and
they have to be in a tight zone to catch the ball. then the next shot they would switch places. the pin wouldnt be a
pin it would be a field goal post ... whoevers turn it is they would have to kick it in the field"; then "obviously wind
would play a factor in passes and field goal kicks", "when it switches to the receiver they would be able to run around
and stand,dive,jump for the ball", "it needs to be a giant fiedl goal that can be kicked through", "im imagining a big
field goal that can be kicked thru from far away if we so choose").

The game: Team Play's alternate shot (Doubles), one team of 2 (2 humans) or 2v2 (4 humans). Every shot is the golf
swing (power, impact, wind, the lie) with one of four shot types, picked with LB/RB (the game's club change; Andrew
2026-11-01: "throw types that have their advantages and disadvantages", "field goal attempt is decided by the team or
player just switch to the field goal shot type", "attributes per shot type should mirror the character"): SHOT_TYPES,
each one of the golfer's clubs (so its reach, timing window and flight are the golfer's own), the last a field goal
try (fb_choose; a box names the type; fbpose.py keeps the bag, the stepper and the launch angles).
A pass: the landing star is the receiver (the shooter's partner), placed by the QB's aim; when the ball leaves, the
camera goes behind the receiver, who runs with the stick, jumps with A (catches higher) and dives with B (farther, then
down a moment). A ball that reaches the receiver's catch zone is caught: it stops there and the team plays on from that
spot. A ball that touches anything first is incomplete: the stroke counts and the ball goes back where it was thrown
from. A kick has to cross the plane of the posts (at the pin, square to the kick) between the uprights and over the
crossbar; good ends the hole like holing out, no good is played again from the same spot. The posts are giant (60 ft
between the uprights, the crossbar 30 ft up), drawn where the flag would be. The partners swap every shot (Doubles' own
toggle). The green plays as field (no putter). While a play is in the air the ball is drawn football-sized and the
receiver's star bigger and steady; a text box says what happened.

The game side (RE-NOTES "Football (v27)"):
  - fb_frame (bl on FRAME_HOOK, `cmpwi r21,0` right after the player update's shot camera call, where both paths meet;
    r31 = the player being updated, every update of every player, fast-forward's extra ones included) works for the
    shooter while its state (+0x24) is 7, the ball in the air or rolling: the first such update sets the play up as
    a pass or a kick, the pick (fb_launch); passes move the receiver (fb_run: the partner's pad, player +0x4F14: +4 new presses, +0x17/+0x18 the
    main stick) on the ground (FUN_8040100c(x, y, z, out): the ground under a point, ray from y + 9.6 down 160 ft)
    and test the catch (fb_catch); kicks test the posts' plane (fb_kick); a manual swing's spin combo dips or floats
    the falling ball (fbpose.py's fp_spinfly); the first contact (fb_contact: the ball's
    y velocity, feet a frame, jumping up, or its speed across halving) ends the play; the ball is then held where it
    stopped until the state moves on (fb_hold). Passes put the setup's target (+0x1EC, what the landing star is drawn
    at) on the receiver and the camera behind the receiver, looking back toward the ball (fb_cam).
  - The landing star (FUN_804317f0, the scene's draw) fades out once the shooter's state is 5-8 or the meter's stage
    is set; star_stage / star_state answer "aiming" while a pass is live, so the star stays lit on the receiver.
  - FUN_80414818(lie) and FUN_804148c4(ball) answer "on the green" (surface code 2) for every caller (the putter,
    the putt camera and grid, the pick order): with football on they answer no.
  - After the shot, teams.py's shot hook (SHOT_HOOK, the penalty and lie block) goes to fb_shot: a catch out of bounds
    or in a hazard counts as incomplete; incomplete and no good skip the block (the team's lie stays: the next turn
    starts from it); a good kick writes the team's lie at the pin, in the hole (lie +0x28), which the game's hole-out
    test right after (0x8041F958) scores; a catch runs the game's block (the new lie).
  - The posts: the flag's drawer (FUN_8044bf34) draws the flag with `bl MODEL_DRAW` (POSTS_HOOK); in football fb_posts
    draws flat-shaded boxes there instead (the slope grid drawer's GX state: one colour channel from the material
    register, position-only vertices; view x the posts' frame through FUN_8001e980).
  - The star's blink (0x804CE588) and scale matrix (0x805060B0), the ball's scale matrix (0x805025E8, 0.14): data the
    draws read every frame, set while a play is in the air (star_alpha, fb_tick).
  - Text boxes: FUN_80024f1c(message, x, y, -1, 15) / FUN_80024c98(box) (fb_say / fb_unsay); our messages are answered
    by fb_messages, which teams.py's message hook goes on to.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppc  # noqa: E402

# dead main.dol functions (mod/ghidra_out/golf/dead_unused.txt, find_dead_code.py): address, size, first word
CAVES = {
    "state": (0x800389B4, 272, 0x7C0802A6),     # the play's state (r31 in the stubs)
    "consts": (0x8003D9A8, 256, 0x7C0802A6),    # tunables and texts (within 32 KB of "state": same base register)
    "frame": (0x80046A6C, 268, 0x7C0802A6),
    "run": (0x800409A0, 268, 0x7C0802A6),
    "run2": (0x800838B0, 264, 0x9421FFE0),
    "run3": (0x8004BC04, 248, 0x7C0802A6),
    "track": (0x8005A058, 240, 0x7C0802A6),
    "launch": (0x8005A9A4, 264, 0x7C0802A6),
    "catch": (0x80069130, 260, 0x9421FFE8),
    "contact": (0x80049624, 260, 0x7C0802A6),
    "kick": (0x80045AC8, 260, 0x7C0802A6),
    "cam": (0x8008CAF4, 256, 0x9421FFF0),
    "cam2": (0x800429C8, 236, 0x7C0802A6),
    "cam3": (0x8008DA10, 232, 0x9421FFF0),
    "shot": (0x80073F28, 256, 0x9421FFE0),
    "small": (0x80057670, 256, 0x7C0802A6),
    "ground": (0x80083208, 248, 0x9421FFE0),
    "posts": (0x8004C43C, 228, 0x7C0802A6),     # the goalposts
    "posts_m": (0x8003D814, 240, 0x9421FFD8),
    "posts2": (0x80054E1C, 224, 0x7C0802A6),
    "posts2b": (0x80072D80, 224, 0x9421FFF0),
    "posts3": (0x80073560, 224, 0x9421FFE0),
    "posts4": (0x8009654C, 220, 0x9421FFF0),
    "pdata": (0x80030B34, 232, 0x7C0802A6),
    "say": (0x8001BD94, 220, 0x9421FFE8),       # what happened, in a text box
    "tick": (0x80094484, 216, 0x9421FFE0),
    "texts": (0x8007FE70, 220, 0x9421FFF0),
    "star": (0x8003FF04, 216, 0x7C0802A6),      # the receiver's star, steady and bigger
    "choose": (0x8005C678, 212, 0x7C0802A6),    # pass or kick
}

# ---- game addresses (golf overlay unless noted)
PLAYERS, PLAYER_SIZE = 0x804ECE70, 0x5204
P_REC, P_BALL, P_STATE, P_PAD, P_SETUP = 0x8, 0x1C, 0x24, 0x4F14, 0x5168
D15, D16, D17 = 0x804E68F9, 0x804E68FA, 0x804E68FB    # sides, records, the shooter (0x80 = nobody)
PIN = 0x804E6864                                       # x, y, z
CAMERA = 0x802D7E64                                    # -> eye xyz +0, look-at xyz +0xC
B_POS, B_VEL = 0x9C, 0x50                              # ball record: position, velocity (feet, feet a frame)
S_TARGET = 0x1EC                                       # setup: the aim point, where the landing star is drawn
S_CLUB = 0x1D4                                         # setup: the club (13 the putter)
STATE_MOVING = 7
PAD_PRESSED, PAD_STICK_X, PAD_STICK_Y = 4, 0x17, 0x18
PAD_A, PAD_B = 0x100, 0x200
GROUND = 0x8040100C            # (f1 x, f2 y, f3 z, r3 out[6]): out = the point under it, then the normal
REC_LIE, REC_PENALTY_KIND = 0xB4, 0x1C4
LIE_IN_HOLE = 0x28
OB_TEST, HAZARD_TEST = 0x8041CC34, 0x8041CCBC          # (ball) -> nonzero when out of bounds / in a hazard
SHOT_HOOK = (0x8041F878, 0x807E001C)   # lwz r3,28(r30): teams.py's "shot" sends football here (fb_shot)
SHOT_DONE = 0x8041F958

FRAME_HOOK = (0x80425BB4, 0x2C150000)  # cmpwi r21,0: after `bl SHOT_CAMERA` (0x80425BB0) and its skip meet
STAR_STAGE = (0x8043183C, 0x80093CB4)  # lwz r0,0x3CB4(r9): FUN_804317f0 reads the meter's stage
STAR_STATE = (0x8043184C, 0x80030024)  # lwz r0,36(r3): ... and the shooter's state
GREEN_LIE = (0x80414818, 0x9421FFE8)   # stwu r1,-24(r1): FUN_80414818(lie), "on the green"
GREEN_BALL = (0x804148C4, 0x9421FFE8)  # stwu r1,-24(r1): FUN_804148c4(ball), the same for a ball

# ---- the round's setup byte (teams.MODE_BYTE): 7 = Football 2v2, 8 = Football, one team of 2
FOOTBALL, FOOTBALL_TEAM = 7, 8
KIND_PASS, KIND_KICK = 1, 2
PH_FLY, PH_HOLD, PH_DEAD = 0, 1, 2
R_NONE, R_CAUGHT, R_INCOMPLETE, R_GOOD, R_NO_GOOD = 0, 1, 2, 3, 4

# ---- tunables (feet and frames; the game runs 60 updates a second)
YD = 3.0
TUNING = {
    "run": 0.40,               # receiver's top speed, feet a frame (24 ft/s, 8 yd/s)
    "accel": 0.25,             # how fast the receiver gets to the stick's speed (share a frame)
    "stick": 1 / 56.0,         # pad stick units for full tilt (the game's +-56 or so; more is clamped)
    "dead2": 0.04,             # stick dead zone, squared
    "dive_speed": 0.75,        # a dive's speed, feet a frame
    "dive_frames": 16,         # in the air
    "down_frames": 40,         # then on the ground, can't move or catch
    "jump_frames": 36,
    "jump_height": 3.5,        # feet at the top of a jump
    "catch_r": 3.0,            # catch zone: radius round the receiver (feet) ...
    "reach": 8.0,              # ... up to this high (plus the jump)
    "dive_r": 5.5,             # diving: farther ...
    "dive_reach": 3.5,         # ... but low
    "low": -1.0,               # a ball this far under the receiver's feet (a slope) still counts
    "lift": 0.1,               # a held ball sits this far over the ground
    "ground_max": 9.0,         # the ground query found nothing (it returns y + 9.6)
    "contact_vy": -0.02,       # contact: the y velocity was falling at least this ...
    "contact_dvy": 0.06,       # ... and jumped up by this in one frame
    "hs_min": 0.01,            # or the speed across (squared) was at least this ...
    "hs_drop": 0.5,            # ... and fell under this share of it
    "half_width": 30.0,        # the posts (giant, see POST_BOXES): uprights 60 ft apart ...
    "crossbar": 30.0,          # ... over a crossbar 30 ft up
    "cam_back": 32.0,          # receiver camera: this far behind the receiver (away from the ball) ...
    "cam_up": 10.0,            # ... this high, looking between the receiver and the ball ...
    "cam_ball_w": 1.6,         # ... nearer the receiver (1 = halfway in angle) ...
    "cam_look_up": 2.0,        # ... raised this much,
    "cam_clear": 6.0,          # ... and at least this high over the ground under it,
    "cam_fov": 60.0,           # ... seeing this wide (the shot camera's 45-50), looking no lower than
    "cam_floor": 3.0,          # ... this over the receiver's ground
    "cam_probe": 100.0,        # (the ground query under the eye starts this far over the receiver)
    "cam_glide": 0.2,
}

STATE_FIELDS = ("on", "last", "kind", "phase", "result", "judged", "cam_first",
                "rx", "ry", "rz", "rvx", "rvz", "jump_t", "dive_t", "dive_x", "dive_z", "jump_h",
                "fx", "fz", "nx", "nz", "prev_s", "pbx", "pby", "pbz", "pvy", "phs2", "hx", "hy", "hz",
                "ex", "ey", "ez", "lx", "ly", "lz", "pnx", "pnz", "said", "box", "box_t",
                "kick_pick", "type")
S = {name: 4 * k for k, name in enumerate(STATE_FIELDS)}
S["ground"] = 4 * len(STATE_FIELDS)          # 6 floats for GROUND's answer
STATE_SIZE = S["ground"] + 24
ON = CAVES["state"][0] + S["on"]             # the football flag (teams.py's setup writes it each round)

MSG_HELP = 0x7FED
HELP_TEXT = b"\x074\x094One QB, the others catch,\x01then kick a field goal!\x00"
MSG_HELP2 = 0x7FBF                             # v28 Pigskin 2v2
HELP2_TEXT = b"\x074\x094Two-vs-two: pass, catch,\x01then kick it in!\x00"

CONST_LIST = ("zero", "one", "half", "threehalf", "tiny", "run", "accel", "stick", "dead2",
              "dive_speed", "dive_total", "down_frames", "jump_frames", "inv_jump_frames", "jump_h4", "catch_r2",
              "reach", "dive_r2", "dive_reach", "low", "lift", "ground_max", "contact_vy", "contact_dvy", "hs_min",
              "hs_drop", "half_width", "crossbar", "cam_back", "cam_up", "cam_dist", "cam_ball_w", "cam_look_up", "cam_glide", "cam_clear",
              "cam_probe", "cam_fov", "cam_floor", "star_big", "ball_normal",
              "ball_big")


def const_values():
    t = TUNING
    return {"zero": 0.0, "one": 1.0, "half": 0.5, "threehalf": 1.5, "tiny": 1e-6,
            "run": t["run"], "accel": t["accel"], "stick": t["stick"],
            "dead2": t["dead2"], "dive_speed": t["dive_speed"],
            "dive_total": float(t["dive_frames"] + t["down_frames"]), "down_frames": float(t["down_frames"]),
            "jump_frames": float(t["jump_frames"]), "inv_jump_frames": 1.0 / t["jump_frames"],
            "jump_h4": 4 * t["jump_height"], "catch_r2": t["catch_r"] ** 2, "reach": t["reach"],
            "dive_r2": t["dive_r"] ** 2, "dive_reach": t["dive_reach"], "low": t["low"], "lift": t["lift"],
            "ground_max": t["ground_max"], "contact_vy": t["contact_vy"], "contact_dvy": t["contact_dvy"],
            "hs_min": t["hs_min"], "hs_drop": t["hs_drop"], "half_width": t["half_width"],
            "crossbar": t["crossbar"], "cam_back": t["cam_back"], "cam_up": t["cam_up"],
            "cam_dist": (t["cam_back"] ** 2 + t["cam_up"] ** 2) ** 0.5, "cam_ball_w": t["cam_ball_w"],
            "cam_look_up": t["cam_look_up"], "cam_glide": t["cam_glide"],
            "cam_clear": t["cam_clear"], "cam_probe": t["cam_probe"], "cam_fov": t["cam_fov"],
            "cam_floor": t["cam_floor"], "star_big": STAR_BIG, "ball_normal": BALL_NORMAL, "ball_big": BALL_BIG}


C0 = CAVES["consts"][0] - CAVES["state"][0]      # the constants, from the state's base
C = {"magic": C0}                                # 0x43300000_80000000 (int -> float), 8-aligned
for _k, _name in enumerate(CONST_LIST):
    C[_name] = C0 + 8 + 4 * _k
C["help"] = C0 + 8 + 4 * len(CONST_LIST)
assert CAVES["consts"][0] % 8 == 0 and C["help"] + len(HELP_TEXT) <= C0 + CAVES["consts"][1]


# ---- instructions ppc.py doesn't have
def lfd(frd, d, ra): return ppc._d(50, frd, d, ra)
def fsub(d, a, b): return 0xFC000028 | d << 21 | a << 16 | b << 11
def fabs(d, b): return 0xFC000210 | d << 21 | b << 11
def xoris(ra, rs, imm): return 0x6C000000 | rs << 21 | ra << 16 | (imm & 0xFFFF)
def xori(ra, rs, imm): return 0x68000000 | rs << 21 | ra << 16 | (imm & 0xFFFF)


BNELR, BGELR, BGTLR, BLELR = 0x4C820020, 0x4C800020, 0x4D810020, 0x4C810020
BEQLR, BLTLR, BLR = ppc.BEQLR, ppc.BLTLR, ppc.BLR


def _base(a):
    """r31 = the state (and, at C[...], the constants)."""
    hi, lo = ppc.hi_lo(CAVES["state"][0])
    a(ppc.lis(31, hi), ppc.addi(31, 31, lo))


def _normalize(a, x, z, n2, t0, t1, t2, t3):
    """f{x}, f{z} /= sqrt(f{n2}) (> 0), Newton twice on frsqrte; uses f{t0}-f{t3}; r31 = state."""
    a(ppc.frsqrte(t0, n2), ppc.lfs(t1, C["half"], 31), ppc.lfs(t2, C["threehalf"], 31))
    for _ in range(2):
        a(ppc.fmuls(t3, t0, t0), ppc.fmuls(t3, t3, n2), ppc.fmuls(t3, t3, t1), ppc.fsubs(t3, t2, t3),
          ppc.fmuls(t0, t0, t3))
    a(ppc.fmuls(x, x, t0), ppc.fmuls(z, z, t0))


def _enter(a, size):
    a(ppc.stwu(1, -size, 1), ppc.mflr(0), ppc.stw(0, size + 4, 1))


def _leave(a, size):
    a(ppc.lwz(0, size + 4, 1), ppc.mtlr(0), ppc.addi(1, 1, size), BLR)


# Internal stubs (called from fb_frame) read r28 = the setup, r29 = the ball, r30 = the shooter, r31 = the state and
# change none of them; they use r0, r3-r12 and f0-f13.

def make_frame(L):
    a = ppc.Asm(CAVES["frame"][0])
    # bl from FRAME_HOOK (replaces cmpwi r21,0); r31 = the player being updated. Every volatile register is free here
    # (one of the two paths in comes straight from a call); r21 and the saved ones are kept, and cr0 = r21 vs 0.
    a.label("fb_frame")
    a(ppc.stwu(1, -0x30, 1), ppc.mflr(0), ppc.stw(0, 0x34, 1), ppc.stmw(26, 0x10, 1))
    a(ppc.mr(30, 31))
    _base(a)
    a(ppc.lwz(0, S["on"], 31), ppc.cmpwi(0, 0))
    a.br("beq", "f_out")
    a(ppc.lis(12, 0x804E), ppc.lbz(0, D17 & 0xFFFF, 12), ppc.andi_(11, 0, 0x80))
    a.br("bne", "f_out")
    hi, lo = ppc.hi_lo(PLAYERS)
    a(ppc.mulli(0, 0, PLAYER_SIZE), ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.add(12, 12, 0), ppc.cmpw(12, 30))
    a.br("bne", "f_out")
    a(ppc.lwz(29, P_BALL, 30), ppc.lwz(28, P_SETUP, 30))
    a(ppc.lwz(3, P_STATE, 30), ppc.lwz(27, S["last"], 31), ppc.stw(3, S["last"], 31), ppc.mr(4, 27))
    a.bl(L["fb_tick"])                      # the text box's upkeep, the pick's default
    a(ppc.lwz(3, P_STATE, 30))
    a.bl(L["fb_choose"])                    # the shot type: pass or kick, and its name
    a(ppc.lwz(0, P_STATE, 30), ppc.cmpwi(0, STATE_MOVING))
    a.br("bne", "f_idle")
    a(ppc.cmpwi(27, STATE_MOVING))
    a.br("beq", "f_fly")
    a.bl(L["fb_launch"])
    a.label("f_fly")
    a(ppc.lwz(0, S["phase"], 31), ppc.cmpwi(0, PH_FLY))
    a.br("bne", "f_held")
    a(ppc.lwz(0, S["kind"], 31), ppc.cmpwi(0, KIND_PASS))
    a.br("bne", "f_kick")
    import fbpose   # (it imports this module) v28: the receivers (run, bump, catch) and the spin, in the golf tail
    tail = fbpose.build()[1]
    a.bl(tail["fp_recv_update"])
    a.br("b", "f_contact")
    a.label("f_kick")
    a.bl(L["fb_kick"])
    a.label("f_contact")
    a.bl(tail["fp_spinfly"])
    a(ppc.lwz(0, S["phase"], 31), ppc.cmpwi(0, PH_FLY))
    a.br("bne", "f_held")
    a.bl(L["fb_contact"])
    a.br("b", "f_track")
    a.label("f_held")
    a.bl(L["fb_hold"])
    a.label("f_track")
    a.bl(L["fb_track"])
    a.bl(L["fb_said"])
    a.br("b", "f_out")
    a.label("f_idle")                       # no play in the air: the star stubs leave the star to the game; the
    a(ppc.li(0, 0), ppc.stw(0, S["kind"], 31))  # ball's place and velocity for the launch's first tests
    a.bl(L["fb_track"])
    a.label("f_out")
    a(ppc.lmw(26, 0x10, 1), ppc.lwz(0, 0x34, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x30), ppc.cmpwi(21, 0), BLR)

    return a


def make_ground(L):
    a = ppc.Asm(CAVES["ground"][0])
    # (f1 x, f2 y, f3 z) -> f1 = the ground's height under (x, z), or y when the query finds nothing near
    a.label("fb_ground")
    _enter(a, 0x20)
    a(ppc.stfs(2, 0x08, 1), ppc.addi(3, 31, S["ground"]))
    a.bl(GROUND)
    a(ppc.lfs(1, S["ground"] + 4, 31), ppc.lfs(2, 0x08, 1), ppc.lfs(0, C["ground_max"], 31), ppc.fadds(0, 2, 0),
      ppc.fcmpu(1, 0))
    a.br("blt", "g_out")
    a(ppc.fmr(1, 2))
    a.label("g_out")
    _leave(a, 0x20)
    # (f7, f8, f9 = f7^2 + f8^2) -> f7, f8 made a unit vector (or (0, 1) when tiny); uses f10-f13 (a leaf)
    a.label("fb_norm")
    a(ppc.lfs(10, C["tiny"], 31), ppc.fcmpu(9, 10))
    a.br("bgt", "n_go")
    a(ppc.lfs(7, C["zero"], 31), ppc.lfs(8, C["one"], 31), BLR)
    a.label("n_go")
    _normalize(a, 7, 8, 9, 10, 11, 12, 13)
    a(BLR)
    return a


def make_launch(L):
    a = ppc.Asm(CAVES["launch"][0])
    # The first update with the ball moving: pass or kick, and the play's state from the ball and the aim.
    a.label("fb_launch")
    _enter(a, 0x10)
    a(ppc.li(0, 0), ppc.stw(0, S["result"], 31), ppc.stw(0, S["phase"], 31), ppc.stw(0, S["judged"], 31),
      ppc.stw(0, S["said"], 31))
    a(ppc.lfs(0, C["zero"], 31))
    for name in ("rvx", "rvz", "jump_t", "dive_t", "jump_h"):
        a(ppc.stfs(0, S[name], 31))
    a(ppc.lfs(1, B_POS, 29), ppc.lfs(2, B_POS + 4, 29), ppc.lfs(3, B_POS + 8, 29))
    hi, lo = ppc.hi_lo(PIN)                 # (the ball's last place and velocity: fb_track, while idle)
    a(ppc.lis(12, hi), ppc.lfs(4, lo, 12), ppc.lfs(6, lo + 8, 12))
    a(ppc.fsubs(7, 4, 1), ppc.fsubs(8, 6, 3), ppc.fmuls(9, 7, 7), ppc.fmuls(10, 8, 8), ppc.fadds(9, 9, 10))
    a(ppc.lwz(0, S["kick_pick"], 31), ppc.cmpwi(0, 0))   # pass or kick: the shooter's pick (fb_tick, fb_choose)
    a.br("beq", "l_pass")
    # a field goal try: the posts' plane is square to the kick, through the pin
    a(ppc.li(0, KIND_KICK), ppc.stw(0, S["kind"], 31))
    a.bl(L["fb_norm"])
    a(ppc.stfs(7, S["nx"], 31), ppc.stfs(8, S["nz"], 31))
    a(ppc.fsubs(10, 1, 4), ppc.fsubs(11, 3, 6), ppc.fmuls(10, 10, 7), ppc.fmuls(11, 11, 8), ppc.fadds(10, 10, 11),
      ppc.stfs(10, S["prev_s"], 31))
    a.br("b", "l_out")
    # a pass: the receiver starts on the aim point, facing back toward the throw
    a.label("l_pass")
    a(ppc.li(0, KIND_PASS), ppc.stw(0, S["kind"], 31), ppc.li(0, 1), ppc.stw(0, S["cam_first"], 31))
    a(ppc.lfs(4, S_TARGET, 28), ppc.lfs(5, S_TARGET + 4, 28), ppc.lfs(6, S_TARGET + 8, 28))
    a(ppc.stfs(4, S["rx"], 31), ppc.stfs(5, S["ry"], 31), ppc.stfs(6, S["rz"], 31))
    a(ppc.fsubs(7, 1, 4), ppc.fsubs(8, 3, 6), ppc.fmuls(9, 7, 7), ppc.fmuls(10, 8, 8), ppc.fadds(9, 9, 10))
    a.bl(L["fb_norm"])
    a(ppc.stfs(7, S["fx"], 31), ppc.stfs(8, S["fz"], 31))
    a.label("l_out")
    _leave(a, 0x10)
    return a


def make_run(L):
    a = ppc.Asm(CAVES["run"][0])
    # The receiver: the partner's stick runs (camera-relative: up = toward the throw), A jumps, B dives.
    a.label("fb_run")
    _enter(a, 0x20)
    hi, lo = ppc.hi_lo(PLAYERS)
    a(ppc.lis(12, 0x804E), ppc.lbz(3, D17 & 0xFFFF, 12), ppc.lbz(4, D15 & 0xFFFF, 12), ppc.lbz(5, D16 & 0xFFFF, 12),
      ppc.add(3, 3, 4), ppc.cmpw(3, 5))
    a.br("blt", "r_partner")
    a(ppc.subf(3, 5, 3))
    a.label("r_partner")
    a(ppc.mulli(3, 3, PLAYER_SIZE), ppc.lis(4, hi), ppc.addi(4, 4, lo), ppc.add(3, 3, 4), ppc.lwz(6, P_PAD, 3))
    a(ppc.lhz(9, PAD_PRESSED, 6), ppc.stw(9, 0x18, 1))
    a(ppc.lis(0, 0x4330), ppc.stw(0, 0x08, 1), lfd(0, C["magic"], 31))
    for off, f in ((PAD_STICK_X, 7), (PAD_STICK_Y, 8)):    # s8 -> float, the usual 0x43300000 way
        a(ppc.lbz(7, off, 6), ppc.extsb(7, 7), xoris(7, 7, 0x8000), ppc.stw(7, 0x0C, 1), lfd(f, 0x08, 1),
          fsub(f, f, 0), ppc.frsp(f, f))
    a(ppc.lfs(0, C["stick"], 31), ppc.fmuls(7, 7, 0), ppc.fmuls(8, 8, 0))
    a(ppc.fmuls(9, 7, 7), ppc.fmuls(10, 8, 8), ppc.fadds(9, 9, 10), ppc.lfs(0, C["dead2"], 31), ppc.fcmpu(9, 0))
    a.br("bge", "r_live")
    a(ppc.lfs(7, C["zero"], 31), ppc.fmr(8, 7))
    a.br("b", "r_dir")
    a.label("r_live")
    a(ppc.lfs(0, C["one"], 31), ppc.fcmpu(9, 0))
    a.br("ble", "r_dir")
    a.bl(L["fb_norm"])
    a.label("r_dir")                        # wanted velocity (f6, f7) = (right x sx + forward x sy) x run
    a(ppc.fmr(1, 7), ppc.fmr(2, 8), ppc.lfs(4, S["fx"], 31), ppc.lfs(5, S["fz"], 31))
    a(ppc.fmuls(6, 4, 2), ppc.fmuls(7, 5, 1), ppc.fsubs(6, 6, 7))
    a(ppc.fmuls(7, 4, 1), ppc.fmuls(8, 5, 2), ppc.fadds(7, 7, 8))
    a(ppc.lfs(0, C["run"], 31), ppc.fmuls(6, 6, 0), ppc.fmuls(7, 7, 0))
    a.b(L["fb_run2"])
    return a


def make_run2(L):
    a = ppc.Asm(CAVES["run2"][0])
    # fb_run's second part (same frame): f6, f7 = the stick's velocity, 0x18(r1) = the partner's new presses
    a.label("fb_run2")
    a(ppc.lfs(8, S["dive_t"], 31), ppc.lfs(0, C["zero"], 31), ppc.fcmpu(8, 0))
    a.br("ble", "r_no_dive")
    a(ppc.lfs(0, C["one"], 31), ppc.fsubs(8, 8, 0), ppc.stfs(8, S["dive_t"], 31), ppc.lfs(0, C["down_frames"], 31),
      ppc.fcmpu(8, 0))
    a.br("blt", "r_down")
    a(ppc.lfs(0, C["dive_speed"], 31), ppc.lfs(6, S["dive_x"], 31), ppc.lfs(7, S["dive_z"], 31),
      ppc.fmuls(6, 6, 0), ppc.fmuls(7, 7, 0))
    a.b(L["fb_run_set"])
    a.label("r_down")
    a(ppc.lfs(6, C["zero"], 31), ppc.fmr(7, 6))
    a.b(L["fb_run_set"])
    a.label("r_no_dive")
    a(ppc.lwz(9, 0x18, 1), ppc.lfs(8, S["jump_t"], 31), ppc.lfs(0, C["zero"], 31), ppc.fcmpu(8, 0))
    a.br("bgt", "r_glide")                  # in the air: no new jump or dive
    a(ppc.andi_(0, 9, PAD_B))
    a.br("beq", "r_no_b")
    # dive along the stick, or at the ball with the stick let go
    a(ppc.fmr(1, 6), ppc.fmr(2, 7), ppc.fmuls(9, 6, 6), ppc.fmuls(10, 7, 7), ppc.fadds(9, 9, 10),
      ppc.lfs(0, C["tiny"], 31), ppc.fcmpu(9, 0))
    a.br("bgt", "r_dive_dir")
    a(ppc.lfs(1, B_POS, 29), ppc.lfs(0, S["rx"], 31), ppc.fsubs(1, 1, 0), ppc.lfs(2, B_POS + 8, 29),
      ppc.lfs(0, S["rz"], 31), ppc.fsubs(2, 2, 0), ppc.fmuls(9, 1, 1), ppc.fmuls(10, 2, 2), ppc.fadds(9, 9, 10))
    a.label("r_dive_dir")
    a(ppc.fmr(7, 1), ppc.fmr(8, 2))
    a.bl(L["fb_norm"])
    a(ppc.stfs(7, S["dive_x"], 31), ppc.stfs(8, S["dive_z"], 31), ppc.lfs(0, C["dive_total"], 31),
      ppc.stfs(0, S["dive_t"], 31), ppc.lfs(0, C["dive_speed"], 31), ppc.fmuls(6, 7, 0), ppc.fmuls(7, 8, 0))
    a.b(L["fb_run_set"])
    a.label("r_no_b")
    a(ppc.andi_(0, 9, PAD_A))
    a.br("beq", "r_glide")
    a(ppc.lfs(0, C["jump_frames"], 31), ppc.stfs(0, S["jump_t"], 31))
    a.label("r_glide")                      # ease toward the stick's velocity
    a(ppc.lfs(0, C["accel"], 31), ppc.lfs(8, S["rvx"], 31), ppc.fsubs(6, 6, 8), ppc.fmadds(6, 6, 0, 8),
      ppc.lfs(8, S["rvz"], 31), ppc.fsubs(7, 7, 8), ppc.fmadds(7, 7, 0, 8))
    a.b(L["fb_run_set"])
    return a


def make_run3(L):
    a = ppc.Asm(CAVES["run3"][0])
    # fb_run's last part: f6, f7 = the receiver's velocity this frame; the jump's height; the move, on the ground
    a.label("fb_run_set")
    a(ppc.stfs(6, S["rvx"], 31), ppc.stfs(7, S["rvz"], 31))
    a(ppc.lfs(8, S["jump_t"], 31), ppc.lfs(0, C["zero"], 31), ppc.fcmpu(8, 0))
    a.br("ble", "r_no_jump")
    a(ppc.lfs(0, C["one"], 31), ppc.fsubs(8, 8, 0), ppc.stfs(8, S["jump_t"], 31), ppc.lfs(9, C["inv_jump_frames"], 31),
      ppc.fmuls(8, 8, 9), ppc.fsubs(9, 0, 8), ppc.fmuls(8, 8, 9), ppc.lfs(0, C["jump_h4"], 31), ppc.fmuls(8, 8, 0))
    a.br("b", "r_height")                   # 4 h t (1 - t)
    a.label("r_no_jump")
    a(ppc.lfs(8, C["zero"], 31))
    a.label("r_height")
    a(ppc.stfs(8, S["jump_h"], 31))
    a(ppc.lfs(1, S["rx"], 31), ppc.fadds(1, 1, 6), ppc.stfs(1, S["rx"], 31), ppc.lfs(3, S["rz"], 31),
      ppc.fadds(3, 3, 7), ppc.stfs(3, S["rz"], 31), ppc.lfs(2, S["ry"], 31))
    a.bl(L["fb_ground"])
    a(ppc.stfs(1, S["ry"], 31))
    _leave(a, 0x20)
    return a


def make_catch(L):
    a = ppc.Asm(CAVES["catch"][0])
    # The ball in the receiver's zone: caught, held there.
    a.label("fb_catch")
    a(ppc.lfs(1, B_POS, 29), ppc.lfs(2, B_POS + 4, 29), ppc.lfs(3, B_POS + 8, 29))
    a(ppc.lfs(4, S["rx"], 31), ppc.lfs(5, S["ry"], 31), ppc.lfs(6, S["rz"], 31))
    a(ppc.fsubs(7, 1, 4), ppc.fsubs(8, 3, 6), ppc.fmuls(9, 7, 7), ppc.fmuls(8, 8, 8), ppc.fadds(9, 9, 8),
      ppc.fsubs(10, 2, 5))
    a(ppc.lfs(11, S["dive_t"], 31), ppc.lfs(0, C["down_frames"], 31), ppc.fcmpu(11, 0))
    a.br("blt", "c_not_diving")
    a(ppc.lfs(12, C["dive_r2"], 31), ppc.lfs(13, C["dive_reach"], 31))
    a.br("b", "c_test")
    a.label("c_not_diving")
    a(ppc.lfs(0, C["zero"], 31), ppc.fcmpu(11, 0), BGTLR)          # down after a dive: no catch
    a(ppc.lfs(12, C["catch_r2"], 31), ppc.lfs(13, C["reach"], 31), ppc.lfs(0, S["jump_h"], 31),
      ppc.fadds(13, 13, 0))
    a.label("c_test")
    a(ppc.fcmpu(9, 12), BGTLR, ppc.fcmpu(10, 13), BGTLR, ppc.lfs(0, C["low"], 31), ppc.fcmpu(10, 0), BLTLR)
    a(ppc.li(0, PH_HOLD), ppc.stw(0, S["phase"], 31), ppc.li(0, R_CAUGHT), ppc.stw(0, S["result"], 31))
    a(ppc.stfs(4, S["hx"], 31), ppc.lfs(0, C["lift"], 31), ppc.fadds(0, 5, 0), ppc.stfs(0, S["hy"], 31),
      ppc.stfs(6, S["hz"], 31), BLR)

    # The ball held where the play ended, until the shooter's state moves on.
    a.label("fb_hold")
    a(ppc.lfs(0, S["hx"], 31), ppc.stfs(0, B_POS, 29), ppc.lfs(0, S["hy"], 31), ppc.stfs(0, B_POS + 4, 29),
      ppc.lfs(0, S["hz"], 31), ppc.stfs(0, B_POS + 8, 29), ppc.li(0, 0), ppc.stw(0, B_VEL, 29),
      ppc.stw(0, B_VEL + 4, 29), ppc.stw(0, B_VEL + 8, 29), BLR)
    return a


def make_contact(L):
    a = ppc.Asm(CAVES["contact"][0])
    # The ball touched something (ground, a tree, the water): the play is over.
    a.label("fb_contact")
    a(ppc.lfs(1, B_VEL + 4, 29), ppc.lfs(2, S["pvy"], 31), ppc.lfs(0, C["contact_vy"], 31), ppc.fcmpu(2, 0))
    a.br("bge", "t_across")
    a(ppc.fsubs(3, 1, 2), ppc.lfs(0, C["contact_dvy"], 31), ppc.fcmpu(3, 0))
    a.br("bgt", "t_hit")
    a.label("t_across")
    a(ppc.lfs(4, B_VEL, 29), ppc.lfs(5, B_VEL + 8, 29), ppc.fmuls(4, 4, 4), ppc.fmuls(5, 5, 5), ppc.fadds(4, 4, 5),
      ppc.lfs(5, S["phs2"], 31), ppc.lfs(0, C["hs_min"], 31), ppc.fcmpu(5, 0), BLELR,
      ppc.lfs(0, C["hs_drop"], 31), ppc.fmuls(0, 5, 0), ppc.fcmpu(4, 0), BGELR)
    a.label("t_hit")
    _enter(a, 0x10)
    a(ppc.li(0, PH_DEAD), ppc.stw(0, S["phase"], 31), ppc.lwz(0, S["kind"], 31), ppc.cmpwi(0, KIND_PASS))
    a.br("bne", "t_kick")
    a(ppc.li(0, R_INCOMPLETE), ppc.stw(0, S["result"], 31))
    a.br("b", "t_place")
    a.label("t_kick")
    a(ppc.lwz(0, S["judged"], 31), ppc.cmpwi(0, 0))
    a.br("bne", "t_place")
    a(ppc.li(0, R_NO_GOOD), ppc.stw(0, S["result"], 31))
    a.label("t_place")                      # held on the ground under where it touched
    a(ppc.lfs(1, B_POS, 29), ppc.lfs(2, B_POS + 4, 29), ppc.lfs(3, B_POS + 8, 29), ppc.stfs(1, S["hx"], 31),
      ppc.stfs(3, S["hz"], 31))
    a.bl(L["fb_ground"])
    a(ppc.lfs(0, C["lift"], 31), ppc.fadds(1, 1, 0), ppc.stfs(1, S["hy"], 31))
    _leave(a, 0x10)
    return a


def make_kick(L):
    a = ppc.Asm(CAVES["kick"][0])
    # A field goal try: crossing the posts' plane (s = (ball - pin) . n from - to +) between the uprights, over
    # the crossbar, is good; the first crossing decides.
    a.label("fb_kick")
    a(ppc.lwz(0, S["judged"], 31), ppc.cmpwi(0, 0), BNELR)
    hi, lo = ppc.hi_lo(PIN)
    a(ppc.lis(12, hi), ppc.lfs(4, lo, 12), ppc.lfs(5, lo + 4, 12), ppc.lfs(6, lo + 8, 12))
    a(ppc.lfs(1, B_POS, 29), ppc.lfs(2, B_POS + 4, 29), ppc.lfs(3, B_POS + 8, 29))
    a(ppc.lfs(7, S["nx"], 31), ppc.lfs(8, S["nz"], 31))
    a(ppc.fsubs(9, 1, 4), ppc.fmuls(9, 9, 7), ppc.fsubs(10, 3, 6), ppc.fmuls(10, 10, 8), ppc.fadds(9, 9, 10))
    a(ppc.lfs(10, S["prev_s"], 31), ppc.stfs(9, S["prev_s"], 31), ppc.lfs(0, C["zero"], 31), ppc.fcmpu(9, 0),
      BLTLR, ppc.fcmpu(10, 0), BGELR)
    # where it crossed: prev + (ball - prev) x prev_s / (prev_s - s)
    a(ppc.fsubs(11, 10, 9), ppc.fdivs(11, 10, 11))
    a(ppc.lfs(12, S["pbx"], 31), ppc.fsubs(13, 1, 12), ppc.fmadds(1, 13, 11, 12))
    a(ppc.lfs(12, S["pby"], 31), ppc.fsubs(13, 2, 12), ppc.fmadds(2, 13, 11, 12))
    a(ppc.lfs(12, S["pbz"], 31), ppc.fsubs(13, 3, 12), ppc.fmadds(3, 13, 11, 12))
    # across: (c - pin) . (-nz, nx); up: c.y - pin.y
    a(ppc.fsubs(1, 1, 4), ppc.fsubs(3, 3, 6), ppc.fmuls(3, 3, 7), ppc.fmuls(1, 1, 8), ppc.fsubs(1, 3, 1),
      fabs(1, 1), ppc.fsubs(2, 2, 5))
    a(ppc.li(0, 1), ppc.stw(0, S["judged"], 31), ppc.li(0, R_NO_GOOD), ppc.stw(0, S["result"], 31))
    a(ppc.lfs(0, C["half_width"], 31), ppc.fcmpu(1, 0), BGTLR, ppc.lfs(0, C["crossbar"], 31), ppc.fcmpu(2, 0),
      BLTLR, ppc.li(0, R_GOOD), ppc.stw(0, S["result"], 31), BLR)
    return a


def make_track(L):
    a = ppc.Asm(CAVES["track"][0])
    # Every update of a play: the ball's velocity and place for the next one's tests; on a pass, the star on the
    # receiver and the camera on the receiver.
    a.label("fb_track")
    a(ppc.lfs(1, B_VEL, 29), ppc.lfs(2, B_VEL + 4, 29), ppc.lfs(3, B_VEL + 8, 29), ppc.stfs(2, S["pvy"], 31),
      ppc.fmuls(1, 1, 1), ppc.fmuls(3, 3, 3), ppc.fadds(1, 1, 3), ppc.stfs(1, S["phs2"], 31))
    a(ppc.lfs(1, B_POS, 29), ppc.lfs(2, B_POS + 4, 29), ppc.lfs(3, B_POS + 8, 29), ppc.stfs(1, S["pbx"], 31),
      ppc.stfs(2, S["pby"], 31), ppc.stfs(3, S["pbz"], 31))
    a(ppc.lwz(0, S["kind"], 31), ppc.cmpwi(0, KIND_PASS), BNELR)
    _enter(a, 0x10)
    import fbpose   # (it imports this module) v28: the landing star run on ahead and the camera's focus (rx, ry, rz:
    a.bl(fbpose.build()[1]["fp_track_pass"])   # the receivers' middle), in the golf overlay's tail
    a(ppc.lwz(0, 0x14, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x10))
    a(ppc.lfs(1, B_POS, 29), ppc.lfs(2, B_POS + 4, 29), ppc.lfs(3, B_POS + 8, 29))
    a(ppc.lfs(4, S["rx"], 31), ppc.lfs(5, S["ry"], 31), ppc.lfs(6, S["rz"], 31))
    a.b(L["fb_cam"])
    return a


def make_cam(L):
    a = ppc.Asm(CAVES["cam"][0])
    # (f1-f3 = the ball, f4-f6 = the receiver) the camera behind the receiver (away from the ball's start) and up,
    # looking between the receiver and the ball as seen from there, so both stay on screen, the receiver nearer the
    # middle: the look-at point is the receiver + (ball - receiver) x k, k = |eye - receiver| / (|eye - receiver| +
    # w |eye - ball|) (w = 1: the bisector)
    a.label("fb_cam")
    a(ppc.lfs(7, S["fx"], 31), ppc.lfs(8, S["fz"], 31), ppc.lfs(0, C["cam_back"], 31))
    a(ppc.fmuls(9, 7, 0), ppc.fsubs(9, 4, 9), ppc.lfs(10, C["cam_up"], 31), ppc.fadds(10, 5, 10),
      ppc.fmuls(11, 8, 0), ppc.fsubs(11, 6, 11))
    a(ppc.fsubs(12, 1, 9), ppc.fmuls(12, 12, 12), ppc.fsubs(13, 2, 10), ppc.fmadds(12, 13, 13, 12),
      ppc.fsubs(13, 3, 11), ppc.fmadds(12, 13, 13, 12))          # |eye - ball|^2
    a(ppc.frsqrte(13, 12), ppc.lfs(7, C["half"], 31), ppc.lfs(8, C["threehalf"], 31))
    for _ in range(2):
        a(ppc.fmuls(0, 13, 13), ppc.fmuls(0, 0, 12), ppc.fmuls(0, 0, 7), ppc.fsubs(0, 8, 0), ppc.fmuls(13, 13, 0))
    a(ppc.fmuls(12, 12, 13), ppc.lfs(7, C["cam_ball_w"], 31), ppc.fmuls(12, 12, 7), ppc.lfs(7, C["cam_dist"], 31),
      ppc.fadds(8, 7, 12), ppc.fdivs(7, 7, 8))
    a(ppc.fsubs(1, 1, 4), ppc.fmadds(1, 1, 7, 4), ppc.fsubs(2, 2, 5), ppc.fmadds(2, 2, 7, 5),
      ppc.lfs(12, C["cam_look_up"], 31), ppc.fadds(2, 2, 12), ppc.fsubs(3, 3, 6), ppc.fmadds(3, 3, 7, 6))
    a.b(L["fb_cam_clear"])
    return a


def make_cam3(L):
    a = ppc.Asm(CAVES["cam3"][0])
    # fb_cam's eye kept over the ground (a hill behind the receiver): the ground under the eye, asked from high over
    # the receiver; the eye at least cam_clear over it. f9-f11 = the eye, f1-f3 = the look-at point, f5 = receiver y.
    a.label("fb_cam_clear")
    _enter(a, 0x30)
    for k, f in enumerate((1, 2, 3, 9, 10, 11)):
        a(ppc.stfs(f, 0x08 + 4 * k, 1))
    a(ppc.fmr(1, 9), ppc.lfs(0, C["cam_probe"], 31), ppc.fadds(2, 5, 0), ppc.stfs(2, 0x20, 1), ppc.fmr(3, 11))
    a.bl(L["fb_ground"])
    a(ppc.lfs(2, 0x20, 1), ppc.lfs(0, C["one"], 31), ppc.fsubs(2, 2, 0), ppc.fcmpu(1, 2))
    a.br("bge", "cc_keep")                  # nothing under it
    a(ppc.lfs(0, C["cam_clear"], 31), ppc.fadds(1, 1, 0), ppc.lfs(0, 0x18, 1), ppc.fcmpu(0, 1))
    a.br("bge", "cc_keep")
    a(ppc.stfs(1, 0x18, 1))
    a.label("cc_keep")
    for k, f in enumerate((1, 2, 3, 9, 10, 11)):
        a(ppc.lfs(f, 0x08 + 4 * k, 1))
    a(ppc.lwz(0, 0x34, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x30))
    a.b(L["fb_cam2"])
    return a


def make_cam2(L):
    a = ppc.Asm(CAVES["cam2"][0])
    # fb_cam's end: f9-f11 = the eye, f1-f3 = the look-at point, glided to (cut to on the play's first update)
    a.label("fb_cam2")
    a(ppc.lfs(12, C["cam_glide"], 31), ppc.lwz(0, S["cam_first"], 31), ppc.cmpwi(0, 0))
    a.br("beq", "k_glide")
    a(ppc.lfs(12, C["one"], 31), ppc.li(0, 0), ppc.stw(0, S["cam_first"], 31))
    a.label("k_glide")
    a(ppc.lis(12, CAMERA >> 16), ppc.lwz(12, CAMERA & 0xFFFF, 12), ppc.lfs(0, C["cam_fov"], 31),
      ppc.stfs(0, 0x2C, 12))                # a wider view than the shot camera's
    a(ppc.lfs(0, C["cam_floor"], 31), ppc.lfs(13, S["ry"], 31), ppc.fadds(0, 13, 0), ppc.fcmpu(2, 0))   # the
    # look-at point no lower than the receiver's ground + cam_floor
    a.br("bge", "k_floor")
    a(ppc.fmr(2, 0))
    a.label("k_floor")
    for k, (f, name) in enumerate(((9, "ex"), (10, "ey"), (11, "ez"), (1, "lx"), (2, "ly"), (3, "lz"))):
        a(ppc.lfs(13, S[name], 31), ppc.fsubs(f, f, 13), ppc.fmadds(f, f, 12, 13), ppc.stfs(f, S[name], 31),
          ppc.stfs(f, 4 * k, 12))
    a(BLR)
    return a


def make_shot(L):
    a = ppc.Asm(CAVES["shot"][0])
    # b from teams.py's shot hook (SHOT_HOOK, football on): r30 = the player; the play's result decides.
    a.label("fb_shot")
    hi, lo = ppc.hi_lo(CAVES["state"][0] + S["result"])
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.li(11, R_NONE), ppc.stw(11, lo, 12))
    a(ppc.cmpwi(0, R_CAUGHT))
    a.br("beq", "s_caught")
    a(ppc.cmpwi(0, R_GOOD))
    a.br("beq", "s_good")
    a(ppc.cmpwi(0, R_NONE))
    a.br("beq", "s_game")
    a.label("s_back")                       # incomplete, no good: the team's lie stays, no penalty
    a(ppc.lwz(9, P_REC, 30), ppc.li(0, 0), ppc.stb(0, REC_PENALTY_KIND, 9))
    a.b(SHOT_DONE)
    a.label("s_caught")                     # caught out of bounds or in a hazard: incomplete
    a(ppc.stwu(1, -0x10, 1), ppc.mflr(0), ppc.stw(0, 0x14, 1), ppc.lwz(3, P_BALL, 30))
    a.bl(OB_TEST)
    a(ppc.cmpwi(3, 0))
    a.br("bne", "s_caught_out")
    a(ppc.lwz(3, P_BALL, 30))
    a.bl(HAZARD_TEST)
    a(ppc.cmpwi(3, 0))
    a.br("bne", "s_caught_out")
    a(ppc.lwz(0, 0x14, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x10))
    a.label("s_game")                       # the game's block: the new lie where the ball is
    a(SHOT_HOOK[1])
    a.b(SHOT_HOOK[0] + 4)
    a.label("s_caught_out")
    a(ppc.lwz(0, 0x14, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x10))
    a.br("b", "s_back")
    a.label("s_good")                       # it's good: the team's lie in the hole, at the pin
    hi, lo = ppc.hi_lo(PIN)
    a(ppc.lwz(9, P_REC, 30), ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.addi(10, 9, REC_LIE))
    for k in range(3):
        a(ppc.lwz(0, 4 * k, 12), ppc.stw(0, 4 * k, 10))
    a(ppc.li(0, 1), ppc.stb(0, LIE_IN_HOLE, 10), ppc.li(0, 0), ppc.stb(0, REC_PENALTY_KIND, 9))
    a.b(SHOT_DONE)
    return a


def make_small(L):
    a = ppc.Asm(CAVES["small"][0])
    hi, lo = ppc.hi_lo(CAVES["state"][0])

    def live_pass():                        # returns (to the hook's caller) unless a pass is live: football, a pass,
        a(ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.lwz(11, S["on"], 12), ppc.cmpwi(11, 0), BEQLR,   # not dead
          ppc.lwz(11, S["kind"], 12), ppc.cmpwi(11, KIND_PASS), BNELR,
          ppc.lwz(11, S["phase"], 12), ppc.cmpwi(11, PH_DEAD), BEQLR)

    a.label("star_stage")                   # bl from STAR_STAGE: the meter's stage, 0 while a pass is live
    a(STAR_STAGE[1])
    live_pass()
    a(ppc.li(0, 0), BLR)
    a.label("star_state")                   # bl from STAR_STATE: the shooter's state, "aiming" while a pass is live
    a(STAR_STATE[1])
    live_pass()
    a(ppc.li(0, 4), BLR)
    for name, (site, word) in (("green_lie", GREEN_LIE), ("green_ball", GREEN_BALL)):
        a.label(name)                       # b from the "on the green" tests: never, in football
        a(ppc.lis(12, hi), ppc.lwz(0, lo + S["on"], 12), ppc.cmpwi(0, 0))
        a.br("beq", name + "_game")
        a(ppc.li(3, 0), BLR)
        a.label(name + "_game")
        a(word)
        a.b(site + 4)
    return a


# ---- the goalposts, drawn where the flag would be (the flag's drawer FUN_8044bf34, its `bl MODEL_DRAW`): flat-shaded
# yellow boxes in the pin's frame, turned to face the team's ball (x across, y up, z toward the kicker's far side)
POSTS_HOOK = 0x8044C0B4                 # bl MODEL_DRAW (0x800072C8): the flag's model
MODEL_DRAW = 0x800072C8
LOAD_MODELVIEW = 0x8001E980             # (view, model, slot): view x model into position (and normal) matrix slot
GX = {"mat_color": 0x8006AF08, "amb_color": 0x8006AE4C, "num_chans": 0x8006AFC4, "chan_ctrl": 0x8006AFE8,
      "num_texgens": 0x80068A38, "num_stages": 0x8006DD18, "tev_order": 0x8006DBA0, "tev_color": 0x8006DD40,
      "tev_alpha": 0x8006DD74, "blend": 0x8006E154, "alpha_cmp": 0x8006DAF0, "vtx_fmt": 0x8006803C,
      "clear_desc": 0x80068014, "descv": 0x80067AA8, "zmode": 0x8006E23C, "begin": 0x8006967C, "cull": 0x8006982C}
POS_ONLY_DESC = 0x804DE3E4              # golf: {GX_VA_POS, GX_DIRECT}, {GX_VA_NULL}: the slope grid's
P_LIE = 0x18                            # player: its (team's) lie
# Giant posts (Andrew: "it needs to be a giant field goal that can be kicked through"): about 3 times an NFL goal's
# 18 ft 6 in between the uprights and 10 ft crossbar, so they stand out over the green from anywhere in range
HALF_GAP, UPRIGHT, CROSSBAR_Y, TOP_Y = 30.0, 2.0, 30.0, 130.0      # feet
POST_BOXES = ((-1.2, 1.2, 0.0, CROSSBAR_Y, -1.2, 1.2),                                          # the stand
              (-HALF_GAP - UPRIGHT, HALF_GAP + UPRIGHT, CROSSBAR_Y - 2.0, CROSSBAR_Y, -1.0, 1.0),    # the crossbar
              (-HALF_GAP - UPRIGHT, -HALF_GAP, CROSSBAR_Y, TOP_Y, -1.0, 1.0),                    # the uprights
              (HALF_GAP, HALF_GAP + UPRIGHT, CROSSBAR_Y, TOP_Y, -1.0, 1.0))
POST_COLORS = (0xFFD81CFF, 0xB89410FF)  # faces toward / away from the kicker; the sides and tops (RGBA)
# each face's 4 corners as (x, y, z) picks of the box's (x0, x1, y0, y1, z0, z1): 0 = low, 1 = high
FACES_BRIGHT = (((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)), ((0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1)))
FACES_DARK = (((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)), ((1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)),
              ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)))


def lfsx(frt, ra, rb): return 0x7C00042E | frt << 21 | ra << 16 | rb << 11


def make_pdata(L):
    a = ppc.Asm(CAVES["pdata"][0])
    a.label("post_boxes")
    for box in POST_BOXES:
        for v in box:
            a(struct.unpack(">I", struct.pack(">f", v))[0])
    for name, faces in (("post_bright", FACES_BRIGHT), ("post_dark", FACES_DARK)):
        offs = bytes(o for face in faces for x, y, z in face for o in (4 * x, 8 + 4 * y, 16 + 4 * z))
        offs += bytes(-len(offs) % 4)
        a.label(name)
        a(*struct.unpack(f">{len(offs) // 4}I", offs))
    a.label("post_colors")
    a(*POST_COLORS)
    return a


def make_posts(L):
    a = ppc.Asm(CAVES["posts"][0])
    # bl from POSTS_HOOK (r3 = the flag's model, r4 its matrix): the game's flag, or in football the posts
    a.label("fb_posts")
    hi, lo = ppc.hi_lo(ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0))
    a.br("bne", "p_go")
    a.b(MODEL_DRAW)
    a.label("p_go")
    a(ppc.stwu(1, -0x60, 1), ppc.mflr(0), ppc.stw(0, 0x64, 1), ppc.stw(31, 0x5C, 1))
    _base(a)
    # which way: from the shooter's lie to the pin (else the last way)
    a(ppc.lis(12, 0x804E), ppc.lbz(0, D17 & 0xFFFF, 12), ppc.andi_(11, 0, 0x80))
    a.br("bne", "p_dir")
    hi, lo = ppc.hi_lo(PLAYERS)
    a(ppc.mulli(0, 0, PLAYER_SIZE), ppc.lis(3, hi), ppc.addi(3, 3, lo), ppc.add(3, 3, 0), ppc.lwz(3, P_LIE, 3),
      ppc.lfs(1, 0, 3), ppc.lfs(3, 8, 3))
    hi, lo = ppc.hi_lo(PIN)
    a(ppc.lis(12, hi), ppc.lfs(4, lo, 12), ppc.lfs(6, lo + 8, 12), ppc.fsubs(7, 4, 1), ppc.fsubs(8, 6, 3),
      ppc.fmuls(9, 7, 7), ppc.fmadds(9, 8, 8, 9))
    a.bl(L["fb_norm"])
    a(ppc.stfs(7, S["pnx"], 31), ppc.stfs(8, S["pnz"], 31))
    a.label("p_dir")
    import fbpose   # (it imports this module)
    a.bl(fbpose.build()[1]["fp_posts_hide"])            # (v28: not while a pass's camera is past them)
    a(ppc.cmpwi(3, 0))
    a.br("beq", "p_draw")
    a(ppc.lwz(31, 0x5C, 1), ppc.lwz(0, 0x64, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x60), BLR)
    a.label("p_draw")
    a.b(L["fb_posts_m"])
    return a


def make_posts_m(L):
    a = ppc.Asm(CAVES["posts_m"][0])
    # fb_posts' frame: the posts' frame at 0x08(r1), rows (t.x 0 n.x px) (0 1 0 py) (t.z 0 n.z pz), t = (n.z, -n.x)
    # (x across), loaded with the camera's view; then the GX state and the faces
    a.label("fb_posts_m")
    hi, lo = ppc.hi_lo(PIN)
    a(ppc.lfs(7, S["pnx"], 31), ppc.lfs(8, S["pnz"], 31), ppc.lfs(0, C["zero"], 31), ppc.lfs(1, C["one"], 31),
      ppc.lis(12, hi), ppc.lfs(4, lo, 12), ppc.lfs(5, lo + 4, 12), ppc.lfs(6, lo + 8, 12), ppc.fneg(2, 7))
    for k, f in enumerate((8, 0, 7, 4, 0, 1, 0, 5, 2, 0, 8, 6)):
        a(ppc.stfs(f, 0x08 + 4 * k, 1))
    a(ppc.lis(3, CAMERA >> 16), ppc.lwz(3, CAMERA & 0xFFFF, 3), ppc.addi(3, 3, 0x3C), ppc.addi(4, 1, 0x08),
      ppc.li(5, 0))
    a.bl(LOAD_MODELVIEW)
    a.bl(L["fb_posts2"])
    a(ppc.lwz(31, 0x5C, 1), ppc.lwz(0, 0x64, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x60), BLR)
    return a


def _gx_calls(a, calls):
    for fn, args in calls:
        for k, v in enumerate(args):
            if v > 0x7FFF:
                hi, lo = ppc.hi_lo(v)
                a(ppc.lis(3 + k, hi), ppc.addi(3 + k, 3 + k, lo))
            else:
                a(ppc.li(3 + k, v))
        a.bl(GX[fn])


# The GX state: the slope grid drawer FUN_80447d48's (one colour channel from the material register, no texture,
# position-only vertices), opaque, depth-tested, both sides
GX_STATE = (("num_chans", (1,)), ("chan_ctrl", (0, 0, 0, 0, 0, 2, 2)), ("chan_ctrl", (2, 0, 0, 0, 0, 0, 2)),
            ("num_texgens", (0,)), ("num_stages", (1,)), ("tev_order", (0, 0xFF, 0xFF, 4)),
            ("tev_color", (0, 0x8FFFA)), ("tev_alpha", (0, 0x8FFE0)), ("blend", (0, 1, 0, 0xF)),
            ("alpha_cmp", (7, 0, 1, 7, 0)), ("vtx_fmt", (0, 9, 1, 4, 0)), ("clear_desc", ()),
            ("descv", (POS_ONLY_DESC,)), ("zmode", (1, 3, 1)), ("cull", (0,)))


def _chain(a, name, body, then):
    """A link of a chain of caves: own frame (the caller's LR kept in it), the body, then on to the next."""
    a.label(name)
    a(ppc.stwu(1, -0x20, 1), ppc.mflr(0), ppc.stw(0, 0x24, 1))
    body()
    a(ppc.lwz(0, 0x24, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x20))
    if then:
        a.b(then)
    else:
        a(BLR)


def make_posts2(L):
    a = ppc.Asm(CAVES["posts2"][0])
    _chain(a, "fb_posts2", lambda: _gx_calls(a, GX_STATE[:8]), L["fb_posts2b"])
    return a


def make_posts2b(L):
    a = ppc.Asm(CAVES["posts2b"][0])
    _chain(a, "fb_posts2b", lambda: _gx_calls(a, GX_STATE[8:]), L["fb_posts3"])
    return a


def _faces(a, L, k, name, faces):
    """One shade's faces: colour k, then every box's faces of the list `name` as quads."""
    hi, lo = ppc.hi_lo(L["post_colors"] + 4 * k)
    a(ppc.lis(4, hi), ppc.addi(4, 4, lo), ppc.li(3, 4))
    a.bl(GX["mat_color"])
    a(ppc.li(3, 0x80), ppc.li(4, 0), ppc.li(5, 4 * len(faces) * len(POST_BOXES)))
    a.bl(GX["begin"])
    hi, lo = ppc.hi_lo(L["post_boxes"])
    a(ppc.lis(6, hi), ppc.addi(6, 6, lo), ppc.li(7, len(POST_BOXES)), ppc.lis(9, 0xCC01))
    a.label(f"p_box{k}")
    hi, lo = ppc.hi_lo(L[name])
    a(ppc.lis(8, hi), ppc.addi(8, 8, lo), ppc.li(10, 4 * len(faces)))
    a.label(f"p_vert{k}")
    for f, d in ((1, 0), (2, 1), (3, 2)):
        a(ppc.lbz(5, d, 8), lfsx(f, 6, 5))
    a(ppc.stfs(1, -0x8000, 9), ppc.stfs(2, -0x8000, 9), ppc.stfs(3, -0x8000, 9), ppc.addi(8, 8, 3),
      ppc.addi(10, 10, -1), ppc.cmpwi(10, 0))
    a.br("bne", f"p_vert{k}")
    a(ppc.addi(6, 6, 24), ppc.addi(7, 7, -1), ppc.cmpwi(7, 0))
    a.br("bne", f"p_box{k}")


def make_posts3(L):
    a = ppc.Asm(CAVES["posts3"][0])
    # the faces toward and away from the kicker, bright (the FIFO: 0xCC008000 = 0xCC010000 - 0x8000)
    _chain(a, "fb_posts3", lambda: _faces(a, L, 0, "post_bright", FACES_BRIGHT), L["fb_posts4"])
    return a


def make_posts4(L):
    a = ppc.Asm(CAVES["posts4"][0])
    # the sides and tops, darker
    _chain(a, "fb_posts4", lambda: _faces(a, L, 1, "post_dark", FACES_DARK), None)
    return a


# ---- what happened, in a text box (the game's message boxes: FUN_80024f1c(message, x, y, -1, 15) opens one and
# returns it, FUN_80024c98(box) closes it; the hole's opening tip uses them): the play's result as soon as it is
# decided, "Field goal try!" when a turn starts in kick range; closed after SAY_FRAMES or when the turn moves on
BOX_OPEN, BOX_CLOSE = 0x80024F1C, 0x80024C98
MSG_SAY = 0x7FC0                        # + the result (1-4); + 5.. the shot types; 0x7FC0 itself is the field goal's
SAY_TEXTS = (None, b"\x075Caught!\x00", b"\x075Incomplete!\x00", b"\x075It's good!\x00", b"\x075No good!\x00",
             None, None, None)          # None: a shot type's text (in the golf overlay's tail, fbpose.py)
SAY_X, SAY_Y, SAY_FRAMES = 320, 150, 100
TIP_X, TIP_Y = 520, 130        # a shot type's tip: its box's middle, up on the right (the menus' 640 x 448 space)

# ---- the shot types, in LB/RB's order: (name, the golfer's club it is, x its launch angle, x its backspin, the box's
# text). The club makes its reach (the golfer's drive x the club's share), its timing window (the golfer's impact, the
# club and the lie) and its flight (the golfer's height and spin); the factors flatten or lift it (the speed is then
# found for the same carry, so a flat throw is a fast one; backspin is lift: an iron's at a low angle still balloons).
# Clubs: 0 driver 100%, 2 86%, 4 74%, 11 38% of the drive.
SHOT_TYPES = (
    ("Bomb", 0, 1.0, 1.0, b"\x073Bomb\x01\x071Far, high, windy\x00"),     # (the tips: small, two short lines)
    ("Bullet", 4, 0.35, 0.1, b"\x073Bullet\x01\x071Low, fast, steady\x00"),
    ("Lob", 11, 1.15, 1.0, b"\x073Lob\x01\x071Short and floaty\x00"),
    ("Field goal", 2, 1.1, 1.0, b"\x073Field goal\x01\x071Kick it through!\x00"),
)
TYPE_FG = 3                             # the field goal try
TYPE_MSG = (MSG_SAY + 5, MSG_SAY + 6, MSG_SAY + 7, MSG_SAY)   # each type's message (SAY_TEXTS' None entries)
# the ball's draw scale (FUN_8041d04c: ball matrix = position x spin x this; FUN_8041dcb8 makes it 0.14 once, the
# ball's 1.68 inches): football-sized (BALL_BIG ft) while a play is in the air, so it can be followed
BALL_MATRIX, BALL_NORMAL, BALL_BIG = 0x805025E8, 0.14, 0.0   # in the air: none (fbpose.py draws a football there)


def make_say(L):
    a = ppc.Asm(CAVES["say"][0])
    # (r3 = message) the box with that message, instead of any open one
    a.label("fb_say_side")                  # (r3 = message) a shot type's tip, up on the right (Andrew: "too big and
    _enter(a, 0x20)                         # in the middle make it smaller and to the side")
    a(ppc.stw(3, 0x08, 1), ppc.li(0, TIP_X), ppc.stw(0, 0x0C, 1), ppc.li(0, TIP_Y))
    a.br("b", "say_at")
    a.label("fb_say")
    _enter(a, 0x20)
    a(ppc.stw(3, 0x08, 1), ppc.li(0, SAY_X), ppc.stw(0, 0x0C, 1), ppc.li(0, SAY_Y))
    a.label("say_at")
    a(ppc.stw(0, 0x10, 1))
    a.bl(L["fb_unsay"])
    a(ppc.lwz(3, 0x08, 1), ppc.lwz(4, 0x0C, 1), ppc.lwz(5, 0x10, 1), ppc.li(6, -1), ppc.li(7, 15))
    a.bl(BOX_OPEN)
    a(ppc.stw(3, S["box"], 31), ppc.li(0, SAY_FRAMES), ppc.stw(0, S["box_t"], 31))
    _leave(a, 0x20)
    # the open box closed
    a.label("fb_unsay")
    a(ppc.lwz(3, S["box"], 31), ppc.cmpwi(3, 0), BEQLR)
    _enter(a, 0x10)
    a(ppc.li(0, 0), ppc.stw(0, S["box"], 31), ppc.stw(0, S["box_t"], 31))
    a.bl(BOX_CLOSE)
    _leave(a, 0x10)
    # (each update of a play) a new result said
    a.label("fb_said")
    a(ppc.lwz(3, S["result"], 31), ppc.cmpwi(3, 0), BEQLR, ppc.lwz(4, S["said"], 31), ppc.cmpw(3, 4), BEQLR,
      ppc.stw(3, S["said"], 31), ppc.addi(3, 3, MSG_SAY))
    a.b(L["fb_say"])
    return a


def make_tick(L):
    a = ppc.Asm(CAVES["tick"][0])
    # (r3 = the shooter's state, r4 = its state the update before) the box's upkeep: a new state closes it (but the
    # ball stopping, 7 -> 8); a new aim (4) has its shot type named again (fb_choose); else the box counts down
    a.label("fb_tick")
    _enter(a, 0x20)
    a(ppc.lfs(0, C["ball_normal"], 31), ppc.cmpwi(3, STATE_MOVING))   # the ball drawn football-sized in the air
    a.br("bne", "t2_ball")
    a(ppc.lfs(0, C["ball_big"], 31))
    a.label("t2_ball")
    hi, lo = ppc.hi_lo(BALL_MATRIX)
    a(ppc.lis(11, hi), ppc.addi(11, 11, lo), ppc.stfs(0, 0, 11), ppc.stfs(0, 0x14, 11), ppc.stfs(0, 0x28, 11))
    a(ppc.stw(3, 0x08, 1), ppc.cmpw(3, 4))
    a.br("beq", "t2_count")
    a(ppc.cmpwi(4, STATE_MOVING))
    a.br("bne", "t2_close")
    a(ppc.cmpwi(3, STATE_MOVING + 1))
    a.br("beq", "t2_count")
    a.label("t2_close")
    a.bl(L["fb_unsay"])
    a(ppc.lwz(0, 0x08, 1), ppc.cmpwi(0, 4))
    a.br("bne", "t2_out")
    a(ppc.li(0, -1), ppc.stw(0, S["type"], 31))          # a new aim: fb_choose names its shot type
    a.br("b", "t2_out")
    a.label("t2_count")
    a(ppc.lwz(0, S["box_t"], 31), ppc.cmpwi(0, 0))
    a.br("ble", "t2_out")
    a(ppc.addi(0, 0, -1), ppc.stw(0, S["box_t"], 31), ppc.cmpwi(0, 0))
    a.br("bne", "t2_out")
    a.bl(L["fb_unsay"])
    a.label("t2_out")
    _leave(a, 0x20)
    return a


MSG_LOOKUP, MSG_LOOKUP_FIRST = 0x80022CD0, 0x7C60C670     # main.dol: message id -> string; srawi r0,r3,24


def make_choose(L):
    a = ppc.Asm(CAVES["choose"][0])
    # (r3 = the shooter's state, r28 = its setup) while aiming, the club is the shot type (fbpose.py keeps it one of
    # SHOT_TYPES' clubs): the field goal's is a kick, the rest passes; a new type is named in the box
    a.label("fb_choose")
    a(ppc.cmpwi(3, 4), BNELR, ppc.lwz(4, S_CLUB, 28))
    for k, (_name, club, _angle, _spin, _text) in enumerate(SHOT_TYPES):
        a(ppc.li(5, k), ppc.cmpwi(4, club))
        a.br("beq", "ch_type")
    a(BLR)                                  # not one yet (fbpose.py's fp_snap makes it one)
    a.label("ch_type")
    a(ppc.li(0, 0), ppc.cmpwi(5, TYPE_FG))
    a.br("bne", "ch_kick")
    a(ppc.li(0, 1))
    a.label("ch_kick")
    a(ppc.stw(0, S["kick_pick"], 31), ppc.lwz(0, S["type"], 31), ppc.cmpw(0, 5), BEQLR, ppc.stw(5, S["type"], 31),
      ppc.addi(3, 5, TYPE_MSG[0]), ppc.cmpwi(5, TYPE_FG))
    a.br("bne", "ch_say")
    a(ppc.li(3, TYPE_MSG[TYPE_FG]))
    a.label("ch_say")
    a.b(L["fb_say_side"])
    return a


def make_texts(L):
    a = ppc.Asm(CAVES["texts"][0])
    # b from teams.py's message hook (after build_mod.py's): our messages, else the game's lookup
    a.label("fb_messages")
    a(ppc.cmpwi(3, MSG_HELP))
    a.br("beq", "m_help")
    a(ppc.cmpwi(3, MSG_HELP2))
    a.br("beq", "m_help2")
    a(ppc.addi(12, 3, -MSG_SAY), ppc.cmplwi(12, len(SAY_TEXTS) - 1))
    a.br("bgt", "m_game")
    a(ppc.slwi(12, 12, 2))
    a.la(11, "say_table")
    a(ppc.lwzx(3, 11, 12), BLR)
    a.label("m_help")
    hi, lo = ppc.hi_lo(CAVES["consts"][0] + C["help"] - C0)
    a(ppc.lis(3, hi), ppc.addi(3, 3, lo), BLR)
    a.label("m_help2")
    a.la(3, "help2")
    a(BLR)
    a.label("m_game")
    a(MSG_LOOKUP_FIRST)
    a.b(MSG_LOOKUP + 4)
    a.label("help2")                        # v28 Pigskin 2v2's help line
    a(*struct.unpack(f">{-(-len(HELP2_TEXT) // 4)}I", HELP2_TEXT + bytes(-len(HELP2_TEXT) % 4)))
    a.label("say_table")
    a(*([0] * len(SAY_TEXTS)))
    for k, text in enumerate(SAY_TEXTS):
        if text is not None:
            a.label(f"say_{k}")
            a(*struct.unpack(f">{-(-len(text) // 4)}I", text + bytes(-len(text) % 4)))
    import fbpose   # (it imports this module) the shot types' texts live in the golf overlay's tail: they are only
    tail = fbpose.build()[1]                            # asked for in a round
    for t, msg in enumerate(TYPE_MSG):
        a.labels[f"say_{msg - MSG_SAY}"] = tail[f"type_text_{t}"]
    table = a.labels["say_table"]
    for k in range(len(SAY_TEXTS)):
        a.words[(table - a.base) // 4 + k] = a.labels[f"say_{k}"]
    return a


# ---- the receiver's star, steady and bigger while a pass is in the air: FUN_804317f0 stores the star's blinking alpha
# (sin x 127 + 128) at 0x804CE588 (`stw r0,-6776(r9)` at STAR_ALPHA, r9 = 0x804D0000) and draws it through the
# scale matrix 0x805060B0 (built once from STAR_SCALE, 0.32)
STAR_ALPHA = (0x804318D8, 0x9009E588)
STAR_SCALE, STAR_MATRIX = 0x804DC254, 0x805060B0
STAR_BIG = 2.5                          # x the star's size while a pass is live


def make_star(L):
    a = ppc.Asm(CAVES["star"][0])
    a.label("star_alpha")
    a(STAR_ALPHA[1])
    hi, lo = ppc.hi_lo(STAR_SCALE)
    a(ppc.lis(11, hi), ppc.lfs(0, lo, 11))
    hi, lo = ppc.hi_lo(CAVES["state"][0])
    a(ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.lwz(11, S["on"], 12), ppc.cmpwi(11, 0))
    a.br("beq", "sa_scale")
    a(ppc.lwz(11, S["kind"], 12), ppc.cmpwi(11, KIND_PASS))
    a.br("bne", "sa_scale")
    a(ppc.lwz(11, S["phase"], 12), ppc.cmpwi(11, PH_DEAD))
    a.br("beq", "sa_scale")
    a(ppc.li(11, 255), ppc.stw(11, -6776, 9), ppc.lfs(13, C["star_big"], 12), ppc.fmuls(0, 0, 13))
    a.label("sa_scale")
    hi, lo = ppc.hi_lo(STAR_MATRIX)
    a(ppc.lis(11, hi), ppc.addi(11, 11, lo), ppc.stfs(0, 0, 11), ppc.stfs(0, 0x14, 11), ppc.stfs(0, 0x28, 11), BLR)
    return a


MAKERS = {"frame": make_frame, "ground": make_ground, "launch": make_launch, "run": make_run, "run2": make_run2,
          "run3": make_run3, "track": make_track, "catch": make_catch, "contact": make_contact, "kick": make_kick,
          "cam": make_cam, "cam2": make_cam2, "cam3": make_cam3, "shot": make_shot, "small": make_small,
          "posts": make_posts, "posts_m": make_posts_m, "posts2": make_posts2, "posts2b": make_posts2b,
          "posts3": make_posts3, "posts4": make_posts4, "pdata": make_pdata, "say": make_say, "tick": make_tick,
          "texts": make_texts, "star": make_star, "choose": make_choose}
CALLS = ("fb_launch", "fb_run", "fb_run2", "fb_run_set", "fb_norm", "fb_cam", "fb_cam2", "fb_cam_clear",
         "fb_posts_m", "fb_posts2", "fb_posts2b", "fb_posts3", "fb_posts4", "post_boxes", "post_bright",
         "post_dark", "post_colors", "fb_catch", "fb_hold", "fb_kick", "fb_contact", "fb_track", "fb_ground",
         "fb_say", "fb_say_side", "fb_unsay", "fb_said", "fb_tick", "fb_choose")


def data_blobs():
    state = bytes(STATE_SIZE)
    if STATE_SIZE > CAVES["state"][1]:
        raise SystemExit(f"football state: {STATE_SIZE} bytes; only {CAVES['state'][1]} fit")
    vals = const_values()
    consts = struct.pack(">II", 0x43300000, 0x80000000) + b"".join(struct.pack(">f", vals[n]) for n in CONST_LIST)
    consts += HELP_TEXT
    return state, consts


_cache = None


def caves():
    """[(address, first word, bytes)] and the labels (cached: teams.py asks for them too)."""
    global _cache
    if _cache:
        return _cache
    labels = {}
    for _ in range(2):          # the first pass finds where each stub lands
        ext = {n: labels.get(n, CAVES["frame"][0]) for n in CALLS}
        out, labels, sizes = [], {}, {}
        for name, make in MAKERS.items():
            a = make(ext)
            code = a.assemble()
            if len(code) > CAVES[name][1]:
                raise SystemExit(f"football cave {name}: {len(code)} bytes; only {CAVES[name][1]} fit")
            out.append((CAVES[name][0], CAVES[name][2], code))
            labels.update(a.labels)
            sizes[name] = len(code)
    state, consts = data_blobs()
    out = [(CAVES["state"][0], CAVES["state"][2], state), (CAVES["consts"][0], CAVES["consts"][2], consts)] + out
    sizes.update(state=len(state), consts=len(consts))
    labels["_sizes"] = sizes
    labels["help"] = CAVES["consts"][0] + 8 + 4 * len(CONST_LIST)
    _cache = (out, labels)
    return _cache


def texts():
    """[(message id, string address)]: answered by fb_messages (teams.py's message hook goes on to it)."""
    L = caves()[1]
    return [(MSG_HELP, L["help"]), (MSG_HELP2, L["help2"])] + [(MSG_SAY + k, L[f"say_{k}"])
                                                                 for k in range(len(SAY_TEXTS))]


def overlay_patches(rel):
    """[(address, new word, expected word)] for the golf overlay."""
    if rel != "C/L/V":
        return []
    import fbpose   # (it imports this module)
    L = caves()[1]
    return [(FRAME_HOOK[0], ppc.bl(FRAME_HOOK[0], L["fb_frame"]), FRAME_HOOK[1]),
            (STAR_STAGE[0], ppc.bl(STAR_STAGE[0], L["star_stage"]), STAR_STAGE[1]),
            (STAR_STATE[0], ppc.bl(STAR_STATE[0], L["star_state"]), STAR_STATE[1]),
            (GREEN_LIE[0], ppc.b(GREEN_LIE[0], L["green_lie"]), GREEN_LIE[1]),
            (GREEN_BALL[0], ppc.b(GREEN_BALL[0], L["green_ball"]), GREEN_BALL[1]),
            (POSTS_HOOK, ppc.bl(POSTS_HOOK, L["fb_posts"]), ppc.bl(POSTS_HOOK, MODEL_DRAW)),
            (STAR_ALPHA[0], ppc.bl(STAR_ALPHA[0], L["star_alpha"]), STAR_ALPHA[1])] + fbpose.overlay_patches(rel)


def overlay_tail():
    """The golf overlay's tail (golfext.py): fbpose.py's code and data."""
    import fbpose
    return fbpose.build()[0]


if __name__ == "__main__":
    out, labels = caves()
    for name, size in labels["_sizes"].items():
        print(f"{name}: {size} of {CAVES[name][1]} bytes at 0x{CAVES[name][0]:08X}")
