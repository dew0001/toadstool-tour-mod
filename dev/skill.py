"""A harder game (v25, Andrew 2026-10-30: "i want to make the game more skilled to play so first thought is get rid of
the landing grid only give a slope grid on the green, knowing exactly where a ball is going to land is too easy so
im thinking increase the impact mishit percentage a bit"; then of the ideas offered "i like all the ideas except for
the last 3, also keep the auto just make it miss sometimes").

  - The slope grid shows only while putting (the putter is out); full shots and chips get none.
  - Impact windows about a quarter narrower for every golfer but Tony (his are 3 and 1 frames already).
  - A press inside the window but off the mark bends and shortens the shot more (BEND x the game's amount).
  - The auto swing (A at the power press) misses sometimes (AUTO_MISS of its shots land just outside the window).
  - Bad lies (rough, bunkers and worse: the lie's spread of 3% or more) spread the power half as much again.

The game side (RE-NOTES "Skill (v25)"):
  - The grid: the player draw (golf FUN_80425d18's caller) calls FUN_80448b2c(0x80502684) unless the debug flag 0x26
    is set or the putter is out with Z held (r30 = 1 skips it). GRID_BRANCH, the `bne` taken when the club isn't
    the putter, now goes to the `li r30,1`.
  - The impact window, FUN_804169d0(lie, setup): the zone Z is 2 x entry - 1 (`addi r3,r9,-1` at ZONE_SET); a hit
    is |impact error| <= Z, so 2Z + 1 frames. zone_note (on `lwz r3,0x25C(r29)` at ZONE_NOTE, the player for the
    impact stat) keeps the golfer code; zone_cut makes Z (3Z + 2) / 4 unless the golfer is Tony: 7 -> 5, 9 -> 7,
    5 -> 4, 3 -> 2 (15 -> 11, 19 -> 15, 11 -> 9, 7 -> 5 frames).
  - The bend inside the window, the shot builder FUN_804c6668: f = |error| / Z x (0.22 - 0.02 x control)
    (`fmuls f31,f31,f13` at BEND_MUL); f scales the launch angle (+10 degrees at 1), speed (x 1 - f/2 early,
    1 - 0.3 f late), side spin and start line (5 degrees at 1). A press outside the window is a full miss (f = 1:
    half the speed when early). bend multiplies f by BEND.
  - The auto swing: in view 0xC the meter tick FUN_8046e440 sets the impact error every frame to the game's own
    random -2..2 (`stw r29,8(r31)` at AUTO_STORE, r31 = the meter block 0x80523CA4); the last frame's counts.
    auto_miss keeps it inside the zone, and with chance AUTO_MISS puts it just outside (Z + 1, early or late).
  - The lie's spread (setup +0x238, % of power, drawn at the power press as +-spread) comes from the lie classes'
    shared method +0x28, FUN_80416cd4: a byte per lie row and club group. spread (at its exit, `lwz r0,28(r1)` at
    SPREAD_EXIT, r3 = the byte, r31 = the setup) makes 3 or more half as much again, putter aside.
"""
import ppc

CAVE = (0x8005D624, 280, 0x7C0802A6)   # dead FUN_8005d624 (find_dead_code.py: DEAD, 2026-10-30): (address, size, first word)
GRID_BRANCH, GRID_BRANCH_WORD = 0x80425FB4, 0x40A20018   # golf: bne 0x80425FCC (not the putter) -> 0x80425FC8
ZONE_NOTE, ZONE_NOTE_WORD = 0x80416A7C, 0x807D025C       # golf: lwz r3,0x25C(r29)
ZONE_SET, ZONE_SET_WORD = 0x80416AB4, 0x3869FFFF         # golf: addi r3,r9,-1
BEND_MUL, BEND_MUL_WORD = 0x804C6E4C, 0xEFFF0372         # golf: fmuls f31,f31,f13
AUTO_STORE, AUTO_STORE_WORD = 0x8046E534, 0x93BF0008     # golf: stw r29,8(r31)
SPREAD_EXIT, SPREAD_EXIT_WORD = 0x80416D90, 0x8001001C   # golf: lwz r0,28(r1)
RANDOM = 0x8001AA54                 # main.dol: f1 = a random number in [0, 1)
GOLFER_CODE = 0x51EF                # player record: the golfer code
CLUB, PUTTER = 0x1D4, 13            # setup: the club
SETUP_PLAYER = 0x25C
METER_ZONE = 0xC                    # meter block +0xC = 0x80523CB0, the zone in use
TONY = 17

BEND = 1.5          # x the game's bend inside the window
AUTO_MISS = 0.10    # share of auto swings that miss
SPREAD_FROM = 3     # lies with a spread (%) of at least this ...
# ... get half as much again (x 1.5, rounded down)


def neg(rd, ra): return 0x7C0000D0 | rd << 21 | ra << 16
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

    # Replaces `stw r29,8(r31)` at AUTO_STORE (r29 = the game's random error -2..2, r31 = the meter block): inside
    # the zone, or with chance AUTO_MISS just outside it. Like the game's own call just before, the RNG call may
    # take any volatile register: only r29 and r31 live on.
    a.label("auto_miss")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1))
    a.bl(RANDOM)
    a(ppc.lwz(9, METER_ZONE, 31), ppc.cmpw(29, 9))
    a.br("ble", "auto_low")
    a(ppc.mr(29, 9))
    a.label("auto_low")
    a(neg(10, 9), ppc.cmpw(29, 10))
    a.br("bge", "auto_roll")
    a(ppc.mr(29, 10))
    a.label("auto_roll")
    a.la(11, "auto_chance")
    a(ppc.lfs(0, 0, 11), ppc.fcmpu(1, 0))
    a.br("bge", "auto_store")
    a(ppc.addi(29, 9, 1), ppc.lfs(0, 4, 11), ppc.fcmpu(1, 0))
    a.br("bge", "auto_store")
    a(neg(29, 29))
    a.label("auto_store")
    a(ppc.stw(29, 8, 31))
    a(ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)
    a.float("auto_chance", AUTO_MISS)
    a.float("auto_early", AUTO_MISS / 2)
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
    return [(GRID_BRANCH, GRID_BRANCH_WORD - 4, GRID_BRANCH_WORD),
            (ZONE_NOTE, ppc.bl(ZONE_NOTE, labels["zone_note"]), ZONE_NOTE_WORD),
            (ZONE_SET, ppc.bl(ZONE_SET, labels["zone_cut"]), ZONE_SET_WORD),
            (BEND_MUL, ppc.bl(BEND_MUL, labels["bend"]), BEND_MUL_WORD),
            (AUTO_STORE, ppc.bl(AUTO_STORE, labels["auto_miss"]), AUTO_STORE_WORD),
            (SPREAD_EXIT, ppc.bl(SPREAD_EXIT, labels["spread"]), SPREAD_EXIT_WORD)]
