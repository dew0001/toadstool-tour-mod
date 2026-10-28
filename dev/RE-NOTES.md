# Reverse-engineering notes (Mario Golf: Toadstool Tour, GFTE01 rev 0)

What has been worked out about the game's code, for changing the mod later. Addresses are GameCube virtual
addresses. `FUN_xxxxxxxx` names are Ghidra's. "Golf overlay" means `C/L/V`, loaded at 0x80400000 during a
round. Everything here was checked in the running game unless it says otherwise.

## Basics

- **Code:** `main.dol`, plus two fixed-address overlays, both flat images at 0x80400000: `C/L/V` (golf) and
  `B/U/C` (menus). Both are type 1 (no relocations). `A/T/J` (movie player) is type 2.
- **File compression:** Camelot LZSS. Byte 0 is the type, bytes 1-3 the unpacked size; `camelot_lz.py`.
- **Small data:** r2 = 0x802DF480, r13 = 0x802DFA60 (`ghidra_export.ps1` sets them).
- **Units:** game units are **feet**. A 15-unit putt is 15.3 ft on the HUD.
- **Messages:** id = bank << 24 | index. Bank 0 is the only one (0x891 strings, pointer array 0x801431CC,
  bank table 0x802CBEC0). `MSG_LOOKUP` = 0x80022CD0 (id -> string). Strings start with 0x07 + a style digit
  (menus use `\x074\x094`); 0x01 is a line break. `FUN_80022ff0(id, buf, size)` formats one;
  `FUN_80024cfc(textbox, id, 0, 0x20, mode)` shows one in a text box; `FUN_80024f1c(id, x, y, ...)` makes a box.

## Free memory for patch code

All are functions nothing on the disc calls (checked with `find_dead_code.py`: no pointer to them in any file,
no branch, no relocation, no lis/addi building the address). `build_mod.py` checks each one's first word.

| Cave | Size | Was | Holds |
| --- | --- | --- | --- |
| 0x8006EAB4 | 736 | SDK torus helper | v1 widescreen stubs (ortho, matrix, aspect) |
| 0x8003E86C | 1104 | `C_MTX44Concat` | v2 camera data block, fast-forward, follow camera |
| 0x8003AE84 | 1872 | `OSCheckActiveThreads` | v2/v3/v4 putt aim view, replay prompt, message hook, HUD anchors, see-through draw |
| 0x80021C60 | 2200 | printf-style formatter | v3 HUD anchor table (data only) |
| 0x800411B8 | 1076 | FUN_800411b8 | v4 quarter-step power |
| 0x8003CA40 | 684 | FUN_8003ca40 | v4 See-Through setting and pause-menu row |
| 0x800757BC | 704 | FUN_800757bc | v5 zoom view camera |
| 0x80093938 | 648 | FUN_80093938 | v6 yardage box (rounded, fitted to the number) |
| 0x80040CE8 | 600 | FUN_80040ce8 | v7 Shy Guy's link record for the select screen, v9 his animation sound list (`--shyguy` only) |
| 0x8003CDE4 | 540 | FUN_8003cde4 | v9 Shy Guy's power shot: sound, star burst, star colours (`--shyguy` only) |
| 0x80069F4C | 560 | FUN_80069f4c | v11 8th course: hole info, file IDs, golf lookup and resolver stubs (`--course8` only) |
| 0x8006A834 | 464 | FUN_8006a834 | v11 8th course: the course select list (8 entries) and the menu lookup stubs |
| 0x80084B2C | 464 | FUN_80084b2c | v11 8th course: list append, music, sky, name, hole-in-one guard |

Still free (DEAD in `find_dead_code.py`): 0x80053528 (476),
0x80054EFC (424), 0x80057A14 (712, used by the `draws` debug patch), 0x8005DAFC (444, `messages` debug
patch), 0x80090438 (404), 0x80096398 (436). Do NOT use 0x80001800: it is wiped before the first frame.

## Gotchas

- `addi rD, r0, n` and `lwz rD, d(r0)` use **0**, not r0. Never use r0 as a base or addi source.
- A `bl` stub that replaces a plain instruction must keep every register the function still needs, and the
  condition register if a branch after it reads cr0 (check with `dumpasm.ps1`). Replacing a function's first
  instruction with `b stub` is easiest: only argument registers are live there.
- Dolphin's JIT keeps compiled code: writing new instructions into RAM from outside does nothing. Rebuild and
  restart. Writing **data** (settings, tables) live works.
- The camera pointer at 0x802D7E64 also points at other cameras during the frame (the ball-lie picture);
  read it right after the game's own camera code, as the hooks do.

## Player and shot

- **Players:** 0x804ECE70 + i * 0x5204. `CUR_PLAYER` byte 0x804E68FB (bit 0x80 = nobody).
  - +0x1C ball (physics record: +0x9C/A0/A4 position, +0x50/54/58 velocity)
  - +0x24 state: 4 aim, 5 swing, 6 stroke / launch animation, 7 ball moving, 8 stopped
  - +0x30 / +0x34 result-screen timer / length (replay possible while timer < length)
  - +0x3C.. launch-speed table: (shot type, club, step) -> 8 bytes, see Power
  - +0x4F14 pad (+0 held, +4 pressed; A 0x100, B 0x200, Z 0x10, Start 0x1000)
  - +0x4F18 character object (not the model)
  - +0x5168 shot setup
  - +0x5170 model holder; **+0x518C = the golfer's model instance** (what `MODEL_DRAW` gets in r3)
  - +0x51F8 open post-shot menu
- **Shot setup** (one per player; `_DAT_80523cd8` = current):
  - +0x100 held buttons (u16), +0x104 pressed
  - +0x120 main stick X (aim), +0x128 / +0x12C C-stick X / Y (Y switches views), +0x130 / +0x134 analog L / R
  - +0x14C camera turn (springs back), +0x16C zoom amount (see Cameras)
  - +0x184 byte: the game is swinging by itself (replays)
  - +0x1C4 view: 5 normal, 6 zoom ("down the hole"), 7 landing spot, 0xB swing meter
  - +0x1CC shot type, +0x1D0 **power step**, +0x1D4 club (13 = putter), +0x1EC aim point xyz
  - +0x250 steps in a full meter (60), +0x25C its player record
