"""v11: an 8th course, Pebble Beach's layout (course code 8, menu index 7); v21: a 9th, Pasadena Municipal Golf
Course in Pasadena, Texas (course code 9, menu index 8).

The game ships course codes 8 and 9 unused (cut 3-hole sets no menu reaches), and every per-course table already has
entries for them that fall back to Lakitu Valley, so the new courses take those codes. Their holes get new hole IDs,
FIRST_ID + 18 x course + hole: 1101-1118 Pebble Beach, 1119-1136 Pasadena (nothing special-cases them). Which tables
and hooks, with addresses (golf = C/L/V, menu = B/U/C, both loaded at 0x80400000; see dev/RE-NOTES.md "Courses"):

  - Hole info (par, yards, hole order): the game's 141-entry table can't grow (golf 0x804CCD60, menu copy
    0x80444E60), so our entries live in cave 11 and the lookups check them first: by ID (golf FUN_80406f90,
    menu FUN_8040094c) and by course + hole (golf FUN_80407048, menu FUN_80400a04).
  - Hole files (model, collision, flyover camera): the resolver FUN_80443e14 searches the file table by ID right
    after asking FUN_80407048 for it (0x80443E68); for our IDs a stub (cave 15, v21) fills the practice row's unused
    last slot (row 8, col 17, 0x804DE338) and points the round at it.
  - Course select (menu FUN_80413910): its list holds 7 entries of 0x2C at 0x8044BC40 with live screen state right
    after it, so the list moves to cave 12 (7 + ours; every lis 0x8045 / addi -0x43C0 pair that addresses it is
    repointed) and a hook where every mode's list ends (0x804140B0) appends ours in Stroke Play, Match Play (not
    Character Match), Skins and Practice. Those modes write no per-course records except the hole-in-one mask.
  - Preview movie: past index 6 the game plays the word at 0x8041445C's file (A/T/C, Lakitu Valley's); a stub plays
    Blooper Bay's (A/T/F) for Pebble Beach and Lakitu Valley's for Pasadena.
  - Music (main.dol FUN_80011a94, table per situation x course 1-7): Pebble Beach plays Blooper Bay's songs,
    Pasadena Lakitu Valley's.
  - Saves: the hole-in-one mask store (golf 0x804682F4) is skipped on our courses, whose index would wrap onto
    Lakitu Valley's mask.
  - Name: six places add the course name's message base (0xA8 + index: 0xAF "Shot Practice", 0xB0 "Approach
    Practice" for ours); each now goes through a stub that swaps those for the course's own message ("msg"), which
    build_mod.py's message hook answers.
  - Sky: the hole loader's sky choice sends Pebble Beach to Blooper Bay's sea sky; Pasadena gets Blooper Bay's sky
    dome alone, with no backdrop (as Congo Canopy has none), so its own skyline of refineries makes the horizon
    (Lakitu Valley's backdrop, the default, has big mountains; Blooper Bay's is a sea in front of the far land).
  - Icon: the course select shows texture <index> of B/W/R: 7 (the star medallion) is redrawn as Pebble Beach's,
    and v21 appends texture 8 for Pasadena.
  - Emblem and HUD card: files of our own per course (E/S/B and E/S/A, F/S/B and F/S/A).
  - Auto-aim (v12): another hole's fairway, fringe and green are no target (AIM_SCORE, a stub in cave 16 since v21).
  - Distance (v17): every golfer's drive is DRIVE_BONUS yards longer on our courses (the clubs scale with it), as
    the real holes are long for the game's golfers (REACH_HOOK, a stub in cave 13). v18: 50 yards, none for Tony
    (golfer 17, 350 already: the longest driver without it), and a Star version drives as its normal self (Andrew:
    "star should just be ignored on pebble beach and only the +50 buff is used": STAR_ROW_HOOK reads the normal
    row of the drive table). v21: Pasadena's drives are 40 yards longer, again not Tony's (Andrew: "make it +20
    except for Tony", then "Make the buff +40 yards"), and its Star versions drive as their normal selves too ("star power should also be ignored on
    Pasadena").
The holes themselves (models, collision, flyover cameras) come from dev/course (holegen.py, coursejson.py).
"""
import struct

import ppc

CODE = 8                    # our first course code (menu index 7); the next is 9
FIRST_ID = 1101             # hole IDs FIRST_ID + HOLES x course + hole
HOLES = 18
COURSES = (                 # in code order: name, message id for it, music column (a course code), preview movie
    {"name": "Pebble Beach", "msg": 0x7FF0, "music": 4, "preview": 0x3E6, "sky": "blooper",     # (file ID / 2),
     "card": "E/S/A", "emblem": "E/S/B", "icon": 7, "bonus": 50.0, "star_normal": True},        # card, emblem and
    {"name": "Pasadena Municipal", "msg": 0x7FEF, "music": 1, "preview": 0x3E0, "sky": "dome",  # icon texture; sky:
     "card": "F/S/A", "emblem": "F/S/B", "icon": 8, "bonus": 40.0, "star_normal": True},       # Blooper Bay's sky
                            # and sea backdrop, or its sky dome alone;
)                           # bonus: yards on every drive but Tony's; star_normal: Star versions drive as their normal

