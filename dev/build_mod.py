"""Build the modded Toadstool Tour tree from a clean extracted disc.

Usage: python -I build_mod.py <clean disc dir> <build dir> [--version N] [--no-unlock] [--no-aspect-write] [--keep-id]
                              [--shyguy <folder with Shy Guy.obj and its texture>] [--shyguy-voice <zip of WAV clips>]
The build dir must already hold a copy of the clean tree (robocopy); this script only rewrites
the files it changes, reading every original from <clean disc dir>.

Changes (v1):
  - Widescreen built in (port of the gamemasterplc 16:9 Gecko code, without Gecko):
      * 3D aspect constant 1.218 -> 1.624 (x4/3), and the main camera's aspect re-asserted each frame
      * every 2D ortho projection widened by 4/3 so HUD art keeps its shape at 16:9
      * full-screen 2D layers at six call sites scaled back to full width
  - All courses and characters unlocked (the two Action Replay unlock codes, built in)
  - Own game ID GFTEMD and banner title, so it sits beside the original in Dolphin's list

Changes (v2):
  - Hold A after the hit: the shooter's update runs up to 3 times a frame (same result, faster)
  - Follow camera: cuts to behind and above the ball at launch, then glides after it
  - Putts: aimed (normal view and swing meter), stroked and followed from behind the ball, down the line;
    any other view, camera turn or side view shows the game's camera instead
  - No opening movie (boot or title idle), no shattered-glass transition during the flight

Changes (v3):
  - B on the result screen asks first: a Continue / Watch Replay menu (the game's post-shot menu, with
    "Watch Replay" text supplied through a message-lookup hook); only Watch Replay replays the shot
  - Follow camera: direction of travel and look-at point eased, no flip when the ball rolls back
  - Landing-spot speed capped (full tilt 20 steps a second instead of 60); the mod layout drives it analog
  - Club Slots item reel without "Double the points"
  - HUD at the screen edges: GXSetProjection's 2D x offset is shifted a quarter screen for the HUD pieces in
    PROJ_CALLERS (left or right), and HUD_SPLITS re-anchor mid-function where one function draws both sides

Changes (v4):
  - Power in quarter steps (1 yd with a 240-yd driver): the stick moves a quarter step, the shot builder adds
    it (real shots) or blends two steps' launch speeds (previews), and the power bar label counts it
  - Zoom view rides high over the ground along the aim line and looks down (replaced in v5)
  - See-through golfer while putting (aim to stroke), with a See-Through On/Off row in the pause menu

Changes (v5):
  - Zoom view rebuilt: starts behind the ball looking down the aim line, then rises and moves up the line to
    high behind the landing spot, looking at the landing spot the whole way, gliding from the normal view
    (cave 7, ZOOM_TUNING)
  - Power bar yardage box without the L / R button wings (YARDS_WING_EDITS)

Changes (v6):
  - Yardage box fitted to the number, centred on it, with rounded corners (cave 8, BOX)

Changes (v7, with --shyguy):
  - Shy Guy as a 17th golfer: the select screen's extra page (Down from the grid's bottom row) lists him as golfer 16.
    Cave 9 writes his Game Boy Advance link record into slot 0 whenever the select screen fills that page and hides
    the record's second golfer (the page also draws one card per record instead of two). Golfer 16 gets Koopa
    Troopa's golfer methods apart from its file names (GOLFER16_VTABLE), and shyguy.py builds its files from
    Koopa's with the OBJ in place of his body, so Shy Guy swings like Koopa and keeps his own shape.

Changes (v8, with --shyguy and --shyguy-voice):
  - Shy Guy's own stats (205 yards, high, narrowest impact, best control, strong spin) and voice: golfer 16 keeps
    its own voice methods (VOICE_METHODS), whose voice set gets his clips (swing, nice impact, near the hole, 8
    chirps); the extra page's label says "More" and has no Game Boy pictures.

Patch code lives over dead functions (cave 1-6 below; checked with find_dead_code.py). Low memory at
0x80001800 does NOT work: the code there is gone by the time the game first draws. dev/RE-NOTES.md explains
the game code each hook relies on.
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402
import ppc  # noqa: E402

CAVE = 0x8006EAB4          # dead SDK function (GXDrawTorus-style helper)
CAVE_SIZE = 736
K_4_3 = 0x3FAAAAAB         # 4/3
K_ASPECT = 0x3FCFDF3B      # 1.624 = 1.218 * 4/3
ASPECT_CONST = 0x8015D940  # main.dol constant the camera setup reads (0x3F9BE76D = 1.218)
CAMERA_ASPECT = 0x8026C7F8  # main camera struct (0x8026C7C0) + 0x38
UNLOCK_FLAGS = 0x8022A3CC  # halfwords: players (A3CC) and tours/courses (A3CE)
ORTHO_HOOK = 0x8003E698    # inside C_MTXOrtho: fdivs f10,f9,f8 = 1/(right-left)
GX_SET_PROJECTION = 0x8006FCC0
LI_R4_1 = 0x38800001

DOL_MATRIX_HOOKS = [0x8000FAA8, 0x800255F4]
OVERLAY_MATRIX_HOOKS = {
    "C/L/V": [0x804303F8, 0x8043E2BC],  # golf overlay, loads at 0x80400000
    "B/U/C": [0x804017F0, 0x80401464],  # second overlay, same load address
}
OVERLAY_BASE = 0x80400000
GAME_ID = b"GFTEMD"
VERSION = sys.argv[sys.argv.index("--version") + 1] if "--version" in sys.argv else "1"
BANNER_TITLE = f"Mario Golf: Toadstool Tour (Mod v{VERSION})".encode("ascii")

SHYGUY = sys.argv[sys.argv.index("--shyguy") + 1] if "--shyguy" in sys.argv else None
SHYGUY_VOICE = sys.argv[sys.argv.index("--shyguy-voice") + 1] if "--shyguy-voice" in sys.argv else None
UNLOCK = "--no-unlock" not in sys.argv
ASPECT_WRITE = "--no-aspect-write" not in sys.argv

# ---- v2: hold A to fast-forward the shot, chase cam behind the ball (shots and putts)
CAVE2 = 0x8003E86C          # dead SDK C_MTX44Concat (4x4 matrices; the game only uses 3x4)
CAVE2_SIZE = 1104
PLAYERS = 0x804ECE70        # 4 player records, 0x5204 bytes each
PLAYER_STRIDE = 0x5204
CUR_PLAYER = 0x804E68FB     # byte: index of the player whose shot it is (bit 0x80 = none)
CAMERA_PTR = 0x802D7E64     # current camera: eye xyz at +0, look-at xyz at +0xC
PLAYER_UPDATE = 0x80423BBC  # one player's per-frame update (ball physics, shot camera, animation)
SHOT_CAMERA = 0x80456D1C    # shot camera, called from PLAYER_UPDATE while a shot plays out
HOOK_SHOOTER_UPDATE = 0x80405620  # golf scene: bl PLAYER_UPDATE for the shooter
HOOK_SHOT_CAMERA = 0x80425BB0     # PLAYER_UPDATE: bl SHOT_CAMERA
AIM_CAMERA = 0x80410838     # aim camera (r3 = shot setup), called from PLAYER_UPDATE while aiming
HOOK_AIM_CAMERA = 0x80424AF8      # PLAYER_UPDATE: bl AIM_CAMERA
SETUP_PTR = 0x5168          # player record: shot setup object
SETUP_CLUB = 0x1D4          # shot setup: club index
CLUB_PUTTER = 13
SETUP_VIEW = 0x1C4          # shot setup: aim view (5 normal, 0xB swing meter, 6 down the hole, 7 landing spot, ...)
SETUP_HELD = 0x100          # shot setup: held buttons (halfword)
PAD_Z = 0x10                # Z (the mod's Back button): side view while held
SETUP_ZOOM_IN = 0x12C       # shot setup: C-stick up/down (float; the mod's LT/RT switch views with it)
SETUP_TURN = 0x14C          # shot setup: camera turn from C-stick left/right (radians, springs back to 0)
SETUP_TARGET = 0x1EC        # shot setup: aim point xyz
AIM_BALL = 0x80502734       # golf overlay: ball position the aim camera works from
STATE_SWING, STATE_LAUNCHED = 5, 6  # player +0x24 during the swing / stroke animation
STATE_BALL_MOVING = 7       # player +0x24 while the ball flies/rolls
PAD_A = 0x100
FF_EXTRA_UPDATES = 2        # holding A runs this many extra updates per frame (3x speed)

# No opening movie: FUN_8000de5c plays the logos, then the opening movie (A/T/L) in a loop that runs until a
# button press or 0x2AE4 frames. The title screen reuses it as its idle movie. Skip straight past that loop.
MOVIE_LOOP = 0x8000E120       # loop head: cmpwi r29,0 (movie object made yet?), addi r28,r28,1
MOVIE_LOOP_EXIT = 0x8000E1D8  # after the loop: wait a frame, then `beq cr4` skips stopping a movie that never started

# Camera data block at CAVE2 (offsets from its start); the stub keeps its state here.
D_LAST_STATE, D_MODE, D_DIRX, D_DIRZ, D_PREV = 0x00, 0x04, 0x08, 0x0C, 0x10  # D_PREV: eye xyz, look xyz
D_ZOOM2, D_EPS2, D_TINY, D_HALF, D_THREEHALF, D_SMOOTH = 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C
D_PARAMS = 0x40  # per mode (0 shot, 1 putt, 2 putt aim): back, up, ahead, look-up
D_ONE, D_DIR_SMOOTH, D_LOOK_SMOOTH = 0x70, 0x74, 0x78
CAM_TUNING = {  # distances in game units, which are feet
    "zoom2": 0.01,      # zoom stick squared above this (0.1 of full tilt) = player is zooming: game camera
    "eps2": 0.0025,     # below this squared horizontal speed (ft/frame, ~3 ft/s), keep the last direction
    "smooth": 0.18,     # fraction of the way the camera moves toward its spot each frame
    "look_smooth": 0.35,  # same for the point it looks at (faster, so the ball stays in view)
    "dir_smooth": 0.06,   # same for the direction of travel, so bounces and slope rolls turn it gently
    "shot": (24.0, 12.0, 10.0, 0.0),  # high behind the ball, looking down at it (~19 degrees)
    "putt": (14.0, 5.0, 10.0, 0.0),   # roll: same spot as the putt aim view, so the stroke doesn't cut
    "aim": (14.0, 5.0, 10.0, 0.0),    # putt aim: backed up behind the ball on the line, golfer in view
}

# ---- v3: B asks before replaying the shot, smooth power with the stick, no double points in Club Slots
CAVE3 = 0x8003AE84          # dead SDK OSCheckActiveThreads (debug-only)
CAVE3_SIZE = 1872
ALLOC = 0x8001A670          # heap alloc(size)
MENU_INIT = 0x80483564      # post-shot menu init(menu, type, pad); type 4 = options Continue (0) / Mulligans (4)
MENU_OPTION_2 = 0x54        # post-shot menu: second option's code (its text is message 0x129 + code)
HOOK_MENU_RESULT = 0x8041F41C  # result screen: bl FUN_804840a8 = the open menu's choice (< 0 while open, -2 = none)
CUR_MENU = 0x804ECE30       # the post-shot menu the HUD runs
TRANSITIONS = 0x80222988    # screen-transition manager, FUN_8000f93c(manager, type)
SET_TRANSITION = 0x8000F93C
TRANSITION_MENU = 6         # what the game asks for when it opens a post-shot menu
MSG_LOOKUP = 0x80022CD0     # message id -> string pointer
MSG_LOOKUP_FIRST = 0x7C60C670  # its first instruction: srawi r0,r3,24
OPTION_REPLAY = 7           # option code shown as "Watch Replay" while our prompt is open (normally "Continue")
MSG_OPTION_REPLAY = 0x129 + OPTION_REPLAY
REPLAY_TEXT = b"\x075Watch Replay\x00"  # 0x07 control byte + style digit, like the game's own menu strings
REPLAY_CHECK = 0x8041E8E8   # golf: sets REPLAY_FLAG on a B press from any controller (ball moving or stopped)
REPLAY_CHECK_WORDS = [0x3D208027, 0xA009BC44, 0x70090200, 0x4D820020, 0x38000001, 0x3D208050, 0x900952A8, 0x4E800020]
REPLAY_FLAG = 0x805052A8    # result screen replays the shot while this is set
PLAYER_MENU = 0x51F8        # player record: open post-shot menu
RESULT_TIMER, RESULT_LENGTH = 0x30, 0x34  # player record: the replay is possible while timer < length
STATE_STOPPED = 8
PAD_B = 0x200

# (v3 slowed the landing spot with the rate constant at 0x804DAE88, 16.0 -> 14.0; v4 steps a quarter as far per
# tick instead, so the constant stays the game's 16.0: full tilt is one quarter step a frame.)
CAVE4 = 0x80021C60          # dead printf-style formatter: holds the HUD anchor table (data only)
CAVE4_SIZE = 2200
CAVE4_FIRST = 0x9421FE20
PROJ_STORE_X = 0x8006FCF4  # GXSetProjection, 2D path: stfs f0,0x488(r13) = the projection's x offset (m[0][3])
PROJ_STORE_X_WORD = 0xD00D0488
ANCHOR_CENTER, ANCHOR_LEFT, ANCHOR_RIGHT = 0, 1, 2
ANCHOR_SHIFT = 0.25         # widened 2D content spans x -0.75..0.75 of the screen; this moves it to an edge
PROJ_CALLERS = {            # bl GX_SET_PROJECTION sites in the golf HUD -> anchor (everything else stays centered)
    0x8044A6E4: ANCHOR_LEFT,    # hole icon
    0x80430020: ANCHOR_LEFT,    # club and shot type
    0x80430974: ANCHOR_LEFT,    # "Hole N / PAR N" (and mode counters); the % box later in it is split off right
    0x8042C6DC: ANCHOR_RIGHT,   # wind gauge
    0x8042C954: ANCHOR_RIGHT,   # wind speed
    0x8042E4AC: ANCHOR_RIGHT,   # player panel (face, score)
}
HUD_SPLITS = [              # bl sites inside HUD functions that draw on both sides: (site, anchor, original target)
    (0x80430724, ANCHOR_RIGHT, 0x8042DAB8),   # after the pin tracker: the ball-lie picture (bottom right)
    (0x80431148, ANCHOR_RIGHT, 0x8006982C),   # hole text -> % box (bottom right)
    (0x80431268, ANCHOR_CENTER, 0x80432E20),  # -> flight distance counter (center)
]
GX_PROJ_X, GX_DIRTY, GX_DIRTY_PROJECTION = 0x488, 0x554, 0x800  # r13-relative GX state, as GXSetProjection uses
SLOT_ITEMS = 0x804E1A10     # Club Slots item reel: 32 entries, shuffled; 4 = "Double the points for this hole!"
SLOT_ITEMS_OLD = [0] * 7 + [1] * 7 + [2] * 7 + [3] * 6 + [4] * 5
SLOT_ITEMS_NEW = [0] * 8 + [1] * 8 + [2] * 8 + [3] * 8  # power shot, mulligan, no wind, sweet spot

# No glass-break transition: the shot camera asks the screen-transition manager (main.dol 0x80222988) for
# type 4, a shattered-glass wipe, when it cuts between flight views. Ask for -1 (none) instead, the value
# the game itself uses to cancel a transition.
GLASS_BREAK_SITES = [0x804570D0, 0x8045744C, 0x804574AC, 0x80457718]  # li r4,4 before bl FUN_8000f93c
LI_R4_4, LI_R4_NONE = 0x38800004, 0x3880FFFF

# ---- v4: power in quarter steps, steady zoom camera
# Power is a whole number of swing-meter steps (setup +0x1D0, 1..60; one step per meter frame), so the landing
# spot moved 1/60 of the club's reach per tick (4 yd with a 240-yd driver). The shot builder FUN_804c6668 turns
# the step into launch values; the launch speed comes from a per-step table that FUN_8044cee8 solves (by
# simulating) so carry = reach * step / 60. v4 keeps a quarter step beside the game's step: the stick moves
# quarters, and the builder adds the quarter (real shots) or blends the two neighbouring steps' launch speeds
# (previews), so the landing spot, the distance and the shot all move a quarter step (1 yd) at a time.
CAVE5 = 0x800411B8          # dead FUN_800411b8 (find_dead_code.py: DEAD)
CAVE5_SIZE = 1076
CAVE5_FIRST = 0x7C0802A6
SETUP_AUTO = 0x184          # shot setup: byte, nonzero while the game swings by itself (replays)
SETUP_RANGE = 0x1D0         # shot setup: power in meter steps (the landing spot); the meter's step when swung
SETUP_RANGE_MAX = 0x250     # shot setup: steps in a full meter (60)
SETUP_PLAYER = 0x25C        # shot setup: the player record it belongs to
SETUP_ZOOM = 0x16C          # shot setup: zoom view amount: < 0 overhead, 0..1 rising, > 1 out along the aim line
PLAYER_SETUP = 0x5168       # player record: its shot setup
RANGE_TARGET = 0x80523CBC   # golf: the swing meter's target step (the aimed SETUP_RANGE)
RANGE_STEP_HOOK = 0x80414538  # range adjust (FUN_80412f6c): lbz r0,0x184(r31), just before range += step (r10)
RANGE_STEP_WORD = 0x881F0184
SPREAD_HOOK = 0x804C68E0    # shot builder, real shots: frsp f0,f0 = (float)step, about to be scaled by the spread
SPREAD_WORD = 0xFC000018
TABLE_HOOK = 0x804C6A3C     # shot builder, previews and putts: stfs f0,0x48(r31) = the step's launch speed
TABLE_WORD = 0xD01F0048
SOLVE_STEP = 0x8044CEE8     # (setup, shot) fills the launch-speed table entry for setup's step (cached)
YARDS_HOOK = 0x8046C964     # power bar HUD (FUN_8046bc78): mullw r9,r9,r0 = shown step * club reach (then / 60)
YARDS_WORD = 0x7D2901D6
HUD_SETUP = 0x34            # power bar HUD object: the shot setup it shows
RANGE_MIN = 5               # the game's lowest aimable step
VIEW_ZOOM = 6
# Zoom view: past amount 1 the game flies its camera out along the aim line a few feet over the ground (terrain
# checks every frame), so it bobs over every bump and ends up behind trees and hills. Replaced in v5 (cave 7).
# See-through golfer: while the shooter putts (aim to stroke), their golfer model is drawn see-through. Characters
# are drawn by MODEL_DRAW (model instance in r3; the shooter's is player +PLAYER_GOLFER). Their materials take
# alpha from the channel material colour (TEV alpha = raster alpha x texture alpha, alpha test only drops 0),
# so during that one draw the material colour's alpha is scaled down, blending is forced on and depth writes off;
# afterwards the blend and depth modes the game last asked for are put back.
MODEL_DRAW = 0x800072C8         # draw a model instance (r3) with matrix r4
MODEL_DRAW_FIRST = 0x9421FD08   # stwu r1,-0x2f8(r1)
GX_SET_BLEND = 0x8006E154       # GXSetBlendMode(type, src, dst, op)
GX_SET_BLEND_FIRST = 0x800D0230
GX_SET_MAT_COLOR = 0x8006AF08   # GXSetChanMatColor(channel, &color)
GX_SET_MAT_COLOR_FIRST = 0x28030005
GX_SET_ZMODE = 0x8006E23C       # GXSetZMode(enable, func, update)
GX_SET_ZMODE_FIRST = 0x800D0238
PLAYER_GOLFER = 0x518C          # player record: the golfer's model instance
STATE_AIM = 4
GX_BM_BLEND, GX_BL_SRCALPHA, GX_BL_INVSRCALPHA, GX_LO_SET = 1, 4, 5, 15
GHOST_ALPHA = 0x60              # golfer opacity while see-through, out of 256
GHOST_OFF, GHOST_PUTTS, GHOST_ALWAYS = 0, 1, 2  # ghost_mode values (ALWAYS: any club; for testing)
# Its setting is a row in the in-round pause menu (Start). FUN_80473918 fills the menu's item list (codes at
# PAUSE_LIST, count at menu +0x116, at most 6 rows); row text is message 0x10D + code, the help line 0x118 +
# code; 30 frames after A, the menu runs the cursor item through a jump table. The row reuses code 10 ("Start
# Game Over", which only one training mode lists, and only when that code isn't already there): its icon is a
# real menu icon, and while our row is listed the message hook answers its two messages with ours.
CAVE6 = 0x8003CA40          # dead FUN_8003ca40 (find_dead_code.py: DEAD)
CAVE6_SIZE = 684
CAVE6_FIRST = 0x7C0802A6
PAUSE_LIST = 0x80523F48
PAUSE_COUNT, PAUSE_CURSOR, PAUSE_ROWS, PAUSE_HELP = 0x116, 0x110, 0x20, 0x4  # pause menu: rows' text boxes at +0x20
PAUSE_ROWS_MAX = 6
PAUSE_BUILD = 0x80473918
PAUSE_BUILD_CALLS = [0x80473194, 0x804737EC]
PAUSE_RUN = 0x80476E48      # bl FUN_80019bf8 right before the item jump table (r25 = menu)
PAUSE_RUN_TARGET = 0x80019BF8
PAUSE_RUN_DEFAULT = 0x80477894  # where the jump table goes for codes it doesn't know
SET_TEXT = 0x80024CFC       # (text box, message id, 0, 0x20, mode): show a message in a text box
GHOST_ITEM = 10
MSG_GHOST_ITEM, MSG_GHOST_HELP = 0x10D + GHOST_ITEM, 0x118 + GHOST_ITEM
GHOST_TEXT_ON = b"\x074\x094See-Through: On\x00"
GHOST_TEXT_OFF = b"\x074\x094See-Through: Off\x00"
GHOST_TEXT_HELP = b"\x074\x094See through your golfer\x01while putting.\x00"
# ---- v5: the zoom view goes up the aim line to the landing spot (cave 7)
# The zoom amount (setup +0x16C) grows while the view's stick is held (about 1.15 a second; the first press jumps
# it to about 0.13) and stays when let go. v4 kept the game's path and looked at the ground; v5 builds its own:
# behind the ball looking down the line, rising first, then up the line to high behind the landing spot, looking
# at the landing spot the whole way. The camera eases toward that spot from wherever it was (the normal view on
# the first frame), so the first press doesn't jump.
CAVE7 = 0x800757BC          # dead FUN_800757bc (find_dead_code.py: DEAD)
CAVE7_SIZE = 704
CAVE7_FIRST = 0x9421FF90
ZOOM_TUNING = {             # feet; "share" = fraction of the shot's length, for short shots
    "start_back": 25.0,     # start: this far behind the ball on the aim line ...
    "start_up": 12.0,       # ... and this high above it
    "end_back": 90.0,       # end: this far short of the landing spot (or end_back_share of the shot) ...
    "end_back_share": 0.35,
    "end_up": 75.0,         # ... and this high above it (end_up_share of the shot, at least end_up_min)
    "end_up_share": 0.3,
    "end_up_min": 20.0,
    "full": 1.2,            # zoom amount that reaches the end (about a second of holding); along the line the
                            # camera eases in and out (smoothstep), its height rises early (t * (2 - t))
    "ease": 0.2,            # fraction of the way to its spot the camera moves each frame
}
# Power bar yardage box: the game draws grey L / R button wings either side of it (textures 0x20 / 0x21 of the
# HUD set, quads from x = -w-32..-w and w..w+32). v5 makes both quads zero-wide: a clean box with the number.
YARDS_WING_EDITS = [(0x8046C7B4, 0x3809FFE0, 0x38090000),   # left wing: subi r0,r9,0x20 -> addi r0,r9,0
                    (0x8046C80C, 0x381F0020, 0x381F0000)]   # right wing: addi r0,r31,0x20 -> addi r0,r31,0

# ---- v7: Shy Guy, a 17th golfer (cave 9; only with --shyguy)
# The select screen (FUN_8040aad4) fills its extra page from the 4 Game Boy Advance link records in the save data
# (LINK_RECORDS + 0x284 * slot, two golfers each: golfer 16 + 2 * slot + body; empty when the name at +0x268 is).
# Cave 9 writes Shy Guy's record (shyguy.RECORD) into slot 0 just before that and hides its second golfer after.
CAVE9 = 0x80040CE8          # dead FUN_80040ce8 (find_dead_code.py: DEAD)
CAVE9_SIZE = 600
CAVE9_FIRST = 0x9421FFD0
LINK_RECORDS = 0x80234040   # 4 records of LINK_SIZE
LINK_SIZE = 0x284
LINK_GOLFERS = 0x80445B2C   # the extra page's 8 golfers (record * 2 + which, -1 = none), filled by the loop
GBA_FILL_HOOK = 0x8040AB98  # bl FUN_80410000, just before the fill loop
GBA_FILL_TARGET = 0x80410000
GBA_DONE_HOOK = 0x8040ACC4  # bl FUN_80410140, just after it
GBA_DONE_TARGET = 0x80410140
GBA_ROW_CELLS = 0x80405F8C  # cmpwi r31,1 in FUN_80405b30: the extra page draws 2 cells per link record -> 1
GBA_ROW_CELLS_WORD = 0x2C1F0001
# In rounds each golfer is an object made by FUN_804074a8(code) with a vtable of 47 methods in the golf overlay.
# Golfer 16 (code 0x10, made by FUN_804c7220's default case) gets Koopa Troopa's methods (code 15, FUN_804bd45c;
# same object size and base constructor) except the three that name its files, which shyguy.py builds from Koopa's,
# and the four that play its voice: those start sounds of its own voice set, the one the game loads for golfer 16
# (Koopa's would ask for his, which isn't loaded, so Shy Guy would be silent).
GOLFER16_VTABLE = 0x804CC948
KOOPA_VTABLE = 0x804CA3C8
VTABLE_METHODS = 47
FILE_METHODS = {22: 0x804CCABC, 23: 0x804CCAB0, 24: 0x804CCAC8}   # golfer 16's: C/W/B, C/W/A, C/W/E
VOICE_METHODS = {42: 0x804C7C00,   # ball near the hole (sfx 0xC3)
                 43: 0x804C7AE4,   # swing (0xAF)
                 44: 0x804C7AA8,   # nice impact (0xB1)
                 46: 0x804C7B34}   # chirp 0-7 while someone else lines up (0xBB-0xC2)


def cave9_code(record):
    """Assemble the select screen's link record for Shy Guy. record: offset -> 4 bytes. Returns (bytes, labels)."""
    a = ppc.Asm(CAVE9)
    # Replaces the `bl FUN_80410000` before the fill loop: record 0 is cleared and becomes golfer 16's, then on to
    # FUN_80410000 (r3-r10 untouched, so its arguments pass through).
    a.label("link_record")
    hi, lo = ppc.hi_lo(LINK_RECORDS)
    a(ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.addi(11, 12, LINK_SIZE), ppc.li(0, 0))
    a.label("link_clear")
    a(ppc.stw(0, 0, 12), ppc.addi(12, 12, 4), ppc.cmpw(12, 11))
    a.br("blt", "link_clear")
    a(ppc.lis(12, hi), ppc.addi(12, 12, lo))
    for off, data in sorted(record.items()):
        w = struct.unpack(">I", data)[0]
        a(ppc.lis(11, w >> 16), ppc.ori(11, 11, w & 0xFFFF), ppc.stw(11, off, 12))
    a.b(GBA_FILL_TARGET)
    # Replaces the `bl FUN_80410140` after the fill loop: record 0's second golfer isn't listed.
    a.label("link_hide")
    hi, lo = ppc.hi_lo(LINK_GOLFERS + 4)
    a(ppc.li(0, -1), ppc.lis(12, hi), ppc.stw(0, lo, 12))
    a.b(GBA_DONE_TARGET)
    code = a.assemble()
    if len(code) > CAVE9_SIZE:
        raise SystemExit(f"cave 9 code is {len(code)} bytes; only {CAVE9_SIZE} fit")
    return code, a.labels