- **Aim ball:** 0x80502734 (what the aim camera works from).

## Power (v4)

- Power is a whole number of swing-meter steps: setup +0x1D0, 5..60 while aiming (`RANGE_TARGET`
  0x80523CBC = the meter's target). The meter counter `_DAT_80523cb8` runs 0..2*max-1 one step per frame;
  pressing sets +0x1D0 to its step. One step = 1/60 of the club's reach (4 yd for a 240-yd driver).
- **Range adjust** in `FUN_80412f6c` (aim update): analog L/R (+0x130/+0x134) tick a step when
  `16 - counter < |stick| * rate` (rate float 0x804DAE88 = 16.0: full tilt = a tick a frame). It then adds the
  step (-1/0/+1, in r10) at 0x80414548, clamps to [5, max], clicks (sound 0x1CC) and sets the target.
- **Shot builder** `FUN_804c6668(player, shot)`: every shot and preview goes through it.
  - `dVar15 = step / 60` scales spin and other inputs.
  - Launch speed (shot +0x48) comes from a per-step table at player + 0x34 + 8 * (type * 0x348 + club * 0x3C
    + step); entry +0 speed, +4 angle. `FUN_8044cee8(setup, shot)` fills the entry for setup's step on first
    use by simulating (`FUN_8044ccd8`, secant search) so carry = reach * step / 60.
  - Real shots (mode 3) take the "spread" branch: effective step = step * (1 + random spread), with the table
    interpolated between two steps. Previews (landing marker, mode 5) and putts read the table at the step.
- **v4 quarter steps** (cave 5, state block at 0x800411B8: player, club, step, quarter, quarter table):
  - `fine_step` (replaces `lbz r0,0x184(r31)` at 0x80414538): the stick moves quarters; the game's step only
    moves when they roll over. Same player, club and step as last time keeps the quarter. Not for the putter.
  - `fine_add` (replaces `frsp f0,f0` at 0x804C68E0): real shots add quarter / 4 to the swung step.
  - `fine_lerp` (replaces `stfs f0,0x48(r31)` at 0x804C6A3C): previews blend the launch speed of the step
    and the next.
  - `fine_yards` (replaces `mullw r9,r9,r0` at 0x8046C964 in the power bar HUD `FUN_8046bc78`): the label
    shows (4 * step + quarter) * reach / 240 yards. Putts' label is a float "%3.1f" path, left alone.
  - The quarter applies only while the target is the step it was set at, for that player and club.
- **Yardage box** (power bar HUD `FUN_8046bc78`, around 0x8046C700): the yellow box spans x = -w..w; then
  texture 0x20 of the HUD set (`DAT_804dfa48`) on a quad at -w-32..-w (the grey "L" wing), texture 0x21 at
  w..w+32 ("R" wing), then texture 0x10 (the pointer below, own matrix), then the number. `FUN_8000c900(set,
  index, 0)` binds a texture; `FUN_8006967c(0x80, 0, 4)` is GXBegin(quads, 4 vertices) followed by FIFO
  writes to 0xCC008000. v5 removes the wings by making both quads zero-wide (`YARDS_WING_EDITS`).
  - The box itself: body quad x -w..w (w = 0x20 yards, 0x2B/0x2E putts) with texture 0x10, u 0.625..0.6875,
    plus 14-px end pieces (u 0..0.3125 left, 0.2916..0.5625 right), all y r27 (-26) .. r29 (0), vertex format
    0 = s16 x, s16 y, f32 u, f32 v. Drawn before the number is formatted.
  - The number: sprintf "%3dy" (yards) or "%3.1fy" (putts; 'y' becomes the ft glyph) into r1+0x1B0; the loop at
    0x8046CA50 draws 16-px cells at x = r21 (-32) + r29 (r29 starts 0, ±16 for putt decimals, += advance).
  - v6 (cave 8, yards only): `box_hide` (at 0x8046C608) sets r27 = 0 so the game's box pieces are zero-high;
    `box_text` (at 0x8046CA40, right before the loop) shifts r29 left half a cell per leading space, binds texture
    0x10 and the box's TEV alpha (0x82FF8), draws a rounded box round the visible cells as a triangle fan, then
    rebinds the digit set (`*0x804DFA4C`, 0) and the digits' TEV alpha (0x8FC8F). `tools/box_sim.py` checks it.

## Cameras

- Camera pointer 0x802D7E64: eye xyz +0, look-at xyz +0xC, fov +0x2C.
- **Aim camera** `FUN_80410838(setup)`, called at 0x80424AF8 in the player update `FUN_80423bbc`.
- **Shot camera** `FUN_80456d1c`, called at 0x80425BB0; modes in `_DAT_8050f128`. Glass-break wipe =
  transition type 4 through `FUN_8000f93c(0x80222988, type)`; -1 = none (v2 removes it at 4 sites).
- **Zoom view** (view 6), amount at setup +0x16C, moved by C-stick Y, kept when let go:
  - < 0: pulls back overhead (down to about -1.7); 0..1: the camera rises and moves forward
  - > 0.98: flies out along the aim line, `(amount - 0.98) * 320` ft, up to the end of the hole (about 3)
  - out on the line the game keeps the camera a few feet over the ground with collision checks every frame
    (`FUN_804379b4`), hence the bobbing and the trees in the way
  - the amount grows about 1.15 a second while the stick is held; the first press jumps it to about 0.13
  - v4 kept the game's spot on the line, rode high and pitched down: Andrew found it useless (just ground).
    What he wants (approved in v5): start behind the ball looking down the line, then go up and toward the
    landing zone so you can see where the ball is going. A first v5 draft moved linearly in t and blended
    from the game's camera; the first press then lurched the camera out over the fairway ("the zoom issue
    happens at the beginning").
  - v5 `zoom` (cave 7, called by the cave 3 aim stub after the game's camera): t = amount / 1.2; along the
    line smoothstep(t) from 25 ft behind the ball to 90 ft short of the landing spot; height ease-out t(2-t)
    from 12 ft over the ball to 75 ft over the spot (both scaled down for short shots); always looks at the
    landing spot (setup +0x1EC). The camera glides there (20% a frame) from last frame's camera; on other
    frames the stub just remembers the game's camera, so entering the view starts from the normal view.
    `ZOOM_TUNING`; `tools/zoom_sim.py` checks the assembled code against this.
- v2/v3 follow camera and putt views: `cave2_code`, `cave3_code` in `build_mod.py`; tuning in `CAM_TUNING`.

## Rendering (v4 see-through golfer)

- `MODEL_DRAW` 0x800072C8 `(instance, matrix, ...)` draws a model; `FUN_80006524` draws skinned meshes.
  `FUN_8000f190(holder, matrix, ...)` draws `holder + 0x1C`. Characters come through the holder at player +0x5170.
- GX: `GXSetBlendMode` 0x8006E154, `GXSetZMode` 0x8006E23C, `GXSetChanMatColor` 0x8006AF08 (color by pointer),
  `GXSetChanCtrl` 0x8006AFE8, `GXSetTevColorIn` 0x8006D6B8, `GXSetTevAlphaIn` 0x8006D704, `GXSetAlphaCompare`
  0x8006DAF0, `GXSetTevOrder` 0x8006DBA0, `GXSetNumTevStages` 0x8006DD18, `GXSetNumChans` 0x8006AFC4,
  `GXSetCullMode` 0x8006982C, `GXLoadPosMtxImm` 0x8006FE10, `GXSetProjection` 0x8006FCC0, `C_MTXOrtho` 0x8003E684.
- Character materials (e.g. `FUN_8002b4d4`): alpha channel from the material colour register, TEV alpha =
  raster alpha x texture alpha, alpha test passes anything > 0. So lowering the material colour's alpha and
  blending makes the model see-through.
- v4 hooks (cave 3): `ghost_draw` on `MODEL_DRAW`'s first instruction wraps the shooter's golfer draw while
  putting (states 4-6, putter, setting on); `color_hook`, `blend_hook`, `zmode_hook` on the GX entries
  scale alpha by `GHOST_ALPHA`, force source-alpha blending and turn depth writes off during that draw, and
  remember the game's last blend and depth modes, which are put back afterwards.
- v10: the see-through golfer is drawn twice, first for depth only (blend zero x source + one x what's there,
  the materials' own depth writes), then see-through over that depth without writing it, so only its nearest
  surfaces show (Shy Guy's legs, belt and the back of his mask showed through his robe). `GXSetColorUpdate`
  0x8006E1E4 / `GXSetAlphaUpdate` 0x8006E210 can't do the first pass: the scene setup `FUN_8001fc0c` turns colour
  writes back on mid-draw. The grid, cup and ball still show through him (they're drawn over the golfer).

## Characters (v7 Shy Guy)

Shy Guy is a 17th golfer, not a replacement: he is golfer 16, the first of the 8 Game Boy Advance link golfers
(16-23), built like Koopa Troopa (golfer 15) with his own files.

- **Koopa Troopa's files:** golfer models `C/V/S` and `C/V/Z` (same skeleton; Z has 5 fewer face bones and no eye
  expressions; both are loaded for a round), body texture bank `C/V/R` (type 1), in-round face `C/V/U` (64x64
  RGB5A3), emblem and name plate `C/V/T` (two 256x128 CMPR on white). Select screen: its own lighter Koopa
  `B/V/D` (77 bones, slightly different bind pose, textures inside the file), the grid of 16 faces `B/U/P`
  texture 0 (464x116 CMPR, 58x58 each, 8 x 2, Koopa 6th in the top row) and the row of 16 faces `B/U/M`
  texture 25 (1024x64 RGB5A3, 64x64 each, used for the 1P badge). Each character has a group like this
  (Mario: `C/R/T`, `C/S/A`, `C/R/U`..`Z`, face `C/R/V`).
- **Golfer 16's files:** models `C/W/B` and `C/W/E`, bank `C/W/A`, face `C/W/D`, emblem `C/W/C`, select-screen
  model `B/V/K`; on the extra page `B/U/P` texture 1 (cell 0) and `B/U/M` texture 39 (slot 0). The extra page's
  "Game Boy Advance" label is `B/U/M` texture 2 (140x30 CMPR) and the Game Boy over each record texture 38 (90x54);
  the stats card's words are textures 0 and 17-27.
- **Link records** (the save data's Game Boy Advance golfers): 4 at 0x80234040 + 0x284 x slot, each two golfer
  entries of 0x2C (golfer 16 + 2 x slot + entry +0x1C) and the record name at +0x268 (non-empty = present;
  +0x27C a version byte). Entry: +0x00/+0x10 name, +0x1A drive (u16, yards), +0x1C body, +0x1D handedness,
  +0x1F..+0x24 the six stats, +0x28 the golfer code it borrows per-character effects from in a round
  (`FUN_80459128` uses it when the golfer code is over 15; Koopa 15). The select screen lists them on an extra page,
  Down from the grid's bottom row
  (`_DAT_8044bab0` = 1): `FUN_8040aad4` fills its 8-golfer list at 0x80445B2C (-1 = none) between
  `bl FUN_80410000` at 0x8040AB98 and `bl FUN_80410140` at 0x8040ACC4, and `FUN_80405b30` draws its cards
  (`cmpwi r31,1` at 0x80405F8C: two cells per record). v7 writes Shy Guy's record into slot 0 before the fill
  (cave 9, `shyguy.RECORD`: his name, drive and stats), hides its second golfer after it, and draws one cell per
  record. A round copies the chosen golfer's data to 0x8017573C and 0x804E5D74; the drive comes from entry +0x1A
  (`FUN_8044c344`).
- **Stats:** the 16 golfers' (and their Star versions') are in the select screen overlay at 0x80445B50, 32 entries
  of 10 bytes: index, character code, drive (u16), then the six stats in the link entry's order: height (-6..6,
  the card's trajectory picture in 5 bands), curve direction (0/1, mirrored by handedness), curve (0..6: straight,
  slight, big), impact, control, spin. The bars (the card is drawn by `FUN_80406ec8`) show value + 10 of 20 segments;
  the roster runs impact 0..4, control -5..4, spin -6..6, and longer drives come with narrower impact and less
  control. Character codes: 0 Mario, 1 Peach, 2 DK, 3 Yoshi, 4 Waluigi, 5 Koopa Troopa, 6 Wario, 7 Daisy, 8 Luigi,
  9 Petey, 10 Boo, 11 Diddy, 12 Birdo, 13 Bowser, 14 Bowser Jr, 15 "nisemario" (the sound group names);
  0x80445D34 maps them to golfer codes (Koopa 5 -> 15).
- **Golfer objects in a round:** `FUN_804074a8(code)` makes each golfer: Koopa (15) in `FUN_804bd45c`, vtable
  0x804CA3C8; golfer 16 in `FUN_804c7220`'s default case, vtable 0x804CC948. Both are 0x1E4 bytes on the same
  base constructor `FUN_80407590`. The vtables have 47 methods; [22], [23] and [24] return the file IDs of the
  golfer model, the bank and the second model, [25] the character data. Golfer 16's own methods are a child's
  (with Koopa's files they draw see-through and give a 30-step meter), so v7 copies Koopa's 47 into golfer 16's
  vtable except [22]-[24] (`GOLFER16_VTABLE` in `build_mod.py`). The voice methods start fixed sound IDs of the
  golfer's own voice set: [42] ball near the hole (`FUN_80420404`), [43] swing (power gauge at the top,
  `FUN_80421154` / `FUN_80423bbc`), [44] nice impact (state 6, inside the impact window), [46] chirp 0-7 (another
  player presses a button while the shooter lines up, `FUN_8041e438`). Koopa's ask for his set (0xCC-0xD6), which
  isn't loaded for golfer 16, so v8 keeps golfer 16's own four (0xAF, 0xB1, 0xBB-0xC2, 0xC3: its set, "neil").
  These four slots are the only per-golfer voice events in every class; nobody has a voice for a bad shot (an
  out-of-bounds shot only plays common sounds, 0x251 / 0x231 from `FUN_804c4b40`).
- **Animation sounds:** method [18] returns (r3) the number of 8-byte entries and (*r4) a list of (u16 animation,
  u16 frame, u16 sfx, u8 0, u8 volume); `FUN_8040bee4` plays an entry's sound when the golfer's current animation
  (object +0x194) passes that frame. Animations 0-4 are the end-of-hole reactions, best to worst (a birdie is 1,
  +5 is 4), carrying the golfer's own voice lines (Koopa: 0xCC-0xD6 in 0x804D8A90, 42 entries; golfer 16: one
  long line per reaction, 0xB6-0xBA, in 0x804D95F4, 26 entries). Animation 5 (Koopa's runs about 6 seconds) plays
  sounds from the golfer's special shot set (Koopa's "shnokonoko" 0x165-0x168, see Sound); a power shot doesn't
  play it.
  Shy Guy moves with Koopa's animations, so v9 gives golfer 16 a method in cave 9 returning Koopa's list with his
  voice IDs in place of Koopa's (`shyguy.ANIM_SOUNDS`).
- **Lefty and Star** (select screen `FUN_8040b9ec`, pad words at 0x8026BB5C + 0x38 x port: +6 repeating
  directions, +0xA new presses): L (0x40) flips the player's lefty word 0x8044BA90 + 4 x pick, R (0x20) the Star
  word 0x8044BA68 + 4 x pick when the golfer's bit is set in the halfword at `*0x80447F90` = 0x8022A3CC (the
  players-unlocked flags, all set by the mod); both only on the grid (not the extra page). The pick ends up in
  0x80176044 + player (bit 0 Star, bit 1 lefty). Dolphin sets L/R only from the mapped buttons, never from the
  analog travel, so the mod's layout gives them the stick clicks (v12).
- **End of round experience** (`FUN_80400a64`, golf): for each player whose golfer code is over 15 (player +0x51EF)
  and who scored points (+0x2C), if the link record's name (+0x268) matches the player's name (0x804E5D74 + 0x2C x
  player) the points go into record +0x278 and the round ends on the experience screen (`FUN_80485818(.., 6, ..)`).
  v12 makes the test `cmplwi r11,0x10` (0x80400AB8) so Shy Guy, golfer 16, gets none.
- **Select screen call:** `FUN_8040b56c` plays one common-set sound per golfer when picked (0x26F Koopa ... by
  character code), and on the extra page 0x270 for even link golfers (golfer 16), 0x271 for odd ones. Landing the
  cursor on a golfer plays its idle line ("taiki"), `FUN_80013108(golfer code)`: 0x258-0x269 for the 16, 0x263
  golfer 16, 0x25E golfer 17, also common-set sounds. v10 gives golfer 16 his lines in both (`shyguy.MENU_VOICE`).
- **Putter at address:** the ball sits in the middle of the mallet putter's head at address for Koopa too; the
  golfer's place by the ball isn't per character code, so Shy Guy stands exactly where Koopa does.
- **Power shot effect:** shot type (setup +0x1CC; B steps through the types the shot allows, e.g. 1 Normal and 0
  Power off the tee, 2 Approach near the green, while power shots last: player +0x5200 byte) 0 is a power shot.
  At impact `FUN_804598c8` sets `_DAT_8050f1ac`: 2 when the launch speed is over `DAT_804def78` and setup +0x22D
  is set (`FUN_80412f6c`: power within a step of the top and an impact error, setup +0x1AC copied to
  `_DAT_80523cac`, under 2), 1 for the speed alone, else 0. Then by golfer code (`_DAT_8050f1b0`; link golfers
  their record's +0x28, `FUN_80459128`, which also loads an effect model `C/O/C`-`G` for codes 1, 2, 3, 12, 13):
  an impact sound from the common set at 2 only (jump table 0x804DF01C for codes 0-15: Mario 0x217, Koopa 0x21F;
  over 15 none), and always a particle burst (jump table 0x804DF05C: codes 7, 8, 15 and over 15 the plain type-1
  glow at 0x80459DD4; 0 and 6 128 stars at 0x8045AB94, type 0x14 for 0, 0x29 for any other); `FUN_8045bb30` adds
  more at 2. Nothing else that reads the code tests for 15 or 16.
- **Effect particles:** 0x400 of 0x3C at 0x8050F1B8 (+0 position, +0xC velocity, +0x28 spin, +0x30 type, -1 =
  free, +0x34 age), handed out by `FUN_8045975c`; their textures are `C/N/W` (42, loaded by `FUN_80459254`).
  `FUN_8045e8c0` draws types 1 (texture 0x19, an orange glow), 0x23 (0x28), 8 and 0x19 (0x11 tinted red), 0x11 and
  0x12. `FUN_8045f6c4` (called by `FUN_8046108c`, which sets additive blending, `GXSetBlendMode` 1, 4, 1) draws
  stars, types 0x14, 0x18, 0x28 and 0x29, with texture 0x13 (RGB565: red and green, no blue); colour = the texture
  through TEV swap table 1 (`GXSetTevSwapModeTable` at 0x8045F9DC, r31 = the particle, r27 = its index: 0x14 R G B,
  0x28 R R G, 0x29 G G R, 0x18 eight mixes by index), alpha = the texture's (255) x the fade.
- **v9 Shy Guy's power shot** (cave 10, `build_mod.py`): his record's +0x28 is 16, his own code. The two switches'
  `bgt` (codes over 15) go to the cave: at 2 he plays his "SsHit" line (0xBA, his voice set) and Mario's 0x217;
  his burst is Mario's stars (so type 0x29). The star draw's swap call goes through the cave too: on golfer 16's
  shots every star sets its blend first, and his stars come out white (R R R, additive) at odd indices and red
  (R B B with the red channel as alpha, blended over with 1, 4, 5) at even ones: red added to the grass turns
  orange.

## Sound

- **MusyX** (Factor 5): main.dol's group table at 0x80137308, 37 entries of 0x14: name, first file ID, sfx count,
  first sfx ID, group ID. 0-15 the golfers by character code, 16 "neil" and 17 "ella" (Game Boy Advance golfers),
  18 "menu", 19-36 "sh" + name (each golfer's special shot set, golfer 16's "shneil"; a power shot plays none of
  them). `JVoiceLoad1` (`FUN_80012844`, group index) loads a group's
  four files, ID, ID + 2, +4, +6: pool, project, sample directory, sample data (e.g. Koopa Troopa "nokonoko"
  `C/V/V`-`Y`, golfer 16 "neil" `C/Y/Q`-`T`). A round loads each player's group by golfer code (golfer 16 -> 16).
  File ID = 2 x (676 a + 26 b + c) for path a/b/c (letters from 0), +1 for some.
- Sounds play through `FUN_80011b88(id, ...)`, `FUN_80011c40(x, y, z, id, ...)` and `FUN_80011d74`; an ID in no
  loaded group (and not a common sound, `FUN_80011a48`) is dropped silently; then MusyX's sfx start `FUN_8007337c`.
  `voiceFXcall` `FUN_800120a8(group, id)` is another path (not used by the golfers' voices).
- File formats and DSP ADPCM: `musyx.py`. Neil's set: 21 sounds 0xAF-0xC3, one macro and one sample each,
  22050 Hz.
- The common set (`B/T/M`-`P`, sfx 0x19D-0x27F) is loaded everywhere: menus, select-screen calls, swing, ball,
  crowd and result sounds.
- Find what plays: `tools/debug_patch.py` `plays` (every ID asked of the three calls and who asked, `sfxlog.ps1
  -Pairs -At 0x80057A14`), `sfx` (every ID MusyX starts), `voices`; Dolphin's `[DSP] DumpAudio = True` records the
  mix to `Dump/Audio/*_dspdump.wav` for checking a sound by correlation. `tools/swing.ps1` swings on the meter's
  own target (reads counter 0x80523CB8 and target 0x80523CBC), so hands-off tests can putt out (on Pebble
  tee shots in the v12 tests it read a target of 117 = 2 x max - 1 and timed out with the counter stopped at 58;
  those tests pressed A on timings instead);
  `tools/power_swing.ps1` swings a power shot and lists the burst's particles as the ball leaves.
- **Model format** (`model.py`): type-2 module; root (magic 0x0131A313) found through the code stub's HA16/LO16
  relocations at +20/+24. Meshes (0x3C): +6 texcoord sets, +7 textures, +8 texture entries (4 bytes: flag short,
  texture, material), +0x28 groups, +0x2C -> groups, +0x34 shader, +0x38 part (1 = body, 3..11 = clubs). Groups
  (0x38): +0 flags (bit 0 rigid, bit 1 list of display lists), +4 matrix count, +8 up to 10 bones (PNMTXIDX = 3 x
  slot, one byte per vertex when the count isn't 1), +0x30 list count, +0x34 -> entries (0x20: list, size,
  model-space bounding box). **Rigid groups index the root's +0x08/+0x1C/+0x30 arrays and their positions are
  in model space, bind pose**: the draw (`MODEL_DRAW`, `FUN_80006524`) loads each bone's skin matrix (animated
  world x the bone's +0x04 inverse bind) into the palette, except for bones with bit 0 set at +0x5C. Skinned
  groups index a per-instance buffer the CPU fills every frame. Triangles are clockwise (the OBJ's are the other
  way). Each list ends with three `08 10 00000001` commands, then zero padding to 32 bytes.
- **Texture sets** (models' root +0x8C and texture files, magic 0x0020AF30): count, then (header offset, 0)
  pairs; header 0x24: height << 16 | width, format, data offset (high bit set = in the character's bank file,
  else from the set's start), wraps, filters, max LOD << 8. CMPR mip levels under 8 pixels still take a 32-byte
  tile. Dolphin's CMPR blends are 5/8 + 3/8.
- **Names and lines** live in `main.dol` message banks with per-message u32 offset tables (e.g. the name list's
  table at file 0x1406A8), so a shorter text padded with NULs is safe. Golfer 16's name comes from its link
  record, so v7 changes no messages.
- **HD texture pack:** NickPancakes' pack replaces textures by XXH64 of their data (`tex1_WxH_hash_fmt`), so any
  picture the mod changes falls back to the game's resolution, including the other faces in `B/U/P` and `B/U/M`.
- `shyguy.py` builds `C/W/B`, `C/W/E` and `B/V/K` from Koopa's `C/V/S`, `C/V/Z` and `B/V/D` (`bone_map`: the bone
  with the matching parent nearest its bind position), and `C/W/A` from `C/V/R` with the OBJ's texture at the
  start. In each model the body meshes get a 32-byte NOP list and one gets the OBJ as two rigid groups (pelvis,
  legs, feet; arms), with positions/normals/texcoords moved to the end of the module after copies of Koopa's (so
  the clubs keep their indices). The body is 90% size and set back 1.2 units because Koopa's swings bring his
  hands 2 units in front of his hips, inside Shy Guy's robe; the arms are moved onto Koopa's arm line. Golfer
  16's files grow by about 60 KB each (`C/W/B` 504 KB packed, Koopa's `C/V/S` 443 KB). The patch names Koopa's
  file as each one's `base` (`make_patch.py BASE`), so Koopa's data goes in as copies.

## Mario Power Tennis (v9 Shy Guy's model)

- **Disc:** GOME01, the maintainer's own (`mpt.Disc` reads .iso and .ciso). Also Camelot's: the same A/A/A file
  names, LZSS types 1 and 2, relocatable modules and texture sets. The characters' names are in `default.dol`
  (about 0x212F38: mario, luigi, peach, daisy, yoshi, wario, waluigi, donkey, koopa, didy, heiho, ...); their
  models are `B/G/F` onwards in that order, so Shy Guy ("heiho") is `B/G/P` (132 bones, 26 meshes, 24 textures).
  His voice set is `B/W/D`-`G`.
- **Model format revision:** root magic 0x0131A5B5 (Toadstool Tour's 0x0131A313), the same root layout, but meshes
  are 0x40 bytes and bones 0x6C, and the array format words lack the top bit (comp = (w >> 5) & 7, frac = w &
  0x1F). Mesh +0x30 is the RGBA colour of untextured meshes. `model.py` reads both (`Model.mpt`).
- **His arrays:** the rigid positions (+0x08) hold fewer entries than the count field says (1,136 of 2,450): read
  up to the next array the module points at. Skinned groups index the skinned positions (+0x10) up to the last
  skin block's end (root +0x54, blocks of 0x20, +0 = end; bone list at root +0x4C), past the count field. Entries
  2,123-2,206 (his mouth) are zero in the file: the game fills them every frame from the face table at root +0x5C
  (4 bytes, then positions in the same format), checked against a RAM dump.
- **Texture data offsets count from the texture set's start** (0x40 in `B/G/P`), not the module's: v9 read every
  texture 64 bytes early, so each began with the previous one's two smallest mip levels (a black or brown block in
  its corner) and was shifted 16 texels; his hood rim, shoe tops and ankles came out black and brown. Each mip
  chain is largest level first, levels under a CMPR block padded to 32 bytes.
- **Meshes:** body 3-16 (mask 3, eyes 4/5, robe and sleeves 6, hood strap 7, belt 8 and buckle 12, legs 9, hood
  10, robe hem 11, shoes 13/14, ankles 16); the rest are his racket, a ball, and a leaf skirt and feathers for his
  special shots. Mario Power Tennis draws his eye whites black; `mpt.py` sorts mesh 4 by position into eyes, blush
  and the inside of his mouth.
- **The port** (`mpt.shy_guy`, `shyguy.rig_mpt`): one 256x256 atlas of his textures at their own size, each
  padded 8 texels on 4x4 CMPR blocks and the free space filled with the nearest texture's colours (black space
  darkened the textures' edges at small mip levels); legs stay where they are on Koopa's leg bones and each shoe
  is whole on the ankle; the sleeves (all on his bones 17/24) move onto Koopa's arm line with the hand on Koopa's,
  except the flare where they meet the robe (|x| under `MPT_SLEEVE`, 2.5 units tall), which rides the pelvis: on
  Koopa's upper arm it swung far out through the body in the swing; the rest rides the pelvis, 90% size and set
  back 1.2 units like the OBJ was.

## Courses (v11 8th course)

Full write-ups in `dev/course/notes/`: `courses.md` (course codes, tables, menus, saves, text), `holedata.md`
(the hole table and the camera, ring and coin files), `collision.md` (the collision file and surface codes).

- **Course codes:** 1-7 the seven courses, 8 and 9 cut 3-hole sets no menu reaches, 10 the practice holes. The
  menu's course index is code - 1; the code goes to the round through the setup block (main.dol 0x80176079).
  v11 makes the new course code 8.
- **Hole info** (par, yards, back-tee yards, course, hole number, Ring Attack group; 141 x 12 bytes): golf
  0x804CCD60, an identical copy in the menu at 0x80444E60. `FUN_80406f90(id)` finds an entry by hole ID,
  `FUN_80407048(course, hole0)` gives the hole ID (the hole order); the menu's copies are `FUN_8040094c` and
  `FUN_80400a04`. Neither table can grow, so v11 keeps its 18 entries (IDs 1101-1118) in cave 11 and hooks the
  four lookups' first instruction.
- **Hole files:** golf 0x804DCF18, 9 rows x 18 x 0x20: +0 model, +4 collision, +8 texture bank (unused),
  +C flyover camera, +10 Ring Attack rings, +14 Coin Attack coins, +18 hole ID, +1C debug name. The resolver
  `FUN_80443e14` searches it by ID right after `bl FUN_80407048` (0x80443E68); v11's stub copies its hole's entry
  into row 8 col 17 (0x804DE338, never used) and sets row 8 / col 17.
- **Hole model** (+0, type 2): header stubs +8 terrain root, +C object count, +10 object table (0x10 each: model
  root, instance count, instances of 0x2C, name). Roots are 0xD0 bytes like a character's; course models have
  colours instead of normals, and each mesh record's +0x38 is the surface code it shows, +0x34 the draw pass.
  Props (trees, tee markers) are whole models with their own texture sets. One model may hold at most about 300
  prop instances in all (retail tops out at 321; 772 hung the game). Positions are s16; a game unit is 32 ft.
- **Water in hole models:** mesh record +0 is the layer (0 ground, 1 water and plants), +4 the flags (0x40000101
  opaque, 0xC0000101 blended by vertex alpha). The sea's surface is surface code 0x18 on layer 1, pass 3, and is
  always see-through: Blooper Bay's has vertex colour (111,183,159) with alpha 0 at the shore up to 95 offshore
  (Cheep Cheep Falls': (159,159,159), alpha 95), over a seabed on layer 0 (code 0x05, beach sand, tinted the same
  teal in the shallows and black out deep). An opaque grey-vertex 0x18 mesh shows as a flat grey plane on either
  layer. Foam is code 0x19 on layer 1, pass 3: white (255,255,255) vertices, blended (0xC0000101), alpha fading out
  to sea. Pond and river beds are code 0x05 on layer 0 (plain ground drawing).
- **Collision** (+4): see `collision.md`; per-triangle surface code (bits 0-7) and zone (bits 13-14: 2 OB,
  3 penalty). At most 65535 triangles per mesh. The layout block holds the two tees (regular, back), four pins and
  the light direction.
- **Course select** (menu `FUN_80413910`): the list is 7 x 0x2C at 0x8044BC40 with live screen state right after
  it; v11 moves it to cave 12 (27 lis/addi pairs, two of the lis serving two addi each; 0x80412658's r20 is reused
  at 0x80412DB8 by the icon draw) and appends index 7 at 0x804140B0 in Stroke, Match (not Character Match), Skins
  and Practice. Icons: textures 0-6 of `B/W/R`; index 7 shows texture 7, the 106x106 star medallion, which v11
  redraws as the course's icon. Preview movie: indexes past 6 play the file at 0x8041445C (now Blooper Bay's).
- **Course name:** message 0xA8 + index (0xAF "Shot Practice" for index 7). v11 swaps 0xAF for its own message
  0x7FF0 at the six places that add the base: menu 0x80414D14, golf 0x8048C77C, 0x804B57B0, 0x804B5814,
  0x804B5BC8, 0x804B5E04 (the hole intro banner), and the message hook answers 0x7FF0.
- **Sky:** the hole loader picks the sky dome and backdrop by the hole's course byte (0x804462E8..); course 8
  fell through to Lakitu Valley's. v11 sends it to Blooper Bay's (0x804463B4) from the test at 0x804463AC.
- **Emblem** (the medallion on the hole intro banner and the pause menu): golf table 0x804D5F9C, file IDs by course
  code 0-11 (entry 8 was Lakitu Valley's C/O/U, 3473). v11 points entry 8 at its own `E/S/B`, a copy of C/O/U's
  106x106 RGB5A3 texture set holding the course select icon. `FUN_8048c354` loads it by the round's course byte
  (0x804E68F4) into 0x80523E4C; Shot Practice's three lessons load 0x12BB/D/F instead. The square icon at the top left
  of the hole intro is not the emblem: it is the mode's icon, file IDs at 0x804D5FF8[mode slot 4-15].
- **Music:** main.dol `FUN_80011a94(situation, course)`, a 16 x 7 song table; v11 plays Blooper Bay's for 8.
- **Saves:** the hole-in-one mask store (golf 0x804682F4) would wrap course 8 onto Lakitu Valley's; v11 skips it.
- **Auto-aim** (v12): every new shot starts from `FUN_804abd70(setup, player)`: yaw (setup +0x1D8) at the pin, then
  by case: pin in reach (2) the power is fitted; out of reach (3, 4) it searches the hole's collision for a landing
  spot. `FUN_804a7874` classes every collision triangle by its surface's score (method [11], called at
  0x804A79EC / 0x804A7A18): codes 0x18 and 0x2E -> 4, score under 0x46 -> 9 (avoid), under 0x50 -> 4, else 0
  (a target: fairway, fringe, green); `FUN_804a7344` walks them. Nothing marks which hole a triangle belongs to, so
  on the 8th course, whose hole files hold their neighbours' fairways, it aimed down other holes. v12 marks another
  hole's fairway, fringe and green with attribute bit 8 (0x100; bits 8-12 go unread, the lie and the rest take the
  low byte) and a stub on 0x804A7A20 (`cmpwi r3,0x4f`, r27 = the triangle record + 0xC) scores them 79 for the
  search only: they still play as fairway, fringe and green.
