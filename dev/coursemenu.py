"""v26: the course select's course row as a dropdown list (Andrew, 2026-10-30: "lets remake the map selection menu
into a dropdown menu to pick the map so when we add more maps later its just a dropdown menu. the hole number and
front and back tees selection can stay the same").

The course select (menu overlay B/U/C: FUN_80413910 builds its list, FUN_8041418c runs it every frame, FUN_80412640
draws its three rows: courses, holes, tees) showed every course the mode offers as an icon in one row; with 11 the
icons barely fit (v22 narrowed their spacing). Now (see dev/RE-NOTES.md "Course select"):
  - The course row draws only the picked course's icon, in the middle (ICON_SKIP: the pass that draws the other
    courses' icons draws none; ROW_SPACING: spacing 0, so the picked icon sits at x 320 wherever it is in the list).
  - A on the course row (more than one course, no prompt up) opens a list window over the rows (a text box like the
    one under the board, between the preview and it): the mode's courses by name, VISIBLE at a time, the
    highlighted one yellow, scrolling to keep it in view. Up/Down move the highlight with the game's repeat delay,
    and the highlight is the course select's own cursor, so the preview movie, the holes and tees choices and the
    course's data follow it as they did with Left/Right. A picks (and moves the cursor to the holes row, where A
    asks "ready to play?" as before), B puts the course, holes and tees back as they were. Meanwhile Toad's box
    under the board shows the highlighted course's name and the buttons, and the three rows and the "X Handicap"
    label aren't drawn (the window covers the rows; X does nothing while it's up).
  - Left/Right on the closed course row still step through the courses (the arrows by the preview say so).
The list itself is the game's (plus course8.py's courses in the modes that offer them), so every mode lists what it
always did, and more courses only make the list longer.
"""
import struct

import course8
import ppc

BASE = 0x8044AFCC           # menu: the course select's state (r27 in FUN_8041418c)
COURSE, TEES, HOLES, ROW = 0x10, 0x14, 0x18, 0x1C   # list index of the course, the tees and holes choices, the row
TOAD_BOX = 0x8044B020       # the text box under the board: the row's name or description (BASE + 0x54)
PREVIEW = 0x8044C250        # 2: the preview movie changes to the course's
THROTTLE = 0x8044C280       # frames until a held direction repeats (the game's 14, then 9)
SCREEN_BUSY = 0x8022299C    # -1 when the screen takes buttons
MODE = 0x80176080           # main.dol setup block: the game mode (4 Tournament)
STAR_CUP = 0x80176092       # byte: the Star tournaments (their names are 0xB8 + index, the others 0xB2 + index)
SOUND = 0x800035EC          # FUN_800035ec(kind, 0xFF): menu sounds, 0 back, 1 cursor, 2 decide
BOX_NEW = 0x80024E04        # FUN_80024e04(x, y, w, h, 0, style) -> a text box (60 of them)
BOX_TEXT = 0x80024CFC       # FUN_80024cfc(box, message, x, y, mode): mode bit 0 = all at once, else typed
BOX_FREE = 0x80024C98
MSG_LOOKUP = 0x80022CD0     # message id -> string (build_mod.py's hook answers ours)
NAME_BASE, CUP_BASE, STAR_CUP_BASE = 0xA8, 0xB2, 0xB8   # course names: base + the course's menu index

