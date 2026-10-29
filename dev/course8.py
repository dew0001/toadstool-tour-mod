"""v11: an 8th course, Pebble Beach's layout (course code 8, menu index 7); v21: a 9th, Pasadena Municipal Golf
Course in Pasadena, Texas (course code 9, menu index 8); v22: Battleground (Deer Park) and Timber Creek (Friendswood),
menu indexes 9 and 10, played as course code 9 with a variant (VARIANT, a spare setup byte: 0 Pasadena, 1
Battleground, 2 Timber Creek).

The game ships course codes 8 and 9 unused (cut 3-hole sets no menu reaches), and every per-course table already has
entries for them that fall back to Lakitu Valley, so the new courses take those codes. Code 10 is the practice holes
and past it the tables end (the CPU table at 0x804D7324 has 10 entries), so the third and fourth courses don't get
codes of their own: the course select's commit (COMMIT, `stb r3,0xA79(r29)`: the code is the menu index + 1) turns
codes 10 and 11 into code 9 and the variant, and everything that has to tell the Texas courses apart reads the
variant. Our courses are numbered k = 0..3 (Pebble Beach, Pasadena, Battleground, Timber Creek); their holes get new
hole IDs, FIRST_ID + 18 x k + hole (1101-1172; nothing special-cases them). Which tables and hooks, with addresses
(golf = C/L/V, menu = B/U/C, both loaded at 0x80400000; see dev/RE-NOTES.md "Courses"):

  - Hole info (par, yards, hole order): the game's 141-entry table can't grow (golf 0x804CCD60, menu copy
    0x80444E60), so our entries live in caves (18 x 12 bytes a course, found through INFO_PTRS) and the lookups
    check them first: by ID (golf FUN_80406f90, menu FUN_8040094c) and by course + hole (golf FUN_80407048, menu
    FUN_80400a04; code 9 adds the variant).
  - Hole files (model, collision, flyover camera): the resolver FUN_80443e14 searches the file table by ID right
    after asking FUN_80407048 for it (0x80443E68); for our IDs a stub fills the practice row's unused last slot (row
    8, col 17, 0x804DE338) from our tables (6 bytes a hole, FILES_PTRS) and points the round at it.
  - Course select (menu FUN_80413910): its list holds 7 entries of 0x2C at 0x8044BC40 with live screen state right
    after it, so the list moves to cave 11 (7 + ours; every lis 0x8045 / addi -0x43C0 pair that addresses it is
    repointed) and a hook where every mode's list ends (0x804140B0) appends ours in Stroke Play, Match Play (not
    Character Match), Skins and Practice. Those modes write no per-course records except the hole-in-one mask. With
    more than 9 icons the row's spacing (56, loaded at ROW_SPACING) narrows to ROW_SPACING_11 so 11 fit the board.
  - Preview movie: past index 6 the game plays the word at 0x8041445C's file (A/T/C, Lakitu Valley's); a stub plays
    Blooper Bay's (A/T/F) for Pebble Beach and Lakitu Valley's for the Texas courses.
  - Music (main.dol FUN_80011a94, table per situation x course 1-7): Pebble Beach plays Blooper Bay's songs, the
    Texas courses each a course's of their own ("music").
  - Saves: the hole-in-one mask store (golf 0x804682F4) is skipped on our courses, whose index would wrap onto
    Lakitu Valley's mask.
  - Name: six places add the course name's message base (0xA8 + index on the course select, 0xA7 + code in a round);
    each goes through a stub that swaps the course's own message in ("msg", build_mod.py's message hook answers).
    In a round code 9 shows ROUND_NAME_MSG, a buffer the round start fills with the variant's name.
  - Round start (golf FUN_804014c0's first instruction, ROUND_START): for code 9 it writes the variant's emblem into
    the emblem table and its name into the ROUND_NAME_MSG buffer (the golf overlay's tables load fresh each round).
  - Sky: the hole loader's sky choice sends Pebble Beach to Blooper Bay's sea sky; the Texas courses get Blooper
    Bay's sky dome alone, with no backdrop (as Congo Canopy has none), so their own scenery makes the horizon
    (Lakitu Valley's backdrop, the default, has big mountains; Blooper Bay's is a sea in front of the far land).
  - Icon: the course select shows texture <index> of B/W/R: 7 (the star medallion) is redrawn as Pebble Beach's,
    and textures 8-10 are appended for the Texas courses.
  - Emblem and HUD card: files of our own per course (E/S/B and E/S/A, F/S/B and F/S/A, G/S/.., H/S/..): entry 8 of
    the emblem table and the card switch is Pebble Beach's, entry 9 the variant's (the card case reads it).
  - Auto-aim (v12): another hole's fairway, fringe and green are no target (AIM_SCORE).
  - Distance (v17): every golfer's drive is the course code's bonus yards longer (the clubs scale with it), as the
    real holes are long for the game's golfers (REACH_HOOK). v18: 50 yards on Pebble Beach, none for Tony (golfer
    17, 350 already: the longest driver without it), and a Star version drives as its normal self (Andrew: "star
    should just be ignored on pebble beach and only the +50 buff is used": STAR_ROW_HOOK reads the normal row of
    the drive table). v21: code 9's drives are 40 yards longer, again not Tony's (Andrew: "make it +20 except for
    Tony", then "Make the buff +40 yards"), and its Star versions drive as their normal selves too ("star power
    should also be ignored on Pasadena"); v22's Texas courses share code 9's rules.
The holes themselves (models, collision, flyover cameras) come from dev/course (holegen.py, coursejson.py).
"""
import struct

import ppc

CODE = 8                    # our first course code (menu index 7); the rest are code 9 (+ VARIANT)
TEXAS = 9
FIRST_ID = 1101             # hole IDs FIRST_ID + HOLES x k + hole
HOLES = 18
COURSES = (                 # k order: name, message id (course select), music column (a course code), preview movie
    {"name": "Pebble Beach", "msg": 0x7FF0, "music": 4, "preview": 0x3E6,                       # (file ID / 2),
     "card": "E/S/A", "emblem": "E/S/B", "icon": 7},                                             # card, emblem and
    {"name": "Pasadena Municipal", "msg": 0x7FDF, "music": 1, "preview": 0x3E0,                  # icon texture
     "card": "F/S/A", "emblem": "F/S/B", "icon": 8},
    {"name": "Battleground", "msg": 0x7FDE, "music": 6, "preview": 0x3E0,
     "card": "G/S/A", "emblem": "G/S/B", "icon": 9},
    {"name": "Timber Creek", "msg": 0x7FDD, "music": 3, "preview": 0x3E0,
     "card": "H/S/A", "emblem": "H/S/B", "icon": 10},
)
BY_CODE = {                 # per course code: sky (Blooper Bay's sky and sea backdrop, or its sky dome alone), the
    8: {"sky": "blooper", "bonus": 50.0, "star_normal": True},   # yards on every drive but Tony's, and whether Star
    9: {"sky": "dome", "bonus": 40.0, "star_normal": True},      # versions drive as their normal selves
}
ROUND_NAME_MSG = 0x7FEF     # code 9's name in a round: a buffer (ROUND_START copies the variant's name in)
VARIANT = 0x8017607E        # main.dol setup block: spare byte (no reads anywhere), which code-9 course
SETUP_CODE = 0x80176079     # main.dol setup block: the round's course code


def code_of(k):
    return CODE if k == 0 else TEXAS


def variant_of(k):
    return 0 if k == 0 else k - 1


CAVE11 = 0x80069F4C         # dead (find_dead_code.py): the course list (7 + ours x 0x2C), the menu's info lookup
CAVE11_SIZE = 560
CAVE11_FIRST = 0x9421FFA8
CAVE12 = 0x8006A834         # dead: hole info of courses 0 and 1, the pointers to each course's
CAVE12_SIZE = 464
CAVE12_FIRST = 0x9421FFE8
CAVE13 = 0x80084B2C         # dead: list append, music, sky, reach, Star row, hole-in-one guard
CAVE13_SIZE = 464
CAVE13_FIRST = 0x9421FFD0
CAVE15 = 0x80073ACC         # dead (v21): the hole files of courses 0 and 1, the golf ID lookup
CAVE15_SIZE = 344
CAVE15_FIRST = 0x9421FFD0
CAVE16 = 0x8007C758         # dead (v21): cards, auto-aim score, the golf name stubs
CAVE16_SIZE = 304
CAVE16_FIRST = 0x9421FFD0
CAVE18 = 0x8003F8C0         # dead (v22): hole info of course 2, the golf info lookup
CAVE18_SIZE = 300
CAVE18_FIRST = 0x7C0802A6
CAVE19 = 0x8008C898         # dead (v22): hole info of course 3
CAVE19_SIZE = 300
CAVE19_FIRST = 0x9421FFE0
CAVE20 = 0x800463C4         # dead (v22): the hole files of courses 2 and 3, the menu's ID lookup
CAVE20_SIZE = 312
CAVE20_FIRST = 0x7C0802A6
CAVE21 = 0x8006F468         # dead (v22): the course names, the round start
CAVE21_SIZE = 344
CAVE21_FIRST = 0x9421FF98
CAVE22 = 0x8007CCC0         # dead (v22): the menu's stubs: commit, row spacing, preview, names
CAVE22_SIZE = 308
CAVE22_FIRST = 0x9421FFF0
CAVE23 = 0x8003176C         # dead (v22): the hole file resolver
CAVE23_SIZE = 316
CAVE23_FIRST = 0x7C0802A6