- **New disc files:** the game builds a file's path from its ID (`FUN_8001bbf0`: ID / 2 in base 26 as "X/Y/Z"),
  so the course's files live under a new top-level folder `E` (IDs from 5408). `TTMod.Build` appends them to the
  file table (0x20440, free space up to 0x28000) and updates boot.bin's FST size.

## Menus

- **Post-shot menu** `FUN_80483564(menu, type, pad)` / `FUN_804835f4`: +0x46 option count, +0x50/+0x54/+0x58
  option codes; text = message 0x129 + code (0 Continue, 1 Do Over, 2 Next Hole, 3 Main Menu, 4 Mulligans,
  5 Start from the Beginning, 6 Select Character, 7 Continue, 8 Next Lesson, 9 Main Menu). Codes < 10 are
  selectable. v3 opens type 4 with code 7 shown as "Watch Replay" (message hook) when B is pressed.
- **Pause menu** (Start during a round), `FUN_80475504` runs it, `FUN_80473918` (called at 0x80473194 and
  0x804737EC) fills its list: item codes at 0x80523F48 (6 slots), count at menu +0x116, cursor +0x110, row
  text boxes at +0x20 + 4 * row, help box at +4. Row text = message 0x10D + code, help = 0x118 + code:
  0 Scorecard, 1 Rules, 2 Controls, 3 Give Up, 4 Save, 5 Start Hole Over, 6 Next Hole, 7 End Game,
  8 Main Menu, 9 Change Weather, 10 Start Game Over. Icons from the table at 0x804D5FCC[code] (codes 0-10 are
  menu icons). Thirty frames after A, the code at 0x80476E48 runs the cursor item through a jump table
  (codes above 12 go to 0x80477894, the "nothing" exit).