# ---- v6: the yardage box fits the number, with rounded corners (cave 8)
# The box is drawn before the number exists: a body quad x -w..w (HUD texture 0x10, u 0.625..0.6875) and 14-px end
# pieces, all y r27 (-26) .. r29 (0). The number is "%3dy" (16-px cells from x -32: digits, then the 'y'), so short
# distances get leading spaces and sit right of centre. For yards (not putts), v6 gives the game's box pieces zero
# height, then just before the digit loop centres the number (half a cell per leading space) and draws a rounded
# box around it as a triangle fan with the box's own texture strip.
CAVE8 = 0x80093938          # dead FUN_80093938 (find_dead_code.py: DEAD)
CAVE8_SIZE = 648
CAVE8_FIRST = 0x9421FFE0
BOX_HIDE_HOOK = 0x8046C608  # li r4,0 before the box body's GXBegin (r1 = HUD frame: +0x18C nonzero = putt)
BOX_HIDE_WORD = 0x38800000
BOX_TEXT_HOOK = 0x8046CA40  # lbz r0,0x1b0(r1): first character of the label, right before the digit loop
BOX_TEXT_WORD = 0x880101B0
HUD_PUTT, HUD_TEXT = 0x18C, 0x1B0  # power bar HUD frame: putt flag, the formatted label
HUD_TEXTURES, DIGIT_TEXTURES = 0x804DFA48, 0x804DFA4C  # pointers to the HUD and digit texture sets
BIND_TEXTURE = 0x8000C900   # (set, index, 0)
GX_BEGIN = 0x8006967C       # (primitive, vertex format, vertices)
GX_SET_TEV_ALPHA_IN = 0x8006DD40
TEV_ALPHA_BOX, TEV_ALPHA_DIGITS = 0x82FF8, 0x8FC8F  # what the game sets for the box and for the digits
GX_TRIANGLEFAN = 0xA0
BOX = {"top": -26, "bottom": 0, "radius": 9, "corner_steps": 3, "pad": 6, "nudge": 1, "u": 0.65625}
# pad: box edge beyond the outer digit cells; nudge: digits right by this much (the 'y' is narrower than its cell)