INFO_BY_ID = {"golf": 0x80406F90, "menu": 0x8040094C}   # first instruction li r8,0 in both
ID_BY_HOLE = {"golf": 0x80407048, "menu": 0x80400A04}   # first instruction mr r8,r3 in both
LI_R8_0, MR_R8_R3 = 0x39000000, 0x7C681B78
RESOLVE_HOOK = 0x80443E68   # golf: li r8,0 right after bl FUN_80407048 (r3 = hole ID)
RESOLVE_DONE = 0x80443EC4   # where the search ends with r29 = row, r30 = col
FILE_SLOT = 0x804DE338      # hole file table row 8 col 17 (never used: practice holes repeat in cols 9-17)
FILE_ROW, FILE_COL = 8, 17
ACE_HOOK = 0x804682F4       # golf: or r0,r0,r10 / stw r0,-0x5978(r11): the hole-in-one mask store
ACE_WORDS = (0x7C005378, 0x900BA688)
ACE_DONE = 0x804682FC
COURSE_NOW = 0x804E68F4     # golf: course code byte of the round
# v12: the auto-aim (FUN_804abd70, every new shot) picks its landing spot from triangles whose surface scores 80+
# (method [11]: fairway, fringe, green), sorted by FUN_804a7874. Our hole files hold their neighbours' fairways
# too, so it aimed at other holes; those triangles carry collision.ATTR_OTHER_HOLE, and the stub scores them 79.
AIM_SCORE = 0x804A7A20      # golf: cmpwi r3,0x4f after the score call (r27 = triangle record + 0xC)
AIM_SCORE_WORD = 0x2C03004F
REACH_HOOK = 0x8044C434     # golf FUN_8044c344 (a club's reach): bl FUN_80009c58(f1 = drive, r3 = club, r4 = set)
REACH = 0x80009C58
DRIVE_BONUS = BY_CODE[8]["bonus"]   # Pebble Beach's (v17 35)
NO_BONUS_GOLFER = 17        # but Tony's (v18)
PLAYER_OPTIONS = 0x804E667C # golf: option bits per player (bit 0 the Star version: FUN_8044c278 picks its drive row)
STAR_ROW_HOOK = 0x8044C40C  # golf FUN_8044c344: lwzx r9,r29,r9, the drive from 0x804D2980 + row x 28 (odd rows Star)
STAR_ROW_WORD = 0x7D3D482E  # (r0 is live past it: the stub uses r11 and r12)
AIM_SCORE_MIN = 0x50
OTHER_HOLE_ATTR = 0x0100      # course/collision.py ATTR_OTHER_HOLE
MUSIC = 0x80011A94          # main.dol: addi r0,r4,-1 (r4 = course code)
MUSIC_FIRST = 0x3804FFFF
NAME_SITES = {"menu": 0x80414D14,   # course select: add r4,r4,r9 (r4 = course index + 0xA8, the name message)
              "golf": 0x8048C77C}   # hole intro banner / pause menu: add r4,r4,r9 (course code + 0xA7)
NAME_ADD = 0x7C844A14       # add r4,r4,r9
NAME_SITES_R0 = [0x804B5814, 0x804B5BC8, 0x804B5E04]   # golf: add r0,r0,r9 in the hole intro's course banner
NAME_ADD_R0 = 0x7C004A14
NAME_SITE_R9 = 0x804B57B0   # golf: add r9,r0,r9 (the banner's "is it showing already" check)
NAME_ADD_R9 = 0x7D204A14
NAME_OLD = 0xA8 + CODE - 1  # 0xAF "Shot Practice": what index 7 / course 8 asked for (0xB0 for index 8 / course 9)
SKY_TEST = 0x804463AC       # golf: cmpwi r0,4 in the hole loader's sky choice (r0 = the hole's course byte)
SKY_TEST_WORD = 0x2C000004
SKY_BLOOPER = 0x804463B4    # Blooper Bay's sky and backdrop (B/I/K, B/I/L)
SKY_DEFAULT = 0x804463C0    # Lakitu Valley's (A/X/I, A/X/J), where course 8 went
SKY_LOAD = 0x80006084       # FUN_80006084(file ID): a model; the loader keeps the dome at r30 +0x5F1C, the backdrop
SKY_DOME, SKY_BACKDROP = 0x5F1C, 0x5F20   # at +0x5F20 (0 = none: drawn only when set)
SKY_DONE = 0x804463E0       # after the backdrop's store
BLOOPER_DOME = 0x6FD        # B/I/K
ROUND_START = 0x804014C0    # golf FUN_804014c0 (the round's setup, copies the setup block): stwu r1,-24(r1)
ROUND_START_WORD = 0x9421FFE8
COMMIT = 0x80415388         # menu FUN_80415040: stb r3,0xA79(r29), the course code (r3 = index + 1; CTR is live)
COMMIT_WORD = 0x987D0A79
ROW_SPACING = 0x80412DB4    # menu icon row: lfs f11,0x7504(r9) (r9 = 0x80440000; 56.0), r9 is free past it
ROW_SPACING_WORD = 0xC1697504
ROW_SPACING_11 = 45.0       # icons 48 wide: 11 fit where 9 did at 56

LIST_OLD = 0x8044BC40       # menu: the course list, 7 x 0x2C
LIST_ENTRY = 0x2C
LIST_COUNT = 0x80445D28     # menu: entries in the list
LIST_SITES = [              # (lis, addi) pairs addressing LIST_OLD; the lis at 0x80413F98 and 0x80412658 serve two each
    (0x8041239C, 0x804123A0), (0x80412658, 0x80412660), (0x80413520, 0x80413528), (0x80413548, 0x8041354C),
    (0x8041356C, 0x80413574), (0x804139E4, 0x804139E8), (0x80413A78, 0x80413A7C), (0x80413B20, 0x80413B24),
    (0x80413BD0, 0x80413BD4), (0x80413C0C, 0x80413C14), (0x80413C94, 0x80413C98), (0x80413D34, 0x80413D38),
    (0x80413DD4, 0x80413DD8), (0x80413E10, 0x80413E18), (0x80413EC8, 0x80413ECC), (0x80413F20, 0x80413F2C),
    (0x80413F40, 0x80413F4C), (0x80413F68, 0x80413F70), (0x80413F98, 0x80413FA0), (0x80413F98, 0x80413FB4),
    (0x8041403C, 0x80414040), (0x80414078, 0x80414080), (0x80414424, 0x80414428), (0x80414A14, 0x80414A1C),
    (0x80414C74, 0x80414C7C), (0x80415080, 0x80415084), (0x80412658, 0x80412DB8)]   # r20 again, in the icon draw
LIST_END = 0x804140B0       # menu: lis r11,0x8045, where every mode's list is done
LIST_END_WORD = 0x3D608045
LIST_FILL = 0x8041358C      # menu: FUN_8041358c(entry, course index, tees, hole sets)
MODE = 0x80176080           # main.dol setup block: game mode (0 Stroke, 1 Match, 2 Skins, 3 Practice, ...)
VERSUS = 0x8017603D         # 4 = Character Match
PREVIEW_DEFAULT = 0x8041445C   # menu: addi r28,r9,0x3E0 (A/T/C, Lakitu's preview) for indexes past 6 (r0 = index,
PREVIEW_WORD = 0x3B8903E0      # r9 = 0); v11 made it 0x3E6 (A/T/F, Blooper Bay's), v21 a stub (by index)


def cmplwi(ra, imm):
    return 0x28000000 | ra << 16 | (imm & 0xFFFF)


def lhz(rd, d, ra):
    return ppc.lhz(rd, d, ra)


def _data(a, blob):
    blob += bytes((-len(blob)) % 4)
    a(*struct.unpack(f">{len(blob) // 4}I", blob))


def _done(a, name, size):
    code = a.assemble()
    if len(code) > size:
        raise SystemExit(f"{name} code is {len(code)} bytes; only {size} fit")
    return code, a.labels


def info_table(k, holes):
    """[(yards, back yards, par)] in hole order -> 18 x 12 bytes like the game's hole info (its course byte is the
    round's code: 9 for the Texas courses)."""
    return b"".join(struct.pack(">IhhBBBB", FIRST_ID + HOLES * k + n, yards, back, par, code_of(k), n + 1, 0)
                    for n, (yards, back, par) in enumerate(holes))


def file_table(files):
    """files: [(model id, collision id, flyover id)] game file IDs (odd = packed) -> 6 bytes per hole."""
    return b"".join(struct.pack(">3H", *f) for f in files)


def load_variant(a, reg):
    """reg = VARIANT (0..2), 0 if it's anything else."""
    hi, lo = ppc.hi_lo(VARIANT)
    if reg == 0:
        raise ValueError("lbz rD,d(r0) reads address d")
    skip = f"_var{len(a.words)}"
    a(ppc.lis(reg, hi), ppc.lbz(reg, lo, reg), cmplwi(reg, 2))
    a.br("ble", skip)
    a(ppc.li(reg, 0))
    a.label(skip)