INPUT = 0x80414764          # FUN_8041418c: lis r9,0x8022, the buttons when no prompt is up (r24 = repeating
INPUT_WORD = 0x3D208022     # directions, r30 = new presses, r25 = 0 "changed", r27 = BASE; r8 = 0x80450000 is live)
INPUT_NEXT = 0x80414768
INPUT_MOVED = 0x80414C08    # the cursor sound and repeat delay, then INPUT_DONE
INPUT_DONE = 0x80414C38     # after the input: r25 != 0 shows the row's text in Toad's box again
LIS_R8 = 0x3D008045         # lis r8,0x8045 (what r8 holds at INPUT)
ROW_SPACING = course8.ROW_SPACING   # icon row draw: lfs f11,0x7504(r9) (56.0; r9 = 0x80440000)
ROW_SPACING_WORD = course8.ROW_SPACING_WORD
ROW_SPACING_ZERO = 0xC16974F0       # lfs f11,0x74F0(r9): 0.0
ICON_SKIP = 0x80412D2C      # pass 0 of the icon row: bne 0x80412D64 draws every course but the picked one, small
ICON_SKIP_WORD = 0x40A20038
NOP = 0x60000000
ROWS = 0x80412CE8           # the row loop: cmpwi r29,0 (r29 = the row being drawn: courses, holes, tees)
ROWS_WORD = 0x2C1D0000
ROWS_NEXT = 0x80412CEC
ROWS_SKIP = 0x80413484      # the row loop's next row
RESET = 0x804140D0          # FUN_80413910 (the course select's set-up): bl FUN_80414170
RESET_CALL = 0x80414170
HANDICAP = 0x8044BD74       # the mode lets X open the handicaps (FUN_804121b0 draws the "X Handicap" label then)

PAD_A, PAD_B, PAD_DOWN, PAD_UP = 0x100, 0x200, 0x4, 0x8
VISIBLE = 6                 # names in the window at a time
NAME_MAX = 28               # longest name copied ("Cheep Cheep Star Tournament" is 27)
BOX = {"x": 320, "y": 278, "w": 360, "h": 135, "style": 0xD}   # the window (style 0xD: Toad's box): its frame
TEXT_X, TEXT_Y = 0, 0x11    # spans about y - h/2 - 10 .. y + h/2 + 20 (201..366, between the preview and Toad's box);
                            # a name's middle is about 3 below the window's top + TEXT_Y, then every 25
MSG_LIST, MSG_HINT = 0x7FC8, 0x7FC9
LIST_STYLE = b"\t3\t2\x073"  # the names: as the game's course names, size 1.0
HINT_STYLE = b"\t3\t2\x074"  # Toad's box: the highlighted course's name (as the game shows it), then the buttons
HINT_TAIL = b"\x01\x073\x12 Choose   \x0a Pick   \x0b Back\0"   # glyphs: 0x12 the +Control Pad, 0x0A A, 0x0B B
HILITE, PLAIN = b"\x083", b"\x080"   # colours: yellow, white

CAVES = {   # dead main.dol functions (find_dead_code.py, mod/ghidra_out/golf/dead_unused.txt): address, size, first word
    "list": (0x8003D35C, 280, 0x7C0802A6),    # the state and the names' text
    "hint": (0x80037A90, 280, 0x7C0802A6),    # Toad's text, a name's message, copying a name
    "input": (0x8004893C, 276, 0x7C0802A6),   # the buttons: opening the window; the draw and set-up hooks
    "keys": (0x8006C168, 272, 0x9421FFE8),    # the buttons while it's up
    "move": (0x80040AAC, 276, 0x7C0802A6),    # Up/Down
    "show": (0x8006BA90, 272, 0x9421FFE0),    # opening and closing the window
    "fill": (0x80094660, 272, 0x9421FFE0),    # writing the window's text
    "toad": (0x800459B8, 272, 0x7C0802A6),    # Toad's text while it's up
}


def _bytes(a, blob):
    blob += bytes((-len(blob)) % 4)
    a(*struct.unpack(f">{len(blob) // 4}I", blob))


def _frame(a, size=16):
    a(ppc.stwu(1, -size, 1), ppc.mflr(0), ppc.stw(0, size + 4, 1))


def _unframe(a, size=16):
    a(ppc.lwz(0, size + 4, 1), ppc.mtlr(0), ppc.addi(1, 1, size))


def _lw(a, rd, addr, rt=None):
    """rd = the word at addr (rt the address register, rd if not given)."""
    hi, lo = ppc.hi_lo(addr)
    rt = rd if rt is None else rt
    a(ppc.lis(rt, hi), ppc.lwz(rd, lo, rt))


def _sw(a, rs, addr, rt):
    hi, lo = ppc.hi_lo(addr)
    a(ppc.lis(rt, hi), ppc.stw(rs, lo, rt))


