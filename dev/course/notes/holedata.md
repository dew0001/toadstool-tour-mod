# Per-hole data files: hole table +0xC, +0x10, +0x14

Static analysis of the golf overlay `C/L/V` (Ghidra `ghidra_out\golf\decomp.c`) and the files themselves.
Script: `holedata.py` in this folder (reads and writes all three; round-trip test below).

| Field | Example (Lakitu 1, ID 106) | What it is | Read by |
| --- | --- | --- | --- |
| +0x0C | `A/V/S` (type 2, packed) | **Hole-intro camera**: up to 3 sets of up to 10 chained camera clips (position, rotation and FOV keys) | `FUN_804ae73c` (load), `FUN_804ae88c` (play) |
| +0x10 | `A/V/P` (raw, 452 B) | **Ring Attack rings**: count + 16 slots of position, two rotations, two scales | `FUN_80453020` (game mode 5 only) |
| +0x14 | `A/V/O` (raw, ~4 KB) | **Coin Attack coins**: count + (position, flags) per coin | `FUN_80454350` (game mode 7 only) |

Nothing else reads them. None of the three holds tees, cups, par, yardage, the hole map, wind, OB or green data;
where those come from is under "Not in these files" below.

## 1. How a hole's files are found

### Hole table: base 0x804DCF18 (not 0x804DD138)

- 0x20 bytes per entry, **9 rows x 18 slots** = 162 entries, entry = row * 18 + slot (`FUN_80443e14`,
  `FUN_80444598`, `FUN_80443d5c` all index `0x804DCF18 + (row * 0x12 + slot) * 0x20`). 0x804DD138 is row 0 slot 17.
- +0x00 model, +0x04 collision, +0x08 shared course file, +0x0C camera, +0x10 rings, +0x14 coins (game file IDs,
  odd = packed), +0x18 hole ID, +0x1C -> name (only the debug hole menu uses it).
- Rows: 0 = 17 dead entries (hole ID 0, model/collision IDs `A/M/T`.. that are not on the disc) + TEST1 (1001) in
  slot 17; rows 1-6 = the six main courses; row 7 = Congo Canopy; row 8 = practice holes 801-809 (slots 9-17 repeat 801).
  The order of slots inside a row does not matter: the game looks the entry up **by hole ID**.
- Lookup (`FUN_80443e14(scene + 0x101C, course, hole_index, coin_stage)`): hole ID = `FUN_80407048(course,
  hole_index)` (hole info table, below), then scan rows 0..8, slots 0..17 for +0x18 == ID; the row/slot found go
  to `scene+0x101C+0x18/+0x1C`, and `FUN_80444598` loads the files from that entry.

### Hole info table: 0x804CCD60 (par, yardage, hole order)

12 bytes per entry, **141 entries** (the count 0x8D is a constant in `FUN_80406f90`, `FUN_80407048`, `FUN_804070c8`).
An identical copy sits in the menu overlay `B/U/C` at **0x80444E60** (course select screens); change both.

| Off | Type | Field |
| --- | --- | --- |
| +0 | u32 | hole ID |
| +4 | s16 | yards (regular) |
| +6 | s16 | yards, Star version |
| +8 | u8 | par |
| +9 | u8 | course (1-6 main, 7 Congo, 8 and 9 = 3-hole sets made of existing holes, 10 = practice) |
| +A | u8 | hole number, 1-based |
| +B | u8 | ring order 1..18 (0 on courses 7-10) |

- `FUN_80406f90(id)`: entry by hole ID (falls back to entry 0). Its +4/+6/+8 are what the game shows.
- `FUN_80407048(course, n)`: hole ID of hole n+1 of a course (returns 109 if absent). **This is the course's hole
  order**: Lakitu = course 1: hole 1 -> 106, hole 2 -> 102, ... (checked: 106 = 363/385 yd par 4, 102 = 382/400
  par 4, as expected).
- `FUN_804070c8(level, course, i)`: hole index whose ring order is i+1 + (0, 6, 10, 14 for level 1..4); used by
  `FUN_80401b70` to build a 6-hole list when the game mode is 5 (Ring Attack). So +B picks which holes a Ring
  Attack level plays.
- The round's hole list is bytes at 0x804E6698 (0-based hole numbers), current course byte 0x804E68F4, current
  slot 0x804E68F8; many HUD/score functions call `FUN_80407048(course, list[slot])` + `FUN_80406f90`.
