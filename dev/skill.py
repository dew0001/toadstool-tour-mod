"""A harder game (v25, Andrew 2026-10-30: "i want to make the game more skilled to play so first thought is get rid of
the landing grid only give a slope grid on the green, knowing exactly where a ball is going to land is too easy so
im thinking increase the impact mishit percentage a bit"; then of the ideas offered "i like all the ideas except for
the last 3, also keep the auto just make it miss sometimes"). v26 (Andrew: "the green grid should show up on
approaches chips etc. like it should always be there when zooming if its in view, revert that auto swing misses
sometimes change").

  - The slope grid covers the green on every shot (the game's green-view grid round the pin), never the landing spot;
    putts keep the game's putt grid.
  - Impact windows about a quarter narrower for every golfer but Tony (his are 3 and 1 frames already).
  - A press inside the window but off the mark bends and shortens the shot more (BEND x the game's amount).
  - Bad lies (rough, bunkers and worse: the lie's spread of 3% or more) spread the power half as much again.
  - The auto swing is the game's own again (v25 made 10% of them land just outside the window; v26 dropped it).

The game side (RE-NOTES "Skill (v25)"):
  - The grid: the aim camera FUN_80410838 (r31 = the setup all through) builds it with FUN_80448120(grid, preview
    ball), round the preview's landing spot or the putt, and in view 9 (the green view) with FUN_8044844c(pin height,
    grid, matrix, 20, 20) round the pin, a 192 ft square. pin_grid (a `b` on FUN_80448120's first instruction,
    GRID_BUILD) builds the green view's grid instead unless the putter is out. The player draw draws it as the game
    does (v25 skipped the draw but for the putter, at 0x80425FB4).
  - The impact window, FUN_804169d0(lie, setup): the zone Z is 2 x entry - 1 (`addi r3,r9,-1` at ZONE_SET); a hit
    is |impact error| <= Z, so 2Z + 1 frames. zone_note (on `lwz r3,0x25C(r29)` at ZONE_NOTE, the player for the
    impact stat) keeps the golfer code; zone_cut makes Z (3Z + 2) / 4 unless the golfer is Tony: 7 -> 5, 9 -> 7,
    5 -> 4, 3 -> 2 (15 -> 11, 19 -> 15, 11 -> 9, 7 -> 5 frames).
  - The bend inside the window, the shot builder FUN_804c6668: f = |error| / Z x (0.22 - 0.02 x control)
    (`fmuls f31,f31,f13` at BEND_MUL); f scales the launch angle (+10 degrees at 1), speed (x 1 - f/2 early,
    1 - 0.3 f late), side spin and start line (5 degrees at 1). A press outside the window is a full miss (f = 1:
    half the speed when early). bend multiplies f by BEND.
  - The auto swing's error is the game's random -2..2 (the meter tick, `stw r29,8(r31)` at 0x8046E534): with the
    narrower zones Z is 2 or more wherever the game's was 3 or more, so it still never leaves the window there.
  - The lie's spread (setup +0x238, % of power, drawn at the power press as +-spread) comes from the lie classes'
    shared method +0x28, FUN_80416cd4: a byte per lie row and club group. spread (at its exit, `lwz r0,28(r1)` at
    SPREAD_EXIT, r3 = the byte, r31 = the setup) makes 3 or more half as much again, putter aside.
"""
import ppc

CAVE = (0x8005D624, 280, 0x7C0802A6)   # dead FUN_8005d624 (find_dead_code.py: DEAD, 2026-10-30): (address, size, first word)
GRID_BUILD, GRID_BUILD_WORD = 0x80448120, 0x9421FF28     # golf: FUN_80448120's stwu r1,-216(r1)
ZONE_NOTE, ZONE_NOTE_WORD = 0x80416A7C, 0x807D025C       # golf: lwz r3,0x25C(r29)
ZONE_SET, ZONE_SET_WORD = 0x80416AB4, 0x3869FFFF         # golf: addi r3,r9,-1
BEND_MUL, BEND_MUL_WORD = 0x804C6E4C, 0xEFFF0372         # golf: fmuls f31,f31,f13
SPREAD_EXIT, SPREAD_EXIT_WORD = 0x80416D90, 0x8001001C   # golf: lwz r0,28(r1)
MTX_IDENTITY = 0x8003C354           # main.dol: a 3x4 matrix made the identity
GRID_MAKE = 0x8044844C              # golf: (f1 height, r3 grid, r4 matrix, r5 columns, r6 rows)
PIN_HI, PIN_LO = 0x804E, 0x6864     # golf: the pin x, y, z
GREEN_HALF = 0x804DAD5C - 0x804E0000   # golf: 96.0, the green view's grid half-width (ft)
GREEN_POINTS = 20                   # the green view's grid: 20 x 20 points
GOLFER_CODE = 0x51EF                # player record: the golfer code
CLUB, PUTTER = 0x1D4, 13            # setup: the club
SETUP_PLAYER = 0x25C
TONY = 17

BEND = 1.5          # x the game's bend inside the window
SPREAD_FROM = 3     # lies with a spread (%) of at least this ...
# ... get half as much again (x 1.5, rounded down)


def srawi(ra, rs, sh): return 0x7C000670 | rs << 21 | ra << 16 | sh << 11


