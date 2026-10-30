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
| 0x8003E86C | 1104 | `C_MTX44Concat` | v2 camera data block, fast-forward (v17: held C-stick up, the mod's RT, or R; was A), follow camera |
| 0x8003AE84 | 1872 | `OSCheckActiveThreads` | v2/v3/v4 putt aim view, replay prompt, message hook (v21: our messages from an (id, address) table), HUD anchors, see-through draw |
| 0x80021C60 | 2200 | printf-style formatter | v3 HUD anchor table (data only) |
| 0x800411B8 | 1076 | FUN_800411b8 | v4 quarter-step power |
| 0x8003CA40 | 684 | FUN_8003ca40 | v4 See-Through setting and pause-menu row; v24 the Arrows setting and row |
| 0x800757BC | 704 | FUN_800757bc | v5 zoom view camera |
| 0x80093938 | 648 | FUN_80093938 | v6 yardage box (rounded, fitted to the number) |
| 0x80040CE8 | 600 | FUN_80040ce8 | v7 Shy Guy's link record for the select screen, v9 his animation sound list (`--shyguy` only) |
| 0x8003CDE4 | 540 | FUN_8003cde4 | v9 Shy Guy's power shot: sound, star burst, star colours (`--shyguy` only) |
| 0x80069F4C | 560 | FUN_80069f4c | v11 8th course: hole info (v21: both courses'), the golf info and ID lookups (`--course8` only) |
| 0x8006A834 | 464 | FUN_8006a834 | v11 8th course: the course select list (7 + ours) and the menu's info lookup |
| 0x80084B2C | 464 | FUN_80084b2c | v11 8th course: list append, music, sky, hole-in-one guard; v17 reach, v18 Star row (v12's auto-aim score and the cards moved to cave 16 in v21) |
| 0x80073ACC | 344 | FUN_80073acc | v21 our courses' hole files and the resolver stub (course8.py cave 15) |
| 0x8007C758 | 304 | FUN_8007c758 | v21 the menu's ID lookup, HUD cards, the auto-aim score stub, the preview movie choice, the course names (course8.py cave 16) |
| 0x80053528 | 476 | FUN_80053528 | v13 Tony's entry in the link record, his B-only power press, impact zone and faster meter (`--tony` only) |
| 0x80014324 | 1632 | FUN_80014324 | v16 team games: the captain's menu runner, then the hooks (`teams.py` "hooks") |
| 0x8003BD84 | 736 | FUN_8003bd84 | v16 the captain's menu camera ("cam") |
| 0x8001B974 | 636 | FUN_8001b974 | v16 the captain's menu and its rows' texts ("menu") |
| 0x80037BA8 | 556 | FUN_80037ba8 | v16 scramble: best shot, taking a shot ("pick") |
| 0x80035D64 | 468 | FUN_80035d64 | v16 Best Ball: whose turn ("choose") |
| 0x800133F0 | 412 | FUN_800133f0 | v16 Best Ball after a shot; the see-through menu box ("after") |
| 0x8003287C | 864 | FUN_8003287c | v16 team games' data: the mode, members, slots, help texts, menu strings ("data") |
| 0x80018130 | 456 | FUN_80018130 | v16 the captain's menu rows ("text") |
| 0x800268D0 | 352 | FUN_800268d0 | v16 Doubles' own choices' help: alternate shot ("extra") |
| 0x80054EFC | 424 | FUN_80054efc | v20 the Team Play list's own icon/help arrays (v21: 12 choices) ("list") |
| 0x8004FBF0 | 352 | FUN_8004fbf0 | v20 Worst Ball: the worst shot ("worst") |
| 0x8003A480 | 320 | FUN_8003a480 | v20 after every member hits; Wolf's menu commit, text buffers, camera slot ("worst2") |
| 0x80096398 | 436 | FUN_80096398 | v20 Wolf: the shooter pick ("wpick") |
| 0x80042AE4 | 324 | FUN_80042ae4 | v20 Wolf: running its menus ("wstep") |
| 0x80090438 | 404 | FUN_80090438 | v20 Wolf: opening its menus ("wmenu") |
| 0x800550A4 | 320 | FUN_800550a4 | v20 Wolf: the scoring hook, golfers' names ("wname") |
| 0x80093460 | 392 | FUN_80093460 | v20 Wolf: a hole's end ("wscore") |
| 0x80067068 | 324 | FUN_80067068 | v20 Wolf: a hole's points ("waward") |
| 0x800542C8 | 364 | FUN_800542c8 | v20 Wolf: points on the panel, scorecard, results ("wshow", full) |
| 0x800816FC | 352 | FUN_800816fc | v20 Wolf: state, points, names ("wdata") |
| 0x8005B7E4 | 344 | FUN_8005b7e4 | v20 Worst Ball and Wolf texts ("wtext") |
| 0x80055248 | 288 | FUN_80055248 | v22 cave 17: the aim arrows (the swing takes the D-pad's spin and curve); v24 the Arrows setting's stubs and texts (268 used) |
| 0x8003F8C0 | 300 | FUN_8003f8c0 | v22 course 2's hole info (Battleground), the golf info lookup (course8.py cave 18) |
| 0x8008C898 | 300 | FUN_8008c898 | v22 course 3's hole info (Timber Creek), the golf ID lookup (cave 19) |
| 0x800463C4 | 312 | FUN_800463c4 | v22 courses 2 and 3's hole files, the menu's ID lookup (cave 20) |
| 0x8006F468 | 344 | FUN_8006f468 | v22 our courses' names, the round's name buffer, the round start stub (cave 21) |
| 0x8007CCC0 | 308 | FUN_8007ccc0 | v22 the course select's commit, icon row spacing, preview and name stubs (cave 22) |

Still free (DEAD in `find_dead_code.py`, run on `mod\ghidra_out\golf\unreferenced.tsv`; the list above v16 only
named the 400-byte ones): 0x8003176C (316), 0x80057A14 (712, used by the `draws` debug patch), 0x8005DAFC (444,
`messages` debug patch). v22 took the rest; v21's caves 11-16 were reshuffled (cave 11 now holds the course list,
cave 12 the first two courses' hole info). Smaller dead functions (under 288 bytes) were never listed: a new tool
run without the size filter would find more. Do NOT use 0x80001800: it is wiped before the first frame.

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
- **Auto and manual swings** (`FUN_80412f6c`, view 0xB = the swing meter): A starts the meter; the power press
  then decides. `andi. r9,r0,0x300` at 0x80413240 (r0 = setup +0x104 pressed, r31 = setup) takes A or B: A sets
  setup +0x234 = 1, the auto swing (the game sets the impact, +0x1AC from `_DAT_80523cac`; sound 0x238, meter
  stage `_DAT_80523cb4` = 3), B sets +0x234 = 0, the manual one (the player presses again at the impact mark, view
  0xC; sound 0x23E, stage 2). Putts (club 13) branch off after it with no auto swing. If neither is pressed before
  the counter reaches 2 x max - 1 the meter lapses back to view 5. Replays (+0x184) fake the press from +0x1B5.
  v13 calls cave 14 there instead: golfer 17's real shots (not putts or replays) take B alone, so Tony has no auto
  swing (checked in game: A at the power press does nothing and the meter lapses; B then A swings; putts as usual).
- **Meter ticks** (`FUN_8046e440`, once a frame, r31 = the meter block 0x80523CA4): +0 the impact counter
  (0x80523CA4), +4 the auto flag (CA8), +8 the impact error (CAC), +0xC the zone (CB0), +0x10 the stage (CB4), +0x14
  the power counter (CB8), +0x18 the target step (CBC), +0x1C / +0x20 the "nice power" / "nice impact" timers
  (CC0 / CC4, 90 when exact), +0x34 the current setup (CD8). On the power bar (view 0xB) CB8 goes up 1
  (`addi r9,r9,1` at 0x8046E54C; power = CB8, or 2 x max - CB8 past the top) and the meter lapses when it equals
  2 x max - 1 exactly. At the power press `FUN_80412f6c` sets CA4 = CB8 - 2 x max; in view 0xC it goes up 1 (the
  `lwz r9,0(r31)` at 0x8046E490, then `addi`), the impact error is CA4 (mirrored below -max), 0 = on the mark,
  further presses add spin (setup +0x24C), and the phase ends when CA4 passes CA8 + 15. Replays press when CB8 /
  CA4 equal the recorded setup +0x190 / +0x1AC. v13 cave 14 (`tony_power_tick`, `tony_impact_tick`) runs golfer
  17's meter twice as fast off the putter: CB8 steps 2, stopping on the top and on 2 x max - 1; CA4 steps 2 on even
  numbers through his zone (v13-v16 `TONY_ZONE`, v17 the zone in use, 0x80523CB0), so it lands on 0 and the zone
  is as wide early as late, then 1 (the spin
  presses keep most of their time: 14 frames after the mark instead of 16). Checked in game: 120 counts a second
  (60 normally), top and lapse met, v14 CA4 ... -4 -2 0 2 4 5 6 ..., putts 60.
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
    The spread is setup +0x23C = (random x 2 - 1) x (+0x238, the lie's "Be Factor" %), drawn at the power press.
  - Shaping: spin = (+0x21C or +0x224) >> 3, curve = (+0x220 or +0x228) >> 3 (each -0x100..0x100), the second of
    each pair when the setup's view is 0xE (the shot itself), the first otherwise (previews). The impact error
    (0x80523CAC) bends and shortens real shots (modes 1, 3; previews only with the shot's +0x55 bit 1): past the zone
    (0x80523CB0) a fixed hook or slice, inside it in proportion to error / zone.
- **Aim preview (the arrows)**: while a human aims (views 5-10, `FUN_80410154`), `FUN_80423bbc` builds the shared shot
  0x805052AC each frame in mode 6/7 and flies it with `FUN_80415790(0x8050272C, lie, shot, mode)`: the arrows, the
  landing star (setup +0x1EC, also 0x80502768) and its yards. Its shot +0x55 comes from the byte 0x804E5C32 (a debug
  byte nothing sets; `stb r11,0x55(r29)` at 0x8042493C): bit 0 = fly the preview with the wind (the flight setup
  `FUN_80414aa4(ball, shot, mode)` always gives modes 1, 3, 5 the wind, 6/7 only with that bit; the No Wind item,
  player +0x51F2, zeroes it), bit 1 = add the impact error. The wind is 0x804E6854 (speed, the HUD's mph) and
  0x804E6850 (direction, radians). The D-pad, in `FUN_8041027c` (views 5-9), moves the plan +0x21C (up/down, spin)
  and +0x220 (left/right, curve) by 0x40: the arrows and the ball picture show it. The swing ignores it: on the
  meter (views 0xB and 0xC until the impact press) `FUN_80412f6c` sets +0x224 / +0x228 every frame from the main
  stick (0x804146B8..0x804147BC; under 0.1 of tilt both 0; the stick's direction scaled so its larger axis is tilt x
  256), and replays from +0x1A4 / +0x1A8. Measured (`scripts\arrow_test.ps1`, Pasadena 12, 4-wood, perfect hits):
  no wind and no shaping lands within a foot of the star; 5 mph of wind 8 yards off it; D-pad curve with a centred
  stick 15 yards off (the ball flew straight); the stick held during the swing 18 yards off (the arrows straight).
  v22 (cave 17): the preview flies with the wind (bit 0 set at 0x8042493C) and a human's swing takes the D-pad plan
  (`b` at 0x804146B8: +0x224 / +0x228 = +0x21C / +0x220 unless the player's port, record +0x5164, is 4 = CPU).
  Checked: wind, curve and spin both ways, and a stick held during the swing all land within 1.3 ft of the star.
  But with bit 0 set the arrow trail is no longer drawn (only the star and its yards), and Andrew wanted the wind
  left to the player ("there should still be skill in calculating for wind") and the stick's shaping back ("add back
  holding the stick curves the ball"). v23: no wind bit (the trail is back); the stub takes the plan only while the
  stick is in the game's dead zone (main stick x^2 + y^2 <= 0.01, the float at 0x804DAE90), else it runs the game's
  stick read. Checked on Lakitu 1, no wind: D-pad curve + spin with the stick left alone 0.2 ft from the star; the
  stick held right curves the ball 9 yd off the straight arrows (the game's way); 6 mph of wind 8 yd off.
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
  control. **Character codes** are the select grid's order: 0 Mario, 1 Luigi, 2 Peach, 3 Daisy, 4 Yoshi, 5 Koopa
  Troopa, 6 DK, 7 Diddy, 8 Wario, 9 Waluigi, 10 Birdo, 11 Bowser, 12 Bowser Jr, 13 Boo, 14 Metal Mario
  ("nisemario"), 15 Petey (an older list here, from the sound group names, had most of these wrong).
  0x80445D34 (16 ints) maps them to **golfer codes**: 0 Mario, 1 Waluigi, 2 Peach, 3 Luigi, 4 Bowser, 5 Wario,
  6 Metal Mario, 7 Birdo, 8 Yoshi, 9 DK, 10 Diddy, 11 Boo, 12 Petey, 13 Daisy, 14 Bowser Jr, 15 Koopa (checked
  v13 by rendering each golfer's in-round model). Each golfer's vtable methods [22]/[23]/[24] name its in-round
  model, texture bank and second model (`lis r3,0; addi r3,r3,ID`): e.g. Waluigi `C/S/C`, `C/S/B`, `C/S/J`, Wario
  `C/T/G`, `C/T/F`, `C/T/N`, Luigi `C/S/S`, `C/S/R`, `C/S/Z`. The select screen's models are u32 file IDs at
  0x804459A0 + 4 x character code (Waluigi `B/V/C`, Koopa `B/V/D`), then the link golfers' (16 `B/V/K`, 17
  `B/V/L`).
- **Impact window** (`FUN_804169d0`, golf, not putts): a column 1..5 from the club and the lie, byte
  `[club + 13 x lie]` of 0x804CD5E0 (0x804CD81C when setup +0x1CC is 2; the driver off the tee is 3, wedges 5,
  rough and bunkers lower), then the window is `2 x entry - 1` with the entry from the 21 x 5 byte table at
  0x804DAFD4, row `10 - impact` (impact from `FUN_8044c5bc`: the golfer's stat plus modifiers, clamped -10..10).
  Impact 4 (Mario): driver 7, wedge 9. Impact -4: 3 and 7. Impact -8: 1 and 3. Impact -10: 1 everywhere. The
  roster's lowest is -6 (the longest Star version). The modifiers: the player's club set (byte 0x804E6664 + 4 x
  player + 0/1/2 for woods/irons/wedges, `FUN_8044c1cc`) indexes 10-byte rows at main.dol 0x8009BD48, whose +4 is
  an impact bonus (`FUN_80009bd0`; -20 to +4), and +1 when the player's +0x18 object's float +0x20 is over 0.985.
  The game keeps the result in 0x80523CB0, set when a shot is set up and again by `FUN_8041073c` (each club or
  shot type change, from the aim camera), and the shot builder compares `|impact error|` (0x80523CAC) with it:
  beyond it the shot hooks or slices hard. The meter's length (setup +0x250, steps) comes from the lie object's
  method +0x24 (`FUN_80416ad4`): a per-club base plus a share that grows in thirds of `impact + 10`.
  v13: cave 14's `tony_zone` (on `FUN_804169d0`'s first instruction) returns `TONY_ZONE` for golfer 17 unless it's
  a putt. With his meter's impact counter stepping 2, a zone of Z takes Z + 1 frames: v13 2 (3 frames), v14 4 (5
  frames, -4 -2 0 2 4: Andrew's "5 frames"). v17 drops that stub (Andrew: "isnt affected by the club selection and
  lie like everyone else"): the stat getter call in this function (`bl FUN_8044c5bc` at 0x80416A80, r3 = player,
  r29 = setup) adds 9 for golfer 17, so his -10 card reads about 0 to the table (the getter's own +1 included; 10
  gave every club but the driver 9). Checked in game off the tee: driver 5, clubs 1-5 7, clubs 6-12 9; a wedge from
  about 50 yards 7; with an odd zone the even steps take Z frames (5: -4..4). v18 (Andrew: "his impact frames need to be 5 and
  adjusted according to worse lies"; 7/9 for longer-zone clubs was wrong): the stub at 0x80416A80 gives golfer 17
  impact 0 (row: 1, 3, 5, 7, 9 by column) and sets the caller's column register r31 to 3 - drop, drop = the club's
  fairway column (lie row 1 of the column table in use) minus this lie's, at least 0, column at least 1: 5 frames
  from the tee, fairway or better, 3 a column worse, 1 two or more (club-set bonuses don't apply to him). v19
  (Andrew: "make tony the tigers impact 3 frames"): 2 - drop, so 3 frames (-2, 0, 2) from good lies and 1 (on the mark
  only) from any worse lie.
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
  v12 makes the test `cmplwi r11,0x10` (0x80400AB8) so Shy Guy, golfer 16, gets none; v13 with Tony `0x11`.
- **v13 Tony the Tiger, golfer 17** (`tony.py`, `--tony`): the second golfer of Shy Guy's link record (entry at
  record +0x2C, body 1; cave 14 writes it after cave 9 writes Shy Guy's, and the extra page keeps 2 cells per
  record). Golfer 17 (`FUN_804c2404`'s default case, vtable 0x804CABC8; its own [22]/[23]/[24] 0x804CAD3C,
  0x804CAD30, 0x804CAD48 name `C/W/G`, `C/W/F`, `C/W/J`; emblem `C/W/H`, face `C/W/I`, select model `B/V/L`) gets
  Waluigi's 47 methods (vtable 0x804C9DA8) except those three, so he moves with Waluigi's animations and is silent
  (Waluigi's voice set isn't loaded for him; golfer 17's own is a girl's). His record's +0x28 is 1: Waluigi's power
  shot effects. Stats (Andrew's high-risk pick): 350 yards (v13 240, then 270, v14 300; each club is the drive x a fixed share, main.dol
  `FUN_80009c58`: 100, 93, 86, 80, 74, 68, 63, 58, 53, 48, 43, 38, 31% for clubs 0-12, x (100 + the club set's
  bonus)%), height 3, curve 1, impact -10, control 4, spin 5, an impact zone of 3 frames on every club, 1 from
  worse lies (v19; v18 5 and 3/1; v13-v16 pinned it: 2, then 4; v17 let clubs widen it; see Impact window), a meter
  twice as fast off the putter (see Meter ticks), and no auto swing (see Power). The select screen's lines for him, common-set 0x25E (cursor) and 0x271 (odd link golfers' pick
  call), are the girl's: v13 makes them silent. Waluigi's in-round model draws his overalls' buttons as mesh part
  7 (not part 1, the body): `tony.py` hides that part too. Waluigi's `C/S/C` has three bones per finger (left /
  right): thumb 51-53 / 70-72, index 60-62 / 79-81, middle 57-59 / 76-78, ring 54-56 / 73-75, pinky 63-65 / 82-84
  (hands 50 / 69). The club sits in the curl of the fingers, so a model whose fingers ride only on the hand bone
  holds it outside the paw: `tony.py` maps each of Tony's finger joints onto these.
  Matching a base's other models to its golf model (`tony.shifted_bone_map`): by the rig's child order first, as
  the select screen models pose the hands (Waluigi's `B/V/C` holds the right hand half closed, and matching by place
  swapped ring 73-75 and pinky 82-84). The select pose clenches that hand into a fist, which bunched the skin of
  Tony's knuckles into a crumpled clump, so v15 gives the select model no finger bones (an open paw).
  Other bases (`tony.BASES`; v15 tried Donkey Kong, which Andrew turned down): golfer objects are 0x1E4 bytes
  (Waluigi, Luigi, Bowser, golfer 17) except Donkey Kong's, 0x1EC (`FUN_804bdfa4` stores a float from 0x804E29A8 at
  +0x1E4 and +0x1E8 for his methods), so golfer 17 on his methods must be made by his constructor (build_mod.py
  `GOLFER17_ALLOC`: `bl` it in place of the allocator at 0x804C2438, `nop` the base constructor call at
  0x804C2440; golfer 17's vtable store then follows). Donkey Kong: `C/U/G`, `C/U/F`, `C/U/J`, select `B/U/Z`
  (character 6), vtable 0x804CA500; pelvis 14, chest 40, neck 41, head 42, arms 66-69 / 85-88, fingers 70-84 /
  89-103 (index, middle, ring, pinky, thumb), legs 16-18 / 28-30, toes 19-22 / 31-34, tie 62-65, club holder
  104-110. His `B/U/Z` hangs the whole body one bone lower, 6.88 back, and poses the hands differently
  (`tony.shifted_bone_map`). Bowser: `C/T/B`, `C/T/A`, `C/T/E`, select `B/V/I` (character 11), vtable 0x804C9C70,
  root 0 at (-0.75, 0.23, -19.71), body 1, tail 2-6, spine 7, chest 8, head 9, arms 42-45 / 85-88, thumb and three
  fingers 46-57 / 89-100, legs from the root 103-106 / 113-116. Luigi: select `B/U/V` (character 1), vtable
  0x804C9A18.
  Club reach is linear in the drive (`FUN_80009c58`), and the launch-speed search has no cap that bites at 350:
  measured (`scripts\tony_drive_test.ps1`, Lakitu 1, power 58/60, impact on the mark) 300 yards carried 273.7 and
  350 carried 315.5 / 324.4, each about 94% of `drive x 58/60` there (downhill, wind, spread).
  Voice slots for him (not built yet): a round loads golfer 17's own set, MusyX group 17 "ella" (`C/Y/U`-`X`, 20
  sounds 0x50-0x63; special shot set "shella" `D/B/S`, 0x15F-0x160). Golfer 17's own voice methods play [43] swing
  0x50, [44] nice impact 0x51, [42] ball near the hole 0x63, [46] chirps 0-7 0x5B-0x62 (jump table 0x804E2EFC);
  its own [18] list (0x804D92C8, 31 entries) uses the rest. Waluigi's methods (what golfer 17 has now) ask for his
  set "waruigi" (0x107-0x119: [43] 0x107, [44] 0x116, [42] 0x119), not loaded for golfer 17. Waluigi's [18] list
  (0x804D7F08, 25 entries) plays his voice at frame 1 of reactions 0-4 (0x109-0x10D, best to worst), 0x117 / 0x118
  later in reaction 0, his special set's 0x13C in animation 5, and common sounds (0x19D, 0x1A0, 0x1C9, 0x1F5,
  0x1F9, 0x209). Power shot hit sounds by effects code (jump table 0x804DF01C): 0 Mario 0x217, 1 Waluigi 0x21E.
  The plan, as Shy Guy's: keep golfer 17's own [42]/[43]/[44]/[46], point [18] at Waluigi's list with his voice
  IDs moved to 0x52-0x59, a power shot shout on 0x5A (like cave 10), and his select-screen lines on 0x25E / 0x271.
- **Model skinning** (main.dol `FUN_80008bfc` each frame; kernels 0x8002E4F8 and 0x8002E5EC, paired singles, so
  Ghidra shows them as bad data): the model's matrix slots (root +0x48 count, +0x4C a byte list of bones; the
  instance's slot buffer, +0x30, is allocated as count x 0x30 by `FUN_8000543c`) get their bones' skin matrices;
  then each skin block (root +0x50 count, +0x54 blocks of 0x20) writes blended vertices into the instance's own
  position and normal buffers (two each, +4/+8 and +0xC/+0x10 by `lha +0x36`, sized root +0x0C and +0x20 entries,
  their first root +0x14 / +0x28 entries copied once from the source arrays root +0x10 / +0x24):
  - block +0x00 / +0x04: first position / normal it writes, in the source arrays and in the buffers
  - +0x0C runs at +0x10 of (u8 slot a, u8 slot b, u16 count): the next `count` vertices, in order, each
    `wa * Ma * v + wb * Mb * v`, weights in pairs at +0x08 (s8, 1/128ths; GQR5 = 0x07060706)
  - +0x18 runs at +0x1C of (u16 slot, u16 count): for `count` vertices numbered (u16, from the block's first) in the
    list at +0x14, add `w * M * v`, the weights bytes following the pairs. Waluigi's `C/S/C`: 1 block from 1141,
    96 pair runs (1074 vertices) and 23 extra runs (548); every vertex's weights total exactly 128.
  A group with flags bit 0 clear draws from those buffers (the draw, `FUN_80006524`, points GX's position and
  normal arrays at them); its palette entry -1 (0xFFFFFFFF) loads matrix 0, the model's own, since the vertices
  are already in model space. Face morphs (`FUN_80008858`, root +0x78/+0x7C) also write into the buffers.
  `tony.skinned_swap` writes Tony this way: one block after everything the base's buffers held, one skinned group.
  One bone per vertex (rigid groups, as Shy Guy has) tore his chest, shoulders and hips apart at every bend.
- **Select screen call:** `FUN_8040b56c` plays one common-set sound per golfer when picked (0x26F Koopa ... by
  character code), and on the extra page 0x270 for even link golfers (golfer 16), 0x271 for odd ones. Landing the
  cursor on a golfer plays its idle line ("taiki"), `FUN_80013108(golfer code)`: 0x258-0x269 for the 16, 0x263
  golfer 16, 0x25E golfer 17, also common-set sounds. v10 gives golfer 16 his lines in both (`shyguy.MENU_VOICE`).
- **Where a skin choice would hook in** (looked into for Halloween skins, 2026-10-28; nothing built yet):
  - Round: every read of a golfer's files goes through its vtable +0x58 [22] model, +0x5C [23] bank (-1 = none) and
    +0x60 [24] second model (-1 = none), always with the player record at hand. `FUN_80426104(player, n)` makes the
    golfer object and preloads the files (`FUN_8000baac(id, 6)`). The player update `FUN_80423bbc` (state 3) builds
    the bank (`FUN_8000ecac`) and the model (`FUN_8000f00c`). So a stub after those calls can map (file ID, that
    player's skin) to another file.
  - Select screen: `FUN_804031c8` runs one model slot per player (0xA8 apart, state word 0x8044913C). State 0
    loads `0x804459A0[character code]` through `FUN_8000f044`.
  - Select-screen buttons (`FUN_8040b9ec`): A, B, X (0x400, opens screen 0x19), R (Star), L (lefty) and the D-pad.
    Y (0x800) and Z (0x10) are never read there.
  - The per-player option byte 0x80176044 has 8 values: the round's debug menu prints "opt:%s" from an 8-name list.
  - The v18 disc has a 182 MB free gap for new files.
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
  v11 makes the new course code 8 (Pebble Beach), v21 code 9 (Pasadena Municipal). Their hole IDs are
  1101 + 18 x (code - 8) + hole (1101-1118, 1119-1136); `course8.py` serves both from one set of stubs.
- **v21, the 9th course (code 9, menu index 8).** What code 9 meets that code 8 didn't:
  - Hole info: one table of 36 entries in cave 11 (contiguous IDs, so the ID lookup is one range); the ID-by-hole
    stubs answer codes 8 and 9. The file IDs (6 bytes a hole) moved to cave 15 with the resolver.
  - Course list: 9 entries in cave 12; the list append adds index 7 then 8 (`FUN_8041358c` each).
  - Icon: `FUN_80412640` binds texture <index> of `B/W/R` (`FUN_8000c27c(0x8044ABB4, idx)`), so index 8 needs a
    texture 8: v21 appends a 68x68 RGB5A3 one (the loader `FUN_8000bed8(0x8044ABB4, 0x9E3)` takes the bigger file).
  - Star overlay and toggle: `DAT_80234a72 >> idx & 1`, a byte, so index 8 never has one.
  - Name: 0xA8 + 8 = 0xB0 ("Approach Practice"); the name stubs swap 0xAF and 0xB0. Training's banner names its
    lessons with a plain `li` (0x8048C75C), not through the course sites, so the swap can't reach it.
  - Preview: the word at 0x8041445C (`addi r28,r9,0x3E0`, r0 = index, r9 = 0) is a `bl` to a stub: index 7 Blooper
    Bay's A/T/F (0x3E6), else Lakitu Valley's A/T/C.
  - Emblem table entry 9 and card switch entry 9 (was Cheep Cheep Falls' card, B/B/C) point at `F/S/B`, `F/S/A`;
    music column 1 (Lakitu Valley); the hole-in-one guard, reach and
    Star-row stubs test code - 8 <= 1.
  - Sky: the loader keeps two models, the dome at loader +0x5F1C and the backdrop at +0x5F20, each drawn only when
    set (`FUN_80006084(id)` loads one). Congo Canopy loads one model (0x8D3, B/R/L) and no backdrop. Lakitu Valley's
    backdrop (A/X/J) has big mountains, and Blooper Bay's (B/I/L) is a sea that stands in front of anything past
    about 1 km of flat land. So course 9 loads Blooper Bay's dome (0x6FD, B/I/K) alone and stores 0 as the
    backdrop (cave 13 `sky_dome`, continuing at 0x804463E0); its own far land, skyline ring and refineries
    (dev/course/industry.py) make the horizon. The camera's far plane (camera +0x34) is 12800 ft (3.9 km).
  - Its files live under a second new top folder, `F` (holes `F/A`..`F/R`, card `F/S/A`, emblem `F/S/B`);
    `TTMod.Build` appends any number of new folders (each with parent 0).
- **v22, the 10th and 11th courses (Battleground, Timber Creek): code 9 with a variant.** Code 10 is the practice
  holes and the per-course tables end there (the CPU table 0x804D7324 has 10 entries, the emblem table 12, the music
  table 7 columns), so the new courses don't get codes. Menu indexes 9 and 10 make codes 10 and 11 at the course
  select's commit (`FUN_80415040`: `stb r3,0xA79(r29)` at 0x80415388 stores index + 1 into 0x80176079; r11 and r12
  are free, CTR is live, nothing reads cr0 before 0x804153A4); a stub there stores code 9 and the variant (1, 2; 0 for
  any other pick) in the spare setup byte 0x8017607E. The game's other writers of 0x80176079 (main menu resets to 1,
  the Game Boy Advance link setup `FUN_8043c2ac`) never write 9. Then (course8.py, caves 11-13, 15, 16, 18-22):
  - Hole IDs 1101 + 18 k + hole for k = 0 Pebble Beach, 1 Pasadena, 2 Battleground, 3 Timber Creek; the ID-by-hole
    lookups (golf 0x80407048, menu 0x80400A04) add the variant to code 9's k. Info and file lookups by ID divide the
    ID by 18 and take each course's table from a pointer table (the tables are spread over four caves). An info
    entry's course byte is the round's code (9 for every Texas course).
  - The course list (7 + 4 entries of 0x2C, 484 bytes) lives in cave 11; the append stub loops over our courses
    with its counter in memory (`FUN_8041358c` clobbers the volatile registers; it was unrolled for two).
  - The icon row (`FUN_80412640`): x = 0x140 + 56 x (i - (n - 1) / 2), the 56 from `lfs f11,0x7504(r9)` at
    0x80412DB4 (r9 = 0x80440000, free after it; icons 48 wide, the picked one bigger). With more than 9 entries the
    stub loads 45.0 instead, so 11 fit the board.
  - Names: on the course select `0xA8 + index` (0xB1, 0xB2 for ours: other texts) is swapped by index for each
    course's message (0x7FF0, 0x7FDF Pasadena, 0x7FDE, 0x7FDD); in a round `0xA7 + code` sites have no free
    register to read the variant with (r0 sites), so code 9 always shows message 0x7FEF, a buffer the round start
    fills with the variant's name.
  - Round start: golf `FUN_804014c0`'s first instruction (`stwu r1,-24(r1)` at 0x804014C0; it copies the setup
    block, once per round) goes through a stub that, for code 9, writes the variant's emblem file ID into the
    emblem table's entry 9 (golf 0x804D5F9C + 36, read by `FUN_8048c354` and the pause menu; the overlay's data
    loads fresh each round) and copies its name into the 0x7FEF buffer.
  - The HUD card switch's case for code 9 reads the variant (r11, r12 free in the case), the music stub too (main.dol
    `FUN_80011a94`: Battleground plays column 6's songs, Timber Creek column 3's). Sky, drive bonus, Star rule and
    the hole-in-one guard go by code: the Texas courses share code 9's.
  - Icons: B/W/R textures 9 and 10 appended (68x68 RGB5A3). Files under top folders `G` (Battleground) and `H`
    (Timber Creek), each with holes A-R and card/emblem S/A, S/B.
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
- **Music:** main.dol `FUN_80011a94(situation, course)`, a 16 x 7 song table; v11 plays Blooper Bay's for 8, v21
  Lakitu Valley's for 9.
- **Saves:** the hole-in-one mask store (golf 0x804682F4) would wrap course 8 onto Lakitu Valley's; v11 skips it.
- **Reach** (v17): a club's reach is `FUN_8044c344(player, club)` = `FUN_80009c58(drive, club, set)` (one call, at
  0x8044C434, for the 16 golfers' drives from 0x804D2980 + id x 0x1C and link golfers' from their record +0x1A).
  On course 8 a stub adds to the drive first (course8.py `REACH_HOOK`): v17 35 for everyone; v18 50, not for
  golfer 17 (Tony, r31 = the player there), and a Star version drives as its normal self there: the Star is bit 0 of
  the player's option bits (golf 0x804E667C + player +0x5160), which `FUN_8044c278` adds to the golfer's drive row
  (even rows normal, odd Star); `STAR_ROW_HOOK` (the `lwzx r9,r29,r9` at 0x8044C40C, r29 = row x 28; r0 live past
  it) reads the row before. Checked on Pebble Beach's 1st tee: Mario and Star Mario 262 (212 / 280 elsewhere), Tony
  350. v21: the bonus is per course (a float per code after the stub: Pebble 50, Pasadena 40, Andrew: "make it +20
  except for Tony", then "+40"; both use the Star row rule: "star power should also be ignored on Pasadena").
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

## Costumes (v24)

Halloween costumes: Y on the character select puts the picking player's golfer in costume (`costumes.py` caves
"data" 0x80023518, "menu" 0x80037EDC, "round" 0x80023188; the looks in `looks.py`).
- **Select screen.** `FUN_8040b9ec` reads the pad's new presses in r30; Y (0x800) is never read there. The Star (R,
  0x20) and lefty (L, 0x40) checks start at 0x8040CBE0 / 0x8040CC64 (per-player words 0x8044BA68 / 0x8044BA90 by
  the picking player 0x8044BA44). Our stub on 0x8040CC64 (`lwz r0,-17744(r31)`, the page flag) flips the player's
  costume word on Y and jumps to 0x8040D3C0, the cursor-move tail: cursor sound, `FUN_8040a76c` (show the golfer
  under the cursor: flips 0x8044BA34 between model slots 4 and 5 and requests the golfer there), and at
  0x8040D3EC the other slot (state 2) is set to 3 (unload). Model slots: `FUN_804031c8`, 6 of 0xA8 at 0x804490E4
  (+0x58 state: -1 idle, 0 load, 1 loading, 2 shown, 3-5 unloading; +0x94 the character code); state 0 loads
  0x804459A0[code] (`lwzx r4,r11,r9` at 0x80403224, r31 = slot, then `bl FUN_8000f044`). Slots 0-3 are per player
  on the team and CPU screens, 4/5 the character select's.
- **Option byte.** 0x80176044 + player: bit 0 Star, 1 lefty (picking: `FUN_8040b56c`, which clears and rewrites it,
  then `bl FUN_800130f8` at 0x8040B6B0), bit 2 human / bit 3 CPU (course select commit). The round's copy is
  0x804E667C + player (+0x5160 = index): player +0x51EE = lefty, +0x51ED = bit 2 | bit 3 >> 2 (2 = CPU). Debug
  names: [AB][NS]-(RIGHT|LEFT). v24 uses bit 4 (0x10) = costume.
- **Round.** `FUN_80426104(player, index, port)` makes each golfer (`bl FUN_804074a8` at 0x80426240, r31 = player;
  players are made in rank order, not index order) and asks its vtable [22] model, [23] bank, [24] second model
  (methods `lis r3,0; addi r3,r3,ID; blr`, r3 = the object; again in state 3, `FUN_80423bbc`). Golfers 2 (Peach)
  and 8 (Yoshi) have neither bank nor second model ([23] the shared `li r3,-1`, [24] another function). v24
  rewrites each simple method as `mr r4,r3; li r3,ID; b costume_map` and notes costume players' objects at
  0x80426240 (dropping old entries at the same address). Golfer 7 (Birdo) is vtable 0x804CA770 (constructor
  `FUN_804c1e18`), files C/T/U, C/T/T, C/T/X.
- **The opening movie** is A/T/L (276 MB; Dolphin's FileMon log: the clean game opens it at boot after the logos
  A/T/K; the mod never opens it, title idle included, since v2 skips the loop). A/T/N (260 MB) is likely the
  ending. v24 makes A/T/L a copy of A/T/K and TTMod.Build fills the freed space.
- **Rigid groups** draw through the bone's animated matrix times its +0x04 matrix. In most models +0x04 is the
  inverse of the bone's rest pose (vertices in model space), but some select screen models store another (Petey's
  B/V/J, Tony's B/V/L, DK's B/U/Z): our vertices go through inverse(+0x04) * inverse(rest) first. Select
  screen skeletons can also be laid out or posed differently from the in-round ones (Peach's lacks two root
  bones, DK's is crouched, Petey's is compressed): pieces are carried by vertices paired by texcoord (the same mesh).