def normalize_xz(a, x, z, n2):
    """f{x}, f{z} /= sqrt(f{n2}), where f{n2} = x*x + z*z > 0. Uses f6-f9; r7 = data block."""
    a(ppc.frsqrte(6, n2), ppc.lfs(7, D_HALF, 7), ppc.lfs(8, D_THREEHALF, 7))
    for _ in range(2):  # Newton steps: y *= 1.5 - 0.5*x*y*y
        a(ppc.fmuls(9, 6, 6), ppc.fmuls(9, 9, n2), ppc.fmuls(9, 9, 7), ppc.fsubs(9, 8, 9), ppc.fmuls(6, 6, 9))
    a(ppc.fmuls(x, x, 6), ppc.fmuls(z, z, 6))


def place_camera(a, params):
    """f5-f7 = eye, f8-f10 = look-at, from ball f0-f2, unit direction f3/f4 and params at r12+params."""
    a(ppc.lfs(10, params, 12), ppc.lfs(11, params + 4, 12), ppc.lfs(12, params + 8, 12),
      ppc.lfs(13, params + 12, 12))
    a(ppc.fmuls(5, 3, 10), ppc.fsubs(5, 0, 5), ppc.fadds(6, 1, 11), ppc.fmuls(7, 4, 10), ppc.fsubs(7, 2, 7))
    a(ppc.fmuls(8, 3, 12), ppc.fadds(8, 0, 8), ppc.fadds(9, 1, 13), ppc.fmuls(10, 4, 12), ppc.fadds(10, 2, 10))


