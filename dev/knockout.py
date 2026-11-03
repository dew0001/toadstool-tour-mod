"""v30 Knockout, a Team Play game (Andrew, 2026-11-02): "2v2 and 2,3,4 player free for all knockout, pretty simple
everyone goes and worse score loses a life (you get 3 lives) if everyone ties no one loses a life and move on to next
hole", then "once ur out of lives ur done playing, and the game ends with last person standing". v31: "instead of ties
it should be a playoff shot closest to the pin. that would be for the bottom 2 players that tied in a 3 or 4 player
knockout and for the 2v2 knockout it would be between the 2 teams that tied. a random place on that same hole in the
rough, bunker, or fairway within 100 yards" (his blacked-out screens for those not hitting: dropped, "forget about
that": NetPlay shows everyone the same picture), then "for 2v2 make it 3 lives per team and no playoffs, ties push, if
tied with amount of lives after 18 then a random closest to the pin on any hole with the same 100 yard random shot" and
"2 player knockout should work the same": a 2-player round and 2v2 push a tied hole; the 3-4 player playoff stays.

Knockout (choice 11, 2-4 humans) and Knockout 2v2 (choice 13, 4 humans: 1P and 2P against 3P and 4P, the game's own
first team layout) play as a Wolf round (teams.py: the game's Skins round, everyone on their own ball, team mode WOLF)
with the setup block's spare byte 0x8017607F (teams.KO_BYTE) saying which: so every teams.py path that is right for
Wolf is right here, and four of the Wolf's hooks get a stub of ours in front (in the golf overlay's tail, golfext.py):
  - ko_pick (the shooter pick, FUN_80402f1c): on a new hole, players out of lives are done before it starts (record
    +0x1BE = 2, so the pick passes them over), every player's result byte for the hole is "no skin", and a notice
    (rules on the first hole, then the last hole's playoff and who lost a life) opens in the game's tip box
    (0x80505358: the first shooter's aim waits for A, which closes it; FUN_80423bbc's state 4).
  - ko_score (scoring after a shot, FUN_8046a0b8): stroke play's scoring for the shot (sub-mode 0 around it, as the
    Wolf's), then ko_check: once every player with lives is done, the worst score loses a life, or in 2v2 the team
    whose best ball is worse. With 3 or 4 players a tie at the worst is played off (v31): one random spot on the hole
    (ko_spot: fairway, first cut, rough or a bunker, 20-100 yards from the pin, not out of bounds or a hazard), the
    tied players' lies moved there with their status back to "playing" and strokes 0, one shot each (done after it);
    the farthest from the pin loses a life (out of bounds or in the water: the farthest); the same distance for
    everyone (all holed): nobody. A 2-player round and 2v2 push a tied hole. When one player or team is left the
    round's hole count (state +0xAD0, 0x804E66B4) becomes this hole + 1, so the round ends after it (the next-hole
    step's round-over test FUN_804034e0: hole >= count - 1) and the results rank by lives.
  - The tiebreaker (v31): the round's last hole decided with two or more level on the most lives (2v2: the teams), the
    leaders are noted (tb 1); ko_over, in front of FUN_804034e0, does what the game does for a match play round level
    after its last hole (FUN_80403680): the hole count 1 and state +0x3E = 1 ("not over"), so the next-hole step
    starts hole slot (hole + 1) % 1 = 0, whose hole (state +0xAB4 + slot, the round's hole order) we make a random one
    of the 18. Its pick (tb 2) sets the leaders up as a playoff from a random spot, the rest sit out; +0x3E goes back to
    0, so the round ends after it unless the leaders are level again (another one). The farther ball loses a life
    (2v2: each team's closest ball).
  - ko_points (FUN_80469720, the points the score panel, scoreboard and results show for Skins): the player's lives.
  - ko_totals (the scorecards' Skins totals): every player's lives, nothing carried.
The Wolf's other hooks see team mode WOLF and do the Wolf's no-op (a tied hole carries nothing; marks are for winners,
and here nobody wins a skin). RE-NOTES "Knockout (v30)".
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppc  # noqa: E402
import golfext  # noqa: E402
import teams  # noqa: E402

FFA, TWO = 1, 2                 # teams.KO_BYTE: Knockout, Knockout 2v2
LIVES = 3
MSG_HELP, MSG_HELP2, MSG_NOTICE = 0x7FBA, 0x7FBB, 0x7FBC
MENU_CAVE = (0x8006FA48, 204, 0x9421FFD8)    # a dead main.dol function (mod/ghidra_out/golf/dead_unused.txt)
HELP_TEXT = b"\x074\x0942-4 players, 3 lives each.\x01Worst score loses a life!\x00"
HELP2_TEXT = b"\x074\x094Two-vs-two, 3 lives a team.\x01Worse best ball loses one!\x00"

# the round (golf overlay)
SETUP_KO = 0x80175600 + teams.KO_BYTE        # main.dol's setup block + 0xA7F = 0x8017607F (read in the round)
HOLE = teams.HOLE_INDEX                      # 0x804E68F8, the round's hole (byte)
PLAYERS_N = teams.D15                        # 0x804E68F9: sides; in a round of single players, the players
HOLE_COUNT = 0x804E66B4                      # golf state +0xAD0: the round's holes (byte; the setup block's 0xA7C)
TIP_BOX = 0x80505358                         # the game's hole tip box: while set, the shooter's aim waits for A
BOX_OPEN = 0x80024F1C                        # (message, x, y, -1, style) -> a box sized to its text
TIP_X, TIP_Y, TIP_STYLE = 320, 224, 15       # where and how the game opens its own tip
PIN = 0x804E6864                             # x, y, z
REC_LIE, REC_PENALTY = teams.REC_LIE, teams.REC_PENALTY_KIND   # record: the lie (0x34), the last penalty (1 drop, 2 OB)
LIE_SIZE = 0x34                              # +0 xyz, +0xC the ball's spin, +0x1C the ground's normal (ball +0xA8),
                                             # +0x28 in the hole, +0x29 zone, +0x2A ball +0x75, +0x2C surface, +0x30
                                             # ball +0xBC (FUN_80414a1c saves one from a ball, FUN_80414970 the reverse)
# v31 the playoff's spot
GROUND = 0x8040100C                          # (f1 x, f2 y, f3 z, r3 out[6]): the ground under a point, its normal
RAYCAST = 0x804379B4                         # (r3 results, r4 ray, r5 1): what the ground query and the ball step use
ALLOC, FREE = 0x8001A670, 0x8001A85C
RAND = 0x8001AA54                            # f1 = a random number in [0, 1)
DISTANCE = 0x80019DA4                        # (double dx, double dz) -> double
RAY_K = 0x804DA30C                           # the ground query's floats: +9.6 up, then the ray's direction and length
SPOT_MIN, SPOT_MAX = 60.0, 300.0             # feet from the pin (Andrew: "within 100 yards")
SPOT_TRIES = 64
SPOT_SURFACES = (0x01, 0x11, 0x0A, 0x04, 0x16, 0x03, 0x21, 0x24)   # fairway, fast fairway, first cut, rough, heavy
                                             # rough, bunker, grass bunker, beach bunker (collision.md's table)
FAR = 99999.0                                # a playoff shot out of bounds or in the water
TEXT_SIZE = 384
# v31 the tiebreaker: the round-over test at the next-hole step (state +0x3E: 1 = go on, as match play's extra holes)
OVER = (0x804034E0, 0x9421FFE8)              # stwu r1,-24(r1): FUN_804034e0(state)
ST_GO_ON, ST_ORDER, ST_COUNT = 0x3E, 0xAB4, 0xAD0
HOLES = 18
RULES = b"\x074Knockout! 3 lives each:\x01the worst score on a hole\x01loses a life. A tie: a\x01playoff, closest to the pin.\x00"
RULES_2 = (b"\x074Knockout! 3 lives each:\x01the worse score on a hole\x01loses a life; a tie, nobody.\x01Level at the end:"
           b" one shot\x01each, closest to the pin.\x00")
RULES2_HEAD = b"\x074Knockout: \x00"
AMP = b" & \x00"
VS = b"\x01vs \x00"
RULES2_TAIL = (b"!\x01The worse best ball loses\x01a life; a tie, nobody.\x01Level at the end: one shot\x01each, closest to"
               b" the pin.\x00")
TB_START = b"\x01Level on lives: a tiebreaker\x01on a random hole, closest\x01to the pin:\x01\x00"
TIE = b"\x074Tied hole: no lives lost!\x00"
SIZE4 = b"\x074\x00"
OUT = b" is knocked out!\x00"
LOSES = b" loses a life: \x00"
LOSE2 = b" lose a life: \x00"
LEFT = b" left\x00"
PO_START = b"\x074Tied! A playoff from here,\x01closest to the pin:\x01\x00"
COMMA = b", \x00"
PO_RESULT = b"\x074Closest to the pin:\x00"
NL = b"\x01\x00"
SPACE = b" \x00"
FEET = b" ft\x00"
HOLED = b" in the hole!\x00"
MISSED = b" out of play\x00"
TIE_AGAIN = b"\x01Tied again: no lives lost!\x00"


def lbzu(rd, d, ra):
    return ppc._d(35, rd, d, ra)


def stbu(rs, d, ra):
    return ppc._d(39, rs, d, ra)


def fabs(d, b):
    return 0xFC000210 | d << 21 | b << 11


BNE, BEQLR = 0x40820000, 0x4D820020


def menu_cave(w):
    """(address, first word, code, labels) for the menu overlay's commit; w = teams.py's v20 labels."""
    at, size, first = MENU_CAVE
    a = ppc.Asm(at)
    # (b from teams.py's commit, r9 = the choice, at least CHOICE_KNOCKOUT; r11 = the setup block)
    a.label("ko_commit")
    a(ppc.cmpwi(9, teams.CHOICE_WOLF))
    a.br("bne", "kc_mine")
    a.b(w["commit_wolf"])
    a.label("kc_mine")
    a(ppc.li(0, FFA), ppc.cmpwi(9, teams.CHOICE_KNOCKOUT))
    a.br("beq", "kc_set")
    a(ppc.li(0, TWO))
    a.label("kc_set")                         # a Skins game of everyone, the Wolf's way (mode 2, sub-mode 3), and
    a(ppc.stb(0, teams.KO_BYTE, 11), ppc.li(0, teams.WOLF), ppc.stb(0, teams.MODE_BYTE, 11), ppc.li(0, 2),
      ppc.stw(0, 0xA80, 11), ppc.li(0, 3), ppc.stw(0, 0xA84, 11), ppc.li(3, 3))    # straight to the course select
    a.bl(teams.SCREEN_PUSH)
    a.bl(teams.COURSE_LIST)
    a.b(teams.COMMIT_END)
    for name, text in (("help", HELP_TEXT), ("help2", HELP2_TEXT)):
        a.label(name)
        a(*struct.unpack(f">{-(-len(text) // 4)}I", text + bytes(-len(text) % 4)))
    code = a.assemble()
    if len(code) > size:
        raise SystemExit(f"knockout menu cave: {len(code)} bytes; only {size} fit")
    return at, first, code, a.labels


def menu_texts(labels):
    return [(MSG_HELP, labels["help"]), (MSG_HELP2, labels["help2"])]


def base():
    """Where our code starts in the golf tail: its start, or after fbpose.py's players when Pigskin is built."""
    return golfext.BASE + (0x10000 if teams.PIGSKIN else 0)