def id_lookup(a, name, count, game):
    """FUN_80407048 / FUN_80400a04 (r3 = course, r4 = hole0) -> hole ID: ours for code 8 and code 9 + variant."""
    a.label(name)
    a(ppc.addi(0, 3, -CODE), cmplwi(0, TEXAS - CODE))
    a.br("bgt", name + "_game")
    a(cmplwi(4, HOLES - 1))
    a.br("bgt", name + "_game")
    a(ppc.cmpwi(0, TEXAS - CODE))
    a.br("bne", name + "_k")
    load_variant(a, 12)
    a(ppc.add(0, 0, 12))
    a.label(name + "_k")
    a(cmplwi(0, count - 1))
    a.br("bgt", name + "_game")
    a(ppc.mulli(0, 0, HOLES), ppc.add(3, 4, 0), ppc.addi(3, 3, FIRST_ID), ppc.BLR)
    a.label(name + "_game")
    a(MR_R8_R3)
    a.b(game + 4)


def per_course(a, entry, ptrs_at):
    """r0 = hole ID - FIRST_ID (checked) -> r3 = the course's table at ptrs_at + (ID within the course) x entry
    (clobbers r0, r11, r12)."""
    a(ppc.li(12, HOLES), ppc.divw(11, 0, 12), ppc.mullw(12, 11, 12), ppc.subf(0, 12, 0), ppc.mulli(0, 0, entry))
    hi, lo = ppc.hi_lo(ptrs_at)
    a(ppc.slwi(11, 11, 2), ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.lwzx(3, 12, 11), ppc.add(3, 3, 0))


def info_lookup(a, name, count, ptrs_at, game):
    """FUN_80406f90 / FUN_8040094c (r3 = hole ID) -> hole info entry: ours first."""
    a.label(name)
    a(ppc.addi(0, 3, -FIRST_ID), cmplwi(0, HOLES * count - 1))
    a.br("bgt", name + "_game")
    per_course(a, 12, ptrs_at)
    a(ppc.BLR)
    a.label(name + "_game")
    a(LI_R8_0)
    a.b(game + 4)


def ours(a, reg, scratch=12):
    """cr0 "gt" unless the course code in `reg` is one of ours, 8 or 9 (clobbers `scratch`)."""
    a(ppc.addi(scratch, reg, -CODE), cmplwi(scratch, TEXAS - CODE))


def cave11_code(count, info_ptrs):
    a = ppc.Asm(CAVE11)
    a.label("list")
    a(*([0] * ((7 + count) * LIST_ENTRY // 4)))
    a.word("list_k")
    info_lookup(a, "info_menu", count, info_ptrs, INFO_BY_ID["menu"])
    return _done(a, "cave 11", CAVE11_SIZE)


def cave12_code(courses):
    a = ppc.Asm(CAVE12)
    a.label("info0")
    _data(a, info_table(0, courses[0]))
    if len(courses) > 1:
        a.label("info1")
        _data(a, info_table(1, courses[1]))
    a.label("info_ptrs")
    a(*([0] * 4))               # filled in by caves(): each course's table
    return _done(a, "cave 12", CAVE12_SIZE)


def cave18_code(courses, info_ptrs):
    a = ppc.Asm(CAVE18)
    if len(courses) > 2:
        a.label("info2")
        _data(a, info_table(2, courses[2]))
    info_lookup(a, "info_golf", len(courses), info_ptrs, INFO_BY_ID["golf"])
    return _done(a, "cave 18", CAVE18_SIZE)


def cave19_code(courses):
    a = ppc.Asm(CAVE19)
    if len(courses) > 3:
        a.label("info3")
        _data(a, info_table(3, courses[3]))
    a(0)
    return _done(a, "cave 19", CAVE19_SIZE)


def cave15_code(files, count):
    a = ppc.Asm(CAVE15)
    a.label("files0")
    _data(a, file_table(files[:HOLES]))
    if count > 1:
        a.label("files1")
        _data(a, file_table(files[HOLES:2 * HOLES]))
    a.label("files_ptrs")
    a(*([0] * 4))               # filled in by caves()
    id_lookup(a, "id_golf", count, ID_BY_HOLE["golf"])
    return _done(a, "cave 15", CAVE15_SIZE)


def cave23_code(count, files_ptrs):
    a = ppc.Asm(CAVE23)
    # FUN_80443e14 after the ID lookup (r3 = ID): our holes go in the spare slot of the file table
    a.label("resolve")
    a(ppc.addi(0, 3, -FIRST_ID), cmplwi(0, HOLES * count - 1))
    a.br("bgt", "resolve_game")
    a(ppc.mr(10, 3))
    per_course(a, 6, files_ptrs)
    a(ppc.mr(9, 3), ppc.mr(3, 10))
    hi, lo = ppc.hi_lo(FILE_SLOT)
    a(ppc.lis(10, hi), ppc.addi(10, 10, lo))
    a(lhz(0, 0, 9), ppc.stw(0, 0x00, 10))        # model
    a(lhz(0, 2, 9), ppc.stw(0, 0x04, 10))        # collision
    a(lhz(0, 4, 9), ppc.stw(0, 0x0C, 10))        # flyover camera
    a(ppc.li(0, 0), ppc.stw(0, 0x08, 10), ppc.stw(0, 0x10, 10), ppc.stw(0, 0x14, 10))   # no bank, rings, coins
    a(ppc.stw(3, 0x18, 10))                       # hole ID
    a(ppc.li(29, FILE_ROW), ppc.li(30, FILE_COL))
    a.b(RESOLVE_DONE)
    a.label("resolve_game")
    a(LI_R8_0)
    a.b(RESOLVE_HOOK + 4)
    return _done(a, "cave 23", CAVE23_SIZE)


def cave20_code(files, count):
    a = ppc.Asm(CAVE20)
    if count > 2:
        a.label("files2")
        _data(a, file_table(files[2 * HOLES:3 * HOLES]))
    if count > 3:
        a.label("files3")
        _data(a, file_table(files[3 * HOLES:4 * HOLES]))
    id_lookup(a, "id_menu", count, ID_BY_HOLE["menu"])
    return _done(a, "cave 20", CAVE20_SIZE)


def cave13_code(list_addr, list_k, count):
    a = ppc.Asm(CAVE13)
    # end of the course list builder: add ours in Stroke Play, Match Play (not Character Match), Skins, Practice
    a.label("list_append")
    hi, lo = ppc.hi_lo(MODE)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), cmplwi(0, 3))
    a.br("bgt", "list_append_done")
    a(ppc.cmpwi(0, 1))
    a.br("bne", "list_append_add")
    hi, lo = ppc.hi_lo(VERSUS)
    a(ppc.lis(12, hi), ppc.lbz(0, lo, 12), ppc.cmpwi(0, 4))
    a.br("beq", "list_append_done")
    a.label("list_append_add")
    k_hi, k_lo = ppc.hi_lo(list_k)
    a(ppc.li(0, 0), ppc.lis(12, k_hi), ppc.stw(0, k_lo, 12))
    a.label("list_append_next")     # k in list_k (FUN_8041358c clobbers the volatile registers)
    a(ppc.lis(12, k_hi), ppc.lwz(4, k_lo, 12), cmplwi(4, count - 1))
    a.br("bgt", "list_append_done")
    hi, lo = ppc.hi_lo(LIST_COUNT)
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), cmplwi(0, 6 + count))   # room left?
    a.br("bgt", "list_append_done")
    a(ppc.mulli(3, 0, LIST_ENTRY))
    hi, lo = ppc.hi_lo(list_addr)
    a(ppc.lis(5, hi), ppc.addi(5, 5, lo), ppc.add(3, 3, 5))
    a(ppc.addi(4, 4, CODE - 1), ppc.li(5, 0), ppc.li(6, 0))   # course index 7 + k
    a.bl(LIST_FILL)
    hi, lo = ppc.hi_lo(LIST_COUNT)
    a(ppc.lis(12, hi), ppc.lwz(11, lo, 12), ppc.addi(11, 11, 1), ppc.stw(11, lo, 12))   # (addi rD,r0,n is li)
    a(ppc.lis(12, k_hi), ppc.lwz(11, k_lo, 12), ppc.addi(11, 11, 1), ppc.stw(11, k_lo, 12))
    a.br("b", "list_append_next")
    a.label("list_append_done")
    a(LIST_END_WORD)
    a.b(LIST_END + 4)

    a.label("music")            # r4 = course code: ours play another course's songs (code 9: by variant)
    a(ppc.cmpwi(4, CODE))
    a.br("bne", "music_texas")
    a(ppc.li(4, COURSES[0]["music"]))
    a.br("b", "music_game")
    a.label("music_texas")
    a(ppc.cmpwi(4, TEXAS))
    a.br("bne", "music_game")
    load_variant(a, 12)
    a.la(11, "music_cols")
    a(ppc.lbzx(4, 11, 12))
    a.label("music_game")
    a(MUSIC_FIRST)
    a.b(MUSIC + 4)
    a.label("music_cols")
    _data(a, bytes(COURSES[k]["music"] for k in range(1, 4)))

    a.label("sky")             # r0 = the hole's course: Blooper Bay's sea sky, or its dome alone (r30 = the loader)
    for code, spec in BY_CODE.items():
        a(ppc.cmpwi(0, code))
        a.br("beq", "sky_" + spec["sky"])
    a(SKY_TEST_WORD)
    a.br("beq", "sky_blooper")
    a.b(SKY_DEFAULT)
    a.label("sky_blooper")
    a.b(SKY_BLOOPER)
    a.label("sky_dome")
    a(ppc.li(3, BLOOPER_DOME))
    a.bl(SKY_LOAD)
    a(ppc.stw(3, SKY_DOME, 30), ppc.li(3, 0), ppc.stw(3, SKY_BACKDROP, 30))
    a.b(SKY_DONE)

    a.label("reach")           # every golfer drives the course's bonus farther here (f1 = drive, r31 = player)
    hi, lo = ppc.hi_lo(COURSE_NOW)
    a(ppc.lis(12, hi), ppc.lbz(12, lo, 12))
    ours(a, 12)
    a.br("bgt", "reach_game")
    a(ppc.lbz(11, 0x51EF, 31), ppc.cmpwi(11, NO_BONUS_GOLFER))
    a.br("beq", "reach_game")
    a(ppc.slwi(12, 12, 2))     # (r3, r4 are the call's; r11, r12 and f0 are free at a call)
    a.la(11, "drive_bonus")
    a(ppc.add(11, 11, 12), ppc.lfs(0, 0, 11), ppc.fadds(1, 1, 0))
    a.label("reach_game")
    a.b(REACH)
    a.label("drive_bonus")
    for code in (CODE, TEXAS):
        a.float(f"drive_bonus_{code}", BY_CODE[code]["bonus"])

    a.label("star_row")        # a Star version's drive is its normal one on the "star_normal" courses
    hi, lo = ppc.hi_lo(COURSE_NOW)     # (r29 = row x 28, r9 = table, r31 = player)
    a(ppc.lis(12, hi), ppc.lbz(12, lo, 12))
    for code, spec in BY_CODE.items():
        if spec["star_normal"]:
            a(ppc.cmpwi(12, code))
            a.br("beq", "star_row_on")
    a.br("b", "star_row_game")
    a.label("star_row_on")
    hi, lo = ppc.hi_lo(PLAYER_OPTIONS)
    a(ppc.lwz(12, 0x5160, 31), ppc.lis(11, hi), ppc.addi(11, 11, lo), ppc.lbzx(12, 11, 12), ppc.andi_(12, 12, 1))
    a.br("beq", "star_row_game")
    a(ppc.addi(12, 29, -28), ppc.lwzx(9, 12, 9), ppc.BLR)   # the row before: the normal version's
    a.label("star_row_game")
    a(STAR_ROW_WORD, ppc.BLR)

    a.label("ace_guard")       # the hole-in-one mask store, skipped on our courses
    hi, lo = ppc.hi_lo(COURSE_NOW)
    a(ppc.lis(12, hi), ppc.lbz(12, lo, 12))
    ours(a, 12)
    a.br("ble", "ace_skip")
    a(*ACE_WORDS)
    a.label("ace_skip")
    a.b(ACE_DONE)
    return _done(a, "cave 13", CAVE13_SIZE)