def cave2_code(aim_place):
    """Assemble the fast-forward and follow-camera stubs (aim_place lives in cave 3). Returns (bytes, labels)."""
    a = ppc.Asm(CAVE2)
    # data block first, so the stubs can use fixed offsets from r7
    for name in ("last_state", "mode", "dirx", "dirz", "ex", "ey", "ez", "tx", "ty", "tz"):
        a.word(name)
    a.float("zoom2", CAM_TUNING["zoom2"])
    a.float("eps2", CAM_TUNING["eps2"])
    a.float("tiny", 1e-12)
    a.float("half", 0.5)
    a.float("threehalf", 1.5)
    a.float("smooth", CAM_TUNING["smooth"])
    for mode in ("shot", "putt", "aim"):
        for i, v in enumerate(CAM_TUNING[mode]):
            a.float(f"{mode}{i}", v)
    a.float("one", 1.0)
    a.float("dir_smooth", CAM_TUNING["dir_smooth"])
    a.float("look_smooth", CAM_TUNING["look_smooth"])
    assert a.here() - CAVE2 == D_LOOK_SMOOTH + 4

    # Fast-forward: replaces `bl PLAYER_UPDATE` for the shooter. r3 = shooter's record.
    a.label("ff")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1), ppc.stw(31, 12, 1), ppc.stw(30, 8, 1))
    a(ppc.mr(31, 3), ppc.li(30, FF_EXTRA_UPDATES))
    a.bl(PLAYER_UPDATE)
    a.label("ff_loop")
    a(ppc.lwz(4, 0x24, 31), ppc.cmpwi(4, STATE_BALL_MOVING))
    a.br("bne", "ff_done")
    a(ppc.lwz(4, 0x4F14, 31), ppc.lhz(4, 0, 4), ppc.andi_(4, 4, PAD_A))  # shooter's pad: held buttons
    a.br("beq", "ff_done")
    a(ppc.mr(3, 31))
    a.bl(PLAYER_UPDATE)
    a(ppc.addi(30, 30, -1), ppc.cmpwi(30, 0))
    a.br("bne", "ff_loop")
    a.label("ff_done")
    a(ppc.lwz(30, 8, 1), ppc.lwz(31, 12, 1), ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    # Chase cam: replaces `bl SHOT_CAMERA`. Runs the game's camera, then while the ball moves puts the
    # camera behind and above it along its (smoothed) direction of travel, eased after a clean cut at launch.
    # During a putt's stroke it holds the putt aim view, instead of the game's face-on stroke view.
    a.label("cam")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1))
    a.bl(SHOT_CAMERA)
    hi, lo = ppc.hi_lo(CUR_PLAYER)
    a(ppc.lis(3, hi), ppc.lbz(4, lo, 3), ppc.mulli(4, 4, PLAYER_STRIDE))
    hi, lo = ppc.hi_lo(PLAYERS)
    a(ppc.lis(5, hi), ppc.addi(5, 5, lo), ppc.add(5, 5, 4))           # r5 = shooter
    a.la(7, "last_state")                                            # r7 = data block
    a(ppc.lwz(6, 0x24, 5), ppc.lwz(8, D_LAST_STATE, 7), ppc.stw(6, D_LAST_STATE, 7),
      ppc.cmpwi(6, STATE_BALL_MOVING))
    a.br("beq", "cam_moving")
    a(ppc.cmpwi(6, STATE_SWING))
    a.br("blt", "cam_done")
    a(ppc.cmpwi(6, STATE_LAUNCHED))
    a.br("bgt", "cam_done")
    a(ppc.lwz(3, SETUP_PTR, 5), ppc.lwz(4, SETUP_CLUB, 3), ppc.cmpwi(4, CLUB_PUTTER))
    a.br("bne", "cam_done")
    a.bl(aim_place)
    a.br("b", "cam_done")
    a.label("cam_moving")
    hi, lo = ppc.hi_lo(CAMERA_PTR)
    a(ppc.lwz(9, 0x1C, 5), ppc.lis(10, hi), ppc.lwz(10, lo, 10))      # r9 = ball, r10 = camera
    a(ppc.cmpwi(8, STATE_BALL_MOVING))
    a.br("beq", "cam_steady")
    # first moving frame: putt if the shooter has the putter out; aim along the game's camera until moving
    a(ppc.lwz(11, SETUP_PTR, 5), ppc.lwz(11, SETUP_CLUB, 11), ppc.cmpwi(11, CLUB_PUTTER), ppc.li(11, 0))
    a.br("bne", "cam_mode")
    a(ppc.li(11, 1))
    a.label("cam_mode")
    a(ppc.stw(11, D_MODE, 7))
    a(ppc.lfs(1, 0xC, 10), ppc.lfs(2, 0x0, 10), ppc.fsubs(1, 1, 2), ppc.stfs(1, D_DIRX, 7),
      ppc.lfs(1, 0x14, 10), ppc.lfs(2, 0x8, 10), ppc.fsubs(1, 1, 2), ppc.stfs(1, D_DIRZ, 7))
    a.label("cam_steady")
    # direction of travel: the horizontal velocity, eased so bounces and slope rolls turn the camera gently.
    # A ball rolling back toward the camera (backspin, slopes) keeps it facing the same way instead of
    # flipping it round; a nearly still ball keeps the last direction.
    a(ppc.lfs(3, 0x50, 9), ppc.lfs(4, 0x58, 9), ppc.fmuls(5, 3, 3), ppc.fmuls(6, 4, 4), ppc.fadds(5, 5, 6),
      ppc.lfs(6, D_EPS2, 7), ppc.fcmpu(5, 6))
    a.br("blt", "cam_keep")
    normalize_xz(a, 3, 4, 5)
    a(ppc.lfs(12, D_ONE, 7), ppc.cmpwi(8, STATE_BALL_MOVING))
    a.br("bne", "cam_turn")  # first moving frame: straight along the launch
    a(ppc.lfs(6, D_DIRX, 7), ppc.lfs(7, D_DIRZ, 7), ppc.fmuls(5, 3, 6), ppc.fmuls(9, 4, 7), ppc.fadds(5, 5, 9),
      ppc.lfs(9, D_TINY, 7), ppc.fcmpu(5, 9))
    a.br("blt", "cam_keep")
    a(ppc.lfs(12, D_DIR_SMOOTH, 7))
    a.label("cam_turn")
    a(ppc.lfs(6, D_DIRX, 7), ppc.fsubs(3, 3, 6), ppc.fmuls(3, 3, 12), ppc.fadds(3, 6, 3),
      ppc.lfs(6, D_DIRZ, 7), ppc.fsubs(4, 4, 6), ppc.fmuls(4, 4, 12), ppc.fadds(4, 6, 4))
    a.br("b", "cam_dir")
    a.label("cam_keep")
    a(ppc.lfs(3, D_DIRX, 7), ppc.lfs(4, D_DIRZ, 7))
    a.label("cam_dir")
    a(ppc.fmuls(5, 3, 3), ppc.fmuls(6, 4, 4), ppc.fadds(5, 5, 6), ppc.lfs(6, D_TINY, 7), ppc.fcmpu(5, 6))
    a.br("blt", "cam_done")
    normalize_xz(a, 3, 4, 5)
    a(ppc.stfs(3, D_DIRX, 7), ppc.stfs(4, D_DIRZ, 7))
    a(ppc.lwz(11, D_MODE, 7), ppc.mulli(11, 11, 16), ppc.add(12, 7, 11))
    a(ppc.lfs(0, 0x9C, 9), ppc.lfs(1, 0xA0, 9), ppc.lfs(2, 0xA4, 9))   # ball position
    place_camera(a, D_PARAMS)
    a(ppc.lfs(12, D_SMOOTH, 7), ppc.lfs(13, D_LOOK_SMOOTH, 7), ppc.cmpwi(8, STATE_BALL_MOVING))
    a.br("beq", "cam_glide")
    a(ppc.lfs(12, D_ONE, 7), ppc.lfs(13, D_ONE, 7))  # first moving frame: cut straight to the follow spot
    a.label("cam_glide")
    for i, f in enumerate((5, 6, 7, 8, 9, 10)):  # glide: prev += (want - prev) * smooth; write the camera
        s = 12 if i < 3 else 13
        a(ppc.lfs(11, D_PREV + 4 * i, 7), ppc.fsubs(f, f, 11), ppc.fmuls(f, f, s), ppc.fadds(f, 11, f),
          ppc.stfs(f, D_PREV + 4 * i, 7), ppc.stfs(f, 4 * i, 10))
    a.label("cam_done")
    a(ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    blob = a.assemble()
    if len(blob) > CAVE2_SIZE:
        raise SystemExit(f"cave 2 code is {len(blob)} bytes; only {CAVE2_SIZE} available")
    return blob, {"ff": a.labels["ff"], "cam": a.labels["cam"]}


def cave5_code():
    """Assemble the quarter-step power and the zoom camera. Returns (bytes, labels)."""
    a = ppc.Asm(CAVE5)
    # quarter-step state: whose aim it is, the club and step it was set at, and the quarter (0..3)
    a.word("fine")
    a.word("fine_club")
    a.word("fine_step_n")
    a.word("fine_quarter")
    for i in range(4):
        a.float(f"quarter{i}", i / 4)
    F_CLUB, F_STEP, F_QUARTER, F_TABLE = 4, 8, 12, 16
    hi_t, lo_t = ppc.hi_lo(RANGE_TARGET)

    # Replaces `lbz r0,0x184(r31)` just before the range adjust adds its step (r10 = -1, 0 or +1; r31 = setup):
    # the step moves a quarter instead. The game's step only moves when the quarters roll over, so r10 becomes
    # 0 or the step. Same aim, club and step as last time = keep the quarter; anything else starts from 0.
    # Putts keep whole steps (they are small already, and their label shows tenths).
    a.label("fine_step")
    a(ppc.stwu(1, -16, 1), ppc.stw(9, 8, 1), ppc.stw(12, 12, 1))
    a(ppc.lbz(0, SETUP_AUTO, 31), ppc.cmpwi(0, 0))
    a.br("bne", "fs_done")                      # the game is swinging by itself
    a(ppc.cmpwi(10, 0))
    a.br("beq", "fs_done")
    a(ppc.lwz(0, SETUP_CLUB, 31), ppc.cmpwi(0, CLUB_PUTTER))
    a.br("beq", "fs_done")
    a.la(9, "fine")
    a(ppc.lwz(11, SETUP_RANGE, 31))
    a(ppc.lwz(12, SETUP_PLAYER, 31), ppc.lwz(0, 0, 9), ppc.cmpw(0, 12))
    a.br("bne", "fs_reset")
    a(ppc.lwz(12, SETUP_CLUB, 31), ppc.lwz(0, F_CLUB, 9), ppc.cmpw(0, 12))
    a.br("bne", "fs_reset")
    a(ppc.lwz(0, F_STEP, 9), ppc.cmpw(0, 11))
    a.br("bne", "fs_reset")
    a(ppc.lwz(12, F_QUARTER, 9))
    a.br("b", "fs_have")
    a.label("fs_reset")
    a(ppc.li(12, 0))
    a.label("fs_have")
    a(ppc.slwi(0, 11, 2), ppc.add(0, 0, 12), ppc.add(0, 0, 10))      # quarters
    a(ppc.cmpwi(0, 4 * RANGE_MIN))
    a.br("bge", "fs_low_ok")
    a(ppc.li(0, 4 * RANGE_MIN))
    a.label("fs_low_ok")
    a(ppc.lwz(12, SETUP_RANGE_MAX, 31), ppc.slwi(12, 12, 2), ppc.cmpw(0, 12))
    a.br("ble", "fs_high_ok")
    a(ppc.mr(0, 12))
    a.label("fs_high_ok")
    a(ppc.andi_(12, 0, 3), ppc.stw(12, F_QUARTER, 9), ppc.srwi(0, 0, 2), ppc.stw(0, F_STEP, 9))
    a(ppc.cmpw(0, 11))
    a.br("bne", "fs_moved")
    a(ppc.li(10, 0))                            # same step, another quarter
    a.label("fs_moved")
    a(ppc.lwz(12, SETUP_PLAYER, 31), ppc.stw(12, 0, 9), ppc.lwz(12, SETUP_CLUB, 31), ppc.stw(12, F_CLUB, 9))
    a.label("fs_done")
    a(ppc.lwz(9, 8, 1), ppc.lwz(12, 12, 1), ppc.addi(1, 1, 16))
    a(ppc.lbz(0, SETUP_AUTO, 31), ppc.BLR)

    def quarter_check(fail, setup_reg, step_reg):
        """Branch to fail unless player r30's aim set a quarter at this club and target, with step_reg below a
        full meter. Leaves r10 = state block and setup_reg = the setup. Uses r0, r12."""
        a.la(10, "fine")
        a(ppc.lwz(12, 0, 10), ppc.cmpw(12, 30))
        a.br("bne", fail)
        a(ppc.lwz(setup_reg, PLAYER_SETUP, 30))
        a(ppc.lwz(12, SETUP_CLUB, setup_reg), ppc.lwz(0, F_CLUB, 10), ppc.cmpw(0, 12))
        a.br("bne", fail)
        a(ppc.lwz(12, SETUP_RANGE_MAX, setup_reg), ppc.cmpw(step_reg, 12))
        a.br("bge", fail)
        a(ppc.lis(12, hi_t), ppc.lwz(12, lo_t, 12), ppc.lwz(0, F_STEP, 10), ppc.cmpw(0, 12))
        a.br("bne", fail)

    # Real shots: replaces `frsp f0,f0` (f0 = the swung step as a double, also at 0xC(r1) ^ 0x80000000;
    # r30 = player). Adds the quarter. Leaf; r0, r3, r4, r10, r12 and f11 are free here.
    a.label("fine_add")
    a(ppc.lwz(0, 0xC, 1), ppc.xoris(4, 0, 0x8000))
    quarter_check("fa_plain", 3, 4)
    a(ppc.lwz(0, F_QUARTER, 10), ppc.slwi(0, 0, 2), ppc.add(12, 10, 0), ppc.lfs(11, F_TABLE, 12))
    a(ppc.frsp(0, 0), ppc.fadds(0, 0, 11), ppc.BLR)
    a.label("fa_plain")
    a(ppc.frsp(0, 0), ppc.BLR)

    # Previews and putts: replaces `stfs f0,0x48(r31)` (f0 = the step's launch speed from the table, r9 + 0x34 =
    # its table entry, r11 = step, r30 = player, r31 = shot). With a quarter set, solves the next step too and
    # stores the blend of the two speeds.
    a.label("fine_lerp")
    a(ppc.stwu(1, -32, 1), ppc.mflr(0), ppc.stw(0, 36, 1), ppc.stfs(0, 0x48, 31))
    quarter_check("fl_done", 3, 11)
    a(ppc.lwz(0, F_QUARTER, 10), ppc.cmpwi(0, 0))
    a.br("beq", "fl_done")
    a(ppc.slwi(0, 0, 2), ppc.add(12, 10, 0), ppc.lfs(0, F_TABLE, 12), ppc.stfs(0, 8, 1))
    a(ppc.stw(9, 12, 1), ppc.stw(11, 16, 1))
    a(ppc.addi(0, 11, 1), ppc.stw(0, SETUP_RANGE, 3), ppc.mr(4, 31))
    a.bl(SOLVE_STEP)
    a(ppc.lwz(3, PLAYER_SETUP, 30), ppc.lwz(11, 16, 1), ppc.stw(11, SETUP_RANGE, 3))
    a(ppc.lwz(9, 12, 1), ppc.lfs(12, 0x34, 9), ppc.lfs(13, 0x3C, 9), ppc.lfs(11, 8, 1))
    a(ppc.fsubs(13, 13, 12), ppc.fmadds(0, 13, 11, 12), ppc.stfs(0, 0x48, 31))
    a.label("fl_done")
    a(ppc.lfs(0, 0x48, 31), ppc.lwz(0, 36, 1), ppc.mtlr(0), ppc.addi(1, 1, 32), ppc.BLR)

    # Power bar label: replaces `mullw r9,r9,r0` (r9 = shown step, r0 = club reach in yards, r23 = the HUD;
    # the game then divides by 60). Returns (4 * step + quarter) * reach / 4, so the label counts yards.
    a.label("fine_yards")
    a(ppc.stwu(1, -16, 1), ppc.stw(8, 8, 1))
    a.la(11, "fine")
    a(ppc.lwz(12, HUD_SETUP, 23))
    a(ppc.lwz(10, SETUP_PLAYER, 12), ppc.lwz(8, 0, 11), ppc.cmpw(8, 10))
    a.br("bne", "fy_plain")
    a(ppc.lwz(10, SETUP_CLUB, 12), ppc.lwz(8, F_CLUB, 11), ppc.cmpw(8, 10))
    a.br("bne", "fy_plain")
    a(ppc.lwz(8, F_STEP, 11), ppc.cmpw(8, 9))
    a.br("bne", "fy_plain")
    a(ppc.lwz(8, F_QUARTER, 11))
    a.br("b", "fy_scale")
    a.label("fy_plain")
    a(ppc.li(8, 0))
    a.label("fy_scale")
    a(ppc.slwi(9, 9, 2), ppc.add(9, 9, 8), ppc.mullw(9, 9, 0), ppc.srwi(9, 9, 2))
    a(ppc.lwz(8, 8, 1), ppc.addi(1, 1, 16), ppc.BLR)

    blob = a.assemble()
    if len(blob) > CAVE5_SIZE:
        raise SystemExit(f"cave 5 code is {len(blob)} bytes; only {CAVE5_SIZE} available")
    return blob, dict(a.labels)


def box_fan():
    """Rounded box as a triangle fan: (side, x offset, y, v) per vertex; x = side * inner + offset at runtime."""
    top, bottom, r, k = BOX["top"], BOX["bottom"], BOX["radius"], BOX["corner_steps"]
    mid = (top + bottom) / 2
    rim = []
    for side, cy, a0 in ((1, top + r, -90), (1, bottom - r, 0), (-1, bottom - r, 90), (-1, top + r, 180)):
        for i in range(k + 1):
            a = math.radians(a0 + 90 * i / k)
            rim.append((side, round(r * math.cos(a)), round(cy + r * math.sin(a))))
    verts = [(0, 0, round(mid))] + rim + [rim[0]]
    return [(s, ox, y, (y - top) / (bottom - top)) for s, ox, y in verts]


def cave8_code():
    """Assemble the fitted, rounded yardage box. Returns (bytes, labels)."""
    a = ppc.Asm(CAVE8)
    fan = box_fan()
    a.float("box_u", BOX["u"])
    a.label("box_fan")
    for side, ox, y, v in fan:
        a(side & 0xFFFFFFFF, ox & 0xFFFFFFFF, y & 0xFFFFFFFF, struct.unpack(">I", struct.pack(">f", v))[0])

    # Replaces `li r4,0` before the box body is drawn. For yards, the game's box pieces get zero height (top = 0).
    a.label("box_hide")
    a(ppc.li(4, 0), ppc.lwz(0, HUD_PUTT, 1), ppc.cmpwi(0, 0))
    a.br("bne", "box_hide_done")
    a(ppc.li(27, 0))
    a.label("box_hide_done")
    a(ppc.BLR)

    # Replaces `lbz r0,0x1b0(r1)` right before the digit loop (label at r1+0x1b0, r29 = x adjust). For yards:
    # move the digits left half a cell per leading space (plus the nudge) and draw the rounded box round them.
    a.label("box_text")
    a(ppc.stwu(1, -32, 1), ppc.mflr(0), ppc.stw(0, 36, 1))
    a(ppc.lwz(0, 32 + HUD_PUTT, 1), ppc.cmpwi(0, 0))
    a.br("bne", "box_text_done")
    a(ppc.addi(9, 1, 32 + HUD_TEXT), ppc.li(10, 0), ppc.li(11, 0))  # r10 = leading spaces, r11 = length
    a.label("box_count")
    a(ppc.add(12, 9, 11), ppc.lbz(0, 0, 12), ppc.cmpwi(0, 0))
    a.br("beq", "box_counted")
    a(ppc.cmpwi(0, 0x20))
    a.br("bne", "box_char")
    a(ppc.cmpw(10, 11))
    a.br("bne", "box_char")
    a(ppc.addi(10, 10, 1))
    a.label("box_char")
    a(ppc.addi(11, 11, 1))
    a.br("b", "box_count")
    a.label("box_counted")
    a(ppc.mulli(0, 10, -8), ppc.add(29, 29, 0), ppc.addi(29, 29, BOX["nudge"]))   # centre the digits
    a(ppc.mulli(0, 10, -1), ppc.add(12, 11, 0), ppc.slwi(12, 12, 3),                # half width of the cells ...
      ppc.addi(12, 12, BOX["pad"] - BOX["radius"]), ppc.stw(12, 8, 1))             # ... + pad - radius = inner
    hi, lo = ppc.hi_lo(HUD_TEXTURES)
    a(ppc.lis(3, hi), ppc.lwz(3, lo, 3), ppc.li(4, 0x10), ppc.li(5, 0))
    a.bl(BIND_TEXTURE)
    a(ppc.li(3, 0), ppc.lis(4, TEV_ALPHA_BOX >> 16), ppc.ori(4, 4, TEV_ALPHA_BOX & 0xFFFF))
    a.bl(GX_SET_TEV_ALPHA_IN)
    a(ppc.li(3, GX_TRIANGLEFAN), ppc.li(4, 0), ppc.li(5, len(fan)))
    a.bl(GX_BEGIN)
    a(ppc.lwz(12, 8, 1), ppc.lis(10, 0xCC01))
    a.la(9, "box_fan")
    a.la(8, "box_u")
    a(ppc.lfs(1, 0, 8), ppc.li(8, len(fan)))
    a.label("box_vertex")                                         # x = side * inner + offset, y, u, v
    a(ppc.lwz(0, 0, 9), ppc.mullw(0, 0, 12), ppc.lwz(7, 4, 9), ppc.add(0, 0, 7), ppc.sth(0, -0x8000, 10),
      ppc.lwz(0, 8, 9), ppc.sth(0, -0x8000, 10), ppc.stfs(1, -0x8000, 10), ppc.lfs(0, 12, 9),
      ppc.stfs(0, -0x8000, 10), ppc.addi(9, 9, 16), ppc.addi(8, 8, -1), ppc.cmpwi(8, 0))
    a.br("bne", "box_vertex")
    a(ppc.li(3, 0), ppc.lis(4, TEV_ALPHA_DIGITS >> 16), ppc.ori(4, 4, TEV_ALPHA_DIGITS & 0xFFFF))
    a.bl(GX_SET_TEV_ALPHA_IN)
    hi, lo = ppc.hi_lo(DIGIT_TEXTURES)
    a(ppc.lis(3, hi), ppc.lwz(3, lo, 3), ppc.li(4, 0), ppc.li(5, 0))
    a.bl(BIND_TEXTURE)
    a.label("box_text_done")
    a(ppc.lwz(12, 36, 1), ppc.mtlr(12), ppc.addi(1, 1, 32), ppc.lbz(0, HUD_TEXT, 1), ppc.BLR)

    blob = a.assemble()
    if len(blob) > CAVE8_SIZE:
        raise SystemExit(f"cave 8 code is {len(blob)} bytes; only {CAVE8_SIZE} available")
    return blob, dict(a.labels)


def cave7_code():
    """Assemble the zoom view camera. Returns (bytes, labels)."""
    a = ppc.Asm(CAVE7)
    for name, value in (("zero", 0.0), ("one", 1.0), ("two", 2.0), ("three", 3.0), ("tiny", 1e-12),
                        *ZOOM_TUNING.items()):
        a.float(f"z_{name}", value)
    for i in range(6):
        a.float(f"z_prev{i}", 0.0)  # the camera last frame (eye xyz, look xyz)
    z = {name: a.labels[f"z_{name}"] - CAVE7
         for name in ("zero", "one", "two", "three", "tiny", "prev0", *ZOOM_TUNING)}

    def fmin(d, b):  # f{d} = min(f{d}, f{b})
        name = f"fmin_{len(a.words)}"
        a(ppc.fcmpu(d, b))
        a.br("ble", name)
        a(ppc.fmr(d, b))
        a.label(name)

    def fmax(d, b):  # f{d} = max(f{d}, f{b})
        name = f"fmax_{len(a.words)}"
        a(ppc.fcmpu(d, b))
        a.br("bge", name)
        a(ppc.fmr(d, b))
        a.label(name)

    # Called after the game's aim camera (r3 = shot setup). In the zoom view with amount > 0, the camera starts
    # behind the ball on the aim line and, as the amount grows, rises and moves up the line until it is high
    # behind the landing spot, looking at the landing spot all the way. It eases toward that spot from last
    # frame's camera; every other frame it just remembers the game's camera. Leaf; uses r4, r7-r10, f0-f13.
    a.label("zoom")
    hi, lo = ppc.hi_lo(CAVE7)
    a(ppc.lis(8, hi), ppc.addi(8, 8, lo))
    hi, lo = ppc.hi_lo(CAMERA_PTR)
    a(ppc.lis(10, hi), ppc.lwz(10, lo, 10))                      # r10 = camera
    a(ppc.lwz(4, SETUP_VIEW, 3), ppc.cmpwi(4, VIEW_ZOOM))
    a.br("bne", "zoom_off")
    a(ppc.lfs(13, SETUP_ZOOM, 3), ppc.lfs(0, z["zero"], 8), ppc.fcmpu(13, 0))   # f13 = zoom amount
    a.br("ble", "zoom_off")
    hi, lo = ppc.hi_lo(AIM_BALL)
    a(ppc.lis(9, hi), ppc.lfs(0, lo, 9), ppc.lfs(1, lo + 4, 9), ppc.lfs(2, lo + 8, 9))   # f0-f2 = ball
    a(ppc.lfs(3, SETUP_TARGET, 3), ppc.fsubs(3, 3, 0), ppc.lfs(4, SETUP_TARGET + 8, 3), ppc.fsubs(4, 4, 2))
    a(ppc.fmuls(5, 3, 3), ppc.fmuls(6, 4, 4), ppc.fadds(5, 5, 6), ppc.lfs(6, z["tiny"], 8), ppc.fcmpu(5, 6))
    a.br("blt", "zoom_off")
    hi, lo = ppc.hi_lo(CAVE2)
    a(ppc.lis(7, hi), ppc.addi(7, 7, lo))
    normalize_xz(a, 3, 4, 5)                                     # f3/f4 = direction to the landing spot
    a(ppc.fmuls(5, 5, 6))                                        # f5 = its distance (n2 / sqrt(n2))
    a(ppc.lfs(12, z["full"], 8), ppc.fdivs(12, 13, 12), ppc.lfs(10, z["one"], 8))
    fmin(12, 10)                                                 # f12 = t, how far along, 0..1
    a(ppc.lfs(9, z["two"], 8), ppc.fmuls(9, 9, 12), ppc.lfs(10, z["three"], 8), ppc.fsubs(10, 10, 9),
      ppc.fmuls(11, 12, 12), ppc.fmuls(11, 11, 10))              # f11 = along the line: t*t*(3 - 2t)
    a(ppc.lfs(8, z["two"], 8), ppc.fsubs(8, 8, 12), ppc.fmuls(8, 8, 12))   # f8 = height: t*(2 - t)
    a(ppc.lfs(6, z["end_back_share"], 8), ppc.fmuls(6, 6, 5), ppc.lfs(7, z["end_back"], 8))
    fmin(6, 7)                                                   # f6 = end: distance short of the spot
    a(ppc.lfs(7, z["end_up_share"], 8), ppc.fmuls(7, 7, 5), ppc.lfs(9, z["end_up_min"], 8))
    fmax(7, 9)
    a(ppc.lfs(9, z["end_up"], 8))
    fmin(7, 9)                                                   # f7 = end: height over the spot
    # how far up the line: from start_back behind the ball to f6 short of the spot
    a(ppc.lfs(10, z["start_back"], 8), ppc.fsubs(9, 5, 6), ppc.fadds(9, 9, 10), ppc.fmuls(9, 9, 11),
      ppc.fsubs(9, 9, 10))
    a(ppc.fmadds(3, 3, 9, 0), ppc.fmadds(4, 4, 9, 2))            # f3/f4 = eye x/z
    a(ppc.lfs(6, z["start_up"], 8), ppc.fadds(6, 1, 6),           # eye height: ball + start_up ...
      ppc.lfs(9, SETUP_TARGET + 4, 3), ppc.fadds(9, 9, 7), ppc.fsubs(9, 9, 6), ppc.fmadds(6, 9, 8, 6))  # ... to spot + f7
    a(ppc.lfs(10, z["ease"], 8))                                 # glide: prev += (want - prev) * ease
    for i, f in enumerate((3, 6, 4)):
        a(ppc.lfs(9, z["prev0"] + 4 * i, 8), ppc.fsubs(f, f, 9), ppc.fmadds(f, f, 10, 9),
          ppc.stfs(f, z["prev0"] + 4 * i, 8), ppc.stfs(f, 4 * i, 10))
    for i in range(3):                                           # look at the landing spot
        a(ppc.lfs(8, SETUP_TARGET + 4 * i, 3), ppc.lfs(9, z["prev0"] + 12 + 4 * i, 8), ppc.fsubs(8, 8, 9),
          ppc.fmadds(8, 8, 10, 9), ppc.stfs(8, z["prev0"] + 12 + 4 * i, 8), ppc.stfs(8, 12 + 4 * i, 10))
    a(ppc.BLR)
    a.label("zoom_off")                                          # not zooming: remember the game's camera
    for i in range(6):
        a(ppc.lfs(9, 4 * i, 10), ppc.stfs(9, z["prev0"] + 4 * i, 8))
    a(ppc.BLR)

    blob = a.assemble()
    if len(blob) > CAVE7_SIZE:
        raise SystemExit(f"cave 7 code is {len(blob)} bytes; only {CAVE7_SIZE} available")
    return blob, dict(a.labels)


def bl_sites(blob, base, target):
    """Addresses of `bl target` in a code image loaded at base."""
    out = []
    for i in range(0, len(blob) - 3, 4):
        w = struct.unpack_from(">I", blob, i)[0]
        if w & 0xFC000003 == 0x48000001:
            off = w & 0x03FFFFFC
            if base + i + off - (0x04000000 if off & 0x02000000 else 0) == target:
                out.append(base + i)
    return out


def projection_call_sites(clean):
    """Every bl GX_SET_PROJECTION in main.dol's text and in the two fixed-address overlays."""
    dol = open(os.path.join(clean, "sys", "main.dol"), "rb").read()
    sites = []
    for i in range(7):
        off, addr, size = (struct.unpack_from(">I", dol, k + 4 * i)[0] for k in (0x00, 0x48, 0x90))
        if size:
            sites += bl_sites(dol[off:off + size], addr, GX_SET_PROJECTION)
    for rel in OVERLAY_MATRIX_HOOKS:
        blob, _ = lz.decompress(open(os.path.join(clean, "files", *rel.split("/")), "rb").read())
        sites += bl_sites(blob, OVERLAY_BASE, GX_SET_PROJECTION)
    if len(set(sites)) != len(sites):
        raise SystemExit("a projection call site is shared by both overlays; the anchor table can't tell them apart")
    return sorted(sites)


def anchor_table(proj_sites):
    """Cave 4: one row per projection call site (return address, anchor, calls seen), then 0."""
    words = []
    for site in proj_sites:
        words += [site + 4, PROJ_CALLERS.get(site, ANCHOR_CENTER), 0]
    blob = struct.pack(f">{len(words) + 1}I", *words, 0)
    if len(blob) > CAVE4_SIZE:
        raise SystemExit(f"anchor table is {len(blob)} bytes; only {CAVE4_SIZE} available")
    return blob


def cave6_code():
    """Assemble the See-Through setting and its pause-menu row. Returns (bytes, labels)."""
    a = ppc.Asm(CAVE6)
    a.word("ghost_mode", GHOST_PUTTS)   # the setting (on by default; lasts until the game is turned off)
    a.word("ghost_item")                # 1 while the pause menu lists our row
    for name, text in (("ghost_text_on", GHOST_TEXT_ON), ("ghost_text_off", GHOST_TEXT_OFF),
                       ("ghost_help", GHOST_TEXT_HELP)):
        a.label(name)
        text += b"\x00" * (-len(text) % 4)
        a(*struct.unpack(f">{len(text) // 4}I", text))

    # Replaces `bl PAUSE_BUILD` (r3 = pause menu): after the game lists its rows, add ours if there's room
    # and the code is free.
    a.label("ghost_menu")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1), ppc.stw(31, 12, 1), ppc.mr(31, 3))
    a.bl(PAUSE_BUILD)
    a.la(12, "ghost_item")
    a(ppc.li(0, 0), ppc.stw(0, 0, 12), ppc.lbz(11, PAUSE_COUNT, 31), ppc.cmpwi(11, PAUSE_ROWS_MAX))
    a.br("bge", "gm_done")
    hi, lo = ppc.hi_lo(PAUSE_LIST)
    a(ppc.lis(10, hi), ppc.addi(10, 10, lo), ppc.li(9, 0))
    a.label("gm_loop")
    a(ppc.cmpw(9, 11))
    a.br("bge", "gm_add")
    a(ppc.slwi(8, 9, 2), ppc.add(8, 8, 10), ppc.lwz(8, 0, 8), ppc.cmpwi(8, GHOST_ITEM))
    a.br("beq", "gm_done")
    a(ppc.addi(9, 9, 1))
    a.br("b", "gm_loop")
    a.label("gm_add")
    a(ppc.slwi(8, 11, 2), ppc.add(8, 8, 10), ppc.li(0, GHOST_ITEM), ppc.stw(0, 0, 8))
    a(ppc.addi(11, 11, 1), ppc.stb(11, PAUSE_COUNT, 31), ppc.li(0, 1), ppc.stw(0, 0, 12))
    a.label("gm_done")
    a(ppc.lwz(31, 12, 1), ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    # Replaces `bl PAUSE_RUN_TARGET` just before the menu runs the chosen row (r25 = menu). Our row flips the
    # setting, shows the new text and goes back to the menu, skipping the game's jump table.
    a.label("ghost_select")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1))
    a.bl(PAUSE_RUN_TARGET)
    a.la(12, "ghost_item")
    a(ppc.lwz(0, 0, 12), ppc.cmpwi(0, 0))
    a.br("beq", "gs_game")
    hi, lo = ppc.hi_lo(PAUSE_LIST)
    a(ppc.lwz(10, PAUSE_CURSOR, 25), ppc.slwi(10, 10, 2), ppc.lis(11, hi), ppc.addi(11, 11, lo), ppc.add(11, 11, 10),
      ppc.lwz(0, 0, 11), ppc.cmpwi(0, GHOST_ITEM))
    a.br("bne", "gs_game")
    a.la(12, "ghost_mode")
    a(ppc.lwz(0, 0, 12), ppc.cmpwi(0, GHOST_OFF), ppc.li(0, GHOST_PUTTS))
    a.br("beq", "gs_set")
    a(ppc.li(0, GHOST_OFF))
    a.label("gs_set")
    a(ppc.stw(0, 0, 12))
    a(ppc.add(10, 10, 25), ppc.lwz(3, PAUSE_ROWS, 10), ppc.li(4, MSG_GHOST_ITEM), ppc.li(5, 0), ppc.li(6, 0x20),
      ppc.li(7, 3))
    a.bl(SET_TEXT)
    a(ppc.lwz(3, PAUSE_HELP, 25), ppc.li(4, MSG_GHOST_HELP), ppc.li(5, 0), ppc.li(6, 0x20), ppc.li(7, 2))
    a.bl(SET_TEXT)
    hi, lo = ppc.hi_lo(PAUSE_RUN_DEFAULT)
    a(ppc.addi(1, 1, 16), ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.mtlr(12), ppc.BLR)
    a.label("gs_game")
    a(ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    blob = a.assemble()
    if len(blob) > CAVE6_SIZE:
        raise SystemExit(f"cave 6 code is {len(blob)} bytes; only {CAVE6_SIZE} available")
    return blob, dict(a.labels)


def cave3_code(zoom, v6):
    """Assemble the putt aim view, the replay prompt and the HUD anchors. Returns (bytes, labels)."""
    a = ppc.Asm(CAVE3)
    a.word("prompt_open")  # 1 while our Continue / Watch Replay menu is up
    a.label("replay_text")
    text = REPLAY_TEXT + b"\x00" * (-len(REPLAY_TEXT) % 4)
    a(*struct.unpack(f">{len(text) // 4}I", text))

    # Putt aim view: replaces `bl AIM_CAMERA` (r3 = shot setup, r4 passed through). Runs the game's aim
    # camera, then with the putter out in the normal view (or on the swing meter) puts the camera behind the
    # ball on the line to the aim point. Every way of looking around wins: another view (LT/RT, X/Y), turning
    # the camera (right stick) or the side view (Back) shows the game's camera until let go.
    a.label("aim")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1), ppc.stw(31, 12, 1), ppc.mr(31, 3))
    a.bl(AIM_CAMERA)
    a(ppc.mr(3, 31))
    a.bl(zoom)  # v4: steady zoom view (does nothing in the other views)
    hi, lo = ppc.hi_lo(CAVE2)
    a(ppc.lis(7, hi), ppc.addi(7, 7, lo))  # r7 = camera data block
    a(ppc.lwz(4, SETUP_CLUB, 31), ppc.cmpwi(4, CLUB_PUTTER))
    a.br("bne", "aim_done")
    a(ppc.lwz(4, SETUP_VIEW, 31), ppc.cmpwi(4, 5))
    a.br("beq", "aim_view")
    a(ppc.cmpwi(4, 0xB))
    a.br("bne", "aim_done")
    a.label("aim_view")
    a(ppc.lfs(1, SETUP_ZOOM_IN, 31), ppc.fmuls(1, 1, 1), ppc.lfs(2, D_ZOOM2, 7), ppc.fcmpu(1, 2))
    a.br("bgt", "aim_done")
    a(ppc.lfs(1, SETUP_TURN, 31), ppc.fmuls(1, 1, 1), ppc.fcmpu(1, 2))  # camera turned more than ~6 degrees
    a.br("bgt", "aim_done")
    a(ppc.lhz(4, SETUP_HELD, 31), ppc.andi_(4, 4, PAD_Z))                 # side view held
    a.br("bne", "aim_done")
    a(ppc.mr(3, 31))
    a.br("bl", "aim_place")
    a.label("aim_done")
    a(ppc.lwz(31, 12, 1), ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    # Leaf: camera behind the ball on the line to the aim point. r3 = shot setup, r7 = data block.
    a.label("aim_place")
    hi, lo = ppc.hi_lo(AIM_BALL)
    a(ppc.lis(8, hi), ppc.addi(8, 8, lo), ppc.lfs(0, 0, 8), ppc.lfs(1, 4, 8), ppc.lfs(2, 8, 8))   # ball
    a(ppc.lfs(3, SETUP_TARGET, 3), ppc.fsubs(3, 3, 0), ppc.lfs(4, SETUP_TARGET + 8, 3), ppc.fsubs(4, 4, 2))
    a(ppc.fmuls(5, 3, 3), ppc.fmuls(6, 4, 4), ppc.fadds(5, 5, 6), ppc.lfs(6, D_TINY, 7), ppc.fcmpu(5, 6))
    a.br("blt", "aim_place_done")
    normalize_xz(a, 3, 4, 5)
    a(ppc.mr(12, 7))
    place_camera(a, D_PARAMS + 0x20)
    hi, lo = ppc.hi_lo(CAMERA_PTR)
    a(ppc.lis(10, hi), ppc.lwz(10, lo, 10))
    for i, f in enumerate((5, 6, 7, 8, 9, 10)):
        a(ppc.stfs(f, 4 * i, 10))
    a.label("aim_place_done")
    a(ppc.BLR)

    # Message lookup hook (first instruction of MSG_LOOKUP): while our prompt is up, option code 7's text
    # reads "Watch Replay"; everything else goes to the game's lookup untouched.
    # v4: while the pause menu lists our See-Through row, its two messages are ours.
    a.label("text_hook")
    a.la(12, "prompt_open")
    a(ppc.lwz(0, 0, 12), ppc.cmpwi(0, 0))
    a.br("beq", "text_ghost")
    a(ppc.cmpwi(3, MSG_OPTION_REPLAY))
    a.br("bne", "text_ghost")
    a.la(3, "replay_text")
    a(ppc.BLR)
    a.label("text_ghost")
    hi, lo = ppc.hi_lo(v6["ghost_item"])
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, 0))
    a.br("beq", "text_game")
    a(ppc.cmpwi(3, MSG_GHOST_HELP))
    a.br("bne", "text_ghost_row")
    hi, lo = ppc.hi_lo(v6["ghost_help"])
    a(ppc.lis(3, hi), ppc.addi(3, 3, lo), ppc.BLR)
    a.label("text_ghost_row")
    a(ppc.cmpwi(3, MSG_GHOST_ITEM))
    a.br("bne", "text_game")
    hi, lo = ppc.hi_lo(v6["ghost_mode"])
    a(ppc.lis(12, hi), ppc.lwz(0, lo, 12), ppc.cmpwi(0, GHOST_OFF))
    hi, lo = ppc.hi_lo(v6["ghost_text_on"])
    a(ppc.lis(3, hi), ppc.addi(3, 3, lo))
    a.br("bne", "text_ghost_done")
    hi, lo = ppc.hi_lo(v6["ghost_text_off"])
    a(ppc.lis(3, hi), ppc.addi(3, 3, lo))
    a.label("text_ghost_done")
    a(ppc.BLR)
    a.label("text_game")
    a(MSG_LOOKUP_FIRST)
    a.b(MSG_LOOKUP + 4)

    # Replaces REPLAY_CHECK (the game replays the shot on any B press). Now, on the result screen, the
    # shooter's B opens a Continue / Watch Replay menu, and only Watch Replay sets the replay flag.
    a.label("replay_check")
    a(ppc.stwu(1, -32, 1), ppc.mflr(0), ppc.stw(0, 36, 1), ppc.stw(31, 28, 1), ppc.stw(30, 24, 1),
      ppc.stw(29, 20, 1))
    hi, lo = ppc.hi_lo(CUR_PLAYER)
    a(ppc.lis(3, hi), ppc.lbz(4, lo, 3), ppc.andi_(0, 4, 0x80))
    a.br("bne", "rc_done")
    a(ppc.mulli(4, 4, PLAYER_STRIDE))
    hi, lo = ppc.hi_lo(PLAYERS)
    a(ppc.lis(31, hi), ppc.addi(31, 31, lo), ppc.add(31, 31, 4))       # r31 = shooter
    a(ppc.lwz(0, 0x24, 31), ppc.cmpwi(0, STATE_STOPPED))
    a.br("bne", "rc_done")
    a(ppc.lwz(30, 0x4F14, 31), ppc.lhz(0, 4, 30), ppc.andi_(0, 0, PAD_B))  # r30 = shooter's pad; B pressed?
    a.br("beq", "rc_done")
    a(ppc.lwz(0, PLAYER_MENU, 31), ppc.cmpwi(0, 0))
    a.br("bne", "rc_done")
    a(ppc.lwz(3, RESULT_TIMER, 31), ppc.lwz(0, RESULT_LENGTH, 31), ppc.cmpw(3, 0))
    a.br("bge", "rc_done")                                              # too late to replay anyway
    a(ppc.li(3, 0x90))
    a.bl(ALLOC)
    a(ppc.mr(29, 3), ppc.li(4, 4), ppc.mr(5, 30))
    a.bl(MENU_INIT)
    a(ppc.li(0, OPTION_REPLAY), ppc.stw(0, MENU_OPTION_2, 29))          # Continue / Watch Replay
    a(ppc.stw(29, PLAYER_MENU, 31))
    hi, lo = ppc.hi_lo(CUR_MENU)
    a(ppc.lis(3, hi), ppc.stw(29, lo, 3))
    a.la(3, "prompt_open")
    a(ppc.li(0, 1), ppc.stw(0, 0, 3))
    hi, lo = ppc.hi_lo(TRANSITIONS)
    a(ppc.lis(3, hi), ppc.addi(3, 3, lo), ppc.li(4, TRANSITION_MENU))
    a.bl(SET_TRANSITION)
    a.label("rc_done")
    a(ppc.lwz(29, 20, 1), ppc.lwz(30, 24, 1), ppc.lwz(31, 28, 1), ppc.lwz(0, 36, 1), ppc.mtlr(0),
      ppc.addi(1, 1, 32), ppc.BLR)

    # Replaces `bl FUN_804840a8` (r3 = open menu; returns its choice). For our prompt: Watch Replay sets the
    # replay flag (the result screen then replays as before); any finished choice closes the prompt.
    a.label("result_hook")
    a(ppc.lwz(3, 0, 3))
    a.la(12, "prompt_open")
    a(ppc.lwz(0, 0, 12), ppc.cmpwi(0, 0))
    a.br("beq", "rh_done")
    a(ppc.cmpwi(3, OPTION_REPLAY))
    a.br("bne", "rh_other")
    hi, lo = ppc.hi_lo(REPLAY_FLAG)
    a(ppc.li(0, 1), ppc.lis(11, hi), ppc.stw(0, lo, 11))
    a.label("rh_other")
    a(ppc.cmpwi(3, -2))
    a.br("beq", "rh_close")
    a(ppc.cmpwi(3, 0))
    a.br("blt", "rh_done")
    a.label("rh_close")
    a(ppc.li(0, 0), ppc.stw(0, 0, 12))
    a.label("rh_done")
    a(ppc.BLR)

    # HUD anchors: replaces GXSetProjection's store of a 2D projection's x offset (f0 = m[0][3]; the caller's
    # return address is still in LR). Widening 2D layers by 4/3 keeps their art in shape at 16:9 but leaves
    # them in the middle; for the HUD pieces in the table, shifting the offset by a quarter screen puts the
    # piece's 4:3 layout flush against the left or right edge instead, still in shape.
    a.float("anchor_shift", ANCHOR_SHIFT)
    a.float("proj_base", 0.0)  # the last 2D projection's x offset before anchoring (for the HUD splits)
    a.label("anchor")
    a.la(12, "proj_base")
    a(ppc.stfs(0, 0, 12))
    hi, lo = ppc.hi_lo(CAVE4)
    a(ppc.mflr(11), ppc.lis(12, hi), ppc.addi(12, 12, lo))   # r12 = anchor table
    a.label("anchor_find")
    a(ppc.lwz(10, 0, 12), ppc.cmpwi(10, 0))
    a.br("beq", "anchor_done")
    a(ppc.cmpw(10, 11))
    a.br("beq", "anchor_found")
    a(ppc.addi(12, 12, 12))
    a.br("b", "anchor_find")
    a.label("anchor_found")
    a(ppc.lwz(10, 8, 12), ppc.addi(10, 10, 1), ppc.stw(10, 8, 12))  # calls seen (handy when mapping the HUD)
    a(ppc.lwz(10, 4, 12))
    a.la(12, "anchor_shift")
    a(ppc.lfs(1, 0, 12), ppc.cmpwi(10, ANCHOR_LEFT))
    a.br("bne", "anchor_right")
    a(ppc.fsubs(0, 0, 1))
    a.br("b", "anchor_done")
    a.label("anchor_right")
    a(ppc.cmpwi(10, ANCHOR_RIGHT))
    a.br("bne", "anchor_done")
    a(ppc.fadds(0, 0, 1))
    a.label("anchor_done")
    a(PROJ_STORE_X_WORD)
    a.b(PROJ_STORE_X + 4)

    # HUD splits: re-anchor the projection already loaded (from proj_base, so it is right even if the HUD
    # function returned early), mark it for GX to resend, then go on to the call this replaced.
    for site, anchor, target in HUD_SPLITS:
        a.label(f"split_{site:08X}")
        a.la(12, "proj_base")
        a(ppc.lfs(0, 0, 12))
        if anchor != ANCHOR_CENTER:
            a.la(12, "anchor_shift")
            a(ppc.lfs(1, 0, 12), ppc.fadds(0, 0, 1) if anchor == ANCHOR_RIGHT else ppc.fsubs(0, 0, 1))
        a(ppc.stfs(0, GX_PROJ_X, 13), ppc.lwz(0, GX_DIRTY, 13), ppc.ori(0, 0, GX_DIRTY_PROJECTION),
          ppc.stw(0, GX_DIRTY, 13))
        a.b(target)

    # v4 see-through golfer (see MODEL_DRAW). State: whether the golfer is being drawn see-through, the blend
    # and depth modes the game last asked for, and the material colour passed instead. The setting is in cave 6.
    a.word("ghost_on")
    for i, v in enumerate((GX_BM_BLEND, GX_BL_SRCALPHA, GX_BL_INVSRCALPHA, GX_LO_SET)):
        a.word(f"blend{i}", v)
    for i, v in enumerate((1, 3, 1)):  # GX_TRUE, GX_LEQUAL, GX_TRUE: what the character materials use
        a.word(f"zmode{i}", v)
    a.word("ghost_color")
    G_ON, G_BLEND, G_ZMODE, G_COLOR = 0, 4, 20, 32

    # Replaces MODEL_DRAW's first instruction (r3 = model instance). The shooter's golfer, putting (aim to
    # stroke) with the setting on, is drawn see-through; everything else draws as normal.
    a.label("ghost_draw")
    hi, lo = ppc.hi_lo(v6["ghost_mode"])
    a(ppc.lis(11, hi), ppc.lwz(11, lo, 11), ppc.cmpwi(11, GHOST_OFF))
    a.br("beq", "gd_plain")
    a.la(12, "ghost_on")
    hi, lo = ppc.hi_lo(CUR_PLAYER)
    a(ppc.lis(10, hi), ppc.lbz(10, lo, 10), ppc.andi_(0, 10, 0x80))
    a.br("bne", "gd_plain")
    a(ppc.mulli(10, 10, PLAYER_STRIDE))
    hi, lo = ppc.hi_lo(PLAYERS)
    a(ppc.lis(9, hi), ppc.addi(9, 9, lo), ppc.add(9, 9, 10))              # r9 = shooter
    a(ppc.lwz(10, PLAYER_GOLFER, 9), ppc.cmpw(10, 3))
    a.br("bne", "gd_plain")
    a(ppc.lwz(10, 0x24, 9), ppc.cmpwi(10, STATE_AIM))
    a.br("blt", "gd_plain")
    a(ppc.cmpwi(10, STATE_LAUNCHED))
    a.br("bgt", "gd_plain")
    a(ppc.cmpwi(11, GHOST_ALWAYS))
    a.br("beq", "gd_ghost")
    a(ppc.lwz(10, SETUP_PTR, 9), ppc.lwz(10, SETUP_CLUB, 10), ppc.cmpwi(10, CLUB_PUTTER))
    a.br("bne", "gd_plain")
    a.label("gd_ghost")
    a(ppc.stwu(1, -32, 1), ppc.mflr(0), ppc.stw(0, 36, 1), ppc.stw(3, 8, 1), ppc.stw(4, 12, 1), ppc.stw(5, 16, 1))
    a(ppc.li(0, 1), ppc.stw(0, G_ON, 12))
    a(ppc.li(3, GX_BM_BLEND), ppc.li(4, GX_BL_SRCALPHA), ppc.li(5, GX_BL_INVSRCALPHA), ppc.li(6, GX_LO_SET))
    a.br("bl", "blend_raw")
    a(ppc.li(3, 1), ppc.li(4, 3), ppc.li(5, 0))
    a.br("bl", "zmode_raw")
    a(ppc.lwz(3, 8, 1), ppc.lwz(4, 12, 1), ppc.lwz(5, 16, 1))
    a.br("bl", "gd_plain")                                               # the game's draw
    a.la(12, "ghost_on")
    a(ppc.li(0, 0), ppc.stw(0, G_ON, 12))
    a(ppc.lwz(3, G_BLEND, 12), ppc.lwz(4, G_BLEND + 4, 12), ppc.lwz(5, G_BLEND + 8, 12),
      ppc.lwz(6, G_BLEND + 12, 12))
    a.br("bl", "blend_raw")
    a.la(12, "ghost_on")
    a(ppc.lwz(3, G_ZMODE, 12), ppc.lwz(4, G_ZMODE + 4, 12), ppc.lwz(5, G_ZMODE + 8, 12))
    a.br("bl", "zmode_raw")
    a(ppc.lwz(0, 36, 1), ppc.mtlr(0), ppc.addi(1, 1, 32), ppc.BLR)
    a.label("gd_plain")
    a(MODEL_DRAW_FIRST)
    a.b(MODEL_DRAW + 4)

    # GXSetBlendMode / GXSetZMode entries: remember what the game asks for; while the golfer is drawn
    # see-through, blend by source alpha and leave depth unwritten instead.
    a.label("blend_hook")
    a.la(12, "ghost_on")
    a(ppc.stw(3, G_BLEND, 12), ppc.stw(4, G_BLEND + 4, 12), ppc.stw(5, G_BLEND + 8, 12),
      ppc.stw(6, G_BLEND + 12, 12), ppc.lwz(11, G_ON, 12), ppc.cmpwi(11, 0))
    a.br("beq", "blend_raw")
    a(ppc.li(3, GX_BM_BLEND), ppc.li(4, GX_BL_SRCALPHA), ppc.li(5, GX_BL_INVSRCALPHA))
    a.label("blend_raw")
    a(GX_SET_BLEND_FIRST)
    a.b(GX_SET_BLEND + 4)
    a.label("zmode_hook")
    a.la(12, "ghost_on")
    a(ppc.stw(3, G_ZMODE, 12), ppc.stw(4, G_ZMODE + 4, 12), ppc.stw(5, G_ZMODE + 8, 12),
      ppc.lwz(11, G_ON, 12), ppc.cmpwi(11, 0))
    a.br("beq", "zmode_raw")
    a(ppc.li(5, 0))
    a.label("zmode_raw")
    a(GX_SET_ZMODE_FIRST)
    a.b(GX_SET_ZMODE + 4)

    # GXSetChanMatColor entry (r4 = &color, RGBA): while see-through, pass a copy with alpha scaled down.
    a.label("color_hook")
    a.la(12, "ghost_on")
    a(ppc.lwz(11, G_ON, 12), ppc.cmpwi(11, 0))
    a.br("beq", "color_go")
    a(ppc.lwz(11, 0, 4), ppc.rlwinm(10, 11, 0, 24, 31), ppc.mulli(10, 10, GHOST_ALPHA), ppc.srwi(10, 10, 8),
      ppc.rlwinm(11, 11, 0, 0, 23), ppc.or_(11, 11, 10), ppc.stw(11, G_COLOR, 12), ppc.addi(4, 12, G_COLOR))
    a.label("color_go")
    a(GX_SET_MAT_COLOR_FIRST)
    a.b(GX_SET_MAT_COLOR + 4)

    blob = a.assemble()
    if len(blob) > CAVE3_SIZE:
        raise SystemExit(f"cave 3 code is {len(blob)} bytes; only {CAVE3_SIZE} available")
    return blob, dict(a.labels)