- v4 adds code 10 as "See-Through: On/Off" when the list has room and doesn't use 10 (`ghost_menu` on both
  `FUN_80473918` calls; `ghost_select` on the `bl FUN_80019bf8` at 0x80476E48 toggles and re-shows the texts,
  then returns to 0x80477894). The message hook supplies its texts while it's listed.

## HUD (v3)

- `GXSetProjection`'s 2D path stores the x offset with `stfs f0,0x488(r13)` at 0x8006FCF4 (dirty bit 0x800 at
  r13+0x554). v3 shifts it a quarter screen left or right per caller (return address), from a table in cave 4.
- Some HUD functions draw both sides, so v3 re-anchors mid-function (`HUD_SPLITS`): pin tracker 0x8042CCC4 ->
  ball-lie picture `FUN_8042dab8`; hole text `FUN_804306d8` -> % box; flight distance counter.

## Other

- Boot: `FUN_8000de5c(1, 8)` plays logos then the opening movie (loop at 0x8000E120); v2 skips the loop.
- Club Slots item reel: 32 ints at 0x804E1A10 (4 = double points), messages 0x56D-0x571.
- B replay: `FUN_8041e8e8` sets 0x805052A8; result handler `FUN_8041f3f4` replays while it's set.
- Golf scene update `FUN_80403b0c` calls the player update `FUN_80423bbc` (shooter at 0x80405620).