def code():
    a = ppc.Asm(CAVE[0])
    a.word("golfer", 0)                 # the golfer whose impact window is being worked out

    # Replaces `lwz r3,0x25C(r29)` at ZONE_NOTE (r29 = the setup): the player, and its golfer noted.
    a.label("zone_note")
    a(ppc.lwz(3, SETUP_PLAYER, 29), ppc.lbz(12, GOLFER_CODE, 3))
    a.la(11, "golfer")
    a(ppc.stb(12, 3, 11), ppc.BLR)

    # Replaces `addi r3,r9,-1` at ZONE_SET (r9 = 2 x entry): the zone, about a quarter narrower but for Tony.
    a.label("zone_cut")
    a(ppc.addi(3, 9, -1))
    a.la(11, "golfer")
    a(ppc.lbz(12, 3, 11), ppc.cmpwi(12, TONY), ppc.BEQLR)
    a(ppc.mulli(3, 3, 3), ppc.addi(3, 3, 2), srawi(3, 3, 2), ppc.cmpwi(3, 1))
    a.br("blt", "zone_one")
    a(ppc.BLR)
    a.label("zone_one")
    a(ppc.li(3, 1), ppc.BLR)

    # Replaces `fmuls f31,f31,f13` at BEND_MUL: the bend inside the window, BEND times the game's. f13 and r11 are
    # loaded again before their next use on both paths after it.
    a.label("bend")
    a(ppc.fmuls(31, 31, 13))
    a.la(11, "bend_k")
    a(ppc.lfs(13, 0, 11), ppc.fmuls(31, 31, 13), ppc.BLR)
    a.float("bend_k", BEND)

    # Replaces `lwz r0,28(r1)` at SPREAD_EXIT (r3 = the lie's spread, r31 = the setup): bad lies spread more.
    a.label("spread")
    a(ppc.lwz(0, CLUB, 31), ppc.cmpwi(0, PUTTER))
    a.br("beq", "spread_done")
    a(ppc.cmpwi(3, SPREAD_FROM))
    a.br("blt", "spread_done")
    a(srawi(0, 3, 1), ppc.add(3, 3, 0))
    a.label("spread_done")
    a(ppc.lwz(0, 28, 1), ppc.BLR)

    # A `b` on FUN_80448120's first instruction (GRID_BUILD; r3 = the grid, r4 = the preview ball, r31 = the aim
    # camera's setup): with the putter out the game's grid (round the putt), else the green view's (view 9: a
    # GREEN_POINTS square of points 2 x 96 ft wide round the pin, the identity scaled 96 across, moved to the pin).
    a.label("pin_grid")
    a(ppc.lwz(0, CLUB, 31), ppc.cmpwi(0, PUTTER))
    a.br("bne", "pin_build")
    a(ppc.stwu(1, -216, 1))
    a.b(GRID_BUILD + 4)
    a.label("pin_build")
    a(ppc.stwu(1, -0x40, 1), ppc.mflr(0), ppc.stw(0, 0x44, 1), ppc.stw(3, 0x3C, 1))
    a(ppc.addi(3, 1, 8))
    a.bl(MTX_IDENTITY)
    a(ppc.lis(9, PIN_HI), ppc.lfs(0, GREEN_HALF, 9))
    a(ppc.lfs(4, PIN_LO, 9), ppc.lfs(1, PIN_LO + 4, 9), ppc.lfs(5, PIN_LO + 8, 9))
    a(ppc.stfs(0, 8, 1), ppc.stfs(4, 8 + 0xC, 1), ppc.stfs(1, 8 + 0x1C, 1), ppc.stfs(0, 8 + 0x28, 1),
      ppc.stfs(5, 8 + 0x2C, 1))
    a(ppc.lwz(3, 0x3C, 1), ppc.addi(4, 1, 8), ppc.li(5, GREEN_POINTS), ppc.li(6, GREEN_POINTS))
    a.bl(GRID_MAKE)
    a(ppc.lwz(0, 0x44, 1), ppc.mtlr(0), ppc.addi(1, 1, 0x40), ppc.BLR)
    return a


def caves():
    """[(address, first word, bytes)] and the labels."""
    asm = code()
    blob = asm.assemble()
    at, size, first = CAVE
    if len(blob) > size:
        raise SystemExit(f"skill: {len(blob)} bytes; only {size} fit at 0x{at:08X}")
    return [(at, first, blob)], {**asm.labels, "_size": len(blob)}


def overlay_patches(rel, labels, word):
    """[(address, new word, expected word)] for the golf overlay."""
    if rel != "C/L/V":
        return []
    return [(GRID_BUILD, ppc.b(GRID_BUILD, labels["pin_grid"]), GRID_BUILD_WORD),
            (ZONE_NOTE, ppc.bl(ZONE_NOTE, labels["zone_note"]), ZONE_NOTE_WORD),
            (ZONE_SET, ppc.bl(ZONE_SET, labels["zone_cut"]), ZONE_SET_WORD),
            (BEND_MUL, ppc.bl(BEND_MUL, labels["bend"]), BEND_MUL_WORD),
            (SPREAD_EXIT, ppc.bl(SPREAD_EXIT, labels["spread"]), SPREAD_EXIT_WORD)]