def name_stub(a, label, add_word, reg, msgs):
    """The name message: msgs[i] where the game would show 0xAF + i (reg holds it after the game's add)."""
    a.label(label)
    a(add_word)
    for i, msg in enumerate(msgs):
        a(ppc.cmpwi(reg, NAME_OLD + i))
        a.br("bne", f"{label}_{i}")
        a(ppc.li(reg, msg), ppc.BLR)
        a.label(f"{label}_{i}")
    a(ppc.BLR)


def cave16_code(count):
    a = ppc.Asm(CAVE16)
    a.label("card_8")          # the HUD card switch's case for code 8: Pebble Beach's card
    a(ppc.li(4, file_id(COURSES[0]["card"])))
    a.b(CARD_LOAD)
    a.label("card_9")          # code 9: the variant's
    load_variant(a, 12)
    a(ppc.slwi(12, 12, 1))
    a.la(11, "card_ids")
    a(ppc.add(11, 11, 12), lhz(4, 0, 11))
    a.b(CARD_LOAD)
    a.label("card_ids")
    _data(a, b"".join(struct.pack(">H", file_id(COURSES[k]["card"])) for k in range(1, max(count, 2))))

    a.label("aim_score")       # the auto-aim's landing classes: another hole's ground scores 79, not a target
    a(ppc.lhz(0, -0xC, 27), ppc.andi_(0, 0, OTHER_HOLE_ATTR))   # r27 = the next triangle's attribute
    a.br("beq", "aim_score_cmp")
    a(ppc.li(3, AIM_SCORE_MIN - 1))
    a.label("aim_score_cmp")
    a(AIM_SCORE_WORD, ppc.BLR)

    # in a round, the name message: Pebble Beach's for code 8, the round's buffer for code 9
    golf_msgs = [COURSES[0]["msg"], ROUND_NAME_MSG]
    for label, add_word, reg in (("name", NAME_ADD, 4), ("name_r0", NAME_ADD_R0, 0), ("name_r9", NAME_ADD_R9, 9)):
        name_stub(a, label, add_word, reg, golf_msgs)
    return _done(a, "cave 16", CAVE16_SIZE)


def name_bytes(name):
    return b"\x093\x092\x074" + name.encode("ascii") + b"\0"   # styles 3 and 2, colour 4, as the game names courses


def cave21_code(count):
    a = ppc.Asm(CAVE21)
    for k in range(count):
        a.label(f"name_text_{k}")
        _data(a, name_bytes(COURSES[k]["name"]))
    longest = max(len(name_bytes(COURSES[k]["name"])) for k in range(1, max(count, 2)))
    a.label("round_name")      # code 9's name in a round (ROUND_NAME_MSG): Pasadena's until a round starts
    _data(a, name_bytes(COURSES[1]["name"]).ljust(longest, b"\0"))
    a.label("name_ptrs")       # the code-9 courses' names, by variant
    a(*[a.labels[f"name_text_{k}"] for k in range(1, max(count, 2))])
    a.label("emblem_ids")      # and emblems
    a(*[file_id(COURSES[k]["emblem"]) for k in range(1, max(count, 2))])

    # FUN_804014c0's first instruction (r3, r4 its arguments): for code 9 the variant's emblem and name
    a.label("round_start")
    hi, lo = ppc.hi_lo(SETUP_CODE)
    a(ppc.lis(12, hi), ppc.lbz(0, lo, 12), ppc.cmpwi(0, TEXAS))
    a.br("bne", "round_start_done")
    load_variant(a, 11)
    a(ppc.slwi(11, 11, 2))
    a.la(12, "emblem_ids")
    a(ppc.lwzx(0, 12, 11))
    hi, lo = ppc.hi_lo(EMBLEM_TABLE + 4 * TEXAS)
    a(ppc.lis(12, hi), ppc.stw(0, lo, 12))
    a.la(12, "name_ptrs")
    a(ppc.lwzx(11, 12, 11))
    a.la(12, "round_name")
    a.label("round_start_copy")
    a(ppc.lbz(0, 0, 11), ppc.stb(0, 0, 12), ppc.addi(11, 11, 1), ppc.addi(12, 12, 1), ppc.cmpwi(0, 0))
    a.br("bne", "round_start_copy")
    a.label("round_start_done")
    a(ROUND_START_WORD)
    a.b(ROUND_START + 4)
    return _done(a, "cave 21", CAVE21_SIZE)


def cave22_code(count):
    a = ppc.Asm(CAVE22)
    # the course select's commit (r3 = index + 1): 10 and 11 are code 9's variants 1 and 2
    a.label("commit")
    a(ppc.li(12, 0), ppc.cmpwi(3, TEXAS + 1))
    a.br("blt", "commit_store")
    a(ppc.addi(12, 3, -TEXAS), ppc.li(3, TEXAS))
    a.label("commit_store")
    hi, lo = ppc.hi_lo(VARIANT)
    a(COMMIT_WORD, ppc.lis(11, hi), ppc.stb(12, lo, 11), ppc.BLR)

    a.label("row_spacing")     # the icon row: narrower with more than 9 icons (r9 free, f11 = the spacing)
    hi, lo = ppc.hi_lo(LIST_COUNT)
    a(ppc.lis(9, hi), ppc.lwz(9, lo, 9), ppc.cmpwi(9, 9))
    a.br("bgt", "row_spacing_11")
    a(ppc.lis(9, 0x8044), ROW_SPACING_WORD, ppc.BLR)
    a.label("row_spacing_11")
    a.la(9, "row_spacing_value")
    a(ppc.lfs(11, 0, 9), ppc.BLR)
    a.float("row_spacing_value", ROW_SPACING_11)

    a.label("preview")         # (bl from PREVIEW_DEFAULT) r0 = course index past 6: r28 = the preview movie
    a(ppc.li(28, PREVIEW_WORD & 0xFFFF))
    for k in range(count):
        if COURSES[k]["preview"] != PREVIEW_WORD & 0xFFFF:
            a(ppc.cmpwi(0, CODE - 1 + k))
            a.br("bne", f"preview_{k}")
            a(ppc.li(28, COURSES[k]["preview"]), ppc.BLR)
            a.label(f"preview_{k}")
    a(ppc.BLR)

    name_stub(a, "name_menu", NAME_ADD, 4, [COURSES[k]["msg"] for k in range(count)])   # the course select's names
    return _done(a, "cave 22", CAVE22_SIZE)