def _li32(a, rd, value):
    hi, lo = ppc.hi_lo(value)
    a(ppc.lis(rd, hi), ppc.addi(rd, rd, lo))


def _list_cave(ext):
    a = ppc.Asm(CAVES["list"][0])
    a.word("dd_open")           # 1 while the window is up
    a.word("dd_box")            # its text box
    a.word("dd_top")            # the list row at the window's top
    a.word("dd_saved", 0)       # the course, tees and holes when it opened (B puts them back)
    a(0, 0)
    a.word("dd_handicap")       # HANDICAP when it opened (0 while it's up: no "X Handicap" label)
    a.label("dd_list_text")     # MSG_LIST: the style codes, then the names (dd_fill)
    _bytes(a, LIST_STYLE + bytes(VISIBLE * (len(HILITE) + NAME_MAX + len(PLAIN) + 1) + 1))
    a.labels["dd_list_rows"] = a.labels["dd_list_text"] + len(LIST_STYLE)
    return a


def _hint_cave(ext):
    a = ppc.Asm(CAVES["hint"][0])
    a.label("dd_hint_text")     # MSG_HINT: the name's style, the name, HINT_TAIL
    _bytes(a, HINT_STYLE + bytes(NAME_MAX + len(HINT_TAIL) + 2))
    a.labels["dd_hint_name"] = a.labels["dd_hint_text"] + len(HINT_STYLE)
    a.label("dd_tail")
    _bytes(a, HINT_TAIL)

    # dd_name: r3 = list row -> r3 = its course's name (a string)
    a.label("dd_name")
    _frame(a)
    _li32(a, 9, ext["list"])
    a(ppc.mulli(3, 3, course8.LIST_ENTRY), ppc.lwzx(4, 9, 3))          # the course's menu index
    hi, lo = ppc.hi_lo(MODE)
    a(ppc.lis(9, hi), ppc.lwz(0, lo, 9), ppc.cmpwi(0, 4))
    a.br("bne", "dd_name_course")
    a(ppc.lbz(0, ppc.hi_lo(STAR_CUP)[1], 9), ppc.li(3, CUP_BASE), ppc.cmpwi(0, 0))   # a tournament's name
    a.br("beq", "dd_name_cup")
    a(ppc.li(3, STAR_CUP_BASE))
    a.label("dd_name_cup")
    a(ppc.add(3, 3, 4))
    a.br("b", "dd_name_lookup")
    a.label("dd_name_course")   # course8.py's stub: the game's name, or ours for our courses
    a(ppc.li(9, NAME_BASE))
    a.bl(ext["name_menu"])
    a(ppc.mr(3, 4))
    a.label("dd_name_lookup")
    a.bl(MSG_LOOKUP)
    _unframe(a)
    a(ppc.BLR)

    # dd_copy: the printable characters of the string at r4 to r3 (at most NAME_MAX) -> r3 = after them
    a.label("dd_copy")
    a(ppc.li(5, NAME_MAX))
    a.label("dd_copy_next")
    a(ppc.lbz(0, 0, 4), ppc.cmpwi(0, 0), ppc.BEQLR, ppc.addi(4, 4, 1), ppc.cmpwi(0, 0x20))
    a.br("bge", "dd_copy_char")
    a(ppc.cmpwi(0, 6))          # codes 6-9 carry a byte (size, colour, style)
    a.br("blt", "dd_copy_next")
    a(ppc.cmpwi(0, 9))
    a.br("bgt", "dd_copy_next")
    a(ppc.addi(4, 4, 1))
    a.br("b", "dd_copy_next")
    a.label("dd_copy_char")
    a(ppc.stb(0, 0, 3), ppc.addi(3, 3, 1), ppc.addi(5, 5, -1), ppc.cmpwi(5, 0))
    a.br("bgt", "dd_copy_next")
    a(ppc.BLR)
    return a