- **Texture sets** (model root +0x8C): +4 count, +8 offset of the (header offset, 0) pairs (always 0xC), headers of
  0x24 right after the pairs. To add one, move the header right after the pairs to the end of the module. A
  header's +8 is the data: high bit = in the golfer's bank file, else from the set's start. Golf models mix both.
- **Not skin matrices:** model instance +0x30 (player +0x518C's) holds pose data per matrix slot (a unit
  quaternion first), not the skin matrices.
- **Testing a look from the front:** the aim camera's right stick only tilts it while held; Dolphin's Free Look
  (test profiles: FreeLook.ini [General] Enabled, BackgroundInput; pad 2 moves/turns it) gives any view
  (`scripts\costume_front.ps1`).

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
- The menu opens in `FUN_80475504`: the icons (file IDs `0x804D5FCC[code]`, `lwzx r4,r9,r0` at 0x804756A0, handles
  at 0x80523E70 + 4 x row), the rows' texts (`bl FUN_80024cfc` at 0x80475A18, r4 = code + 0x10D), the help line
  (0x80475A74, list[0] + 0x118). Moving the cursor re-shows the help (`bl FUN_80024cfc` at 0x80477890, r25 = menu,
  r9 = list[cursor], or 11 for Give Up before the first stroke: message 0x123). Only the highlighted row's icon is
  drawn (big, at a fixed spot). Rows are at y = 150 + 28 x row (float 0x804E045C; the cursor moves by 28.0, 0x804DFDFC),
  the help line at 336 (0x804E0468), and the menu's art has six row slots with lines between them: a 7th row lands
  in the help box (checked). Codes 11 and up have no messages of their own (0x10D + 11 is 0x118, Scorecard's help),
  and the icon table runs on into the mode icons (0x804D5FF8). The game's lists hold 5 rows at most.
- v24 adds code 11, "Arrows: On/Off", after See-Through (cave 6 `ghost_menu` / `gs_arrows`, cave 17); a full menu
  (Stroke Play: 5 rows + See-Through) drops its Rules row (code 1) for it. The row text and help calls above go
  through stubs that give it messages 0x7FD0-0x7FD2, its icon load takes
  Controls' (code 2), and while it's off the player draw's `bl FUN_804168fc` at 0x80426040 (queues the arrow trail,
  drawer `FUN_804160f4`, while a human aims a non-putt) is skipped; the landing star (`FUN_80448b2c` at
  0x80425FDC) still draws.