def caves(courses):
    """courses: [(holes, files)] in k order -> [(address, expected first word, code)], labels"""
    holes = [h for h, f in courses]
    files = [x for h, f in courses for x in f]
    count = len(courses)
    if count > len(COURSES):
        raise SystemExit(f"{count} courses: only {len(COURSES)} are known")
    # two passes: the pointer tables' addresses are needed before they're known
    c12, l12 = cave12_code(holes)
    c18, l18 = cave18_code(holes, l12["info_ptrs"])
    c19, l19 = cave19_code(holes)
    c15, l15 = cave15_code(files, count)
    c20, l20 = cave20_code(files, count)
    c11, l11 = cave11_code(count, l12["info_ptrs"])
    c13, l13 = cave13_code(l11["list"], l11["list_k"], count)
    c16, l16 = cave16_code(count)
    c21, l21 = cave21_code(count)
    c22, l22 = cave22_code(count)
    c23, l23 = cave23_code(count, l15["files_ptrs"])
    info = [l12["info0"]] + [l for l in (l12.get("info1"), l18.get("info2"), l19.get("info3")) if l][:count - 1]
    file_ = [l15["files0"]] + [l for l in (l15.get("files1"), l20.get("files2"), l20.get("files3")) if l][:count - 1]
    c12 = bytearray(c12)
    struct.pack_into(">4I", c12, l12["info_ptrs"] - CAVE12, *(info + [0] * (4 - len(info))))
    c15 = bytearray(c15)
    struct.pack_into(">4I", c15, l15["files_ptrs"] - CAVE15, *(file_ + [0] * (4 - len(file_))))
    labels = {**l11, **l12, **l13, **l15, **l16, **l18, **l19, **l20, **l21, **l22, **l23, "_count": count,
              "_sizes": {"11": len(c11), "12": len(c12), "13": len(c13), "15": len(c15), "16": len(c16),
                         "18": len(c18), "19": len(c19), "20": len(c20), "21": len(c21), "22": len(c22),
                         "23": len(c23)}}
    return [(CAVE11, CAVE11_FIRST, c11), (CAVE12, CAVE12_FIRST, bytes(c12)), (CAVE13, CAVE13_FIRST, c13),
            (CAVE15, CAVE15_FIRST, bytes(c15)), (CAVE16, CAVE16_FIRST, c16), (CAVE18, CAVE18_FIRST, c18),
            (CAVE19, CAVE19_FIRST, c19), (CAVE20, CAVE20_FIRST, c20), (CAVE21, CAVE21_FIRST, c21),
            (CAVE22, CAVE22_FIRST, c22), (CAVE23, CAVE23_FIRST, c23)], labels


def texts(labels):
    """[(message id, string address)] for build_mod.py's message hook."""
    out = [(COURSES[k]["msg"], labels[f"name_text_{k}"]) for k in range(labels["_count"])]
    return out + [(ROUND_NAME_MSG, labels["round_name"])]


def dol_patches(labels):
    """[(address, new word, expected word)] for main.dol."""
    return [(MUSIC, ppc.b(MUSIC, labels["music"]), MUSIC_FIRST)]


def overlay_patches(rel, labels, word):
    """[(address, new word, expected word)] for the golf (C/L/V) or menu (B/U/C) overlay; word(addr) reads it."""
    out = []
    count = labels["_count"]
    if rel == "C/L/V":
        out.append((INFO_BY_ID["golf"], ppc.b(INFO_BY_ID["golf"], labels["info_golf"]), LI_R8_0))
        out.append((ID_BY_HOLE["golf"], ppc.b(ID_BY_HOLE["golf"], labels["id_golf"]), MR_R8_R3))
        out.append((RESOLVE_HOOK, ppc.b(RESOLVE_HOOK, labels["resolve"]), LI_R8_0))
        out.append((ACE_HOOK, ppc.b(ACE_HOOK, labels["ace_guard"]), ACE_WORDS[0]))
        out.append((AIM_SCORE, ppc.bl(AIM_SCORE, labels["aim_score"]), AIM_SCORE_WORD))
        out.append((REACH_HOOK, ppc.bl(REACH_HOOK, labels["reach"]), ppc.bl(REACH_HOOK, REACH)))
        out.append((STAR_ROW_HOOK, ppc.bl(STAR_ROW_HOOK, labels["star_row"]), STAR_ROW_WORD))
        out.append((SKY_TEST, ppc.b(SKY_TEST, labels["sky"]), SKY_TEST_WORD))
        out.append((NAME_SITES["golf"], ppc.bl(NAME_SITES["golf"], labels["name"]), NAME_ADD))
        out.append((ROUND_START, ppc.b(ROUND_START, labels["round_start"]), ROUND_START_WORD))
        for code in (CODE, TEXAS):
            entry = CARD_TABLE + 4 * code
            out.append((entry, (labels[f"card_{code}"] - CARD_TABLE) & 0xFFFFFFFF, word(entry)))
            entry = EMBLEM_TABLE + 4 * code
            out.append((entry, file_id(COURSES[code - CODE]["emblem"]), EMBLEM_OLD[code - CODE]))
        for site in NAME_SITES_R0:
            out.append((site, ppc.bl(site, labels["name_r0"]), NAME_ADD_R0))
        out.append((NAME_SITE_R9, ppc.bl(NAME_SITE_R9, labels["name_r9"]), NAME_ADD_R9))
    elif rel == "B/U/C":
        out.append((INFO_BY_ID["menu"], ppc.b(INFO_BY_ID["menu"], labels["info_menu"]), LI_R8_0))
        out.append((ID_BY_HOLE["menu"], ppc.b(ID_BY_HOLE["menu"], labels["id_menu"]), MR_R8_R3))
        hi, lo = ppc.hi_lo(labels["list"])
        old_hi, old_lo = ppc.hi_lo(LIST_OLD)
        done = set()
        for lis_at, addi_at in LIST_SITES:
            if lis_at not in done:
                w = word(lis_at)
                if w & 0xFC1FFFFF != 0x3C000000 | (old_hi & 0xFFFF):
                    raise SystemExit(f"0x{lis_at:08X}: not lis rX,0x{old_hi:04X}")
                out.append((lis_at, (w & 0xFFFF0000) | hi, w))
                done.add(lis_at)
            w = word(addi_at)
            if w & 0xFFFF != old_lo & 0xFFFF or w >> 26 != 14:
                raise SystemExit(f"0x{addi_at:08X}: not addi rX,rY,{old_lo}")
            out.append((addi_at, (w & 0xFFFF0000) | (lo & 0xFFFF), w))
        out.append((LIST_END, ppc.b(LIST_END, labels["list_append"]), LIST_END_WORD))
        out.append((PREVIEW_DEFAULT, ppc.bl(PREVIEW_DEFAULT, labels["preview"]), PREVIEW_WORD))
        out.append((NAME_SITES["menu"], ppc.bl(NAME_SITES["menu"], labels["name_menu"]), NAME_ADD))
        out.append((COMMIT, ppc.bl(COMMIT, labels["commit"]), COMMIT_WORD))
        out.append((ROW_SPACING, ppc.bl(ROW_SPACING, labels["row_spacing"]), ROW_SPACING_WORD))
    return out


# ---------------------------------------------------------------- the courses' content

HOLE_FILES = 0x804DCF18     # golf: hole file table, 9 rows x 18 x 0x20 (+0 model, +4 collision, +C flyover, +18 ID)
CARD = [(380, 380, 4), (511, 516, 5), (404, 404, 4), (331, 331, 4), (195, 195, 3), (523, 523, 5), (109, 109, 3),
        (428, 428, 4), (505, 526, 4), (446, 495, 4), (390, 390, 4), (202, 202, 3), (445, 445, 4), (580, 580, 5),
        (397, 397, 4), (403, 403, 4), (178, 178, 3), (543, 543, 5)]   # Pebble Beach: regular, back tees, par


def file_id(path):
    """Disc path "E/A/B" -> the game's file ID for a packed file (2 x letter number + 1)."""
    a, b, c = (ord(x) - 65 for x in path.split("/"))
    return 2 * (676 * a + 26 * b + c) + 1


def placeholder_files(golf, ids=range(201, 219)):
    """(model, collision, flyover) of existing holes, to try the course out before its own files exist."""
    found = {}
    for k in range(9 * 18):
        model, coll, bank, fly, rings, coins, hole_id = struct.unpack_from(">7I", golf, HOLE_FILES - 0x80400000 + 0x20 * k)
        found.setdefault(hole_id, (model, coll, fly))
    return [found[i] for i in ids]


def load(folder, golf):
    """A course from a folder made by the course generator (course.json + its files), or Pebble Beach's card on
    placeholder holes when folder is "placeholder". Returns (holes, files, {disc path: source file})."""
    if folder == "placeholder":
        return CARD, placeholder_files(golf), {}
    import json
    import os
    spec = json.load(open(os.path.join(folder, "course.json")))
    holes = [(h["yards"], h["back"], h["par"]) for h in spec["holes"]]
    files = [(file_id(h["model"]), file_id(h["collision"]), file_id(h["flyover"])) for h in spec["holes"]]
    disc = {path: os.path.join(folder, src) for path, src in spec["files"].items()}
    return holes, files, disc


# ---------------------------------------------------------------- the course select icon (our own art)

ICONS = "files/B/W/R"       # course select icons: textures 0-6, 68x68; 7 is the 106x106 star medallion that index 7
ICON_TEX = 7                # shows (and the records screen's fallback): it becomes Pebble Beach's icon; index 8 shows
                            # texture 8, which v21 appends for Pasadena (68x68 like the game's own)


