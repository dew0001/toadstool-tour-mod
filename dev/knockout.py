"""v30 Knockout, a Team Play game (Andrew, 2026-11-02): "2v2 and 2,3,4 player free for all knockout, pretty simple
everyone goes and worse score loses a life (you get 3 lives) if everyone ties no one loses a life and move on to next
hole", then "once ur out of lives ur done playing, and the game ends with last person standing".

Knockout (choice 11, 2-4 humans) and Knockout 2v2 (choice 13, 4 humans: 1P and 2P against 3P and 4P, the game's own
first team layout) play as a Wolf round (teams.py: the game's Skins round, everyone on their own ball, team mode WOLF)
with the setup block's spare byte 0x8017607F (teams.KO_BYTE) saying which: so every teams.py path that is right for
Wolf is right here, and four of the Wolf's hooks get a stub of ours in front (in the golf overlay's tail, golfext.py):
  - ko_pick (the shooter pick, FUN_80402f1c): on a new hole, players out of lives are done before it starts (record
    +0x1BE = 2, so the pick passes them over), every player's result byte for the hole is "no skin", and a notice
    (rules on the first hole, then who lost a life, or a tied hole) opens in the game's tip box (0x80505358: the
    first shooter's aim waits for A, which closes it; FUN_80423bbc's state 4).
  - ko_score (scoring after a shot, FUN_8046a0b8): stroke play's scoring for the shot (sub-mode 0 around it, as the
    Wolf's), then ko_check: once every player with lives is done, the worst score loses a life (all tied at the worst
    lose one; everyone tied, nobody), or in 2v2 the team whose best ball is worse; when one player or team is left the
    round's hole count (state +0xAD0, 0x804E66B4) becomes this hole + 1, so the round ends after it (FUN_80403b0c's
    `hole + 1 == count`) and the results rank by lives.
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
TEXT_SIZE = 192
RULES = b"\x074Knockout! 3 lives each:\x01the worst score on a hole\x01loses a life.\x00"
RULES2_HEAD = b"\x074Knockout: \x00"
AMP = b" & \x00"
VS = b"\x01vs \x00"
RULES2_TAIL = b"!\x01The worse best ball\x01loses a life.\x00"
TIE = b"\x074Tied hole: no lives lost!\x00"
SIZE4 = b"\x074\x00"
OUT = b" is knocked out!\x00"
LOSES = b" loses a life: \x00"
LOSE2 = b" lose a life: \x00"
LEFT = b" left\x00"


def lbzu(rd, d, ra):
    return ppc._d(35, rd, d, ra)


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


def make_tail(labels, B):
    a = ppc.Asm(B)
    # ---- data (the tail loads fresh with every round, so these are a round's starting values)
    a.label("lives")
    a(*([(LIVES << 24 | LIVES << 16 | LIVES << 8 | LIVES)]))
    a.label("losts")                          # the last hole's losers (bytes)
    a(0)
    a.label("scores")                         # this hole's scores (0xFF: out of lives)
    a(0)
    a.label("scored")                         # byte: this hole is decided
    a(0)
    a.word("hole_seen", -1)
    a.label("text")
    a(*([0] * (TEXT_SIZE // 4)))
    strings = (("rules", RULES), ("rules2_head", RULES2_HEAD), ("amp", AMP), ("vs", VS), ("rules2_tail", RULES2_TAIL),
               ("tie", TIE), ("size4", SIZE4), ("out", OUT), ("loses", LOSES), ("lose2", LOSE2), ("left", LEFT))
    for name, text in strings:
        a.label(name)
        a(*struct.unpack(f">{-(-len(text) // 4)}I", text + bytes(-len(text) % 4)))
    names = b""
    offsets = []
    for name in teams.GOLFER_NAMES:
        offsets.append(len(names))
        names += name.encode() + b"\x00"
    a.label("name_offsets")
    blob = bytes(offsets)
    a(*struct.unpack(f">{-(-len(blob) // 4)}I", blob + bytes(-len(blob) % 4)))
    a.label("names")
    a(*struct.unpack(f">{-(-len(names) // 4)}I", names + bytes(-len(names) % 4)))
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

    # ---- ko_pick (b from teams.PICKER, r3 = the golf state)
    a.label("ko_pick")
    _kind(a, team_mode, "pick")
    a.br("bne", "kp_go")
    a.b(labels["w_wolf_pick"])
    a.label("kp_go")
    a(ppc.stwu(1, -0x40, 1), ppc.mflr(0), ppc.stw(0, 0x44, 1), ppc.stmw(20, 0x10, 1))
    a(ppc.mr(31, 3), ppc.mr(24, 12))
    a.la(30, "lives")                         # r30 = our data
    hi, lo = ppc.hi_lo(HOLE)
    a(ppc.lis(12, hi), ppc.lbz(29, lo, 12), ppc.lwz(28, off("hole_seen"), 30), ppc.cmpw(28, 29))
    a.br("beq", "kp_game")
    # a new hole: those out of lives are done; nobody's result is a skin
    a(ppc.stw(29, off("hole_seen"), 30), ppc.li(0, 0), ppc.stb(0, off("scored"), 30))
    hi, lo = ppc.hi_lo(PLAYERS_N)
    a(ppc.lis(12, hi), ppc.lbz(27, lo, 12), ppc.li(26, 0))
    a.label("kp_loop")
    _player(a, 25, 26)
    a(ppc.lwz(11, teams.PLAYER_CARD, 25), ppc.slwi(10, 29, 3), ppc.li(0, 1), ppc.stbx(0, 11, 10))
    a(ppc.lbzx(0, 30, 26), ppc.cmpwi(0, 0))
    a.br("bne", "kp_next")
    a(ppc.lwz(11, teams.PLAYER_REC, 25), ppc.li(0, 2), ppc.stb(0, teams.REC_STATUS, 11))
    a.label("kp_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kp_loop")
    # the notice: the rules on the round's first hole, then the last hole's losers
    a(ppc.addi(3, 30, off("text")), ppc.cmpwi(28, 0))
    a.br("bge", "kp_result")
    a(ppc.cmpwi(24, TWO))
    a.br("beq", "kp_rules2")
    a(ppc.addi(4, 30, off("rules")))
    a.br("bl", "kt_str")
    a.br("b", "kp_show")
    a.label("kp_rules2")                      # "Knockout: A & B / vs C & D! / The worse best ball loses a life."
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
    a(ppc.lwz(0, off("losts"), 30), ppc.cmpwi(0, 0))
    a.br("bne", "kp_losers")
    a(ppc.addi(4, 30, off("tie")))
    a.br("bl", "kt_str")
    a.br("b", "kp_show")
    a.label("kp_losers")
    a(ppc.addi(4, 30, off("size4")))
    a.br("bl", "kt_str")
    a(ppc.cmpwi(24, TWO))
    a.br("beq", "kp_team")
    a(ppc.li(21, 0), ppc.li(20, 0))           # r21 = the player, r20 = lines written
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
    a(ppc.li(3, MSG_NOTICE), ppc.li(4, TIP_X), ppc.li(5, TIP_Y), ppc.li(6, -1), ppc.li(7, TIP_STYLE))
    a.bl(BOX_OPEN)
    hi, lo = ppc.hi_lo(TIP_BOX)
    a(ppc.lis(12, hi), ppc.stw(3, lo, 12))
    a.label("kp_game")                        # the game's pick
    a(ppc.mr(3, 31), ppc.lmw(20, 0x10, 1), ppc.lwz(0, 0x44, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x40))
    a(teams.PICKER[1])
    a.b(teams.PICKER[0] + 4)

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
    # answer: 5 kept its lives, 6 lost one, 7 everyone tied.
    hi, lo = ppc.hi_lo(PLAYERS_N)
    a(ppc.lis(12, hi), ppc.lbz(0, lo, 12), ppc.cmpwi(0, 2))
    a.br("bne", "ks_ret")
    a.la(12, "lives")
    a(ppc.lbz(0, off("scored"), 12), ppc.cmpwi(0, 0))
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

    # ---- ko_check (r3 = the kind): once everyone with lives is done, who loses one
    a.label("ko_check")
    a(ppc.stwu(1, -0x40, 1), ppc.mflr(0), ppc.stw(0, 0x44, 1), ppc.stmw(20, 0x10, 1), ppc.mr(24, 3))
    a.la(30, "lives")
    a(ppc.lbz(0, off("scored"), 30), ppc.cmpwi(0, 0))
    a.br("bne", "kc_out")
    hi, lo = ppc.hi_lo(PLAYERS_N)
    a(ppc.lis(12, hi), ppc.lbz(27, lo, 12), ppc.li(26, 0))
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
    a(ppc.li(0, 0), ppc.stw(0, off("losts"), 30), ppc.cmpwi(24, TWO))
    a.br("beq", "kc_teams")
    a(ppc.li(29, -1), ppc.li(28, 999), ppc.li(26, 0))       # r29 the worst, r28 the best
    a.label("kc_ext")
    a(ppc.addi(12, 30, off("scores")), ppc.lbzx(0, 12, 26), ppc.cmpwi(0, 0xFF))
    a.br("beq", "kc_ext_next")
    a(ppc.cmpw(0, 29))
    a.br("ble", "kc_e1")
    a(ppc.mr(29, 0))
    a.label("kc_e1")
    a(ppc.cmpw(0, 28))
    a.br("bge", "kc_ext_next")
    a(ppc.mr(28, 0))
    a.label("kc_ext_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_ext")
    a(ppc.cmpw(29, 28))
    a.br("beq", "kc_done")                    # everyone tied: nobody
    a(ppc.li(26, 0))
    a.label("kc_mark")
    a(ppc.addi(12, 30, off("scores")), ppc.lbzx(0, 12, 26), ppc.cmpw(0, 29))
    a.br("bne", "kc_mark_next")
    a(ppc.addi(12, 30, off("losts")), ppc.li(0, 1), ppc.stbx(0, 12, 26))
    a.label("kc_mark_next")
    a(ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_mark")
    a.br("b", "kc_apply")
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
    a.br("beq", "kc_done")
    a.br("bgt", "kt_a")
    a(ppc.stb(0, off("losts") + 2, 30), ppc.stb(0, off("losts") + 3, 30))
    a.br("b", "kc_apply")
    a.label("kt_a")
    a(ppc.stb(0, off("losts"), 30), ppc.stb(0, off("losts") + 1, 30))
    a.label("kc_apply")                       # the losers' lives
    a(ppc.li(26, 0))
    a.label("kc_ap")
    a(ppc.addi(12, 30, off("losts")), ppc.lbzx(0, 12, 26), ppc.lbzx(9, 30, 26), ppc.subf(9, 0, 9),
      ppc.stbx(9, 30, 26), ppc.addi(26, 26, 1), ppc.cmpw(26, 27))
    a.br("blt", "kc_ap")
    a.label("kc_done")
    a(ppc.li(0, 1), ppc.stb(0, off("scored"), 30), ppc.li(28, 0), ppc.li(26, 0), ppc.cmpwi(24, TWO))
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
    a(ppc.cmpwi(28, 1))
    a.br("bgt", "kc_out")
    hi, lo = ppc.hi_lo(HOLE)
    a(ppc.lis(12, hi), ppc.lbz(9, lo, 12), ppc.addi(9, 9, 1))      # (not r0: addi reads it as 0)
    hi, lo = ppc.hi_lo(HOLE_COUNT)
    a(ppc.lis(12, hi), ppc.stb(9, lo, 12))
    a.label("kc_out")
    a(ppc.lmw(20, 0x10, 1), ppc.lwz(0, 0x44, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x40), ppc.BLR)

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