## Team games (v16 Best Ball and Scramble)

Doubles (alternate shot) is the game's only team mode; v16 bends it into Best Ball and Scramble (`teams.py`).

**Menus** (menu overlay):
- Screens (`FUN_80403e18` switches on the current one; `FUN_80439c1c(id)` pushes, `FUN_80439cd4` pops): 0 top menu
  (player count: 0x8044B014 humans, 0x80176078 players, 0x8044B018 golfers), 4 character select (humans pick
  first), 1 the Play Mode carousel `FUN_8041cc9c`, 5 the Doubles team screen `FUN_8041f10c`, 6 CPU picks, 3 the
  course select (commit `FUN_80415040`), 7 tees and options.
- Carousel rows: bytes at 0x80445FEC + set x 52 + (humans - 1) x 13 (set = Star Tournament unlocked), counts at
  0x80446054; entry codes 0 Stroke, 1 Tournament, 2 Character Match, 3 Speed Golf, 4 Coin Attack, 5 Ring Attack,
  6 Practice, 7 Match Play, 8 Club Slots, 9 Doubles, 10 Side Games, 11 Skins, 12 Star Tournament, 13 Near-Pin.
  An entry's name is texture [code] of B/V/T, its model record 0x80449CB4 + code x 0xA8, its help message 0x14 +
  code. Doubles is offered for 1-4 humans; CPUs always fill it to 4 golfers.