def load_const(fr, addr):
    hi, lo = ppc.hi_lo(addr)
    return [ppc.lis(4, hi), ppc.lfs(fr, lo, 4)]


def ortho_stub(at):
    code = []
    if ASPECT_WRITE:
        hi, lo = ppc.hi_lo(CAMERA_ASPECT)
        code += load_const(12, CAVE + 4) + [ppc.lis(4, hi), ppc.stfs(12, lo, 4)]  # camera aspect = 1.624
    if UNLOCK:
        hi, lo = ppc.hi_lo(UNLOCK_FLAGS)
        code += [ppc.lis(4, hi), ppc.li(0, -1), 0x90040000 | (lo & 0xFFFF)]       # stw r0: both flags = FFFF
    code += load_const(12, CAVE)                                                  # f12 = 4/3
    code += [ppc.fmuls(8, 12, 8),                                                 # (right-left) *= 4/3
             ppc.fdivs(10, 9, 8)]                                                 # original instruction
    code.append(ppc.b(at + 4 * len(code), ORTHO_HOOK + 4))
    return code


def matrix_stub(at, hook):
    code = load_const(13, CAVE) + [                                               # f13 = 4/3
        ppc.lfs(12, 0x0, 3), ppc.fmuls(12, 13, 12), ppc.stfs(12, 0x0, 3),          # m[0][0] *= 4/3
        ppc.lfs(12, 0xC, 3), ppc.fmuls(12, 13, 12), ppc.stfs(12, 0xC, 3),          # m[0][3] *= 4/3
        LI_R4_1,                                                                  # original instruction
    ]
    code.append(ppc.b(at + 4 * len(code), hook + 4))
    return code


