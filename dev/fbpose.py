"""v27 Football: the players' bodies. The receiver stands on the field as a golfer (the QB's partner, in its own
model), placed where the landing star is while the QB aims and running, jumping, diving and catching with the play once
the ball is thrown (football.py moves it); its poses are built bone by bone from fbmoves.py's keys (Andrew: "animations
for throwing, running, catching etc."), and no club shows in its hands. Code and data live in the golf overlay's tail
(golfext.py).

The game side (RE-NOTES "Football (v27)", "Golfer models"):
  - Only the shooter's golfer model exists during a turn: the player update loads it at the turn's start (states 10
    3, 10 and 0xB: `FUN_8000ecac(*(player +0x516C), bank id, 8)` for the texture bank when the golfer has one, then
    `FUN_8000f00c(player +0x5170, model id, bank holder, 8)`; the ids from the golfer object's (player +0x4F18)
    methods +0x5C and +0x58 (state 3; +0x60, the second model, in 10 and 0xB), which the costumes answer too; heap 8
    is 2 MB, room for one golfer) and the turn's end frees it (`FUN_8042685c` ->
    `FUN_80426b6c`, which in Doubles frees the partner's as well). Holders (0x24 bytes): +0 class (0x80160F10 model,
    0x80160F20 bank), +4 state, +8 wanted state (2 loaded, 5 free: `FUN_80009888` loaded, `FUN_800098b0` free,
    `FUN_800099dc` frees), +0xC heap, +0x10 a time stamp and +0x14 -> it (the unloader reads it), +0x18 file id, +0x1C
    the data (a model's instance, `FUN_8000f130(holder)` once it and its bank are loaded), +0x20 the bank's holder.
    The game animates every player whose +0x5170 holder is loaded (FUN_8041ef?? at 0x8041EF.. reads its animations,
    which the receiver doesn't have: PC 0x80005114 read past them), so the receiver's model goes in holders of our own
    (data "mh", "bh"), loaded while the QB aims and plays and freed when the turn moves on (fp_release).
  - A model instance (0x44 bytes): +0 the model root, +0x14 the bones' matrices, 0x60 each (+0x00 the bone in model
    space, +0x30 the same without the bone's scale and translation), +0x28 the list of bones with flag 2, +0x2C 0 =
    "pose changed" (MODEL_DRAW then turns +0x14 into skin matrices and skins the vertices once, and sets it).
    Bones (root +0x64, count +0x60, 0x60 each): +0 parent (-1 root), +4 the inverse bind matrix, +0x34 scale,
    +0x40 translation, +0x4C rotation (quaternion x y z w), +0x5C flags (4: children take +0x30, 2: listed, 0x400
    animated). The game's pose builder `FUN_800080c8` (main.dol 0x80008358..0x8000842C): non-root
    +0x30 = parent's (+0x30 with flag 4, else +0x00) x MTXQuat(q), root +0x30 = MTXQuat(q); +0x00 = +0x30 x
    MTXScale(s); its translation = parent's +0x00 x t (`FUN_8002e718(m, v, dst)` writes dst's translation column),
    the root's t. fp_fk does the same with our rotations for the bones a pose moves, and scale 0 for the clubs' bones.
  - The golfer's draw: `FUN_8042ab38(record)` (queued by `FUN_8001e924(1048576.0, FUN_8042ab38, record, layer 1)`,
    3 for Metal Mario) lights and draws record +0x34's holder with record +0x00 (3x4 world matrix: the golfer's place,
    turn and its object's scale, golfer object +0x84) after the camera; +0x30 the golfer code, +0x38 a byte, 0. The
    receiver has its own record; fp_queue (on the flag's queue function `FUN_8044c0e0`, which the scene's draw calls
    every frame of a hole) builds the pose and queues it.
Poses (fbmoves.py): per golfer a rig (the 19 joints' bones, the nearest joint above each, the hips' height, the club
bones, and each joint's parent bone's rest rotation R_p); per key the joints' model-space rotations D and the body's
pitch (cos, sin) and drop. fp_pose blends two keys (nlerp), sets each joint bone's local rotation to
conj(R_p) * conj(D_a) * D_j * R_p * l_b (fbmoves.py's notes) and runs fp_fk.
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppc  # noqa: E402
import golfext  # noqa: E402
import football as fb  # noqa: E402
import fbhud  # noqa: E402

BASE = golfext.BASE

# ---- the game
PLAYERS, PLAYER_SIZE = fb.PLAYERS, fb.PLAYER_SIZE
P_STATE, P_BALL, P_SETUP = fb.P_STATE, fb.P_BALL, fb.P_SETUP
P_OBJ, P_CODE, P_HOLDER, P_LIE, P_DRAWREC = 0x4F18, 0x51EF, 0x5170, 0x18, 4
OBJ_SCALE = 0x84
M_BANK_ID, M_MODEL_ID = 0x5C, 0x58            # golfer object methods (r3 = the object): bank, main model ([22])
D15, D16, D17 = fb.D15, fb.D16, fb.D17
S_TARGET = 0x1EC
B_POS, B_VEL = 0x9C, 0x50                              # the ball: place, velocity (feet a frame)

HOLDER_FREE, HOLDER_RELEASE = 0x800098B0, 0x800099DC
HOLDER_FLIP = 0x8000F248   # (holder) the instance's skinned vertices are double-buffered (+0x36 picks one); the
                           # player update flips the shooter's every frame (0x8042..: FUN_8000f248(player +0x5170))
HOLDER_VTABLE, BANK_VTABLE = 0x80160F10, 0x80160F20       # a model holder's and a texture bank holder's class
LOAD_BANK, LOAD_MODEL = 0x8000ECAC, 0x8000F00C       # (bank holder, id, heap); (holder, id, bank holder, heap)
GOLFER_HEAP = 0            # the main heap (heap 8, where the game loads golfers, has room for one: a second stalls loading)
HOLE = 0x804E68F8          # golf: the round's hole number (byte)
REC_DONE = 0x1BE            # golf: a team record's hole status (byte: 0 playing, 1 holed, 2 out)
HEAPS = 0x8023FA18         # main.dol: the 12 heaps, 0x14 each (+0 the free list, +4 free bytes)
RCV_HEAPS = (0, 2)         # v28 receivers' heaps: 0 the main one (3.8 MB free in a 1-player round, ~2.9 in Pigskin with 4
                           # before any receiver), 2 the hole arena (9 MB: 1.2 MB free on Pebble Beach 1, 3 on
                           # Battleground 1, 4 on Timber Creek 1); each receiver goes in the one with the most free
RCV_SIZES = (936928, 962336, 1626912, 1029280, 1052576, 1042528, 674560, 853824, 1530336, 1358464, 1099168, 293184,
             867936, 1001664, 1063424, 882368, 970496, 1209568)   # by golfer code: its model and bank unpacked, the
                           # larger of the normal and costume ones (v28 build: I/<golfer letter>/A + C; Peach and Yoshi
                           # carry their textures in the model)
RCV_SPARE = 0x20000        # and the instance's buffers, rounding
INSTANCE = 0x8000F130
QUEUE = 0x8001E924                                     # (f1 depth, r3 draw, r4 argument, r5 layer)
GOLFER_DRAW = 0x8042AB38
GOLFER_DEPTH = 0x804DBCC0                              # golf: the golfer draw's depth, 1048576.0
MTX_QUAT, MTX_SCALE, MTX_CONCAT, MTX_TRANS = 0x8003D904, 0x8003D700, 0x8003C6C8, 0x8002E718

QUEUE_HOOK = (0x8044C0E0, 0x9421FFE8)                  # FUN_8044c0e0's stwu r1,-24(r1): the flag's queue
PREVIEW_FLY = 0x80415790                               # (preview ball, lie, shot, mode): the aim's preview flight
PREVIEW_CALL = 0x80424974                              # its call for a human's aim (FUN_80423bbc, after 0x8042493C)
LIE_SIZE = 0x34                                        # a lie (team record +0xB4): place, ..., +0x28, +0x2C surface

# ---- the shot types (football.SHOT_TYPES: each one of the golfer's clubs). The player's bag (+0xE, a bit per club,
# 0-13) is what the game's opening club pick (the auto-aim, FUN_804ab1fc) and LB/RB's stepper (FUN_80412ee0(setup,
# -1 or 1)) choose from; in Football it holds the passes, and the stepper goes through all the types in their order
# (the field goal's club last). The aim update (FUN_80412f6c) clears the setup's "club changed" byte (+0x24E) first
# thing: a club that isn't a type is made one there, so the rest of that update sees a club change (zone, meter).
P_BAG = 0xE
S_CLUB, S_CHANGED, S_REPLAY, S_REPLAY_CLUB = 0x1D4, 0x24E, 0x184, 0x18C
CLUB_STEP = (0x80412EE0, 0x2C04FFFF)                   # FUN_80412ee0's cmpwi r4,-1
CLUB_STEP_SET, CLUB_STEP_OUT = 0x80412F58, 0x80412F64  # li r0,1; stw r11,0x1d4(r3); stb r0,0x24e(r3) / lbz r3; blr
AIM_CLEAR = (0x80412F8C, 0x9BC3024E)                   # FUN_80412f6c's stb r30,0x24e(r3) (r30 = 0, r3 = the setup)
ANGLE_STORE = (0x804C66E4, 0xD03F0044)                 # the shot builder's stfs f1,0x44(r31): the launch angle before
                                                       # the golfer's height (r29 = the club, r3 live)
SPIN_STORE = (0x804C67DC, 0xD17F0050)                  # its stfs f11,0x50(r31): the backspin, the golfer's spin in it
                                                       # (r29 = the club; f0 free past it off the putter)
ANGLE_FINAL = (0x804C6744, 0xD1BF0044)                 # its stfs f13,0x44(r31): the angle with the golfer's height
                                                       # (r12 free: a call follows)
BEND_END = (0x804C70F0, 0x801F000C)                    # its lwz r0,0xc(r31) where the timing miss's block (from
                                                       # 0x804C6D4C: angle + f x 10 degrees, backspin + speed x 1350 f,
                                                       # ...) and its skip meet; r30 = the player
ROTATE = 0x8040347C        # the shooter pick's Doubles part: bl TOGGLE(the team's first player), then d17 = the team,
TOGGLE = 0x80426B58        # + the side count when the record's toggle +0x1C2 is set (FUN_80426b58: toggle ^= 1)
PICK_DONE = 0x804034AC     # where it loads d17 and starts that player's turn
SOUND = 0x80011B88                                     # main.dol: (r3 sound, r4 volume) a common-set or voice sound
GOLF_SOUNDS = (0x80422144,   # FUN_80421154's bl SOUND: the ball's contact (0x1B2, or by the lie's method +0x30, or
                             # 0x1B5 / 0x1B6 by the club), the shot's only call there
               0x80459DA4)   # FUN_804598c8's bl SOUND: a power shot's hit (by golfer code; Shy Guy's cave 10 too)
S_SPIN = 0x1C8                                         # setup: the manual swing's spin combo, 1 A A topspin, 2 A B
                                                       # super topspin, 3 B B backspin, 4 B A super backspin, 0 none
GRAVITY = 0.011                                        # the ball's fall, feet a frame per frame (measured in flight)
SPIN_DV = (-0.25, -0.65, 0.2, 0.35)                    # by combo 1-4: x GRAVITY on the falling ball's y velocity a frame
                                                       # (a 212-yd Bomb: -14, -24, +13, +24 yd from the star)
TYPE_CLUBS = tuple(t[1] for t in fb.SHOT_TYPES)

# ---- v28 Pigskin: up to three receivers on the field (one team of 2-4: everyone but the QB; 2v2: the partner), each in
# its player's slot: its rank (0 starts on the star), place and motion (fp_recv_update), its model's holders, pose and
# draw record (fp_rcv)
N_RCV = 4                  # a slot per player (the QB's empty), so a new turn reloads only the old QB's model
R = {}
_roff = 0
for _name, _size in (("player", 4), ("rank", 4), ("x", 4), ("y", 4), ("z", 4), ("vx", 4), ("vz", 4), ("jump_t", 4), ("dive_t", 4),
                     ("dive_x", 4), ("dive_z", 4), ("jump_h", 4), ("px", 4), ("py", 4), ("pz", 4), ("dx", 4),
                     ("dz", 4), ("phase", 4), ("t", 4), ("model_id", 4), ("scale", 4), ("hips", 4), ("mh", 0x24),
                     ("bh", 0x24), ("rec", 0x40)):
    R[_name] = _roff
    _roff += _size
RSIZE = (_roff + 15) & ~15
RCV_SPREAD = 18.0          # while the QB aims: receivers 1 and 2 stand this many feet to the left / right of the star
RCV_BUMP = 2.5             # receivers closer than this (feet) are pushed apart (Andrew: "collide with each other")
RCV_PULL = 1.0             # the receiver camera backs off by the receivers' spread times this
PAD_TRIG_L, PAD_TRIG_R = 0x30, 0x34   # the pad's analog L / R (floats 0..1); the mod's controls send the left stick's
                                      # up there and its down to R (app/common.ps1), so the receiver reads them as up/down
GROUND_Q = fb.GROUND                   # (f1 x, f2 y, f3 z, r3 out[6]): the ground under a point
BALL_STEP = 0x80417B00                 # (ball) one update of a ball's flight (the aim preview runs it in a loop)
BALL_SIZE = 0xE0                       # a ball record (a team record +0xE8, of 0x1C8)
B_FLAGS = 0xC0                         # the ball: bit 0 = it has touched down
PRED_EVERY, PRED_MAX = 4, 720          # the landing run every 4 updates, at most 720 updates ahead
BALL_SEE = 1 / 25.0                    # the football in the air drawn bigger past 25 ft from the camera (its size x
                                       # distance / 25), so it stays in sight
BAG = sum(1 << c for c in TYPE_CLUBS[:fb.TYPE_FG])     # the passes (the auto-aim never picks a kick)

FB = fb.CAVES["state"][0]                              # football.py's state (fb.S offsets)
T = fb.TUNING

RUN_CYCLE = 3.6            # the run cycle's length (two steps) in hips heights
RUN_SPEED2 = 0.05 ** 2     # running from this speed (feet a frame) up
CATCH_D = 25.0             # the hands go up for a ball this near (feet, across)
BALL_SPIN = 0.45           # the football's spiral: radians a frame about its long axis
THROW_UP = 1.3             # a pass leaves the hand this many hips heights up (the arrows start there)
HAND_IN = 0.45            # the football in the hand: past the wrist this share of the forearm's length
THROW_SIDE = 0.35          # ... over a spot this many hips heights in from the QB's hips toward the ball (its hand)
BALL_A, BALL_B = 0.62, 0.36  # the football's half length and radius (feet; see ball_mesh)
QB_WIND = 30               # frames of the power bar to cock the arm (or leg) back
QB_REL = 2.0 / 3           # the throw's and kick's times at the cocked and released keys (keys 0, 1/3, 2/3, 1)
QB_COCK = 1.0 / 3
QB_REL_FRAMES = 3          # frames of the stroke (view 0xE) to release
QB_FOLLOW = 14             # frames of the flight to follow through
VIEW_POWER, VIEW_IMPACT, VIEW_STROKE = 0xB, 0xC, 0xE   # the setup's view (+0x1C4) during the swing
S_VIEW = 0x1C4

N_JOINTS = 19
N_RIGS = 18
GROUNDED = ("ready", "run", "catch", "hold", "throw", "kick")   # clips whose lower foot stays on the ground
RIG_SIZE, KEY_SIZE = 0x190, 0x140
RIG_ANC, RIG_HIPS, RIG_NHIDE, RIG_HIDE, RIG_RP, RIG_FEET = 0x14, 0x28, 0x2C, 0x30, 0x50, 0x180
RIG_HIPS_X, RIG_HIPS_Z = 0x188, 0x18C   # the hips' rest place across (the y is RIG_HIPS)
CLIP_LOOP, CLIP_GROUND = 1, 2       # clip flags: loops; keeps the lower foot on the ground
KEY_PC, KEY_PS, KEY_DROP = 0x130, 0x134, 0x138
MAX_HIDE = 32


# ---- instructions ppc.py doesn't have
def stwx(rs, ra, rb): return 0x7C00012E | rs << 21 | ra << 16 | rb << 11
def fnmsubs(d, a, c, b): return 0xEC00003C | d << 21 | a << 16 | b << 11 | c << 6   # d = b - a*c
def lfd(frd, d, ra): return ppc._d(50, frd, d, ra)
def stfd(frs, d, ra): return ppc._d(54, frs, d, ra)
def lha(rd, d, ra): return ppc._d(42, rd, d, ra)
def fsub(d, a, b): return 0xFC000028 | d << 21 | a << 16 | b << 11
def divw(rd, ra, rb): return ppc.divw(rd, ra, rb)
def cmplw(ra, rb): return 0x7C000040 | ra << 16 | rb << 11
BCTRL = 0x4E800421
BLR, BEQLR, BNELR = ppc.BLR, fb.BEQLR, fb.BNELR
lfsx = fb.lfsx

# ---- our data (r31 in the stubs)
D = {}
_off = 0
for _name, _size in (("rec", 0x40), ("tmp", 0x30), ("mh", 0x24), ("bh", 0x24), ("model_id", 4),
                     ("x", 4), ("y", 4), ("z", 4), ("dx", 4), ("dz", 4), ("scale", 4), ("hips", 4),
                     ("u", 4), ("pc", 4), ("ps", 4), ("drop", 4), ("phase", 4), ("t", 4),
                     ("zero", 4), ("one", 4), ("half", 4), ("threehalf", 4), ("tiny", 4), ("run_cycle", 4),
                     ("run_speed2", 4), ("catch_d2", 4), ("inv_catch_d2", 4), ("down_frames", 4), ("inv_dive", 4),
                     ("inv_jump", 4), ("big", 4), ("clip_flags", 4), ("qb_state", 4), ("qb_f", 4), ("qb_t", 4), ("qb_wind", 4), ("qb_relf", 4),
                     ("qb_follow", 4), ("qb_cock", 4), ("qb_rel", 4), ("qb_sx", 4), ("qb_sy", 4), ("qb_sz", 4), ("shift_x", 4),
                     ("shift_y", 4), ("shift_z", 4), ("bax", 4), ("bay", 4), ("baz", 4), ("bcs", 4),
                     ("bsn", 4), ("spin_c", 4), ("spin_s", 4), ("ball_m", 0x30), ("ball_at", 4), ("ball_mode", 4), ("bp", 12), ("bv", 12), ("throw_h", 4), ("lie_copy", 0x34),
                     ("throw_up", 4), ("hand_in", 4), ("throw_side", 4), ("throw_dx", 4), ("throw_dz", 4), ("w_set", 4), ("w_mx", 4),
                     ("w_mz", 4), ("tee_up", 4), ("tee_tilt", 4), ("dbg_ball", 4), ("dbg_ball_f", 4),
                     ("dbg_ball_up", 4),
                     ("dbg_noqb", 4), ("dbg_near", 4), ("dbg_clip", 4), ("dbg_t", 4), ("dbg_speed", 4),
                     ("types", 4), ("angle_k", 4 * 14), ("spin_k", 4 * 14), ("badge_reset", 4), ("a0", 4), ("s0", 4), ("spin_dv", 16),
                     ("rcv", RSIZE * N_RCV), ("need", 4 * 18), ("lead", 4), ("hole_seen", 4), ("rot", 4), ("rcv_live", 4), ("catcher", 4), ("pred_n", 4), ("gq", 24), ("spread", 4),
                     ("bump", 4), ("bump2", 4), ("pull", 4), ("gq_max", 4), ("ball_see2", 4), ("pball", BALL_SIZE),
                     ("magic", 8), ("cvt", 8), ("e", 16), ("t1", 16),
                     ("dbuf", 16 * N_JOINTS), ("q", 16 * N_JOINTS), ("map", 256)):
    if _size == 8 or _size == 16:
        _off = (_off + 7) & ~7
    D[_name] = _off
    _off += _size
DATA_SIZE = (_off + 31) & ~31
CONSTS = {"spread": RCV_SPREAD, "bump": RCV_BUMP, "bump2": RCV_BUMP ** 2, "pull": RCV_PULL, "gq_max": 9.0,
          "ball_see2": BALL_SEE ** 2, "throw_up": THROW_UP, "hand_in": HAND_IN, "throw_side": THROW_SIDE, "tee_up": BALL_A * 0.95, "tee_tilt": 0.25, "dbg_ball_f": 3.0, "dbg_ball_up": 4.0, "bax": 1.0, "bcs": 1.0, "spin_c": math.cos(BALL_SPIN), "spin_s": math.sin(BALL_SPIN), "big": 1e9, "zero": 0.0, "one": 1.0, "half": 0.5, "threehalf": 1.5, "tiny": 1e-6, "run_cycle": RUN_CYCLE,
          "run_speed2": RUN_SPEED2, "catch_d2": CATCH_D ** 2, "inv_catch_d2": 1 / CATCH_D ** 2,
          "down_frames": float(T["down_frames"]), "inv_dive": 1.0 / T["dive_frames"], "inv_jump": 1.0 / T["jump_frames"],
          "qb_wind": 1.0 / QB_WIND, "qb_relf": 1.0 / QB_REL_FRAMES, "qb_follow": 1.0 / QB_FOLLOW,
          "qb_cock": QB_COCK, "qb_rel": QB_REL}


def _enter(a, size, first):
    a(ppc.stwu(1, -size, 1), ppc.mflr(0), ppc.stw(0, size + 4, 1), ppc.stmw(first, size - 4 * (32 - first), 1))


def _leave(a, size, first):
    a(ppc.lmw(first, size - 4 * (32 - first), 1), ppc.lwz(0, size + 4, 1), ppc.mtlr(0), ppc.addi(1, 1, size), BLR)


def _call(a, addr):
    a(ppc.lis(12, ppc.hi_lo(addr)[0]), ppc.addi(12, 12, ppc.hi_lo(addr)[1]), ppc.mtctr(12), BCTRL)


def _li32(a, reg, value):
    hi, lo = ppc.hi_lo(value)
    a(ppc.lis(reg, hi), ppc.addi(reg, reg, lo))


def _rsqrt(a, y, n2, t0, t1, t2):
    """f{y} = 1 / sqrt(f{n2}) (> 0): frsqrte and Newton twice; uses f{t0}-f{t2}; r31 = our data."""
    a(ppc.frsqrte(y, n2), ppc.lfs(t0, D["half"], 31), ppc.lfs(t1, D["threehalf"], 31))
    for _ in range(2):
        a(ppc.fmuls(t2, y, y), ppc.fmuls(t2, t2, n2), ppc.fmuls(t2, t2, t0), ppc.fsubs(t2, t1, t2), ppc.fmuls(y, y, t2))


def _int_to_float(a, f, r):
    """f{f} = (float) r{r} (signed); uses r0 and our data's "cvt"."""
    a(ppc.lis(0, 0x4330), ppc.stw(0, D["cvt"], 31), ppc.xoris(0, r, 0x8000), ppc.stw(0, D["cvt"] + 4, 31),
      lfd(f, D["cvt"], 31), lfd(0, D["magic"], 31), fsub(f, f, 0), ppc.frsp(f, f))


