"""v16: Best Ball and Scramble, team games beside Doubles (alternate shot).

Menus (B/U/C): the Doubles list (Play Mode -> Doubles) gets four more choices after Skins:
  - Best Ball Match and Best Ball Stroke (2v2): everyone plays their own ball; on each hole a team counts its
    better player's strokes, under match-play rules (the better team score wins the hole, a tie halves it) or
    stroke-play rules (fewest total strokes).
  - Scramble (2v2): every team member hits from the team's spot, the team's captain picks the ball the team
    plays next (one stroke a round). The captain is the team's lowest-numbered human player (1P, and 3P with the
    first team arrangement); a team of CPUs takes the best shot.
  - Team Scramble: everyone on one team (2, 3 or 4 players, however many picked the game; not offered to 1),
    1P (the lowest-numbered player) picks.
  The 2v2 games go on like Doubles (team screen, CPUs fill the empty seats, teams are slots {0, 2} and {1, 3}).
  Team Scramble goes straight to the course select as a plain N-player game. The choice travels to the round in a
  spare setup byte (MODE_BYTE), cleared wherever the game clears the doubles flag.

Rounds (C/L/V), from `RE-NOTES.md` "Team games". All three keep Doubles' shared team record (one ball, lie, stroke
count and scorecard per team), so the game's own Doubles scoring, score panel, scorecard and results do the rest:
  - Best Ball: each member's ball lives in a slot of ours (lie and strokes). Before every turn the next member
    (tee shots first, then off the green, farthest from the pin first) gets loaded into the team record; after
    the shot it goes back to the slot, and the team record shows the team's best: the best holed score once no
    teammate can still beat it (the hole is then over for the team), else the fewest strokes still playing.
  - Scramble / Team Scramble (one side, d15 = 1): members take turns from the team's lie, starting with the member
    whose ball the team plays (v17), each one's result going
    to a slot instead of the team's lie. After a hole-out that ball is taken at once; after the last member the
    captain picks from a menu (the game's post-shot menu: a header row and one row per ball, with its distance
    and lie; the best shot is highlighted first: holed, then no penalty, then the distance to the pin weighted
    by the lie). Only the first member's swing counts a stroke (and a putt); a penalty counts only if the team
    takes that shot.

v20 adds two more (the list has its own icon/help arrays now: the game's hold 10):
  - Worst Ball (2v2): a scramble where the team plays its worst ball, taken at once without a menu: a ball not in
    the hole before a holed one, then a penalty, then the farthest (by the lie); the hole is over only when every
    member holes out from the same spot.
  - Wolf (3 or 4 humans, no CPUs; Golf Digest's rules, as Andrew asked): a Skins game of everyone on their own ball.
    The Wolf rotates (hole 1 the last player, hole 2 1P, ...) and tees off last; after each other player's drive,
    in order, the Wolf's menu asks "team up with YP?" (No can't be taken back; No to the last = the Lone Wolf).
    The hole is a best-ball match, Wolf's side against the rest: 1 point to each winner, 2 to a winning Lone Wolf,
    1 to each of the others when the Lone Wolf loses, nothing for a tie. Skins' own scoring is swapped for stroke
    play's per shot plus ours per hole; the points show where the game shows skins (score panel, the hole-end
    scorecard counting them up, the results).
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402
import ppc  # noqa: E402
import textures  # noqa: E402

# ---- where things are: three dead main.dol functions for code, one for data and one for text (find_dead_code.py)
CAVES = {            # name: (address, size, first word)
    "hooks": (0x80014324, 1632, 0x9421FFB0),   # the captain's menu runner, then the hooks
    "cam": (0x8003BD84, 736, 0x7C0802A6),
    "menu": (0x8001B974, 636, 0x9421FFD8),
    "pick": (0x80037BA8, 556, 0x7C0802A6),
    "choose": (0x80035D64, 468, 0x7C0802A6),   # Best Ball: whose turn
    "after": (0x800133F0, 412, 0x9421FFA8),    # Best Ball: after a shot
    "data": (0x8003287C, 864, 0x7C0802A6),
    "text": (0x80018130, 456, 0x9421FFE8),
    "extra": (0x800268D0, 352, 0x9421FFD0),    # Doubles' own five choices' help (alternate shot); v21 row_x
    # v20: Worst Ball and Wolf
    "list": (0x80054EFC, 424, 0x7C0802A6),     # the Team Play list's own icon/help arrays (11 choices)
    "worst": (0x8004FBF0, 352, 0x7C0802A6),    # Worst Ball: the worst shot
    "wpick": (0x80096398, 436, 0x9421FFD0),    # Wolf: the shooter pick (tee order, the Wolf's choices)
    "wmenu": (0x80090438, 404, 0x9421FFE0),    # Wolf: its menus
    "wscore": (0x80093460, 392, 0x9421FFF0),   # Wolf: scoring a hole
    "wshow": (0x800542C8, 364, 0x7C0802A6),    # Wolf: points on the panel, scorecard and results
    "wdata": (0x800816FC, 352, 0x9421FFF0),    # Wolf: state and points
    "wtext": (0x8005B7E4, 344, 0x7C0802A6),    # Worst Ball and Wolf texts
    "worst2": (0x8003A480, 320, 0x7C0802A6),   # after every member has hit; Wolf's menu commit
    "wstep": (0x80042AE4, 324, 0x7C0802A6),    # Wolf: running its menus
    "wname": (0x800550A4, 320, 0x7C0802A6),    # Wolf: the scoring hook, players' names, team_of
    "waward": (0x80067068, 324, 0x9421FFD8),   # Wolf: a hole's points
}

MODE_BYTE = 0xA7D            # setup block (main.dol 0x80175600) + 0xA7D = 0x8017607D: unused by the game
BEST_BALL, SCRAMBLE, TEAM_SCRAMBLE, WORST, WOLF = 1, 2, 3, 4, 5
TEAM_WORST = 6               # v21, the setup byte only: the round plays it as WORST with one side

PLAYERS, PLAYER_SIZE = 0x804ECE70, 0x5204
PLAYER_REC, PLAYER_BALL, PLAYER_PAD, PLAYER_INDEX, PLAYER_CONTROLLER = 0x8, 0x1C, 0x4F14, 0x5160, 0x5164
CPU = 4                      # PLAYER_CONTROLLER of a CPU golfer
REC_LIE, REC_STROKES, REC_STATUS, REC_TOGGLE, REC_PENALTY_KIND = 0xB4, 0x1BC, 0x1BE, 0x1C2, 0x1C4
LIE_SIZE = 0x34              # position, ..., +0x28 in the hole, +0x2C surface code
SLOT_SIZE = 0x38             # per player record: a lie, +0x34 penalty (scramble), +0x35 strokes, +0x36 done
SLOT_PEN, SLOT_STROKES, SLOT_DONE = 0x34, 0x35, 0x36
STATE_DOUBLES, STATE_D15, STATE_D16, STATE_D17 = 0xAE4, 0xD15, 0xD16, 0xD17   # golf state 0x804E5BE4 +
COURSE = 0x804E68F4
HOLE_INDEX = 0x804E68F8
D15, D16, D17 = 0x804E68F9, 0x804E68FA, 0x804E68FB
PIN_X, PIN_Z = 0x804E6864, 0x804E686C
GREEN = 0x02

# golf overlay hook sites: (address, the game's word)
SETUP_HOOK = (0x80401578, 0x981F0D16)        # stb r0,0xD16(r31): number of player records (r30 = setup block)
PICK_HOOK = (0x80403458, 0x3D20804E)         # lis r9,0x804E: the doubles part of the shooter pick (r3 = team)
PICK_DONE = 0x804034AC                       # loads d17 and starts that player's turn
PICK_NONE = 0x804034C8                       # the picker's epilogue: nobody's turn this frame
STROKE_HOOK = (0x8041344C, 0x39290001)       # addi r9,r9,1: a stroke at the power press (r11 = team record)
PUTT_HOOK = (0x80413474, 0x39290001)         # addi r9,r9,1: a putt
MULLIGAN_HOOK = (0x8041F5A0, 0x3929FFFF)     # addi r9,r9,-1: a mulligan takes the stroke back
SHOT_HOOK = (0x8041F878, 0x807E001C)         # lwz r3,28(r30): the shot's penalty and lie block (r30 = player)
SHOT_DONE = 0x8041F958
AFTER_HOOK = (0x8041F958, 0x3F60804E)        # lis r27,0x804E: right after that block, before the hole-out test
FACE_HOOK = (0x8042E358, 0x9421FFD8)         # stwu r1,-40(r1): FUN_8042e358(record), a face on the score panel
MENU_RUN = 0x804840B0                        # runs a post-shot menu a frame: -1 / -3 while open, then its choice
MENU_HOOK = (0x80404134, 0x4807FF7D)         # bl FUN_804840b0: the scene runs CUR_MENU, and while it is open
                                             # stops there for the frame: nothing else moves
DRAW_HOOK = (0x80406AD8, 0x4807DF59)         # bl FUN_80484a30: the scene's draw queues CUR_MENU's while it is
                                             # open and then draws nothing else (the course isn't drawn)
MENU_DRAW = 0x80484A30
DRAW_QUEUE, MENU_DRAWER, MENU_DRAW_PRIORITY = 0x8001E924, 0x8048497C, 0x804E05E8   # queue(f1 prio, fn, arg, 0x15)
BOX_ALPHA_HOOKS = ((0x80484508, 0x4BBE986D), (0x80484528, 0x4BBE984D))   # bl GXSetTevAlphaIn-raw(0, 0x8FFC0) twice,
TEV_ALPHA_ENV = 0x8006DD74                   # right before the menu's wooden box: alpha = the texture's
TEV_KALPHA_SEL, KSEL_SHADOW = 0x8006D9FC, 0x802DFC70   # GXSetTevKAlphaSel(stage, sel); its register's shadow
BOX_ALPHA_ENV = 0x8F370                      # stage 0 alpha = texture alpha x konst (a 0, b TEXA, c KONST, d 0)
BOX_KASEL = 3                                # GX_TEV_KASEL_5_8: the captain's menu box at 5/8 opacity
CAMERA = 0x802D7E64                          # -> the camera: eye xyz +0, look-at xyz +0xC
CAMERA_VIEW = 0x800179F0                     # (camera): its view and projection matrices
PAD_CSTICK_X, PAD_CSTICK_Y = 0x19, 0x1A      # pad state (player +0x4F14, menu +0x8C): C-stick, s8
MENU_PAD = 0x8C
# the captain's menu camera: orbits the highlighted ball (C-stick left/right turns, up/down zooms)
CAM_TURN = 0.0436                            # radians a frame (2.5 degrees)
CAM_START, CAM_NEAR, CAM_FAR, CAM_ZOOM = 45.0, 12.0, 160.0, 1.5   # feet from the ball
CAM_RISE, CAM_LIFT, CAM_GLIDE = 0.35, 3.0, 0.2          # eye height = distance x rise + lift
CAM_AHEAD, CAM_UP = 0.6, 0.12                            # look-at: distance x these toward the pin, and up
                                                         # (the ball sits low on the screen, under the menu)
OB_TEST, HAZARD_TEST = 0x8041CC34, 0x8041CCBC
HAZARD_DROP, CONGO_DROP = 0x80426F38, 0x8041F31C   # (player, lie) / (lie): where a penalized ball is played from
LIE_SAVE = 0x80414A1C                        # (ball, lie)
DISTANCE = 0x80019DA4                        # (double dx, double dz) -> double
SPRINTF = 0x8001E484                         # (buffer, format, ...)
ALLOC, FREE = 0x8001A670, 0x8001A85C
MENU_INIT = 0x80483564                       # post-shot menu (menu, type, pad); type 2's codes are replaced
MENU_CLEANUP = 0x804841A4
MENU_COUNT, MENU_CURSOR, MENU_CODES = 0x46, 0x40, 0x50   # byte, word, words (codes < 10 can be chosen)
CUR_MENU = 0x804ECE30                        # the post-shot menu the scene runs (and waits on)
TRANSITIONS, SET_TRANSITION, TRANSITION_MENU = 0x80222988, 0x8000F93C, 6
HEADER_CODE = 10                             # a row that can't be chosen: message 0x129 + 10
MSG_OPTION = 0x129
MSG_LOOKUP = 0x80022CD0
MSG_LOOKUP_FIRST = 0x7C60C670                # srawi r0,r3,24

# menu overlay hook sites
CLEAR_SUBLIST = (0x8041D31C, 0x98080A90)     # stb r0,0xA90(r8): doubles flag cleared before any sub-list commit
CLEAR_DIRECT = (0x8041D738, 0x9BBF0A90)      # stb r29,0xA90(r31): the same for modes without a sub-list
COMMIT_HOOK = (0x8041D438, 0x4181009C)       # bgt 0x8041D4D4: Doubles choices past 4 (r9 = choice, r11 = setup)
COMMIT_TABLE, COMMIT_MATCH, COMMIT_TAIL, COMMIT_END = 0x8041D43C, 0x8041D468, 0x8041D4D4, 0x8041DB40
SCREEN_PUSH, COURSE_LIST = 0x80439C1C, 0x80413910
SUBLIST_HOOK = (0x8041CAE4, 0x4E800020)      # blr ending the Doubles case of FUN_8041ca00
SUB_TEX, SUB_HELP = 0x8044C50C, 0x8044C534   # 10 ints each: icon/label texture and help (message 0x22 + value)
SUB_COUNTS = 0x8044617C                      # Doubles' choice count for 1..4 human players (words)
SUB_COUNTS_OLD, SUB_COUNTS_NEW = (5, 5, 5, 5), (9, 11, 12, 12)   # the one-team games from 2 humans, Wolf from 3
CHOICE_BB_MATCH, CHOICE_BB_STROKE, CHOICE_SCRAMBLE, CHOICE_WORST = 5, 6, 7, 8
CHOICE_TEAM, CHOICE_TEAM_WORST, CHOICE_WOLF = 9, 10, 11
# The game keeps a sub-list's icons and help in two arrays of 10 (SUB_TEX, SUB_HELP, back to back); v20's 11
# choices have their own (cave "list"), which the list's three readers load through a pointer (LIST_READERS).
LIST_FILL = (0x8041CA00, 0x3CE08017)         # lis r7,0x8017: FUN_8041ca00's first instruction (fills the arrays)
LIST_READERS = ((0x8041C4C0, 0x393CC50C, "tex_load"), (0x8041C5C4, 0x393CC50C, "tex_load"),   # the icons, labels
                (0x8041DB60, 0x3929C534, "help_load"))                                         # and help line
SUB_COUNT_DOUBLES = 5                        # Doubles' own choices
# v21: the sub-list row lays its icons out at x = 72 i - 36 count + 356 (centred on 320; FUN_8041c2xx, the only
# place): 12 icons ran the end ones' labels off the 16:9 screen, so 11 or more take 60 apart (60 i - 30 count + 350).
ROW_X = (0x8041C3A0, 0x39290164)             # addi r9,r9,356 (r30 = icon, r23 = 0x80450000; cr0 is read after it)
ROW_COUNT = 0x8044C440                       # the row's icon count
ROW_TIGHT, ROW_STEP = 11, 60

ICONS, LABELS = "B/V/V", "B/V/W"             # the sub-lists' 96x96 CMPR icons and IA4 labels (25 each)
FIRST_TEX = 25                               # ours: 25.. in NAMES order
NAMES = ("Best Ball Match", "Best Ball Stroke", "Scramble", "Worst Ball", "Team Scramble", "Team Worst Ball",
         "Wolf")
HELP_IDS = (0x7FE1, 0x7FE2, 0x7FE3, 0x7FEA, 0x7FE4, 0x7FEC, 0x7FEB)  # our help messages, answered by build_mod.py's hook
HELP_TEXTS = (
    b"\x074\x094Two-vs-two match: the best\x01ball on each hole wins it.\x00",
    b"\x074\x094Two-vs-two. Each team counts\x01its best score on every hole.\x00",
    b"\x074\x094Two-vs-two. All hit, then the\x01captain picks the ball.\x00",
    b"\x074\x094Two-vs-two. All hit, then the\x01team plays its worst ball.\x00",
    b"\x074\x094One team: everyone hits, then\x011P picks the ball to play.\x00",
    b"\x074\x094One team: everyone hits, then\x01the team plays its worst ball.\x00",
    b"\x074\x0943-4 players. The Wolf picks a\x01partner, or goes Lone Wolf!\x00",
)
DATA_HELP_KEYS = (0, 1, 2, 4)                # HELP_TEXTS in cave "data" (v16's); the others are in "wtext"
HEADER_TEXT = b"\x075Pick the team's ball:\x00"
# The carousel entry is "Team Play" now (its name banner, B/V/T texture 9, and its help line, message 0x1D), and
# Doubles' own five choices say they are alternate shot.
BANNERS, TEAM_BANNER, TEAM_NAME = "B/V/T", 9, "Team Play"
MSG_TEAM_HELP = 0x14 + 9
TEAM_HELP = b"\x074\x094Best ball, scramble, wolf,\x01alternate shot and more!\x00"
ALT_IDS = (0x7FE5, 0x7FE6, 0x7FE7, 0x7FE8, 0x7FE9)
ALT_TEXTS = tuple(b"\x074\x094Alternate shot, two-vs-two:\x01" + rule + b"\x00" for rule in
                  (b"stroke-play rules.", b"match-play rules.", b"four-slot rules!", b"three-slot rules!",
                   b"skins-match rules."))
LIE_NAMES = ((0x01, b"Fairway"), (0x02, b"Green"), (0x0B, b"Fringe"), (0x0A, b"First Cut"), (0x04, b"Rough"),
             (0x03, b"Bunker"), (0x24, b"Bunker"), (0x05, b"Sand"), (0x07, b"Cart Path"))
LIE_OTHER = b"Rough"
OPTION_TEXT = 52             # bytes per option row we write

# A scramble's best shot: distance to the pin, squared, times these by the lie's surface code (rough and sand
# count as a bit farther than the fairway).
LIE_WEIGHTS = ((1.0, (0x01, 0x02, 0x0B)), (1.21, (0x0A,)), (1.69, (0x04,)), (2.25, (0x03, 0x24)))
LIE_WEIGHT_OTHER = 1.44


def _la(a, reg, addr):
    hi, lo = ppc.hi_lo(addr)
    a(ppc.lis(reg, hi), ppc.addi(reg, reg, lo))


def _lbz_abs(a, reg, addr):
    hi, lo = ppc.hi_lo(addr)
    a(ppc.lis(reg, hi), ppc.lbz(reg, lo, reg))


def _enter(a, size, first):
    """Stack frame of `size` bytes saving LR and r`first`..r31 at its top."""
    a(ppc.stwu(1, -size, 1), ppc.mflr(0), ppc.stw(0, size + 4, 1), ppc.stmw(first, size - 4 * (32 - first), 1))


def _leave(a, size, first):
    a(ppc.lmw(first, size - 4 * (32 - first), 1), ppc.lwz(0, size + 4, 1), ppc.mtlr(0), ppc.addi(1, 1, size), ppc.BLR)


def _player(a, reg, index_reg):
    """reg = player record `index_reg` (reg may equal index_reg; uses r12 when it doesn't)."""
    a(ppc.mulli(reg, index_reg, PLAYER_SIZE))
    hi, lo = ppc.hi_lo(PLAYERS)
    a(ppc.addis(reg, reg, hi), ppc.addi(reg, reg, lo))


def _slot(a, reg, index_reg, d):
    a(ppc.mulli(reg, index_reg, SLOT_SIZE))
    hi, lo = ppc.hi_lo(d["slots"])
    a(ppc.addis(reg, reg, hi), ppc.addi(reg, reg, lo))


def _string(asm, name, text):
    asm.label(name)
    padded = text + b"\x00" * (-len(text) % 4)
    asm(*struct.unpack(f">{len(padded) // 4}I", padded))


def data_block():
    a = ppc.Asm(CAVES["data"][0])
    a.label("weights")
    for w, _ in LIE_WEIGHTS:
        a(struct.unpack(">I", struct.pack(">f", w))[0])
    a(struct.unpack(">I", struct.pack(">f", LIE_WEIGHT_OTHER))[0])
    a.float("third", 1 / 3)
    for name in ("team_mode", "bb_hole", "choose_team", "choose_menu", "choose_default", "menu_open"):
        a.word(name, 0)
    a.label("members")
    a(0)
    a.label("starts")                         # v17: each team's first shooter, the member whose ball it plays
    a(0)
    a.label("slots")
    a(*([0] * (4 * SLOT_SIZE // 4)))
    for k, text in enumerate(HELP_TEXTS):
        if k in DATA_HELP_KEYS:
            _string(a, f"help_{k}", text)
    _string(a, "header", HEADER_TEXT)
    a.word("header_ptr", a.labels["header"])  # the captain's menu header row (v20: the Wolf's menus point it at theirs)
    _string(a, "team_help", TEAM_HELP)
    _string(a, "fmt_yards", b"\x075%s: %d yds, %s\x00")
    _string(a, "fmt_feet", b"\x075%s: %d ft, %s\x00")
    _string(a, "fmt_penalty", b"\x075%s: penalty\x00")
    _string(a, "fmt_player", b"%dP\x00")
    _string(a, "cpu", b"CPU\x00")
    for k, (_, name) in enumerate(LIE_NAMES):
        _string(a, f"lie_{k}", name + b"\x00")
    _string(a, "lie_other", LIE_OTHER + b"\x00")
    a.label("lie_table")                      # (surface code, name) pairs, then -1
    for k, (code, _) in enumerate(LIE_NAMES):
        a(code, a.labels[f"lie_{k}"])
    a(0xFFFFFFFF)
    code = a.assemble()
    t = ppc.Asm(CAVES["text"][0])
    t.label("options")
    t(*([0] * (4 * OPTION_TEXT // 4)))
    t.label("labels")
    t(*([0] * (4 * 8 // 4)))
    # strokes and putts (bl, replaces addi r9,r9,1) and a mulligan (bl, replaces addi r9,r9,-1): in a scramble
    # only each round's first shot counts. Keeps r3, r4, r11; r0, r10, r12 scratch.
    d = a.labels

    def first_test():                         # returns (cr0 eq) when this shot counts
        _la(t, 12, d["team_mode"])
        t(ppc.lwz(12, 0, 12), ppc.cmpwi(12, SCRAMBLE), ppc.BLTLR)
        t(ppc.lis(12, 0x804E), ppc.lbz(10, D17 & 0xFFFF, 12), ppc.lbz(12, D15 & 0xFFFF, 12),
          ppc.divw(0, 10, 12), ppc.mullw(0, 0, 12), ppc.subf(10, 0, 10))   # the shooter's team
        _la(t, 12, d["members"])
        t(ppc.lbzx(10, 12, 10), ppc.cmpwi(10, 0), ppc.BEQLR)
    t.label("stroke")
    t(ppc.addi(9, 9, 1))
    first_test()
    t(ppc.addi(9, 9, -1), ppc.BLR)
    t.label("mulligan")
    t(ppc.addi(9, 9, -1))
    first_test()
    t(ppc.addi(9, 9, 1), ppc.BLR)
    return (code, a.labels), (t.assemble(), t.labels)


def pick_code(d):
    """Scramble: the best shot and taking a shot (cave "pick")."""
    a = ppc.Asm(CAVES["pick"][0])

    a.label("copy_lie")                       # (r3 = to, r4 = from) 0x34 bytes; r0 and ctr
    a(ppc.li(0, LIE_SIZE // 4), ppc.mtctr(0), ppc.addi(3, 3, -4), ppc.addi(4, 4, -4))
    a.label("copy_lie_loop")
    a(ppc.lwzu(0, 4, 4), ppc.stwu(0, 4, 3))
    a.br("bdnz", "copy_lie_loop")
    a(ppc.BLR)

    # best_of(r3 = team, r4 = members who hit) -> r3 = member: holed first, then fewest penalties, then the
    # distance to the pin squared times the lie's weight. f1 = best key.
    a.label("best_of")
    _enter(a, 0x30, 26)
    a(ppc.mr(31, 3), ppc.mr(29, 4), ppc.li(28, 0), ppc.li(27, -1))
    _lbz_abs(a, 30, D15)
    a.label("best_loop")
    a(ppc.mullw(12, 30, 28), ppc.add(12, 12, 31))
    _slot(a, 10, 12, d)
    a(ppc.lbz(0, 0x28, 10), ppc.cmpwi(0, 0))
    a.br("bne", "best_take")
    hi, lo = ppc.hi_lo(PIN_X)
    a(ppc.lis(12, hi), ppc.lfs(3, lo, 12), ppc.lfs(2, 0, 10), ppc.fsubs(2, 2, 3))
    hi, lo = ppc.hi_lo(PIN_Z)
    a(ppc.lis(12, hi), ppc.lfs(3, lo, 12), ppc.lfs(4, 8, 10), ppc.fsubs(4, 4, 3))
    a(ppc.fmuls(2, 2, 2), ppc.fmadds(2, 4, 4, 2))
    a(ppc.lwz(0, 0x2C, 10), ppc.li(9, 4 * len(LIE_WEIGHTS)))
    for k, (_, codes) in enumerate(LIE_WEIGHTS):
        for code in codes:
            a(ppc.cmpwi(0, code))
            a.br("beq", f"weight_{k}")
    a.br("b", "weight_load")
    for k in range(len(LIE_WEIGHTS)):
        a.label(f"weight_{k}")
        a(ppc.li(9, 4 * k))
        a.br("b", "weight_load")
    a.label("weight_load")
    _la(a, 12, d["weights"])
    a(ppc.add(12, 12, 9), ppc.lfs(3, 0, 12), ppc.fmuls(2, 2, 3))
    a(ppc.lbz(9, SLOT_PEN, 10), ppc.cmpwi(27, 0))
    a.br("blt", "best_set")
    a(ppc.cmpw(9, 26))
    a.br("blt", "best_set")
    a.br("bgt", "best_next")
    a(ppc.fcmpu(2, 1))
    a.br("bge", "best_next")
    a.label("best_set")
    a(ppc.mr(27, 28), ppc.mr(26, 9), ppc.fmr(1, 2))
    a.label("best_next")
    a(ppc.addi(28, 28, 1), ppc.cmpw(28, 29))
    a.br("blt", "best_loop")
    a(ppc.mr(3, 27), ppc.cmpwi(3, 0))
    a.br("bge", "best_done")
    a(ppc.li(3, 0))
    a.br("b", "best_done")
    a.label("best_take")
    a(ppc.mr(3, 28))
    a.label("best_done")
    _leave(a, 0x30, 26)

    # take(r3 = team, r4 = member): that member's shot becomes the team's lie; a penalty only now.
    a.label("take")
    _enter(a, 0x20, 29)
    _la(a, 12, d["starts"])
    a(ppc.stbx(4, 12, 3), ppc.mr(31, 3))
    _lbz_abs(a, 12, D15)
    a(ppc.mullw(12, 12, 4), ppc.add(12, 12, 31))
    _slot(a, 30, 12, d)
    _player(a, 29, 31)
    a(ppc.lwz(29, PLAYER_REC, 29), ppc.addi(3, 29, REC_LIE), ppc.mr(4, 30))
    a.br("bl", "copy_lie")
    a(ppc.lbz(0, SLOT_PEN, 30), ppc.stb(0, REC_PENALTY_KIND, 29), ppc.cmpwi(0, 0))
    a.br("beq", "take_reset")
    a(ppc.lbz(12, REC_STROKES, 29), ppc.addi(12, 12, 1), ppc.stb(12, REC_STROKES, 29))
    a.label("take_reset")
    _la(a, 12, d["members"])
    a(ppc.li(0, 0), ppc.stbx(0, 12, 31))
    _leave(a, 0x20, 29)

    return a


def step_code(d, p, m, cam):
    """Scramble: running the captain's menu (start of cave "hooks")."""
    a = ppc.Asm(CAVES["hooks"][0])
    # choose_step(): called by the picker while a team waits for its captain. Opens the menu, or reads the
    # finished one and takes that ball.
    a.label("choose_step")
    _enter(a, 0x20, 28)
    _la(a, 12, d["choose_team"])
    a(ppc.lwz(31, 0, 12), ppc.addi(31, 31, -1))            # r31 = team
    _la(a, 12, d["choose_menu"])
    a(ppc.lwz(30, 0, 12), ppc.cmpwi(30, 0))
    a.br("bne", "choose_read")
    a(ppc.mr(3, 31))
    a.bl(m["choose_open"])
    a(ppc.cmpwi(3, 0))
    a.br("bne", "choose_out")                               # the menu is up
    _la(a, 12, d["choose_default"])                         # nobody to ask: the best shot
    a(ppc.lwz(29, 0, 12))
    a.br("b", "choose_take")
    a.label("choose_read")
    a(ppc.lwz(29, 0, 30), ppc.cmpwi(29, -1))
    a.br("beq", "choose_look")                              # still open
    a(ppc.cmpwi(29, -3))
    a.br("beq", "choose_look")
    a(ppc.mr(3, 30))
    a.bl(MENU_CLEANUP)
    a(ppc.mr(3, 30))
    a.bl(FREE)
    a(ppc.li(0, 0))
    hi, lo = ppc.hi_lo(CUR_MENU)
    a(ppc.lis(12, hi), ppc.stw(0, lo, 12))
    _la(a, 12, d["choose_menu"])
    a(ppc.stw(0, 0, 12))
    _la(a, 12, d["menu_open"])
    a(ppc.stw(0, 0, 12))
    _lbz_abs(a, 12, D16)                                    # a ball's row, or the best shot (B, the header)
    _lbz_abs(a, 11, D15)
    a(ppc.divw(12, 12, 11), ppc.cmpwi(29, 0))
    a.br("blt", "choose_default")
    a(ppc.cmpw(29, 12))
    a.br("blt", "choose_take")
    a.label("choose_default")
    _la(a, 12, d["choose_default"])
    a(ppc.lwz(29, 0, 12))
    a.label("choose_take")
    a(ppc.mr(3, 31), ppc.mr(4, 29))
    a.bl(p["take"])
    _la(a, 12, d["choose_team"])
    a(ppc.li(0, 0), ppc.stw(0, 0, 12))
    a.br("b", "choose_out")
    a.label("choose_look")
    a(ppc.mr(3, 30))
    a.bl(cam["cam_update"])
    a.label("choose_out")
    _leave(a, 0x20, 28)

    return a


def menu_code(d, t):
    """Scramble: the captain's menu, its rows' texts (cave "menu")."""
    a = ppc.Asm(CAVES["menu"][0])
    # choose_open(r3 = team) -> r3 = 1 if the captain's menu is up, 0 if the team has no human.
    a.label("choose_open")
    _enter(a, 0x40, 22)
    a(ppc.mr(31, 3))
    _lbz_abs(a, 30, D15)
    _lbz_abs(a, 29, D16)
    a(ppc.divw(29, 29, 30), ppc.li(28, -1), ppc.li(27, CPU), ppc.li(26, 0))   # r29 = members, r28 = captain
    a.label("captain_loop")
    a(ppc.mullw(25, 30, 26), ppc.add(25, 25, 31))
    _player(a, 24, 25)
    a(ppc.lwz(0, PLAYER_CONTROLLER, 24), ppc.cmpw(0, 27))
    a.br("bge", "captain_next")
    a(ppc.mr(27, 0), ppc.mr(28, 25))
    a.label("captain_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 29))
    a.br("blt", "captain_loop")
    a(ppc.li(3, 0), ppc.cmpwi(28, 0))
    a.br("blt", "open_out")
    # the rows' texts, before the menu makes its text boxes; the buffers are cleared first, since the game's text
    # shows what is left past a shorter string's end ("Green" over "Fairway" read "Greenrway")
    _la(a, 11, t["options"] - 4)
    a(ppc.li(0, 0), ppc.li(12, 4 * OPTION_TEXT // 4), ppc.mtctr(12))
    a.label("text_clear")
    a(ppc.stwu(0, 4, 11))
    a.br("bdnz", "text_clear")
    a(ppc.li(26, 0))
    a.label("text_loop")
    a(ppc.mullw(25, 30, 26), ppc.add(25, 25, 31))           # r25 = record, r24 = player, r23 = slot
    _player(a, 24, 25)
    _slot(a, 23, 25, d)
    a(ppc.lwz(5, PLAYER_CONTROLLER, 24), ppc.cmpwi(5, CPU))
    a.br("bge", "text_cpu")
    _la(a, 3, t["labels"])
    a(ppc.slwi(0, 26, 3), ppc.add(3, 3, 0), ppc.mr(22, 3), ppc.addi(5, 5, 1))
    _la(a, 4, d["fmt_player"])
    a(ppc.CRCLR6)
    a.bl(SPRINTF)
    a.br("b", "text_line")
    a.label("text_cpu")
    _la(a, 22, d["cpu"])
    a.label("text_line")
    _la(a, 3, t["options"])
    a(ppc.mulli(0, 26, OPTION_TEXT), ppc.add(3, 3, 0), ppc.stw(3, 8, 1))
    a(ppc.lbz(0, SLOT_PEN, 23), ppc.cmpwi(0, 0))
    a.br("beq", "text_distance")
    a(ppc.mr(5, 22))
    _la(a, 4, d["fmt_penalty"])
    a(ppc.CRCLR6)
    a.bl(SPRINTF)
    a.br("b", "text_next")
    a.label("text_distance")
    hi, lo = ppc.hi_lo(PIN_X)
    a(ppc.lis(12, hi), ppc.lfs(0, lo, 12), ppc.lfs(1, 0, 23), ppc.fsubs(1, 1, 0))
    hi, lo = ppc.hi_lo(PIN_Z)
    a(ppc.lis(12, hi), ppc.lfs(0, lo, 12), ppc.lfs(2, 8, 23), ppc.fsubs(2, 2, 0))
    a.bl(DISTANCE)                                          # f1 = feet to the pin
    a(ppc.lwz(0, 0x2C, 23), ppc.cmpwi(0, GREEN))
    _la(a, 4, d["fmt_feet"])
    a.br("beq", "text_number")
    _la(a, 12, d["third"])
    a(ppc.lfs(0, 0, 12), ppc.fmuls(1, 1, 0))
    _la(a, 4, d["fmt_yards"])
    a.label("text_number")
    a(ppc.fctiwz(0, 1), ppc.stfd(0, 0x10, 1), ppc.lwz(6, 0x14, 1))
    a(ppc.lwz(0, 0x2C, 23))
    _la(a, 7, d["lie_other"])
    _la(a, 12, d["lie_table"])
    a.label("name_loop")
    a(ppc.lwz(11, 0, 12), ppc.cmpwi(11, -1))
    a.br("beq", "text_print")
    a(ppc.cmpw(11, 0), ppc.addi(12, 12, 8))
    a.br("bne", "name_loop")
    a(ppc.lwz(7, -4, 12))
    a.label("text_print")
    a(ppc.lwz(3, 8, 1), ppc.mr(5, 22), ppc.CRCLR6)
    a.bl(SPRINTF)
    a.label("text_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 29))
    a.br("blt", "text_loop")
    # the menu: a header row, then one row per ball, the best one highlighted; the captain's pad
    a(ppc.li(3, 0x90))
    a.bl(ALLOC)
    a(ppc.mr(26, 3), ppc.li(4, 2))
    _player(a, 12, 28)
    a(ppc.lwz(5, PLAYER_PAD, 12))
    a.bl(MENU_INIT)
    a(ppc.addi(0, 29, 1), ppc.stb(0, MENU_COUNT, 26), ppc.li(0, HEADER_CODE), ppc.stw(0, MENU_CODES, 26))
    a(ppc.li(12, 0), ppc.addi(11, 26, MENU_CODES + 4))
    a.label("codes_loop")
    a(ppc.stw(12, 0, 11), ppc.addi(11, 11, 4), ppc.addi(12, 12, 1), ppc.cmpw(12, 29))
    a.br("blt", "codes_loop")
    _la(a, 12, d["choose_default"])
    a(ppc.lwz(11, 0, 12), ppc.addi(11, 11, 1), ppc.stw(11, MENU_CURSOR, 26))
    hi, lo = ppc.hi_lo(CUR_MENU)
    a(ppc.lis(12, hi), ppc.stw(26, lo, 12))
    _la(a, 12, d["choose_menu"])
    a(ppc.stw(26, 0, 12), ppc.li(0, 1))
    _la(a, 12, d["menu_open"])
    a(ppc.stw(0, 0, 12))
    # (no "menu" screen transition: it freezes the picture behind the menu, and the camera moves behind this one)
    a(ppc.li(3, 1))
    a.label("open_out")
    _leave(a, 0x40, 22)
    return a


def cam_code(d):
    """The captain's menu camera (cave "cam"): flies to the highlighted ball, which the team's ball moves to, and
    orbits it with the C-stick. The menu doesn't stop the scene (the game's own menus do, and the scene then isn't
    drawn), so the camera is written after the game's and its view is rebuilt."""
    import math
    a = ppc.Asm(CAVES["cam"][0])
    for name, value in (("cos", math.cos(CAM_TURN)), ("sin", math.sin(CAM_TURN)),
                        ("start", CAM_START), ("near", CAM_NEAR), ("far", CAM_FAR), ("zoom", CAM_ZOOM),
                        ("rise", CAM_RISE), ("lift", CAM_LIFT), ("ahead", CAM_AHEAD), ("up", CAM_UP), ("glide", CAM_GLIDE)):
        a.float(name, value)
    a.word("member", -1)
    a.word("menu", 0)
    a.float("dir_x", 0.0)
    a.float("dir_z", 1.0)
    a.float("dist", CAM_START)

    def f(reg, name):                         # r26 = this cave's data
        a(ppc.lfs(reg, a.labels[name] - CAVES["cam"][0], 26))

    def fst(reg, name):
        a(ppc.stfs(reg, a.labels[name] - CAVES["cam"][0], 26))

    a.label("cam_update")                     # (r3 = the captain's menu), every frame it is up
    _enter(a, 0x30, 26)
    _la(a, 26, CAVES["cam"][0])
    a(ppc.mr(31, 3))
    off = lambda name: a.labels[name] - CAVES["cam"][0]
    a(ppc.lwz(0, off("menu"), 26), ppc.cmpw(0, 31), ppc.stw(31, off("menu"), 26))   # a new menu: start over
    a.br("beq", "cam_same_menu")
    a(ppc.li(0, -1), ppc.stw(0, off("member"), 26))
    a.label("cam_same_menu")
    a(ppc.lwz(29, MENU_CURSOR, 31), ppc.addi(29, 29, -1), ppc.cmpwi(29, 0))   # r29 = highlighted member
    a.br("bge", "cam_member")
    _la(a, 12, d["choose_default"])
    a(ppc.lwz(29, 0, 12))
    a.label("cam_member")
    hi, lo = ppc.hi_lo(d["team_mode"])         # v20: the Wolf's menu looks at one ball, its candidate's (slot 0's
    a(ppc.lis(12, hi), ppc.lwz(12, lo, 12), ppc.cmpwi(12, WOLF))   # place: the candidate's own slot)
    a.br("bne", "cam_team")
    a(ppc.li(29, 0))
    a.label("cam_team")
    _la(a, 12, d["choose_team"])
    a(ppc.lwz(28, 0, 12), ppc.addi(28, 28, -1))
    _lbz_abs(a, 12, D15)
    a(ppc.mullw(12, 12, 29), ppc.add(12, 12, 28))
    _slot(a, 27, 12, d)                       # r27 = its slot
    a(ppc.lwz(0, off("member"), 26), ppc.cmpw(0, 29), ppc.stw(29, off("member"), 26))
    a.br("beq", "cam_steer")
    _player(a, 11, 28)                        # another ball: the team's ball goes there, the view starts behind it
    a(ppc.lwz(11, PLAYER_BALL, 11))
    for off in (0, 4, 8):
        a(ppc.lwz(0, off, 27), ppc.stw(0, 0x9C + off, 11))
    hi, lo = ppc.hi_lo(PIN_X)
    a(ppc.lis(12, hi), ppc.lfs(0, lo, 12), ppc.lfs(1, 0, 27), ppc.fsubs(1, 1, 0), ppc.stfs(1, 8, 1))
    hi, lo = ppc.hi_lo(PIN_Z)
    a(ppc.lis(12, hi), ppc.lfs(0, lo, 12), ppc.lfs(2, 8, 27), ppc.fsubs(2, 2, 0), ppc.stfs(2, 12, 1))
    a.bl(DISTANCE)                            # (a ball in the menu is never on the pin)
    a(ppc.lfs(2, 8, 1), ppc.lfs(3, 12, 1), ppc.fdivs(2, 2, 1), ppc.fdivs(3, 3, 1))
    fst(2, "dir_x")
    fst(3, "dir_z")
    f(0, "start")
    fst(0, "dist")
    a.label("cam_steer")                      # C-stick: left/right turns round the ball, up/down zooms
    a(ppc.lwz(11, MENU_PAD, 31), ppc.lbz(0, PAD_CSTICK_X, 11), ppc.extsb(0, 0), ppc.cmpwi(0, 30))
    f(5, "sin")
    a.br("bgt", "cam_turn")
    a(ppc.cmpwi(0, -30))
    a.br("bge", "cam_zoom")
    a(ppc.fneg(5, 5))
    a.label("cam_turn")
    f(4, "cos")
    f(2, "dir_x")
    f(3, "dir_z")
    a(ppc.fmuls(6, 2, 4), ppc.fmuls(7, 3, 5), ppc.fsubs(6, 6, 7))          # x cos - z sin
    a(ppc.fmuls(7, 2, 5), ppc.fmadds(7, 3, 4, 7))                          # x sin + z cos
    fst(6, "dir_x")
    fst(7, "dir_z")
    a.label("cam_zoom")
    a(ppc.lwz(11, MENU_PAD, 31), ppc.lbz(0, PAD_CSTICK_Y, 11), ppc.extsb(0, 0))
    f(1, "dist")
    f(2, "zoom")
    a(ppc.cmpwi(0, 30))
    a.br("ble", "cam_zoom_out")
    a(ppc.fsubs(1, 1, 2))
    f(3, "near")
    a(ppc.fcmpu(1, 3))
    a.br("bge", "cam_zoom_set")
    a(ppc.fmr(1, 3))
    a.br("b", "cam_zoom_set")
    a.label("cam_zoom_out")
    a(ppc.cmpwi(0, -30))
    a.br("bge", "cam_zoom_set")
    a(ppc.fadds(1, 1, 2))
    f(3, "far")
    a(ppc.fcmpu(1, 3))
    a.br("ble", "cam_zoom_set")
    a(ppc.fmr(1, 3))
    a.label("cam_zoom_set")
    fst(1, "dist")
    # targets: eye = ball + dir x dist, raised dist x rise + lift; look-at = ball - dir x dist x ahead, raised
    # dist x up (dir points from the pin to the ball)
    f(2, "dir_x")
    f(3, "dir_z")
    a(ppc.lfs(4, 0, 27), ppc.fmadds(8, 2, 1, 4))                           # eye x
    a(ppc.lfs(4, 8, 27), ppc.fmadds(10, 3, 1, 4))                          # eye z
    f(5, "ahead")
    a(ppc.fmuls(5, 5, 1), ppc.lfs(4, 0, 27), ppc.fmuls(6, 2, 5), ppc.fsubs(11, 4, 6))   # look-at x
    a(ppc.lfs(4, 8, 27), ppc.fmuls(6, 3, 5), ppc.fsubs(13, 4, 6))                      # look-at z
    f(2, "rise")
    f(3, "lift")
    a(ppc.lfs(4, 4, 27), ppc.fmadds(9, 1, 2, 3), ppc.fadds(9, 9, 4))       # eye y
    f(2, "up")
    a(ppc.fmadds(12, 1, 2, 4))                                             # look-at y
    f(0, "glide")
    hi, lo = ppc.hi_lo(CAMERA)
    a(ppc.lis(11, hi), ppc.lwz(11, lo, 11))
    for k, target in enumerate((8, 9, 10, 11, 12, 13)):                    # glide there
        a(ppc.lfs(1, 4 * k, 11), ppc.fsubs(2, target, 1), ppc.fmadds(1, 2, 0, 1), ppc.stfs(1, 4 * k, 11))
    a(ppc.mr(3, 11))
    a.bl(CAMERA_VIEW)                         # the scene, which would, waits while a menu is up
    _leave(a, 0x30, 26)
    return a


def best_code(d, x):
    """Best Ball: whose turn it is and loading them into the team record (cave "choose"); saving them after the
    shot (cave "after")."""
    a = ppc.Asm(CAVES["choose"][0])

    # bb_choose(): r3 = record to play (the member with tee shots first, then off the green, then the
    # farthest from the pin), loaded into its team's record. New hole: everyone starts from the team's lie.
    a.label("bb_choose")
    _enter(a, 0x30, 24)
    _lbz_abs(a, 30, D15)
    _lbz_abs(a, 29, D16)
    _lbz_abs(a, 12, HOLE_INDEX)
    _la(a, 11, d["bb_hole"])
    a(ppc.lwz(0, 0, 11), ppc.cmpw(0, 12))
    a.br("beq", "bb_find")
    a(ppc.stw(12, 0, 11), ppc.li(28, 0))
    a.label("bb_reset")
    a(ppc.divw(12, 28, 30), ppc.mullw(12, 12, 30), ppc.subf(12, 12, 28))   # team
    _player(a, 4, 12)
    a(ppc.lwz(4, PLAYER_REC, 4), ppc.addi(4, 4, REC_LIE))
    _slot(a, 3, 28, d)
    a(ppc.mr(27, 3))
    a.bl(x["copy_lie"])
    a(ppc.li(0, 0), ppc.stb(0, SLOT_STROKES, 27), ppc.stb(0, SLOT_DONE, 27), ppc.addi(28, 28, 1), ppc.cmpw(28, 29))
    a.br("blt", "bb_reset")
    a.label("bb_find")
    a(ppc.li(28, 0), ppc.li(31, -1), ppc.li(25, -1))        # r31 = best record, r25 = its priority, f1 = distance
    a.label("bb_loop")
    a(ppc.divw(12, 28, 30), ppc.mullw(12, 12, 30), ppc.subf(26, 12, 28))   # r26 = team
    _player(a, 12, 26)
    a(ppc.lwz(12, PLAYER_REC, 12), ppc.lbz(0, REC_STATUS, 12), ppc.cmpwi(0, 0))
    a.br("bne", "bb_next")                                  # the team is done
    _slot(a, 27, 28, d)
    a(ppc.lbz(0, SLOT_DONE, 27), ppc.cmpwi(0, 0))
    a.br("bne", "bb_next")
    a(ppc.li(24, 2), ppc.lbz(0, SLOT_STROKES, 27), ppc.cmpwi(0, 0))
    a.br("beq", "bb_priority")
    a(ppc.li(24, 1), ppc.lwz(0, 0x2C, 27), ppc.cmpwi(0, GREEN))
    a.br("bne", "bb_priority")
    a(ppc.li(24, 0))
    a.label("bb_priority")
    hi, lo = ppc.hi_lo(PIN_X)
    a(ppc.lis(12, hi), ppc.lfs(3, lo, 12), ppc.lfs(2, 0, 27), ppc.fsubs(2, 2, 3))
    hi, lo = ppc.hi_lo(PIN_Z)
    a(ppc.lis(12, hi), ppc.lfs(3, lo, 12), ppc.lfs(4, 8, 27), ppc.fsubs(4, 4, 3))
    a(ppc.fmuls(2, 2, 2), ppc.fmadds(2, 4, 4, 2), ppc.cmpw(24, 25))
    a.br("bgt", "bb_set")
    a.br("blt", "bb_next")
    a(ppc.fcmpu(2, 1))
    a.br("ble", "bb_next")
    a.label("bb_set")
    a(ppc.mr(31, 28), ppc.mr(25, 24), ppc.fmr(1, 2))
    a.label("bb_next")
    a(ppc.addi(28, 28, 1), ppc.cmpw(28, 29))
    a.br("blt", "bb_loop")
    a(ppc.mr(3, 31), ppc.cmpwi(31, 0))
    a.br("blt", "bb_out")
    a(ppc.divw(12, 31, 30), ppc.mullw(26, 12, 30), ppc.subf(26, 26, 31))   # r26 = team, r12 = member
    a(ppc.li(0, 0), ppc.cmpwi(12, 0))
    a.br("beq", "bb_face")
    a(ppc.li(0, 1))
    a.label("bb_face")
    _player(a, 29, 26)
    a(ppc.lwz(29, PLAYER_REC, 29), ppc.stb(0, REC_TOGGLE, 29))
    _slot(a, 27, 31, d)
    a(ppc.lbz(0, SLOT_STROKES, 27), ppc.stb(0, REC_STROKES, 29), ppc.addi(3, 29, REC_LIE), ppc.mr(4, 27))
    a.bl(x["copy_lie"])
    a(ppc.mr(3, 31))
    a.label("bb_out")
    _leave(a, 0x30, 24)
    choose = a
    a = ppc.Asm(CAVES["after"][0])

    # bb_after(r3 = player): the shot's lie and strokes back to its slot; the team record then shows the team:
    # once a holed score can't be beaten by a teammate still playing (strokes + 1 >= it), that score and a lie
    # in the hole (the game ends the team's hole); else the fewest strokes still playing and a lie out of it.
    a.label("bb_after")
    _enter(a, 0x30, 24)
    a(ppc.lwz(31, PLAYER_INDEX, 3), ppc.lwz(30, PLAYER_REC, 3))
    _slot(a, 29, 31, d)
    a(ppc.mr(3, 29), ppc.addi(4, 30, REC_LIE))
    a.bl(x["copy_lie"])
    a(ppc.lbz(0, REC_STROKES, 30), ppc.stb(0, SLOT_STROKES, 29), ppc.lbz(0, 0x28, 29), ppc.stb(0, SLOT_DONE, 29))
    _lbz_abs(a, 28, D15)
    _lbz_abs(a, 27, D16)
    a(ppc.divw(12, 31, 28), ppc.mullw(12, 12, 28), ppc.subf(26, 12, 31))   # r26 = team, start record
    a(ppc.li(25, 99), ppc.li(24, 99), ppc.li(11, -1))       # r25 = best holed, r24 = fewest playing, r11 its slot
    a.label("bb_sum")
    _slot(a, 10, 26, d)
    a(ppc.lbz(9, SLOT_STROKES, 10), ppc.lbz(0, SLOT_DONE, 10), ppc.cmpwi(0, 0))
    a.br("beq", "bb_playing")
    a(ppc.cmpw(9, 25))
    a.br("bge", "bb_sum_next")
    a(ppc.mr(25, 9), ppc.mr(11, 10))
    a.br("b", "bb_sum_next")
    a.label("bb_playing")
    a(ppc.cmpw(9, 24))
    a.br("bge", "bb_sum_next")
    a(ppc.mr(24, 9))
    a.label("bb_sum_next")
    a(ppc.add(26, 26, 28), ppc.cmpw(26, 27))
    a.br("blt", "bb_sum")
    a(ppc.cmpwi(25, 99))
    a.br("bge", "bb_open")                                  # nobody has holed (r11 is an address: test r25)
    a(ppc.addi(0, 24, 1), ppc.cmpw(0, 25))
    a.br("blt", "bb_open")                                  # a teammate can still beat it
    a(ppc.stb(25, REC_STROKES, 30), ppc.addi(3, 30, REC_LIE), ppc.mr(4, 11))
    a.bl(x["copy_lie"])
    a.br("b", "bb_after_out")
    a.label("bb_open")
    a(ppc.stb(24, REC_STROKES, 30), ppc.li(0, 0), ppc.stb(0, REC_LIE + 0x28, 30))
    a.label("bb_after_out")
    _leave(a, 0x30, 24)

    # The captain's menu drawer (queued by menu_draw): the game's, with the wooden box see-through.
    a.word("glass", 0)
    a.label("glass_draw")
    _enter(a, 0x10, 30)
    a(ppc.mr(31, 3))
    hi, lo = ppc.hi_lo(KSEL_SHADOW)
    a(ppc.lis(12, hi), ppc.lwz(30, lo, 12), ppc.li(3, 0), ppc.li(4, BOX_KASEL))
    a.bl(TEV_KALPHA_SEL)
    a(ppc.li(0, 1))
    a.la(12, "glass")
    a(ppc.stw(0, 0, 12), ppc.mr(3, 31))
    a.bl(MENU_DRAWER)
    a(ppc.li(0, 0))
    a.la(12, "glass")
    a(ppc.stw(0, 0, 12), ppc.li(3, 0), ppc.rlwinm(4, 30, 23, 27, 31))   # the stage's old konst alpha
    a.bl(TEV_KALPHA_SEL)
    _leave(a, 0x10, 30)
    a.label("glass_env")                      # (bl from BOX_ALPHA_HOOKS) the box's alpha, while ours is drawn
    a.la(12, "glass")
    a(ppc.lwz(12, 0, 12), ppc.cmpwi(12, 0))
    a.br("beq", "glass_env_game")
    a(ppc.lis(4, BOX_ALPHA_ENV >> 16), ppc.ori(4, 4, BOX_ALPHA_ENV & 0xFFFF))
    a.label("glass_env_game")
    a.b(TEV_ALPHA_ENV)
    return choose, a


def hooks_code(d, x, b, at, w):
    """The hooks themselves (cave "hooks", after the menu runner at `at`); `w` = the v20 caves' labels."""
    a = ppc.Asm(at)

    # -- round setup: replaces stb r0,0xD16(r31). r30 = setup block, r31 = golf state, cr0 = "not doubles"
    # (the beq right after skips halving the side count); keep cr0 unless we decide the side count ourselves.
    a.label("setup")
    a(ppc.stb(0, STATE_D16, 31), ppc.mfcr(12), ppc.mflr(10))
    a.bl(w["wolf_reset"])                     # (keeps r0, r10, r12)
    a(ppc.mtlr(10), ppc.lbz(11, MODE_BYTE, 30), ppc.cmpwi(11, TEAM_WORST))
    a.br("bne", "setup_mode")
    a(ppc.li(11, WORST))                      # (Team Worst Ball: Worst Ball with one side)
    a.label("setup_mode")
    _la(a, 10, d["team_mode"])
    a(ppc.stw(11, 0, 10), ppc.li(9, -1))      # (r0 is the player count the game halves next: keep it)
    _la(a, 10, d["bb_hole"])
    a(ppc.stw(9, 0, 10), ppc.li(9, 0))
    _la(a, 10, d["choose_team"])
    a(ppc.stw(9, 0, 10))
    _la(a, 10, d["choose_menu"])
    a(ppc.stw(9, 0, 10))
    _la(a, 10, d["menu_open"])
    a(ppc.stw(9, 0, 10))
    _la(a, 10, d["starts"])
    a(ppc.stw(9, 0, 10), ppc.lbz(9, MODE_BYTE, 30), ppc.cmpwi(9, TEAM_WORST))
    a.br("beq", "setup_team")
    a(ppc.cmpwi(11, TEAM_SCRAMBLE))
    a.br("beq", "setup_team")
    a(ppc.mtcrf(0xFF, 12), ppc.BLR)
    a.label("setup_team")                     # one shared ball: doubles on, one side
    a(ppc.li(11, 1), ppc.stb(11, STATE_DOUBLES, 31), ppc.stb(11, STATE_D15, 31), ppc.mtcrf(0xFF, 12),
      ppc.cmpw(0, 0), ppc.BLR)

    # -- shooter pick, Doubles part (b from PICK_HOOK): r3 = team, r31 = golf state.
    a.label("pick")
    _la(a, 12, d["team_mode"])
    a(ppc.lwz(12, 0, 12), ppc.cmpwi(12, BEST_BALL))
    a.br("beq", "pick_best")
    a(ppc.cmpwi(12, SCRAMBLE))
    a.br("bge", "pick_scramble")
    a(PICK_HOOK[1])
    a.b(PICK_HOOK[0] + 4)
    a.label("pick_best")
    a.bl(b["bb_choose"])
    a(ppc.cmpwi(3, 0))
    a.br("blt", "pick_none")
    a(ppc.stb(3, STATE_D17, 31))
    a.b(PICK_DONE)
    a.label("pick_scramble")                  # a team waiting for its captain goes first: nobody plays meanwhile
    _la(a, 12, d["choose_team"])
    a(ppc.lwz(12, 0, 12), ppc.cmpwi(12, 0))
    a.br("beq", "pick_member")
    a.bl(x["choose_step"])
    a.label("pick_none")
    a(ppc.li(0, -1), ppc.stb(0, STATE_D17, 31))
    a.b(PICK_NONE)
    a.label("pick_member")                    # record team + d15 x member, member 0 when the team starts a hole
    _player(a, 9, 3)
    a(ppc.lwz(9, PLAYER_REC, 9))
    _la(a, 10, d["members"])
    a(ppc.lbzx(11, 10, 3), ppc.lbz(12, REC_STROKES, 9), ppc.cmpwi(12, 0))
    a.br("bne", "pick_rotate")
    a(ppc.li(11, 0), ppc.stbx(11, 10, 3))
    a.label("pick_rotate")                    # from the member whose ball the team plays, round in order
    _la(a, 10, d["starts"])
    a(ppc.lbzx(12, 10, 3), ppc.add(11, 11, 12), ppc.lbz(12, STATE_D16, 31), ppc.lbz(10, STATE_D15, 31),
      ppc.divw(12, 12, 10), ppc.divw(10, 11, 12), ppc.mullw(10, 10, 12), ppc.subf(11, 10, 11))
    a(ppc.lbz(12, STATE_D15, 31), ppc.mullw(12, 12, 11), ppc.add(12, 12, 3), ppc.stb(12, STATE_D17, 31))
    a(ppc.li(12, 0), ppc.cmpwi(11, 0))
    a.br("beq", "pick_face")
    a(ppc.li(12, 1))
    a.label("pick_face")                      # the HUD's big face: the lead, or a partner
    a(ppc.stb(12, REC_TOGGLE, 9))
    a.b(PICK_DONE)

    # -- after a shot (b from SHOT_HOOK): r30 = player. Not a scramble: the game's own penalty and lie code.
    a.label("shot")
    _la(a, 12, d["team_mode"])
    a(ppc.lwz(12, 0, 12), ppc.cmpwi(12, SCRAMBLE))
    a.br("blt", "shot_game")
    a(ppc.cmpwi(12, WOLF))                    # (Wolf: everyone plays their own ball, the game's way)
    a.br("bne", "shot_scramble")
    a.label("shot_game")
    a(SHOT_HOOK[1])
    a.b(SHOT_HOOK[0] + 4)
    a.label("shot_scramble")
    a(ppc.stwu(1, -0x40, 1), ppc.stmw(24, 0x10, 1))
    a(ppc.lwz(29, PLAYER_REC, 30), ppc.lwz(28, PLAYER_BALL, 30), ppc.lwz(25, PLAYER_INDEX, 30))
    _slot(a, 27, 25, d)
    a(ppc.mr(3, 28))
    a.bl(OB_TEST)
    a(ppc.cmpwi(3, 0))
    a.br("beq", "shot_hazard")
    a(ppc.li(0, 2), ppc.stb(0, REC_PENALTY_KIND, 29))      # out of bounds: played again from the team's lie
    a(ppc.mr(3, 27), ppc.addi(4, 29, REC_LIE))
    a.bl(x["copy_lie"])
    a(ppc.li(0, 1), ppc.stb(0, SLOT_PEN, 27))
    _lbz_abs(a, 12, COURSE)
    a(ppc.cmpwi(12, 7))
    a.br("beq", "shot_congo")
    a.br("b", "shot_kept")
    a.label("shot_hazard")
    a(ppc.mr(3, 28))
    a.bl(HAZARD_TEST)
    a(ppc.cmpwi(3, 0))
    a.br("beq", "shot_clean")
    a(ppc.li(0, 1), ppc.stb(0, REC_PENALTY_KIND, 29), ppc.stb(0, SLOT_PEN, 27))   # water and the like: a drop
    a(ppc.mr(3, 27), ppc.addi(4, 29, REC_LIE))
    a.bl(x["copy_lie"])
    _lbz_abs(a, 12, COURSE)
    a(ppc.cmpwi(12, 7))
    a.br("beq", "shot_congo")
    a(ppc.mr(3, 30), ppc.mr(4, 27))
    a.bl(HAZARD_DROP)
    a.br("b", "shot_kept")
    a.label("shot_congo")                     # the side-games course drops its own way, as the game does
    a(ppc.mr(3, 27))
    a.bl(CONGO_DROP)
    a.br("b", "shot_kept")
    a.label("shot_clean")
    a(ppc.mr(3, 28), ppc.mr(4, 27))
    a.bl(LIE_SAVE)
    a(ppc.li(0, 0), ppc.stb(0, SLOT_PEN, 27))
    a.label("shot_kept")                      # r31 = team, r24 = d15, r11 = members who have hit
    _lbz_abs(a, 24, D15)
    a(ppc.divw(11, 25, 24), ppc.mullw(11, 11, 24), ppc.subf(31, 11, 25))
    _la(a, 26, d["members"])
    a(ppc.lbzx(11, 26, 31), ppc.addi(11, 11, 1), ppc.stbx(11, 26, 31))
    _la(a, 12, d["team_mode"])                # (Worst Ball: a holed ball waits for the others)
    a(ppc.lwz(12, 0, 12), ppc.cmpwi(12, WORST))
    a.br("beq", "shot_more")
    a(ppc.lbz(0, 0x28, 27), ppc.cmpwi(0, 0))
    a.br("beq", "shot_more")
    a(ppc.divw(4, 25, 24), ppc.mr(3, 31))                   # in the hole: the holer's ball, now
    a.bl(x["take"])
    a.br("b", "shot_out")
    a.label("shot_more")
    _lbz_abs(a, 12, D16)
    a(ppc.divw(12, 12, 24), ppc.cmpw(11, 12))
    a.br("blt", "shot_out")
    a(ppc.mr(3, 31), ppc.mr(4, 11))                         # everyone has hit: the captain picks (Worst Ball:
    a.bl(w["all_hit"])                                      # the worst ball, now)
    a.label("shot_out")
    a(ppc.lmw(24, 0x10, 1), ppc.addi(1, 1, 0x40))
    a.b(SHOT_DONE)

    # -- right after the penalty/lie block (b from AFTER_HOOK): Best Ball keeps the shooter's ball in its slot
    a.label("after")
    _la(a, 12, d["team_mode"])
    a(ppc.lwz(12, 0, 12), ppc.cmpwi(12, BEST_BALL))
    a.br("bne", "after_game")
    a(ppc.mr(3, 30))
    a.bl(b["bb_after"])
    a.label("after_game")
    a(AFTER_HOOK[1])
    a.b(AFTER_HOOK[0] + 4)

    # -- score panel face (b from FACE_HOOK, r3 = record): a team of 3 or 4 has room for two faces, the lead's
    # and a partner's; the partner's is whoever is up when it isn't the lead.
    a.label("face")
    _la(a, 12, d["team_mode"])
    a(ppc.lwz(12, 0, 12), ppc.cmpwi(12, SCRAMBLE))   # (one team: Team Scramble, Team Worst Ball)
    a.br("blt", "face_game")
    a(ppc.lis(12, 0x804E), ppc.lbz(11, D15 & 0xFFFF, 12), ppc.cmpwi(11, 1))
    a.br("bne", "face_game")
    a(ppc.cmpw(3, 11))
    a.br("blt", "face_game")
    a(ppc.lbz(12, D17 & 0xFFFF, 12), ppc.cmpw(12, 11))
    a.br("blt", "face_game")
    a(ppc.cmpwi(12, 4))
    a.br("bge", "face_game")
    a(ppc.mr(3, 12))
    a.label("face_game")
    a(FACE_HOOK[1])
    a.b(FACE_HOOK[0] + 4)

    # -- the scene's menu call (bl from MENU_HOOK, r3 = CUR_MENU): for the captain's menu, "not open", so the
    # scene goes on (and is drawn) while the picker reads the menu's own value
    a.label("menu_scene")
    _enter(a, 0x10, 31)
    a(ppc.mr(31, 3))
    a.bl(MENU_RUN)
    _la(a, 12, d["choose_menu"])
    a(ppc.lwz(0, 0, 12), ppc.cmpw(0, 31))
    a.br("bne", "menu_scene_out")
    a(ppc.li(3, 0))
    a.label("menu_scene_out")
    _leave(a, 0x10, 31)

    # -- the scene's draw (bl from DRAW_HOOK, r3 = CUR_MENU): the captain's menu is drawn over the course
    a.label("menu_draw")
    _enter(a, 0x10, 31)
    a(ppc.mr(31, 3))
    _la(a, 12, d["choose_menu"])
    a(ppc.lwz(0, 0, 12), ppc.cmpw(0, 31))
    a.br("bne", "menu_draw_game")
    a(ppc.lwz(0, 0, 31), ppc.cmpwi(0, -1))
    a.br("bne", "menu_draw_none")
    hi, lo = ppc.hi_lo(MENU_DRAW_PRIORITY)
    a(ppc.lis(12, hi), ppc.lfs(1, lo, 12))
    _la(a, 3, b["glass_draw"])
    a(ppc.mr(4, 31), ppc.li(5, 0x15))
    a.bl(DRAW_QUEUE)
    a.label("menu_draw_none")
    a(ppc.li(3, 0))
    a.br("b", "menu_draw_out")
    a.label("menu_draw_game")
    a.bl(MENU_DRAW)
    a.label("menu_draw_out")
    _leave(a, 0x10, 31)

    # -- message lookup, after build_mod.py's own (b from cave 3): the captain's menu rows while it is up
    a.label("messages")
    _la(a, 12, d["menu_open"])
    a(ppc.lwz(0, 0, 12), ppc.cmpwi(0, 0))
    a.br("beq", "messages_game")
    a(ppc.cmpwi(3, MSG_OPTION + HEADER_CODE))
    a.br("bne", "messages_row")
    hi, lo = ppc.hi_lo(d["header_ptr"])
    a(ppc.lis(3, hi), ppc.lwz(3, lo, 3), ppc.BLR)
    a.label("messages_row")
    a(ppc.addi(12, 3, -MSG_OPTION), ppc.cmplwi(12, 4))
    a.br("bge", "messages_game")
    a(ppc.mulli(12, 12, OPTION_TEXT))
    _la(a, 3, x["_options"])
    a(ppc.add(3, 3, 12), ppc.BLR)
    a.label("messages_game")
    a(MSG_LOOKUP_FIRST)
    a.b(MSG_LOOKUP + 4)

    # -- menus (B/U/C). Clearing the doubles flag clears our byte too (bl; r0 / r29 = 0, cr0 untouched).
    a.label("clear_sublist")
    a(ppc.stb(0, 0xA90, 8), ppc.stb(0, MODE_BYTE, 8), ppc.BLR)
    a.label("clear_direct")
    a(ppc.stb(29, 0xA90, 31), ppc.stb(29, MODE_BYTE, 31), ppc.BLR)
    # Doubles choices (b from COMMIT_HOOK): cr0 = choice vs 4, r9 = choice, r11 = setup block, r6 = its page.
    a.label("commit")
    a.br("bgt", "commit_ours")
    a.b(COMMIT_TABLE)
    a.label("commit_ours")
    a(ppc.cmpwi(9, CHOICE_TEAM))
    a.br("beq", "commit_team")
    a(ppc.cmpwi(9, CHOICE_TEAM_WORST))
    a.br("beq", "commit_team_worst")
    a(ppc.cmpwi(9, CHOICE_WOLF))
    a.br("bne", "commit_teams")
    a.b(w["commit_wolf"])
    a.label("commit_teams")
    a(ppc.li(0, WORST), ppc.cmpwi(9, CHOICE_WORST))
    a.br("beq", "commit_on")
    a(ppc.li(0, SCRAMBLE), ppc.cmpwi(9, CHOICE_SCRAMBLE))
    a.br("beq", "commit_on")
    a(ppc.li(0, BEST_BALL), ppc.stb(0, MODE_BYTE, 11), ppc.cmpwi(9, CHOICE_BB_MATCH))
    a.br("bne", "commit_tail")
    a.b(COMMIT_MATCH)                         # Doubles' own Match Play case: mode 1, sub-mode 2
    a.label("commit_on")
    a(ppc.stb(0, MODE_BYTE, 11))
    a.label("commit_tail")                    # stroke rules: mode 0 is already set
    a.b(COMMIT_TAIL)
    a.label("commit_team_worst")
    a(ppc.li(0, TEAM_WORST))
    a.br("b", "commit_team_on")
    a.label("commit_team")                    # one team of everyone: a plain stroke game, straight to the course
    a(ppc.li(0, TEAM_SCRAMBLE))
    a.label("commit_team_on")
    a(ppc.stb(0, MODE_BYTE, 11), ppc.li(3, 3))
    a.bl(SCREEN_PUSH)
    a.bl(COURSE_LIST)
    a.b(COMMIT_END)
    return a


def extra_code():
    """Doubles' own choices' help texts: alternate shot (cave "extra"); v21 the row's spacing for long lists."""
    a = ppc.Asm(CAVES["extra"][0])
    for k, text in enumerate(ALT_TEXTS):
        _string(a, f"alt_{k}", text)
    a.label("row_x")                          # (bl from ROW_X) r9 = 72 i - 36 count: the icon's x, less 356
    a(ppc.lwz(12, ROW_COUNT - 0x80450000, 23), 0x2C800000 | 12 << 16 | ROW_TIGHT)   # cmpwi cr1,r12,ROW_TIGHT
    a(0x41840000 | 4 * 6)                     # blt cr1, row_x_game (cr0 is the caller's)
    a(ppc.mulli(9, 30, ROW_STEP), ppc.mulli(12, 12, ROW_STEP // 2), ppc.subf(9, 12, 9),
      ppc.addi(9, 9, 320 + ROW_STEP // 2), ppc.BLR)
    a.label("row_x_game")
    a(ROW_X[1], ppc.BLR)
    return a


# ---- v20: Worst Ball (2v2, every member hits, the team plays its worst ball) and Wolf (3 or 4 players, each with
# their own ball; the Wolf of each hole tees off last and, after each other player's drive, takes them as a partner
# or not; nobody taken = the Lone Wolf. The game's Skins round underneath, with its scoring swapped for the Wolf's
# points, so the score panel, the hole-end scorecard and the results show them; RE-NOTES "Team games")

STATE_SUB_MODE = 0x804E66BC                  # the round's sub-mode word (3 Skins; the Wolf's scoring runs as 0)
REC_HONOR, PLAYER_CARD = 0x1C1, 0x14         # record: tee order (lowest first); player: its scorecard (hole x 8)
SKINS_POT, SKINS_TOTALS = 0x80523FF8, 0x80523FFC   # the Skins scorecard's carried skins and each player's total
PICKER = (0x80402F1C, 0x9421FFA8)            # stwu r1,-88(r1): FUN_80402f1c(state), the shooter pick
SCORE = (0x8046A0B8, 0x9421FFE8)             # stwu r1,-24(r1): FUN_8046a0b8(side), scoring after a shot
POINTS_GET = (0x80469720, 0x9421FFD8)        # stwu r1,-40(r1): FUN_80469720(player), the panel's/results' score
TOTALS = ((0x80472FD4, 0x80140A84), (0x8047362C, 0x80140A84))   # lwz r0,0xA84(r20): after the scorecards' totals
TIE = (0x80474448, 0x39290001)               # addi r9,r9,1: the hole-end scorecard carries a tied hole's skin
MARK, MARK_DRAW = (0x8047B314, 0x4800EB61), 0x80489E74   # bl: a skin's number on the scorecard (r28 hole, r8 player)
WOLF_TEAM, OTHERS = 1, 2
TEAM_WIN, LONE_WIN, LONE_LOSS = 1, 2, 1      # points (Golf Digest's): each winner of a 2-v-2 hole; a Lone Wolf who
                                             # wins; each other player when the Lone Wolf loses (the same as a win)
KIND_START, KIND_DECIDE = 1, 2               # the Wolf's menus: "X is the Wolf!" (OK), "team up with Y?"
PLAYER_GOLFER = 0x51EF                       # player: its golfer code (byte)
GOLFER_NAMES = ("Mario", "Waluigi", "Peach", "Luigi", "Bowser", "Wario", "Metal Mario", "Birdo", "Yoshi", "DK",
                "Diddy", "Boo", "Petey", "Daisy", "Bowser Jr.", "Koopa", "Shy Guy", "Tony", "?")   # by golfer code
WOLF_TEXTS = {
    "fmt_start": b"\x075%s is the Wolf this hole!\x00",
    "fmt_decide": b"\x075Wolf %s: team up with %s?\x00",
    "row_ok": b"\x075OK\x00",
    "row_yes": b"\x075Yes\x00",
    "row_no": b"\x075No\x00",
    "row_lone": b"\x075No, go Lone Wolf\x00",
}
# Worst Ball's worst shot: not in the hole first, then a penalty, then the distance to the pin, squared, times
# these by the lie (as a scramble's best shot)
WORST_WEIGHTS = tuple((code, w) for w, codes in LIE_WEIGHTS for code in codes)
WORST_BIG = 1.0e9


def lbzu(rd, d, ra):
    return ppc._d(35, rd, d, ra)


def stbu(rs, d, ra):
    return ppc._d(39, rs, d, ra)


def stwx(rs, ra, rb):
    return 0x7C00012E | rs << 21 | ra << 16 | rb << 11


def _clear(a, at, size):
    """Zero `size` bytes at `at` (r0, r11, r12, ctr)."""
    _la(a, 11, at - 4)
    a(ppc.li(0, 0), ppc.li(12, size // 4), ppc.mtctr(12))
    a.label(f"clear_{at:x}")
    a(ppc.stwu(0, 4, 11))
    a.br("bdnz", f"clear_{at:x}")


BNELR = 0x4C820020


def v20_code(d, t, x, cam, L):
    """The v20 caves (built twice: `L` holds every label, from the first pass)."""
    out = {}
    tm_hi, tm_lo = ppc.hi_lo(d["team_mode"])

    def mode_is(a, mode):                     # cr0 eq when the round's team mode is `mode` (r12)
        a(ppc.lis(12, tm_hi), ppc.lwz(12, tm_lo, 12), ppc.cmpwi(12, mode))

    # -- wdata: the Wolf's state
    w = ppc.Asm(CAVES["wdata"][0])
    W = CAVES["wdata"][0]
    w.word("hole", -1)                        # the hole the state below is for
    w.label("st")                             # bytes: the Wolf, partner (0xFF none), candidates offered, decided,
    w(0, 0)                                   # scored, lone, menu kind, candidate
    w.word("outs", 0)                         # players stopped because they can't help their team (bytes)
    w.label("points")
    w(*([0] * 4))
    w.label("hole_points")                    # [hole][player] bytes: this hole's points
    w(*([0] * (18 * 4 // 4)))
    w.label("header_buf")
    w(*([0] * 16))
    w.label("name_a")
    w(*([0] * 4))
    w.label("name_b")
    w(*([0] * 4))
    names = b""
    offsets = []
    for name in GOLFER_NAMES:                 # the golfers' names, as the Wolf's menus call them
        offsets.append(len(names))
        names += name.encode() + b"\x00"
    _string(w, "name_offsets", bytes(offsets))
    _string(w, "names", names)
    out["wdata"] = w
    ST = w.labels["st"] - W
    WOLF_, PARTNER, OFFERED, DECIDED, SCORED, LONE, KIND, CAND = (ST + k for k in range(8))
    HOLE, OUTS, POINTS, HOLE_POINTS = (w.labels[k] - W for k in ("hole", "outs", "points", "hole_points"))
    HEADER_BUF, NAME_A, NAME_B = (w.labels[k] - W for k in ("header_buf", "name_a", "name_b"))

    # -- wtext: texts
    s = ppc.Asm(CAVES["wtext"][0])
    for k, text in enumerate(HELP_TEXTS):
        if k not in DATA_HELP_KEYS:
            _string(s, f"help_{k}", text)
    for name, text in WOLF_TEXTS.items():
        _string(s, name, text)
    out["wtext"] = s
    T = s.labels

    # -- list (menu overlay): the Team Play list's arrays
    a = ppc.Asm(CAVES["list"][0])
    a.word("tex_ptr", SUB_TEX)
    a.word("help_ptr", SUB_HELP)
    a.label("new_tex")
    a(*([0] * (SUB_COUNT_DOUBLES + len(NAMES))))
    a.label("new_help")
    a(*([0] * (SUB_COUNT_DOUBLES + len(NAMES))))
    a.label("list_reset")                     # (b from LIST_FILL) every fill starts on the game's arrays
    a.la(12, "tex_ptr")
    a(ppc.lis(11, SUB_TEX >> 16), ppc.ori(11, 11, SUB_TEX & 0xFFFF), ppc.stw(11, 0, 12),
      ppc.lis(11, SUB_HELP >> 16), ppc.ori(11, 11, SUB_HELP & 0xFFFF), ppc.stw(11, 4, 12))
    a(LIST_FILL[1])
    a.b(LIST_FILL[0] + 4)
    a.label("tex_load")                       # (bl from LIST_READERS) r9 = the arrays in use
    a.la(9, "tex_ptr")
    a(ppc.lwz(9, 0, 9), ppc.BLR)
    a.label("help_load")
    a.la(9, "help_ptr")
    a(ppc.lwz(9, 0, 9), ppc.BLR)
    a.label("sublist")                        # (b from SUBLIST_HOOK, the end of the Doubles case) our arrays:
    a.la(11, "new_tex")                       # Doubles' own five (their help says alternate shot), then ours
    a.la(12, "new_help")
    _la(a, 10, SUB_TEX)
    for k in range(SUB_COUNT_DOUBLES):
        a(ppc.lwz(0, 4 * k, 10), ppc.stw(0, 4 * k, 11), ppc.li(0, ALT_IDS[k] - 0x22), ppc.stw(0, 4 * k, 12))
    for k in range(len(NAMES)):
        at = 4 * (SUB_COUNT_DOUBLES + k)
        a(ppc.li(0, FIRST_TEX + k), ppc.stw(0, at, 11), ppc.li(0, HELP_IDS[k] - 0x22), ppc.stw(0, at, 12))
    a.la(10, "tex_ptr")
    a(ppc.stw(11, 0, 10), ppc.stw(12, 4, 10), ppc.BLR)
    out["list"] = a

    # -- worst: the worst shot, and what happens once every member has hit
    a = ppc.Asm(CAVES["worst"][0])
    a.float("neg_one", -1.0)
    a.float("neg_two", -2.0)
    a.float("big", WORST_BIG)
    a.label("weights")
    for code, wt in WORST_WEIGHTS:
        a(code, struct.unpack(">I", struct.pack(">f", wt))[0])
    a(0xFFFFFFFF, struct.unpack(">I", struct.pack(">f", LIE_WEIGHT_OTHER))[0])
    WB = CAVES["worst"][0]

    # worst_of(r3 = team, r4 = members who hit) -> r3 = member: any ball not in the hole before a holed one, then
    # a penalty, then the farthest (distance squared times the lie's weight)
    a.label("worst_of")
    _enter(a, 0x30, 26)
    a(ppc.mr(31, 3), ppc.mr(29, 4), ppc.li(28, 0), ppc.li(27, 0))
    _la(a, 26, WB)
    a(ppc.lfs(1, a.labels["neg_two"] - WB, 26))
    _lbz_abs(a, 30, D15)
    a.label("wo_loop")
    a(ppc.mullw(12, 30, 28), ppc.add(12, 12, 31))
    _slot(a, 10, 12, d)
    a(ppc.lbz(0, 0x28, 10), ppc.cmpwi(0, 0))
    a.br("beq", "wo_out_hole")
    a(ppc.lfs(2, a.labels["neg_one"] - WB, 26))
    a.br("b", "wo_cmp")
    a.label("wo_out_hole")
    hi, lo = ppc.hi_lo(PIN_X)
    a(ppc.lis(12, hi), ppc.lfs(3, lo, 12), ppc.lfs(2, 0, 10), ppc.fsubs(2, 2, 3))
    hi, lo = ppc.hi_lo(PIN_Z)
    a(ppc.lis(12, hi), ppc.lfs(3, lo, 12), ppc.lfs(4, 8, 10), ppc.fsubs(4, 4, 3))
    a(ppc.fmuls(2, 2, 2), ppc.fmadds(2, 4, 4, 2), ppc.lwz(0, 0x2C, 10),
      ppc.addi(12, 26, a.labels["weights"] - WB - 8))
    a.label("wo_weight")
    a(ppc.lwzu(9, 8, 12), ppc.cmpwi(9, -1))
    a.br("beq", "wo_weighed")
    a(ppc.cmpw(9, 0))
    a.br("bne", "wo_weight")
    a.label("wo_weighed")
    a(ppc.lfs(3, 4, 12), ppc.fmuls(2, 2, 3), ppc.lbz(9, SLOT_PEN, 10), ppc.cmpwi(9, 0))
    a.br("beq", "wo_cmp")
    a(ppc.lfs(3, a.labels["big"] - WB, 26), ppc.fadds(2, 2, 3))
    a.label("wo_cmp")
    a(ppc.fcmpu(2, 1))
    a.br("ble", "wo_next")
    a(ppc.mr(27, 28), ppc.fmr(1, 2))
    a.label("wo_next")
    a(ppc.addi(28, 28, 1), ppc.cmpw(28, 29))
    a.br("blt", "wo_loop")
    a(ppc.mr(3, 27))
    _leave(a, 0x30, 26)
    out["worst"] = a

    a = ppc.Asm(CAVES["worst2"][0])
    # all_hit(r3 = team, r4 = members who hit): Worst Ball takes the worst ball now; a scramble asks its captain
    a.label("all_hit")
    _enter(a, 0x20, 30)
    a(ppc.mr(31, 3))
    mode_is(a, WORST)
    a.br("bne", "ah_scramble")
    a.bl(L["worst_of"])
    a(ppc.mr(4, 3), ppc.mr(3, 31))
    a.bl(x["take"])
    a.br("b", "ah_out")
    a.label("ah_scramble")
    a.bl(x["best_of"])
    _la(a, 12, d["choose_default"])
    a(ppc.stw(3, 0, 12), ppc.addi(0, 31, 1))
    _la(a, 12, d["choose_team"])
    a(ppc.stw(0, 0, 12))
    a.label("ah_out")
    _leave(a, 0x20, 30)
    a.label("commit_wolf")                    # (b from "commit", r11 = setup block) a Skins game of everyone,
    a(ppc.li(0, WOLF), ppc.stb(0, MODE_BYTE, 11), ppc.li(0, 2), ppc.stw(0, 0xA80, 11), ppc.li(0, 3),   # each on
      ppc.stw(0, 0xA84, 11), ppc.li(3, 3))   # their own ball (mode 2, sub-mode 3), straight to the course select
    a.bl(SCREEN_PUSH)
    a.bl(COURSE_LIST)
    a.b(COMMIT_END)
    a.label("wolf_clear")                     # the Wolf's texts' buffers (the game's text boxes show what is left
    _clear(a, W + HEADER_BUF, 64)             # past a shorter string)
    _clear(a, t["options"], 4 * OPTION_TEXT)
    a(ppc.BLR)
    a.label("wolf_cam_slot")                  # (r12 = candidate) the captain's menu camera flies to its ball
    a(ppc.addi(0, 12, 1))                     # (cam_update: team = the candidate, its slot = where the ball is)
    _la(a, 11, d["choose_team"])
    a(ppc.stw(0, 0, 11), ppc.li(0, 0))
    _la(a, 11, d["choose_default"])
    a(ppc.stw(0, 0, 11))
    _player(a, 10, 12)
    a(ppc.lwz(10, PLAYER_BALL, 10))
    _slot(a, 9, 12, d)
    for off in (0, 4, 8):
        a(ppc.lwz(0, 0x9C + off, 10), ppc.stw(0, off, 9))
    a(ppc.BLR)
    out["worst2"] = a

    # -- wpick: the shooter pick (b from PICKER, r3 = golf state)
    a = ppc.Asm(CAVES["wpick"][0])
    a.label("wolf_pick")
    mode_is(a, WOLF)
    a.br("beq", "wp_go")
    a(PICKER[1])
    a.b(PICKER[0] + 4)
    a.label("wp_go")
    _enter(a, 0x30, 25)
    a(ppc.mr(31, 3), ppc.lbz(30, STATE_D15, 31))           # r30 = players
    _la(a, 28, W)
    _lbz_abs(a, 29, HOLE_INDEX)
    a(ppc.lwz(0, HOLE, 28), ppc.cmpw(0, 29))
    a.br("beq", "wp_known")
    # a new hole: its Wolf (on the first hole the last player, then 1P, 2P, ...), who tees off last
    a(ppc.stw(29, HOLE, 28), ppc.add(12, 29, 30), ppc.addi(12, 12, -1), ppc.divw(11, 12, 30),
      ppc.mullw(11, 11, 30), ppc.subf(12, 11, 12), ppc.stb(12, WOLF_, 28))
    a(ppc.li(0, -1), ppc.stb(0, PARTNER, 28), ppc.li(0, 0))
    for off in (OFFERED, DECIDED, SCORED, LONE):
        a(ppc.stb(0, off, 28))
    a(ppc.stw(0, OUTS, 28), ppc.li(27, 0))
    a.label("wp_order")                       # tee order: the one after the Wolf first, ..., the Wolf last; and
    _player(a, 26, 27)                        # the hole's result byte "no points" for now
    a(ppc.lwz(25, PLAYER_REC, 26), ppc.lbz(12, WOLF_, 28), ppc.subf(11, 12, 27), ppc.addi(11, 11, -1),
      ppc.add(11, 11, 30), ppc.add(11, 11, 30), ppc.divw(12, 11, 30), ppc.mullw(12, 12, 30), ppc.subf(11, 12, 11))
    a(ppc.stb(11, REC_HONOR, 25), ppc.lwz(11, PLAYER_CARD, 26), ppc.slwi(12, 29, 3), ppc.li(0, 1),
      ppc.stbx(0, 11, 12), ppc.addi(27, 27, 1), ppc.cmpw(27, 30))
    a.br("blt", "wp_order")
    a(ppc.li(3, KIND_START))
    a.bl(L["wolf_open"])
    a.br("b", "wp_none")
    a.label("wp_known")
    a(ppc.lbz(0, KIND, 28), ppc.cmpwi(0, 0))
    a.br("beq", "wp_free")
    a.bl(L["wolf_step"])
    a(ppc.cmpwi(3, 0))
    a.br("bne", "wp_none")
    a.label("wp_free")                        # the next candidate has driven: the Wolf's call on them
    a(ppc.lbz(0, DECIDED, 28), ppc.cmpwi(0, 0))
    a.br("bne", "wp_game")
    a(ppc.lbz(12, WOLF_, 28), ppc.lbz(11, OFFERED, 28), ppc.add(12, 12, 11), ppc.addi(12, 12, 1),
      ppc.divw(11, 12, 30), ppc.mullw(11, 11, 30), ppc.subf(27, 11, 12))
    _player(a, 26, 27)
    a(ppc.lwz(25, PLAYER_REC, 26), ppc.lbz(0, REC_STROKES, 25), ppc.cmpwi(0, 0))
    a.br("beq", "wp_game")
    a(ppc.stb(27, CAND, 28), ppc.li(3, KIND_DECIDE))
    a.bl(L["wolf_open"])
    a.label("wp_none")                        # nobody's turn while a menu is up
    a(ppc.li(0, -1), ppc.stb(0, STATE_D17, 31))
    _leave(a, 0x30, 25)
    a.label("wp_game")                        # the game's pick
    a(ppc.mr(3, 31), ppc.lmw(25, 0x30 - 4 * 7, 1), ppc.lwz(0, 0x34, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x30))
    a(PICKER[1])
    a.b(PICKER[0] + 4)
    out["wpick"] = a

    # wolf_step() -> r3 = 1 while the Wolf's menu is up, 0 once it has closed (its choice taken)
    a = ppc.Asm(CAVES["wstep"][0])
    a.label("wolf_step")
    _enter(a, 0x20, 28)
    _la(a, 28, W)
    _la(a, 12, d["choose_menu"])
    a(ppc.lwz(30, 0, 12), ppc.lwz(29, 0, 30), ppc.cmpwi(29, -1))
    a.br("beq", "ws_open")
    a(ppc.cmpwi(29, -3))
    a.br("beq", "ws_open")
    a(ppc.mr(3, 30))
    a.bl(MENU_CLEANUP)
    a(ppc.mr(3, 30))
    a.bl(FREE)
    a(ppc.li(0, 0))
    hi, lo = ppc.hi_lo(CUR_MENU)
    a(ppc.lis(12, hi), ppc.stw(0, lo, 12))
    for name in ("choose_menu", "menu_open", "choose_team"):
        _la(a, 12, d[name])
        a(ppc.stw(0, 0, 12))
    _la(a, 12, d["header_ptr"])
    _la(a, 11, d["header"])
    a(ppc.stw(11, 0, 12), ppc.lbz(31, KIND, 28), ppc.stb(0, KIND, 28), ppc.cmpwi(31, KIND_DECIDE))
    a.br("bne", "ws_closed")
    a(ppc.cmpwi(29, 0))                       # row 0, "Yes": that partner
    a.br("bne", "ws_pass")
    a(ppc.lbz(0, CAND, 28), ppc.stb(0, PARTNER, 28), ppc.li(0, 1), ppc.stb(0, DECIDED, 28))
    a.br("b", "ws_closed")
    a.label("ws_pass")                        # "No" (or B): the next one; after the last, the Lone Wolf
    a(ppc.lbz(12, OFFERED, 28), ppc.addi(12, 12, 1), ppc.stb(12, OFFERED, 28))
    _lbz_abs(a, 11, D15)
    a(ppc.addi(11, 11, -1), ppc.cmpw(12, 11))
    a.br("blt", "ws_closed")
    a(ppc.li(0, 1), ppc.stb(0, LONE, 28), ppc.stb(0, DECIDED, 28))
    a.label("ws_closed")
    a(ppc.li(3, 0))
    a.br("b", "ws_out")
    a.label("ws_open")
    a(ppc.lbz(0, KIND, 28), ppc.cmpwi(0, KIND_DECIDE))
    a.br("bne", "ws_still")
    a(ppc.mr(3, 30))
    a.bl(cam["cam_update"])
    a.label("ws_still")
    a(ppc.li(3, 1))
    a.label("ws_out")
    _leave(a, 0x20, 28)
    out["wstep"] = a

    # -- wmenu: the Wolf's menus (the captain's menu's way: our header and rows, the Wolf's pad)
    a = ppc.Asm(CAVES["wmenu"][0])
    a.label("wolf_open")                      # (r3 = kind)
    _enter(a, 0x40, 24)
    a(ppc.mr(31, 3))
    _la(a, 28, W)
    a(ppc.stb(31, KIND, 28))
    a.bl(L["wolf_clear"])
    a(ppc.lbz(3, WOLF_, 28), ppc.addi(4, 28, NAME_A))
    a.bl(L["name_of"])
    a(ppc.lbz(3, CAND, 28), ppc.addi(4, 28, NAME_B))
    a.bl(L["name_of"])
    a(ppc.addi(3, 28, HEADER_BUF), ppc.cmpwi(31, KIND_DECIDE))
    _la(a, 4, T["fmt_decide"])
    a.br("beq", "wo_fmt")
    _la(a, 4, T["fmt_start"])
    a.label("wo_fmt")
    a(ppc.addi(5, 28, NAME_A), ppc.addi(6, 28, NAME_B), ppc.CRCLR6)
    a.bl(SPRINTF)
    _la(a, 12, d["header_ptr"])
    a(ppc.addi(0, 28, HEADER_BUF), ppc.stw(0, 0, 12))
    _la(a, 3, t["options"])
    a(ppc.cmpwi(31, KIND_DECIDE))
    a.br("bne", "wo_ok")
    _la(a, 4, T["row_yes"])
    a.bl(L["strcpy"])
    _la(a, 3, t["options"] + OPTION_TEXT)
    _la(a, 4, T["row_no"])
    a(ppc.lbz(12, OFFERED, 28))
    _lbz_abs(a, 11, D15)
    a(ppc.addi(11, 11, -2), ppc.cmpw(12, 11))
    a.br("blt", "wo_no")
    _la(a, 4, T["row_lone"])
    a.label("wo_no")
    a.bl(L["strcpy"])
    a(ppc.li(27, 2))
    a.br("b", "wo_menu")
    a.label("wo_ok")
    _la(a, 4, T["row_ok"])
    a.bl(L["strcpy"])
    a(ppc.li(27, 1))
    a.label("wo_menu")                        # a header row and the rows, on the Wolf's pad
    a(ppc.li(3, 0x90))
    a.bl(ALLOC)
    a(ppc.mr(26, 3), ppc.li(4, 2), ppc.lbz(12, WOLF_, 28))
    _player(a, 12, 12)
    a(ppc.lwz(5, PLAYER_PAD, 12))
    a.bl(MENU_INIT)
    a(ppc.addi(0, 27, 1), ppc.stb(0, MENU_COUNT, 26), ppc.li(0, HEADER_CODE), ppc.stw(0, MENU_CODES, 26),
      ppc.li(0, 0), ppc.stw(0, MENU_CODES + 4, 26), ppc.li(0, 1), ppc.stw(0, MENU_CODES + 8, 26),
      ppc.stw(0, MENU_CURSOR, 26))
    hi, lo = ppc.hi_lo(CUR_MENU)
    a(ppc.lis(12, hi), ppc.stw(26, lo, 12))
    _la(a, 12, d["choose_menu"])
    a(ppc.stw(26, 0, 12))
    _la(a, 12, d["menu_open"])
    a(ppc.stw(0, 0, 12), ppc.cmpwi(31, KIND_DECIDE))
    a.br("bne", "wo_out")
    a(ppc.lbz(12, CAND, 28))
    a.bl(L["wolf_cam_slot"])
    a.label("wo_out")
    _leave(a, 0x40, 24)

    out["wmenu"] = a

    a = ppc.Asm(CAVES["wname"][0])
    a.label("name_of")                        # (r3 = player, r4 = buffer) its golfer's name ("Mario")
    _player(a, 12, 3)
    a(ppc.lbz(12, PLAYER_GOLFER, 12), ppc.cmplwi(12, len(GOLFER_NAMES) - 1))
    a.br("blt", "name_known")
    a(ppc.li(12, len(GOLFER_NAMES) - 1))
    a.label("name_known")
    _la(a, 11, w.labels["name_offsets"])
    a(ppc.lbzx(0, 11, 12), ppc.mr(3, 4))
    _la(a, 4, w.labels["names"])
    a(ppc.add(4, 4, 0))                       # (then strcpy, right below)
    a.label("strcpy")                         # (r3 = to, r4 = from)
    a(ppc.addi(3, 3, -1), ppc.addi(4, 4, -1))
    a.label("strcpy_loop")
    a(lbzu(0, 1, 4), stbu(0, 1, 3), ppc.cmpwi(0, 0))
    a.br("bne", "strcpy_loop")
    a(ppc.BLR)

    # -- scoring (b from SCORE, r3 = side): stroke play's (sub-mode 0) for the shot, then the Wolf's
    a.label("wolf_score")
    mode_is(a, WOLF)
    a.br("beq", "wsc_go")
    a.label("wsc_game")
    a(SCORE[1])
    a.b(SCORE[0] + 4)
    a.label("wsc_go")
    _enter(a, 0x10, 30)
    hi, lo = ppc.hi_lo(STATE_SUB_MODE)
    a(ppc.mr(30, 3), ppc.lis(12, hi), ppc.li(0, 0), ppc.stw(0, lo, 12))
    a.br("bl", "wsc_game")
    a(ppc.mr(31, 3), ppc.lis(12, hi), ppc.li(0, 3), ppc.stw(0, lo, 12))
    a.bl(L["wolf_check"])
    # once the hole is scored, this player's result byte stays the Wolf's (0 = points), whatever stroke play's
    # scoring writes for someone it sees as picked up (status 2: par x 3)
    _la(a, 12, W)
    a(ppc.lbz(0, SCORED, 12), ppc.cmpwi(0, 0))
    a.br("beq", "wsc_out")
    _lbz_abs(a, 11, HOLE_INDEX)
    a(ppc.slwi(10, 11, 2), ppc.add(10, 10, 30), ppc.add(10, 10, 12), ppc.lbz(0, HOLE_POINTS, 10), ppc.li(9, 1),
      ppc.cmpwi(0, 0))
    a.br("beq", "wsc_card")
    a(ppc.li(9, 0))
    a.label("wsc_card")
    _player(a, 10, 30)
    a(ppc.lwz(10, PLAYER_CARD, 10), ppc.slwi(11, 11, 3), ppc.stbx(9, 10, 11))
    a.label("wsc_out")
    a(ppc.mr(3, 31))
    _leave(a, 0x10, 30)

    a.label("team_of")                        # (r27 = player, r28 = state) -> r12 = WOLF_TEAM / OTHERS
    a(ppc.li(12, WOLF_TEAM), ppc.lbz(11, WOLF_, 28), ppc.cmpw(27, 11), ppc.BEQLR, ppc.lbz(11, PARTNER, 28),
      ppc.cmpw(27, 11), ppc.BEQLR, ppc.li(12, OTHERS), ppc.BLR)

    # wolf_check(): once the teams are set, stop anyone who can't better their team's holed score; when everyone is
    # done, each team's score is its best (holed, or picked up at the limit) and the winners get their points
    out["wname"] = a

    a = ppc.Asm(CAVES["wscore"][0])
    a.label("wolf_check")
    _enter(a, 0x40, 20)
    _la(a, 28, W)
    a(ppc.lbz(0, SCORED, 28), ppc.cmpwi(0, 0))
    a.br("bne", "wc_out")
    a(ppc.lbz(0, DECIDED, 28), ppc.cmpwi(0, 0))
    a.br("beq", "wc_out")
    _lbz_abs(a, 30, D15)
    a(ppc.li(25, 99), ppc.li(24, 99), ppc.li(27, 0))       # r25 / r24: the Wolf's team's / the others' best holed
    a.label("wc_best")
    _player(a, 26, 27)
    a(ppc.lwz(26, PLAYER_REC, 26), ppc.lbz(0, REC_STATUS, 26), ppc.cmpwi(0, 1))
    a.br("bne", "wc_best_next")
    a(ppc.lbz(0, REC_STROKES, 26))
    a.bl(L["team_of"])
    a(ppc.cmpwi(12, WOLF_TEAM))
    a.br("beq", "wc_best_wolf")
    a(ppc.cmpw(0, 24))
    a.br("bge", "wc_best_next")
    a(ppc.mr(24, 0))
    a.br("b", "wc_best_next")
    a.label("wc_best_wolf")
    a(ppc.cmpw(0, 25))
    a.br("bge", "wc_best_next")
    a(ppc.mr(25, 0))
    a.label("wc_best_next")
    a(ppc.addi(27, 27, 1), ppc.cmpw(27, 30))
    a.br("blt", "wc_best")
    a(ppc.li(23, 99), ppc.li(22, 99), ppc.li(21, 1), ppc.li(27, 0))   # r23 / r22 the teams' scores, r21 all done
    a.label("wc_done")
    _player(a, 26, 27)
    a(ppc.lwz(26, PLAYER_REC, 26))
    a.bl(L["team_of"])
    a(ppc.mr(20, 25), ppc.cmpwi(12, WOLF_TEAM))
    a.br("beq", "wc_team_best")
    a(ppc.mr(20, 24))
    a.label("wc_team_best")
    a(ppc.lbz(0, REC_STATUS, 26), ppc.cmpwi(0, 0))
    a.br("bne", "wc_finished")
    a(ppc.lbz(9, REC_STROKES, 26), ppc.addi(9, 9, 1), ppc.cmpw(9, 20))
    a.br("blt", "wc_playing")
    a(ppc.li(0, 2), ppc.stb(0, REC_STATUS, 26), ppc.addi(11, 28, OUTS), ppc.li(0, 1), ppc.stbx(0, 11, 27))
    a.br("b", "wc_next")
    a.label("wc_playing")
    a(ppc.li(21, 0))
    a.br("b", "wc_next")
    a.label("wc_finished")
    a(ppc.addi(11, 28, OUTS), ppc.lbzx(0, 11, 27), ppc.cmpwi(0, 0))
    a.br("bne", "wc_next")                    # (stopped by us: not a score)
    a(ppc.lbz(9, REC_STROKES, 26), ppc.cmpwi(12, WOLF_TEAM))
    a.br("beq", "wc_score_wolf")
    a(ppc.cmpw(9, 22))
    a.br("bge", "wc_next")
    a(ppc.mr(22, 9))
    a.br("b", "wc_next")
    a.label("wc_score_wolf")
    a(ppc.cmpw(9, 23))
    a.br("bge", "wc_next")
    a(ppc.mr(23, 9))
    a.label("wc_next")
    a(ppc.addi(27, 27, 1), ppc.cmpw(27, 30))
    a.br("blt", "wc_done")
    a(ppc.cmpwi(21, 0))
    a.br("beq", "wc_out")
    a.b(L["wc_award"])                        # (in cave "waward", on this frame)
    a.label("wc_out")
    _leave(a, 0x40, 20)
    out["wscore"] = a

    a = ppc.Asm(CAVES["waward"][0])
    a.label("wc_award")
    a(ppc.li(0, 1), ppc.stb(0, SCORED, 28), ppc.li(29, 0), ppc.li(31, TEAM_WIN), ppc.cmpw(23, 22))
    a.br("blt", "wc_wolf_won")
    a.br("bgt", "wc_others_won")
    a.br("b", "wc_points")                    # a tie: nobody
    a.label("wc_wolf_won")
    a(ppc.li(29, WOLF_TEAM), ppc.lbz(0, LONE, 28), ppc.cmpwi(0, 0))
    a.br("beq", "wc_points")
    a(ppc.li(31, LONE_WIN))
    a.br("b", "wc_points")
    a.label("wc_others_won")
    a(ppc.li(29, OTHERS), ppc.lbz(0, LONE, 28), ppc.cmpwi(0, 0))
    a.br("beq", "wc_points")
    a(ppc.li(31, LONE_LOSS))
    a.label("wc_points")                      # winners: points, this hole's points, result byte 0 (a skin)
    _lbz_abs(a, 21, HOLE_INDEX)
    a(ppc.li(27, 0))
    a.label("wc_aw")
    _player(a, 26, 27)
    a.bl(L["team_of"])
    a(ppc.li(0, 1), ppc.cmpw(12, 29))
    a.br("bne", "wc_aw_card")
    a(ppc.slwi(11, 27, 2), ppc.addi(11, 11, POINTS), ppc.lwzx(0, 28, 11), ppc.add(0, 0, 31), stwx(0, 28, 11))
    a(ppc.slwi(11, 21, 2), ppc.add(11, 11, 27), ppc.addi(11, 11, HOLE_POINTS), ppc.stbx(31, 28, 11), ppc.li(0, 0))
    a.label("wc_aw_card")
    a(ppc.lwz(11, PLAYER_CARD, 26), ppc.slwi(10, 21, 3), ppc.stbx(0, 11, 10), ppc.addi(27, 27, 1),
      ppc.cmpw(27, 30))
    a.br("blt", "wc_aw")
    _leave(a, 0x40, 20)
    out["waward"] = a

    # -- wshow: the points where the game shows skins
    a = ppc.Asm(CAVES["wshow"][0])
    a.label("wolf_points")                    # (b from POINTS_GET, r3 = player) -> its points
    mode_is(a, WOLF)
    a.br("beq", "wpt_go")
    a(POINTS_GET[1])
    a.b(POINTS_GET[0] + 4)
    a.label("wpt_go")
    a(ppc.lwz(3, PLAYER_INDEX, 3), ppc.slwi(3, 3, 2))
    _la(a, 12, W + POINTS)
    a(ppc.lwzx(3, 12, 3), ppc.BLR)

    a.label("wolf_totals")                    # (bl from TOTALS) the scorecard: points before this hole, and this
    a(ppc.stwu(1, -0x40, 1), ppc.stw(11, 0x08, 1), ppc.stw(12, 0x0C, 1), ppc.stmw(24, 0x10, 1))   # hole's extra
    mode_is(a, WOLF)                          # points as "carried skins", which the hole-end scorecard counts up
    a.br("bne", "wt_out")
    _la(a, 31, W)
    _lbz_abs(a, 30, D15)
    _lbz_abs(a, 29, HOLE_INDEX)
    a(ppc.lbz(28, SCORED, 31))
    _la(a, 27, SKINS_TOTALS)
    a(ppc.li(26, 0), ppc.li(12, 0))
    a.label("wt_loop")
    a(ppc.slwi(25, 26, 2), ppc.addi(24, 31, POINTS), ppc.lwzx(24, 24, 25), ppc.cmpwi(28, 0))
    a.br("beq", "wt_set")
    a(ppc.slwi(11, 29, 2), ppc.add(11, 11, 26), ppc.add(11, 11, 31), ppc.lbz(0, HOLE_POINTS, 11),
      ppc.subf(24, 0, 24), ppc.cmpwi(0, 0))
    a.br("beq", "wt_set")
    a(ppc.add(12, 12, 0), ppc.addi(12, 12, -1))
    a.label("wt_set")
    a(stwx(24, 27, 25), ppc.addi(26, 26, 1), ppc.cmpw(26, 30))
    a.br("blt", "wt_loop")
    a(ppc.stw(12, SKINS_POT - SKINS_TOTALS, 27))
    a.label("wt_out")
    a(ppc.lmw(24, 0x10, 1), ppc.lwz(12, 0x0C, 1), ppc.lwz(11, 0x08, 1), ppc.addi(1, 1, 0x40))
    a(TOTALS[0][1], ppc.BLR)

    a.label("wolf_tie")                       # (bl from TIE) a tied hole carries nothing
    a(TIE[1])
    mode_is(a, WOLF)
    a(BNELR, ppc.addi(9, 9, -1), ppc.BLR)

    a.label("wolf_mark")                      # (bl from MARK) a winner's number on the scorecard: its points
    mode_is(a, WOLF)
    a.br("bne", "wm_go")
    a(ppc.slwi(12, 28, 2), ppc.add(12, 12, 8))
    _la(a, 11, W + HOLE_POINTS)
    a(ppc.lbzx(5, 11, 12))
    a.label("wm_go")
    a.b(MARK_DRAW)

    a.label("wolf_reset")                     # (bl from "setup") a new round; keeps r0, r10, r12
    _la(a, 11, W)
    a(ppc.li(9, -1), ppc.stw(9, HOLE, 11), ppc.li(9, 0), ppc.stb(9, KIND, 11), ppc.addi(11, 11, POINTS - 4),
      ppc.li(9, (HOLE_POINTS + 18 * 4 - POINTS) // 4), ppc.mtctr(9), ppc.li(9, 0))
    a.label("wr_loop")
    a(ppc.stwu(9, 4, 11))
    a.br("bdnz", "wr_loop")
    _la(a, 11, d["header_ptr"])
    _la(a, 9, d["header"])
    a(ppc.stw(9, 0, 11), ppc.BLR)
    out["wshow"] = a
    return out


class _AnyLabel(dict):
    """First-pass labels: any name is somewhere near (the second pass has the real ones)."""
    def __init__(self, near):
        super().__init__()
        self.near = near

    def __missing__(self, key):
        return self.near


def caves():
    """[(address, first word, bytes)] and the labels; texts() then lists our help messages."""
    (data, d), (text, t) = data_block()
    c = cam_code(d)
    c_code = c.assemble()
    m = menu_code(d, t)
    m_code = m.assemble()
    x = pick_code(d)
    x_code = x.assemble()
    s = step_code(d, x.labels, m.labels, c.labels)
    s_code = s.assemble()
    s_code += b"\x00" * (-len(s_code) % 8)
    xl = dict(x.labels, _options=t["options"], choose_step=s.labels["choose_step"])
    bc, ba = best_code(d, xl)
    bc_code, ba_code = bc.assemble(), ba.assemble()
    b_labels = {**bc.labels, **ba.labels}
    e = extra_code()
    e_code = e.assemble()
    # v20: Worst Ball and Wolf, assembled twice (their caves call each other): first for the labels
    first = v20_code(d, t, x.labels, c.labels, _AnyLabel(CAVES["wpick"][0]))
    for asm in first.values():
        asm.assemble()
    w_labels = {k: v for asm in first.values() for k, v in asm.labels.items()}
    v20 = v20_code(d, t, x.labels, c.labels, w_labels)
    v20_codes = [(name, asm.assemble()) for name, asm in v20.items()]
    w_labels = {k: v for asm in v20.values() for k, v in asm.labels.items()}
    h = hooks_code(d, xl, b_labels, CAVES["hooks"][0] + len(s_code), w_labels)
    h_code = s_code + h.assemble()
    out = []
    sizes = (("hooks", h_code), ("choose", bc_code), ("after", ba_code), ("pick", x_code), ("menu", m_code),
             ("cam", c_code), ("data", data), ("text", text), ("extra", e_code), *v20_codes)
    for name, code in sizes:
        at, size, first = CAVES[name]
        if len(code) > size:
            raise SystemExit(f"team games, cave {name}: {len(code)} bytes; only {size} fit")
        out.append((at, first, code))
    labels = {**h.labels, "stroke": t["stroke"], "mulligan": t["mulligan"], "cam_update": c.labels["cam_update"], **{f"best_{k}": v for k, v in b_labels.items()}, **{f"pick_{k}": v for k, v in x.labels.items()},
              **{f"data_{k}": v for k, v in d.items()}, **{f"w_{k}": v for k, v in w_labels.items()}}
    labels["_texts"] = [(HELP_IDS[k], d[f"help_{k}"] if k in DATA_HELP_KEYS else w_labels[f"help_{k}"])
                        for k in range(len(NAMES))] + \
        [(MSG_TEAM_HELP, d["team_help"])] + [(ALT_IDS[k], e.labels[f"alt_{k}"]) for k in range(len(ALT_IDS))]
    labels["_sizes"] = {name: len(code) for name, code in sizes}
    labels["row_x"] = e.labels["row_x"]
    return out, labels


def texts(labels):
    return labels["_texts"]


def message_hook(labels):
    """Where build_mod.py's message hook goes on to instead of the game's lookup."""
    return labels["messages"]


def overlay_patches(rel, labels, word):
    """[(address, new word, expected word)] for the golf (C/L/V) or menu (B/U/C) overlay."""
    out = []
    if rel == "C/L/V":
        for (site, old), stub, link in ((SETUP_HOOK, "setup", True), (PICK_HOOK, "pick", False),
                                         (STROKE_HOOK, "stroke", True), (PUTT_HOOK, "stroke", True),
                                         (MULLIGAN_HOOK, "mulligan", True), (SHOT_HOOK, "shot", False),
                                         (AFTER_HOOK, "after", False), (FACE_HOOK, "face", False),
                                         (MENU_HOOK, "menu_scene", True), (DRAW_HOOK, "menu_draw", True),
                                         (PICKER, "w_wolf_pick", False), (SCORE, "w_wolf_score", False),
                                         (POINTS_GET, "w_wolf_points", False), (TIE, "w_wolf_tie", True),
                                         (MARK, "w_wolf_mark", True)) + \
                tuple((hook, "best_glass_env", True) for hook in BOX_ALPHA_HOOKS) + \
                tuple((hook, "w_wolf_totals", True) for hook in TOTALS):
            out.append((site, (ppc.bl if link else ppc.b)(site, labels[stub]), old))
    elif rel == "B/U/C":
        for (site, old), stub, link in ((CLEAR_SUBLIST, "clear_sublist", True), (CLEAR_DIRECT, "clear_direct", True),
                                         (COMMIT_HOOK, "commit", False), (SUBLIST_HOOK, "w_sublist", False),
                                         (LIST_FILL, "w_list_reset", False), (ROW_X, "row_x", True)) + \
                tuple(((site, old), "w_" + stub, True) for site, old, stub in LIST_READERS):
            out.append((site, (ppc.bl if link else ppc.b)(site, labels[stub]), old))
        for k, (old, new) in enumerate(zip(SUB_COUNTS_OLD, SUB_COUNTS_NEW)):
            out.append((SUB_COUNTS + 4 * k, new, old))
    return out


# ---- pictures: our icons (96x96 CMPR) and name labels (IA4), drawn here, appended to the sets

def _font(size):
    from PIL import ImageFont
    for name in ("ARLRDBD.TTF", "arialbd.ttf"):
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    raise SystemExit("no Arial Rounded MT Bold (ARLRDBD.TTF) for the mode names")


def label_image(text, height=28, scale=4, size=25, outline=3):
    """White letters with a black outline, like the game's labels: intensity + 1-bit alpha (IA4)."""
    from PIL import Image, ImageDraw
    font = _font(size * scale)
    stroke = outline * scale
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    x0, y0, x1, y1 = probe.textbbox((0, 0), text, font=font, stroke_width=stroke)
    w = x1 - x0 + 2 * scale
    big_h = height * scale
    cap = probe.textbbox((0, 0), "B", font=font)
    top = (big_h - (cap[3] - cap[1])) // 2 - cap[1] - scale     # caps centred, descenders below
    outer = Image.new("L", (w, big_h))
    ImageDraw.Draw(outer).text((scale - x0, top), text, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    inner = Image.new("L", (w, big_h))
    ImageDraw.Draw(inner).text((scale - x0, top), text, font=font, fill=255)
    size = (-(-w // scale), height)
    o = np.asarray(outer.resize(size, Image.BOX), np.float64) / 255
    i = np.asarray(inner.resize(size, Image.BOX), np.float64) / 255
    alpha = o >= 0.5
    inten = np.where(alpha, np.clip(i / np.maximum(o, 1e-6), 0, 1), 0)
    out = np.zeros(o.shape + (4,), np.uint8)
    out[..., :3] = (inten * 255 + 0.5).astype(np.uint8)[..., None]
    out[..., 3] = alpha * 255
    return out


def encode_ia4(img):
    h, w = img.shape[:2]
    th, tw = -(-h // 4) * 4, -(-w // 8) * 8
    px = np.zeros((th, tw, 4), np.uint8)
    px[:h, :w] = img
    v = ((px[..., 3].astype(np.int64) * 15 + 127) // 255 << 4) | ((px[..., 0].astype(np.int64) * 15 + 127) // 255)
    tiles = v.astype(np.uint8).reshape(th // 4, 4, tw // 8, 8).transpose(0, 2, 1, 3)
    return tiles.tobytes()


def icon_image(name, size=96, scale=4):
    """An orange button like the Doubles list's, with golf balls (and a star for the shot the team takes)."""
    kind = name
    from PIL import Image, ImageDraw
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2
    r = c - 1.5 * scale
    yy, xx = np.mgrid[0:s, 0:s]
    dist = np.hypot(xx - c + 0.5, yy - c + 0.5) / r
    disc = np.zeros((s, s, 4), np.uint8)
    rim = np.clip((dist - 0.86) / 0.14, 0, 1)
    disc[..., 0] = 255
    disc[..., 1] = (132 + 36 * rim).astype(np.uint8)
    disc[..., 2] = (61 * rim).astype(np.uint8)
    disc[..., 3] = np.where(dist <= 1, 255, 0).astype(np.uint8)
    img = Image.alpha_composite(img, Image.fromarray(disc))
    d = ImageDraw.Draw(img)
    line = 4 * scale

    def star(cx, cy, ro, ri, fill=(255, 238, 0, 255), points=5):
        import math
        pts = []
        for k in range(2 * points):
            rr = ro if k % 2 == 0 else ri
            t = -math.pi / 2 + k * math.pi / points
            pts.append((cx + rr * math.cos(t), cy + rr * math.sin(t)))
        d.polygon(pts, fill=fill, outline=(0, 0, 0, 255), width=line)

    def ball(cx, cy, rr):
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(0, 0, 0, 255))
        rr2 = rr - line
        d.ellipse((cx - rr2, cy - rr2, cx + rr2, cy + rr2), fill=(205, 205, 210, 255))
        d.ellipse((cx - rr2 * 0.95, cy - rr2, cx + rr2 * 0.75, cy + rr2 * 0.7), fill=(250, 250, 250, 255))
        h = rr2 * 0.32
        d.ellipse((cx - rr2 * 0.55 - h, cy - rr2 * 0.55 - h, cx - rr2 * 0.55 + h, cy - rr2 * 0.55 + h),
                  fill=(255, 255, 255, 255))

    u = s / 96
    if kind == "Best Ball Match":  # two balls on a red-edged burst, like Match Play's
        star(48 * u, 48 * u, 42 * u, 22 * u, fill=(255, 238, 0, 255), points=8)
        d.polygon([(48 * u + 30 * u * np.cos(np.pi * k / 8 - np.pi / 2) * (1 if k % 2 == 0 else 0.55),
                    48 * u + 30 * u * np.sin(np.pi * k / 8 - np.pi / 2) * (1 if k % 2 == 0 else 0.55))
                   for k in range(16)], fill=(230, 30, 20, 255))
        ball(36 * u, 56 * u, 15 * u)
        ball(62 * u, 44 * u, 13 * u)
    elif kind == "Best Ball Stroke":  # two balls, the better one under a star
        star(62 * u, 34 * u, 26 * u, 11 * u)
        ball(36 * u, 60 * u, 17 * u)
        ball(62 * u, 62 * u, 13 * u)
    elif kind == "Scramble":  # three shots, the team takes the starred one
        star(48 * u, 40 * u, 30 * u, 13 * u)
        ball(48 * u, 42 * u, 13 * u)
        ball(24 * u, 66 * u, 11 * u)
        ball(72 * u, 66 * u, 11 * u)
    elif kind == "Worst Ball":  # three shots, a blue arrow down to the one the team must play
        ball(24 * u, 30 * u, 11 * u)
        ball(72 * u, 30 * u, 11 * u)
        d.polygon([(40 * u, 14 * u), (56 * u, 14 * u), (56 * u, 34 * u), (66 * u, 34 * u), (48 * u, 52 * u),
                   (30 * u, 34 * u), (40 * u, 34 * u)], fill=(40, 120, 230, 255), outline=(0, 0, 0, 255),
                  width=line)
        ball(48 * u, 70 * u, 14 * u)
    elif kind == "Wolf":  # a grey wolf's head under a yellow moon
        d.ellipse((58 * u, 12 * u, 80 * u, 34 * u), fill=(255, 238, 0, 255), outline=(0, 0, 0, 255), width=line)
        head = [(22, 14), (36, 34), (60, 34), (74, 14), (78, 46), (70, 62), (58, 78), (48, 86), (38, 78),
                (26, 62), (18, 46)]
        d.polygon([(x * u, y * u) for x, y in head], fill=(120, 124, 136, 255), outline=(0, 0, 0, 255),
                  width=line)
        for ear in ([(26, 22), (34, 34), (28, 38)], [(70, 22), (62, 34), (68, 38)]):
            d.polygon([(x * u, y * u) for x, y in ear], fill=(240, 160, 170, 255))
        d.polygon([(x * u, y * u) for x, y in [(40, 56), (56, 56), (58, 70), (48, 82), (38, 70)]],
                  fill=(225, 225, 230, 255))
        for x in (36, 60):
            d.ellipse(((x - 6) * u, 42 * u, (x + 6) * u, 52 * u), fill=(255, 220, 0, 255), outline=(0, 0, 0, 255),
                      width=2 * scale)
            d.ellipse(((x - 2) * u, 44 * u, (x + 2) * u, 50 * u), fill=(0, 0, 0, 255))
        d.ellipse((43 * u, 60 * u, 53 * u, 68 * u), fill=(20, 20, 20, 255))
    elif kind == "Team Worst Ball":   # a whole team's balls, a blue arrow down to the one it must play
        for x, y in ((18, 26), (78, 26), (20, 62), (76, 62)):
            ball(x * u, y * u, 9 * u)
        d.polygon([(41 * u, 10 * u), (55 * u, 10 * u), (55 * u, 32 * u), (65 * u, 32 * u), (48 * u, 50 * u),
                   (31 * u, 32 * u), (41 * u, 32 * u)], fill=(40, 120, 230, 255), outline=(0, 0, 0, 255),
                  width=line)
        ball(48 * u, 70 * u, 14 * u)
    else:             # Team Scramble: a whole team's balls round the starred one
        star(48 * u, 46 * u, 26 * u, 11 * u)
        ball(48 * u, 46 * u, 12 * u)
        for x, y in ((22, 30), (74, 30), (24, 72), (72, 72)):
            ball(x * u, y * u, 10 * u)
    small = img.resize((size, size), Image.BOX)
    return np.asarray(small)


def append_textures(blob, new):
    """A texture file with more textures: new = [(header 0x24 bytes, data)] (data offset in the header is set
    here). Existing headers and data keep their bytes; the table, headers and data are laid out again."""
    count = struct.unpack_from(">I", blob, 4)[0]
    old = []
    for h, w, ht, fmt, at, lod in textures.headers(blob):
        size = textures.level_size(w, ht, fmt)
        levels = lod + 1
        total, lw, lh = 0, w, ht
        for _ in range(levels):
            total += max(textures.level_size(lw, lh, fmt), 32)
            lw, lh = max(1, lw // 2), max(1, lh // 2)
        old.append((bytes(blob[h:h + 0x24]), bytes(blob[at:at + (total if levels > 1 else size)])))
    items = old + new
    n = len(items)
    table = 0xC + 8 * n
    head_at = table
    data_at = -(-(head_at + 0x24 * n) // 32) * 32
    out = bytearray(data_at)
    struct.pack_into(">III", out, 0, textures.MAGIC, n, 0xC)
    for k, (hdr, data) in enumerate(items):
        h = head_at + 0x24 * k
        struct.pack_into(">II", out, 0xC + 8 * k, h, 0)
        out[h:h + 0x24] = hdr
        struct.pack_into(">I", out, h + 8, len(out))
        out += data
        out += b"\x00" * (-len(out) % 32)
    if count + len(new) != n:
        raise SystemExit("texture count mismatch")
    return bytes(out)


def _header_like(template, w, h):
    hdr = bytearray(template)
    struct.pack_into(">I", hdr, 0, h << 16 | w)
    return bytes(hdr)


def icons_file(clean_files):
    raw = open(os.path.join(clean_files, *ICONS.split("/")), "rb").read()
    kind, _ = lz.header(raw)
    blob = textures.load_bytes(raw)
    hs = textures.headers(blob)
    if len(hs) != FIRST_TEX or any((w, ht, fmt) != (96, 96, 14) for _, w, ht, fmt, _, _ in hs):
        raise SystemExit(f"{ICONS}: not the 25 96x96 CMPR icons")
    import shyguy
    template = bytes(blob[hs[0][0]:hs[0][0] + 0x24])
    new = [(template, shyguy.cmpr(icon_image(name))) for name in NAMES]
    return lz.pack(kind, append_textures(blob, new))


def banners_file(clean_files):
    """B/V/T with texture TEAM_BANNER (the carousel's "Doubles", 172x50 IA4) redrawn in place as TEAM_NAME."""
    raw = open(os.path.join(clean_files, *BANNERS.split("/")), "rb").read()
    kind, _ = lz.header(raw)
    blob = bytearray(textures.load_bytes(raw))
    h, w, ht, fmt, at, lod = textures.headers(blob)[TEAM_BANNER]
    if (w, ht, fmt) != (172, 50, 2):
        raise SystemExit(f"{BANNERS} texture {TEAM_BANNER}: not the 172x50 IA4 Doubles banner")
    img = label_image(TEAM_NAME, height=46, size=40, outline=5)
    if img.shape[1] > w - 4:      # squeeze it to fit
        from PIL import Image
        img = np.asarray(Image.fromarray(img).resize((w - 4, img.shape[0]), Image.BOX))
    pic = np.zeros((ht, w, 4), np.uint8)
    x0 = (w - img.shape[1]) // 2
    pic[0:img.shape[0], x0:x0 + img.shape[1]] = img
    data = encode_ia4(pic)
    blob[at:at + len(data)] = data
    return lz.pack(kind, bytes(blob))


def labels_file(clean_files):
    raw = open(os.path.join(clean_files, *LABELS.split("/")), "rb").read()
    kind, _ = lz.header(raw)
    blob = textures.load_bytes(raw)
    hs = textures.headers(blob)
    if len(hs) != FIRST_TEX or any(fmt != 2 for _, _, _, fmt, _, _ in hs):
        raise SystemExit(f"{LABELS}: not the 25 IA4 labels")
    template = bytes(blob[hs[0][0]:hs[0][0] + 0x24])
    new = []
    for name in NAMES:
        img = label_image(name)
        new.append((_header_like(template, img.shape[1], img.shape[0]), encode_ia4(img)))
    return lz.pack(kind, append_textures(blob, new))