def build_cave():
    """Return (cave bytes, {hook address: stub address})."""
    words = [K_4_3, K_ASPECT]
    stubs = {}
    at = CAVE + 8
    hooks = [ORTHO_HOOK] + DOL_MATRIX_HOOKS + sum(OVERLAY_MATRIX_HOOKS.values(), [])
    for hook in hooks:
        code = ortho_stub(at) if hook == ORTHO_HOOK else matrix_stub(at, hook)
        stubs[hook] = at
        words += code
        at += 4 * len(code)
    blob = b"".join(struct.pack(">I", w) for w in words)
    if len(blob) > CAVE_SIZE:
        raise SystemExit(f"cave code is {len(blob)} bytes; only {CAVE_SIZE} available")
    return blob, stubs


def word(buf, base, addr):
    return struct.unpack_from(">I", buf, addr - base)[0]


def put(buf, base, addr, value, expect):
    old = word(buf, base, addr)
    if old != expect:
        raise SystemExit(f"0x{addr:08X}: expected {expect:08X}, found {old:08X} (not a clean GFTE01 file?)")
    struct.pack_into(">I", buf, addr - base, value)


def check_matrix_site(buf, base, hook):
    """The stub assumes r3 = matrix just built by C_MTXOrtho and a GXSetProjection call right after."""
    following = [word(buf, base, hook + 4 * i) for i in (1, 2)]
    targets = [hook + 4 * i + ((w & 0x03FFFFFC) - (0x04000000 if w & 0x02000000 else 0))
               for i, w in zip((1, 2), following) if w & 0xFC000003 == 0x48000001]
    if GX_SET_PROJECTION not in targets:
        raise SystemExit(f"0x{hook:08X}: no GXSetProjection call right after the hook")