def _kind(a, team_mode, tag):
    """r12 = Knockout's kind (0: not Knockout), cr0 = r12 vs 0. Uses r11."""
    hi, lo = ppc.hi_lo(team_mode)
    a(ppc.lis(12, hi), ppc.lwz(11, lo, 12))
    hi, lo = ppc.hi_lo(SETUP_KO)
    a(ppc.lis(12, hi), ppc.lbz(12, lo, 12), ppc.cmpwi(11, teams.WOLF))
    a.br("beq", f"kind_{tag}")
    a(ppc.li(12, 0))
    a.label(f"kind_{tag}")
    a(ppc.cmpwi(12, 0))


def _player(a, reg, index_reg):
    """reg = player index_reg's record (uses r12)."""
    a(ppc.mulli(reg, index_reg, teams.PLAYER_SIZE))
    hi, lo = ppc.hi_lo(teams.PLAYERS)
    a(ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.add(reg, reg, 12))


def _enter(a, size, first):
    a(ppc.stwu(1, -size, 1), ppc.mflr(0), ppc.stw(0, size + 4, 1), ppc.stmw(first, size - 4 * (32 - first), 1))


def _leave(a, size, first):
    a(ppc.lmw(first, size - 4 * (32 - first), 1), ppc.lwz(0, size + 4, 1), ppc.mtlr(0), ppc.addi(1, 1, size), ppc.BLR)


def _string(a, name, text):
    a.label(name)
    a(*struct.unpack(f">{-(-len(text) // 4)}I", text + bytes(-len(text) % 4)))


def _float(a, name, value):
    a.label(name)
    a(struct.unpack(">I", struct.pack(">f", value))[0])