def _input_cave(ext):
    a = ppc.Asm(CAVES["input"][0])
    # at INPUT (b): the window's buttons while it's up; A on the course row opens it; else the game's
    a.label("dd_input")
    _frame(a)
    _li32(a, 12, ext["dd_open"])
    a(ppc.lwz(0, 0, 12), ppc.cmpwi(0, 0))
    a.br("beq", "dd_in_closed")
    a.b(ext["dd_in_open"])
    a.label("dd_in_closed")
    a(ppc.andi_(0, 30, PAD_A))
    a.br("beq", "dd_in_game")
    a(ppc.lwz(0, ROW, 27), ppc.cmpwi(0, 0))
    a.br("bne", "dd_in_game")
    _lw(a, 0, course8.LIST_COUNT, 9)
    a(ppc.cmpwi(0, 1))
    a.br("ble", "dd_in_game")
    _lw(a, 0, SCREEN_BUSY, 9)
    a(ppc.cmpwi(0, -1))
    a.br("bne", "dd_in_game")
    for k, off in enumerate((COURSE, TEES, HOLES)):        # (r12 = the state)
        a(ppc.lwz(0, off, 27), ppc.stw(0, ext["dd_saved"] - ext["dd_open"] + 4 * k, 12))
    a.bl(ext["dd_show"])
    a(ppc.li(3, 2), ppc.li(4, 0xFF))
    a.bl(SOUND)
    a.br("b", "dd_in_done")
    a.label("dd_in_game")
    _unframe(a)
    a(LIS_R8, INPUT_WORD)
    a.b(INPUT_NEXT)

    a.label("dd_in_moved")
    _unframe(a)
    a.b(INPUT_MOVED)
    a.label("dd_in_done")
    _unframe(a)
    a.b(INPUT_DONE)

    # at ROWS (b): the rows aren't drawn while the window is up
    a.label("dd_rows")
    _lw(a, 0, ext["dd_open"], 12)
    a(ppc.cmpwi(0, 0))
    a.br("beq", "dd_rows_game")
    a.b(ROWS_SKIP)
    a.label("dd_rows_game")
    a(ROWS_WORD)
    a.b(ROWS_NEXT)

    # at RESET (bl, the course select's set-up): the window is closed
    a.label("dd_reset")
    _li32(a, 12, ext["dd_open"])
    a(ppc.li(0, 0), ppc.stw(0, 0, 12), ppc.stw(0, ext["dd_box"] - ext["dd_open"], 12))
    a.b(RESET_CALL)
    return a


def _keys_cave(ext):
    a = ppc.Asm(CAVES["keys"][0])
    # (from dd_input, its frame made) the window's buttons: A picks, B goes back, Up/Down move
    a.label("dd_in_open")
    _lw(a, 0, SCREEN_BUSY, 9)
    a(ppc.cmpwi(0, -1))
    a.br("bne", "dd_in_dirs")
    a(ppc.andi_(0, 30, PAD_A))
    a.br("beq", "dd_in_b")
    a(ppc.li(3, 2), ppc.li(4, 0xFF))
    a.bl(SOUND)
    a.bl(ext["dd_hide"])
    a(ppc.li(0, 1), ppc.stw(0, ROW, 27), ppc.li(25, 1))   # on to the holes row (Toad shows its text again)
    a.b(ext["dd_in_done"])
    a.label("dd_in_b")
    a(ppc.andi_(0, 30, PAD_B))
    a.br("beq", "dd_in_dirs")
    a(ppc.li(3, 0), ppc.li(4, 0xFF))
    a.bl(SOUND)
    a.bl(ext["dd_hide"])
    _li32(a, 12, ext["dd_saved"])
    a(ppc.lwz(3, 0, 12), ppc.lwz(0, COURSE, 27), ppc.cmpw(0, 3))
    a.br("beq", "dd_in_same")
    a(ppc.stw(3, COURSE, 27), ppc.li(0, 2))
    _sw(a, 0, PREVIEW, 9)
    a.label("dd_in_same")
    a(ppc.lwz(0, 4, 12), ppc.stw(0, TEES, 27), ppc.lwz(0, 8, 12), ppc.stw(0, HOLES, 27), ppc.li(25, 1))
    a.b(ext["dd_in_done"])
    a.label("dd_in_dirs")       # Up/Down, with the game's repeat delay
    hi, lo = ppc.hi_lo(THROTTLE)
    a(ppc.lis(9, hi), ppc.lwz(3, lo, 9), ppc.cmpwi(3, 0))
    a.br("ble", "dd_in_wait")
    a(ppc.addi(3, 3, -1), ppc.stw(3, lo, 9))
    a.label("dd_in_wait")
    a(ppc.cmpwi(3, 1))
    a.br("bgt", "dd_in_wait_done")
    a(ppc.li(4, -1), ppc.andi_(0, 24, PAD_UP))
    a.br("bne", "dd_in_move")
    a(ppc.li(4, 1), ppc.andi_(0, 24, PAD_DOWN))
    a.br("beq", "dd_in_wait_done")
    a.label("dd_in_move")
    a.bl(ext["dd_move"])
    a.b(ext["dd_in_moved"])
    a.label("dd_in_wait_done")
    a.b(ext["dd_in_done"])
    return a