## Testing workflow

The maintainer's layout (paths the tools default to, relative to the folder above the repo):
`disc\` clean extracted disc, `build\` build tree, `unpacked\` decoded files, `tools\` Ghidra + JDK,
`mod\ghidra_proj\` Ghidra projects (dol, golf, menu), `mod\test-profile\` a separate Dolphin user folder
with keyboard controls. Set `TTMOD_ROOT`, `TTMOD_DOL` or `TTMOD_PID` to point elsewhere.

1. Build into the build tree: `python -I dev\build_mod.py <disc> <build> --version N`.
2. Run the test Dolphin **hands-off** (never the player's own Dolphin, and never let Dolphin update itself):
   `dev\tools\test_dolphin.ps1 start [-Image <main.dol or .iso>]`. It starts Dolphin on its own hidden Windows
   desktop (`TTModTest`), so no window ever shows on the player's screen or takes focus, switches the test
   profile to the virtual controller (`dsu_pad.py`, Dolphin's DSU Client on udp 26760), turns on background
   input and hotkeys without focus (`HotkeysRequireFocus = False`), maps the screenshot hotkey to the pad's PS
   button and forgets the saved game-window position (Qt.ini `[renderwidget]`). It sends no keys and moves no
   windows. Rendering and screenshots work on the hidden desktop. (Don't go back to an off-screen window on the
   normal desktop: the test profile's game settings start fullscreen, and Dolphin restores its last window
   position over the configured one, which once covered the player's screen.)
3. Drive it: `python -I dev\tools\dsu_pad.py press Cross` / `seq "Share 200; wait 3000; Cross 200"` /
   `stick L 0 1 300` / `status`. Mapping: A = Cross, B = Circle, X = Square, Y = Triangle, Z = R1,
   Start = Share, L/R = L2/R2, main stick = left stick, C-stick = right stick, D-pad = Pad N/S/E/W.
   Look: `test_dolphin.ps1 shot` prints a screenshot path (a 960-wide `.small.png` copy). `stop` closes it.
   To hand the test game to a person (only when they ask): `test_dolphin.ps1 play` starts it on the normal
   desktop with keyboard controls (keys: x = A, z = B, c = X, s = Y, d = Z, i/k/j/l = C-stick, q/w = L/R,
   arrows = main stick, Enter = Start).
4. Menus to a round: Start, A, A (1 Player), A (Mario; Pad E five times = Koopa Troopa; Pad S twice = Shy Guy on
   the extra page), Pad E, A (Character Match; Pad E three times = Stroke Play), A, A (Novice), A (course), A
   (Yes), then A. About 3 s between menu steps, 8 s for the course to load.
   Shortcuts: keep writing the setup block while the round loads (about 6 s from the last A): the hole order
   (0x80176060, 18 bytes) picks the first hole, 0x8017607C the number of holes (1 = a one-hole round). Writing
   the ball record's position (+0x9C, feet; collision vertices are x32) and zeroing its velocity (+0x50) every few
   ms for 1.5-3 s while a shot flies drops the ball on that spot, so a test can land on a given surface or in the
   cup (the pin the auto-aim uses: 0x804E6864/68/6C). The ball record's +0xB8 is the surface code it rests on.
5. Tools in `dev\tools` (PowerShell 7 or 5.1):
   - `gcmem.ps1` (dot-source): `[GCMem]::Open(pid, 'GFTEMD')`, `U8/U32/F32/W32(address)`, `ReadGC(address, n)`;
     finds Dolphin's emulated RAM by the game ID and the 0x01800000 size at +0x28.
   - `aimstate.ps1`, `power.ps1`, `zoomtrace.ps1`, `camtrace.ps1`, `inputtrace.ps1`, `chardump.ps1`: read and
     trace the shooter, power, cameras and inputs.
   - `memfind.ps1 <hex word>`, `memstr.ps1 <text>`, `memseq.ps1 <hex bytes>`: search all of RAM.
   - `msgids.ps1`: message ids whose string is at given addresses.
   - `hud.ps1`, `hudcrop.ps1`: the v3 HUD anchor table (list, reset, pin a caller and crop screenshots).
   - `debug_patch.py <build>\sys\main.dol draws|messages|files`, then `drawlog.ps1` / `msglog.ps1` /
     `filelog.ps1`: which code draws which model (with live skip switches), which code shows which message,
     which disc files get opened (in order).
   - `dumpasm.ps1 golf out.txt 0x804c6668:0x100 ref:0x804dae88`: disassembly and data references from Ghidra.
   - `dol_words.py dump|callers`, `dol_strings.py`, `find_bl.py`, `find_text.py`: static searches.
   - `zoom_sim.py`: runs the assembled zoom camera on a tiny PowerPC interpreter and checks it against the
     formula, no Dolphin needed (handy when the test Dolphin can't be on screen). Extend it for other stubs.
6. Don't drive tests with screen clicks or key presses (computer use): the player asked that tests never take
   over their PC, and everything above works in the background. `test_dolphin.ps1 stop` only closes the test
   Dolphin (by the pid in the test profile), never the player's own.