def make_code(L):
    """L: the tables' addresses ("data", "rigs", "keys", "clips")."""
    a = ppc.Asm(BASE)
    data = L["data"]

    # ---- fp_queue: b from QUEUE_HOOK (the flag's queue function's first instruction, r3 = its argument)
    a.label("fp_queue")
    a(ppc.stwu(1, -0x10, 1), ppc.mflr(0), ppc.stw(0, 0x14, 1), ppc.stw(3, 0x08, 1))
    a.br("bl", "fp_frame")
    a(ppc.lwz(3, 0x08, 1), ppc.lwz(0, 0x14, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x10))
    a(QUEUE_HOOK[1])                                   # the instruction replaced
    a.b(QUEUE_HOOK[0] + 4)

    # ---- fp_frame: the receiver, every frame of a hole
    a.label("fp_frame")
    _enter(a, 0x60, 22)
    _li32(a, 31, data)
    a(ppc.li(0, 0), ppc.stw(0, D["ball_mode"], 31))
    _li32(a, 24, FB)                                    # r24 = football's state
    a(ppc.lwz(0, fb.S["on"], 24), ppc.cmpwi(0, 0))
    a.br("beq", "f_none")
    _li32(a, 12, PLAYERS + P_BAG)                       # every player's bag: the passes (the shot types)
    a(ppc.li(0, BAG))
    for _ in range(4):
        a(ppc.sth(0, 0, 12), ppc.addi(12, 12, PLAYER_SIZE))
    a(ppc.lwz(0, D["badge_reset"], 31), ppc.cmpwi(0, 0))   # once a round: the HUD badge's loaded files forgotten, so
    a.br("bne", "f_badge")                              # its first load is ours too (fbhud.py; it starts as club 0's)
    a(ppc.li(0, 1), ppc.stw(0, D["badge_reset"], 31), ppc.li(0, -1))
    hi, lo = ppc.hi_lo(fbhud.BADGE_CACHE)
    a(ppc.lis(12, hi), ppc.stw(0, lo, 12), ppc.stw(0, lo + 4, 12))
    a.label("f_badge")
    a(ppc.lis(12, 0x804E), ppc.lbz(0, HOLE & 0xFFFF, 12), ppc.lwz(9, D["hole_seen"], 31), ppc.cmpw(0, 9))
    a.br("beq", "f_hole")                               # a new hole: the receivers' models let go (two sit in the
    a(ppc.stw(0, D["hole_seen"], 31))                   # hole arena, heap 2), else they stay loaded between turns
    for k in range(N_RCV):
        a(ppc.addi(3, 31, D["rcv"] + RSIZE * k))
        a.br("bl", "fp_release")
    a.label("f_hole")
    a(ppc.lis(12, 0x804E), ppc.lbz(3, D17 & 0xFFFF, 12), ppc.andi_(0, 3, 0x80))
    a.br("bne", "f_none")
    _li32(a, 12, PLAYERS)
    a(ppc.mulli(3, 3, PLAYER_SIZE), ppc.add(30, 12, 3))  # r30 = the QB
    a(ppc.lwz(9, fb.P_REC, 30), ppc.lbz(0, REC_DONE, 9), ppc.cmpwi(0, 0))
    a.br("bne", "f_none")                               # its team's hole over: the receivers let go (before the next
    a(ppc.lwz(0, P_STATE, 30), ppc.cmpwi(0, 4))         # hole's files load into the hole arena)
    a.br("blt", "f_hide")                               # (a turn changing hands: receivers kept, not drawn)
    a.br("bgt", "f_state")
    a(ppc.li(0, 0), ppc.stw(0, D["rcv_live"], 31))      # aiming: no play yet (fp_recv_update starts the next)
    a.label("f_state")
    a(ppc.cmpwi(0, 8))
    a.br("bgt", "f_hide")
    a.br("bl", "fp_slots")                              # who receives
    a(ppc.lwz(0, D["dbg_noqb"], 31), ppc.cmpwi(0, 0))   # (tests: the game's own swing pose)
    a.br("bne", "f_noqb")
    _li32(a, 9, fb.BALL_MATRIX)                         # no golf ball (nor its tee) in Football's turns: its
    a(ppc.lfs(0, D["zero"], 31), ppc.stfs(0, 0x00, 9), ppc.stfs(0, 0x14, 9), ppc.stfs(0, 0x28, 9))  # scale 0 for the
    a.br("bl", "fp_qb")                                 # QB's throw or kick (the ball's draw, later this frame)
    a.label("f_noqb")
    a(ppc.lwz(0, D["dbg_ball"], 31), ppc.cmpwi(0, 2))   # (tests: the football in receiver 0's right hand, after
    a.br("beq", "f_noball")                             # its pose, over the QB's: fp_rcv)
    a(ppc.lwz(0, D["ball_mode"], 31), ppc.cmpwi(0, 0))  # the football: in the QB's hand or on the spot (fp_qb),
    a.br("bne", "f_ball")                               # in the air (or held after a catch)
    a(ppc.lwz(0, D["dbg_ball"], 31), ppc.cmpwi(0, 0))   # (tests: the football by receiver 0 while aiming)
    a.br("beq", "f_ball_air")
    a(ppc.lwz(9, D["lead"], 31), ppc.cmpwi(9, 0))      # (the receiver on the star)
    a.br("beq", "f_ball_air")
    a(ppc.lfs(1, D["dbg_ball_f"], 31), ppc.lfs(2, R["dx"], 9), ppc.lfs(0, R["px"], 9),
      ppc.fmadds(0, 2, 1, 0), ppc.stfs(0, D["bp"], 31), ppc.lfs(2, R["dz"], 9), ppc.lfs(0, R["pz"], 9),
      ppc.fmadds(0, 2, 1, 0), ppc.stfs(0, D["bp"] + 8, 31), ppc.lfs(0, R["py"], 9),
      ppc.lfs(1, D["dbg_ball_up"], 31), ppc.fadds(0, 0, 1), ppc.stfs(0, D["bp"] + 4, 31))   # 4 ft up, 3 toward the QB
    a(ppc.lfs(4, R["dz"], 9), ppc.stfs(4, D["bv"], 31), ppc.lfs(4, D["half"], 31), ppc.stfs(4, D["bv"] + 4, 31),
      ppc.lfs(4, R["dx"], 9), ppc.fneg(4, 4), ppc.stfs(4, D["bv"] + 8, 31), ppc.li(0, 1),
      ppc.stw(0, D["ball_mode"], 31))
    a.br("b", "f_ball")
    a.label("f_ball_air")
    a(ppc.lwz(0, P_STATE, 30), ppc.cmpwi(0, 7))
    a.br("bne", "f_noball")
    a(ppc.lwz(0, fb.S["kind"], 24), ppc.cmpwi(0, 0))
    a.br("beq", "f_noball")
    a.label("f_ball")
    a.br("bl", "fp_ball")
    a.label("f_noball")
    a(ppc.lwz(0, fb.S["kind"], 24), ppc.cmpwi(0, fb.KIND_PASS))
    a.br("beq", "f_want")
    a(ppc.cmpwi(0, 0))
    a.br("bne", "f_hide")                               # a kick: no receivers on the field
    a(ppc.lwz(0, fb.S["kick_pick"], 24), ppc.cmpwi(0, 0))
    a.br("bne", "f_hide")
    a.label("f_want")
    for k in range(N_RCV):
        a(ppc.addi(3, 31, D["rcv"] + RSIZE * k), ppc.li(4, k))
        a.br("bl", "fp_rcv")
    a.label("f_out")
    _leave(a, 0x60, 22)
    a.label("f_hide")                                   # no receivers drawn this frame (their models kept)
    a(ppc.li(0, 0), ppc.stw(0, D["throw_h"], 31))
    a.br("b", "f_out")
    a.label("f_none")                                   # Pigskin off, or nobody up: let their holders go
    a(ppc.li(0, 0), ppc.stw(0, D["throw_h"], 31))
    for k in range(N_RCV):
        a(ppc.addi(3, 31, D["rcv"] + RSIZE * k))
        a.br("bl", "fp_release")
    a.br("b", "f_out")

    # ---- fp_qb: (r30 = the QB, state 4..8, r24 = football's state, r31 = our data) the QB's pose over the game's
    # swing: the throw (or the kick, when the play is one or the aim's pick is). The swing is all in state 4 but its
    # last frames: the setup's view (+0x1C4) 0xB while the power bar runs (cocking: the throw's 0 .. QB_COCK over
    # QB_WIND frames), 0xC waiting for the impact press (held cocked), 0xE the stroke (released, to 2/3 over QB_REL
    # frames); then states 5-6 (a frame or two) and the flight, 7 (followed through, to 1 over QB_FOLLOW frames).
    a.label("fp_qb")
    _enter(a, 0x30, 27)
    a(ppc.lwz(3, P_STATE, 30), ppc.lwz(9, P_SETUP, 30), ppc.lwz(4, S_VIEW, 9), ppc.slwi(0, 3, 8), ppc.or_(0, 0, 4),
      ppc.lwz(5, D["qb_state"], 31), ppc.cmpw(5, 0))
    a.br("beq", "q_same")
    a(ppc.stw(0, D["qb_state"], 31), ppc.lfs(0, D["zero"], 31), ppc.stfs(0, D["qb_f"], 31), ppc.srwi(6, 5, 8),
      ppc.cmpwi(6, 4))
    a.br("beq", "q_clip")
    a(ppc.li(6, 0), ppc.stw(6, D["w_set"], 31))          # a new turn's aim: the throw's spot noted again
    a.br("b", "q_clip")
    a.label("q_same")
    a(ppc.lfs(0, D["qb_f"], 31), ppc.lfs(1, D["one"], 31), ppc.fadds(0, 0, 1), ppc.stfs(0, D["qb_f"], 31))
    a.label("q_clip")                                   # f0 = frames in this state and view; r3 state, r4 view
    a(ppc.li(27, CLIP["throw"]), ppc.lwz(0, fb.S["kind"], 24), ppc.cmpwi(0, fb.KIND_KICK))
    a.br("beq", "q_kick")
    a(ppc.cmpwi(0, 0))
    a.br("bne", "q_t")
    a(ppc.lwz(0, fb.S["kick_pick"], 24), ppc.cmpwi(0, 0))
    a.br("beq", "q_t")
    a.label("q_kick")
    a(ppc.li(27, CLIP["kick"]))
    a.label("q_t")                                      # f1 = t: a from-to ramp f2 -> f3 over 1/f5 frames
    a(ppc.lfs(4, D["one"], 31), ppc.lfs(6, D["qb_cock"], 31), ppc.lfs(7, D["qb_rel"], 31), ppc.cmpwi(3, 4))
    a.br("bne", "q_flight")
    a(ppc.lfs(1, D["zero"], 31), ppc.cmpwi(4, VIEW_POWER))
    a.br("bne", "q_top")
    a(ppc.fmr(2, 1), ppc.fmr(3, 6), ppc.lfs(5, D["qb_wind"], 31))
    a.br("b", "q_ramp")
    a.label("q_top")
    a(ppc.fmr(1, 6), ppc.cmpwi(4, VIEW_IMPACT))
    a.br("beq", "q_pose")
    a(ppc.lfs(1, D["zero"], 31), ppc.cmpwi(4, VIEW_STROKE))
    a.br("bne", "q_pose")
    a(ppc.fmr(2, 6), ppc.fmr(3, 7), ppc.lfs(5, D["qb_relf"], 31))
    a.br("b", "q_ramp")
    a.label("q_flight")                                 # states 5-8: on from the release to the end
    a(ppc.fmr(2, 7), ppc.fmr(3, 4), ppc.lfs(5, D["qb_follow"], 31))
    a.label("q_ramp")
    a(ppc.fmuls(1, 0, 5), ppc.fcmpu(1, 4))
    a.br("ble", "q_ramp2")
    a(ppc.fmr(1, 4))
    a.label("q_ramp2")
    a(ppc.fsubs(3, 3, 2), ppc.fmadds(1, 1, 3, 2))
    a.label("q_pose")
    a(ppc.stfs(1, D["qb_t"], 31), ppc.addi(3, 30, P_HOLDER))
    _call(a, INSTANCE)
    a(ppc.mr(28, 3), ppc.cmpwi(3, 0))
    a.br("beq", "q_out")
    a(ppc.lbz(29, P_CODE, 30), ppc.cmplwi(29, N_RIGS - 1))
    a.br("ble", "q_code")
    a(ppc.li(29, 0))
    a.label("q_code")
    # A pass is thrown from the hand: while aiming (state 4) the aim's preview flies from THROW_UP hips heights over the
    # QB's hand (fp_preview, "throw_h", "throw_dx/dz"), so the arrows start at the throw; the first frame of the flight
    # moves the ball as much (it was launched from the ground at the spot). (Raising the lie itself moved the ball and
    # the golfer with it.)
    a(ppc.lwz(3, P_STATE, 30), ppc.mulli(9, 29, RIG_SIZE))
    _li32(a, 10, L["rigs"])
    a(ppc.add(9, 9, 10), ppc.lfs(1, RIG_HIPS, 9), ppc.lwz(9, P_OBJ, 30), ppc.lfs(2, OBJ_SCALE, 9), ppc.fmuls(1, 1, 2),
      ppc.lfs(2, D["throw_up"], 31), ppc.fmuls(1, 1, 2), ppc.lfs(0, D["zero"], 31), ppc.lfs(5, D["throw_h"], 31))
    a(ppc.cmpwi(3, 7))
    a.br("bne", "q_lie4")
    a(ppc.fcmpu(5, 0))
    a.br("beq", "q_lie_done")
    a(ppc.lwz(9, P_BALL, 30), ppc.lfs(2, B_POS + 4, 9), ppc.fadds(2, 2, 5), ppc.stfs(2, B_POS + 4, 9),
      ppc.stfs(0, D["throw_h"], 31))
    for off, name in ((0, "throw_dx"), (8, "throw_dz")):
        a(ppc.lfs(2, B_POS + off, 9), ppc.lfs(3, D[name], 31), ppc.fadds(2, 2, 3), ppc.stfs(2, B_POS + off, 9))
    a.br("b", "q_lie_done")
    a.label("q_lie4")
    a(ppc.cmpwi(3, 4))
    a.br("bne", "q_lie_done")
    a(ppc.cmpwi(27, CLIP["throw"]))
    a.br("beq", "q_lie_set")
    a(ppc.fmr(1, 0))                                    # a kick: from the ground
    a.label("q_lie_set")
    a(ppc.stfs(1, D["throw_h"], 31))
    # ... and across, from the QB's hand: the QB stands where the swing puts the golfer, so the spot is the game's hips
    # at address (noted once a turn, from the game's own pose: it sways) THROW_SIDE hips heights in toward the ball,
    # through the QB's world matrix (mirrored for a lefty, as the hand's below)
    a(ppc.lwz(0, D["w_set"], 31), ppc.cmpwi(0, 0))
    a.br("bne", "q_w")
    a(ppc.lwz(0, 0x2C, 28), ppc.cmpwi(0, 0))
    a.br("bne", "q_lie_done")
    a(ppc.mulli(9, 29, RIG_SIZE))
    _li32(a, 10, L["rigs"])
    a(ppc.add(9, 9, 10), ppc.lbz(11, J_INDEX["hips"], 9), ppc.cmpwi(11, 0xFF))
    a.br("beq", "q_lie_done")
    a(ppc.lwz(10, 0x14, 28), ppc.mulli(11, 11, 0x60), ppc.add(11, 11, 10), ppc.lfs(1, 0x0C, 11),
      ppc.stfs(1, D["w_mx"], 31), ppc.lfs(1, RIG_HIPS, 9), ppc.lfs(2, D["throw_side"], 31), ppc.lfs(3, 0x2C, 11),
      ppc.fmadds(1, 1, 2, 3), ppc.stfs(1, D["w_mz"], 31), ppc.li(0, 1), ppc.stw(0, D["w_set"], 31))
    a.label("q_w")
    a(ppc.lfs(1, D["w_mx"], 31), ppc.lfs(3, D["w_mz"], 31), lha(0, 0x34, 28), ppc.cmpwi(0, 1))
    a.br("bne", "q_w_unmirrored")
    a(ppc.fneg(1, 1))
    a.label("q_w_unmirrored")
    a(ppc.lwz(10, P_DRAWREC, 30))
    for k, name in ((0, "throw_dx"), (2, "throw_dz")):
        a(ppc.lfs(4, 0x10 * k, 10), ppc.lfs(6, 0x10 * k + 8, 10), ppc.fmuls(7, 4, 1), ppc.fmadds(7, 6, 3, 7),
          ppc.stfs(7, D[name], 31))
    a.label("q_lie_done")
    # where the game's swing puts the golfer: its animation moves the body from the ball (the world matrix's place)
    # back to the stance and down to the ground. When this frame's pose is the game's (+0x2C = 0: built, not drawn
    # yet), the shift = its hips' place across and its lower ankle's height, less their rest ones; else last frame's.
    a(ppc.lwz(0, 0x2C, 28), ppc.cmpwi(0, 0))
    a.br("bne", "q_shifted")
    a(ppc.mulli(9, 29, RIG_SIZE))
    _li32(a, 10, L["rigs"])
    a(ppc.add(9, 9, 10), ppc.lwz(10, 0x14, 28), ppc.lbz(11, J_INDEX["hips"], 9), ppc.cmpwi(11, 0xFF))
    a.br("beq", "q_shifted")
    a(ppc.mulli(11, 11, 0x60), ppc.add(11, 11, 10), ppc.lfs(1, 0x0C, 11), ppc.lfs(2, RIG_HIPS_X, 9),
      ppc.fsubs(1, 1, 2), ppc.stfs(1, D["qb_sx"], 31), ppc.lfs(1, 0x2C, 11), ppc.lfs(2, RIG_HIPS_Z, 9),
      ppc.fsubs(1, 1, 2), ppc.stfs(1, D["qb_sz"], 31), ppc.lfs(1, D["big"], 31))
    for k, joint in enumerate(("foot_r", "foot_l")):
        a(ppc.lbz(11, J_INDEX[joint], 9), ppc.cmpwi(11, 0xFF))
        a.br("beq", f"q_nofoot{k}")
        a(ppc.mulli(11, 11, 0x60), ppc.add(11, 11, 10), ppc.lfs(2, 0x1C, 11), ppc.lfs(3, RIG_FEET + 4 * k, 9),
          ppc.fsubs(2, 2, 3), ppc.fcmpu(2, 1))
        a.br("bge", f"q_nofoot{k}")
        a(ppc.fmr(1, 2))
        a.label(f"q_nofoot{k}")
    a(ppc.lfs(0, D["big"], 31), ppc.fcmpu(1, 0))
    a.br("blt", "q_sy")
    a(ppc.lfs(1, D["zero"], 31))
    a.label("q_sy")
    a(ppc.stfs(1, D["qb_sy"], 31))
    a.label("q_shifted")
    for axis in "xyz":
        a(ppc.lwz(0, D["qb_s" + axis], 31), ppc.stw(0, D["shift_" + axis], 31))
    # the passer stands where the kicker does, beside and behind the ball as the swing puts the golfer (Andrew: "move
    # them to the left side like the field goal"; it stood on the ball's spot before)
    a(ppc.mr(3, 28), ppc.mr(4, 29), ppc.mr(5, 27), ppc.lfs(1, D["qb_t"], 31))
    a.br("bl", "fp_pose")
    a(ppc.li(0, 0))
    for axis in "xyz":
        a(ppc.stw(0, D["shift_" + axis], 31))
    # the football while aiming and swinging (state 4): a pass's in the throwing hand (its bone in model space, mirrored
    # for a lefty: instance +0x34 = 1, through the QB's draw record's world matrix, player +4), pointed downfield and
    # up; a kick's standing on the ball's spot
    a(ppc.lwz(0, P_STATE, 30), ppc.cmpwi(0, 4))
    a.br("bne", "q_out")
    a(ppc.lwz(9, P_SETUP, 30), ppc.lwz(10, P_BALL, 30), ppc.lfs(4, S_TARGET, 9), ppc.lfs(0, B_POS, 10),
      ppc.fsubs(4, 4, 0), ppc.lfs(6, S_TARGET + 8, 9), ppc.lfs(0, B_POS + 8, 10), ppc.fsubs(6, 6, 0),
      ppc.fmuls(7, 4, 4), ppc.fmadds(7, 6, 6, 7))
    _rsqrt(a, 8, 7, 9, 10, 11)
    a(ppc.fmuls(4, 4, 8), ppc.fmuls(6, 6, 8))           # (f4, f6) = downfield
    a(ppc.cmpwi(27, CLIP["throw"]))
    a.br("beq", "q_hand")
    a(ppc.lfs(0, D["tee_tilt"], 31), ppc.fmuls(1, 4, 0), ppc.stfs(1, D["bv"], 31), ppc.fmuls(1, 6, 0),
      ppc.stfs(1, D["bv"] + 8, 31), ppc.lfs(1, D["one"], 31), ppc.stfs(1, D["bv"] + 4, 31))
    a(ppc.lwz(10, P_BALL, 30), ppc.lfs(1, B_POS, 10), ppc.stfs(1, D["bp"], 31), ppc.lfs(1, B_POS + 8, 10),
      ppc.stfs(1, D["bp"] + 8, 31), ppc.lfs(1, B_POS + 4, 10), ppc.lfs(0, D["tee_up"], 31), ppc.fadds(1, 1, 0),
      ppc.stfs(1, D["bp"] + 4, 31))
    a.br("b", "q_ball_on")
    a.label("q_hand")
    a(ppc.stfs(4, D["bv"], 31), ppc.stfs(6, D["bv"] + 8, 31), ppc.lfs(1, D["half"], 31), ppc.stfs(1, D["bv"] + 4, 31))
    a(ppc.mulli(9, 29, RIG_SIZE))
    _li32(a, 10, L["rigs"])
    a(ppc.add(4, 9, 10), ppc.mr(3, 28), ppc.lwz(5, P_DRAWREC, 30))   # (the QB's draw record: its world matrix)
    a.br("bl", "fp_palm")
    a(ppc.cmpwi(3, 0))
    a.br("beq", "q_out")
    a.label("q_ball_on")
    a(ppc.li(0, 1), ppc.stw(0, D["ball_mode"], 31))
    a.label("q_out")
    _leave(a, 0x30, 27)

    # ---- fp_ball: (r30 = the QB, r24 = football's state, r31 = our data) the football's frame this frame, at the ball
    # (+0x9C), its long axis along the flight (+0x50; held after a catch: the receiver's way), spinning about it
    # (a spiral, BALL_SPIN a frame); then its draw queued (fp_ball_draw)
    a.label("fp_ball")
    _enter(a, 0x20, 30)
    a(ppc.lwz(9, P_BALL, 30), ppc.addi(9, 9, B_POS), ppc.lwz(0, D["ball_mode"], 31), ppc.cmpwi(0, 0))
    a.br("beq", "b_ball")
    a(ppc.addi(9, 31, D["bp"]), ppc.lfs(4, D["bv"], 31), ppc.lfs(5, D["bv"] + 4, 31), ppc.lfs(6, D["bv"] + 8, 31))
    a.br("b", "b_axis")
    a.label("b_ball")
    a(ppc.stw(9, D["ball_at"], 31), ppc.lwz(9, P_BALL, 30), ppc.lfs(4, B_VEL, 9), ppc.lfs(5, B_VEL + 4, 9),
      ppc.lfs(6, B_VEL + 8, 9), ppc.lwz(9, D["ball_at"], 31))
    a(ppc.lwz(0, fb.S["phase"], 24), ppc.cmpwi(0, fb.PH_HOLD))
    a.br("bne", "b_axis")
    a(ppc.lfs(4, D["dx"], 31), ppc.lfs(5, D["zero"], 31), ppc.lfs(6, D["dz"], 31))
    a.label("b_axis")
    a(ppc.stw(9, D["ball_at"], 31))                      # (the place: the ball's, or the test's)
    a(ppc.fmuls(7, 4, 4), ppc.fmadds(7, 5, 5, 7), ppc.fmadds(7, 6, 6, 7), ppc.lfs(0, D["tiny"], 31), ppc.fcmpu(7, 0))
    a.br("ble", "b_spin")                               # (stopped: the last axis)
    _rsqrt(a, 8, 7, 9, 10, 11)
    a(ppc.fmuls(4, 4, 8), ppc.fmuls(5, 5, 8), ppc.fmuls(6, 6, 8), ppc.stfs(4, D["bax"], 31), ppc.stfs(5, D["bay"], 31),
      ppc.stfs(6, D["baz"], 31))
    a.label("b_spin")                                   # (cs, sn) on by the spin step, renormalised
    a(ppc.lfs(1, D["bcs"], 31), ppc.lfs(2, D["bsn"], 31), ppc.lfs(3, D["spin_c"], 31), ppc.lfs(4, D["spin_s"], 31),
      ppc.fmuls(5, 1, 3), fnmsubs(5, 2, 4, 5), ppc.fmuls(6, 2, 3), ppc.fmadds(6, 1, 4, 6),
      ppc.fmuls(7, 5, 5), ppc.fmadds(7, 6, 6, 7))
    _rsqrt(a, 8, 7, 9, 10, 11)
    a(ppc.fmuls(1, 5, 8), ppc.fmuls(2, 6, 8), ppc.stfs(1, D["bcs"], 31), ppc.stfs(2, D["bsn"], 31))
    # X = the axis; Y0 = up x X normalised = (X.z, 0, -X.x) / n; Z0 = X x Y0; Y = cs Y0 + sn Z0, Z = cs Z0 - sn Y0
    a(ppc.lfs(4, D["bax"], 31), ppc.lfs(5, D["bay"], 31), ppc.lfs(6, D["baz"], 31),
      ppc.fmuls(7, 6, 6), ppc.fmadds(7, 4, 4, 7), ppc.lfs(0, D["tiny"], 31), ppc.fcmpu(7, 0))
    a.br("bgt", "b_side")
    a(ppc.lfs(7, D["one"], 31), ppc.lfs(6, D["one"], 31), ppc.lfs(4, D["zero"], 31))   # (straight up: any side)
    a.label("b_side")
    _rsqrt(a, 8, 7, 9, 10, 11)
    a(ppc.fmuls(9, 6, 8), ppc.fmuls(10, 4, 8), ppc.fneg(10, 10))                          # Y0 = (f9, 0, f10)
    a(ppc.lfs(4, D["bax"], 31), ppc.lfs(6, D["baz"], 31))
    a(ppc.fmuls(11, 5, 10), ppc.fmuls(12, 6, 9), fnmsubs(12, 4, 10, 12), ppc.fmuls(13, 5, 9), ppc.fneg(13, 13))
    # Z0 = (f11, f12, f13); Y = cs Y0 + sn Z0 -> (f7, f8, f3); Z = cs Z0 - sn Y0 -> (f11, f12, f13)
    a(ppc.fmuls(7, 1, 9), ppc.fmadds(7, 2, 11, 7), ppc.fmuls(8, 2, 12), ppc.fmuls(3, 1, 10), ppc.fmadds(3, 2, 13, 3))
    a(ppc.fmuls(11, 1, 11), fnmsubs(11, 2, 9, 11), ppc.fmuls(12, 1, 12), ppc.fmuls(13, 1, 13), fnmsubs(13, 2, 10, 13))
    a(ppc.lwz(0, D["ball_mode"], 31), ppc.cmpwi(0, 0))   # in the air: bigger when far from the camera (BALL_SEE)
    a.br("bne", "b_store")
    a(ppc.lwz(9, D["ball_at"], 31), ppc.lis(10, fb.CAMERA >> 16), ppc.lwz(10, fb.CAMERA & 0xFFFF, 10))
    for k in range(3):
        a(ppc.lfs(0, 4 * k, 9), ppc.lfs(1, 4 * k, 10), ppc.fsubs(0, 0, 1))
        a(ppc.fmuls(9, 0, 0) if k == 0 else ppc.fmadds(9, 0, 0, 9))
    a(ppc.lfs(0, D["ball_see2"], 31), ppc.fmuls(9, 9, 0), ppc.lfs(0, D["one"], 31), ppc.fcmpu(9, 0))
    a.br("ble", "b_store")
    _rsqrt(a, 10, 9, 0, 1, 2)
    a(ppc.fmuls(10, 9, 10))                             # k = distance x BALL_SEE
    for f in (4, 5, 6, 7, 8, 3, 11, 12, 13):
        a(ppc.fmuls(f, f, 10))
    a.label("b_store")
    m = D["ball_m"]
    a(ppc.lwz(9, D["ball_at"], 31))
    for k, f in enumerate((4, 7, 11)):
        a(ppc.stfs(f, m + 4 * k, 31))
    for k, f in enumerate((5, 8, 12)):
        a(ppc.stfs(f, m + 0x10 + 4 * k, 31))
    for k, f in enumerate((6, 3, 13)):
        a(ppc.stfs(f, m + 0x20 + 4 * k, 31))
    for k in range(3):
        a(ppc.lfs(0, 4 * k, 9), ppc.stfs(0, m + 0x0C + 0x10 * k, 31))
    hi, lo = ppc.hi_lo(GOLFER_DEPTH)
    a(ppc.lis(12, hi), ppc.lfs(1, lo, 12), ppc.li(4, 0), ppc.li(5, 1))
    a.la(3, "fp_ball_draw")
    _call(a, QUEUE)
    _leave(a, 0x20, 30)

    # ---- fp_ball_draw: (the draw queue's callback) the football: GX as the posts draw (football.py GX_STATE: one
    # colour channel from the material colour, position-only vertices), the frame after the camera, the bands' quads
    a.label("fp_ball_draw")
    _enter(a, 0x30, 26)
    _li32(a, 31, L["data"])
    for fn, args in fb.GX_STATE:
        for k, v in enumerate(args):
            if v > 0x7FFF:
                _li32(a, 3 + k, v)
            else:
                a(ppc.li(3 + k, v))
        _call(a, fb.GX[fn])
    a(ppc.lis(3, fb.CAMERA >> 16), ppc.lwz(3, fb.CAMERA & 0xFFFF, 3), ppc.addi(3, 3, 0x3C), ppc.addi(4, 31, D["ball_m"]),
      ppc.li(5, 0))
    _call(a, fb.LOAD_MODELVIEW)
    _li32(a, 28, L["ball_mesh"])
    a(ppc.li(27, 0))
    a.label("bd_band")                                  # a band: u32 colour, u32 vertices, then x y z each
    a(ppc.cmpwi(27, BALL_BANDS))
    a.br("bge", "bd_done")
    a(ppc.li(3, 4), ppc.mr(4, 28))
    _call(a, fb.GX["mat_color"])
    a(ppc.li(3, 0x80), ppc.li(4, 0), ppc.lwz(5, 4, 28))
    _call(a, fb.GX["begin"])
    a(ppc.lwz(26, 4, 28), ppc.addi(28, 28, 8), ppc.lis(9, 0xCC01))
    a.label("bd_vert")
    a(ppc.lfs(1, 0, 28), ppc.lfs(2, 4, 28), ppc.lfs(3, 8, 28), ppc.stfs(1, -0x8000, 9), ppc.stfs(2, -0x8000, 9),
      ppc.stfs(3, -0x8000, 9), ppc.addi(28, 28, 12), ppc.addi(26, 26, -1), ppc.cmpwi(26, 0))
    a.br("bne", "bd_vert")
    a(ppc.addi(27, 27, 1))
    a.br("b", "bd_band")
    a.label("bd_done")
    _leave(a, 0x30, 26)

    # ---- fp_preview: bl from PREVIEW_CALL (r3 the preview ball, r4 the team's lie, r5 the shot, r6 the mode; the aim's
    # preview flight FUN_80415790, which redoes the flight when the lie's or the shot's values change): in a pass's aim,
    # a copy of the lie "throw_h" higher, so the arrows and the star fly from the throw
    a.label("fp_preview")
    _li32(a, 12, data)
    a(ppc.lfs(0, D["throw_h"], 12), ppc.lfs(1, D["zero"], 12), ppc.fcmpu(0, 1))
    a.br("beq", "pv_go")
    for k in range(LIE_SIZE // 4):
        a(ppc.lwz(11, 4 * k, 4), ppc.stw(11, D["lie_copy"] + 4 * k, 12))
    a(ppc.lfs(1, D["lie_copy"] + 4, 12), ppc.fadds(1, 1, 0), ppc.stfs(1, D["lie_copy"] + 4, 12),
      ppc.addi(4, 12, D["lie_copy"]))
    for off, name in ((0, "throw_dx"), (8, "throw_dz")):
        a(ppc.lfs(1, D["lie_copy"] + off, 12), ppc.lfs(2, D[name], 12), ppc.fadds(1, 1, 2),
          ppc.stfs(1, D["lie_copy"] + off, 12))
    a.label("pv_go")
    a.b(PREVIEW_FLY)

    # ---- fp_club: b from CLUB_STEP (r3 the setup, r4 -1 or 1): in Football, the next shot type that way (none past
    # the ends, as the game's clubs); a replay goes straight to its recorded club (the game steps to it club by club)
    a.label("fp_club")
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0))
    a.br("beq", "cl_game")
    a(ppc.lbz(0, S_REPLAY, 3), ppc.cmpwi(0, 0))
    a.br("beq", "cl_type")
    a(ppc.lwz(11, S_REPLAY_CLUB, 3))
    a.b(CLUB_STEP_SET)
    a.label("cl_type")
    _li32(a, 10, data + D["types"])
    a(ppc.lwz(9, S_CLUB, 3), ppc.li(11, 0))
    a.label("cl_find")
    a(ppc.lbzx(0, 10, 11), ppc.cmpw(0, 9))
    a.br("beq", "cl_found")
    a(ppc.addi(11, 11, 1), ppc.cmpwi(11, len(TYPE_CLUBS)))
    a.br("blt", "cl_find")
    a(ppc.li(11, -1))                                   # not a type: the first one up
    a.label("cl_found")
    a(ppc.add(11, 11, 4), ppc.cmpwi(11, 0))
    a.br("blt", "cl_none")
    a(ppc.cmpwi(11, len(TYPE_CLUBS) - 1))
    a.br("bgt", "cl_none")
    a(ppc.lbzx(11, 10, 11))
    a.b(CLUB_STEP_SET)
    a.label("cl_none")
    a.b(CLUB_STEP_OUT)
    a.label("cl_game")
    a(CLUB_STEP[1])
    a.b(CLUB_STEP[0] + 4)

    # ---- fp_snap: bl from AIM_CLEAR (r3 = r31 the setup; r0 and r9-r12 free): the game's clear, then in Football a
    # club that isn't a shot type (the auto-aim's fallback wedge, ...) becomes the nearest pass, as a club change
    a.label("fp_snap")
    a(AIM_CLEAR[1])
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0), BEQLR, ppc.lbz(0, S_REPLAY, 3), ppc.cmpwi(0, 0), BNELR)
    a(ppc.lwz(11, S_CLUB, 3))
    for club in TYPE_CLUBS:
        a(ppc.cmpwi(11, club), BEQLR)
    near = sorted(TYPE_CLUBS[:fb.TYPE_FG])              # the passes' clubs, longest first
    a(ppc.li(12, near[-1]))
    for k in range(len(near) - 1, 0, -1):               # below the midpoint between two passes' clubs: the longer
        a(ppc.cmpwi(11, (near[k - 1] + near[k] + 1) // 2))
        a.br("bge", "sn_set")
        a(ppc.li(12, near[k - 1]))
    a.label("sn_set")
    a(ppc.stw(12, S_CLUB, 3), ppc.li(0, 1), ppc.stb(0, S_CHANGED, 3), BLR)

    # ---- fp_angle: bl from ANGLE_STORE (f1 the launch angle by power and club, r29 the club, r31 the shot; r3 and
    # f1's store kept): in Football x the shot type's angle factor (the speed is searched for after, for the carry)
    a.label("fp_angle")
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0))
    a.br("beq", "an_store")
    a(ppc.cmplwi(29, 13))
    a.br("bgt", "an_store")
    _li32(a, 12, data + D["angle_k"])
    a(ppc.slwi(11, 29, 2), lfsx(0, 12, 11), ppc.fmuls(1, 1, 0))
    a.label("an_store")
    a(ANGLE_STORE[1], BLR)

    # ---- fp_spin: bl from SPIN_STORE (f11 the backspin): in Football x the shot type's spin factor
    a.label("fp_spin")
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0))
    a.br("beq", "sp_store")
    a(ppc.cmplwi(29, 12))
    a.br("bgt", "sp_store")
    _li32(a, 12, data + D["spin_k"])
    a(ppc.slwi(11, 29, 2), lfsx(0, 12, 11), ppc.fmuls(11, 11, 0))
    a.label("sp_store")
    _li32(a, 12, data)
    a(ppc.stfs(11, D["s0"], 12), SPIN_STORE[1], BLR)

    # ---- fp_angle0: bl from ANGLE_FINAL: the angle the launch speed is searched with, kept for fp_bend
    a.label("fp_angle0")
    _li32(a, 12, data)
    a(ppc.stfs(13, D["a0"], 12), ANGLE_FINAL[1], BLR)

    # ---- fp_bend: bl from BEND_END: in Football the timing miss's change to the angle and the backspin x the shot
    # type's factors, so a flat, low-spin throw (the Bullet) gets the same share of it as the game's clubs (its fixed
    # degrees and the backspin it adds by speed would otherwise more than double the Bullet's angle and lift)
    a.label("fp_bend")
    a(ppc.stwu(1, -0x30, 1), ppc.stw(11, 0x08, 1), ppc.stw(12, 0x0C, 1), stfd(0, 0x10, 1), stfd(12, 0x18, 1),
      stfd(13, 0x20, 1))
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0))
    a.br("beq", "bd2_out")
    a(ppc.lwz(12, P_SETUP, 30), ppc.lwz(11, S_CLUB, 12), ppc.cmplwi(11, 12))
    a.br("bgt", "bd2_out")
    _li32(a, 12, data)
    a(ppc.slwi(11, 11, 2), ppc.addi(11, 11, D["angle_k"]))
    for field, kept, step in ((0x44, "a0", D["spin_k"] - D["angle_k"]), (0x50, "s0", 0)):
        a(lfsx(0, 12, 11), ppc.lfs(13, field, 31), ppc.lfs(12, D[kept], 12), ppc.fsubs(13, 13, 12),
          ppc.fmadds(13, 13, 0, 12), ppc.stfs(13, field, 31), ppc.addi(11, 11, step))   # kept + change x factor
    a.label("bd2_out")
    a(ppc.lwz(11, 0x08, 1), ppc.lwz(12, 0x0C, 1), lfd(0, 0x10, 1), lfd(12, 0x18, 1), lfd(13, 0x20, 1),
      ppc.addi(1, 1, 0x30), BEND_END[1], BLR)

    # ---- fp_spinfly: bl from football.py's fb_frame every update of a play in the air (r28 = the setup, r29 = the
    # ball, r31 = football's state; r0, r3-r12 and f0-f13 only): a manual swing's spin combo (setup +0x1C8) in
    # Football. Once the ball falls, SPIN_DV[combo] x GRAVITY goes on its y velocity each frame: topspin dips (lands
    # sooner and shorter), backspin floats (hangs, carries farther). The game's own spin only changes the roll after
    # landing, which a play never sees; the aim's preview has no spin, so the star doesn't show it.
    a.label("fp_spinfly")
    a(ppc.lwz(0, fb.S["phase"], 31), ppc.cmpwi(0, fb.PH_FLY), BNELR, ppc.lwz(3, S_SPIN, 28), ppc.addi(3, 3, -1),
      ppc.cmplwi(3, 3), fb.BGTLR, ppc.lfs(1, B_VEL + 4, 29))
    _li32(a, 12, data)
    a(ppc.lfs(0, D["zero"], 12), ppc.fcmpu(1, 0), fb.BGELR, ppc.slwi(3, 3, 2), ppc.addi(3, 3, D["spin_dv"]),
      lfsx(0, 12, 3), ppc.fadds(1, 1, 0), ppc.stfs(1, B_VEL + 4, 29), BLR)

    # ---- fp_palm: (r3 = a golfer's model instance, r4 = its rig, r5 = its world matrix (3x4); r31 = our data) the
    # football's place in its right hand, "bp": the hand bone (at the wrist) on along the forearm by "hand_in" of the
    # forearm's length, into the palm (Andrew: "the ball isnt really in their hands when throwing": it sat on the
    # wrist); mirrored for a lefty (instance +0x34 = 1). r3 = 0 when the rig has no hand. Uses r10-r12, f0-f7.
    a.label("fp_palm")
    a(ppc.lbz(11, J_INDEX["hand_r"], 4), ppc.cmpwi(11, 0xFF))
    a.br("beq", "pm_none")
    a(ppc.lwz(10, 0x14, 3), ppc.mulli(11, 11, 0x60), ppc.add(11, 11, 10), ppc.lfs(1, 0x0C, 11), ppc.lfs(2, 0x1C, 11),
      ppc.lfs(3, 0x2C, 11), ppc.lbz(12, J_INDEX["farm_r"], 4), ppc.cmpwi(12, 0xFF))
    a.br("beq", "pm_mirror")
    a(ppc.mulli(12, 12, 0x60), ppc.add(12, 12, 10), ppc.lfs(0, D["hand_in"], 31))
    for f, off in ((1, 0x0C), (2, 0x1C), (3, 0x2C)):
        a(ppc.lfs(4, off, 12), ppc.fsubs(4, f, 4), ppc.fmadds(f, 4, 0, f))   # hand + (hand - forearm) x hand_in
    a.label("pm_mirror")
    a(lha(0, 0x34, 3), ppc.cmpwi(0, 1))
    a.br("bne", "pm_world")
    a(ppc.fneg(1, 1))
    a.label("pm_world")
    for k in range(3):                                  # world = matrix (3x4) x (x, y, z, 1)
        a(ppc.lfs(4, 0x10 * k, 5), ppc.lfs(5, 0x10 * k + 4, 5), ppc.lfs(6, 0x10 * k + 8, 5),
          ppc.lfs(7, 0x10 * k + 0xC, 5), ppc.fmadds(7, 4, 1, 7), ppc.fmadds(7, 5, 2, 7), ppc.fmadds(7, 6, 3, 7),
          ppc.stfs(7, D["bp"] + 4 * k, 31))
    a(ppc.li(3, 1), BLR)
    a.label("pm_none")
    a(ppc.li(3, 0), BLR)

    # ---- fp_slots: (r31 = our data) who receives: the QB's team-mates (the players whose number less the QB's is a
    # multiple of the side count: one team of 2-4, everyone else; 2v2, the partner), from the one after the QB on, into
    # the slots; the slots left over empty
    a.label("fp_slots")
    a(ppc.lis(12, 0x804E), ppc.lbz(3, D17 & 0xFFFF, 12), ppc.lbz(4, D15 & 0xFFFF, 12), ppc.lbz(5, D16 & 0xFFFF, 12),
      ppc.li(6, 0), ppc.li(0, 0), ppc.stw(0, D["lead"], 31), ppc.cmpwi(4, 1))
    a.br("bge", "sl_next")
    a(ppc.li(4, 1))
    a.label("sl_next")                                  # r6 = p, each player's slot
    a(ppc.mulli(9, 6, RSIZE), ppc.addi(9, 9, D["rcv"]), ppc.add(9, 9, 31), ppc.li(0, 0), ppc.cmpw(6, 5))
    a.br("bge", "sl_set")                               # (no such player)
    a(ppc.subf(8, 3, 6), ppc.cmpwi(8, 0))               # d = (p - QB) mod count; 0 is the QB
    a.br("beq", "sl_set")
    a.br("bgt", "sl_d")
    a(ppc.add(8, 8, 5))
    a.label("sl_d")
    a(ppc.divw(10, 8, 4), ppc.mullw(11, 10, 4), ppc.cmpw(11, 8))
    a.br("bne", "sl_set")                               # another side's
    a(ppc.addi(10, 10, -1), ppc.stw(10, R["rank"], 9), ppc.cmpwi(10, 0))   # rank = d / sides - 1: 0 on the star
    a.br("bne", "sl_who")
    a(ppc.stw(9, D["lead"], 31))
    a.label("sl_who")
    _li32(a, 10, PLAYERS)
    a(ppc.mulli(0, 6, PLAYER_SIZE), ppc.add(0, 10, 0))
    a.label("sl_set")
    a(ppc.stw(0, R["player"], 9), ppc.addi(6, 6, 1), ppc.cmpwi(6, N_RCV))
    a.br("blt", "sl_next")
    a(BLR)

    # ---- fp_ground: (f1 x, f2 y, f3 z; r31 = our data) f2 = the ground's height under (x, z) (y when the query finds
    # nothing near); f1, f3 kept
    a.label("fp_ground")
    a(ppc.stwu(1, -0x20, 1), ppc.mflr(0), ppc.stw(0, 0x24, 1), ppc.stfs(1, 0x08, 1), ppc.stfs(2, 0x0C, 1),
      ppc.stfs(3, 0x10, 1), ppc.addi(3, 31, D["gq"]))
    _call(a, GROUND_Q)
    a(ppc.lfs(1, 0x08, 1), ppc.lfs(3, 0x10, 1), ppc.lfs(2, D["gq"] + 4, 31), ppc.lfs(0, 0x0C, 1),
      ppc.lfs(4, D["gq_max"], 31), ppc.fadds(4, 0, 4), ppc.fcmpu(2, 4))
    a.br("blt", "gq_ok")
    a(ppc.fmr(2, 0))
    a.label("gq_ok")
    a(ppc.lwz(0, 0x24, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x20), BLR)

    # ---- fp_rcv: (r3 = a receiver slot, r4 = its number; r30 = the QB, r24 = football's state, r31 = our data) a
    # receiver: its model in the slot's holders (or let go), then where it is and how it moves, its pose and its draw
    a.label("fp_rcv")
    _enter(a, 0x40, 21)
    a(ppc.mr(23, 3), ppc.mr(22, 4), ppc.lwz(21, R["rank"], 3), ppc.lwz(29, R["player"], 23), ppc.cmpwi(29, 0))
    a.br("bne", "rv_on")
    a(ppc.mr(3, 23))
    a.br("bl", "fp_release")
    a.br("b", "rv_out")
    a.label("rv_on")
    a(ppc.lwz(3, P_OBJ, 29), ppc.lwz(9, 0, 3), ppc.lwz(12, M_MODEL_ID, 9), ppc.mtctr(12), BCTRL)
    a(ppc.mr(26, 3), ppc.lwz(0, R["model_id"], 23), ppc.cmpw(0, 26))
    a.br("beq", "rv_same")
    a(ppc.mr(3, 23))
    a.br("bl", "fp_release")                            # another golfer's (or none): free them, then load
    a(ppc.cmpwi(3, 0))
    a.br("beq", "rv_out")
    # one load at a time (a load takes its memory a few frames on, and the heaps' free counts must show it before the
    # next is placed), into whichever of RCV_HEAPS has the most free, if that's the golfer's size (RCV_SIZES) with room
    # to spare (three golfers don't fit the main heap: the third stalled loading)
    for k in range(N_RCV):
        for name in ("mh", "bh"):
            a(ppc.lwz(0, D["rcv"] + RSIZE * k + R[name] + 4, 31), ppc.cmpwi(0, 1))
            a.br("beq", "rv_out")
    a(ppc.lbz(9, P_CODE, 29), ppc.cmplwi(9, len(RCV_SIZES) - 1))
    a.br("ble", "rv_size")
    a(ppc.li(9, len(RCV_SIZES) - 1))                     # (past the table: its last entry, the largest)
    a.label("rv_size")
    a(ppc.slwi(9, 9, 2), ppc.addi(9, 9, D["need"]), ppc.lwzx(10, 31, 9), ppc.li(5, -1), ppc.li(6, 0))
    for h in RCV_HEAPS:
        hi, lo = ppc.hi_lo(HEAPS + 0x14 * h + 4)
        a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), cmplw(0, 10))
        a.br("blt", f"rv_heap{h}")
        a(cmplw(0, 6))
        a.br("ble", f"rv_heap{h}")
        a(ppc.mr(6, 0), ppc.li(5, h))
        a.label(f"rv_heap{h}")
    a(ppc.cmpwi(5, 0))
    a.br("blt", "rv_out")                               # (no room anywhere: not drawn this frame)
    a.label("rv_load")
    a(ppc.mr(3, 23), ppc.mr(4, 26))
    a.br("bl", "fp_load")
    a.br("b", "rv_out")
    a.label("rv_same")
    a(ppc.addi(28, 23, R["mh"]), ppc.mr(3, 28))
    _call(a, INSTANCE)
    a(ppc.mr(27, 3), ppc.cmpwi(3, 0))                   # r27 = its instance (0 while loading)
    a.br("beq", "rv_out")
    # the motion (r25 = the clip, "t" its time) and where it faces
    a(ppc.li(25, CLIP["ready"]), ppc.lfs(0, D["zero"], 31), ppc.stfs(0, R["t"], 23))
    a(ppc.lwz(0, fb.S["kind"], 24), ppc.cmpwi(0, fb.KIND_PASS))
    a.br("bne", "rv_aim")
    a(ppc.lwz(0, D["rcv_live"], 31), ppc.cmpwi(0, 0))   # (the play's first update still to come: where it stood)
    a.br("beq", "rv_placed")
    a(ppc.lfs(1, R["x"], 23), ppc.lfs(2, R["y"], 23), ppc.lfs(0, R["jump_h"], 23), ppc.fadds(2, 2, 0),
      ppc.lfs(3, R["z"], 23))
    a(ppc.lwz(0, fb.S["phase"], 24), ppc.cmpwi(0, fb.PH_HOLD))
    a.br("bne", "rv_not_held")
    a(ppc.lwz(0, D["catcher"], 31), ppc.cmpw(0, 22))
    a.br("bne", "rv_face_ball")                         # the others stand by
    a(ppc.li(25, CLIP["hold"]))
    a.br("b", "rv_face_ball")
    a.label("rv_not_held")
    a(ppc.cmpwi(0, fb.PH_FLY))
    a.br("bne", "rv_face_ball")
    a(ppc.lfs(8, R["dive_t"], 23), ppc.lfs(0, D["zero"], 31), ppc.fcmpu(8, 0))
    a.br("ble", "rv_no_dive")
    a(ppc.lfs(4, R["dive_x"], 23), ppc.lfs(5, R["dive_z"], 23), ppc.lfs(6, D["one"], 31),
      ppc.li(25, CLIP["down"]), ppc.lfs(0, D["down_frames"], 31), ppc.fcmpu(8, 0))
    a.br("ble", "rv_dir")
    a(ppc.li(25, CLIP["dive"]), ppc.fsubs(8, 8, 0), ppc.lfs(0, D["inv_dive"], 31), ppc.fmuls(8, 8, 0),
      ppc.lfs(0, D["one"], 31), ppc.fsubs(8, 0, 8), ppc.stfs(8, R["t"], 23))
    a.br("b", "rv_dir")
    a.label("rv_no_dive")
    a(ppc.lfs(8, R["jump_t"], 23), ppc.fcmpu(8, 0))
    a.br("ble", "rv_no_jump")
    a(ppc.li(25, CLIP["jump"]), ppc.lfs(0, D["inv_jump"], 31), ppc.fmuls(8, 8, 0), ppc.lfs(0, D["one"], 31),
      ppc.fsubs(8, 0, 8), ppc.stfs(8, R["t"], 23))
    a.label("rv_no_jump")
    a(ppc.lfs(4, R["vx"], 23), ppc.lfs(5, R["vz"], 23), ppc.fmuls(6, 4, 4), ppc.fmadds(6, 5, 5, 6),
      ppc.lfs(0, D["run_speed2"], 31), ppc.fcmpu(6, 0))
    a.br("ble", "rv_still")
    a(ppc.cmpwi(25, CLIP["ready"]))                      # running (unless in the air)
    a.br("bne", "rv_dir")
    a(ppc.li(25, CLIP["run"]))
    a.br("b", "rv_dir")
    a.label("rv_still")                                 # standing: hands up for a ball coming near
    a(ppc.cmpwi(25, CLIP["ready"]))
    a.br("bne", "rv_face_ball")
    a(ppc.lwz(9, P_BALL, 30), ppc.lfs(4, B_POS, 9), ppc.fsubs(4, 4, 1), ppc.lfs(5, B_POS + 8, 9), ppc.fsubs(5, 5, 3),
      ppc.fmuls(6, 4, 4), ppc.fmadds(6, 5, 5, 6), ppc.lfs(0, D["catch_d2"], 31), ppc.fcmpu(6, 0))
    a.br("bge", "rv_face_ball")
    a(ppc.li(25, CLIP["catch"]), ppc.lfs(0, D["inv_catch_d2"], 31), ppc.fmuls(7, 6, 0), ppc.lfs(0, D["one"], 31),
      ppc.fsubs(7, 0, 7), ppc.stfs(7, R["t"], 23))
    a.br("b", "rv_face_ball")
    # aiming (or a kick picked): rank 0 on the landing star, 1 and 2 "spread" feet to its left and right
    a.label("rv_aim")
    a(ppc.lwz(9, P_SETUP, 30), ppc.lfs(1, S_TARGET, 9), ppc.lfs(2, S_TARGET + 4, 9), ppc.lfs(3, S_TARGET + 8, 9))
    a(ppc.lwz(9, P_BALL, 30), ppc.lfs(4, B_POS, 9), ppc.lfs(5, B_POS + 8, 9), ppc.fsubs(4, 1, 4), ppc.fsubs(5, 3, 5),
      ppc.fmuls(6, 4, 4), ppc.fmadds(6, 5, 5, 6), ppc.lfs(0, D["tiny"], 31), ppc.fcmpu(6, 0))
    a.br("ble", "rv_stand")
    _rsqrt(a, 7, 6, 8, 9, 10)
    a(ppc.fmuls(4, 4, 7), ppc.fmuls(5, 5, 7))           # (f4, f5) = the throw's way
    a(ppc.cmpwi(21, 0))
    a.br("bne", "rv_side")
    a(ppc.lfs(7, D["dbg_near"], 31), ppc.lfs(0, D["zero"], 31), ppc.fcmpu(7, 0))
    a.br("ble", "rv_stand")                             # (tests: "dbg_near" feet from the QB's ball toward the aim)
    a(ppc.lwz(9, P_BALL, 30), ppc.lfs(1, B_POS, 9), ppc.lfs(2, B_POS + 4, 9), ppc.lfs(3, B_POS + 8, 9),
      ppc.fmadds(1, 4, 7, 1), ppc.fmadds(3, 5, 7, 3))
    a.br("b", "rv_stand")
    a.label("rv_side")
    a(ppc.lfs(0, D["spread"], 31), ppc.cmpwi(21, 1))
    a.br("bne", "rv_right")
    a(ppc.fneg(0, 0))
    a.label("rv_right")
    a(fnmsubs(1, 5, 0, 1), ppc.fmadds(3, 4, 0, 3))      # across the throw: x - dz s, z + dx s
    a.br("bl", "fp_ground")
    a.label("rv_stand")
    a(ppc.stfs(1, R["x"], 23), ppc.stfs(2, R["y"], 23), ppc.stfs(3, R["z"], 23))
    a.label("rv_placed")
    a(ppc.lfs(1, R["x"], 23), ppc.lfs(2, R["y"], 23), ppc.lfs(3, R["z"], 23))
    a.label("rv_face_ball")
    a(ppc.lwz(9, P_BALL, 30), ppc.lfs(4, B_POS, 9), ppc.fsubs(4, 4, 1), ppc.lfs(5, B_POS + 8, 9), ppc.fsubs(5, 5, 3),
      ppc.fmuls(6, 4, 4), ppc.fmadds(6, 5, 5, 6), ppc.lfs(0, D["tiny"], 31), ppc.fcmpu(6, 0))
    a.br("bgt", "rv_dir")
    a(ppc.lfs(4, D["zero"], 31), ppc.lfs(5, D["one"], 31), ppc.fmr(6, 5))
    a.label("rv_dir")                                   # (f4, f5) /= sqrt(f6)
    _rsqrt(a, 7, 6, 8, 9, 10)
    a(ppc.fmuls(4, 4, 7), ppc.fmuls(5, 5, 7))
    a(ppc.stfs(1, R["px"], 23), ppc.stfs(2, R["py"], 23), ppc.stfs(3, R["pz"], 23), ppc.stfs(4, R["dx"], 23),
      ppc.stfs(5, R["dz"], 23))
    a(ppc.lwz(9, P_OBJ, 29), ppc.lfs(0, OBJ_SCALE, 9), ppc.stfs(0, R["scale"], 23))
    a(ppc.lbz(26, P_CODE, 29), ppc.cmplwi(26, N_RIGS - 1))   # r26 = the golfer code (no rig: Mario's)
    a.br("ble", "rv_code")
    a(ppc.li(26, 0))
    a.label("rv_code")
    a(ppc.mulli(9, 26, RIG_SIZE))
    _li32(a, 10, L["rigs"])
    a(ppc.add(9, 9, 10), ppc.lfs(1, RIG_HIPS, 9), ppc.stfs(1, R["hips"], 23))
    a(ppc.cmpwi(25, CLIP["run"]))                        # the run's phase: on by distance, a cycle each
    a.br("bne", "rv_pose")                               # RUN_CYCLE hips heights
    a(ppc.lfs(4, R["vx"], 23), ppc.lfs(5, R["vz"], 23), ppc.fmuls(6, 4, 4), ppc.fmadds(6, 5, 5, 6))
    _rsqrt(a, 7, 6, 8, 9, 10)
    a(ppc.fmuls(6, 6, 7), ppc.lfs(0, R["scale"], 23), ppc.fmuls(1, 1, 0), ppc.lfs(0, D["run_cycle"], 31),
      ppc.fmuls(1, 1, 0), ppc.fdivs(6, 6, 1), ppc.lfs(0, R["phase"], 23), ppc.fadds(0, 0, 6),
      ppc.lfs(1, D["one"], 31), ppc.fcmpu(0, 1))
    a.br("blt", "rv_phase")
    a(ppc.fsubs(0, 0, 1))
    a.label("rv_phase")
    a(ppc.stfs(0, R["phase"], 23), ppc.stfs(0, R["t"], 23))
    a.label("rv_pose")
    a(ppc.cmpwi(21, 0))                                 # (tests: receiver 0 takes a forced clip, "dbg_clip", its time
    a.br("bne", "rv_pose2")                             # running at "dbg_speed")
    a(ppc.lwz(0, D["dbg_clip"], 31), ppc.cmpwi(0, 0))
    a.br("blt", "rv_pose2")
    a(ppc.mr(25, 0), ppc.lfs(1, D["dbg_t"], 31), ppc.stfs(1, R["t"], 23), ppc.lfs(0, D["dbg_speed"], 31),
      ppc.fadds(1, 1, 0), ppc.lfs(0, D["one"], 31), ppc.fcmpu(1, 0))
    a.br("ble", "rv_dbg_t")
    a(ppc.fsubs(1, 1, 0))
    a.label("rv_dbg_t")
    a(ppc.stfs(1, D["dbg_t"], 31))
    a.label("rv_pose2")
    a(ppc.mr(3, 28))                                    # its skinned vertices' other buffer this frame
    _call(a, HOLDER_FLIP)
    a(ppc.mr(3, 27), ppc.mr(4, 26), ppc.mr(5, 25), ppc.lfs(1, R["t"], 23))
    a.br("bl", "fp_pose")
    # the world matrix: T(place) RotY(+Z to (dx, dz)) RotX(pitch) S(scale), pitched about the hips and dropped
    r = R["rec"]
    a(ppc.lfs(0, R["scale"], 23), ppc.lfs(4, R["dx"], 23), ppc.lfs(5, R["dz"], 23), ppc.lfs(6, D["pc"], 31),
      ppc.lfs(7, D["ps"], 31))
    a(ppc.fmuls(10, 4, 0), ppc.fmuls(11, 5, 0), ppc.fmuls(12, 6, 0), ppc.fmuls(13, 7, 0))   # dx s, dz s, c s, sn s
    a(ppc.stfs(11, r + 0x00, 23), ppc.fmuls(1, 10, 7), ppc.stfs(1, r + 0x04, 23), ppc.fmuls(1, 10, 6),
      ppc.stfs(1, r + 0x08, 23))
    a(ppc.lfs(1, D["zero"], 31), ppc.stfs(1, r + 0x10, 23), ppc.stfs(12, r + 0x14, 23), ppc.fneg(1, 13),
      ppc.stfs(1, r + 0x18, 23))
    a(ppc.fneg(1, 10), ppc.stfs(1, r + 0x20, 23), ppc.fmuls(1, 11, 7), ppc.stfs(1, r + 0x24, 23),
      ppc.fmuls(1, 11, 6), ppc.stfs(1, r + 0x28, 23))
    a(ppc.lfs(8, R["hips"], 23), ppc.fmuls(9, 8, 7))                                       # h sn
    a(ppc.lfs(1, R["px"], 23), fnmsubs(1, 10, 9, 1), ppc.stfs(1, r + 0x0C, 23))            # x - dx s h sn
    a(ppc.lfs(1, R["pz"], 23), fnmsubs(1, 11, 9, 1), ppc.stfs(1, r + 0x2C, 23))            # z - dz s h sn
    a(ppc.lfs(1, D["one"], 31), ppc.lfs(2, D["drop"], 31), ppc.fsubs(1, 1, 2), ppc.fsubs(1, 1, 6),
      ppc.fmuls(1, 1, 8), ppc.fmuls(1, 1, 0), ppc.lfs(2, R["py"], 23), ppc.fadds(1, 2, 1),
      ppc.stfs(1, r + 0x1C, 23))                                                           # y + s h (1 - drop - c)
    a(ppc.cmpwi(21, 0))                                 # (tests: the football in receiver 0's right hand, this frame's
    a.br("bne", "rv_queue")                             # pose: MODEL_DRAW turns the bones into skin matrices once drawn)
    a(ppc.lwz(0, D["dbg_ball"], 31), ppc.cmpwi(0, 2))
    a.br("bne", "rv_queue")
    a(ppc.mulli(4, 26, RIG_SIZE))
    _li32(a, 10, L["rigs"])
    a(ppc.add(4, 4, 10), ppc.mr(3, 27), ppc.addi(5, 23, r))
    a.br("bl", "fp_palm")
    a(ppc.lfs(4, R["dx"], 23), ppc.stfs(4, D["bv"], 31), ppc.lfs(4, D["half"], 31), ppc.stfs(4, D["bv"] + 4, 31),
      ppc.lfs(4, R["dz"], 23), ppc.stfs(4, D["bv"] + 8, 31), ppc.li(0, 1), ppc.stw(0, D["ball_mode"], 31))
    a.br("bl", "fp_ball")
    a.label("rv_queue")
    a(ppc.lbz(5, P_CODE, 29), ppc.stw(5, r + 0x30, 23), ppc.stw(28, r + 0x34, 23), ppc.li(0, 0),
      ppc.stb(0, r + 0x38, 23))
    a(ppc.cmpwi(5, 6), ppc.li(5, 1))
    a.br("bne", "rv_layer")
    a(ppc.li(5, 3))
    a.label("rv_layer")
    hi, lo = ppc.hi_lo(GOLFER_DEPTH)
    a(ppc.lis(12, hi), ppc.lfs(1, lo, 12), ppc.addi(4, 23, r))
    _li32(a, 3, GOLFER_DRAW)
    _call(a, QUEUE)
    a.label("rv_out")
    _leave(a, 0x40, 21)

    # ---- fp_recv_update: bl from football.py's fb_frame every update of a pass in the air (r28 = the setup, r29 =
    # the ball, r30 = the QB, r31 = football's state): every receiver runs, jumps and dives on its own pad, bumps off
    # the others, and the first with the ball in reach catches it
    a.label("fp_recv_update")
    _enter(a, 0x40, 21)
    a(ppc.mr(24, 31), ppc.mr(21, 29))                    # r24 = football's state, r21 = the ball
    _li32(a, 31, data)
    a(ppc.lwz(0, D["rcv_live"], 31), ppc.cmpwi(0, 0))
    a.br("bne", "ru_live")
    a(ppc.li(0, 1), ppc.stw(0, D["rcv_live"], 31), ppc.li(0, -1), ppc.stw(0, D["catcher"], 31), ppc.li(0, 0),
      ppc.stw(0, D["pred_n"], 31), ppc.lfs(0, D["zero"], 31))
    for k in range(N_RCV):
        for name in ("vx", "vz", "jump_t", "dive_t", "jump_h"):
            a(ppc.stfs(0, D["rcv"] + RSIZE * k + R[name], 31))
    a.label("ru_live")
    a(ppc.lwz(0, fb.S["phase"], 24), ppc.cmpwi(0, fb.PH_FLY))
    a.br("bne", "ru_out")
    for k in range(N_RCV):
        a(ppc.addi(23, 31, D["rcv"] + RSIZE * k))
        a.br("bl", "fp_run1")
    a.br("bl", "fp_bump")
    for k in range(N_RCV):
        a(ppc.addi(23, 31, D["rcv"] + RSIZE * k), ppc.li(22, k))
        a.br("bl", "fp_catch1")
    a.label("ru_out")
    _leave(a, 0x40, 21)

    # ---- fp_run1: (r23 = a receiver slot; r21 = the ball, r24 = football's state, r31 = our data) its own pad moves
    # it: the main stick, plus the analog triggers for up and down (the mod's controls put the left stick's up and down
    # there, so before v28 a real controller only ran sideways), camera-relative (up = toward the throw); A jumps, B
    # dives (along the stick, or at the ball); on the ground
    a.label("fp_run1")
    a(ppc.lwz(9, R["player"], 23), ppc.cmpwi(9, 0), BEQLR)
    a(ppc.stwu(1, -0x20, 1), ppc.mflr(0), ppc.stw(0, 0x24, 1))
    a(ppc.lwz(6, fb.P_PAD, 9), ppc.lhz(0, fb.PAD_PRESSED, 6), ppc.stw(0, 0x08, 1))
    a(ppc.lis(0, 0x4330), ppc.stw(0, 0x10, 1), lfd(0, D["magic"], 31))
    for off, f in ((fb.PAD_STICK_X, 7), (fb.PAD_STICK_Y, 8)):    # s8 -> float, the usual 0x43300000 way
        a(ppc.lbz(7, off, 6), ppc.extsb(7, 7), ppc.xoris(7, 7, 0x8000), ppc.stw(7, 0x14, 1), lfd(f, 0x10, 1),
          fsub(f, f, 0), ppc.frsp(f, f))
    a(ppc.lfs(0, fb.C["stick"], 24), ppc.fmuls(7, 7, 0), ppc.fmuls(8, 8, 0))
    a(ppc.lfs(0, PAD_TRIG_L, 6), ppc.fadds(8, 8, 0), ppc.lfs(0, PAD_TRIG_R, 6), ppc.fsubs(8, 8, 0))
    a(ppc.fmuls(9, 7, 7), ppc.fmadds(9, 8, 8, 9), ppc.lfs(0, fb.C["dead2"], 24), ppc.fcmpu(9, 0))
    a.br("bge", "r1_live")
    a(ppc.lfs(7, D["zero"], 31), ppc.fmr(8, 7))
    a.br("b", "r1_dir")
    a.label("r1_live")
    a(ppc.lfs(0, D["one"], 31), ppc.fcmpu(9, 0))
    a.br("ble", "r1_dir")
    _rsqrt(a, 10, 9, 11, 12, 13)
    a(ppc.fmuls(7, 7, 10), ppc.fmuls(8, 8, 10))
    a.label("r1_dir")                       # wanted velocity (f6, f7) = (right x sx + forward x sy) x run
    a(ppc.fmr(1, 7), ppc.fmr(2, 8), ppc.lfs(4, fb.S["fx"], 24), ppc.lfs(5, fb.S["fz"], 24))
    a(ppc.fmuls(6, 4, 2), ppc.fmuls(7, 5, 1), ppc.fsubs(6, 6, 7))
    a(ppc.fmuls(7, 4, 1), ppc.fmuls(8, 5, 2), ppc.fadds(7, 7, 8))
    a(ppc.lfs(0, fb.C["run"], 24), ppc.fmuls(6, 6, 0), ppc.fmuls(7, 7, 0))
    a(ppc.lfs(8, R["dive_t"], 23), ppc.lfs(0, D["zero"], 31), ppc.fcmpu(8, 0))   # a dive: on along it, then down
    a.br("ble", "r1_no_dive")
    a(ppc.lfs(0, D["one"], 31), ppc.fsubs(8, 8, 0), ppc.stfs(8, R["dive_t"], 23), ppc.lfs(0, fb.C["down_frames"], 24),
      ppc.fcmpu(8, 0))
    a.br("blt", "r1_down")
    a(ppc.lfs(0, fb.C["dive_speed"], 24), ppc.lfs(6, R["dive_x"], 23), ppc.lfs(7, R["dive_z"], 23),
      ppc.fmuls(6, 6, 0), ppc.fmuls(7, 7, 0))
    a.br("b", "r1_set")
    a.label("r1_down")
    a(ppc.lfs(6, D["zero"], 31), ppc.fmr(7, 6))
    a.br("b", "r1_set")
    a.label("r1_no_dive")
    a(ppc.lwz(9, 0x08, 1), ppc.lfs(8, R["jump_t"], 23), ppc.lfs(0, D["zero"], 31), ppc.fcmpu(8, 0))
    a.br("bgt", "r1_glide")                 # in the air: no new jump or dive
    a(ppc.andi_(0, 9, fb.PAD_B))
    a.br("beq", "r1_no_b")
    a(ppc.fmr(1, 6), ppc.fmr(2, 7), ppc.fmuls(9, 6, 6), ppc.fmadds(9, 7, 7, 9), ppc.lfs(0, D["tiny"], 31),
      ppc.fcmpu(9, 0))
    a.br("bgt", "r1_dive_dir")
    a(ppc.lfs(1, B_POS, 21), ppc.lfs(0, R["x"], 23), ppc.fsubs(1, 1, 0), ppc.lfs(2, B_POS + 8, 21),
      ppc.lfs(0, R["z"], 23), ppc.fsubs(2, 2, 0), ppc.fmuls(9, 1, 1), ppc.fmadds(9, 2, 2, 9),
      ppc.lfs(0, D["tiny"], 31), ppc.fcmpu(9, 0))
    a.br("ble", "r1_glide")                 # (the ball right overhead: no dive)
    a.label("r1_dive_dir")
    _rsqrt(a, 10, 9, 11, 12, 13)
    a(ppc.fmuls(1, 1, 10), ppc.fmuls(2, 2, 10))
    a(ppc.stfs(1, R["dive_x"], 23), ppc.stfs(2, R["dive_z"], 23), ppc.lfs(0, fb.C["dive_total"], 24),
      ppc.stfs(0, R["dive_t"], 23), ppc.lfs(0, fb.C["dive_speed"], 24), ppc.fmuls(6, 1, 0), ppc.fmuls(7, 2, 0))
    a.br("b", "r1_set")
    a.label("r1_no_b")
    a(ppc.andi_(0, 9, fb.PAD_A))
    a.br("beq", "r1_glide")
    a(ppc.lfs(0, fb.C["jump_frames"], 24), ppc.stfs(0, R["jump_t"], 23))
    a.label("r1_glide")                     # ease toward the stick's velocity
    a(ppc.lfs(0, fb.C["accel"], 24), ppc.lfs(8, R["vx"], 23), ppc.fsubs(6, 6, 8), ppc.fmadds(6, 6, 0, 8),
      ppc.lfs(8, R["vz"], 23), ppc.fsubs(7, 7, 8), ppc.fmadds(7, 7, 0, 8))
    a.label("r1_set")                       # f6, f7 = this frame's velocity; the jump's height; the move, on the ground
    a(ppc.stfs(6, R["vx"], 23), ppc.stfs(7, R["vz"], 23))
    a(ppc.lfs(8, R["jump_t"], 23), ppc.lfs(0, D["zero"], 31), ppc.fcmpu(8, 0))
    a.br("ble", "r1_no_jump")
    a(ppc.lfs(0, D["one"], 31), ppc.fsubs(8, 8, 0), ppc.stfs(8, R["jump_t"], 23),
      ppc.lfs(9, fb.C["inv_jump_frames"], 24), ppc.fmuls(8, 8, 9), ppc.fsubs(9, 0, 8), ppc.fmuls(8, 8, 9),
      ppc.lfs(0, fb.C["jump_h4"], 24), ppc.fmuls(8, 8, 0))
    a.br("b", "r1_height")                  # 4 h t (1 - t)
    a.label("r1_no_jump")
    a(ppc.lfs(8, D["zero"], 31))
    a.label("r1_height")
    a(ppc.stfs(8, R["jump_h"], 23))
    a(ppc.lfs(1, R["x"], 23), ppc.fadds(1, 1, 6), ppc.stfs(1, R["x"], 23), ppc.lfs(3, R["z"], 23),
      ppc.fadds(3, 3, 7), ppc.stfs(3, R["z"], 23), ppc.lfs(2, R["y"], 23))
    a.br("bl", "fp_ground")
    a(ppc.stfs(2, R["y"], 23), ppc.lwz(0, 0x24, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x20), BLR)

    # ---- fp_bump: (r31 = our data) receivers closer than "bump" feet are pushed apart, half the overlap each, along
    # the line between them (Andrew: "receivers should be able to collide with each other to make it harder")
    a.label("fp_bump")
    for i in range(N_RCV):
        for j in range(i + 1, N_RCV):
            si, sj, lab = D["rcv"] + RSIZE * i, D["rcv"] + RSIZE * j, f"bp_{i}{j}"
            a(ppc.lwz(9, si + R["player"], 31), ppc.lwz(10, sj + R["player"], 31), ppc.cmpwi(9, 0))
            a.br("beq", lab)
            a(ppc.cmpwi(10, 0))
            a.br("beq", lab)
            a(ppc.lfs(1, sj + R["x"], 31), ppc.lfs(2, si + R["x"], 31), ppc.fsubs(1, 1, 2),
              ppc.lfs(3, sj + R["z"], 31), ppc.lfs(4, si + R["z"], 31), ppc.fsubs(3, 3, 4),
              ppc.fmuls(5, 1, 1), ppc.fmadds(5, 3, 3, 5), ppc.lfs(0, D["bump2"], 31), ppc.fcmpu(5, 0))
            a.br("bge", lab)
            a(ppc.lfs(0, D["tiny"], 31), ppc.fcmpu(5, 0))
            a.br("bgt", lab + "_d")
            a(ppc.lfs(1, D["one"], 31), ppc.lfs(3, D["zero"], 31), ppc.fmr(5, 1))   # on top of each other: along x
            a.label(lab + "_d")
            _rsqrt(a, 6, 5, 7, 8, 9)
            a(ppc.fmuls(1, 1, 6), ppc.fmuls(3, 3, 6), ppc.fmuls(5, 5, 6))      # the unit (f1, f3), the distance f5
            a(ppc.lfs(0, D["bump"], 31), ppc.fsubs(0, 0, 5), ppc.lfs(7, D["half"], 31), ppc.fmuls(0, 0, 7))
            a(ppc.lfs(7, sj + R["x"], 31), ppc.fmadds(7, 1, 0, 7), ppc.stfs(7, sj + R["x"], 31),
              ppc.lfs(7, sj + R["z"], 31), ppc.fmadds(7, 3, 0, 7), ppc.stfs(7, sj + R["z"], 31),
              ppc.lfs(7, si + R["x"], 31), fnmsubs(7, 1, 0, 7), ppc.stfs(7, si + R["x"], 31),
              ppc.lfs(7, si + R["z"], 31), fnmsubs(7, 3, 0, 7), ppc.stfs(7, si + R["z"], 31))
            a.label(lab)
    a(BLR)

    # ---- fp_catch1: (r23 = a receiver slot, r22 = its number; r21 = the ball, r24 = football's state, r31 = our data)
    # the ball in its catch zone (football.py's sizes: a dive reaches farther but lower, down after one none): caught,
    # held there
    a.label("fp_catch1")
    a(ppc.lwz(9, R["player"], 23), ppc.cmpwi(9, 0), BEQLR, ppc.lwz(0, fb.S["phase"], 24), ppc.cmpwi(0, fb.PH_FLY),
      BNELR)
    a(ppc.lfs(1, B_POS, 21), ppc.lfs(2, B_POS + 4, 21), ppc.lfs(3, B_POS + 8, 21))
    a(ppc.lfs(4, R["x"], 23), ppc.lfs(5, R["y"], 23), ppc.lfs(6, R["z"], 23))
    a(ppc.fsubs(7, 1, 4), ppc.fsubs(8, 3, 6), ppc.fmuls(9, 7, 7), ppc.fmadds(9, 8, 8, 9), ppc.fsubs(10, 2, 5))
    a(ppc.lfs(11, R["dive_t"], 23), ppc.lfs(0, fb.C["down_frames"], 24), ppc.fcmpu(11, 0))
    a.br("blt", "c1_not_diving")
    a(ppc.lfs(12, fb.C["dive_r2"], 24), ppc.lfs(13, fb.C["dive_reach"], 24))
    a.br("b", "c1_test")
    a.label("c1_not_diving")
    a(ppc.lfs(0, D["zero"], 31), ppc.fcmpu(11, 0), fb.BGTLR)          # down after a dive: no catch
    a(ppc.lfs(12, fb.C["catch_r2"], 24), ppc.lfs(13, fb.C["reach"], 24), ppc.lfs(0, R["jump_h"], 23),
      ppc.fadds(13, 13, 0))
    a.label("c1_test")
    a(ppc.fcmpu(9, 12), fb.BGTLR, ppc.fcmpu(10, 13), fb.BGTLR, ppc.lfs(0, fb.C["low"], 24), ppc.fcmpu(10, 0),
      fb.BLTLR)
    a(ppc.li(0, fb.PH_HOLD), ppc.stw(0, fb.S["phase"], 24), ppc.li(0, fb.R_CAUGHT), ppc.stw(0, fb.S["result"], 24),
      ppc.stw(22, D["catcher"], 31))
    a(ppc.stfs(4, fb.S["hx"], 24), ppc.lfs(0, fb.C["lift"], 24), ppc.fadds(0, 5, 0), ppc.stfs(0, fb.S["hy"], 24),
      ppc.stfs(6, fb.S["hz"], 24), BLR)

    # ---- fp_track_pass: bl from football.py's fb_track every update of a pass (r28 = the setup, r29 = the ball,
    # r31 = football's state): the landing star where the ball will come down (the flight run on ahead with the
    # game's own ball update, wind and spin and all; Andrew: "a landing zone star on the receiver side to see where its
    # gonna land"), and the camera's focus (football's rx, ry, rz, which fb_cam frames): the catcher once caught, else
    # the receivers' middle, backed off toward the camera by how far apart they are
    a.label("fp_track_pass")
    _enter(a, 0x30, 24)
    a(ppc.mr(24, 31), ppc.mr(26, 28), ppc.mr(27, 29))
    _li32(a, 31, data)
    a(ppc.lwz(0, fb.S["phase"], 24), ppc.cmpwi(0, fb.PH_FLY))
    a.br("bne", "tp_focus")
    a(ppc.lwz(9, D["pred_n"], 31), ppc.addi(0, 9, -1), ppc.stw(0, D["pred_n"], 31), ppc.cmpwi(9, 0))
    a.br("bgt", "tp_focus")
    a(ppc.li(0, PRED_EVERY - 1), ppc.stw(0, D["pred_n"], 31))
    a.br("bl", "fp_predict")
    a.label("tp_focus")
    a(ppc.lwz(9, D["catcher"], 31), ppc.cmpwi(9, 0))
    a.br("blt", "tp_mid")
    a(ppc.mulli(9, 9, RSIZE), ppc.add(9, 9, 31), ppc.lfs(1, D["rcv"] + R["x"], 9), ppc.lfs(2, D["rcv"] + R["y"], 9),
      ppc.lfs(3, D["rcv"] + R["z"], 9))
    a.br("b", "tp_set")
    a.label("tp_mid")
    a(ppc.lfs(1, D["zero"], 31), ppc.fmr(2, 1), ppc.fmr(3, 1), ppc.fmr(4, 1), ppc.lfs(5, D["one"], 31))
    for k in range(N_RCV):
        sk = D["rcv"] + RSIZE * k
        a(ppc.lwz(0, sk + R["player"], 31), ppc.cmpwi(0, 0))
        a.br("beq", f"tp_sum{k}")
        a(ppc.lfs(0, sk + R["x"], 31), ppc.fadds(1, 1, 0), ppc.lfs(0, sk + R["y"], 31), ppc.fadds(2, 2, 0),
          ppc.lfs(0, sk + R["z"], 31), ppc.fadds(3, 3, 0), ppc.fadds(4, 4, 5))
        a.label(f"tp_sum{k}")
    a(ppc.lfs(0, D["zero"], 31), ppc.fcmpu(4, 0))
    a.br("ble", "tp_out")                               # (nobody: football's own)
    a(ppc.fdivs(1, 1, 4), ppc.fdivs(2, 2, 4), ppc.fdivs(3, 3, 4), ppc.lfs(6, D["zero"], 31))
    for k in range(N_RCV):                              # the spread: the farthest from the middle, squared
        sk = D["rcv"] + RSIZE * k
        a(ppc.lwz(0, sk + R["player"], 31), ppc.cmpwi(0, 0))
        a.br("beq", f"tp_far{k}")
        a(ppc.lfs(0, sk + R["x"], 31), ppc.fsubs(0, 0, 1), ppc.fmuls(7, 0, 0), ppc.lfs(0, sk + R["z"], 31),
          ppc.fsubs(0, 0, 3), ppc.fmadds(7, 0, 0, 7), ppc.fcmpu(7, 6))
        a.br("ble", f"tp_far{k}")
        a(ppc.fmr(6, 7))
        a.label(f"tp_far{k}")
    a(ppc.lfs(0, D["tiny"], 31), ppc.fcmpu(6, 0))
    a.br("ble", "tp_set")
    _rsqrt(a, 7, 6, 8, 9, 10)
    a(ppc.fmuls(6, 6, 7), ppc.lfs(0, D["pull"], 31), ppc.fmuls(6, 6, 0), ppc.lfs(0, fb.S["fx"], 24),
      fnmsubs(1, 0, 6, 1), ppc.lfs(0, fb.S["fz"], 24), fnmsubs(3, 0, 6, 3))   # backed off, away from the throw
    a.label("tp_set")
    a(ppc.stfs(1, fb.S["rx"], 24), ppc.stfs(2, fb.S["ry"], 24), ppc.stfs(3, fb.S["rz"], 24))
    a.label("tp_out")
    _leave(a, 0x30, 24)

    # ---- fp_predict: (r26 = the setup, r27 = the ball, r31 = our data) the ball copied and flown on with the game's
    # own update (BALL_STEP, what the aim preview loops; the copy's trail recorder is off in flight) and the spin's
    # dip or float (fp_spinfly's) until it touches down: the setup's target there (the landing star)
    a.label("fp_predict")
    _enter(a, 0x20, 28)
    a(ppc.addi(3, 31, D["pball"] - 4), ppc.addi(4, 27, -4), ppc.li(0, BALL_SIZE // 4), ppc.mtctr(0))
    a.label("pr_copy")
    a(ppc.lwzu(0, 4, 4), ppc.stwu(0, 4, 3))
    a.br("bdnz", "pr_copy")
    a(ppc.li(28, PRED_MAX))
    a.label("pr_step")
    a(ppc.addi(3, 31, D["pball"]))
    _call(a, BALL_STEP)
    a(ppc.lwz(3, S_SPIN, 26), ppc.addi(3, 3, -1), ppc.cmplwi(3, 3))
    a.br("bgt", "pr_spun")
    a(ppc.lfs(1, D["pball"] + B_VEL + 4, 31), ppc.lfs(0, D["zero"], 31), ppc.fcmpu(1, 0))
    a.br("bge", "pr_spun")
    a(ppc.slwi(3, 3, 2), ppc.addi(3, 3, D["spin_dv"]), lfsx(0, 31, 3), ppc.fadds(1, 1, 0),
      ppc.stfs(1, D["pball"] + B_VEL + 4, 31))
    a.label("pr_spun")
    a(ppc.lwz(0, D["pball"] + B_FLAGS, 31), ppc.andi_(0, 0, 1))
    a.br("bne", "pr_down")
    a(ppc.addi(28, 28, -1), ppc.cmpwi(28, 0))
    a.br("bgt", "pr_step")
    a.label("pr_down")
    for k in range(3):
        a(ppc.lfs(0, D["pball"] + B_POS + 4 * k, 31), ppc.stfs(0, S_TARGET + 4 * k, 26))
    _leave(a, 0x20, 28)

    # ---- fp_posts_hide: bl from football.py's fb_posts (r31 = football's state, its pnx/pnz the way from the
    # shooter's lie to the pin, just set) -> r3 = 1 to leave the posts out this frame: a pass whose camera is past them
    # (behind receivers standing near the posts it looks back at the QB, and an upright stood in the way); kicks keep them
    a.label("fp_posts_hide")
    a(ppc.li(3, 0), ppc.lwz(0, fb.S["kind"], 31), ppc.cmpwi(0, fb.KIND_PASS), BNELR)
    hi, lo = ppc.hi_lo(fb.CAMERA)
    a(ppc.lis(12, hi), ppc.lwz(12, lo, 12), ppc.lfs(1, 0, 12), ppc.lfs(3, 8, 12))
    hi, lo = ppc.hi_lo(fb.PIN)
    a(ppc.lis(12, hi), ppc.lfs(4, lo, 12), ppc.lfs(6, lo + 8, 12), ppc.fsubs(1, 1, 4), ppc.fsubs(3, 3, 6),
      ppc.lfs(7, fb.S["pnx"], 31), ppc.lfs(8, fb.S["pnz"], 31), ppc.fmuls(9, 1, 7), ppc.fmadds(9, 3, 8, 9))
    _li32(a, 12, data)
    a(ppc.lfs(0, D["zero"], 12), ppc.fcmpu(9, 0), fb.BLELR, ppc.li(3, 1), BLR)

    # ---- fp_rotate: bl from ROTATE (r3 = the team's first player, r31 = the golf state; the game flips the team
    # record's alternate-shot toggle +0x1C2 there, then makes the shooter the team or, toggled, its partner): in
    # Pigskin's one team of 3 or 4 the QB goes round everyone (Andrew: "1 qb 3 receivers rotating"): the toggle counts
    # 0 .. players - 1 and the shooter is the team + it
    a.label("fp_rotate")
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0))
    a.br("beq", "ro_game")
    a(ppc.lis(12, 0x804E), ppc.lbz(10, D15 & 0xFFFF, 12), ppc.lbz(11, D16 & 0xFFFF, 12), ppc.cmpwi(10, 1))
    a.br("bne", "ro_game")
    a(ppc.cmpwi(11, 2))
    a.br("ble", "ro_game")
    _li32(a, 12, data)                                  # (our own count: the game's toggle starts at 1, so it put
    a(ppc.lwz(9, 8, 3), ppc.lwz(8, D["rot"], 12), ppc.addi(8, 8, 1), ppc.cmpw(8, 11))   # player 2 up first; ours
    a.br("blt", "ro_set")                               # starts each round at -1: 1P first)
    a(ppc.li(8, 0))
    a.label("ro_set")
    a(ppc.stw(8, D["rot"], 12), ppc.stb(8, 0x1C2, 9), ppc.lbz(10, 0xD17, 31), ppc.add(10, 10, 8),
      ppc.stb(10, 0xD17, 31))
    _li32(a, 12, PICK_DONE)
    a(ppc.mtlr(12), BLR)                                # (on where the game loads the shooter)
    a.label("ro_game")
    a.b(TOGGLE)

    # ---- fp_quiet: bl from GOLF_SOUNDS (in place of bl SOUND; r3 the sound, r4 its volume): no golf club sounds in
    # Pigskin (Andrew: "remove the golf impact sound in football mode"); else the game's call
    a.label("fp_quiet")
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0), BNELR)
    a.b(SOUND)

    # ---- fp_label: bl from fbhud.LABEL_HOOKS (`addi r4,r4,0xa29`, r4 = 0): the HUD badge's name file base, ours in
    # Football (fbhud.py: J/A/<club>, the shot type's name)
    a.label("fp_label")
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.li(4, 0xA29), ppc.cmpwi(0, 0), BEQLR, ppc.li(4, fbhud.LABEL_BASE), BLR)

    # ---- fp_badge: bl from fbhud.BALL_HOOKS (`add r3,r28,r29`: r28 = 2 x club, r29 = 0xa45, then `add r29,r31,r29`
    # with r31 = 2 x club + 0x1C x club set): the badge picture's preload (r3) and file (r31 + r29); in Football ours,
    # J/B/<club> (a football), the same for every club set
    a.label("fp_badge")
    hi, lo = ppc.hi_lo(fb.ON)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0))
    a.br("bne", "bg_ours")
    a(ppc.add(3, 28, 29), BLR)
    a.label("bg_ours")
    a(ppc.li(3, fbhud.BALL_BASE), ppc.add(3, 3, 28), ppc.subf(29, 31, 3), BLR)

    # ---- the shot types' texts (football.py's message table points at them; only asked for in a round)
    for t, (_name, _club, _angle, _spin, text) in enumerate(fb.SHOT_TYPES):
        a.label(f"type_text_{t}")
        a(*struct.unpack(f">{-(-len(text) // 4)}I", text + bytes(-len(text) % 4)))

    # ---- fp_release: free our holders; r3 = 1 once both are free (r31 = our data)
    # ---- fp_release: (r3 = a receiver slot) its holders let go; r3 = 1 when both are free (then it can load)
    a.label("fp_release")
    _enter(a, 0x20, 29)
    a(ppc.mr(29, 3), ppc.li(30, 1))
    for name in ("mh", "bh"):
        a(ppc.addi(3, 29, R[name]))
        _call(a, HOLDER_FREE)
        a(ppc.cmpwi(3, 0))
        a.br("bne", "r_free_" + name)
        a(ppc.addi(3, 29, R[name]), ppc.li(30, 0))
        _call(a, HOLDER_RELEASE)
        a.label("r_free_" + name)
    a(ppc.li(0, 0), ppc.stw(0, R["model_id"], 29), ppc.mr(3, 30))
    _leave(a, 0x20, 29)

    # ---- fp_load: (r3 = a receiver slot, r4 = its model's id, r5 = a heap, r29 = the receiver) load its bank (if any)
    # and model into the slot's holders
    a.label("fp_load")
    _enter(a, 0x30, 24)
    a(ppc.mr(24, 3), ppc.mr(26, 4), ppc.stw(26, R["model_id"], 24), ppc.mr(25, 5), ppc.li(27, 0))
    a(ppc.lwz(3, P_OBJ, 29), ppc.lwz(9, 0, 3), ppc.lwz(12, M_BANK_ID, 9), ppc.mtctr(12), BCTRL)
    a(ppc.cmpwi(3, -1))
    a.br("beq", "l_model")
    a(ppc.mr(4, 3), ppc.addi(27, 24, R["bh"]), ppc.mr(3, 27), ppc.mr(5, 25))
    _call(a, LOAD_BANK)
    a.label("l_model")
    a(ppc.addi(3, 24, R["mh"]), ppc.mr(4, 26), ppc.mr(5, 27), ppc.mr(6, 25))
    _call(a, LOAD_MODEL)
    _leave(a, 0x30, 24)

    # ---- fp_pose: (r3 = an instance, r4 = its golfer code, r5 = a clip, f1 = its time) the pose, into the instance
    a.label("fp_pose")
    _enter(a, 0x60, 22)
    _li32(a, 31, data)
    a(ppc.mr(30, 3), ppc.mulli(4, 4, RIG_SIZE))
    _li32(a, 29, L["rigs"])
    a(ppc.add(29, 29, 4))                               # r29 = the golfer's rig
    a(ppc.lwz(9, 0, 30), ppc.lwz(25, 0x64, 9))           # r25 = its model's bones
    _li32(a, 9, L["clips"])
    a(ppc.slwi(0, 5, 3), ppc.add(9, 9, 0), ppc.lhz(22, 0, 9), ppc.lhz(23, 2, 9), ppc.lwz(24, 4, 9),
      ppc.stw(24, D["clip_flags"], 31), ppc.andi_(24, 24, CLIP_LOOP))
    a(ppc.li(26, 0), ppc.li(27, 0), ppc.lfs(2, D["zero"], 31), ppc.stfs(2, D["u"], 31), ppc.cmpwi(23, 1))
    a.br("ble", "p_keys")                               # (one key: k0 = k1 = 0)
    a(ppc.cmpwi(24, 0))
    a.br("beq", "p_once")
    _int_to_float(a, 2, 23)                             # a loop: x = t n, k = x mod n, next one on
    a(ppc.fmuls(3, 1, 2), ppc.fctiwz(0, 3), ppc.stfd(0, D["cvt"], 31), ppc.lwz(26, D["cvt"] + 4, 31))
    _int_to_float(a, 4, 26)
    a(ppc.fsubs(3, 3, 4), ppc.stfs(3, D["u"], 31))
    a(divw(9, 26, 23), ppc.mullw(9, 9, 23), ppc.subf(26, 9, 26), ppc.addi(27, 26, 1), ppc.cmpw(27, 23))
    a.br("blt", "p_keys")
    a(ppc.li(27, 0))
    a.br("b", "p_keys")
    a.label("p_once")                                   # once through: x = t (n - 1), clamped
    a(ppc.addi(9, 23, -1))
    _int_to_float(a, 2, 9)
    a(ppc.fmuls(3, 1, 2), ppc.lfs(0, D["zero"], 31), ppc.fcmpu(3, 0))
    a.br("ble", "p_keys")
    a(ppc.fcmpu(3, 2))
    a.br("blt", "p_mid")
    a(ppc.addi(26, 23, -2), ppc.addi(27, 23, -1), ppc.lfs(0, D["one"], 31), ppc.stfs(0, D["u"], 31))
    a.br("b", "p_keys")
    a.label("p_mid")
    a(ppc.fctiwz(0, 3), ppc.stfd(0, D["cvt"], 31), ppc.lwz(26, D["cvt"] + 4, 31))
    _int_to_float(a, 4, 26)
    a(ppc.fsubs(3, 3, 4), ppc.stfs(3, D["u"], 31), ppc.addi(27, 26, 1))
    a.label("p_keys")                                   # r28, r27 = the two keys
    _li32(a, 9, L["keys"])
    a(ppc.add(26, 26, 22), ppc.mulli(26, 26, KEY_SIZE), ppc.add(28, 9, 26), ppc.add(27, 27, 22),
      ppc.mulli(27, 27, KEY_SIZE), ppc.add(27, 9, 27))
    # each joint's D: nlerp of the two keys'
    a(ppc.li(26, 0))
    a.label("p_blend")
    a(ppc.slwi(9, 26, 4), ppc.add(3, 28, 9), ppc.add(4, 27, 9), ppc.addi(5, 31, D["dbuf"]), ppc.add(5, 5, 9))
    a.br("bl", "fp_nlerp")
    a(ppc.addi(26, 26, 1), ppc.cmpwi(26, N_JOINTS))
    a.br("blt", "p_blend")
    # the body's pitch (cos, sin; renormalised) and drop
    a(ppc.lfs(10, D["u"], 31))
    for off, f in ((KEY_PC, 1), (KEY_PS, 2), (KEY_DROP, 3)):
        a(ppc.lfs(f, off, 28), ppc.lfs(0, off, 27), ppc.fsubs(0, 0, f), ppc.fmadds(f, 0, 10, f))
    a(ppc.stfs(3, D["drop"], 31), ppc.fmuls(6, 1, 1), ppc.fmadds(6, 2, 2, 6))
    _rsqrt(a, 7, 6, 8, 9, 11)
    a(ppc.fmuls(1, 1, 7), ppc.fmuls(2, 2, 7), ppc.stfs(1, D["pc"], 31), ppc.stfs(2, D["ps"], 31))
    # each joint's bone: L_b = conj(R_p) conj(D_a) D_j R_p l_b
    a(ppc.li(26, 0))
    a.label("p_joint")
    a(ppc.lbzx(24, 29, 26), ppc.cmpwi(24, 0xFF))         # r24 = the joint's bone
    a.br("beq", "p_next")
    a(ppc.slwi(23, 26, 4), ppc.addi(4, 31, D["dbuf"]), ppc.add(4, 4, 23), ppc.addi(9, 29, RIG_ANC),
      ppc.lbzx(0, 9, 26), ppc.cmpwi(0, 0xFF))
    a.br("bne", "p_rel")
    a(ppc.lwz(9, 0, 4), ppc.lwz(10, 4, 4), ppc.lwz(11, 8, 4), ppc.lwz(12, 12, 4), ppc.stw(9, D["e"], 31),
      ppc.stw(10, D["e"] + 4, 31), ppc.stw(11, D["e"] + 8, 31), ppc.stw(12, D["e"] + 12, 31))
    a.br("b", "p_e")
    a.label("p_rel")
    a(ppc.slwi(0, 0, 4), ppc.addi(3, 31, D["dbuf"]), ppc.add(3, 3, 0), ppc.addi(5, 31, D["e"]), ppc.li(6, 1))
    a.br("bl", "fp_qmul")
    a.label("p_e")
    a(ppc.addi(3, 29, RIG_RP), ppc.add(3, 3, 23), ppc.addi(4, 31, D["e"]), ppc.addi(5, 31, D["t1"]), ppc.li(6, 1))
    a.br("bl", "fp_qmul")
    a(ppc.addi(4, 29, RIG_RP), ppc.add(4, 4, 23), ppc.addi(3, 31, D["t1"]), ppc.addi(5, 31, D["t1"]), ppc.li(6, 0))
    a.br("bl", "fp_qmul")
    a(ppc.mulli(4, 24, 0x60), ppc.add(4, 4, 25), ppc.addi(4, 4, 0x4C), ppc.addi(3, 31, D["t1"]),
      ppc.addi(5, 31, D["q"]), ppc.add(5, 5, 23), ppc.li(6, 0))
    a.br("bl", "fp_qmul")
    a(ppc.addi(9, 31, D["map"]), ppc.stbx(26, 9, 24))
    a.label("p_next")
    a(ppc.addi(26, 26, 1), ppc.cmpwi(26, N_JOINTS))
    a.br("blt", "p_joint")
    # the clubs' bones: scale 0
    a(ppc.lwz(23, RIG_NHIDE, 29), ppc.li(9, 0), ppc.addi(10, 31, D["map"]), ppc.addi(11, 29, RIG_HIDE),
      ppc.li(0, 0xFE))
    a.label("p_hide")
    a(ppc.cmpw(9, 23))
    a.br("bge", "p_fk")
    a(ppc.lbzx(12, 11, 9), ppc.stbx(0, 10, 12), ppc.addi(9, 9, 1))
    a.br("b", "p_hide")
    a.label("p_fk")
    a(ppc.mr(3, 30))
    a.br("bl", "fp_fk")
    # grounded clips: the lower ankle back at its rest height (bent knees about fixed hips lift the feet); then the
    # "shift" (the QB's place in the game's swing, fp_qb); every bone's translation (+0x00's and +0x30's) moved
    a(ppc.lfs(1, D["zero"], 31), ppc.lwz(0, D["clip_flags"], 31), ppc.andi_(0, 0, CLIP_GROUND))
    a.br("beq", "p_shift")
    a(ppc.lfs(1, D["big"], 31), ppc.lwz(10, 0x14, 30))
    for k, joint in enumerate(("foot_r", "foot_l")):
        a(ppc.lbz(9, J_INDEX[joint], 29), ppc.cmpwi(9, 0xFF))
        a.br("beq", f"p_nofoot{k}")
        a(ppc.mulli(9, 9, 0x60), ppc.add(9, 9, 10), ppc.lfs(2, 0x1C, 9), ppc.lfs(3, RIG_FEET + 4 * k, 29),
          ppc.fsubs(2, 2, 3), ppc.fcmpu(2, 1))
        a.br("bge", f"p_nofoot{k}")
        a(ppc.fmr(1, 2))
        a.label(f"p_nofoot{k}")
    a(ppc.lfs(0, D["big"], 31), ppc.fcmpu(1, 0))
    a.br("blt", "p_shift")
    a(ppc.lfs(1, D["zero"], 31))                         # (no feet)
    a.label("p_shift")                                  # (f4, f5, f6) = shift - (0, lift, 0)
    a(ppc.lfs(4, D["shift_x"], 31), ppc.lfs(5, D["shift_y"], 31), ppc.fsubs(5, 5, 1), ppc.lfs(6, D["shift_z"], 31),
      ppc.lwz(10, 0x14, 30), ppc.lwz(9, 0, 30), ppc.lwz(11, 0x60, 9), ppc.mtctr(11))
    a.label("p_lower")
    for off, f in ((0x0C, 4), (0x1C, 5), (0x2C, 6), (0x3C, 4), (0x4C, 5), (0x5C, 6)):
        a(ppc.lfs(2, off, 10), ppc.fadds(2, 2, f), ppc.stfs(2, off, 10))
    a(ppc.addi(10, 10, 0x60))
    a.br("bdnz", "p_lower")
    a.label("p_clear0")
    # leave the map empty for the next pose
    a(ppc.addi(10, 31, D["map"]), ppc.li(0, 0xFF), ppc.li(9, 0))
    a.label("p_clear")
    a(ppc.lbzx(12, 29, 9), ppc.stbx(0, 10, 12), ppc.addi(9, 9, 1), ppc.cmpwi(9, N_JOINTS))
    a.br("blt", "p_clear")
    a(ppc.li(9, 0), ppc.addi(11, 29, RIG_HIDE))
    a.label("p_clear2")
    a(ppc.cmpw(9, 23))
    a.br("bge", "p_done")
    a(ppc.lbzx(12, 11, 9), ppc.stbx(0, 10, 12), ppc.addi(9, 9, 1))
    a.br("b", "p_clear2")
    a.label("p_done")
    a(ppc.li(0, 0xFF), ppc.stb(0, D["map"] + 0xFF, 31))   # (a joint without a bone wrote map[0xFF])
    _leave(a, 0x60, 22)

    # ---- fp_qmul: (r3 = a, r4 = b, r5 = out, r6 = 1: conj(a)) out = a b; f0-f12 (no stack)
    a.label("fp_qmul")
    a(ppc.lfs(1, 0, 3), ppc.lfs(2, 4, 3), ppc.lfs(3, 8, 3), ppc.lfs(4, 12, 3), ppc.cmpwi(6, 0))
    a.br("beq", "q_go")
    a(ppc.fneg(1, 1), ppc.fneg(2, 2), ppc.fneg(3, 3))
    a.label("q_go")
    a(ppc.lfs(5, 0, 4), ppc.lfs(6, 4, 4), ppc.lfs(7, 8, 4), ppc.lfs(8, 12, 4))
    a(ppc.fmuls(9, 4, 5), ppc.fmadds(9, 1, 8, 9), ppc.fmadds(9, 2, 7, 9), fnmsubs(9, 3, 6, 9))      # x
    a(ppc.fmuls(10, 4, 6), fnmsubs(10, 1, 7, 10), ppc.fmadds(10, 2, 8, 10), ppc.fmadds(10, 3, 5, 10))  # y
    a(ppc.fmuls(11, 4, 7), ppc.fmadds(11, 1, 6, 11), fnmsubs(11, 2, 5, 11), ppc.fmadds(11, 3, 8, 11))  # z
    a(ppc.fmuls(12, 4, 8), fnmsubs(12, 1, 5, 12), fnmsubs(12, 2, 6, 12), fnmsubs(12, 3, 7, 12))   # w
    a(ppc.stfs(9, 0, 5), ppc.stfs(10, 4, 5), ppc.stfs(11, 8, 5), ppc.stfs(12, 12, 5), BLR)

    # ---- fp_nlerp: (r3 = a, r4 = b, r5 = out, "u") out = normalised a + (+-b - a) u; f0-f12, r31 = our data
    a.label("fp_nlerp")
    a(ppc.lfs(1, 0, 3), ppc.lfs(2, 4, 3), ppc.lfs(3, 8, 3), ppc.lfs(4, 12, 3))
    a(ppc.lfs(5, 0, 4), ppc.lfs(6, 4, 4), ppc.lfs(7, 8, 4), ppc.lfs(8, 12, 4))
    a(ppc.fmuls(9, 1, 5), ppc.fmadds(9, 2, 6, 9), ppc.fmadds(9, 3, 7, 9), ppc.fmadds(9, 4, 8, 9),
      ppc.lfs(0, D["zero"], 31), ppc.fcmpu(9, 0))
    a.br("bge", "n_same")
    a(ppc.fneg(5, 5), ppc.fneg(6, 6), ppc.fneg(7, 7), ppc.fneg(8, 8))
    a.label("n_same")
    a(ppc.lfs(10, D["u"], 31))
    for fa, fb_ in ((1, 5), (2, 6), (3, 7), (4, 8)):
        a(ppc.fsubs(fb_, fb_, fa), ppc.fmadds(fa, fb_, 10, fa))
    a(ppc.fmuls(9, 1, 1), ppc.fmadds(9, 2, 2, 9), ppc.fmadds(9, 3, 3, 9), ppc.fmadds(9, 4, 4, 9))
    _rsqrt(a, 11, 9, 5, 6, 7)
    a(ppc.fmuls(1, 1, 11), ppc.fmuls(2, 2, 11), ppc.fmuls(3, 3, 11), ppc.fmuls(4, 4, 11))
    a(ppc.stfs(1, 0, 5), ppc.stfs(2, 4, 5), ppc.stfs(3, 8, 5), ppc.stfs(4, 12, 5), BLR)

    # ---- fp_fk: (r3 = an instance) the bones' matrices from their rest values, our rotations for mapped bones
    # (map[bone] = a joint, its rotation at q + 16 joint; 0xFE = a club's: scale 0), the game's way (module notes)
    a.label("fp_fk")
    _enter(a, 0x50, 21)
    _li32(a, 21, data)
    a(ppc.mr(26, 3), ppc.lwz(27, 0, 26), ppc.lwz(23, 0x64, 27), ppc.lwz(29, 0x60, 27), ppc.lwz(24, 0x14, 26),
      ppc.li(30, 0), ppc.li(25, 0), ppc.mr(22, 24))
    a.label("k_loop")
    a(ppc.cmpw(30, 29))
    a.br("bge", "k_done")
    a(ppc.addi(9, 21, D["map"]), ppc.lbzx(28, 9, 30), ppc.cmpwi(28, 0xFE), ppc.addi(4, 23, 0x4C))
    a.br("bge", "k_q")
    a(ppc.slwi(0, 28, 4), ppc.addi(4, 21, D["q"]), ppc.add(4, 4, 0))
    a.label("k_q")
    a(ppc.lwz(0, 0, 23), ppc.cmpwi(0, -1))
    a.br("beq", "k_root")
    a(ppc.addi(3, 21, D["tmp"]))
    _call(a, MTX_QUAT)
    a(ppc.lwz(0, 0, 23), ppc.mulli(0, 0, 0x60), ppc.add(3, 24, 0), ppc.lwz(9, 0x5C, 23), ppc.andi_(9, 9, 4))
    a.br("beq", "k_base")
    a(ppc.addi(3, 3, 0x30))
    a.label("k_base")
    a(ppc.addi(4, 21, D["tmp"]), ppc.addi(5, 22, 0x30))
    _call(a, MTX_CONCAT)
    a.br("b", "k_scale")
    a.label("k_root")
    a(ppc.addi(3, 22, 0x30))
    _call(a, MTX_QUAT)
    a.label("k_scale")
    a(ppc.lfs(1, 0x34, 23), ppc.lfs(2, 0x38, 23), ppc.lfs(3, 0x3C, 23), ppc.cmpwi(28, 0xFE))
    a.br("bne", "k_scaled")
    a(ppc.lfs(1, D["zero"], 21), ppc.fmr(2, 1), ppc.fmr(3, 1))
    a.label("k_scaled")
    a(ppc.addi(3, 21, D["tmp"]))
    _call(a, MTX_SCALE)
    a(ppc.addi(3, 22, 0x30), ppc.addi(4, 21, D["tmp"]), ppc.mr(5, 22))
    _call(a, MTX_CONCAT)
    a(ppc.lwz(0, 0, 23), ppc.cmpwi(0, -1))
    a.br("beq", "k_root_t")
    a(ppc.mulli(0, 0, 0x60), ppc.add(3, 24, 0), ppc.addi(4, 23, 0x40), ppc.mr(5, 22))
    _call(a, MTX_TRANS)
    a.br("b", "k_flags")
    a.label("k_root_t")
    a(ppc.lfs(0, 0x40, 23), ppc.stfs(0, 0x0C, 22), ppc.lfs(0, 0x44, 23), ppc.stfs(0, 0x1C, 22), ppc.lfs(0, 0x48, 23),
      ppc.stfs(0, 0x2C, 22))
    a.label("k_flags")
    a(ppc.lwz(0, 0x5C, 23), ppc.andi_(0, 0, 2))
    a.br("beq", "k_next")
    a(ppc.lwz(11, 0x28, 26), ppc.cmpwi(11, 0))
    a.br("beq", "k_next")
    a(ppc.slwi(9, 25, 2), stwx(30, 11, 9), ppc.addi(25, 25, 1))
    a.label("k_next")
    a(ppc.addi(30, 30, 1), ppc.addi(23, 23, 0x60), ppc.addi(22, 22, 0x60))
    a.br("b", "k_loop")
    a.label("k_done")
    a(ppc.li(0, 0), ppc.stw(0, 0x2C, 26))
    _leave(a, 0x50, 21)
    return a