- **Star courses use the same hole ID and the same six files**; only the yardage label (+6) and the tee differ
  (the back tee, see below). Nothing in +0xC/+0x10/+0x14 changes for Star.

## 2. +0x0C: hole-intro camera (type-2 module)

Loaded by `FUN_80444598` (`FUN_804ae73c(state, file, set)`, set 1 if game mode 5, 2 if mode 7, else 0) for
every course row except 0, and played in state 1 of the golf scene `FUN_80403b0c` (the "Course%dHole%d" intro):
one frame per update (three per update in one state, a fast-forward), A skips (`FUN_8040175c`), and the camera is
freed when the last clip ends.

The file must be **packed (odd file ID)**: the module loader `FUN_80028240` only loads odd or negative IDs. The
second argument the loader gets (`file + 2`) is ignored.

### Module layout (all offsets from the decoded module start; pointers are ADDR32 relocations, stored as 0)

```
0x00  -> ctor list (ADDR32)        run by FUN_8002e140 after loading; a single 0 word (empty)
0x04  -> dtor list (ADDR32)        a single 0 word
0x08  48000000  b 0x0C (REL24)     module entry: FUN_804ae73c calls module+8 to get the root
0x0C  3C600000  lis  r3, root@ha (HA16)
0x10  38630000  addi r3, r3, root@l (LO16)
0x14  4E800020  blr
0x18  0, 0
0x20  clip data: for each clip in order of first use (set 0 slot 0, 1, ..., then set 1, set 2):
        position keys, rotation keys, FOV keys, then the clip header (no padding anywhere)
root  3 sets x 10 words (0x78 bytes): clip header pointers, 0 = none
      set 0 normal, set 1 Ring Attack (mode 5), set 2 Coin Attack (mode 7)
+0x78 0 (ctor list)   +0x7C 0 (dtor list)       = end of module
```

Relocations: ADDR32 at 0 and 4, REL24 at 8 (value 0x0C), HA16 at 0x0C and LO16 at 0x10 (value root), then one
ADDR32 per pointer, sorted by offset (3 per clip header, one per used root slot). No external relocations.
All 135 camera files on the disc follow this exactly (`holedata.py test`).

### Clip header (0x1C)

| Off | Field |
| --- | --- |
| +0x00 | length in frames |
| +0x04 / +0x08 | position key count / -> position keys (0x10 each: s32 frame, f32 x, y, z) |
| +0x0C / +0x10 | rotation key count / -> rotation keys (0x14 each: s32 frame, f32 qx, qy, qz, qw) |
| +0x14 / +0x18 | FOV key count / -> FOV keys (8 each: s32 frame, f32 degrees) |

### Playback (`FUN_804ae88c(state, &pos, &forward, &up, &fov)`)

- Per track: binary search for the first key with frame >= t; equal -> that key, else linear interpolation from the
  key before (quaternions: slerp, `FUN_80040fa4`). So each track needs a key at frame 0, frames strictly
  increasing, and a key at length-1 (after the last key it would extrapolate). Keys may be sparse (e.g. hole 201:
  800 frames, 20 position keys, 114 rotation keys, 2 FOV keys); most files key every frame.
- Position x 0.97765 (`0x804E17B8`) inside the player, then the intro code multiplies by 32 (`0x804DA460`):
  **world = key x 31.2848**, i.e. keys are in units of 32 feet (feet = world / 0.97765; RE-NOTES: a 15-unit putt
  shows 15.3 ft). Check: hole 106 clip 0 starts at key x -2.0612 -> world x -64.5, exactly the regular tee's x.
- Rotation: quaternion (x, y, z, w), `PSMTXQuat` (`FUN_8003d904`); forward = R x (0, 0, -1), up = R x (0, 1, 0).
- Camera written to the camera at 0x802D7E64 (pos = key x 0.97765): eye = pos x 32, look-at = (pos + forward) x
  32, up at +0x18,
  FOV (degrees) at +0x2C. Stock FOV: 39.887 in every course clip except five clips at 54.432 (holes 305, 406,
  409, 414, 509); 35.0 / 25.08 on the driving range.
- When t reaches length-1 the next slot of the same set plays (up to 10, until a 0 slot); `FUN_804aecd4`
  (t == length-2) starts a wipe (`FUN_8000f93c(0x80222988, 1)`) at the end of every clip. If the chosen set's
  slot 0 is empty the game falls back to set 0. On the disc only the driving range (801, `B/R/V`) fills sets 1
  and 2 (with the same two clips in the other order); every course hole uses set 0 only, with 2-5 clips (hole 106:
  a tee-to-green flyover, a shot round the green, a pull-out), 800-2000 frames in all (13-33 s at 60 Hz; the frame
  rate is my assumption). Congo Canopy's 18 files each hold their hole's own clips (400/500/600 frames).