- Sub-lists: count per entry and humans at 0x804460E8 + (code x 4 + humans) x 4 (Doubles: 0x8044617C.., 5 each);
  `FUN_8041ca00` fills 0x8044C50C[i] (icon B/V/V and label B/V/W texture, 96x96 CMPR / IA4, 25 each) and
  0x8044C534[i] (help = message 0x22 + value). The row lays out x = 0x164 - 0x24 x count + 0x48 x i; 8 fit.
- Commit: 0x8041D310-0x8041D32C clears 0x80176090 and the sub-mode, then a switch on code - 4; Doubles (0x8041D41C)
  writes mode 0/1/8/2 by choice (jump table 0x80447A40, `bgt` at 0x8041D438 for choices past 4 goes to the
  common tail), then 0x80176090 = 1 and the team screen (or, with 1 human, `FUN_8040b05c` and the CPU screen).
  Modes without a sub-list clear at 0x8041D738.
- The team screen's arrangement (0x8044C59C; tables 0x80446228 / 0x804462E8) reorders the setup block at the end
  of `FUN_80415040`, so team A is slots {0, 2} and team B {1, 3} (4 humans {1,2} v {3,4} -> [H1, H3, H2, H4]).
- Spare setup bytes (no reads anywhere): 0x8017607D-7F, 0x80176095-97, 0x801760A3. v16 uses 0x8017607D.