# ---- the football (Andrew: "a football model"): an ellipsoid, long along x, in bands of one colour each (the
# draw has no lighting): the top, sides and bottom of the leather, and the white laces on top. In feet, about 1.5
# times a real ball's 11 x 6.7 inches, so it reads in the air.
BALL_RINGS, BALL_SEGS = 8, 12
BALL_COLORS = (0xA0602EFF, 0x7E4622FF, 0x52301AFF, 0xF4F0E8FF)   # top, sides, bottom, laces (RGBA)
BALL_BANDS = len(BALL_COLORS)


def ball_mesh():
    quads = [[] for _ in BALL_COLORS]
    pt = lambda i, j: (BALL_A * math.cos(math.pi * i / BALL_RINGS),
                       BALL_B * math.sin(math.pi * i / BALL_RINGS) * math.cos(2 * math.pi * j / BALL_SEGS),
                       BALL_B * math.sin(math.pi * i / BALL_RINGS) * math.sin(2 * math.pi * j / BALL_SEGS))
    for i in range(BALL_RINGS):
        for j in range(BALL_SEGS):
            q = [pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1)]
            y = sum(v[1] for v in q) / 4
            quads[0 if y > 0.35 * BALL_B else 2 if y < -0.35 * BALL_B else 1].append(q)
    lift = BALL_B * 1.04                                 # the laces, just over the top
    quads[3].append([(-0.3 * BALL_A, lift, -0.025), (0.3 * BALL_A, lift, -0.025), (0.3 * BALL_A, lift, 0.025),
                     (-0.3 * BALL_A, lift, 0.025)])
    for k in range(7):
        x = -0.24 * BALL_A + 0.08 * BALL_A * k
        quads[3].append([(x - 0.012, lift, -0.07), (x + 0.012, lift, -0.07), (x + 0.012, lift, 0.07),
                         (x - 0.012, lift, 0.07)])
    out = bytearray()
    for color, band in zip(BALL_COLORS, quads):
        out += struct.pack(">II", color, 4 * len(band))
        for q in band:
            for v in q:
                out += struct.pack(">3f", *v)
    return bytes(out)