CAVE11 = 0x80069F4C         # dead (find_dead_code.py): hole info, the golf lookups
CAVE11_SIZE = 560
CAVE11_FIRST = 0x9421FFA8
CAVE12 = 0x8006A834         # dead: the course list (7 + ours x 0x2C) and the menu's info lookup
CAVE12_SIZE = 464
CAVE12_FIRST = 0x9421FFE8
CAVE13 = 0x80084B2C         # dead: list append, music, sky, reach, Star row, hole-in-one guard
CAVE13_SIZE = 464
CAVE13_FIRST = 0x9421FFD0
CAVE15 = 0x80073ACC         # dead (v21): the hole files and the resolver
CAVE15_SIZE = 344
CAVE15_FIRST = 0x9421FFD0
CAVE16 = 0x8007C758         # dead (v21): the menu's ID lookup, cards, auto-aim score, the preview, the names
CAVE16_SIZE = 304
CAVE16_FIRST = 0x9421FFD0

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
DRIVE_BONUS = COURSES[0]["bonus"]   # Pebble Beach's (v17 35); each course's is in COURSES
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


def info_table(courses):
    """courses: [[(yards, back yards, par)] in hole order] -> 18 x 12 bytes per course like the game's hole info."""
    out = b""
    for k, holes in enumerate(courses):
        for n, (yards, back, par) in enumerate(holes):
            out += struct.pack(">IhhBBBB", FIRST_ID + HOLES * k + n, yards, back, par, CODE + k, n + 1, 0)
    return out


def file_table(files):
    """files: [(model id, collision id, flyover id)] game file IDs (odd = packed) -> 6 bytes per hole."""
    return b"".join(struct.pack(">3H", *f) for f in files)


def id_lookup(a, name, count, game):
    """FUN_80407048 / FUN_80400a04 (course, hole0) -> hole ID: ours for courses CODE .. CODE + count - 1."""
    a.label(name)
    a(ppc.addi(0, 3, -CODE), cmplwi(0, count - 1))
    a.br("bgt", name + "_game")
    a(cmplwi(4, HOLES - 1))
    a.br("bgt", name + "_game")
    a(ppc.mulli(0, 0, HOLES), ppc.add(3, 4, 0), ppc.addi(3, 3, FIRST_ID), ppc.BLR)
    a.label(name + "_game")
    a(MR_R8_R3)
    a.b(game + 4)


def ours(a, reg, count, scratch=12):
    """cr0 "gt" unless the course code in `reg` is one of ours (clobbers `scratch`)."""
    a(ppc.addi(scratch, reg, -CODE), cmplwi(scratch, count - 1))


def cave11_code(courses):
    a = ppc.Asm(CAVE11)
    a.label("info")
    _data(a, info_table(courses))

    # FUN_80406f90(id) -> hole info entry: ours first
    a.label("info_golf")
    a(ppc.addi(0, 3, -FIRST_ID), cmplwi(0, HOLES * len(courses) - 1))
    a.br("bgt", "info_golf_game")
    a(ppc.mulli(0, 0, 12))
    a.la(3, "info")
    a(ppc.add(3, 3, 0), ppc.BLR)
    a.label("info_golf_game")
    a(LI_R8_0)
    a.b(INFO_BY_ID["golf"] + 4)
    id_lookup(a, "id_golf", len(courses), ID_BY_HOLE["golf"])
    return _done(a, "cave 11", CAVE11_SIZE)


def cave15_code(files):
    a = ppc.Asm(CAVE15)
    a.label("files")
    _data(a, file_table(files))

    # FUN_80443e14 after the ID lookup (r3 = ID): our holes go in the spare slot of the file table
    a.label("resolve")
    a(ppc.addi(0, 3, -FIRST_ID), cmplwi(0, len(files) - 1))
    a.br("bgt", "resolve_game")
    a(ppc.mulli(0, 0, 6))
    a.la(9, "files")
    a(ppc.add(9, 9, 0))
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
    return _done(a, "cave 15", CAVE15_SIZE)