def _move_cave(ext):
    a = ppc.Asm(CAVES["move"][0])
    # dd_move (r4 = -1 up, 1 down, r27 = BASE): the next course, as Left/Right on the course row do
    a.label("dd_move")
    _frame(a)
    a(ppc.lwz(3, COURSE, 27))
    _lw(a, 5, course8.LIST_COUNT, 9)
    a(ppc.add(6, 3, 4), ppc.add(6, 6, 5), ppc.divw(7, 6, 5), ppc.mullw(7, 7, 5), ppc.subf(6, 7, 6))   # wraps
    a(ppc.stw(6, COURSE, 27), ppc.li(0, 2))
    _sw(a, 0, PREVIEW, 9)
    _li32(a, 9, ext["list"])
    a(ppc.mulli(10, 6, course8.LIST_ENTRY), ppc.add(10, 10, 9), ppc.mulli(11, 3, course8.LIST_ENTRY),
      ppc.add(11, 11, 9))       # r10 = the new course's list entry, r11 the old one's
    # the tees and holes choices stay if the new course has them (the game's 0x80414AE8..0x80414B2C)
    for off, first, count in ((TEES, 0x20, 0x28), (HOLES, 0x04, 0x1C)):
        a(ppc.lwz(7, off, 27), ppc.lwz(0, count, 10), ppc.cmpw(7, 0))
        a.br("bge", f"dd_move_reset_{off}")
        a(ppc.slwi(8, 7, 2), ppc.add(9, 8, 11), ppc.lwz(0, first, 9), ppc.add(9, 8, 10), ppc.lwz(9, first, 9),
          ppc.cmpw(0, 9))
        a.br("beq", f"dd_move_keep_{off}")
        a.label(f"dd_move_reset_{off}")
        a(ppc.li(0, 0), ppc.stw(0, off, 27))
        a.label(f"dd_move_keep_{off}")
    a.bl(ext["dd_fill"])
    a(ppc.lwz(3, COURSE, 27))
    a.bl(ext["dd_toad"])
    _unframe(a)
    a(ppc.BLR)

    return a


