# Maintainer tools

Everything here runs on the maintainer's PC against a clean, extracted GFTE01 disc. Nothing in this folder contains game data.

| Tool | What it does |
|---|---|
| `camelot_lz.py` | Camelot LZSS codec (decode, encode, relocation tables), reimplemented from `main.dol` (`FUN_8000b134`, `FUN_8000a16c`, `FUN_80009fc8`) |
| `unpack_all.py` / `repack_all.py` / `roundtrip_test.py` | Decode every file to `unpacked\` plus a manifest; re-encode and verify |
| `build_mod.py` | Applies every mod change to a copy of the clean tree, checking each original instruction first |
| `make_patch.py` | Diffs the build into `mod/patches/vN.json` (format 2: decoded-level edits plus result hashes; `rebuild` ops for files that grow or change relocations, with runs of the original moved by copy instructions so no game data goes in; from v11 `create` ops for our courses' files, whose own bytes go in gzip files instead of the JSON: v11-v21 one `vN.data.gz` next to the patch, from v22 one per course under `mod/data`, named by hash, so an unchanged course is never uploaded or downloaded again; v24 `recolours` steps on create ops, and created files start from copies of game files wherever their bytes match one, in place or moved) |
| `publish.ps1` | Builds, writes the patch, does a reference build with the friends' C# code, and updates `mod/latest.json` |
| `ppc.py` | Tiny PowerPC encoder for patch stubs, self-tested against known machine code |
| `shyguy.py` | Shy Guy as a 17th golfer (`build_mod.py --shyguy <folder> --shyguy-voice <zip> --shyguy-mpt <disc>`): builds golfer 16's models from Koopa Troopa's around his model (Mario Power Tennis', or the OBJ without `--shyguy-mpt`), encodes its texture, renders the menu pictures and the "More" label, sets his stats, builds his voice set |
| `tony.py`, `glb.py` | Tony the Tiger as an 18th golfer (`build_mod.py --tony <folder>`, with `--shyguy`): reads his rigged Blender export (`source\untitled.glb`; `glb.py`), simplifies it to about 4,300 triangles with texture coordinates and bone weights sampled back from the original, fits it to Waluigi's skeleton, and builds golfer 17's models from Waluigi's with the game's own smooth skinning (`skinned_swap`; format in `RE-NOTES.md`), plus his texture, pictures and link record entry. Needs `pip install fast-simplification` (MIT) |
| `costumes.py`, `looks.py` | Halloween costumes (v24, built with every build): Y on the character select and the round's file swap (caves "data", "menu", "round"), each golfer's costume files under disc folder `I` (in-round model, second model, texture bank, select screen model). `looks.py` holds each golfer's look: colour rules made into 64K colour tables that Play recolours the player's own textures with (patch `recolours` steps), skeleton and bandage patterns, Dry Bones' eyes; `costumes.py` adds Daisy's bikini and Birdo's chest |
| `skill.py` | A harder game (v25, built with every build): the slope grid on the green for every shot, never round the landing spot (v26; v25 showed it only while putting), narrower impact windows (not Tony's), more bend from a press off the mark, more power spread from bad lies (one cave; tunables `BEND`, `SPREAD_FROM`; v25's auto swing misses were taken out in v26) |
| `knockout.py` | Knockout (v30), a Team Play game (built with every build; its menu cave and round stubs come with `teams.py`'s): 2-4 players or 2v2 on 3 lives, the worst score on a hole loses one, the last one standing wins; v31: 3-4 players play a tie for the worst off (one shot each from a random spot, closest to the pin), 2 players and 2v2 push a tie, and leaders level on lives at the end play a tiebreaker on a random hole. A Wolf round plus the setup byte 0x8017607F; the shooter pick, scoring, points, scorecard totals and the round-over test get stubs in the golf tail; the notice in the game's tip box |
| `football.py` | (Out of the build since v30: `teams.PIGSKIN`, kept for a later football game; `fbpose.py`, `fbmoves.py`, `rigmap.py` and `fbhud.py` too.) Football (v27), a Team Play game (built with every build, its caves and hooks come with `teams.py`'s): passes to the partner, who runs, jumps and dives to catch under their own camera, and giant field goal posts at the pin; the pass/kick pick, the catch and the kick's plane, the boxes saying what happened (29 small caves; tunables in `TUNING`); v29 `fb_fast` (cave "fast"): passes fly their same path `fbpose.PASS_SPEED` times as fast |
| `fbpose.py` | Football's players (v27): the receiver drawn as the partner's golfer (its model in holders of our own), the poses built bone by bone from `fbmoves.py`'s keys (run, jump, dive, catch, the QB's throw and kick over the game's swing), no clubs in their hands, and the spiralling football; code and data in the golf overlay's tail (`golfext.py`); test switches in its data (`dbg_near`, `dbg_clip`, `dbg_ball`, `dbg_noqb`). v28 Pigskin: up to three receivers (a slot per player, each on its own pad, bumping apart, models in heap 0 or 2 by free space), the QB rotating round a team of 3-4, the landing star moved to the predicted touchdown in flight, the football in the QB's hand, no golf hit sounds |
| `fbmoves.py` | Football's poses: keyframed joint rotations for one canonical body (Y up, facing +Z, a T), the run cycle, jump, dive, down, catch, hold, throw and kick; `python fbmoves.py [codes] [clips]` checks the run-time maths and draws stick figures (`screens/fbmoves_sheet.png`) |
| `rigmap.py` | Which bones of each golfer's in-round model are its hips, spine, chest, neck, head, arms and legs (found from the bind positions and the bone tree; Shy Guy and Tony on their bases' skeletons); `python rigmap.py` prints all 18 |
| `fbhud.py` | Football's shot type badge (v27): the HUD's club picture and name (files 0xA45.., 0xA29..) taken from our own files under the disc folder J in Football: each shot type's name and a football, drawn here |
| `golfext.py` | The golf overlay's tail: code and data appended to `C/L/V` at 0x80528000 (free while a round runs, up to the overlay load's 0x80550000) |
| `course8.py` | Our courses (`build_mod.py --course8 .. --course9 .. --course10 .. --course11 <course folders>`): course code 8 (Pebble Beach) and 9 (Pasadena; Battleground and Timber Creek as code 9 with a variant byte), hole IDs 1101-1172, hooks for the hole tables, the course select list and commit, name, icon, emblem, HUD card, sky, music and preview (caves 11-13, 15, 16, 18-23) |
| `coursemenu.py` | The course select's dropdown (v26, with `--course8`): the course row shows the picked course's icon, A opens a list window of the mode's courses by name (scrolling, `VISIBLE` at a time), Up/Down move the course select's own cursor, A picks, B goes back; Toad's box shows the buttons. Uses course8.py's list and name stub; eight small caves |
| `modemenu.py` | Team Play's game list as a dropdown (v28, with every build; its caves and hooks come with `teams.py`'s): the row shows the picked game's icon, A opens a list window of the games by name (`VISIBLE` at a time, scrolling), Up/Down move the list's cursor, A plays, B goes back; Left/Right still step. Seven small caves |
| `course/` | Generates our courses from real data (`TTMOD_COURSE=pebble|pasadena|battleground|timbercreek`): `fetch_data.py` downloads OpenStreetMap and elevation data, `canopy.py` the canopy heights the Texas courses' trees come from (`forest.py` places them), `holegen.py <course folder>` builds each hole's model, collision and flyover camera, `coursejson.py <course folder>` writes the `course.json` the build reads. `collision.py`, `holedata.py` and `modlink.py` read and write the hole file formats; `notes/` has the full write-ups |
| `mpt.py` | Reads a Mario Power Tennis disc (GOME01, .iso or .ciso) and Shy Guy's model there (`B/G/P`) for `shyguy.py` |
| `musyx.py` | MusyX sound groups (pool, project, sample directory, samples) and a GameCube DSP ADPCM encoder and decoder |
| `model.py`, `textures.py` | Read character models (meshes, groups, display lists, bones) and texture files (decode RGB5A3, CMPR, I and IA formats; encode RGB5A3) |
| `find_dead_code.py` | Confirms a `main.dol` function is referenced nowhere on the disc, so it's safe to reuse for patch code |
| `dol2elf.py`, `ghidra_export.ps1`, `ghidra_scripts/` | Ghidra headless analysis: `main.dol` plus overlays as one ELF, then exported C and disassembly helpers |
| `find_func.py`, `scan_code.py`, `survey_headers.py`, `patch_text.py` | Investigation helpers |
| `tools/` | Live testing against a running Dolphin (read/write game RAM, trace cameras and power, find values and strings, log draws and messages with `debug_patch.py`) and Ghidra disassembly (`dumpasm.ps1`). See [`RE-NOTES.md`](RE-NOTES.md#testing-workflow). |

**[`RE-NOTES.md`](RE-NOTES.md) is the reference for everything learned about the game's code:** addresses, structures, the hooks each version adds, and the free memory used for patch code. Read it before changing a hook, and add to it when you find something.

## Key facts

- **Game code:** the golf overlay `C/L/V` is a flat image loaded at 0x80400000. `B/U/C` is a second overlay at the same address. Small-data bases are r2 = 0x802DF480 and r13 = 0x802DFA60.
- **Patch code location:** the stubs live over dead functions in `main.dol` (ten so far; list in `RE-NOTES.md`). Don't put code at 0x80001800; it gets wiped before the first frame is drawn.
- **Disc layout:** files sit at the outer end of the disc, aligned to 32 bytes. Everything between the file table and 0x1032F9A0 (about 271 MB) is free. `TTMod.Build` moves any file that grows into that space, and from v11 adds files the game doesn't have (the 8th course's, under a new top-level folder `E`) to the file table and that space.
- **Game ID:** keep GFTEMD across versions so saves carry over. The version number goes in the banner title.

## Publishing version N

```
powershell -ExecutionPolicy Bypass -File dev\publish.ps1 -Version N -CleanGame <clean .ciso> -CleanDisc <extracted clean disc> -BuildDir <scratch dir>
git add -A
git commit -m "Mod vN"
git push
```

If you change anything in `app\`, bump `app\version.txt` before publishing (v10 did: `Install-ModHotkeys` sets the fullscreen toggle and Esc; v11 did: `create` patch ops, the patch's data file and new disc files). `Play.bat` then updates its own scripts on everyone's PC before installing the new mod.

From v7 the build needs Shy Guy's source model: `Shy Guy.obj` and `heyho_body_alb.png` from the Sketchfab download, in `assets\shy-guy` next to the repo (or pass `-ShyGuy <folder>`). Only the converted model goes into the patch: golfer 16's files are built from Koopa's (named as each file's `base` in the patch), and Koopa's data in them goes in as copy instructions, never as bytes. From v8 it also needs his voice clips (`-ShyGuyVoice`, default `assets\shy-guy\mario-power-tennis-shy-guy-voice.zip`: the Sounds Resource's Mario Power Tennis "Shy Guy's Voice"); `shyguy.VOICE` says which clip plays for each of his lines, and the encoded samples go into the patch as a `replace` op. From v9 his model comes from Mario Power Tennis (`-ShyGuyMpt`, default `gamecube_games\Mario Power Tennis (USA) (Rev 1).ciso` two folders above the repo: the maintainer's own disc); the OBJ is then only a fallback, and the converted model and pictures go into the patch as before.

From v11 the build also needs the 8th course (`-Course8`, default `mod\course8` next to the repo). Make it once:

```
python -I dev\course\fetch_data.py
python -I dev\course\holegen.py ..\mod\course8
python -I dev\course\coursejson.py ..\mod\course8
```

`holegen.py` writes each hole's three files under `E\<hole letter>\` plus `A.prov.json`, the ranges its models copied from the game's own files (Cheep Cheep Falls' trees and textures, Blooper Bay's sea and rocks). `make_patch.py` turns those into copy instructions (and searches Cheep Cheep Falls' collision file for the tree meshes the collision files reuse), so only the course's own geometry goes into the patch.
