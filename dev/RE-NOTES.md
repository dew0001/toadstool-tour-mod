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
| 0x80040CE8 | 600 | FUN_80040ce8 | v7 Shy Guy's link record for the select screen (`--shyguy` only) |

Still free (DEAD in `find_dead_code.py`): 0x8003CDE4 (540), 0x80053528 (476),
0x80054EFC (424), 0x80057A14 (712, used by the `draws` debug patch), 0x8005DAFC (444, `messages` debug
patch), 0x80069F4C (560), 0x8006A834 (464), 0x80084B2C (464), 0x80090438 (404),
0x80096398 (436). Do NOT use 0x80001800: it is wiped before the first frame.

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

## Sound

- **MusyX** (Factor 5): main.dol's group table at 0x80137308, 37 entries of 0x14: name, first file ID, sfx count,
  first sfx ID, group ID. 0-15 the golfers by character code, 16 "neil" and 17 "ella" (Game Boy Advance golfers),
  18 "menu", 19-36 "sh" + name (power shot sounds). `JVoiceLoad1` (`FUN_80012844`, group index) loads a group's
  four files, ID, ID + 2, +4, +6: pool, project, sample directory, sample data (e.g. Koopa Troopa "nokonoko"
  `C/V/V`-`Y`, golfer 16 "neil" `C/Y/Q`-`T`). A round loads each player's group by golfer code (golfer 16 -> 16).
  File ID = 2 x (676 a + 26 b + c) for path a/b/c (letters from 0), +1 for some.
- Sounds play through `FUN_80011b88(id, ...)`, `FUN_80011c40(x, y, z, id, ...)` and `FUN_80011d74`; an ID in no
  loaded group (and not a common sound, `FUN_80011a48`) is dropped silently; then MusyX's sfx start `FUN_8007337c`.
  `voiceFXcall` `FUN_800120a8(group, id)` is another path (not used by the golfers' voices).
- File formats and DSP ADPCM: `musyx.py`. Neil's set: 21 sounds 0xAF-0xC3, one macro and one sample each,
  22050 Hz.
- Find what plays: `tools/debug_patch.py` `plays` (every ID asked of the three calls, `sfxlog.ps1 -Pairs -At
  0x80057A14`), `sfx` (every ID MusyX starts), `voices`; Dolphin's `[DSP] DumpAudio = True` records the mix to
  `Dump/Audio/*_dspdump.wav` for checking a sound by correlation.
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