**Rounds** (golf overlay; golf state 0x804E5BE4):
- `FUN_804014c0` copies the setup block (doubles flag -> state +0xAE4 = 0x804E66C8) and sets +0xD15 (0x804E68F9,
  sides = balls) = +0xD16 (records) = players, halving +0xD15 in Doubles (0x8040158C). +0xD17 = shooter (0xFF none).
- Team records: `FUN_80400014` allocates 4 of 0x1C8; `FUN_80426104` links player +0x8/+0x10 = the record of side
  `index mod sides`, +0x14 its scorecard (record +0x8 + hole x 8: +0 hole result, +1 putts, +2 strokes), +0x18
  its lie (record +0xB4, 0x34 bytes: position, ..., +0x28 in the hole, +0x2C surface code), +0x1C its ball (record
  +0xE8). So Doubles partners share a ball, lie, strokes and card. Record +0x1BC strokes this hole, +0x1BD putts,
  +0x1BE 0 playing / 1 holed / 2 out, +0x1C1 honor, +0x1C2 the alternate-shot toggle (and the HUD's big face),
  +0x1C4 the last penalty (1 drop, 2 out of bounds). `FUN_80414a1c(ball, lie)` saves a lie, `FUN_80414970` puts
  the ball back on it (every turn start, state 3, 0x80424248).
- Shooter pick `FUN_80402f1c` (sides only): not started (+0x1BC 0) first, then off the green, then on it; ties
  by distance to the pin (0x804E6864/686C), then honor. Doubles part 0x80403458-0x804034A8 flips +0x1C2 and adds
  the side count for the partner. A stroke and a putt count at the power press (0x80413448, 0x80413470);
  `FUN_8041f3f4` (after the shot, 0x8041F878-0x8041F954) adds penalties (`FUN_8041cc34` out of bounds: replayed
  from the lie; `FUN_8041ccbc` water and the like: `FUN_80426f38(player, lie)` drops; course 7 `FUN_8041f31c`) or
  saves the new lie, then marks holed from lie +0x28 and scores (`FUN_8046a0b8`). A mulligan takes the stroke
  back at 0x8041F5A0. When every side is done, `FUN_80403b0c` calls `FUN_804683c4` at 0x80405A28, then the
  scoreboard. Score panel `FUN_8042e448` draws faces through `FUN_8042e358(record)`.
- v16 (`teams.py`, the mode in 0x8017607D: 1 Best Ball, 2 Scramble, 3 Team Scramble; Doubles list choices 5
  Best Ball Match (Doubles' own Match case at 0x8041D468: mode 1, sub-mode 2), 6 Best Ball Stroke, 7 Scramble,
  8 Team Scramble). All keep Doubles' team record, so its scoring, panel, scorecard and results do the rest.
  - `setup` (on the store at 0x80401578; keep r0, the player count halved next): Team Scramble turns the round's
    doubles flag on with one side.
  - Best Ball: each member's ball lives in a slot (lie, strokes, done). `bb_choose` (in the picker) picks the
    member (not started first, then off the green, then the farthest) and loads its lie and strokes into the team
    record; `bb_after` (at 0x8041F958, after the penalty/lie block) saves them back and leaves the team record as
    the team: once the best holed score can't be beaten (every teammate still playing has strokes + 1 >= it) that
    score and a lie in the hole, so the game ends the team's hole (and match play compares teams as usual); else
    the fewest strokes still playing and the lie's in-hole flag cleared. Gotcha hit: comparing a slot address
    with `cmpwi 0` (our addresses are negative as signed words).
  - Scramble: `pick` makes the shooter side + sides x member, member = (start + shots this round) mod members
    (round count reset when +0x1BC is 0; v17 start = the member whose ball the team plays, so they hit first: Andrew
    "if we all hit and pick player 4's ball then player 4 gets to hit first"; a holer leads off the next hole);
    `stroke` / `mulligan` (cave "text") count only each round's first shot; `shot` replaces the penalty/lie block:
    each member's result goes to a slot (OB: the lie again, flagged; drop: `FUN_80426f38` into the slot); a
    hole-out takes the holer's ball at once; after the last member the team's captain (its lowest controller port,
    player +0x5164; no human: the best shot) picks.
  - The captain's menu is a post-shot menu (`FUN_80483564`, type 2 with its codes replaced: a header row, code 10,
    which can't be chosen, then codes 0..n-1, texts 0x129 + code from our buffers through the message hook,
    cursor +0x40 starting on the best shot). As CUR_MENU (0x804ECE30) the scene would stop for it (0x80404134) and
    its draw would skip the course and queue only the menu (0x80406AD8, `FUN_80484a30`), over a frozen picture
    (screen transition 6); so `menu_scene` answers "not open" for ours, `menu_draw` queues our drawer and lets the
    course draw, and the picker reads the menu's own value (+0). `glass_draw` wraps the game's drawer
    (`FUN_8048497c`) with konst alpha 5/8 (`GXSetTevKAlphaSel` 0x8006D9FC, shadow 0x802DFC70) and swaps the box's
    TEV alpha (raw `FUN_8006dd74(0, 0x8FFC0)` = texture alpha, at 0x80484508/28) for texture x konst (0x8F370):
    the wooden box (C/O/P texture 0, CMPR) shows the course through it, the rows stay solid.
  - `cam_update` (each frame the menu is up): the team's ball moves to the highlighted slot and the camera glides
    to behind it (away from the pin), looking past it toward the pin, then `FUN_800179f0(camera)` rebuilds the
    view and projection from it (the game's own camera code has already run that frame).
    Pad state (0x8026BB60 + 0x38 x port; player +0x4F14, menu +0x8C): +0 held, +2 repeating directions, +4
    pressed, +0x17/+0x18 main stick X/Y, +0x19/+0x1A C-stick X/Y (s8). C-stick X turns 2.5 degrees a frame,
    Y zooms 12-160 ft.
  - `face` puts the member who is up in the partner's face slot (teams of 3 or 4).
  - The carousel's Doubles reads "Team Play": its name banner, B/V/T texture 9 (172x50 IA4), is redrawn in place,
    its help (message 0x1D) is ours, and the `sublist` stub also gives Doubles' own five choices help ids of ours
    (alternate shot; cave "extra" at 0x800268D0).
  Checked in game: Best Ball Match and Stroke, Scramble 2v2 (also with CPUs), Team Scramble of 2, 3 and 4, the
  captain's menu, camera and see-through box, an out-of-bounds member costing nothing, plain Doubles.

**v20 Worst Ball and Wolf** (`teams.py`; modes 4 and 5 in 0x8017607D; Doubles list choices 8 Worst Ball, 9 Team
Scramble, 10 Wolf; counts 9/10/11/11 for 1-4 humans: Team Scramble from 2, Wolf from 3):
- **The list's arrays hold 10.** `FUN_8041ca00` fills the icon/label textures at 0x8044C50C and the help values
  right after at 0x8044C534 (10 each; 0x8044C55C is a float of the menu's), so an 11th choice would overwrite
  help[0]. Their only readers outside the side-games code: `addi r9,r28,-0x3AF4` at 0x8041C4C0 (icon) and 0x8041C5C4
  (label), `addi r9,r9,-0x3ACC` at 0x8041DB60 (help line). v20 turns those into `bl` loads of a pointer (cave
  "list"), which `FUN_8041ca00`'s first instruction resets to the game's arrays and the Doubles case's end points at
  ours (Doubles' five, then ours). 11 icons fit the 16:9 screen (centres -40..680, the bar +-420 round 320).
- **Worst Ball** is a scramble (team record, slots, members, one stroke a round) with no captain: after the last
  member `all_hit` takes `worst_of` at once (a ball not in the hole before a holed one, then a penalty, then the
  farthest by distance squared times the lie weight), and a holed ball waits for the others (the team holes only
  when everyone holes from the same spot).
- **Wolf** is the game's Skins round (mode 2, sub-mode 3, no doubles, 3 or 4 sides, no CPUs: commit straight to
  the course select). Skins in the round:
  - `FUN_8046a0b8(side)` scores after every shot (and the picker calls it for every side not done, every pick);
    `FUN_8046a134` by sub-mode: 0 stroke (result byte = strokes when holed, par x 3 and status 2 at the limit,
    returns 6 then), 3 skins (result byte 0 = won the skin, 1 = not; ends the hole for whoever can't win it).
  - Skins shown: `FUN_80469720(player)` (score panel `FUN_8042e448`, results values 0x805240D0 in
    `FUN_8048a9c8`/`FUN_8048b5ec`, ranked high first): holes won, each with the tied holes before it. The
    scorecard's setup `FUN_80472b54`/`FUN_804731ac` (iVar11 == 3 branch, joins at 0x80472FD4 / 0x8047362C)
    totals the holes before this one into 0x80523FFC[player] and the carry into 0x80523FF8; the hole-end scorecard
    `FUN_80473ee8` counts them up (frame 30: +1 to each winner of this hole, or +1 to the carry when nobody won,
    `addi r9,r9,1` at 0x80474448; then every 10 frames 1 of the carry to each winner); the scorecard grid
    (`FUN_80479fd0`) draws each hole's winner's count with `bl FUN_80489e74` at 0x8047B314 (r28 hole, r8 player).
    The game calls skins "Points" on screen ("Carry-over Points").
  - v20: the scoring hook runs the shot as stroke play (sub-mode word 0x804E66BC = 0 around the call), then
    `wolf_check`: once the teams are set, anyone whose strokes + 1 can't beat their team's best holed score stops
    (status 2); when everyone is done, each team scores its best (holed, or at the limit), and the winners get 1
    (a Lone Wolf 2; when the Lone Wolf loses, each other player 1): result byte 0 for them, 1 for the rest (kept
    over stroke play's later par x 3 for stopped players). `FUN_80469720` answers the points; the scorecard's totals
    get the points before this hole and the carry = this hole's points past 1 for each winner, so the count-up adds
    exactly the hole's points; a tie carries nothing; the grid shows each winner's points.
  - Tee order and the Wolf (`FUN_80402f1c`'s first instruction): the picker takes tee shots by priority 2 and equal
    distance, lowest record +0x1C1 first, so on a new hole v20 writes +0x1C1 = (player - Wolf - 1) mod n (the
    Wolf last; Wolf = (hole + n - 1) mod n: the last player on hole 1, then 1P, ...). While a menu of ours is up it
    returns with nobody's turn (d17 = 0xFF; the caller ignores the return). After each candidate's drive (its
    strokes > 0) the Wolf's menu (the captain's menu's way, on the Wolf's pad, the camera on that ball) asks
    "Wolf X: team up with Y?"; No to the last = the Lone Wolf. A notice "X is the Wolf this hole!" opens with the
    hole (over its intro).
  - Player +0x51EF is the golfer code; the menus name golfers from our own table (the game's names are messages).
  Checked in game (4 players, 2 holes): tee order, the notice, the Wolf passing then taking a partner, early stops,
  1 point each; Lone Wolf passing all three and winning 2; the scoreboard, the scorecard grid and the results.

**v21 Team Worst Ball** (choice 10, from 2 humans; Wolf moves to 11; counts 9/11/12/12): the commit writes
0x8017607D = 6, which only the round's `setup` reads: it plays as Worst Ball (team mode 4) with one side, as Team
Scramble does. The score panel's face swap (`face`) now runs for any scramble-kind mode with one side.

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
   desktop, on the screen their own Dolphin's game window last used (its Qt.ini [renderwidget]; without that,
   Dolphin opens it on the screen the mouse is on), with their own controller mapping, else keyboard controls (keys: x = A, z = B, c = X, s = Y, d = Z, i/k/j/l = C-stick, q/w = L/R,
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