def patch_dol(src, dst, cave, stubs, cave2, cave3, v3, cave4, cave5, cave6, cave7, cave8, cave9=None):
    data = bytearray(open(src, "rb").read())
    t0_off = struct.unpack_from(">I", data, 0x00)[0]
    t0_addr = struct.unpack_from(">I", data, 0x48)[0]
    base = t0_addr - t0_off  # address of file offset 0, for word()/put()

    for addr, first, code in ((CAVE, 0x9421FF70, cave), (CAVE2, 0x7C0802A6, cave2), (CAVE3, 0x7C0802A6, cave3),
                              (CAVE4, CAVE4_FIRST, cave4), (CAVE5, CAVE5_FIRST, cave5), (CAVE6, CAVE6_FIRST, cave6),
                              (CAVE7, CAVE7_FIRST, cave7), (CAVE8, CAVE8_FIRST, cave8), (CAVE9, CAVE9_FIRST, cave9)):
        if code is None:
            continue
        if word(data, base, addr) != first:  # still the original (dead) function
            raise SystemExit(f"0x{addr:08X}: expected first instruction {first:08X}")
        data[addr - base:addr - base + len(code)] = code
    put(data, base, MSG_LOOKUP, ppc.b(MSG_LOOKUP, v3["text_hook"]), MSG_LOOKUP_FIRST)
    put(data, base, PROJ_STORE_X, ppc.b(PROJ_STORE_X, v3["anchor"]), PROJ_STORE_X_WORD)
    for site, first, stub in ((MODEL_DRAW, MODEL_DRAW_FIRST, "ghost_draw"), (GX_SET_BLEND, GX_SET_BLEND_FIRST, "blend_hook"),
                              (GX_SET_ZMODE, GX_SET_ZMODE_FIRST, "zmode_hook"),
                              (GX_SET_MAT_COLOR, GX_SET_MAT_COLOR_FIRST, "color_hook")):
        put(data, base, site, ppc.b(site, v3[stub]), first)
    put(data, base, ASPECT_CONST, K_ASPECT, 0x3F9BE76D)
    put(data, base, ORTHO_HOOK, ppc.b(ORTHO_HOOK, stubs[ORTHO_HOOK]), ppc.fdivs(10, 9, 8))
    for hook in DOL_MATRIX_HOOKS:
        check_matrix_site(data, base, hook)
        put(data, base, hook, ppc.b(hook, stubs[hook]), LI_R4_1)
    if word(data, base, MOVIE_LOOP_EXIT + 8) != 0x41B20058:  # beq cr4, past the movie's stop/destroy calls
        raise SystemExit(f"0x{MOVIE_LOOP_EXIT + 8:08X}: not the expected movie loop exit")
    put(data, base, MOVIE_LOOP, 0x2E1D0000, 0x2C1D0000)  # cmpwi cr4,r29,0: r29 = 0 here, so cr4 = "no movie"
    put(data, base, MOVIE_LOOP + 4, ppc.b(MOVIE_LOOP + 4, MOVIE_LOOP_EXIT), 0x3B9C0001)
    open(dst, "wb").write(data)
    print(f"main.dol: aspect 1.624, {1 + len(DOL_MATRIX_HOOKS)} hooks, {len(cave)}-byte cave at 0x{CAVE:08X}"
          f" (aspect write {'on' if ASPECT_WRITE else 'off'}, unlock {'on' if UNLOCK else 'off'}), no opening movie")