def icon_image(size=106):
    """Pebble Beach: a rocky headland in the sea with a green and a red flag, outlined in black like the game's
    icons."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    k = 4
    S = size * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 6 * k

    def blob(cx, cy, rx, ry, wobble, seed, n=40):
        rng = np.random.default_rng(seed)
        ph = rng.uniform(0, 6.28, 3)
        pts = []
        for i in range(n):
            a = 6.2832 * i / n
            r = 1 + wobble * (0.5 * np.sin(3 * a + ph[0]) + 0.3 * np.sin(5 * a + ph[1]) + 0.2 * np.sin(7 * a + ph[2]))
            pts.append((cx + rx * r * np.cos(a), cy + ry * r * np.sin(a)))
        return pts

    sea = blob(S / 2, S / 2 + 4 * k, S / 2 - pad, S / 2 - pad - 6 * k, 0.05, 1)
    d.polygon(sea, fill=(0, 0, 0, 255))
    inner = blob(S / 2, S / 2 + 4 * k, S / 2 - pad - 4 * k, S / 2 - pad - 10 * k, 0.05, 1)
    d.polygon(inner, fill=(40, 120, 200, 255))
    for x, y, w in ((0.25, 0.3, 12), (0.62, 0.26, 14), (0.72, 0.78, 10), (0.2, 0.76, 9)):   # waves
        d.arc([S * x - w * k, S * y - 3 * k, S * x + w * k, S * y + 5 * k], 200, 340, fill=(190, 225, 250, 255),
              width=2 * k)
    rock = blob(S * 0.46, S * 0.62, S * 0.27, S * 0.16, 0.18, 3)
    d.polygon([(x + 3 * k, y + 5 * k) for x, y in rock], fill=(255, 255, 255, 220))    # surf
    d.polygon(rock, fill=(110, 95, 80, 255), outline=(30, 25, 20, 255))
    land = blob(S * 0.45, S * 0.56, S * 0.25, S * 0.12, 0.16, 3)
    d.polygon(land, fill=(70, 170, 60, 255), outline=(30, 80, 25, 255))
    green = blob(S * 0.52, S * 0.54, S * 0.09, S * 0.045, 0.1, 5)
    d.polygon(green, fill=(120, 220, 90, 255))
    for x, y in ((0.3, 0.52), (0.36, 0.48)):   # cypress trees
        d.ellipse([S * x - 7 * k, S * y - 6 * k, S * x + 7 * k, S * y + 3 * k], fill=(30, 90, 40, 255),
                  outline=(15, 45, 20, 255))
    fx, fy = S * 0.54, S * 0.53
    d.line([(fx, fy), (fx, fy - 22 * k)], fill=(250, 250, 250, 255), width=2 * k)
    d.polygon([(fx, fy - 22 * k), (fx + 11 * k, fy - 18 * k), (fx, fy - 14 * k)], fill=(230, 30, 30, 255))
    img = img.resize((size, size), Image.LANCZOS)
    return np.asarray(img)


def icons_file(clean_files, count=1):
    """B/W/R with texture 7 replaced by Pebble Beach's icon (same size and format), and textures 8.. appended for
    the other courses (68x68 like the game's own): Pasadena's, Battleground's, Timber Creek's."""
    import os
    import camelot_lz as lz
    import teams
    import textures as tx
    raw = open(os.path.join(clean_files, *ICONS[len("files/"):].split("/")), "rb").read()
    blob = bytearray(lz.decompress(raw)[0])
    hs = tx.headers(blob, 0)
    ho, w, h, f, data, lod = hs[ICON_TEX]
    if (w, h, f) != (106, 106, 5) or len(hs) != 8:
        raise SystemExit(f"{ICONS}: texture {ICON_TEX} isn't the 106x106 RGB5A3 medallion")
    pic = icon_image(108)
    tx.put_rgb5a3(blob, data, 108, 0, 0, pic)
    if count > 1:
        h0 = hs[0]
        if (h0[1], h0[2], h0[3], h0[5]) != (68, 68, 5, 0):
            raise SystemExit(f"{ICONS}: texture 0 isn't a 68x68 RGB5A3 icon")
        added = []
        for k in range(1, count):
            new = bytearray(tx.level_size(68, 68, 5))
            tx.put_rgb5a3(new, 0, 68, 0, 0, ICON_ART[k](68))
            added.append((bytes(blob[h0[0]:h0[0] + 0x24]), bytes(new)))
        blob = teams.append_textures(bytes(blob), added)
    return lz.pack(raw[0], bytes(blob))


def pasadena_icon(size=68):
    """Pasadena Municipal: a parkland hole on flat ground, a pond, an oak and a green with a red flag under a Texas
    star, outlined in black like the game's icons."""
    import numpy as np
    from PIL import Image, ImageDraw
    k = 4
    S = size * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 3 * k
    d.ellipse([pad, pad, S - pad, S - pad], fill=(0, 0, 0, 255))
    o = pad + 3 * k
    d.ellipse([o, o, S - o, S - o], fill=(110, 190, 240, 255))     # sky
    land = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(land)
    ld.rectangle([0, S * 0.42, S, S], fill=(80, 170, 60, 255))     # flat Texas grass from the horizon down
    for x, r in ((0.12, 0.09), (0.3, 0.07), (0.82, 0.1), (0.95, 0.08)):   # the tree line
        ld.ellipse([S * (x - r), S * (0.42 - r * 0.8), S * (x + r), S * (0.42 + r * 0.6)], fill=(35, 100, 45, 255))
    ld.polygon([(S * 0.35, S * 0.47), (S * 0.65, S * 0.47), (S * 0.9, S), (S * 0.1, S)], fill=(115, 205, 80, 255))
    ld.ellipse([S * 0.05, S * 0.66, S * 0.5, S * 0.86], fill=(40, 110, 200, 255), outline=(20, 60, 120, 255),
               width=k)                                             # the pond
    ld.ellipse([S * 0.13, S * 0.7, S * 0.3, S * 0.74], fill=(170, 215, 245, 255))
    ld.ellipse([S * 0.48, S * 0.5, S * 0.78, S * 0.6], fill=(150, 230, 110, 255), outline=(40, 110, 40, 255),
               width=k)                                             # the green
    ld.line([(S * 0.68, S * 0.15), (S * 0.68, S * 0.66)], fill=(70, 50, 30, 255), width=3 * k)   # an oak
    ld.ellipse([S * 0.55, S * 0.12, S * 0.84, S * 0.42], fill=(45, 120, 50, 255), outline=(20, 60, 25, 255),
               width=k)
    fx, fy = S * 0.6, S * 0.55
    ld.line([(fx, fy), (fx, fy - 0.3 * S)], fill=(250, 250, 250, 255), width=2 * k)
    ld.polygon([(fx, fy - 0.3 * S), (fx + 0.14 * S, fy - 0.25 * S), (fx, fy - 0.2 * S)], fill=(230, 30, 30, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([o, o, S - o, S - o], fill=255)
    img.paste(land, (0, 0), Image.composite(land, Image.new("RGBA", (S, S)), mask).split()[3])

    def star(cx, cy, ro, fill):
        import math
        pts = [(cx + (ro if i % 2 == 0 else ro * 0.42) * math.cos(-math.pi / 2 + i * math.pi / 5),
                cy + (ro if i % 2 == 0 else ro * 0.42) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
        d.polygon(pts, fill=fill, outline=(0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    star(S * 0.3, S * 0.24, S * 0.13, (255, 255, 255, 255))         # the lone star
    return np.asarray(img.resize((size, size), Image.LANCZOS))


EMBLEM_TEMPLATE = "C/O/U"   # our emblem files (COURSES "emblem") are 106x106 RGB5A3 medallions like this one
EMBLEM_TABLE = 0x804D5F9C   # golf: course emblem file IDs by course code (hole intro banner, pause menu)
EMBLEM_OLD = (3473, 3473)   # entries 8 and 9: C/O/U, Lakitu Valley's


def emblem_file(clean_files, k=0):
    """A medallion file like C/O/U holding course k's course select icon picture, packed the same way."""
    import os
    import camelot_lz as lz
    import numpy as np
    import textures as tx
    raw = open(os.path.join(clean_files, *EMBLEM_TEMPLATE.split("/")), "rb").read()
    blob = bytearray(lz.decompress(raw)[0])
    ho, w, h, f, data, lod = tx.headers(blob, 0)[0]
    if (w, h, f) != (106, 106, 5):
        raise SystemExit(f"{EMBLEM_TEMPLATE} isn't the 106x106 RGB5A3 medallion")
    pic = icon_image(108) if k == 0 else np.pad(ICON_ART[k](104), ((2, 2), (2, 2), (0, 0)))
    tx.put_rgb5a3(blob, data, 108, 0, 0, pic)
    return lz.pack(raw[0], bytes(blob))


# ---------------------------------------------------------------- the HUD course card (our own art)

CARD_TEMPLATE = "A/X/K"     # our card files (COURSES "card") hold one 130x130 CMPR texture like this, Lakitu's card
CARD_TABLE = 0x804DCA78     # golf: the hole loader's card switch, entries relative to the table, by course code
CARD_LOAD = 0x80446468      # bl FUN_8000bed8(r3 = loader + 0x5F58, r4 = file ID)


def card_image(size=130):
    """Pebble Beach's course card: a rocky point with a green, a cypress and the sea, in a frame with wave
    corners."""
    import numpy as np
    from PIL import Image, ImageDraw
    k = 4
    S = size * k
    img = Image.new("RGB", (S, S), (255, 200, 60))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, S - 1, S - 1], outline=(200, 120, 20), width=3 * k)
    m = 10 * k
    d.ellipse([m, m, S - m, S - m], fill=(20, 60, 90))
    inner = [m + 3 * k, m + 3 * k, S - m - 3 * k, S - m - 3 * k]
    scene = Image.new("RGB", (S, S), (0, 0, 0))
    sd = ImageDraw.Draw(scene)
    for y in range(S):                       # sky, then sea below the horizon
        t = y / S
        if t < 0.48:
            c = (int(120 + 100 * t), int(190 + 60 * t), 250)
        else:
            u = (t - 0.48) / 0.52
            c = (int(30 + 40 * (1 - u)), int(110 + 60 * (1 - u)), int(170 + 40 * (1 - u)))
        sd.line([(0, y), (S, y)], fill=c)
    sd.polygon([(0, S * 0.5), (S * 0.25, S * 0.43), (S * 0.45, S * 0.47), (S * 0.6, S * 0.5)], fill=(90, 120, 110))
    sd.polygon([(S * 0.18, S), (S * 0.22, S * 0.66), (S * 0.5, S * 0.58), (S * 0.85, S * 0.64), (S * 0.95, S)],
               fill=(105, 90, 75))                                       # the rocks
    sd.polygon([(S * 0.24, S * 0.68), (S * 0.5, S * 0.6), (S * 0.82, S * 0.65), (S * 0.78, S * 0.72),
                (S * 0.3, S * 0.74)], fill=(80, 175, 60))                 # grass
    sd.ellipse([S * 0.48, S * 0.62, S * 0.7, S * 0.68], fill=(130, 225, 95))   # the green
    for x0 in (0.1, 0.9):                    # surf
        sd.ellipse([S * (x0 - 0.12), S * 0.8, S * (x0 + 0.12), S * 0.9], fill=(235, 245, 250))
    fx, fy = S * 0.6, S * 0.645
    sd.line([(fx, fy), (fx, fy - 18 * k)], fill=(255, 255, 255), width=k)
    sd.polygon([(fx, fy - 18 * k), (fx + 9 * k, fy - 15 * k), (fx, fy - 12 * k)], fill=(230, 30, 30))
    cx, cy = S * 0.33, S * 0.6                # a Monterey cypress, flat-topped and leaning
    sd.line([(cx, cy + 10 * k), (cx + 6 * k, cy - 8 * k)], fill=(80, 55, 40), width=3 * k)
    for dx, dy, r in ((-4, -12, 11), (8, -14, 12), (18, -11, 9), (2, -18, 9)):
        sd.ellipse([cx + (dx - r) * k, cy + (dy - r * 0.55) * k, cx + (dx + r) * k, cy + (dy + r * 0.55) * k],
                   fill=(35, 95, 50))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(inner, fill=255)
    img.paste(scene, (0, 0), mask)
    for cx, cy in ((m, m), (S - m, m), (m, S - m), (S - m, S - m)):   # wave corners
        d.ellipse([cx - 9 * k, cy - 9 * k, cx + 9 * k, cy + 9 * k], fill=(250, 250, 255), outline=(60, 120, 190),
                  width=k)
        d.arc([cx - 6 * k, cy - 4 * k, cx + 6 * k, cy + 6 * k], 200, 340, fill=(60, 120, 190), width=k)
    return np.asarray(img.resize((size, size), Image.LANCZOS))


def pasadena_card(size=130):
    """Pasadena Municipal's course card: a flat parkland hole with a pond, oaks and a green under a big Texas sky,
    in a frame with star corners."""
    import math
    import numpy as np
    from PIL import Image, ImageDraw
    k = 4
    S = size * k
    img = Image.new("RGB", (S, S), (190, 40, 50))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, S - 1, S - 1], outline=(120, 20, 30), width=3 * k)
    m = 10 * k
    d.ellipse([m, m, S - m, S - m], fill=(30, 50, 110))
    inner = [m + 3 * k, m + 3 * k, S - m - 3 * k, S - m - 3 * k]
    scene = Image.new("RGB", (S, S), (0, 0, 0))
    sd = ImageDraw.Draw(scene)
    for y in range(S):                       # sky down to a low horizon, then grass
        t = y / S
        if t < 0.52:
            c = (int(90 + 120 * t), int(170 + 70 * t), 250)
        else:
            u = (t - 0.52) / 0.48
            c = (int(95 - 25 * u), int(175 - 30 * u), int(70 - 20 * u))
        sd.line([(0, y), (S, y)], fill=c)
    for x, r in ((0.08, 0.08), (0.2, 0.06), (0.34, 0.07), (0.7, 0.07), (0.84, 0.09), (0.97, 0.07)):   # tree line
        sd.ellipse([S * (x - r), S * (0.52 - r * 0.9), S * (x + r), S * (0.52 + r * 0.4)], fill=(40, 95, 45))
    sd.polygon([(S * 0.44, S * 0.53), (S * 0.58, S * 0.53), (S * 0.85, S), (S * 0.25, S)], fill=(120, 200, 85))
    sd.ellipse([S * 0.08, S * 0.7, S * 0.5, S * 0.86], fill=(50, 120, 190))       # the pond
    sd.ellipse([S * 0.15, S * 0.73, S * 0.32, S * 0.76], fill=(170, 210, 240))
    sd.ellipse([S * 0.48, S * 0.56, S * 0.68, S * 0.61], fill=(150, 230, 105))     # the green
    fx, fy = S * 0.58, S * 0.585
    sd.line([(fx, fy), (fx, fy - 18 * k)], fill=(255, 255, 255), width=k)
    sd.polygon([(fx, fy - 18 * k), (fx + 9 * k, fy - 15 * k), (fx, fy - 12 * k)], fill=(230, 30, 30))
    cx, cy = S * 0.76, S * 0.62               # a live oak, wide and low
    sd.line([(cx, cy + 12 * k), (cx, cy - 4 * k)], fill=(80, 55, 40), width=3 * k)
    for dx, dy, r in ((-9, -8, 10), (6, -10, 11), (16, -5, 8), (-1, -15, 9)):
        sd.ellipse([cx + (dx - r) * k, cy + (dy - r * 0.7) * k, cx + (dx + r) * k, cy + (dy + r * 0.7) * k],
                   fill=(40, 105, 50))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(inner, fill=255)
    img.paste(scene, (0, 0), mask)
    for cx, cy in ((m, m), (S - m, m), (m, S - m), (S - m, S - m)):   # star corners
        pts = [(cx + (9 * k if i % 2 == 0 else 3.8 * k) * math.cos(-math.pi / 2 + i * math.pi / 5),
                cy + (9 * k if i % 2 == 0 else 3.8 * k) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
        d.polygon(pts, fill=(255, 255, 255), outline=(30, 50, 110))
    return np.asarray(img.resize((size, size), Image.LANCZOS))


def _disc(size, sky, k=4):
    """A round icon's canvas: a black ring with the sky inside. Returns (image, S, inner offset)."""
    from PIL import Image, ImageDraw
    S = size * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 3 * k
    d.ellipse([pad, pad, S - pad, S - pad], fill=(0, 0, 0, 255))
    o = pad + 3 * k
    d.ellipse([o, o, S - o, S - o], fill=sky)
    return img, S, o


def _paste_round(img, scene, S, o):
    from PIL import Image, ImageDraw
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([o, o, S - o, S - o], fill=255)
    img.paste(scene, (0, 0), Image.composite(scene, Image.new("RGBA", (S, S)), mask).split()[3])


def _monument(d, x, base, top, w):
    """The San Jacinto Monument: a tapering shaft on a base, the Lone Star on top."""
    import math
    d.polygon([(x - w, base), (x + w, base), (x + w * 0.62, top), (x - w * 0.62, top)], fill=(236, 226, 200),
              outline=(120, 110, 90))
    d.rectangle([x - w * 1.9, base - w * 0.5, x + w * 1.9, base + w * 0.4], fill=(220, 210, 185),
                outline=(120, 110, 90))
    r = w * 1.25
    pts = [(x + (r if i % 2 == 0 else r * 0.42) * math.cos(-math.pi / 2 + i * math.pi / 5),
            top - r * 0.9 + (r if i % 2 == 0 else r * 0.42) * math.sin(-math.pi / 2 + i * math.pi / 5))
           for i in range(10)]
    d.polygon(pts, fill=(250, 250, 255), outline=(60, 60, 70))


def _flag(d, S, fx, fy, k=1):
    d.line([(fx, fy), (fx, fy - 0.26 * S)], fill=(250, 250, 250, 255), width=8)
    d.polygon([(fx, fy - 0.26 * S), (fx + 0.13 * S, fy - 0.215 * S), (fx, fy - 0.17 * S)], fill=(230, 30, 30, 255))


def battleground_icon(size=68):
    """Battleground: the San Jacinto Monument over flat grass, a pond and a green with a red flag."""
    import numpy as np
    from PIL import Image, ImageDraw
    img, S, o = _disc(size, (110, 185, 240, 255))
    scene = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(scene)
    d.rectangle([0, S * 0.55, S, S], fill=(85, 170, 65, 255))
    for x, r in ((0.08, 0.08), (0.9, 0.09)):                       # trees on the horizon
        d.ellipse([S * (x - r), S * (0.55 - r), S * (x + r), S * (0.55 + r * 0.5)], fill=(40, 100, 45, 255))
    _monument(d, S * 0.36, S * 0.57, S * 0.13, S * 0.045)
    d.polygon([(S * 0.45, S * 0.6), (S * 0.62, S * 0.6), (S * 0.92, S), (S * 0.2, S)], fill=(120, 205, 85, 255))
    d.ellipse([S * 0.05, S * 0.72, S * 0.45, S * 0.9], fill=(40, 110, 200, 255), outline=(20, 60, 120, 255),
              width=4)                                              # the pond
    d.ellipse([S * 0.5, S * 0.62, S * 0.8, S * 0.71], fill=(150, 230, 110, 255), outline=(40, 110, 40, 255), width=4)
    _flag(d, S, S * 0.66, S * 0.66)
    _paste_round(img, scene, S, o)
    return np.asarray(img.resize((size, size), Image.LANCZOS))


def _pine(d, x, base, h, w, fill=(30, 85, 45, 255), edge=(15, 45, 22, 255)):
    d.line([(x, base), (x, base - h * 0.2)], fill=(85, 60, 40), width=max(2, int(w * 0.25)))
    for t in range(3):                                              # three tiers
        y0 = base - h * (0.15 + 0.27 * t)
        ww = w * (1 - 0.25 * t)
        d.polygon([(x - ww, y0), (x + ww, y0), (x, y0 - h * 0.42)], fill=fill, outline=edge)


def timbercreek_icon(size=68):
    """Timber Creek: tall pines either side, Clear Creek under a wooden bridge, a green with a red flag."""
    import numpy as np
    from PIL import Image, ImageDraw
    img, S, o = _disc(size, (120, 190, 240, 255))
    scene = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(scene)
    d.rectangle([0, S * 0.5, S, S], fill=(80, 160, 60, 255))
    for x, h in ((0.1, 0.5), (0.22, 0.42), (0.8, 0.46), (0.93, 0.52), (0.5, 0.2), (0.62, 0.18)):   # the woods
        _pine(d, S * x, S * 0.56, S * h, S * h * 0.32)
    d.polygon([(0, S * 0.78), (S * 0.3, S * 0.72), (S * 0.65, S * 0.8), (S, S * 0.74), (S, S * 0.86),
               (S * 0.65, S * 0.92), (S * 0.3, S * 0.84), (0, S * 0.9)], fill=(50, 120, 200, 255))   # the creek
    d.rectangle([S * 0.36, S * 0.73, S * 0.56, S * 0.8], fill=(140, 95, 55, 255), outline=(70, 45, 25, 255),
                width=3)                                            # the bridge
    for x in (0.4, 0.45, 0.5):
        d.line([(S * x, S * 0.73), (S * x, S * 0.8)], fill=(90, 60, 35, 255), width=2)
    d.ellipse([S * 0.32, S * 0.55, S * 0.66, S * 0.66], fill=(150, 230, 110, 255), outline=(40, 110, 40, 255),
              width=4)                                              # the green
    _flag(d, S, S * 0.52, S * 0.6)
    _paste_round(img, scene, S, o)
    return np.asarray(img.resize((size, size), Image.LANCZOS))


def _card(size, frame, edge, ring, scene_draw, corner):
    """A course card: a frame round a round scene, with four corner marks (like pasadena_card)."""
    import numpy as np
    from PIL import Image, ImageDraw
    k = 4
    S = size * k
    img = Image.new("RGB", (S, S), frame)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, S - 1, S - 1], outline=edge, width=3 * k)
    m = 10 * k
    d.ellipse([m, m, S - m, S - m], fill=ring)
    inner = [m + 3 * k, m + 3 * k, S - m - 3 * k, S - m - 3 * k]
    scene = Image.new("RGB", (S, S), (0, 0, 0))
    scene_draw(ImageDraw.Draw(scene), S, k)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(inner, fill=255)
    img.paste(scene, (0, 0), mask)
    for cx, cy in ((m, m), (S - m, m), (m, S - m), (S - m, S - m)):
        corner(d, cx, cy, k)
    return np.asarray(img.resize((size, size), Image.LANCZOS))


def _sky_and_grass(sd, S, horizon, grass=((95, 175, 70), (70, 145, 50))):
    for y in range(S):
        t = y / S
        if t < horizon:
            c = (int(90 + 120 * t), int(170 + 70 * t), 250)
        else:
            u = (t - horizon) / (1 - horizon)
            c = tuple(int(a + (b - a) * u) for a, b in zip(*grass))
        sd.line([(0, y), (S, y)], fill=c)


def _star_corner(d, cx, cy, k, fill=(255, 255, 255), outline=(30, 50, 110)):
    import math
    pts = [(cx + (9 * k if i % 2 == 0 else 3.8 * k) * math.cos(-math.pi / 2 + i * math.pi / 5),
            cy + (9 * k if i % 2 == 0 else 3.8 * k) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
    d.polygon(pts, fill=fill, outline=outline)


def battleground_card(size=130):
    """Battleground's course card: the San Jacinto Monument over a pond and a green, in Texas blue with stars."""
    def scene(sd, S, k):
        _sky_and_grass(sd, S, 0.55)
        for x, r in ((0.12, 0.07), (0.25, 0.05), (0.78, 0.06), (0.9, 0.08)):
            sd.ellipse([S * (x - r), S * (0.55 - r * 0.9), S * (x + r), S * (0.55 + r * 0.4)], fill=(40, 95, 45))
        _monument(sd, S * 0.42, S * 0.56, S * 0.16, S * 0.035)
        sd.ellipse([S * 0.08, S * 0.7, S * 0.5, S * 0.86], fill=(50, 120, 190))
        sd.ellipse([S * 0.15, S * 0.73, S * 0.32, S * 0.76], fill=(170, 210, 240))
        sd.ellipse([S * 0.5, S * 0.6, S * 0.72, S * 0.66], fill=(150, 230, 105))
        fx, fy = S * 0.62, S * 0.63
        sd.line([(fx, fy), (fx, fy - 18 * k)], fill=(255, 255, 255), width=k)
        sd.polygon([(fx, fy - 18 * k), (fx + 9 * k, fy - 15 * k), (fx, fy - 12 * k)], fill=(230, 30, 30))
    return _card(size, (30, 60, 140), (15, 30, 80), (190, 40, 50), scene, _star_corner)


def timbercreek_card(size=130):
    """Timber Creek's course card: a fairway between tall pines, the creek and a green, in a wooden frame."""
    def scene(sd, S, k):
        _sky_and_grass(sd, S, 0.5)
        for x, h in ((0.05, 0.42), (0.16, 0.36), (0.27, 0.3), (0.73, 0.32), (0.84, 0.38), (0.95, 0.44)):
            _pine(sd, S * x, S * 0.62, S * h, S * h * 0.3, fill=(30, 85, 45), edge=(15, 45, 22))
        sd.polygon([(S * 0.4, S * 0.52), (S * 0.6, S * 0.52), (S * 0.8, S), (S * 0.2, S)], fill=(120, 200, 85))
        sd.polygon([(0, S * 0.8), (S * 0.35, S * 0.76), (S * 0.7, S * 0.83), (S, S * 0.78), (S, S * 0.88),
                    (S * 0.7, S * 0.93), (S * 0.35, S * 0.86), (0, S * 0.9)], fill=(50, 115, 190))
        sd.rectangle([S * 0.4, S * 0.77, S * 0.6, S * 0.84], fill=(140, 95, 55), outline=(70, 45, 25))
        sd.ellipse([S * 0.42, S * 0.53, S * 0.6, S * 0.58], fill=(150, 230, 105))
        fx, fy = S * 0.52, S * 0.555
        sd.line([(fx, fy), (fx, fy - 18 * k)], fill=(255, 255, 255), width=k)
        sd.polygon([(fx, fy - 18 * k), (fx + 9 * k, fy - 15 * k), (fx, fy - 12 * k)], fill=(230, 30, 30))

    def corner(d, cx, cy, k):
        _pine(d, cx, cy + 8 * k, 18 * k, 7 * k, fill=(40, 110, 55), edge=(15, 45, 22))
    return _card(size, (150, 100, 55), (90, 55, 25), (60, 40, 20), scene, corner)


ICON_ART = {1: lambda size: pasadena_icon(size), 2: battleground_icon, 3: timbercreek_icon}
CARD_ART = {0: lambda size: card_image(size), 1: lambda size: pasadena_card(size), 2: battleground_card,
            3: timbercreek_card}


def card_file(clean_files, k=0):
    """A texture file like A/X/K holding course k's card picture, packed the same way."""
    import os
    import camelot_lz as lz
    import numpy as np
    import shyguy
    import textures as tx
    raw = open(os.path.join(clean_files, *CARD_TEMPLATE.split("/")), "rb").read()
    blob = bytearray(tx.load_bytes(raw))
    ho, w, h, f, data, lod = tx.headers(blob, 0)[0]
    if (w, h, f) != (130, 130, 14):
        raise SystemExit(f"{CARD_TEMPLATE} isn't the 130x130 CMPR card")
    pic = CARD_ART[k](130)
    pic = np.pad(pic, ((0, 6), (0, 6), (0, 0)), mode="edge")   # CMPR tiles are 8x8
    enc = shyguy.cmpr(pic.astype(np.float64))
    blob[data:data + len(enc)] = enc
    return lz.pack(raw[0], bytes(blob)) if raw[0] in (1, 2) and raw[:4] != b"\x00\x20\xaf\x30" else bytes(blob)