# ---- tables (fbmoves.py)
def _tables():
    import fbmoves
    import rigmap
    rigs = bytearray()
    for code in sorted(rigmap.MODELS):
        rig = fbmoves.Rig(rigmap.load(code, ROOT))
        if len(rig.hide) > MAX_HIDE:
            raise SystemExit(f"{rigmap.NAMES[code]}: {len(rig.hide)} club bones; the rig table holds {MAX_HIDE}")
        b = bytearray(RIG_SIZE)
        for j in range(N_JOINTS):
            b[j] = rig.bone[j] & 0xFF
            b[RIG_ANC + j] = rig.anc[j] & 0xFF
            struct.pack_into(">4f", b, RIG_RP + 16 * j, *rig.rp[j])
        b[N_JOINTS] = b[RIG_ANC + N_JOINTS] = 0xFF
        struct.pack_into(">fI", b, RIG_HIPS, rig.hips_y, len(rig.hide))
        hb = rig.bone[fbmoves.J["hips"]]
        if hb >= 0:
            struct.pack_into(">ff", b, RIG_HIPS_X, rig.world[hb][3], rig.world[hb][11])
        for k, joint in enumerate(("foot_r", "foot_l")):
            fb_ = rig.bone[fbmoves.J[joint]]
            struct.pack_into(">f", b, RIG_FEET + 4 * k, rig.world[fb_][7] if fb_ >= 0 else 0.0)
        b[RIG_HIDE:RIG_HIDE + len(rig.hide)] = bytes(rig.hide)
        rigs += b
    keys, clips = bytearray(), bytearray()
    for name, ks, loop in fbmoves.CLIPS:
        flags = (CLIP_LOOP if loop else 0) | (CLIP_GROUND if name in GROUNDED else 0)
        clips += struct.pack(">HHI", len(keys) // KEY_SIZE, len(ks), flags)
        for key in ks:
            k = bytearray(KEY_SIZE)
            for j, joint in enumerate(fbmoves.JOINTS):
                struct.pack_into(">4f", k, 16 * j, *key["D"][joint])
            import math
            p = math.radians(key["pitch"])
            struct.pack_into(">3f", k, KEY_PC, math.cos(p), math.sin(p), key["drop"])
            keys += k
    return bytes(rigs), bytes(keys), bytes(clips)


ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def _clip_ids():
    import fbmoves
    return fbmoves.CLIP


CLIP = _clip_ids()
J_INDEX = {name: k for k, name in enumerate(("hips", "spine", "chest", "neck", "head", "clav_r", "uarm_r", "farm_r",
                                              "hand_r", "clav_l", "uarm_l", "farm_l", "hand_l", "thigh_r", "shin_r",
                                              "foot_r", "thigh_l", "shin_l", "foot_l"))}


def data_blob(at):
    b = bytearray(DATA_SIZE)
    for name, v in CONSTS.items():
        struct.pack_into(">f", b, D[name], v)
    struct.pack_into(">II", b, D["magic"], 0x43300000, 0x80000000)
    b[D["map"]:D["map"] + 256] = b"\xFF" * 256
    struct.pack_into(">i", b, D["dbg_clip"], -1)                     # (tests only)
    b[D["types"]:D["types"] + 4] = bytes(TYPE_CLUBS)
    angles, spins = [1.0] * 14, [1.0] * 14
    for _name, club, angle, spin, _text in fb.SHOT_TYPES:
        angles[club], spins[club] = angle, spin
    struct.pack_into(">14f", b, D["angle_k"], *angles)
    struct.pack_into(">14f", b, D["spin_k"], *spins)
    struct.pack_into(">4f", b, D["spin_dv"], *(k * GRAVITY for k in SPIN_DV))
    for name, vtable in (("mh", HOLDER_VTABLE), ("bh", BANK_VTABLE)):   # free holders (the tail reloads each round);
        struct.pack_into(">III", b, D[name], vtable, 5, 5)                 # +0x14 -> +0x10 (the unloader reads it)
        struct.pack_into(">I", b, D[name] + 0x14, at + D[name] + 0x10)
        for k in range(N_RCV):                                             # each receiver slot's too
            off = D["rcv"] + RSIZE * k + R[name]
            struct.pack_into(">III", b, off, vtable, 5, 5)
            struct.pack_into(">I", b, off + 0x14, at + off + 0x10)
    struct.pack_into(">i", b, D["catcher"], -1)
    struct.pack_into(">i", b, D["rot"], -1)
    struct.pack_into(">i", b, D["hole_seen"], -1)
    struct.pack_into(f">{len(RCV_SIZES)}I", b, D["need"], *(n + RCV_SPARE for n in RCV_SIZES))
    return bytes(b)


_cache = None


def build():
    """(blob for the golf tail at BASE, labels)."""
    global _cache
    if _cache:
        return _cache
    rigs, keys, clips = _tables()
    mesh = ball_mesh()
    L = {"data": BASE, "rigs": BASE, "keys": BASE, "clips": BASE, "ball_mesh": BASE}
    for _ in range(2):                                  # the first pass finds the code's size
        a = make_code(L)
        code = a.assemble()
        L["data"] = (BASE + len(code) + 31) & ~31
        L["rigs"] = L["data"] + DATA_SIZE
        L["keys"] = L["rigs"] + len(rigs)
        L["clips"] = L["keys"] + len(keys)
        L["ball_mesh"] = L["clips"] + len(clips)
    blob = code + bytes(L["data"] - BASE - len(code)) + data_blob(L["data"]) + rigs + keys + clips + mesh
    labels = dict(a.labels, **L)
    _cache = (blob, labels)
    return _cache


def overlay_patches(rel):
    if rel != "C/L/V":
        return []
    L = build()[1]
    return [(QUEUE_HOOK[0], ppc.b(QUEUE_HOOK[0], L["fp_queue"]), QUEUE_HOOK[1]),
            (PREVIEW_CALL, ppc.bl(PREVIEW_CALL, L["fp_preview"]), ppc.bl(PREVIEW_CALL, PREVIEW_FLY)),
            (CLUB_STEP[0], ppc.b(CLUB_STEP[0], L["fp_club"]), CLUB_STEP[1]),
            (AIM_CLEAR[0], ppc.bl(AIM_CLEAR[0], L["fp_snap"]), AIM_CLEAR[1]),
            (ANGLE_STORE[0], ppc.bl(ANGLE_STORE[0], L["fp_angle"]), ANGLE_STORE[1]),
            (SPIN_STORE[0], ppc.bl(SPIN_STORE[0], L["fp_spin"]), SPIN_STORE[1]),
            (ANGLE_FINAL[0], ppc.bl(ANGLE_FINAL[0], L["fp_angle0"]), ANGLE_FINAL[1]),
            (BEND_END[0], ppc.bl(BEND_END[0], L["fp_bend"]), BEND_END[1])] + [
        (at, ppc.bl(at, L["fp_quiet"]), ppc.bl(at, SOUND)) for at in GOLF_SOUNDS] + [
        (ROTATE, ppc.bl(ROTATE, L["fp_rotate"]), ppc.bl(ROTATE, TOGGLE))] + [
        (at, ppc.bl(at, L["fp_label"]), old) for at, old in fbhud.LABEL_HOOKS] + [
        (at, ppc.bl(at, L["fp_badge"]), old) for at, old in fbhud.BALL_HOOKS]


if __name__ == "__main__":
    blob, labels = build()
    print(f"golf tail: {len(blob)} bytes at 0x{BASE:08X}: code to 0x{labels['data']:08X}, rigs 0x{labels['rigs']:08X},"
          f" keys 0x{labels['keys']:08X}, clips 0x{labels['clips']:08X}")
