# Hole collision file (hole table +4)

Mario Golf: Toadstool Tour, GFTE01. Static analysis of the golf overlay `C/L/V` (0x80400000) and main.dol, checked
against every collision file on the disc. `collision.py` (same folder) parses all 118 retail collision files and
rebuilds each decoded module and its relocation table byte for byte from the parsed form, and it can write new
files. Addresses are GameCube addresses, `FUN_x` names are Ghidra's (`ghidra_out\golf\decomp.c`).

## Short version for a writer

- The file is a list of **objects**. Object 0 is the terrain ("course"): one mesh, one identity instance. Objects
  1..n-1 are props (trees, tee markers, fences), each a mesh plus an array of placed **instances**.
- A mesh is quantised vertices + 12-byte triangles + a **BVH** (bounding volume tree) whose leaves list triangle
  numbers. There is **no grid**: the ~5216 ADDR32 relocations in A/V/R are BVH nodes of old-version tree meshes,
  and the 11866 in the driving range B/R/U are the BVH of its single old-version terrain mesh.
- Per triangle: 3 vertex indices, 3 normal-table indices (one per corner), and a 16-bit attribute:
  **surface code** in bits 0-7, a **zone** in bits 13-14 (0 in play, 2 out of bounds, 3 hazard/penalty area),
  bit 15 = **two-sided**. The surface code picks one of 65 surface classes in the overlay (fairway, rough, bunker,
  water, OB ...; table below). Everything else about a lie (power %, picture, bounce, sound) comes from that class.
- Coordinates are the hole model's own: **collision unit = model unit, world feet = unit x 32**. The terrain mesh
  is a subset of the hole model's triangles (same vertex positions, bit for bit), plus optional collision-only
  triangles (invisible OB walls).
- There is no green grain or slope field. Greens are surface code 0x02; their break comes from the geometry.
- The block at module stub 3 (0x1AA8 bytes, "hole layout") holds the tee and pin positions and the light direction.
- To write a new hole: `make_mesh()` the terrain, `make_mesh()` any props, `make_collision()`, `build()`,
  `save_packed()`. Use version 0x0131A3CB for every mesh. `python -I collision.py selftest` checks a rebuilt hole
  against the original (ground height and surface at random points: 0 differences on A/V/R, B/Q/R, B/F/A).

## Loading

- `FUN_80444598` (hole loader) loads hole entry +0 (model) then +4 with `FUN_80028240(file id)`: main.dol
  decompresses, applies the relocations (`FUN_80009fc8`) and runs the module's constructor list (module +0, a
  zero-terminated list of function pointers, `FUN_8002e140`). The module pointer goes to `_DAT_805060e0`
  (and loader object +0x24).
- The module exports three functions through `b` instructions at +0x08/+0x0C/+0x10:
  `+8()` = object count, `+C()` = object records, `+10()` = hole layout block.