## 3. +0x10: Ring Attack rings (raw)

Loaded only in game mode 5 by `FUN_80453020(rings, file)` (`FUN_8000b214` raw load, then freed).

```
0x000  u32 count (1..16)
0x004  16 slots x 0x1C:  f32 x, y, z   (world units)
                         f32 rot_x, rot_y  (radians)
                         f32 scale_x, scale_y
```

- Always 452 bytes on the disc; slots past `count` hold leftover memory from the authoring tool (pointers like
  0x8125DAF8) and are never read. Write zeros there in new files. The game keeps 16 rings (`FUN_80452260`), so 16 is
  the maximum.
- Matrix = T(x, y, z) x S(scale_x, scale_y, (scale_x + scale_y) x 0.5) x RotY(rot_y) x RotX(rot_x)
  (`0x804DEBA0` = 0.5). The ring model is built in code: a torus in the local XY plane, radius 0.9, tube 0.1
  (`FUN_80452260`), so scale = outer radius in world units (3.2 .. 135.8 on the disc, scale_x == scale_y in all 502
  rings; 181 have rot_x != 0).
- Pass test (`FUN_80452be4`, only for a ball object whose +0x48 is 1, presumably the live ball): the ball's
  segment crosses the ring plane (local Z axis = normal)
  within |matrix column 0| (about scale_x) of the centre. Each ring has a per-player bit mask at rings+0x358 (0x1F
  at load). Sound 0x1FE on a pass.

## 4. +0x14: Coin Attack coins (raw)

Loaded only in game mode 7 by `FUN_80454350(coins, file, stage)` (raw, then freed).

```
0x000  u32 count (<= 256)
0x004  count x 0x10:  f32 x, y, z  (world units)   u32 flags
flags  bits 0-3   kind: 0 none (skipped), 1 coin (1 point), 2 big coin
       bits 4-6   stage: a kind-1 coin is only placed if stage <= the hole's stage (below);
                  not checked for other kinds (all big coins on the disc have 3)
       bit 7      collect group: touching this coin collects every coin with the same group
       bits 8-15  0 in files (bit 8 is a run-time "collected" flag)
       bits 16-31 group, 0..255: coins of a group start turned the same way about Y
                  (group x pi / number of groups), and bit 7 collects by group
```

- Files are exactly 4 + 16 x count bytes (59..256 coins on the disc, 24,359 coins + 878 big ones in all).
  Values on the disc: 0x01, 0x11, 0x21, 0x81, 0x32 in the low byte. Coins sit on the ground or in the air along
  shot lines (hole 106: 45 coins on the green around the cups; a star of 20 coins with 4 collect-group coins in
  the middle; 10-coin circles above the fairway).
- Stage (`FUN_8040176c(holes_in_round, hole_index)`, passed by `FUN_80443e14`): 3-hole rounds: index+1; otherwise
  3 on the last hole, 2 from 2/3 of the round, 1 from 1/3, else 0.
- Value (`FUN_80453bf0`): kind 1 = 1; kind 2 = 1 / 10 / 20 / 40 at stage 0 / 1 / 2 / 3. Added to the shooter's
  score (`**(0x804ECE78 + player x 0x5204)`) in mode 7.
- Pickup (`FUN_80453c4c`): distance from the coin to the ball's path < 19.2 world units (`0x804DEBBC`).
- 256 slots (matrices at coins+0x6C9C, flags at +0xCC9C); more than 256 placed coins would overrun them.

## 5. Not in these files (found while tracing; owners of those files should confirm)

