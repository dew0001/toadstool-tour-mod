# Courses above the hole files: tables, menus, saves, text (GFTE01)

Scope: everything a new, 8th selectable course needs above its hole files. All of this is static analysis of
`main.dol`, the golf overlay `C/L/V` and the menu overlay `B/U/C` (both flat images at 0x80400000). Nothing was run
in Dolphin. Scripts are in `scripts\` (see the end). `scripts\courses.py --check` rebuilds every table listed here
byte-identically from its parsed form (all OK).

## Short version

- A course is a **course code** (1-7 retail, 8/9 unused 3-hole sets, 10 practice, 0 debug). The menu's course
  index is code - 1. The code reaches the round through the setup block in main.dol (0x80176079).
- The hole order lives in the **hole info table** (golf 0x804CCD60, an identical copy in the menu at 0x80444E60):
  141 entries of 12 bytes keyed by (course, hole number). Files live in a separate **hole file table**
  (golf 0x804DCF18, 9 rows x 18) keyed by hole ID only.
- About 15 more per-course lookups are spread over three binaries: emblem, wind-globe card, sky, music,
  CPU data, text, THP preview, menu icon. Most are tables or switches sized for codes 0-10 or 0-11, and
  they fall back to Lakitu Valley's assets for codes they don't know.
- The save mirror (0x8022A3C8, 0xAAAC bytes) has fixed per-course arrays sized for 6 (tournament, Coin Attack)
  or 7 (Club Slots, Speed Golf, hole-in-one masks) courses. A code 8 course **overflows them**. Only some writers
  are guarded.
- **Recommendation:** make the new course **code 8 / menu index 7**, the cut 3-hole slot that has no menu path. Use
  **new hole IDs** (1101-1118 suggested). Hold its 18 hole-info entries and stubs in a main.dol cave, and its hole-file
  entries in the dead row 0 of the hole file table. Copy the chosen entry into a scratch slot (row 8 col 17) when a hole
  loads. Relocate the 7-entry menu course list. Keep the save format unchanged:
  - v1 offers the course only in Stroke Play, Match Play, Skins and Practice (and their Doubles variants). Those
    modes write nothing per course except the hole-in-one mask, so guard that one writer.
  - Tournament, Ring Attack, Coin Attack, Club Slots and Speed Golf come later, if at all. Each needs save space
    and its own data.
  Details and the patch list are in "Recommendation" at the end.

## 1. The setup block (menu -> round)

main.dol 0x80175600, 0xAAD bytes. The golf overlay copies it to golf state 0x804E5BE4 + 0x54 (`FUN_804014c0`), then
copies a few fields to state + 0xD10.. (`DAT_804e68f4` = course code, the most used global in the golf overlay).
Golf address = 0x804E5C38 + (main.dol address - 0x80175600).

| main.dol | golf copy | meaning |
| --- | --- | --- |
| 0x8017603C [4] | 0x804E6674 | controller per player |
| 0x80176040 [4] | 0x804E6678 | tee per player: 0 REGULAR, 1 BACK (back tees = the "star" yardage) |
| 0x80176044 [4] | 0x804E667C | player option bits (debug names BN/BS/AN/AS _RIGHT/_LEFT) |
| 0x80176060 [18] | 0x804E6698 | **hole order**: 0-based hole numbers to play, in order |
| 0x80176074 | 0x804E66AC | pin set (debug names CUP0-3, CUPRNDALL, CUPRND0_1, CUPRND2_3) |
| 0x80176078 | 0x804E66B0 | number of players |
| 0x80176079 | 0x804E66B1 and 0x804E68F4 | **course code** (menu: list entry index + 1, `FUN_80415040`) |
| 0x8017607A | 0x804E68F8 | index into the hole order (current hole) |
| 0x8017607C | 0x804E66B4 | number of holes to play (18, 9, 6, 4, 3, 2, 1) |
| 0x80176080 | 0x804E66B8 | game mode (below) |
| 0x80176084 | 0x804E66BC | sub-mode |
| 0x80176090 | 0x804E66C8 | doubles flag |
| 0x80176092 | 0x804E66CA | star tournament flag (also picks the save block, x 0x2C4) |
| 0x80176094 | 0x804E66CC | star (back) tees on a non-tournament round |
| 0x80176098 | 0x804E66D0 | side-game / training kind (mode 9) |

Game modes (0x80176080, from the main menu handler in the menu overlay around 0x8041D258):

| mode | game |
| --- | --- |
| 0 | Stroke Play |
| 1 | Match Play; Character Match is mode 1 against a CPU (0x8017603D = 4) |
| 2 | Skins |
| 3 | Practice |
| 4 | Tournament (star version with 0x80176092 = 1) |
| 5 | Ring Attack |
| 6 | Speed Golf |
| 7 | Coin Attack |
| 8 | Club Slots |
| 9 | Side Games and Training (0x80176098: 2-4 = practice range and greens on course 10, 5 = Near-Pin, 6 = training) |

Doubles reuses modes 0, 1, 2 and 8 with 0x80176090 = 1. The password ("Enter the code") tournaments (`FUN_8043bf84`)
accept course indexes 0-6 only.

## 2. Course codes

| code | menu idx | what | hole info | hole file row |
| --- | --- | --- | --- | --- |
| 0 | - | debug: row 0 (17 dead entries pointing at files that don't exist, A/M/T..A/O/A, and TEST1 = ID 1001) | none | 0 |
| 1-6 | 0-5 | Lakitu Valley, Cheep Cheep Falls, Shifting Sands, Blooper Bay, Peach's Castle Grounds, Bowser Badlands | 18 each, par 72 | 1-6 |
| 7 | 6 | Congo Canopy (the side-games course: 18 par 3s of 62-168 yd, back-tee field 100 = none, no rings or coins) | 18 | 7 |
| 8 | (7) | **unused**: 3 holes = 201, 308, 402 (Cheep Cheep 18, Sands 4, Blooper 10) | 3 | none (IDs live in rows 2-4) |
| 9 | (8) | **unused**: 3 holes = 501, 503, 517 (Peach 1, 3, 12) | 3 | none |
| 10 | - | practice: 801 KWA_DR driving range, 802/803 SMZ_PRA/PRB, 804-809 AWA_1..6 | 9 (par 4, 100 yd) | 8 (cols 9-17 repeat 801) |

No menu path sets codes 8 or 9; only the debug course/hole/mode selector (`FUN_8040e368`, codes 0-10) can.
The menu's generic "is this index unlocked" logic, inlined in `FUN_80413910`, still knows indexes 7 and 8:
- idx 7 is gated on bit 0 of 0x8022A3D0, idx 8 on bit 1. Those are side-game unlock bits that `FUN_80469234` sets.
- No list loop reaches idx 7 or 8: the loops run over 0-5 plus an explicit idx 6.

Codes 8 and 9 already have entries in the per-course tables that cover 0-9 or 0-10. Those entries fall back to
course 1 or 2 assets, so code 8 is the cleanest free slot.

## 3. Hole tables

### Hole info (golf 0x804CCD60, menu copy 0x80444E60, 141 x 12 bytes, identical)

| off | type | field |
| --- | --- | --- |
| +0 | u32 | hole ID |
| +4 | u16 | yards (regular tees) |
| +6 | u16 | yards (back tees; the "Lakitu Star Cup" yardage, e.g. hole 1: 363 / 385) |
| +8 | u8 | par |
| +9 | u8 | course code |
| +A | u8 | hole number 1-18 (**this is the hole order**: course 1 hole 1 = ID 106, hole 2 = ID 102) |
| +B | u8 | Ring Attack group index 1-18 (1-6 = the 1-player 6-hole set; 7-10, 11-14, 15-18 = the 4-hole sets for 2-4 players; 0 = none) |

Lookups (each loop counts to 0x8C, `cmplwi cr7,rN,140`; table base via `lis r9,0x804D/0x8044`):

| golf | menu | does | on miss |
| --- | --- | --- | --- |
| `FUN_80406f90(id)` base 0x80406F98/0x80406FA0, bound 0x80406FA4 | `FUN_8040094c` 0x80400954/0x8040095C, bound 0x80400960 | info by ID | returns entry 0 (ID 106) |
| `FUN_80407048(course, hole0)` base 0x80407054/0x8040705C, bound 0x80407060 | `FUN_80400a04` 0x80400A10/0x80400A18, bound 0x80400A1C | ID by course + hole | returns **109** |
| `FUN_804070c8(players, course, i)` base 0x804070F4/0x804070FC, bound 0x80407100 | third copy 0x80400AB0/0x80400AB8, bound 0x80400ABC | Ring Attack: hole0 for group slot i (+6/+10/+14 for 2/3/4 players) | 0 |

Helpers `FUN_80406fcc`/`FUN_80407008` (golf, at 0x80406FCC/0x80407008) bucket +B into groups 0-3.
The tables end at 0x804CD3FC (golf) / 0x804454FC (menu), where other data starts (read at 0x80408920 / 0x804010A8),
so they can't grow in place.

### Hole files (golf 0x804DCF18, 9 rows x 18 cols x 0x20)

Row = storage only: the lookup is by hole ID. Fields: +0 hole model (type 2), +4 collision module, +8 external
texture bank, +C flyover/camera module (3 paths: normal, Ring Attack, Coin Attack), +10 ring layout (raw 452 B, used
only in mode 5), +14 coin layout (raw, mode 7), +18 hole ID, +1C pointer to an 8-byte debug name (names at
0x804DCAD8..0x804DCF17, e.g. "SMZ_1_C").

- **+8 (A/X/H for course 1)** is an external texture bank, raw texture data with no header. It loads only if the hole
  model's texture set (root +0x8C) has magic 0x0131A3CB instead of 0x0020AF30 (`FUN_80009400`, main.dol). Every
  retail hole model checked embeds its own textures, so the bank never loads:
  - A/X/H (course 1) and B/A/Y (course 2) are byte-identical leftovers.
  - Courses 3-7 point at files that don't exist (B/E/Q, B/I/J, B/M/G, B/Q/D, B/R/K).
  - A new course can put any value there and should embed its textures.
- Congo Canopy shares one model (B/Q/Q) and one collision (B/Q/R) for all 18 holes. Only its flyover file differs per
  hole, and its rings/coins files (B/Q/P, B/Q/O) don't exist. Row 8's rings/coins files don't exist either.

Resolver `FUN_80443e14(loader 0x804E6C00, course, hole0, x)`:
- Course 0 means row 0, col = hole. Course 10 means row 8.
- Any other course calls `FUN_80407048`, then searches 9 rows for the ID (bases 0x80443E78/0x80443E7C and
  0x80443EF0/0x80443EF8, row bound `cmpwi r8,8` at 0x80443EBC).
- **If the ID isn't found it keeps (course, hole) as (row, col)**: for a code >= 9 that indexes past the table, so it
  would crash.
- It stores the row and col at loader +0x18/+0x1C, and fills par 0x804E685C, yards 0x804E685E, back yards 0x804E6860
  and the info pointer 0x804E68B0.

`FUN_80443d5c` is the same search for the debug name (bases 0x80443D98/0x80443D9C and 0x80443DE8, bound 0x80443DDC).
The loader `FUN_80444598` reads the table at three more bases: 0x80444910, 0x80444C64 and 0x80445CA0.

What the loader does with the row (it never looks at the course code for files):
- row != 0: loads +C (flyover).
- row 1-7: looks for tee parts named "mur_0001_tee" in the collision module to hide them. With flag 0xFE (set when
  the hole was aced before, `FUN_80401e78`), swaps in the ace tee marker D/N/Y using the part name
  0x804D28D8[row-1] ("mur_0101_tee".."mur_0701_tee"; only 7 entries).
- row 3: special object D/L/U. Row 6: D/M/M. Row 7: Congo extras.
- (row 0, col 17) = TEST1 gets sky B/T/K, which doesn't exist.

Hole-ID special cases in the same loader stay inactive for new IDs: alternate models D/N/Z..D/O/E (IDs 305, 417, 418,
508, 513, 518), per-ID objects (0x763, 0x7B7, 0x1241-0x126F), and ID ranges 700-799 and 804-809 in the renderers
`FUN_80441ff8`/`FUN_8043ffdc`.

## 4. Holes played, nines, star versions

- `FUN_80415040` (menu) writes the order: identity 0..17. Row-2 option 0 = 18 holes, 1 = front nine (first 9 of the
  order), 2 = back nine (order 9..17, count 9), 3/4/5 = random 9/6/3 (100 random swaps), 6 = 6 holes. Side games use
  par-3-only sets from the hole info (`+8 == 3`).
- Ring Attack overwrites the order from +B (`FUN_80401b70`). Coin Attack plays 6 or 4 holes.
- Star versions:
  - The back-tee yardage (+6) and the back-tee geometry in the hole files.
  - The star tournament: names 0xB8+idx, save block 1, rival tables.
  - A per-course "star unlocked" bit at 0x80234A72 (bit = course idx 0-5; Congo uses 0x8022A3D0 bit 0x20). When it is
    set, the course select shows the star overlay (`FUN_804121b0`) and lets the player toggle 0x80176094.

## 5. Per-course assets and settings (golf overlay unless noted)

| what | where | by | new course (code 8) gets today |
| --- | --- | --- | --- |
| Sky dome + backdrop (two type-2 models, state +0x5F1C/+0x5F20) | `FUN_80444598` ~0x80446100-0x804463E0: a chain on hole ID (sunset/night variants), default by hole-info course byte: 1/other A/X/I+A/X/J, 2 B/A/Z+B/B/A, 3 B/E/R+B/E/S, 4 B/I/K+B/I/L, 5 B/M/I+B/M/J, 6 B/Q/E+B/Q/F, 7 only B/R/L | hole ID, course byte | Lakitu's sky |
| Course card, 130x130 CMPR (Lakitu: green hole picture in a frame; Sands: pyramid) at loader +0x5F58 | jump table 0x804DCA78 [codes 0-10], switch at 0x804463E8; files A/X/K, B/B/C, B/E/V, B/I/O, B/M/K (5 and 10), B/M/P, B/Q/M; load `bl` at 0x80446468 | code | Lakitu's card |
| **Top-left HUD picture**: the card above drawn as a small 3-D object (`FUN_8044a658` -> `FUN_8044a190`, skipped for code 10) and the wind display `FUN_8044ae80`, tinted by `FUN_8044ad70(code)` (colours per code 0-7/10, default 0xFF640000) | | code | Lakitu's card, orange tint |
| 88 KB texture set (12 textures; the six copies A/X/L, B/B/D, B/E/W, B/I/P, B/M/L, B/M/Q are identical) | jump table 0x804DCAA4 [0-9] at 0x804464FC and `FUN_8044400c` | code | identical anyway |
| Course emblem, 106x106 RGB5A3 medallion (shown in the pause menu; the hole intro's square icon is the mode's, from 0x804D5FF8) | table 0x804D5F9C [12 entries, codes 0-11]: C/O/U..C/P/A; `FUN_8048c354` (training uses 0x12BB/D/F), `FUN_80475504` | code | entry 8 = C/O/U (Lakitu); v11: E/S/B, a 4-byte data patch |
| Banner text | `FUN_8048c354`: 0xA8 + code - 1 (course), tournament 0xB2/0xB8 + code - 1, training 0xAF-0xB1 | code | 0xAF "Shot Practice" (wrong) |
| Music | main.dol `FUN_80011a94(situation, code)` (not in the Ghidra function list; at 0x80011A94): table 0x80137A74 [16 situations][7 courses] u32 song numbers into the song table 0x80137788 (38 x 0x10: song file, MusyX song id, volume, name, e.g. "bgmLake.sng"). Situation from `FUN_80401d74` | code | code > 7 returns song 12 ("end3.sng") in every situation |
| Wind strength | `FUN_804017d8`: Tournament max = course code (0 if < 2; star tournament 9); Ring Attack mode 5 max = course code; other modes use the wind option | code | fine (8) |
| Points multiplier (point-scoring modes) | `FUN_80420e28`: 1.0, 1.5, 2.0, 2.5, 3.5, 4.0 for codes 1-6, else 1.0 (mode 9: 1.0) | code | 1.0 |
| Caddie/commentary distance thresholds | `FUN_8041c5ac`: index code - 1, 11 -> 5, others > 6 -> 0 | code | Lakitu's |
| CPU per-hole bytes | table 0x804D7324 [10 pointers, codes 0-9] -> 20-byte arrays 0x804D7298..; `FUN_804a8c40`; plus CPU position tables keyed by (code, hole) in `FUN_804a6190`/`FUN_804a6e18` (defaults when absent) and `FUN_804aabdc` (6-wide table) | code | Lakitu's (valid pointer). **Code >= 10 reads a garbage pointer** |
| Tournament rivals | `FUN_804900f0(code)` (runs at every round start): score ranges 0x804D65BE/0x804D65CA, rosters 0x804D643A [2][6][30]; rival name messages 0x804D60B0[star*6+code] (`FUN_80472948`) | code | reads neighbouring rows (harmless outside tournaments) |
| Hole-specific fixes | `FUN_80426f38` (course 4 holes 6/17, course 6 hole 4), `FUN_804b1ac8`, `FUN_804abd70`, course 7 camera/sounds (`FUN_80410838`, `FUN_80433700`, `FUN_8041f3f4`) | code + hole | none apply |
| Green speed, weather | No course-level table found. Green behaviour must come from the hole files (collision/flyover modules); that is for the hole-file side. There is no weather system: time of day = the hole's sky pair. The pause menu has a "Change Weather" item (code 9) that wasn't traced | | |

## 6. Menu overlay: course select and other lists

Course select:
- **List builder** `FUN_80413910`: per mode, loops course idx 0..5. Idx 0 is always listed; idx 1-5 need bit
  idx-1 of 0x8022A3CF. Some modes then add idx 6 (Congo) explicitly:
  - Stroke/Skins/Practice/Club Slots (default branch): 0-5 + Congo.
  - Match Play: 0-5 + Congo. Character Match (0x8017603D = 4): 0-5 only.
  - Tournament: 0-5. Ring Attack: 0-5. Coin Attack: 0-5.
  - Speed Golf: 0-5 + Congo (if it has options).
  - Side Games: Congo only (or 0-5 for training kind 6).
- `FUN_8041358c(entry, idx, row3, row2)` fills one entry.
- **List** 0x8044BC40, **7 entries of 0x2C**: +0 course idx, +4..+0x18 row-2 options (hole-set codes 0-6, side games
  8/7/1/2), +0x1C row-2 count, +0x20/+0x24 row-3 options (tees), +0x28 row-3 count. Count in 0x80445D28. Cursors:
  0x8044AFDC (course), 0x8044AFE4 (row 2), 0x8044AFE0 (row 3), active row 0x8044AFE8.
- **The array is full**: entry 8 would cover live screen state at 0x8044BD74..0x8044BD9F (flags, blink and arrow
  timers, star toggle). 26 `lis 0x8045 / addi -0x43C0` sites address the list base:
  - 0x804123A0, 0x80412660, 0x80413528, 0x8041354C, 0x80413574, 0x804139E8, 0x80413A7C, 0x80413B24, 0x80413BD4
  - 0x80413C14, 0x80413C98, 0x80413D38, 0x80413DD8, 0x80413E18, 0x80413ECC, 0x80413F2C, 0x80413F4C, 0x80413F70
  - 0x80413FA0, 0x80413FB4, 0x80414040, 0x80414080, 0x80414428, 0x80414A1C, 0x80414C7C, 0x80415084
- **Icons**: `FUN_80412640` draws one per entry from texture set B/W/R (`FUN_8000c27c(0x8044ABB4, idx)`):
  - textures 0-6 are the seven 68x68 course icons; texture 7 is a 106x106 star medallion that the records screen
    `FUN_804273d8` uses as a fallback (`li 7`).
  - Layout: x = 320 + (i - (n-1)/2) x 56, half size 24 (40 when selected, x1.2 pulse), y 256. Eight icons span x
    100-540, so they fit.
  - Row-2/row-3 icons come from B/W/S.
- **Preview movie** (`FUN_8041418c`): `cmplwi r0,6` at 0x80414434, then the 7-entry jump table 0x80447564 to file
  0x3E0 + 2 x idx = A/T/C..A/T/I (THP, 20-30 MB each). Idx > 6 falls to A/T/C (Lakitu). It also calls
  `FUN_804134c4(file == 0x3E0)`.
- **Name**: text box with message idx + 0xA8 (tournament: + 0xB2 / + 0xB8), `FUN_8041418c` ~0x80414C7C-0x80414D1C.
  For idx 7 that is 0xAF "Shot Practice".
- **Star overlay**: `FUN_804121b0`, `FUN_80415040`: bit idx of 0x80234A72 (idx 6: 0x8022A3D0 & 0x20). For idx 7 that
  is bit 7, never set (no star version).
- **Commit** `FUN_80415040`: 0x80176079 = idx + 1, plus hole order and count, star tees, pin set.

Other places that list courses:
- **Confirm screen** `FUN_80421898` shows the icon by idx.
- **Continue a saved game**: `FUN_80417c34`/`FUN_80419614` show the icon and name (0xA8/0xB2/0xB8 + byte) of each
  suspended game (copies at 0x801760B0 + 0x20 x slot from the save).
- **Records screens** iterate the 6 tournaments or 7 courses by unlock bits (`FUN_80426f5c`, `FUN_80428af0`,
  `FUN_8042a414`, `FUN_8042e8dc`, `FUN_8042f2d0`). A new course simply doesn't appear there.
- **Password tournaments**: course 0-6 only.
- **Hole intro banner and pause menu**: see section 5 (emblem table, 0xA8 text).

## 7. Text

Bank 0 is the only message bank: a -1-terminated offset table at 0x801431CC, relocated and counted at load
(`FUN_80024508`); lookup `FUN_80022CD0` (id = bank << 24 | index, 50 bank slots at 0x802CBEC0). Course messages:

| ids | text |
| --- | --- |
| 0x95-0x9B | course names, style "\t2" (7) |
| 0x9C-0xA1 / 0xA2-0xA7 | tournament / star tournament names, style "\t2" |
| 0xA8-0xAE | course names, style "\t3\t2" (banner, course select) |
| 0xAF-0xB1 | Shot / Approach / Putting Practice |
| 0xB2-0xB7 / 0xB8-0xBD | tournament / star tournament names, style "\t3\t2" |
| 0xBE.. | hole-set descriptions ("Play all 18 holes", ...) |

The blocks are contiguous, so code 8 lands on the next block: 0xA8+7 = "Shot Practice", 0x95+7 = "Lakitu Cup". The
mod's existing MSG_LOOKUP hook (`build_mod.py`, first instruction of 0x80022CD0) is the place to answer those ids
with the new course name when the current course is 8:
- in a round: golf 0x804E68F4 == 8, or main.dol 0x80176079 == 8;
- on the select screen: the list entry under the cursor has idx 7.

Run `tools\debug_patch.py messages` during a test round to catch any other screen that composes a course name.

## 8. Save data

Mirror 0x8022A3C8, 0xAAAC bytes (shadow copy at 0x80234E74 for "changed since saved", `FUN_80013e4c`). Defaults:
`FUN_80013ea0` / `FUN_800140cc`. The card file is scrambled (the backup GCI in `save-bak\` has no plain records), so
the layout below comes from code. P = 0x8022A3CC (the 0x132C-byte profile).

| address | size | content | course dimension |
| --- | --- | --- | --- |
| P+0 | u16 | golfer unlocks | - |
| P+2 (0x8022A3CE) | u8 | tournament ladder progress | - |
| P+3 (0x8022A3CF) | u8 | course unlocks: bit i opens course idx i+1; bit 5 set after the Bowser tournament | 6 bits |
| P+4 (0x8022A3D0) | u8 | Congo Canopy / side-game unlocks (bits 0-5, `FUN_80469234`) | - |
| P+0x008 + b x 0x2C4 | 6 x 0x3C | tournament records (b = 0 normal, 1 star). The init loop writes 7, the 7th lands on the next table and is overwritten | **6** |
| P+0x170 + b x 0x2C4 | 40 x 6 | per-tournament ranking bytes (0x80 = none) | 6 |
| P+0x260 + b x 0x2C4 | 6 x 18 | best badge per hole (`FUN_80423bbc`, `FUN_80479fd0`, mode 4 only) | **6** |
| P+0x590 | 24 x 0x20 | Character Match records per golfer (`FUN_80469358`) | - |
| P+0x890 / P+0x914 | 22 x 6 / 3 x 6 | per-golfer / per-player course bits (`FUN_800149ec`, main.dol, guarded `course-1 < 6`) | 6 |
| P+0x932 | 4 x 7 x 12 | Club Slots top 3 (`FUN_80468ae4`, mode 8). Group = 2 x option bit 0 + back tees; index g x 7 + code | **7, no guard** |
| P+0xA84 | 4 x 6 x 0x10 | Coin Attack top 3 (`FUN_80468e60`, mode 7), index g x 6 + code | **6, no guard** |
| P+0xC04 | 4 x 7 x 0x3C | Speed Golf top 3 + hole splits (`FUN_80468ffc`, mode 6) | **7, no guard** |
| P+0x1294 (0x8022B660) | 40 x u16 | side-game / training completion bits | - |
| P+0x12E4 | 3 x 0x18 | Near-Pin top 3 per kind (`FUN_80468c6c`) | - |
| S+0x1330 | 3 x 0xD80 | suspended games (start with a copy of the 0xAAD setup block, so they hold the course code) | code stored |
| S+0x3BB8 (0x8022DF80) | 4 x 18 x 0x158 | best-hole replays: birdie, eagle, ace, albatross (`FUN_804681cc`, any mode) | hole stored |
| S+0x9C78 (0x80234040) | 4 x 0x284 | Game Boy Advance link records | - |
| 0x80234A50 | 7 x u32 | **hole-in-one masks** per course, index (code + 7 & 7) % 7 (`FUN_804681cc` writes, `FUN_80401e78` reads for the ace tee marker) | **7, wraps** |
| 0x80234A6B..0x80234A71 | bytes | per-? bits (`FUN_80403b0c`) | - |
| 0x80234A72 | u8 | star-version unlocked, bit per course idx 0-5 | 6 |
| 0x80234A74..0x80234E73 | 1 KB | no references found. Tail padding? Not proven: indexed base+0x10000 accesses can't be ruled out statically | free? |

What a code 8 round would write today:
- **Any mode, 1 human:**
  - The hole-in-one bit goes into course 1's mask ((8+7&7)%7 = 0): a false "aced Lakitu hole n".
  - A best-hole replay saves the hole; viewing it works with the mod. Without the mod it resolves (8, n): holes 0-2
    find the old 3-hole set, others fall back to ID 109, so the replay shows the wrong hole without crashing.
- **Suspended game**: resumes fine with the mod. Without the mod it resumes on the wrong holes, but doesn't crash.
- **Club Slots**: index g x 7 + 8 runs into the next group's course 1 (group 3 runs past the array into Coin Attack).
- **Coin Attack**: index g x 6 + 8 runs into the next group, or into Speed Golf.
- **Speed Golf**: the same as Club Slots, running into the 0x8022B660 bits at the end.
- **Tournament**: records, badges, star bits and the main.dol helpers are all guarded by `course - 1 < 6`, so nothing
  would be saved. The new course has no tournament anyway (names, rivals and unlock flow would all need work).

Stroke Play, Match Play, Skins and Practice write no per-course records of their own. Character Match writes per
golfer.

## 9. Options for adding the course

| option | for | against |
| --- | --- | --- |
| **A. Code 8 (unused slot), menu idx 7** (recommended) | menu rule idx + 1 = code gives 8 for free. Every course table sized 0-9/0-10/0-11 already has an entry 8 that falls back to course 1/2 assets (no garbage pointers). No new course code anywhere. The 3 old course-8 hole-info entries are unreachable | course-8 entries 126-128 must lose to the new ones (lookup order or a byte patch). Save arrays still overflow for 6/7-wide records, so guard them. Text ids collide (0xAF, 0x9C) |
| B. Code 11 | no clash with old entries; `FUN_8041c5ac` already maps 11 -> 6 | 0x804D7324[11] is a garbage pointer (CPU code crash), debug selector stops at 10, menu idx 10 needs every idx-based table extended further. No benefit over A |
| C. Replace a retail course (e.g. Congo Canopy, code 7) | zero code changes: swap files and table entries | loses a course; Congo is the side-games course |
| D. Reuse hole-table slots 701-718 / 801-809 | - | those are live courses (Congo, practice/training); only row 0 cols 0-16 and row 8 cols 9-17 are dead |
| E. Grow tables in place / extend C/L/V | - | data follows every table. Appending to C/L/V lands in its BSS (golf BSS runs to about 0x80529C00 inside the 0x80400000-0x80550000 overlay window). Usable only by padding the image over the BSS and proving 0x8052A000-0x80550000 is free during a round (not checked) |

Hole IDs: they are opaque keys (nothing derives a course from ID / 100), but avoid the special-cased ranges 101-718,
700-799, 801-809 and 1001. Use **1101-1118**.

## 10. Recommendation (code 8): what to build

Free memory: main.dol caves from RE-NOTES (0x80053528 476 B, 0x80054EFC 424, 0x80069F4C 560, 0x8006A834 464,
0x80084B2C 464, 0x80090438 404, 0x80096398 436; 0x80057A14 and 0x8005DAFC are taken by debug patches). Inside the golf
image, hole-file row 0 cols 0-16 (0x804DCF18..0x804DD137, 544 B) and row 8 cols 9-16 (0x804DE238..0x804DE337, 256 B) are
dead data.

Data (no code):
1. **Hole info**: 18 entries (216 B) in a main.dol cave, shared by both overlays: ID 1101-1118, yards, back yards, par,
   course 8, hole 1-18, Ring Attack group 0. The hole-file side supplies the numbers.
2. **Hole files**: 18 entries in golf row 0 cols 0-16 + row 8 col 16. Fields:
   - model, collision, flyover;
   - +8 = 0 (embedded textures);
   - +10/+14 = 0 (no Ring/Coin Attack);
   - ID; name pointer to a new 8-byte string (debug only).
   The resolver's ID search scans row 0 too, so either store these copies with ID 0 (the stub then finds a hole by its
   number), or let the stub in item 7 override whatever the search found.
3. Emblem: golf 0x804D5F9C[8] = the new medallion file (106x106 RGB5A3, texture set like C/O/U).
4. Menu icon: add a 68x68 RGB5A3 icon to B/W/R. Insert it as texture 7 and move the medallion to 8, then patch
   `FUN_804273d8`'s `li 7` to 8. Or append it as 8 and remap idx 7 -> 8 at the three draw sites.
5. New disc files: hole models/collision/flyover, emblem, card, optional sky pair, optional THP preview. Adding files
   to the disc's file system table (FST) is a build-tool question.

Stubs (main.dol caves, the same `b stub` pattern as the mod's other hooks):
6. **Hole-info lookups**: hook the first instruction of the six functions (golf 0x80406F90, 0x80407048, 0x804070C8;
   menu 0x8040094C, 0x80400A04 and its third copy). Search the 18-entry table first, then fall through. This also
   shadows the old course-8 entries.
7. **Hole-file resolver**: in `FUN_80443e14`, after the search (0x80443EC4): if the ID is 1101-1118, copy that hole's
   0x20-byte entry into row 8 col 17 (0x804DE338; never used by practice) and set row 8, col 17.
   Why row 8 col 17:
   - The flyover file loads (row != 0) and the tee-marker logic for rows 1-7 is skipped.
   - The ace swap is skipped too (`row - 1 < 7` is false), so 0x804D28D8 is never indexed past its 7 entries.
   - No relocation of the 5 KB table.
8. **Course card and sky**:
   - card: at 0x80446468 (`bl 0x8000BED8`), set r4 = new card file when the course is 8;
   - sky: at the sky default (0x804462B8 path), when the hole-info course byte is 8, load the new pair.
   Without these the course uses Lakitu's card and sky, which is fine for a first test.
9. **Music**: hook `FUN_80011a94` (main.dol 0x80011A94, first instruction `addi r0,r4,-1`): course 8 -> column 4
   (Blooper Bay, the seaside course), or a new column if a new song is ever made. New music would need a MusyX song
   file plus samples in group 0x59; out of scope.
10. **Menu list**: move the 7 x 0x2C list to an 8 x 0x2C buffer in a cave (patch the 26 lis/addi pairs). Then hook the
    end of `FUN_80413910`: for modes 0, 1 (not Character Match), 2 and 3, append `FUN_8041358c(list + n x 0x2C, 7, 0,
    0)` and n++, with your own unlock rule (always on, or after something). Idx 7 never reads the save's unlock bits.
11. **Preview**: replace `cmplwi r0,6` at 0x80414434 with `b stub`. If idx is 7, set r28 = the new THP (or A/T/F, the
    Blooper Bay preview, as a stand-in) and branch to 0x804144A8. Otherwise run the compare and continue at 0x80414438.
12. **Text**: extend the MSG_LOOKUP hook. Answer 0xAF and 0x9C/0x95+7 (whatever the message log shows) with the new
    course name when the context is course 8 (see section 7).
13. **Saves**: guard `FUN_804681cc`'s hole-in-one store (0x804682DC..0x804682F8) when the course is 8: skip it, or
    store into the free tail once 0x80234A74.. is confirmed unused. Optionally also skip best-hole replays for course
    8, which keeps saves fully mod-independent. With the course limited to modes 0-3 nothing else writes per-course
    data.
14. Later modes, each its own task:
    - Speed Golf and Club Slots: redirect their writers' course-8 records into the save tail, and teach the
      records screens to show them.
    - Ring Attack / Coin Attack: per-hole ring/coin files, hole-info +B groups, and Coin Attack's 6-wide table.
    - Character Match: CPU data (per-hole bytes like 0x804D7298 and position tables).
    - Tournament: names, rivals, unlocks and 6-wide record arrays, so needs a save layout decision.

Things to check in Dolphin when building it:
- that 0x80234A74..0x80234E73 stays zero on a well-played save;
- that the golf overlay never touches 0x8052A000-0x80550000 during a round (only matters for option E);
- the message log on the new course;
- whether the B/W/R loader sizes its buffer from the file (adding a texture grows the file);
- the A/X/K card's exact on-screen use.

## Scripts (`scripts\`)

| file | what |
| --- | --- |
| `courses.py` | parses and rebuilds the course-level tables (hole info x2, hole files, names, emblems, CPU pointers + arrays, ace tee names, songs, BGM, THP jump table); `--check` (byte-identical round trip, all OK), `--text`, `--json` (wrote `..\courses.json`) |
| `holetab.py` | hole info / hole file dumps with disc paths, types and sizes |
| `msgs.py` | message bank 0 dump/search |
| `texlist.py` | texture set lister (magic 0x0020AF30; header-offset table at +8) |
| `ppcdis.py` | small PowerPC disassembler for golf/menu/dol ranges (enough to find patch sites) |
| `scan_refs.py`, `scan_refs2.py` | lis+addi/load reference finders (the second tracks addis/mr chains) |
| `findbl.py` | `bl` call sites into a target from an overlay |
| `grepfn.py`, `grepfn2.py` | grep decomp.c with the enclosing function name |
| `ovl.py` | shared readers for the overlays and main.dol |