def _show_cave(ext):
    a = ppc.Asm(CAVES["show"][0])
    # dd_show: open the window (r27 = BASE), scrolled so the course is near its middle
    a.label("dd_show")
    _frame(a)
    a(ppc.li(3, BOX["x"]), ppc.li(4, BOX["y"]), ppc.li(5, BOX["w"]), ppc.li(6, BOX["h"]), ppc.li(7, 0),
      ppc.li(8, BOX["style"]))
    a.bl(BOX_NEW)
    a(ppc.cmpwi(3, 0))
    a.br("beq", "dd_show_done")
    _li32(a, 12, ext["dd_open"])
    a(ppc.stw(3, ext["dd_box"] - ext["dd_open"], 12), ppc.li(0, 1), ppc.stw(0, 0, 12))
    a(ppc.lwz(4, COURSE, 27), ppc.addi(4, 4, -(VISIBLE // 2)))
    _lw(a, 5, course8.LIST_COUNT, 9)
    a(ppc.addi(5, 5, -VISIBLE), ppc.cmpw(4, 5))
    a.br("ble", "dd_show_low")
    a(ppc.mr(4, 5))
    a.label("dd_show_low")
    a(ppc.cmpwi(4, 0))
    a.br("bge", "dd_show_top")
    a(ppc.li(4, 0))
    a.label("dd_show_top")
    a(ppc.stw(4, ext["dd_top"] - ext["dd_open"], 12))
    hi, lo = ppc.hi_lo(HANDICAP)
    a(ppc.lis(9, hi), ppc.lwz(0, lo, 9), ppc.stw(0, ext["dd_handicap"] - ext["dd_open"], 12), ppc.li(0, 0),
      ppc.stw(0, lo, 9))
    a.bl(ext["dd_fill"])
    a(ppc.lwz(3, COURSE, 27))
    a.bl(ext["dd_toad"])
    a.label("dd_show_done")
    _unframe(a)
    a(ppc.BLR)

    # dd_hide: close the window
    a.label("dd_hide")
    _frame(a)
    _li32(a, 12, ext["dd_open"])
    hi, lo = ppc.hi_lo(HANDICAP)
    a(ppc.lwz(0, ext["dd_handicap"] - ext["dd_open"], 12), ppc.lis(9, hi), ppc.stw(0, lo, 9))
    a(ppc.li(0, 0), ppc.stw(0, 0, 12), ppc.lwz(3, ext["dd_box"] - ext["dd_open"], 12),
      ppc.stw(0, ext["dd_box"] - ext["dd_open"], 12), ppc.cmpwi(3, 0))
    a.br("beq", "dd_hide_done")
    a.bl(BOX_FREE)
    a.label("dd_hide_done")
    _unframe(a)
    a(ppc.BLR)
    return a


def _fill_cave(ext):
    a = ppc.Asm(CAVES["fill"][0])
    # dd_fill: the window's names (rows dd_top.. of the list, the course yellow)
    a.label("dd_fill")
    _frame(a, 48)
    a(ppc.stmw(26, 20, 1))
    _li32(a, 29, ext["dd_open"])                 # r29 = the state
    _li32(a, 31, BASE)
    a(ppc.lwz(30, COURSE, 31), ppc.lwz(28, ext["dd_top"] - ext["dd_open"], 29), ppc.cmpw(30, 28))
    a.br("bge", "dd_fill_above")
    a(ppc.mr(28, 30))
    a.label("dd_fill_above")
    a(ppc.addi(0, 28, VISIBLE - 1), ppc.cmpw(30, 0))
    a.br("ble", "dd_fill_below")
    a(ppc.addi(28, 30, -(VISIBLE - 1)))
    a.label("dd_fill_below")
    a(ppc.stw(28, ext["dd_top"] - ext["dd_open"], 29), ppc.addi(26, 28, VISIBLE))
    _lw(a, 0, course8.LIST_COUNT, 9)
    a(ppc.cmpw(26, 0))
    a.br("ble", "dd_fill_end")
    a(ppc.mr(26, 0))                             # r26 = the row after the last shown
    a.label("dd_fill_end")
    _li32(a, 27, ext["dd_list_rows"])
    a.label("dd_fill_row")
    a(ppc.lwz(0, ext["dd_top"] - ext["dd_open"], 29), ppc.cmpw(28, 0))
    a.br("beq", "dd_fill_first")
    a(ppc.li(0, 1), ppc.stb(0, 0, 27), ppc.addi(27, 27, 1))   # a line break between names
    a.label("dd_fill_first")
    for name, code in (("dd_fill_on", HILITE), ("dd_fill_off", PLAIN)):
        a(ppc.cmpw(28, 30))
        a.br("bne", name)
        a(ppc.li(0, code[0]), ppc.stb(0, 0, 27), ppc.li(0, code[1]), ppc.stb(0, 1, 27), ppc.addi(27, 27, 2))
        a.label(name)
        if code is HILITE:
            a(ppc.mr(3, 28))
            a.bl(ext["dd_name"])
            a(ppc.mr(4, 3), ppc.mr(3, 27))
            a.bl(ext["dd_copy"])
            a(ppc.mr(27, 3))
    a(ppc.addi(28, 28, 1), ppc.cmpw(28, 26))
    a.br("blt", "dd_fill_row")
    a(ppc.li(0, 0), ppc.stb(0, 0, 27))
    a(ppc.lwz(3, ext["dd_box"] - ext["dd_open"], 29), ppc.li(4, MSG_LIST), ppc.li(5, TEXT_X), ppc.li(6, TEXT_Y),
      ppc.li(7, 1))
    a.bl(BOX_TEXT)
    a(ppc.lmw(26, 20, 1))
    _unframe(a, 48)
    a(ppc.BLR)

    return a


def _toad_cave(ext):
    a = ppc.Asm(CAVES["toad"][0])
    # dd_toad (r3 = list row): Toad's box under the board shows its course's name and the buttons
    a.label("dd_toad")
    _frame(a)
    a.bl(ext["dd_name"])
    a(ppc.mr(4, 3))
    _li32(a, 3, ext["dd_hint_name"])
    a.bl(ext["dd_copy"])
    _li32(a, 4, ext["dd_tail"])
    a.label("dd_fill_tail")
    a(ppc.lbz(0, 0, 4), ppc.stb(0, 0, 3), ppc.addi(3, 3, 1), ppc.addi(4, 4, 1), ppc.cmpwi(0, 0))
    a.br("bne", "dd_fill_tail")
    _lw(a, 3, TOAD_BOX)
    a(ppc.li(4, MSG_HINT), ppc.li(5, 0), ppc.li(6, 0x10), ppc.li(7, 1))
    a.bl(BOX_TEXT)
    _unframe(a)
    a(ppc.BLR)
    return a


MAKERS = {"list": _list_cave, "hint": _hint_cave, "input": _input_cave, "keys": _keys_cave, "move": _move_cave,
          "show": _show_cave, "fill": _fill_cave, "toad": _toad_cave}


def caves(course_labels):
    """course_labels: course8.caves()'s labels (the list, the name stub) -> [(address, first word, code)], labels"""
    ext = {"list": course_labels["list"], "name_menu": course_labels["name_menu"]}
    names = ("dd_open", "dd_box", "dd_top", "dd_saved", "dd_list_rows", "dd_hint_name", "dd_tail", "dd_name",
             "dd_copy", "dd_show", "dd_hide", "dd_move", "dd_fill", "dd_in_open", "dd_in_done", "dd_in_moved",
             "dd_toad", "dd_handicap")
    labels = {}
    for _ in range(2):          # the first pass finds the labels the caves use of each other
        ext.update({n: labels.get(n, CAVES["list"][0]) for n in names})
        out, labels, sizes = [], {}, {}
        for name, make in MAKERS.items():
            a = make(ext)
            code = a.assemble()
            if len(code) > CAVES[name][1]:
                raise SystemExit(f"course menu cave {name}: {len(code)} bytes; only {CAVES[name][1]} fit")
            out.append((CAVES[name][0], CAVES[name][2], code))
            labels.update(a.labels)
            sizes[name] = len(code)
    labels["_menu_sizes"] = sizes
    return out, labels


def texts(labels):
    """[(message id, string address)] for build_mod.py's message hook."""
    return [(MSG_LIST, labels["dd_list_text"]), (MSG_HINT, labels["dd_hint_text"])]


def overlay_patches(rel, labels):
    """[(address, new word, expected word)] for the menu overlay (B/U/C)."""
    if rel != "B/U/C":
        return []
    return [(INPUT, ppc.b(INPUT, labels["dd_input"]), INPUT_WORD),
            (ICON_SKIP, NOP, ICON_SKIP_WORD),
            (ROW_SPACING, ROW_SPACING_ZERO, ROW_SPACING_WORD),
            (ROWS, ppc.b(ROWS, labels["dd_rows"]), ROWS_WORD),
            (RESET, ppc.bl(RESET, labels["dd_reset"]), ppc.bl(RESET, RESET_CALL))]