- **Tees, cups, drop points, sun direction**: the collision module (+0x04) has a third entry stub (module+0x10,
  e.g. `A/V/R`: `lis/addi` -> 0x97090) returning an info block, scaled x32 into world units (`0x804DA3E0`):
  - +0x000 tee 0 (regular), +0x00C tee 1 (back = Star; hole 106: z 549.5 vs 510.8 world units), +0x018 zero
    on every hole (`FUN_80402400` reads 2 tees; the ball goes 0.22 above).
  - +0x024 4 cups x 0xC (`FUN_80402400`; choice by mode: 0-3 fixed, 4 random of 4, 5 0-1, 6 2-3, 7 1-2, 8 0-2,
    9 1-3; the debug menu calls them CUP0-3 / CUPRNDALL / CUPRND0-1 / CUPRND2-3 and the tees REGU / BACK).
    Tee 0 -> cup distance / 0.97765 / 3 matches the table yardage on straight holes (106: 357-368 vs 363;
    tee 1: 375-384 vs Star 385), confirming both the units and which tee is Star.
  - +0x054 8 points (only hole 501 uses them, to place objects), +0x2F4 16 pairs of points (the nearest one to the
    ball is picked by `FUN_80417938`: probably drop points), +0x474 a unit vector (light/sun direction, sets
    0x805016C0 and shadow offsets).
  - Congo Canopy (row 7) shares one collision file, so it keeps one tee per hole at +0x670 + hole x 0xC (used for
    both tee slots) and 4 cups per hole at +0x748 + hole x 0x30 + cup x 0xC.
- **Par, yardage, hole order, Star yardage, Ring Attack order**: the hole info table (section 1).
- **Animated extras** (crowds `mur_0X01_tee`, pigeons `hato`, ducks `kamo`, fish, yacht, Cheep Cheeps `puku`...):
  named objects inside the model (+0x00), matched by name in `FUN_80444598`. On Congo the tee crowd
  (`mur_0701_tee`) gets its hole's 0x58-byte entry copied into slot 0.
- **Hard-coded hole IDs** in `FUN_80444598` load extra objects or alternate models (about 30 IDs between 201 and
  618, e.g. 305, 417, 418, 501, 508, 513, 518, 601, 618; plus whole-row tests for rows 3 and 6). New holes should
  use IDs outside 101-718 so none of these fire.
- Not located (not in these three files): the HUD hole overview picture, wind and weather, OB lines, green slope and
  grain, aim defaults. Likely in the collision (+0x04) or shared (+0x08) files, or computed.

## 6. Writing new holes

- Camera: `holedata.build_camera(cam)` -> (module bytes, relocations); `pack_camera(cam)` -> the type-2 disc file.
  Give the hole table an **odd** (packed) ID for it. Convert world positions to keys with / 31.2848 (= 32 x
  0.97765). Keep every track starting at frame 0 and ending at length-1; `check_camera` lists problems and
  `camera_at(clip, t)` gives the world eye / look-at / up / FOV the game would use at frame t.
- Rings: `build_rings({'rings': [...]})` -> 452 bytes (zero-filled spare slots). Coins: `build_coins({'coins':
  [...]})`. Both can stay raw (even file ID); `FUN_8000b214` also takes packed files (odd ID).
- New holes also need a hole table entry and a hole info entry (both tables are full-size arrays with
  hard-coded counts: 162 and 141), mirrored in `B/U/C`'s info copy.

## 7. Script and tests

```
python -I holedata.py tables          hole table + info table (and checks B/U/C's copy is identical)
python -I holedata.py dump 106        one hole's camera clips (world eye positions), rings and coin groups
python -I holedata.py export 106 x.json / build x.json outdir
python -I holedata.py test            every hole's three files: parse -> JSON -> rebuild -> compare
python -I tools/findref.py <C/L/V.bin|main.dol> <lo> <hi>   lis + addi/load pairs building an address in [lo, hi)
```

`test` result: **351 files rebuilt byte-identically, 0 mismatches** (135 camera modules: decoded bytes and the
relocation table, also after packing and decoding again; 108 ring files; 108 coin files; holes from all seven
courses, Congo Canopy's 18 camera files and the 9 practice holes included). Congo's and the practice holes' ring and
coin files (`B/Q/O`, `B/Q/P`, `B/R/R`...) are not on the disc: those holes have no Ring or Coin Attack.
Repacking does not reproduce the original compressed bytes (the repo's LZSS encoder makes different, slightly
bigger streams), but the game only sees the decoded data, which is identical.

## Open questions

- Frame rate of the intro (assumed 60 Hz) and which of the per-update loops (the "3 frames per update" state 6) is
  the fast-forward; not checked in a running game.
- Ring Attack levels and +B: offsets 0/6/10/14 overlap (holes with order 11-12 and 15-16 in two levels); what
  "level" is (`scene+0xD16`, or 1 when `scene+0xAD8` == 5) is not traced.
- Bits 4-6 of big coins (always 3) are never read; maybe the editor's default.
- The dtor list at module+4 is never seen called (`FUN_804ae7d8` just frees).
- Collision info block (section 5) fields other than tees, cups, +0x54, +0x2F4, +0x474 and Congo's tables are
  unknown; left to whoever does the +0x04 file.