- Load-time fixups (same function): if count > 1 and object 0's mesh is version > 0x0131A3CA and its root +0x38 is
  0, the global instance BVH (object 1's, record +4) is converted from self-relative offsets to pointers
  (`FUN_804c9000`). Then every mesh with version > 0x0131A3CA and root +0x38 == 0 gets the same treatment on its
  triangle BVH and root +0x38 is set to 1. Older meshes' BVHs are fixed by ordinary ADDR32 relocations instead.
- The loader then sets up query masks and an instance-removal list (see Queries) and places tees and pins
  (`FUN_80402400`).

## Module layout

All offsets are module offsets; big-endian. Relocation table: sorted by offset, kinds 0 ADDR32, 1 REL24, 2 HA16,
3 LO16 only, all module-relative.

| Offset | Content |
| --- | --- |
| 0x00 | ADDR32 -> end-8 (constructor list: one zero word) |
| 0x04 | ADDR32 -> end-4 (second empty list, presumably destructors) |
| 0x08 / 0x0C / 0x10 | `48000000` with REL24 -> 0x14 / 0x1C / 0x28 |
| 0x14 | `li r3, count` ; `blr` |
| 0x1C | `lis r3,0` (HA16) ; `addi r3,r3,0` (LO16) -> object records ; `blr` |
| 0x28 | same -> hole layout block ; `blr` |
| 0x34-0x3F | zero |
| 0x40.. | data, in this order (every retail file): |

1. Mesh blocks of objects 1..n-1, then object 0's. Each block: vertices, triangles, BVH leaf lists, BVH nodes,
   mesh root (0x3C). Blocks start 4-aligned.
2. The global instance BVH (object 1's record +4; only in files whose object 0 is version 0x0131A3CB): lists, nodes.
3. Instance arrays of objects 1..n-1, then object 0's (0x2C each).
4. Object 0's instance BVH (one leaf `[0x0000, 0xFFFF]` + one node; relocated). In old-format files every object's
   own instance BVH would go here.
5. Object records, 0x28 each.
6. Hole layout block, 0x1AA8 bytes.
7. Names, NUL-terminated, each padded to 4 bytes. Objects without a name (B/R/U) have none.
8. 8 zero bytes (the two lists from header +0/+4), 4-aligned.

**Stored values of relocated words** (needed for a byte-exact rebuild; the game overwrites them): 0, except name
pointers (offset of the name inside the name block) and internal BVH links of relocated BVHs (target minus BVH root).

### Object record (0x28)

| Off | Field |
| --- | --- |
| +0x00 | -> mesh root |
| +0x04 | -> instance BVH root, or 0. Object 0: one-leaf BVH (relocated). Object 1: the global BVH of every prop instance (self-relative). Objects 2+: 0. |
| +0x08 | -> instance array (count is implicit: arrays are contiguous; the model's object table has the counts) |
| +0x0C | bbox min xyz, max xyz (floats). Object 0: = its mesh bbox. Object 1: bounds of every prop instance's transformed vertices (no margin). Others: zero. |
| +0x24 | -> name ("course", "mur_0001_tree", "mur_0101_tee" ...) or 0 |

### Instance (0x2C)

`+0 flags` (1 translate, 2 scale, 4 rotate; 0 = identity), `+4 position xyz`, `+0x10 scale xyz` (only x is used:
uniform), `+0x1C quaternion xyzw`. Applied scale, rotate, translate (the query transforms the ray by the inverse).
Identical records (same values) are in the hole model's object table, keyed by the same names.

### Mesh root (0x3C)

| Off | Field |
| --- | --- |
| +0x00 | version = build date as a number: 0x0131A2B1 (2003-01-17), 0x0131A313 (2003-02-27), 0x0131A3CB (2003-04-11) |
| +0x04 | -> vertices |
| +0x08 | -> triangles |
| +0x0C | 0 (the old query path reads a 2D grid here when non-zero; no file uses it) |
| +0x10 | -> BVH root node |
| +0x14 | bbox min xyz, max xyz: vertex bounds +- about 0.0098 (the root box for traversal) |
| +0x2C | vertex format: component type << 8 \| fraction bits (0x3xx = s16; terrain uses 0x308-0x30D) |
| +0x30 | triangle count |
| +0x34 | vertex count (0 in 0x0131A2B1 meshes) |
| +0x38 | 0 in the file; set to 1 by the loader after the BVH fixup |

Version effects: < 0x0131A313: mesh coordinates are hundredths of a foot (the game scales the ray by 3200 =
32 x 100 instead of 32, and multiplies instance translations, still in collision units, by 3200).
<= 0x0131A313: BVH links fixed by relocations. > 0x0131A3CA: self-relative BVH fixed at load. The query path is
chosen by object 0's version: exactly 0x0131A3CB -> `FUN_804382d4` (global instance BVH); anything else ->
`FUN_804379b4`'s per-object loop. Retail: 117 files new path, B/R/U old path, B/R/P (TEST1, hole 1001, unused) is a
version-0 pre-release format with 0x20-byte float BVH nodes (not handled by collision.py).

### Vertices

`count x 3` components of the root's format (s16 in practice), value / 2^frac in collision units. Terrain meshes
use 8-13 fraction bits, mostly 9 (s16 / 512 covers +-64 units = +-2048 ft, in steps of 1/16 ft).

### Triangle (12 bytes)

| Off | Field |
| --- | --- |
| +0 | u16 v0, v1, v2 |
| +6 | u8 n0, n1, n2: corner normals, indices into the 256 unit normals at 0x804CE58C (254 = straight up) |
| +9 | 0 |
| +0xA | u16 attribute |

- Front face: normal = normalize((v2 - v1) x (v1 - v0)), as `FUN_80435284` computes it, i.e. the usual
  right-handed (v1 - v0) x (v2 - v0) points to the BACK. Ground triangles have that cross product pointing down
  (negative y): clockwise on a map drawn with x to the right and z downwards. Checked: 0 back-face-only hits on
  random vertical rays; `make_mesh` and the OBJ export follow this.
- Attribute: bits 0-7 surface code (the hit stores the u16; readers take the low byte), bits 13-14 zone, bit 15
  two-sided. Bits 8-12 are unused by retail; v12's course marks another hole's fairway, fringe and green with bit 8
  for its auto-aim stub (`collision.ATTR_OTHER_HOLE`, RE-NOTES "Auto-aim"). In `FUN_80436cf0`: bit 15 clear -> only rays from the front collide; set -> both faces, except for
  queries in mode 1 (query +0x1C = 1, the ball step uses it while the ball is sunk). Zone: the ball step stores
  `(attr >> 13) & 3` in ball +0xC8; 2 = out of bounds whatever the surface (`FUN_8041cc34`), 2 or 3 = ball lost,
  penalty drop (`FUN_8041ccbc`). Zone 1 is never used. If a downward probe hits nothing the ball gets code 6, zone 2.
- Corner normal bytes are copied into the hit (+0x28..+0x2A); their only reader is `FUN_8043ae04` (barycentric
  smooth normal), which nothing calls. Physics uses the face normal. Terrain mostly has all three equal (the
  face normal's nearest table entry); about 10 % of terrain triangles have per-vertex normals.

### BVH

Leaf lists: u16 item numbers ending with 0xFFFF (triangle numbers; for instance BVHs `object << 8 | instance`).
Nodes, 12 bytes: `u32 link, u8 q[6], u16 0`.

- Internal node: link -> right child; the left child is the next node (depth-first layout).
  Leaf: link -> its list. The traversal tells them apart by address: **a link below the node is a leaf**, so all
  lists precede all nodes, and right children come after their parent.
- Stored link = target - BVH root (leaves negative). Self-relative BVHs keep that; relocated ones (meshes
  <= 0x0131A313, object 0's one-leaf instance BVH) carry an ADDR32 for every node and store 0 for leaves.
- Boxes: the root box is the mesh bbox (or the record bbox for instance BVHs). Each node's q shrinks its parent's
  box: `min += extent * q[0..2] / 256`, `max -= extent * q[3..5] / 256` (`FUN_80437168`: psq_l with GQR5 =
  0x08040804, u8 / 2^8, float32 fmadds / fnmsubs). The root node's own q applies to the root box.
- Traversal (`FUN_804372c0` thin/fat segment, `FUN_80437414` with the object mask, `FUN_8043761c`/`FUN_804377e8`
  for spheres): box test, then left first; a leaf ORs its list into a 64K-bit candidate set (`FUN_80436ac4` /
  `FUN_80436c54`), so items listed in several leaves cost nothing. Candidates are then tested exactly.
- Retail layout details: lists in leaf (depth-first) order; for self-relative BVHs each list starts 4-aligned
  (zero padding), relocated BVHs pack lists 2-aligned; nodes 4-aligned after the lists. The original tool built a
  spatial (kd-tree-like) tree: leaves average 12 triangles, a triangle appears in 3.8 lists on average, leaf boxes
  do not contain whole triangles. An ordinary object-partition BVH (every box contains its items) is equally valid;
  `build_bvh` makes one.

### Hole layout block (module stub 3, 0x1AA8 bytes, collision units)

| Off | Content | Evidence |
| --- | --- | --- |
| +0x000, +0x00C | tee 0, tee 1 (xyz); +0x018 a third, zero in retail | `FUN_80402400` snaps both to the ground (`FUN_804011b4`) |
| +0x024..+0x053 | 4 pin positions; which one is chosen by the pin setting (0-3 or random) | `FUN_80402400` -> `FUN_8040100c` |
| +0x054..+0x0B3 | 8 positions (hole 501 only: effect objects) | `FUN_80444598`, hole id 0x1F5 |
| +0x0B4..+0x173 | 8 pairs of positions; the ball is moved to the nearest (gimmick exits, course 5/6 holes) | `FUN_80417b00` |
| +0x174..+0x2F3 | used by a few course 5/6 holes, meaning unknown | |
| +0x2F4..+0x473 | 16 pairs of positions, nearest one chosen | `FUN_80417938` |
| +0x474 | light direction (unit vector, default -0.707, -0.593, -0.385): shadows | loader -> 0x805016C0, 0x8050F084 |
| +0x480..+0x50B | a few course 3/5/6 holes; unknown | |
| +0x670.. | Congo Canopy's shared file (B/Q/R, 18 holes): a tee per hole (+0x670 + 12 x n) and 4 pins per hole (+0x748 + hole x 0x30 + pin x 12); read instead of +0x000/+0x024 when byte +0xD10 of the round object is 7 | `FUN_80402400` |
| +0xAA8.. | 0x20-byte entries (word 1.0 or 3.0, xyz, ..., 1.0) in 9 holes of courses 2-5; unknown | |

Normal holes fill only tees 0-1, pins 0-3 and the light direction. Positions are x32 = feet (x0.01 if object 0
is older than 0x0131A313).

## Surface codes

The surface table is 65 pointers at 0x804D93C0 (`_DAT_804e68ac` points to it) to 39 static objects at
0x805245B8 (constructed by `FUN_804c4760`), one vtable each (0x804CB138 + 0x48 x k). Codes above 0x40 index past the
table. The methods: [0] out of bounds, [1] ball lost (penalty), [2] category, [3] lie index (end-of-shot message
0x834 + n, and the row of the lie tables), [4] lie picture (texture file id 0xC05 + 2n, `FUN_8042dab8`),
[5] bounce restitution, [6] roll/speed retention (constant or a function of time), [7]/[8] 90/100 (all), [9]
`FUN_80416ad4` lie power limit, [10] `FUN_80416cd4`, [11] a 0-100 score used for drops (>= 80 required by
`FUN_80416da4`, > 10 by the drop search `FUN_80426f38`), [12] -1/439/599, [13] 0/1, [14] landing sound id.
Lie index "a-b" = depends on the ball's sub-lie (ball record +0x30, 0-3).

| Code | Name (lie text) | OB | Lost | Lie index | Bounce | Score | Sound | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 00 | Tee Box | | | 0 | 0.4 | 70 | 413 | |
| 01 | Fairway | | | 4-7 | 0.4 | 80 | 413 | |
| 02 | Green | | | 26 | 0.4 | 100 | 413 | roll function `0x804CBDC4` depends on 0x804E66CC (green speed?) |
| 03 | Bunker | | | 16-19 | 0.1 | 30 | 415 | |
| 04 | Rough | | | 10-12 | 0.2 | 50 | 416 | |
| 05 | Water | | yes | - | 1.0 | 0 | 552 | message "Water Hazard" |
| 06 | OB | yes | yes | (10-12) | 0.2 | 0 | 416 | also assumed when nothing is under the ball |
| 07 | Cart Path | | | 25 | 1.0 | 10 | 560 | |
| 08 | Tee Box | | | 1 | 0.4 | 70 | 413 | second tee variant |
| 09 | Rock | | | 23 | 1.0 | 10 | 560 | cliffs, walls |
| 0A | Semi-Rough (first cut) | | | 8-9 | 0.4 | 70 | 413 | |
| 0B | Fringe | | | 2-3 | 0.4 | 80 | 413 | |
| 0C | Tree Hazard | | | 10-12 | 0.2 | 50 | 422 | tree foliage, plays as rough |
| 0D | Tree Hazard | | yes | 13-14 | 0.2 | 0 | 586 | ball lost in the tree |
| 0E, 0F, 10 | OB | yes | yes | | 0.2 | 0 | 416 | |
| 11 | Fast Fairway | | | 27-30 | 0.4 | 80 | 413 | roll 0.9 |
| 12 | Heath (Flower Patch on course 5) | | | 15 / 42 | 0.2 | 20 | 537 | |
| 13 | Tree Hazard | | | 10-12 | 0.2 | 50 | 422 | like 0C |
| 14, 15, 18, 19 | Water | | yes | | 1.0 | 0 | 553 | `FUN_80417ac0` = 1 |
| 16 | Heavy Rough | | | 13-14 | 0.2 | 20 | 537 | |
| 17, 22 | Waste Area | | | 22 | 0.2 | 30 | 595 | |
| 1A | Mushroom | | | 40 | 2.0 | 10 | 596 | bounces the ball up |
| 1B | OB | yes | yes | | 0.0 | 0 | 416 | invisible OB walls (0xC01B in B/Q/R) |
| 1C | Water | | yes | | 1.0 | 0 | 553 | `FUN_80417ac0` = 2 |
| 1D | Pipe | | | 35 | 1.0 | 0 | 532 | |
| 1E | OB | yes | yes | | | | 416 | ball step also special-cases 0x1E (gimmick object) |
| 1F, 20 | Rock (OB) | yes | yes | 23 | 0.97 | 10 | 487/560 | |
| 21 | Grass Bunker | | | 20 | 0.2 | 20 | 537 | |
| 23, 26 | Wood | | | 24 | 0.9 | 10 | 531 | bridges, fences |
| 24 | Beach Bunker | | | 31-34 | 0.1 | 30 | 422 | |
| 25, 27, 28 | Rock | | | 23 | 1.0 | 10 | 560 | |
| 29 | Thwomp | | | 41 | 0.8 | 10 | 560 | |
| 2A | Tree Hazard | | yes | 13-14 | 0.8 | 0 | 590 | |
| 2B, 2D, 36-40 | OB | yes | yes | | 0.2 | 0 | 416 | |
| 2C | OB | yes | yes | | 0.2 | 0 | 491 | ball step special case |
| 2E | (message "OB") | | | 10-12 | 0.2 | 0 | 540 | not flagged OB |
| 2F | - | | | 10-12 | 0.5 | 0 | 487 | |
| 30 | Rock | yes | | 23 | 1.0 | 0 | 560 | OB but not "lost" |
| 31 | Brick | | | 43 | 1.0 | 10 | 417 | |
| 32, 33, 34 | Rock | | | 23 | 1.0 | 0 | 554/585/525 | |
| 35 | - | | yes | 13-14 | 0.8 | 0 | 590 | like 2A |

Lie names (message 0x834 + n): 0-1 Tee Box, 2-3 Fringe, 4-7 Fairway, 8-9 Semi-Rough, 10-12 Rough, 13-14 Heavy
Rough, 15 Heath, 16-19 Bunker, 20 Grass Bunker, 21 Bare Ground, 22 Waste Area, 23 Rock, 24 Wood, 25 Cart Path,
26 Green, 27-30 Fast Fairway, 31-34 Beach Bunker, 35 Pipe, 36 Stone Bridge, 37 Wooden Bridge, 38 Path,
39 Pavement, 40 Mushroom, 41 Thwomp, 42 Flower Patch, 43 Brick. Special messages from `FUN_80433700`: water codes
(05, 14, 15, 18, 19, 1C) "Water Hazard" (0x830), codes 0C, 0D, 13, 2A "Tree Hazard" (0x833), OB "OB" (0x82F),
with "Safe Drop Zone" variants (0x831/0x832). Lie effects, all keyed by the lie index (method [3]) and the club,
applied in the aim update `FUN_8041073c`:
- method [9] `FUN_80416ad4`: the lie's power cap in meter steps (setup +0x250; 60 = full meter), from 7-byte rows
  (club groups) at 0x804CDA58 and 0x804CDB8C (approach shots 0x804CDCC0 / 0x804CDDF4) plus the golfer's power stat:
  tee 60, fairway 57-59 (sub-lies 0..3 down to 48), first cut 47-56, rough 35-53, heavy rough 29-45, bunker 21-54,
  green 60. This is presumably the HUD's lie %.
- method [10] `FUN_80416cd4`: a second value per lie and club (setup +0x238), rows at 0x804CDF28 / 0x804CE05C
  (1 on tee and fairway, rising to 15 on bad lies).
- `FUN_804169d0`: the impact-timing tolerance (`_DAT_80523cb0`; the shot builder `FUN_804c6668` mishits when the
  impact error exceeds it), from 13-byte rows at 0x804CD5E0 / 0x804CD81C.
- Putting: code 02 (lie 26, full power, roll function 0x804CBDC4). Green and fringe (codes 02, 0B) also get a
  fixed cap of 30 or 45 steps in `FUN_80416ad4` depending on 0x804E6858 / 0x804E66CC.

Retail use (A/V/R terrain): 01 fairway 2390, 04 rough 2509, 16 heavy rough 1857, 06 OB 1806, 05/18 water,
02 green 375, 03 bunker, 0A first cut, 0B fringe, 08 tee, 09 rock. Trees: 0C/0D. Tee markers: 09 or 08.
Common attribute words: 0x0001 fairway, 0x4006 OB ground, 0x6005 water in a hazard zone, 0xE00C two-sided tree.

## Queries (code that reads the file)

Query input (7 floats, feet): origin xyz, delta xyz (segment = origin + t x delta, t in 0..1), radius
(0.14 ft = the ball). Result struct: +0 hit buffer (0x34 each), +4 pointers, +8 capacity, +0xC hit count (sorted by
t, `FUN_8043461c`), +0x10 candidates, +0x14 instance matrix, +0x18 instance scale, +0x1C mode, +0x20 instance,
+0x24 mesh root. Hit (0x34): +0 t, +4 point (feet), +0x10 normal, +0x1C plane d, +0x20 attribute (u16, so the
code is the byte at +0x21), +0x22 v0/v1/v2, +0x28 corner normal bytes, +0x2B edge/vertex contact, +0x2C mesh root,
+0x30 instance. Coordinates are divided by 32 (`DAT_804dc484`) on the way in and multiplied back for the hit.

| Function | What |
| --- | --- |
| `FUN_804379b4(result, segment, type)` | swept-sphere segment cast. New files -> `FUN_804382d4` |
| `FUN_80438964` -> `FUN_80438ef0` | sphere overlap (centre, radius) |
| `FUN_8043a58c` -> `FUN_8043a9f4` | another sphere query |
| `FUN_804382d4` | walks object 0's and object 1's instance BVHs (with the type mask), removes listed instances, transforms the ray per instance, then `FUN_80436cf0` per mesh |
| `FUN_80436cf0` | mesh BVH walk, vertex fetch (GQR5 from root +0x2C), one/two-sided triangle tests; straight-down rays use a 2D test (`FUN_80436a28`) |
| `FUN_80435284` | sphere vs triangle, fills the hit (`FUN_80434534` keeps the nearest when full) |
| `FUN_80436280` / `FUN_80436558` | segment vs box, thin / widened by the radius |
| `FUN_80437168` | node q decode |
| `FUN_804c9000` | load-time BVH fixup |

Query type (third argument): 0 = everything (the ball in flight and bouncing, `FUN_80417b00`), 1 = object 0 only
(ground probes, tee placement, lie, camera, drops: the loader sets mask 0x80506220 to all objects but 0), 0xFFFF =
a flat test plane instead of the file (`FUN_80435094`). The loader also fills a removal list (0x805060E4, up to
0x80 `object << 8 | instance`): instances of "mur_0001_tee", and on course 7 the "mur_0701_tee" markers of the
other 17 holes, never collide.

Callers: `FUN_804011b4` (ground at x,z: sphere cast from y + 3.2 ft down 160 ft, returns point and normal; tees,
replays), `FUN_8040100c` (pins), `FUN_80416f34` (surface code), `FUN_8041704c` (surface object),
`FUN_80416da4` (all hits score >= 80), `FUN_80417174` (segment end point), `FUN_80417b00` (ball step: bounce with
[5] and [6], sound [14], then a probe sets ball +0xB8 = code and +0xC8 = zone), `FUN_8042dab8` (lie picture),
`FUN_80433700` (end-of-shot lie text), `FUN_80426f38` (drop point search), `FUN_80410838` (aim camera),
`FUN_804379b4`'s 31 callers in all.

## Relation to the hole model (+0 file)

- Same coordinate system and quantisation: A/V/Q's positions are s16 / 512 like A/V/R's terrain (format 0x309).
- Every terrain triangle is a triangle of the model with the same vertex positions: A/V/R 10329/10329, A/Y/J
  15729/15729, B/F/A 21932/21932; B/Q/R 21780/21982, the other 202 being collision-only (200 x 0xC01B invisible OB
  planes, 2 x 0x4023). Surface codes follow the model's meshes (A/V/Q mesh 5 = fairway, 7 = green, 4 = rough,
  3 = heavy rough, 9 = water, 2 = OB ...). Model vertex colours are unrelated.
- Props: the model's object table (stub +0x20 in A/V/Q -> 0x4697E8, 0x10 each: model root, instance count,
  instances, name) has the same names and identical instance records. Visual-only objects (birds, fish) are absent
  from the collision. Prop collision meshes reuse the prop model's geometry (all 279 vertices of A/V/R's
  "mur_0001_tree" collision mesh are vertices of the model's mur_0001_tree, same s16 / 2^14 format).

## Limits and rules for a writer

- Use version 0x0131A3CB for every mesh (object 0's must be exactly that for the new path), root +0x38 = 0,
  +0x0C = 0. Lists before nodes, right children after parents, left child = next node.
- Up to 65535 triangles and 65536 vertices per mesh (u16, 0xFFFF ends lists; candidate bitset is 64K bits).
  Retail max: B/O/N terrain 43603 triangles, 22962 vertices, file 2.3 MB.
- Up to 256 objects and 256 collidable instances per object (`object << 8 | instance`): B/N/J's "mur_0601_ashi"
  has 270 instances but only 0-255 are in the BVH.
- BVH depth under 256 (traversal stacks); retail max 34.
- s16 vertices: choose fraction bits so the largest coordinate fits (`vertex_format`).
- Child boxes are decoded from the parent's decoded box in float32; quantise conservatively (round q down).
- Instance count is implicit; keep the arrays in the file order above.
- Holes load into a 9 MB arena (`FUN_80443e14`), shared with the model and other hole files.

## collision.py

```
python -I collision.py roundtrip-all          # 118 of 118 files rebuilt byte-identically
python -I collision.py roundtrip A/V/R B/Q/R B/R/U
python -I collision.py info A/V/R             # objects, surfaces, tees, pins
python -I collision.py obj A/V/R out.obj      # every instance in feet, grouped by surface code
python -I collision.py selftest A/V/R         # rebuild with the writer, compare ground/surface at 400 points
```

Library: `load`, `parse`, `build`, `save_packed`, `make_mesh(points, faces)` (faces = (i0, i1, i2, attr),
points in collision units), `attr(code, zone, two_sided)`, `instance(pos, scale, yaw_degrees)`,
`make_collision(course_mesh, props, layout)`, `make_layout(tees, pins, light)` (feet), `build_bvh`,
`normal_table`, `ground(mesh, x, z)`, `world_triangles`, `SURFACES`.

`collision_tools\` has the research helpers: `ppcdis.py` (a small Gekko disassembler that, unlike the Ghidra export,
decodes paired-single instructions such as `psq_l`), `dumpr.py` (hex dump with relocation targets), `msgs.py`
(main.dol message bank), `surftable.py` (surface vtables), `holes.py` (hole table).

## Open questions

- Methods [2], [7], [8], [10], [12], [13] of the surface classes: values known, use not traced.
- The ball's sub-lie (ball +0x30, 0-3) that picks the lie variant is computed outside this file (likely from
  slope or bounce); not traced.
- Layout block +0x174..+0x2F3 and +0x480..+0x50B (a few course 3/5/6 holes) and most of the course 7 area.
- Whether the green's speed comes from method [6] alone (function `0x804CBDC4` reads byte 0x804E66CC).
- Code 0x2E shows "OB" without being OB; codes 0x1E and 0x2C have extra ball-step handling (gimmicks).
- Tee 1 (+0x00C) is presumably the back tee (Lakitu Valley hole 1: 349 yd tee 0 to pin 0, 363/385 on the
  scorecard); not checked in game.