def cave12_code(count):
    a = ppc.Asm(CAVE12)
    a.label("list")
    a(*([0] * ((7 + count) * LIST_ENTRY // 4)))

    a.label("info_menu")       # the menu's copy of the info lookup (its own table base, same entries)
    a(ppc.addi(0, 3, -FIRST_ID), cmplwi(0, HOLES * count - 1))
    a.br("bgt", "info_menu_game")
    a(ppc.mulli(0, 0, 12))
    hi, lo = ppc.hi_lo(CAVE11)   # "info" is the start of cave 11
    a(ppc.lis(3, hi), ppc.addi(3, 3, lo), ppc.add(3, 3, 0), ppc.BLR)
    a.label("info_menu_game")
    a(LI_R8_0)
    a.b(INFO_BY_ID["menu"] + 4)
    return _done(a, "cave 12", CAVE12_SIZE)


def cave13_code(list_addr, count):
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
    for k in range(count):
        hi, lo = ppc.hi_lo(LIST_COUNT)
        a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), cmplwi(0, 6 + count))   # room left?
        a.br("bgt", "list_append_done")
        a(ppc.mulli(3, 0, LIST_ENTRY))
        hi, lo = ppc.hi_lo(list_addr)
        a(ppc.lis(4, hi), ppc.addi(4, 4, lo), ppc.add(3, 3, 4))
        a(ppc.li(4, CODE - 1 + k), ppc.li(5, 0), ppc.li(6, 0))
        a.bl(LIST_FILL)
        hi, lo = ppc.hi_lo(LIST_COUNT)
        a(ppc.lis(12, hi), ppc.lwz(11, lo, 12), ppc.addi(11, 11, 1), ppc.stw(11, lo, 12))   # (addi rD,r0,n is li)
    a.label("list_append_done")
    a(LIST_END_WORD)
    a.b(LIST_END + 4)

    a.label("music")            # r4 = course code: ours play another course's songs
    for k in range(count):
        a(ppc.cmpwi(4, CODE + k))
        a.br("bne", f"music_{k}")
        a(ppc.li(4, COURSES[k]["music"]))
        a.br("b", "music_game")
        a.label(f"music_{k}")
    a.label("music_game")
    a(MUSIC_FIRST)
    a.b(MUSIC + 4)

    a.label("sky")             # r0 = the hole's course: Blooper Bay's sea sky, or its dome alone (r30 = the loader)
    for k in range(count):
        if COURSES[k]["sky"]:
            a(ppc.cmpwi(0, CODE + k))
            a.br("beq", "sky_" + COURSES[k]["sky"])
    a(SKY_TEST_WORD)
    a.br("beq", "sky_blooper")
    a.b(SKY_DEFAULT)
    a.label("sky_blooper")
    a.b(SKY_BLOOPER)
    if any(COURSES[k]["sky"] == "dome" for k in range(count)):
        a.label("sky_dome")
        a(ppc.li(3, BLOOPER_DOME))
        a.bl(SKY_LOAD)
        a(ppc.stw(3, SKY_DOME, 30), ppc.li(3, 0), ppc.stw(3, SKY_BACKDROP, 30))
        a.b(SKY_DONE)

    a.label("reach")           # every golfer drives the course's bonus farther here (f1 = drive, r31 = player)
    hi, lo = ppc.hi_lo(COURSE_NOW)
    a(ppc.lis(12, hi), ppc.lbz(12, lo, 12))
    ours(a, 12, count)
    a.br("bgt", "reach_game")
    a(ppc.lbz(11, 0x51EF, 31), ppc.cmpwi(11, NO_BONUS_GOLFER))
    a.br("beq", "reach_game")
    a(ppc.slwi(12, 12, 2))     # (r3, r4 are the call's; r11, r12 and f0 are free at a call)
    a.la(11, "drive_bonus")
    a(ppc.add(11, 11, 12), ppc.lfs(0, 0, 11), ppc.fadds(1, 1, 0))
    a.label("reach_game")
    a.b(REACH)
    a.label("drive_bonus")
    for k in range(count):
        a.float(f"drive_bonus_{k}", COURSES[k]["bonus"])

    a.label("star_row")        # a Star version's drive is its normal one on the "star_normal" courses (Pebble Beach)
    hi, lo = ppc.hi_lo(COURSE_NOW)     # (r29 = row x 28, r9 = table, r31 = player)
    a(ppc.lis(12, hi), ppc.lbz(12, lo, 12))
    for k in range(count):
        if COURSES[k]["star_normal"]:
            a(ppc.cmpwi(12, CODE + k))
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
    ours(a, 12, count)
    a.br("ble", "ace_skip")
    a(*ACE_WORDS)
    a.label("ace_skip")
    a.b(ACE_DONE)
    return _done(a, "cave 13", CAVE13_SIZE)


def cave16_code(count):
    a = ppc.Asm(CAVE16)
    id_lookup(a, "id_menu", count, ID_BY_HOLE["menu"])

    for k in range(count):      # the HUD card switch's case for our courses: our own card files
        a.label(f"card_{k}")
        a(ppc.li(4, file_id(COURSES[k]["card"])))
        a.b(CARD_LOAD)

    a.label("aim_score")       # the auto-aim's landing classes: another hole's ground scores 79, not a target
    a(ppc.lhz(0, -0xC, 27), ppc.andi_(0, 0, OTHER_HOLE_ATTR))   # r27 = the next triangle's attribute
    a.br("beq", "aim_score_cmp")
    a(ppc.li(3, AIM_SCORE_MIN - 1))
    a.label("aim_score_cmp")
    a(AIM_SCORE_WORD, ppc.BLR)

    a.label("preview")         # (bl from PREVIEW_DEFAULT) r0 = course index past 6: r28 = the preview movie
    a(ppc.li(28, PREVIEW_WORD & 0xFFFF))
    for k in range(count):
        a(ppc.cmpwi(0, CODE - 1 + k))
        a.br("bne", f"preview_{k}")
        a(ppc.li(28, COURSES[k]["preview"]), ppc.BLR)
        a.label(f"preview_{k}")
    a(ppc.BLR)

    # the name message: ours where the game would show 0xAF / 0xB0 for our courses (r4, r0 or r9 holds it)
    for label, add_word, reg in (("name", NAME_ADD, 4), ("name_r0", NAME_ADD_R0, 0), ("name_r9", NAME_ADD_R9, 9)):
        a.label(label)
        a(add_word)
        for k in range(count):
            a(ppc.cmpwi(reg, NAME_OLD + k))
            a.br("bne", f"{label}_{k}")
            a(ppc.li(reg, COURSES[k]["msg"]), ppc.BLR)
            a.label(f"{label}_{k}")
        a(ppc.BLR)
    for k in range(count):
        a.label(f"name_text_{k}")
        _data(a, b"\x093\x092\x074" + COURSES[k]["name"].encode("ascii") + b"\0")   # styles 3 and 2, colour 4,
    return _done(a, "cave 16", CAVE16_SIZE)                                         # as the game names courses


def caves(courses):
    """courses: [(holes, files)] in code order -> [(address, expected first word, code)], labels"""
    holes = [h for h, f in courses]
    files = [x for h, f in courses for x in f]
    count = len(courses)
    c11, l11 = cave11_code(holes)
    c12, l12 = cave12_code(count)
    c13, l13 = cave13_code(l12["list"], count)
    c15, l15 = cave15_code(files)
    c16, l16 = cave16_code(count)
    labels = {**l11, **l12, **l13, **l15, **l16, "_count": count,
              "_sizes": {"11": len(c11), "12": len(c12), "13": len(c13), "15": len(c15), "16": len(c16)}}
    return [(CAVE11, CAVE11_FIRST, c11), (CAVE12, CAVE12_FIRST, c12), (CAVE13, CAVE13_FIRST, c13),
            (CAVE15, CAVE15_FIRST, c15), (CAVE16, CAVE16_FIRST, c16)], labels


def texts(labels):
    """[(message id, string address)] for build_mod.py's message hook."""
    return [(COURSES[k]["msg"], labels[f"name_text_{k}"]) for k in range(labels["_count"])]


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
        for k in range(count):
            entry = CARD_TABLE + 4 * (CODE + k)
            out.append((entry, (labels[f"card_{k}"] - CARD_TABLE) & 0xFFFFFFFF, word(entry)))
            entry = EMBLEM_TABLE + 4 * (CODE + k)
            out.append((entry, file_id(COURSES[k]["emblem"]), EMBLEM_OLD[k]))
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
        out.append((NAME_SITES["menu"], ppc.bl(NAME_SITES["menu"], labels["name"]), NAME_ADD))
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
    """B/W/R with texture 7 replaced by Pebble Beach's icon (same size and format), and with two courses a texture
    8 appended: Pasadena's."""
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
        new = bytearray(tx.level_size(68, 68, 5))
        tx.put_rgb5a3(new, 0, 68, 0, 0, pasadena_icon(68))
        blob = teams.append_textures(bytes(blob), [(bytes(blob[h0[0]:h0[0] + 0x24]), bytes(new))])
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
    pic = icon_image(108) if k == 0 else np.pad(pasadena_icon(104), ((2, 2), (2, 2), (0, 0)))
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
    pic = card_image(130) if k == 0 else pasadena_card(130)
    pic = np.pad(pic, ((0, 6), (0, 6), (0, 0)), mode="edge")   # CMPR tiles are 8x8
    enc = shyguy.cmpr(pic.astype(np.float64))
    blob[data:data + len(enc)] = enc
    return lz.pack(raw[0], bytes(blob)) if raw[0] in (1, 2) and raw[:4] != b"\x00\x20\xaf\x30" else bytes(blob)