def float_word(v):
    return struct.unpack(">I", struct.pack(">f", v))[0]


def patch_overlay(clean_files, build_files, rel, stubs, v2, v3, v4, v9=None):
    raw = open(os.path.join(clean_files, *rel.split("/")), "rb").read()
    kind, _ = lz.header(raw)
    blob, _ = lz.decompress(raw)
    buf = bytearray(blob)
    for hook in OVERLAY_MATRIX_HOOKS[rel]:
        check_matrix_site(buf, OVERLAY_BASE, hook)
        put(buf, OVERLAY_BASE, hook, ppc.b(hook, stubs[hook]), LI_R4_1)
    if rel == "C/L/V":  # the gameplay hooks live in the golf overlay
        put(buf, OVERLAY_BASE, HOOK_SHOOTER_UPDATE, ppc.bl(HOOK_SHOOTER_UPDATE, v2["ff"]),
            ppc.bl(HOOK_SHOOTER_UPDATE, PLAYER_UPDATE))
        put(buf, OVERLAY_BASE, HOOK_SHOT_CAMERA, ppc.bl(HOOK_SHOT_CAMERA, v2["cam"]),
            ppc.bl(HOOK_SHOT_CAMERA, SHOT_CAMERA))
        put(buf, OVERLAY_BASE, HOOK_AIM_CAMERA, ppc.bl(HOOK_AIM_CAMERA, v3["aim"]),
            ppc.bl(HOOK_AIM_CAMERA, AIM_CAMERA))
        for site in GLASS_BREAK_SITES:
            if word(buf, OVERLAY_BASE, site + 4) != 0x38632988:  # addi r3,r3,0x2988: the transition manager
                raise SystemExit(f"0x{site:08X}: not a glass-break transition request")
            put(buf, OVERLAY_BASE, site, LI_R4_NONE, LI_R4_4)
        if [word(buf, OVERLAY_BASE, REPLAY_CHECK + 4 * i) for i in range(8)] != REPLAY_CHECK_WORDS:
            raise SystemExit(f"0x{REPLAY_CHECK:08X}: not the expected replay check")
        put(buf, OVERLAY_BASE, REPLAY_CHECK, ppc.b(REPLAY_CHECK, v3["replay_check"]), REPLAY_CHECK_WORDS[0])
        put(buf, OVERLAY_BASE, HOOK_MENU_RESULT, ppc.bl(HOOK_MENU_RESULT, v3["result_hook"]),
            ppc.bl(HOOK_MENU_RESULT, 0x804840A8))
        for site, _, target in HUD_SPLITS:
            put(buf, OVERLAY_BASE, site, ppc.bl(site, v3[f"split_{site:08X}"]), ppc.bl(site, target))
        for i, (old, new) in enumerate(zip(SLOT_ITEMS_OLD, SLOT_ITEMS_NEW)):
            put(buf, OVERLAY_BASE, SLOT_ITEMS + 4 * i, new, old)
        for site, expect, stub in ((RANGE_STEP_HOOK, RANGE_STEP_WORD, "fine_step"), (SPREAD_HOOK, SPREAD_WORD, "fine_add"),
                                   (TABLE_HOOK, TABLE_WORD, "fine_lerp"), (YARDS_HOOK, YARDS_WORD, "fine_yards")):
            put(buf, OVERLAY_BASE, site, ppc.bl(site, v4[stub]), expect)
        for site in PAUSE_BUILD_CALLS:
            put(buf, OVERLAY_BASE, site, ppc.bl(site, v4["ghost_menu"]), ppc.bl(site, PAUSE_BUILD))
        put(buf, OVERLAY_BASE, PAUSE_RUN, ppc.bl(PAUSE_RUN, v4["ghost_select"]), ppc.bl(PAUSE_RUN, PAUSE_RUN_TARGET))
        for site, old, new in YARDS_WING_EDITS:
            put(buf, OVERLAY_BASE, site, new, old)
        for site, old, stub in ((BOX_HIDE_HOOK, BOX_HIDE_WORD, "box_hide"), (BOX_TEXT_HOOK, BOX_TEXT_WORD, "box_text")):
            put(buf, OVERLAY_BASE, site, ppc.bl(site, v4[stub]), old)
        if v9:  # golfer 16 (Shy Guy) behaves like Koopa Troopa, with his own files
            for k in range(VTABLE_METHODS):
                koopa = word(buf, OVERLAY_BASE, KOOPA_VTABLE + 4 * k)
                old = word(buf, OVERLAY_BASE, GOLFER16_VTABLE + 4 * k)
                own = FILE_METHODS.get(k, VOICE_METHODS.get(k))
                if own is not None and old != own:
                    raise SystemExit(f"golfer 16's vtable entry {k} isn't the method this build keeps")
                if own is None:
                    put(buf, OVERLAY_BASE, GOLFER16_VTABLE + 4 * k, koopa, old)
    if rel == "B/U/C" and v9:  # the select screen's extra page: Shy Guy's link record
        put(buf, OVERLAY_BASE, GBA_FILL_HOOK, ppc.bl(GBA_FILL_HOOK, v9["link_record"]),
            ppc.bl(GBA_FILL_HOOK, GBA_FILL_TARGET))
        put(buf, OVERLAY_BASE, GBA_DONE_HOOK, ppc.bl(GBA_DONE_HOOK, v9["link_hide"]),
            ppc.bl(GBA_DONE_HOOK, GBA_DONE_TARGET))
        put(buf, OVERLAY_BASE, GBA_ROW_CELLS, GBA_ROW_CELLS_WORD & ~0xFFFF, GBA_ROW_CELLS_WORD)   # cmpwi r31,0
    out = lz.pack(kind, bytes(buf))
    if lz.decompress(out)[0] != bytes(buf):
        raise SystemExit(f"{rel}: repack check failed")
    open(os.path.join(build_files, *rel.split("/")), "wb").write(out)
    print(f"{rel}: {len(OVERLAY_MATRIX_HOOKS[rel])} hooks, repacked {len(raw):,} -> {len(out):,} bytes")


def patch_ids(clean_sys, build_sys, clean_files, build_files):
    boot = bytearray(open(os.path.join(clean_sys, "boot.bin"), "rb").read())
    if boot[:6] != b"GFTE01":
        raise SystemExit(f"boot.bin: expected GFTE01, found {boot[:6]!r}")
    if "--keep-id" not in sys.argv:
        boot[:6] = GAME_ID
    open(os.path.join(build_sys, "boot.bin"), "wb").write(boot)
    bnr = bytearray(open(os.path.join(clean_files, "opening.bnr"), "rb").read())
    if bnr[:4] != b"BNR1":
        raise SystemExit("opening.bnr: not a BNR1 banner")
    long_name = 0x1820 + 0x20 + 0x20  # after short name and short maker
    bnr[long_name:long_name + 0x40] = BANNER_TITLE.ljust(0x40, b"\x00")
    open(os.path.join(build_files, "opening.bnr"), "wb").write(bnr)
    print(f"game ID {boot[:6].decode()}, banner title {BANNER_TITLE.decode()!r}")


def main():
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and sys.argv[i - 1] not in ("--version", "--shyguy", "--shyguy-voice")]
    clean, build = args[:2]
    ppc.selftest()
    proj_sites = projection_call_sites(clean)
    cave4 = anchor_table(proj_sites)
    cave5, v4 = cave5_code()
    cave6, v6 = cave6_code()
    cave7, v7 = cave7_code()
    cave8, v8 = cave8_code()
    v4.update(v6)
    v4.update(v8)
    cave3, v3 = cave3_code(v7["zoom"], v6)
    cave, stubs = build_cave()
    cave2, v2 = cave2_code(v3["aim_place"])
    print(f"cave 2: {len(cave2)} of {CAVE2_SIZE} bytes at 0x{CAVE2:08X} (fast-forward 0x{v2['ff']:08X},"
          f" follow cam 0x{v2['cam']:08X})")
    print(f"cave 3: {len(cave3)} of {CAVE3_SIZE} bytes at 0x{CAVE3:08X} (putt aim 0x{v3['aim']:08X},"
          f" replay prompt 0x{v3['replay_check']:08X}, HUD anchors 0x{v3['anchor']:08X})")
    print(f"cave 4: {len(cave4)} of {CAVE4_SIZE} bytes at 0x{CAVE4:08X} (anchor table, {len(proj_sites)} callers,"
          f" {sum(1 for s in proj_sites if PROJ_CALLERS.get(s))} anchored)")
    print(f"cave 5: {len(cave5)} of {CAVE5_SIZE} bytes at 0x{CAVE5:08X} (quarter steps 0x{v4['fine_step']:08X})")
    print(f"cave 6: {len(cave6)} of {CAVE6_SIZE} bytes at 0x{CAVE6:08X} (see-through setting 0x{v6['ghost_mode']:08X},"
          f" pause menu row 0x{v6['ghost_menu']:08X})")
    print(f"cave 7: {len(cave7)} of {CAVE7_SIZE} bytes at 0x{CAVE7:08X} (zoom view 0x{v7['zoom']:08X})")
    print(f"cave 8: {len(cave8)} of {CAVE8_SIZE} bytes at 0x{CAVE8:08X} (yardage box 0x{v8['box_text']:08X})")
    cave9 = v9 = None
    if SHYGUY:
        import shyguy
        cave9, v9 = cave9_code(shyguy.RECORD)
        print(f"cave 9: {len(cave9)} of {CAVE9_SIZE} bytes at 0x{CAVE9:08X} (Shy Guy's link record"
              f" 0x{v9['link_record']:08X})")
    patch_dol(os.path.join(clean, "sys", "main.dol"), os.path.join(build, "sys", "main.dol"), cave, stubs, cave2,
              cave3, v3, cave4, cave5, cave6, cave7, cave8, cave9)
    for rel in OVERLAY_MATRIX_HOOKS:
        patch_overlay(os.path.join(clean, "files"), os.path.join(build, "files"), rel, stubs, v2, v3, v4, v9)
    patch_ids(os.path.join(clean, "sys"), os.path.join(build, "sys"),
              os.path.join(clean, "files"), os.path.join(build, "files"))
    if SHYGUY:
        for rel, data in shyguy.build(os.path.join(clean, "files"), SHYGUY, SHYGUY_VOICE).items():
            open(os.path.join(build, "files", *rel.split("/")), "wb").write(data)


if __name__ == "__main__":
    main()
