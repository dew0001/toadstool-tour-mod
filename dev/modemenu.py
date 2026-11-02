"""v28: Team Play's game list as a dropdown (Andrew, 2026-11-02: "should make the game modes a dropdown menu like we
did the maps"), as coursemenu.py made the course select's course row one.

The Play Mode screen (menu overlay B/U/C: FUN_8041cc9c runs it every frame, FUN_8041b6c4 draws it) opens a sub-list
of icons under a carousel entry; Team Play's (Doubles') had grown to 14 (teams.py: the game's five alternate-shot
games, then ours), a row as wide as the screen. Now (RE-NOTES "Play Mode list (v28 dropdown)"):
  - Team Play's row (a sub-list of 5 or more: the others have 3 at most) draws only the picked game's icon and name, in
    the middle (ROW_X: every other icon is placed off the screen), with the arrows beside it (ARROWS: spaced as for one
    icon). Left/Right still step through the games.
  - A opens a list window (a text box like Toad's, over the row) of the games by name, VISIBLE at a time, the picked
    one yellow, scrolling; Up/Down move the list's own cursor (so the icon and Toad's help line follow it, as with
    Left/Right); A plays the picked game (the game's own A: its sound and countdown to the next screen); B closes the
    window and puts the cursor back.
The games' names: the game's alternate-shot five (they only had pictures) by their rules, then teams.NAMES.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppc  # noqa: E402
import teams  # noqa: E402

STATE = 0x80450000          # menu: the Play Mode screen's words are just under it
SUB_OPEN = 0x8044C434       # 0 the carousel, 1 a sub-list, 2 a sub-list's sub-list
CURSOR = 0x8044C42C         # the sub-list's cursor
COUNT = 0x8044C440          # its length (teams.ROW_COUNT)
DECIDED = 0x8044C438        # A pressed: counts up to 0x10, then the game is set up
INPUT = 0x8041D5C0          # FUN_8041cc9c: andi. r0,r23,0x200 (r23 = the pads' new presses, r20 their repeating
INPUT_WORD = 0x72E00200     # directions), where B, A, Left and Right are handled while nothing is decided
INPUT_NEXT = 0x8041D5C4
DONE = 0x8041DB40           # past the buttons: Toad's help line shows the cursor's game (0x22 + its help value)
DECIDE_TAIL = 0x8041D6B8    # bl SOUND (r3, r4), then DONE: what A does after counting DECIDED to 1
ROW_X = teams.ROW_X         # FUN_8041b6c4's icon loop: addi r9,r9,356 (r9 = 72 i - 36 count, r30 = i; r11 =
                            # 0x80450000 and cr0 are read after it)
ARROWS = (0x8041C10C, 0x1D6B0024)   # its mulli r11,r11,0x24 (r11 = the count): the arrows count x 36 + 24 apart
SOUND = 0x800035EC          # FUN_800035ec(kind, 0xFF): 0 back, 1 cursor, 2 decide
BOX_NEW = 0x80024E04        # FUN_80024e04(x, y, w, h, 0, style) -> a text box
BOX_TEXT = 0x80024CFC       # FUN_80024cfc(box, message, x, y, mode): mode 1 = all at once
BOX_FREE = 0x80024C98
OFFSCREEN = 2000            # x for the icons not shown

DROPDOWN_MIN = 5            # sub-lists this long are Team Play's
PAD_A, PAD_B, PAD_DOWN, PAD_UP = 0x100, 0x200, 0x4, 0x8
VISIBLE = 6
BOX = {"x": 320, "y": 266, "w": 360, "h": 135, "style": 0xD}   # frame about y 188..353: under the carousel's name,
TEXT_X, TEXT_Y = 0, 0x11                                       # over Toad's box
MSG_LIST = 0x7FBE
LIST_STYLE = b"\t3\t2\x073"
HILITE, PLAIN = b"\x083", b"\x080"
ALT_NAMES = ("Alt Shot Stroke", "Alt Shot Match", "Alt Shot Slots x4", "Alt Shot Slots x3", "Alt Shot Skins")
NAMES = ALT_NAMES + teams.NAMES
NAME_MAX = max(len(n) for n in NAMES)
assert len(ALT_NAMES) == teams.SUB_COUNT_DOUBLES

CAVES = {   # dead main.dol functions (mod/ghidra_out/golf/dead_unused.txt): address, size, first word
    "names": (0x800961DC, 252, 0x9421FFE0),   # the games' names, offsets
    "data": (0x8002063C, 216, 0x9421FFC0),    # the window's state and text
    "input": (0x8003FFDC, 212, 0x7C0802A6),   # the buttons; the row's x and the arrows
    "keys": (0x800369AC, 212, 0x7C0802A6),    # the buttons while the window is up
    "show": (0x8008C9C4, 208, 0x9421FFE0),    # opening and closing the window
    "fill": (0x800867A4, 208, 0x9421FFF0),    # its text: the scroll
    "rows": (0x8006F978, 208, 0x9421FFD8),    # its text: the names
}


def _bytes(a, blob):
    blob += bytes((-len(blob)) % 4)
    a(*struct.unpack(f">{len(blob) // 4}I", blob))


def _frame(a, size=16):
    a(ppc.stwu(1, -size, 1), ppc.mflr(0), ppc.stw(0, size + 4, 1))


def _unframe(a, size=16):
    a(ppc.lwz(0, size + 4, 1), ppc.mtlr(0), ppc.addi(1, 1, size))


def _li32(a, rd, value):
    hi, lo = ppc.hi_lo(value)
    a(ppc.lis(rd, hi), ppc.addi(rd, rd, lo))


def _off(addr):
    return addr - STATE


def _names_cave(ext):
    a = ppc.Asm(CAVES["names"][0])
    a.label("mm_offsets")       # a byte each: the name's offset from mm_names
    offsets, blob = [], b""
    for name in NAMES:
        offsets.append(len(blob))
        blob += name.encode() + b"\0"
    assert len(blob) < 256
    _bytes(a, bytes(offsets))
    a.label("mm_names")
    _bytes(a, blob)
    return a


def _data_cave(ext):
    a = ppc.Asm(CAVES["data"][0])
    a.word("mm_open")           # 1 while the window is up
    a.word("mm_box")            # its text box
    a.word("mm_top")            # the list row at its top
    a.word("mm_saved")          # the cursor when it opened (B puts it back)
    a.label("mm_text")          # MSG_LIST: the style codes, then the names (mm_fill)
    _bytes(a, LIST_STYLE + bytes(VISIBLE * (len(HILITE) + NAME_MAX + len(PLAIN) + 1) + 1))
    a.labels["mm_rows"] = a.labels["mm_text"] + len(LIST_STYLE)
    return a


def _input_cave(ext):
    a = ppc.Asm(CAVES["input"][0])
    # at INPUT (b): Team Play's list: A opens the window, the window's own buttons while it's up; else the game's
    a.label("mm_input")
    a(ppc.lis(12, STATE >> 16), ppc.lwz(0, _off(SUB_OPEN), 12), ppc.cmpwi(0, 1))
    a.br("bne", "mm_game")
    a(ppc.lwz(0, _off(COUNT), 12), ppc.cmpwi(0, DROPDOWN_MIN))
    a.br("blt", "mm_game")
    _frame(a)
    _li32(a, 12, ext["mm_open"])
    a(ppc.lwz(0, 0, 12), ppc.cmpwi(0, 0))
    a.br("beq", "mm_closed")
    a.b(ext["mm_keys"])
    a.label("mm_closed")
    a(ppc.andi_(0, 23, PAD_A))
    a.br("beq", "mm_game_frame")
    a.bl(ext["mm_show"])
    a(ppc.li(3, 1), ppc.li(4, 0xFF))
    a.bl(SOUND)
    a.label("mm_done")
    _unframe(a)
    a.b(DONE)
    a.label("mm_game_frame")
    _unframe(a)
    a.label("mm_game")
    a(INPUT_WORD)
    a.b(INPUT_NEXT)

    # at ROW_X (bl, for r9 = 72 i - 36 count + 356): Team Play's list shows only the cursor's icon, in the middle
    # (none while the window is up); others as the game lays them out. Keeps r11 and cr0.
    a.label("mm_row_x")
    a(ppc.lis(12, STATE >> 16), ppc.lwz(0, _off(COUNT), 12), 0x2C800000 | DROPDOWN_MIN)    # cmpwi cr1,r0,5
    a(0x41840000 | 4 * 12)                                              # blt cr1, mm_row_game
    a(ppc.lwz(0, _off(CURSOR), 12), 0x7C9E0000)                         # cmpw cr1,r30,r0
    a(0x40860000 | 4 * 7)                                               # bne cr1, mm_row_off
    hi, lo = ppc.hi_lo(ext["mm_open"])
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), 0x2C800000)                  # cmpwi cr1,r0,0
    a(0x40860000 | 4 * 3)                                               # bne cr1, mm_row_off
    a(ppc.li(9, 320), ppc.BLR)
    a.label("mm_row_off")
    a(ppc.li(9, OFFSCREEN), ppc.BLR)
    a.label("mm_row_game")
    a(ROW_X[1], ppc.BLR)
    lab = a.labels                                      # (the cr1 branches above, counted by hand: checked here)
    assert lab["mm_row_game"] - (lab["mm_row_x"] + 12) == 4 * 12 and lab["mm_row_off"] - (lab["mm_row_x"] + 24) == 4 * 7

    return a


def _keys_cave(ext):
    a = ppc.Asm(CAVES["keys"][0])
    # (from mm_input, its frame made) the window's buttons: A plays the game, B goes back, Up/Down move
    a.label("mm_keys")
    a(ppc.andi_(0, 23, PAD_A))
    a.br("beq", "mm_keys_b")
    a.bl(ext["mm_hide"])
    _unframe(a)
    a(ppc.li(0, 1), ppc.lis(12, STATE >> 16), ppc.stw(0, _off(DECIDED), 12), ppc.li(3, 2), ppc.li(4, 0xFF))
    a.b(DECIDE_TAIL)            # (the game's A: its sound, then on toward the game's set-up)
    a.label("mm_keys_b")
    a(ppc.andi_(0, 23, PAD_B))
    a.br("beq", "mm_keys_dirs")
    a.bl(ext["mm_hide"])
    _li32(a, 12, ext["mm_saved"])
    a(ppc.lwz(0, 0, 12), ppc.lis(12, STATE >> 16), ppc.stw(0, _off(CURSOR), 12), ppc.li(3, 0), ppc.li(4, 0xFF))
    a.bl(SOUND)
    a.b(ext["mm_done"])
    a.label("mm_keys_dirs")
    a(ppc.li(4, -1), ppc.andi_(0, 20, PAD_UP))
    a.br("bne", "mm_keys_move")
    a(ppc.li(4, 1), ppc.andi_(0, 20, PAD_DOWN))
    a.br("beq", "mm_keys_done")
    a.label("mm_keys_move")     # the cursor on, wrapping (the icon and Toad's help follow it)
    a(ppc.lis(12, STATE >> 16), ppc.lwz(3, _off(CURSOR), 12), ppc.lwz(5, _off(COUNT), 12), ppc.add(6, 3, 4),
      ppc.add(6, 6, 5), ppc.divw(7, 6, 5), ppc.mullw(7, 7, 5), ppc.subf(6, 7, 6), ppc.stw(6, _off(CURSOR), 12))
    a.bl(ext["mm_fill"])
    a(ppc.li(3, 1), ppc.li(4, 0xFF))
    a.bl(SOUND)
    a.label("mm_keys_done")
    a.b(ext["mm_done"])
    return a


def _show_cave(ext):
    a = ppc.Asm(CAVES["show"][0])
    # mm_show: the window opened, scrolled so the cursor is near its middle
    a.label("mm_show")
    _frame(a)
    a(ppc.li(3, BOX["x"]), ppc.li(4, BOX["y"]), ppc.li(5, BOX["w"]), ppc.li(6, BOX["h"]), ppc.li(7, 0),
      ppc.li(8, BOX["style"]))
    a.bl(BOX_NEW)
    a(ppc.cmpwi(3, 0))
    a.br("beq", "mm_show_done")
    _li32(a, 12, ext["mm_open"])
    a(ppc.stw(3, ext["mm_box"] - ext["mm_open"], 12), ppc.li(0, 1), ppc.stw(0, 0, 12))
    a(ppc.lis(11, STATE >> 16), ppc.lwz(4, _off(CURSOR), 11), ppc.stw(4, ext["mm_saved"] - ext["mm_open"], 12),
      ppc.addi(4, 4, -(VISIBLE // 2)), ppc.lwz(5, _off(COUNT), 11), ppc.addi(5, 5, -VISIBLE), ppc.cmpw(4, 5))
    a.br("ble", "mm_show_low")
    a(ppc.mr(4, 5))
    a.label("mm_show_low")
    a(ppc.cmpwi(4, 0))
    a.br("bge", "mm_show_top")
    a(ppc.li(4, 0))
    a.label("mm_show_top")
    a(ppc.stw(4, ext["mm_top"] - ext["mm_open"], 12))
    a.bl(ext["mm_fill"])
    a.label("mm_show_done")
    _unframe(a)
    a(ppc.BLR)

    # mm_hide: the window closed
    a.label("mm_hide")
    _frame(a)
    _li32(a, 12, ext["mm_open"])
    a(ppc.li(0, 0), ppc.stw(0, 0, 12), ppc.lwz(3, ext["mm_box"] - ext["mm_open"], 12),
      ppc.stw(0, ext["mm_box"] - ext["mm_open"], 12), ppc.cmpwi(3, 0))
    a.br("beq", "mm_hide_done")
    a.bl(BOX_FREE)
    a.label("mm_hide_done")
    _unframe(a)
    a(ppc.BLR)
    return a


def _fill_cave(ext):
    a = ppc.Asm(CAVES["fill"][0])
    # mm_fill: the window's names (rows mm_top.. of the list, the cursor's yellow), scrolled to keep it in view
    a.label("mm_fill")
    _frame(a, 48)
    a(ppc.stmw(27, 28, 1))
    _li32(a, 29, ext["mm_open"])                 # r29 = the state
    a(ppc.lis(9, STATE >> 16), ppc.lwz(30, _off(CURSOR), 9), ppc.lwz(31, _off(COUNT), 9),
      ppc.lwz(28, ext["mm_top"] - ext["mm_open"], 29), ppc.cmpw(30, 28))
    a.br("bge", "mm_fill_above")
    a(ppc.mr(28, 30))
    a.label("mm_fill_above")
    a(ppc.addi(0, 28, VISIBLE - 1), ppc.cmpw(30, 0))
    a.br("ble", "mm_fill_below")
    a(ppc.addi(28, 30, -(VISIBLE - 1)))
    a.label("mm_fill_below")
    a(ppc.stw(28, ext["mm_top"] - ext["mm_open"], 29), ppc.addi(0, 28, VISIBLE), ppc.cmpw(0, 31))
    a.br("bge", "mm_fill_end")
    a(ppc.mr(31, 0))                             # r31 = the row after the last shown
    a.label("mm_fill_end")
    _li32(a, 27, ext["mm_rows"])
    a.b(ext["mm_fill_rows"])

    # at ARROWS (bl, for r11 = r11 x 0x24; r0 is free): Team Play's arrows as for one icon, off the screen while the
    # window is up (they showed through it)
    a.label("mm_arrows")
    hi, lo = ppc.hi_lo(ext["mm_open"])
    a(0x2C8B0000 | DROPDOWN_MIN, 0x41840018)            # cmpwi cr1,r11,5; blt cr1, +6 words (the game's)
    a(ppc.lis(11, hi), ppc.lwz(0, lo, 11), ppc.li(11, 1), 0x2C800000, 0x41860008, ppc.li(11, 40))   # cmpwi cr1,r0,0;
    a(ARROWS[1], ppc.BLR)                                                                       # beq cr1, +2 words
    return a


def _rows_cave(ext):
    a = ppc.Asm(CAVES["rows"][0])
    # mm_fill's rest (its frame and registers: r27 = where the text goes, r28 = the first row, r29 = the state, r30
    # = the cursor, r31 = the row after the last): each name, the cursor's yellow, then the window's text
    a.label("mm_fill_rows")
    a.label("mm_fill_row")
    a(ppc.lwz(0, ext["mm_top"] - ext["mm_open"], 29), ppc.cmpw(28, 0))
    a.br("beq", "mm_fill_first")
    a(ppc.li(0, 1), ppc.stb(0, 0, 27), ppc.addi(27, 27, 1))   # a line break between names
    a.label("mm_fill_first")
    a(ppc.li(3, PLAIN[1]), ppc.cmpw(28, 30))
    a.br("bne", "mm_fill_colour")
    a(ppc.li(3, HILITE[1]))
    a.label("mm_fill_colour")
    a(ppc.li(0, HILITE[0]), ppc.stb(0, 0, 27), ppc.stb(3, 1, 27), ppc.addi(27, 27, 2))
    _li32(a, 4, ext["mm_offsets"])
    a(ppc.lbzx(5, 4, 28))
    _li32(a, 4, ext["mm_names"])
    a(ppc.add(4, 4, 5))
    a.label("mm_fill_char")
    a(ppc.lbz(0, 0, 4), ppc.cmpwi(0, 0))
    a.br("beq", "mm_fill_next")
    a(ppc.stb(0, 0, 27), ppc.addi(27, 27, 1), ppc.addi(4, 4, 1))
    a.br("b", "mm_fill_char")
    a.label("mm_fill_next")
    a(ppc.addi(28, 28, 1), ppc.cmpw(28, 31))
    a.br("blt", "mm_fill_row")
    a(ppc.li(0, 0), ppc.stb(0, 0, 27))
    a(ppc.lwz(3, ext["mm_box"] - ext["mm_open"], 29), ppc.li(4, MSG_LIST), ppc.li(5, TEXT_X), ppc.li(6, TEXT_Y),
      ppc.li(7, 1))
    a.bl(BOX_TEXT)
    a(ppc.lmw(27, 28, 1))
    _unframe(a, 48)
    a(ppc.BLR)
    return a


MAKERS = {"names": _names_cave, "data": _data_cave, "input": _input_cave, "keys": _keys_cave, "show": _show_cave,
          "fill": _fill_cave, "rows": _rows_cave}


def caves():
    """[(address, first word, code)], labels"""
    names = ("mm_open", "mm_box", "mm_top", "mm_saved", "mm_rows", "mm_offsets", "mm_names", "mm_keys", "mm_done",
             "mm_show", "mm_hide", "mm_fill", "mm_fill_rows")
    labels, ext = {}, {}
    for _ in range(2):          # the first pass finds the labels the caves use of each other
        ext.update({n: labels.get(n, CAVES["data"][0]) for n in names})
        out, labels, sizes = [], {}, {}
        for name, make in MAKERS.items():
            a = make(ext)
            code = a.assemble()
            if len(code) > CAVES[name][1]:
                raise SystemExit(f"mode menu cave {name}: {len(code)} bytes; only {CAVES[name][1]} fit")
            out.append((CAVES[name][0], CAVES[name][2], code))
            labels.update(a.labels)
            sizes[name] = len(code)
    labels["_sizes"] = sizes
    return out, labels


def texts(labels):
    """[(message id, string address)] for build_mod.py's message hook."""
    return [(MSG_LIST, labels["mm_text"])]


def overlay_patches(rel, labels):
    """[(address, new word, expected word)] for the menu overlay (B/U/C); ROW_X replaces teams.py's hook there."""
    if rel != "B/U/C":
        return []
    return [(INPUT, ppc.b(INPUT, labels["mm_input"]), INPUT_WORD),
            (ROW_X[0], ppc.bl(ROW_X[0], labels["mm_row_x"]), ROW_X[1]),
            (ARROWS[0], ppc.bl(ARROWS[0], labels["mm_arrows"]), ARROWS[1])]


if __name__ == "__main__":
    out, labels = caves()
    print(labels["_sizes"], {n: CAVES[n][1] for n in CAVES})