def make_tail(labels, B):
    a = ppc.Asm(B)
    # ---- data (the tail loads fresh with every round, so these are a round's starting values)
    a.label("lives")
    a(*([(LIVES << 24 | LIVES << 16 | LIVES << 8 | LIVES)]))
    a.label("losts")                          # the last hole's losers (bytes)
    a(0)
    a.label("scores")                         # this hole's scores (0xFF: out of lives)
    a(0)
    a.word("scored", 0)                       # this hole is decided
    a.word("po", 0)                           # v31 the playoff: 0 none, 1 under way, 2 decided this hole
    a.label("in_po")                          # bytes: 1 in the playoff, 2 has hit
    a(0)
    a.word("hole_seen", -1)                   # (-2: a tiebreaker's slot, which may be the one just played)
    a.word("tb", 0)                           # the tiebreaker: 1 due after this hole, 2 its hole is next, 3 under way
    a.label("tb_in")                          # bytes: in it (the leaders)
    a(0)
    a.label("pdist")                          # each player's playoff shot: feet from the pin
    a(0, 0, 0, 0)
    if (a.here() - B) % 8:
        a(0)
    a.label("tmp")                            # 8 bytes for a float's integer (stfd: 8-byte aligned)
    a(0, 0)
    assert (a.labels["tmp"] - B) % 8 == 0
    a.label("gq")                             # the ground query's point and normal
    a(*([0] * 6))
    a.label("spot")                           # the playoff's lie
    a(*([0] * (LIE_SIZE // 4)))
    a.label("numbuf")
    a(0, 0, 0)
    a.label("text")
    a(*([0] * (TEXT_SIZE // 4)))
    for name, value in (("zero", 0.0), ("one", 1.0), ("two", 2.0), ("spot_max", SPOT_MAX), ("min2", SPOT_MIN ** 2),
                        ("max2", SPOT_MAX ** 2), ("up", 100.0), ("probe", 5.0), ("far", FAR), ("farther", 2 * FAR),
                        ("neg", -1.0), ("half_far", FAR / 2), ("holes", float(HOLES)), ("half", 0.5)):
        _float(a, name, value)
    a.label("surfaces")
    blob = bytes(SPOT_SURFACES) + b"\xFF"
    a(*struct.unpack(f">{-(-len(blob) // 4)}I", blob + bytes(-len(blob) % 4)))
    strings = (("rules", RULES), ("rules_2", RULES_2), ("rules2_head", RULES2_HEAD), ("amp", AMP), ("vs", VS),
               ("rules2_tail", RULES2_TAIL), ("tie", TIE), ("size4", SIZE4), ("out", OUT), ("loses", LOSES),
               ("lose2", LOSE2), ("left", LEFT), ("po_start", PO_START), ("comma", COMMA), ("po_result", PO_RESULT),
               ("nl", NL), ("space", SPACE), ("feet", FEET), ("holed", HOLED), ("missed", MISSED),
               ("tie_again", TIE_AGAIN), ("tb_start", TB_START))
    for name, text in strings:
        _string(a, name, text)
    names = b""
    offsets = []
    for name in teams.GOLFER_NAMES:
        offsets.append(len(names))
        names += name.encode() + b"\x00"
    _string(a, "name_offsets", bytes(offsets))
    _string(a, "names", names)
    L = a.labels

    def off(name):
        return L[name] - B

    team_mode = labels["data_team_mode"]

    # ---- kt_str: (r3 = where, r4 = a string) copies it with its 0; r3 -> that 0 (the next string goes there). Uses r0.
    a.label("kt_str")
    a(ppc.addi(4, 4, -1))
    a.label("ks_loop")
    a(lbzu(0, 1, 4), ppc.stb(0, 0, 3), ppc.cmpwi(0, 0), BEQLR, ppc.addi(3, 3, 1))
    a.br("b", "ks_loop")

    # ---- kt_name: (r3 = where, r4 = a player) its golfer's name, as kt_str. Uses r0, r4, r11, r12.
    a.label("kt_name")
    _player(a, 4, 4)
    a(ppc.lbz(4, teams.PLAYER_GOLFER, 4), ppc.cmplwi(4, len(teams.GOLFER_NAMES) - 1))
    a.br("ble", "kn_ok")
    a(ppc.li(4, len(teams.GOLFER_NAMES) - 1))
    a.label("kn_ok")
    a.la(11, "name_offsets")
    a(ppc.lbzx(4, 11, 4))
    a.la(11, "names")
    a(ppc.add(4, 4, 11))
    a.br("b", "kt_str")

    # ---- kt_num: (r3 = where, r4 = a number >= 0) its digits, as kt_str. Uses r0, r4, r9-r12.
    a.label("kt_num")
    a.la(11, "numbuf")
    a(ppc.addi(11, 11, 11), ppc.mr(10, 11), ppc.li(12, 10))
    a.label("kn_digit")
    a(ppc.divw(9, 4, 12), ppc.mullw(0, 9, 12), ppc.subf(0, 0, 4), ppc.ori(0, 0, 0x30), stbu(0, -1, 11),
      ppc.mr(4, 9), ppc.cmpwi(4, 0))
    a.br("bne", "kn_digit")
    a.label("kn_copy")
    a(ppc.cmpw(11, 10))
    a.br("bge", "kn_end")
    a(ppc.lbz(0, 0, 11), ppc.stb(0, 0, 3), ppc.addi(3, 3, 1), ppc.addi(11, 11, 1))
    a.br("b", "kn_copy")
    a.label("kn_end")
    a(ppc.li(0, 0), ppc.stb(0, 0, 3), ppc.BLR)

    # ---- kt_dist: (r3 = where, r4 = a player; r30 = our data) " 12 ft", " in the hole!" or " out of play". Uses r0,
    # r4, r9-r12, f0, f1.
    a.label("kt_dist")
    a(ppc.slwi(4, 4, 2), ppc.addi(4, 4, off("pdist")), ppc.add(4, 4, 30), ppc.lfs(1, 0, 4), ppc.lfs(0, off("zero"), 30),
      ppc.fcmpu(1, 0))
    a.br("bne", "kd_not_in")
    a(ppc.addi(4, 30, off("holed")))
    a.br("b", "kt_str")
    a.label("kd_not_in")
    a(ppc.lfs(0, off("half_far"), 30), ppc.fcmpu(1, 0))
    a.br("blt", "kd_feet")
    a(ppc.addi(4, 30, off("missed")))
    a.br("b", "kt_str")
    a.label("kd_feet")
    a(ppc.lfs(0, off("half"), 30), ppc.fadds(1, 1, 0), ppc.fctiwz(0, 1), ppc.stfd(0, off("tmp"), 30),   # (rounded)
      ppc.stwu(1, -0x10, 1), ppc.mflr(0), ppc.stw(0, 0x14, 1),
      ppc.stw(3, 0x08, 1), ppc.addi(4, 30, off("space")))
    a.br("bl", "kt_str")
    a(ppc.lwz(4, off("tmp") + 4, 30))
    a.br("bl", "kt_num")
    a(ppc.addi(4, 30, off("feet")))
    a.br("bl", "kt_str")
    a(ppc.lwz(0, 0x14, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x10), ppc.BLR)

    # ---- ko_attr: (f1 x, f2 y, f3 z) -> r3 = the collision attribute right under the point (the ground query's ray,
    # its first hit's +0x20, as the ball step reads it: bits 0-7 surface, 13-14 zone), -1 when nothing is there
    a.label("ko_attr")
    _enter(a, 0x60, 30)
    hi, lo = ppc.hi_lo(RAY_K)
    a(ppc.lis(9, hi), ppc.lfs(0, lo, 9), ppc.fadds(2, 2, 0), ppc.stfs(1, 0x08, 1), ppc.stfs(2, 0x0C, 1),
      ppc.stfs(3, 0x10, 1), ppc.lfs(13, lo + 4, 9), ppc.lfs(0, lo + 8, 9), ppc.stfs(13, 0x14, 1), ppc.stfs(0, 0x18, 1),
      ppc.stfs(13, 0x1C, 1), ppc.lfs(0, lo + 12, 9), ppc.stfs(0, 0x20, 1), ppc.li(3, 0x34))
    a.bl(ALLOC)
    a(ppc.stw(3, 0x28, 1), ppc.li(3, 4))
    a.bl(ALLOC)
    a(ppc.stw(3, 0x2C, 1), ppc.lwz(0, 0x28, 1), ppc.stw(0, 0, 3), ppc.li(0, 1), ppc.stw(0, 0x30, 1), ppc.li(0, 0),
      ppc.stw(0, 0x34, 1), ppc.stw(0, 0x38, 1), ppc.stw(0, 0x44, 1), ppc.addi(3, 1, 0x28), ppc.addi(4, 1, 0x08),
      ppc.li(5, 1))
    a.bl(RAYCAST)
    a(ppc.li(31, -1), ppc.lwz(0, 0x34, 1), ppc.cmpwi(0, 0))
    a.br("beq", "ka_free")
    a(ppc.lwz(9, 0x2C, 1), ppc.lwz(9, 0, 9), ppc.lhz(31, 0x20, 9))
    a.label("ka_free")
    a(ppc.lwz(3, 0x2C, 1))
    a.bl(FREE)
    a(ppc.lwz(3, 0x28, 1))
    a.bl(FREE)
    a(ppc.mr(3, 31))
    _leave(a, 0x60, 30)

    # ---- ko_spot: (r3 = a playoff player, whose lie is the template; r30 = our data) -> r3 = 1 when "spot" holds the
    # playoff's lie: random points 60-300 ft from the pin until one is on SPOT_SURFACES, in play
    a.label("ko_spot")
    _enter(a, 0x40, 26)
    a(ppc.mr(26, 3), ppc.li(28, SPOT_TRIES))
    a.label("sp_try")
    a.bl(RAND)
    a(ppc.lfs(0, off("two"), 30), ppc.lfs(2, off("one"), 30), ppc.fmuls(1, 1, 0), ppc.fsubs(1, 1, 2),
      ppc.lfs(0, off("spot_max"), 30), ppc.fmuls(1, 1, 0), ppc.stfs(1, 0x08, 1))
    a.bl(RAND)
    a(ppc.lfs(0, off("two"), 30), ppc.lfs(2, off("one"), 30), ppc.fmuls(1, 1, 0), ppc.fsubs(1, 1, 2),
      ppc.lfs(0, off("spot_max"), 30), ppc.fmuls(1, 1, 0), ppc.stfs(1, 0x0C, 1), ppc.lfs(2, 0x08, 1),
      ppc.fmuls(3, 2, 2), ppc.fmadds(3, 1, 1, 3), ppc.lfs(0, off("min2"), 30), ppc.fcmpu(3, 0))
    a.br("blt", "sp_next")
    a(ppc.lfs(0, off("max2"), 30), ppc.fcmpu(3, 0))
    a.br("bgt", "sp_next")
    hi, lo = ppc.hi_lo(PIN)
    a(ppc.lis(9, hi), ppc.lfs(0, lo, 9), ppc.fadds(1, 2, 0), ppc.lfs(0, lo + 8, 9), ppc.lfs(3, 0x0C, 1),
      ppc.fadds(3, 3, 0), ppc.stfs(1, 0x08, 1), ppc.stfs(3, 0x0C, 1), ppc.lfs(2, lo + 4, 9), ppc.lfs(0, off("up"), 30),
      ppc.fadds(2, 2, 0), ppc.stfs(2, 0x10, 1), ppc.addi(3, 30, off("gq")))
    a.bl(GROUND)                              # (nothing hit: out[1] stays the start, 9.6 up)
    a(ppc.lfs(1, off("gq") + 4, 30), ppc.lfs(2, 0x10, 1), ppc.fcmpu(1, 2))
    a.br("bge", "sp_next")
    a(ppc.lfs(0, off("probe"), 30), ppc.fadds(2, 1, 0), ppc.lfs(1, 0x08, 1), ppc.lfs(3, 0x0C, 1))
    a.br("bl", "ko_attr")
    a(ppc.cmpwi(3, 0))
    a.br("blt", "sp_next")
    a(ppc.rlwinm(0, 3, 19, 30, 31), ppc.cmpwi(0, 0))   # (attribute >> 13) & 3: out of bounds or a hazard
    a.br("bne", "sp_next")
    a(ppc.andi_(27, 3, 0xFF), ppc.addi(9, 30, off("surfaces") - 1))
    a.label("sp_surface")
    a(lbzu(0, 1, 9), ppc.cmpwi(0, 0xFF))
    a.br("beq", "sp_next")
    a(ppc.cmpw(0, 27))
    a.br("bne", "sp_surface")
    # found: the template's lie with this place, the ground's normal and surface, not in the hole, in play
    _player(a, 9, 26)
    a(ppc.lwz(9, teams.PLAYER_REC, 9), ppc.addi(9, 9, REC_LIE - 4), ppc.addi(10, 30, off("spot") - 4),
      ppc.li(0, LIE_SIZE // 4), ppc.mtctr(0))
    a.label("sp_copy")
    a(ppc.lwzu(0, 4, 9), ppc.stwu(0, 4, 10))
    a.br("bdnz", "sp_copy")
    a(ppc.lfs(0, 0x08, 1), ppc.stfs(0, off("spot"), 30), ppc.lfs(0, off("gq") + 4, 30), ppc.stfs(0, off("spot") + 4, 30),
      ppc.lfs(0, 0x0C, 1), ppc.stfs(0, off("spot") + 8, 30))
    for k in range(3):
        a(ppc.lfs(0, off("gq") + 12 + 4 * k, 30), ppc.stfs(0, off("spot") + 0x1C + 4 * k, 30))
    a(ppc.li(0, 0), ppc.stb(0, off("spot") + 0x28, 30), ppc.stb(0, off("spot") + 0x29, 30),
      ppc.stb(0, off("spot") + 0x2A, 30), ppc.stw(27, off("spot") + 0x2C, 30), ppc.li(0, -1),
      ppc.stw(0, off("spot") + 0x30, 30), ppc.li(3, 1))
    a.br("b", "sp_out")
    a.label("sp_next")
    a(ppc.addi(28, 28, -1), ppc.cmpwi(28, 0))
    a.br("bgt", "sp_try")
    a(ppc.li(3, 0))
    a.label("sp_out")
    _leave(a, 0x40, 26)

    # ---- ko_pick (b from teams.PICKER, r3 = the golf state)
    a.label("ko_pick")
    _kind(a, team_mode, "pick")
    a.br("bne", "kp_go")
    a.b(labels["w_wolf_pick"])
    a.label("kp_go")
    _enter(a, 0x40, 20)
    a(ppc.mr(31, 3), ppc.mr(24, 12))
    a.la(30, "lives")                         # r30 = our data
    hi, lo = ppc.hi_lo(HOLE)
    a(ppc.lis(12, hi), ppc.lbz(29, lo, 12), ppc.lwz(28, off("hole_seen"), 30), ppc.cmpw(28, 29))
    a.br("beq", "kp_game")
    # a new hole: those out of lives are done; nobody's result is a skin
    a(ppc.stw(29, off("hole_seen"), 30), ppc.li(0, 0), ppc.stw(0, off("scored"), 30))
    hi, lo = ppc.hi_lo(PLAYERS_N)
    a(ppc.lis(12, hi), ppc.lbz(27, lo, 12), ppc.li(26, 0))
    a.label("kp_loop")
    _player(a, 25, 26)
    a(ppc.lwz(11, teams.PLAYER_CARD, 25), ppc.slwi(10, 29, 3), ppc.li(0, 1), ppc.stbx(0, 11, 10))
    a(ppc.lbzx(0, 30, 26), ppc.cmpwi(0, 0))
    a.br("beq", "kp_sit")
    a(ppc.lwz(0, off("tb"), 30), ppc.cmpwi(0, 2))     # a tiebreaker's hole: the rest sit it out
    a.br("bne", "kp_next")
    a(ppc.addi(12, 30, off("tb_in")), ppc.lbzx(0, 12, 26), ppc.cmpwi(0, 0))
    a.br("bne", "kp_next")
    a.label("kp_sit")
    a(ppc.lwz(11, teams.PLAYER_REC, 25), ppc.li(0, 2), ppc.stb(0, teams.REC_STATUS, 11))
    a.label("kp_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kp_loop")
    # the notice: the rules on the round's first hole, then the last hole's playoff and losers
    a(ppc.addi(3, 30, off("text")), ppc.cmpwi(28, -1))
    a.br("bne", "kp_result")
    a(ppc.cmpwi(24, TWO))
    a.br("beq", "kp_rules2")
    a(ppc.addi(4, 30, off("rules")), ppc.cmpwi(27, 2))
    a.br("bgt", "kp_rules_n")
    a(ppc.addi(4, 30, off("rules_2")))        # two players: a tie pushes
    a.label("kp_rules_n")
    a.br("bl", "kt_str")
    a.br("b", "kp_show")
    a.label("kp_rules2")                      # "Knockout: A & B / vs C & D! / The worse best ball loses a life ..."
    a(ppc.addi(4, 30, off("rules2_head")))
    a.br("bl", "kt_str")
    for k in range(4):
        a(ppc.li(4, k))
        a.br("bl", "kt_name")
        if k < 3:
            a(ppc.addi(4, 30, off("vs" if k == 1 else "amp")))
            a.br("bl", "kt_str")
    a(ppc.addi(4, 30, off("rules2_tail")))
    a.br("bl", "kt_str")
    a.br("b", "kp_show")
    a.label("kp_result")
    a(ppc.lwz(0, off("po"), 30), ppc.cmpwi(0, 2))
    a.br("bne", "kp_plain")
    # v31 the playoff: everyone's distance, then the losers (or a tie again)
    a(ppc.addi(4, 30, off("po_result")))
    a.br("bl", "kt_str")
    a(ppc.li(21, 0))
    a.label("kp_po_loop")
    a(ppc.addi(12, 30, off("in_po")), ppc.lbzx(0, 12, 21), ppc.cmpwi(0, 0))
    a.br("beq", "kp_po_next")
    a(ppc.addi(4, 30, off("nl")))
    a.br("bl", "kt_str")
    a(ppc.mr(4, 21))
    a.br("bl", "kt_name")
    a(ppc.mr(4, 21))
    a.br("bl", "kt_dist")
    a.label("kp_po_next")
    a(ppc.addi(21, 21, 1), ppc.cmpw(21, 27))
    a.br("blt", "kp_po_loop")
    a(ppc.li(20, 1), ppc.lwz(0, off("losts"), 30), ppc.cmpwi(0, 0))
    a.br("bne", "kp_lines")
    a(ppc.addi(4, 30, off("tie_again")))
    a.br("bl", "kt_str")
    a.br("b", "kp_show")
    a.label("kp_plain")
    a(ppc.lwz(0, off("losts"), 30), ppc.cmpwi(0, 0))
    a.br("bne", "kp_losers")
    a(ppc.addi(4, 30, off("tie")))
    a.br("bl", "kt_str")
    a.br("b", "kp_show")
    a.label("kp_losers")
    a(ppc.addi(4, 30, off("size4")))
    a.br("bl", "kt_str")
    a(ppc.li(20, 0))                          # r20 = lines written
    a.label("kp_lines")
    a(ppc.cmpwi(24, TWO))
    a.br("beq", "kp_team")
    a(ppc.li(21, 0))                          # r21 = the player
    a.label("kp_l_loop")
    a(ppc.addi(12, 30, off("losts")), ppc.lbzx(0, 12, 21), ppc.cmpwi(0, 0))
    a.br("beq", "kp_l_next")
    a(ppc.cmpwi(20, 0))
    a.br("beq", "kp_l_first")
    a(ppc.li(0, 1), ppc.stb(0, 0, 3), ppc.addi(3, 3, 1))     # a line break
    a.label("kp_l_first")
    a(ppc.addi(20, 20, 1), ppc.mr(4, 21))
    a.br("bl", "kt_name")
    a(ppc.lbzx(0, 30, 21), ppc.cmpwi(0, 0))
    a.br("bne", "kp_l_left")
    a(ppc.addi(4, 30, off("out")))
    a.br("bl", "kt_str")
    a.br("b", "kp_l_next")
    a.label("kp_l_left")
    a(ppc.addi(4, 30, off("loses")))
    a.br("bl", "kt_str")
    a(ppc.lbzx(9, 30, 21), ppc.addi(9, 9, 0x30), ppc.stb(9, 0, 3), ppc.addi(3, 3, 1), ppc.addi(4, 30, off("left")))
    a.br("bl", "kt_str")
    a.label("kp_l_next")
    a(ppc.addi(21, 21, 1), ppc.cmpw(21, 27))
    a.br("blt", "kp_l_loop")
    a.br("b", "kp_show")
    a.label("kp_team")                        # 2v2: "A & B lose a life: n left"
    a(ppc.cmpwi(20, 0))
    a.br("beq", "kp_t_first")
    a(ppc.li(0, 1), ppc.stb(0, 0, 3), ppc.addi(3, 3, 1))
    a.label("kp_t_first")
    a(ppc.li(21, 0), ppc.lbz(0, off("losts"), 30), ppc.cmpwi(0, 0))
    a.br("bne", "kp_t")
    a(ppc.li(21, 2))
    a.label("kp_t")
    a(ppc.mr(4, 21))
    a.br("bl", "kt_name")
    a(ppc.addi(4, 30, off("amp")))
    a.br("bl", "kt_str")
    a(ppc.addi(4, 21, 1))
    a.br("bl", "kt_name")
    a(ppc.addi(4, 30, off("lose2")))
    a.br("bl", "kt_str")
    a(ppc.lbzx(9, 30, 21), ppc.addi(9, 9, 0x30), ppc.stb(9, 0, 3), ppc.addi(3, 3, 1), ppc.addi(4, 30, off("left")))
    a.br("bl", "kt_str")
    a.label("kp_show")
    a(ppc.li(0, 0), ppc.stw(0, off("po"), 30), ppc.stw(0, off("in_po"), 30))
    a(ppc.lwz(0, off("tb"), 30), ppc.cmpwi(0, 2))
    a.br("bne", "kp_notice")
    # the tiebreaker's hole: the leaders play off from a random spot; the round ends after it (+0x3E back to 0)
    a(ppc.li(0, 3), ppc.stw(0, off("tb"), 30), ppc.li(0, 0), ppc.stb(0, ST_GO_ON, 31), ppc.lwz(0, off("tb_in"), 30),
      ppc.stw(0, off("in_po"), 30), ppc.mr(22, 3), ppc.li(3, 0))
    a.label("kp_tb_first")
    a(ppc.addi(12, 30, off("in_po")), ppc.lbzx(0, 12, 3), ppc.cmpwi(0, 0))
    a.br("bne", "kp_tb_found")
    a(ppc.addi(3, 3, 1))
    a.br("b", "kp_tb_first")
    a.label("kp_tb_found")
    a.br("bl", "ko_spot")
    a(ppc.cmpwi(3, 0))
    a.br("beq", "kp_tb_none")
    a.br("bl", "ko_po_move")
    a(ppc.mr(3, 22), ppc.addi(4, 30, off("tb_start")))
    a.br("bl", "kt_str")
    a.br("bl", "ko_po_names")
    a.br("b", "kp_notice")
    a.label("kp_tb_none")                     # (no spot: they play the hole out)
    a(ppc.li(0, 0), ppc.stw(0, off("in_po"), 30), ppc.mr(3, 22))
    a.label("kp_notice")
    a.br("bl", "ko_notice")
    a.label("kp_game")                        # the game's pick
    a(ppc.mr(3, 31), ppc.lmw(20, 0x10, 1), ppc.lwz(0, 0x44, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x40))
    a(teams.PICKER[1])
    a.b(teams.PICKER[0] + 4)

    # ---- ko_notice: our text in the game's tip box (the next shooter's aim waits for A, which closes it)
    a.label("ko_notice")
    a(ppc.stwu(1, -0x10, 1), ppc.mflr(0), ppc.stw(0, 0x14, 1))
    a(ppc.li(3, MSG_NOTICE), ppc.li(4, TIP_X), ppc.li(5, TIP_Y), ppc.li(6, -1), ppc.li(7, TIP_STYLE))
    a.bl(BOX_OPEN)
    hi, lo = ppc.hi_lo(TIP_BOX)
    a(ppc.lis(12, hi), ppc.stw(3, lo, 12), ppc.lwz(0, 0x14, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x10), ppc.BLR)

    # ---- ko_score (b from teams.SCORE, r3 = the side): stroke play's scoring of the shot, then ours
    a.label("ko_score")
    _kind(a, team_mode, "score")
    a.br("bne", "ks_go")
    a.b(labels["w_wolf_score"])
    a.label("ks_go")
    a(ppc.stwu(1, -0x20, 1), ppc.mflr(0), ppc.stw(0, 0x24, 1), ppc.stmw(29, 0x14, 1))
    a(ppc.mr(30, 3), ppc.mr(29, 12))
    hi, lo = ppc.hi_lo(teams.STATE_SUB_MODE)
    a(ppc.lis(12, hi), ppc.li(0, 0), ppc.stw(0, lo, 12), ppc.mr(3, 30))
    a.br("bl", "ks_game")
    a(ppc.mr(31, 3))
    hi, lo = ppc.hi_lo(teams.STATE_SUB_MODE)
    a(ppc.lis(12, hi), ppc.li(0, 3), ppc.stw(0, lo, 12), ppc.mr(3, 29))
    a.br("bl", "ko_check")
    # Two sides in a Skins round: the game ends the hole the match's way (the pick, FUN_80402f1c, puts both players'
    # reactions up together, for sides whose scoring answers 5 won, 6 lost, 7 halved; until then their record +0x1BF
    # stays 1 and FUN_80402a78 keeps the hole going). Stroke play's scoring answers 0, so once the hole is decided we
    # answer: 5 kept its lives, 6 lost one, 7 nobody lost one.
    hi, lo = ppc.hi_lo(PLAYERS_N)
    a(ppc.lis(12, hi), ppc.lbz(0, lo, 12), ppc.cmpwi(0, 2))
    a.br("bne", "ks_ret")
    a.la(12, "lives")
    a(ppc.lwz(0, off("scored"), 12), ppc.cmpwi(0, 0))
    a.br("beq", "ks_ret")
    a(ppc.lwz(0, off("losts"), 12), ppc.cmpwi(0, 0), ppc.li(31, 7))
    a.br("beq", "ks_ret")
    a(ppc.addi(11, 12, off("losts")), ppc.lbzx(0, 11, 30), ppc.cmpwi(0, 0), ppc.li(31, 5))
    a.br("beq", "ks_ret")
    a(ppc.li(31, 6))
    a.label("ks_ret")
    a(ppc.mr(3, 31), ppc.lmw(29, 0x14, 1), ppc.lwz(0, 0x24, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x20), ppc.BLR)
    a.label("ks_game")
    a(teams.SCORE[1])
    a.b(teams.SCORE[0] + 4)

    # ---- ko_check (r3 = the kind): once everyone with lives is done, who loses one; a tie at the worst plays off
    a.label("ko_check")
    _enter(a, 0x50, 20)
    a(ppc.mr(24, 3))
    a.la(30, "lives")
    a(ppc.lwz(0, off("scored"), 30), ppc.cmpwi(0, 0))
    a.br("bne", "kc_out")
    hi, lo = ppc.hi_lo(PLAYERS_N)
    a(ppc.lis(12, hi), ppc.lbz(27, lo, 12), ppc.lwz(0, off("po"), 30), ppc.cmpwi(0, 1))
    a.br("beq", "kc_po")
    a(ppc.li(26, 0))
    a.label("kc_scan")                        # still playing? else its strokes (0xFF when out of lives)
    a(ppc.lbzx(0, 30, 26), ppc.li(9, 0xFF), ppc.cmpwi(0, 0))
    a.br("beq", "kc_put")
    _player(a, 25, 26)
    a(ppc.lwz(11, teams.PLAYER_REC, 25), ppc.lbz(0, teams.REC_STATUS, 11), ppc.cmpwi(0, 0))
    a.br("beq", "kc_out")
    a(ppc.lbz(9, teams.REC_STROKES, 11))
    a.label("kc_put")
    a(ppc.addi(12, 30, off("scores")), ppc.stbx(9, 12, 26), ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_scan")
    a(ppc.li(0, 0), ppc.stw(0, off("losts"), 30), ppc.stw(0, off("in_po"), 30), ppc.cmpwi(24, TWO))
    a.br("beq", "kc_teams")
    a(ppc.li(29, -1), ppc.li(26, 0))          # r29 the worst score
    a.label("kc_ext")
    a(ppc.addi(12, 30, off("scores")), ppc.lbzx(0, 12, 26), ppc.cmpwi(0, 0xFF))
    a.br("beq", "kc_ext_next")
    a(ppc.cmpw(0, 29))
    a.br("ble", "kc_ext_next")
    a(ppc.mr(29, 0))
    a.label("kc_ext_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_ext")
    a(ppc.li(28, 0), ppc.li(26, 0))           # everyone at the worst: losts and in_po, r28 counts them
    a.label("kc_mark")
    a(ppc.addi(12, 30, off("scores")), ppc.lbzx(0, 12, 26), ppc.cmpw(0, 29))
    a.br("bne", "kc_mark_next")
    a(ppc.li(0, 1), ppc.addi(12, 30, off("losts")), ppc.stbx(0, 12, 26), ppc.addi(12, 30, off("in_po")),
      ppc.stbx(0, 12, 26), ppc.addi(28, 28, 1))
    a.label("kc_mark_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_mark")
    a(ppc.cmpwi(28, 1))
    a.br("bgt", "kc_tie")
    a(ppc.li(0, 0), ppc.stw(0, off("in_po"), 30))           # one worst: it loses a life
    a.br("b", "kc_apply")
    a.label("kc_tie")                         # tied at the worst: they play off (two players: a push)
    a(ppc.li(0, 0), ppc.stw(0, off("losts"), 30), ppc.cmpwi(27, 2))
    a.br("ble", "kc_done")
    a.br("b", "kc_po_start")
    a.label("kc_teams")                       # 2v2: each team's best ball, 1P & 2P against 3P & 4P
    a(ppc.lbz(29, off("scores"), 30), ppc.lbz(0, off("scores") + 1, 30), ppc.cmpw(0, 29))
    a.br("bge", "kt_1")
    a(ppc.mr(29, 0))
    a.label("kt_1")
    a(ppc.lbz(28, off("scores") + 2, 30), ppc.lbz(0, off("scores") + 3, 30), ppc.cmpw(0, 28))
    a.br("bge", "kt_2")
    a(ppc.mr(28, 0))
    a.label("kt_2")
    a(ppc.cmpw(29, 28), ppc.li(0, 1))
    a.br("bgt", "kt_a")
    a.br("blt", "kt_b")
    a.br("b", "kc_done")                      # tied: a push
    a.label("kt_b")
    a(ppc.stb(0, off("losts") + 2, 30), ppc.stb(0, off("losts") + 3, 30))
    a.br("b", "kc_apply")
    a.label("kt_a")
    a(ppc.stb(0, off("losts"), 30), ppc.stb(0, off("losts") + 1, 30))
    a.br("b", "kc_apply")

    # the playoff starts: a spot, everyone in it moved there to play one shot, a notice
    a.label("kc_po_start")
    a(ppc.li(3, 0))
    a.label("kc_first")
    a(ppc.addi(12, 30, off("in_po")), ppc.lbzx(0, 12, 3), ppc.cmpwi(0, 0))
    a.br("bne", "kc_found_first")
    a(ppc.addi(3, 3, 1))
    a.br("b", "kc_first")
    a.label("kc_found_first")
    a.br("bl", "ko_spot")
    a(ppc.cmpwi(3, 0))
    a.br("bne", "kc_po_go")
    # (no spot found: the v30 rule, everyone tied at the worst loses one)
    a(ppc.lwz(0, off("in_po"), 30), ppc.stw(0, off("losts"), 30), ppc.li(0, 0), ppc.stw(0, off("in_po"), 30))
    a.br("b", "kc_apply")
    a.label("kc_po_go")
    a.br("bl", "ko_po_move")
    a(ppc.addi(3, 30, off("text")), ppc.addi(4, 30, off("po_start")))
    a.br("bl", "kt_str")
    a.br("bl", "ko_po_names")
    a.br("bl", "ko_notice")
    a.br("b", "kc_out")

    # the playoff under way: after each one's shot its distance, and it's done; once all have hit, the farthest loses
    a.label("kc_po")
    a(ppc.li(26, 0), ppc.li(21, 0))           # r21 = still to hit
    a.label("kc_po_loop")
    a(ppc.addi(12, 30, off("in_po")), ppc.lbzx(0, 12, 26), ppc.cmpwi(0, 1))
    a.br("bne", "kc_po_next")
    _player(a, 25, 26)
    a(ppc.lwz(23, teams.PLAYER_REC, 25), ppc.lbz(0, teams.REC_STROKES, 23), ppc.cmpwi(0, 0))
    a.br("bne", "kc_po_hit")
    a(ppc.addi(21, 21, 1))
    a.br("b", "kc_po_next")
    a.label("kc_po_hit")
    a(ppc.lbz(0, REC_PENALTY, 23), ppc.cmpwi(0, 0), ppc.lfs(1, off("far"), 30))
    a.br("bne", "kc_po_store")
    a(ppc.lbz(0, teams.REC_STATUS, 23), ppc.cmpwi(0, 1), ppc.lfs(1, off("zero"), 30))
    a.br("beq", "kc_po_store")
    hi, lo = ppc.hi_lo(PIN)
    a(ppc.lis(9, hi), ppc.lfs(0, lo, 9), ppc.lfs(1, REC_LIE, 23), ppc.fsubs(1, 1, 0), ppc.lfs(0, lo + 8, 9),
      ppc.lfs(2, REC_LIE + 8, 23), ppc.fsubs(2, 2, 0))
    a.bl(DISTANCE)
    a(ppc.frsp(1, 1))
    a.label("kc_po_store")
    a(ppc.slwi(9, 26, 2), ppc.addi(9, 9, off("pdist")), ppc.add(9, 9, 30), ppc.stfs(1, 0, 9), ppc.li(0, 2),
      ppc.addi(12, 30, off("in_po")), ppc.stbx(0, 12, 26), ppc.lbz(0, teams.REC_STATUS, 23), ppc.cmpwi(0, 0))
    a.br("bne", "kc_po_next")
    a(ppc.li(0, 2), ppc.stb(0, teams.REC_STATUS, 23))   # (one shot: done)
    a.label("kc_po_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_po_loop")
    a(ppc.cmpwi(21, 0))
    a.br("bne", "kc_out")
    a(ppc.li(0, 2), ppc.stw(0, off("po"), 30), ppc.li(0, 0), ppc.stw(0, off("losts"), 30), ppc.cmpwi(24, TWO))
    a.br("beq", "kc_po_teams")
    a(ppc.lfs(13, off("neg"), 30), ppc.lfs(12, off("farther"), 30), ppc.li(26, 0))   # f13 the farthest, f12 nearest
    a.label("kc_po_ext")
    a(ppc.addi(12, 30, off("in_po")), ppc.lbzx(0, 12, 26), ppc.cmpwi(0, 0))
    a.br("beq", "kc_po_ext_next")
    a(ppc.slwi(9, 26, 2), ppc.addi(9, 9, off("pdist")), ppc.add(9, 9, 30), ppc.lfs(0, 0, 9), ppc.fcmpu(0, 13))
    a.br("ble", "kc_po_e1")
    a(ppc.fmr(13, 0))
    a.label("kc_po_e1")
    a(ppc.fcmpu(0, 12))
    a.br("bge", "kc_po_ext_next")
    a(ppc.fmr(12, 0))
    a.label("kc_po_ext_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_po_ext")
    a(ppc.fcmpu(13, 12))
    a.br("beq", "kc_done")                    # the same distance for everyone: nobody
    a(ppc.li(26, 0))
    a.label("kc_po_mark")
    a(ppc.addi(12, 30, off("in_po")), ppc.lbzx(0, 12, 26), ppc.cmpwi(0, 0))
    a.br("beq", "kc_po_mark_next")
    a(ppc.slwi(9, 26, 2), ppc.addi(9, 9, off("pdist")), ppc.add(9, 9, 30), ppc.lfs(0, 0, 9), ppc.fcmpu(0, 13))
    a.br("bne", "kc_po_mark_next")
    a(ppc.li(0, 1), ppc.addi(12, 30, off("losts")), ppc.stbx(0, 12, 26))
    a.label("kc_po_mark_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_po_mark")
    a.br("b", "kc_apply")
    a.label("kc_po_teams")                    # 2v2: each team's nearest ball
    a(ppc.lfs(1, off("pdist"), 30), ppc.lfs(0, off("pdist") + 4, 30), ppc.fcmpu(0, 1))
    a.br("bge", "kpt_1")
    a(ppc.fmr(1, 0))
    a.label("kpt_1")
    a(ppc.lfs(2, off("pdist") + 8, 30), ppc.lfs(0, off("pdist") + 12, 30), ppc.fcmpu(0, 2))
    a.br("bge", "kpt_2")
    a(ppc.fmr(2, 0))
    a.label("kpt_2")
    a(ppc.fcmpu(1, 2), ppc.li(0, 1))
    a.br("beq", "kc_done")
    a.br("bgt", "kt_a")
    a.br("b", "kt_b")

    a.label("kc_apply")                       # the losers' lives
    a(ppc.li(26, 0))
    a.label("kc_ap")
    a(ppc.addi(12, 30, off("losts")), ppc.lbzx(0, 12, 26), ppc.lbzx(9, 30, 26), ppc.subf(9, 0, 9),
      ppc.stbx(9, 30, 26), ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_ap")
    a.label("kc_done")
    a(ppc.li(0, 1), ppc.stw(0, off("scored"), 30), ppc.li(28, 0), ppc.li(26, 0), ppc.cmpwi(24, TWO))
    a.br("beq", "kc_teams_left")
    a.label("kc_left")                        # how many are left
    a(ppc.lbzx(0, 30, 26), ppc.cmpwi(0, 0))
    a.br("beq", "kc_l_next")
    a(ppc.addi(28, 28, 1))
    a.label("kc_l_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_left")
    a.br("b", "kc_end")
    a.label("kc_teams_left")
    a(ppc.lbz(0, 0, 30), ppc.cmpwi(0, 0))
    a.br("beq", "kc_tl1")
    a(ppc.addi(28, 28, 1))
    a.label("kc_tl1")
    a(ppc.lbz(0, 2, 30), ppc.cmpwi(0, 0))
    a.br("beq", "kc_end")
    a(ppc.addi(28, 28, 1))
    a.label("kc_end")                         # the last one standing: the round ends after this hole
    a(ppc.li(0, 0), ppc.stw(0, off("tb"), 30), ppc.stw(0, off("tb_in"), 30), ppc.cmpwi(28, 1))
    a.br("bgt", "kc_more")
    hi, lo = ppc.hi_lo(HOLE)
    a(ppc.lis(12, hi), ppc.lbz(9, lo, 12), ppc.addi(9, 9, 1))      # (not r0: addi reads it as 0)
    hi, lo = ppc.hi_lo(HOLE_COUNT)
    a(ppc.lis(12, hi), ppc.stb(9, lo, 12))
    a.br("b", "kc_out")
    a.label("kc_more")                        # the round's last hole: level on the most lives -> a tiebreaker next
    hi, lo = ppc.hi_lo(HOLE)
    a(ppc.lis(12, hi), ppc.lbz(9, lo, 12), ppc.addi(9, 9, 1))
    hi, lo = ppc.hi_lo(HOLE_COUNT)
    a(ppc.lis(12, hi), ppc.lbz(0, lo, 12), ppc.cmpw(9, 0))
    a.br("bne", "kc_out")
    a(ppc.li(29, 0), ppc.li(26, 0))           # r29 the most lives
    a.label("kc_max")
    a(ppc.lbzx(0, 30, 26), ppc.cmpw(0, 29))
    a.br("ble", "kc_max_next")
    a(ppc.mr(29, 0))
    a.label("kc_max_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_max")
    a(ppc.li(28, 0), ppc.li(26, 0))           # r28 players at it, marked in tb_in
    a.label("kc_lead")
    a(ppc.lbzx(0, 30, 26), ppc.cmpw(0, 29))
    a.br("bne", "kc_lead_next")
    a(ppc.li(0, 1), ppc.addi(12, 30, off("tb_in")), ppc.stbx(0, 12, 26), ppc.addi(28, 28, 1))
    a.label("kc_lead_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_lead")
    a(ppc.li(0, 2), ppc.cmpwi(24, TWO))
    a.br("bne", "kc_lead_n")
    a(ppc.li(0, 4))                           # (2v2: both teams' players)
    a.label("kc_lead_n")
    a(ppc.cmpw(28, 0))
    a.br("blt", "kc_lead_none")
    a(ppc.li(0, 1), ppc.stw(0, off("tb"), 30))
    a.br("b", "kc_out")
    a.label("kc_lead_none")
    a(ppc.li(0, 0), ppc.stw(0, off("tb_in"), 30))
    a.label("kc_out")
    _leave(a, 0x50, 20)

    # ---- ko_po_move: (r30 our data, r27 the players) a playoff starts: everyone in in_po onto "spot", playing, no strokes
    a.label("ko_po_move")
    _enter(a, 0x40, 20)
    a(ppc.li(0, 1), ppc.stw(0, off("po"), 30), ppc.li(26, 0))
    a.label("pm_loop")
    a(ppc.addi(12, 30, off("in_po")), ppc.lbzx(0, 12, 26), ppc.cmpwi(0, 0))
    a.br("beq", "pm_next")
    _player(a, 25, 26)
    a(ppc.lwz(11, teams.PLAYER_REC, 25), ppc.addi(9, 11, REC_LIE - 4), ppc.addi(10, 30, off("spot") - 4),
      ppc.li(0, LIE_SIZE // 4), ppc.mtctr(0))
    a.label("pm_lie")
    a(ppc.lwzu(0, 4, 10), ppc.stwu(0, 4, 9))
    a.br("bdnz", "pm_lie")
    a(ppc.li(0, 0), ppc.stb(0, teams.REC_STATUS, 11), ppc.stb(0, teams.REC_STROKES, 11),
      ppc.stb(0, REC_PENALTY, 11))
    a.label("pm_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "pm_loop")
    _leave(a, 0x40, 20)

    # ---- ko_po_names: (r3 = where, r30, r27) "A, B, C": everyone in in_po, as kt_str
    a.label("ko_po_names")
    _enter(a, 0x40, 20)
    a(ppc.li(26, 0), ppc.li(20, 0))
    a.label("pn_loop")
    a(ppc.addi(12, 30, off("in_po")), ppc.lbzx(0, 12, 26), ppc.cmpwi(0, 0))
    a.br("beq", "pn_next")
    a(ppc.cmpwi(20, 0))
    a.br("beq", "pn_name")
    a(ppc.addi(4, 30, off("comma")))
    a.br("bl", "kt_str")
    a.label("pn_name")
    a(ppc.addi(20, 20, 1), ppc.mr(4, 26))
    a.br("bl", "kt_name")
    a.label("pn_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "pn_loop")
    _leave(a, 0x40, 20)

    # ---- ko_over (b from OVER, r3 = the golf state): a tiebreaker due: on to hole slot 0 (count 1, +0x3E "go on"),
    # a random hole there; then the game's test
    a.label("ko_over")
    _kind(a, team_mode, "over")
    a.br("beq", "ko_over_game")
    a.la(12, "lives")
    a(ppc.lwz(0, off("tb"), 12), ppc.cmpwi(0, 1))
    a.br("bne", "ko_over_game")
    a(ppc.stwu(1, -0x20, 1), ppc.mflr(0), ppc.stw(0, 0x24, 1), ppc.stw(31, 0x1C, 1), ppc.stw(3, 0x18, 1),
      ppc.mr(31, 12))
    a.bl(RAND)
    a(ppc.lfs(0, off("holes"), 31), ppc.fmuls(1, 1, 0), ppc.fctiwz(1, 1), ppc.stfd(1, off("tmp"), 31),
      ppc.lwz(9, off("tmp") + 4, 31), ppc.lwz(3, 0x18, 1), ppc.stb(9, ST_ORDER, 3), ppc.li(0, 1),
      ppc.stb(0, ST_COUNT, 3), ppc.stb(0, ST_GO_ON, 3), ppc.li(0, 2), ppc.stw(0, off("tb"), 31), ppc.li(0, -2),
      ppc.stw(0, off("hole_seen"), 31))
    a(ppc.lwz(31, 0x1C, 1), ppc.lwz(0, 0x24, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x20))
    a.label("ko_over_game")
    a(OVER[1])
    a.b(OVER[0] + 4)

    # ---- ko_points (b from teams.POINTS_GET, r3 = a player): its lives
    a.label("ko_points")
    _kind(a, team_mode, "points")
    a.br("bne", "kpt_go")
    a.b(labels["w_wolf_points"])
    a.label("kpt_go")
    a(ppc.lwz(3, teams.PLAYER_INDEX, 3))
    a.la(12, "lives")
    a(ppc.lbzx(3, 12, 3), ppc.BLR)

    # ---- ko_totals (bl from teams.TOTALS): the scorecards' Skins totals are the lives; nothing carried. Keeps r10-r12.
    a.label("ko_totals")
    a(ppc.stwu(1, -0x20, 1), ppc.stw(10, 0x08, 1), ppc.stw(11, 0x0C, 1), ppc.stw(12, 0x10, 1))
    _kind(a, team_mode, "totals")
    a.br("bne", "kto_go")
    a(ppc.lwz(10, 0x08, 1), ppc.lwz(11, 0x0C, 1), ppc.lwz(12, 0x10, 1), ppc.addi(1, 1, 0x20))
    a.b(labels["w_wolf_totals"])
    a.label("kto_go")
    hi, lo = ppc.hi_lo(PLAYERS_N)
    a(ppc.lis(12, hi), ppc.lbz(10, lo, 12))
    hi, lo = ppc.hi_lo(teams.SKINS_TOTALS)
    a(ppc.lis(11, hi), ppc.addi(11, 11, lo), ppc.li(0, 0), ppc.stw(0, teams.SKINS_POT - teams.SKINS_TOTALS, 11))
    a.la(12, "lives")
    a.label("kto_loop")
    a(ppc.cmpwi(10, 0))
    a.br("ble", "kto_done")
    a(ppc.lbz(0, 0, 12), ppc.stw(0, 0, 11), ppc.addi(12, 12, 1), ppc.addi(11, 11, 4), ppc.addi(10, 10, -1))
    a.br("b", "kto_loop")
    a.label("kto_done")
    a(ppc.lwz(10, 0x08, 1), ppc.lwz(11, 0x0C, 1), ppc.lwz(12, 0x10, 1), ppc.addi(1, 1, 0x20))
    a(teams.TOTALS[0][1], ppc.BLR)
    return a


_cache = None


def tail(labels):
    """(blob at base(), labels); labels = teams.caves()'s."""
    global _cache
    if _cache:
        return _cache
    a = make_tail(labels, base())
    blob = a.assemble()
    _cache = (blob, dict(a.labels))
    return _cache


def tail_blob(labels):
    """The golf overlay's tail (golfext.py): ours, after fbpose.py's when Pigskin is built."""
    blob = tail(labels)[0]
    if not teams.PIGSKIN:
        return blob
    import football
    players = football.overlay_tail()
    if len(players) > base() - golfext.BASE:
        raise SystemExit(f"golf tail: fbpose.py's {len(players)} bytes reach past Knockout's 0x{base():08X}")
    return players + bytes(base() - golfext.BASE - len(players)) + blob


def texts(labels):
    """[(message id, address)]: the notice (its text is written in a round)."""
    return [(MSG_NOTICE, tail(labels)[1]["text"])]
